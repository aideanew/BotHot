"""R9 验收测试：back-channel logout（OIDC Back-Channel Logout 1.0 子集）。

覆盖（R9 §5 SPEC + §4 A6）：
- RS256 验签通过 → 按 sub 删除该用户**全部**本地会话；users 锚点保留；不误删他人会话；
- alg=none / 签名伪造 / 未知 kid / iss 不符 / aud 不符 / 缺 events / 含 nonce / iat 超窗 → 拒绝；
- iss/aud 期望值未配置 → 拒绝（本端点不得 fail-open）；
- JWKS 不可达且无缓存 → 拒绝（fail-closed）；缓存命中时 JWKS 不可达仍可验；
- kid 轮换后强制刷新取新钥；
- 端点恒 200 同形响应（不泄露校验差异）；不外呼主平台 revoke/introspect；幂等；
- Redis 侧 delete_by_sub 走 SCAN，跳过损坏记录。
"""

from __future__ import annotations

import base64
import fnmatch
import json
import time
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from fastapi.testclient import TestClient

from app.api.v1.auth import get_auth_service
from app.core.config import Settings
from app.main import create_app
from app.providers.aidean import AideanProviderClient
from app.repositories.user import InMemoryUserStore
from app.services.auth import AuthService, InMemorySessionStore, InMemorySsoStateStore
from app.services.auth.logout_token import (
    LOGOUT_EVENT,
    InvalidLogoutToken,
    JwksVerifier,
    verify_logout_token,
)
from app.services.auth.session_store import RedisSessionStore, SessionRecord

ISSUER = "http://aidean-idp.test"
CLIENT_ID = "wechat-rag"
REDIRECT_URI = "https://wechat-rag.aidean.local/auth/aidean/callback"
SUB = "user-1"

# 2048 位 RSA：单模块内生成一次，约 0.1-0.5s
_RSA: list[RSAPrivateKey] = []


