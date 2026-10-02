"""M3 批次 2（SPEC-M3，A-2 叠加裁定 2026-09-23）验收测试：/api/v1/admin/* 跨用户端点。

A-2：既有用户端点（PATCH /spaces/{id}、DELETE /spaces/{id}/docs/{docId}）一律不动，
admin 的跨用户能力走**新增** /admin/* 端点。故本文件同时锁两侧——

- admin 端点：绕过归属校验，`admin` 放行，`user`/`operator` → 10004；
- 用户端点：跨用户写仍 30004（A-2 的「零回归」承诺不被本次 Service 改造削弱）。

Service 改造口径：update_space/delete_doc 各抽出 _update_space/_delete_doc 单一实现，
`owner=None` 表示无归属约束；两条入口的全部差异只在这一处判据。引擎先行顺序、失败
整体回滚、资产孤儿收敛、校验先于取行等契约不得在两份拷贝间漂移——本文件的
test_update_space_both_entries_validate_before_fetch 直接锁「单一实现」这一点。
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.api.deps import get_current_user_id, get_db, get_langbot_client, get_space_service
from app.core.errors import LangbotApiError
from app.main import create_app
from app.models.entities import ContentAsset, KnowledgeDocument, KnowledgeSpace, Source, User
from app.repositories.space import SpaceRepository
from app.services.spaces import SpaceService, SpaceValidationError

DOC_ID_MISSING = "00000000-0000-0000-0000-000000000001"
SPACE_ID_MISSING = "00000000-0000-0000-0000-000000000002"


class FakeKbClient:
    """LangBotClient 删除面桩：记录 delete_kb_file 调用，可注入失败。"""

    def __init__(self, fail: Exception | None = None) -> None:
        self.fail = fail
        self.deleted_files: list[tuple[str, str]] = []

    async def delete_kb_file(self, kb_uuid: str, file_id: str) -> None:
        if self.fail is not None:
            raise self.fail
        self.deleted_files.append((kb_uuid, file_id))

    async def delete_kb(self, kb_uuid: str) -> None:  # 协议完整性
        return None


# ------------------------------------------------------------------ 夹具


async def _seed(db_session: Any, *, file_id: str = "file-admin") -> dict[str, str]:
    """铺两个租户的最小数据链 + 三个角色账号。

    owner：space + doc（langbot_file_id=file_id）；second：space_b + doc_b——
    两条互不相干的用户链，admin 的跨用户操作对象就是 owner 的空间。
    admin/operator/user 三个角色账号无自有空间，专供授权门禁用例。
    """
    owner = User(sub="r11-admin-owner", email="r11-admin-owner@r11.test", nickname="owner")
    second = User(sub="r11-admin-second", email="r11-admin-second@r11.test", nickname="second")
    admin = User(sub="r11-admin-admin", email="r11-admin-admin@r11.test", nickname="admin", role="admin")
    operator = User(sub="r11-admin-operator", email="r11-admin-operator@r11.test", nickname="operator", role="operator")
    db_session.add_all([owner, second, admin, operator])
    await db_session.flush()

    source = Source(type="wechat_oa", external_id="biz-r11-admin", name="管理端测试号")
    db_session.add(source)
    await db_session.flush()

    space = KnowledgeSpace(user_id=owner.id, name="租户A空间", langbot_kb_uuid="kb-admin-a", doc_count=1)
    space_b = KnowledgeSpace(user_id=second.id, name="租户B空间", langbot_kb_uuid="kb-admin-b", doc_count=1)
    db_session.add_all([space, space_b])
    await db_session.flush()

    asset_a = ContentAsset(
        source_id=source.id,
        external_id="a-1",
        url="https://mp.weixin.qq.com/s/a1",
        title="A文章",
        content_hash="h-a1",
        content_markdown="# A",
        category="其他",
    )
    asset_b = ContentAsset(
        source_id=source.id,
        external_id="b-1",
        url="https://mp.weixin.qq.com/s/b1",
        title="B文章",
        content_hash="h-b1",
        content_markdown="# B",
        category="其他",
    )
    db_session.add_all([asset_a, asset_b])
    await db_session.flush()

    doc_a = KnowledgeDocument(asset_id=asset_a.id, space_id=space.id, langbot_file_id=file_id, status="READY")
    doc_b = KnowledgeDocument(asset_id=asset_b.id, space_id=space_b.id, langbot_file_id="file-b", status="READY")
    db_session.add_all([doc_a, doc_b])
    await db_session.flush()
    await db_session.commit()  # 夹具 savepoint 模式：只释放保存点，外层回滚清场

    return {
        "space": space.id,
        "space_b": space_b.id,
        "doc": doc_a.id,
        "doc_b": doc_b.id,
        "owner": owner.id,
        "second": second.id,
        "admin": admin.id,
        "operator": operator.id,
    }


def _app(db_session: Any, actor_id: str, kb: FakeKbClient | None = None) -> TestClient:
    """挂真实 PG 会话与 role 门禁的测试应用（依赖装配与生产一致，仅替换身份与客户端）。"""
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: actor_id
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_space_service] = lambda: SpaceService(SpaceRepository(db_session), db_session)
    if kb is not None:
        app.dependency_overrides[get_langbot_client] = lambda: kb  # type: ignore[arg-type]
    return TestClient(app)


def _hit(client: TestClient, method: str, path: str, **kwargs: Any) -> tuple[int, int]:
    """打一次请求，返回 (http_status, 业务码)。"""
    resp = getattr(client, method)(path, **kwargs)
    return resp.status_code, resp.json().get("code", -1)


# ------------------------------------------------------------------ admin PATCH


async def test_admin_patch_space_cross_user_persists(db_session) -> None:  # type: ignore[no-untyped-def]
    """A-2 的实际增量：admin 可改他人空间简介（既有端点强制本人 → 30004）。"""
    rows = await _seed(db_session)
    client = _app(db_session, rows["admin"], kb=FakeKbClient())

    resp = client.patch(f"/api/v1/admin/spaces/{rows['space']}", json={"description": "管理端改写"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {"ok": True, "id": rows["space"], "description": "管理端改写"}

    space = await db_session.get(KnowledgeSpace, rows["space"])
    assert space is not None and space.description == "管理端改写"


async def test_admin_patch_space_accepts_empty_string_to_clear(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """与既有端点同契约："" 表示清空为「未填写」，不是校验失败。"""
    rows = await _seed(db_session)
    space = await db_session.get(KnowledgeSpace, rows["space"])
    assert space is not None and space.description is None
    client = _app(db_session, rows["admin"], kb=FakeKbClient())

    resp = client.patch(f"/api/v1/admin/spaces/{rows['space']}", json={"description": "先写后清"})
    assert resp.status_code == 200, resp.text
    resp = client.patch(f"/api/v1/admin/spaces/{rows['space']}", json={"description": ""})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["description"] == ""

    space = await db_session.get(KnowledgeSpace, rows["space"])
    assert space is not None and space.description == ""


async def test_admin_patch_space_requires_description_and_rejects_invalid(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """description 是 admin 端点唯一可写字段：缺失 → 10005，不产生写入。

    既有端点容忍 null（PATCH 部分更新语义，返回详情视图）；admin 端点返回写回执，
    无可写内容即客户端 bug，故拒绝而非静默 no-op。
    """
    rows = await _seed(db_session)
    client = _app(db_session, rows["admin"], kb=FakeKbClient())

    for payload in ({}, {"description": None}, {"description": "x" * 600}, {"description": "a\nb"}):
        status, code = _hit(client, "patch", f"/api/v1/admin/spaces/{rows['space']}", json=payload)
        assert status == 422 and code == 10005, (payload, status, code)

    space = await db_session.get(KnowledgeSpace, rows["space"])
    assert space is not None and space.description is None  # 四次失败均零写入


async def test_admin_patch_space_invalid_id_30004(db_session) -> None:  # type: ignore[no-untyped-def]
    """无效空间 → 30004/404，不泄露存在性（与既有端点同语义）。"""
    rows = await _seed(db_session)
    status, code = _hit(
        _app(db_session, rows["admin"], kb=FakeKbClient()),
        "patch",
        f"/api/v1/admin/spaces/{SPACE_ID_MISSING}",
        json={"description": "x"},
    )
    assert (status, code) == (404, 30004)


async def test_update_space_both_entries_validate_before_fetch(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """单一实现锁：两条入口共用 _update_space，非法取值在任何 DB 读之前拒绝。

    若简介校验顺序在两份拷贝里各写一份，很容易出现「owner 入口先取行、admin 入口
    先校验」的漂移——非法取值对不存在的空间会返回 30004 而非 10005。
    """
    rows = await _seed(db_session)
    svc = SpaceService(SpaceRepository(db_session), db_session)
    bad = "x" * 600
    for call in (
        lambda: svc.update_space(rows["owner"], SPACE_ID_MISSING, bad),
        lambda: svc.update_space_any(SPACE_ID_MISSING, bad),
    ):
        try:
            await call()
        except SpaceValidationError:
            pass
        else:  # noqa: B012
            raise AssertionError("非法简介未在任何取行之前被拒绝")


# ------------------------------------------------------------------ admin DELETE


async def test_admin_delete_doc_cross_user_engine_first(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """A-2 的实际增量：admin 可删他人空间的文档，引擎先行顺序不变。"""
    rows = await _seed(db_session)
    kb = FakeKbClient()
    client = _app(db_session, rows["admin"], kb=kb)

    resp = client.delete(f"/api/v1/admin/spaces/{rows['space']}/docs/{rows['doc']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {
        "ok": True,
        "docId": rows["doc"],
        "docs": 1,
        "assets": 1,
    }
    assert kb.deleted_files == [("kb-admin-a", "file-admin")]  # 引擎先删且用 langbot_kb_uuid

    assert await db_session.get(KnowledgeDocument, rows["doc"]) is None
    space = await db_session.get(KnowledgeSpace, rows["space"])
    assert space is not None and space.doc_count == 0


async def test_admin_delete_doc_engine_failure_rolls_back(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """引擎失败 → 错误信封，PG 行保留（不出现「PG 删了库没删」）。"""
    rows = await _seed(db_session)
    kb = FakeKbClient(fail=LangbotApiError("LangBot 删除失败: 500"))
    client = _app(db_session, rows["admin"], kb=kb)

    resp = client.delete(f"/api/v1/admin/spaces/{rows['space']}/docs/{rows['doc']}")
    assert resp.status_code == 502 and resp.json()["code"] == 30002
    assert kb.deleted_files == []
    assert await db_session.get(KnowledgeDocument, rows["doc"]) is not None


async def test_admin_delete_doc_skips_engine_for_copy_doc(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """langbot_file_id 为空的 doc（公共库 link 引入的副本）不触发引擎调用。"""
    rows = await _seed(db_session, file_id="")
    kb = FakeKbClient()
    client = _app(db_session, rows["admin"], kb=kb)

    resp = client.delete(f"/api/v1/admin/spaces/{rows['space']}/docs/{rows['doc']}")
    assert resp.status_code == 200, resp.text
    assert kb.deleted_files == []
    assert await db_session.get(KnowledgeDocument, rows["doc"]) is None


async def test_admin_delete_doc_invalid_targets_30004(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """无效空间 / doc 不存在 / doc 不属于该空间 → 30004，一律不泄露存在性。

    跨空间误指是 A-2 特有的新增面：admin 能跨租户，但「doc 属于哪个空间」的
    归属判据不能随空间归属一起放开——否则可凭任意 doc_id 越界删除。
    """
    rows = await _seed(db_session)
    client = _app(db_session, rows["admin"], kb=FakeKbClient())

    for path in (
        f"/api/v1/admin/spaces/{SPACE_ID_MISSING}/docs/{rows['doc']}",
        f"/api/v1/admin/spaces/{rows['space']}/docs/{DOC_ID_MISSING}",
        f"/api/v1/admin/spaces/{rows['space_b']}/docs/{rows['doc']}",  # 空间存在、doc 不属之
        f"/api/v1/admin/spaces/{rows['space']}/docs/{rows['doc_b']}",  # doc 存在、不属之空间
    ):
        status, code = _hit(client, "delete", path)
        assert (status, code) == (404, 30004), (path, status, code)

    assert await db_session.get(KnowledgeDocument, rows["doc"]) is not None


# ------------------------------------------------------------------ 授权门禁


async def test_admin_routes_role_gate(db_session) -> None:  # type: ignore[no-untyped-def]
    """role 门禁：非 admin → 10004/403，且失败发生在任何写入之前。

    用**空间所有者本人**当 user 角色探子——他对自己的空间有完全使用权，
    却仍被 /admin 端点拒绝，正好证明门禁按角色而非按数据归属生效。
    """
    rows = await _seed(db_session)
    space = await db_session.get(KnowledgeSpace, rows["space"])
    assert space is not None and space.description is None

    for actor_key in ("owner", "operator"):
        client = _app(db_session, rows[actor_key], kb=FakeKbClient())
        status, code = _hit(client, "patch", f"/api/v1/admin/spaces/{rows['space']}", json={"description": "越权"})
        assert (status, code) == (403, 10004), actor_key
        status, code = _hit(client, "delete", f"/api/v1/admin/spaces/{rows['space']}/docs/{rows['doc']}")
        assert (status, code) == (403, 10004), actor_key

    space = await db_session.get(KnowledgeSpace, rows["space"])
    assert space is not None and space.description is None  # 四次拒绝零写入
    assert await db_session.get(KnowledgeDocument, rows["doc"]) is not None


async def test_admin_routes_require_login_10001(db_session) -> None:  # type: ignore[no-untyped-def]
    """未登录 → 10001（role 门禁之前先确认身份存在，与既有端点同序）。"""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_space_service] = lambda: SpaceService(SpaceRepository(db_session), db_session)
    client = TestClient(app)

    status, code = _hit(client, "patch", f"/api/v1/admin/spaces/{SPACE_ID_MISSING}", json={"description": "x"})
    assert (status, code) == (401, 10001)
    status, code = _hit(client, "delete", f"/api/v1/admin/spaces/{SPACE_ID_MISSING}/docs/{DOC_ID_MISSING}")
    assert (status, code) == (401, 10001)


# ------------------------------------------------------------------ A-2 零回归锁


async def test_user_routes_still_reject_cross_user(db_session) -> None:  # type: ignore[no-untyped-def]
    """零回归锁：既有用户端点未动，跨用户写仍 30004。

    A-2 的全部价值在于「admin 能力走新端点、旧端点不动」。若抽 _update_space /
    _delete_doc 时把 owner 判据漏成可选，旧端点会静默失守而没有任何调用方报错。
    """
    rows = await _seed(db_session)
    client = _app(db_session, rows["second"], kb=FakeKbClient())

    status, code = _hit(client, "patch", f"/api/v1/spaces/{rows['space']}", json={"description": "越权"})
    assert (status, code) == (404, 30004)
    status, code = _hit(client, "delete", f"/api/v1/spaces/{rows['space']}/docs/{rows['doc']}")
    assert (status, code) == (404, 30004)


async def test_user_patch_space_noop_semantics_unchanged(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """零回归锁：本人 PATCH 缺 description → 不写入且返回**详情视图**（非写回执）。

    admin 端点对同样输入返回 10005——两个端点对同一请求体的分歧是 A-2 刻意设计的
    （旧端点保持原样，新端点收紧），故显式锁两侧形状，防日后被「统一」掉。
    """
    rows = await _seed(db_session)
    client = _app(db_session, rows["owner"], kb=FakeKbClient())

    resp = client.patch(f"/api/v1/spaces/{rows['space']}", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert {"name", "docCount", "stats", "isPublic"} <= set(data)  # 详情视图
    assert "ok" not in data

    space = await db_session.get(KnowledgeSpace, rows["space"])
    assert space is not None and space.description is None


async def test_user_delete_doc_still_works_for_owner(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """零回归锁：本人删自己文档的既有路径不受影响（引擎先行、计数递减）。"""
    rows = await _seed(db_session)
    kb = FakeKbClient()
    client = _app(db_session, rows["owner"], kb=kb)

    resp = client.delete(f"/api/v1/spaces/{rows['space']}/docs/{rows['doc']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["ok"] is True
    assert kb.deleted_files == [("kb-admin-a", "file-admin")]
    assert await db_session.get(KnowledgeDocument, rows["doc"]) is None
