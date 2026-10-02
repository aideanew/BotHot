"""B-T3 验收测试：SSO 授权码流 + 会话生命周期。

覆盖（任务卡验收项）：
- state 篡改 → 10002；state 单次消费（重放拒绝）；
- code 重放 → 10003（主平台 invalid_grant 透传）；
- refresh 旧值复用 → 拒绝；轮换链正常推进；
- /auth/me 聚合 userinfo + 实时 wallet；access 过期自动 refresh 一次；
- logout 撤销 refresh 链 + 会话删除。

主平台以进程内有状态伪 IdP 模拟（httpx MockTransport，零真实请求）。
"""

from __future__ import annotations

import base64
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.v1.auth import get_auth_service
from app.core.config import Settings
from app.core.errors import SsoTokenExchangeError
from app.main import create_app
from app.models.entities import User
from app.providers.aidean import AideanProviderClient
from app.repositories.user import InMemoryUserStore
from app.services.auth import (
    AuthService,
    InMemorySessionStore,
    InMemorySsoStateStore,
)
from app.services.auth.session_store import (
    RedisSessionStore,  # noqa: F401  # 确认可导入
    SessionRecord,
)
from app.services.auth.state_store import RedisSsoStateStore  # noqa: F401

ISSUER = "http://aidean-idp.test"
CLIENT_ID = "wechat-rag"
CLIENT_SECRET = "dev-secret-test"
REDIRECT_URI = "https://wechat-rag.aidean.local/auth/aidean/callback"


class FakeAideanIdP:
    """有状态伪主平台：code 一次性 / refresh 轮换链 / Basic 服务间认证。"""

    def __init__(self, userinfo_extra: dict[str, str] | None = None) -> None:
        self.codes: dict[str, bool] = {}
        self.refresh_chain: dict[str, bool] = {}
        self.valid_access: set[str] = set()
        self.last_revoke: str | None = None
        self._seq = 0
        self._userinfo_extra = userinfo_extra or {}

    def issue_code(self) -> str:
        self._seq += 1
        code = f"code-{self._seq}"
        self.codes[code] = True
        return code

    def _issue_pair(self) -> tuple[str, str, int]:
        self._seq += 1
        access, refresh = f"access-{self._seq}", f"refresh-{self._seq}"
        self.valid_access.add(access)
        self.refresh_chain[refresh] = True
        return access, refresh, 900

    def _basic_ok(self, request: httpx.Request) -> bool:
        expected = "Basic " + base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        return request.headers.get("authorization") == expected

    def handler(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        if method == "POST" and path == "/oauth/token":
            if not self._basic_ok(request):
                return httpx.Response(401, json={"error": "invalid_client"})
            form = parse_qs(request.read().decode())
            grant = form.get("grant_type", [""])[0]
            if grant == "authorization_code":
                code = form.get("code", [""])[0]
                redirect = form.get("redirect_uri", [""])[0]
                if not self.codes.pop(code, False) or redirect != REDIRECT_URI:
                    # code 一次性：pop 即失效 → 重放/过期统一 invalid_grant
                    return httpx.Response(
                        400, json={"error": "invalid_grant", "error_description": "code used or expired"}
                    )
                access, refresh, expires = self._issue_pair()
                return httpx.Response(
                    200,
                    json={
                        "access_token": access,
                        "token_type": "Bearer",
                        "expires_in": expires,
                        "refresh_token": refresh,
                        "id_token": "",
                        "scope": "openid profile wallet:read",
                    },
                )
            if grant == "refresh_token":
                token = form.get("refresh_token", [""])[0]
                if not self.refresh_chain.pop(token, False):
                    # 轮换链：旧值复用（重放检测）→ 拒绝；真实主平台此时整链撤销
                    return httpx.Response(
                        400, json={"error": "invalid_grant", "error_description": "refresh replay detected"}
                    )
                access, refresh, expires = self._issue_pair()
                return httpx.Response(
                    200,
                    json={
                        "access_token": access,
                        "token_type": "Bearer",
                        "expires_in": expires,
                        "refresh_token": refresh,
                        "id_token": "",
                        "scope": "openid profile wallet:read",
                    },
                )
            return httpx.Response(400, json={"error": "unsupported_grant_type"})

        if method == "GET" and path == "/oauth/userinfo":
            token = request.headers.get("authorization", "").removeprefix("Bearer ")
            if token in self.valid_access:
                return httpx.Response(
                    200,
                    json={
                        "sub": "user-1",
                        "email": "dev@aidean.local",
                        "nickname": "老板",
                        "tier": "PRO",
                        "role": "USER",
                        **self._userinfo_extra,
                    },
                )
            return httpx.Response(401, json={"error": "invalid_token"})

        if method == "GET" and path == "/api/v1/internal/billing/wallet":
            if not self._basic_ok(request):
                return httpx.Response(401, json={"code": 10001, "message": "client 认证失败"})
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "message": "ok",
                    "data": {
                        "user": {"id": "user-1", "tier": "PRO", "status": "ACTIVE", "nickname": "老板"},
                        "wallet": {
                            "balanceYuan": "12.34",
                            "heldYuan": "0.00",
                            "availableYuan": "12.34",
                            "currency": "CNY",
                        },
                    },
                },
            )

        if method == "POST" and path == "/oauth/revoke":
            if not self._basic_ok(request):
                return httpx.Response(401, json={"error": "invalid_client"})
            form = parse_qs(request.read().decode())
            token = form.get("token", [""])[0]
            self.last_revoke = token
            self.refresh_chain.pop(token, None)  # 整链撤销的伪实现：该 refresh 失效
            return httpx.Response(200, json={})

        return httpx.Response(404, json={"error": "not_found"})


