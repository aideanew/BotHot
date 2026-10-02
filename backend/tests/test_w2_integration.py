"""W2 PG 集成测试（验收 3 / 4 / 5）：用 db_session 夹具（savepoint 回滚隔离）。

- 验收 3：聚簇重跑同日不产生重复 topic；feed_items 无 (item_type,ref_id) 重复；
- 验收 4：on_article_indexed 写 article FeedItem（kb INDEXED 落点调用的同一函数）；
- 验收 5：build_daily_report 在 LLM 失败时仍产出含降级摘要的日报。

前置：迁移 ab1004w2a 已应用（`alembic upgrade head`），否则 upsert 的 ON CONFLICT
缺少唯一约束会报错。PG 不可达 → db_session 夹具自动 skip。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.models.bothot_entities import FeedItem, HotTopic
from app.models.entities import ContentAsset, Source
from app.services.feed_service import build_daily_report, on_article_indexed
from app.services.hot_cluster import run_clustering

_TZ = ZoneInfo("Asia/Shanghai")
_FIXED_NOW = datetime(2026, 9, 30, 12, 0, tzinfo=_TZ)
_TOPIC_DATE = _FIXED_NOW.strftime("%Y-%m-%d")


def _make_asset(source_id: str, *, key: str, title: str, quality: float, body: str = "正文首段。") -> ContentAsset:
    return ContentAsset(
        source_id=source_id,
        external_id=key,
        url=f"https://example.test/{key}",
        title=title,
        author="",
        published_at=_FIXED_NOW - timedelta(hours=2),
        content_type="article",
        content_hash=f"hash-{key}",
        raw_uri="",
        content_markdown=body,
        version=1,
        quality_score=quality,
        status="READY",
        hit_count=0,
        category="tech",
    )


async def _seed_cluster_corpus(session) -> list[ContentAsset]:
    s1 = Source(type="wechat_oa", external_id="biz-w2-a", name="来源A", url="", status="ACTIVE")
    s2 = Source(type="wechat_oa", external_id="biz-w2-b", name="来源B", url="", status="ACTIVE")
    session.add_all([s1, s2])
    await session.flush()
    assets = [
        _make_asset(s1.id, key="a1", title="OpenAI发布GPT-5模型", quality=0.5, body="OpenAI 发布了 GPT-5 模型。"),
        _make_asset(s2.id, key="a2", title="OpenAI推出全新GPT-5大模型", quality=0.8, body="OpenAI 推出全新 GPT-5。"),
        _make_asset(s1.id, key="b1", title="美联储宣布加息50个基点", quality=0.6, body="美联储宣布加息 50 基点。"),
        _make_asset(s2.id, key="b2", title="美联储加息50基点应对通胀", quality=0.9, body="美联储加息应对通胀。"),
    ]
    session.add_all(assets)
    await session.flush()
    return assets


@pytest.mark.asyncio
async def test_run_clustering_idempotent_no_dup_feed(db_session) -> None:  # type: ignore[no-untyped-def]
    """验收 3：重跑同日不产生重复 topic，feed_items 无重复。"""
    await _seed_cluster_corpus(db_session)
    res = await run_clustering(db_session, days=1, now=_FIXED_NOW)
    assert res["topics_persisted"] == 2

    topics = (await db_session.execute(select(HotTopic).where(HotTopic.topic_date == _TOPIC_DATE))).scalars().all()
    assert len(topics) == 2
    first_ids = {t.id for t in topics}

    # 重跑：整日 wipe 重建，topic 数不变，topic_id 变化（重建）
    await run_clustering(db_session, days=1, now=_FIXED_NOW)
    topics2 = (await db_session.execute(select(HotTopic).where(HotTopic.topic_date == _TOPIC_DATE))).scalars().all()
    assert len(topics2) == 2
    assert {t.id for t in topics2} != first_ids  # 重建后是新 id

    # feed_items 无 (hot_topic, ref_id) 重复——每个 topic 恰一条
    feeds = (
        (
            await db_session.execute(
                select(FeedItem).where(FeedItem.item_type == "hot_topic", FeedItem.ref_id.in_([t.id for t in topics2]))
            )
        )
        .scalars()
        .all()
    )
    assert len(feeds) == 2
    # upsert 幂等：对同一 topic 再 add_hot_topic_feed 不新增行
    from app.services.feed_service import add_hot_topic_feed

    await add_hot_topic_feed(db_session, topics2[0])
    feeds2 = (
        (
            await db_session.execute(
                select(FeedItem).where(FeedItem.item_type == "hot_topic", FeedItem.ref_id == topics2[0].id)
            )
        )
        .scalars()
        .all()
    )
    assert len(feeds2) == 1


@pytest.mark.asyncio
async def test_on_article_indexed_writes_feed_article(db_session) -> None:  # type: ignore[no-untyped-def]
    """验收 4：on_article_indexed 写 article FeedItem（kb INDEXED 落点同函数）。"""
    src = Source(type="wechat_oa", external_id="biz-w2-feed", name="来源X", url="", status="ACTIVE")
    db_session.add(src)
    await db_session.flush()
    asset = _make_asset(src.id, key="f1", title="某公众号文章", quality=0.42)
    db_session.add(asset)
    await db_session.flush()

    await on_article_indexed(db_session, asset, space_id="space-1")

    items = (
        (await db_session.execute(select(FeedItem).where(FeedItem.item_type == "article", FeedItem.ref_id == asset.id)))
        .scalars()
        .all()
    )
    assert len(items) == 1
    assert items[0].title == "某公众号文章"
    assert items[0].source_name == "来源X"
    assert abs(items[0].score - 0.42) < 1e-9

    # 验收 3（feed 唯一）：同 asset 再调一次不新增
    await on_article_indexed(db_session, asset, space_id="space-1")
    items2 = (
        (await db_session.execute(select(FeedItem).where(FeedItem.item_type == "article", FeedItem.ref_id == asset.id)))
        .scalars()
        .all()
    )
    assert len(items2) == 1


@pytest.mark.asyncio
async def test_build_daily_report_degraded_with_llm_none(db_session) -> None:  # type: ignore[no-untyped-def]
    """验收 5：LLM 失败时日报仍产出，含降级摘要（中心文章正文首段）。"""
    assets = await _seed_cluster_corpus(db_session)
    await run_clustering(db_session, days=1, now=_FIXED_NOW)

    async def _llm_none(title: str, body: str) -> str | None:
        return None

    report = await build_daily_report(db_session, _TOPIC_DATE, llm=_llm_none, generated_by="manual")
    assert report is not None
    assert report.topic_count == 2
    # 降级摘要 = 中心文章 content_markdown 首段截断（seed body 形如 "OpenAI 发布了..."）
    asset_a2 = next(a for a in assets if a.external_id == "a2")  # A 组 center
    assert (
        asset_a2.content_markdown in report.content_markdown
        or asset_a2.content_markdown[:150] in report.content_markdown
    )
    # 幂等：再调返回既有（不重建）
    again = await build_daily_report(db_session, _TOPIC_DATE, llm=_llm_none)
    assert again is not None and again.id == report.id
