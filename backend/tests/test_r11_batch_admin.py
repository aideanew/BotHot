"""M3 批次 4（SPEC-M3 T5.7，A-2 叠加口径）验收测试：/api/v1/admin/* 批量文档操作。

批次 4 的 T5.7 差量 = 既有 `POST /spaces/{id}/docs:delete` 与 `docs:recategorize`
（R0.2.5，强制本人空间）新增跨用户变体。沿用批次 2 已确立的手法：Service 抽出
`_delete_docs` / `_recategorize_docs` 单一实现，`owner=None` 表示无归属约束，两条入口
的全部差异只在这一处判据——否则「篇级部分成功、两阶段切分、逐篇提交、整批原子」这些
契约会在两份拷贝间漂移，且没有任何调用方会报错。

本文件同时锁两侧：
- admin 端点：绕过归属校验，`admin` 放行，`user`/`operator` → 10004；
- 用户端点：跨用户批量操作仍 30004（A-2 的「零回归」承诺不被本批 Service 改造削弱）。

T5.6 计费预留按管理者裁定不建任何计费面（无表、无消费者），故本批无计费相关测试面。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_current_user_id, get_db, get_langbot_client, get_space_service
from app.core.errors import LangbotApiError
from app.main import create_app
from app.models.entities import ContentAsset, KnowledgeDocument, KnowledgeSpace, Source, User
from app.repositories.space import SpaceRepository
from app.services.spaces import SpaceService, SpaceValidationError

DOC_ID_MISSING = "00000000-0000-0000-0000-000000000003"
SPACE_ID_MISSING = "00000000-0000-0000-0000-000000000004"

DEL = "/api/v1/admin/spaces/{space_id}/docs:delete"
REC = "/api/v1/admin/spaces/{space_id}/docs:recategorize"


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


class SelectiveKbClient:
    """按 file_id 选择性注入失败，用于验证篇级部分成功。"""

    def __init__(self, fail_file_ids: set[str]) -> None:
        self.fail_file_ids = fail_file_ids
        self.deleted_files: list[tuple[str, str]] = []

    async def delete_kb_file(self, kb_uuid: str, file_id: str) -> None:
        if file_id in self.fail_file_ids:
            raise LangbotApiError(f"LangBot 删除失败: 500（{file_id}）")
        self.deleted_files.append((kb_uuid, file_id))

    async def delete_kb(self, kb_uuid: str) -> None:  # 协议完整性
        return None


# ------------------------------------------------------------------ 夹具


async def _seed(db_session: Any) -> dict[str, str]:
    """铺两个租户 + 三个角色账号。

    owner：kb-a 空间 3 篇（file-a1/a2/a3）——admin 跨用户操作对象；
    second：kb-b 空间 1 篇（file-b1）——用于「doc 存在但不属之空间」的越界探子；
    admin/operator/user 三个角色账号无自有空间，专供授权门禁用例。
    """
    owner = User(sub="r11-batch-owner", email="r11-batch-owner@r11.test", nickname="owner")
    second = User(sub="r11-batch-second", email="r11-batch-second@r11.test", nickname="second")
    admin = User(sub="r11-batch-admin", email="r11-batch-admin@r11.test", nickname="admin", role="admin")
    operator = User(sub="r11-batch-operator", email="r11-batch-operator@r11.test", nickname="operator", role="operator")
    db_session.add_all([owner, second, admin, operator])
    await db_session.flush()

    source = Source(type="wechat_oa", external_id="biz-r11-batch", name="批量管理端测试号")
    db_session.add(source)
    await db_session.flush()

    space_a = KnowledgeSpace(user_id=owner.id, name="租户A空间", langbot_kb_uuid="kb-a", doc_count=3)
    space_b = KnowledgeSpace(user_id=second.id, name="租户B空间", langbot_kb_uuid="kb-b", doc_count=1)
    # 钉死时间戳：CI 快钟下两条 flush 的 created_at 可并列同微秒，主键并列时
    # id tiebreaker 接管顺序 ⇒ 「created_at 序」断言随机红（2026-09-30 CI 实证，
    # test_admin_list_spaces_cross_user_with_owner 1 failed）。显式值让不变式可测。
    _now = datetime.now(UTC)
    space_a.created_at = _now - timedelta(hours=1)
    space_b.created_at = _now - timedelta(minutes=30)
    db_session.add_all([space_a, space_b])
    await db_session.flush()

    assets = {}
    for i in (1, 2, 3):
        asset = ContentAsset(
            source_id=source.id,
            external_id=f"a-{i}",
            url=f"https://mp.weixin.qq.com/s/a{i}",
            title=f"A文章{i}",
            content_hash=f"h-a{i}",
            content_markdown=f"# A{i}",
            category="其他",
        )
        db_session.add(asset)
        await db_session.flush()
        assets[f"a{i}"] = asset.id

    asset_b = ContentAsset(
        source_id=source.id,
        external_id="b-1",
        url="https://mp.weixin.qq.com/s/b1",
        title="B文章",
        content_hash="h-b1",
        content_markdown="# B",
        category="其他",
    )
    db_session.add(asset_b)
    await db_session.flush()

    docs: dict[str, str] = {}
    for i in (1, 2, 3):
        doc = KnowledgeDocument(
            asset_id=assets[f"a{i}"], space_id=space_a.id, langbot_file_id=f"file-a{i}", status="READY"
        )
        db_session.add(doc)
        await db_session.flush()
        docs[f"a{i}"] = doc.id

    doc_b = KnowledgeDocument(asset_id=asset_b.id, space_id=space_b.id, langbot_file_id="file-b1", status="READY")
    db_session.add(doc_b)
    await db_session.flush()
    await db_session.commit()  # 夹具 savepoint 模式：只释放保存点，外层回滚清场

    return {
        "space": space_a.id,
        "space_b": space_b.id,
        "doc_a1": docs["a1"],
        "doc_a2": docs["a2"],
        "doc_a3": docs["a3"],
        "doc_b1": doc_b.id,
        "asset_a1": assets["a1"],
        "asset_a2": assets["a2"],
        "owner": owner.id,
        "second": second.id,
        "admin": admin.id,
        "operator": operator.id,
    }


def _app(db_session: Any, actor_id: str, kb: FakeKbClient | SelectiveKbClient | None = None) -> TestClient:
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


async def _remaining_doc_ids(db_session: Any, space_ids: Iterable[str]) -> set[str]:
    """SQL 口径的**给定空间内**现存 doc 行集合（绕开 identity map 陈旧对象）。

    必须按 space 限定：夹具只在写侧隔离（外层事务回滚），读侧仍可见环境里
    其他空间的 doc（人工 QA 数据）——全表计数会把环境噪音误判成产品缺陷。
    """
    rows = await db_session.execute(select(KnowledgeDocument.id).where(KnowledgeDocument.space_id.in_(space_ids)))
    return set(rows.scalars().all())


async def _categories(db_session: Any) -> dict[str, str]:
    """资产 id → category（批量改分类断言用）。"""
    rows = (await db_session.execute(select(ContentAsset.id, ContentAsset.category))).all()
    return {asset_id: category for asset_id, category in rows}


# ------------------------------------------------------------------ admin 批量删除


async def test_admin_batch_delete_cross_user_engine_first(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """A-2 的实际增量：admin 可批量删他人空间，引擎先行顺序与计数递减不变。"""
    rows = await _seed(db_session)
    kb = FakeKbClient()
    client = _app(db_session, rows["admin"], kb=kb)

    resp = client.post(
        DEL.format(space_id=rows["space"]),
        json={"ids": [rows["doc_a1"], rows["doc_a2"], rows["doc_a3"]]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {
        "ok": True,
        "requested": 3,
        "docs": 3,
        "assets": 3,
        "failed": [],
    }
    assert kb.deleted_files == [("kb-a", f"file-a{i}") for i in (1, 2, 3)]  # 引擎先删且用 langbot_kb_uuid

    assert rows["doc_a1"] not in await _remaining_doc_ids(db_session, {rows["space"], rows["space_b"]})
    assert rows["doc_a2"] not in await _remaining_doc_ids(db_session, {rows["space"], rows["space_b"]})
    assert rows["doc_a3"] not in await _remaining_doc_ids(db_session, {rows["space"], rows["space_b"]})
    # 他人空间另一租户不受影响
    assert rows["doc_b1"] in await _remaining_doc_ids(db_session, {rows["space"], rows["space_b"]})

    space = await db_session.get(KnowledgeSpace, rows["space"])
    assert space is not None and space.doc_count == 0


async def test_admin_batch_delete_partial_failure_keeps_failed_rows_retryable(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """篇级部分成功：引擎侧失败篇的 PG 行完整保留（可原样重试），不是整体回滚。"""
    rows = await _seed(db_session)
    kb = SelectiveKbClient(fail_file_ids={"file-a2"})
    client = _app(db_session, rows["admin"], kb=kb)

    resp = client.post(
        DEL.format(space_id=rows["space"]),
        json={"ids": [rows["doc_a1"], rows["doc_a2"], rows["doc_a3"]]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["ok"] is True and data["requested"] == 3 and data["docs"] == 2
    assert len(data["failed"]) == 1
    assert data["failed"][0]["docId"] == rows["doc_a2"]
    assert data["failed"][0]["code"] == 30002  # LangBotApiError 的登记码位

    remaining = await _remaining_doc_ids(db_session, {rows["space"], rows["space_b"]})
    assert rows["doc_a2"] in remaining  # 失败篇 PG 行保留
    assert rows["doc_a1"] not in remaining and rows["doc_a3"] not in remaining
    assert kb.deleted_files == [("kb-a", "file-a1"), ("kb-a", "file-a3")]

    space = await db_session.get(KnowledgeSpace, rows["space"])
    assert space is not None and space.doc_count == 1  # 只递减已成功篇


async def test_admin_batch_delete_all_failed_raises_envelope(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """全批失败 → 错误信封（非「200 但一篇都没删」），且 PG 零写入。"""
    rows = await _seed(db_session)
    kb = FakeKbClient(fail=LangbotApiError("LangBot 删除失败: 500"))
    client = _app(db_session, rows["admin"], kb=kb)

    resp = client.post(DEL.format(space_id=rows["space"]), json={"ids": [rows["doc_a1"]]})
    assert resp.status_code == 502 and resp.json()["code"] == 30002

    assert rows["doc_a1"] in await _remaining_doc_ids(db_session, {rows["space"], rows["space_b"]})
    space = await db_session.get(KnowledgeSpace, rows["space"])
    assert space is not None and space.doc_count == 3


async def test_admin_batch_delete_invalid_targets_30004(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """无效空间 / doc 缺失 / doc 不属该空间 → 30004，一律不泄露存在性且零副作用。

    跨空间误指是 A-2 特有的新增面：admin 能跨租户操作，但「doc 属于所给空间」是数据
    事实校验，不随空间归属一起放开——否则可凭任意 doc_id 越界批量删除。
    """
    rows = await _seed(db_session)
    kb = FakeKbClient()
    client = _app(db_session, rows["admin"], kb=kb)

    for payload in (
        {"ids": [DOC_ID_MISSING]},  # 空间存在、doc 不存在
        {"ids": [rows["doc_b1"]]},  # doc 存在、不属之空间
        {"ids": [rows["doc_a1"], DOC_ID_MISSING]},  # 混入一篇缺失即全批拒绝
    ):
        resp = client.post(DEL.format(space_id=rows["space"]), json=payload)
        assert resp.status_code == 404 and resp.json()["code"] == 30004, payload

    status, code = _hit(client, "post", DEL.format(space_id=SPACE_ID_MISSING), json={"ids": [rows["doc_a1"]]})
    assert (status, code) == (404, 30004)  # 空间不存在

    assert await _remaining_doc_ids(db_session, {rows["space"], rows["space_b"]}) == {
        rows["doc_a1"],
        rows["doc_a2"],
        rows["doc_a3"],
        rows["doc_b1"],
    }
    assert kb.deleted_files == []  # 请求形态错误在任何引擎调用之前被拒


async def test_admin_batch_delete_skips_engine_for_copy_rows(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """langbot_file_id 为空的 doc（公共库 link 引入的副本）不触发引擎调用，PG 照常删。"""
    rows = await _seed(db_session)
    # 独立资产：knowledge_documents 有 uq_doc_asset_space，同一资产不能在同空间建两篇
    source_id = await db_session.scalar(select(ContentAsset.source_id).where(ContentAsset.id == rows["asset_a2"]))
    asset = ContentAsset(
        source_id=source_id,
        external_id="copy-1",
        url="https://mp.weixin.qq.com/s/copy1",
        title="副本",
        content_hash="h-copy",
        content_markdown="# C",
        category="其他",
    )
    db_session.add(asset)
    await db_session.flush()
    doc = KnowledgeDocument(asset_id=asset.id, space_id=rows["space"], langbot_file_id="", status="READY")
    db_session.add(doc)
    await db_session.flush()

    kb = FakeKbClient()
    client = _app(db_session, rows["admin"], kb=kb)

    resp = client.post(DEL.format(space_id=rows["space"]), json={"ids": [rows["doc_a1"], doc.id]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["docs"] == 2
    assert kb.deleted_files == [("kb-a", "file-a1")]  # 副本篇不触发引擎
    remaining = await _remaining_doc_ids(db_session, {rows["space"], rows["space_b"]})
    assert doc.id not in remaining and rows["doc_a1"] not in remaining


async def test_admin_batch_delete_validation_errors_before_any_engine_call(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """请求形态错误一律零副作用，且不触碰引擎：pydantic 体量硬闸与业务上限双层。"""
    rows = await _seed(db_session)
    kb = FakeKbClient()
    client = _app(db_session, rows["admin"], kb=kb)

    for payload in (
        {},  # 缺 ids → pydantic → 10005
        {"ids": []},  # 空批 → pydantic min_length → 10005
        {"ids": ["   ", "\t"]},  # 全空白 → 服务层归一化后为空 → 10005
        {"ids": [f"d-{i}" for i in range(51)]},  # 超业务上限 50 → 10005
    ):
        status, code = _hit(client, "post", DEL.format(space_id=rows["space"]), json=payload)
        assert status == 422 and code == 10005, (payload, status, code)

    assert kb.deleted_files == []
    assert await _remaining_doc_ids(db_session, {rows["space"], rows["space_b"]}) == {
        rows["doc_a1"],
        rows["doc_a2"],
        rows["doc_a3"],
        rows["doc_b1"],
    }


# ------------------------------------------------------------------ admin 批量改分类


async def test_admin_batch_recategorize_cross_user_persists_asset_level(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """A-2 的实际增量：admin 可跨用户批量改分类，资产级生效范围不变。"""
    rows = await _seed(db_session)
    client = _app(db_session, rows["admin"], kb=FakeKbClient())

    resp = client.post(
        REC.format(space_id=rows["space"]),
        json={"ids": [rows["doc_a1"], rows["doc_a2"]], "category": "AI·技术"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {"ok": True, "requested": 2, "docs": 2, "category": "AI·技术"}

    cats = await _categories(db_session)
    assert cats[rows["asset_a1"]] == "AI·技术"
    assert cats[rows["asset_a2"]] == "AI·技术"


async def test_admin_batch_recategorize_illegal_category_10005_before_fetch(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """取值非法 → 10005，且在任何 DB 读之前拒绝（对不存在的空间同样返回 10005）。"""
    rows = await _seed(db_session)
    client = _app(db_session, rows["admin"], kb=FakeKbClient())

    status, code = _hit(
        client,
        "post",
        REC.format(space_id=rows["space"]),
        json={"ids": [rows["doc_a1"]], "category": "自由文本"},
    )
    assert (status, code) == (422, 10005)

    status, code = _hit(
        client,
        "post",
        REC.format(space_id=SPACE_ID_MISSING),
        json={"ids": [rows["doc_a1"]], "category": "自由文本"},
    )
    assert (status, code) == (422, 10005)  # 校验先于取行，不是 30004

    assert (await _categories(db_session))[rows["asset_a1"]] == "其他"


async def test_admin_batch_recategorize_missing_id_rolls_back_entire_batch(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """整批原子：任一篇缺失 → 30004，全批不生效，不产生「改了一半」的中间态。"""
    rows = await _seed(db_session)
    client = _app(db_session, rows["admin"], kb=FakeKbClient())

    status, code = _hit(
        client,
        "post",
        REC.format(space_id=rows["space"]),
        json={"ids": [rows["doc_a1"], DOC_ID_MISSING], "category": "AI·技术"},
    )
    assert (status, code) == (404, 30004)

    assert (await _categories(db_session))[rows["asset_a1"]] == "其他"  # 已选篇也未改写


async def test_admin_batch_both_entries_validate_before_fetch(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """单一实现锁：两条入口共用 _delete_docs / _recategorize_docs，校验在任何取行之前。

    若校验顺序在两份拷贝里各写一份，很容易出现「owner 入口先校验、admin 入口先取行」
    的漂移——非法输入对不存在的空间会返回 30004 而非 10005，且没有调用方会报错。
    """
    rows = await _seed(db_session)
    svc = SpaceService(SpaceRepository(db_session), db_session)
    empty_msg = "批量列表为空或全部无效，请至少提交一篇有效文档"

    checks: list[tuple[str, bool, str, int]] = []
    for label, call in (
        ("delete_docs", lambda: svc.delete_docs(rows["owner"], SPACE_ID_MISSING, [], None)),
        ("delete_docs_any", lambda: svc.delete_docs_any(SPACE_ID_MISSING, [], None)),
        ("recategorize_docs", lambda: svc.recategorize_docs(rows["owner"], SPACE_ID_MISSING, [], "x")),
        ("recategorize_docs_any", lambda: svc.recategorize_docs_any(SPACE_ID_MISSING, [], "x")),
    ):
        try:
            await call()
        except SpaceValidationError as exc:
            checks.append((label, True, exc.message, exc.code))
        else:
            checks.append((label, False, "", 0))

    assert [c[0] for c in checks] == [
        "delete_docs",
        "delete_docs_any",
        "recategorize_docs",
        "recategorize_docs_any",
    ]
    assert all(c[1] for c in checks), "四条入口都必须在任何取行之前被拒绝"
    assert (checks[0][2], checks[0][3]) == (empty_msg, 10005)
    assert (checks[1][2], checks[1][3]) == (empty_msg, 10005)
    assert checks[2][2].startswith("分类取值非法：x") and checks[2][3] == 10005
    assert checks[3][2].startswith("分类取值非法：x") and checks[3][3] == 10005


# ------------------------------------------------------------------ 授权门禁


async def test_admin_batch_role_gate(db_session) -> None:  # type: ignore[no-untyped-def]
    """role 门禁：非 admin → 10004/403，且失败发生在任何写入与引擎调用之前。

    用**空间所有者本人**当 user 角色探子——他对自己的空间有完全使用权，却仍被
    /admin 端点拒绝，正好证明门禁按角色而非按数据归属生效；operator 秩低于 admin。
    """
    rows = await _seed(db_session)
    kb = FakeKbClient()
    original = await _remaining_doc_ids(db_session, {rows["space"], rows["space_b"]})

    for actor_key in ("owner", "operator"):
        client = _app(db_session, rows[actor_key], kb=kb)
        status, code = _hit(client, "post", DEL.format(space_id=rows["space"]), json={"ids": [rows["doc_a1"]]})
        assert (status, code) == (403, 10004), actor_key
        status, code = _hit(
            client,
            "post",
            REC.format(space_id=rows["space"]),
            json={"ids": [rows["doc_a1"]], "category": "AI·技术"},
        )
        assert (status, code) == (403, 10004), actor_key

    assert await _remaining_doc_ids(db_session, {rows["space"], rows["space_b"]}) == original  # 四次拒绝零写入
    assert (await _categories(db_session))[rows["asset_a1"]] == "其他"
    assert kb.deleted_files == []


async def test_admin_batch_requires_login_10001(db_session) -> None:  # type: ignore[no-untyped-def]
    """未登录 → 10001（role 门禁之前先确认身份存在，与既有端点同序）。"""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_space_service] = lambda: SpaceService(SpaceRepository(db_session), db_session)
    client = TestClient(app)

    status, code = _hit(client, "post", DEL.format(space_id=SPACE_ID_MISSING), json={"ids": [DOC_ID_MISSING]})
    assert (status, code) == (401, 10001)
    status, code = _hit(
        client,
        "post",
        REC.format(space_id=SPACE_ID_MISSING),
        json={"ids": [DOC_ID_MISSING], "category": "AI·技术"},
    )
    assert (status, code) == (401, 10001)


# ------------------------------------------------------------------ A-2 零回归锁


async def test_user_batch_routes_still_reject_cross_user(db_session) -> None:  # type: ignore[no-untyped-def]
    """零回归锁：既有用户批量端点未动，跨用户批量操作仍 30004。

    A-2 的全部价值在于「admin 能力走新端点、旧端点不动」。若抽 _delete_docs /
    _recategorize_docs 时把 owner 判据漏成可选，旧端点会静默失守而没有任何调用方报错。
    """
    rows = await _seed(db_session)
    client = _app(db_session, rows["second"], kb=FakeKbClient())

    status, code = _hit(client, "post", f"/api/v1/spaces/{rows['space']}/docs:delete", json={"ids": [rows["doc_a1"]]})
    assert (status, code) == (404, 30004)
    status, code = _hit(
        client,
        "post",
        f"/api/v1/spaces/{rows['space']}/docs:recategorize",
        json={"ids": [rows["doc_a1"]], "category": "AI·技术"},
    )
    assert (status, code) == (404, 30004)

    assert await _remaining_doc_ids(db_session, {rows["space"], rows["space_b"]}) == {
        rows["doc_a1"],
        rows["doc_a2"],
        rows["doc_a3"],
        rows["doc_b1"],
    }
    assert (await _categories(db_session))[rows["asset_a1"]] == "其他"


async def test_user_batch_routes_still_work_for_owner(db_session) -> None:  # type: ignore[no-untyped-def]
    """零回归锁：本人批量端点的既有行为不受影响（引擎先行、计数递减、整批原子）。"""
    rows = await _seed(db_session)
    kb = FakeKbClient()
    client = _app(db_session, rows["owner"], kb=kb)

    resp = client.post(
        f"/api/v1/spaces/{rows['space']}/docs:recategorize",
        json={"ids": [rows["doc_a3"]], "category": "教程·实践"},
    )
    assert resp.status_code == 200, resp.text
    assert (await _categories(db_session))[rows["asset_a2"]] == "其他"  # 未选篇不变

    resp = client.post(f"/api/v1/spaces/{rows['space']}/docs:delete", json={"ids": [rows["doc_a1"]]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["ok"] is True
    assert kb.deleted_files == [("kb-a", "file-a1")]
    remaining = await _remaining_doc_ids(db_session, {rows["space"], rows["space_b"]})
    assert rows["doc_a1"] not in remaining
    space = await db_session.get(KnowledgeSpace, rows["space"])
    assert space is not None and space.doc_count == 2


# ------------------------------------------------------------------ 批次 2 读面（跨用户浏览）

LIST = "/api/v1/admin/spaces"
DOCS = "/api/v1/admin/spaces/{space_id}/docs"


async def test_admin_list_spaces_cross_user_with_owner(db_session) -> None:  # type: ignore[no-untyped-def]
    """admin 一次取得全部租户的空间，每条带归属；docCount 走既有 GROUP BY 口径。

    端点是「全量列表」，只断言本用例播种的两个空间可见且顺序/归属/计数正确——
    环境里可能已有其他来源的空间，精确相等会把环境噪音误判成产品缺陷。
    """
    rows = await _seed(db_session)
    items = _app(db_session, rows["admin"]).get(LIST).json()["data"]["items"]
    ids = [i["id"] for i in items]

    by_id = {i["id"]: i for i in items}
    assert by_id.keys() >= {rows["space"], rows["space_b"]}  # 两个租户的空间均可见
    assert ids.index(rows["space"]) < ids.index(rows["space_b"])  # created_at 序
    owner_view, other_view = by_id[rows["space"]], by_id[rows["space_b"]]
    assert owner_view["docCount"] == 3 and other_view["docCount"] == 1

    for key, value in (("ownerId", rows["owner"]), ("ownerSub", "r11-batch-owner"), ("ownerNickname", "owner")):
        assert owner_view[key] == value, key
    for key, value in (("ownerId", rows["second"]), ("ownerSub", "r11-batch-second"), ("ownerNickname", "second")):
        assert other_view[key] == value, key
    # 既有视图字段形状不变
    for view in (owner_view, other_view):
        assert set(view) == {
            "id",
            "name",
            "description",
            "docCount",
            "updatedAt",
            "engine",
            "engineKbId",
            "isPublic",
            "ownerId",
            "ownerSub",
            "ownerNickname",
        }


async def test_admin_list_space_docs_cross_user(db_session) -> None:  # type: ignore[no-untyped-def]
    """admin 能列出**他人**空间的文档——这是批量操作面板唯一的目标来源。

    owner 本人对该空间是 30004，同一数据经 /admin 可见：差异只在归属判据。
    """
    rows = await _seed(db_session)
    client = _app(db_session, rows["admin"])

    resp = client.get(DOCS.format(space_id=rows["space_b"]))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 1 and data["limit"] == 100 and data["offset"] == 0
    assert [d["id"] for d in data["items"]] == [rows["doc_b1"]]
    assert data["items"][0]["category"] == "其他"


async def test_admin_list_docs_pagination_and_category_agree(db_session) -> None:  # type: ignore[no-untyped-def]
    """分页后的 total 不虚高，category 过滤与 total 走同一谓词（F-9 口径）。"""
    rows = await _seed(db_session)
    kb = FakeKbClient()
    client = _app(db_session, rows["admin"], kb=kb)

    assert client.get(f"{DOCS.format(space_id=rows['space'])}?limit=2&offset=0").json()["data"]["total"] == 3
    page = client.get(f"{DOCS.format(space_id=rows['space'])}?limit=2&offset=1").json()["data"]
    assert len(page["items"]) == 2 and page["total"] == 3

    client.post(
        REC.format(space_id=rows["space"]),
        json={"ids": [rows["doc_a1"]], "category": "AI·技术"},
    )
    filtered = client.get(f"{DOCS.format(space_id=rows['space'])}?category=AI·技术").json()["data"]
    assert filtered["total"] == 1 and len(filtered["items"]) == 1
    assert filtered["items"][0]["id"] == rows["doc_a1"]

    # 哨兵 __uncategorized__ 被译成空串精确匹配（库里不存哨兵值）；夹具资产均有分类，
    # 故 0——关键是 total 与 items 走同一谓词（F-9），不是数值本身。
    uncategorized = client.get(f"{DOCS.format(space_id=rows['space'])}?category=__uncategorized__").json()["data"]
    assert uncategorized["total"] == 0
    assert uncategorized["items"] == []
    assert uncategorized["total"] == len(uncategorized["items"])


async def test_admin_list_docs_invalid_space_30004(db_session) -> None:  # type: ignore[no-untyped-def]
    """无效空间 → 30004 而非空列表：否则「空间不存在」与「空间为空」无法区分。"""
    rows = await _seed(db_session)
    status, code = _hit(_app(db_session, rows["admin"]), "get", DOCS.format(space_id=SPACE_ID_MISSING))
    assert (status, code) == (404, 30004)


async def test_admin_list_role_gate_and_requires_login(db_session) -> None:  # type: ignore[no-untyped-def]
    """两条读端点同门禁：非 admin → 10004/403，未登录 → 10001。"""
    rows = await _seed(db_session)
    for actor_key in ("owner", "operator"):
        client = _app(db_session, rows[actor_key])
        status, code = _hit(client, "get", LIST)
        assert (status, code) == (403, 10004), f"{actor_key} → spaces"
        status, code = _hit(client, "get", DOCS.format(space_id=rows["space"]))
        assert (status, code) == (403, 10004), f"{actor_key} → docs"

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_space_service] = lambda: SpaceService(SpaceRepository(db_session), db_session)
    client = TestClient(app)
    assert _hit(client, "get", LIST) == (401, 10001)
    assert _hit(client, "get", DOCS.format(space_id=rows["space"])) == (401, 10001)


async def test_user_space_routes_no_owner_fields_zero_regression(db_session) -> None:  # type: ignore[no-untyped-def]
    """零回归锁：本人空间端点不加归属字段，跨用户读仍 30004。

    admin 视图的 owner 三字段是**增量**，靠独立端点承载——若抽 _space_view /
    _list_space_docs 时把 owner 判据漏成可选，旧端点会静默失守而无调用方报错。
    """
    rows = await _seed(db_session)
    client = _app(db_session, rows["owner"])

    items = client.get("/api/v1/spaces").json()["data"]["items"]
    assert [i["id"] for i in items] == [rows["space"]]  # 只列本人空间
    assert "ownerId" not in items[0] and "ownerSub" not in items[0] and "ownerNickname" not in items[0]
    for key in ("id", "name", "description", "docCount", "updatedAt", "engine", "engineKbId", "isPublic"):
        assert key in items[0], key

    status, code = _hit(client, "get", f"/api/v1/spaces/{rows['space_b']}/docs")
    assert (status, code) == (404, 30004)
    status, code = _hit(client, "get", f"/api/v1/spaces/{SPACE_ID_MISSING}/docs")
    assert (status, code) == (404, 30004)