def _settings() -> Settings:
    return Settings(  # type: ignore[call-arg]  # pydantic-settings 运行时合法，类型桩缺失
        _env_file=None,
        oidc_redirect_uri=REDIRECT_URI,
        session_cookie_secure=False,
    )


def _svc_bundle() -> tuple[AuthService, FakeAideanIdP, InMemoryUserStore, InMemorySessionStore]:
    idp = FakeAideanIdP()
    http = httpx.AsyncClient(transport=httpx.MockTransport(idp.handler))
    client = AideanProviderClient(ISSUER, CLIENT_ID, CLIENT_SECRET, client=http)
    user_store = InMemoryUserStore()
    session_store = InMemorySessionStore()
    svc = AuthService(client, InMemorySsoStateStore(), session_store, user_store, _settings())
    return svc, idp, user_store, session_store


def _client_with(svc: AuthService) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: svc
    # follow_redirects=False：login 的 302 指向伪 IdP 域名，不跟随（由断言校验 Location）
    return TestClient(app, follow_redirects=False)


def _login_state(client: TestClient) -> str:
    resp = client.get("/api/v1/auth/login")
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith(f"{ISSUER}/oauth/authorize?")
    query = parse_qs(urlparse(location).query)
    assert query["response_type"] == ["code"]
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == [REDIRECT_URI]
    assert query["scope"] == ["openid profile wallet:read"]
    return query["state"][0]


# ------------------------------------------------------------------ 测试


def test_login_builds_authorize_url_with_state() -> None:
    """login 返回 302 且 authorize 参数齐全、state ≥16 字符。"""
    svc, *_ = _svc_bundle()
    client = _client_with(svc)
    state = _login_state(client)
    assert len(state) >= 16


def test_authorize_url_dual_base_url_split() -> None:
    """裁决 B（A-T21）：authorize 用浏览器侧 public 基址；未配置时回落 issuer 单值语义。"""
    idp = FakeAideanIdP()
    http = httpx.AsyncClient(transport=httpx.MockTransport(idp.handler))
    # 回落：public_base_url 缺省 → authorize 仍指 issuer（既有部署/生产零变更）
    fallback = AideanProviderClient(ISSUER, CLIENT_ID, CLIENT_SECRET, client=http)
    assert fallback.authorize_url("s1", REDIRECT_URI, "openid").startswith(f"{ISSUER}/oauth/authorize?")
    # 拆分：public 指浏览器可达 localhost，token 仍走容器侧 host.docker.internal
    split = AideanProviderClient(
        "http://host.docker.internal:3000",
        CLIENT_ID,
        CLIENT_SECRET,
        client=http,
        public_base_url="http://localhost:3000",
    )
    assert split.authorize_url("s2", REDIRECT_URI, "openid").startswith("http://localhost:3000/oauth/authorize?")


