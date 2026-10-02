"""R0.2.5 批量文档操作端点：POST /spaces/{id}/docs:delete + :recategorize。

F-2 收尾：单篇 DELETE/PATCH 已销账文档编辑入口，但数百篇空间要逐篇点删，
与 F-1（单页 100 条上限）组合仍是「删不掉 + 看不全」的死锁。本批补批量端点。

口径锚点（与单篇端点及前端契约须同口径）：
- 双层闸沿用 batch_ingest：路由侧 pydantic 体量硬闸（1..500），
  业务上限（默认 50，`batch_docs_max_ids`）在 Service 内走错误信封（10005）；
- **批量删除是篇级部分成功**（与单篇 all-or-nothing 相反）：引擎文件删除是外部副作用，
  整体回滚会抹掉已成功的 PG 删除、同时留下「PG 有行但文件没了」的永久死档——
  失败篇的 PG 行完整保留即可原样重试。实现上须**两阶段切分**（先引擎后 DB）：
  引擎失败时会话无 pending 写、无需回滚；若连续两篇失败各回滚一次，savepoint 会话
  报 MissingGreenlet（本批实测踩到的坑）；
- **批量改分类是整批原子**（纯 DB 写、无外部副作用，单事务即可）：
  任一篇缺失或越权 → 30004 且全批不生效，不产生「改了一半」中间态；
- 请求形态错误（10005 空批/超上限、30004 任一篇缺失或越权）一律零副作用；
- category 仍是 **ContentAsset 级**属性（跨空间共享），批量改分类对同一资产在
  其他空间的呈现一并生效——与单篇 PATCH 同一范围语义。

注意：夹具为 savepoint 模式 + `expire_on_commit=False`，`session.get()` 会返回
identity map 里的旧对象——凡「行是否真被删」的断言走 SQL 查询，不能靠 `get()`。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_r02_docs_lifecycle import (  # 夹具与桩复用 R0.2.1/R0.2.2 既有实现（本仓惯例）
    DOC_ID_UNKNOWN,
    FakeAdapter,
    FakeKbClient,
    FakeRouter,
    _app,
    _seed,
)

from app.core.errors import LangbotApiError, ResourceNotFoundError
from app.main import create_app
from app.models.entities import ContentAsset, KnowledgeDocument, KnowledgeSpace
from app.repositories.space import SpaceRepository
from app.services.spaces import SpaceService

DEL = "/api/v1/spaces/{space_id}/docs:delete"
REC = "/api/v1/spaces/{space_id}/docs:recategorize"


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


async def _remaining_doc_ids(db_session: Any, space_id: str) -> set[str]:
    """SQL 口径的**该空间**现存 doc 行集合（绕开 identity map 陈旧对象）。

    必须按 space 限定：夹具只在写侧隔离（外层事务回滚），读侧仍可见环境里
    其他空间的 doc（如人工 QA 数据）——全表计数会把环境噪音误判成产品缺陷。
    """
    rows = await db_session.execute(select(KnowledgeDocument.id).where(KnowledgeDocument.space_id == space_id))
    return set(rows.scalars().all())


async def _categories(db_session: Any) -> dict[str, str]:
    """资产 id → category（批量改分类断言用）。"""
    rows = (await db_session.execute(select(ContentAsset.id, ContentAsset.category))).all()
    return {asset_id: category for asset_id, category in rows}


async def _asset_id_of(db_session: Any, doc_id: str) -> str:
    return await db_session.scalar(select(KnowledgeDocument.asset_id).where(KnowledgeDocument.id == doc_id))


# ------------------------------------------------------------------ R0.2.5 双层闸（10005 / 422）


async def test_delete_docs_batch_over_business_limit_returns_10005(db_session) -> None:
    """51 篇真实文档 → 10005/422，且一篇都不删（限流在取行之前）。"""
    space_id, user_id, doc_ids = await _seed(
        db_session, sub="r025-lim", docs=[(f"d{i:02d}", f"f{i:02d}") for i in range(51)]
    )
    kb = FakeKbClient()
    client = _app(db_session, user_id, kb=kb)

    resp = client.post(DEL.format(space_id=space_id), json={"ids": list(doc_ids.values())})
    assert resp.status_code == 422 and resp.json()["code"] == 10005
    assert "51" in resp.text and "50" in resp.text  # 错误文案回显实际条数与上限

    assert len(await _remaining_doc_ids(db_session, space_id)) == 51
    assert kb.deleted_files == []


async def test_delete_docs_batch_huge_body_hit_pydantic_hard_gate(db_session) -> None:
    """501 条 → 422 体量硬闸（路由层拦截，错误信封形态由 FastAPI 校验承担）。"""
    space_id, user_id, _ = await _seed(db_session, sub="r025-hard", docs=[("a", "f1")])
    client = _app(db_session, user_id, kb=FakeKbClient())

    resp = client.post(DEL.format(space_id=space_id), json={"ids": [str(i) for i in range(501)]})
    assert resp.status_code == 422


async def test_delete_docs_batch_empty_ids_returns_422(db_session) -> None:
    space_id, user_id, _ = await _seed(db_session, sub="r025-empty", docs=[("a", "f1")])
    client = _app(db_session, user_id, kb=FakeKbClient())

    resp = client.post(DEL.format(space_id=space_id), json={"ids": []})
    assert resp.status_code == 422


async def test_delete_docs_batch_all_whitespace_ids_returns_10005(db_session) -> None:
    """归一化后为空（纯空白/空串）→ 10005，不落到「删了 0 篇却报成功」。"""
    space_id, user_id, _ = await _seed(db_session, sub="r025-ws", docs=[("a", "f1")])
    kb = FakeKbClient()
    client = _app(db_session, user_id, kb=kb)

    resp = client.post(DEL.format(space_id=space_id), json={"ids": ["", "  ", "\t"]})
    assert resp.status_code == 422 and resp.json()["code"] == 10005
    assert len(await _remaining_doc_ids(db_session, space_id)) == 1
    assert kb.deleted_files == []


async def test_recategorize_docs_batch_over_business_limit_returns_10005(db_session) -> None:
    space_id, user_id, doc_ids = await _seed(
        db_session, sub="r025-rlim", docs=[(f"d{i:02d}", f"f{i:02d}") for i in range(51)]
    )
    client = _app(db_session, user_id, kb=FakeKbClient())

    resp = client.post(
        REC.format(space_id=space_id),
        json={"ids": list(doc_ids.values()), "category": "AI·技术"},
    )
    assert resp.status_code == 422 and resp.json()["code"] == 10005
    assert "51" in resp.text and "50" in resp.text

    assert await _categories(db_session)  # 资产行与分类均未受影响
    assert len(await _remaining_doc_ids(db_session, space_id)) == 51


async def test_recategorize_docs_batch_illegal_category_returns_10005(db_session) -> None:
    """分类取值不在规则版六类或空串 → 10005，且先校验后取行（零副作用）。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r025-illeg", docs=[("a", "f1")])
    client = _app(db_session, user_id, kb=FakeKbClient())

    resp = client.post(REC.format(space_id=space_id), json={"ids": [doc_ids["a"]], "category": "随手写的标签"})
    assert resp.status_code == 422 and resp.json()["code"] == 10005

    asset_id = await _asset_id_of(db_session, doc_ids["a"])
    assert (await _categories(db_session))[asset_id] == "其他"  # 未生效


