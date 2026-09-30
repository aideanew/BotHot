"""R4.8（A-2 叠加口径）验收：作业/订阅跨用户读面 + 信息源写面收口。

缺口与 M3 批次 2 读面同源：jobs/subscriptions 的既有读端点全带本人归属谓词，
admin 无法回答「全系统哪条号卡住了 / 谁在跑同步」。沿用批次 4 已确立的手法：
Service 抽出单一实现，`owner=None` 表示无归属约束，两条入口的全部差异只在这一处判据
——否则「total 与过滤同谓词」「latestJobId 归属取订阅本人」这类契约会在两份拷贝间漂移，
且没有任何调用方会报错。

本文件同时锁两侧：
- admin 端点：跨用户可见，admin 放行，operator/user → 10004；
- 用户端点：跨用户读取仍 30004（A-2「零回归」承诺不被本批 Service 改造削弱）；
- 信息源写面：PATCH /sources/{id} 收口到 admin（与 DELETE 同口径），type/external_id 不可写。

另锁 F-23 的修正确实生效：GET /sources 返回**全用户共享**清单，不再声称用户上下文。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.api.deps import get_current_sub, get_current_user_id, get_db
from app.main import create_app
from app.models.entities import (
    ArticleManifest,
    Job,
    JobItem,
    KnowledgeSpace,
    Source,
    SourceSubscription,
    User,
)
from app.repositories.job import JobItemRepository, JobRepository

JOB_ID_MISSING = "00000000-0000-0000-0000-000000000001"
SPACE_ID_MISSING = "00000000-0000-0000-0000-000000000002"
SOURCE_ID_MISSING = "00000000-0000-0000-0000-000000000003"

ADMIN_JOBS = "/api/v1/admin/jobs"
ADMIN_JOB = "/api/v1/admin/jobs/{job_id}"
ADMIN_SUBS = "/api/v1/admin/subscriptions"
PATCH_SOURCE = "/api/v1/sources/{source_id}"


async def _seed(db_session: Any) -> dict[str, Any]:
    """铺两个租户 + admin/operator 角色账号 + 一条共享信息源。

    owner：space_a + 2 个 Job（一个带 3 篇 JobItem，供 counts 断言）；
    second：space_b + 1 条订阅 + 1 个匹配幂等键的 Job（供 latestJobId 跨用户断言）；
    admin/operator 无自有数据，专供授权门禁用例。
    """
    owner = User(sub="r48-owner", email="r48-owner@r48.test", nickname="owner")
    second = User(sub="r48-second", email="r48-second@r48.test", nickname="second")
    admin = User(sub="r48-admin", email="r48-admin@r48.test", nickname="admin", role="admin")
    operator = User(
        sub="r48-operator", email="r48-operator@r48.test", nickname="operator", role="operator"
    )
    db_session.add_all([owner, second, admin, operator])
    await db_session.flush()

    src = Source(
        type="wechat_oa",
        external_id="biz-r48",
        name="R48 测试号",
        url="https://redfox.hk/apis/gongzhonghao/biz-r48",
    )
    db_session.add(src)
    await db_session.flush()

    space_a = KnowledgeSpace(user_id=owner.id, name="R48 租户A空间", langbot_kb_uuid="kb-r48-a")
    space_b = KnowledgeSpace(user_id=second.id, name="R48 租户B空间", langbot_kb_uuid="kb-r48-b")
    db_session.add_all([space_a, space_b])
    await db_session.flush()

    job_owner_sync = Job(type="sync_account", user_id=owner.id, idempotency_key="sync_account:own-1")
    job_owner_ingest = Job(type="ingest_url", user_id=owner.id, idempotency_key="ingest_r48_1")
    db_session.add_all([job_owner_sync, job_owner_ingest])
    await db_session.flush()

    for i in (1, 2):
        item = JobItem(job_id=job_owner_sync.id, external_id=f"w-r48-{i}", url=f"https://x/{i}")
        item.status = "SUCCEEDED"
        db_session.add(item)
        await db_session.flush()
    item = JobItem(job_id=job_owner_sync.id, external_id="w-r48-3", url="https://x/3")
    item.status = "PENDING"
    db_session.add(item)
    await db_session.flush()

    sub = SourceSubscription(
        user_id=second.id,
        source_id=src.id,
        space_id=space_b.id,
        sync_policy="auto",
        sync_interval_minutes=120,
        next_run_at=datetime.now(UTC),
    )
    db_session.add(sub)
    await db_session.flush()

    job_second = Job(
        type="sync_account",
        user_id=second.id,
        idempotency_key=f"sync_account:{sub.id}",
    )
    db_session.add(job_second)
    await db_session.flush()

    db_session.add(
        ArticleManifest(source_id=src.id, external_id="w-r48-disc", url="https://x/disc")
    )
    await db_session.commit()  # 夹具 savepoint 模式：只释放保存点，外层回滚清场

    return {
        "owner": owner.id,
        "second": second.id,
        "admin": admin.id,
        "operator": operator.id,
        "source": src.id,
        "space_a": space_a.id,
        "space_b": space_b.id,
        "job_owner_sync": job_owner_sync.id,
        "job_owner_ingest": job_owner_ingest.id,
        "job_second": job_second.id,
        "sub": sub.id,
    }


def _app(db_session: Any, actor_id: str) -> TestClient:
    """挂真实 PG 会话与身份覆盖的测试应用（依赖装配与生产一致）。"""
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: actor_id
    app.dependency_overrides[get_current_sub] = lambda: "r48-sub"
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def _unauth_client(db_session: Any) -> TestClient:
    """未登录客户端：仅覆盖 db，身份依赖走真实解析 → 10001。"""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def _hit(client: TestClient, method: str, path: str, **kwargs: Any) -> tuple[int, int]:
    """打一次请求，返回 (http_status, 业务码)。"""
    resp = getattr(client, method)(path, **kwargs)
    return resp.status_code, resp.json().get("code", -1)


# ------------------------------------------------------------------ GET /admin/jobs


async def test_admin_list_jobs_cross_user_with_owner(db_session) -> None:  # type: ignore[no-untyped-def]
    """admin 一次取得全部租户的 Job，每条带 ownerId；分页与 total 同谓词。

    夹具只在**写侧**隔离（外层事务回滚），读侧仍可见环境已提交的其他 Job
    （如人工 QA 数据），故不断言全局绝对值/归属全集——只断言本用例播种的三条
    可见、归属正确，且 total 与实际条目自洽。
    """
    rows = await _seed(db_session)
    client = _app(db_session, rows["admin"])

    data = client.get(ADMIN_JOBS).json()["data"]
    assert data["limit"] == 50 and data["offset"] == 0
    assert data["total"] == len(data["items"])  # 未分页时 total 与条目数自洽

    by_id = {i["jobId"]: i for i in data["items"]}
    for jid in (rows["job_owner_sync"], rows["job_owner_ingest"], rows["job_second"]):
        assert jid in by_id, f"播种的 Job 未在跨用户清单: {jid}"
    assert by_id[rows["job_owner_sync"]]["ownerId"] == rows["owner"]
    assert by_id[rows["job_second"]]["ownerId"] == rows["second"]  # 跨租户可见

    page = client.get(f"{ADMIN_JOBS}?limit=2&offset=0").json()["data"]
    assert len(page["items"]) == 2 and page["total"] == data["total"]  # total 不受 LIMIT 截断


async def test_admin_list_jobs_filters_share_total_predicate(db_session) -> None:  # type: ignore[no-untyped-def]
    """type/status 过滤与 total 走同一谓词（F-9 口径，不按调用方身份过滤）。

    读侧不隔离，环境可能自带其他 Job：过滤生效的证据是「播种集合被正确纳入/排除」，
    而非全局总数等于某个常量。
    """
    rows = await _seed(db_session)
    client = _app(db_session, rows["admin"])
    seeded = {rows["job_owner_sync"], rows["job_owner_ingest"], rows["job_second"]}

    by_type = client.get(f"{ADMIN_JOBS}?type=sync_account").json()["data"]
    type_ids = {i["jobId"] for i in by_type["items"]}
    assert {rows["job_owner_sync"], rows["job_second"]} <= type_ids
    assert rows["job_owner_ingest"] not in type_ids  # ingest_url 被 type 谓词排除
    assert by_type["total"] == len(type_ids)

    by_status = client.get(f"{ADMIN_JOBS}?status=QUEUED").json()["data"]
    queued_ids = {i["jobId"] for i in by_status["items"]}
    assert seeded <= queued_ids
    assert by_status["total"] == len(queued_ids)

    done = client.get(f"{ADMIN_JOBS}?status=SUCCEEDED").json()["data"]
    done_ids = {i["jobId"] for i in done["items"]}
    assert not done_ids & seeded  # 播种集合全为 QUEUED，必须被 SUCCEEDED 谓词排除
    assert done["total"] == len(done_ids)


async def test_count_by_user_zero_condition_returns_real_count(db_session) -> None:  # type: ignore[no-untyped-def]
    """F-24：零条件求总数不得退化成 `SELECT count(*)`（无 FROM，恒返 1）。

    `with_only_columns(func.count())` 会把 SELECT 列换成标量函数，SQLAlchemy 随即剪掉
    它不引用的 FROM。历史实现靠 `Job.user_id == user_id` 这个**恒有**的谓词把 FROM 顶住，
    所以从未暴露；`user_id` 放开为可选（跨用户清单）后，零条件路径的 total 恒为 1——
    列表有 3 条、总数报 1，分页控件按 1 页渲染，跨用户清单完全不可用。
    """
    repo = JobRepository(db_session)
    # 基线在播种前取：夹具只在**写侧**隔离，读侧可见环境已提交的其他 Job（人工 QA 数据），
    # 故用「基线 + 增量」而非全局绝对值。owner/second 两个分支不受影响——
    # 二者是本用例新建 UUID，全库唯一。
    base_all = await repo.count_by_user(None)
    base_queued = await repo.count_by_user(None, status="QUEUED")
    base_done = await repo.count_by_user(None, status="SUCCEEDED")
    base_sync = await repo.count_by_user(None, job_type="sync_account")

    rows = await _seed(db_session)
    assert await repo.count_by_user(None) == base_all + 3
    assert await repo.count_by_user(None, status="QUEUED") == base_queued + 3
    assert await repo.count_by_user(None, status="SUCCEEDED") == base_done
    assert await repo.count_by_user(None, job_type="sync_account") == base_sync + 2
    assert await repo.count_by_user(rows["owner"]) == 2
    assert await repo.count_by_user(rows["second"]) == 1

    # 编译口径核对：count 语句必须带 jobs 表，不能退化成无 FROM 的 `count(*)`
    compiled = str(
        repo._job_stmt(None, None, None)
        .with_only_columns(func.count())
        .select_from(Job)
        .compile(compile_kwargs={"literal_binds": True})
    )
    assert "FROM jobs" in compiled, compiled

    raw = await db_session.scalar(select(func.count()).select_from(Job))
    assert raw == await repo.count_by_user(None)
    assert (await db_session.scalar(text("select count(*) from jobs"))) == raw


async def test_admin_get_job_cross_user_shows_counts(db_session) -> None:  # type: ignore[no-untyped-def]
    """admin 查他人 Job 详情：JobItem counts 与 error 文本可见（排障必需）。"""
    rows = await _seed(db_session)
    item_repo = JobItemRepository(db_session)

    # 造一篇 FAILED——验证 counts 与 failedItems 明细走同一批行
    items = await item_repo.list_by_job(rows["job_owner_sync"])
    await item_repo.set_status(items[2].id, "FAILED", "20003 EXTRACT_QUALITY_LOW: 质量分过低")
    await db_session.commit()

    client = _app(db_session, rows["admin"])
    resp = client.get(ADMIN_JOB.format(job_id=rows["job_owner_sync"]))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["jobId"] == rows["job_owner_sync"]
    assert data["counts"] == {"total": 3, "succeeded": 2, "failed": 1, "pending": 0}
    assert data["error"] == ""
    # 篇级失败明细：只有 job 级一行 error 时，用户看不出哪几篇失败、能否重试
    assert data["failedItems"] == [
        {
            "itemId": items[2].id,
            "url": "https://x/3",
            "error": "20003 EXTRACT_QUALITY_LOW: 质量分过低",
            "retryCount": 0,
        }
    ]

    status, code = _hit(client, "get", ADMIN_JOB.format(job_id=JOB_ID_MISSING))
    assert (status, code) == (404, 30004)


# ------------------------------------------------------------------ GET /admin/subscriptions


async def test_admin_list_subscriptions_all_spaces_with_owner(db_session) -> None:  # type: ignore[no-untyped-def]
    """space_id 省略 → 全系统所有空间的订阅，每条带归属四字段（无 N+1）。"""
    rows = await _seed(db_session)
    client = _app(db_session, rows["admin"])

    resp = client.get(ADMIN_SUBS)
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    # 本套件共用线上 PG（未设 AIDEANBOT_TEST_PG_DSN，见 conftest 警告）：全系统清单
    # 会带回其他环境的订阅行，故按本用例种子的 sub id 定位，不断言绝对条数。
    item = next(i for i in items if i["subscriptionId"] == rows["sub"])
    assert item["subscriptionId"] == rows["sub"]
    assert item["sourceName"] == "R48 测试号" and item["biz"] == "biz-r48"
    assert item["syncPolicy"] == "auto" and item["syncIntervalMinutes"] == 120
    assert item["discoveredCount"] == 1
    for key, value in (("spaceId", rows["space_b"]), ("spaceName", "R48 租户B空间"),
                       ("ownerId", rows["second"]), ("ownerNickname", "second")):
        assert item[key] == value, key
    assert item["latestJobId"] == rows["job_second"]


async def test_admin_list_subscriptions_space_filter_and_invalid_space(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """space_id 过滤跨用户生效；无效空间 → 30004（不校验会让「无空间」与「无订阅」不分）。"""
    rows = await _seed(db_session)
    client = _app(db_session, rows["admin"])

    own = client.get(f"{ADMIN_SUBS}?space_id={rows['space_a']}").json()["data"]["items"]
    assert own == []  # A 的空间有订阅，且不做归属校验

    other = client.get(f"{ADMIN_SUBS}?space_id={rows['space_b']}").json()["data"]["items"]
    assert [i["subscriptionId"] for i in other] == [rows["sub"]]

    status, code = _hit(client, "get", f"{ADMIN_SUBS}?space_id={SPACE_ID_MISSING}")
    assert (status, code) == (404, 30004)


async def test_admin_latest_job_id_uses_subscriber_not_caller(db_session) -> None:  # type: ignore[no-untyped-def]
    """latestJobId 的归属取订阅本人，而非调用方。

    旧实现按调用方 user_id 过滤 Job；admin 路径下调用方并非订阅者，
    他人订阅的 latestJobId 会被静默过滤成空串，前端据此判断「从未同步」。
    这里给 admin 自己造一个不同幂等键的 Job，断言 admin 不会因此被误配。
    """
    rows = await _seed(db_session)
    admin_job = Job(type="sync_account", user_id=rows["admin"], idempotency_key="sync_account:r48-admin")
    db_session.add(admin_job)
    await db_session.flush()

    items = _app(db_session, rows["admin"]).get(ADMIN_SUBS).json()["data"]["items"]
    item = next(i for i in items if i["subscriptionId"] == rows["sub"])
    assert item["latestJobId"] == rows["job_second"]  # 订阅者 B 的 Job，不是 admin 的


# ------------------------------------------------------------------ 授权门禁


async def test_admin_r48_role_gate_and_requires_login(db_session) -> None:  # type: ignore[no-untyped-def]
    """三条新端点同门禁：非 admin → 10004/403，未登录 → 10001。"""
    rows = await _seed(db_session)
    paths = [
        ADMIN_JOBS,
        ADMIN_JOB.format(job_id=rows["job_owner_sync"]),
        ADMIN_SUBS,
    ]
    for actor_key in ("owner", "operator"):
        client = _app(db_session, rows[actor_key])
        for path in paths:
            status, code = _hit(client, "get", path)
            assert (status, code) == (403, 10004), (actor_key, path)

    client = _unauth_client(db_session)
    for path in paths:
        status, code = _hit(client, "get", path)
        assert (status, code) == (401, 10001), path


async def test_user_job_routes_no_regression(db_session) -> None:  # type: ignore[no-untyped-def]
    """零回归锁：本人端点不动——只列本人 Job，他人 Job 详情仍 30004。"""
    rows = await _seed(db_session)
    client = _app(db_session, rows["second"])

    items = client.get("/api/v1/jobs").json()["data"]["items"]
    assert [i["jobId"] for i in items] == [rows["job_second"]]  # 只列本人

    status, code = _hit(client, "get", f"/api/v1/jobs/{rows['job_owner_sync']}")
    assert (status, code) == (404, 30004)  # 他人 Job 不泄露存在性
    status, code = _hit(client, "get", f"/api/v1/jobs/{JOB_ID_MISSING}")
    assert (status, code) == (404, 30004)  # 与「他人」同码，可区分性由门禁而非错误码承担


async def test_user_subscription_routes_no_regression(db_session) -> None:  # type: ignore[no-untyped-def]
    """零回归锁：本人订阅端点不动——他人空间仍 30004。"""
    rows = await _seed(db_session)
    client = _app(db_session, rows["second"])

    status, code = _hit(client, "get", f"/api/v1/spaces/{rows['space_a']}/subscriptions")
    assert (status, code) == (404, 30004)
    own = client.get(f"/api/v1/spaces/{rows['space_b']}/subscriptions").json()["data"]["items"]
    assert [i["subscriptionId"] for i in own] == [rows["sub"]]


# ------------------------------------------------------------------ PATCH /sources/{id}


async def test_patch_source_admin_partial_update(db_session) -> None:  # type: ignore[no-untyped-def]
    """admin 改全局源展示名 / 上游地址（部分更新）。"""
    rows = await _seed(db_session)
    client = _app(db_session, rows["admin"])

    resp = client.patch(PATCH_SOURCE.format(source_id=rows["source"]), json={"name": "改名后"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data == {
        "sourceId": rows["source"], "biz": "biz-r48", "name": "改名后",
        "url": "https://redfox.hk/apis/gongzhonghao/biz-r48",
    }

    resp = client.patch(PATCH_SOURCE.format(source_id=rows["source"]), json={"url": "https://x/y"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["url"] == "https://x/y" and data["name"] == "改名后"  # 省略字段不改

    row = await db_session.get(Source, rows["source"])
    assert row is not None and row.name == "改名后" and row.url == "https://x/y"


async def test_patch_source_dedup_anchor_immutable_and_missing_404(db_session) -> None:  # type: ignore[no-untyped-def]
    """type/external_id 不可写（uq_source_type_external 去重锚）；无效 id → 30004。

    这两个字段是跨用户去重与 CASCADE 引用链的锚，改了等于删后重建，
    故服务端**忽略**而非报错（部分更新语义：只认已知字段）。
    """
    rows = await _seed(db_session)
    client = _app(db_session, rows["admin"])

    resp = client.patch(
        PATCH_SOURCE.format(source_id=rows["source"]),
        json={"type": "web", "external_id": "hijack", "name": "仍可改"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["biz"] == "biz-r48" and data["name"] == "仍可改"

    row = await db_session.get(Source, rows["source"])
    assert row is not None and row.type == "wechat_oa" and row.external_id == "biz-r48"

    status, code = _hit(
        _app(db_session, rows["admin"]), "patch",
        PATCH_SOURCE.format(source_id=SOURCE_ID_MISSING), json={"name": "x"},
    )
    assert (status, code) == (404, 30004)


async def test_patch_source_role_gate_and_requires_login(db_session) -> None:  # type: ignore[no-untyped-def]
    """写面收口：非 admin → 10004/403，未登录 → 10001，且拒绝时零写入。"""
    rows = await _seed(db_session)
    for actor_key in ("owner", "second", "operator"):
        status, code = _hit(
            _app(db_session, rows[actor_key]), "patch",
            PATCH_SOURCE.format(source_id=rows["source"]), json={"name": "越权改名"},
        )
        assert (status, code) == (403, 10004), actor_key

    status, code = _hit(
        _unauth_client(db_session), "patch",
        PATCH_SOURCE.format(source_id=rows["source"]), json={"name": "未登录"},
    )
    assert (status, code) == (401, 10001)

    row = await db_session.get(Source, rows["source"])
    assert row is not None and row.name == "R48 测试号"


# ------------------------------------------------------------------ F-23：GET /sources 口径


async def test_list_sources_is_global_registry_not_user_scoped(db_session) -> None:  # type: ignore[no-untyped-def]
    """F-23：GET /sources 返回全用户共享清单，不含调用方未注册的源。

    `sources` 表无 user_id 列，「我的信息源」无定义。旧签名收了 user_id 却从不过滤，
    是契约误导；本次修正确保端点行为与文档一致（全局清单 + 登录闸门）。

    读侧不隔离，环境里可能已有其他业务注册的源——按 sourceId 取本用例播种的那条
    断言，而非断言清单长度。
    """
    rows = await _seed(db_session)
    resp = _app(db_session, rows["owner"]).get("/api/v1/sources")
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    by_id = {i["sourceId"]: i for i in items}
    assert rows["source"] in by_id  # 全量清单包含其他用户注册的源，非用户作用域
    item = by_id[rows["source"]]
    assert item["biz"] == "biz-r48"
    # 视图只暴露公开标识，无用户可识别信息
    assert set(item) == {"sourceId", "biz", "name", "url", "status"}

    # 类型过滤走取值语义（未知取值 → 空列表，读路径不设校验闸门）
    assert _app(db_session, rows["owner"]).get("/api/v1/sources?type=web").json()["data"]["items"] == []

    status, code = _hit(_unauth_client(db_session), "get", "/api/v1/sources")
    assert (status, code) == (401, 10001)


def test_list_subscriptions_service_signature_has_no_user_scope() -> None:
    """服务层锁：list_sources 不接受 user_id（死参数移除后不应回归）。

    W8 C.1 后增 limit/offset（SQL 分页），仍无 user_id 死参数。
    """
    import inspect

    from app.services.subscription import SourceSubscriptionService

    sig = inspect.signature(SourceSubscriptionService.list_sources)
    assert list(sig.parameters) == ["self", "source_type", "limit", "offset"], list(sig.parameters)
    assert sig.parameters["source_type"].default == "wechat_oa"
    assert sig.parameters["limit"].default == 50
    assert sig.parameters["offset"].default == 0


# ------------------------------------------------------------------ 路由注册锚


async def test_r48_admin_routes_registered(db_session) -> None:  # type: ignore[no-untyped-def]
    """R4.8 路由注册锚：三条 admin 读端点 + PATCH /sources 经 OpenAPI 契约核对。

    同时锁「信息源清单未在 admin 域重复」——那是同一份数据的第二条路径。
    """
    paths = create_app().openapi()["paths"]
    assert set(paths["/api/v1/admin/jobs"].keys()) == {"get"}
    assert set(paths["/api/v1/admin/jobs/{job_id}"].keys()) == {"get"}
    assert set(paths["/api/v1/admin/jobs/{job_id}:cancel"].keys()) == {"post"}
    assert set(paths["/api/v1/admin/jobs/{job_id}:retry"].keys()) == {"post"}
    assert set(paths["/api/v1/admin/subscriptions"].keys()) == {"get"}
    assert set(paths["/api/v1/admin/subscriptions/{subscription_id}"].keys()) == {"delete"}
    assert set(paths["/api/v1/admin/sources"].keys()) == {"get"}
    assert set(paths["/api/v1/admin/sources/{source_id}"].keys()) == {"delete"}

    rows = await _seed(db_session)
    admin_items = _app(db_session, rows["admin"]).get(ADMIN_SUBS).json()["data"]["items"]
    assert {"spaceId", "spaceName", "ownerId", "ownerNickname"} <= set(admin_items[0])

    # 本人端点不带归属字段（admin 端点单独存在，既有契约零回归）
    own = _app(db_session, rows["second"]).get(
        f"/api/v1/spaces/{rows['space_b']}/subscriptions"
    ).json()["data"]["items"]
    assert not ({"spaceId", "spaceName", "ownerId", "ownerNickname"} & set(own[0]))


# ------------------------------------------------------------------ R7.4 Admin 操作性补全验收


ADMIN_JOB_CANCEL = "/api/v1/admin/jobs/{job_id}:cancel"
ADMIN_JOB_RETRY = "/api/v1/admin/jobs/{job_id}:retry"
ADMIN_SUB_CANCEL = "/api/v1/admin/subscriptions/{subscription_id}"
ADMIN_SOURCES = "/api/v1/admin/sources"
ADMIN_SOURCE = "/api/v1/admin/sources/{source_id}"


async def test_r74_admin_cancel_job(db_session: Any) -> None:
    """R7.4.1：admin 跨用户取消 QUEUED Job；RUNNING/终态拒绝。"""
    rows = await _seed(db_session)
    admin = _app(db_session, rows["admin"])

    job_queued = Job(type="ingest_url", user_id=rows["owner"], idempotency_key="r74-q-1")
    db_session.add(job_queued)
    await db_session.commit()

    r = admin.post(ADMIN_JOB_CANCEL.format(job_id=job_queued.id))
    assert r.status_code == 200
    assert r.json()["data"]["ok"] is True
    assert r.json()["data"]["status"] == "CANCELLED"

    job_running = Job(type="ingest_url", user_id=rows["owner"], idempotency_key="r74-r-1", status="RUNNING")
    db_session.add(job_running)
    await db_session.commit()

    r = admin.post(ADMIN_JOB_CANCEL.format(job_id=job_running.id))
    assert r.json()["code"] == 30005

    r = admin.post(ADMIN_JOB_CANCEL.format(job_id=job_queued.id))
    assert r.json()["code"] == 30005

    r = _app(db_session, rows["owner"]).post(ADMIN_JOB_CANCEL.format(job_id=job_queued.id))
    assert r.json()["code"] == 10004


async def test_r74_admin_retry_job(db_session: Any) -> None:
    """R7.4.2：admin 跨用户重试 FAILED Job（FAILED ItemItem → PENDING，Job → QUEUED）。"""
    rows = await _seed(db_session)
    admin = _app(db_session, rows["admin"])

    job = Job(type="ingest_url", user_id=rows["owner"], idempotency_key="r74-retry-1", status="FAILED")
    db_session.add(job)
    await db_session.flush()
    item = JobItem(job_id=job.id, external_id="w-r74-1", url="https://x/r74")
    item.status = "FAILED"
    db_session.add(item)
    await db_session.commit()

    r = admin.post(ADMIN_JOB_RETRY.format(job_id=job.id))
    assert r.status_code == 200
    assert r.json()["data"]["retried"] == 1
    assert r.json()["data"]["status"] == "QUEUED"

    r = _app(db_session, rows["owner"]).post(ADMIN_JOB_RETRY.format(job_id=job.id))
    assert r.json()["code"] == 10004


async def test_r74_admin_cancel_subscription(db_session: Any) -> None:
    """R7.4.3：admin 跨用户退订（幂等：已退订 → cancelled=False）。"""
    rows = await _seed(db_session)
    admin = _app(db_session, rows["admin"])

    r = admin.delete(ADMIN_SUB_CANCEL.format(subscription_id=rows["sub"]))
    assert r.status_code == 200
    assert r.json()["data"]["ok"] is True
    assert r.json()["data"]["cancelled"] is True

    r = admin.delete(ADMIN_SUB_CANCEL.format(subscription_id=rows["sub"]))
    assert r.status_code == 200
    assert r.json()["data"]["cancelled"] is False

    r = _app(db_session, rows["owner"]).delete(ADMIN_SUB_CANCEL.format(subscription_id=rows["sub"]))
    assert r.json()["code"] == 10004


async def test_r74_admin_list_sources(db_session: Any) -> None:
    """R7.4.4：admin 信息源清单含引用计数。"""
    rows = await _seed(db_session)
    admin = _app(db_session, rows["admin"])

    r = admin.get(ADMIN_SOURCES)
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert len(items) >= 1
    src_item = next(i for i in items if i["sourceId"] == rows["source"])
    assert "subscriptionCount" in src_item
    assert "assetCount" in src_item
    assert "manifestCount" in src_item

    r = _app(db_session, rows["owner"]).get(ADMIN_SOURCES)
    assert r.json()["code"] == 10004


async def test_r74_admin_delete_source(db_session: Any) -> None:
    """R7.4.5：admin 删除零引用信息源；有引用 → 10005。"""
    rows = await _seed(db_session)
    admin = _app(db_session, rows["admin"])

    r = admin.delete(ADMIN_SOURCE.format(source_id=rows["source"]))
    assert r.json()["code"] == 10005

    orphan = Source(type="wechat_oa", external_id="biz-r74-orphan", name="R74 孤儿源")
    db_session.add(orphan)
    await db_session.commit()

    r = admin.delete(ADMIN_SOURCE.format(source_id=orphan.id))
    assert r.status_code == 200
    assert r.json()["data"]["ok"] is True
