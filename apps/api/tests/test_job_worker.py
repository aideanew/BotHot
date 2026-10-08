"""T2.3 Job 执行器验收：状态机收敛 + SKIP LOCKED 双 worker 并发安全 + 崩溃自愈 + 限流暂停。

机器门口径（大纲 v1.4 §8.1 序2 验收锚）：
- Job 状态机 `QUEUED → RUNNING → SUCCEEDED / PARTIAL_SUCCESS / FAILED`（越级 → 30005）；
- JobItem `PENDING → RUNNING → SUCCEEDED / FAILED`；
- **SKIP LOCKED 并发安全：PG 双 worker 同取不同项**（job 级 + item 级各一断言）；
- 崩溃自愈：RUNNING 心跳超时 → Job 回退 QUEUED + item 回退 PENDING；
- 限流暂停：保持 RUNNING + `paused:rate_limited` 标记，item 留 PENDING（可续）。

连库口径（真提交连接，与 T2.7 同法）：PG 不可达 → skip 并标注原因（CI 无 PG 时体面
跳过，不染红门禁）；用例级清场保证套件自身幂等可重复。
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.errors import (
    JobStateInvalidError,
    RateLimitedUpstreamError,
    SourceUrlUnrecognizedError,
)
from app.models.entities import Job, JobItem, KnowledgeSpace, User
from app.repositories.job import JobItemRepository, JobRepository
from app.repositories.space import SpaceRepository
from app.repositories.user import SqlAlchemyUserStore
from app.services.job_worker import JobWorker

PG_DSN = os.environ.get(
    "AIDEANBOT_TEST_PG_DSN", "postgresql+psycopg://bothot:bothot@localhost:5433/bothot"
)
_T23_SUB = "sub-t23-worker"
_T23_SPACE = "T23执行器空间"
_T23_KEY_PREFIX = "t23:"
_T23_URL = "https://mp.weixin.qq.com/s/t23-{n}?biz=MjM5MjgwNTQ1MQ==&hid=t23"


def _purge_t23() -> None:
    """清 T2.7/T2.3 命名空间残留，保证套件可重复（连库真提交路径是唯一残留源）。"""
    try:
        engine = create_engine(PG_DSN, connect_args={"connect_timeout": 3})
    except Exception:  # noqa: BLE001
        return
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM jobs WHERE idempotency_key LIKE :p"), {"p": f"{_T23_KEY_PREFIX}%"})
            conn.execute(text("DELETE FROM users WHERE sub = :s"), {"s": _T23_SUB})
            conn.execute(text("DELETE FROM knowledge_spaces WHERE name LIKE :p"), {"p": "T23%"})
    except Exception:  # noqa: BLE001
        return
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def _t23_guard() -> Iterator[None]:
    """PG 可达性守卫 + 用例前后清场（前后各清一次，套件幂等）。"""
    try:
        engine = create_engine(PG_DSN, connect_args={"connect_timeout": 3})
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PG 不可达（{type(exc).__name__}），Docker 引擎恢复后复跑本用例")
    _purge_t23()
    yield
    _purge_t23()


class _StubIngest:
    """可编程入库桩：记录调用序，按 url 映射成功/失败/限流。"""

    def __init__(
        self,
        *,
        fail: set[str] | None = None,
        throttle: set[str] | None = None,
        domain_error: set[str] | None = None,
    ) -> None:
        self.calls: list[str] = []
        self._fail = fail or set()
        self._throttle = throttle or set()
        self._domain_error = domain_error or set()

    async def __call__(self, session, space_id: str, url: str) -> dict[str, object]:  # noqa: ANN001
        self.calls.append(url)
        if url in self._throttle:
            raise RateLimitedUpstreamError("RedFox 限频（4004）")
        if url in self._fail:
            raise RuntimeError("stub ingest 失败")
        if url in self._domain_error:
            raise SourceUrlUnrecognizedError("页面不是公众号文章（锚点缺失）")
        return {"docId": f"doc-{url[-3:]}", "status": "INDEXED"}


def _factory():  # noqa: ANN202
    engine = create_async_engine(PG_DSN, pool_pre_ping=True, connect_args={"connect_timeout": 3})
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _worker(session_factory, ingest: _StubIngest) -> JobWorker:  # noqa: ANN001
    """item 间隔置 0（测试不睡），max_retries=1（快速触顶 FAILED），自愈阈值 1 秒。

    `heartbeat_enabled=False`：本文件的工厂直连共库真提交，开着的存活上报会留下
    **运维可读的假存活信号**（详见 `JobWorker.heartbeat_enabled` 的注释）。
    """
    return JobWorker(
        session_factory,
        ingest,
        settings=Settings(),
        item_interval_seconds=0.0,
        max_item_retries=1,
        stale_job_seconds=1,
        idle_sleep_seconds=0.0,
        heartbeat_enabled=False,
    )


async def _seed_job(session_factory, *, urls: list[str], key: str) -> str:  # noqa: ANN001
    """建 user + space + Job(QUEUED) + N 个 PENDING JobItem（真提交）。"""
    async with session_factory() as session:
        user = await SqlAlchemyUserStore(session).upsert_by_sub(_T23_SUB, "t23@test.local", "T23")
        space = (
            await session.execute(
                select(KnowledgeSpace).where(
                    KnowledgeSpace.user_id == user.id, KnowledgeSpace.name == _T23_SPACE
                )
            )
        ).scalar_one_or_none()
        if space is None:
            space = await SpaceRepository(session).create(user_id=user.id, name=_T23_SPACE)
        job_repo = JobRepository(session)
        job, created = await job_repo.create_or_get(
            type="sync_account",
            user_id=user.id,
            payload=json.dumps({"space_id": space.id, "source_id": ""}),
            idempotency_key=f"{_T23_KEY_PREFIX}{key}",
        )
        if created:
            await job_repo.set_status(job.id, "QUEUED")
            item_repo = JobItemRepository(session)
            for u in urls:
                await item_repo.create(job_id=job.id, external_id=u[-8:], url=u)
        await session.commit()
        return job.id


async def _job_status(session_factory, job_id: str) -> tuple[str, str]:  # noqa: ANN001
    async with session_factory() as session:
        job = await JobRepository(session).get_by_id(job_id)
        assert job is not None
        return job.status, job.error


async def _item_statuses(session_factory, job_id: str) -> dict[str, int]:  # noqa: ANN001
    async with session_factory() as session:
        return await JobItemRepository(session).counts(job_id)


# ---------------------------------------------------------------- ① 状态机收敛


async def test_all_items_succeed_job_succeeded() -> None:
    """全篇成功 → Job SUCCEEDED，item 全 SUCCEEDED（QUEUED→RUNNING→SUCCEEDED）。"""
    engine, factory = _factory()
    try:
        urls = [_T23_URL.format(n=n) for n in (1, 2, 3)]
        job_id = await _seed_job(factory, urls=urls, key="ok")
        ingest = _StubIngest()
        assert await _worker(factory, ingest).run_once() is True

        status, error = await _job_status(factory, job_id)
        assert status == "SUCCEEDED", f"预期 SUCCEEDED，实际 {status}/{error}"
        counts = await _item_statuses(factory, job_id)
        assert counts == {"total": 3, "succeeded": 3, "failed": 0, "pending": 0}, counts
        assert sorted(ingest.calls) == sorted(urls), "每篇恰调用一次"
    finally:
        await engine.dispose()


async def test_partial_success_when_one_item_fails() -> None:
    """有成有败 → Job PARTIAL_SUCCESS（30005 语义），失败 item 计 FAILED。"""
    engine, factory = _factory()
    try:
        urls = [_T23_URL.format(n=n) for n in (1, 2, 3)]
        job_id = await _seed_job(factory, urls=urls, key="partial")
        ingest = _StubIngest(fail={urls[1]})
        await _worker(factory, ingest).run_once()

        status, error = await _job_status(factory, job_id)
        assert status == "PARTIAL_SUCCESS", f"预期 PARTIAL_SUCCESS，实际 {status}/{error}"
        counts = await _item_statuses(factory, job_id)
        assert counts == {"total": 3, "succeeded": 2, "failed": 1, "pending": 0}, counts
        # 失败篇已按 max_retries=1 退避重试过一次（首跑 + 一次重试 = 2 次调用）
        assert ingest.calls.count(urls[1]) == 2, ingest.calls
    finally:
        await engine.dispose()


async def test_all_items_fail_job_failed() -> None:
    """全篇失败 → Job FAILED。"""
    engine, factory = _factory()
    try:
        urls = [_T23_URL.format(n=n) for n in (1, 2)]
        job_id = await _seed_job(factory, urls=urls, key="allfail")
        await _worker(factory, _StubIngest(fail=set(urls))).run_once()

        status, _ = await _job_status(factory, job_id)
        assert status == "FAILED"
        counts = await _item_statuses(factory, job_id)
        assert counts["succeeded"] == 0 and counts["failed"] == 2
    finally:
        await engine.dispose()


async def test_failed_item_error_text_shaped_for_consumers() -> None:
    """失败原因面向消费者：业务异常只留错误码+文案，未预期异常才保留类名。

    实测缺陷：kb.py 漏引 SourceUrlUnrecognizedError，非文章链接在重试分支抛 NameError，
    篇目明细显示 "NameError: name 'SourceUrlUnrecognizedError' is not defined"。
    """
    engine, factory = _factory()
    try:
        urls = [_T23_URL.format(n=n) for n in (1, 2)]
        job_id = await _seed_job(factory, urls=urls, key="errtext")
        await _worker(
            factory, _StubIngest(fail={urls[0]}, domain_error={urls[1]})
        ).run_once()

        async with factory() as session:
            rows = (
                await session.execute(
                    select(JobItem.url, JobItem.error).where(JobItem.job_id == job_id)
                )
            ).all()

        by_url = {url: err for url, err in rows}
        assert by_url[urls[0]] == "RuntimeError: stub ingest 失败", by_url
        assert "20001" in by_url[urls[1]], by_url
        assert "SourceUrlUnrecognizedError" not in by_url[urls[1]], by_url
        assert "NameError" not in "".join(by_url.values()), by_url
    finally:
        await engine.dispose()


async def test_permanent_domain_error_fails_without_retry() -> None:
    """不可重试的域错误一次即 FAILED（不占 max_retries、不重复抓上游）。

    实测缺陷（2026-09-25 假链接批次）：worker 把「链接不是公众号文章」当普通失败退避重试
    3 次，retry_count=3、整篇耗时 ~14s，而结果永远不变，纯浪费上游额度。
    """
    engine, factory = _factory()
    try:
        urls = [_T23_URL.format(n=n) for n in (1, 2)]
        job_id = await _seed_job(factory, urls=urls, key="permanent")
        ingest = _StubIngest(domain_error={urls[0]}, fail={urls[1]})
        await _worker(factory, ingest).run_once()

        async with factory() as session:
            rows = (
                await session.execute(
                    select(
                        JobItem.url, JobItem.status, JobItem.retry_count
                    ).where(JobItem.job_id == job_id)
                )
            ).all()

        by_url = {url: (status, int(retry or 0)) for url, status, retry in rows}
        assert by_url[urls[0]] == ("FAILED", 0), by_url
        assert ingest.calls.count(urls[0]) == 1, ingest.calls
        # 普通失败仍按 max_retries=1 重试一次：域错误分支不得误伤重试口径
        assert by_url[urls[1]] == ("FAILED", 1), by_url
        assert ingest.calls.count(urls[1]) == 2, ingest.calls
    finally:
        await engine.dispose()


async def test_empty_manifest_job_failed_with_reason() -> None:
    """空清单（0 item）→ Job FAILED + no_items 语义（不冒充成功）。"""
    engine, factory = _factory()
    try:
        job_id = await _seed_job(factory, urls=[], key="empty")
        await _worker(factory, _StubIngest()).run_once()
        status, error = await _job_status(factory, job_id)
        assert status == "FAILED"
        assert "no_items" in error, error
    finally:
        await engine.dispose()


# ---------------------------------------------------------------- ② SKIP LOCKED 并发


async def test_claim_next_queued_skip_locked_two_workers_distinct() -> None:
    """**job 级 SKIP LOCKED**：两个并发事务同语句取件，必须取到不同 job。

    若 SKIP LOCKED 失效 → 两者返回同一行 → 断言失败（该行被并行的第二个 get 到）。

    取件范围**限定在本用例自己 seed 的两个 job**：全表 QUEUED 计数会随线上库其他测试的
    残留波动（D19），此前按全表计数做前置判定，既不必要（本用例自己就 seed 了 2 条 QUEUED）
    又有害——残留 job 存在时会触发 SKIP LOCKED 抢到无关 job，使断言失义。
    """
    engine, factory = _factory()
    try:
        ids = {
            await _seed_job(factory, urls=[_T23_URL.format(n=1)], key="race-a"),
            await _seed_job(factory, urls=[_T23_URL.format(n=2)], key="race-b"),
        }

        async with factory() as s1, factory() as s2:
            stmt = (
                select(Job)
                .where(Job.id.in_(ids), Job.status == "QUEUED")
                .order_by(Job.created_at, Job.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            first = (await s1.execute(stmt)).scalars().first()
            second = (await s2.execute(stmt)).scalars().first()
            assert first is not None and second is not None, "本用例 seed 的两个 job 应均为 QUEUED"
            assert first.id != second.id, "SKIP LOCKED 失效：两个 worker 取到同一 job"
    finally:
        await engine.dispose()


async def test_concurrent_workers_each_item_processed_once() -> None:
    """**item 级并发安全**：两 worker 并发消费同一 job，每 item 恰处理一次（无重复消费）。"""
    engine, factory = _factory()
    try:
        urls = [_T23_URL.format(n=n) for n in range(1, 7)]
        job_id = await _seed_job(factory, urls=urls, key="itemrace")
        ingest = _StubIngest()

        w1, w2 = _worker(factory, ingest), _worker(factory, ingest)
        await asyncio.gather(w1.run_once(), w2.run_once())

        counts = await _item_statuses(factory, job_id)
        assert counts["total"] == 6
        assert counts["pending"] == 0, f"并发后有 item 滞留 PENDING: {counts}"
        assert counts["succeeded"] == 6, counts
        assert sorted(ingest.calls) == sorted(urls), f"存在重复或漏采: {ingest.calls}"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------- ③ 崩溃自愈 / 限流


async def test_recover_stale_running_job_requeued() -> None:
    """心跳超时的 RUNNING job + 其 RUNNING item → 分别回退 QUEUED / PENDING。"""
    engine, factory = _factory()
    try:
        job_id = await _seed_job(factory, urls=[_T23_URL.format(n=1)], key="stale")
        # 伪造：job 置 RUNNING + 心跳回拨 1 小时；item 置 RUNNING
        async with factory() as session:
            await session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(status="RUNNING", worker_heartbeat_at=text("now() - interval '1 hour'"))
            )
            await session.execute(update(JobItem).where(JobItem.job_id == job_id).values(status="RUNNING"))
            await session.commit()

        assert await _worker(factory, _StubIngest()).recover_stale() == 1
        status, _ = await _job_status(factory, job_id)
        assert status == "QUEUED", f"自愈后应回退 QUEUED，实际 {status}"
        counts = await _item_statuses(factory, job_id)
        assert counts["pending"] == 1, counts
    finally:
        await engine.dispose()


async def test_throttle_pauses_job_and_keeps_items_pending() -> None:
    """限流 → Job 保持 RUNNING + `paused:rate_limited` 标记，item 留 PENDING（可续）。"""
    engine, factory = _factory()
    try:
        urls = [_T23_URL.format(n=n) for n in (1, 2, 3)]
        job_id = await _seed_job(factory, urls=urls, key="throttle")
        ingest = _StubIngest(throttle=set(urls))
        await _worker(factory, ingest).run_once()

        status, error = await _job_status(factory, job_id)
        assert status == "RUNNING", f"限流应保持 RUNNING 待自愈重入，实际 {status}"
        assert "paused:rate_limited" in error, error
        counts = await _item_statuses(factory, job_id)
        assert counts["failed"] == 0, "限流不得计入 FAILED（否则污染 PARTIAL 分母）"
        assert counts["pending"] == 3, counts
    finally:
        await engine.dispose()


async def test_illegal_transition_rejected_by_state_machine() -> None:
    """状态机护栏：QUEUED → SUCCEEDED 越级流转必须 30005（防绕过 RUNNING 审计）。"""
    from app.services.state_machine import validate_transition

    with pytest.raises(JobStateInvalidError):
        validate_transition("job", "QUEUED", "SUCCEEDED")


async def test_user_table_role_column_contract() -> None:
    """M3 权限地基契约锁（ab1004m3a 落地）。

    本用例原名 test_user_table_has_no_role_column，是 D9 终底**前提**复核
    （users 表无 role/is_admin，M3 权限地基待新增迁移）。SPEC-M3 批次 1 已把
    role 列迁移落地，故反转为锁定**落地后的**形状——不是删除锁，而是把锁的
    对象从「尚无地基」换成「地基仅此一种形状」：
    - role 存在且 NOT NULL、server_default='user'（不升权任何现有账号的承载属性）；
    - is_admin **不存在**（SPEC-M3 §2.1 明确不做并列布尔，三态单一列）；
    - ix_users_role 索引存在（SPEC-M3 §2.2）；
    - 原有五列不丢失（防无声 schema 漂移）。
    """
    engine, factory = _factory()
    try:
        async with factory() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT column_name, is_nullable, column_default "
                        "FROM information_schema.columns WHERE table_name = 'users'"
                    )
                )
            ).all()
            indexes = set(
                (await session.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'users'")))
                .scalars()
                .all()
            )
    finally:
        await engine.dispose()

    cols = {r[0]: (r[1], r[2]) for r in rows}
    assert {"id", "sub", "email", "nickname", "status"} <= set(cols), cols
    assert "role" in cols, cols
    is_nullable, default = cols["role"]
    assert is_nullable == "NO", cols["role"]
    assert default and "user" in default, cols["role"]
    assert "is_admin" not in cols, cols
    assert "ix_users_role" in indexes, indexes


async def test_worker_module_entrypoint_importable() -> None:
    """`python -m app.services.job_worker` 入口可导入（compose worker 服务前置）。"""
    import importlib

    mod = importlib.import_module("app.services.job_worker")
    assert hasattr(mod, "JobWorker") and hasattr(mod, "make_default_ingest")


def test_user_model_import_smoke() -> None:
    """实体导入冒烟（User/Job/JobItem 契约未漂移）。"""
    assert User.__tablename__ == "users"
    assert Job.__tablename__ == "jobs"
    assert JobItem.__tablename__ == "job_items"
