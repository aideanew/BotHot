"""T2.4 增量调度器：`next_run_at` 驱动触发 + `consecutiveEmpty` 退避。

设计口径（大纲 v1.4 §8.1 序3 验收锚）：
- **触发窗口**：`status=ACTIVE AND next_run_at <= now` 的订阅为「到期」；到期的逐条触发
  一轮增量同步（`_populate_job_items` 的 Diff 侧），**不重不漏**（`FOR UPDATE SKIP LOCKED`，
  见 repositories/subscription.py claim_due）；
- **固定时点锚（每天 10 点这类需求）**：`sync_anchor_hour` 非空时，`next_run_at` 不再取
  `now + interval` 的滑动值，而是对准调度器时区（`scheduler_timezone`，默认 Asia/Shanghai）
  的**下一次该整点**；空轮询退避按整天往后跳（mult=2 → 次日同点），故锚定订阅恒为
  「每天一次」，不会因隔间小于一天而退化成一天多次；
- **并发执行**：同一轮内 `scheduler_concurrency` 条到期订阅**并行**同步，不串行排队。
  并发安全完全来自 `claim_due` 的 SKIP LOCKED 行锁——各事务认领互不相同的订阅；
- **空轮询退避**：一轮同步 Diff 结果为空（无新篇）→ `consecutive_empty_syncs += 1`，
  下次触发时间按 `interval × min(2^n, cap)` 指数拉开（首次空即 2×），避免无谓空轮询；
  一旦发现新篇 → 计数清零、恢复基准间隔；
- **原子性**：认领 + 入列 + 水位推进在**同一条事务**内完成（claim_due 不 commit）；
  崩溃则整体回滚，`next_run_at` 保持原值，下个 tick 自然重试（at-least-once）。

与 T2.3 的分工：调度器只管「**何时**触发、触发后水位怎么走」；入列的 Job 由 JobWorker
（T2.3）消费。二者共享同一套 Job/JobItem 表，无接口耦合。

与 T2.2 的衔接：默认 runner（`make_default_sync_runner`）在一轮触发内**先发现后入列**——
`REDFOX_API_KEY` 配置时拉清单幂等落 `ArticleManifest`（T2.2），再按 Diff 增量入列（T2.4）；
未配置则跳过发现、仅按既有清单 Diff（不造数、不打断调度）。发现/入列抛错 → 整轮回滚、
水位按基准间隔推进，既不吞错空转、也不污染空轮询退避语义。

术语对齐注记（防复议）：订阅表的空轮询计数字段为 `consecutive_empty_syncs`
（entities.py:84，落库名 `consecutive_empty_syncs`），前端呈现口径写作 `consecutiveEmptySyncs`
（subscription.py:181）。同一字段，本模块用库名。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Protocol
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, assert_production_ready, get_settings
from app.models.entities import Source, SourceSubscription, User
from app.providers.discovery.registry import make_default_provider, resolve_default_channel
from app.repositories.subscription import SourceSubscriptionRepository
from app.services.manifest import ManifestSyncService, WorkListProvider
from app.services.process_heartbeat import BEACON_MIN_INTERVAL_SECONDS, BeaconGate
from app.services.process_heartbeat import beacon as _heartbeat
from app.services.subscription import SourceSubscriptionService

logger = structlog.get_logger(__name__)

DEFAULT_INTERVAL_MINUTES = 360  # 与 SourceSubscription.sync_interval_minutes 默认值一致

# W2：每日定时入队热点/日报 Job 的时点（本地时区 06:30）。日报生成**前一日**，
# 聚簇取近 1 日——放在 06:30 让凌晨发布的内容有窗口沉淀，不卡在 0 点边界。
DAILY_REPORT_HOUR = 6
DAILY_REPORT_MINUTE = 30

HOT_CLUSTER_HOUR = 6
HOT_CLUSTER_MINUTE = 35

RESCORE_INTERVAL_HOURS = 1


class SyncRunner(Protocol):
    """单订阅增量同步调用口：返回本轮**新增篇数**（0 = 空轮询）。

    默认走 `SourceSubscriptionService.run_incremental_sync`；测试注入桩以隔离调度算术。
    """

    def __call__(
        self, session: AsyncSession, sub: SourceSubscription, run_token: str
    ) -> Awaitable[int]: ...


class DocReconcileFn(Protocol):
    """后台推进非终态文档的入库状态；返回本轮**状态发生变化的篇数**。

    为什么需要它：`kb.ingest_url` 触发引擎**异步**入库后即返回，doc 停在 INDEXED；
    本地状态只在有人调 `get_doc_ingest_status` 时才被懒推进。单篇 UI 会轮询该端点，
    但**批量入库与订阅同步都只轮询 Job、从不轮询单篇文档状态**——没有服务端兜底的话，
    这两条路的文档会永远显示「采集中」，而任务中心却报成功（2026-09-25 实测：
    批量重采一篇后 doc 停在 INDEXED 8 分钟以上，admin 文档清单与空间列表同时失真）。
    """

    def __call__(self, session: AsyncSession) -> Awaitable[int]: ...


def _utc_from_epoch(dt: datetime) -> datetime:
    """把 datetime 按**绝对时刻**解释成 UTC。

    naive 输入按 UTC 时刻解释（不猜测其「原本所在时区」）：`astimezone()` 对 naive
    datetime 的行为正是「当作 UTC」，故此处显式写出该约定，避免下游各处各自假设。
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _run_token(due_at: datetime | None, now: datetime) -> str:
    """本轮运行令牌 = 触发时刻的 `next_run_at`（微秒精度，天然唯一）。

    用作 Job 幂等键尾缀 → 同一轮重放（调度器崩溃后同值重启）不建双 Job；
    跨轮次 `next_run_at` 必变 → 新轮次建新 Job（增量语义）。
    """
    stamp = due_at if due_at is not None else now
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC).strftime("%Y%m%dT%H%M%S%f")


