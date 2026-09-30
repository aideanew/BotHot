"""BotHot 推送任务调度器（W3 并发安全重构）。

架构取舍（at-most-once 语义）：
- 短锁领取：FOR UPDATE SKIP LOCKED 选中 due 任务 → 同一短事务内推进
  next_run_at 与 last_run_at → commit 释放锁 → 事务外逐任务投递。
- 崩溃至多丢一轮投递：若进程在 commit 后、投递前崩溃，该轮投递丢失，
  下轮 cron 周期重新触发。这是 cron 调度的 at-most-once 语义，可接受。
- 事件 outbox 同为 at-most-once：claim_pending_events 在投递前标记 consumed_at，
  claim 后投递前崩溃则该事件丢失（换取绝不重复投递；如需 at-least-once 改为
  投递成功后再标记，代价是可能重复推送）。
- 单任务隔离：try/except 包裹，单任务异常不影响其他任务。
- 事件 outbox：claim_pending_events 轮询消费，匹配 event 类型任务投递。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.secret_crypto import decrypt_channel_secret
from app.models.bothot_entities import BotChannel, PushLog, PushTask
from app.providers.push import PushMessage, make_push_provider
from app.services.cron_expr import parse_cron_next
from app.services.push_events import claim_pending_events
from app.services.push_template import render

logger = logging.getLogger(__name__)

PUSH_SCHEDULER_INTERVAL = 60


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

    async def _claim_due_cron_tasks(self, now: datetime) -> list[PushTask]:
        async with self._session_factory() as db:
            result = await db.execute(
                select(PushTask)
                .where(
                    PushTask.trigger_type == "cron",
                    PushTask.status == "active",
                    PushTask.next_run_at.is_not(None),
                    PushTask.next_run_at <= now,
                )
                .with_for_update(skip_locked=True)
            )
            tasks = list(result.scalars().all())

            for task in tasks:
                next_run = parse_cron_next(task.cron_expr, now)
                if next_run is None:
                    task.status = "paused"
                    task.last_run_at = now
                    logger.warning(
                        "Task %s cron 解析失败，已暂停: %s", task.id, task.cron_expr
                    )
                else:
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
                extra_config=ch.extra_config,
            )

            provider = make_push_provider(ch.channel_type)
            result = await provider.push(push_msg)

            log = PushLog(
                bot_channel_id=ch.id,
                push_task_id=task.id,
                status="success" if result.delivered else "failed",
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