# ------------------------------------------------------------------ R0.2.5 越权与 30004


async def test_delete_docs_batch_foreign_space_returns_30004(db_session) -> None:
    space_id, user_id, doc_ids = await _seed(db_session, sub="r025-own", docs=[("a", "f1")])
    kb = FakeKbClient()
    client = _app(db_session, user_id, kb=kb)

    resp = client.post(DEL.format(space_id="not-a-space"), json={"ids": [doc_ids["a"]]})
    assert resp.status_code == 404 and resp.json()["code"] == 30004

    assert len(await _remaining_doc_ids(db_session, space_id)) == 1
    assert kb.deleted_files == []


async def test_delete_docs_batch_doc_from_other_space_returns_30004(db_session) -> None:
    """本批含「不属该空间」的 doc → 整体 30004，连合法篇也不删（不泄露存在性）。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r025-cross", docs=[("a", "f1"), ("b", "f2")])
    other = KnowledgeSpace(user_id=user_id, name="另一空间", langbot_kb_uuid="kb-2", engine="builtin")
    db_session.add(other)
    await db_session.commit()

    kb = FakeKbClient()
    client = _app(db_session, user_id, kb=kb)
    resp = client.post(DEL.format(space_id=space_id), json={"ids": [doc_ids["a"], doc_ids["b"], DOC_ID_UNKNOWN]})
    assert resp.status_code == 404 and resp.json()["code"] == 30004

    assert len(await _remaining_doc_ids(db_session, space_id)) == 2
    assert kb.deleted_files == []


async def test_recategorize_docs_batch_missing_id_rolls_back_entire_batch(db_session) -> None:
    """整批原子：任一篇缺失 → 30004，其余合法篇的分类也**不**被改（无中间态）。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r025-atom", docs=[("a", "f1"), ("b", "f2"), ("c", "f3")])
    client = _app(db_session, user_id, kb=FakeKbClient())

    resp = client.post(
        REC.format(space_id=space_id),
        json={"ids": [doc_ids["a"], doc_ids["b"], doc_ids["c"], DOC_ID_UNKNOWN], "category": "AI·技术"},
    )
    assert resp.status_code == 404 and resp.json()["code"] == 30004

    changed = 0
    for key in ("a", "b", "c"):
        asset_id = await _asset_id_of(db_session, doc_ids[key])
        if (await _categories(db_session))[asset_id] != "其他":
            changed += 1
    assert changed == 0, "整批原子：全批不得有任何一篇生效"


