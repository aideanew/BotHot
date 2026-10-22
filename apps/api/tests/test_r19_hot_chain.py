"""STEP-19 S19.1.2：REQ-F-002 热点链路端到端（一条链，不是四段碎片）。

卡面的待验命题是"聚簇→评分→Feed 回刷→日报降级 端到端一条链是否真贯通"。
本仓已有的用例把这条链**逐段**判过（`test_wa_hot_scoring` 判"聚簇后评分为正"与"Feed 分数与
hot_score 一致"、`test_w2_report` 判 `_topic_summary` 的降级、`test_w2_integration` 判"LLM 失败
日报仍产出"），每一段都绿。但"每段各自绿"不等于"一条链贯到底"：段与段之间是靠
`HotTopicArticle` / `FeedItem.ref_id` / `DailyReport.report_date` 三处外键串起来的，
任何一处接错，四段判据可以全部照样绿（它们各自只看自己那张表）。

所以本文件的判据是**同一条事务里把四个产物串起来核一次**，并专门判两件事：

- 聚簇落库时 `hot_score` 是 **0.0 占位**（`hot_cluster.py:275` 那行注释写明了"评分由 hot_scorer 回填"），
  评分之后必须变成非 0 且**回刷进 FeedItem**——这一对"先 0 后非 0"是链路真的在跑的证据；
  只看"最后非 0"的话，一个在聚簇时就直接写好分数的实现也照样绿，而那条每小时重评的回路就不存在了。
- LLM 抛穿与 LLM 返回空**两条**降级路径都要在日报正文里留下正文首段（不是空串、不是异常）。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.models.bothot_entities import FeedItem, HotTopic, HotTopicArticle
from app.models.entities import ContentAsset, Source
from app.services.feed_service import build_daily_report
from app.services.hot_cluster import run_clustering
from app.services.hot_scorer import run_scoring

_TZ = ZoneInfo("Asia/Shanghai")
#: 与 `test_w2_integration`（9-30）、`test_wa_hot_scoring`（10-01）错开业务日：
#: 日报按 `report_date` 幂等，同一天会被别的文件的既有报告挡住（真库残留时尤其明显）。
_T0 = datetime(2026, 10, 6, 12, 0, tzinfo=_TZ)
_DATE = _T0.strftime("%Y-%m-%d")


def _asset(source_id: str, *, key: str, title: str, quality: float, body: str) -> ContentAsset:
    return ContentAsset(
        source_id=source_id,
        external_id=key,
        url=f"https://r19.example.test/{key}",
        title=title,
        author="",
        published_at=_T0 - timedelta(hours=2),
        content_type="article",
        content_hash=f"hash-r19-{key}",
        raw_uri="",
        content_markdown=body,
        version=1,
        quality_score=quality,
        status="READY",
        hit_count=0,
        category="tech",
    )


async def _seed_corpus(session: Any, prefix: str) -> None:
    """两篇一组、共两组：一组两个话题，另加一组单篇（单篇**不该**成话题——卡面没写，但它是"聚簇"的反例）。"""
    s1 = Source(type="wechat_oa", external_id=f"biz-{prefix}-a", name=f"{prefix}A", url="", status="ACTIVE")
    s2 = Source(type="wechat_oa", external_id=f"biz-{prefix}-b", name=f"{prefix}B", url="", status="ACTIVE")
    session.add_all([s1, s2])
    await session.flush()
    session.add_all(
        [
            _asset(
                s1.id,
                key=f"{prefix}1",
                title="启明星发布新款大模型",
                quality=0.5,
                body=f"R19 降级锚点甲：{prefix} 模型发布正文首段。",
            ),
            _asset(
                s2.id,
                key=f"{prefix}2",
                title="启明星新款大模型正式上线",
                quality=0.9,
                body=f"R19 降级锚点乙：{prefix} 新款上线正文首段。",
            ),
            _asset(
                s1.id,
                key=f"{prefix}3",
                title="远望号完成深海试航",
                quality=0.6,
                body=f"R19 深海锚点：{prefix} 试航正文首段。",
            ),
            _asset(
                s2.id,
                key=f"{prefix}4",
                title="远望号深海试航结果公布",
                quality=0.8,
                body=f"R19 深海锚点二：{prefix} 结果正文首段。",
            ),
            _asset(
                s1.id,
                key=f"{prefix}5",
                title="孤篇：本地菜场猪肉价格",
                quality=0.7,
                body="R19 孤篇正文。",
            ),
        ]
    )
    await session.flush()


async def _topics(session: Any, topic_date: str) -> list[HotTopic]:
    return list((await session.execute(select(HotTopic).where(HotTopic.topic_date == topic_date))).scalars().all())


async def _feed_score(session: Any, topic_id: str) -> float | None:
    row = (
        await session.execute(
            select(FeedItem.score).where(FeedItem.item_type == "hot_topic", FeedItem.ref_id == topic_id)
        )
    ).scalar_one_or_none()
    return None if row is None else float(row)


# ── 一条链贯到底 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_chain_lands_in_a_report_whose_feed_and_scores_are_consistent(db_session: Any) -> None:
    """聚簇 → 评分 → Feed 回刷 → 日报，四步在同一份数据上串起来且彼此对得上。"""
    await _seed_corpus(db_session, "r19a")

    await run_clustering(db_session, days=1, now=_T0)
    topics = await _topics(db_session, _DATE)
    assert len(topics) == 2, f"两个话题族应各成一簇，孤篇不成话题；实际 {len(topics)}：{[t.title for t in topics]}"
    assert not any("猪肉" in t.title for t in topics), "单篇文章被当成话题（聚簇门槛失效）"
    # 聚簇阶段：评分位是 0.0 占位，Feed 也是 0.0——"链路后面那一步真的存在"才有这个 0
    for t in topics:
        assert float(t.hot_score) == 0.0, f"聚簇落库就带分数（{t.hot_score}）⇒ 评分回路不再是必经点"
        assert await _feed_score(db_session, t.id) == 0.0
    topic_ids = [t.id for t in topics]
    linked = int(
        await db_session.scalar(select(func.count()).select_from(HotTopicArticle).where(
            HotTopicArticle.hot_topic_id.in_(topic_ids)
        ))
        or 0
    )
    assert linked == 4, f"话题成员表应有 4 行（两簇各 2 篇），实际 {linked}"

    scored = await run_scoring(db_session, now=_T0)
    assert scored >= 2
    for t in topics:
        await db_session.refresh(t)
        assert float(t.hot_score) > 0.0, f"评分后 hot_score 仍是 {t.hot_score}（占位没被回填）"
        feed = await _feed_score(db_session, t.id)
        same = feed is not None and abs(feed - float(t.hot_score)) < 1e-9
        assert same, f"Feed 分数 {feed} != hot_score {t.hot_score}"

    async def _llm(title: str, body: str) -> str:
        return f"LLM 摘要：{title}"

    report = await build_daily_report(db_session, _DATE, llm=_llm, generated_by="manual")
    assert report is not None, "日报没产出（TOP10 取了却组装失败）"
    assert report.topic_count == 2
    for t in topics:
        assert t.title in report.content_markdown, "日报正文缺这个话题（TOP 选取与正文组装脱钩）"
        assert f"LLM 摘要：{t.title}" in report.content_markdown
    daily_feed = (
        await db_session.execute(
            select(FeedItem).where(FeedItem.item_type == "daily_report", FeedItem.ref_id == report.id)
        )
    ).scalar_one_or_none()
    assert daily_feed is not None, "日报落库了但没有 Feed 条目（前端 Feed 看不到日报）"


@pytest.mark.asyncio
async def test_hourly_rescore_keeps_the_feed_in_sync_after_the_clock_moves(db_session: Any) -> None:
    """每小时重评那一环：把时钟推后，重跑评分，Feed 必须跟着走——不能只有第一次同步。"""
    await _seed_corpus(db_session, "r19c")
    await run_clustering(db_session, days=1, now=_T0)
    await run_scoring(db_session, now=_T0)

    later = _T0 + timedelta(hours=30)
    await run_scoring(db_session, now=later)
    for t in await _topics(db_session, _DATE):
        feed = await _feed_score(db_session, t.id)
        assert feed is not None and abs(feed - float(t.hot_score)) < 1e-9, (
            f"重评后 Feed 分数没跟上（feed={feed} vs hot_score={t.hot_score}）"
        )


# ── 日报降级：两条失败形状都要留下正文首段 ──────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["raises", "returns_none"], ids=["LLM抛穿", "LLM返回空"])
async def test_llm_failure_still_lands_a_report_built_from_the_body(db_session: Any, kind: str) -> None:
    """卡面 2.2 的最后一格：触发日报并模拟 LLM 失败，断言走降级而不是失败或缺摘要。

    两种失败形状分开判：`_topic_summary` 的 `except` 管抛穿、`if summary:` 管空返回，
    只测一种时另一条被删掉也不会红。
    """

    async def _llm(title: str, body: str) -> str | None:
        if kind == "raises":
            raise RuntimeError("LLM 上游 500")
        return None

    await _seed_corpus(db_session, "r19d")
    await run_clustering(db_session, days=1, now=_T0)
    await run_scoring(db_session, now=_T0)

    report = await build_daily_report(db_session, _DATE, llm=_llm, generated_by="manual")
    assert report is not None, "LLM 失败把整份日报带崩（降级语义失效）"
    assert "LLM 摘要" not in report.content_markdown
    topics = await _topics(db_session, _DATE)
    for t in topics:
        # 降级源 = 中心文章正文首段；中心是组内 quality 最高那一篇
        assert t.center_asset_id is not None
        center = await db_session.get(ContentAsset, t.center_asset_id)
        assert center is not None
        first_para = (center.content_markdown or "").strip().split("\n", 1)[0].strip()
        assert first_para, "中心文章正文为空，降级没有素材（这条话题会以空摘要进日报）"
        assert first_para in report.content_markdown, f"话题「{t.title}」的降级摘要没进日报正文"