def test_callback_rejects_tampered_state() -> None:
    """验收项：state 篡改 → 10002。"""
    svc, idp, *_ = _svc_bundle()
    client = _client_with(svc)
    code = idp.issue_code()
    resp = client.get(f"/api/v1/auth/callback?code={code}&state=tampered-state")
    assert resp.status_code == 400
    assert resp.json()["code"] == 10002


def test_state_is_single_use() -> None:
    """state 单次消费：同一 state 第二次回调即使 code 新鲜也被拒。"""
    svc, idp, *_ = _svc_bundle()
    client = _client_with(svc)
    state = _login_state(client)
    first = client.get(f"/api/v1/auth/callback?code={idp.issue_code()}&state={state}")
    assert first.status_code == 200
    second = client.get(f"/api/v1/auth/callback?code={idp.issue_code()}&state={state}")
    assert second.status_code == 400
    assert second.json()["code"] == 10002


def test_full_login_flow_establishes_session_and_me() -> None:
    """登录→callback→/me：sub/email/tier + 实时 wallet 聚合，全部走信封。"""
    svc, idp, user_store, _ = _svc_bundle()
    client = _client_with(svc)
    state = _login_state(client)
    callback = client.get(f"/api/v1/auth/callback?code={idp.issue_code()}&state={state}")
    assert callback.status_code == 200
    body = callback.json()
    assert body["code"] == 0 and body["data"]["sub"] == "user-1"
    cookie = callback.headers["set-cookie"]
    assert "bothot_session=" in cookie and "HttpOnly" in cookie
    # 本地 users 已按 sub upsert
    assert user_store.get_by_sub("user-1") is not None

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    data = me.json()["data"]
    assert data["user"]["sub"] == "user-1"
    assert data["user"]["tier"] == "PRO"
    assert data["wallet"]["availableYuan"] == "12.34"  # 余额实时查询，不落库
    # 无 DB 工厂（桩路径）→ fail closed，不得猜成 admin
    assert data["user"]["is_admin"] is False


