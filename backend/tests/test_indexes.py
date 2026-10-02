"""C.3 索引断言 + 连接池容量断言（PG 不可达 skip，对齐 conftest 口径）。

断言 4 个高流量 FK 索引已建（migration 落库）且可被 EXPLAIN 选用（非 Seq Scan）。
PG 不可达 → db_session 夹具自动 skip。
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

# 4 个高流量 FK 索引（W8 hot/feed/push 读路径）— (table, column)
TARGET_INDEXES = [
    ("hot_topic_articles", "hot_topic_id"),
    ("hot_topic_articles", "asset_id"),
    ("push_logs", "bot_channel_id"),
    ("feed_items", "ref_id"),
]


@pytest.mark.asyncio
async def test_fk_indexes_exist(db_session) -> None:  # type: ignore[no-untyped-def]
    """4 个 FK 索引在 pg_indexes 中存在（migration 确实落库）。"""
    for table, col in TARGET_INDEXES:
        rows = (
            await db_session.execute(
                text("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public' AND tablename=:t"),
                {"t": table},
            )
        ).all()
        # 索引定义中包含列名即认为该列被索引（单列 index 或复合索引首列）
        assert any(col in r[1] for r in rows), f"{table}.{col} 索引缺失——migration 未落库，见 alembic 索引声明"


@pytest.mark.asyncio
async def test_explain_uses_index_not_seq_scan(db_session) -> None:  # type: ignore[no-untyped-def]
    """EXPLAIN（关闭 seqscan 强制走索引）非 Seq Scan → 索引可被优化器选用。"""
    await db_session.execute(text("SET enable_seqscan=off"))
    checks = [
        ("SELECT * FROM hot_topic_articles WHERE hot_topic_id='x'", "hot_topic_id"),
        ("SELECT * FROM hot_topic_articles WHERE asset_id='x'", "asset_id"),
        ("SELECT * FROM push_logs WHERE bot_channel_id='x'", "bot_channel_id"),
        ("SELECT * FROM feed_items WHERE ref_id='x'", "ref_id"),
    ]
    for sql, label in checks:
        plan = (await db_session.execute(text(f"EXPLAIN {sql}"))).all()
        plan_text = " ".join(str(r[0]) for r in plan)
        assert "Seq Scan" not in plan_text, f"{label}: EXPLAIN 仍走 Seq Scan（索引不可用？）plan={plan_text}"


@pytest.mark.asyncio
async def test_pool_capacity_assertion_runs(db_session) -> None:  # type: ignore[no-untyped-def]
    """assert_pool_capacity 在 PG 可达时不抛（默认 4×(5+5)=40 ≤ 100）。"""
    from app.db import assert_pool_capacity

    await assert_pool_capacity()  # PG 可达则断言通过；不可达则内部跳过
