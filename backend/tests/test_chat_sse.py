"""B-T9 验收测试：问答端点 + SSE（契约 v0.4）。

- 桩轮（零真实网络）：meta/delta/done/error 四帧结构、ping、断连、
  流前信封（10001/10005/30004）；
- 真实轮（连库标记）：真实 LangBot retrieve → 帧流冒烟（:5300 不可达自动 skip）。
"""

from __future__ import annotations

import json
import socket
import sys
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from conftest import PG_URL
from fastapi.testclient import TestClient
from test_repositories import _make_user

from app.api.deps import get_current_user_id, get_db, get_langbot_client
from app.core.errors import DependencyUnavailableError, ResourceNotFoundError
from app.main import create_app
from app.models.entities import KnowledgeSpace
from app.models.entities import User as UserEntity
from app.providers.langbot.client import LangBotClient
from app.repositories.user import SqlAlchemyUserStore


@pytest.fixture(autouse=True)
def _restore_llm_factory():
    """_client 助手直接赋值换 LLM 桩（非 monkeypatch）：每用例后强制恢复，防残留污染真实冒烟。"""
    from app.api.v1 import chat as chat_module

    original = chat_module._llm_http_factory
    yield
    chat_module._llm_http_factory = original


# ------------------------------------------------------------------ 桩


class _StubLangBot(LangBotClient):
    """retrieve 桩：返回 v4.10.9 实测形状（content 为块列表）。"""

    def __init__(self, results: list[dict[str, Any]] | None = None, fail: bool = False) -> None:
        super().__init__("http://langbot.stub", "a", "b")
        self._results = (
            results
            if results is not None
            else [
                {
                    "content": [{"text": "麻籽是核心货币。抓鸟→驯养→进化是主循环。", "file_name": "v1/x/养成循环.md"}],
                    "score": 0.92,
                },
                {
                    "content": [{"text": "第二段落：星辉用于高级兑换。", "file_name": "v1/x/经济系统.md"}],
                    "score": 0.81,
                },
            ]
        )
        self._fail = fail

    async def retrieve(
        self, kb_uuid: str, query: str, top_k: int = 5, search_type: str = "vector"
    ) -> list[dict[str, Any]]:
        if self._fail:
            raise httpx.ConnectError("boom")
        return self._results


def _frames(text: str) -> list[dict[str, Any]]:
    """SSE 文本 → 帧列表（每帧 data: <单行JSON>）。"""
    frames = []
    for block in text.split("\n\n"):
        block = block.strip()
        if block.startswith("data: "):
            frames.append(json.loads(block[len("data: ") :]))
    return frames


