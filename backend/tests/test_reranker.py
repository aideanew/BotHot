"""阶段 3.2.1 验收测试：检索重排（硅基流动 bge-reranker-v2-m3 端口 + ask 链路接线）。

大纲 3.2.1 口径：`providers/reranker.py`——retrieve top_k=20 → 重排取 5。

覆盖：
- 端口契约（mock transport，零真实网络）：请求形状 / 乱序回填 / 空候选零请求 /
  4xx、非 JSON、缺分 → None（保序回退）/ 停用态显式不可用；
- 装配：Key 缺失或显式关闭 → NoopReranker；留空回落 embedding_*（同供应商）；
- ask 链路（真实 PG + 桩 retrieve）：重排开启 → 候选宽度 20 且 citations 按重排序取 5；
  重排失败 → 保序截断；重排关闭 → top_k=5 零回归；与 3.1.1 过滤可组合。
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from test_chat_sse import _frames, _llm_echo_transport
from test_metadata_filter import _RecordingLangBot, _results, _seed_doc, _seed_source, _seed_space

from app.api.deps import get_current_user_id, get_db, get_langbot_client, get_reranker
from app.main import create_app
from app.providers.reranker import (
    DEFAULT_RERANK_MODEL,
    NoopReranker,
    SiliconflowReranker,
    make_reranker,
)


@pytest.fixture(autouse=True)
def _restore_llm_factory() -> Any:
    from app.api.v1 import chat as chat_module

    original = chat_module._llm_http_factory
    yield
    chat_module._llm_http_factory = original


# ------------------------------------------------------------------ 端口契约（mock transport）


def _reranker_with(handler: Any, **kwargs: Any) -> tuple[SiliconflowReranker, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def _wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(_wrapped))
    return SiliconflowReranker("https://api.example/v1", "sk-test", http=http, **kwargs), seen


def _payload(*pairs: tuple[int, float]) -> str:
    return json.dumps(
        {
            "id": "r-1",
            "results": [{"index": i, "document": None, "relevance_score": s} for i, s in pairs],
            "meta": {"tokens": {"input_tokens": 1, "output_tokens": 0}},
        }
    )


async def test_rerank_request_shape_and_index_backfill() -> None:
    """请求形状（/rerank + Bearer + model/top_n/return_documents）+ 乱序响应按 index 回填原序。"""
    reranker, seen = _reranker_with(lambda _r: httpx.Response(200, text=_payload((2, 0.9), (0, 0.1), (1, 0.5))))
    scores = await reranker.rerank("问题", ["doc-a", "doc-b", "doc-c"])
    # 原序回填：doc-a=0.1 / doc-b=0.5 / doc-c=0.9（不依赖上游返回顺序）
    assert scores == [0.1, 0.5, 0.9]
    assert len(seen) == 1
    req = seen[0]
    assert str(req.url) == "https://api.example/v1/rerank"
    assert req.headers["authorization"] == "Bearer sk-test"
    assert req.headers["content-type"].startswith("application/json")
    body = json.loads(req.content)
    assert body["model"] == DEFAULT_RERANK_MODEL
    assert body["query"] == "问题"
    assert body["documents"] == ["doc-a", "doc-b", "doc-c"]
    assert body["top_n"] == 3
    assert body["return_documents"] is False


async def test_rerank_empty_documents_makes_no_request() -> None:
    """空候选 → [] 且零上游请求（不计费、不空转）。"""
    reranker, seen = _reranker_with(lambda _r: httpx.Response(200, text=_payload()))
    assert await reranker.rerank("问题", []) == []
    assert seen == []


@pytest.mark.parametrize(
    "handler",
    [
        pytest.param(lambda _r: httpx.Response(429, text="rate limited"), id="4xx"),
        pytest.param(lambda _r: httpx.Response(200, text="not-json"), id="non-json"),
        pytest.param(lambda _r: httpx.Response(200, text=_payload((0, 0.7))), id="missing-index"),
        pytest.param(lambda _r: httpx.Response(200, text=json.dumps({"results": "x"})), id="bad-shape"),
    ],
)
async def test_rerank_failures_return_none(handler: Any) -> None:
    """上游异常/形状不符 → None（调用方保序回退；绝不猜分、绝不假装成功）。"""
    reranker, _ = _reranker_with(handler)
    assert await reranker.rerank("问题", ["doc-a", "doc-b"]) is None


async def test_rerank_network_error_returns_none() -> None:
    """网络异常 → None（不抛穿 SSE 流）。"""

    def _boom(_r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    reranker, _ = _reranker_with(_boom)
    assert await reranker.rerank("问题", ["doc-a"]) is None


async def test_noop_reranker_is_explicitly_unavailable() -> None:
    """停用态：available=False 且 rerank=None（显式不可用，不假装可用）。"""
    noop = NoopReranker()
    assert noop.available() is False
    assert await noop.rerank("q", ["d"]) is None


class _Settings:
    def __init__(self, **kw: Any) -> None:
        self.rerank_enabled = True
        self.rerank_api_base = ""
        self.rerank_api_key = ""
        self.rerank_model = DEFAULT_RERANK_MODEL
        self.embedding_api_base = "https://api.siliconflow.cn/v1"
        self.embedding_api_key = ""
        for key, value in kw.items():
            setattr(self, key, value)


def test_make_reranker_switches() -> None:
    """装配开关：无 Key/显式关闭 → Noop；有 Key（含 embedding 回落）→ 硅基流动。"""
    assert isinstance(make_reranker(_Settings()), NoopReranker)
    assert isinstance(make_reranker(_Settings(rerank_enabled=False, rerank_api_key="k")), NoopReranker)
    from_rerank_key = make_reranker(_Settings(rerank_api_key="k"))
    assert isinstance(from_rerank_key, SiliconflowReranker) and from_rerank_key.available()
    from_embedding = make_reranker(_Settings(embedding_api_key="ek"))
    assert isinstance(from_embedding, SiliconflowReranker) and from_embedding.available()
    dedicated = make_reranker(_Settings(rerank_api_base="https://other/v1", rerank_api_key="k", embedding_api_key="ek"))
    assert isinstance(dedicated, SiliconflowReranker)


# ------------------------------------------------------------------ ask 链路（真实 PG + 桩 retrieve）


class _StubReranker:
    """重排桩：记录入参；按固定分数表排序（末位分最高）或失败返回 None。"""

    name = "stub"

    def __init__(self, *, fail: bool = False, ascending: bool = True) -> None:
        self._fail = fail
        self._ascending = ascending
        self.calls: list[tuple[str, list[str]]] = []

    def available(self) -> bool:
        return True

    async def rerank(self, query: str, documents: list[str]) -> list[float] | None:
        self.calls.append((query, list(documents)))
        if self._fail:
            return None
        n = len(documents)
        if self._ascending:
            return [0.1 * (i + 1) for i in range(n)]
        return [1.0 - 0.1 * i for i in range(n)]


def _client(db_session: Any, stub: Any, user_id: str, reranker: Any) -> TestClient:
    from app.api.v1 import chat as chat_module

    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_langbot_client] = lambda: stub
    app.dependency_overrides[get_reranker] = lambda: reranker
    chat_module._llm_http_factory = lambda: httpx.AsyncClient(transport=_llm_echo_transport())
    return TestClient(app)


async def _seed_six(db_session: Any, sub: str, name: str) -> tuple[str, str, str]:
    """1 源 + 6 篇 READY doc（file_id=f-1..f-6，标题=标题6 等反序便于断序）。"""
    from datetime import UTC, datetime, timedelta

    user_id, space_id = await _seed_space(db_session, sub=sub, name=name)
    src = await _seed_source(db_session, f"{sub}-A")
    now = datetime.now(UTC)
    for i in range(1, 7):
        await _seed_doc(
            db_session,
            space_id=space_id,
            source_id=src.id,
            external_id=f"rk-{i}",
            file_id=f"f-{i}",
            published_at=now - timedelta(days=1),
        )
    return user_id, space_id, src.id


async def test_ask_rerank_reorders_and_widens_candidates(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """重排开启：候选宽度 20，citations 按重排序取前 5（末位分最高 → 反序）。"""
    user_id, space_id, _ = await _seed_six(db_session, "sub-rk-1", "重排空间")
    stub = _RecordingLangBot(_results(*[f"f-{i}" for i in range(1, 7)]))
    reranker = _StubReranker()
    client = _client(db_session, stub, user_id, reranker)

    frames = _frames(client.post("/api/v1/chat/ask", json={"spaceId": space_id, "question": "q"}).text)
    assert stub.top_k_seen == [20]
    titles = [c["title"] for c in frames[0]["citations"]]
    assert titles == ["标题rk-6", "标题rk-5", "标题rk-4", "标题rk-3", "标题rk-2"]
    assert len(reranker.calls) == 1 and len(reranker.calls[0][1]) == 6
    assert frames[-1]["type"] == "done"


async def test_ask_rerank_failure_falls_back_to_original_order(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """重排失败（None）：保序截断前 5，链路不中断。"""
    user_id, space_id, _ = await _seed_six(db_session, "sub-rk-2", "重排失败空间")
    stub = _RecordingLangBot(_results(*[f"f-{i}" for i in range(1, 7)]))
    client = _client(db_session, stub, user_id, _StubReranker(fail=True))

    frames = _frames(client.post("/api/v1/chat/ask", json={"spaceId": space_id, "question": "q"}).text)
    assert [c["title"] for c in frames[0]["citations"]] == [
        "标题rk-1",
        "标题rk-2",
        "标题rk-3",
        "标题rk-4",
        "标题rk-5",
    ]
    assert frames[-1]["type"] == "done"


async def test_ask_without_reranker_truncates_in_original_order(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """重排停用（Noop）：候选宽度仍 20（B25 起缺省恒收窄），按原序截断前 5。"""
    user_id, space_id, _ = await _seed_six(db_session, "sub-rk-3", "重排停用空间")
    stub = _RecordingLangBot(_results(*[f"f-{i}" for i in range(1, 7)]))
    client = _client(db_session, stub, user_id, NoopReranker())

    frames = _frames(client.post("/api/v1/chat/ask", json={"spaceId": space_id, "question": "q"}).text)
    # top_k=5 的旧默认仅当调用方显式放弃收窄（allowed_file_ids=None）时才出现
    assert stub.top_k_seen == [20]
    titles = [c["title"] for c in frames[0]["citations"]]
    assert titles == ["标题rk-1", "标题rk-2", "标题rk-3", "标题rk-4", "标题rk-5"]


async def test_ask_filter_then_rerank_composes(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """3.1.1 × 3.2 组合：过滤收窄到 3 篇 → 重排在其上排序取前 3（宽度仍 20）。"""
    from datetime import UTC, datetime, timedelta

    user_id, space_id = await _seed_space(db_session, sub="sub-rk-4", name="组合空间")
    src = await _seed_source(db_session, "sub-rk-4-A")
    now = datetime.now(UTC)
    for i in range(1, 4):
        await _seed_doc(
            db_session,
            space_id=space_id,
            source_id=src.id,
            external_id=f"rk-{i}",
            file_id=f"f-{i}",
            published_at=now - timedelta(days=1),
        )
    stub = _RecordingLangBot(_results("f-1", "f-2", "f-3"))
    reranker = _StubReranker()
    client = _client(db_session, stub, user_id, reranker)

    frames = _frames(
        client.post(
            "/api/v1/chat/ask",
            json={"spaceId": space_id, "question": "q", "filters": {"sourceIds": [src.id], "days": 7}},
        ).text
    )
    assert stub.top_k_seen == [20]
    assert [c["title"] for c in frames[0]["citations"]] == ["标题rk-3", "标题rk-2", "标题rk-1"]
    assert len(reranker.calls[0][1]) == 3  # 重排只看到过滤后的候选
