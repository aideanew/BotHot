"""STEP-47（V0.21.0，D-V21-08，P-82 第二刀）：其余 mock 域的**线上响应形状**进契约，并由真端点反向核。

与 STEP-46 同模式：`app/contracts/shapes.py` 是唯一源，schema 与 TS 从它派生；本文件证明
**真路由 + 真 service** 吐出的 `data` 与契约逐键一致（`additionalProperties: false`：多一个键也红）。
外部依赖（主平台、LangBot、微信抓取）一律换成既有测试里的桩，桩只替网络层，序列化走真代码。

三组断言：
1. 不连库：契约本身有牙齿（多键红 / 缺键红 / 枚举外取值红）。
2. S47.4 机器表：前端 mock 表 22 条路由 ↔ `MOCK_ROUTE_CONTRACTS` 一一对应，且每个契约名都真存在。
3. 连库：每个响应契约至少一条真端点反向核（`test_every_response_contract_has_a_live_check` 管覆盖）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.api.deps import (
    get_current_sub,
    get_current_user_id,
    get_db,
    get_kb_service,
    get_langbot_client,
    get_space_service,
)
from app.contracts.shapes import MOCK_ROUTE_CONTRACTS, MeWallet
from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = REPO_ROOT / "packages" / "contracts" / "schemas"
SHAPES = json.loads((SCHEMA_DIR / "shapes.schema.json").read_text("utf-8"))
ENGINE = json.loads((SCHEMA_DIR / "engine.schema.json").read_text("utf-8"))
MOCK_ROUTES_TS = REPO_ROOT / "apps" / "web" / "lib" / "api" / "mock-routes.ts"
TS_DTO = REPO_ROOT / "packages" / "contracts" / "src" / "shapes" / "dto.ts"

def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator({**SHAPES, "$ref": f"#/$defs/{name}"})


def _errors(name: str, data: Any) -> list[str]:
    return [f"{list(e.path)}: {e.message}" for e in _validator(name).iter_errors(data)]


def _check(name: str, data: Any) -> None:
    errs = _errors(name, data)
    assert not errs, f"{name} 与真端点 data 不一致：{errs}"


# ── 1. 不连库：契约本身有牙齿 ──────────────────────────────────────────────────


def test_closed_objects_reject_extra_and_missing_keys() -> None:
    good = {"ok": True, "engineResidue": False}
    assert not _errors("SpaceDeleteResult", good)
    assert _errors("SpaceDeleteResult", {**good, "extra": 1}), "多键必须红"
    assert _errors("SpaceDeleteResult", {"ok": True}), "缺键必须红"


def test_enums_reject_values_outside_the_published_set() -> None:
    item = {"id": "d", "title": "t", "source": "copy", "status": "ready", "updatedAt": "", "category": ""}
    assert not _errors("SpaceDocItem", item)
    assert _errors("SpaceDocItem", {**item, "status": "READY"}), "列表展示态只有小写三值"
    state = {"docId": "d", "status": "READY", "langbotFileId": ""}
    assert not _errors("DocIngestState", state)
    assert _errors("DocIngestState", {**state, "status": "FAILED"}), "FAILED 走 30003 错误信封，不进 200"


def test_stats_chunks_null_is_legal_but_negative_is_not() -> None:
    assert not _errors("SpaceStats", {"docs": 0, "chunks": None})
    assert _errors("SpaceStats", {"docs": 0, "chunks": -1})


def test_no_object_definition_is_open() -> None:
    """STEP-61 之后的状态：**本域没有任何开放对象**，多一个键一律红。

    原名 `test_me_wallet_is_the_only_open_object`（P-121 时代钉住"只有 `MeWallet` 开放"）。
    STEP-57 先用后端白名单投影断掉泄露路径（`test_me_wallet_projection.py`），STEP-61 再按
    D-V21-21 留下的另一半、以 D-V22-05 的"同一提交改冻结稿 + 改 `shapes.py` + 重生成"把
    `MeWallet` 改成封闭，于是这一条从"数出唯一开放对象"升级成"一个都不许开放"。
    数一遍的目的不变：防有人顺手把别的对象也放开。
    """
    open_defs = sorted(n for n, d in SHAPES["$defs"].items() if d.get("additionalProperties") is True)
    assert open_defs == [], f"契约里又出现开放对象（上游加字段就直通对外）：{open_defs}"
    objects = [n for n, d in SHAPES["$defs"].items() if d.get("type") == "object"]
    assert all(SHAPES["$defs"][n].get("additionalProperties") is False for n in objects)


def test_me_wallet_rejects_a_key_the_contract_does_not_publish() -> None:
    """STEP-61（D-V21-21 留下的另一半，落笔方式按 D-V22-05/D-V22-06）：契约侧封口。

    投影（`service.py` 的 `_project_wallet`）拦的是"我们往外吐什么"，本用例钉的是"契约认不认识
    这个键"——两边都改才算补完 P-121。先红读数在 `EVD-V22-61/`：改前 `extra="allow"`，多一个
    `internalNote` 不抛 ⇒ 本用例红。
    """
    with pytest.raises(ValidationError):
        MeWallet.model_validate({"balanceYuan": "1.00", "currency": "CNY", "internalNote": "风控内部值"})


def test_ts_dto_exports_every_def_without_unknown() -> None:
    src = TS_DTO.read_text("utf-8")
    for name in SHAPES["$defs"]:
        assert re.search(rf"export (interface|type) {name}\b", src), f"{name} 未出现在 shapes/dto.ts"
    assert "unknown" not in src and "any" not in re.findall(r"\b\w+\b", src)


# ── 2. S47.4：mock 路由 ↔ 契约名 机器表 ───────────────────────────────────────


def _ts_routes() -> list[tuple[str, re.Pattern[str]]]:
    src = MOCK_ROUTES_TS.read_text("utf-8")
    pairs = re.findall(r'method:\s*"([A-Z]+)",\s*\n\s*pattern:\s*/(.+?)/,\s*\n', src)
    return [(m, re.compile(p)) for m, p in pairs]


def _sample_path(template: str) -> str:
    return re.sub(r"\{[^}]+\}", "x1", template)


def test_mock_route_table_matches_the_frontend_one_to_one() -> None:
    routes = _ts_routes()
    assert len(routes) == 22, f"mock 表条数变了（{len(routes)}）：同批更新 MOCK_ROUTE_CONTRACTS"
    assert len(MOCK_ROUTE_CONTRACTS) == len(routes)
    hit: set[int] = set()
    for key in MOCK_ROUTE_CONTRACTS:
        method, template = key.split(" ", 1)
        path = _sample_path(template)
        # 首个命中生效——与前端分发器同序，所以这里也只认第一个
        first = next((i for i, (m, p) in enumerate(routes) if m == method and p.search(path)), None)
        assert first is not None, f"{key} 在前端 mock 表里找不到对应 pattern"
        assert first not in hit, f"{key} 与另一条登记撞到同一个 pattern"
        hit.add(first)
    assert hit == set(range(len(routes)))


def test_every_mapped_contract_name_exists() -> None:
    known = set(SHAPES["$defs"]) | set(ENGINE["$defs"])
    missing = {k: v for k, v in MOCK_ROUTE_CONTRACTS.items() if v not in known}
    assert not missing, missing


# ── 3. 连库：真端点反向核 ───────────────────────────────────────────────────────


async def _user(db_session: Any, sub: str) -> Any:
    from app.repositories.user import SqlAlchemyUserStore

    return await SqlAlchemyUserStore(db_session).upsert_by_sub(sub, f"{sub}@test.local", sub)


def _const(value: Any) -> Any:
    def provide() -> Any:
        return value

    return provide


def _app_for(db_session: Any, user_id: str, sub: str = "", **extra: Any) -> TestClient:
    from app.repositories.space import SpaceRepository
    from app.services.spaces import SpaceService

    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_current_sub] = lambda: sub or "sub-unused"
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_space_service] = lambda: SpaceService(SpaceRepository(db_session), db_session)
    for dep, value in extra.items():
        # 不能写 `lambda v=value: v`：FastAPI 会把带默认值的形参当成查询参数解析
        app.dependency_overrides[{"kb": get_langbot_client, "kbsvc": get_kb_service}[dep]] = _const(value)
    return TestClient(app)


async def test_spaces_crud_shapes(db_session) -> None:  # type: ignore[no-untyped-def]
    from test_r02_docs_lifecycle import FakeKbClient

    user = await _user(db_session, "sub-s47-spaces")
    client = _app_for(db_session, user.id, kb=FakeKbClient())

    created = client.post("/api/v1/spaces", json={"name": "S47 空间", "description": "d"})
    assert created.status_code == 201, created.text
    _check("SpaceDetail", created.json()["data"])
    space_id = created.json()["data"]["id"]

    listed = client.get("/api/v1/spaces")
    assert listed.status_code == 200, listed.text
    _check("SpacePage", listed.json()["data"])
    assert listed.json()["data"]["items"], "列表空 ⇒ items[] 的元素形状没被核到"

    got = client.get(f"/api/v1/spaces/{space_id}")
    _check("SpaceDetail", got.json()["data"])
    patched = client.patch(f"/api/v1/spaces/{space_id}", json={"description": "d2"})
    assert patched.status_code == 200, patched.text
    _check("SpaceDetail", patched.json()["data"])

    deleted = client.delete(f"/api/v1/spaces/{space_id}")
    assert deleted.status_code == 200, deleted.text
    _check("SpaceDeleteResult", deleted.json()["data"])


async def test_docs_read_and_write_shapes(db_session) -> None:  # type: ignore[no-untyped-def]
    from test_r02_docs_lifecycle import FakeKbClient, _seed

    space_id, user_id, doc_ids = await _seed(
        db_session, sub="sub-s47-docs", docs=[("a1", "f1"), ("a2", "f2"), ("a3", "f3"), ("a4", "f4")]
    )
    client = _app_for(db_session, user_id, kb=FakeKbClient())

    page = client.get(f"/api/v1/spaces/{space_id}/docs")
    assert page.status_code == 200, page.text
    _check("SpaceDocPage", page.json()["data"])
    assert len(page.json()["data"]["items"]) == 4

    cats = client.get(f"/api/v1/spaces/{space_id}/docs:categories")
    _check("DocCategoryList", cats.json()["data"])

    patch = client.patch(f"/api/v1/spaces/{space_id}/docs/{doc_ids['a1']}", json={"category": ""})
    assert patch.status_code == 200, patch.text
    _check("DocCategoryPatch", patch.json()["data"])

    recat = client.post(f"/api/v1/spaces/{space_id}/docs:recategorize", json={"ids": [doc_ids["a2"]], "category": ""})
    assert recat.status_code == 200, recat.text
    _check("DocsRecategorizeResult", recat.json()["data"])

    one = client.delete(f"/api/v1/spaces/{space_id}/docs/{doc_ids['a3']}")
    assert one.status_code == 200, one.text
    _check("DocDeleteResult", one.json()["data"])


async def test_docs_batch_delete_with_partial_failure_shape(db_session) -> None:  # type: ignore[no-untyped-def]
    """部分失败才会把 failed[] 的元素形状吐出来——全成功只核得到空数组。"""
    from test_r02_batch_docs import SelectiveKbClient
    from test_r02_docs_lifecycle import _seed

    space_id, user_id, doc_ids = await _seed(db_session, sub="sub-s47-batch", docs=[("b1", "fb1"), ("b2", "fb2")])
    client = _app_for(db_session, user_id, kb=SelectiveKbClient(fail_file_ids={"fb2"}))
    resp = client.post(f"/api/v1/spaces/{space_id}/docs:delete", json={"ids": [doc_ids["b1"], doc_ids["b2"]]})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    _check("DocsBatchDeleteResult", data)
    assert data["failed"], "failed[] 为空 ⇒ BatchDocFailure 没被核到"


async def test_public_library_shapes(db_session) -> None:  # type: ignore[no-untyped-def]
    from app.models.entities import ContentAsset, KnowledgeDocument, KnowledgeSpace, Source

    owner = await _user(db_session, "sub-s47-pub-owner")
    user = await _user(db_session, "sub-s47-pub-user")
    pub = KnowledgeSpace(
        user_id=owner.id, name="S47 公共库", langbot_kb_uuid="kb-s47-pub", is_public=True, owner_type="system"
    )
    mine = KnowledgeSpace(user_id=user.id, name="S47 我的空间", langbot_kb_uuid="kb-s47-mine")
    source = Source(type="wechat_oa", external_id="biz-s47", name="S47号")
    db_session.add_all([pub, mine, source])
    await db_session.flush()
    asset = ContentAsset(
        source_id=source.id, external_id="s47-a", url="https://mp.weixin.qq.com/s/s47a", title="t",
        content_hash="h-s47-a", content_markdown="# t", status="READY",
    )
    db_session.add(asset)
    await db_session.flush()
    db_session.add(KnowledgeDocument(asset_id=asset.id, space_id=pub.id, status="READY"))
    await db_session.commit()

    client = _app_for(db_session, user.id)
    listed = client.get("/api/v1/spaces/public")
    assert listed.status_code == 200, listed.text
    _check("PublicSpacePage", listed.json()["data"])
    assert listed.json()["data"]["items"]

    linked = client.post(f"/api/v1/spaces/{mine.id}/links", json={"public_space_id": pub.id})
    assert linked.status_code == 200, linked.text
    _check("LinkResult", linked.json()["data"])
    assert linked.json()["data"]["copied"] == 1


async def test_ingest_and_status_shapes(db_session) -> None:  # type: ignore[no-untyped-def]
    from test_langbot import _client as lb_client
    from test_langbot import _StubResolver

    from app.repositories.space import SpaceRepository
    from app.services.kb import KnowledgeBaseService

    user = await _user(db_session, "sub-s47-ingest")
    space = await SpaceRepository(db_session).create(user_id=user.id, name="S47 入库空间")
    await db_session.commit()
    svc = KnowledgeBaseService(lb_client(), db_session, _StubResolver())
    client = _app_for(db_session, user.id, kbsvc=svc)

    accepted = client.post(f"/api/v1/spaces/{space.id}/docs", json={"url": "https://mp.weixin.qq.com/s/s47ingest"})
    assert accepted.status_code == 202, accepted.text
    _check("IngestAccepted", accepted.json()["data"])

    doc_id = accepted.json()["data"]["docId"]
    status = client.get(f"/api/v1/spaces/{space.id}/docs/{doc_id}/status")
    assert status.status_code == 200, status.text
    _check("DocIngestState", status.json()["data"])


async def test_notifications_shapes(db_session) -> None:  # type: ignore[no-untyped-def]
    from app.models.bothot_entities import Notification

    db_session.add_all([
        Notification(sub="sub-s47-n", title="定向", message="m", url="https://x.test/a", space_id="sp", doc_id="d"),
        Notification(sub="", is_broadcast=True, title="广播", message="m"),
    ])
    await db_session.flush()
    client = _app_for(db_session, "uid-unused", sub="sub-s47-n")

    hist = client.get("/api/v1/system/notifications/history")
    assert hist.status_code == 200, hist.text
    _check("NotificationHistoryPage", hist.json()["data"])
    assert len(hist.json()["data"]["items"]) >= 2

    read = client.put("/api/v1/system/notifications/read", json={"before": "2999-01-01T00:00:00+00:00"})
    assert read.status_code == 200, read.text
    _check("NotificationReadResult", read.json()["data"])


# ── 不连库的真端点（依赖全是桩，序列化走真路由）────────────────────────────────


def test_resolve_and_extract_shapes() -> None:
    from test_extractor import _endpoint_client as extract_client
    from test_resolver import SAMPLE_CT, _client_of

    from app.api.v1.resolve import get_resolver_service

    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_resolver_service] = lambda: _client_of(SAMPLE_CT)
    resolved = TestClient(app).post("/api/v1/resolve", json={"url": "https://mp.weixin.qq.com/s/abc"})
    assert resolved.status_code == 200, resolved.text
    _check("ResolvedArticleView", resolved.json()["data"])

    extracted = extract_client().post("/api/v1/extract", json={"url": "https://mp.weixin.qq.com/s/abc"})
    assert extracted.status_code == 200, extracted.text
    _check("ExtractedArticleView", extracted.json()["data"])
    assert extracted.json()["data"]["images"], "images 为空 ⇒ ExtractedImageView 没被核到"


def test_me_normal_branch_and_logout_shapes() -> None:
    from test_auth import _client_with, _login_state, _svc_bundle

    svc, idp, _, _ = _svc_bundle()
    client = _client_with(svc)
    state = _login_state(client)
    assert client.get(f"/api/v1/auth/callback?code={idp.issue_code()}&state={state}").status_code == 200

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    _check("MeView", me.json()["data"])

    out = client.post("/api/v1/auth/logout")
    assert out.status_code == 200, out.text
    _check("LogoutResult", out.json()["data"])


async def test_me_degraded_branch_shape(db_session) -> None:  # type: ignore[no-untyped-def]
    """降级分支多带 providerUnreachable——可选键要真被吐出来过一次才算核到。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from test_auth import _client_with, _dead_record, _unreachable_bundle

    from app.models.entities import User

    db_session.add(User(sub="user-1", email="dev@aidean.local", nickname="老板"))
    await db_session.flush()
    conn = await db_session.connection()
    factory = async_sessionmaker(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
    svc, store = _unreachable_bundle(factory)
    await store.create(_dead_record(), 900)
    client = _client_with(svc)
    client.cookies.set("bothot_session", "sid-unreachable")
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    _check("MeView", data)
    assert data["providerUnreachable"] is True


# ── 覆盖守卫：每个"顶层响应契约"都被上面某条真端点核过（静态读本文件，不依赖库在不在）──


def test_every_response_contract_has_a_live_check() -> None:
    """静态判定：本文件里 `_check("<契约名>", …)` 的集合必须覆盖登记表的全部 shapes 契约。

    为什么不用运行期集合：无库环境下连库用例被 skip，运行期集合必然不全，守卫只能跟着 skip——
    而 CI-Windows 的 skip 门是零余量记账的，多一条 skip 就红。静态读源码两边都稳定。
    """
    expected = set(MOCK_ROUTE_CONTRACTS.values()) - set(ENGINE["$defs"])
    checked = set(re.findall(r'_check\("(\w+)"', Path(__file__).read_text("utf-8")))
    missing = expected - checked
    assert not missing, f"这些响应契约没有任何真端点反向核：{sorted(missing)}"