async def test_me_reports_is_admin_from_local_role(db_session) -> None:  # type: ignore[no-untyped-def]
    """is_admin 取自本地 users.role（授权判据同源），不是 userinfo 的 role。

    伪 IdP 回显 `"role": "USER"`（主平台大写枚举，与本地阶梯不同源不同形）：
    若前端拿它门禁，会与后端 10004 双向分歧。本用例证明真 PG 路径下
    is_admin 只随本地列变化。
    """
    conn = await db_session.connection()
    factory = async_sessionmaker(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")

    idp = FakeAideanIdP()
    http = httpx.AsyncClient(transport=httpx.MockTransport(idp.handler))
    client_impl = AideanProviderClient(ISSUER, CLIENT_ID, CLIENT_SECRET, client=http)
    svc = AuthService(
        client_impl,
        InMemorySsoStateStore(),
        InMemorySessionStore(),
        InMemoryUserStore(),
        _settings(),
        factory,
    )
    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: svc
    http_client = TestClient(app, follow_redirects=False)

    state = _login_state(http_client)
    callback = http_client.get(f"/api/v1/auth/callback?code={idp.issue_code()}&state={state}")
    assert callback.status_code == 200

    # 本地列默认 user → is_admin False，虽 userinfo 声称 role=USER
    assert http_client.get("/api/v1/auth/me").json()["data"]["user"]["is_admin"] is False

    # 显式授予 admin（唯一升权路径：一条可审计 UPDATE）→ is_admin True
    user = await db_session.scalar(select(User).where(User.sub == "user-1"))
    assert user is not None
    user.role = "admin"
    await db_session.flush()

    assert http_client.get("/api/v1/auth/me").json()["data"]["user"]["is_admin"] is True


def test_code_replay_rejected() -> None:
    """验收项：code 重放（新 state + 已用 code）→ 主平台 invalid_grant → 10003。"""
    svc, idp, *_ = _svc_bundle()
    client = _client_with(svc)
    code = idp.issue_code()
    state1 = _login_state(client)
    assert client.get(f"/api/v1/auth/callback?code={code}&state={state1}").status_code == 200
    state2 = _login_state(client)
    replay = client.get(f"/api/v1/auth/callback?code={code}&state={state2}")
    assert replay.status_code == 401  # SsoTokenExchangeError.http_status
    assert replay.json()["code"] == 10003


def test_refresh_rotation_and_old_value_reuse_rejected() -> None:
    """验收项：refresh 旧值复用 → 拒绝；会话内轮换链正常推进。"""
    svc, idp, _, session_store = _svc_bundle()
    client = _client_with(svc)
    state = _login_state(client)
    callback = client.get(f"/api/v1/auth/callback?code={idp.issue_code()}&state={state}")
    sid = callback.cookies["bothot_session"]
    record_before = session_store._sessions[sid][0]
    old_refresh = record_before.refresh_token

    # 会话内连续轮换两次均成功（链推进）
    import asyncio

    asyncio.run(svc.refresh_session(sid))
    token_after_first = session_store._sessions[sid][0].refresh_token
    assert token_after_first != old_refresh  # 最新一代已可靠持久化
    asyncio.run(svc.refresh_session(sid))
    assert session_store._sessions[sid][0].refresh_token != token_after_first

    # 旧值复用（直接拿旧 refresh 打主平台）→ invalid_grant → SsoTokenExchangeError
    with pytest.raises(SsoTokenExchangeError):
        asyncio.run(svc._client.refresh(old_refresh))


def test_me_auto_refreshes_once_when_access_expired() -> None:
    """/me 遇 userinfo 401 → 自动 refresh 一次 → 重试成功（指南 §6）。"""
    svc, idp, _, session_store = _svc_bundle()
    client = _client_with(svc)
    state = _login_state(client)
    callback = client.get(f"/api/v1/auth/callback?code={idp.issue_code()}&state={state}")
    sid = callback.cookies["bothot_session"]
    # 模拟 access 过期：伪 IdP 侧作废当前 access
    record = session_store._sessions[sid][0]
    idp.valid_access.discard(record.access_token)
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["data"]["user"]["sub"] == "user-1"


def _unreachable_bundle(
    factory: Any | None = None,
) -> tuple[AuthService, InMemorySessionStore]:
    """主平台连接层不可达（ConnectError）的会话桩——依赖降级路径用。"""

    def transport(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    http = httpx.AsyncClient(transport=httpx.MockTransport(transport))
    client_impl = AideanProviderClient(ISSUER, CLIENT_ID, CLIENT_SECRET, client=http)
    session_store = InMemorySessionStore()
    svc = AuthService(
        client_impl,
        InMemorySsoStateStore(),
        session_store,
        InMemoryUserStore(),
        _settings(),
        factory,
    )
    return svc, session_store


def _dead_record(session_id: str = "sid-unreachable") -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        sub="user-1",
        email="dev@aidean.local",
        nickname="老板",
        access_token="access-dead",
        refresh_token="refresh-dead",
        access_expires_at=time.time() + 900,
    )


async def test_me_provider_unreachable_without_snapshot_keeps_50002() -> None:
    """无本地资料快照（单测桩路径）时保持原 50002 语义，不得凭空捏造身份。"""
    svc, store = _unreachable_bundle()
    await store.create(_dead_record(), 900)
    client = _client_with(svc)
    client.cookies.set("bothot_session", "sid-unreachable")
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 503
    assert resp.json()["code"] == 50002


async def test_me_provider_unreachable_degrades_to_local_profile(db_session) -> None:  # type: ignore[no-untyped-def]
    """有本地 users 行时降级回填资料，不整站 503——会话有效就不该把用户挡回登录页。

    缺陷背景：主平台宕机时 /auth/me 唯一入口 503，前端把整个登录态回落 guest，
    顶栏显示「未登录」，而 spaces/jobs 等域接口其实都可用。
    """
    conn = await db_session.connection()
    factory = async_sessionmaker(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")

    # 本地 users 行必须存在——callback 正常路径会 upsert，此处直接落一行等价数据
    user = (await db_session.execute(select(User).where(User.sub == "user-1"))).scalar_one_or_none()
    if user is None:
        db_session.add(User(sub="user-1", email="dev@aidean.local", nickname="老板"))
        await db_session.flush()

    svc, store = _unreachable_bundle(factory)
    await store.create(_dead_record(), 900)

    client = _client_with(svc)
    client.cookies.set("bothot_session", "sid-unreachable")
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    data = resp.json()["data"]
    # 资料来自本地行，且带降级标记
    assert data["user"]["sub"] == "user-1"
    assert data["user"]["nickname"] == "老板"
    assert data["providerUnreachable"] is True
    # wallet 标记不可查——前端据此显示「余额暂不可查」而非 ¥0.00
    assert data["wallet"]["available"] is False
    # 降级只影响 /me 的资料来源：会话本身仍有效，不该把用户踢回登录页
    assert await svc.current_sub("sid-unreachable") == "user-1"


def test_logout_revokes_chain_and_clears_session() -> None:
    """logout：撤销 refresh 链（仅本产品）+ 会话删除 + 清 cookie；再访问 /me → 10001。"""
    svc, idp, _, session_store = _svc_bundle()
    client = _client_with(svc)
    state = _login_state(client)
    callback = client.get(f"/api/v1/auth/callback?code={idp.issue_code()}&state={state}")
    sid = callback.cookies["bothot_session"]
    refresh_token = session_store._sessions[sid][0].refresh_token

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    assert logout.json()["data"]["logged_out"] is True
    assert idp.last_revoke == refresh_token  # refresh 链已撤销
    assert session_store._sessions.get(sid) is None  # 服务端会话已删除
    assert "bothot_session=" in logout.headers.get("set-cookie", "")

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 401
    assert me.json()["code"] == 10001


def test_me_without_session_returns_10001() -> None:
    """未登录访问 /me → 10001（不泄露会话细节）。"""
    svc, *_ = _svc_bundle()
    client = _client_with(svc)
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == 10001


def test_session_store_backend_switch() -> None:
    """A 返工项：SESSION_STORE 开关生效（memory|redis，默认 memory；Redis 客户端惰性建连）。"""
    from app.api.v1.auth import _build_stores

    memory_settings = _settings()
    state_store, session_store = _build_stores(memory_settings)
    assert isinstance(state_store, InMemorySsoStateStore)
    assert isinstance(session_store, InMemorySessionStore)

    redis_settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        oidc_redirect_uri=REDIRECT_URI,
        session_store_backend="redis",
        redis_url="redis://localhost:6380/0",
    )
    redis_state, redis_session = _build_stores(redis_settings)
    from app.services.auth import RedisSessionStore as _RS
    from app.services.auth import RedisSsoStateStore as _RSS

    assert isinstance(redis_state, _RSS)
    assert isinstance(redis_session, _RS)


def test_callback_with_idp_error_param_maps_to_10003() -> None:
    """主平台以 error 参数回传（invalid_scope 等）→ 10003。"""
    svc, *_ = _svc_bundle()
    client = _client_with(svc)
    resp = client.get("/api/v1/auth/callback?error=invalid_scope&error_description=scope%20not%20registered")
    assert resp.status_code == 401
    assert resp.json()["code"] == 10003


# ---------------------------------------------------------------------------
# R5.1.1：SSO userinfo iss/aud 校验
# ---------------------------------------------------------------------------


def _settings_with_claims(
    issuer: str = "",
    audience: str = "",
) -> Settings:
    """带 iss/aud 期望值的 Settings（空字符串 = 跳过校验，向后兼容）。"""
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        oidc_redirect_uri=REDIRECT_URI,
        session_cookie_secure=False,
        oidc_issuer_expected=issuer,
        oidc_audience_expected=audience,
    )


