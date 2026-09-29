"""API 依赖装配（B-T4R）：数据库会话与登录保护，供各域路由复用。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_auth_service
from app.core.config import get_settings
from app.core.errors import UnauthenticatedError
from app.db import get_session_factory
from app.models.entities import User
from app.providers.engine_port import EngineRouter
from app.providers.langbot.client import LangBotClient
from app.providers.raw_store import RawStore, make_raw_store
from app.providers.reranker import RerankerPort, make_reranker
from app.repositories.job import JobRepository
from app.repositories.space import SpaceRepository
from app.repositories.user import SqlAlchemyUserStore
from app.services.auth import AuthService
from app.services.jobs import JobService
from app.services.kb import KnowledgeBaseService
from app.services.resolver import SourceResolverService
from app.services.roles import require_role
from app.services.spaces import SpaceService


async def get_db() -> AsyncIterator[AsyncSession]:
    """请求作用域会话；请求结束统一回滚（写提交由 Service/编排层显式 commit）。

    引擎/工厂单例在 app.db（pool_pre_ping 兜底容器重启后的失连）。
    """
    async with get_session_factory()() as session:
        yield session


async def get_current_sub(
    request: Request,
    svc: Annotated[AuthService, Depends(get_auth_service)],
) -> str:
    """cookie 会话 → 身份锚点 sub；未登录 → 10001（登录保护接口共用）。"""
    session_id = request.cookies.get(get_settings().session_cookie_name)
    return await svc.current_sub(session_id)


async def get_current_user_id(
    sub: Annotated[str, Depends(get_current_sub)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> str:
    """sub → 本地 users 行 id（spaces/jobs 等域表的外键锚点）。"""
    user = await SqlAlchemyUserStore(session).get_by_sub(sub)
    if user is None:  # 有会话但本地无行（异常态，如库被手工清理）→ 重新走 SSO
        raise UnauthenticatedError("本地用户不存在，请重新登录")
    return user.id


def require_roles(*roles: str):
    """M3 role 依赖工厂：路由写 user: Annotated[User, Depends(require_roles("admin"))]。

    session 与 user_id 复用既有依赖（FastAPI 按依赖对象去重，与本路由的
    Depends(get_db) 拿到同一会话）；判定逻辑只在 app.services.roles.require_role。
    每次调用返回独立函数对象，不同角色要求的依赖键互不串用。
    """

    async def _require(
        session: Annotated[AsyncSession, Depends(get_db)],
        user_id: Annotated[str, Depends(get_current_user_id)],
    ) -> User:
        return await require_role(session, user_id, *roles)

    return _require


async def get_space_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SpaceService:
    # BE-02：引擎路由装配（delete_space 按 space.engine 分发删库）
    return SpaceService(SpaceRepository(session), session, engine_router=get_engine_router())


_engine_router_inst: EngineRouter | None = None


def get_engine_router() -> EngineRouter:
    """进程级引擎路由单例（settings + langbot client 装配）。"""
    global _engine_router_inst
    if _engine_router_inst is None:
        _engine_router_inst = EngineRouter(get_settings(), get_langbot_client())
    return _engine_router_inst


_raw_store_inst: RawStore | None = None


def get_raw_store() -> RawStore:
    """进程级 raw_store 单例（config.raw_store_backend 决定 url/local）。"""
    global _raw_store_inst
    if _raw_store_inst is None:
        _raw_store_inst = make_raw_store()
    return _raw_store_inst


_reranker_inst: RerankerPort | None = None


def get_reranker() -> RerankerPort:
    """进程级重排器单例（Key 只读 env；未配置 → NoopReranker，显式不可用）。"""
    global _reranker_inst
    if _reranker_inst is None:
        _reranker_inst = make_reranker(get_settings())
    return _reranker_inst


_langbot_client: LangBotClient | None = None  # 进程级单例（登录态缓存复用）


def get_langbot_client() -> LangBotClient:
    global _langbot_client
    if _langbot_client is None:
        settings = get_settings()
        _langbot_client = LangBotClient(
            settings.langbot_base_url,
            settings.langbot_admin_username,
            settings.langbot_admin_password,
        )
    return _langbot_client


def get_resolver_service_internal() -> SourceResolverService:
    """resolve/extract/ingest 共用（B-T6 起的既有工厂，保持命名）。"""
    return SourceResolverService()


async def get_kb_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> KnowledgeBaseService:
    return KnowledgeBaseService(
        get_langbot_client(), session, get_resolver_service_internal(),
        raw_store=get_raw_store(), engine_router=get_engine_router(),
    )


async def get_job_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JobService:
    """jobs 域服务（B-T8R：session 传入，状态机写路径 commit 在 Service）。"""
    return JobService(JobRepository(session), session)
