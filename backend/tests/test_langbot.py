"""B-T8 验收测试：LangBot 防腐层（MockTransport 桩，零真实请求）+ KB 编排 + 端点。

- client：登录/token 缓存/401 重登、错误映射（404→30004、4xx→30002、5xx/网络→50002）、
  上传/触发/清单/删除形状；
- service（连库，PG 不可达自动 skip）：ensure_kb 建库回写幂等、ingest_url 全链落库、
  状态回写映射；
- 端点：未登录 10001（连库轮内验证 202 链）。
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_extractor import SAMPLE_RICH  # B-T6 既有精简样本（含广告/二维码/图片）

from app.api.deps import get_current_user_id, get_kb_service
from app.core.errors import (
    DependencyUnavailableError,
    ExtractQualityLowError,
    IngestFailedError,
    LangbotApiError,
    ResourceNotFoundError,
)
from app.main import create_app
from app.models.entities import KnowledgeDocument
from app.providers.langbot.client import LangBotClient
from app.providers.source_resolver import WechatArticleFetcher
from app.repositories.space import SpaceRepository
from app.services.kb import KnowledgeBaseService
from app.services.resolver import SourceResolverService

BASE = "http://langbot.test"


# ------------------------------------------------------------------ 桩工厂


def _lb_transport() -> tuple[httpx.MockTransport, dict[str, list[tuple[str, str]]]]:
    """LangBot 全链桩：login→建库→上传→触发→清单→删除；记录请求序列。"""
    calls: dict[str, list[tuple[str, str]]] = {"reqs": []}
    state = {"file": "lb-file-1", "kb": "kb-uuid-1", "status": "processing"}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["reqs"].append((request.method, request.url.path))
        path = request.url.path
        if path == "/api/v1/user/auth":
            return httpx.Response(200, json={"data": {"token": "jwt-1"}})
        if path == "/api/v1/knowledge/engines":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {"engines": [{"plugin_id": "langbot-team/LangRAG", "capabilities": ["doc_ingestion"]}]},
                },
            )
        if path == "/api/v1/provider/models/embedding":
            from app.core.config import get_settings

            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "models": [
                            {
                                "uuid": "emb-1",
                                "name": "bge-m3",
                                "provider": {"base_url": get_settings().embedding_api_base.rstrip("/")},
                            }
                        ]
                    },
                },
            )
        if path == "/api/v1/knowledge/bases" and request.method == "POST":
            return httpx.Response(200, json={"uuid": state["kb"]})
        if path == "/api/v1/files/documents":
            return httpx.Response(200, json={"code": 0, "data": {"file_id": state["file"]}})
        if path == f"/api/v1/knowledge/bases/{state['kb']}/files" and request.method == "POST":
            state["status"] = "processing"
            return httpx.Response(200, json={"task_id": "task-1"})
        if path == f"/api/v1/knowledge/bases/{state['kb']}/files" and request.method == "GET":
            return httpx.Response(
                200, json={"code": 0, "data": {"files": [{"file_name": state["file"], "status": state["status"]}]}}
            )
        if path == f"/api/v1/knowledge/bases/{state['kb']}/files/{state['file']}":
            return httpx.Response(204)
        if path == f"/api/v1/knowledge/bases/{state['kb']}/retrieve":
            return httpx.Response(
                200, json={"code": 0, "data": {"results": [{"content": [{"text": "命中段落"}], "score": 0.9}]}}
            )
        return httpx.Response(404, json={"message": "not found"})

    return httpx.MockTransport(handler), calls


def _client(transport: httpx.MockTransport | None = None) -> LangBotClient:
    http = httpx.AsyncClient(transport=transport or _lb_transport()[0], follow_redirects=True)
    return LangBotClient(BASE, "admin@bothot.local", "pw", http=http)


# ------------------------------------------------------------------ client 桩测


def test_login_caches_token_and_request_chain() -> None:
    """登录 → token 缓存复用（第二次请求不再 /auth）。"""
    transport, calls = _lb_transport()
    client = _client(transport)

    async def run() -> None:
        await client.list_engines()
        await client.list_embedding_models()
        assert len([m for m in calls["reqs"] if m[1] == "/api/v1/user/auth"]) == 1

    import anyio

    anyio.run(run)


def test_401_relogin_retry() -> None:
    """token 失效：401 → 重登一次 → 重试成功。"""
    calls: list[tuple[str, str]] = []
    tokens = iter(["stale", "fresh"])

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        auth = request.headers.get("authorization", "")
        if request.url.path == "/api/v1/user/auth":
            return httpx.Response(200, json={"data": {"token": next(tokens)}})
        if auth.endswith("stale"):
            return httpx.Response(401)
        return httpx.Response(200, json={"data": [{"plugin_id": "x"}]})

    client = LangBotClient(BASE, "a", "b", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    import anyio

    assert anyio.run(client.list_engines)[0]["plugin_id"] == "x"
    assert calls.count(("POST", "/api/v1/user/auth")) == 2  # 首登 + 401 重登


def test_error_mapping_404_4xx_5xx_network() -> None:
    """404→30004；其他 4xx→30002；5xx→50002；网络异常→50002。"""
    import anyio

    def make(status: int, network: bool = False):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/user/auth":
                return httpx.Response(200, json={"data": {"token": "t"}})
            if network:
                raise httpx.ConnectError("boom")
            return httpx.Response(status, json={"message": "err"})

        return LangBotClient(BASE, "a", "b", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    with pytest.raises(ResourceNotFoundError):
        anyio.run(make(404).list_engines)
    with pytest.raises(LangbotApiError):
        anyio.run(make(400).list_engines)
    with pytest.raises(DependencyUnavailableError):
        anyio.run(make(503).list_engines)
    with pytest.raises(DependencyUnavailableError):
        anyio.run(make(0, network=True).list_engines)


def test_upload_ingest_poll_shapes() -> None:
    """上传→file_id；触发→task_id；清单解包；retrieve 结果。"""
    import anyio

    client = _client()
    file_id = anyio.run(client.upload_document, "a.md", "# 标题")
    assert file_id == "lb-file-1"
    task_id = anyio.run(client.trigger_ingest, "kb-uuid-1", file_id)
    assert task_id == "task-1"
    files = anyio.run(client.list_kb_files, "kb-uuid-1")
    assert files[0]["status"] == "processing"
    hits = anyio.run(client.retrieve, "kb-uuid-1", "麻籽")
    assert hits[0]["content"][0]["text"] == "命中段落"  # 实测形状：content 为块列表
    anyio.run(client.delete_kb_file, "kb-uuid-1", file_id)  # 不抛即通过


# ------------------------------------------------------------------ service 编排（连库）


class _StubResolver(SourceResolverService):
    """换桩网络层的 resolver（其余复用真解析链）。"""

    def __init__(self) -> None:
        super().__init__(
            WechatArticleFetcher(
                client=httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda req: httpx.Response(
                            200, text=SAMPLE_RICH, headers={"content-type": "text/html; charset=utf-8"}
                        )
                    )
                )
            )
        )


class _LowQualityResolver(SourceResolverService):
    """低质样本桩（20003 前置拦截验证；SAMPLE_LOW_QUALITY 全链真实解析）。"""

    def __init__(self) -> None:
        from test_normalizer_quality import SAMPLE_LOW_QUALITY

        super().__init__(
            WechatArticleFetcher(
                client=httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda req: httpx.Response(
                            200,
                            text=SAMPLE_LOW_QUALITY,
                            headers={"content-type": "text/html; charset=utf-8"},
                        )
                    )
                )
            )
        )


def _counter_lb_transport() -> tuple[httpx.MockTransport, dict[str, list[tuple[str, str]]], dict[str, int]]:
    """LangBot 桩（每次上传返回递增 file_id）：验证 V5 覆盖重走。"""
    calls: dict[str, list[tuple[str, str]]] = {"reqs": []}
    state = {"kb": "kb-uuid-1", "n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["reqs"].append((request.method, request.url.path))
        path, method = request.url.path, request.method
        if path == "/api/v1/user/auth":
            return httpx.Response(200, json={"data": {"token": "jwt-1"}})
        if path == "/api/v1/knowledge/engines":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {"engines": [{"plugin_id": "langbot-team/LangRAG", "capabilities": ["doc_ingestion"]}]},
                },
            )
        if path == "/api/v1/provider/models/embedding":
            from app.core.config import get_settings

            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "models": [
                            {
                                "uuid": "emb-1",
                                "name": "bge-m3",
                                "provider": {"base_url": get_settings().embedding_api_base.rstrip("/")},
                            }
                        ]
                    },
                },
            )
        if path == "/api/v1/knowledge/bases" and method == "POST":
            return httpx.Response(200, json={"uuid": state["kb"]})
        if path == "/api/v1/files/documents":
            state["n"] += 1
            return httpx.Response(200, json={"code": 0, "data": {"file_id": f"lb-file-{state['n']}"}})
        if path == f"/api/v1/knowledge/bases/{state['kb']}/files" and method == "POST":
            return httpx.Response(200, json={"task_id": "task-ignored"})
        if path == f"/api/v1/knowledge/bases/{state['kb']}/files" and method == "GET":
            return httpx.Response(
                200,
                json={"code": 0, "data": {"files": [{"file_name": f"lb-file-{state['n']}", "status": "processing"}]}},
            )
        return httpx.Response(404, json={"message": "not found"})

    return httpx.MockTransport(handler), calls, state


async def test_ensure_kb_and_ingest_full_chain(db_session) -> None:  # type: ignore[no-untyped-def]
    """ensure_kb 建库回写 + 幂等复用；ingest_url 全链：上传/触发/资产/文档落库。"""
    from test_repositories import _make_user

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="B-T8空间")
    await db_session.commit()

    svc = KnowledgeBaseService(_client(), db_session, _StubResolver())
    kb_uuid = await svc.ensure_kb(space.id)
    assert kb_uuid == "kb-uuid-1"

    repo = SpaceRepository(db_session)
    refreshed = await repo.get_by_id(space.id)
    assert refreshed is not None and refreshed.langbot_kb_uuid == "kb-uuid-1"
    assert await svc.ensure_kb(space.id) == "kb-uuid-1"  # 幂等：不再建库

    result = await svc.ingest_url(space.id, "https://mp.weixin.qq.com/s/sample001")
    assert result["status"] == "INDEXED"
    assert result["langbotFileId"] == "lb-file-1"
    # SPEC §3.1 冻结：taskId 恒空串——桩返回 task-1 也不得透传（V1 形状回归）
    assert result["taskId"] == ""
    assert result["title"]  # 样本真实解析出标题


async def test_doc_status_poll_maps_to_ready(db_session) -> None:  # type: ignore[no-untyped-def]
    """状态查询：LangBot completed → 本地 READY 回写；FAILED → 30003。"""
    from test_repositories import _make_user

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="状态查询空间")
    await db_session.commit()
    svc = KnowledgeBaseService(_client(), db_session, _StubResolver())
    result = await svc.ingest_url(space.id, "https://mp.weixin.qq.com/s/sample002")
    doc_id = result["docId"]

    # 桩清单此时 status=processing → INDEXED
    status = await svc.get_doc_ingest_status(space.id, doc_id)
    assert status["status"] == "INDEXED"

    # 翻桩为 completed → READY 回写
    transport, _ = _lb_transport()
    http = httpx.AsyncClient(transport=transport, follow_redirects=True)
    client2 = _FlippableClient(http)
    svc2 = KnowledgeBaseService(client2, db_session, _StubResolver())
    final = await svc2.get_doc_ingest_status(space.id, doc_id)
    assert final["status"] == "READY"


class _FlippableClient(LangBotClient):
    """文件状态恒 completed 的桩（READY 回写用）。"""

    def __init__(self, http: httpx.AsyncClient) -> None:
        super().__init__(BASE, "a", "b", http=http)

    async def list_kb_files(self, kb_uuid: str) -> list[dict[str, Any]]:
        return [{"file_name": "lb-file-1", "status": "completed"}]


async def test_ingest_url_unknown_space_maps_30004(db_session) -> None:  # type: ignore[no-untyped-def]
    """无效空间 → 30004（不泄露存在性）。"""
    svc = KnowledgeBaseService(_client(), db_session, _StubResolver())
    with pytest.raises(ResourceNotFoundError):
        await svc.ingest_url("no-such-space", "https://mp.weixin.qq.com/s/x")


# ------------------------------------------------------------------ 端点


def test_endpoints_unauthenticated_10001() -> None:
    """登录保护：两端点未登录 → 10001（容器冒烟对照证据）。"""
    client = TestClient(create_app(), raise_server_exceptions=False)
    r1 = client.post("/api/v1/spaces/xxx/docs", json={"url": "https://mp.weixin.qq.com/s/a"})
    r2 = client.get("/api/v1/spaces/xxx/docs/doc-1/status")
    assert r1.status_code == 401 and r1.json()["code"] == 10001
    assert r2.status_code == 401 and r2.json()["code"] == 10001


def _unused_import_guard() -> None:  # pragma: no cover
    raise IngestFailedError("keep-import")


async def test_ingest_low_quality_maps_20003(db_session) -> None:  # type: ignore[no-untyped-def]
    """v0.3h④：低质内容 → 20003/422（非 30003/502），message 带 qualityScore 可观测。"""
    from test_repositories import _make_user

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="低质空间")
    svc = KnowledgeBaseService(_client(), db_session, _LowQualityResolver())
    with pytest.raises(ExtractQualityLowError) as exc_info:
        await svc.ingest_url(space.id, "https://mp.weixin.qq.com/s/lowquality")
    assert exc_info.value.code == 20003
    assert "qualityScore=" in exc_info.value.message


# ---------------------------------------------- SPEC V1-V5 形状桩回归（implement-single-article-mvp）


class _FixedStatusClient(LangBotClient):
    """KB 文件清单恒返回指定状态的桩（failed/timeout → 30003 路径）。"""

    def __init__(self, status: str) -> None:
        super().__init__(BASE, "a", "b", http=httpx.AsyncClient())
        self._status = status

    async def list_kb_files(self, kb_uuid: str) -> list[dict[str, Any]]:
        return [{"file_name": "lb-file-1", "status": self._status}]


@pytest.mark.parametrize("lb_status", ["failed", "timeout"])
async def test_doc_status_failed_and_timeout_raise_30003(  # type: ignore[no-untyped-def]
    db_session, lb_status
) -> None:
    """SPEC §3.2/V2：LangBot failed/timeout → 抛 30003/502（抛错，非 200 包 error）。"""
    from test_repositories import _make_user

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="失败态空间")
    await db_session.commit()
    svc = KnowledgeBaseService(_client(), db_session, _StubResolver())
    doc_id = (await svc.ingest_url(space.id, "https://mp.weixin.qq.com/s/failcase"))["docId"]

    svc2 = KnowledgeBaseService(_FixedStatusClient(lb_status), db_session, _StubResolver())
    with pytest.raises(IngestFailedError) as exc_info:
        await svc2.get_doc_ingest_status(space.id, doc_id)
    assert exc_info.value.code == 30003
    assert exc_info.value.http_status == 502


async def test_ingest_low_quality_never_touches_langbot(db_session) -> None:  # type: ignore[no-untyped-def]
    """SPEC V3：低质 20003/422 前置拦截——不建 docId，LangBot 零请求（不触达）。"""
    from test_repositories import _make_user

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="低质零触达空间")

    transport, calls = _lb_transport()
    lb = LangBotClient(BASE, "a", "b", http=httpx.AsyncClient(transport=transport, follow_redirects=True))
    svc = KnowledgeBaseService(lb, db_session, _LowQualityResolver())
    with pytest.raises(ExtractQualityLowError) as exc_info:
        await svc.ingest_url(space.id, "https://mp.weixin.qq.com/s/lowquality")
    assert exc_info.value.code == 20003
    # 登录/引擎/上传/触发全部零请求——评分护栏在 KB 就绪之前
    assert calls["reqs"] == []


async def test_reingest_same_url_overwrites_no_new_row(db_session) -> None:  # type: ignore[no-untyped-def]
    """SPEC V5/D3(a)：同 URL 同空间重复提交 → 覆盖 langbot_file_id 重走，行数不增、docId 不变。"""
    from test_repositories import _make_user

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="幂等空间")
    await db_session.commit()

    transport, _, state = _counter_lb_transport()
    lb = LangBotClient(BASE, "a", "b", http=httpx.AsyncClient(transport=transport, follow_redirects=True))
    svc = KnowledgeBaseService(lb, db_session, _StubResolver())

    first = await svc.ingest_url(space.id, "https://mp.weixin.qq.com/s/idem001")
    assert first["taskId"] == ""  # SPEC §3.1 恒空串（桩返回 task-ignored 也不透传）
    second = await svc.ingest_url(space.id, "https://mp.weixin.qq.com/s/idem001")

    assert second["docId"] == first["docId"]  # 不产生新 docId（非短路：仍重走 ingest）
    assert second["langbotFileId"] == "lb-file-2"  # 覆盖为第二次上传的 file_id
    assert state["n"] == 2  # 重走 ingest（两次上传，非短路返回）

    total = await db_session.scalar(
        select(func.count()).select_from(KnowledgeDocument).where(KnowledgeDocument.space_id == space.id)
    )
    assert total == 1  # DB 文档行数不增


# ------------------------------------------------------------------ 端点（桩 service）：V1/V2/V3 信封形状


class _StubKBService:
    """端点桩：固定 v0.3h 响应形状或抛指定异常（路由/信封/状态码验证）。"""

    def __init__(self, result: dict[str, Any] | Exception) -> None:
        self._result = result

    async def ingest_url(self, space_id: str, url: str) -> dict[str, Any]:
        if isinstance(self._result, Exception):
            raise self._result
        return dict(self._result)

    async def get_doc_ingest_status(self, space_id: str, doc_id: str) -> dict[str, Any]:
        if isinstance(self._result, Exception):
            raise self._result
        return dict(self._result)


def _ingest_endpoint_client(svc: _StubKBService) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_kb_service] = lambda: svc
    return TestClient(app)


_V1_SHAPE = {"docId": "doc-1", "title": "标题", "status": "INDEXED", "langbotFileId": "lb-file-1", "taskId": ""}


def test_ingest_endpoint_202_shape_v1() -> None:
    """SPEC V1：202 + data 键精确 {docId,title,status,langbotFileId,taskId}，taskId==""。"""
    resp = _ingest_endpoint_client(_StubKBService(_V1_SHAPE)).post(
        "/api/v1/spaces/s1/docs", json={"url": "https://mp.weixin.qq.com/s/x"}
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["code"] == 0
    assert set(body["data"].keys()) == {"docId", "title", "status", "langbotFileId", "taskId"}
    assert body["data"]["status"] == "INDEXED"
    assert body["data"]["taskId"] == ""


def test_ingest_status_endpoint_200_shape() -> None:
    """SPEC §3.2：轮询端点 data 键精确 {docId,status,langbotFileId}。"""
    resp = _ingest_endpoint_client(_StubKBService({"docId": "doc-1", "status": "READY", "langbotFileId": "f"})).get(
        "/api/v1/spaces/s1/docs/doc-1/status"
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    assert set(resp.json()["data"].keys()) == {"docId", "status", "langbotFileId"}


def test_ingest_endpoint_missing_url_maps_10005() -> None:
    """10005/422：body 缺 url（RequestValidationError → 统一信封）。"""
    resp = _ingest_endpoint_client(_StubKBService(_V1_SHAPE)).post("/api/v1/spaces/s1/docs", json={})
    assert resp.status_code == 422
    assert resp.json()["code"] == 10005


def test_ingest_status_endpoint_failed_maps_30003_502() -> None:
    """SPEC V2：轮询失败路径 → 30003/502 信封（非 200 包裹 error 字段）。"""
    resp = _ingest_endpoint_client(_StubKBService(IngestFailedError("LangBot ingest failed"))).get(
        "/api/v1/spaces/s1/docs/doc-1/status"
    )
    assert resp.status_code == 502
    body = resp.json()
    assert body["code"] == 30003
    assert body["data"] is None


def test_ingest_status_endpoint_bad_space_maps_30004_readable() -> None:
    """30004/404：无效空间/文档，message 可读不裸 UUID（不泄露存在性）。"""
    resp = _ingest_endpoint_client(_StubKBService(ResourceNotFoundError("0f0e9d8c7b6a49388a7b6c5d4e3f2a1b"))).get(
        "/api/v1/spaces/s1/docs/doc-1/status"
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == 30004
    assert body["message"].startswith("资源不存在或无权限")
