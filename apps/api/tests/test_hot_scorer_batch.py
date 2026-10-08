"""C.2 批量 UPDATE 单测：run_scoring 的 FeedItem 分数同步由 N 次 UPDATE 降为 1 条。

用伪 session 拦截 execute，计数 UPDATE feed_items 语句数。无需 PG。
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.services.hot_scorer import run_scoring


class _ScalarResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def scalars(self):  # noqa: ANN202
        return self

    def all(self):  # noqa: ANN202
        return self._rows


class _FakeSession:
    """拦截 execute：首次返回话题列表，后续 select 返回空文章行，记录 UPDATE 语句。

    run_scoring 执行序：
    1. select(HotTopic) → 话题列表
    2. 每话题 select(ContentAsset join HotTopicArticle) → 文章行（此处空）
    3. 批量 update(FeedItem)（C.2：应为 1 条）
    """

    def __init__(self, topics: list) -> None:
        self._topics = topics
        self._first = True
        self.feed_update_count = 0
        self.all_statements: list = []

    async def execute(self, stmt):  # noqa: ANN202
        self.all_statements.append(stmt)
        compiled = str(stmt.compile()).strip().upper()
        if compiled.startswith("UPDATE") and "FEED_ITEMS" in compiled:
            self.feed_update_count += 1
            return None
        if self._first and compiled.startswith("SELECT"):
            self._first = False
            return _ScalarResult(self._topics)
        return _ScalarResult([])  # 每话题文章行空


@pytest.mark.asyncio
async def test_feed_sync_is_single_batch_update() -> None:
    """3 个话题 → FeedItem UPDATE 语句数 == 1（C.2：原 N=3 降 1）。"""
    topics = [
        SimpleNamespace(id="t1", status="rising", hot_score=0.0, source_count=0, article_count=0),
        SimpleNamespace(id="t2", status="rising", hot_score=0.0, source_count=0, article_count=0),
        SimpleNamespace(id="t3", status="rising", hot_score=0.0, source_count=0, article_count=0),
    ]
    fake = _FakeSession(topics)
    await run_scoring(fake, now=datetime(2026, 9, 30, 12, 0, tzinfo=UTC))
    assert fake.feed_update_count == 1, (
        f"C.2 应为 1 条批量 UPDATE，实际 {fake.feed_update_count}（N 次=回归）"
    )
