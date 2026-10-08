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
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname='public' AND tablename=:t"
                ),
                {"t": table},
            )
        ).all()
        # 索引定义中包含列名即认为该列被索引（单列 index 或复合索引首列）
        assert any(col in r[1] for r in rows), (
            f"{table}.{col} 索引缺失——migration 未落库，见 alembic 索引声明"
        )


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
        assert "Seq Scan" not in plan_text, (
            f"{label}: EXPLAIN 仍走 Seq Scan（索引不可用？）plan={plan_text}"
        )


# ── assert_pool_capacity 三分支确定性用例（S0.2，全 mock 不依赖 PG 可达性）──
# 为什么不传真实 engine：Windows 测试进程里新建 psycopg async 连接受事件循环
# 策略影响，失败会被 assert_pool_capacity 的 except Exception 吞掉 → 正向/超限
# 用例都会假绿。mock engine 让「SHOW max_connections 返回值」完全可控，
# 三分支（通过/拒启/跳过）各自确定性覆盖。

class _FakeResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar(self) -> object:
        return self._value


class _FakeConn:
    def __init__(self, max_conn: object) -> None:
        self._max_conn = max_conn

    async def __aenter__(self) -> "_FakeConn":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def execute(self, _query: object) -> _FakeResult:
        return _FakeResult(self._max_conn)


class _FakeEngine:
    def __init__(self, max_conn: object) -> None:
        self._max_conn = max_conn

    def connect(self) -> _FakeConn:
        return _FakeConn(self._max_conn)


@pytest.mark.asyncio
async def test_pool_capacity_assertion_runs() -> None:
    """正向：默认口径 4×(5+5)=40 ≤ max_connections=100 → 不抛。"""
    from app.db import assert_pool_capacity

    await assert_pool_capacity(_FakeEngine(max_conn=100))


@pytest.mark.asyncio
async def test_pool_capacity_fail_fast_when_over_limit(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """S0.2：容量超限必须 fail-fast（RuntimeError 拒启），而不是静默放行。"""
    import app.db as db_mod
    from app.db import assert_pool_capacity

    # 把容量口径拉到必然超限：100 进程 × (100+100)=20000 ≫ max_connections=100
    monkeypatch.setattr(db_mod, "EXPECTED_PROCESSES", 100)
    monkeypatch.setattr(db_mod, "_DB_POOL_SIZE", 100)
    monkeypatch.setattr(db_mod, "_DB_MAX_OVERFLOW", 100)

    with pytest.raises(RuntimeError, match="连接池容量超限"):
        await assert_pool_capacity(_FakeEngine(max_conn=100))


@pytest.mark.asyncio
async def test_pool_capacity_skips_when_pg_unreachable() -> None:
    """PG 不可达时启动断言静默跳过（不拒启——连接故障由 pool_pre_ping 首查兜底）。"""
    from app.db import assert_pool_capacity

    class _BrokenEngine:  # 模拟 PG 不可达：connect() 即抛
        def connect(self) -> None:
            raise ConnectionError("pg unreachable")

    await assert_pool_capacity(_BrokenEngine())  # 不抛 = 内部跳过生效


@pytest.mark.asyncio
async def test_pool_capacity_skips_when_pg_unreachable() -> None:  # type: ignore[no-untyped-def]
    """PG 不可达时启动断言静默跳过（不拒启——连接故障由 pool_pre_ping 首查兜底）。"""
    from app.db import assert_pool_capacity

    class _BrokenEngine:  # 模拟 PG 不可达：connect() 即抛
        def connect(self):  # noqa: ANN202
            raise ConnectionError("pg unreachable")

    await assert_pool_capacity(_BrokenEngine())  # 不抛 = 内部跳过生效
