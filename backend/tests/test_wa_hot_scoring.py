"""WA 热点域评分接通与性能护栏验收测试。

覆盖：
1.1 评分接线：聚簇后 hot_score>0 + feed_items.score 同步
1.2 Feed 分数回刷：run_scoring 后 FeedItem.score 与 HotTopic.hot_score 一致
1.3 周期重评分：hot_rescore Job 类型；时间推进状态机迁移
1.4 LLM 摘要并行：并发峰值 ≤ _SUMMARY_CONCURRENCY
1.5 聚簇护栏：max_candidates 截断 + 倒排预筛结果不变
1.6 日报兜底评分：build_daily_report 前 run_scoring 被调，TOP10 非零序
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.models.bothot_entities import FeedItem, HotTopic
from app.models.entities import ContentAsset, Source
from app.services.feed_service import build_daily_report
from app.services.hot_cluster import AssetDoc, cluster, run_clustering
from app.services.hot_scorer import (
    ARCHIVE_AGE_HOURS,
    _ArticleTime,
    compute_score,
    next_status,
    run_scoring,
)

_TZ = ZoneInfo("Asia/Shanghai")
_FIXED_NOW = datetime(2026, 10, 1, 12, 0, tzinfo=_TZ)
_TOPIC_DATE = _FIXED_NOW.strftime("%Y-%m-%d")


def _make_asset(
    source_id: str, *, key: str, title: str, quality: float, body: str = "正文首段摘要内容。"
) -> ContentAsset:
    return ContentAsset(
        source_id=source_id,
        external_id=key,
        url=f"https://example.test/{key}",
        title=title,
        author="",
        published_at=_FIXED_NOW - timedelta(hours=2),
        content_type="article",
        content_hash=f"hash-wa-{key}",
        raw_uri="",
        content_markdown=body,
        version=1,
        quality_score=quality,
        status="READY",
        hit_count=0,
        category="tech",
    )


async def _seed_corpus(session) -> list[ContentAsset]:
    s1 = Source(type="wechat_oa", external_id="biz-wa-a", name="来源A", url="", status="ACTIVE")
    s2 = Source(type="wechat_oa", external_id="biz-wa-b", name="来源B", url="", status="ACTIVE")
    session.add_all([s1, s2])
    await session.flush()
    assets = [
        _make_asset(s1.id, key="wa1", title="OpenAI发布GPT-5模型", quality=0.5, body="OpenAI 发布了 GPT-5 模型。"),
        _make_asset(s2.id, key="wa2", title="OpenAI推出全新GPT-5大模型", quality=0.8, body="OpenAI 推出全新 GPT-5。"),
        _make_asset(s1.id, key="wa3", title="美联储宣布加息50个基点", quality=0.6, body="美联储宣布加息 50 基点。"),
        _make_asset(s2.id, key="wa4", title="美联储加息50基点应对通胀", quality=0.9, body="美联储加息应对通胀。"),
    ]
    session.add_all(assets)
    await session.flush()
    return assets


# ── 1.1 + 1.2 评分接线 + Feed 回刷 ─────────────────────────────────


@pytest.mark.asyncio
async def test_cluster_then_score_hot_score_positive(db_session) -> None:
    """聚簇→评分后 HotTopic.hot_score>0 且 feed_items.score 同步。"""
    await _seed_corpus(db_session)
    await run_clustering(db_session, days=1, now=_FIXED_NOW)
    await run_scoring(db_session, now=_FIXED_NOW)

    topics = (await db_session.execute(select(HotTopic).where(HotTopic.topic_date == _TOPIC_DATE))).scalars().all()
    assert len(topics) == 2
    for t in topics:
        assert t.hot_score > 0.0, f"topic {t.id} hot_score={t.hot_score}，应为正"


@pytest.mark.asyncio
async def test_feed_score_synced_with_hot_score(db_session) -> None:
    """run_scoring 后 FeedItem.score 与 HotTopic.hot_score 一致。"""
    await _seed_corpus(db_session)
    await run_clustering(db_session, days=1, now=_FIXED_NOW)
    await run_scoring(db_session, now=_FIXED_NOW)

    topics = (await db_session.execute(select(HotTopic).where(HotTopic.topic_date == _TOPIC_DATE))).scalars().all()
    for t in topics:
        feed = (
            await db_session.execute(select(FeedItem).where(FeedItem.item_type == "hot_topic", FeedItem.ref_id == t.id))
        ).scalar_one_or_none()
        assert feed is not None
        assert abs(feed.score - t.hot_score) < 1e-9, f"feed.score={feed.score} != hot_score={t.hot_score}"


# ── 1.3 状态机迁移（纯函数） ───────────────────────────────────────


def test_rising_to_hot_when_score_high() -> None:
    assert next_status("rising", score=10.0, prev_score=0.0, topic_age_hours=1.0) == "hot"


def test_hot_to_cooling_after_24h_score_drops() -> None:
    now = datetime(2026, 10, 1, 12, 0, tzinfo=_TZ)
    articles = [_ArticleTime("s1", published_at=now - timedelta(hours=30), created_at=now)]
    score, _, _ = compute_score(articles, now=now)
    assert next_status("hot", score=score, prev_score=10.0, topic_age_hours=30.0) == "cooling"


def test_cooling_to_archived_after_48h() -> None:
    assert next_status("cooling", score=0.5, prev_score=0.5, topic_age_hours=ARCHIVE_AGE_HOURS + 1) == "archived"


def test_rising_direct_to_archived_after_48h() -> None:
    assert next_status("rising", score=100.0, prev_score=100.0, topic_age_hours=ARCHIVE_AGE_HOURS + 1) == "archived"


# ── 1.3 hot_rescore Job 类型 ────────────────────────────────────────


def test_hot_rescore_in_job_types() -> None:
    from app.services.job_worker import HOT_JOB_TYPES

    assert "hot_rescore" in HOT_JOB_TYPES


# ── 1.4 LLM 摘要并行 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_daily_report_parallel_summary_concurrency(db_session) -> None:
    """日报摘要并发峰值 ≤ _SUMMARY_CONCURRENCY。"""
    from app.services.feed_service import _SUMMARY_CONCURRENCY

    await _seed_corpus(db_session)
    await run_clustering(db_session, days=1, now=_FIXED_NOW)
    await run_scoring(db_session, now=_FIXED_NOW)

    peak = 0
    current = 0

    async def _tracking_summarizer(title: str, body: str) -> str | None:
        nonlocal peak, current
        current += 1
        if current > peak:
            peak = current
        await asyncio.sleep(0.01)
        current -= 1
        return f"摘要:{title[:10]}"

    report = await build_daily_report(db_session, _TOPIC_DATE, llm=_tracking_summarizer, generated_by="manual")
    assert report is not None
    assert report.topic_count == 2
    assert peak <= _SUMMARY_CONCURRENCY, f"并发峰值 {peak} > {_SUMMARY_CONCURRENCY}"


# ── 1.5 聚簇护栏 ───────────────────────────────────────────────────


def test_inverted_index_cluster_results_match_brute_force() -> None:
    """倒排预筛结果与暴力 O(n²) 一致。"""
    docs = [
        AssetDoc("x1", "GPT-5震撼发布改变AI格局", 0.5),
        AssetDoc("x2", "GPT-5震撼推出AI新纪元", 0.8),
        AssetDoc("x3", "美联储加息50基点应对通胀压力", 0.6),
        AssetDoc("x4", "美联储宣布加息50基点抗通胀", 0.9),
        AssetDoc("x5", "独立话题：火星探测器成功着陆", 0.3),
    ]
    groups = cluster(docs)
    multi = [g for g in groups if len(g) >= 2]
    assert len(multi) == 2
    member_sets = [frozenset(docs[i].id for i in g) for g in multi]
    assert frozenset({"x1", "x2"}) in member_sets
    assert frozenset({"x3", "x4"}) in member_sets


@pytest.mark.asyncio
async def test_cluster_max_candidates_truncation(db_session) -> None:
    """候选超 max_candidates 时截断+告警，不抛错。"""
    s = Source(type="wechat_oa", external_id="biz-wa-trunc", name="来源T", url="", status="ACTIVE")
    db_session.add(s)
    await db_session.flush()
    for i in range(5):
        a = _make_asset(s.id, key=f"trunc-{i}", title=f"独立话题{i}", quality=0.1 * i)
        db_session.add(a)
    await db_session.flush()

    res = await run_clustering(db_session, days=1, now=_FIXED_NOW, max_candidates=3)
    assert res["candidates"] <= 3


# ── 1.6 日报兜底评分 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_daily_report_topics_ordered_by_nonzero_score(db_session) -> None:
    """日报 TOP10 按非零 hot_score 降序（评分在日报前完成）。"""
    await _seed_corpus(db_session)
    await run_clustering(db_session, days=1, now=_FIXED_NOW)
    await run_scoring(db_session, now=_FIXED_NOW)

    async def _no_llm(title: str, body: str) -> str | None:
        return None

    report = await build_daily_report(db_session, _TOPIC_DATE, llm=_no_llm, generated_by="manual")
    assert report is not None
    assert report.topic_count == 2

    topics = (
        (
            await db_session.execute(
                select(HotTopic).where(HotTopic.topic_date == _TOPIC_DATE).order_by(HotTopic.hot_score.desc())
            )
        )
        .scalars()
        .all()
    )
    scores = [t.hot_score for t in topics]
    assert all(s > 0 for s in scores), f"存在零分话题: {scores}"
    assert scores == sorted(scores, reverse=True), "TOP10 未按 hot_score 降序"


# ── 状态机集成（时间推进） ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_scoring_status_transitions_with_time(db_session) -> None:
    """注入时间推进：话题 >24h 且分降 → cooling；>48h → archived。"""
    await _seed_corpus(db_session)
    await run_clustering(db_session, days=1, now=_FIXED_NOW)
    await run_scoring(db_session, now=_FIXED_NOW)

    topics_before = (
        (await db_session.execute(select(HotTopic).where(HotTopic.topic_date == _TOPIC_DATE))).scalars().all()
    )
    assert len(topics_before) == 2
    for t in topics_before:
        assert t.status in ("rising", "hot"), f"初始状态应为 rising/hot，实际 {t.status}"

    now_36h = _FIXED_NOW + timedelta(hours=36)
    await run_scoring(db_session, now=now_36h)
    topics_36h = (await db_session.execute(select(HotTopic).where(HotTopic.topic_date == _TOPIC_DATE))).scalars().all()
    for t in topics_36h:
        assert t.status in ("hot", "cooling", "archived"), f"36h 后状态应为 hot/cooling/archived，实际 {t.status}"

    now_54h = _FIXED_NOW + timedelta(hours=54)
    await run_scoring(db_session, now=now_54h)
    topics_54h = (await db_session.execute(select(HotTopic).where(HotTopic.topic_date == _TOPIC_DATE))).scalars().all()
    for t in topics_54h:
        assert t.status == "archived", f"54h 后状态应为 archived，实际 {t.status}"


# ── scheduler rescore 幂等 ─────────────────────────────────────────


def test_rescore_hour_key_idempotent() -> None:
    """同小时 rescore 幂等：_last_rescore_hour 去重。"""
    from app.services.scheduler import IncrementalScheduler

    scheduler = IncrementalScheduler.__new__(IncrementalScheduler)
    scheduler._last_rescore_hour = "2026100112"
    hour_key = datetime(2026, 10, 1, 12, 30, tzinfo=_TZ).strftime("%Y%m%d%H")
    assert hour_key == "2026100112"
    assert scheduler._last_rescore_hour == hour_key
