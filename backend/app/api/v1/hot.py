"""BotHot 热点聚簇与日报 API（融合 AIHOT）。

- GET    /api/v1/hot/topics          热点列表（分页 + 分类过滤）
- GET    /api/v1/hot/topics/{id}     热点详情（含关联文章）
- POST   /api/v1/hot/topics/cluster  手动触发聚簇（admin）——入队 Job type=hot_cluster
- GET    /api/v1/hot/daily/reports   日报列表
- GET    /api/v1/hot/daily/reports/{date}  指定日期日报
- POST   /api/v1/hot/daily/generate  手动生成日报（admin）
- GET    /api/v1/hot/feed            Feed 流（信息流首页用）

时区口径（任务 2.6）：热点业务日界 = Asia/Shanghai，如改口径只动 BUSINESS_TZ。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
from app.models.entities import User
from app.repositories.job import JobRepository
from app.services.feed_service import build_daily_report
from app.services.jobs import JobService

# 热点业务日界 = Asia/Shanghai；如改口径只动此常量。
BUSINESS_TZ = ZoneInfo("Asia/Shanghai")

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
        # 默认取最近 7 天（业务日界 = Asia/Shanghai）
        today = datetime.now(BUSINESS_TZ).strftime("%Y-%m-%d")
        week_ago = (datetime.now(BUSINESS_TZ) - timedelta(days=7)).strftime("%Y-%m-%d")
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
    user: User = Depends(require_roles("admin", "operator")),
):
    """手动触发热点聚簇：入队 Job type=hot_cluster，立即返回 queued 回执。

    幂等（任务 2.5c）：同日已有未完成（QUEUED/RUNNING）的 hot_cluster job 且 days
    相同时不重复入队，返回既有 job；已终结的可重跑（聚簇落库本身整日 wipe 重建）。
    实际聚簇由 job_worker 消费 hot_cluster Job 执行（services/job_worker.py 注册分支）。
    """
    today = datetime.now(BUSINESS_TZ).strftime("%Y-%m-%d")
    repo = JobRepository(db)
    # 幂等预检：同日未完成的 hot_cluster job 不重复入队
    queued = await repo.list_by_user(None, status="QUEUED", job_type="hot_cluster", limit=50)
    running = await repo.list_by_user(None, status="RUNNING", job_type="hot_cluster", limit=50)
    for j in [*queued, *running]:
        try:
            payload = json.loads(j.payload or "{}")
        except ValueError:
            payload = {}
        if str(payload.get("date", "")) == today and int(payload.get("days", 0)) == days:
            return success({
                "queued": False,
                "job_id": j.id,
                "topic_date": today,
                "days": days,
                "message": "同日聚簇任务已在执行中，未重复入队",
            })

    # idempotency_key 含短随机：已终结 job 不阻塞重跑（同日新触发建新 Job）
    from uuid import uuid4

    job, _created = await JobService(repo, db).submit(
        job_type="hot_cluster",
        user_id=user.id,
        idempotency_key=f"hot_cluster:{today}:{days}:{uuid4().hex[:8]}",
        payload_json=json.dumps({"date": today, "days": days}),
    )
    return success({
        "queued": True,
        "job_id": job.id,
        "topic_date": today,
        "days": days,
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
    _: User = Depends(require_roles("admin", "operator")),
):
    """手动生成日报：取当日 TOP10 热点 → LLM 摘要（失败降级正文首段）→ 落库 DailyReport。

    日报组装委托 services/feed_service.build_daily_report（job_worker 的 daily_report
    Job 也复用同一函数，避免 services→api 反向依赖）。LLM 失败时降级为中心文章正文
    首段截断 150 字——日报永不因 LLM 故障缺失（降级语义见 feed_service._topic_summary）。
    """
    if not report_date:
        report_date = datetime.now(BUSINESS_TZ).strftime("%Y-%m-%d")

    # 手动触发对已存在日报报 400（与历史 UX 一致）；scheduler 路径走 build_daily_report
    # 的幂等返回（已存在则返回既有，不报错）。
    existing = (
        await db.execute(select(DailyReport).where(DailyReport.report_date == report_date))
    ).scalar_one_or_none()
    if existing:
        raise RequestInvalidError(f"{report_date} 的日报已存在（id={existing.id}）")

    report = await build_daily_report(db, report_date, generated_by="manual")
    if report is None:
        raise RequestInvalidError(f"{report_date} 日报生成失败")
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
