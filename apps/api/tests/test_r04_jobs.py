"""R0.4 Job 可观测与取消：GET /jobs（清单分页）+ POST /jobs/{id}/cancel。

F-7：Job 只有单篇读端点（GET /jobs/{id}），用户看不到「我的任务列表」，也停不掉排队的
任务——批量采集一提交就只能干等。本批补清单分页与取消。

口径锚点（与 R0.1.1 分页及既有 Job 端点须同口径）：
- `type`/`status` 是**取值过滤**而非域校验：未知取值返空列表（读路径不设校验闸门，与
  R0.1.1 同口径）；资源约束（limit 1..100、offset >= 0）另算，防大页 DoS；
- `total` 与 `items` 共用 `_job_stmt`，否则会出现「过滤后列表配未过滤 total」的静默漂移
  ——两个查询都成功、只是数字不自洽，无异常可捕；基座刻意不含 order_by/limit，否则
  count 会落在被 LIMIT 截断的语句上；
- 排序 `(created_at desc, id desc)`：`created_at` 为 `server_default=now()`，而 PostgreSQL
  的 `now()` 返回**事务开始时刻**——同一事务批量建的 Job 时间戳完全相同，只按 created_at
  排序属未定序，offset 分页会重复页/漏行，故追加 `id` 作确定性兜底；
- 取消**仅 QUEUED → CANCELLED**：RUNNING 已投入执行的作业不半途作废（状态机亦不设
  RUNNING→CANCELLED 出边），拒绝时在 message 里回当前 progress——错误信封无 error-data
  通道，与 `delete_source` 同口径把上下文放进 message；终态（含已取消）同理拒绝；
- 归属同 get_job 口径：他人/无效 job → 30004，且两种情况**不可区分**（不泄露他人 job 是否存在）；
- CANCELLED 是真终态：worker 只认领 QUEUED，取消后永不被取件。但
  `batch_ingest._TERMINAL_STATUSES` 必须含 CANCELLED——否则该批次幂等键被永久判为「在途」，
  同一批次再也无法重新采集（本文件最后一测即此回归锁）。

夹具沿用 test_r02_docs_lifecycle 的 savepoint 会话：Service 内 commit 只释放 savepoint，
外层事务回滚清场；故「行是否真改了」的断言直接读库即可。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from test_r02_docs_lifecycle import _seed

from app.api.deps import get_current_user_id, get_db
from app.main import create_app
from app.models.entities import Job, User
from app.repositories.job import JobRepository
from app.services.batch_ingest import BatchIngestService
from app.services.jobs import JobService
from app.services.state_machine import can_transition

# 全部同值：这正是「同一事务批量入库」产生的 created_at 相等等值态
FIXED_TS = datetime(2026, 9, 22, 8, 0, tzinfo=UTC)
JOB_ID_UNKNOWN = "00000000-0000-0000-0000-0000000000aa"


async def _add_job(
    db_session: Any,
    *,
    user_id: str,
    job_id: str,
    status: str = "QUEUED",
    progress: int = 0,
    job_type: str = "batch_ingest",
    key: str | None = None,
    created_at: datetime | None = None,
) -> Job:
    job = Job(
        id=job_id,
        type=job_type,
        user_id=user_id,
        status=status,
        progress=progress,
        idempotency_key=key or f"test:{job_id}",
        created_at=created_at or FIXED_TS,
    )
    db_session.add(job)
    await db_session.flush()
    return job


def _client(db_session: Any, user_id: str) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


# ------------------------------------------------------------------ R0.4.1 GET /jobs


async def test_list_jobs_pages_own_jobs_with_consistent_total(db_session) -> None:
    """分页形状 + total 与 items 同谓词 + 他人 Job 不泄露（total 也不含）。"""
    _, user_id, _ = await _seed(db_session, sub="r04-own")
    other = User(sub="r04-other", email="r04-other@test.local", nickname="他人")
    db_session.add(other)
    await db_session.flush()

    for i, jid in enumerate(("j-1", "j-2", "j-3"), start=1):
        await _add_job(db_session, user_id=user_id, job_id=jid, key=f"b{i}")
        await _add_job(db_session, user_id=other.id, job_id=f"x-{i}", key=f"x{i}")

    client = _client(db_session, user_id)
    first = client.get("/api/v1/jobs", params={"limit": 2, "offset": 0})
    assert first.status_code == 200
    data = first.json()["data"]
    assert (data["total"], data["limit"], data["offset"]) == (3, 2, 0)
    assert [i["jobId"] for i in data["items"]] == ["j-3", "j-2"]

    second = client.get("/api/v1/jobs", params={"limit": 2, "offset": 2}).json()["data"]
    assert second["total"] == 3
    assert [i["jobId"] for i in second["items"]] == ["j-1"]

    assert client.get("/api/v1/jobs", params={"limit": 2, "offset": 3}).json()["data"]["items"] == []


async def test_list_jobs_offsets_are_stable_when_created_at_ties(db_session) -> None:
    """created_at 同值时靠 id 兜底排序：逐条翻页恰好全覆盖，不重复不漏行。"""
    _, user_id, _ = await _seed(db_session, sub="r04-stable")
    for jid in ("s-1", "s-2", "s-3", "s-4"):
        await _add_job(db_session, user_id=user_id, job_id=jid, key=jid)

    client = _client(db_session, user_id)
    seen: list[str] = []
    for off in (0, 1, 2, 3):
        data = client.get("/api/v1/jobs", params={"limit": 1, "offset": off}).json()["data"]
        assert data["total"] == 4
        seen.extend(i["jobId"] for i in data["items"])
    assert seen == ["s-4", "s-3", "s-2", "s-1"]


async def test_list_jobs_filters_type_and_status(db_session) -> None:
    """type/status 过滤同时作用于 items 与 total（同一 _job_stmt）。"""
    _, user_id, _ = await _seed(db_session, sub="r04-filter")
    await _add_job(db_session, user_id=user_id, job_id="f-1", status="QUEUED", key="f1")
    await _add_job(db_session, user_id=user_id, job_id="f-2", status="SUCCEEDED", job_type="sync_account", key="f2")
    await _add_job(db_session, user_id=user_id, job_id="f-3", status="RUNNING", job_type="sync_account", key="f3")
    client = _client(db_session, user_id)

    by_type = client.get("/api/v1/jobs", params={"type": "sync_account"}).json()["data"]
    assert by_type["total"] == 2
    assert sorted(i["jobId"] for i in by_type["items"]) == ["f-2", "f-3"]

    by_status = client.get("/api/v1/jobs", params={"status": "RUNNING"}).json()["data"]
    assert by_status["total"] == 1 and by_status["items"][0]["jobId"] == "f-3"

    both = client.get("/api/v1/jobs", params={"type": "sync_account", "status": "SUCCEEDED"}).json()["data"]
    assert both["total"] == 1 and both["items"][0]["jobId"] == "f-2"


async def test_list_jobs_unknown_type_or_status_returns_empty_not_422(db_session) -> None:
    """未知取值是合法的空集合，不是请求错误——读路径不设校验闸门。"""
    _, user_id, _ = await _seed(db_session, sub="r04-unknown")
    await _add_job(db_session, user_id=user_id, job_id="u-1", key="u1")
    client = _client(db_session, user_id)

    for params in ({"type": "no_such_type"}, {"status": "NO_SUCH"}, {"type": "sync_account", "status": "NO_SUCH"}):
        resp = client.get("/api/v1/jobs", params=params)
        assert resp.status_code == 200, params
        assert resp.json()["data"] == {"items": [], "total": 0, "limit": 50, "offset": 0}, params


async def test_list_jobs_resource_bounds_enforced(db_session) -> None:
    """limit/offset 是资源约束（防大页 DoS），越界 422 走 10005；合法边界放行。"""
    _, user_id, _ = await _seed(db_session, sub="r04-bounds")
    await _add_job(db_session, user_id=user_id, job_id="b-1", key="b1")
    client = _client(db_session, user_id)

    for params in ({"limit": 101}, {"limit": 0}, {"offset": -1}):
        resp = client.get("/api/v1/jobs", params=params)
        assert resp.status_code == 422, params
        assert resp.json()["code"] == 10005, params

    assert client.get("/api/v1/jobs", params={"limit": 100}).status_code == 200
    assert client.get("/api/v1/jobs", params={"limit": 1}).json()["data"]["limit"] == 1


# ------------------------------------------------------------------ R0.4.2 POST /jobs/{id}/cancel


async def test_cancel_queued_job_succeeds_and_persists(db_session) -> None:
    _, user_id, _ = await _seed(db_session, sub="r04-cancel")
    await _add_job(db_session, user_id=user_id, job_id="c-1", status="QUEUED", key="c1")
    client = _client(db_session, user_id)

    resp = client.post("/api/v1/jobs/c-1/cancel")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["jobId"] == "c-1" and data["status"] == "CANCELLED"
    assert data["error"] == "cancelled: 用户取消"

    row = await db_session.get(Job, "c-1")
    assert row is not None and row.status == "CANCELLED"
    assert row.progress == 0

    # 取消后的 Job 出现在清单里，可被 status 过滤出来（可观测性是 R0.4 的目标）
    listed = client.get("/api/v1/jobs", params={"status": "CANCELLED"}).json()["data"]
    assert [i["jobId"] for i in listed["items"]] == ["c-1"]


async def test_cancel_running_job_rejected_and_reports_progress(db_session) -> None:
    """RUNNING 拒绝并回当前 progress；错误信封无 error-data 通道，故上下文进 message。"""
    _, user_id, _ = await _seed(db_session, sub="r04-running")
    await _add_job(db_session, user_id=user_id, job_id="r-1", status="RUNNING", progress=42, key="r1")
    client = _client(db_session, user_id)

    body = client.post("/api/v1/jobs/r-1/cancel").json()
    assert body["code"] == 30005
    assert "42%" in body["message"] and "无法取消" in body["message"]
    assert body["data"] is None

    row = await db_session.get(Job, "r-1")
    assert row is not None and row.status == "RUNNING" and row.progress == 42


async def test_cancel_terminal_jobs_rejected(db_session) -> None:
    """终态一律拒绝（含已取消者）：取消不可重复，也不把「已取消」当成功回 200。"""
    _, user_id, _ = await _seed(db_session, sub="r04-terminal")
    rows = {"t-suc": "SUCCEEDED", "t-par": "PARTIAL_SUCCESS", "t-fail": "FAILED", "t-can": "CANCELLED"}
    for jid, status in rows.items():
        await _add_job(db_session, user_id=user_id, job_id=jid, status=status, key=jid)
    client = _client(db_session, user_id)

    for jid, status in rows.items():
        body = client.post(f"/api/v1/jobs/{jid}/cancel").json()
        assert body["code"] == 30005, jid
        assert status in body["message"], jid
    for jid, status in rows.items():
        row = await db_session.get(Job, jid)
        assert row is not None and row.status == status, jid


async def test_cancel_foreign_or_unknown_job_indistinguishable_30004(db_session) -> None:
    """越权与「不存在」不可区分——不泄露他人 job 是否存在（与 get_job 同口径）。"""
    _, owner_id, _ = await _seed(db_session, sub="r04-iso-a")
    stranger = User(sub="r04-iso-b", email="r04-iso-b@test.local", nickname="B")
    db_session.add(stranger)
    await db_session.flush()
    await _add_job(db_session, user_id=owner_id, job_id="iso-1", key="iso1")

    s_client = _client(db_session, stranger.id)
    assert s_client.post("/api/v1/jobs/iso-1/cancel").json()["code"] == 30004
    assert s_client.post(f"/api/v1/jobs/{JOB_ID_UNKNOWN}/cancel").json()["code"] == 30004
    assert s_client.get("/api/v1/jobs").json()["data"]["total"] == 0

    assert _client(db_session, owner_id).post("/api/v1/jobs/iso-1/cancel").json()["code"] == 0


async def test_worker_never_claims_cancelled_job(db_session) -> None:
    """CANCELLED 是真终态：取件只认 QUEUED，同表内的 CANCELLED 行不会被误取。"""
    _, user_id, _ = await _seed(db_session, sub="r04-worker")
    await _add_job(db_session, user_id=user_id, job_id="w-1", status="CANCELLED", key="w1")
    await _add_job(db_session, user_id=user_id, job_id="w-2", status="QUEUED", key="w2")

    claimed = await JobRepository(db_session).claim_next_queued()
    assert claimed is not None and claimed.id == "w-2"
    row = await db_session.get(Job, "w-1")
    assert row is not None and row.status == "CANCELLED"


async def test_cancelled_batch_key_can_be_resubmitted(db_session) -> None:
    """回归锁：CANCELLED 若不在终态集，该批次幂等键会被永久判为「在途」，同批再也采集不了。"""
    space_id, user_id, _ = await _seed(db_session, sub="r04-idem")
    svc = BatchIngestService(db_session)
    urls = ["https://mp.weixin.qq.com/s/r04-idem-1"]

    first = await svc.submit_batch(user_id, space_id, urls)
    assert first["reused"] is False

    # 对照：在途（QUEUED）同批 → 复用，零重复入队（既有语义）
    in_flight = await svc.submit_batch(user_id, space_id, urls)
    assert in_flight["reused"] is True and in_flight["jobId"] == first["jobId"]

    # 取消后重提：换 :r2 键建新 Job，而不是复用这个已被取消的死 Job
    await JobService(JobRepository(db_session), db_session).cancel_job(user_id, first["jobId"])
    again = await svc.submit_batch(user_id, space_id, urls)
    assert again["reused"] is False
    assert again["jobId"] != first["jobId"]
    assert again["status"] == "QUEUED"


def test_state_machine_allows_queued_to_cancelled_only() -> None:
    """QUEUED→CANCELLED 放行；RUNNING 不设 CANCELLED 出边（不半途作废已执行的作业）。"""
    assert can_transition("job", "QUEUED", "CANCELLED")
    assert can_transition("job", "QUEUED", "RUNNING")
    assert not can_transition("job", "RUNNING", "CANCELLED")
    for status in ("SUCCEEDED", "PARTIAL_SUCCESS", "FAILED", "CANCELLED"):
        assert not can_transition("job", status, "CANCELLED"), status