def make_sync_runner(
    provider: WorkListProvider | None,
    *,
    max_pages: int = 20,
    skip_reason: str = "发现渠道未配置",
) -> SyncRunner:
    """装配一轮同步：**先发现（T2.2）→ 再 Diff 增量入列（T2.4）**。

    `provider is None` = 无可用发现渠道 → 跳过发现、仅按既有清单 Diff（日志留痕，
    不造数、不打断调度，承 1.1.4 口径）。显式注入 provider 供单测/离线验证。
    `skip_reason` 由调用方给出（渠道名 / 凭据项），此处不写死具体渠道。
    """

    async def _run(session: AsyncSession, sub: SourceSubscription, run_token: str) -> int:
        if provider is None:
            logger.warning(
                "%s：跳过 Manifest 发现，仅按既有清单 Diff（source=%s）",
                skip_reason,
                sub.source_id,
            )
        else:
            src = await session.get(Source, sub.source_id)
            if src is not None and src.external_id:
                await ManifestSyncService(session, provider).sync_source(
                    sub.source_id, src.external_id, max_pages=max_pages
                )
        return await SourceSubscriptionService(session).run_incremental_sync(sub, run_token)

    return _run


def make_default_sync_runner(settings: Settings | None = None) -> SyncRunner:
    """生产默认调用口：按后台配置解析默认发现渠道并装配（无可用渠道 → 跳过发现）。

    渠道选择全在 `providers/discovery/registry.py`（注册表 ∩ 启用白名单 → 默认解析）；
    此处只装配，不判渠道。
    """
    s = settings or get_settings()
    max_pages = int(getattr(s, "manifest_sync_max_pages", 20))
    channel = resolve_default_channel(s)
    if channel is None:
        logger.warning(
            "发现渠道全部不可用（discovery_channels=%r / discovery_default_channel=%r）："
            "跳过 Manifest 发现，仅按既有清单 Diff",
            s.discovery_channels,
            s.discovery_default_channel,
        )
        return make_sync_runner(None, max_pages=max_pages)
    return make_sync_runner(
        make_default_provider(s),
        max_pages=max_pages,
        skip_reason=f"发现渠道 {channel} provider 装配失败",
    )


