"""数据库引擎与会话工厂（B-T4）。

约定（高内聚）：
- Repository 只 flush 不 commit —— 事务边界由调用方（Service/API 依赖）管理，
  测试借此用「事务回滚」做用例隔离；
- pool_pre_ping 兜底容器重启后的失连；
- pool_recycle=1800（30 分钟）主动回收空闲连接，避免被中间防火墙/PG idle
  超时静默掐断后首查延迟（pool_pre_ping 是兜底，recycle 是前置）。

连接池参数取舍（3.1）：pool_size/max_overflow/pool_recycle 不进 Settings
（config.py 归 WB），改用模块常量 + 环境变量覆盖（`DB_POOL_SIZE`/`DB_MAX_OVERFLOW`
/`DB_POOL_RECYCLE`）。理由：运维调参（容器内存/连接上限变更）无需改代码、无需
走 WB 的 Settings 变更流程；默认值（5/5/1800）与历史行为一致，零回归。
不改 create_engine_and_session 签名（调用方零感知）。
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

# 连接池参数（env 覆盖，默认与历史一致）；DB_POOL_RECYCLE 秒数前置回收防 idle 断连。
_DB_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "5"))
_DB_MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", "5"))
_DB_POOL_RECYCLE = int(os.environ.get("DB_POOL_RECYCLE", "1800"))


def resolve_database_url(default_url: str | None = None, environ: Mapping[str, str] | None = None) -> str:
    """解析数据库连接串：`DATABASE_URL` 环境变量优先，缺省回落 `default_url` / Settings。

    `alembic/env.py` 依赖它——`alembic.ini` 硬编码的 `localhost:5433` 只在宿主裸跑时成立，
    容器内 postgres 主机是 `postgres:5432`，compose `migrate` 服务靠该变量指向卷内库。
    """
    env = os.environ if environ is None else environ
    return env.get("DATABASE_URL") or default_url or get_settings().database_url


def create_engine_and_session(url: str | None = None) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """按连接串创建引擎与会话工厂（缺省取 Settings.database_url）。

    池参数取模块常量（env 可覆盖）；pool_recycle 前置回收防 idle 断连。
    """
    database_url = url or get_settings().database_url
    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=_DB_POOL_SIZE,
        max_overflow=_DB_MAX_OVERFLOW,
        pool_recycle=_DB_POOL_RECYCLE,
    )
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


# C.3：常驻进程数（web + scheduler + worker + push-scheduler = 4），可由 env 覆盖。
# 每进程各持一份连接池（pool_size+max_overflow），总占用 = 进程数 × 单池容量。
EXPECTED_PROCESSES = int(os.environ.get("BOTHOT_PROCESS_COUNT", "4"))


async def assert_pool_capacity(engine: AsyncEngine | None = None) -> None:
    """C.3 启动断言：进程数 × (pool_size + max_overflow) ≤ PG max_connections。

    超限则 raise RuntimeError 拒启（fail-fast）：4 进程 × (5+5)=40 远低于 PG 默认 100，
    但 pool 调大或多副本时必须拦截。PG 不可达时跳过（不阻断启动——连接故障由
    pool_pre_ping 在首查兜底，启动期断言不应比健康检查更严）。

    engine 参数：scheduler/worker 进程自建引擎（create_engine_and_session），
    传入自己的 engine 复用既有连接做 SHOW max_connections，避免为断言单独
    建模块级连接；web 进程（main.lifespan）省略参数走模块级单例。
    """
    from sqlalchemy import text

    target = engine if engine is not None else _engine
    capacity = EXPECTED_PROCESSES * (_DB_POOL_SIZE + _DB_MAX_OVERFLOW)
    try:
        async with target.connect() as conn:
            max_conn = (await conn.execute(text("SHOW max_connections"))).scalar()
    except Exception:  # noqa: BLE001 PG 不可达：启动不断言失败（首查兜底）
        return
    if max_conn is not None and capacity > int(max_conn):
        raise RuntimeError(
            f"连接池容量超限：{EXPECTED_PROCESSES} 进程 × "
            f"({_DB_POOL_SIZE}+{_DB_MAX_OVERFLOW})={capacity} > PG max_connections={max_conn}"
        )