def _svc_bundle_with_claims(
    issuer: str = "",
    audience: str = "",
    userinfo_extra: dict[str, str] | None = None,
) -> tuple[AuthService, FakeAideanIdP, InMemoryUserStore, InMemorySessionStore]:
    idp = FakeAideanIdP(userinfo_extra=userinfo_extra)
    http = httpx.AsyncClient(transport=httpx.MockTransport(idp.handler))
    client = AideanProviderClient(ISSUER, CLIENT_ID, CLIENT_SECRET, client=http)
    user_store = InMemoryUserStore()
    session_store = InMemorySessionStore()
    svc = AuthService(
        client, InMemorySsoStateStore(), session_store, user_store, _settings_with_claims(issuer, audience)
    )
    return svc, idp, user_store, session_store


def test_callback_rejects_wrong_issuer() -> None:
    """R5.1.1：userinfo iss 不匹配 → 10003（SsoTokenExchangeError），不建立会话。"""
    svc, idp, *_ = _svc_bundle_with_claims(
        issuer=ISSUER,
        userinfo_extra={"iss": "http://evil-idp.example.com", "aud": CLIENT_ID},
    )
    client = _client_with(svc)
    state = _login_state(client)
    resp = client.get(f"/api/v1/auth/callback?code={idp.issue_code()}&state={state}")
    assert resp.status_code == 401
    assert resp.json()["code"] == 10003