def make_default_doc_reconciler(settings: Settings | None = None) -> DocReconcileFn:
    """生产默认：逐篇以引擎文件状态为准推进 INDEXED/FETCHED → READY/FAILED。

    逐篇各发一次文件清单请求（builtin 走 `_poll_file_status`），故按
    `scheduler_doc_reconcile_limit` 限额；非终态 doc 数量天然很小，限额内即可完成。
    单篇探测失败只跳过该篇，不影响整轮（下一 tick 重试）。
    """
    s = settings or get_settings()
    limit = int(getattr(s, "scheduler_doc_reconcile_limit", 20))

    async def _reconcile(session: AsyncSession) -> int:
        from app.providers.engine_port import EngineRouter
        from app.providers.langbot.client import LangBotClient
        from app.providers.raw_store import make_raw_store
        from app.repositories.asset import DocumentRepository
        from app.services.kb import KnowledgeBaseService
        from app.services.resolver import SourceResolverService

        repo = DocumentRepository(session)
        docs = await repo.list_pending_ingest(limit)
        if not docs:
            return 0

        client = LangBotClient(
            s.langbot_base_url, s.langbot_admin_username, s.langbot_admin_password
        )
        svc = KnowledgeBaseService(
            client,
            session,
            SourceResolverService(),
            settings=s,
            raw_store=make_raw_store(),
            engine_router=EngineRouter(s, client),
        )
        advanced = 0
        for doc in docs:
            before = doc.status
            try:
                await svc.get_doc_ingest_status(doc.space_id, doc.id)
            except Exception:  # noqa: BLE001 单篇失败不中断整轮（含 FAILED 上抛的 IngestFailedError）
                logger.warning("文档状态推进跳过 doc=%s", doc.id, exc_info=True)
                continue
            fresh = await repo.get_by_id(doc.id)
            if fresh is not None and fresh.status != before:
                advanced += 1
        return advanced

    return _reconcile


