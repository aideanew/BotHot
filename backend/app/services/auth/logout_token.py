"""主平台 JWKS 拉取与 back-channel logout_token 本地 RS256 验签（R9）。

契约来源：主平台 `apps/web/lib/features/oauth/backchannel.ts` +
《子平台SSO接入指南》v1.3 §4（back-channel logout 语义）。

为何必须本地验签：主平台 `/oauth/introspect` **仅支持 refresh 令牌**
（`apps/web/app/oauth/introspect/route.ts:3`），无 RPC 可验证 logout_token，
本地 JWKS 验签是唯一路径。

R5.1.2「不引入 PyJWT」的裁定不变：RS256 = RSA PKCS1v15 + SHA256，
用已在依赖树的 `cryptography` 手写，零新增依赖。
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"

logger = structlog.get_logger(__name__)


class InvalidLogoutToken(Exception):
    """logout_token 校验失败。`reason` 是稳定字符串，供日志聚合，不外泄到响应。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(slots=True)
class LogoutTokenClaims:
    """校验通过的 logout_token 声明子集（只取本方需要的字段）。"""

    sub: str
    sid: str


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _jwk_to_public_key(jwk: dict[str, Any]) -> rsa.RSAPublicKey:
    if jwk.get("kty") != "RSA":
        raise InvalidLogoutToken("unsupported_kty")
    try:
        return rsa.RSAPublicNumbers(
            e=int.from_bytes(_b64url_decode(str(jwk["e"])), "big"),
            n=int.from_bytes(_b64url_decode(str(jwk["n"])), "big"),
        ).public_key()
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidLogoutToken("malformed_jwk") from exc


class JwksVerifier:
    """JWKS 拉取 + 进程内缓存 + 按 kid 选钥。

    缓存 TTL 与主平台 JWKS 端点的 `cache-control: public, max-age=300` 对齐
    （`apps/web/app/.well-known/jwks.json/route.ts`）。

    失败方向 fail-closed：无缓存且拉取失败 → 拒绝校验，**绝不降级为「不校验」**
    （降级等于把登录凭据面变成开放端点）。拉取失败但有旧缓存 → 用旧缓存，
    代价是刚轮换的 kid 可能暂不可用，方向上是多拒而非多收。
    """

    def __init__(
        self,
        issuer_url: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 5.0,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self._jwks_url = f"{issuer_url.rstrip('/')}/.well-known/jwks.json"
        self._client = client
        self._timeout = timeout
        self._cache_ttl_seconds = cache_ttl_seconds
        self._keys: dict[str, rsa.RSAPublicKey] = {}
        self._fetched_at: float = 0.0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def _refresh(self) -> None:
        http = await self._get_client()
        try:
            resp = await http.get(self._jwks_url)
        except httpx.HTTPError as exc:
            logger.warning("JWKS 拉取失败（回退旧缓存，若为空则拒绝校验）: %s", exc)
            return
        if resp.status_code != 200:
            logger.warning("JWKS 端点返回 %s（回退旧缓存）", resp.status_code)
            return
        try:
            keys = resp.json().get("keys", [])
        except json.JSONDecodeError:
            logger.warning("JWKS 响应非 JSON（回退旧缓存）")
            return
        fresh: dict[str, rsa.RSAPublicKey] = {}
        for jwk in keys:
            if not isinstance(jwk, dict):
                continue
            kid = jwk.get("kid")
            if not isinstance(kid, str) or not kid:
                continue
            # 只收 RS256：logout_token 的 alg 必须是 RS256，非 RS256 的 JWK 收了也无用
            if jwk.get("alg") not in (None, "RS256"):
                continue
            try:
                fresh[kid] = _jwk_to_public_key(jwk)
            except InvalidLogoutToken:
                continue
        self._keys = fresh
        self._fetched_at = time.time()
        if not fresh:
            logger.warning("JWKS 未解析出可用 RS256 公钥（回退旧缓存）")

    async def key_for(self, kid: str) -> rsa.RSAPublicKey | None:
        """按 kid 取公钥；未命中时强制刷新一次（覆盖主平台刚轮换密钥的场景）。"""
        if kid in self._keys:
            return self._keys[kid]
        stale = time.time() - self._fetched_at >= self._cache_ttl_seconds
        if stale or not self._keys:
            await self._refresh()
        return self._keys.get(kid)


async def verify_logout_token(
    token: str,
    *,
    jwks: JwksVerifier,
    expected_issuer: str,
    expected_audience: str,
    max_age_seconds: int,
) -> LogoutTokenClaims:
    """fail-closed 校验，任一失败抛 `InvalidLogoutToken(reason)`。

    校验序列（R9 §5.2）：alg → kid → 签名 → iss → aud → events → nonce → sub → iat 窗。
    `iss`/`aud` 期望值**必须已配置**：本端点无 client 凭证可校验，
    issuer/audience 是唯一的接收方证明，不得沿用 userinfo 路径的「未配置则跳过」。
    """
    if not expected_issuer or not expected_audience:
        raise InvalidLogoutToken("misconfigured_expected_claims")

    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidLogoutToken("malformed_token")
    header_b64, payload_b64, sig_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
        signature = _b64url_decode(sig_b64)
    except (ValueError, json.JSONDecodeError) as exc:
        raise InvalidLogoutToken("malformed_token") from exc
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise InvalidLogoutToken("malformed_token")

    if header.get("alg") != "RS256":
        raise InvalidLogoutToken("invalid_alg")

    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise InvalidLogoutToken("missing_kid")
    public_key = await jwks.key_for(kid)
    if public_key is None:
        raise InvalidLogoutToken("unknown_kid")

    try:
        public_key.verify(
            signature,
            f"{header_b64}.{payload_b64}".encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except InvalidSignature as exc:
        raise InvalidLogoutToken("invalid_sig") from exc

    if payload.get("iss") != expected_issuer:
        raise InvalidLogoutToken("issuer_mismatch")

    aud = payload.get("aud")
    accepted = aud == expected_audience or (isinstance(aud, list) and expected_audience in aud)
    if not accepted:
        raise InvalidLogoutToken("audience_mismatch")

    events = payload.get("events")
    if not isinstance(events, dict) or LOGOUT_EVENT not in events:
        raise InvalidLogoutToken("no_events")

    # OIDC Back-Channel Logout 1.0 §2.1：含 nonce 的 logout_token 必须被拒
    # （主平台 side 也不签发 nonce，见 backchannel.ts 注释）
    if "nonce" in payload:
        raise InvalidLogoutToken("nonce_rejected")

    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        raise InvalidLogoutToken("no_sub")

    iat = payload.get("iat")
    if not isinstance(iat, int | float):
        raise InvalidLogoutToken("missing_iat")
    # 主平台不发 exp，RP 自建时间窗；abs() 同时容忍双向时钟偏移。
    # 不设窗 = 该 token 可无限重放，构成可用 DoS 向量（只能删会话，但可反复摧毁受害者会话）。
    if abs(time.time() - float(iat)) > max_age_seconds:
        raise InvalidLogoutToken("stale_iat")

    sid = payload.get("sid")
    return LogoutTokenClaims(sub=sub, sid=sid if isinstance(sid, str) else "")
