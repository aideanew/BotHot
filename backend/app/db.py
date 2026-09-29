"""数据库引擎与会话工厂（B-T4）。

约定（高内聚）：
- Repository 只 flush 不 commit —— 事务边界由调用方（Service/API 依赖）管理，
  测试借此用「事务回滚」做用例隔离；
- pool_pre_ping 兜底容器重启后的失连。
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


def resolve_database_url(default_url: str | None = None, environ: Mapping[str, str] | None = None) -> str:
    """解析数据库连接串：`DATABASE_URL` 环境变量优先，缺省回落 `default_url` / Settings。

    `alembic/env.py` 依赖它——`alembic.ini` 硬编码的 `localhost:5433` 只在宿主裸跑时成立，
    容器内 postgres 主机是 `postgres:5432`，compose `migrate` 服务靠该变量指向卷内库。
    """
    env = os.environ if environ is None else environ
    return env.get("DATABASE_URL") or default_url or get_settings().database_url


def create_engine_and_session(url: str | None = None) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """按连接串创建引擎与会话工厂（缺省取 Settings.database_url）。"""
    database_url = url or get_settings().database_url
    engine = create_async_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


# 进程级单例，模块导入期创建（此时无事件循环在跑，连接按需惰性建立）。
# 引擎按 event loop 绑定连接池：多处各自 create 会得到互不相通的池，
# 而惰性初始化会让首个调用者所在 loop 独占该引擎，其余 loop 触发跨 loop 报错。
_engine, _session_factory = create_engine_and_session()


def get_engine() -> AsyncEngine:
    """进程级引擎单例（pool_pre_ping 兜底容器重启后的失连）。"""
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """进程级会话工厂单例。"""
    return _session_factory
