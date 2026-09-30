"""T2.3 Job 执行器：消费 QUEUED Job 与其 PENDING JobItem，逐篇复用单篇 ingest 流水线。

设计口径（大纲 v1.4 §8.1 序2 验收锚）：
- **状态机**：Job `QUEUED → RUNNING → SUCCEEDED / PARTIAL_SUCCESS / FAILED`，严格经
  `state_machine.validate_transition`（越级流转 → 30005）；JobItem `PENDING → RUNNING →
  SUCCEEDED / FAILED`（无独立状态机，终态由 counts 收敛）；
- **并发安全**：取件走 `FOR UPDATE SKIP LOCKED`（repositories/job.py claim_next_*），
  PG 双 worker 同取不同项；
- **崩溃自愈**：RUNNING 心跳超时 → Job 回退 QUEUED、其 RUNNING item 回退 PENDING；
- **幂等复用**：逐篇调 `kb.ingest_url`，**完整复用** P0 缓存/短链/版本/superseded 链，
  零新增微信抓取逻辑（大纲 1.3.2 口径）。

术语对齐注记（防复议）：大纲文字写作 "→DONE/FAILED"，代码契约实为
`SUCCEEDED / PARTIAL_SUCCESS / FAILED`（entities.py:175 注释 + state_machine.py:14-17）。
**以实现为准**，本模块统一使用契约词。

限流暂停口径（不擅改状态机契约）：连续限流时 **保持 RUNNING + error 标记
`paused:rate_limited`**，剩余 item 留 PENDING，由 `run_forever` 的自愈（心跳超时 → QUEUED）
重入。不新增 `PAUSED` 状态——那属状态机契约变更，须先走 APPROVE（见台账口径注记）。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, assert_production_ready, get_settings
from app.core.errors import (
    AppError,
    DependencyUnavailableError,
    ExtractQualityLowError,
    RateLimitedUpstreamError,
    SourceUrlUnrecognizedError,
)
from app.repositories.job import JobItemRepository, JobRepository
from app.services.process_heartbeat import BEACON_MIN_INTERVAL_SECONDS, BeaconGate
from app.services.process_heartbeat import beacon as _heartbeat
from app.services.state_machine import validate_transition

logger = structlog.get_logger(__name__)

JOB_STATUS_QUEUED = "QUEUED"
JOB_STATUS_RUNNING = "RUNNING"
JOB_STATUS_SUCCEEDED = "SUCCEEDED"
JOB_STATUS_PARTIAL = "PARTIAL_SUCCESS"
JOB_STATUS_FAILED = "FAILED"

ITEM_STATUS_PENDING = "PENDING"
ITEM_STATUS_RUNNING = "RUNNING"
ITEM_STATUS_SUCCEEDED = "SUCCEEDED"
ITEM_STATUS_FAILED = "FAILED"

PAUSED_PREFIX = "paused:rate_limited"
_ERROR_MAX_LEN = 500

# W2：无 JobItem 的单作业类型——claim 后直接跑处理函数，不走 _drain_items/_finalize
# （后者按 JobItem counts 收敛，对无 item 的 Job 会误判 total=0 → FAILED）。
HOT_JOB_TYPES = frozenset({"hot_cluster", "daily_report", "hot_rescore"})
_HOT_BUSINESS_TZ = ZoneInfo("Asia/Shanghai")


class IngestInvoker(Protocol):
    """逐篇入库调用口：默认走 `KnowledgeBaseService.ingest_url`，测试注入桩。"""

    def __call__(self, session: AsyncSession, space_id: str, url: str) -> Awaitable[dict[str, Any]]: ...


def _parse_payload(payload: str) -> dict[str, Any]:
    try:
        data = json.loads(payload or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _is_throttle_error(exc: Exception) -> bool:
    """限流/配额类错误 → 应暂停整批（而非当作单篇失败计入 PARTIAL）。

    - `RateLimitedUpstreamError`（4004 限频）直接命中；
    - `DependencyUnavailableError` 需辨别来源：RedFox 3201 积分余额不足属"整批不可继续"，
      而 LangBot 5xx 等瞬时不可用同样宜暂停等待（由自愈重入），故一并纳入。
    """
    if isinstance(exc, RateLimitedUpstreamError):
        return True
    if isinstance(exc, DependencyUnavailableError):
        text = str(exc)
        return "3201" in text or "积分余额不足" in text or "不可达" in text
    return False


def _is_permanent_error(exc: Exception) -> bool:
    """不可重试的域错误：链接本身不是公众号文章 / 正文质量不足，重采必然同结果。

    `kb._resolve_with_retry` 内部已跳过这两类的重试，但 worker 每次重试都是**从头再跑一遍
    ingest_url**，等于把同一结论重采 4 次（含退避等待）。实测 2026-09-25：一条假链接
    retry_count 到 3、耗时 ~14s，纯属浪费上游额度。
    """
    return isinstance(exc, SourceUrlUnrecognizedError | ExtractQualityLowError)


def make_default_ingest(settings: Settings) -> IngestInvoker:
    """生产默认调用口：装配 LangBot 客户端 + resolver + 引擎路由，逐篇走单篇流水线。

    刻意只在 services 层装配（不引 `app.api.deps`），避免 services→api 的反向依赖。
    """
    from app.providers.engine_port import EngineRouter
    from app.providers.langbot.client import LangBotClient
    from app.providers.raw_store import make_raw_store
    from app.services.kb import KnowledgeBaseService
    from app.services.resolver import SourceResolverService

    client = LangBotClient(
        settings.langbot_base_url,
        settings.langbot_admin_username,
        settings.langbot_admin_password,
    )
    resolver = SourceResolverService()

    async def _ingest(session: AsyncSession, space_id: str, url: str) -> dict[str, Any]:
        svc = KnowledgeBaseService(
            client,
            session,
            resolver,
            settings=settings,
            raw_store=make_raw_store(),
            engine_router=EngineRouter(settings, client),
        )
        return await svc.ingest_url(space_id, url)

    return _ingest


class JobWorker:
    """单进程 worker：一次取一件 job，逐篇消费至终态；可注入会话工厂与入库桩。"""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        ingest: IngestInvoker,
        *,
        settings: Settings | None = None,
        item_interval_seconds: float | None = None,
        max_item_retries: int | None = None,
        stale_job_seconds: int | None = None,
        idle_sleep_seconds: float | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        heartbeat_enabled: bool = True,
    ) -> None:
        self._factory = session_factory
        self._ingest = ingest
        s = settings or get_settings()
        self._item_interval = (
            item_interval_seconds
            if item_interval_seconds is not None
            else float(getattr(s, "job_worker_item_interval_seconds", 2.0))
        )
        self._max_retries = (
            max_item_retries if max_item_retries is not None else int(getattr(s, "job_worker_max_retries", 3))
        )
        self._stale_seconds = (
            stale_job_seconds
            if stale_job_seconds is not None
            else int(getattr(s, "job_worker_stale_seconds", 300))
        )
        self._idle_sleep = (
            idle_sleep_seconds
            if idle_sleep_seconds is not None
            else float(getattr(s, "job_worker_idle_sleep_seconds", 5.0))
        )
        self._sleep = sleep or asyncio.sleep
        # 存活上报开关：测试用真引擎直连共库时会绕过事务夹具，留下的心跳行是**运维可读的
        # 假存活信号**（跑一遍测试就让人以为 worker 在跑），故测试桩必须关掉它。
        self._heartbeat_enabled = heartbeat_enabled
        # 心跳节流门：`run_once` 内可能长跑（大批量逐篇 ingest），节流避免把心跳表
        # 变成每篇一次的高频写入面。
        self._gate = BeaconGate(BEACON_MIN_INTERVAL_SECONDS, clock=time.monotonic)

    # ------------------------------------------------------------------ 存活上报

    async def _beacon(self, detail: str = "") -> None:
        """向 `process_heartbeats` 报到一次；失败不影响消费。

        为什么必须吞异常：心跳写不进去时若上抛，会把「可观测性故障」放大成
        「队列全线停摆」——一次数据库抖动即让所有 Job 卡死，得不偿失。
        存活信号缺失本身会被读侧如实报为 `stale`，仍可见。
        """
        if not self._heartbeat_enabled or not self._gate.ready():
            return
        try:
            async with self._factory() as session:
                await _heartbeat(session, "worker", detail)
        except Exception:  # noqa: BLE001
            logger.debug("job_worker 心跳写入失败（不影响本轮消费）", exc_info=True)

    # ------------------------------------------------------------------ 自愈

    async def recover_stale(self) -> int:
        """崩溃自愈：心跳超时的 RUNNING job → QUEUED，其 RUNNING item → PENDING。"""
        async with self._factory() as session:
            stale_ids = await JobRepository(session).requeue_stale_running(self._stale_seconds)
            if not stale_ids:
                return 0
            item_repo = JobItemRepository(session)
            for jid in stale_ids:
                await item_repo.requeue_running(jid)
            await session.commit()
            logger.warning("job_worker 自愈回退 %d 件滞留 job: %s", len(stale_ids), stale_ids)
            return len(stale_ids)

    # ------------------------------------------------------------------ 主循环

    async def run_once(self) -> bool:
        """取一件 QUEUED job 并消费至终态；无可取 → False。

        W2 起按 job.type 分流：hot_cluster/daily_report 走 `_run_hot_job`（无 JobItem，
        单作业直接执行）；其余走既有 `_drain_items` + `_finalize`（按 JobItem counts 收敛）。
        """
        async with self._factory() as session:
            job = await JobRepository(session).claim_next_queued()
            if job is None:
                return False
            job_id = job.id
            job_type = job.type
            payload = _parse_payload(job.payload)

        if job_type in HOT_JOB_TYPES:
            await self._run_hot_job(job_id, job_type, payload)
            return True

        space_id = str(payload.get("space_id", ""))
        await self._drain_items(job_id, space_id)
        await self._finalize(job_id)
        return True

    async def run_forever(self, stop: asyncio.Event | None = None) -> None:
        """常驻循环：无活时空转（含自愈巡检）。`stop` 置位后优雅退出。

        轮次开始即报到心跳（节流 `BEACON_MIN_INTERVAL_SECONDS`）。放**开头**而非末尾：
        容器在跑但循环卡死时，心跳会立刻过期被读侧报 `stale`；若放末尾，卡死期间
        心跳仍是上一轮的旧值，等于用阈值掩盖卡死。
        """
        while stop is None or not stop.is_set():
            await self._beacon()
            try:
                await self.recover_stale()
                worked = await self.run_once()
            except Exception as exc:  # noqa: BLE001 worker 不得因单轮异常退出
                logger.exception("job_worker 单轮异常: %s", exc)
                worked = False
            if not worked:
                await self._sleep(self._idle_sleep)

    # ------------------------------------------------------------------ W2 单作业

    async def _run_hot_job(self, job_id: str, job_type: str, payload: dict[str, Any]) -> None:
        """hot_cluster / hot_rescore / daily_report 处理分支：单作业执行，无 JobItem。

        懒导入服务层避免 worker 启动期强耦合；失败记 error 并收敛到 FAILED（不抛穿，
        与既有逐篇消费口径一致——单轮异常不得让 worker 退出）。

        评分接线语义：
        - hot_cluster 分支：聚簇后首次评分——run_clustering 落库 HotTopic(hot_score=0.0)，
          run_scoring 在同事务回填真实分数 + 同步 FeedItem.score；
        - hot_rescore 分支：周期重评分——仅调 run_scoring 刷新所有非 archived 话题分数；
        - daily_report 分支：日报前兜底重算——保证 TOP10 按最新分排序，
          与入队顺序解耦（评分可能在日报入队后被 hot_rescore 刷新）。
        """
        try:
            async with self._factory() as session:
                if job_type == "hot_cluster":
                    from app.core.metrics import HOT_CLUSTER_DURATION
                    from app.services.hot_cluster import run_clustering
                    from app.services.hot_scorer import run_scoring

                    _t0 = time.perf_counter()
                    try:
                        await run_clustering(session, days=int(payload.get("days", 1)))
                    finally:
                        HOT_CLUSTER_DURATION.observe(time.perf_counter() - _t0)
                    await run_scoring(session)
                elif job_type == "hot_rescore":
                    from app.services.hot_scorer import run_scoring

                    await run_scoring(session)
                elif job_type == "daily_report":
                    from app.services.feed_service import build_daily_report
                    from app.services.hot_scorer import run_scoring

                    await run_scoring(session)
                    report_date = str(payload.get("date", ""))
                    if not report_date:
                        report_date = (
                            datetime.now(_HOT_BUSINESS_TZ) - timedelta(days=1)
                        ).strftime("%Y-%m-%d")
                    await build_daily_report(session, report_date)
                await session.commit()
            await self._finalize_simple(job_id, True, "")
        except Exception as exc:  # noqa: BLE001 单作业失败不退出 worker
            logger.exception("hot job %s 失败 job=%s", job_type, job_id)
            await self._finalize_simple(job_id, False, str(exc)[:_ERROR_MAX_LEN])

    async def _finalize_simple(self, job_id: str, ok: bool, error: str) -> None:
        """无 JobItem 的单作业终态收敛：RUNNING → SUCCEEDED / FAILED。"""
        async with self._factory() as session:
            job = await JobRepository(session).get_by_id(job_id)
            if job is None:
                return
            new_status = JOB_STATUS_SUCCEEDED if ok else JOB_STATUS_FAILED
            validate_transition("job", job.status, new_status)
            job.status = new_status
            job.progress = 1
            if error:
                job.error = error
            await session.commit()
            logger.info("hot job 终态 job=%s status=%s", job_id, new_status)

    # ------------------------------------------------------------------ 逐篇消费

    async def _drain_items(self, job_id: str, space_id: str) -> None:
        """逐篇消费：取件 → ingest → SUCCEEDED / 退避重试 / FAILED；限流则暂停整批。"""
        paused = False
        error_msg = ""
        while not paused:
            async with self._factory() as session:
                item = await JobItemRepository(session).claim_next_pending(job_id)
                if item is None:
                    return
                item_id, url, attempts = item.id, item.url, int(item.retry_count or 0)

            error_type, error_msg = "", ""
            throttled = False
            permanent = False
            async with self._factory() as session:
                try:
                    if not url:
                        raise ValueError("item.url 为空，无可采地址")
                    await self._ingest(session, space_id, url)
                except Exception as exc:  # noqa: BLE001 逐篇失败不得中断整批
                    error_type = type(exc).__name__
                    # 业务异常自带已登记错误码与面向用户的文案，不拼内部类名；
                    # 未预期异常保留类名，便于定位故障根因
                    error_msg = str(exc) if isinstance(exc, AppError) else f"{error_type}: {exc}"
                    throttled = _is_throttle_error(exc)
                    permanent = _is_permanent_error(exc)

            retryable = bool(error_type) and not throttled and not permanent and attempts < self._max_retries
            async with self._factory() as session:
                repo = JobItemRepository(session)
                if not error_type:
                    await repo.set_status(item_id, ITEM_STATUS_SUCCEEDED)
                elif throttled:
                    # 限流暂停：item 留 PENDING 待重入，不打 FAILED（不计入 PARTIAL 分母）
                    await repo.set_status(item_id, ITEM_STATUS_PENDING, error_msg[:_ERROR_MAX_LEN])
                elif retryable:
                    await repo.set_status(item_id, ITEM_STATUS_PENDING, error_msg[:_ERROR_MAX_LEN])
                    await repo.bump_retry(item_id)
                else:
                    await repo.set_status(item_id, ITEM_STATUS_FAILED, error_msg[:_ERROR_MAX_LEN])
                await self._touch(job_id, session)
                await session.commit()

            # 大批量 Job 逐篇 ingest 可远超 stale 阈值（数千篇 × 退避），
            # 只靠 `run_forever` 轮首报到的话，健康消费会被误报 stale。
            await self._beacon(f"job={job_id} item={item_id} retry={attempts}")

            if throttled:
                logger.warning("job_worker 限流暂停 job=%s item=%s: %s", job_id, item_id, error_msg)
                paused = True
                break
            if retryable:
                await self._sleep(self._backoff(attempts))
            else:
                await self._sleep(self._item_interval)

        if paused:
            async with self._factory() as session:
                job = await JobRepository(session).get_by_id(job_id)
                if job is not None:
                    job.error = f"{PAUSED_PREFIX}: {error_msg}"[:_ERROR_MAX_LEN]
                    await session.commit()

    async def _touch(self, job_id: str, session: AsyncSession) -> None:
        """心跳 + 进度（已完成 item 数 / 总数）。"""
        repo = JobItemRepository(session)
        counts = await repo.counts(job_id)
        await JobRepository(session).heartbeat(job_id, counts["succeeded"] + counts["failed"])

    async def _finalize(self, job_id: str) -> None:
        """终态收敛：全成 → SUCCEEDED；有成有败 → PARTIAL_SUCCESS；无成 → FAILED。

        未消费完（pending>0，含限流暂停与崩溃）→ **保持 RUNNING**，交由自愈重入，
        不写终态以免丢失可续性。
        """
        async with self._factory() as session:
            job = await JobRepository(session).get_by_id(job_id)
            if job is None:
                return
            counts = await JobItemRepository(session).counts(job_id)
            total, ok, failed, pending = (
                counts["total"],
                counts["succeeded"],
                counts["failed"],
                counts["pending"],
            )
            if pending > 0:
                await session.commit()  # 保持 RUNNING；error 已在暂停分支标记
                return
            if total == 0:
                new_status, note = JOB_STATUS_FAILED, "no_items: 清单为空（Manifest 未落库或无可采篇目）"
            elif failed == 0:
                new_status, note = JOB_STATUS_SUCCEEDED, ""
            elif ok == 0:
                new_status, note = JOB_STATUS_FAILED, f"all_failed: {failed}/{total} 篇失败"
            else:
                new_status, note = JOB_STATUS_PARTIAL, f"partial: {failed}/{total} 篇失败可重试"
            validate_transition("job", job.status, new_status)
            job.status = new_status
            job.progress = total
            if note:
                job.error = note[:_ERROR_MAX_LEN]
            await session.commit()
            logger.info("job_worker 终态 job=%s status=%s counts=%s", job_id, new_status, counts)

    def _backoff(self, attempts: int) -> float:
        """指数退避：interval × 2^attempts（attempts 从 0 起）。"""
        return float(self._item_interval * (2**max(attempts, 0)))


async def _main() -> None:
    """`python -m app.services.job_worker` 入口（compose worker 服务用）。"""
    from app.core.logging import configure_logging

    configure_logging()
    settings = get_settings()
    assert_production_ready(settings)
    from app.db import create_engine_and_session

    engine, factory = create_engine_and_session(settings.database_url)
    stop = asyncio.Event()
    worker = JobWorker(factory, make_default_ingest(settings), settings=settings)
    try:
        await worker.run_forever(stop)
    except asyncio.CancelledError:  # pragma: no cover - 信号退出路径
        stop.set()
        raise
    finally:
        with contextlib.suppress(Exception):
            await engine.dispose()


if __name__ == "__main__":  # pragma: no cover - 进程入口
    asyncio.run(_main())