def test_callback_rejects_wrong_audience() -> None:
    """R5.1.1：userinfo aud 不匹配 → 10003。"""
    svc, idp, *_ = _svc_bundle_with_claims(
        audience=CLIENT_ID,
        userinfo_extra={"iss": ISSUER, "aud": "some-other-client"},
    )
    client = _client_with(svc)
    state = _login_state(client)
    resp = client.get(f"/api/v1/auth/callback?code={idp.issue_code()}&state={state}")
    assert resp.status_code == 401
    assert resp.json()["code"] == 10003


def test_callback_accepts_matching_claims() -> None:
    """R5.1.1：iss/aud 均匹配 → 正常建立会话。"""
    svc, idp, user_store, _ = _svc_bundle_with_claims(
        issuer=ISSUER,
        audience=CLIENT_ID,
        userinfo_extra={"iss": ISSUER, "aud": CLIENT_ID},
    )
    client = _client_with(svc)
    state = _login_state(client)
    resp = client.get(f"/api/v1/auth/callback?code={idp.issue_code()}&state={state}")
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    assert "bothot_session=" in resp.headers["set-cookie"]
    assert user_store.get_by_sub("user-1") is not None


def test_callback_skips_claim_validation_when_unconfigured() -> None:
    """R5.1.1 向后兼容：未配置 oidc_issuer_expected/oidc_audience_expected 时不校验，正常通过。"""
    svc, idp, *_ = _svc_bundle_with_claims(
        issuer="",  # 未配置
        audience="",  # 未配置
        userinfo_extra={"iss": "http://any-idp.example.com", "aud": "whatever"},
    )
    client = _client_with(svc)
    state = _login_state(client)
    resp = client.get(f"/api/v1/auth/callback?code={idp.issue_code()}&state={state}")
    assert resp.status_code == 200
    assert resp.json()["code"] == 0


def test_callback_rejects_missing_issuer_when_expected() -> None:
    """R6.2.1 fail-closed：配置了 oidc_issuer_expected 但 userinfo 未返回 iss → 10003 拒绝。"""
    svc, idp, *_ = _svc_bundle_with_claims(
        issuer=ISSUER,
        audience="",
    )
    client = _client_with(svc)
    state = _login_state(client)
    resp = client.get(f"/api/v1/auth/callback?code={idp.issue_code()}&state={state}")
    assert resp.status_code == 401
    assert resp.json()["code"] == 10003


def test_callback_rejects_missing_audience_when_expected() -> None:
    """R6.2.1 fail-closed：配置了 oidc_audience_expected 但 userinfo 未返回 aud → 10003 拒绝。"""
    svc, idp, *_ = _svc_bundle_with_claims(
        issuer="",
        audience=CLIENT_ID,
    )
    client = _client_with(svc)
    state = _login_state(client)
    resp = client.get(f"/api/v1/auth/callback?code={idp.issue_code()}&state={state}")
    assert resp.status_code == 401
    assert resp.json()["code"] == 10003


def test_production_guard_rejects_empty_iss_aud() -> None:
    """R6.2.1：生产守卫——APP_ENV=production 时 oidc_issuer_expected/oidc_audience_expected 为空 → 启动拒绝。"""
    prod_settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        app_env="production",
        oidc_redirect_uri=REDIRECT_URI,
        session_cookie_secure=True,
        session_store_backend="redis",
        oidc_client_secret="real-secret",
    )
    violations = prod_settings.production_guard_violations()
    iss_msg = [v for v in violations if "OIDC_ISSUER_EXPECTED" in v]
    aud_msg = [v for v in violations if "OIDC_AUDIENCE_EXPECTED" in v]
    assert len(iss_msg) == 1
    assert len(aud_msg) == 1
