"""Schema 版本一致性探测（W6 A.3）：alembic head ↔ DB `alembic_version` 单点逻辑。

此前该探测只活在 `main._assert_schema_current` 的启动路径里（一次性独立引擎、
生产拒启）。W6 要把「schema 是否追平代码」变成**运行期可查**的就绪信号（`/ready`），
故把两份口径收敛到这里，启动守卫与就绪探针共用同一实现，杜绝漂移。

- `get_alembic_head()`：代码侧 HEAD 版本（纯文件扫描，无 DB，廉价、同步）。
- `read_current_version_async(engine)`：库侧 `alembic_version.version_num`（异步、需连通）。

调用方按上下文选引擎：启动守卫用一次性独立引擎（避免 asyncio.run 绑坏进程单例池，
见 `main._assert_schema_current` 注释），就绪探针用进程单例 `get_engine()`。
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine

# 本模块自身不打日志（探测结果由各调用方决定告警/拒启/降级），保留 logger 备用。
logger = structlog.get_logger(__name__)


def get_alembic_head() -> str | None:
    """代码侧 alembic HEAD revision；扫描失败返回 None（调用方按不可判定处理）。"""
    try:
        from alembic.config import Config as AlembicConfig
        from alembic.script import ScriptDirectory

        cfg = AlembicConfig()
        cfg.set_main_option("script_location", "alembic")
        return ScriptDirectory.from_config(cfg).get_current_head()
    except Exception:  # noqa: BLE001  # 探测不可用不能反噬调用方
        logger.warning("alembic head 探测失败", exc_info=True)
        return None


async def read_current_version_async(engine: AsyncEngine) -> str | None:
    """库侧当前 `alembic_version.version_num`；表不存在/查询失败返回 None。"""
    import sqlalchemy

    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(sqlalchemy.text("SELECT version_num FROM alembic_version"))
            ).fetchone()
        return row[0] if row else None
    except Exception:  # noqa: BLE001  # 库不可达/无表 → 不可判定，交由就绪聚合降级
        return None
