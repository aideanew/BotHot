"""B-T8R 回归：跨请求持久化（本次暴露的测试策略盲区——事务回滚隔离测不出漏 commit）。

形态：真实 PG、显式 commit 后**新开 session** 断言可读（模拟下一个请求），
收尾显式清理（真实 commit 不受夹具回滚保护，必须自清理）。
覆盖（卡面要求）：auth callback 用户落库（user_session_factory 生产路径）、
create_space、jobs 状态机流转终点。PG 不可达 → skip（与全仓约定一致）。
"""

from __future__ import annotations

import os
import sys
import uuid

import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_auth import CLIENT_ID, CLIENT_SECRET, ISSUER, FakeAideanIdP

from app.core.config import Settings
from app.models.entities import Job, KnowledgeSpace, Source, User
from app.providers.aidean import AideanProviderClient
from app.repositories.job import JobRepository
from app.repositories.space import SpaceRepository
from app.repositories.user import InMemoryUserStore, SqlAlchemyUserStore
from app.services.auth import InMemorySessionStore, InMemorySsoStateStore
from app.services.auth.service import AuthService
from app.services.jobs import JobService
from app.services.spaces import SpaceService

PG_URL = os.environ.get("AIDEANBOT_TEST_PG_DSN", "postgresql+psycopg://bothot:bothot@localhost:5433/bothot")


def _settings() -> Settings:
    return Settings(
        aidean_issuer=ISSUER,
        oidc_client_id=CLIENT_ID,
        oidc_client_secret=CLIENT_SECRET,
        oidc_redirect_uri="https://wechat-rag.aidean.local/auth/aidean/callback",
        oidc_scopes="openid profile wallet:read",
        oidc_state_ttl_seconds=600,
    )


def _engine_and_factory() -> tuple:  # type: ignore[type-arg]
    """显式 5433 引擎 + 工厂（app 默认 config 指 5432，凭据不同；回归固定指向测试库）。"""
    engine = create_async_engine(PG_URL, pool_pre_ping=True, connect_args={"connect_timeout": 3})
    return engine, async_sessionmaker(bind=engine, expire_on_commit=False)


async def _require_pg() -> async_sessionmaker:  # type: ignore[type-arg]
    """PG 可达窗口判定：不可达 → skip（3 秒超时，不挂死）。"""
    import asyncio

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    engine, factory = _engine_and_factory()
    try:
        from sqlalchemy import text

        async with engine.connect() as conn:
            await conn.execute(text("select 1"))
    except Exception as exc:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f"PG:5433 不可达（{type(exc).__name__}），恢复后复跑")
    else:
        await engine.dispose()  # 探测完释放；用例内自建
        return factory


# ------------------------------------------------------------------ ① auth


async def test_callback_user_persists_across_sessions() -> None:
    """auth：callback upsert+commit 后，新开 session 能读到该 sub（登录死循环回归）。"""
    factory = await _require_pg()
    engine, _ = _engine_and_factory()
    try:
        idp = FakeAideanIdP()
        http = httpx.AsyncClient(transport=httpx.MockTransport(idp.handler))
        client = AideanProviderClient(ISSUER, CLIENT_ID, CLIENT_SECRET, client=http)
        # 生产等价装配：user_session_factory 指向真 PG；内存 user_store 仅占位（工厂路径不触它）
        svc = AuthService(
            client,
            InMemorySsoStateStore(),
            InMemorySessionStore(),
            InMemoryUserStore(),
            _settings(),
            user_session_factory=factory,
        )
        authorize_url = await svc.build_login()
        from urllib.parse import parse_qs, urlparse

        state = parse_qs(urlparse(authorize_url).query)["state"][0]
        record = await svc.handle_callback(idp.issue_code(), state)

        # 新开 session（模拟下一个请求的 get_current_user_id 查库）
        async with factory() as session2:
            user = await SqlAlchemyUserStore(session2).get_by_sub(record.sub)
            assert user is not None, "callback 用户未跨请求持久化（漏 commit 死循环复现）"
            assert user.email == "dev@aidean.local"

        # 自清理（真实 commit 不受夹具回滚保护）
        async with factory() as session:
            await session.execute(delete(User).where(User.sub == record.sub, User.email == "dev@aidean.local"))
            await session.commit()
    finally:
        await engine.dispose()


# ------------------------------------------------------------------ ② spaces


