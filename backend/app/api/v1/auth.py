"""SSO 认证路由（B-T3）：login / callback / logout / me / backchannel-logout。

Route 层只做参数装配、cookie 处理与响应归一；全部业务在 AuthService。
错误语义：state 问题 → 10002；code 拒绝 → 10003；未登录 → 10001（全局异常处理器统一转信封）。
backchannel-logout 例外：**恒 200 同形响应**，不向主平台泄露校验结果差异（理由见该路由）。
"""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.config import Settings, get_settings
from app.core.errors import SsoTokenExchangeError, UnauthenticatedError
from app.core.response import success
from app.providers.aidean import AideanProviderClient
from app.repositories.user import InMemoryUserStore, UserStore
from app.services.auth import (
    AuthService,
    InMemorySessionStore,
    InMemorySsoStateStore,
    JwksVerifier,
    RedisSessionStore,
    RedisSsoStateStore,
    SessionStore,
    SsoStateStore,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# ------------------------------------------------------------------ 装配

_user_store: UserStore = InMemoryUserStore()
_service: AuthService | None = None


def _build_stores(settings: Settings) -> tuple[SsoStateStore, SessionStore]:
    """按 SESSION_STORE 开关装配存储后端（A 裁决：memory|redis，默认 memory）。

    Redis 客户端惰性建连（from_url 不触发网络 IO，首个命令才连接）。
    """
    if settings.session_store_backend == "redis":
        import redis.asyncio as aioredis

        redis_client = aioredis.from_url(settings.redis_url, protocol=2)
        return RedisSsoStateStore(redis_client), RedisSessionStore(redis_client)
    return InMemorySsoStateStore(), InMemorySessionStore()


def _build_default_service(settings: Settings) -> AuthService:
    """生产默认装配：存储后端由 SESSION_STORE 决定；用户落库走真 PG
    （B-T8R：user_session_factory 接线，callback upsert 后显式 commit，
    否则请求末回滚 → get_current_user_id 查无此人 → 登录死循环）。"""
    http = httpx.AsyncClient(timeout=10.0)
    client = AideanProviderClient(
        settings.aidean_issuer,
        settings.oidc_client_id,
        settings.oidc_client_secret,
        client=http,
        public_base_url=settings.aidean_public_url or None,
    )
    state_store, session_store = _build_stores(settings)
    from app.db import create_engine_and_session

    _, session_factory = create_engine_and_session()
    # R9：JWKS 走后端可达的 issuer（aidean_issuer），与 token/userinfo 同路。
    # 注意它可能不等于 logout_token 的 iss 声明值（容器内网地址 vs 主平台
    # NEXT_PUBLIC_SITE_URL），后者须显式配 OIDC_ISSUER_EXPECTED。
    jwks = JwksVerifier(settings.aidean_issuer, client=http)
    return AuthService(
        client,
        state_store,
        session_store,
        _user_store,
        settings,
        session_factory,
        jwks=jwks,
    )


def get_auth_service() -> AuthService:
    """FastAPI 依赖入口（测试经 app.dependency_overrides 替换）。"""
    global _service
    if _service is None:
        _service = _build_default_service(get_settings())
    return _service


def _set_session_cookie(response: Response, settings: Settings, session_id: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        max_age=settings.session_ttl_seconds,
        httponly=True,  # 铁律：JS 不可读
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


# ------------------------------------------------------------------ 路由


@router.get("/login")
async def login(svc: Annotated[AuthService, Depends(get_auth_service)]) -> RedirectResponse:
    """生成一次性 state → 302 跳主平台 authorize（密码只在主平台输入）。"""
    return RedirectResponse(await svc.build_login(), status_code=302)


@router.get("/callback")
async def callback(
    request: Request,
    svc: Annotated[AuthService, Depends(get_auth_service)],
) -> JSONResponse:
    """主平台回调（前端 /auth/aidean/callback 转发 code/state 到此）。

    失败场景主平台以 error 参数回传（指南 §3 第 3 步）→ 10003。
    """
    settings = get_settings()
    error = request.query_params.get("error", "")
    if error:
        description = request.query_params.get("error_description", "")
        raise SsoTokenExchangeError(f"主平台回传授权错误: {error} {description}".strip())
    record = await svc.handle_callback(
        code=request.query_params.get("code", ""),
        state=request.query_params.get("state", ""),
    )
    body = success(
        data={
            "sub": record.sub,
            "email": record.email,
            "nickname": record.nickname,
            "session": "established",
        }
    )
    response = JSONResponse(status_code=200, content=body.model_dump())
    _set_session_cookie(response, settings, record.session_id)
    return response


@router.post("/logout")
async def logout(
    request: Request,
    svc: Annotated[AuthService, Depends(get_auth_service)],
) -> JSONResponse:
    """撤销 refresh 链 + 删除服务端会话 + 清 cookie（幂等：无会话也返回成功）。"""
    settings = get_settings()
    session_id = request.cookies.get(settings.session_cookie_name)
    await svc.logout(session_id)
    body = success(data={"logged_out": True})
    response = JSONResponse(status_code=200, content=body.model_dump())
    response.delete_cookie(key=settings.session_cookie_name, path="/")
    return response


@router.post("/backchannel-logout")
async def backchannel_logout(
    request: Request,
    svc: Annotated[AuthService, Depends(get_auth_service)],
) -> JSONResponse:
    """主平台 back-channel 登出接收（OIDC Back-Channel Logout 1.0 子集，R9）。

    服务器间 POST（不经浏览器、不读/写本方 cookie）：主平台在用户登出后按
    「该用户全部活跃产品链」广播 `logout_token`。恒 200 同形响应——无论 token
    缺失、签名无效还是声明不符都返回同一 body，不向主平台泄露校验结果差异
    （对齐主平台 `/oauth/revoke` 恒 200 口径；理由见 services/auth/service.py）。
    校验明细只进日志（含原因码与 sub 前缀，不含 token 原文）。
    仅当服务端自身故障（如会话存储不可达）才返回 5xx。
    """
    content_type = request.headers.get("content-type", "")
    logout_token = ""
    if content_type.startswith("application/x-www-form-urlencoded"):
        form = await request.form()
        logout_token = str(form.get("logout_token", ""))
    await svc.handle_backchannel_logout(logout_token)
    body = success(data={"received": True})
    return JSONResponse(status_code=200, content=body.model_dump())


@router.get("/me")
async def me(
    request: Request,
    svc: Annotated[AuthService, Depends(get_auth_service)],
) -> JSONResponse:
    """聚合 userinfo + 实时 wallet（余额不落库，铁律）。未登录 → 10001。"""
    settings = get_settings()
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        raise UnauthenticatedError("未登录")
    body = success(data=await svc.get_me(session_id))
    return JSONResponse(status_code=200, content=body.model_dump())
