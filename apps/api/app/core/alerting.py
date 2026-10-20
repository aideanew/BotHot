"""运行期告警（W6 A.5）：四类硬化信号经**既有推送 Provider**投递。

四类告警（对应任务 A.5 + STEP-05）：
1. **心跳缺失**：常驻进程（scheduler / worker）心跳 stale 或从未启动——
   正是 R7.7 那次「backend 全绿、采集停摆 5 天」的盲区，现主动点名。
2. **Job 积压**：`jobs` 表 `QUEUED` 超过阈值——队列只进不出的早期征兆。
3. **推送连败**：`push_logs` 最近 N 条投递**全部**非 success——某渠道持续投不出去。
4. **采集静默**（STEP-05，两条入口共用同一个日幂等门）：
   - `check_discovery_silence`：某源连续 N 轮同步零新增清单行，读库里既有的
     `source_subscriptions.consecutive_empty_syncs` ⇒ backend 进程也判得动；
   - `notify_discovery_event`：同步进程当场的「整页全丢弃」（契约 `CollectionEvent`
     的 `discovery.page_all_skipped`）⇒ 这一半发生在 scheduler 进程，backend 的
     探测看不见进程内指标，只能由事件侧直接投递。

投递复用 `providers/push.make_push_provider`（默认 `web` 站内通知，可经
`ALERT_CHANNEL` 指向已配置的飞书/钉钉/webhook），不新造投递面。

装配纪律
--------------------------------------
- **默认关闭**：`ALERTING_ENABLED` 非真时 `run_alert_checks` 直接返回空，绝不在
  开发/测试里意外推送；生产显式开启。
- **配置读 env、不进 Settings**：`core/config.py` 归 W7（禁改），阈值/渠道全部取自
  `os.environ`，保持零跨批次耦合。
- **探测函数可注入 session_factory**：调度接线（push_scheduler）传进程工厂，测试传
  内存/夹具库；四类探测各自独立 try，单类失败不影响其余。
- **告警本身best-effort**：`_deliver` 失败只记日志，绝不反噬调用它的主循环。
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.contracts.collection import CollectionEvent
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


# 进程启动时刻（单调钟）：供心跳告警的启动宽限使用。
_PROCESS_START_MONOTONIC = time.monotonic()


def in_startup_grace() -> bool:
    """心跳类告警的启动宽限期是否仍在生效（`ALERT_STARTUP_GRACE_SECONDS`，默认 0=不宽限）。

    为什么必须默认 0：滚动发布时新进程还没写第一拍心跳，`check_heartbeat_missing` 一定报 stale
    ——不加宽限则每次发版都变成一次「进程心跳缺失」误报；把宽限设成非零默认则会反过来
    吃掉 `test_alerting_drill.py:112` 那条「三探针全命中」的既有断言（进程刚起即在宽限内）。
    所以：**代码默认不宽限，部署侧由 compose/env 显式给 600**（见 docker/compose.yml）。

    只作用于心跳探测；Job 积压与推送连败是数据驱动的历史事实，与进程新旧无关，不受宽限影响。
    """
    grace = _int_env("ALERT_STARTUP_GRACE_SECONDS", 0)
    if grace <= 0:
        return False
    return (time.monotonic() - _PROCESS_START_MONOTONIC) < grace


# 同一告警的上次投递时刻（单调钟）。进程内状态——重启即重置，与"探测器随进程走"一致。
_LAST_FIRED_MONO: dict[str, float] = {}


def allow_alert(title: str) -> bool:
    """同一告警在冷却期内只投一次（`ALERT_COOLDOWN_SECONDS`，默认 0=不冷却）。

    为什么这条必须存在：`run_alert_checks` 由推送调度循环**每 60 秒**调一次
    （`services/push_scheduler.py:88-92`），而 STEP-16 把部署层 `ALERTING_ENABLED` 默认翻成
    true。没有冷却时，一条持续存在的积压/连败会**每分钟重投一条站内通知**——
    告警把自己变成故障源，最终被人整个关掉（等于回到 F-83 的起点）。

    代码默认仍是 0：`test_alerting_drill.py:123` 断言一次调用三探针全命中，
    非零默认会吃掉它；部署侧由 compose 给 1800。
    """
    cooldown = _int_env("ALERT_COOLDOWN_SECONDS", 0)
    now = time.monotonic()
    if cooldown > 0:
        last = _LAST_FIRED_MONO.get(title)
        if last is not None and (now - last) < cooldown:
            return False
    _LAST_FIRED_MONO[title] = now
    return True


def reset_alert_cooldown_state() -> None:
    """清空冷却与日幂等状态，供用例隔离（进程内 dict/set 会让相邻用例互相污染）。"""
    _LAST_FIRED_MONO.clear()
    _FIRED_DAYS.clear()


# ── STEP-05：采集静默的日幂等 ──────────────────────────────────────────────────

# 业务日界与全仓一致（Asia/Shanghai）：告警键里的 yyyymmdd 必须按业务日切，
# 否则跨零点的两轮同步会算成两个"一天一次"，把同一件事报两遍。
DISCOVERY_TZ = ZoneInfo("Asia/Shanghai")

# 已投递过的日幂等键（`{source_id}:{channel}:{yyyymmdd}[:{page}]`）。进程内状态，
# 与 `_LAST_FIRED_MONO` 同纪律：重启即重置，探测随进程走。
_FIRED_DAYS: set[str] = set()


def discovery_day_key(source_id: str, channel: str, at: datetime | None = None) -> str:
    """告警级日幂等键 `{source_id}:{channel}:{yyyymmdd}`（比事件级少一段 page）。

    为什么两级键都要有：契约 `CollectionEvent.idempotency_key`（collection.py:225-228）
    是 **page 级**，用于把同一页的重复事件去重；而投递给运维的那条告警必须**一天一条**，
    按页去重会让"这个源今天第 3 页又全丢"成为第 3 条告警。

    `strftime` 之前必须 `astimezone`：aware datetime 的 `strftime` 打的是它**自带偏移**的字段，
    不换算就等于拿 UTC 切业务日——UTC 17:00 已是上海次日 01:00，同一件事会被算成两天各一次。
    """
    moment = at.astimezone(DISCOVERY_TZ) if at is not None else datetime.now(DISCOVERY_TZ)
    return f"{source_id}:{channel}:{moment.strftime('%Y%m%d')}"


def discovery_idempotency_key(source_id: str, channel: str, page: int, at: datetime | None = None) -> str:
    """契约形状的 page 级事件键 `{source_id}:{channel}:{yyyymmdd}:{page}`。"""
    return f"{discovery_day_key(source_id, channel, at)}:{page}"


def allow_daily_alert(key: str) -> bool:
    """日幂等门：同键当天第一次放行并登记，之后一律挡下。"""
    if key in _FIRED_DAYS:
        return False
    _FIRED_DAYS.add(key)
    return True


async def notify_discovery_event(event: CollectionEvent) -> bool:
    """把一个采集静默事件投成一条当天唯一的告警；返回是否真的投递。

    投递正文只带键里已有的标识（源/渠道/页/丢弃行数）——**不带上游响应原文与凭据**。
    """
    day_key = discovery_day_key(event.source_id, str(event.channel), event.at)
    if not allow_daily_alert(day_key):
        logger.info("采集静默告警被日幂等抑制", key=event.idempotency_key)
        return False
    return await _deliver(
        "BotHot 告警：采集静默（整页全丢弃）",
        f"渠道 {event.channel} 的源 {event.source_id} 第 {event.idempotency_key.rsplit(':', 1)[-1]} 页"
        f" {event.count} 行全部不可用入库，本地清单零新增。请核对上游字段形状。",
    )


def _str_env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


async def _deliver(title: str, message: str) -> bool:
    """经配置的渠道投递一条告警；成功返回 True。失败吞异常并记日志。"""
    channel = _str_env("ALERT_CHANNEL", "web")
    target = _str_env("ALERT_TARGET", "")
    try:
        provider = make_push_provider(channel)
        result = await provider.push(PushMessage(external_user_id=target, title=title, message=message))
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
    row = (await session.execute(sa_text("SELECT COUNT(*) FROM jobs WHERE status = 'QUEUED'"))).one()
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


async def check_discovery_silence(session: AsyncSession, *, threshold: int) -> list[dict[str, object]]:
    """连续 `threshold` 轮及以上「调用成功而清单零新增」的 ACTIVE 订阅。

    读的是既有列 `source_subscriptions.consecutive_empty_syncs`（由调度器每轮写，
    `models/entities.py:93`）——所以 backend 进程不必共享发现进程的内存就能判。
    静默信号的另一半（整页全丢弃）只在同步进程内出声，见 `core/metrics.py` 的进程边界说明。

    SQL 只负责「取所有非零空轮询的 ACTIVE 订阅」，阈值比较留在 Python：把 `>= :n` 写进
    SQL 也能跑，但那条判据就无法脱离数据库被验证（用例的桩会话不会执行 WHERE）。
    行数天然很小（ACTIVE 且计数非零），不为它做优化。
    """
    rows = (
        await session.execute(
            sa_text(
                "SELECT ss.source_id, s.name, ss.consecutive_empty_syncs "
                "FROM source_subscriptions ss JOIN sources s ON s.id = ss.source_id "
                "WHERE ss.status = 'ACTIVE' AND ss.consecutive_empty_syncs > 0 "
                "ORDER BY ss.consecutive_empty_syncs DESC, ss.source_id"
            )
        )
    ).all()
    return [
        {"source_id": str(r[0]), "name": str(r[1]), "rounds": int(r[2])} for r in rows if int(r[2]) >= threshold
    ]


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
            # 一次判定只调一次 allow_alert：它在放行时就写入时间戳，
            # 若在条件里调一次、分支里再调一次，第二次必然落进自己的冷却 ⇒ 告警永远投不出去。
            if in_startup_grace():
                # 发版窗口内的首拍心跳缺失不是故障：降噪但留痕，避免"没告警"等于"没发生过"。
                logger.info("心跳缺失告警被启动宽限抑制", stale=len(stale))
            elif not allow_alert("常驻进程心跳缺失"):
                logger.info("心跳缺失告警被冷却期抑制", stale=len(stale))
            else:
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
            if allow_alert("Job 积压"):
                fired.append("Job 积压")
                await _deliver(
                    "BotHot 告警：Job 积压",
                    f"当前 QUEUED 任务 {backlog} 条（阈值 {backlog_threshold}）",
                )
            else:
                logger.info("Job 积压告警被冷却期抑制", backlog=backlog)
    except Exception:  # noqa: BLE001
        logger.warning("Job 积压探测失败", exc_info=True)

    try:
        async with session_factory() as session:
            all_failed = await check_push_consecutive_failures(session, window)
        if all_failed:
            if allow_alert("推送连续失败"):
                fired.append("推送连续失败")
                await _deliver(
                    "BotHot 告警：推送连续失败",
                    f"最近 {window} 条推送投递全部失败，请检查渠道配置与目标可达性",
                )
            else:
                logger.info("推送连败告警被冷却期抑制", window=window)
    except Exception:  # noqa: BLE001
        logger.warning("推送连败探测失败", exc_info=True)

    silence_threshold = _int_env("ALERT_DISCOVERY_SILENCE_ROUNDS", 3)
    try:
        async with session_factory() as session:
            silent = await check_discovery_silence(session, threshold=silence_threshold)
        for hit in silent:
            source_id = str(hit["source_id"])
            if not allow_daily_alert(discovery_day_key(source_id, "subscription")):
                logger.info("采集静默告警被日幂等抑制", source_id=source_id)
                continue
            fired.append(f"采集静默（连续空轮询）：{hit['name']}")
            await _deliver(
                "BotHot 告警：采集静默（连续空轮询）",
                f"源 {hit['name']}（{source_id}）连续 {hit['rounds']} 轮同步零新增清单行"
                f"（阈值 {silence_threshold}），请核对上游是否仍返回可用行。",
            )
    except Exception:  # noqa: BLE001
        logger.warning("采集静默探测失败", exc_info=True)

    return fired
