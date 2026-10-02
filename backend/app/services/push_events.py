"""事件 outbox 模式实现。

W2 在 kb 流水线/聚簇/日报事务里调用 emit_event 落库，
push_scheduler 轮询 claim_pending_events 消费。

payload 自足快照（WB，审查补完）：emit_event 落库前按 event_type 查库补齐模板
变量所需的业务值（doc_title/space_name/hot_topic/topic_count 等）——消费侧
push_template.render 零额外查询即可渲染。与业务同事务落库，快照与事件原子一致。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import RequestInvalidError
from app.models.bothot_entities import DailyReport, HotTopic, PushEvent
from app.models.entities import ContentAsset, KnowledgeSpace

logger = structlog.get_logger(__name__)

VALID_EVENT_TYPES = {"new_article", "hot_topic_update", "daily_report"}


async def _hydrate_payload(session: AsyncSession, event_type: str, payload: dict) -> dict:
    """按事件类型查库补齐模板变量快照；查不到置空串（不抛错，消费侧渲染空值）。

    all 调用点（feed_service）都在业务行 flush 之后触发本函数，session.get 命中
    同事务数据；identity map 命中时零额外查询。
    """
    hydrated = dict(payload)

    if event_type == "new_article":
        asset_id = str(hydrated.get("asset_id") or "")
        if asset_id:
            asset = await session.get(ContentAsset, asset_id)
            hydrated.setdefault("doc_title", asset.title if asset else "")
        space_id = str(hydrated.get("space_id") or "")
        if space_id:
            space = await session.get(KnowledgeSpace, space_id)
            hydrated.setdefault("space_name", space.name if space else "")
        hydrated.setdefault("doc_title", "")
        hydrated.setdefault("space_name", "")

    elif event_type == "hot_topic_update":
        topic_id = str(hydrated.get("topic_id") or "")
        topic = await session.get(HotTopic, topic_id) if topic_id else None
        hydrated["hot_topic"] = topic.title if topic else ""
        hydrated["topic_count"] = str(topic.article_count) if topic else ""

    elif event_type == "daily_report":
        if not hydrated.get("report_title"):
            report_date = str(hydrated.get("report_date") or "")
            row = (
                (
                    await session.execute(select(DailyReport.title).where(DailyReport.report_date == report_date))
                ).scalar_one_or_none()
                if report_date
                else None
            )
            hydrated["report_title"] = row or ""

    return hydrated


async def emit_event(session: AsyncSession, event_type: str, payload: dict) -> None:
    if event_type not in VALID_EVENT_TYPES:
        raise RequestInvalidError(f"非法事件类型: {event_type}（合法：{', '.join(sorted(VALID_EVENT_TYPES))}）")

    hydrated = await _hydrate_payload(session, event_type, payload)
    event = PushEvent(
        event_type=event_type,
        payload=json.dumps(hydrated, ensure_ascii=False),
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
