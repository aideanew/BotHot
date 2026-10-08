"""Aidean 主平台防腐层：SSO 与钱包端点的唯一出口（B-T3）。

契约来源：《子平台SSO接入指南》v1.0 + M0 报告 §五（T0.7 全链实证）。
本层职责：
- 端点形态/鉴权方式（Basic / Bearer）全部收敛在此，Service 层不感知 HTTP 细节；
- 主平台错误 → 项目错误码映射：token 端点业务拒绝 → 10003，userinfo 401 → 10001，
  网络/5xx → 50002（依赖不可用）。
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core.errors import (
    DependencyUnavailableError,
    SsoTokenExchangeError,
    UnauthenticatedError,
)


@dataclass(slots=True)
class TokenPair:
    """token 端点成功响应（兑换与刷新同形态）。"""

    access_token: str
    refresh_token: str
    expires_in: int
    id_token: str
    scope: str


def decode_id_token_payload(id_token: str) -> dict:
    """解码 id_token 载荷（不验签，仅作 userinfo 的旁证参考）。

    权威身份以 /oauth/userinfo 实时返回为准（本地 RS256 验签依赖 PyJWT，
    新增依赖须 A 批准，见交付报告遗留项）。
    """
    try:
        payload_b64 = id_token.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except Exception as exc:  # noqa: BLE001 - 畸形 token 统一视为兑换失败旁证
        raise SsoTokenExchangeError(f"id_token 解析失败: {type(exc).__name__}") from exc


class AideanProviderClient:
    """主平台端点客户端（authorize/token/userinfo/wallet/revoke）。"""

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
        public_base_url: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        # authorize 302 Location 签发给宿主浏览器，需浏览器可达基址（localhost）；
        # token/userinfo/wallet/revoke 是容器内 httpx 直连，仍走 base_url（host.docker.internal）。
        # 未配置 public_base_url 时回落 base_url（单值语义，向后兼容）。
        self._public_base_url = (public_base_url or base_url).rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._auth = httpx.BasicAuth(client_id, client_secret)
        self._timeout = timeout
        self._client = client  # 测试注入 MockTransport；生产路径惰性自建

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    # -------------------------------------------------- 授权跳转（第 1 步）

    def authorize_url(self, state: str, redirect_uri: str, scope: str) -> str:
        """构造 authorize 跳转地址（state 必填；PKCE 仅公共客户端必填，见交付报告）。

        基址用 _public_base_url（浏览器侧）：签给宿主浏览器的 Location 必须浏览器可达
        （如 localhost），不能用容器侧 host.docker.internal。
        """
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._client_id,
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": state,
            }
        )
        return f"{self._public_base_url}/oauth/authorize?{query}"

    # -------------------------------------------------- token 端点（第 4 步 / 刷新）

    async def _token_request(self, form: dict) -> TokenPair:
        url = f"{self._base_url}/oauth/token"
        try:
            http = await self._get_client()
            resp = await http.post(url, data=form, auth=self._auth)
        except httpx.HTTPError as exc:
            raise DependencyUnavailableError(f"主平台 token 端点不可达: {type(exc).__name__}") from exc
        if resp.status_code in (400, 401):
            # 指南 §6：invalid_grant(code 过期/已用/redirect 不一致/refresh 重放) 等
            is_json = resp.headers.get("content-type", "").startswith("application/json")
            err = resp.json().get("error", "unknown_error") if is_json else resp.text[:120]
            raise SsoTokenExchangeError(f"主平台拒绝令牌请求: {err}")
        if resp.status_code >= 500:
            raise DependencyUnavailableError(f"主平台 token 端点 5xx: {resp.status_code}")
        try:
            body = resp.json()
            return TokenPair(
                access_token=body["access_token"],
                refresh_token=body["refresh_token"],
                expires_in=int(body.get("expires_in", 900)),
                id_token=body.get("id_token", ""),
                scope=body.get("scope", ""),
            )
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise DependencyUnavailableError(f"主平台 token 响应形态异常: {type(exc).__name__}") from exc

    async def exchange_code(self, code: str, redirect_uri: str) -> TokenPair:
        """授权码兑换（code 一次性，60s 有效；重放由主平台 400 拒绝）。"""
        return await self._token_request(
            {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri}
        )

    async def refresh(self, refresh_token: str) -> TokenPair:
        """刷新（轮换链：旧 refresh 立即失效，返回全新对）。"""
        return await self._token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})

    # -------------------------------------------------- 用户资料 / 钱包 / 撤销

    async def userinfo(self, access_token: str) -> dict:
        """Bearer 用户资料（sub/email/nickname/tier/role）。401 → 10001。"""
        url = f"{self._base_url}/oauth/userinfo"
        try:
            http = await self._get_client()
            resp = await http.get(url, headers={"Authorization": f"Bearer {access_token}"})
        except httpx.HTTPError as exc:
            raise DependencyUnavailableError(f"主平台 userinfo 不可达: {type(exc).__name__}") from exc
        if resp.status_code == 401:
            raise UnauthenticatedError("access_token 无效或已过期")
        if resp.status_code >= 500:
            raise DependencyUnavailableError(f"主平台 userinfo 5xx: {resp.status_code}")
        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            raise DependencyUnavailableError("主平台 userinfo 响应非 JSON") from exc

    async def wallet(self, user_id: str) -> dict:
        """服务间钱包实时查询（Basic 认证 + scope wallet:read；余额不落库铁律）。"""
        url = f"{self._base_url}/api/v1/internal/billing/wallet"
        try:
            http = await self._get_client()
            resp = await http.get(url, params={"userId": user_id}, auth=self._auth)
        except httpx.HTTPError as exc:
            raise DependencyUnavailableError(f"主平台 wallet 不可达: {type(exc).__name__}") from exc
        if resp.status_code in (401, 403):
            raise DependencyUnavailableError(f"主平台拒绝 wallet 服务间认证: {resp.status_code}")
        if resp.status_code >= 500:
            raise DependencyUnavailableError(f"主平台 wallet 5xx: {resp.status_code}")
        body = resp.json()
        # 主平台统一信封 {code, message, data}；data = {user, wallet}
        if body.get("code") != 0:
            raise DependencyUnavailableError(f"主平台 wallet 业务拒绝: code={body.get('code')}")
        return body.get("data") or {}

    async def revoke(self, refresh_token: str) -> None:
        """撤销 refresh 链（RFC 7009 子集：无论令牌状态恒 200，不泄露存在性）。"""
        url = f"{self._base_url}/oauth/revoke"
        try:
            http = await self._get_client()
            await http.post(url, data={"token": refresh_token}, auth=self._auth)
        except httpx.HTTPError as exc:
            # 恒 200 语义下网络异常才需要上报；登出主流程不被其阻断由 Service 决策
            raise DependencyUnavailableError(f"主平台 revoke 不可达: {type(exc).__name__}") from exc