def _rsa() -> RSAPrivateKey:
    if not _RSA:
        _RSA.append(rsa.generate_private_key(public_exponent=65537, key_size=2048))
    return _RSA[0]


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _jwk(public_key: RSAPublicKey, kid: str) -> dict[str, str]:
    """JWK 形状与主平台 `lib/features/auth/keys.ts` 一致（无 padding）。"""
    nums = public_key.public_numbers()
    return {
        "kty": "RSA",
        "n": _b64(nums.n.to_bytes((nums.n.bit_length() + 7) // 8)),
        "e": _b64(nums.e.to_bytes((nums.e.bit_length() + 7) // 8)),
        "kid": kid,
        "alg": "RS256",
        "use": "sig",
    }


def _jwks_response(keys: dict[str, RSAPublicKey]) -> httpx.Response:
    body = {"keys": [_jwk(k, kid) for kid, k in keys.items()]}
    return httpx.Response(200, json=body, headers={"cache-control": "public, max-age=300"})


def _sign(
    payload: dict[str, Any],
    *,
    key: RSAPrivateKey,
    kid: str = "kid-1",
    alg: str = "RS256",
) -> str:
    """用 key 对 header/payload 签名（alg 字段可被篡改以测试算法降级拒绝）。"""
    header = json.dumps({"alg": alg, "kid": kid}).encode()
    body = json.dumps(payload).encode()
    signing_input = f"{_b64(header)}.{_b64(body)}".encode()
    sig = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{_b64(header)}.{_b64(body)}.{_b64(sig)}"


def _payload(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "events": {LOGOUT_EVENT: {}},
        "sub": SUB,
        "sid": "chain-1",
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "jti": "logout-1",
        "iat": int(time.time()),
    }
    base.update(overrides)
    return base


def _token(
    key: RSAPrivateKey | None = None, kid: str = "kid-1", alg: str = "RS256", **overrides: Any
) -> str:
    return _sign(_payload(**overrides), key=key or _rsa(), kid=kid, alg=alg)


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "oidc_redirect_uri": REDIRECT_URI,
        "session_cookie_secure": False,
        "oidc_issuer_expected": ISSUER,
        "oidc_audience_expected": CLIENT_ID,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


class FlipJwks:
    """状态可控的 JWKS 端点：翻转 `status` 可模拟主平台在缓存有效期内故障。"""

    def __init__(self, keys: dict[str, RSAPublicKey] | None = None) -> None:
        self.keys = keys if keys is not None else {"kid-1": _rsa().public_key()}
        self.status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "boom"})
        if request.url.path != "/.well-known/jwks.json":
            return httpx.Response(404, json={"error": "not_found"})
        return _jwks_response(self.keys)


def _verifier(keys: dict[str, RSAPublicKey] | None = None, *, status: int = 200) -> JwksVerifier:
    """JWKS 走 MockTransport，零真实请求。`status != 200` 模拟主平台故障。"""
    flip = FlipJwks(keys)
    flip.status = status
    return JwksVerifier(ISSUER, client=httpx.AsyncClient(transport=httpx.MockTransport(flip.handler)))


class RecordingIdP:
    """只记录调用：用于断言 back-channel 路径不外呼主平台 revoke/introspect。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        return httpx.Response(200, json={})


async def _seed(store: InMemorySessionStore, sub: str, count: int = 1) -> list[str]:
    ids: list[str] = []
    for i in range(count):
        record = SessionRecord(
            session_id=f"s-{sub}-{i}",
            sub=sub,
            email=f"{sub}@aidean.local",
            nickname="老板",
            access_token="access-x",
            refresh_token="refresh-x",
            access_expires_at=time.time() + 900,
        )
        await store.create(record, 3600)
        ids.append(record.session_id)
    return ids


async def _service(
    *,
    jwks: JwksVerifier | None = None,
    idp: RecordingIdP | None = None,
    **settings_overrides: Any,
) -> tuple[AuthService, InMemorySessionStore, InMemoryUserStore, RecordingIdP]:
    idp = idp or RecordingIdP()
    http = httpx.AsyncClient(transport=httpx.MockTransport(idp.handler))
    client = AideanProviderClient(ISSUER, CLIENT_ID, "dev-secret-test", client=http)
    user_store = InMemoryUserStore()
    session_store = InMemorySessionStore()
    svc = AuthService(
        client,
        InMemorySsoStateStore(),
        session_store,
        user_store,
        _settings(**settings_overrides),
        jwks=jwks,
    )
    return svc, session_store, user_store, idp


def _client_with(svc: AuthService) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: svc
    return TestClient(app, follow_redirects=False)


def _http_post(svc: AuthService, token: str) -> httpx.Response:
    return _client_with(svc).post(
        "/api/v1/auth/backchannel-logout", data={"logout_token": token}
    )


# ------------------------------------------------------------------ 验签层


async def test_verify_accepts_valid_logout_token() -> None:
    """验签通过 → 返回 sub/sid 子集。"""
    claims = await verify_logout_token(
        _token(),
        jwks=_verifier(),
        expected_issuer=ISSUER,
        expected_audience=CLIENT_ID,
        max_age_seconds=300,
    )
    assert claims.sub == SUB
    assert claims.sid == "chain-1"


@pytest.mark.parametrize(
    "mutate,reason",
    [
        (lambda p: p.update({"events": {"other": {}}}), "no_events"),
        (lambda p: p.pop("events"), "no_events"),
        (lambda p: p.update({"nonce": "n-1"}), "nonce_rejected"),
        (lambda p: p.update({"iss": "http://evil.test"}), "issuer_mismatch"),
        (lambda p: p.update({"aud": "another-client"}), "audience_mismatch"),
        (lambda p: p.update({"sub": ""}), "no_sub"),
        (lambda p: p.pop("sub"), "no_sub"),
        (lambda p: p.pop("iat"), "missing_iat"),
        (lambda p: p.update({"iat": int(time.time()) - 600}), "stale_iat"),
        (lambda p: p.update({"iat": int(time.time()) + 600}), "stale_iat"),
    ],
)
async def test_verify_rejects_claims(mutate: Any, reason: str) -> None:
    """claims 校验逐项 fail-closed（R9 §5.2 步骤 4-9）。"""
    payload = _payload()
    mutate(payload)
    token = _sign(payload, key=_rsa())
    with pytest.raises(InvalidLogoutToken) as exc:
        await verify_logout_token(
            token,
            jwks=_verifier(),
            expected_issuer=ISSUER,
            expected_audience=CLIENT_ID,
            max_age_seconds=300,
        )
    assert exc.value.reason == reason


@pytest.mark.parametrize(
    "token,reason",
    [
        pytest.param(_token(alg="none"), "invalid_alg", id="alg-none"),
        pytest.param(_token(alg="HS256"), "invalid_alg", id="alg-hs256"),
        pytest.param(_token(kid="kid-unknown"), "unknown_kid", id="unknown-kid"),
    ],
)
async def test_verify_rejects_header(token: str, reason: str) -> None:
    """算法降级 / 未知 kid 拒绝（R9 §5.2 步骤 1-2）。"""
    with pytest.raises(InvalidLogoutToken) as exc:
        await verify_logout_token(
            token,
            jwks=_verifier(),
            expected_issuer=ISSUER,
            expected_audience=CLIENT_ID,
            max_age_seconds=300,
        )
    assert exc.value.reason == reason


async def test_verify_rejects_tampered_signature() -> None:
    """payload 被篡改后签名不再匹配（R9 §5.2 步骤 3）。"""
    head, _payload_b64, sig = _sign(_payload(), key=_rsa()).split(".")
    forged = _b64(json.dumps(_payload(sub="user-2")).encode())
    with pytest.raises(InvalidLogoutToken) as exc:
        await verify_logout_token(
            f"{head}.{forged}.{sig}",
            jwks=_verifier(),
            expected_issuer=ISSUER,
            expected_audience=CLIENT_ID,
            max_age_seconds=300,
        )
    assert exc.value.reason == "invalid_sig"


async def test_verify_rejects_wrong_key_signature() -> None:
    """其他私钥签的 token 必须被拒（不可误接受）。"""
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _sign(_payload(), key=other)
    with pytest.raises(InvalidLogoutToken) as exc:
        await verify_logout_token(
            token,
            jwks=_verifier(),
            expected_issuer=ISSUER,
            expected_audience=CLIENT_ID,
            max_age_seconds=300,
        )
    assert exc.value.reason == "invalid_sig"


async def test_verify_accepts_audience_as_list() -> None:
    """`aud` 为数组时任一匹配即通过（OIDC 标准形态）。"""
    token = _token(aud=[CLIENT_ID, "another-client"])
    claims = await verify_logout_token(
        token,
        jwks=_verifier(),
        expected_issuer=ISSUER,
        expected_audience=CLIENT_ID,
        max_age_seconds=300,
    )
    assert claims.sub == SUB


@pytest.mark.parametrize("issuer,audience", [("x", ""), ("", "x"), ("", "")])
async def test_verify_rejects_when_expected_claims_unset(
    issuer: str, audience: str
) -> None:
    """iss/aud 期望值未配置 → 拒绝，**不得沿用 userinfo 路径的 fail-open**（D4）。

    本端点无 client 凭证可校验，issuer/audience 是唯一的接收方证明。
    """
    with pytest.raises(InvalidLogoutToken) as exc:
        await verify_logout_token(
            _token(),
            jwks=_verifier(),
            expected_issuer=issuer,
            expected_audience=audience,
            max_age_seconds=300,
        )
    assert exc.value.reason == "misconfigured_expected_claims"


async def test_verify_rejects_malformed_token() -> None:
    for junk in ["", "not-a-jwt", "a.b", "a.b.c.d", "!!not-base64!!.###"]:
        with pytest.raises(InvalidLogoutToken) as exc:
            await verify_logout_token(
                junk,
                jwks=_verifier(),
                expected_issuer=ISSUER,
                expected_audience=CLIENT_ID,
                max_age_seconds=300,
            )
        assert exc.value.reason == "malformed_token"


# ------------------------------------------------------------------ JWKS 层


async def test_jwks_fails_closed_when_unreachable_and_cache_empty() -> None:
    """JWKS 不可达且无缓存 → 拒绝校验（fail-closed，不降级为「不校验」）。"""
    with pytest.raises(InvalidLogoutToken) as exc:
        await verify_logout_token(
            _token(),
            jwks=_verifier(status=500),
            expected_issuer=ISSUER,
            expected_audience=CLIENT_ID,
            max_age_seconds=300,
        )
    assert exc.value.reason == "unknown_kid"


async def test_jwks_refreshes_on_key_rotation() -> None:
    """主平台轮换密钥：缓存只有旧 kid 时强制刷新取新钥，新 token 可验。"""
    old = _rsa()
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = JwksVerifier(
        ISSUER,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _req: _jwks_response({"kid-old": old.public_key()})
            )
        ),
    )
    claims = await verify_logout_token(
        _token(kid="kid-old"),
        jwks=verifier,
        expected_issuer=ISSUER,
        expected_audience=CLIENT_ID,
        max_age_seconds=300,
    )
    assert claims.sub == SUB

    # 主平台发布新钥，旧钥仍在（current+previous 并存）
    verifier = JwksVerifier(
        ISSUER,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _req: _jwks_response(
                    {"kid-old": old.public_key(), "kid-new": new_key.public_key()}
                )
            )
        ),
    )
    old_claims = await verify_logout_token(
        _token(kid="kid-old"),
        jwks=verifier,
        expected_issuer=ISSUER,
        expected_audience=CLIENT_ID,
        max_age_seconds=300,
    )
    new_claims = await verify_logout_token(
        _token(key=new_key, kid="kid-new"),  # 必须用新私钥签：换 kid 不换钥 = 签名不匹配
        jwks=verifier,
        expected_issuer=ISSUER,
        expected_audience=CLIENT_ID,
        max_age_seconds=300,
    )
    assert old_claims.sub == new_claims.sub == SUB


# ------------------------------------------------------------------ 服务层


async def test_backchannel_deletes_all_sessions_of_sub() -> None:
    """验签通过 → 删除该 sub 的**全部**会话（多设备），且不误删他人、保留 users 锚点。"""
    user_store = InMemoryUserStore()
    await user_store.upsert_by_sub(SUB, "dev@aidean.local", "老板")
    svc, store, _, idp = await _service(jwks=_verifier())
    await user_store.upsert_by_sub("user-2", "u2@aidean.local", "二号")

    own = await _seed(store, SUB, 2)
    other = await _seed(store, "user-2", 1)

    result = await svc.handle_backchannel_logout(_token())
    assert result["verified"] is True
    assert result["reason"] == "verified"
    assert result["sessionsDeleted"] == 2
    assert result["subPrefix"] == SUB[:8]

    for session_id in own:
        assert await store.get(session_id) is None
    assert await store.get(other[0]) is not None  # 他人会话不受影响
    assert user_store.get_by_sub(SUB) is not None  # 身份锚点保留
    assert idp.calls == []  # 不外呼主平台（不 revoke、不 introspect）


async def test_backchannel_is_idempotent() -> None:
    """重复投递同一 token 无害（第二次删 0 条）。"""
    svc, store, _, _ = await _service(jwks=_verifier())
    await _seed(store, SUB, 1)
    first = await svc.handle_backchannel_logout(_token())
    second = await svc.handle_backchannel_logout(_token())
    assert first["sessionsDeleted"] == 1
    assert second["sessionsDeleted"] == 0


@pytest.mark.parametrize(
    "token,reason",
    [
        pytest.param(_token(alg="none"), "invalid_alg", id="alg-none"),
        pytest.param(_token(kid="kid-unknown"), "unknown_kid", id="unknown-kid"),
        pytest.param(_token(iss="http://evil.test"), "issuer_mismatch", id="iss"),
        pytest.param(_token(aud="another-client"), "audience_mismatch", id="aud"),
        pytest.param(_token(nonce="n-1"), "nonce_rejected", id="nonce"),
        pytest.param(
            _token(iat=int(time.time()) - 600), "stale_iat", id="iat-out-of-window"
        ),
    ],
)
async def test_backchannel_invalid_token_deletes_nothing(token: str, reason: str) -> None:
    """无效 token 不删任何会话（含他人会话）。"""
    svc, store, _, idp = await _service(jwks=_verifier())
    await _seed(store, SUB, 2)
    result = await svc.handle_backchannel_logout(token)
    assert result["verified"] is False
    assert result["reason"] == reason
    assert result["sessionsDeleted"] == 0
    assert await store.get(f"s-{SUB}-0") is not None
    assert idp.calls == []


async def test_backchannel_empty_token_and_missing_jwks() -> None:
    """缺 token / 未装配 JWKS → 拒绝且零删除（fail-closed）。"""
    svc, store, _, _ = await _service(jwks=_verifier())
    await _seed(store, SUB, 1)
    assert (await svc.handle_backchannel_logout(""))["reason"] == "missing_token"

    no_jwks, store2, _, _ = await _service(jwks=None)
    await _seed(store2, SUB, 1)
    assert (await no_jwks.handle_backchannel_logout(_token()))["reason"] == "jwks_not_configured"
    assert await store2.get(f"s-{SUB}-0") is not None


async def test_backchannel_still_verifies_when_jwks_unreachable_but_cache_warm() -> None:
    """JWKS 先成功缓存，之后主平台故障 → 仍用缓存验签（不阻断登出）。"""
    flip = FlipJwks()
    svc, store, _, _ = await _service(
        jwks=JwksVerifier(ISSUER, client=httpx.AsyncClient(transport=httpx.MockTransport(flip.handler)))
    )
    await _seed(store, SUB, 1)
    assert (await svc.handle_backchannel_logout(_token()))["sessionsDeleted"] == 1

    flip.status = 500  # 主平台故障，缓存仍在 TTL 内
    await _seed(store, SUB, 1)
    assert (await svc.handle_backchannel_logout(_token()))["sessionsDeleted"] == 1


# ------------------------------------------------------------------ HTTP 层


def _shape(body: dict[str, Any]) -> dict[str, Any]:
    """剔除每请求唯一的 requestId，比较「同形响应」。"""
    return {k: v for k, v in body.items() if k != "requestId"}


async def test_endpoint_always_200_same_shape() -> None:
    """端点恒 200 同形响应：不向主平台泄露校验结果差异（D5）。"""
    svc, _, _, _ = await _service(jwks=_verifier())
    valid_shape: dict[str, Any] | None = None
    for token, label in [
        (_token(), "valid"),
        (_token(alg="none"), "bad-alg"),
        (_token(iss="http://evil.test"), "bad-iss"),
        ("garbage", "garbage"),
    ]:
        resp = _http_post(svc, token)
        assert resp.status_code == 200, label
        shape = _shape(resp.json())
        if label == "valid":
            valid_shape = shape
        else:
            assert shape == valid_shape, label
    assert valid_shape == {"code": 0, "message": "ok", "data": {"received": True}}


async def test_endpoint_deletes_sessions_over_http() -> None:
    """端到端：POST form → 验签 → 会话销毁（服务端 HttpOnly cookie 会话随之失效）。"""
    svc, store, _, _ = await _service(jwks=_verifier())
    session_id = (await _seed(store, SUB, 1))[0]

    resp = _client_with(svc).post(
        "/api/v1/auth/backchannel-logout",
        data={"logout_token": _token()},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200
    assert await store.get(session_id) is None


async def test_endpoint_ignores_non_form_body() -> None:
    """非 form 请求体按缺失处理（恒 200），不删会话。"""
    svc, store, _, _ = await _service(jwks=_verifier())
    session_id = (await _seed(store, SUB, 1))[0]

    resp = _client_with(svc).post(
        "/api/v1/auth/backchannel-logout",
        content=json.dumps({"logout_token": _token()}).encode(),
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == {"received": True}
    assert await store.get(session_id) is not None


async def test_endpoint_survives_without_any_main_platform_call() -> None:
    """除 JWKS 取钥外，整条路径零主平台调用（fire-and-forget 5s 超时约束）。"""
    idp = RecordingIdP()
    svc, _, _, _ = await _service(jwks=_verifier(), idp=idp)
    assert _http_post(svc, _token()).status_code == 200
    assert all(path != "/oauth/revoke" for _method, path in idp.calls)
    assert all(path != "/oauth/introspect" for _method, path in idp.calls)


# ------------------------------------------------------------------ Redis 层


class FakeRedis:
    """内存版 Redis 子集（get/setex/delete/scan），用于隔离 SCAN 逻辑。"""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.deleted: list[str] = []

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> None:
        self.data[key] = value

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)
        self.deleted.append(key)

    async def scan(
        self, cursor: int = 0, match: str = "*", count: int = 100
    ) -> tuple[int, list[str]]:
        assert cursor == 0  # 单轮即耗尽，验证迭代终止条件
        return 0, [k for k in self.data if fnmatch.fnmatchcase(k, match)]


async def test_redis_delete_by_sub_scans_and_skips_corrupt_records() -> None:
    """SCAN 全量比对（不建二级索引，D2）；跳过损坏记录与其他前缀键。"""
    fake = FakeRedis()
    store = RedisSessionStore(fake)

    own = SessionRecord(
        session_id="a1", sub=SUB, email="a@x", nickname="A",
        access_token="at", refresh_token="rt", access_expires_at=time.time() + 900,
    )
    other = SessionRecord(
        session_id="b1", sub="user-2", email="b@x", nickname="B",
        access_token="at", refresh_token="rt", access_expires_at=time.time() + 900,
    )
    await store.create(own, 3600)
    await store.create(other, 3600)
    # 干扰：损坏记录 + 非会话前缀键（如 state store）
    fake.data["sso:session:corrupt"] = "{not json"
    fake.data["sso:state:s123"] = "payload"

    assert await store.delete_by_sub(SUB) == 1
    assert fake.deleted == ["sso:session:a1"]
    assert fake.data["sso:session:b1"] is not None
    assert fake.data["sso:session:corrupt"] is not None  # 损坏记录不清理，留给 TTL
    assert fake.data["sso:state:s123"] is not None  # 前缀外键不受影响