class IncrementalScheduler:
    """增量调度器：扫描到期订阅 → 触发一轮同步 → 推进 `next_run_at`（含空轮询退避）。"""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        settings: Settings | None = None,
        sync_runner: SyncRunner | None = None,
        doc_reconciler: DocReconcileFn | None = None,
        now_fn: Callable[[], datetime] | None = None,
        max_backoff_multiplier: int | None = None,
        batch_limit: int | None = None,
        idle_sleep_seconds: float | None = None,
        concurrency: int | None = None,
        timezone: str | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        heartbeat_enabled: bool = True,
    ) -> None:
        self._factory = session_factory
        self._sync = sync_runner or make_default_sync_runner()
        self._reconcile = doc_reconciler or make_default_doc_reconciler()
        s = settings or get_settings()
        self._now = now_fn or (lambda: datetime.now(UTC))
        self._max_mult = (
            max_backoff_multiplier
            if max_backoff_multiplier is not None
            else int(getattr(s, "scheduler_max_backoff_multiplier", 8))
        )
        self._batch_limit = (
            batch_limit if batch_limit is not None else int(getattr(s, "scheduler_batch_limit", 100))
        )
        self._idle_sleep = (
            idle_sleep_seconds
            if idle_sleep_seconds is not None
            else float(getattr(s, "scheduler_idle_sleep_seconds", 10.0))
        )
        self._concurrency = max(
            1,
            concurrency if concurrency is not None else int(getattr(s, "scheduler_concurrency", 1)),
        )
        # 固定时点锚的时区口径：sync_anchor_hour=10 在此时区解读为每天 10:00。
        # ZoneInfo 不可用时回归 UTC 而不是让调度器拒启（时区数据缺失属部署瑕疵，
        # 不应导致整号采集全线停摆）。
        self._tz: tzinfo
        zone_name = timezone or str(getattr(s, "scheduler_timezone", "Asia/Shanghai"))
        try:
            self._tz = ZoneInfo(zone_name)
        except Exception:  # noqa: BLE001
            logger.warning("scheduler 时区 %r 不可用，固定时点锚回退 UTC", zone_name)
            self._tz = UTC
        self._sleep = sleep or asyncio.sleep
        # 存活上报开关：测试用真引擎直连共库时会绕过事务夹具，留下的心跳行是**运维可读的
        # 假存活信号**（跑一遍测试就让人以为 scheduler 在跑），故测试桩必须关掉它。
        self._heartbeat_enabled = heartbeat_enabled
        # 心跳节流门：单实例字段，`run_once` 可并发重入但门本身是同步比较，无锁需求
        self._gate = BeaconGate(BEACON_MIN_INTERVAL_SECONDS, clock=time.monotonic)
        # W2：每日热点/日报入队的进程内去重戳（同日已入队则不重复）。跨重启由
        # JobService 的 idempotency_key 兜底（同日同类型 Job 重复提交返回既有）。
        self._last_daily_date: str | None = None
        # 审查缝合：hot_cluster 独立幂等戳（与 daily_report 分门控错峰）
        self._last_cluster_date: str | None = None
        # WA：每小时整点后首 tick 入队 hot_rescore 的进程内去重戳（同小时不重复）。
        # 跨重启由 idempotency_key 兜底。
        self._last_rescore_hour: str | None = None

    # ------------------------------------------------------------------ 存活上报

    async def _beacon(self, detail: str = "") -> None:
        """向 `process_heartbeats` 报到一次；失败不影响调度。

        为什么必须吞异常：心跳写不进去时若上抛，会把「可观测性故障」放大成
        「采集全线停摆」——一次数据库抖动即丢整天采集，得不偿失。
        存活信号缺失本身会被读侧如实报为 `stale`，仍可见。
        """
        if not self._heartbeat_enabled or not self._gate.ready():
            return
        try:
            async with self._factory() as session:
                await _heartbeat(session, "scheduler", detail)
        except Exception:  # noqa: BLE001
            logger.debug("scheduler 心跳写入失败（不影响本轮调度）", exc_info=True)

    # ------------------------------------------------------------------ W2 每日热点/日报

    async def _maybe_enqueue_daily_jobs(self) -> None:
        """每日入队热点/日报 Job——两个独立门控真正错峰（审查缝合修正）。

        语义：06:30 入队 daily_report（前一日），06:35 入队 hot_cluster（近 1 日）。
        各自独立时间门与幂等戳（_last_daily_date / _last_cluster_date）——WA 初版把
        两个 Job 放在同一门控同一事务提交，created_at 相同、取件序仍未定，"错峰"
        名存实亡。两者无硬数据依赖（日报读前一日话题，聚簇产当日话题；评分由
        各分支前置 run_scoring 兜底），错峰只为负载平滑与取件序确定性。
        跨重启由 JobService 的 idempotency_key 兜底。operator 取首个 admin 用户。
        """
        now_local = datetime.now(self._tz)
        today = now_local.strftime("%Y-%m-%d")
        prev = (now_local - timedelta(days=1)).strftime("%Y-%m-%d")

        def _past(hour: int, minute: int) -> bool:
            return (now_local.hour, now_local.minute) >= (hour, minute) or now_local.hour > hour

        if self._last_daily_date != today and _past(DAILY_REPORT_HOUR, DAILY_REPORT_MINUTE):
            try:
                async with self._factory() as session:
                    operator_id = await self._resolve_operator_id(session)
                    if operator_id is None:
                        logger.warning("scheduler 跳过每日热点/日报入队：无 admin 用户可作 operator")
                        return
                    from app.repositories.job import JobRepository
                    from app.services.jobs import JobService

                    svc = JobService(JobRepository(session), session)
                    await svc.submit(
                        job_type="daily_report",
                        user_id=operator_id,
                        idempotency_key=f"daily_report:{prev}",
                        payload_json=json.dumps({"date": prev}),
                    )
                    await session.commit()
                self._last_daily_date = today
                logger.info("scheduler 每日入队：daily_report(%s)", prev)
            except Exception:  # noqa: BLE001 每日入队不得拖垮订阅调度
                logger.exception("scheduler daily_report 入队失败，下轮重试")

        if self._last_cluster_date != today and _past(HOT_CLUSTER_HOUR, HOT_CLUSTER_MINUTE):
            try:
                async with self._factory() as session:
                    operator_id = await self._resolve_operator_id(session)
                    if operator_id is None:
                        logger.warning("scheduler 跳过 hot_cluster 入队：无 admin 用户可作 operator")
                        return
                    from app.repositories.job import JobRepository
                    from app.services.jobs import JobService

                    svc = JobService(JobRepository(session), session)
                    await svc.submit(
                        job_type="hot_cluster",
                        user_id=operator_id,
                        idempotency_key=f"hot_cluster:{today}:1",
                        payload_json=json.dumps({"date": today, "days": 1}),
                    )
                    await session.commit()
                self._last_cluster_date = today
                logger.info("scheduler 每日入队：hot_cluster(%s)", today)
            except Exception:  # noqa: BLE001
                logger.exception("scheduler hot_cluster 入队失败，下轮重试")

    async def _maybe_enqueue_rescore(self) -> None:
        """每小时整点后首 tick 入队 hot_rescore（幂等）。

        语义：刷新所有非 archived 话题的热度分数与状态机（rising→hot→cooling→archived），
        保证 Feed 排序与状态标签始终反映最新衰减。
        幂等：进程内 `_last_rescore_hour` 戳防同小时重复；跨重启由 idempotency_key 兜底
        （格式 hot_rescore:yyyyMMddHH，同小时只入队一次）。
        """
        now_local = datetime.now(self._tz)
        hour_key = now_local.strftime("%Y%m%d%H")
        if self._last_rescore_hour == hour_key:
            return
        try:
            async with self._factory() as session:
                operator_id = await self._resolve_operator_id(session)
                if operator_id is None:
                    return
                from app.repositories.job import JobRepository
                from app.services.jobs import JobService

                svc = JobService(JobRepository(session), session)
                await svc.submit(
                    job_type="hot_rescore",
                    user_id=operator_id,
                    idempotency_key=f"hot_rescore:{hour_key}",
                    payload_json="{}",
                )
                await session.commit()
            self._last_rescore_hour = hour_key
            logger.info("scheduler 入队 hot_rescore（小时=%s）", hour_key)
        except Exception:  # noqa: BLE001
            logger.exception("scheduler hot_rescore 入队失败，下轮重试")

    async def _resolve_operator_id(self, session: AsyncSession) -> str | None:
        """取首个 admin 用户 id 作为系统触发 Job 的归属。无 admin → None（跳过）。"""
        rows = await session.scalars(
            select(User).where(User.role == "admin").limit(1)
        )
        u = rows.first()
        return u.id if u is not None else None

    # ------------------------------------------------------------------ 纯函数（可单测）

    def backoff_multiplier(self, consecutive_empty_syncs: int) -> int:
        """空轮询退避倍数 = `min(2^n, cap)`；n<=0 → 1（非空轮询基准）。

        序列（cap=8）：n=1→2，n=2→4，n=3→8，n≥3→8（截断）。
        """
        if consecutive_empty_syncs <= 0:
            return 1
        return int(min(2**consecutive_empty_syncs, self._max_mult))

    def _anchor_base(self, now: datetime, anchor_hour: int) -> datetime:
        """下一次「每天 anchor_hour:00:00」触发点（严格落在调度器时区的整点时点上）。

        为什么用 `_utc_from_epoch` 再 `astimezone` 而不是直接 `replace(tzinfo=tz)`：
        对 naive `now`，`replace` 会把它当作**当地时间**，而 `astimezone` 会当作 **UTC 时刻**
        换算——两者差一个 UTC 偏移，混用会让锚点静默错位约 8 小时（2026-09-26 复核）。
        """
        local = _utc_from_epoch(now).astimezone(self._tz)
        candidate = local.replace(hour=anchor_hour, minute=0, second=0, microsecond=0)
        if candidate <= local:
            candidate += timedelta(days=1)
        return candidate

    def next_run_at(
        self,
        now: datetime,
        interval_minutes: int,
        consecutive_empty_syncs: int,
        anchor_hour: int | None = None,
    ) -> datetime:
        """下次触发时间。

        anchor_hour 为 None（默认）= 历史滑动窗口：`now + interval × 退避倍数`。
        非 None = 固定时点锚：最近一次「每天 anchor_hour:00」为起点，空轮询退避按**整天**
        往后跳（mult=1 → 最近锚点；mult=2 → 次日同点；mult=3 → 第三日同点）。步长向上取整
        到整天，故锚定订阅永远是「每天一次」，不会退化成一天多次触发。
        """
        mult = self.backoff_multiplier(consecutive_empty_syncs)
        if anchor_hour is None:
            return now + timedelta(minutes=int(interval_minutes) * mult)
        step_days = max(1, round(int(interval_minutes) / 1440))
        return self._anchor_base(now, int(anchor_hour)) + timedelta(days=(mult - 1) * step_days)

    # ------------------------------------------------------------------ 主循环

    async def run_once(self) -> int:
        """处理一批到期订阅，返回本轮处理条数（含空轮询；不含未来订阅）。

        到期订阅按 `scheduler_concurrency` **并行**同步（多号同时到期不必串行排队）。
        并发安全来自 `claim_due` 的 `FOR UPDATE SKIP LOCKED`：各并发事务各自认领
        **互不相同**的订阅，无一条被重复取走。
        无到期订阅时同样执行文档状态推进——否则空转轮次不做任何事，
        批量/订阅入库的文档会一直停在 INDEXED。

        轮次开始即报到心跳（节流 `BEACON_MIN_INTERVAL_SECONDS`）。故意放**开头**而非末尾：
        容器在跑但循环卡死时，心跳会立刻过期被读侧报 `stale`；若放末尾，
        卡死期间心跳仍是上一轮的旧值，直到阈值超时才暴露，等于用阈值掩盖卡死。
        """
        await self._beacon()
        await self._maybe_enqueue_daily_jobs()
        await self._maybe_enqueue_rescore()
        await self._reconcile_docs()
        processed = 0
        while processed < self._batch_limit:
            results = await asyncio.gather(
                *(self._claim_and_process_one() for _ in range(self._concurrency))
            )
            done = sum(1 for ok in results if ok)
            if not done:
                break
            processed += done
        return processed

    async def _claim_and_process_one(self) -> bool:
        """单次认领 + 同步；单条异常只计为「本轮无进展」，不得拖垮并发批次。"""
        try:
            return await self._process_one()
        except Exception:  # noqa: BLE001 事务已回滚，下个 tick 自然重试
            logger.exception("scheduler 单条处理异常")
            return False

    async def run_forever(self, stop: asyncio.Event | None = None) -> None:
        """常驻循环：无到期订阅时空转。`stop` 置位后优雅退出。"""
        while stop is None or not stop.is_set():
            try:
                worked = await self.run_once()
            except Exception as exc:  # noqa: BLE001 调度器不得因单轮异常退出
                logger.exception("scheduler 单轮异常: %s", exc)
                worked = 0
            if not worked:
                await self._sleep(self._idle_sleep)

    # ------------------------------------------------------------------ 内部

    async def _reconcile_docs(self) -> int:
        """推进非终态文档入库状态；异常只记日志，不得拖垮订阅调度。"""
        try:
            async with self._factory() as session:
                advanced = await self._reconcile(session)
            if advanced:
                logger.info("scheduler 推进 %d 篇文档入库状态", advanced)
            return advanced
        except Exception:  # noqa: BLE001
            logger.exception("scheduler 文档状态推进失败，本轮跳过")
            return 0

    async def _process_one(self) -> bool:
        """认领一件到期订阅 → 同步一轮 → 推水位；无可取 → False。

        **认领与水位推进同事务提交**：行锁须持有到水位落库。若错误路径先回滚（释放锁）
        再另起事务推水位，中间存在可被重新认领的窗口——`scheduler_concurrency` 个并行事务
        或下一轮批次会认领到同一条订阅，同一轮内把 `_sync` 跑两次；发现阶段的 RedFox 清单
        调用按次计费，重复认领即重复扣费（实测 concurrency=4 + 立即抛错的 runner 约 4 成轮次）。
        """
        now = self._now()
        async with self._factory() as session:
            sub = await SourceSubscriptionRepository(session).claim_due(now)
            if sub is None:
                await session.rollback()
                return False

            sub_id = sub.id
            run_token = _run_token(sub.next_run_at, now)
            interval = int(sub.sync_interval_minutes or DEFAULT_INTERVAL_MINUTES)
            anchor = sub.sync_anchor_hour
            try:
                async with session.begin_nested():  # SAVEPOINT：只包住同步那一半的写入
                    new_count = await self._sync(session, sub, run_token)
            except Exception:
                # 发现/入列失败（如 RedFox 3201 积分不足、5xx）：SAVEPOINT 回滚丢弃半成品写入，
                # 水位按**基准间隔**在**同一事务**推进——既不吞错空转每 tick 重试，也不把「错误」
                # 记成「空轮询」污染退避语义。行锁与水位同提交，故不留下重新认领窗口。
                logger.exception("scheduler 同步失败 subscription=%s，水位按基准间隔推进", sub_id)
                sub.next_run_at = self.next_run_at(now, interval, 0, anchor)
                await session.commit()
                return True

            prev_empty = int(sub.consecutive_empty_syncs or 0)
            if new_count > 0:
                sub.consecutive_empty_syncs = 0
                mult = 1
            else:
                sub.consecutive_empty_syncs = prev_empty + 1
                mult = self.backoff_multiplier(sub.consecutive_empty_syncs)
            sub.next_run_at = self.next_run_at(now, interval, sub.consecutive_empty_syncs, anchor)
            sub.last_success_at = now
            await session.commit()
            logger.info(
                "scheduler 触发订阅 %s：新增=%d 空轮询累计=%d 下次=%s（%d×%s）",
                sub_id,
                new_count,
                sub.consecutive_empty_syncs,
                sub.next_run_at.isoformat(),
                mult,
                f"锚{anchor:02d}点" if anchor is not None else "滑动窗口",
            )
            return True


async def _main() -> None:  # pragma: no cover - 进程入口
    """`python -m app.services.scheduler` 入口。

    compose 编排已接线（2026-09-23：`docker compose` 的 `scheduler` 服务，
    见 docker/compose.yml 进程拓扑注释）。生产配置不合格时此处拒启。
    """
    from app.core.logging import configure_logging

    configure_logging()
    settings = get_settings()
    assert_production_ready(settings)
    from app.db import create_engine_and_session

    engine, factory = create_engine_and_session(settings.database_url)
    stop = asyncio.Event()
    scheduler = IncrementalScheduler(factory, settings=settings)
    try:
        await scheduler.run_forever(stop)
    except asyncio.CancelledError:  # pragma: no cover - 信号退出路径
        stop.set()
        raise
    finally:
        with contextlib.suppress(Exception):
            await engine.dispose()


if __name__ == "__main__":  # pragma: no cover - 进程入口
    asyncio.run(_main())
