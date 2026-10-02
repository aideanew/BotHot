"""常驻进程心跳（R7.7）：让「scheduler / worker 到底在不在跑」变成可查询的事实。

根因（2026-09-28 实测，本模块存在的理由）：`docker/compose.yml` 在提交 `9362d3c`
（2026-09-23 17:40）才声明 `migrate` / `scheduler` / `worker` 三个服务，
但运行中的栈建于 **2026-09-08 ~ 09-14**——三个服务进文件的时点**晚于**栈的创建
5 天。此后线上操作只有 `docker cp` 与 `docker restart`，**从未跑过 `docker compose up -d`**。

`docker restart` 只能重启**已存在**的容器，无法创建不存在的容器。因此这三个服务
**从未实例化过**，表现为：

- 无 `scheduler` → 每天 10 点定时采集从不触发；
- 无 `worker` → Job 队列无人消费；
- 无 `migrate` → **今后没有东西会自动执行结构迁移**（注意：库结构当时并不落后——
  迁移此前经《部署运维手册》记录的**手工宿主步骤**执行过，`alembic_version` 一直在
  `ab1004s1a`。缺 migrate 的后果是「无人自动推进」，不是「结构落后」）。

而 **backend 健康检查全绿**，静默失效持续 5 天无人察觉。
（同期还有一个**独立**问题：线上 backend 镜像落后库结构 6 个 revision，见《阻塞项登记表》
D20。二者成因同源——都只 `docker cp` + `restart`、从未 `build` + `up -d`——但后果不同。）

两类结构性盲区使它不可见：
1. `restart: unless-stopped` 只管「容器存在但退出」，管不到「容器从未存在」；
2. backend 与 scheduler/worker 之间没有任何进程间信号，backend 无从感知。

本模块补的是第 2 类：常驻进程每轮向 `process_heartbeats` 报到，读侧
`GET /api/v1/admin/ops/liveness` 与容器 `healthcheck` 各自消费它。
这不违反「不新建无读侧写面」纪律（`push_port.py` 对 `BotBinding` 死表的两次标记）——
本表有两个明确消费方：管理端读侧 + 容器健康检查，且读侧会随进程缺失而报 `stale`。

读侧纪律沿用 `providers/push_port.registered_channels()`：不可用就如实回报并点名原因，
不用「无记录」暗示「健康」。`lastHeartbeatAt=null` 与 `lastHeartbeatAt` 很久没更新
是**两种不同故障**（前者=进程从未启动，后者=进程启动后卡死），必须可区分。
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypedDict

import structlog
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

# 模型 `ProcessHeartbeat` 在 `app/models/entities.py` 里保留（保证 autogenerate 不会把它
# 判成「无模型即删除」）；本模块读写走单条 SQL——upsert 一次往返，读侧也直接要原始行。

logger = structlog.get_logger(__name__)

# 表名单一真源：本模块的 SQL 与 `entities.ProcessHeartbeat` 的 ORM 映射必须指向同一张表，
# 抽成常量避免两处硬编码漂移。此处是**模块常量而非用户输入**，故 f-string 拼接不构成
# 注入面；它同时是测试指向隔离表的接缝（见 tests/test_process_heartbeat.py）。
TABLE_NAME = "process_heartbeats"

# 期望常驻的进程键 → 一句话职责说明（读侧据此向调用方解释「该在跑什么」）。
# 进程不存在时读侧仍会列出它并标 stale——若只回报「已有的」，缺进程就查不出来了。
EXPECTED_PROCESSES: dict[str, str] = {
    "scheduler": "订阅定时调度：认领到期订阅 → Manifest 发现 → Diff 入列 → 推进水位",
    "worker": "Job 执行器：逐篇 ingest → 推 LangBot RAG",
}

# 判定 stale 的默认阈值。取 300s 而非更小的理由：scheduler/worker 空闲时按
# `idle_sleep_seconds`（默认 10s）休眠，但心跳本身也节流（见各进程侧调用点），
# 阈值必须覆盖「心跳节流 + 一次正常轮次耗时」的最坏组合，否则健康进程会被误报。
DEFAULT_MAX_AGE_SECONDS = 300

# 进程写入心跳的最小间隔。避免把心跳表变成每 10 秒一条的高频写入面。
BEACON_MIN_INTERVAL_SECONDS = 30.0


class ProcessLiveness(TypedDict):
    """单个常驻进程的存活回报。

    `lastHeartbeatAt` 与 `ageSeconds` 同为 `None` 只有一种含义：**该行不存在**
    （进程从未启动）；有行时二者必有值。读侧不得用「空值」同时表达「从未启动」
    和「已过期」——那是这次要防的盲区。
    """

    processKey: str
    purpose: str
    lastHeartbeatAt: str | None
    ageSeconds: int | None
    stale: bool
    lastDetail: str


class LivenessSnapshot(TypedDict):
    """`describe_liveness` 的返回契约：按 `EXPECTED_PROCESSES` 全景，缺进程也占位。"""

    processes: list[ProcessLiveness]
    maxAgeSeconds: int
    allHealthy: bool


class BeaconGate:
    """写入节流门：单调时钟驱动，跨 await 安全，测试可注入时钟。"""

    def __init__(self, min_interval: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._min_interval = float(min_interval)
        self._clock = clock
        self._last = float("-inf")

    def ready(self) -> bool:
        now = self._clock()
        if now - self._last < self._min_interval:
            return False
        self._last = now
        return True


async def beacon(session: AsyncSession, process_key: str, detail: str = "") -> None:
    """向心跳表报到一次（upsert，同键覆盖）。

    **调用方必须吞掉本函数的异常**：心跳写不进去绝不能拖垮采集主循环——
    否则一次数据库抖动就会把「写心跳失败」放大成「采集全线停摆」，
    那是把一个可观测性问题变成一个功能性故障。
    """
    await session.execute(
        sa_text(
            f"""
            INSERT INTO {TABLE_NAME} (process_key, last_heartbeat_at, last_detail)
            VALUES (:key, now(), :detail)
            ON CONFLICT (process_key) DO UPDATE
            SET last_heartbeat_at = now(),
                last_detail = EXCLUDED.last_detail
            """
        ),
        {"key": process_key, "detail": detail[:512]},
    )
    await session.commit()


async def describe_liveness(
    session: AsyncSession,
    *,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    now_fn: Callable[[], datetime] | None = None,
) -> LivenessSnapshot:
    """读侧全景：每个**期望**进程的回报状态 + 是否 stale。

    缺行的进程（从未启动）返回 `lastHeartbeatAt=None`、`stale=true`，
    与「有行但过期」区分开——两者都不可用，但处置动作不同。
    """
    now = datetime.now(UTC) if now_fn is None else now_fn()
    rows = (
        await session.execute(sa_text(f"SELECT process_key, last_heartbeat_at, last_detail FROM {TABLE_NAME}"))
    ).all()
    by_key = {row[0]: row for row in rows}

    processes: list[ProcessLiveness] = []
    for key, purpose in EXPECTED_PROCESSES.items():
        row = by_key.get(key)
        if row is None:
            processes.append(
                {
                    "processKey": key,
                    "purpose": purpose,
                    "lastHeartbeatAt": None,
                    "ageSeconds": None,
                    "stale": True,
                    "lastDetail": "",
                }
            )
            continue
        last_at = _utc_from_epoch(row[1])
        age = int((now - last_at).total_seconds())
        processes.append(
            {
                "processKey": key,
                "purpose": purpose,
                "lastHeartbeatAt": last_at.isoformat(),
                "ageSeconds": age,
                "stale": age > int(max_age_seconds),
                "lastDetail": str(row[2] or ""),
            }
        )
    return {
        "processes": processes,
        "maxAgeSeconds": int(max_age_seconds),
        "allHealthy": all(not bool(p["stale"]) for p in processes),
    }


def _utc_from_epoch(dt: datetime) -> datetime:
    """按**绝对时刻**归一到 UTC，age 计算不受写入方墙钟时区影响。

    列是 `timestamptz`，读回恒为 tz-aware——naive 分支只为直调本函数的场景兜底。
    反例（2026-09-28 实测）：往该列写 **naive** 值时 PG 按**会话时区**解释，
    naive「11:59」在 +08 会话下落库成「03:59+00」，按墙钟算 age 会差整 8 小时。
    故 `beacon()` 只用 SQL `now()`、不用 Python 侧 naive 时间。
    """
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


async def check_process(process_key: str, max_age_seconds: int) -> int:
    """容器 healthcheck 用的同步入口：0 = 存活，1 = stale / 缺进程。

    为什么用它而不是 TCP 探针：scheduler/worker **不开任何端口**，
    `CMD ["python", "-m", ...]` 之外没有可探测的服务面。
    数据库里的心跳是唯一诚实的健康信号——端口通了不代表进程在干活。
    """
    from app.core.config import get_settings
    from app.db import create_engine_and_session

    settings = get_settings()
    engine, factory = create_engine_and_session(settings.database_url)
    try:
        async with factory() as session:
            snap = await describe_liveness(session, max_age_seconds=max_age_seconds)
        entry = next((p for p in snap["processes"] if p["processKey"] == process_key), None)
        if entry is None:
            logger.error("healthcheck：%s 不在期望进程清单中", process_key)
            return 1
        if entry["stale"]:
            logger.error(
                "healthcheck：%s 心跳过期 lastHeartbeatAt=%s ageSeconds=%s",
                process_key,
                entry["lastHeartbeatAt"],
                entry["ageSeconds"],
            )
            return 1
        return 0
    finally:
        with contextlib.suppress(Exception):
            await engine.dispose()


async def _cli() -> int:
    """`python -m app.services.process_heartbeat <process_key> [--max-age N]`。"""
    args = [a for a in sys.argv[1:] if a and not a.startswith("--")]
    max_age = DEFAULT_MAX_AGE_SECONDS
    if "--max-age" in sys.argv:
        idx = sys.argv.index("--max-age")
        max_age = int(sys.argv[idx + 1])
    key = args[0] if args else "scheduler"
    return await check_process(key, max_age)


if __name__ == "__main__":  # pragma: no cover - 进程入口
    try:
        sys.exit(asyncio.run(_cli()))
    except Exception as exc:  # noqa: BLE001 healthcheck 崩溃必须表现为非零退出，不是 traceback
        print(f"heartbeat check failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
