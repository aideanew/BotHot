"""BotHot 热点聚簇与日报 API（融合 AIHOT）。

- GET    /api/v1/hot/topics          热点列表（分页 + 分类过滤）
- GET    /api/v1/hot/topics/{id}     热点详情（含关联文章）
- POST   /api/v1/hot/topics/cluster  手动触发聚簇（admin）
- GET    /api/v1/hot/daily/reports   日报列表
- GET    /api/v1/hot/daily/reports/{date}  指定日期日报
- POST   /api/v1/hot/daily/generate  手动生成日报（admin）
- GET    /api/v1/hot/feed            Feed 流（信息流首页用）
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import get_current_sub, get_db, require_roles
from app.core.errors import RequestInvalidError, ResourceNotFoundError
from app.core.response import success
from app.models.bothot_entities import (
    DailyReport,
    FeedItem,
    HotTopic,
    HotTopicArticle,
)

router = APIRouter(
    prefix="/api/v1/hot",
    tags=["hot-topics"],
    # 全域登录门禁：热点/日报/Feed 含运营数据，无一可匿名读。router 级依赖会并入
    # 每个 route 的 dependant，故 main._uses_session 递归即能捕获并标注 security。
    dependencies=[Depends(get_current_sub)],
)


# ── 热点列表 ──────────────────────────────────────────────────────────

@router.get("/topics")
async def list_hot_topics(
    category: str = "",
    status: str = "",
    topic_date: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db = Depends(get_db),
):
    """查询热点列表（按热度排序）。"""
    q = select(HotTopic)
    if category:
        q = q.where(HotTopic.category == category)
    if status:
        q = q.where(HotTopic.status == status)
    if topic_date:
        q = q.where(HotTopic.topic_date == topic_date)
    else:
        # 默认取最近 7 天
        today = datetime.utcnow().strftime("%Y-%m-%d")
        week_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        q = q.where(HotTopic.topic_date >= week_ago, HotTopic.topic_date <= today)

    q = q.order_by(HotTopic.hot_score.desc())

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return success({
        "items": [
            {
                "id": t.id,
                "title": t.title,
                "summary": t.summary,
                "hot_score": t.hot_score,
                "source_count": t.source_count,
                "article_count": t.article_count,
                "status": t.status,
                "topic_date": t.topic_date,
                "category": t.category,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/topics/{topic_id}")
async def get_hot_topic(topic_id: str, db = Depends(get_db)):
    """查询单个热点详情（含关联文章）。"""
    t = (await db.execute(select(HotTopic).where(HotTopic.id == topic_id))).scalar_one_or_none()
    if t is None:
        raise ResourceNotFoundError(f"热点不存在: {topic_id}")

    # 查关联文章
    arts = (
        await db.execute(
            select(HotTopicArticle)
            .where(HotTopicArticle.hot_topic_id == topic_id)
            .order_by(HotTopicArticle.relevance_score.desc())
        )
    ).scalars().all()

    return success({
        "id": t.id,
        "title": t.title,
        "summary": t.summary,
        "hot_score": t.hot_score,
        "source_count": t.source_count,
        "article_count": t.article_count,
        "status": t.status,
        "topic_date": t.topic_date,
        "category": t.category,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "articles": [
            {
                "asset_id": a.asset_id,
                "relevance_score": a.relevance_score,
            }
            for a in arts
        ],
    })


# ── 手动触发聚簇 ──────────────────────────────────────────────────────

@router.post("/topics/cluster")
async def trigger_cluster(
    days: int = 1,
    db = Depends(get_db),
    _: str = Depends(require_roles("admin", "operator")),
):
    """手动触发热点聚簇。

    聚簇算法（融合 AIHOT）：
    1. 取最近 N 天的 content_assets
    2. 按标题相似度聚簇（Jaccard / TF-IDF）
    3. 计算热度：48h 内独立来源数加权，24h 减半
    4. 取 TOP N 生成 HotTopic 记录
    """
    # TODO: 实际聚簇逻辑需要 LLM + 向量相似度
    # 当前返回占位结果，真实实现需接入 content_assets 表
    today = datetime.utcnow().strftime("%Y-%m-%d")
    return success({
        "triggered": True,
        "topic_date": today,
        "days": days,
        "message": "聚簇任务已触发（实际聚簇逻辑需接入 LLM + 向量相似度，当前为占位响应）",
    })


# ── 日报 ──────────────────────────────────────────────────────────────

@router.get("/daily/reports")
async def list_daily_reports(
    status: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db = Depends(get_db),
):
    """查询日报列表。"""
    q = select(DailyReport)
    if status:
        q = q.where(DailyReport.status == status)
    q = q.order_by(DailyReport.report_date.desc())

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return success({
        "items": [
            {
                "id": r.id,
                "report_date": r.report_date,
                "title": r.title,
                "topic_count": r.topic_count,
                "status": r.status,
                "generated_by": r.generated_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/daily/reports/{report_date}")
async def get_daily_report(report_date: str, db = Depends(get_db)):
    """查询指定日期的日报详情。"""
    r = (
        await db.execute(select(DailyReport).where(DailyReport.report_date == report_date))
    ).scalar_one_or_none()
    if r is None:
        raise ResourceNotFoundError(f"日报不存在: {report_date}")

    return success({
        "id": r.id,
        "report_date": r.report_date,
        "title": r.title,
        "content_markdown": r.content_markdown,
        "topic_count": r.topic_count,
        "status": r.status,
        "generated_by": r.generated_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    })


@router.post("/daily/generate")
async def generate_daily_report(
    report_date: str = "",
    db = Depends(get_db),
    _: str = Depends(require_roles("admin", "operator")),
):
    """手动生成日报。

    日报生成逻辑（融合 AIHOT）：
    1. 取指定日期的 TOP 10 热点
    2. 用 LLM 生成中文标题和摘要
    3. 组装 Markdown 日报
    4. 落库 DailyReport
    """
    if not report_date:
        report_date = datetime.utcnow().strftime("%Y-%m-%d")

    # 检查是否已存在
    existing = (
        await db.execute(select(DailyReport).where(DailyReport.report_date == report_date))
    ).scalar_one_or_none()
    if existing:
        raise RequestInvalidError(f"{report_date} 的日报已存在（id={existing.id}）")

    # 取当日热点
    topics = (
        await db.execute(
            select(HotTopic)
            .where(HotTopic.topic_date == report_date)
            .order_by(HotTopic.hot_score.desc())
            .limit(10)
        )
    ).scalars().all()

    # 生成 Markdown 日报
    md_lines = [f"# BotHot 热点日报 · {report_date}", ""]
    if not topics:
        md_lines.append("今日暂无热点事件。")
    else:
        for i, t in enumerate(topics, 1):
            md_lines.append(f"## {i}. {t.title}")
            md_lines.append("")
            md_lines.append(
                f"**热度**: {t.hot_score:.1f} | **来源数**: {t.source_count} | **文章数**: {t.article_count}"
            )
            md_lines.append("")
            if t.summary:
                md_lines.append(t.summary)
                md_lines.append("")

    content = "\n".join(md_lines)
    title = f"BotHot 热点日报 · {report_date}"

    report = DailyReport(
        report_date=report_date,
        title=title,
        content_markdown=content,
        topic_count=len(topics),
        status="published",
        generated_by="manual",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    return success({
        "id": report.id,
        "report_date": report.report_date,
        "title": report.title,
        "topic_count": report.topic_count,
        "status": report.status,
    })


# ── Feed 流 ───────────────────────────────────────────────────────────

@router.get("/feed")
async def get_feed(
    item_type: str = "",
    category: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db = Depends(get_db),
):
    """查询 Feed 流（信息流首页用）。

    排序：置顶优先 → 热度分数 → 创建时间。
    """
    q = select(FeedItem)
    if item_type:
        q = q.where(FeedItem.item_type == item_type)
    if category:
        q = q.where(FeedItem.category == category)

    # 置顶优先，然后按 score 降序，最后按 created_at 降序
    q = q.order_by(
        FeedItem.is_pinned.desc(),
        FeedItem.score.desc(),
        FeedItem.created_at.desc(),
    )

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return success({
        "items": [
            {
                "id": f.id,
                "item_type": f.item_type,
                "ref_id": f.ref_id,
                "title": f.title,
                "summary": f.summary,
                "source_name": f.source_name,
                "score": f.score,
                "category": f.category,
                "url": f.url,
                "is_pinned": f.is_pinned,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    })