async def test_delete_docs_batch_requires_login() -> None:
    resp = TestClient(create_app()).post("/api/v1/spaces/x/docs:delete", json={"ids": ["a"]})
    assert resp.status_code == 401 and resp.json()["code"] == 10001


async def test_recategorize_docs_batch_requires_login() -> None:
    resp = TestClient(create_app()).post("/api/v1/spaces/x/docs:recategorize", json={"ids": ["a"]})
    assert resp.status_code == 401 and resp.json()["code"] == 10001


# ------------------------------------------------------------------ R0.2.5 :delete 篇级部分成功


async def test_delete_docs_batch_all_succeed(db_session) -> None:
    """3 篇全成功 → {ok, requested, docs, assets, failed:[]}，引擎按篇调用且用 langbot_kb_uuid。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r025-ok", docs=[("a", "f1"), ("b", "f2"), ("c", "f3")])
    kb = FakeKbClient()
    client = _app(db_session, user_id, kb=kb)

    resp = client.post(DEL.format(space_id=space_id), json={"ids": [doc_ids["a"], doc_ids["b"], doc_ids["c"]]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] == {"ok": True, "requested": 3, "docs": 3, "assets": 3, "failed": []}
    assert kb.deleted_files == [("kb-r02", "f1"), ("kb-r02", "f2"), ("kb-r02", "f3")]
    assert await _remaining_doc_ids(db_session, space_id) == set()


async def test_delete_docs_batch_partial_failure_keeps_failed_rows_retryable(db_session) -> None:
    """中间一篇引擎失败 → 200 + failed 明细；已删篇立即生效，失败篇 PG 行完整保留。"""
    space_id, user_id, doc_ids = await _seed(
        db_session, sub="r025-partial", docs=[("a", "f1"), ("b", "f2"), ("c", "f3")]
    )
    kb = SelectiveKbClient(fail_file_ids={"f2"})
    client = _app(db_session, user_id, kb=kb)

    resp = client.post(DEL.format(space_id=space_id), json={"ids": [doc_ids["a"], doc_ids["b"], doc_ids["c"]]})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["ok"] is True
    assert data["requested"] == 3
    assert data["docs"] == 2, "引擎删除成功的篇立即生效，不被后续失败回滚"
    assert data["assets"] == 2
    assert data["failed"] == [{"docId": doc_ids["b"], "code": 30002, "error": "LangBot 删除失败: 500（f2）"}], (
        "失败明细带码位，前端可按码映射友好文案"
    )

    # 关键契约：失败篇的 PG 行完整保留（含 langbot_file_id），可原样重试
    assert await _remaining_doc_ids(db_session, space_id) == {doc_ids["b"]}
    assert kb.deleted_files == [("kb-r02", "f1"), ("kb-r02", "f3")]


async def test_delete_docs_batch_all_failed_raises_envelope(db_session) -> None:
    """全批失败 → 错误信封（30002/502），不是「200 但一篇都没删」。

    同时是本批 MissingGreenlet 回归桩：连续两篇引擎失败且中间无 commit——
    若失败分支里仍各回滚一次，即在此爆炸。
    """
    space_id, user_id, doc_ids = await _seed(db_session, sub="r025-allfail", docs=[("a", "f1"), ("b", "f2")])
    client = _app(db_session, user_id, kb=FakeKbClient(fail=LangbotApiError("LangBot 删除失败: 500")))

    resp = client.post(DEL.format(space_id=space_id), json={"ids": [doc_ids["a"], doc_ids["b"]]})
    assert resp.status_code == 502 and resp.json()["code"] == 30002
    assert len(await _remaining_doc_ids(db_session, space_id)) == 2


async def test_delete_docs_batch_405_structural_failure_degrades(db_session) -> None:
    """B34：引擎 405（本 LangBot 版本无文件级 DELETE 路由）对批量路径同样降级——
    三篇全部删除、failed 为空，而非全批 502（修复前批量删除与单删一样整体不可用）。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r025-405", docs=[("a", "f1"), ("b", "f2"), ("c", "f3")])
    kb = FakeKbClient(fail=LangbotApiError("LangBot 405: Method Not Allowed", upstream_status=405))
    client = _app(db_session, user_id, kb=kb)

    resp = client.post(
        DEL.format(space_id=space_id),
        json={"ids": [doc_ids["a"], doc_ids["b"], doc_ids["c"]]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["failed"] == [], "结构性失败应降级，不计入失败明细"
    assert data["docs"] == 3
    assert await _remaining_doc_ids(db_session, space_id) == set()


async def test_delete_docs_batch_dedupes_and_strips_ids(db_session) -> None:
    """重复 id 与首尾空白 → 归一化去重保序，每篇只删一次。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r025-dedup", docs=[("a", "f1")])
    kb = FakeKbClient()
    client = _app(db_session, user_id, kb=kb)

    resp = client.post(DEL.format(space_id=space_id), json={"ids": [f" {doc_ids['a']} ", doc_ids["a"], ""]})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data == {"ok": True, "requested": 1, "docs": 1, "assets": 1, "failed": []}
    assert kb.deleted_files == [("kb-r02", "f1")]
    assert await _remaining_doc_ids(db_session, space_id) == set()


async def test_delete_docs_batch_skips_engine_for_copy_rows(db_session) -> None:
    """langbot_file_id 为空的副本行（公共库 link 引入）→ 不调引擎，直接删 PG。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r025-copy", docs=[("a", ""), ("b", ""), ("c", "f3")])
    kb = FakeKbClient()
    client = _app(db_session, user_id, kb=kb)

    resp = client.post(DEL.format(space_id=space_id), json={"ids": [doc_ids["a"], doc_ids["b"], doc_ids["c"]]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["failed"] == []
    assert kb.deleted_files == [("kb-r02", "f3")]


async def test_delete_docs_batch_keeps_shared_asset(db_session) -> None:
    """资产被另一空间 doc 引用 → 该篇 assets=0（跨空间共享资产不删）。"""
    space_id, user_id, doc_ids = await _seed(
        db_session,
        sub="r025-shared",
        docs=[("a", "f1"), ("b", "f2")],
        extra_space_for_shared_asset=True,
    )
    kb = FakeKbClient()
    client = _app(db_session, user_id, kb=kb)

    resp = client.post(DEL.format(space_id=space_id), json={"ids": [doc_ids["a"], doc_ids["b"]]})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["docs"] == 2
    assert data["assets"] == 1, "第一篇的资产被另一空间引用，不得连带删除"


async def test_delete_docs_batch_decrements_doc_count(db_session) -> None:
    """批量删除后 space.doc_count 按成功篇数递减（与单篇 DELETE 对称）。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r025-count", docs=[("a", "f1"), ("b", "f2"), ("c", "f3")])
    repo = SpaceRepository(db_session)
    space = await repo.get_by_id(space_id)
    space.doc_count = 3
    await db_session.commit()

    kb = SelectiveKbClient(fail_file_ids={"f2"})
    client = _app(db_session, user_id, kb=kb)
    resp = client.post(DEL.format(space_id=space_id), json={"ids": [doc_ids["a"], doc_ids["b"], doc_ids["c"]]})
    assert resp.status_code == 200, resp.text

    refreshed = await repo.get_by_id(space_id)
    assert refreshed.doc_count == 1, "只按 2 篇成功递减，失败篇不计入"


async def test_delete_docs_batch_non_builtin_uses_engine_router(db_session) -> None:
    """非 builtin 空间走 EngineRouter.adapter_for（与单篇 DELETE 同口径）。"""
    space_id, user_id, doc_ids = await _seed(
        db_session, sub="r025-router", docs=[("a", "f1"), ("b", "f2")], space_engine="redfox", engine_kb_id="kb-e1"
    )
    adapter = FakeAdapter()
    client = _app(db_session, user_id, kb=FakeKbClient(), router=FakeRouter(adapter))

    resp = client.post(DEL.format(space_id=space_id), json={"ids": [doc_ids["a"], doc_ids["b"]]})
    assert resp.status_code == 200, resp.text
    assert adapter.deleted_files == [("kb-e1", "f1"), ("kb-e1", "f2")]


# ------------------------------------------------------------------ R0.2.5 :recategorize 整批原子


async def test_recategorize_docs_batch_updates_asset_categories(db_session) -> None:
    """整批成功 → 每个资产 category 生效，返回归一化 category。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r025-rec", docs=[("a", "f1"), ("b", "f2"), ("c", "f3")])
    client = _app(db_session, user_id, kb=FakeKbClient())

    resp = client.post(
        REC.format(space_id=space_id),
        json={"ids": [doc_ids["a"], doc_ids["b"], doc_ids["c"]], "category": "AI·技术"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {"ok": True, "requested": 3, "docs": 3, "category": "AI·技术"}

    cats = await _categories(db_session)
    for key in ("a", "b", "c"):
        assert cats[await _asset_id_of(db_session, doc_ids[key])] == "AI·技术"


async def test_recategorize_docs_batch_empty_string_reverts_to_default(db_session) -> None:
    """category=""（清空人工标签）→ 响应归一化为默认「其他」，与单篇 PATCH 同契约。

    承袭单篇的已知不对称：库里存字面空串（语义=无人工标签），响应归一化为「其他」
    供前端呈现——空串不能当作文义分类值写入视图层。
    """
    space_id, user_id, doc_ids = await _seed(db_session, sub="r025-rev", docs=[("a", "f1")])
    client = _app(db_session, user_id, kb=FakeKbClient())

    resp = client.post(REC.format(space_id=space_id), json={"ids": [doc_ids["a"]], "category": ""})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data == {"ok": True, "requested": 1, "docs": 1, "category": "其他"}
    assert (await _categories(db_session))[await _asset_id_of(db_session, doc_ids["a"])] == ""


async def test_recategorize_docs_batch_is_asset_level_across_spaces(db_session) -> None:
    """category 是资产级属性：改本空间的 doc 分类，同一资产在另一空间的呈现一并生效。"""
    space_id, user_id, doc_ids = await _seed(
        db_session, sub="r025-level", docs=[("a", "f1")], extra_space_for_shared_asset=True
    )
    client = _app(db_session, user_id, kb=FakeKbClient())

    resp = client.post(REC.format(space_id=space_id), json={"ids": [doc_ids["a"]], "category": "教程·实践"})
    assert resp.status_code == 200, resp.text

    cats = await _categories(db_session)
    assert cats[await _asset_id_of(db_session, doc_ids["a"])] == "教程·实践"


async def test_recategorize_docs_batch_dedupes_ids(db_session) -> None:
    space_id, user_id, doc_ids = await _seed(db_session, sub="r025-rdedup", docs=[("a", "f1")])
    client = _app(db_session, user_id, kb=FakeKbClient())

    resp = client.post(REC.format(space_id=space_id), json={"ids": [doc_ids["a"], doc_ids["a"]], "category": "AI·技术"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["requested"] == 1


async def test_service_recategorize_docs_raises_for_missing_space(db_session) -> None:
    """服务层直调：无效空间 → 30004（不依赖路由与信封映射）。"""
    _space_id, user_id, doc_ids = await _seed(db_session, sub="r025-svc", docs=[("a", "f1")])
    svc = SpaceService(SpaceRepository(db_session), db_session)
    with pytest.raises(ResourceNotFoundError):
        await svc.recategorize_docs("nobody", "no-such-space", [doc_ids["a"]], "AI·技术")
