"""pytest 共享夹具（B-T4 起有连库测试）。

- Windows 下 psycopg async 要求 Selector 事件循环，统一在 import 时设置；
- PG 夹具连真实本地 PG:5433（迁移已应用）；不可达（如 Docker 引擎故障）
  则 skip 并标注原因，引擎恢复后由 A 直接复跑补验收；
- R6.4.5（F-21）/ D23 隔离根治：连库目标按 `环境变量 > backend/.env > 默认生产库`
  三级解析。优先读 `AIDEANBOT_TEST_PG_DSN` 指向独立测试库，避免与部署中的
  scheduler/worker 共库竞态；三级都未命中才回退默认 DSN 并告警。
- 测试库初始化（一次性）：`createdb bothot_test` 后
  `DATABASE_URL=...5433/bothot_test alembic upgrade head`，再把该 DSN 写入
  `backend/.env` 的 `AIDEANBOT_TEST_PG_DSN`（.env 已被 .gitignore 覆盖，不入库）。
- 隔离策略：每个用例一个引擎连接 + 外层事务，用例结束统一回滚，零残留。
"""

from __future__ import annotations

import asyncio
import os
import sys
import warnings
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # noqa: E402

from collections.abc import AsyncIterator  # noqa: E402

import pytest  # noqa: E402  # 必须在事件循环策略设置之后导入
from dotenv import dotenv_values  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_DEFAULT_PG_URL = "postgresql+psycopg://bothot:bothot@localhost:5433/bothot"
_BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def _resolve_test_pg_url() -> tuple[str, str]:
    """解析连库目标，返回 (dsn, 来源)。

    第三级不是「顺手用生产库」，而是**显式告警**：与部署中的 scheduler/worker 共库时，
    测试用的是固定时钟（落在真实过去），线上守护进程会把测试订阅当成到期任务真实
    消费——scheduler 认领并推进水位、worker 对测试占位链接发起真实 HTTP 抓取（D23）。
    """
    explicit = os.environ.get("AIDEANBOT_TEST_PG_DSN")
    if explicit:
        return explicit, "env:AIDEANBOT_TEST_PG_DSN"
    if _BACKEND_ENV_FILE.is_file():
        from_env = dotenv_values(_BACKEND_ENV_FILE).get("AIDEANBOT_TEST_PG_DSN")
        if from_env:
            return from_env, f"file:{_BACKEND_ENV_FILE.name}"
    return _DEFAULT_PG_URL, "default"


PG_URL, _PG_URL_SOURCE = _resolve_test_pg_url()

# 下游 7 个连库用例各自 `os.environ.get("AIDEANBOT_TEST_PG_DSN", 生产库)` 独立判定；
# 若只在本模块解析而不回写，它们仍会直连生产库，隔离形同虚设。setdefault 保证
# 显式环境变量优先级不变，.env 命中时统一向下游广播同一 DSN。
os.environ.setdefault("AIDEANBOT_TEST_PG_DSN", PG_URL)

if _PG_URL_SOURCE == "default":
    warnings.warn(
        "AIDEANBOT_TEST_PG_DSN 未设置（环境变量与 backend/.env 均未命中），"
        "回退默认生产库 DSN。若 scheduler/worker 正在部署中，测试会被线上守护进程"
        "消费（D23）。请在 backend/.env 设置 AIDEANBOT_TEST_PG_DSN 指向独立测试库。",
        stacklevel=1,
    )


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """真实 PG 会话（外层事务回滚隔离）；PG 不可达 → 3 秒内判定并 skip。

    A 实测教训：无超时连接在 PG 宕机时整套测试挂死——connect_timeout 强制 ≤3s。
    """
    engine = create_async_engine(PG_URL, pool_pre_ping=True, connect_args={"connect_timeout": 3})
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            # create_savepoint：Service 内 commit（B-T8R 起）只释放 savepoint，
            # 外层事务回滚仍能清场——隔离语义不被 Service commit 击穿
            factory = async_sessionmaker(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            )
            session = factory()
            try:
                yield session
            finally:
                await session.close()
                # session.close() 可能已隐式回滚外层事务，避免二次回滚告警
                if transaction.is_active:
                    await transaction.rollback()
    except Exception as exc:  # 连接失败（引擎故障/未启动）
        pytest.skip(f"PG:5433 不可达（{type(exc).__name__}），Docker 引擎恢复后复跑本用例")
    finally:
        await engine.dispose()
