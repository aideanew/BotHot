"""R0.2.3 订阅生命周期端点：PATCH/DELETE /spaces/{id}/subscriptions/{subId} + DELETE /sources/{id}。

F-2 背景：此前订阅只有 POST（建）与 GET（列），无编辑、无退订；
信息源只有 POST/GET，无删除。整号采集管道建成后「订了就订着」——改不了频率、退不掉。

口径锚点（前端与 A 契约须同口径）：
- 改间隔只可能把 next_run_at **往前**拉（更频繁），绝不把已逾期的一次同步往后推；
- 退订是软取消（status=CANCELLED + next_run_at=None），**不删任何文档/资产/清单**；
- DELETE /sources 的闸门是「订阅 + 资产 + 清单」三者皆空，而非大纲所写的仅「订阅」——
  三张子表全是 ondelete=CASCADE，而 content_assets 又被 knowledge_documents CASCADE
  引用，只挡订阅会级联删掉文档行（证据链见 services/subscription.py::delete_source）；
- sync_policy 此前是无校验自由文本且调度器从不读取（契约失实）；
  建订阅与改订阅现共用同一白名单谓词。

注意：夹具为 savepoint 模式 + `expire_on_commit=False`，`session.get()` 会返回
identity map 里的旧对象——凡「行是否真被删」的断言必须走 SQL 查询，不能靠 `get()`。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_current_user_id, get_db
from app.core.errors import ResourceNotFoundError
from app.main import create_app
from app.models.entities import (
    ArticleManifest,
    ContentAsset,
    KnowledgeSpace,
    Source,
    SourceSubscription,
    User,
)
from app.repositories.subscription import SourceSubscriptionRepository
from app.services.subscription import SourceSubscriptionService

ID_UNKNOWN = "00000000-0000-0000-0000-000000000009"

# 固定时点锚的时区口径（须与 backend/app/core/config.py::scheduler_timezone 一致）
SZ = ZoneInfo("Asia/Shanghai")


# ------------------------------------------------------------------ 桩与夹具


async def _seed(
    db_session: Any,
    *,
    sub: str,
    source_name: str = "R02源",
    with_subscription: bool = True,
    next_run_at: datetime | None = None,
    with_assets: int = 0,
    with_manifests: int = 0,
    with_other_users_subscription: bool = False,
    role: str = "user",
) -> dict[str, Any]:
    """铺一条最小数据链：user → space → source（→ subscription/assets/manifests）。

    返回 {user, space, source, sub_row}（无订阅时 sub_row 为 None）。
    """
    user = User(sub=sub, email=f"{sub}@test.local", nickname=sub, role=role)
    db_session.add(user)
    await db_session.flush()
    space = KnowledgeSpace(user_id=user.id, name=f"R02订阅空间-{sub}", langbot_kb_uuid="kb-r02s", engine="builtin")
    db_session.add(space)
    await db_session.flush()
    source = Source(type="wechat_oa", external_id=f"biz-{sub}", name=source_name, url="https://mp.weixin.qq.com")
    db_session.add(source)
    await db_session.flush()

    sub_row: SourceSubscription | None = None
    if with_subscription:
        sub_row = SourceSubscription(
            user_id=user.id,
            source_id=source.id,
            space_id=space.id,
            sync_policy="auto",
            sync_interval_minutes=360,
            next_run_at=next_run_at,
            status="ACTIVE",
        )
        db_session.add(sub_row)
        await db_session.flush()

    for i in range(with_assets):
        db_session.add(
            ContentAsset(
                source_id=source.id,
                external_id=f"a-{i}",
                url=f"https://mp.weixin.qq.com/s/a-{i}",
                title=f"资产 {i}",
                content_hash=f"h-{i}",
                content_markdown=f"# {i}",
            )
        )
    for i in range(with_manifests):
        db_session.add(
            ArticleManifest(
                source_id=source.id,
                external_id=f"m-{i}",
                url=f"https://mp.weixin.qq.com/s/m-{i}",
                title=f"清单 {i}",
                content_hash=f"mh-{i}",
                status="DISCOVERED",
            )
        )
    if with_assets or with_manifests:
        await db_session.flush()

    if with_other_users_subscription:
        other = User(sub=f"{sub}-other", email=f"{sub}-other@test.local", nickname=f"{sub}-other")
        db_session.add(other)
        await db_session.flush()
        other_space = KnowledgeSpace(
            user_id=other.id, name=f"他空间-{sub}", langbot_kb_uuid="kb-other", engine="builtin"
        )
        db_session.add(other_space)
        await db_session.flush()
        db_session.add(
            SourceSubscription(
                user_id=other.id,
                source_id=source.id,
                space_id=other_space.id,
                sync_policy="auto",
                next_run_at=datetime.now(UTC),
                status="ACTIVE",
            )
        )
        await db_session.flush()

    await db_session.commit()  # savepoint 模式：只释放保存点，外层回滚清场
    return {"user": user, "space": space, "source": source, "sub_row": sub_row}


def _client(db_session: Any, user_id: str) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def _path(d: dict[str, Any]) -> str:
    return f"/api/v1/spaces/{d['space'].id}/subscriptions/{d['sub_row'].id}"


async def _row_exists(db_session: Any, model: Any, pk: str) -> bool:
    """走 SQL 的「行是否还在」判定（不依赖 identity map 缓存）。"""
    return await db_session.scalar(select(model.id).where(model.id == pk)) is not None


# ------------------------------------------------------------------ PATCH 订阅


async def test_patch_subscription_interval_pulled_forward(db_session) -> None:
    """间隔改小 → syncIntervalMinutes 落库，next_run_at 被往前拉到 now+interval。"""
    far = datetime.now(UTC) + timedelta(days=3)
    d = await _seed(db_session, sub="r02s-short", next_run_at=far)
    client = _client(db_session, d["user"].id)

    resp = client.patch(_path(d), json={"sync_interval_minutes": 60})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["syncIntervalMinutes"] == 60
    assert data["syncPolicy"] == "auto"
    assert data["status"] == "ACTIVE"

    new_due = datetime.fromisoformat(data["nextRunAt"])
    assert new_due < far, "改勤必须往前拉，不能往后推"
    assert timedelta(minutes=55) < (new_due - datetime.now(UTC)) < timedelta(minutes=65), (
        "next_run_at 应等于 now + 60 分钟"
    )


async def test_patch_subscription_interval_never_pushes_overdue_back(db_session) -> None:
    """间隔改大但已有**逾期**同步 → next_run_at 不动（不能让用户跳过期望中的同步）。"""
    overdue = datetime.now(UTC) - timedelta(minutes=30)
    d = await _seed(db_session, sub="r02s-late", next_run_at=overdue)
    client = _client(db_session, d["user"].id)

    resp = client.patch(_path(d), json={"sync_interval_minutes": 1000})
    assert resp.status_code == 200, resp.text
    got = datetime.fromisoformat(resp.json()["data"]["nextRunAt"])
    assert got == overdue, "逾期同步不应被往后推"


async def test_patch_subscription_policy_and_validation(db_session) -> None:
    """sync_policy=auto 可写；非法取值 / 间隔越界 → 10005/422 且不改库。"""
    d = await _seed(db_session, sub="r02s-policy")
    client = _client(db_session, d["user"].id)

    ok = client.patch(_path(d), json={"sync_policy": "auto", "sync_interval_minutes": 120})
    assert ok.status_code == 200 and ok.json()["data"]["syncIntervalMinutes"] == 120

    for bad_body in (
        {"sync_policy": "daily"},
        {"sync_policy": ""},
        {"sync_interval_minutes": 1},
        {"sync_interval_minutes": 99999},
    ):
        resp = client.patch(_path(d), json=bad_body)
        assert resp.status_code == 422 and resp.json()["code"] == 10005, (bad_body, resp.text)

    sub = await db_session.get(SourceSubscription, d["sub_row"].id)
    assert sub is not None
    assert sub.sync_policy == "auto" and sub.sync_interval_minutes == 120, "校验失败不得改库"


@pytest.mark.parametrize("interval", [4, 4321])
async def test_patch_subscription_interval_boundary_rejected(db_session, interval: int) -> None:
    """间隔上下界外推（5 分钟下限 / 4320 上限）→ 10005/422。"""
    d = await _seed(db_session, sub=f"r02s-bd-{interval}")
    client = _client(db_session, d["user"].id)
    resp = client.patch(_path(d), json={"sync_interval_minutes": interval})
    assert resp.status_code == 422 and resp.json()["code"] == 10005


async def test_patch_subscription_cancelled_not_rescheduled(db_session) -> None:
    """已退订的订阅允许改值，但 next_run_at 保持 None（不再重排）。"""
    d = await _seed(db_session, sub="r02s-off")
    client = _client(db_session, d["user"].id)
    assert client.delete(_path(d)).status_code == 200

    resp = client.patch(_path(d), json={"sync_interval_minutes": 30})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["syncIntervalMinutes"] == 30
    assert data["status"] == "CANCELLED"
    assert data["nextRunAt"] == ""


async def test_patch_subscription_empty_body_is_noop(db_session) -> None:
    """空 body = 全字段省略 → 200 无副作用（部分更新语义）。"""
    d = await _seed(db_session, sub="r02s-empt", next_run_at=datetime.now(UTC) + timedelta(days=2))
    client = _client(db_session, d["user"].id)
    resp = client.patch(_path(d), json={})
    assert resp.status_code == 200
    assert resp.json()["data"]["syncIntervalMinutes"] == 360


async def test_patch_subscription_anchor_sets_daily_hour(db_session) -> None:
    """设固定时点锚 → next_run_at 对准「下一次每天 10:00」（调度器时区 Asia/Shanghai）。"""
    d = await _seed(db_session, sub="r02s-anchor")
    client = _client(db_session, d["user"].id)

    resp = client.patch(_path(d), json={"sync_anchor_hour": 10})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["syncAnchorHour"] == 10

    now_local = datetime.now(UTC).astimezone(SZ)
    due = datetime.fromisoformat(data["nextRunAt"]).astimezone(SZ)
    assert (due.hour, due.minute, due.second) == (10, 0, 0), f"锚点必须落在整点，实际 {due.isoformat()}"
    assert due > now_local, "锚点必须在未来"
    assert (due - now_local) <= timedelta(days=1), "锚点应是**最近**的一次整点，不能隔天以上"

    sub = await db_session.get(SourceSubscription, d["sub_row"].id)
    assert sub is not None and sub.sync_anchor_hour == 10, "锚值必须落库"


@pytest.mark.parametrize("hour", [-1, 24])
async def test_patch_subscription_anchor_boundary_rejected(db_session, hour: int) -> None:
    """锚值越界（0..23 之外）→ 10005/422，且不落库、不改水位。"""
    far = datetime.now(UTC) + timedelta(days=2)
    d = await _seed(db_session, sub=f"r02s-anchd-{hour}", next_run_at=far)
    client = _client(db_session, d["user"].id)
    resp = client.patch(_path(d), json={"sync_anchor_hour": hour})
    assert resp.status_code == 422 and resp.json()["code"] == 10005

    sub = await db_session.get(SourceSubscription, d["sub_row"].id)
    assert sub is not None
    assert sub.sync_anchor_hour is None and sub.next_run_at == far, "校验失败不得落库、不得动水位"


async def test_patch_subscription_anchor_null_clears_back_to_sliding(db_session) -> None:
    """显式传 null 清除锚定 → 回到滑动窗口（next_run_at ≈ now + interval），且列表同步反映。"""
    d = await _seed(db_session, sub="r02s-anchor-clear")
    client = _client(db_session, d["user"].id)
    assert client.patch(_path(d), json={"sync_anchor_hour": 10}).json()["data"]["syncAnchorHour"] == 10

    resp = client.patch(_path(d), json={"sync_anchor_hour": None})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["syncAnchorHour"] is None

    now = datetime.now(UTC)
    due = datetime.fromisoformat(data["nextRunAt"])
    assert timedelta(minutes=5) < (due - now) < timedelta(minutes=366), (
        f"清锚后应回到滑动窗口（now+interval×1），实际 {due.isoformat()}"
    )
    sub = await db_session.get(SourceSubscription, d["sub_row"].id)
    assert sub is not None and sub.sync_anchor_hour is None, "清除必须真落到 NULL"

    items = client.get(f"/api/v1/spaces/{d['space'].id}/subscriptions").json()["data"]["items"]
    assert items and items[0]["syncAnchorHour"] is None, "列表视图须同口径暴露锚值"


async def test_patch_subscription_anchor_cancelled_editable_not_rescheduled(db_session) -> None:
    """已退订的订阅允许改锚值，但不重排 next_run_at（与改间隔同纪律）。"""
    d = await _seed(db_session, sub="r02s-anchor-off")
    client = _client(db_session, d["user"].id)
    assert client.delete(_path(d)).status_code == 200

    resp = client.patch(_path(d), json={"sync_anchor_hour": 10})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "CANCELLED"
    assert data["nextRunAt"] == "", "退订后不得重排触发时间"

    sub = await db_session.get(SourceSubscription, d["sub_row"].id)
    assert sub is not None and sub.sync_anchor_hour == 10, "配置项应可改（保留用户设置）"


async def test_patch_subscription_authorization(db_session) -> None:
    """越权空间 / 不存在订阅 / 他人订阅 → 30004（不泄露存在性）。"""
    d = await _seed(db_session, sub="r02s-auth", with_other_users_subscription=True)
    client = _client(db_session, d["user"].id)

    assert client.patch("/api/v1/spaces/not-a-space/subscriptions/x", json={}).status_code == 404
    assert client.patch(f"/api/v1/spaces/{d['space'].id}/subscriptions/{ID_UNKNOWN}", json={}).status_code == 404

    # 他人订阅（同一 source，另一用户）——跨用户不可改
    subs = (
        await db_session.scalars(
            select(SourceSubscription).where(
                SourceSubscription.source_id == d["source"].id,
                SourceSubscription.user_id != d["user"].id,
            )
        )
    ).all()
    assert len(subs) == 1
    resp = client.patch(f"/api/v1/spaces/{d['space'].id}/subscriptions/{subs[0].id}", json={})
    assert resp.status_code == 404 and resp.json()["code"] == 30004


async def test_patch_subscription_requires_login() -> None:
    """登录保护：未登录 PATCH → 10001（不 override 鉴权依赖）。"""
    client = TestClient(create_app())
    resp = client.patch(f"/api/v1/spaces/{ID_UNKNOWN}/subscriptions/{ID_UNKNOWN}", json={})
    assert resp.status_code == 401 and resp.json()["code"] == 10001


# ------------------------------------------------------------------ DELETE 订阅


async def test_cancel_subscription_soft_and_keeps_data(db_session) -> None:
    """退订 = 软取消：status=CANCELLED + next_run_at=None，文档/资产/清单零删除。"""
    d = await _seed(
        db_session,
        sub="r02s-cancel",
        with_assets=2,
        with_manifests=3,
        next_run_at=datetime.now(UTC) + timedelta(hours=2),
    )
    client = _client(db_session, d["user"].id)
    resp = client.delete(_path(d))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["cancelled"] is True
    assert data["status"] == "CANCELLED"
    assert data["nextRunAt"] == ""

    sub = await db_session.get(SourceSubscription, d["sub_row"].id)
    assert sub is not None and sub.status == "CANCELLED" and sub.next_run_at is None
    # 按本用例的 source 限定：夹具只在写侧隔离，读侧可见环境里其他源
    # 的资产/清单行（人工 QA 数据），全表计数会把环境噪音误判成产品缺陷。
    assets = (
        (await db_session.execute(select(ContentAsset).where(ContentAsset.source_id == d["source"].id))).scalars().all()
    )
    manifests = (
        (await db_session.execute(select(ArticleManifest).where(ArticleManifest.source_id == d["source"].id)))
        .scalars()
        .all()
    )
    assert len(assets) == 2 and len(manifests) == 3, "退订不得删除资产或清单"


async def test_cancel_subscription_idempotent(db_session) -> None:
    """已退订再退订 → 200 且 cancelled=False（不报错）。"""
    d = await _seed(db_session, sub="r02s-idem")
    client = _client(db_session, d["user"].id)
    path = _path(d)
    assert client.delete(path).json()["data"]["cancelled"] is True
    second = client.delete(path)
    assert second.status_code == 200
    assert second.json()["data"]["cancelled"] is False
    assert second.json()["data"]["status"] == "CANCELLED"


async def test_cancel_subscription_unsubscribes_from_scheduler(db_session) -> None:
    """退订后 claim_due 不再认领（调度器双保险：status=ACTIVE 且 next_run_at 非空）。"""
    due = datetime.now(UTC) - timedelta(minutes=5)
    d = await _seed(db_session, sub="r02s-claim", next_run_at=due)
    repo = SourceSubscriptionRepository(db_session)
    assert (await repo.claim_due(datetime.now(UTC))) is not None, "退订前应能认领"

    client = _client(db_session, d["user"].id)
    assert client.delete(_path(d)).status_code == 200

    assert await repo.claim_due(datetime.now(UTC)) is None, "退订后不应再被认领"


async def test_cancel_subscription_authorization(db_session) -> None:
    """越权空间 / 不存在订阅 → 30004（不泄露存在性）。"""
    d = await _seed(db_session, sub="r02s-authz")
    client = _client(db_session, d["user"].id)
    assert client.delete("/api/v1/spaces/not-a-space/subscriptions/x").status_code == 404
    resp = client.delete(f"/api/v1/spaces/{d['space'].id}/subscriptions/{ID_UNKNOWN}")
    assert resp.status_code == 404 and resp.json()["code"] == 30004, resp.text


async def test_cancel_subscription_requires_login() -> None:
    """登录保护：未登录 DELETE → 10001。"""
    client = TestClient(create_app())
    resp = client.delete(f"/api/v1/spaces/{ID_UNKNOWN}/subscriptions/{ID_UNKNOWN}")
    assert resp.status_code == 401 and resp.json()["code"] == 10001


# ------------------------------------------------------------------ DELETE 信息源


async def test_delete_source_zero_references(db_session) -> None:
    """零下游引用 → 200 deleted，源行真消失（SQL 复核，不靠 identity map）。"""
    d = await _seed(db_session, sub="r02s-src", with_subscription=False, role="admin")
    client = _client(db_session, d["user"].id)

    resp = client.delete(f"/api/v1/sources/{d['source'].id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] == {
        "sourceId": d["source"].id,
        "deleted": True,
        "references": {"subscriptions": 0, "assets": 0, "manifests": 0},
    }

    assert not await _row_exists(db_session, Source, d["source"].id)


@pytest.mark.parametrize("kind", ["sub", "assets", "manifests"])
async def test_delete_source_rejected_when_referenced(db_session, kind: str) -> None:
    """任一子表有引用 → 10005/422 并附引用计数；源行保留。

    尤其 assets：大纲原口径「仅挡订阅」会级联删掉资产与文档行，此测锁定该闸门。
    """
    seed = {"sub": {}, "assets": {"with_assets": 1}, "manifests": {"with_manifests": 1}}[kind]
    d = await _seed(db_session, sub=f"r02s-ref-{kind}", role="admin", **seed)
    client = _client(db_session, d["user"].id)

    resp = client.delete(f"/api/v1/sources/{d['source'].id}")
    assert resp.status_code == 422 and resp.json()["code"] == 10005
    assert "引用" in resp.json()["message"]
    assert await _row_exists(db_session, Source, d["source"].id), "有引用时源行不得被删"


async def test_delete_source_cross_tenant_reference_blocks(db_session) -> None:
    """他人对同一源仍有订阅 → 拒绝删除（sources 无归属，闸门覆盖全用户）。"""
    d = await _seed(
        db_session,
        sub="r02s-xten",
        with_subscription=False,
        with_other_users_subscription=True,
        role="admin",
    )
    client = _client(db_session, d["user"].id)

    resp = client.delete(f"/api/v1/sources/{d['source'].id}")
    assert resp.status_code == 422 and resp.json()["code"] == 10005


async def test_delete_source_unknown_login_and_role(db_session) -> None:
    """不存在 → 30004；未登录 → 10001；非 admin → 10004/403。

    授权门在路由体之前生效，故先验角色再看 id 是否存在——非 admin 拿 403 而非 404，
    不泄露「该源是否存在」（越权探测面与其他域端点同口径）。
    """
    d = await _seed(db_session, sub="r02s-unk", with_subscription=False, role="admin")
    client = _client(db_session, d["user"].id)
    assert client.delete(f"/api/v1/sources/{ID_UNKNOWN}").status_code == 404

    anon = TestClient(create_app())
    assert anon.delete(f"/api/v1/sources/{d['source'].id}").status_code == 401

    for role in ("user", "operator"):
        plain = await _seed(db_session, sub=f"r02s-{role}", with_subscription=False, role=role)
        resp = _client(db_session, plain["user"].id).delete(f"/api/v1/sources/{d['source'].id}")
        assert resp.status_code == 403 and resp.json()["code"] == 10004, (role, resp.text)


# ------------------------------------------------------------------ 契约与回归


async def test_create_subscription_rejects_bad_policy(db_session) -> None:
    """建订阅现与改订阅共用同一谓词：非法策略 → 10005/422（此前是自由文本）。"""
    d = await _seed(db_session, sub="r02s-create", with_subscription=False)
    client = _client(db_session, d["user"].id)
    resp = client.post(
        f"/api/v1/spaces/{d['space'].id}/subscriptions",
        json={"source_id": d["source"].id, "sync_policy": "every-hour"},
    )
    assert resp.status_code == 422 and resp.json()["code"] == 10005


async def test_list_subscriptions_exposes_interval(db_session) -> None:
    """列表视图补 syncIntervalMinutes（与 PATCH 视图同口径）。"""
    d = await _seed(db_session, sub="r02s-list")
    client = _client(db_session, d["user"].id)
    resp = client.get(f"/api/v1/spaces/{d['space'].id}/subscriptions")
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["syncIntervalMinutes"] == 360


def test_r023_subscription_routes_registered() -> None:
    """R0.2.3 路由注册锚：三条新端点 + 既有端点未被覆盖。经 OpenAPI 契约核对。"""
    paths = create_app().openapi()["paths"]
    sub_path = "/api/v1/spaces/{space_id}/subscriptions/{subscription_id}"
    assert set(paths[sub_path].keys()) == {"patch", "delete"}
    # R4.8：PATCH（admin 改全局源）与 DELETE 同挂一个路径键——既有契约未变，仅多一方法
    assert set(paths["/api/v1/sources/{source_id}"].keys()) == {"delete", "patch"}
    assert {"get", "post"} <= set(paths["/api/v1/spaces/{space_id}/subscriptions"].keys())
    assert {"get", "post"} <= set(paths["/api/v1/sources"].keys())


async def test_service_delete_source_raises_for_missing_source(db_session) -> None:
    """服务层直测：无效源 → 30004（Route 之外的口径核对）。"""
    svc = SourceSubscriptionService(db_session)
    with pytest.raises(ResourceNotFoundError) as exc:
        await svc.delete_source(ID_UNKNOWN)
    assert exc.value.code == 30004
