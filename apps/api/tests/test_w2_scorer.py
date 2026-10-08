"""W2 热度评分单测（验收 2）：纯函数，零 DB 依赖。

断言（product-requirements.md:64 口径："48h 内独立来源数加权，24h 减半"）：
- 24h 前 2 独立来源 → 得分 2×0.5=1.0；
- 48h 外不计；
- 跨来源去重正确（同来源多篇取最年轻）。
状态机：rising→hot（score≥10）/ hot→cooling（age>24h 且分降）/ cooling→archived（age>48h）。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.hot_scorer import (
    ARCHIVE_AGE_HOURS,
    COOLING_AGE_HOURS,
    HOT_SCORE_RISING_TO_HOT,
    _ArticleTime,
    compute_score,
    next_status,
)

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=TZ)


def _art(source: str, hours_ago: float) -> _ArticleTime:
    return _ArticleTime(
        source_id=source,
        published_at=NOW - timedelta(hours=hours_ago),
        created_at=NOW,
    )


def test_two_sources_24h_ago_scores_one() -> None:
    """2 独立来源各 24h 前 → 每个贡献 2^(-1)=0.5，合计 1.0。"""
    articles = [_art("s1", 24.0), _art("s2", 24.0)]
    score, src_count, art_count = compute_score(articles, now=NOW)
    assert abs(score - 1.0) < 1e-9
    assert src_count == 2
    assert art_count == 2


def test_beyond_48h_not_counted() -> None:
    """48h 外的来源不计入分数与来源数。"""
    articles = [_art("s1", 24.0), _art("s2", 24.0), _art("s3", 50.0)]
    score, src_count, art_count = compute_score(articles, now=NOW)
    assert abs(score - 1.0) < 1e-9  # s3 不计
    assert src_count == 2
    assert art_count == 3  # 文章总数仍含


def test_cross_source_dedup_takes_freshest() -> None:
    """同来源多篇取最年轻（最小 age）那篇算权重；来源数只计 1。"""
    articles = [_art("s1", 12.0), _art("s1", 6.0), _art("s2", 24.0)]
    score, src_count, art_count = compute_score(articles, now=NOW)
    # s1 取 6h → 2^(-6/24)=2^(-0.25)；s2 24h → 0.5
    expected = 2.0 ** (-6.0 / 24.0) + 0.5
    assert abs(score - expected) < 1e-9
    assert src_count == 2
    assert art_count == 3


def test_boundary_48h_included() -> None:
    """age==48h 仍计入（>48 才排除）；权重 2^(-2)=0.25。"""
    score, src_count, _ = compute_score([_art("s1", 48.0)], now=NOW)
    assert abs(score - 0.25) < 1e-9
    assert src_count == 1


def test_next_status_rising_to_hot() -> None:
    assert next_status("rising", score=HOT_SCORE_RISING_TO_HOT, prev_score=0.0, topic_age_hours=1.0) == "hot"
    assert next_status("rising", score=HOT_SCORE_RISING_TO_HOT - 1, prev_score=0.0, topic_age_hours=1.0) == "rising"


def test_next_status_hot_to_cooling() -> None:
    """age>24h 且分降 → cooling；分不降则保持 hot。"""
    assert next_status("hot", score=5.0, prev_score=8.0, topic_age_hours=COOLING_AGE_HOURS + 1) == "cooling"
    assert next_status("hot", score=8.0, prev_score=8.0, topic_age_hours=COOLING_AGE_HOURS + 1) == "hot"


def test_next_status_archive() -> None:
    """age>48h → archived（不论当前 rising/hot/cooling）。"""
    for cur in ("rising", "hot", "cooling"):
        assert next_status(cur, score=100.0, prev_score=100.0, topic_age_hours=ARCHIVE_AGE_HOURS + 1) == "archived"
    assert next_status("archived", score=0.0, prev_score=10.0, topic_age_hours=99.0) == "archived"
