"""T2.4 增量调度器验收：触发窗口 + consecutiveEmpty 退避序列 + 原子认领并发安全。

机器门口径（大纲 v1.4 §8.1 序3 验收锚：「`next_run_at` 驱动触发 + `consecutiveEmpty`
退避；单测断言触发窗口与退避序列」）：
- **触发窗口**：`status=ACTIVE AND next_run_at<=now` 触发；未来/非 ACTIVE 不触发；
- **退避序列**：连续空轮询 → `interval × min(2^n, cap)`，序列可逐一断言；发现新篇即清零；
- **原子认领**：PG 双调度器并发 → 每订阅恰被处理一次（`FOR UPDATE SKIP LOCKED`）；
- **增量入列**：Diff 新篇 → 建 run-scoped Job + JobItem；空轮询不建 Job。

连库口径（真提交连接，与 T2.3/T2.7 同法）：PG 不可达 → skip 并标注原因；用例级清场
（订阅 id 前缀 `t24-` 收敛命名空间）保证套件自身幂等可重复。时钟可控（now_fn 注入）。

S6.2.1（STEP-06 纠偏）：清单夹具与 READY 资产改用**真实形态**键。旧写法把资产 external_id
铺成渠道内 id（`t24-w0`），而清单行 `article_key` 是那条短路径 URL 算出来的 `h:` 兜底支——
两支永不相等 ⇒ Diff 的 ready 键减恒不命中；又因为首轮已把清单翻成 ENQUEUED，Diff 的首道谓词
是 status，于是"已入库篇不得再入列"这条断言实际由状态门守着，ready 门写坏也照样绿。
现在两支按生产各自的真源铺（`_article_seed`），并把 Job 置终态 + 清单合法回退成 DISCOVERED，
让 ready 键减成为**唯一**能救那条断言的门（变异读数见 EVD-V17-06 §1）。
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import NamedTuple
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.models.entities import (
    ArticleManifest,
    ContentAsset,
    Job,
    JobItem,
    KnowledgeDocument,
    KnowledgeSpace,
    Source,
    SourceSubscription,
    User,
)
from app.repositories.space import SpaceRepository
from app.repositories.user import SqlAlchemyUserStore
from app.services import scheduler as scheduler_module
from app.services.article_identity import canonical_article_key
from app.services.scheduler import IncrementalScheduler
from app.services.state_machine import validate_transition

PG_DSN = os.environ.get("AIDEANBOT_TEST_PG_DSN", "postgresql+psycopg://bothot:bothot@localhost:5433/bothot")
_T24_SUB = "sub-t24-sched"
_T24_SPACE = "T24调度空间"
# S6.2.1：biz 取 base64 形态（真实 `__biz` 值形如 `MjM5MjgwNTQ1MQ==`），保留 `T24` 前缀
# 是为了让 `_purge_t24` 的 `external_id LIKE 'T24%'` 仍能收敛命名空间。
_T24_BIZ = "T24SCHEDZHhkZg=="


# ---------------------------------------------------------------- 夹具 / 清场


def _purge_t24() -> None:
    """清 T2.4 命名空间残留（jobs 键前缀 `sync_account:t24-`，余经 FK 级联）。"""
    try:
        engine = create_engine(PG_DSN, connect_args={"connect_timeout": 3})
    except Exception:  # noqa: BLE001
        return
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM jobs WHERE idempotency_key LIKE :p"), {"p": "sync_account:t24-%"})
            conn.execute(text("DELETE FROM users WHERE sub = :s"), {"s": _T24_SUB})
            conn.execute(text("DELETE FROM sources WHERE external_id LIKE :p"), {"p": "T24%"})
            conn.execute(text("DELETE FROM knowledge_spaces WHERE name LIKE :p"), {"p": "T24%"})
    except Exception:  # noqa: BLE001
        return
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def _t24_guard() -> Iterator[None]:
    """PG 可达性守卫 + 用例前后清场（前后各一次，套件幂等）。"""
    try:
        engine = create_engine(PG_DSN, connect_args={"connect_timeout": 3})
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PG 不可达（{type(exc).__name__}），Docker 引擎恢复后复跑本用例")
    _purge_t24()
    yield
    _purge_t24()


def _factory():  # noqa: ANN202
    engine = create_async_engine(PG_DSN, pool_pre_ping=True, connect_args={"connect_timeout": 3})
    return engine, async_sessionmaker(engine, expire_on_commit=False)


class _Clock:
    """可控时钟：调度器算术断言不依赖真实时间流逝。"""

    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now = self.now + timedelta(**kwargs)


class _StubRunner:
    """可编程同步桩：按序吐出新增篇数（隔离调度算术，不碰 Manifest/Job 表）。"""

    def __init__(self, counts: list[int] | None = None, *, delay: float = 0.0) -> None:
        self._counts = list(counts or [])
        self.calls: list[str] = []
        self._delay = delay

    async def __call__(self, session: AsyncSession, sub: SourceSubscription, run_token: str) -> int:  # noqa: ARG002
        self.calls.append(sub.id)
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._counts.pop(0) if self._counts else 0


def _scheduler(factory, clock: _Clock, runner) -> IncrementalScheduler:  # noqa: ANN001
    """退避上限 8、空转 0（测试不睡）、时钟注入。

    `heartbeat_enabled=False`：本文件工厂直连共库真提交，开着的存活上报会留下
    运维可读的假存活信号（详见 `IncrementalScheduler.heartbeat_enabled` 的注释）。
    """
    return IncrementalScheduler(
        factory,
        settings=Settings(),
        sync_runner=runner,
        now_fn=clock,
        max_backoff_multiplier=8,
        idle_sleep_seconds=0.0,
        heartbeat_enabled=False,
    )


async def _seed_source(session: AsyncSession, biz: str = _T24_BIZ) -> Source:
    row = (
        await session.execute(select(Source).where(Source.type == "wechat_oa", Source.external_id == biz))
    ).scalar_one_or_none()
    if row is None:
        row = Source(type="wechat_oa", external_id=biz, name=biz, url=f"https://redfox.hk/{biz}")
        session.add(row)
        await session.flush()
    return row


async def _seed_sub(
    factory,  # noqa: ANN001
    *,
    sub_id: str,
    next_run_at: datetime,
    interval_minutes: int = 60,
    consecutive_empty: int = 0,
    status: str = "ACTIVE",
    biz: str = _T24_BIZ,
    anchor_hour: int | None = None,
) -> tuple[str, str, str]:
    """建 user + space + source + 订阅（显式 sub_id 以收敛命名空间）；返回 (sub_id, space_id, source_id)。"""
    async with factory() as session:
        user = await SqlAlchemyUserStore(session).upsert_by_sub(_T24_SUB, "t24@test.local", "T24")
        space = (
            await session.execute(
                select(KnowledgeSpace).where(KnowledgeSpace.user_id == user.id, KnowledgeSpace.name == _T24_SPACE)
            )
        ).scalar_one_or_none()
        if space is None:
            space = await SpaceRepository(session).create(user_id=user.id, name=_T24_SPACE)
        source = await _seed_source(session, biz)
        existing = await session.get(SourceSubscription, sub_id)
        if existing is None:
            session.add(
                SourceSubscription(
                    id=sub_id,
                    user_id=user.id,
                    source_id=source.id,
                    space_id=space.id,
                    sync_policy="auto",
                    sync_interval_minutes=interval_minutes,
                    sync_anchor_hour=anchor_hour,
                    next_run_at=next_run_at,
                    consecutive_empty_syncs=consecutive_empty,
                    status=status,
                )
            )
        await session.commit()
        return sub_id, space.id, source.id


class ArticleSeed(NamedTuple):
    """一篇清单行的真实形态（三键同时给出，调用方不许自己拼形状）。"""

    external_id: str
    url: str
    article_key: str
    title_hint: str
    content_hash: str


def _article_seed(prefix: str, index: int) -> ArticleSeed:
    external_id = hashlib.sha256(f"{prefix}{index}".encode()).hexdigest()[:32]
    url = (
        f"https://mp.weixin.qq.com/s?__biz={_T24_BIZ}&mid={2650000000 + index}&idx=1&sn={external_id[:16]}"
        f"&chksm=f2b6330c&from=timeline#wechat_redirect"
    )
    key = canonical_article_key(url)
    assert key.startswith("b:") and key.count(":") == 3, f"长链夹具必须解出 b: 支，实得 {key}"
    assert key != external_id, "两支键空间必须可区分，否则本夹具退化回被掩盖的形态"
    return ArticleSeed(
        external_id=external_id,
        url=url,
        article_key=key,
        title_hint=f"T24清单{external_id[:8]}",
        content_hash=f"hash-{external_id[:8]}",
    )


async def _seed_manifests(
    factory,  # noqa: ANN001
    source_id: str,
    count: int,
    *,
    prefix: str = "t24-w",  # noqa: ANN001
) -> list[ArticleSeed]:
    """铺 count 篇 DISCOVERED 清单行（= 1.2.1 _sync_manifests 的合法 PG 产物，非伪造抓取）。

    三个字段都必须按**生产者真实形态**铺（S6.2.1）：
    - `external_id` = 32 位小写 hex（渠道内幂等键，redfox `workUuid` 同形）；
    - `url` = 带 `__biz/mid/idx/sn` 的微信长链（不是"短链路径 + 伪 biz 参数"）；
    - `article_key` = `canonical_article_key(url)`，于是这一支是 `b:{biz}:{mid}:{idx}`，
      与 `external_id` **互不相等**——旧夹具让两者同串，Diff 的按键减就永远"看起来对"。
    """
    async with factory() as session:
        seeds = [_article_seed(prefix, i) for i in range(count)]
        for seed in seeds:
            session.add(
                ArticleManifest(
                    source_id=source_id,
                    external_id=seed.external_id,
                    # STEP-04 S4.4.1：Diff 按 `article_key` 减资产/减在途，铺数据必须带规范键
                    article_key=seed.article_key,
                    url=seed.url,
                    title=seed.title_hint,
                    content_hash=seed.content_hash,
                    status="DISCOVERED",
                )
            )
        await session.commit()
    return seeds


async def _mark_ingested_and_reshare(factory, source_id: str, seeds: list[ArticleSeed]) -> None:  # noqa: ANN001
    """把 seeds 变成"资产已 READY、清单回到 DISCOVERED"的合法存量（S6.2.1 的判据补强）。

    只置资产不改状态的话，本用例第三条断言是**空的**：`_populate_job_items` 已把这些行翻成
    ENQUEUED，而 Diff 的第一道谓词就是 `status == DISCOVERED` ⇒ 返回 0 条与"ready 键减没减对"
    无关，把 `ready_keys` 改成按 `external_id` 减也照样绿。改状态走真状态机（ENQUEUED→DISCOVERED
    是合法回退，生产里由批次 6 的失败重试 `_reopen_manifests` 产生），不是手写一个非法值。
    """
    async with factory() as session:
        for seed in seeds:
            session.add(
                ContentAsset(
                    source_id=source_id,
                    external_id=seed.article_key,  # 规范键，不是渠道内 workUuid（uq_asset_source_external 同键空间）
                    url=seed.url,
                    title=seed.title_hint,
                    content_hash=seed.content_hash,
                    content_markdown="x",
                    status="READY",
                )
            )
            row = (
                await session.execute(
                    select(ArticleManifest).where(
                        ArticleManifest.source_id == source_id,
                        ArticleManifest.external_id == seed.external_id,
                    )
                )
            ).scalar_one()
            validate_transition("manifest", row.status, "DISCOVERED")
            row.status = "DISCOVERED"
        await session.commit()


async def _read_sub(factory, sub_id: str) -> SourceSubscription:  # noqa: ANN001
    async with factory() as session:
        row = await session.get(SourceSubscription, sub_id)
        assert row is not None
        return row


async def _jobs_for(factory, sub_id: str) -> list[Job]:  # noqa: ANN001
    async with factory() as session:
        rows = await session.scalars(
            select(Job).where(Job.idempotency_key.like(f"sync_account:{sub_id}%")).order_by(Job.created_at)
        )
        return list(rows)


async def _items_for(factory, job_id: str) -> list[JobItem]:  # noqa: ANN001
    async with factory() as session:
        rows = await session.scalars(select(JobItem).where(JobItem.job_id == job_id))
        return list(rows)


# ---------------------------------------------------------------- ① 纯函数：退避算术


def test_backoff_multiplier_sequence() -> None:
    """退避倍数序列：0→1（基准），1→2，2→4，3→8，4→8（cap=8 截断）。"""
    s = _scheduler(None, _Clock(datetime(2026, 9, 22, tzinfo=UTC)), _StubRunner())  # type: ignore[arg-type]
    assert [s.backoff_multiplier(n) for n in (0, 1, 2, 3, 4, 5)] == [1, 2, 4, 8, 8, 8]


def test_next_run_at_math() -> None:
    """下次触发时间 = now + interval × 退避倍数（60min 基准）。"""
    now = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    s = _scheduler(None, _Clock(now), _StubRunner())  # type: ignore[arg-type]
    assert s.next_run_at(now, 60, 0) == now + timedelta(minutes=60)
    assert s.next_run_at(now, 60, 1) == now + timedelta(minutes=120)
    assert s.next_run_at(now, 60, 3) == now + timedelta(minutes=480)
    assert s.next_run_at(now, 60, 9) == now + timedelta(minutes=480)  # cap


def test_next_run_at_anchored_lands_on_daily_hour() -> None:
    """锚定：结果必须落在调度器时区的该整点上，且严格在未来。"""
    now = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)  # = 上海 20:00，已过 10:00
    s = _scheduler(None, _Clock(now), _StubRunner())  # type: ignore[arg-type]
    out = s.next_run_at(now, 1440, 0, 10)
    assert out.astimezone(ZoneInfo("Asia/Shanghai")) == datetime(2026, 9, 23, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert out > now, "锚点必须指向未来，不得原地重放"


def test_next_run_at_anchored_just_before_hour_picks_same_day() -> None:
    """09:59（上海）→ 当天 10:00，不等到次日。"""
    sh = ZoneInfo("Asia/Shanghai")
    now = datetime(2026, 9, 22, 1, 59, 59, tzinfo=UTC)  # = 上海 09:59:59
    s = _scheduler(None, _Clock(now), _StubRunner())  # type: ignore[arg-type]
    assert s.next_run_at(now, 1440, 0, 10).astimezone(sh).hour == 10
    assert s.next_run_at(now, 1440, 0, 10).astimezone(sh).day == 22


def test_next_run_at_anchored_exactly_on_hour_rolls_forward() -> None:
    """恰好 10:00:00 触发后，下一次必须是次日 10:00（严格未来，否则同点重放成紧密循环）。"""
    sh = ZoneInfo("Asia/Shanghai")
    now = datetime(2026, 9, 22, 2, 0, 0, tzinfo=UTC)  # = 上海 10:00:00
    s = _scheduler(None, _Clock(now), _StubRunner())  # type: ignore[arg-type]
    assert s.next_run_at(now, 1440, 0, 10).astimezone(sh) == datetime(2026, 9, 23, 10, 0, tzinfo=sh)


def test_next_run_at_anchored_backoff_steps_whole_days() -> None:
    """锚定 + 空轮询退避：按整天往后跳，仍对准锚点（mult=2 → 次日同点，mult=4 → 第四日同点）。"""
    sh = ZoneInfo("Asia/Shanghai")
    now = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)  # 上海 20:00
    s = _scheduler(None, _Clock(now), _StubRunner())  # type: ignore[arg-type]
    for empties, day in ((0, 23), (1, 24), (2, 26), (3, 30), (9, 30)):  # 1×/2×/4×/8×cap/8×cap
        out = s.next_run_at(now, 1440, empties, 10)
        got = out.astimezone(sh)
        assert (got.day, got.hour) == (day, 10), f"空轮询 {empties} 次应落在 9/{day} 10:00"


def test_next_run_at_anchored_sub_daily_interval_still_daily() -> None:
    """间隔小于一天时锚定仍只触发一次/天（步长向上取整到日），不会退化成一天多次。"""
    sh = ZoneInfo("Asia/Shanghai")
    now = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
    s = _scheduler(None, _Clock(now), _StubRunner())  # type: ignore[arg-type]
    first = s.next_run_at(now, 360, 0, 10)
    second = s.next_run_at(first, 360, 0, 10)
    assert second.astimezone(sh).day == first.astimezone(sh).day + 1
    assert second.astimezone(sh).hour == 10


async def test_anchored_watermark_stays_on_anchor_after_empty_sync() -> None:
    """集成：锚定订阅空轮询后，水位仍对准下一个整点（而非滑成 now+interval）。"""
    engine, factory = _factory()
    try:
        clock = _Clock(datetime(2026, 9, 22, 2, 30, tzinfo=UTC))  # 上海 10:30
        sub_id, _, _ = await _seed_sub(
            factory,
            sub_id="t24-anchor",
            next_run_at=clock.now - timedelta(minutes=30),  # 已到点（上海 10:00 那轮）
            interval_minutes=1440,
            anchor_hour=10,
        )
        sched = _scheduler(factory, clock, _StubRunner([0]))
        assert await sched.run_once() == 1

        sub = await _read_sub(factory, sub_id)
        assert sub.consecutive_empty_syncs == 1
        got = sub.next_run_at
        assert got is not None
        sh = got.astimezone(ZoneInfo("Asia/Shanghai"))
        assert (sh.day, sh.hour, sh.minute) == (24, 10, 0), (
            f"空轮询后退避应落到次日 10:00（mult=2 → 基准锚 9/23 再跳 1 天），实际 {sh.isoformat()}"
        )
    finally:
        await engine.dispose()


async def test_run_once_runs_due_subscriptions_in_parallel() -> None:
    """并发执行度：两条到期订阅在一个 run_once 内**并行**跑完（非串行排队）。

    判据用**会合点**而非墙钟窗（S35.3，P-52/P-71）：每个 runner 进入时置位自己的
    Event、再等对方的——真并行 ⇒ 双方都能越过会合点；串行 ⇒ 先到的永远等不到
    后者，`wait_for` 显式超时判红。旧判据"两段 50ms sleep 的区间是否重叠"仍是
    50 毫秒的墙钟窗：满负载下第二个任务的起步被建连/认领拖过第一个的 end，
    好调度器被读成串行（P-52 两次全量首跑实测、P-71 拆解了机理）。会合点判据
    与机器负载无关：慢只会让用例更久，不会把并行读成串行。
    """
    engine, factory = _factory()
    try:
        clock = _Clock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))

        class _RendezvousRunner:
            """第 i 个进场的任务置位自己的 Event，再等对方的——会合即证并行。"""

            def __init__(self) -> None:
                self.arrived = [asyncio.Event(), asyncio.Event()]
                self._entered = 0

            async def __call__(self, session, sub, run_token):  # noqa: ANN001,ARG002
                i = self._entered
                self._entered += 1
                mine, other = self.arrived[i], self.arrived[1 - i]
                mine.set()
                await asyncio.wait_for(other.wait(), timeout=30)
                return 0

        for i in range(2):
            await _seed_sub(
                factory,
                sub_id=f"t24-par{i}",
                next_run_at=clock.now - timedelta(minutes=1),
                biz=f"T24PAR{i}",
            )
        runner = _RendezvousRunner()
        sched = _scheduler(factory, clock, runner)
        sched._concurrency = 2
        assert await sched.run_once() == 2, "两条都必须跑完（任一会合超时都会让它 <2）"
        assert all(e.is_set() for e in runner.arrived), "两个 runner 都必须真实进场"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------- ② 触发窗口


async def test_trigger_window_only_due() -> None:
    """到期（next_run_at<=now）触发；未来不触发；非 ACTIVE 不触发。"""
    engine, factory = _factory()
    try:
        clock = _Clock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
        _sub_due, _, _ = await _seed_sub(factory, sub_id="t24-due", next_run_at=clock.now - timedelta(minutes=1))
        _sub_future, _, _ = await _seed_sub(
            factory, sub_id="t24-future", next_run_at=clock.now + timedelta(minutes=30), biz="T24FUTURE"
        )
        _sub_paused, _, _ = await _seed_sub(
            factory,
            sub_id="t24-paused",
            next_run_at=clock.now - timedelta(minutes=5),
            status="PAUSED",
            biz="T24PAUSED",
        )
        runner = _StubRunner([1])
        processed = await _scheduler(factory, clock, runner).run_once()

        assert processed == 1, "仅到期且 ACTIVE 的一条应被处理"
        assert runner.calls == ["t24-due"], runner.calls
        future = await _read_sub(factory, _sub_future)
        paused = await _read_sub(factory, _sub_paused)
        assert future.next_run_at == clock.now + timedelta(minutes=30), "未来订阅水位不得被触碰"
        assert paused.next_run_at == clock.now - timedelta(minutes=5), "非 ACTIVE 不触发"
    finally:
        await engine.dispose()


async def test_nonempty_run_resets_counter_and_sets_base_interval() -> None:
    """非空轮询 → 计数清零、水位 = now + 基准间隔、last_success_at 落时间。"""
    engine, factory = _factory()
    try:
        clock = _Clock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
        sub_id, _, _ = await _seed_sub(
            factory,
            sub_id="t24-reset",
            next_run_at=clock.now - timedelta(minutes=1),
            consecutive_empty=3,  # 先欠着 3 次空轮询
        )
        runner = _StubRunner([5])
        assert await _scheduler(factory, clock, runner).run_once() == 1

        sub = await _read_sub(factory, sub_id)
        assert sub.consecutive_empty_syncs == 0, "发现新篇须清零空轮询计数"
        assert sub.next_run_at == clock.now + timedelta(minutes=60), "恢复基准间隔"
        assert sub.last_success_at == clock.now
    finally:
        await engine.dispose()


# ---------------------------------------------------------------- ③ 退避序列


async def test_backoff_sequence_across_successive_empty_runs() -> None:
    """连续空轮询 → 水位间隔序列 2×,4×,8×,8×（cap）——逐轮断言。"""
    engine, factory = _factory()
    try:
        clock = _Clock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
        sub_id, _, _ = await _seed_sub(
            factory,
            sub_id="t24-backoff",
            next_run_at=clock.now - timedelta(minutes=1),
            interval_minutes=60,
        )
        sched = _scheduler(factory, clock, _StubRunner())  # 恒空轮询
        expected_mult = [2, 4, 8, 8]
        expected_empty = [1, 2, 3, 4]

        for mult, empty in zip(expected_mult, expected_empty, strict=True):
            before = clock.now
            assert await sched.run_once() == 1
            sub = await _read_sub(factory, sub_id)
            assert sub.consecutive_empty_syncs == empty, sub.consecutive_empty_syncs
            assert sub.next_run_at == before + timedelta(minutes=60 * mult), (
                f"第 {empty} 次空轮询应退避 {mult}×，实际水位 {sub.next_run_at}"
            )
            # 时间推进到下次触发点（=刚写入的水位）以驱动下一轮
            clock.now = sub.next_run_at
        # 无新篇时不得建任何 Job
        assert await _jobs_for(factory, sub_id) == [], "空轮询不得建 Job"
    finally:
        await engine.dispose()


async def test_nonempty_after_empties_resets_backoff() -> None:
    """空轮询若干轮后发现新篇 → 计数清零、水位回到基准间隔。"""
    engine, factory = _factory()
    try:
        clock = _Clock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
        sub_id, _, _ = await _seed_sub(factory, sub_id="t24-recover", next_run_at=clock.now, interval_minutes=60)
        runner = _StubRunner([0, 0, 3])  # 空、空、有 3 篇
        sched = _scheduler(factory, clock, runner)

        for _ in range(2):
            await sched.run_once()
            clock.now = (await _read_sub(factory, sub_id)).next_run_at
        mid = await _read_sub(factory, sub_id)
        assert mid.consecutive_empty_syncs == 2

        before = clock.now
        assert await sched.run_once() == 1
        sub = await _read_sub(factory, sub_id)
        assert sub.consecutive_empty_syncs == 0
        assert sub.next_run_at == before + timedelta(minutes=60)
    finally:
        await engine.dispose()


async def test_inactive_matcher_no_next_run_not_claimed() -> None:
    """next_run_at 为 NULL（未排程）的订阅不参与认领（窗口判定要求非空）。"""
    engine, factory = _factory()
    try:
        clock = _Clock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
        await _seed_sub(factory, sub_id="t24-null", next_run_at=None)  # type: ignore[arg-type]
        assert await _scheduler(factory, clock, _StubRunner([1])).run_once() == 0
    finally:
        await engine.dispose()


# ---------------------------------------------------------------- ④ 增量入列（真 runner）


async def test_incremental_sync_creates_job_with_diff_items() -> None:
    """真 runner：Diff 新篇 → 建 run-scoped Job + PENDING JobItem，且不重复入列在途篇。"""
    engine, factory = _factory()
    try:
        clock = _Clock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
        sub_id, _space_id, source_id = await _seed_sub(
            factory, sub_id="t24-incr", next_run_at=clock.now - timedelta(minutes=1), interval_minutes=60
        )
        seeds = await _seed_manifests(factory, source_id, 2)
        sched = IncrementalScheduler(
            factory,
            settings=Settings(),
            now_fn=clock,
            idle_sleep_seconds=0.0,
            heartbeat_enabled=False,
        )

        assert await sched.run_once() == 1
        jobs = await _jobs_for(factory, sub_id)
        assert len(jobs) == 1, "一轮非空增量应恰建 1 个 Job"
        assert jobs[0].idempotency_key.startswith(f"sync_account:{sub_id}:"), jobs[0].idempotency_key
        items = await _items_for(factory, jobs[0].id)
        assert sorted(i.external_id for i in items) == sorted(s.external_id for s in seeds)
        assert all(i.status == "PENDING" for i in items)

        sub = await _read_sub(factory, sub_id)
        assert sub.consecutive_empty_syncs == 0
        assert sub.next_run_at == clock.now + timedelta(minutes=60)

        # 在途去重：Job 仍 QUEUED（篇未入库）→ 下轮 Diff 为空，不得重复入列
        clock.now = sub.next_run_at
        assert await sched.run_once() == 1
        jobs2 = await _jobs_for(factory, sub_id)
        assert len(jobs2) == 1, "在途篇不得重复入列（防轮询撞车）"
        sub2 = await _read_sub(factory, sub_id)
        assert sub2.consecutive_empty_syncs == 1, "在途去重后本轮=空轮询"

        # 已入库去重：置 READY 资产（按规范键）+ 清单回 DISCOVERED + Job 终态 → 仍不重复入列。
        # Job 必须先进终态：否则"第二轮 0 条"可以是**在途键减**救的，ready 键支写错也照样绿。
        await _mark_ingested_and_reshare(factory, source_id, seeds)
        async with factory() as session:
            job = await session.get(Job, jobs[0].id)
            assert job is not None
            job.status = "SUCCEEDED"
            await session.commit()
        clock.now = sub2.next_run_at
        assert await sched.run_once() == 1
        assert len(await _jobs_for(factory, sub_id)) == 1, "已入库篇不得再入列"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------- ⑤ 并发认领（SKIP LOCKED）


async def test_concurrent_schedulers_claim_distinct_subscriptions() -> None:
    """PG 双调度器并发 → 到期订阅不重不漏：每订阅恰被处理一次（SET 锁跳过已锁行）。"""
    engine, factory = _factory()
    try:
        clock = _Clock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
        ids = []
        for i in range(4):
            sid, _, _ = await _seed_sub(
                factory,
                sub_id=f"t24-conc-{i}",
                next_run_at=clock.now - timedelta(minutes=1),
                biz=f"T24CONC{i}",
            )
            ids.append(sid)

        runner = _StubRunner(delay=0.03)  # 持锁窗口拉长以逼出并发交叠
        s1 = _scheduler(factory, clock, runner)
        s2 = _scheduler(factory, clock, runner)
        totals = await asyncio.gather(s1.run_once(), s2.run_once())

        assert sum(totals) == 4, f"4 条到期订阅应恰处理 4 次，实际 {totals}"
        for sid in ids:
            sub = await _read_sub(factory, sid)
            assert sub.consecutive_empty_syncs == 1, f"{sid} 被重复处理（计数 {sub.consecutive_empty_syncs}）"
        assert sorted(runner.calls) == sorted(ids), "每次调用应对应唯一订阅"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------- ⑥ 生命周期 / 入口


async def test_run_forever_stops_on_event() -> None:
    """stop 置位即优雅退出（不空转挂死）。"""
    engine, factory = _factory()
    try:
        clock = _Clock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC))
        stop = asyncio.Event()
        sched = _scheduler(factory, clock, _StubRunner())
        task = asyncio.create_task(sched.run_forever(stop))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
        assert task.done() and not task.cancelled()
    finally:
        await engine.dispose()


async def test_module_importable_and_exported() -> None:
    """模块可导入且导出核心符号（compose 入口 `python -m app.services.scheduler` 前置）。"""
    from app.services import scheduler as mod

    assert hasattr(mod, "IncrementalScheduler")
    assert hasattr(mod, "make_default_sync_runner")
    assert hasattr(mod, "_main")


async def test_repository_claim_due_is_read_only_on_empty() -> None:
    """无可取行时 claim_due 返回 None（空表/全未来 → 不误触发）。"""
    from app.repositories.subscription import SourceSubscriptionRepository

    engine, factory = _factory()
    try:
        async with factory() as session:
            repo = SourceSubscriptionRepository(session)
            assert await repo.claim_due(datetime(2000, 1, 1, tzinfo=UTC)) is None
            assert await repo.list_due(datetime(2000, 1, 1, tzinfo=UTC)) == []
            await session.rollback()
    finally:
        await engine.dispose()


async def test_job_count_baseline_smoke() -> None:
    """冒烟：jobs 表可计数（保证清场 SQL 的表名/连接口径正确）。"""
    engine, factory = _factory()
    try:
        async with factory() as session:
            n = await session.scalar(select(func.count()).select_from(Job))
            assert isinstance(n, int)
    finally:
        await engine.dispose()


class _StubReconciler:
    """文档状态推进桩：记录调用次数，可编程序列/抛错（不碰真实引擎）。"""

    def __init__(self, results: list[int] | None = None, *, raise_exc: bool = False) -> None:
        self._results = list(results or [])
        self.calls = 0
        self._raise = raise_exc

    async def __call__(self, session: AsyncSession) -> int:  # noqa: ARG002
        self.calls += 1
        if self._raise:
            raise RuntimeError("推进失败")
        return self._results.pop(0) if self._results else 0


async def test_run_once_reconciles_docs_when_no_due_subscriptions() -> None:
    """空转轮次也推进文档状态：无到期订阅时批量/订阅入库的文档不应永远停在 INDEXED。

    实测缺陷（2026-09-25）：ingest 触发引擎异步入库后即返回，doc 状态只在有人调
    get_doc_ingest_status 时才被懒推进；批量入库只轮询 Job，不轮询单篇文档状态，
    于是任务中心报成功、文档清单却永远显示「采集中」。
    """
    engine, factory = _factory()
    try:
        recon = _StubReconciler([3])
        # 时钟取远早于任何订阅 created_at 的时刻：连库目标按 AIDEANBOT_TEST_PG_DSN 两级
        # 解析（未设则 skip，原因见 conftest SKIP_UNSET_REASON），指向共用库时他人订阅的
        # next_run_at 都在
        # 2026 年后，远早时钟下全部「未到期」——「无到期订阅」这一前提才不随库内
        # 数据漂移（2026-09-26 实测：线上有一条 next_run_at=2026-09-27 的锚定订阅，
        # 2030 时钟下它到期，`== 0` 断言必败）。
        sched = _scheduler(factory, _Clock(datetime(2000, 1, 1, tzinfo=UTC)), _StubRunner())
        sched._reconcile = recon
        assert await sched.run_once() == 0  # 无到期订阅
        assert recon.calls == 1, "无到期订阅也必须推进一次文档状态"
    finally:
        await engine.dispose()


async def test_doc_reconcile_failure_does_not_block_subscriptions() -> None:
    """推进失败只跳过本轮推进，订阅调度照常触发（不因兜底路径拖垮主循环）。"""
    engine, factory = _factory()
    try:
        await _seed_sub(
            factory,
            sub_id="t24-recon-sub",
            next_run_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        runner = _StubRunner([0])
        sched = _scheduler(factory, _Clock(datetime(2030, 1, 1, tzinfo=UTC)), runner)
        sched._reconcile = _StubReconciler(raise_exc=True)
        assert await sched.run_once() == 1
        assert runner.calls == ["t24-recon-sub"]
    finally:
        await engine.dispose()


# ── S35.6 / 三连跑收口：scheduler.py 的墙钟分支确定覆盖 ─────────────────────────
#
# `_maybe_enqueue_daily_jobs` 用的是**不可注入的** `datetime.now(self._tz)`（scheduler.py:409）
# ——CI 几点跑决定 06:30/06:35 两个门开不开；reconcile 的默认实现体内有无待推进文档取决于
# 同批其它用例留下的 DB 状态。run 40010753485 三次 attempt 的 TOTAL 88.26/88.34/88.37，
# 逐模块差分唯一漂移模块就是 scheduler.py（missing 75↔67）。源码不在本卡允许面
# ⇒ 测试侧冻结模块级 datetime（monkeypatch，源码零改动）+ 种一份非终态文档把
# reconcile 路径钉成确定覆盖。


class _FrozenDatetime(datetime):
    """子类只重写 now()：模块内其它 datetime 用法（构造/strptime）全部继承真类。"""

    _frozen: datetime = datetime(2026, 10, 24, 7, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    @classmethod
    def now(cls, tz=None):  # noqa: ANN001
        base = cls._frozen
        return base if tz is None else base.astimezone(tz)


async def test_daily_jobs_enqueue_after_0630_with_frozen_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """上海 07:00（两个门都开）⇒ daily_report 与 hot_cluster 各入队一条，幂等戳按日期。"""
    monkeypatch.setattr(scheduler_module, "datetime", _FrozenDatetime)
    engine, factory = _factory()
    try:
        async with factory() as session:
            session.add(
                User(
                    id="u-s35-daily",
                    sub="sub-s35-daily",
                    email="s35daily@test.local",
                    role="admin",
                )
            )
            await session.commit()
        sched = _scheduler(factory, _Clock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC)), _StubRunner())
        await sched._maybe_enqueue_daily_jobs()
        assert sched._last_daily_date == "2026-10-24"
        assert sched._last_cluster_date == "2026-10-24"
        async with factory() as session:
            keys = set(
                (
                    await session.scalars(
                        select(Job.idempotency_key).where(Job.type.in_(["daily_report", "hot_cluster"]))
                    )
                ).all()
            )
        assert "daily_report:2026-10-23" in keys, f"daily_report 幂等戳缺失：{sorted(keys)}"
        assert "hot_cluster:2026-10-24:1" in keys, f"hot_cluster 幂等戳缺失：{sorted(keys)}"
    finally:
        await engine.dispose()


async def test_daily_jobs_skip_before_0630_with_frozen_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """上海 03:00（两个门都关）⇒ 不入队、幂等戳不动——这是"门关"一侧的确定覆盖。"""

    class _EarlyDatetime(_FrozenDatetime):
        _frozen = datetime(2026, 10, 24, 3, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    monkeypatch.setattr(scheduler_module, "datetime", _EarlyDatetime)
    engine, factory = _factory()
    try:
        sched = _scheduler(factory, _Clock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC)), _StubRunner())
        await sched._maybe_enqueue_daily_jobs()
        assert sched._last_daily_date is None and sched._last_cluster_date is None
        async with factory() as session:
            keys = set(
                (
                    await session.scalars(
                        select(Job.idempotency_key).where(Job.type.in_(["daily_report", "hot_cluster"]))
                    )
                ).all()
            )
        leaked = [k for k in keys if k.startswith(("daily_report:", "hot_cluster:"))]
        assert not leaked, f"门关侧不得入队：{leaked}"
    finally:
        await engine.dispose()


async def test_default_doc_reconciler_covers_pending_docs_deterministically() -> None:
    """种一份 FETCHED+file_id 的非终态文档 ⇒ 默认 reconcile 的主体行确定被走到。

    LangBot 在 CI 不可达 ⇒ `get_doc_ingest_status` 抛错 ⇒ except-continue 分支确定；
    「无待推进文档」的早退分支由"无文档"的另一侧确定。两态都钉死后，
    reconcile 主体行的覆盖不再取决于同批其它用例留下的 DB 状态。"""
    engine, factory = _factory()
    try:
        _user, space, source = await _seed_sub(
            factory, sub_id="t35-rec", next_run_at=datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
        )
        async with factory() as session:
            asset = ContentAsset(
                source_id=source,
                external_id="s35-rec-asset",
                url="https://mp.weixin.qq.com/s/s35-rec",
                title="S35 reconcile 种子",
                content_hash="h-s35-rec",
                content_markdown="# s35",
                category="其他",
            )
            session.add(asset)
            await session.flush()
            session.add(
                KnowledgeDocument(
                    asset_id=asset.id,
                    space_id=space,
                    langbot_file_id="file-s35-rec",
                    status="FETCHED",
                )
            )
            await session.commit()
        sched = _scheduler(factory, _Clock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC)), _StubRunner())
        advanced = await sched._reconcile_docs()
        assert advanced == 0, "LangBot 不可达 ⇒ 推进数必为 0（单篇失败不中断）"
        # 早退分支：空库（无待推进文档）⇒ 0
        engine2, factory2 = _factory()
        try:
            sched2 = _scheduler(factory2, _Clock(datetime(2026, 9, 22, 12, 0, tzinfo=UTC)), _StubRunner())
            assert await sched2._reconcile_docs() == 0
        finally:
            await engine2.dispose()
    finally:
        await engine.dispose()
