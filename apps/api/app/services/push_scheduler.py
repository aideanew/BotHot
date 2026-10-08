"""BotHot 推送任务调度器（W3 并发安全重构 + WB 重试补完）。

架构取舍（at-most-once 语义）：
- 短锁领取：FOR UPDATE SKIP LOCKED 选中 due 任务 → 同一短事务内推进
  next_run_at 与 last_run_at → commit 释放锁 → 事务外逐任务投递。
- 崩溃至多丢一轮投递：若进程在 commit 后、投递前崩溃，该轮投递丢失，
  下轮 cron 周期重新触发。这是 cron 调度的 at-most-once 语义，可接受。
- 事件 outbox 同为 at-most-once：claim_pending_events 在投递前标记 consumed_at，
  claim 后投递前崩溃则该事件丢失（换取绝不重复投递；如需 at-least-once 改为
  投递成功后再标记，代价是可能重复推送）。
- 单任务隔离：try/except 包裹，单任务异常不影响其他任务。
- 投递重试（WB）：可重试失败（网络/超时/5xx，由 Provider 回执 retryable 位标记）
  按指数退避重投（60/240/960s），重试态挂 PushTask.retry_count/next_retry_at；
  超过上限转 PushLog(status="dead") + 任务 status=failed 终态。领取谓词同时覆盖
  「cron 到期」与「重试到期」两类任务——重试到期的任务不动 next_run_at（cron
  节奏与重试节奏正交），只推进 last_run_at。
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.metrics import PUSH_DELIVERIES_TOTAL
from app.core.secret_crypto import decrypt_channel_secret, decrypt_extra_config
from app.models.bothot_entities import BotChannel, Notification, PushLog, PushTask
from app.providers.push import PushMessage, make_push_provider
from app.services.cron_expr import parse_cron_next
from app.services.push_events import claim_pending_events
from app.services.push_template import render

logger = structlog.get_logger(__name__)

# R3.3：轮询间隔 env 化（v0.9 §0.4 吸收项）。默认 60 不变，compose 不注入保持默认；
# 下限 5s 防误配——claim 是 SKIP LOCKED 短锁，频率过高徒增锁竞争与空轮询。
PUSH_SCHEDULER_INTERVAL = max(5, int(os.getenv("PUSH_SCHEDULER_INTERVAL", "60")))

# WB：投递重试策略——指数退避 base*4^(n-1)（60/240/960s），超过上限转死信终态。
MAX_PUSH_RETRIES = 3
RETRY_BACKOFF_BASE_SECONDS = 60


class PushTaskScheduler:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("PushTaskScheduler started (interval=%ds)", PUSH_SCHEDULER_INTERVAL)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            async with _suppress_cancel():
                await self._task
            self._task = None
        logger.info("PushTaskScheduler stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("PushTaskScheduler tick failed")
            await asyncio.sleep(PUSH_SCHEDULER_INTERVAL)

    async def _tick(self) -> None:
        now = datetime.now(UTC)

        claimed_cron = await self._claim_due_cron_tasks(now)
        for task in claimed_cron:
            await self._execute_task_safe(task, now)

        await self._claim_and_dispatch_events(now)

        # W6 A.5：运行期告警（心跳缺失/Job 积压/推送连败）。run_alert_checks 在
        # ALERTING_ENABLED 未置真时直接短路返回空，故开发/测试零副作用、生产才投递。
        from app.core.alerting import run_alert_checks

        await run_alert_checks(self._session_factory)

    async def _claim_due_cron_tasks(self, now: datetime) -> list[PushTask]:
        """领取到期任务：cron 到期 OR 重试到期（两类谓词并集，SKIP LOCKED 防多副本）。

        cron 到期的任务推进 next_run_at（解析失败转 paused）；仅重试到期的任务
        不动 next_run_at（cron 节奏与重试节奏正交），只推进 last_run_at。
        重试计数与 next_retry_at 的清理/推进在 _execute_task 的投递事务里完成。
        """
        async with self._session_factory() as db:
            result = await db.execute(
                select(PushTask)
                .where(
                    PushTask.status == "active",
                    or_(
                        (PushTask.trigger_type == "cron")
                        & PushTask.next_run_at.is_not(None)
                        & (PushTask.next_run_at <= now),
                        PushTask.next_retry_at.is_not(None) & (PushTask.next_retry_at <= now),
                    ),
                )
                .with_for_update(skip_locked=True)
            )
            tasks = list(result.scalars().all())

            for task in tasks:
                cron_due = (
                    task.trigger_type == "cron"
                    and task.next_run_at is not None
                    and task.next_run_at <= now
                )
                if cron_due:
                    next_run = parse_cron_next(task.cron_expr, now)
                    if next_run is None:
                        task.status = "paused"
                        task.last_run_at = now
                        logger.warning(
                            "Task %s cron 解析失败，已暂停: %s", task.id, task.cron_expr
                        )
                        continue
                    task.next_run_at = next_run
                task.last_run_at = now

            await db.commit()
            return tasks

    async def _claim_and_dispatch_events(self, now: datetime) -> int:
        async with self._session_factory() as db:
            events = await claim_pending_events(db)

        if not events:
            return 0

        for event in events:
            await self._dispatch_event(event, now)

        return len(events)

    async def _dispatch_event(self, event, now: datetime) -> None:
        async with self._session_factory() as db:
            result = await db.execute(
                select(PushTask).where(
                    PushTask.trigger_type == "event",
                    PushTask.trigger_event == event.event_type,
                    PushTask.status == "active",
                )
            )
            tasks = list(result.scalars().all())

        for task in tasks:
            await self._execute_task_safe(task, now, event_payload=_extract_payload(event))

    async def _execute_task_safe(
        self, task: PushTask, now: datetime, event_payload: dict | None = None
    ) -> None:
        try:
            await self._execute_task(task, now, event_payload)
        except Exception as exc:
            logger.exception("Task %s 执行异常: %s", task.id, exc)
            await self._write_failure_log(task, str(exc))

    async def _execute_task(
        self, task: PushTask, now: datetime, event_payload: dict | None = None
    ) -> None:
        async with self._session_factory() as db:
            ch = (
                await db.execute(select(BotChannel).where(BotChannel.id == task.bot_channel_id))
            ).scalar_one_or_none()

            if ch is None or ch.status != "active":
                logger.warning("Task %s: channel unavailable, skipping", task.id)
                return

            variables = dict(event_payload) if event_payload else {}
            content = render(task.content_template or "BotHot 推送通知", variables)

            push_msg = PushMessage(
                message=content,
                title=task.name,
                webhook_url=ch.webhook_url,
                # AES 密文 AAD 绑定 channel id；不可解时抛 RequestInvalidError，
                # 由 _execute_task_safe 捕获写 failed PushLog（fail-closed，绝不静默空密钥投递）
                secret=decrypt_channel_secret(ch.id, ch.secret_enc),
                # S2.1：投递前解密 extra_config（密文列，存量明文兼容读）
                extra_config=decrypt_extra_config(ch.id, ch.extra_config),
            )

            provider = make_push_provider(ch.channel_type)
            result = await provider.push(push_msg)

            # WB：重试簿记——重投/终态决策与 PushLog 同事务落库。
            # 任务行重新 SELECT（本 session 与领取 session 不同，领取返回的是
            # detached 对象），任务已删/暂停则只落日志不动任务。
            log_status = "success" if result.delivered else "failed"
            if not result.delivered and result.retryable:
                task_row = (
                    await db.execute(select(PushTask).where(PushTask.id == task.id))
                ).scalar_one_or_none()
                if task_row is not None and task_row.status == "active":
                    new_count = int(task_row.retry_count or 0) + 1
                    if new_count > MAX_PUSH_RETRIES:
                        log_status = "dead"
                        task_row.status = "failed"
                        task_row.next_retry_at = None
                        logger.warning(
                            "Task %s 重试 %d 次仍失败，转死信终态", task.id, task_row.retry_count
                        )
                    else:
                        backoff = RETRY_BACKOFF_BASE_SECONDS * (4 ** (new_count - 1))
                        task_row.retry_count = new_count
                        task_row.next_retry_at = now + timedelta(seconds=backoff)
                        logger.info(
                            "Task %s 第 %d 次投递失败（可重试），%ds 后重投",
                            task.id, new_count, backoff,
                        )
            elif result.delivered:
                task_row = (
                    await db.execute(select(PushTask).where(PushTask.id == task.id))
                ).scalar_one_or_none()
                if task_row is not None:
                    # 投递成功清零重试态（上次失败的退避计划作废）
                    task_row.retry_count = 0
                    task_row.next_retry_at = None

            # S1.1（R1.2）：web 渠道投递成功 → 通知落库（离线补投存储底座）。
            # savepoint 包裹：落库失败只回滚通知行，投递回执（PushLog/计数）不受影响。
            if ch.channel_type == "web" and result.delivered:
                await persist_web_notification(db, push_msg)

            # W6 A.2：投递结果计入 Prometheus（outcome ∈ success/failed/dead）。
            PUSH_DELIVERIES_TOTAL.labels(channel=ch.channel_type, outcome=log_status).inc()

            log = PushLog(
                bot_channel_id=ch.id,
                push_task_id=task.id,
                status=log_status,
                content_preview=content[:200],
                error_message=result.reason if not result.delivered else "",
                response_summary=result.response_data[:500],
            )
            db.add(log)
            ch.total_push_count += 1
            if result.delivered:
                ch.success_push_count += 1

            await db.commit()

    async def _write_failure_log(self, task: PushTask, error_msg: str) -> None:
        """任务级异常兜底日志（类方法——R2 门禁修复：曾因缩进事故嵌进
        persist_web_notification 体内，类丢失该方法，异常路径运行时必 AttributeError）。
        """
        try:
            async with self._session_factory() as db:
                ch = (
                    await db.execute(select(BotChannel).where(BotChannel.id == task.bot_channel_id))
                ).scalar_one_or_none()
                if ch is None:
                    return

                log = PushLog(
                    bot_channel_id=ch.id,
                    push_task_id=task.id,
                    status="failed",
                    content_preview="",
                    error_message=error_msg[:500],
                    response_summary="",
                )
                db.add(log)
                await db.commit()
        except Exception:
            logger.exception("Task %s 写失败日志异常", task.id)

async def persist_web_notification(db: AsyncSession, msg: PushMessage) -> None:
    """S1.1：web 渠道通知落库（notifications 表，R1.2 离线补投存储底座）。

    广播/定向判定与 web.py 频道选择**同源**（external_user_id 有无），两处永不漂移：
    - 定向：sub=external_user_id，is_broadcast=False；
    - 广播：sub=""，is_broadcast=True（历史查询按 sub==me OR is_broadcast 覆盖两类）。
    savepoint 语义：落库失败仅回滚本通知行并 warning（通知历史可容忍单条缺失），
    绝不影响同事务内的 PushLog/渠道计数（投递回执优先）。
    """
    try:
        async with db.begin_nested():
            db.add(
                Notification(
                    sub=msg.external_user_id or "",
                    is_broadcast=not msg.external_user_id,
                    channel_type="web",
                    title=msg.title or "BotHot 通知",
                    message=msg.message,
                    url=msg.url,
                    space_id=msg.space_id,
                    doc_id=msg.doc_id,
                )
            )
    except Exception:
        logger.warning("web 通知落库失败（不影响投递回执）: %s", msg.title)


def _extract_payload(event) -> dict:
    import json
    try:
        return json.loads(event.payload) if event.payload else {}
    except Exception:
        return {}


class _suppress_cancel:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return exc_type is asyncio.CancelledError


_scheduler_instance: PushTaskScheduler | None = None


async def start_push_scheduler(session_factory: async_sessionmaker[AsyncSession]) -> PushTaskScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = PushTaskScheduler(session_factory)
    await _scheduler_instance.start()
    return _scheduler_instance


async def stop_push_scheduler() -> None:
    global _scheduler_instance
    if _scheduler_instance is not None:
        await _scheduler_instance.stop()
        _scheduler_instance = None
