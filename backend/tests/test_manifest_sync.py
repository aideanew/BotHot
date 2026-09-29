"""T2.2 Manifest 同步验收：清单落库 + `(source, article_id)` 唯一键幂等 + 分页 + 不造数。

机器门口径（大纲 v1.4 §8.1 序4 验收锚：「`_sync_manifests` 接 query_work_list 或
`_seed_manifests`；biz+article_id 唯一键幂等」）：
- **落库**：Provider 原始行 → `ArticleManifest`（DISCOVERED），字段防御式映射；
- **幂等**：同键二次同步**不产生重复行**，第二跑 `discovered=0 / unchanged=n`；
- **更新**：可变字段（title/url/时间/hash）变更 → 行数不变、`updated` 计数命中；
- **分页**：空页即止、`max_pages` 封顶；
- **不造数**：无 Key → Provider=None（调度器跳过发现）；Provider 报错 → 上抛不吞（承 1.1.4）。

连库口径（真提交连接，与 T2.3/T2.4 同法）：PG 不可达 → skip；命名空间 `t22-` 清场保证幂等。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.errors import DependencyUnavailableError
from app.models.entities import ArticleManifest, Job, KnowledgeSpace, Source, SourceSubscription
from app.repositories.space import SpaceRepository
from app.repositories.user import SqlAlchemyUserStore
from app.services.manifest import (
    UPSTREAM_TZ,
    ManifestSyncReport,
    ManifestSyncService,
    _map_row,
    _parse_time,
    make_redfox_provider,
)
from app.services.scheduler import IncrementalScheduler, make_sync_runner

PG_DSN = os.environ.get(
    "AIDEANBOT_TEST_PG_DSN", "postgresql+psycopg://bothot:bothot@localhost:5433/bothot"
)
_T22_USER = "sub-t22-manifest"
_T22_SPACE = "T22清单空间"
_T22_BIZ = "T22MANIFESTBIZ"

# 用小页加速多页路径的断言（生产常量 PAGE_SIZE=20；游标逻辑与页大小无关）
TEST_PAGE_SIZE = 2


# ---------------------------------------------------------------- 夹具 / 清场


def _purge_t22() -> None:
    try:
        engine = create_engine(PG_DSN, connect_args={"connect_timeout": 3})
    except Exception:  # noqa: BLE001
        return
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM jobs WHERE idempotency_key LIKE :p"), {"p": "sync_account:t22-%"})
            conn.execute(text("DELETE FROM users WHERE sub = :s"), {"s": _T22_USER})
            conn.execute(text("DELETE FROM sources WHERE external_id LIKE :p"), {"p": "T22%"})
            conn.execute(text("DELETE FROM knowledge_spaces WHERE name LIKE :p"), {"p": "T22%"})
    except Exception:  # noqa: BLE001
        return
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def _t22_guard() -> Iterator[None]:
    try:
        engine = create_engine(PG_DSN, connect_args={"connect_timeout": 3})
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PG 不可达（{type(exc).__name__}），Docker 引擎恢复后复跑本用例")
    _purge_t22()
    yield
    _purge_t22()


def _factory():  # noqa: ANN202
    engine = create_async_engine(PG_DSN, pool_pre_ping=True, connect_args={"connect_timeout": 3})
    return engine, async_sessionmaker(engine, expire_on_commit=False)


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now


class _StubProvider:
    """可编程清单桩：按 page 返回 `(行, 上游 total)`。

    `total=None` 模拟上游缺字段 → 游标退化为「按空页/末页终止」的遍历。
    """

    def __init__(self, pages: dict[int, list[dict[str, object]]], total: int | None = None) -> None:
        self._pages = pages
        self._total = total
        self.calls: list[int] = []

    async def query_work_list(
        self, biz: str, page: int
    ) -> tuple[list[dict[str, object]], int | None]:  # noqa: ARG002
        self.calls.append(page)
        return self._pages.get(page, []), self._total

    async def aclose(self) -> None:  # pragma: no cover - 桩无需释放
        return None


class _AlwaysRowsProvider:
    """每页都返回满页行（测 max_pages 封顶 / 缺口规划的上界）。"""

    def __init__(self, page_size: int, total: int) -> None:
        self._page_size = page_size
        self._total = total
        self.calls: list[int] = []

    async def query_work_list(
        self, biz: str, page: int
    ) -> tuple[list[dict[str, object]], int | None]:  # noqa: ARG002
        self.calls.append(page)
        return [
            {
                "workUuid": f"w-{page}-{i}",
                "workUrl": f"https://mp.weixin.qq.com/s/w-{page}-{i}",
                "title": f"t-{page}-{i}",
            }
            for i in range(self._page_size)
        ], self._total

    async def aclose(self) -> None:  # pragma: no cover
        return None


def _row(n: int, *, title: str | None = None, uid_key: str = "workUuid") -> dict[str, object]:
    """按**实测真实字段形状**造行：`workUrl`（非 `url`）+ 无时区北京时间串。"""
    return {
        uid_key: f"T22-w-{n}",
        "workUrl": f"https://mp.weixin.qq.com/s/T22-{n}",
        "title": title if title is not None else f"T22文章{n}",
        "publishTime": "2026-09-20 10:00:00",
    }


async def _seed_source(factory, biz: str = _T22_BIZ) -> tuple[str, str]:  # noqa: ANN001
    """建 user + space + source；返回 (source_id, space_id)。"""
    async with factory() as session:
        user = await SqlAlchemyUserStore(session).upsert_by_sub(_T22_USER, "t22@test.local", "T22")
        space = (
            await session.execute(
                select(KnowledgeSpace).where(
                    KnowledgeSpace.user_id == user.id, KnowledgeSpace.name == _T22_SPACE
                )
            )
        ).scalar_one_or_none()
        if space is None:
            space = await SpaceRepository(session).create(user_id=user.id, name=_T22_SPACE)
        src = (
            await session.execute(
                select(Source).where(Source.type == "wechat_oa", Source.external_id == biz)
            )
        ).scalar_one_or_none()
        if src is None:
            src = Source(type="wechat_oa", external_id=biz, name=biz, url=f"https://redfox.hk/{biz}")
            session.add(src)
            await session.flush()
        await session.commit()
        return src.id, space.id


async def _manifest_rows(factory, source_id: str) -> list[ArticleManifest]:  # noqa: ANN001
    async with factory() as session:
        rows = await session.scalars(
            select(ArticleManifest)
            .where(ArticleManifest.source_id == source_id)
            .order_by(ArticleManifest.external_id)
        )
        return list(rows)


async def _sync(
    source_id: str, provider: _StubProvider, *, page_size: int = TEST_PAGE_SIZE, **kw: object
) -> ManifestSyncReport:
    engine, factory = _factory()
    try:
        async with factory() as session:
            report = await ManifestSyncService(
                session, provider, page_size=page_size  # type: ignore[arg-type]
            ).sync_source(
                source_id, _T22_BIZ, **kw  # type: ignore[arg-type]
            )
            await session.commit()
            return report
    finally:
        await engine.dispose()


# ---------------------------------------------------------------- ① 纯函数：映射


def test_map_row_defensive_aliases() -> None:
    """字段别名防御式映射：workUuid/uuid/articleId 均认；缺 id → None。"""
    assert _map_row({"workUuid": "w1", "url": "u", "title": "t"})["external_id"] == "w1"  # type: ignore[index]
    assert _map_row({"uuid": "w2", "url": "u", "title": "t"})["external_id"] == "w2"  # type: ignore[index]
    assert _map_row({"articleId": "w3", "url": "u", "title": "t"})["external_id"] == "w3"  # type: ignore[index]
    assert _map_row({"url": "u", "title": "t"}) is None, "缺 external_id 不可用"
    assert _map_row({}) is None


def test_map_row_accepts_real_redfox_shape() -> None:
    """F2 回归：广域库真实行形状（`workUrl`、无 `url` 键）必须映射出非空 url。

    此前 `_URL_KEYS` 缺 `workUrl` → 入库 `url=""` → JobWorker 硬失败
    （`ValueError("item.url 为空，无可采地址")`），整条采集链 100% 失败。
    """
    real_row = {
        "workUuid": "d5e2a9e08485478ab949a6ce39a0c75f",
        "workUrl": "https://mp.weixin.qq.com/s?__biz=MzA5NDQ2MjkzOQ%3D&mid=1",
        "title": "实测样本",
        "publishTime": "2026-09-27 07:42:00",
        "content": None,
        "sourceUrl": None,
    }
    m = _map_row(real_row)
    assert m is not None
    assert m["external_id"] == "d5e2a9e08485478ab949a6ce39a0c75f"
    assert m["url"] == "https://mp.weixin.qq.com/s?__biz=MzA5NDQ2MjkzOQ%3D&mid=1"
    assert m["publish_time"] == datetime(2026, 9, 27, 7, 42, tzinfo=UPSTREAM_TZ)


def test_map_row_workurl_wins_over_legacy_url_alias() -> None:
    """两键并存时以真实契约键 `workUrl` 为准，`url` 仅作兜底。"""
    m = _map_row({"workUuid": "w", "workUrl": "real", "url": "legacy", "title": "t"})
    assert m is not None and m["url"] == "real"
    m2 = _map_row({"workUuid": "w2", "url": "legacy", "title": "t"})
    assert m2 is not None and m2["url"] == "legacy"


def test_map_row_derives_hash_and_status() -> None:
    """无 contentHash 时按 url|title 派生（64 位 sha256）；状态恒 DISCOVERED。"""
    m = _map_row({"workUuid": "w", "url": "u", "title": "t", "publishTime": "2026-09-20T10:00:00Z"})
    assert m is not None
    assert len(str(m["content_hash"])) == 64
    assert m["status"] == "DISCOVERED"
    assert m["publish_time"] == datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
    # 无时间字段 → None（不造时间）
    assert _map_row({"workUuid": "w2", "url": "u", "title": "t"})["publish_time"] is None  # type: ignore[index]


def test_parse_time_variants() -> None:
    """时间解析：ISO-Z / ISO 无时区 / epoch 秒 / epoch 毫秒 / 非法值。"""
    assert _parse_time("2026-09-20T10:00:00Z") == datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
    assert _parse_time(1700000000) == datetime.fromtimestamp(1700000000, tz=UTC)
    assert _parse_time(1700000000000) == datetime.fromtimestamp(1700000000, tz=UTC), "毫秒自动降级"
    assert _parse_time("不是时间") is None
    assert _parse_time(None) is None
    assert _parse_time(True) is None, "bool 不是时间"


def test_parse_time_naive_string_is_upstream_beijing() -> None:
    """时区回归：无时区串按上游 `Asia/Shanghai` 解释，不再默认 UTC（此前整体早 8 小时）。

    显式带时区的值不受影响（Z / 偏移量均按字面解释）。
    """
    beijing = datetime(2026, 9, 27, 7, 42, tzinfo=UPSTREAM_TZ)
    assert _parse_time("2026-09-27 07:42:00") == beijing
    assert _parse_time("2026-09-27T07:42:00+08:00") == beijing
    # UTC 锚点下的同一时刻应为 23:42Z 前一天
    assert _parse_time("2026-09-27 07:42:00") == datetime(2026, 9, 26, 23, 42, tzinfo=UTC)


def test_redfox_provider_gate_no_key() -> None:
    """无 Key → Provider=None（显式缺省不造数）；有 Key → 装配成功。"""
    assert make_redfox_provider(Settings(redfox_api_key="")) is None
    p = make_redfox_provider(Settings(redfox_api_key="k-123", redfox_base_url="https://redfox.hk"))
    assert p is not None and hasattr(p, "query_work_list")


# ---------------------------------------------------------------- ② 落库 / 幂等


async def test_sync_creates_discovered_rows() -> None:
    """首轮：3 行清单 → 3 条 DISCOVERED ArticleManifest；按缺口规划 2 页（页大小 2）。"""
    engine, factory = _factory()
    try:
        source_id, _ = await _seed_source(factory)
        provider = _StubProvider({1: [_row(1), _row(2)], 2: [_row(3)]}, total=3)
        report = await _sync(source_id, provider)

        assert report.discovered == 3 and report.updated == 0 and report.unchanged == 0  # type: ignore[attr-defined]
        rows = await _manifest_rows(factory, source_id)
        assert len(rows) == 3
        assert all(r.status == "DISCOVERED" for r in rows)
        assert provider.calls == [1, 2], "末页不足整页即止"
        assert report.pages_planned == 2 and report.calls_made == 2  # type: ignore[attr-defined]
    finally:
        await engine.dispose()


async def test_sync_steady_state_is_exactly_one_call() -> None:
    """稳态核心（成本口径）：本地条数 = 上游 total → 缺口 0 → **恰好 1 次上游调用**。

    旧实现固定翻到 `max_pages` 或空页，稳态每号每轮 10 次调用；这是 10× 削减的来源。
    """
    engine, factory = _factory()
    try:
        source_id, _ = await _seed_source(factory)
        await _sync(source_id, _StubProvider({1: [_row(1), _row(2)], 2: [_row(3)]}, total=3))

        provider = _StubProvider({1: [_row(1), _row(2)]}, total=3)
        report = await _sync(source_id, provider)

        assert provider.calls == [1] and report.calls_made == 1  # type: ignore[attr-defined]
        assert report.known_local == 3 and report.total_remote == 3  # type: ignore[attr-defined]
        assert report.pages_planned == 1  # type: ignore[attr-defined]
        assert report.discovered == 0 and report.unchanged == 2 and report.updated == 0  # type: ignore[attr-defined]
    finally:
        await engine.dispose()


async def test_sync_total_under_reports_still_recovers_all() -> None:
    """鲁棒性（L3-2.2.4）：上游 `total` 少报时仍不漏采。

    `total` 报 2、实际 3 篇：第 1 页满页且**全为新行** → 触发继续翻页，
    第 2 页拿到被漏报的那 1 篇。这是「未见篇恒为前缀」带来的性质，不依赖 `total` 正确。
    """
    engine, factory = _factory()
    try:
        source_id, _ = await _seed_source(factory)
        provider = _StubProvider({1: [_row(1), _row(2)], 2: [_row(3)]}, total=2)
        report = await _sync(source_id, provider)

        assert report.discovered == 3, "漏报的 1 篇必须被补回"  # type: ignore[attr-defined]
        assert provider.calls == [1, 2]
        assert report.total_remote == 2  # type: ignore[attr-defined]
    finally:
        await engine.dispose()


async def test_sync_walk_continues_past_rows_without_id() -> None:
    """缺 id 的脏行不中断翻页：它既非新篇也非既有篇，不构成「前缀已结束」的信号。"""
    engine, factory = _factory()
    try:
        source_id, _ = await _seed_source(factory)
        provider = _StubProvider(
            {1: [_row(1), {"url": "u", "title": "无ID"}], 2: [_row(2)]}, total=2
        )
        report = await _sync(source_id, provider)

        assert report.skipped == 1 and report.discovered == 2  # type: ignore[attr-defined]
        assert provider.calls == [1, 2]
    finally:
        await engine.dispose()


async def test_sync_total_missing_falls_back_to_walk() -> None:
    """上游缺 total → 退化为遍历至末页，仍能拿全（不让游标静默丢篇）。"""
    engine, factory = _factory()
    try:
        source_id, _ = await _seed_source(factory)
        provider = _StubProvider({1: [_row(1), _row(2)], 2: [_row(3), _row(4)], 3: [_row(5)]})
        report = await _sync(source_id, provider)

        assert report.total_remote is None  # type: ignore[attr-defined]
        assert provider.calls == [1, 2, 3] and report.discovered == 5  # type: ignore[attr-defined]
    finally:
        await engine.dispose()


async def test_sync_idempotent_second_run_unchanged() -> None:
    """幂等（核心验收）：同键二次同步 → 行数不变、discovered=0、每条既有行均计 unchanged。

    两篇同置一页，保证第二轮走的是**全量已有行**而非仅首页。
    """
    engine, factory = _factory()
    try:
        source_id, _ = await _seed_source(factory)
        pages = {1: [_row(1), _row(2)]}
        r1 = await _sync(source_id, _StubProvider(pages, total=2))
        r2 = await _sync(source_id, _StubProvider(pages, total=2))

        assert r1.discovered == 2  # type: ignore[attr-defined]
        assert r2.discovered == 0 and r2.unchanged == 2 and r2.updated == 0  # type: ignore[attr-defined]
        assert r2.calls_made == 1, "全量已是既有行 → 首页即止"  # type: ignore[attr-defined]
        rows = await _manifest_rows(factory, source_id)
        assert len(rows) == 2, "唯一键 (source_id, external_id) 保证不重复"
    finally:
        await engine.dispose()


async def test_sync_updates_changed_fields_no_new_rows() -> None:
    """远端字段变更 → 原地更新（行数不变，updated 计数命中）。"""
    engine, factory = _factory()
    try:
        source_id, _ = await _seed_source(factory)
        await _sync(source_id, _StubProvider({1: [_row(1, title="旧标题")]}, total=1))
        report = await _sync(source_id, _StubProvider({1: [_row(1, title="新标题")]}, total=1))

        assert report.updated == 1 and report.discovered == 0  # type: ignore[attr-defined]
        rows = await _manifest_rows(factory, source_id)
        assert len(rows) == 1 and rows[0].title == "新标题"
    finally:
        await engine.dispose()


async def test_sync_updates_empty_url_from_real_workurl() -> None:
    """F2 数据修复路径：历史入库的空 url 由后续一轮同步用 `workUrl` 原地补齐。

    不需要数据迁移——`_apply_update` 对可变字段做差异更新，url 从 "" 变为真实值即命中。
    """
    engine, factory = _factory()
    try:
        source_id, _ = await _seed_source(factory)
        # 旧代码形状（缺 workUrl）→ 入库空 url
        legacy = {1: [{"workUuid": "T22-w-1", "url": "", "title": "旧", "publishTime": ""}]}
        await _sync(source_id, _StubProvider(legacy, total=1))
        rows = await _manifest_rows(factory, source_id)
        assert rows[0].url == "", "旧形状入库为空 url"

        report = await _sync(source_id, _StubProvider({1: [_row(1)]}, total=1))
        assert report.updated == 1 and report.discovered == 0  # type: ignore[attr-defined]
        rows = await _manifest_rows(factory, source_id)
        assert rows[0].url == "https://mp.weixin.qq.com/s/T22-1"
    finally:
        await engine.dispose()


async def test_sync_skips_rows_without_id() -> None:
    """缺 external_id 的行计入 skipped，不入库（不造脏行）。"""
    engine, factory = _factory()
    try:
        source_id, _ = await _seed_source(factory)
        provider = _StubProvider({1: [_row(1), {"url": "u", "title": "无ID"}]}, total=2)
        report = await _sync(source_id, provider)

        assert report.discovered == 1 and report.skipped == 1  # type: ignore[attr-defined]
        assert len(await _manifest_rows(factory, source_id)) == 1
    finally:
        await engine.dispose()


async def test_sync_max_pages_caps_backfill() -> None:
    """`max_pages` 是回填硬上限：缺口再大也不越过（防首次接入把余额打光）。"""
    engine, factory = _factory()
    try:
        source_id, _ = await _seed_source(factory)
        huge = _AlwaysRowsProvider(page_size=TEST_PAGE_SIZE, total=1000)
        async with factory() as session:
            r = await ManifestSyncService(
                session, huge, page_size=TEST_PAGE_SIZE  # type: ignore[arg-type]
            ).sync_source(source_id, "T22CAPBIZ", max_pages=3)
            await session.commit()
        assert r.pages == 3, "max_pages=3 封顶"  # type: ignore[attr-defined]
        assert r.calls_made == 3  # type: ignore[attr-defined]
        assert r.pages_planned == 500, "缺口规划值不受 cap 影响，仅循环上界受 cap"  # type: ignore[attr-defined]
        assert huge.calls == [1, 2, 3]
    finally:
        await engine.dispose()


async def test_sync_missing_biz_returns_empty_report() -> None:
    """缺 biz → 空报告且不调用 Provider（不盲打上游）。"""
    engine, factory = _factory()
    try:
        source_id, _ = await _seed_source(factory)
        provider = _StubProvider({1: [_row(1)]})
        async with factory() as session:
            report = await ManifestSyncService(session, provider).sync_source(source_id, "")
            await session.commit()
        assert report.total == 0 and provider.calls == []
    finally:
        await engine.dispose()


async def test_sync_provider_error_propagates() -> None:
    """Provider 报错（如 3201 积分不足）→ 上抛，不吞错冒成功（1.1.4 反造假）。"""

    class _Boom:
        async def query_work_list(
            self, biz: str, page: int
        ) -> tuple[list[dict[str, object]], int | None]:  # noqa: ARG002
            raise DependencyUnavailableError("RedFox 积分余额不足（3201）")

        async def aclose(self) -> None:
            return None

    engine, factory = _factory()
    try:
        source_id, _ = await _seed_source(factory)
        async with factory() as session:
            with pytest.raises(DependencyUnavailableError):
                await ManifestSyncService(session, _Boom()).sync_source(source_id, _T22_BIZ)  # type: ignore[arg-type]
            await session.rollback()
    finally:
        await engine.dispose()


# ---------------------------------------------------------------- ③ 与调度器闭环


async def test_scheduler_discovers_then_enqueues() -> None:
    """闭环：调度触发 → 发现落库（T2.2）→ Diff 增量入列（T2.4）→ Job + PENDING item。"""
    engine, factory = _factory()
    try:
        clock = _Clock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
        source_id, space_id = await _seed_source(factory)
        async with factory() as session:
            user = await SqlAlchemyUserStore(session).upsert_by_sub(_T22_USER, "t22@test.local", "T22")
            session.add(
                SourceSubscription(
                    id="t22-loop",
                    user_id=user.id,
                    source_id=source_id,
                    space_id=space_id,
                    sync_interval_minutes=60,
                    next_run_at=clock.now - timedelta(minutes=1),
                )
            )
            await session.commit()

        provider = _StubProvider({1: [_row(1), _row(2)]})
        sched = IncrementalScheduler(
            factory,
            settings=Settings(),
            sync_runner=make_sync_runner(provider),  # type: ignore[arg-type]
            now_fn=clock,
            idle_sleep_seconds=0.0,
            heartbeat_enabled=False,
        )
        assert await sched.run_once() == 1

        rows = await _manifest_rows(factory, source_id)
        assert len(rows) == 2, "发现环节应落 2 条清单"
        async with factory() as session:
            jobs = list(
                await session.scalars(
                    select(Job).where(Job.idempotency_key.like("sync_account:t22-loop%"))
                )
            )
            assert len(jobs) == 1, "非空轮询应建 1 个 Job"
            sub = await session.get(SourceSubscription, "t22-loop")
            assert sub is not None and sub.consecutive_empty_syncs == 0
    finally:
        await engine.dispose()


async def test_scheduler_error_advances_watermark_without_polluting_empty() -> None:
    """同步抛错 → 水位按基准间隔推进（不空转），且**不**计入空轮询计数。"""
    engine, factory = _factory()
    try:
        clock = _Clock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
        source_id, space_id = await _seed_source(factory, biz="T22ERRBIZ")
        async with factory() as session:
            user = await SqlAlchemyUserStore(session).upsert_by_sub(_T22_USER, "t22@test.local", "T22")
            session.add(
                SourceSubscription(
                    id="t22-err",
                    user_id=user.id,
                    source_id=source_id,
                    space_id=space_id,
                    sync_interval_minutes=60,
                    next_run_at=clock.now - timedelta(minutes=1),
                )
            )
            await session.commit()

        calls = 0

        async def _boom(session: AsyncSession, sub: SourceSubscription, run_token: str) -> int:  # noqa: ARG001
            nonlocal calls
            calls += 1
            raise DependencyUnavailableError("RedFox 积分余额不足（3201）")

        sched = IncrementalScheduler(
            factory,
            settings=Settings(),
            sync_runner=_boom,
            now_fn=clock,
            idle_sleep_seconds=0.0,
            heartbeat_enabled=False,
        )
        assert await sched.run_once() == 1
        # 认领与水位推进须同事务提交：若错误路径先回滚（释放行锁）再另起事务推水位，
        # `scheduler_concurrency` 个并行认领者会认领到同一条订阅，把 _sync 跑两次——
        # 发现阶段 RedFox 清单调用按次计费，重复认领即重复扣费。本断言是该竞态的直接检测器。
        assert calls == 1, f"同一条订阅被认领 {calls} 次：认领/推水位之间存在可重认领窗口"

        async with factory() as session:
            sub = await session.get(SourceSubscription, "t22-err")
            assert sub is not None
            assert sub.next_run_at == clock.now + timedelta(minutes=60), "错误路径水位按基准间隔推进"
            assert sub.consecutive_empty_syncs == 0, "错误不得计为空轮询"
    finally:
        await engine.dispose()
