"""订阅仓储（T2.4）：`next_run_at` 驱动的到期认领原语。

与 JobRepository.claim_next_queued 同口径：`FOR UPDATE SKIP LOCKED` 保证并行的多调度器
实例取到**不同**订阅行（不重不漏）。差异在于本原语**不在此处 commit**——调度器需要在
同一条事务内完成「认领 → 增量入列 → 水位推进」，使整轮成为原子操作（崩溃即整体回滚，
下个 tick 重试），故锁由调用方持有至其 commit。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import SourceSubscription


class SourceSubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim_due(self, now: datetime) -> SourceSubscription | None:
        """取一件到期订阅并加行锁：`status=ACTIVE AND next_run_at <= now`。

        返回被锁定的订阅行（**不 commit**，锁随调用方事务释放）；无可取 → None。
        """
        result = await self._session.execute(
            select(SourceSubscription)
            .where(
                SourceSubscription.status == "ACTIVE",
                SourceSubscription.next_run_at.is_not(None),
                SourceSubscription.next_run_at <= now,
            )
            .order_by(SourceSubscription.next_run_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        return result.scalars().first()

    async def list_due(self, now: datetime, limit: int = 100) -> list[SourceSubscription]:
        """只读列出到期订阅（不含行锁；观测/预检用，不参与原子认领）。"""
        rows = await self._session.scalars(
            select(SourceSubscription)
            .where(
                SourceSubscription.status == "ACTIVE",
                SourceSubscription.next_run_at.is_not(None),
                SourceSubscription.next_run_at <= now,
            )
            .order_by(SourceSubscription.next_run_at)
            .limit(limit)
        )
        return list(rows)
