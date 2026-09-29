"""BotHot 推送任务调度器。

功能：
- 定时扫描 push_tasks 表，找出 next_run_at <= now 的 active 任务
- 执行推送（调用对应渠道的 Provider）
- 更新 next_run_at（基于 cron_expr 计算下次执行时间）
- 记录 PushLog

独立于订阅同步调度器（scheduler.py），两者各跑各的 loop。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.bothot_entities import BotChannel, PushLog, PushTask
from app.providers.push import PushMessage, make_push_provider

logger = logging.getLogger(__name__)

# 调度间隔（秒）：默认 60s 扫一次
PUSH_SCHEDULER_INTERVAL = 60


def _parse_cron_next(cron_expr: str, now: datetime) -> datetime | None:
    """简版 cron 解析：仅支持 "HH:MM"（每天定时）和 "*/N"（每 N 小时）格式。

    完整 cron 解析需要 croniter 库；当前实现覆盖最常见的定时推送场景。
    """
    expr = cron_expr.strip()
    if not expr:
        return None

    # 格式1：HH:MM（如 "10:00"）
    if ":" in expr and "/" not in expr:
        try:
            hh, mm = expr.split(":")
            hh, mm = int(hh), int(mm)
            next_run = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run
        except (ValueError, IndexError):
            return None

    # 格式2：*/N（每 N 小时）
    if expr.startswith("*/"):
        try:
            n = int(expr[2:])
            if n <= 0:
                return None
            return now + timedelta(hours=n)
        except ValueError:
            return None

    # 格式3：纯数字 N（每 N 分钟）
    if expr.isdigit():
        n = int(expr)
        if n <= 0:
            return None
        return now + timedelta(minutes=n)

    return None


class PushTaskScheduler:
    """推送任务调度器：后台 loop 扫描到期任务并执行。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """启动调度器后台循环。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("PushTaskScheduler started (interval=%ds)", PUSH_SCHEDULER_INTERVAL)

    async def stop(self) -> None:
        """停止调度器。"""
        self._running = False
        if self._task:
            self._task.cancel()
            with _suppress_cancel():
                await self._task
            self._task = None
        logger.info("PushTaskScheduler stopped")

    async def _loop(self) -> None:
        """主循环：每 PUSH_SCHEDULER_INTERVAL 秒扫描一次。"""
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("PushTaskScheduler tick failed")
            await asyncio.sleep(PUSH_SCHEDULER_INTERVAL)

    async def _tick(self) -> None:
        """单轮扫描：找出到期任务并执行。"""
        now = datetime.now(timezone.utc)

        async with self._session_factory() as db:
            # 查找到期的 cron 任务
            result = await db.execute(
                select(PushTask).where(
                    PushTask.trigger_type == "cron",
                    PushTask.status == "active",
                    PushTask.next_run_at.is_not(None),
                    PushTask.next_run_at <= now,
                )
            )
            due_tasks = result.scalars().all()

            if not due_tasks:
                return

            logger.info("PushTaskScheduler: %d tasks due", len(due_tasks))

            for task in due_tasks:
                await self._execute_task(db, task, now)

            await db.commit()

    async def _execute_task(self, db: AsyncSession, task: PushTask, now: datetime) -> None:
        """执行单个推送任务。"""
        # 查渠道
        ch = (
            await db.execute(select(BotChannel).where(BotChannel.id == task.bot_channel_id))
        ).scalar_one_or_none()

        if ch is None or ch.status != "active":
            logger.warning("Task %s: channel unavailable, skipping", task.id)
            # 仍然推进 next_run_at，避免反复触发
            task.next_run_at = _parse_cron_next(task.cron_expr, now)
            task.last_run_at = now
            return

        # 构建推送消息
        content = task.content_template or "BotHot 定时推送通知"

        # 简单变量替换
        content = content.replace("{date}", now.strftime("%Y-%m-%d"))
        content = content.replace("{time}", now.strftime("%H:%M"))

        push_msg = PushMessage(
            message=content,
            title=task.name,
            webhook_url=ch.webhook_url,
            secret=_decrypt_secret(ch.secret_enc),
            extra_config=ch.extra_config,
        )

        # 调用 Provider
        provider = make_push_provider(ch.channel_type)
        result = await provider.push(push_msg)

        # 记录日志
        log = PushLog(
            bot_channel_id=ch.id,
            push_task_id=task.id,
            status="success" if result.delivered else "failed",
            content_preview=content[:200],
            error_message=result.reason if not result.delivered else "",
            response_summary=result.response_data[:500],
        )
        db.add(log)

        # 更新统计
        ch.total_push_count += 1
        if result.delivered:
            ch.success_push_count += 1

        # 推进 next_run_at
        task.next_run_at = _parse_cron_next(task.cron_expr, now)
        task.last_run_at = now

        logger.info(
            "Task %s executed: delivered=%s reason=%s",
            task.id, result.delivered, result.reason,
        )


def _decrypt_secret(enc: str) -> str:
    """解密 secret（与 bots.py 保持一致）。"""
    import base64
    if not enc:
        return ""
    try:
        return base64.b64decode(enc.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""


class _suppress_cancel:
    """contextlib.suppress(asyncio.CancelledError) 的轻量替代。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return exc_type is asyncio.CancelledError


# 全局实例（懒初始化）
_scheduler_instance: PushTaskScheduler | None = None


async def start_push_scheduler(session_factory: async_sessionmaker[AsyncSession]) -> PushTaskScheduler:
    """启动全局推送调度器。"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = PushTaskScheduler(session_factory)
    await _scheduler_instance.start()
    return _scheduler_instance


async def stop_push_scheduler() -> None:
    """停止全局推送调度器。"""
    global _scheduler_instance
    if _scheduler_instance is not None:
        await _scheduler_instance.stop()
        _scheduler_instance = None
