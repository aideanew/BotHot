"""pytest 共享夹具（B-T4 起有连库测试）。

- Windows 下 psycopg async 要求 Selector 事件循环，统一在 import 时设置；
- 连库目标按 `环境变量 AIDEANBOT_TEST_PG_DSN > apps/api/.env 同名键` **两级**解析；
  两级都未命中即判定「未配置」，连库夹具直接 skip 并报原因——不再猜一个库连。
  D-12：旧实现有第三级回退——硬编码一个指向 :5433/bothot 的生产形态 DSN 常量（含口令
  字面量）且只告警不拒绝，未设变量时测试真实写入生产形态库；测试用固定时钟
  （落在真实过去），部署中的 scheduler 会把测试订阅当到期任务认领并推进水位、
  worker 对测试占位链接发起真实 HTTP 抓取（D23）。宁 skip 不写生产。
- 「未配置」时 `PG_URL` 取一个必然拒连的地址：下游 9 个连库模块各自
  `os.environ.get(AIDEANBOT_TEST_PG_DSN, 生产字面量)` 独立判定，只把本模块置空
  并不能阻止它们直连 :5433（清单见 docs/06_validation/evidence/EVD-V2-00/README.md）。
- 取得测试库：`bash scripts/test-env.sh up && eval "$(bash scripts/test-env.sh env)"`
  （PG 16@宿主 5547 / Redis@宿主 6390，拒绝复用 5433/5435/6379/6380），
  再 `cd apps/api && alembic upgrade head`。
- 隔离策略：每个用例一个引擎连接 + 外层事务，用例结束统一回滚，零残留。
"""

from __future__ import annotations

import asyncio
import os
import sys
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

_TEST_PG_ENV_VAR = "AIDEANBOT_TEST_PG_DSN"
# 端口 1 需 root 才能监听 ⇒ 本机不可能有 PG 监听其上，连接立即被拒——各连库夹具据此 skip。
_REFUSED_PG_URL = "postgresql+psycopg://invalid@127.0.0.1:1/bothot_dsn_unset"
SKIP_UNSET_REASON = (
    "AIDEANBOT_TEST_PG_DSN 未设置：连库用例需要独立测试库。"
    '准备命令：bash scripts/test-env.sh up && eval "$(bash scripts/test-env.sh env)"'
)
_BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def _resolve_test_pg_url() -> tuple[str, str]:
    """解析连库目标，返回 (dsn, 来源)；来源为 "unset" 时 dsn 为空串。

    刻意不设「顺手用生产库」的第三级回退：与部署中的 scheduler/worker 共库时，
    测试用的是固定时钟（落在真实过去），线上守护进程会把测试订阅当成到期任务真实
    消费——scheduler 认领并推进水位、worker 对测试占位链接发起真实 HTTP 抓取（D23）。
    """
    explicit = (os.environ.get(_TEST_PG_ENV_VAR) or "").strip()
    if explicit:
        return explicit, f"env:{_TEST_PG_ENV_VAR}"
    if _BACKEND_ENV_FILE.is_file():
        from_env = (dotenv_values(_BACKEND_ENV_FILE).get(_TEST_PG_ENV_VAR) or "").strip()
        if from_env:
            return from_env, f"file:{_BACKEND_ENV_FILE.name}"
    return "", "unset"


PG_URL, _PG_URL_SOURCE = _resolve_test_pg_url()
if _PG_URL_SOURCE == "unset":
    PG_URL = _REFUSED_PG_URL

# 下游 9 个连库用例各自 `os.environ.get(_TEST_PG_ENV_VAR, 生产库)` 独立判定；
# 若只在本模块解析而不回写，它们仍会直连生产库，隔离形同虚设。setdefault 保证
# 显式环境变量优先级不变，.env 命中时统一向下游广播同一 DSN。
os.environ.setdefault(_TEST_PG_ENV_VAR, PG_URL)


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """真实 PG 会话（外层事务回滚隔离）；未配置测试库 → skip 报原因，PG 不可达 → 3 秒内判定并 skip。

    A 实测教训：无超时连接在 PG 宕机时整套测试挂死——connect_timeout 强制 ≤3s。
    """
    if _PG_URL_SOURCE == "unset":
        pytest.skip(SKIP_UNSET_REASON)
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
        pytest.skip(f"测试 PG 不可达（{type(exc).__name__}），环境恢复后复跑本用例")
    finally:
        await engine.dispose()
