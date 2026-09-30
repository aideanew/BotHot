"""W2 热度评分与状态机：48h 窗口独立来源去重加权 + rising→hot→cooling→archived。

需求口径（product-requirements.md:64）："48h 内独立来源数加权，24h 减半"。

分数定义（任务 2.3a）：
    score = Σ_{来源 s ∈ 48h 窗口} 2^(-age_hours(s)/24)
- age_hours(s)：来源 s 在该话题内**最新一篇**文章距今小时数（同来源多篇取最年轻）；
- 24h 前的来源贡献 2^(-1)=0.5（"24h 减半"）；48h 外不计；
- 跨来源去重：同来源多篇只计一次（取最年轻那篇的 age）；
- source_count：48h 窗口内独立来源数；article_count：话题文章总数。

状态机（任务 2.3b，阈值为模块常量，可调）：
- rising→hot：score ≥ HOT_SCORE_RISING_TO_HOT（默认 10）；
- hot→cooling：topic_age > COOLING_AGE_HOURS（24h）且当前分较上次回填下降；
- cooling→archived：topic_age > ARCHIVE_AGE_HOURS（48h）；
- archived 终态。cooling 不回 hot（v0 简化：降温后不再升回，避免抖动）。
topic_age = 距话题内**最早一篇**文章的小时数。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import case, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bothot_entities import FeedItem, HotTopic, HotTopicArticle
from app.models.entities import ContentAsset

logger = logging.getLogger(__name__)

BUSINESS_TZ = ZoneInfo("Asia/Shanghai")

HALF_LIFE_HOURS = 24.0  # 半衰期：每 24h 权重减半
WINDOW_HOURS = 48.0  # 48h 外不计

# 状态机阈值（可调）
HOT_SCORE_RISING_TO_HOT = 10.0  # rising → hot
COOLING_AGE_HOURS = 24.0  # hot → cooling 需话题年龄 > 24h 且分降
ARCHIVE_AGE_HOURS = 48.0  # cooling → archived 需话题年龄 > 48h


@dataclass(frozen=True)
class _ArticleTime:
    source_id: str
    published_at: datetime | None
    created_at: datetime


def compute_score(
    articles: list[_ArticleTime], *, now: datetime
) -> tuple[float, int, int]:
    """返回 (hot_score, source_count_48h, article_count_total)。"""
    # 同来源取最年轻（最小 age）；age 用 published_at，缺失回落 created_at
    freshest_age: dict[str, float] = {}
    for a in articles:
        moment = a.published_at if a.published_at is not None else a.created_at
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=BUSINESS_TZ)
        age_h = (now - moment).total_seconds() / 3600.0
        if age_h < 0:
            age_h = 0.0  # 未来时刻（时钟偏移）按 0 计
        if age_h > WINDOW_HOURS:
            continue  # 48h 外不计
        cur = freshest_age.get(a.source_id)
        if cur is None or age_h < cur:
            freshest_age[a.source_id] = age_h
    score = sum(2.0 ** (-age / HALF_LIFE_HOURS) for age in freshest_age.values())
    return score, len(freshest_age), len(articles)


def next_status(
    current: str, *, score: float, prev_score: float, topic_age_hours: float
) -> str:
    """状态机迁移。current 已为 archived 时不动。

    语义（审查缝合修正）：未达 hot 阈值的话题不允许"永困 rising"——
    过了黄金期（24h）且分数从未/不再够 hot 线，就转入 cooling；
    否则话题会顶着 rising 标签一直存活到 48h 归档，状态标签失真。
    """
    if current == "archived":
        return "archived"
    if topic_age_hours > ARCHIVE_AGE_HOURS and current in ("rising", "hot", "cooling"):
        return "archived"
    if current == "rising" and score >= HOT_SCORE_RISING_TO_HOT:
        return "hot"
    if topic_age_hours > COOLING_AGE_HOURS and current in ("rising", "hot"):
        # hot：分数较上次回落即降温（保持 W2 原语义，分未降仍算热度持续）；
        # rising：从未达 hot 线且已过黄金期，转入 cooling（修复"永困 rising"）
        if current == "hot" and score < prev_score:
            return "cooling"
        if current == "rising" and score < HOT_SCORE_RISING_TO_HOT:
            return "cooling"
    return current


async def run_scoring(session: AsyncSession, *, now: datetime | None = None) -> int:
    """回填所有非 archived 话题的 hot_score/source_count/article_count/status。

    事务边界由调用方持有；只 flush 不 commit。返回更新条数。
    """
    moment = now or datetime.now(BUSINESS_TZ)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=BUSINESS_TZ)

    topics = (
        await session.execute(select(HotTopic).where(HotTopic.status != "archived"))
    ).scalars().all()
    updated = 0
    for t in topics:
        rows = (
            await session.execute(
                select(ContentAsset.source_id, ContentAsset.published_at, ContentAsset.created_at)
                .join(HotTopicArticle, HotTopicArticle.asset_id == ContentAsset.id)
                .where(HotTopicArticle.hot_topic_id == t.id)
            )
        ).all()
        articles = [
            _ArticleTime(
                source_id=str(r[0]),
                published_at=r[1],
                created_at=r[2] if r[2] is not None else moment,
            )
            for r in rows
        ]
        score, src_count, art_count = compute_score(articles, now=moment)
        # 话题年龄 = 距最早一篇（用 published_at，缺失回落 created_at）
        moments = [
            (a.published_at if a.published_at is not None else a.created_at) for a in articles
        ]
        for i, m in enumerate(moments):
            if m.tzinfo is None:
                moments[i] = m.replace(tzinfo=BUSINESS_TZ)
        topic_age_hours = (moment - min(moments)).total_seconds() / 3600.0 if moments else 0.0
        prev = float(t.hot_score or 0.0)
        new_status = next_status(
            t.status, score=score, prev_score=prev, topic_age_hours=topic_age_hours
        )
        t.hot_score = float(score)
        t.source_count = int(src_count)
        t.article_count = int(art_count)
        if new_status != t.status:
            t.status = new_status
        updated += 1

    # Feed 分数同步：单条批量 UPDATE（C.2）——原逐话题 N 次 UPDATE 改为 1 条
    # CASE ... WHEN ref_id THEN score 语句，WHERE item_type='hot_topic' AND ref_id IN (...)。
    # 各话题 score 不同，故用 simple-CASE 按 ref_id 分发值；SQL 往返由 N 降 1。
    if topics:
        score_map = {t.id: float(t.hot_score or 0.0) for t in topics}
        await session.execute(
            update(FeedItem)
            .where(FeedItem.item_type == "hot_topic", FeedItem.ref_id.in_(score_map))
            .values(score=case(score_map, value=FeedItem.ref_id))
        )

    logger.info("hot_scorer: 回填 %d 个话题 + Feed 分数同步（批量 1 条 UPDATE）", updated)
    return updated