def _llm_echo_transport() -> httpx.MockTransport:
    """LLM 桩：回显 prompt 中的引用块与问题（存量 delta 断言不回退）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        body = _json.loads(request.content)
        user_msg = next(m["content"] for m in body["messages"] if m["role"] == "user")
        chunks = [user_msg[i : i + 32] for i in range(0, len(user_msg), 32)]
        payload = "".join(
            f'data: {{"choices":[{{"delta":{{"content":{_json.dumps(c, ensure_ascii=False)}}}}}]}}\n\n' for c in chunks
        )
        return httpx.Response(200, text=payload + "data: [DONE]\n\n")

    return httpx.MockTransport(handler)


def _client(
    db_session,
    stub: LangBotClient,
    user_id: str,
    llm_transport: httpx.MockTransport | None = None,
) -> TestClient:
    from app.api.v1 import chat as chat_module

    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_langbot_client] = lambda: stub
    transport = llm_transport or _llm_echo_transport()
    chat_module._llm_http_factory = lambda: httpx.AsyncClient(transport=transport)
    return TestClient(app)


async def _seed_ready_doc(db_session, space_id: str, file_id: str, title: str | None = None) -> None:
    """种一条 READY 且已入库的 doc（B25 起 ask 恒收窄到本空间 READY doc）。

    未种的 file_id 必被候选集裁掉（孤儿隔离）；桩返回的 file_name 必须与之一致，
    否则引用为空、链路提前落到 error 30002。
    """
    from app.models.entities import Source
    from app.repositories.asset import AssetRepository, DocumentRepository

    source = Source(type="wechat_oa", external_id=f"src-{file_id}", name="测试公众号")
    db_session.add(source)
    await db_session.flush()
    asset = await AssetRepository(db_session).create(
        source_id=source.id,
        external_id=file_id,
        url=f"https://mp.weixin.qq.com/s/{file_id}",
        title=title or file_id.rsplit("/", 1)[-1].rsplit(".", 1)[0],
        content_markdown="正文",
        content_hash=f"hash-{file_id}",
    )
    doc = await DocumentRepository(db_session).create(asset_id=asset.id, space_id=space_id)
    await DocumentRepository(db_session).set_langbot_file_id(doc.id, file_id)
    await DocumentRepository(db_session).set_status(doc.id, "READY")


async def test_ask_full_stream_meta_delta_done(db_session) -> None:  # type: ignore[no-untyped-def]
    """正常链：meta（引用先行）→ delta ×N → done（messageId）。"""
    from app.repositories.space import SpaceRepository

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="问答空间", langbot_kb_uuid="kb-1")
    await _seed_ready_doc(db_session, space.id, "v1/x/养成循环.md")
    await _seed_ready_doc(db_session, space.id, "v1/x/经济系统.md")
    client = _client(db_session, _StubLangBot(), user.id)
    resp = client.post("/api/v1/chat/ask", json={"spaceId": space.id, "question": "麻籽怎么用？"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    frames = _frames(resp.text)
    assert [f["type"] for f in frames][0] == "meta"
    assert [f["type"] for f in frames][-1] == "done"
    assert all(f["type"] in ("meta", "delta", "done") for f in frames)
    meta = frames[0]
    # AB-P004 P4：citations 三元 {title, spaceName, engine}（ADR-0004）
    assert set(meta["citations"][0].keys()) == {"title", "spaceName", "engine"}
    assert meta["citations"][0]["spaceName"] == "问答空间"
    assert meta["citations"][0]["title"] == "养成循环"  # file_name 尾段
    assert meta["citations"][0]["engine"] in ("builtin", "")  # 空间 engine 默认 builtin
    deltas = "".join(f["content"] for f in frames if f["type"] == "delta")
    assert "麻籽是核心货币" in deltas and "星辉" in deltas  # 两块均流出
    assert len(frames[-1]["messageId"]) == 36


async def test_ask_ping_covers_retrieve_blocking(db_session, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """B-T10 任务2：ping 心跳覆盖 retrieve 阻塞期（否则长检索期前端判死）。

    慢桩 0.5s 返回、间隔 patch 至 0.1s → meta 帧之前必须已出现 ping 帧。
    """
    import asyncio

    from app.api.v1 import chat as chat_module
    from app.repositories.space import SpaceRepository

    class _SlowStub(_StubLangBot):
        async def retrieve(
            self, kb_uuid: str, query: str, top_k: int = 5, search_type: str = "vector"
        ) -> list[dict[str, Any]]:
            await asyncio.sleep(0.5)
            return await super().retrieve(kb_uuid, query, top_k, search_type)

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="慢检索空间", langbot_kb_uuid="kb-1")
    monkeypatch.setattr(chat_module, "PING_INTERVAL_SECONDS", 0.1)
    client = _client(db_session, _SlowStub(), user.id)
    resp = client.post("/api/v1/chat/ask", json={"spaceId": space.id, "question": "q"})
    frames = _frames(resp.text)
    types = [f["type"] for f in frames]
    assert "ping" in types, f"retrieve 阻塞期无心跳帧: {types}"
    assert types.index("ping") < types.index("meta"), "ping 应出现在 meta 之前（阻塞期内）"


async def test_ask_citation_title_prefers_local_doc(db_session) -> None:  # type: ignore[no-untyped-def]
    """B-T10 任务4：citation title 优先取本地 doc.title，替代 hash 文件名尾段。"""
    from test_repositories import _make_source

    from app.repositories.asset import AssetRepository, DocumentRepository
    from app.repositories.space import SpaceRepository

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="引用空间", langbot_kb_uuid="kb-1")
    source = await _make_source(db_session)
    asset = await AssetRepository(db_session).create(
        source_id=source.id,
        external_id="art-1",
        url="https://mp.weixin.qq.com/s/art1",
        title="真实文章标题",
        content_markdown="正文",
        content_hash="h1",
    )
    doc = await DocumentRepository(db_session).create(asset_id=asset.id, space_id=space.id)
    await DocumentRepository(db_session).set_langbot_file_id(doc.id, "v1/x/养成循环.md")
    await DocumentRepository(db_session).set_status(doc.id, "READY")
    await _seed_ready_doc(db_session, space.id, "v1/x/经济系统.md")

    client = _client(db_session, _StubLangBot(), user.id)
    resp = client.post("/api/v1/chat/ask", json={"spaceId": space.id, "question": "q"})
    meta = _frames(resp.text)[0]
    assert meta["type"] == "meta"
    titles = [c["title"] for c in meta["citations"]]
    assert "真实文章标题" in titles, f"citation title 未接本地 doc.title: {titles}"
    # 无本地映射的第二块回退文件名尾段
    assert "经济系统" in titles


async def test_ask_citations_dedup_multi_chunk_hits(db_session) -> None:  # type: ignore[no-untyped-def]
    """同一文档的多 chunk 命中去重：引用不重复列同一篇。

    实测缺陷（2026-09-25）：单篇知识库提问时 top_k 个命中全来自同一篇，
    UI 渲染出 4 条完全相同的「来源文章」。此处同时用 LangBot 2.x 的真实形状
    （content 为块列表、只有 distance 无 score）验证无 score 时的保序截断。
    """
    from app.repositories.space import SpaceRepository

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="去重空间", langbot_kb_uuid="kb-1")
    same_doc = "v1/x/同一篇.md"
    hits = [{"content": [{"text": f"第 {i} 块正文。", "file_name": same_doc}], "distance": i * 0.05} for i in range(4)]
    await _seed_ready_doc(db_session, space.id, same_doc)
    client = _client(db_session, _StubLangBot(hits), user.id)
    meta = _frames(client.post("/api/v1/chat/ask", json={"spaceId": space.id, "question": "q"}).text)[0]
    assert [c["title"] for c in meta["citations"]] == ["同一篇"]
    assert meta["citations"][0]["spaceName"] == "去重空间"


class _RaisingStub(LangBotClient):
    """与真实 LangBotClient 同形状的桩：retrieve 直接抛预包装 AppError。"""

    def __init__(self, exc: Exception) -> None:
        super().__init__("http://langbot.stub", "a", "b")
        self._exc = exc

    async def retrieve(
        self, kb_uuid: str, query: str, top_k: int = 5, search_type: str = "vector"
    ) -> list[dict[str, Any]]:
        raise self._exc


async def test_ask_stream_error_frame_dependency_unavailable(db_session) -> None:  # type: ignore[no-untyped-def]
    """真实形状①：client 预包装 DependencyUnavailableError(50002) → 流中 error 帧关流。

    回归背景（B-T9R P1）：真实 client._request 将 httpx.HTTPError 归一为 50002 抛出，
    旧捕获面（LangbotApiError/httpx.HTTPError）接不住 → 裸逃逸 200 空体零帧断流。
    """
    from app.repositories.space import SpaceRepository

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="宕机空间", langbot_kb_uuid="kb-1")
    client = _client(db_session, _RaisingStub(DependencyUnavailableError("LangBot 不可达")), user.id)
    resp = client.post("/api/v1/chat/ask", json={"spaceId": space.id, "question": "q"})
    frames = _frames(resp.text)
    assert frames[-1]["type"] == "error" and frames[-1]["code"] == 50002
    assert not any(f["type"] == "done" for f in frames)


async def test_ask_stream_error_frame_resource_not_found(db_session) -> None:  # type: ignore[no-untyped-def]
    """真实形状②：client 预包装 ResourceNotFoundError(30004) → 流中 error 帧关流。

    回归背景（B-T9R P1）：LangBot 404 被 client._request 归一为 30004，同属裸逃逸面。
    """
    from app.repositories.space import SpaceRepository

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="资源缺失空间", langbot_kb_uuid="kb-1")
    client = _client(db_session, _RaisingStub(ResourceNotFoundError("LangBot 资源不存在")), user.id)
    resp = client.post("/api/v1/chat/ask", json={"spaceId": space.id, "question": "q"})
    frames = _frames(resp.text)
    assert frames[-1]["type"] == "error" and frames[-1]["code"] == 30004
    assert not any(f["type"] == "done" for f in frames)


async def test_ask_langbot_down_error_frame_50002(db_session) -> None:  # type: ignore[no-untyped-def]
    """真实形状（B-T8R 口径校准）：retrieve 抛预包装 DependencyUnavailableError → 50002 帧。"""
    from app.repositories.space import SpaceRepository

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="宕机空间", langbot_kb_uuid="kb-1")
    client = _client(db_session, _RaisingStub(DependencyUnavailableError("LangBot 不可达")), user.id)
    resp = client.post("/api/v1/chat/ask", json={"spaceId": space.id, "question": "q"})
    frames = _frames(resp.text)
    assert frames[-1]["type"] == "error" and frames[-1]["code"] == 50002


async def test_ask_langbot_raw_httpx_error_frame_50002(db_session) -> None:  # type: ignore[no-untyped-def]
    """裸 httpx 兜底分支守护（防桩再次掩盖）：直抛 ConnectError → error 帧 50002。"""
    from app.repositories.space import SpaceRepository

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="裸错空间", langbot_kb_uuid="kb-1")
    client = _client(db_session, _StubLangBot(fail=True), user.id)
    resp = client.post("/api/v1/chat/ask", json={"spaceId": space.id, "question": "q"})
    frames = _frames(resp.text)
    assert frames[-1]["type"] == "error" and frames[-1]["code"] == 50002


async def test_ask_error_frame_30002_via_real_shape_stub(db_session) -> None:  # type: ignore[no-untyped-def]
    """B-T10 任务3：'触发错误'测试缝摘除后，30002 error 帧走真实形状桩（LangbotApiError）。"""
    from app.core.errors import LangbotApiError
    from app.repositories.space import SpaceRepository

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="错误空间", langbot_kb_uuid="kb-1")
    client = _client(db_session, _RaisingStub(LangbotApiError("LangBot 检索或生成异常")), user.id)
    resp = client.post("/api/v1/chat/ask", json={"spaceId": space.id, "question": "普通问题"})
    frames = _frames(resp.text)
    # 检索期失败发生在 meta 之前（citations 依赖 retrieve 产物）→ 单 error 帧关流，无 done
    types = [f["type"] for f in frames]
    assert types == ["error"]
    assert frames[0]["code"] == 30002
    assert "message" in frames[0]


async def test_ask_pre_stream_envelopes(db_session) -> None:  # type: ignore[no-untyped-def]
    """流前错误走 JSON 信封：10005 空问题；30004 他人空间/无效 id。"""
    from app.repositories.space import SpaceRepository

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="信封空间", langbot_kb_uuid="kb-1")
    client = _client(db_session, _StubLangBot(), user.id)

    resp = client.post("/api/v1/chat/ask", json={"spaceId": space.id, "question": "  "})
    assert resp.status_code == 422 and resp.json()["code"] == 10005

    resp = client.post("/api/v1/chat/ask", json={"spaceId": "no-such", "question": "q"})
    assert resp.status_code == 404 and resp.json()["code"] == 30004
    # 契约 v0.4a（A 打回项）：30004 message 必须是可读文案，禁止裸 id 回填
    msg = resp.json()["message"]
    assert "不存在" in msg or "无权限" in msg, f"30004 message 非可读文案: {msg}"
    assert msg != "no-such", "30004 message 仍是裸 id"

    # 越权：他人空间（真实第二用户行，FK 约束）
    other_user = await SqlAlchemyUserStore(db_session).upsert_by_sub("sub-other-chat", "other@test.local", "他人")
    other = await SpaceRepository(db_session).create(user_id=other_user.id, name="他人空间")
    resp = client.post("/api/v1/chat/ask", json={"spaceId": other.id, "question": "q"})
    assert resp.status_code == 404 and resp.json()["code"] == 30004
    msg = resp.json()["message"]
    assert "不存在" in msg or "无权限" in msg, f"30004 message 非可读文案: {msg}"
    assert msg != other.id, "30004 message 仍是裸 id"


def test_ask_unauthenticated_10001() -> None:
    """登录保护：未登录 → 10001 信封（不走流）。"""
    client = TestClient(create_app())
    resp = client.post("/api/v1/chat/ask", json={"spaceId": "x", "question": "q"})
    assert resp.status_code == 401 and resp.json()["code"] == 10001


async def test_ask_empty_kb_30002(db_session) -> None:  # type: ignore[no-untyped-def]
    """流前错误：空间未 ingest（langbot_kb_uuid 空）→ 30002 信封（不走流）。"""
    from app.repositories.space import SpaceRepository

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="空库空间")
    client = _client(db_session, _StubLangBot(), user.id)
    resp = client.post("/api/v1/chat/ask", json={"spaceId": space.id, "question": "q"})
    assert resp.status_code == 502 and resp.json()["code"] == 30002


# ------------------------------------------------------------------ B-T10R 任务1：真实 LLM 流（TDD）


def _llm_sse_transport(
    chunks: list[str],
    status: int = 200,
    first_delay: float = 0.0,
    stall_after_first: bool = False,
    raw_lines: list[str] | None = None,
    mid_error: bool = False,
) -> httpx.MockTransport:
    """OpenAI 兼容 SSE 上游桩：chunk 回放 + 首块延迟/首块后停摆/原样行/流中错误可控。"""

    async def handler(request: httpx.Request) -> httpx.Response:
        import asyncio
        import json as _json

        if status >= 400:
            return httpx.Response(status, json={"error": {"message": "upstream rejected"}})

        async def body() -> Any:
            # 延迟注入响应体首块（头立即返回）：first-token 超时计时段在流读取期
            if first_delay:
                await asyncio.sleep(first_delay)
            if raw_lines is not None:
                for ln in raw_lines:
                    yield ln.encode()
                return
            for c in chunks:
                frame = f'data: {{"choices":[{{"delta":{{"content":{_json.dumps(c, ensure_ascii=False)}}}}}]}}\n\n'
                yield frame.encode()
                if stall_after_first:
                    await asyncio.sleep(999)  # 首块后停摆（空闲判死用例；999s 内必然被超时/取消）
            if mid_error:
                raise httpx.ReadError("mid-stream failure")
            yield b"data: [DONE]\n\n"

        return httpx.Response(200, content=body())

    return httpx.MockTransport(handler)


async def test_ask_llm_stream_passthrough(db_session, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """任务1-核心：上游 chunk → delta 帧一一对应（非占位拼装）。"""
    from app.api.v1 import chat as chat_module
    from app.repositories.space import SpaceRepository

    chunks = ["麻籽的秘密数字是 ", "42", "。"]
    monkeypatch.setattr(
        chat_module, "_llm_http_factory", lambda: httpx.AsyncClient(transport=_llm_sse_transport(chunks))
    )
    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="LLM流空间", langbot_kb_uuid="kb-1")
    await _seed_ready_doc(db_session, space.id, "v1/x/养成循环.md")
    client = _client(db_session, _StubLangBot(), user.id, llm_transport=_llm_sse_transport(chunks))
    resp = client.post("/api/v1/chat/ask", json={"spaceId": space.id, "question": "秘密数字"})
    frames = _frames(resp.text)
    deltas = [f["content"] for f in frames if f["type"] == "delta"]
    assert deltas == chunks, f"chunk→delta 未一一对应: {deltas}"
    assert frames[-1]["type"] == "done"


async def test_ask_llm_first_token_timeout_50002(db_session, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """首 token 超时 → error 帧 50002 关流（批复 PLAN 语义）。"""
    from app.api.v1 import chat as chat_module
    from app.repositories.space import SpaceRepository

    monkeypatch.setattr(chat_module, "LLM_FIRST_TOKEN_TIMEOUT", 0.1)
    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(transport=_llm_sse_transport(["晚到"], first_delay=0.5)),
    )
    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="首token超时空间", langbot_kb_uuid="kb-1")
    await _seed_ready_doc(db_session, space.id, "v1/x/养成循环.md")
    client = _client(db_session, _StubLangBot(), user.id, llm_transport=_llm_sse_transport(["晚到"], first_delay=0.5))
    resp = client.post("/api/v1/chat/ask", json={"spaceId": space.id, "question": "q"})
    frames = _frames(resp.text)
    assert frames[-1]["type"] == "error" and frames[-1]["code"] == 50002
    assert not any(f["type"] == "delta" for f in frames)


async def test_ask_llm_upstream_4xx_30002(db_session) -> None:  # type: ignore[no-untyped-def]
    """上游 4xx → error 帧 30002 关流（批复 PLAN 语义，零新码位）。

    须种候选 doc：空候选也走 30002，不种会让本用例变成恒真断言。
    """
    from app.repositories.space import SpaceRepository

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="上游4xx空间", langbot_kb_uuid="kb-1")
    await _seed_ready_doc(db_session, space.id, "v1/x/养成循环.md")
    client = _client(db_session, _StubLangBot(), user.id, llm_transport=_llm_sse_transport([], status=401))
    resp = client.post("/api/v1/chat/ask", json={"spaceId": space.id, "question": "q"})
    frames = _frames(resp.text)
    assert frames[-1]["type"] == "error" and frames[-1]["code"] == 30002


async def test_ask_llm_disconnect_aborts_upstream(db_session, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """断连即中止上游（不烧 token）：进入 LLM 流后立即断开 → 零 delta、上游仅一次请求。

    B-T10 终版适配：检索期新增断连检查（首次 is_disconnected=False 放行 retrieve，
    进入 LLM 后第二次 True 触发中止）——检索期断开的行为由
    test_event_stream_disconnect_cancels_retrieve 单独覆盖。
    """
    from fastapi import Request as FastapiRequest

    from app.api.v1 import chat as chat_module
    from app.repositories.space import SpaceRepository

    calls = {"n": 0}
    flags = [False, True]

    def counting_handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"x"}}]}\n\ndata: [DONE]\n\n')

    async def _disconnect_after_retrieve(self) -> bool:  # type: ignore[no-untyped-def]
        return flags.pop(0) if flags else True

    monkeypatch.setattr(FastapiRequest, "is_disconnected", _disconnect_after_retrieve)
    monkeypatch.setattr(
        chat_module, "_llm_http_factory", lambda: httpx.AsyncClient(transport=httpx.MockTransport(counting_handler))
    )
    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="断连空间", langbot_kb_uuid="kb-1")
    await _seed_ready_doc(db_session, space.id, "v1/x/养成循环.md")
    client = _client(db_session, _StubLangBot(), user.id, llm_transport=httpx.MockTransport(counting_handler))
    resp = client.post("/api/v1/chat/ask", json={"spaceId": space.id, "question": "q"})
    frames = _frames(resp.text)
    assert not any(f["type"] == "delta" for f in frames)
    assert calls["n"] == 1  # 上游仅一次请求（中止后不再消费/重连）


# ------------------------------------------------------------------ B-T10R 补强：资源生命周期


def _track_llm_tasks(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """追踪生成器创建的 pending 读取任务（经模块级 _ensure_future 注入点）。"""
    from app.api.v1 import chat as chat_module

    created: list[Any] = []
    real_ef = chat_module._ensure_future

    def tracking(coro: Any) -> Any:
        t = real_ef(coro)
        created.append(t)
        return t

    monkeypatch.setattr(chat_module, "_ensure_future", tracking)
    return created


def _stub_settings(monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> None:
    """替换 chat 模块内 get_settings 为受控桩（LLM Key 优先级用例）。"""
    from types import SimpleNamespace

    from app.api.v1 import chat as chat_module

    base = {
        "llm_api_base": "http://llm.stub/v1",
        "llm_model": "stub-model",
        "llm_api_key": "llm-key-explicit",
        "embedding_api_key": "emb-key-other",
    }
    base.update(overrides)
    monkeypatch.setattr(chat_module, "get_settings", lambda: SimpleNamespace(**base))


async def _consume(gen: Any) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    async for item in gen:
        out.append(item)
    return out


async def test_llm_first_token_timeout_cleans_pending(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """首 token 超时：pending 读取任务被 cancel+await 清理，无存活任务。"""
    import asyncio

    from app.api.v1 import chat as chat_module
    from app.core.errors import DependencyUnavailableError

    created = _track_llm_tasks(monkeypatch)
    monkeypatch.setattr(chat_module, "LLM_FIRST_TOKEN_TIMEOUT", 0.1)
    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(transport=_llm_sse_transport(["晚到"], first_delay=0.5)),
    )
    gen = chat_module._llm_stream_delta("q", [{"content": [{"text": "上下文"}]}])
    with pytest.raises(DependencyUnavailableError):
        await _consume(gen)
    await asyncio.sleep(0.05)
    assert created and all(t.done() for t in created), "首 token 超时后仍有存活读取任务"


async def test_llm_idle_timeout_cleans_pending(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """连续空闲判死：首块后停摆 → 2 ping 后 50002；pending 被清理。"""
    import asyncio

    from app.api.v1 import chat as chat_module
    from app.core.errors import DependencyUnavailableError

    created = _track_llm_tasks(monkeypatch)
    monkeypatch.setattr(chat_module, "LLM_FIRST_TOKEN_TIMEOUT", 1.0)
    monkeypatch.setattr(chat_module, "LLM_STREAM_IDLE_TIMEOUT", 0.1)
    monkeypatch.setattr(chat_module, "LLM_MAX_CONSECUTIVE_IDLE", 2)
    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(transport=_llm_sse_transport(["首块"], stall_after_first=True)),
    )
    gen = chat_module._llm_stream_delta("q", [{"content": [{"text": "上下文"}]}])
    items: list[tuple[str, str]] = []
    with pytest.raises(DependencyUnavailableError):
        async for item in gen:
            items.append(item)
    kinds = [k for k, _ in items]
    # 连读 2 次判死语义：第 1 次空闲超时发 ping，第 2 次判死（50002）
    assert kinds == ["delta", "ping"], f"空闲判死帧序异常: {kinds}"
    await asyncio.sleep(0.05)
    assert all(t.done() for t in created), "空闲判死后仍有存活读取任务"


async def test_llm_disconnect_stops_upstream_no_delta_after(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """断连后上游流停止：恰 1 delta 后终止，断开后零新增 delta，无存活任务。"""
    import asyncio

    from app.api.v1 import chat as chat_module

    created = _track_llm_tasks(monkeypatch)
    flags = iter([False, True])

    async def disconnect() -> bool:
        return next(flags)

    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(transport=_llm_sse_transport(["一", "二", "三"])),
    )
    items = await _consume(chat_module._llm_stream_delta("q", [{"content": [{"text": "上下文"}]}], disconnect))
    deltas = [c for k, c in items if k == "delta"]
    assert deltas == ["一"], f"断开后仍继续产出: {deltas}"
    await asyncio.sleep(0.05)
    assert all(t.done() for t in created)


async def test_llm_malformed_json_cleans_pending(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """JSON 解析异常退出路径：异常外抛且 pending 已清理（无未处理 task exception）。"""
    import asyncio

    from app.api.v1 import chat as chat_module

    created = _track_llm_tasks(monkeypatch)
    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(
            transport=_llm_sse_transport([], raw_lines=["data: {bad json\n", "data: [DONE]\n\n"])
        ),
    )
    with pytest.raises(ValueError):  # json.JSONDecodeError
        await _consume(chat_module._llm_stream_delta("q", [{"content": [{"text": "上下文"}]}]))
    await asyncio.sleep(0.05)
    assert all(t.done() for t in created)


async def test_llm_mid_stream_read_error_cleans_pending(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """流中上游 ReadError：异常外抛且 pending 已清理。"""
    import asyncio

    from app.api.v1 import chat as chat_module

    created = _track_llm_tasks(monkeypatch)
    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(transport=_llm_sse_transport(["块1", "块2"], mid_error=True)),
    )
    with pytest.raises(httpx.ReadError):
        await _consume(chat_module._llm_stream_delta("q", [{"content": [{"text": "上下文"}]}]))
    await asyncio.sleep(0.05)
    assert all(t.done() for t in created)


async def test_llm_normal_done_cleans_pending(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """[DONE] 正常结束：零残留任务（finally 对 pending=None 为 no-op）。"""
    import asyncio

    from app.api.v1 import chat as chat_module

    created = _track_llm_tasks(monkeypatch)
    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(transport=_llm_sse_transport(["a", "b"])),
    )
    items = await _consume(chat_module._llm_stream_delta("q", [{"content": [{"text": "上下文"}]}]))
    assert [k for k, _ in items] == ["delta", "delta"]
    await asyncio.sleep(0.05)
    assert all(t.done() for t in created)


async def test_llm_explicit_api_key_precedence(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """显式 LLM_API_KEY 优先：Authorization 用 llm_api_key，不依赖 EMBEDDING_API_KEY。"""
    from app.api.v1 import chat as chat_module

    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n')

    _stub_settings(monkeypatch)  # llm_api_key=llm-key-explicit / embedding_api_key=emb-key-other
    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    items = await _consume(chat_module._llm_stream_delta("q", [{"content": [{"text": "上下文"}]}]))
    assert any(c == "ok" for _, c in items)
    assert captured["auth"] == "Bearer llm-key-explicit"


# ------------------------------------------------------------ B-T10 终版：外层取消 + retrieve + 帧序
# 全部直接驱动生成器（零 PG 依赖）：request/space 桩化、_local_title_map 换桩，
# 连库环境（PG 不可达）下仍可全量实测生命周期与帧序契约。


def _track_create_task(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """追踪 _event_stream 创建的 retrieve 任务（经模块级 _create_task 注入点）。"""
    from app.api.v1 import chat as chat_module

    created: list[Any] = []
    real_ct = chat_module._create_task

    def tracking(coro: Any) -> Any:
        t = real_ct(coro)
        created.append(t)
        return t

    monkeypatch.setattr(chat_module, "_create_task", tracking)
    return created


async def _noop_title_map(session: Any, space_id: str, file_ids: list[str]) -> dict[str, str]:
    """_local_title_map 桩：不触碰 session（直接驱动 _event_stream 时 session 传 None）。"""
    return {}


def _stub_request(disconnect: Any = None) -> Any:
    """_event_stream 的 Request 桩：is_disconnected 可控（默认恒 False）。"""

    async def _never() -> bool:
        return False

    return SimpleNamespace(is_disconnected=disconnect or _never)


_SPACE_STUB = SimpleNamespace(id="sp-1", name="桩空间")


async def _consume_frames(gen: Any) -> list[dict[str, Any]]:
    """驱动 _event_stream 生成器 → 解析完整响应帧（与 _frames 同解析口径）。"""
    frames = []
    async for raw in gen:
        block = raw.strip()
        if block.startswith("data: "):
            frames.append(json.loads(block[len("data: ") :]))
    return frames


async def _drive_event_stream(langbot: Any, disconnect: Any = None) -> list[dict[str, Any]]:
    """桩化调用 _event_stream（Request/space/session 全桩，session=None + title map 换桩）。

    集中收口桩调用（mypy 对桩参数类型豁免在此一处）。
    """
    from app.api.v1 import chat as chat_module

    gen = chat_module._event_stream(
        _stub_request(disconnect),
        langbot,
        "kb-1",
        "q",
        _SPACE_STUB,
        None,  # type: ignore[arg-type]
    )
    return await _consume_frames(gen)


async def test_llm_outer_close_cleans_pending(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """B-8 测试7：外层取消（驱动任务 cancel）→ pending 清理，无存活任务（response 随之退出）。

    aclose() 不能在生成器被其他任务驱动挂起时调用（asyncio 报 already running）；
    取消驱动任务等价于取消生成器——CancelledError 注入 await 点 → finally 清理路径。
    """
    import asyncio

    from app.api.v1 import chat as chat_module

    created = _track_llm_tasks(monkeypatch)
    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(transport=_llm_sse_transport(["首块"], stall_after_first=True)),
    )
    gen = chat_module._llm_stream_delta("q", [{"content": [{"text": "上下文"}]}])
    it = gen.__aiter__()
    first = await it.__anext__()
    assert first == ("delta", "首块")
    # 生成器继续读取时上游停摆 → pending 挂起；此时取消驱动任务（外层取消语义）
    reader = asyncio.ensure_future(it.__anext__())
    await asyncio.sleep(0.05)
    reader.cancel()
    try:
        await reader
    except asyncio.CancelledError:
        pass
    await asyncio.sleep(0.05)
    assert created and all(t.done() for t in created), "取消后仍有存活读取任务"


async def test_llm_single_idle_recovers(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """B-8 测试2：单次空闲发 ping 后上游恢复 → delta 继续、pending 复用无残留。

    用 asyncio.Event 门控上游第二块（消除 sleep 时序窄窗口）：
    第二次 anext 驱动生成器 → wait_for 0.1s 超时 → ping；放行 gate 后第三次
    anext 立即拿到恢复块（不触发判死）。
    """
    import asyncio
    import json as _json

    from app.api.v1 import chat as chat_module

    created = _track_llm_tasks(monkeypatch)
    monkeypatch.setattr(chat_module, "LLM_FIRST_TOKEN_TIMEOUT", 1.0)
    monkeypatch.setattr(chat_module, "LLM_STREAM_IDLE_TIMEOUT", 0.1)
    monkeypatch.setattr(chat_module, "LLM_MAX_CONSECUTIVE_IDLE", 2)

    gate = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        async def body() -> Any:
            yield f'data: {{"choices":[{{"delta":{{"content":{_json.dumps("首块")}}}}}]}}\n\n'.encode()
            await gate.wait()  # 挂起直至测试放行（模拟一次上游空闲）
            yield f'data: {{"choices":[{{"delta":{{"content":{_json.dumps("恢复块")}}}}}]}}\n\n'.encode()
            yield b"data: [DONE]\n\n"

        return httpx.Response(200, content=body())

    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    gen = chat_module._llm_stream_delta("q", [{"content": [{"text": "上下文"}]}])
    it = gen.__aiter__()
    first = await it.__anext__()
    assert first == ("delta", "首块")
    second = await it.__anext__()  # wait_for 0.1s 超时 → 单次空闲 ping（未判死）
    assert second == ("ping", "")
    gate.set()  # 放行上游第二块
    third = await it.__anext__()
    assert third == ("delta", "恢复块")
    with pytest.raises(StopAsyncIteration):
        await it.__anext__()  # [DONE] → 生成器正常结束
    await asyncio.sleep(0.05)
    assert all(t.done() for t in created), "空闲恢复后仍有存活读取任务"


async def test_event_stream_retrieve_normal_no_residue(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """B-9 测试1：retrieve 正常 → meta 先于 delta、done 收尾；任务 done 无残留。"""
    import asyncio

    from app.api.v1 import chat as chat_module

    tasks = _track_create_task(monkeypatch)
    monkeypatch.setattr(chat_module, "_local_title_map", _noop_title_map)
    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(transport=_llm_echo_transport()),
    )
    frames = await _drive_event_stream(_StubLangBot())
    types = [f["type"] for f in frames]
    assert types[0] == "meta" and types[-1] == "done"
    assert tasks and tasks[0].done() and not tasks[0].cancelled()
    await asyncio.sleep(0.05)
    assert all(t.done() for t in tasks), "retrieve_task 未收敛"


async def test_event_stream_retrieve_blocking_ping_not_cancelled(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """B-9 测试2：retrieve 阻塞 → 检索期 ping 先于 meta；任务未被取消，完成后继续。"""
    import asyncio

    from app.api.v1 import chat as chat_module

    tasks = _track_create_task(monkeypatch)
    monkeypatch.setattr(chat_module, "PING_INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr(chat_module, "_local_title_map", _noop_title_map)
    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(transport=_llm_echo_transport()),
    )

    class _SlowStub(_StubLangBot):
        async def retrieve(
            self, kb_uuid: str, query: str, top_k: int = 5, search_type: str = "vector"
        ) -> list[dict[str, Any]]:
            await asyncio.sleep(0.2)
            return await super().retrieve(kb_uuid, query, top_k, search_type)

    frames = await _drive_event_stream(_SlowStub())
    types = [f["type"] for f in frames]
    assert "ping" in types and types.index("ping") < types.index("meta")
    assert frames[-1]["type"] == "done"
    await asyncio.sleep(0.05)
    assert tasks[0].done() and not tasks[0].cancelled(), "retrieve_task 被错误取消"


async def test_event_stream_retrieve_error_consumed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """B-9 测试3：retrieve 抛 AppError → 单 error 帧、无后续正文；任务异常已消费无残留。"""
    import asyncio

    from app.core.errors import LangbotApiError

    tasks = _track_create_task(monkeypatch)
    frames = await _drive_event_stream(_RaisingStub(LangbotApiError("检索失败")))
    assert [f["type"] for f in frames] == ["error"]
    assert frames[0]["code"] == 30002
    assert tasks and tasks[0].done()
    await asyncio.sleep(0.05)
    assert all(t.done() for t in tasks), "retrieve_task 未收敛"


async def test_event_stream_disconnect_cancels_retrieve(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """B-9 测试4：检索期断开 → retrieve_task 被 cancel+await；零帧；不发起 LLM 请求。"""
    import asyncio

    from app.api.v1 import chat as chat_module

    calls = {"llm": 0}

    def counting_handler(request: httpx.Request) -> httpx.Response:
        calls["llm"] += 1
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"x"}}]}\n\ndata: [DONE]\n\n')

    async def _always_true() -> bool:
        return True

    tasks = _track_create_task(monkeypatch)
    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(counting_handler)),
    )

    class _BlockingStub(_StubLangBot):
        async def retrieve(
            self, kb_uuid: str, query: str, top_k: int = 5, search_type: str = "vector"
        ) -> list[dict[str, Any]]:
            await asyncio.sleep(0.5)
            return await super().retrieve(kb_uuid, query, top_k, search_type)

    frames = await _drive_event_stream(_BlockingStub(), disconnect=_always_true)
    assert frames == [], "断连后不应输出任何帧"
    await asyncio.sleep(0.05)
    assert tasks and tasks[0].cancelled(), "断连后 retrieve_task 未被取消"
    assert calls["llm"] == 0, "断连后仍发起 LLM 请求"


async def test_event_stream_title_map_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """B-9 测试5：title map 抛异常 → error 50001、无 done；retrieve_task 已收敛。"""
    import asyncio

    from app.api.v1 import chat as chat_module

    tasks = _track_create_task(monkeypatch)

    async def _boom(session: Any, space_id: str, file_ids: list[str]) -> dict[str, str]:
        raise RuntimeError("db down")

    monkeypatch.setattr(chat_module, "_local_title_map", _boom)
    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(transport=_llm_echo_transport()),
    )
    frames = await _drive_event_stream(_StubLangBot())
    assert [f["type"] for f in frames] == ["error"]
    assert frames[0]["code"] == 50001
    assert not any(f["type"] == "done" for f in frames)
    await asyncio.sleep(0.05)
    assert tasks[0].done() and not tasks[0].cancelled()


async def test_event_stream_llm_error_retrieve_converged(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """B-9 测试6：LLM 阶段异常 → error 50002、无 done；retrieve_task 已收敛。"""
    import asyncio

    from app.api.v1 import chat as chat_module

    tasks = _track_create_task(monkeypatch)
    monkeypatch.setattr(chat_module, "_local_title_map", _noop_title_map)
    monkeypatch.setattr(chat_module, "LLM_FIRST_TOKEN_TIMEOUT", 0.1)
    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(transport=_llm_sse_transport(["晚到"], first_delay=0.5)),
    )
    frames = await _drive_event_stream(_StubLangBot())
    assert frames[-1]["type"] == "error" and frames[-1]["code"] == 50002
    assert not any(f["type"] == "done" for f in frames)
    await asyncio.sleep(0.05)
    assert all(t.done() for t in tasks), "LLM 异常后 retrieve_task 未收敛"


async def test_event_stream_outer_close_cleans_retrieve(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """B-9 测试7：外层取消驱动任务 → retrieve_task 被 cancel+await，无后台残留。

    生成器被 consumer 驱动挂起在 retrieve 等待时，取消 consumer（CancelledError
    注入生成器）→ finally 收敛路径；aclose 在生成器运行中调用会报 already running。
    """
    import asyncio

    from app.api.v1 import chat as chat_module

    tasks = _track_create_task(monkeypatch)
    monkeypatch.setattr(chat_module, "_local_title_map", _noop_title_map)
    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(transport=_llm_echo_transport()),
    )

    class _SlowStub(_StubLangBot):
        async def retrieve(
            self, kb_uuid: str, query: str, top_k: int = 5, search_type: str = "vector"
        ) -> list[dict[str, Any]]:
            await asyncio.sleep(5)
            return await super().retrieve(kb_uuid, query, top_k, search_type)

    gen: Any = chat_module._event_stream(
        _stub_request(),
        _SlowStub(),
        "kb-1",
        "q",
        _SPACE_STUB,
        None,  # type: ignore[arg-type]
    )
    consumer = asyncio.create_task(gen.asend(None))  # 后台驱动：挂起在 retrieve 等待
    await asyncio.sleep(0.2)
    consumer.cancel()  # 外层取消 → CancelledError 注入生成器 → finally cancel+await retrieve_task
    try:
        await consumer
    except asyncio.CancelledError:
        pass
    await asyncio.sleep(0.05)
    assert tasks and tasks[0].cancelled(), "取消后 retrieve_task 未被取消"


async def test_event_stream_malformed_json_error_frame(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """B-10：malformed JSON 在 endpoint 层归一 error 50001（不裸逃逸、无 done）。"""
    from app.api.v1 import chat as chat_module

    monkeypatch.setattr(chat_module, "_local_title_map", _noop_title_map)
    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(
            transport=_llm_sse_transport([], raw_lines=["data: {bad json\n", "data: [DONE]\n\n"])
        ),
    )
    frames = await _drive_event_stream(_StubLangBot())
    types = [f["type"] for f in frames]
    assert types[0] == "meta" and types[-1] == "error"  # meta 已发（流已开），error 收尾
    assert frames[-1]["code"] == 50001
    assert not any(f["type"] == "done" for f in frames)


async def test_event_stream_read_error_error_frame(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """B-10：流中 ReadError → error 50002、无 done；已发 delta 保留。"""
    from app.api.v1 import chat as chat_module

    monkeypatch.setattr(chat_module, "_local_title_map", _noop_title_map)
    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(transport=_llm_sse_transport(["块1"], mid_error=True)),
    )
    frames = await _drive_event_stream(_StubLangBot())
    types = [f["type"] for f in frames]
    assert types == ["meta", "delta", "error"]  # 已生成内容保留，error 收尾
    assert frames[-1]["code"] == 50002
    assert not any(f["type"] == "done" for f in frames)


async def test_event_stream_delta_then_idle_error_sequence(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """B-10：已发 delta 后连续空闲判死 → 帧序 meta→delta→ping→error(50002)，无 done。"""
    from app.api.v1 import chat as chat_module

    monkeypatch.setattr(chat_module, "_local_title_map", _noop_title_map)
    monkeypatch.setattr(chat_module, "LLM_FIRST_TOKEN_TIMEOUT", 1.0)
    monkeypatch.setattr(chat_module, "LLM_STREAM_IDLE_TIMEOUT", 0.1)
    monkeypatch.setattr(chat_module, "LLM_MAX_CONSECUTIVE_IDLE", 2)
    monkeypatch.setattr(
        chat_module,
        "_llm_http_factory",
        lambda: httpx.AsyncClient(transport=_llm_sse_transport(["首块"], stall_after_first=True)),
    )
    frames = await _drive_event_stream(_StubLangBot())
    types = [f["type"] for f in frames]
    assert types == ["meta", "delta", "ping", "error"]
    assert frames[-1]["code"] == 50002


# ------------------------------------------------------------------ 真实轮（连库标记）


def _langbot_reachable() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 5300), timeout=2):
            return True
    except OSError:
        return False


@pytest.mark.langbot_real
async def test_ask_real_langbot_smoke() -> None:
    """真实 LangBot 冒烟（连库标记）：真实 retrieve → 帧流。

    前置：LangBot :5300 在跑 且 env 提供 LANGBOT_ADMIN_PASSWORD（凭据不入码）。
    空间行不入库——KB uuid 用占位仅测帧协议？不行：retrieve 需真库。
    实测策略：取 LangBot 现存第一个 KB（若有）做 retrieve；无库 → skip。
    """
    import asyncio

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    from app.core.config import get_settings

    s = get_settings()
    if not _langbot_reachable() or not s.langbot_admin_password:
        pytest.skip("LangBot :5300 不可达或未注入管理员凭据，跳过真实冒烟")

    client = LangBotClient(s.langbot_base_url, s.langbot_admin_username, s.langbot_admin_password)
    kb_uuid: str | None = None
    try:
        from app.api.v1.chat import _citations_from, _context_texts

        # 自建临时库（确定性可重复，不依赖 M0 遗留库状态）
        engine_id = ""
        for eng in await client.list_engines():
            pid = eng.get("plugin_id") or eng.get("id")
            if pid:
                engine_id = str(pid)
                break
        models = await client.list_embedding_models()
        emb = ""
        for m in models:
            provider = m.get("provider") or {}
            if provider.get("base_url", "").rstrip("/") == s.embedding_api_base.rstrip("/"):
                emb = str(m.get("uuid"))
                break
        if not emb:  # 硅基流动模型未注册 → 自举注册（与 kb.ensure_embedding_model 同口径）
            if not s.embedding_api_key:
                pytest.skip("无嵌入模型且未注入 EMBEDDING_API_KEY，跳过真实冒烟")
            provider_uuid = await client.register_provider(
                "bothot-embedding", s.embedding_api_base, s.embedding_api_key
            )
            emb = await client.register_embedding_model(s.embedding_model, provider_uuid)
        if not engine_id:
            pytest.skip("LangBot 无知识引擎，跳过真实冒烟")
        kb_uuid = await client.create_kb("b-t9-smoke", engine_id, emb)

        space_like = type("S", (), {"name": "B-T9 冒烟"})()
        # full_text 免查询嵌入（M0 §四），空库返回空 results——帧协议组装仍验证
        results = await client.retrieve(kb_uuid, "冒烟查询", top_k=3, search_type="full_text")
        citations = _citations_from(results, space_like, {})
        answer = "\n\n".join(_context_texts(results))
        assert isinstance(citations, list) and isinstance(answer, str)
        print(f"[B-T9 real smoke] kb={kb_uuid[:8]}.. citations={len(citations)} answer_len={len(answer)}")
    finally:
        # P3-3：任何失败路径都不向真实 LangBot 泄漏临时 KB
        if kb_uuid:
            try:
                await client.delete_kb(kb_uuid)
            except Exception:  # noqa: BLE001  # 清理失败不吞用例结论，但尽力而为
                print(f"[B-T9 real smoke] 临时库清理失败，残留 kb={kb_uuid}")
        await client.aclose()


@pytest.mark.langbot_real
async def test_ask_real_full_chain_smoke() -> None:
    """B-T10R 全链真实冒烟：建库→上传→ingest→挂KB→流式 ask→真实 LLM delta→清库。

    前置：LangBot :5300 在跑、env 注入 LANGBOT_ADMIN_PASSWORD 与 LLM/embedding Key
    （LLM_API_KEY 缺省回落 EMBEDDING_API_KEY——同供应商同 Key）。断言 delta 非占位
    拼装：answer_len>0 且语义含"麻籽"。
    """
    import asyncio

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    from sqlalchemy import delete as sa_delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.api.deps import get_current_user_id, get_db, get_langbot_client
    from app.api.v1.chat import _context_texts
    from app.core.config import get_settings
    from app.repositories.space import SpaceRepository
    from app.repositories.user import SqlAlchemyUserStore

    s = get_settings()
    if not _langbot_reachable() or not s.langbot_admin_password:
        pytest.skip("LangBot :5300 不可达或未注入管理员凭据，跳过全链冒烟")
    if not (s.llm_api_key or s.embedding_api_key):
        pytest.skip("未注入 LLM/embedding Key，无法验证真实生成，跳过全链冒烟")

    client = LangBotClient(s.langbot_base_url, s.langbot_admin_username, s.langbot_admin_password)
    kb_uuid: str | None = None
    engine = create_async_engine(PG_URL, pool_pre_ping=True, connect_args={"connect_timeout": 3})
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    user_id = ""
    space_id = ""
    try:
        # ── 建库前置：引擎 + 嵌入模型自举（与既有冒烟同口径）──
        engine_id = ""
        for eng in await client.list_engines():
            pid = eng.get("plugin_id") or eng.get("id")
            if pid:
                engine_id = str(pid)
                break
        models = await client.list_embedding_models()
        emb = ""
        for m in models:
            provider = m.get("provider") or {}
            if provider.get("base_url", "").rstrip("/") == s.embedding_api_base.rstrip("/"):
                emb = str(m.get("uuid"))
                break
        if not emb:
            if not s.embedding_api_key:
                pytest.skip("无嵌入模型且未注入 EMBEDDING_API_KEY，跳过全链冒烟")
            provider_uuid = await client.register_provider(
                "bothot-embedding", s.embedding_api_base, s.embedding_api_key
            )
            emb = await client.register_embedding_model(s.embedding_model, provider_uuid)
        if not engine_id:
            pytest.skip("LangBot 无知识引擎，跳过全链冒烟")
        kb_uuid = await client.create_kb("b-t10r-smoke", engine_id, emb)

        # ── 上传 + ingest + 轮询就绪（full_text 可检索即就绪）──
        file_id = await client.upload_document(
            "b-t10r-smoke.md",
            "# 奖励一颗麻籽 设定文档\n\n"
            "《奖励一颗麻籽》的核心循环是：玩家首先获得奖励麻籽，用麻籽抓鸟，"
            "抓到鸟后进行驯养培养，鸟类进化后参与对战，最终完成收集。\n",
        )
        await client.trigger_ingest(kb_uuid, file_id)
        ready = False
        for _ in range(30):
            await asyncio.sleep(2)
            # 实测：full_text 多词含空格按短语处理不命中，用单词查询（诊断实证）
            probe = await client.retrieve(kb_uuid, "麻籽", top_k=3, search_type="full_text")
            if _context_texts(probe):
                ready = True
                break
        assert ready, "ingest 60s 内未产出可检索内容"

        # ── 本地落库：user + space（挂 KB）──
        async with factory() as session:
            user = await SqlAlchemyUserStore(session).upsert_by_sub(
                "sub-b-t10r-smoke", "smoke@b-t10r.local", "冒烟用户"
            )
            await session.commit()
            user_id = user.id
            space = await SpaceRepository(session).create(user_id=user_id, name="全链冒烟空间", langbot_kb_uuid=kb_uuid)
            await session.commit()
            space_id = space.id

        # ── 端点级流式 ask（真实 LangBot + 真实 LLM，不换任何桩）──
        app = create_app()

        async def _real_db() -> Any:
            # TestClient 自起事件循环：引擎必须在请求 loop 内新建（跨 loop 绑定会炸 Event）
            req_engine = create_async_engine(PG_URL, pool_pre_ping=True, connect_args={"connect_timeout": 3})
            try:
                mk = async_sessionmaker(bind=req_engine, expire_on_commit=False)
                async with mk() as session:
                    yield session
            finally:
                await req_engine.dispose()

        app.dependency_overrides[get_current_user_id] = lambda: user_id
        app.dependency_overrides[get_db] = _real_db

        # LangBotClient 同样 loop 绑定（httpx 内部锁）：依赖内新建+teardown（请求 loop 内完成）
        async def _real_langbot() -> Any:
            c2 = LangBotClient(s.langbot_base_url, s.langbot_admin_username, s.langbot_admin_password)
            try:
                yield c2
            finally:
                await c2.aclose()

        app.dependency_overrides[get_langbot_client] = _real_langbot
        resp = TestClient(app).post(
            "/api/v1/chat/ask",
            json={"spaceId": space_id, "question": "《奖励一颗麻籽》的核心循环是什么？"},
        )
        frames = _frames(resp.text)
        assert frames, "端点零帧（全链断裂）"
        assert frames[0]["type"] == "meta", f"首帧非 meta: {frames[0]}"
        answer = "".join(f["content"] for f in frames if f["type"] == "delta")
        assert len(answer) > 0, (
            f"delta 全空: frames={[(f['type'], f.get('code'), f.get('message', '')[:60]) for f in frames]}"
        )
        assert "麻籽" in answer, f"delta 非语义回答: {answer[:100]}"
        pings = sum(1 for f in frames if f["type"] == "ping")
        assert frames[-1]["type"] == "done"
        print(
            f"[B-T10R real full-chain] kb={kb_uuid[:8]}.. frames={len(frames)} "
            f"answer_len={len(answer)} pings={pings} answer={answer[:60]}..."
        )
    finally:
        # 清库 + 本地行清理（delete_kb_file 实测 405，整库删除为准）
        if kb_uuid:
            try:
                await client.delete_kb(kb_uuid)
            except Exception:  # noqa: BLE001
                print(f"[B-T10R real full-chain] 临时库清理失败，残留 kb={kb_uuid}")
        if space_id or user_id:
            try:
                async with factory() as session:
                    if space_id:
                        await session.execute(sa_delete(KnowledgeSpace).where(KnowledgeSpace.id == space_id))
                    if user_id:
                        await session.execute(sa_delete(KnowledgeSpace).where(KnowledgeSpace.user_id == user_id))
                        await session.execute(sa_delete(UserEntity).where(UserEntity.sub == "sub-b-t10r-smoke"))
                    await session.commit()
            except Exception:  # noqa: BLE001
                print("[B-T10R real full-chain] 本地行清理失败（user=sub-b-t10r-smoke）")
        await client.aclose()
        await engine.dispose()