async def test_create_space_persists_across_sessions() -> None:
    """spaces：create_space commit 后新开 session 可读（空间不持久化回归）。"""
    factory = await _require_pg()
    engine, _ = _engine_and_factory()
    try:
        sub = f"b-t8r-{uuid.uuid4().hex[:8]}"
        async with factory() as session:
            user = await SqlAlchemyUserStore(session).upsert_by_sub(sub, f"{sub}@test.local", "回归")
            await session.commit()
            svc = SpaceService(SpaceRepository(session), session)
            space = await svc.create_space(user.id, "持久化回归空间")
            space_id = space.id

        async with factory() as session2:
            found = await SpaceRepository(session2).get_by_id(space_id)
            assert found is not None, "create_space 未跨请求持久化（漏 commit 复现）"
            assert found.name == "持久化回归空间"

        # 自清理：删用户级联清空间
        async with factory() as session:
            await session.execute(delete(User).where(User.sub == sub))
            await session.commit()
    finally:
        await engine.dispose()


async def test_space_description_persists_across_sessions() -> None:
    """R0.5.1/R0.5.2（F-4）：description 列真实落库并可被改（迁移生效性回归）。

    内存桩证明不了列存在；本测走真实 PG 验证 ab1004m5a 落列后
    「建时写入 → 跨 session 回读 → PATCH 改写 → 清空」全链路。
    """
    factory = await _require_pg()
    engine, _ = _engine_and_factory()
    try:
        sub = f"r051-{uuid.uuid4().hex[:8]}"
        async with factory() as session:
            user = await SqlAlchemyUserStore(session).upsert_by_sub(sub, f"{sub}@test.local", "回归")
            await session.commit()
            repo = SpaceRepository(session)
            svc = SpaceService(repo, session)
            space = await svc.create_space(user.id, "简介回归空间", "初始简介")
            space_id = space.id

        # 跨 session 回读：值不得丢（旧缺陷在 Service 层就丢了）
        async with factory() as session2:
            found = await SpaceRepository(session2).get_by_id(space_id)
            assert found is not None
            assert found.description == "初始简介", "description 未跨请求持久化"

        # PATCH 改写路径
        async with factory() as session3:
            svc3 = SpaceService(SpaceRepository(session3), session3)
            await svc3.update_space(user.id, space_id, "改后的简介")

        async with factory() as session4:
            updated = await SpaceRepository(session4).get_by_id(space_id)
            assert updated is not None
            assert updated.description == "改后的简介"

        # 空串清空合法（「未填写简介」是合法状态，不是丢失）
        async with factory() as session5:
            svc5 = SpaceService(SpaceRepository(session5), session5)
            await svc5.update_space(user.id, space_id, "")
            view = await svc5.get_space_view(user.id, space_id)
            assert view["description"] == ""
            # R0.5.3（F-5）：chunk 数据源未接线 → null 而非 0
            assert view["stats"]["chunks"] is None

        # 自清理：删用户级联清空间
        async with factory() as session:
            await session.execute(delete(User).where(User.sub == sub))
            await session.commit()
    finally:
        await engine.dispose()


# ------------------------------------------------------------------ ③ jobs


async def test_job_transition_persists_across_sessions() -> None:
    """jobs：transition 写路径终点 commit 后新开 session 可读（状态机回滚回归）。"""
    factory = await _require_pg()
    engine, _ = _engine_and_factory()
    sub = f"b-t8r-{uuid.uuid4().hex[:8]}"
    biz = f"biz-{uuid.uuid4().hex[:8]}"
    try:
        async with factory() as session:
            user = await SqlAlchemyUserStore(session).upsert_by_sub(sub, f"{sub}@test.local", "回归")
            source = Source(type="wechat_oa", external_id=biz, name="回归源")
            session.add(source)
            await session.commit()
            svc = JobService(JobRepository(session), session)
            job, created = await svc.submit(job_type="ingest", user_id=user.id, idempotency_key=f"b-t8r-{biz}")
            assert created
            await svc.transition(job.id, "RUNNING")
            job_id = job.id

        async with factory() as session2:
            found = await JobRepository(session2).get_by_id(job_id)
            assert found is not None, "job 未跨请求持久化（漏 commit 复现）"
            assert found.status == "RUNNING"

        # 自清理（job → source → user）
        async with factory() as session:
            await session.execute(delete(Job).where(Job.id == job_id))
            await session.execute(delete(Source).where(Source.external_id == biz))
            await session.execute(delete(User).where(User.sub == sub))
            await session.commit()
    finally:
        await engine.dispose()


# 空间模型引用守护（import 侧不再使用则此行无副作用）
_SPACE_REF: type[KnowledgeSpace] = KnowledgeSpace  # noqa: F841
