"""运行期告警（W6 A.5）：三类硬化信号经**既有推送 Provider**投递。

三类告警（对应任务 A.5）：
1. **心跳缺失**：常驻进程（scheduler / worker）心跳 stale 或从未启动——
   正是 R7.7 那次「backend 全绿、采集停摆 5 天」的盲区，现主动点名。
2. **Job 积压**：`jobs` 表 `QUEUED` 超过阈值——队列只进不出的早期征兆。
3. **推送连败**：`push_logs` 最近 N 条投递**全部**非 success——某渠道持续投不出去。

投递复用 `providers/push.make_push_provider`（默认 `web` 站内通知，可经
`ALERT_CHANNEL` 指向已配置的飞书/钉钉/webhook），不新造投递面。

装配纪律
--------------------------------------
- **默认关闭**：`ALERTING_ENABLED` 非真时 `run_alert_checks` 直接返回空，绝不在
  开发/测试里意外推送；生产显式开启。
- **配置读 env、不进 Settings**：`core/config.py` 归 W7（禁改），阈值/渠道全部取自
  `os.environ`，保持零跨批次耦合。
- **探测函数可注入 session_factory**：调度接线（push_scheduler）传进程工厂，测试传
  内存/夹具库；三类探测各自独立 try，单类失败不影响其余。
- **告警本身best-effort**：`_deliver` 失败只记日志，绝不反噬调用它的主循环。
"""

from __future__ import annotations

import os

import structlog
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.providers.push import PushMessage, make_push_provider
from app.services.process_heartbeat import describe_liveness

logger = structlog.get_logger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _str_env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


async def _deliver(title: str, message: str) -> bool:
    """经配置的渠道投递一条告警；成功返回 True。失败吞异常并记日志。"""
    channel = _str_env("ALERT_CHANNEL", "web")
    target = _str_env("ALERT_TARGET", "")
    try:
        provider = make_push_provider(channel)
        result = await provider.push(
            PushMessage(external_user_id=target, title=title, message=message)
        )
        if not result.delivered:
            logger.warning("告警投递未成功", channel=channel, reason=result.reason)
        return bool(result.delivered)
    except Exception:  # noqa: BLE001  # 告警投递失败不能打断探测主流程
        logger.warning("告警投递异常", channel=channel, exc_info=True)
        return False


async def check_heartbeat_missing(session: AsyncSession) -> list[str]:
    """返回 stale / 从未启动的进程键（含 purpose 摘要文案供告警正文用）。"""
    snap = await describe_liveness(session)
    return [
        f"{p['processKey']}（lastHeartbeatAt={p['lastHeartbeatAt']} age={p['ageSeconds']}）"
        for p in snap["processes"]
        if p["stale"]
    ]


async def check_job_backlog(session: AsyncSession) -> int:
    """当前 QUEUED 积压条数（阈值判定由调用方按 `ALERT_JOB_BACKLOG` 决定）。"""
    row = (
        await session.execute(sa_text("SELECT COUNT(*) FROM jobs WHERE status = 'QUEUED'"))
    ).one()
    return int(row[0])


async def check_push_consecutive_failures(session: AsyncSession, window: int) -> bool:
    """最近 window 条投递（success/failed/dead）是否**全部**失败——不足 window 条不告警。"""
    rows = (
        await session.execute(
            sa_text(
                "SELECT status FROM push_logs "
                "WHERE status IN ('success', 'failed', 'dead') "
                "ORDER BY created_at DESC LIMIT :n"
            ).bindparams(n=window)
        )
    ).all()
    if len(rows) < window:
        return False
    return all(str(r[0]) != "success" for r in rows)


async def run_alert_checks(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[str]:
    """跑三类探测，命中即投递；返回**已触发**的告警标题列表（未启用返回空）。"""
    if not _flag("ALERTING_ENABLED", default=False):
        return []

    fired: list[str] = []
    window = _int_env("ALERT_PUSH_FAIL_WINDOW", 5)
    backlog_threshold = _int_env("ALERT_JOB_BACKLOG", 100)

    try:
        async with session_factory() as session:
            stale = await check_heartbeat_missing(session)
        if stale:
            fired.append("常驻进程心跳缺失")
            await _deliver(
                "BotHot 告警：进程心跳缺失",
                "以下常驻进程心跳过期或从未启动：" + "；".join(stale),
            )
    except Exception:  # noqa: BLE001  # 单类探测异常隔离
        logger.warning("心跳缺失探测失败", exc_info=True)

    try:
        async with session_factory() as session:
            backlog = await check_job_backlog(session)
        if backlog >= backlog_threshold:
            fired.append("Job 积压")
            await _deliver(
                "BotHot 告警：Job 积压",
                f"当前 QUEUED 任务 {backlog} 条（阈值 {backlog_threshold}）",
            )
    except Exception:  # noqa: BLE001
        logger.warning("Job 积压探测失败", exc_info=True)

    try:
        async with session_factory() as session:
            all_failed = await check_push_consecutive_failures(session, window)
        if all_failed:
            fired.append("推送连续失败")
            await _deliver(
                "BotHot 告警：推送连续失败",
                f"最近 {window} 条推送投递全部失败，请检查渠道配置与目标可达性",
            )
    except Exception:  # noqa: BLE001
        logger.warning("推送连败探测失败", exc_info=True)

    return fired
