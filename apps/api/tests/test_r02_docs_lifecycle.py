"""R0.2.1 / R0.2.2 文档生命周期端点：DELETE /spaces/{id}/docs/{docId} + PATCH（仅分类）。

F-2 背景：此前全仓写路径仅 3 条（PATCH /public、DELETE space、PATCH engine），
文档零删除/编辑入口 → 与 F-1（单页 100 条上限）组合成「删不掉 + 看不全」的死锁。

口径锚点：
- 删除顺序沿用 AB-T11（引擎文件先删，成功才删 PG 行；失败整体回滚，PG 零残留）；
- builtin 走 kb_client.delete_kb_file 直调（不经 EngineRouter，防 allowlist 误配拦住 builtin）；
- 孤儿资产判定沿用 delete_space_cascade 的 NOT EXISTS（跨空间共享资产不删）；
- 「跳过公共库引入副本」的判定依据是 langbot_file_id 为空（link 只建 PG 行、未上传引擎），
  而非 doc.source——所有 doc 的 source 默认值都是 "copy"，无法区分来源。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_current_user_id, get_langbot_client, get_space_service
from app.core.errors import LangbotApiError, ResourceNotFoundError
from app.main import create_app
from app.models.entities import ContentAsset, KnowledgeDocument, KnowledgeSpace, Source, User
from app.repositories.space import SpaceRepository
from app.services.spaces import SpaceService

DOC_ID_UNKNOWN = "00000000-0000-0000-0000-000000000009"


# ------------------------------------------------------------------ 桩与夹具


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


class FakeAdapter:
    """非 builtin 引擎适配器桩（EngineRouter.adapter_for 返回）。"""

    def __init__(self, fail: Exception | None = None) -> None:
        self.fail = fail
        self.deleted_files: list[tuple[str, str]] = []

    async def delete_file(self, kb_id: str, file_id: str) -> None:
        if self.fail is not None:
            raise self.fail
        self.deleted_files.append((kb_id, file_id))


async def _seed(
    db_session: Any,
    *,
    sub: str,
    space_engine: str = "builtin",
    kb_uuid: str = "kb-r02",
    engine_kb_id: str = "",
    docs: list[tuple[str, str]] = (),
    extra_space_for_shared_asset: bool = False,
) -> tuple[str, str, dict[str, str]]:
    """铺一条最小数据链：user → space → source → assets → docs。

    docs: [(article_key, langbot_file_id)]，返回 {article_key: doc_id}。
    """
    user = User(sub=sub, email=f"{sub}@test.local", nickname=sub)
    db_session.add(user)
    await db_session.flush()
    source = Source(type="wechat_oa", external_id=f"biz-{sub}", name="R02测试号")
    db_session.add(source)
    await db_session.flush()
    space = KnowledgeSpace(
        user_id=user.id, name=f"R02空间-{sub}", langbot_kb_uuid=kb_uuid,
        engine=space_engine, engine_kb_id=engine_kb_id,
    )
    db_session.add(space)
    await db_session.flush()

    doc_ids: dict[str, str] = {}
    asset_ids: dict[str, str] = {}
    for i, (key, file_id) in enumerate(docs):
        asset = ContentAsset(
            source_id=source.id, external_id=f"{key}-{i}", url=f"https://mp.weixin.qq.com/s/{key}",
            title=f"文章 {key}-{i}", content_hash=f"h-{key}-{i}", content_markdown=f"# {key}-{i}",
            category="其他",
        )
        db_session.add(asset)
        await db_session.flush()
        asset_ids[key] = asset.id
        doc = KnowledgeDocument(asset_id=asset.id, space_id=space.id, langbot_file_id=file_id, status="READY")
        db_session.add(doc)
        await db_session.flush()
        doc_ids[key] = doc.id

    if extra_space_for_shared_asset and docs:
        other = KnowledgeSpace(user_id=user.id, name="共享资产的空间", langbot_kb_uuid="kb-other", engine="builtin")
        db_session.add(other)
        await db_session.flush()
        first_asset_id = next(iter(asset_ids.values()))
        db_session.add(KnowledgeDocument(asset_id=first_asset_id, space_id=other.id, status="READY"))
        await db_session.flush()

    await db_session.commit()  # 夹具 savepoint 模式：只释放保存点，外层回滚清场
    return space.id, user.id, doc_ids


class FakeRouter:
    """EngineRouter 桩：只覆写 adapter_for（非 builtin 分支）。"""

    def __init__(self, adapter: FakeAdapter) -> None:
        self._adapter = adapter

    def adapter_for(self, space: Any) -> Any:
        return self._adapter


def _app(
    db_session: Any,
    user_id: str,
    kb: FakeKbClient | None = None,
    router: FakeRouter | None = None,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_space_service] = lambda: SpaceService(
        SpaceRepository(db_session), db_session, engine_router=router
    )
    if kb is not None:
        app.dependency_overrides[get_langbot_client] = lambda: kb
    return TestClient(app)


# ------------------------------------------------------------------ R0.2.1 DELETE


async def test_delete_doc_builtin_calls_engine_then_deletes_rows(db_session) -> None:
    """builtin + 有 file_id：引擎 delete_kb_file 先于 PG 删除，doc/asset 行真消失。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r02-ok", docs=[("art-1", "file-1")])
    kb = FakeKbClient()
    client = _app(db_session, user_id, kb=kb)

    resp = client.delete(f"/api/v1/spaces/{space_id}/docs/{doc_ids['art-1']}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["ok"] is True
    assert body["data"]["docId"] == doc_ids["art-1"]
    assert body["data"] == {"ok": True, "docId": doc_ids["art-1"], "docs": 1, "assets": 1}
    assert kb.deleted_files == [("kb-r02", "file-1")]  # 引擎先行且用的是 langbot_kb_uuid

    await db_session.rollback()
    doc = await db_session.get(KnowledgeDocument, doc_ids["art-1"])
    assert doc is None


async def test_delete_doc_engine_failure_leaves_pg_intact(db_session) -> None:
    """引擎删除失败 → 错误信封（30002/502），doc 行保留（不出现「PG 删了库没删」）。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r02-fail", docs=[("art-1", "file-1")])
    kb = FakeKbClient(fail=LangbotApiError("LangBot 删除失败: 500"))
    client = _app(db_session, user_id, kb=kb)

    resp = client.delete(f"/api/v1/spaces/{space_id}/docs/{doc_ids['art-1']}")
    assert resp.status_code == 502 and resp.json()["code"] == 30002
    assert kb.deleted_files == []

    doc = await db_session.get(KnowledgeDocument, doc_ids["art-1"])
    assert doc is not None  # 未走到 PG 删除


async def test_delete_doc_405_structural_failure_degrades_and_removes_rows(db_session) -> None:
    """B34：引擎 405（该 LangBot 版本无文件级 DELETE 路由）是结构性失败——降级为告警后
    继续删 PG 行。修复前此路径整体 502/30002，前端文章删除完全不可用。

    降级安全的前提是 ask() 的候选集收窄（B25）只认 DB 行：残留的引擎文件不可能
    进入检索结果与引用，故继续删 PG 行不产生越界回答。
    """
    space_id, user_id, doc_ids = await _seed(db_session, sub="r02-405", docs=[("art-1", "file-1")])
    kb = FakeKbClient(fail=LangbotApiError("LangBot 405: Method Not Allowed", upstream_status=405))
    client = _app(db_session, user_id, kb=kb)

    resp = client.delete(f"/api/v1/spaces/{space_id}/docs/{doc_ids['art-1']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["ok"] is True

    await db_session.rollback()
    assert await db_session.get(KnowledgeDocument, doc_ids["art-1"]) is None


async def test_delete_doc_404_engine_file_absent_removes_rows(db_session) -> None:
    """引擎 404（文件已不在）= 删除意图已满足，同样继续删 PG 行。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r02-404", docs=[("art-1", "file-1")])
    kb = FakeKbClient(fail=ResourceNotFoundError("LangBot 资源不存在: files/file-1"))
    client = _app(db_session, user_id, kb=kb)

    resp = client.delete(f"/api/v1/spaces/{space_id}/docs/{doc_ids['art-1']}")
    assert resp.status_code == 200, resp.text

    await db_session.rollback()
    assert await db_session.get(KnowledgeDocument, doc_ids["art-1"]) is None


async def test_delete_doc_other_upstream_status_still_hard_fails(db_session) -> None:
    """405 之外的上游状态码仍是硬失败：保住「引擎删失败则 PG 零残留」的原契约。

    降级只认 405（与 404，见上）；400/502 等可能是可重试的真实故障，
    若一并吞掉会造出「本地已删、引擎仍在」的不一致。
    """
    space_id, user_id, doc_ids = await _seed(db_session, sub="r02-400", docs=[("art-1", "file-1")])
    kb = FakeKbClient(fail=LangbotApiError("LangBot 400: bad request", upstream_status=400))
    client = _app(db_session, user_id, kb=kb)

    resp = client.delete(f"/api/v1/spaces/{space_id}/docs/{doc_ids['art-1']}")
    assert resp.status_code == 502 and resp.json()["code"] == 30002

    doc = await db_session.get(KnowledgeDocument, doc_ids["art-1"])
    assert doc is not None  # 未走到 PG 删除


async def test_delete_doc_skips_engine_when_file_id_empty(db_session) -> None:
    """langbot_file_id 为空（公共库 link 引入的副本只建 PG 行）→ 不调引擎，直接删 PG。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r02-copy", docs=[("art-1", "")])
    kb = FakeKbClient()
    client = _app(db_session, user_id, kb=kb)

    resp = client.delete(f"/api/v1/spaces/{space_id}/docs/{doc_ids['art-1']}")
    assert resp.status_code == 200, resp.text
    assert kb.deleted_files == []
    assert resp.json()["data"]["docs"] == 1


async def test_delete_doc_shared_asset_is_kept(db_session) -> None:
    """资产被另一空间 doc 引用 → assets=0（跨空间共享资产不删，NOT EXISTS 孤儿判定）。"""
    space_id, user_id, doc_ids = await _seed(
        db_session, sub="r02-shared", docs=[("art-1", "file-1")], extra_space_for_shared_asset=True
    )
    # 先记下资产 id——断言针对「这条资产是否还在」，而非全表计数
    # （夹具只在写侧隔离，读侧可见环境里其他空间的资产行）。
    asset_id = await db_session.scalar(
        select(KnowledgeDocument.asset_id).where(KnowledgeDocument.id == doc_ids["art-1"])
    )
    kb = FakeKbClient()
    client = _app(db_session, user_id, kb=kb)

    resp = client.delete(f"/api/v1/spaces/{space_id}/docs/{doc_ids['art-1']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["assets"] == 0, "共享资产不应被删"

    remaining = await db_session.scalar(select(ContentAsset.id).where(ContentAsset.id == asset_id))
    assert remaining == asset_id, "资产行应保留（仍被另一空间 doc 引用）"


async def test_delete_doc_doc_count_decrements(db_session) -> None:
    """删除后 space.doc_count 递减（与 link_public_space 的递增对称）。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r02-count", docs=[("a", "f1"), ("b", "f2")])
    repo = SpaceRepository(db_session)
    space = await repo.get_by_id(space_id)
    space.doc_count = 2
    await db_session.commit()

    client = _app(db_session, user_id, kb=FakeKbClient())
    assert client.delete(f"/api/v1/spaces/{space_id}/docs/{doc_ids['a']}").status_code == 200

    refreshed = await repo.get_by_id(space_id)
    assert refreshed.doc_count == 1


async def test_delete_doc_unauthorized_and_unknown_ids(db_session) -> None:
    """他人空间 / 不存在的 doc / doc 不属该空间 → 30004（不泄露存在性）。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r02-owner", docs=[("art-1", "file-1")])
    kb = FakeKbClient()
    client = _app(db_session, user_id, kb=kb)

    assert client.delete("/api/v1/spaces/not-a-space/docs/x").status_code == 404
    assert client.delete(f"/api/v1/spaces/{space_id}/docs/{DOC_ID_UNKNOWN}").status_code == 404

    # doc 不属于该空间
    other = KnowledgeSpace(user_id=user_id, name="另一空间", langbot_kb_uuid="kb-2", engine="builtin")
    db_session.add(other)
    await db_session.commit()
    resp = client.delete(f"/api/v1/spaces/{other.id}/docs/{doc_ids['art-1']}")
    assert resp.status_code == 404 and resp.json()["code"] == 30004
    assert kb.deleted_files == []  # 越权路径不触碰引擎


async def test_delete_doc_requires_login() -> None:
    """登录保护：未登录 DELETE → 10001（不 override 鉴权依赖）。"""
    client = TestClient(create_app())
    resp = client.delete(f"/api/v1/spaces/{DOC_ID_UNKNOWN}/docs/{DOC_ID_UNKNOWN}")
    assert resp.status_code == 401 and resp.json()["code"] == 10001


async def test_delete_doc_non_builtin_uses_engine_router(db_session) -> None:
    """非 builtin：走 EngineRouter.adapter_for(space).delete_file(engine_kb_id, file_id)。"""
    space_id, user_id, doc_ids = await _seed(
        db_session, sub="r02-coze", space_engine="coze", engine_kb_id="coze-dataset-1", docs=[("art-1", "cz-1")]
    )
    adapter = FakeAdapter()
    client = _app(db_session, user_id, kb=FakeKbClient(), router=FakeRouter(adapter))

    resp = client.delete(f"/api/v1/spaces/{space_id}/docs/{doc_ids['art-1']}")
    assert resp.status_code == 200, resp.text
    assert adapter.deleted_files == [("coze-dataset-1", "cz-1")]  # 用的是 engine_kb_id


# ------------------------------------------------------------------ R0.2.2 PATCH（分类）


async def test_patch_doc_category_updates_asset(db_session) -> None:
    """合法分类 → 200 {docId, category}，asset.category 真被改写。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r02-cat", docs=[("art-1", "file-1")])
    client = _app(db_session, user_id)

    resp = client.patch(
        f"/api/v1/spaces/{space_id}/docs/{doc_ids['art-1']}",
        json={"category": "AI·技术"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] == {"docId": doc_ids["art-1"], "category": "AI·技术"}

    doc = await db_session.get(KnowledgeDocument, doc_ids["art-1"])
    asset = await db_session.get(ContentAsset, doc.asset_id)  # type: ignore[union-attr]
    assert asset is not None and asset.category == "AI·技术"


async def test_patch_doc_category_empty_string_allowed(db_session) -> None:
    """空串 = 清空人工标签（回默认展示口径），不报错。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r02-caten", docs=[("art-1", "f1")])
    client = _app(db_session, user_id)

    resp = client.patch(f"/api/v1/spaces/{space_id}/docs/{doc_ids['art-1']}", json={"category": ""})
    assert resp.status_code == 200, resp.text
    doc = await db_session.get(KnowledgeDocument, doc_ids["art-1"])
    asset = await db_session.get(ContentAsset, doc.asset_id)  # type: ignore[union-attr]
    assert asset is not None and asset.category == ""


@pytest.mark.parametrize("bad", ["小说", "AI·技术 ", "ai·技术"])
async def test_patch_doc_category_rejects_out_of_taxonomy(db_session, bad: str) -> None:
    """分类不在规则版六类或空串 → 10005/422（含大小写与尾随空格，不做归一化掩盖）。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub=f"r02-bad-{bad}", docs=[("art-1", "f1")])
    client = _app(db_session, user_id)

    resp = client.patch(f"/api/v1/spaces/{space_id}/docs/{doc_ids['art-1']}", json={"category": bad})
    assert resp.status_code == 422 and resp.json()["code"] == 10005

    doc = await db_session.get(KnowledgeDocument, doc_ids["art-1"])
    asset = await db_session.get(ContentAsset, doc.asset_id)  # type: ignore[union-attr]
    assert asset is not None and asset.category == "其他"  # 校验失败不改写


async def test_patch_doc_category_rejects_body_change_field(db_session) -> None:
    """请求体只接受 category；正文字段不在此端点范围（正文属采集事实，改写须走新采集）。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r02-body", docs=[("art-1", "f1")])
    client = _app(db_session, user_id)

    resp = client.patch(
        f"/api/v1/spaces/{space_id}/docs/{doc_ids['art-1']}",
        json={"category": "其他", "content": "被忽略的自由字段"},
    )
    assert resp.status_code == 200, resp.text
    doc = await db_session.get(KnowledgeDocument, doc_ids["art-1"])
    asset = await db_session.get(ContentAsset, doc.asset_id)  # type: ignore[union-attr]
    assert asset is not None and asset.content_markdown.startswith("# ")  # 正文未被自由字段污染


async def test_patch_doc_unauthorized_returns_30004(db_session) -> None:
    """越权空间 → 30004；不存在 doc → 30004。"""
    space_id, user_id, doc_ids = await _seed(db_session, sub="r02-authz", docs=[("art-1", "f1")])
    client = _app(db_session, user_id)

    resp = client.patch(
        f"/api/v1/spaces/{space_id}/docs/{DOC_ID_UNKNOWN}", json={"category": "其他"}
    )
    assert resp.status_code == 404 and resp.json()["code"] == 30004

    other = KnowledgeSpace(user_id=user_id, name="别碰", langbot_kb_uuid="kb", engine="builtin")
    db_session.add(other)
    await db_session.commit()
    resp2 = client.patch(f"/api/v1/spaces/{other.id}/docs/{doc_ids['art-1']}", json={"category": "其他"})
    assert resp2.status_code == 404 and resp2.json()["code"] == 30004


async def test_patch_doc_requires_login() -> None:
    """登录保护：未登录 PATCH → 10001。"""
    client = TestClient(create_app())
    resp = client.patch(f"/api/v1/spaces/{DOC_ID_UNKNOWN}/docs/{DOC_ID_UNKNOWN}", json={"category": "其他"})
    assert resp.status_code == 401 and resp.json()["code"] == 10001


# ------------------------------------------------------------------ F-2 路由存在性


def test_f2_doc_write_routes_registered() -> None:
    """F-2 销账锚：此前全仓写路径仅 3 条，文档零删除/编辑端点。经 OpenAPI 契约核对已注册。"""
    paths = create_app().openapi()["paths"]
    doc_path = paths["/api/v1/spaces/{space_id}/docs/{doc_id}"]
    assert "delete" in doc_path
    assert "patch" in doc_path
    # 同路径下既有的 GET（清单）与 POST（入库）未被覆盖
    assert "get" in paths["/api/v1/spaces/{space_id}/docs"]
    assert "post" in paths["/api/v1/spaces/{space_id}/docs"]


async def test_service_delete_doc_raises_for_missing_space(db_session) -> None:
    """服务层直测：无效空间 → 30004（Route 之外的口径核对）。"""
    repo = SpaceRepository(db_session)
    svc = SpaceService(repo, db_session)
    with pytest.raises(ResourceNotFoundError) as exc:
        await svc.delete_doc("nobody", "no-such-space", "no-doc")
    assert exc.value.code == 30004
