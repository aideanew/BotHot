"""事件 outbox 模式实现。

W2 在 kb 流水线/聚簇/日报事务里调用 emit_event 落库，
push_scheduler 轮询 claim_pending_events 消费。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import RequestInvalidError
from app.models.bothot_entities import PushEvent

logger = logging.getLogger(__name__)

VALID_EVENT_TYPES = {"new_article", "hot_topic_update", "daily_report"}


async def emit_event(session: AsyncSession, event_type: str, payload: dict) -> None:
    if event_type not in VALID_EVENT_TYPES:
        raise RequestInvalidError(
            f"非法事件类型: {event_type}（合法：{', '.join(sorted(VALID_EVENT_TYPES))}）"
        )

    event = PushEvent(
        event_type=event_type,
        payload=json.dumps(payload, ensure_ascii=False),
    )
    session.add(event)


async def claim_pending_events(session: AsyncSession, limit: int = 100) -> list[PushEvent]:
    result = await session.execute(
        select(PushEvent)
        .where(PushEvent.consumed_at.is_(None))
        .order_by(PushEvent.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    events = list(result.scalars().all())

    for event in events:
        event.consumed_at = datetime.now(UTC)

    await session.commit()
    return events
