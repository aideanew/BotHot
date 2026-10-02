"""T2.6.1 批量粘贴 Job 化验收（后端半程，连库；PG 不可达 → skip 并标注原因）。

机器门口径（大纲 v1.4 §8.1 序6 验收锚「50 篇批量 202 + 刷新进度不丢 + PARTIAL 重试可用」）：
- **提交即返**：`submit_batch` 零网络抓取，仅落 Job(batch_ingest) + 逐篇 PENDING JobItem；
- **幂等提交**：同批在途（QUEUED/RUNNING）复用同一 Job（reused=True，不重建 JobItem）；
  已终态则换新键重建（允许重复采集，重复入库由 T2.7 幂等链拦截）；
- **校验语义**：越权空间 → 30004；空批/超限 → 10005；非 http(s)/超长 → 10006；
- **进度不丢 + 消费闭环**：Job/JobItem 持久化，交 T2.3 JobWorker 逐篇消费至终态，
  全成 → SUCCEEDED、有成有败 → PARTIAL_SUCCESS（T2.3.3 重试端点已覆盖）。

边界注记（防复议）：本文只断言「每篇恰好调用 ingest 一次、Job 收敛到正确终态」；
ingest 内部的五层缓存复用（短链映射 / READY 命中 / version+1 / 公共库 skipped）
由 test_idempotency_lock.py（T2.7）单独锁定，此处不重复实现真实抓取链路。

连库口径（真提交连接，与 T2.3/T2.7 同法）：conftest 外层事务对其他连接不可见，
worker 必须走独立提交连接才拿得到 Job，故本套件不复用 db_session 夹具；
用例前后各清一次 T26 命名空间，保证套件自身幂等可重复。
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.errors import (
    MalformedUrlError,
    RequestInvalidError,
    ResourceNotFoundError,
)
from app.models.entities import KnowledgeSpace
from app.repositories.job import JobItemRepository, JobRepository
from app.repositories.space import SpaceRepository
from app.repositories.user import SqlAlchemyUserStore
from app.services.batch_ingest import JOB_TYPE_BATCH, BatchIngestService
from app.services.job_worker import JobWorker

PG_DSN = os.environ.get("AIDEANBOT_TEST_PG_DSN", "postgresql+psycopg://bothot:bothot@localhost:5433/bothot")
_T26_SUB = "sub-t26-batch"
_T26_SPACE = "T26批量空间"
_T26_URL = "https://mp.weixin.qq.com/s/t26-{n}?biz=MjM5MjgwNTQ1MQ==&hid=t26"


def _purge_t26() -> None:
    """清 T2.6 命名空间残留，保证套件可重复（真提交路径是唯一残留源）。"""
    try:
        engine = create_engine(PG_DSN, connect_args={"connect_timeout": 3})
    except Exception:  # noqa: BLE001 引擎不可用交由守卫 skip
        return
    try:
        with engine.begin() as conn:
            # 只能清**本测试用户**的 Job：生产批量的 idempotency_key 前缀就是
            # `batch_ingest:`（见 batch_ingest._create_batch_job），用
            # `LIKE 'batch_ingest:%'` 清场会把开发库里用户的真实批量任务连带删掉
            # （2026-09-25 实测：任务中心刚提交的 Job 被本套件清成 0 条）。
            conn.execute(
                text("DELETE FROM jobs WHERE user_id IN (SELECT id FROM users WHERE sub = :s)"),
                {"s": _T26_SUB},
            )
            conn.execute(text("DELETE FROM users WHERE sub = :s"), {"s": _T26_SUB})
            conn.execute(text("DELETE FROM knowledge_spaces WHERE name LIKE :p"), {"p": "T26%"})
    except Exception:  # noqa: BLE001 清理失败不掩盖用例本身的判定
        return
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def _t26_guard() -> Iterator[None]:
    """PG 可达性守卫 + 用例前后清场。"""
    try:
        engine = create_engine(PG_DSN, connect_args={"connect_timeout": 3})
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
    except Exception as exc:  # noqa: BLE001 不可达统一 skip 并标注原因
        pytest.skip(f"PG 不可达（{type(exc).__name__}），Docker 引擎恢复后复跑本用例")
    _purge_t26()
    yield
    _purge_t26()


def _factory() -> Any:
    engine = create_async_engine(PG_DSN, pool_pre_ping=True, connect_args={"connect_timeout": 3})
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _seed(factory: Any) -> tuple[str, str]:
    """建 user + space（真提交，供 worker 独立连接可见）；返回 (user_id, space_id)。"""
    async with factory() as session:
        user = await SqlAlchemyUserStore(session).upsert_by_sub(_T26_SUB, "t26@test.local", "T26")
        space = (
            await session.execute(
                select(KnowledgeSpace).where(KnowledgeSpace.user_id == user.id, KnowledgeSpace.name == _T26_SPACE)
            )
        ).scalar_one_or_none()
        if space is None:
            space = await SpaceRepository(session).create(user_id=user.id, name=_T26_SPACE)
        await session.commit()
        return user.id, space.id


def _urls(*ns: int) -> list[str]:
    return [_T26_URL.format(n=n) for n in ns]


def _service(session: Any, *, max_urls: int | None = None) -> BatchIngestService:
    return BatchIngestService(session, max_urls=max_urls)


class _StubIngest:
    """记录式入库桩：按 URL 记录调用，可指定失败集合（不落真实抓取）。"""

    def __init__(self, *, fail: set[str] | None = None) -> None:
        self.calls: list[str] = []
        self._fail = fail or set()

    async def __call__(self, session: Any, space_id: str, url: str) -> dict[str, Any]:
        self.calls.append(url)
        if url in self._fail:
            raise RuntimeError("stub ingest 失败")
        return {"docId": f"doc-{url[-3:]}", "title": "t26", "status": "INDEXED"}


def _worker(factory: Any, ingest: _StubIngest) -> JobWorker:
    """item 间隔置 0（测试不睡），max_retries=1（快速触顶 FAILED）。

    `heartbeat_enabled=False`：本文件工厂直连共库真提交，开着的存活上报会留下
    运维可读的假存活信号（详见 `JobWorker.heartbeat_enabled` 的注释）。
    """
    return JobWorker(
        factory,
        ingest,
        settings=Settings(),
        item_interval_seconds=0.0,
        max_item_retries=1,
        stale_job_seconds=1,
        idle_sleep_seconds=0.0,
        heartbeat_enabled=False,
    )


async def _job_state(factory: Any, job_id: str) -> tuple[str, str, str]:
    async with factory() as session:
        job = await JobRepository(session).get_by_id(job_id)
        assert job is not None, f"job {job_id} 应存在"
        return job.type, job.status, job.payload


async def _counts(factory: Any, job_id: str) -> dict[str, int]:
    async with factory() as session:
        return await JobItemRepository(session).counts(job_id)


# ---------------------------------------------------------------- ① 提交即返


async def test_submit_batch_creates_job_and_pending_items() -> None:
    """批量提交 → Job(batch_ingest, QUEUED) + N 个 PENDING JobItem；counts 全 pending。"""
    engine, factory = _factory()
    try:
        user_id, space_id = await _seed(factory)
        urls = _urls(1, 2, 3)
        async with factory() as session:
            result = await _service(session).submit_batch(user_id, space_id, urls)

        assert result["reused"] is False, f"首次提交应新建 Job，实际 {result}"
        assert result["urlCount"] == 3
        assert result["status"] == "QUEUED"
        assert result["counts"] == {"total": 3, "succeeded": 0, "failed": 0, "pending": 3}, result

        jtype, status, payload = await _job_state(factory, result["jobId"])
        assert jtype == JOB_TYPE_BATCH
        assert status == "QUEUED"
        # job_worker 依赖 payload.space_id 定位入库目标空间
        assert json.loads(payload)["space_id"] == space_id

        async with factory() as session:
            items = await JobItemRepository(session).list_by_job(result["jobId"])
        assert [it.url for it in items] == urls, "JobItem 应按提交顺序逐篇落库"
        assert all(it.status == "PENDING" for it in items)
    finally:
        await engine.dispose()


async def test_submit_batch_normalizes_strip_and_dedup() -> None:
    """归一化：strip 空白、跳过空行、保序去重（重复 URL 只建一个 JobItem）。"""
    engine, factory = _factory()
    try:
        user_id, space_id = await _seed(factory)
        u1, u2 = _urls(1, 2)
        raw = [f"  {u1}  ", "", "   ", u2, u1, u2]
        async with factory() as session:
            result = await _service(session).submit_batch(user_id, space_id, raw)

        assert result["urlCount"] == 2, f"应去重为 2 条，实际 {result}"
        assert result["counts"]["total"] == 2
        async with factory() as session:
            items = await JobItemRepository(session).list_by_job(result["jobId"])
        assert [it.url for it in items] == [u1, u2], "去重后应保序且已 strip"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------- ② 幂等提交


async def test_submit_batch_reuses_inflight_job() -> None:
    """同批在途（QUEUED）重复提交 → 复用同一 Job（reused=True），不重建 JobItem。"""
    engine, factory = _factory()
    try:
        user_id, space_id = await _seed(factory)
        urls = _urls(1, 2)
        async with factory() as session:
            first = await _service(session).submit_batch(user_id, space_id, urls)
            second = await _service(session).submit_batch(user_id, space_id, list(reversed(urls)))

        assert first["reused"] is False
        assert second["reused"] is True, "在途批次应复用，不双份排队"
        assert second["jobId"] == first["jobId"]
        assert second["urlCount"] == first["urlCount"]
        # 指纹与提交顺序无关：倒序提交仍命中同一键
        assert (await _counts(factory, first["jobId"]))["total"] == 2, "复用路径不得重复建 item"
    finally:
        await engine.dispose()


async def test_submit_batch_resubmits_after_terminal() -> None:
    """同批已终态后重复提交 → 换新键重建 Job（允许重复采集；重复入库由 T2.7 链拦截）。"""
    engine, factory = _factory()
    try:
        user_id, space_id = await _seed(factory)
        urls = _urls(1, 2)
        async with factory() as session:
            first = await _service(session).submit_batch(user_id, space_id, urls)

        # 置为终态（模拟上一轮已跑完）
        async with factory() as session:
            await JobRepository(session).set_status(first["jobId"], "SUCCEEDED")
            await session.commit()

        async with factory() as session:
            second = await _service(session).submit_batch(user_id, space_id, urls)

        assert second["reused"] is False, "终态后应允许重建"
        assert second["jobId"] != first["jobId"]
        assert (await _counts(factory, second["jobId"]))["total"] == 2

        async with factory() as session:
            jobs = await JobRepository(session).list_by_user(user_id, limit=10)
        keys = {j.idempotency_key for j in jobs}
        assert any(k.endswith(":r2") for k in keys), f"重建应换新幂等键，实际 {keys}"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------- ③ 校验语义


async def test_submit_batch_rejects_other_users_space() -> None:
    """越权空间 → 30004（不泄露存在性），且不落任何 Job。"""
    engine, factory = _factory()
    try:
        owner, space_id = await _seed(factory)
        urls = _urls(1)
        with pytest.raises(ResourceNotFoundError) as exc_info:
            async with factory() as session:
                await _service(session).submit_batch("user-other", space_id, urls)
        assert exc_info.value.code == 30004, f"应为 30004，实际 {exc_info.value.code}"

        async with factory() as session:
            jobs = await JobRepository(session).list_by_user(owner, limit=10)
        assert not jobs, "越权请求不得产生 Job"
    finally:
        await engine.dispose()


async def test_submit_batch_rejects_invalid_space_id() -> None:
    """无效空间 id → 30004（与越权同语义，不泄露存在性）。"""
    engine, factory = _factory()
    try:
        user_id, _ = await _seed(factory)
        bogus = "00000000-0000-0000-0000-000000000099"
        with pytest.raises(ResourceNotFoundError) as exc_info:
            async with factory() as session:
                await _service(session).submit_batch(user_id, bogus, _urls(1))
        assert exc_info.value.code == 30004
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "payload,expected_code",
    [
        ([], 10005),  # 空批
        (["", "   ", "\t"], 10005),  # 全空白：与空批同语义
        (["mp.weixin.qq.com/s/no-scheme"], 10006),  # 非 http(s)
        (["ftp://mp.weixin.qq.com/s/x"], 10006),  # 非 http(s)
        (["https://mp.weixin.qq.com/s/" + "x" * 496], 10006),  # 超列宽 512
    ],
)
async def test_submit_batch_rejects_invalid_inputs(payload: list[str], expected_code: int) -> None:
    """空批/全空白 → 10005；非 http(s)/超长 URL → 10006；均不落 Job。"""
    engine, factory = _factory()
    try:
        user_id, space_id = await _seed(factory)
        with pytest.raises((RequestInvalidError, MalformedUrlError)) as exc_info:
            async with factory() as session:
                await _service(session).submit_batch(user_id, space_id, payload)
        assert exc_info.value.code == expected_code, (
            f"应为 {expected_code}，实际 {exc_info.value.code}：{exc_info.value}"
        )
        async with factory() as session:
            assert not await JobRepository(session).list_by_user(user_id, limit=10)
    finally:
        await engine.dispose()


async def test_submit_batch_enforces_max_urls() -> None:
    """超业务上限（batch_ingest_max_urls）→ 10005，且错误信息含上限值。"""
    engine, factory = _factory()
    try:
        user_id, space_id = await _seed(factory)
        with pytest.raises(RequestInvalidError) as exc_info:
            async with factory() as session:
                await _service(session, max_urls=3).submit_batch(user_id, space_id, _urls(1, 2, 3, 4))
        assert exc_info.value.code == 10005
        assert "3" in str(exc_info.value), f"错误信息应含上限值：{exc_info.value}"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------- ④ worker 消费闭环


async def test_worker_consumes_batch_job_and_finalizes() -> None:
    """worker 逐篇消费 batch Job → 全成 SUCCEEDED；每篇恰好调用 ingest 一次。"""
    engine, factory = _factory()
    try:
        user_id, space_id = await _seed(factory)
        urls = _urls(1, 2, 3)
        async with factory() as session:
            result = await _service(session).submit_batch(user_id, space_id, urls)

        ingest = _StubIngest()
        assert await _worker(factory, ingest).run_once() is True

        assert (await _job_state(factory, result["jobId"]))[1] == "SUCCEEDED"
        assert await _counts(factory, result["jobId"]) == {
            "total": 3,
            "succeeded": 3,
            "failed": 0,
            "pending": 0,
        }
        assert sorted(ingest.calls) == sorted(urls), "每篇恰好消费一次"
    finally:
        await engine.dispose()


async def test_worker_partial_failure_converges_partial_success() -> None:
    """有成有败 → PARTIAL_SUCCESS（T2.3.3 重试端点入口）；失败篇记录 error。"""
    engine, factory = _factory()
    try:
        user_id, space_id = await _seed(factory)
        urls = _urls(1, 2, 3)
        async with factory() as session:
            result = await _service(session).submit_batch(user_id, space_id, urls)

        ingest = _StubIngest(fail={urls[1]})
        await _worker(factory, ingest).run_once()

        assert (await _job_state(factory, result["jobId"]))[1] == "PARTIAL_SUCCESS"
        counts = await _counts(factory, result["jobId"])
        assert counts["total"] == 3 and counts["succeeded"] == 2 and counts["failed"] == 1, counts

        async with factory() as session:
            failed = await JobItemRepository(session).list_failed(result["jobId"])
        assert len(failed) == 1 and failed[0].url == urls[1]
        assert failed[0].error, "失败篇应记录 error 供 PARTIAL 重试"
    finally:
        await engine.dispose()


async def test_worker_stale_batch_job_requeues_items() -> None:
    """崩溃自愈：batch Job 心跳超时 → 回退 QUEUED + item 回退 PENDING（可续采）。"""
    engine, factory = _factory()
    try:
        user_id, space_id = await _seed(factory)
        urls = _urls(1, 2)
        async with factory() as session:
            result = await _service(session).submit_batch(user_id, space_id, urls)

        worker = _worker(factory, _StubIngest())
        assert await worker.run_once() is True  # 基线：可完整消费至终态

        # 伪造"worker 抢到 item 即宕机"现场：Job RUNNING + 心跳超阈值 + item 停留 RUNNING
        async with factory() as session:
            job = await JobRepository(session).get_by_id(result["jobId"])
            assert job is not None
            job.status = "RUNNING"
            job.worker_heartbeat_at = datetime.now(UTC) - timedelta(seconds=30)
            for it in await JobItemRepository(session).list_by_job(result["jobId"]):
                it.status = "RUNNING"
                it.completed = False
            await session.flush()
            await session.commit()

        requeued = await worker.recover_stale()
        assert requeued == 1, f"应回退 1 件滞留 Job，实际 {requeued}"
        assert (await _job_state(factory, result["jobId"]))[1] == "QUEUED"
        counts = await _counts(factory, result["jobId"])
        assert counts["pending"] == 2 and counts["succeeded"] == 0, f"item 应回退 PENDING：{counts}"

        # 可续性：自愈后重入应把整批重新消费到终态（批量进度不因宕机丢失）
        assert await worker.run_once() is True
        assert (await _job_state(factory, result["jobId"]))[1] == "SUCCEEDED"
    finally:
        await engine.dispose()


# ---------------------------------------------------------------- ⑤ HTTP 接线


async def test_docs_batch_endpoint_202_envelope() -> None:
    """POST /spaces/{id}/docs:batch → 202 + 统一信封；与 /docs 单篇路由不冲突。"""
    from fastapi.testclient import TestClient

    from app.api.deps import get_current_user_id, get_db
    from app.main import create_app

    engine, factory = _factory()
    try:
        user_id, space_id = await _seed(factory)
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        session = factory()
        try:
            app.dependency_overrides[get_current_user_id] = lambda: user_id
            app.dependency_overrides[get_db] = lambda: session
            try:
                resp = client.post(
                    f"/api/v1/spaces/{space_id}/docs:batch",
                    json={"urls": _urls(1, 2)},
                )
            finally:
                app.dependency_overrides.clear()
        finally:
            await session.close()

        assert resp.status_code == 202, f"批量提交应 202 提交即返，实际 {resp.status_code}"
        body = resp.json()
        assert set(body) >= {"code", "message", "data"}, f"应为统一信封：{body}"
        assert body["code"] == 0
        data = body["data"]
        assert data["jobId"] and data["status"] == "QUEUED"
        assert data["counts"]["total"] == 2 and data["counts"]["pending"] == 2
        assert data["urlCount"] == 2

        # 登录保护：未覆盖 user 依赖 → 10001 先行
        app2 = create_app()
        client2 = TestClient(app2, raise_server_exceptions=False)
        resp2 = client2.post(f"/api/v1/spaces/{space_id}/docs:batch", json={"urls": _urls(1)})
        assert resp2.status_code == 401, f"未登录应 401 登录保护先行，实际 {resp2.status_code}"
    finally:
        await engine.dispose()
