"""W2 Feed 生产者：FeedItem upsert + 事件发射桩 + 日报组装。

三类 Feed 条目（任务 2.4）：
- article：kb 入库 INDEXED 落点调 on_article_indexed 写入；
- hot_topic：聚簇落库同事务调 add_hot_topic_feed 写入；
- daily_report：日报组装 build_daily_report 末尾调 add_daily_report_feed 写入。

upsert 语义：依赖 bothot_entities.FeedItem 的 UniqueConstraint(item_type, ref_id)
（迁移 ab1004w2a）；冲突时覆盖 title/summary/source_name/category/url/score，
保留 is_pinned 与 created_at。

事件发射桩（任务 2.7）：import app.services.push_events.emit_event；W3 未交付该模块
时回落 no-op 桩（try/except ImportError），生产代码照常 import，W3 落地后自动联通。
禁止在此创建 push_events.py。

日报组装（任务 2.5b）：build_daily_report 为每个 topic 调 LLM 生成中文摘要，LLM 失败
降级为中心文章 content_markdown 首段截断 150 字——日报永不因 LLM 故障缺失。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bothot_entities import DailyReport, FeedItem, HotTopic
from app.models.entities import ContentAsset, Source
from app.services.llm_summary import summarize_topic

logger = logging.getLogger(__name__)

BUSINESS_TZ = ZoneInfo("Asia/Shanghai")

_SUMMARY_CONCURRENCY = 3

# 事件类型枚举固定（任务 2.7 契约）
EVENT_NEW_ARTICLE = "new_article"
EVENT_HOT_TOPIC_UPDATE = "hot_topic_update"
EVENT_DAILY_REPORT = "daily_report"

# LLM 可调用类型（供测试注入；默认走 llm_summary.summarize_topic）
LlmSummarizer = Callable[[str, str], Awaitable[str | None]]

# MERGE: 依赖 W3 push_events 模块，审查者验证联通。W3 未交付时 _PUSH_REAL 为 None，
# _emit_event 退化为 no-op 桩；W3 落地后 _PUSH_REAL 绑定真实 emit_event，自动联通。
# 用单一 _emit_event 签名包裹（而非 try/except 绑定同名函数），避免 mypy 条件分支
# 签名不一致误报。
_PUSH_REAL: Any = None
try:  # pragma: no cover - W3 落地后分支
    from app.services.push_events import emit_event as _PUSH_REAL  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - W3 未交付分支
    pass


async def _emit_event(session: AsyncSession, event_type: str, payload: dict[str, Any]) -> None:
    """事件发射口：W3 联通前 no-op，联通后委托真实 emit_event。"""
    if _PUSH_REAL is not None:
        await _PUSH_REAL(session, event_type, payload)


# ── upsert ────────────────────────────────────────────────────────────


async def _upsert_feed_item(
    session: AsyncSession,
    *,
    item_type: str,
    ref_id: str,
    title: str,
    summary: str = "",
    source_name: str = "",
    category: str = "",
    url: str = "",
    score: float = 0.0,
) -> None:
    """PostgreSQL upsert：冲突 (item_type, ref_id) 覆盖非主键列，保留 is_pinned/created_at。"""
    stmt = pg_insert(FeedItem).values(
        item_type=item_type,
        ref_id=ref_id,
        title=title,
        summary=summary,
        source_name=source_name,
        category=category,
        url=url,
        score=float(score),
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_feed_item_type_ref",
        set_={
            "title": stmt.excluded.title,
            "summary": stmt.excluded.summary,
            "source_name": stmt.excluded.source_name,
            "category": stmt.excluded.category,
            "url": stmt.excluded.url,
            "score": stmt.excluded.score,
        },
    )
    await session.execute(stmt)


# ── 事件发射 ──────────────────────────────────────────────────────────


async def emit_event(session: AsyncSession, event_type: str, payload: dict[str, Any]) -> None:
    """对外暴露的事件发射口（聚簇/日报/入库末尾调用）。W3 未交付时 no-op。"""
    try:
        await _emit_event(session, event_type, payload)
    except Exception:  # noqa: BLE001 事件发射不得阻断主事务
        logger.warning("emit_event(%s) 失败（已忽略）", event_type, exc_info=True)


# ── article 条目 ───────────────────────────────────────────────────────


async def on_article_indexed(session: AsyncSession, asset: ContentAsset, space_id: str = "") -> None:
    """kb 入库 INDEXED 落点调用：写 article FeedItem + 发 new_article 事件。

    source_name 经 Source join（按 asset.source_id 取 sources.name）。
    """
    source_name = ""
    src = await session.get(Source, asset.source_id)
    if src is not None:
        source_name = src.name or ""
    await _upsert_feed_item(
        session,
        item_type="article",
        ref_id=asset.id,
        title=asset.title,
        source_name=source_name,
        category=asset.category,
        url=asset.url,
        score=float(asset.quality_score or 0.0),
    )
    await emit_event(session, EVENT_NEW_ARTICLE, {"asset_id": asset.id, "space_id": space_id})


# ── hot_topic 条目 ─────────────────────────────────────────────────────


async def add_hot_topic_feed(session: AsyncSession, topic: HotTopic) -> None:
    """聚簇落库同事务调用：写 hot_topic FeedItem + 发 hot_topic_update 事件。"""
    await _upsert_feed_item(
        session,
        item_type="hot_topic",
        ref_id=topic.id,
        title=topic.title,
        summary=topic.summary,
        source_name="热点",
        category=topic.category,
        score=float(topic.hot_score or 0.0),
    )
    await emit_event(session, EVENT_HOT_TOPIC_UPDATE, {"topic_id": topic.id})


# ── daily_report 条目 ─────────────────────────────────────────────────


async def add_daily_report_feed(session: AsyncSession, report: DailyReport) -> None:
    """日报落库同事务调用：写 daily_report FeedItem + 发 daily_report 事件。"""
    await _upsert_feed_item(
        session,
        item_type="daily_report",
        ref_id=report.id,
        title=report.title,
        summary="",
        score=0.0,
    )
    await emit_event(session, EVENT_DAILY_REPORT, {"report_date": report.report_date})


# ── 日报组装（任务 2.5b）──────────────────────────────────────────────


def _fallback_summary(center_content: str, *, limit: int = 150) -> str:
    """降级摘要：中心文章正文首段截断。取首个空白/换行分段，再截 limit 字。"""
    if not center_content:
        return ""
    first_para = center_content.strip().split("\n", 1)[0].strip()
    return first_para[:limit]


async def _topic_summary(
    topic: HotTopic, center_content: str, llm: LlmSummarizer | None
) -> str:
    """单话题摘要：LLM 成功用 LLM；LLM 返回空/None/异常 走正文首段降级。

    降级语义在 docstring 与代码一致：LLM 故障永不缺失摘要（至少有首段截断）。
    llm=None → 用真实 summarize_topic（默认 OpenAI 兼容直连）。
    """
    summarizer = llm if llm is not None else summarize_topic
    try:
        summary = await summarizer(topic.title, center_content)
    except Exception:  # noqa: BLE001 LLM 不得抛穿
        logger.warning("topic=%s LLM 异常，走降级", topic.id, exc_info=True)
        summary = None
    if summary:
        return summary
    return _fallback_summary(center_content)


def assemble_report(report_date: str, topics: list[HotTopic], summaries: list[str]) -> str:
    """纯函数：把 topic+摘要列表组装成 Markdown 日报（供单测，无 DB/LLM 依赖）。"""
    lines = [f"# BotHot 热点日报 · {report_date}", ""]
    if not topics:
        lines.append("今日暂无热点事件。")
        return "\n".join(lines)
    for i, (t, s) in enumerate(zip(topics, summaries, strict=False), 1):
        lines.append(f"## {i}. {t.title}")
        lines.append("")
        lines.append(
            f"**热度**: {float(t.hot_score or 0.0):.1f} | "
            f"**来源数**: {t.source_count} | **文章数**: {t.article_count}"
        )
        lines.append("")
        if s:
            lines.append(s)
            lines.append("")
    return "\n".join(lines)


async def build_daily_report(
    session: AsyncSession,
    report_date: str,
    *,
    llm: LlmSummarizer | None = None,
    generated_by: str = "auto",
) -> DailyReport | None:
    """生成指定日期日报：取 TOP10 热点 → 逐个 LLM 摘要（失败降级）→ 落 DailyReport + Feed。

    幂等：同 report_date 已存在则返回既有报告，不重建（scheduler/手动重复触发安全）。
    事务边界由调用方持有；只 flush 不 commit。generated_by: auto（scheduler/worker）
    或 manual（手动端点），由调用方传入。
    """
    existing = (
        await session.execute(select(DailyReport).where(DailyReport.report_date == report_date))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    topics = (
        await session.execute(
            select(HotTopic)
            .where(HotTopic.topic_date == report_date)
            .order_by(HotTopic.hot_score.desc())
            .limit(10)
        )
    ).scalars().all()

    # 中心文章正文：日报摘要的素材 + LLM 失败时的降级源。
    # 审查缝合：DB 读取必须在 gather 之外串行完成——AsyncSession 不允许跨任务并发
    # 使用（并发 session.get 会撞连接 provisioning 竞态）；并发区只保留无 DB 的
    # LLM 调用（这才是可安全并发的部分）。
    center_contents: list[str] = []
    for t in topics:
        content = ""
        if t.center_asset_id:
            asset = await session.get(ContentAsset, t.center_asset_id)
            if asset is not None:
                content = asset.content_markdown or ""
        center_contents.append(content)

    sem = asyncio.Semaphore(_SUMMARY_CONCURRENCY)

    async def _summarize_one(t: HotTopic, center_content: str) -> str:
        async with sem:
            return await _topic_summary(t, center_content, llm)

    summaries = list(
        await asyncio.gather(
            *[_summarize_one(t, c) for t, c in zip(topics, center_contents, strict=False)]
        )
    )

    content_md = assemble_report(report_date, list(topics), summaries)
    title = f"BotHot 热点日报 · {report_date}"
    report = DailyReport(
        report_date=report_date,
        title=title,
        content_markdown=content_md,
        topic_count=len(topics),
        status="published",
        generated_by=generated_by,
    )
    session.add(report)
    await session.flush()  # 取 report.id
    await add_daily_report_feed(session, report)
    logger.info("daily_report: 日期=%s 话题=%d", report_date, len(topics))
    return report
