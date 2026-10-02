"""阶段 3.1.1 验收测试：问答元数据过滤（sourceIds + 时间窗）。

大纲 3.1.1 口径：ask 入口按 space 的 source 集合 + 时间范围预过滤 doc 候选再进引擎检索；
验收 = 限定 7 天/单源提问时 citations 全部落在过滤范围内。

覆盖：
- 仓库层 allowed_file_ids：READY/file_id 非空硬门 + 空间隔离 + 源过滤 + 时间窗 + 空集合法；
- 端点层：过滤开启 → citations 收窄（且候选宽度 20）；**未开启 → 同语义收窄**
  （B25：缺省即收窄到本空间 READY doc，宽度自动 5→20，孤儿文件必被裁）；
- 空候选 → meta 空引用 + error 30002（不编造、不无过滤回退）；
- 参数上限：days 越界 / sourceIds 超 20 → 10005/422。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from test_chat_sse import _frames, _llm_echo_transport

from app.api.deps import get_current_user_id, get_db, get_langbot_client
from app.main import create_app
from app.models.entities import ContentAsset, Source
from app.models.entities import User as UserEntity
from app.providers.langbot.client import LangBotClient
from app.repositories.asset import DocumentRepository
from app.repositories.space import SpaceRepository


@pytest.fixture(autouse=True)
def _restore_llm_factory() -> Any:
    """LLM 桩换入后强制恢复（防残留污染同进程其他用例）。"""
    from app.api.v1 import chat as chat_module

    original = chat_module._llm_http_factory
    yield
    chat_module._llm_http_factory = original


class _RecordingLangBot(LangBotClient):
    """retrieve 桩：记录 top_k 并回放固定结果（可含允许/不允许两种 file_name）。"""

    def __init__(self, results: list[dict[str, Any]]) -> None:
        super().__init__("http://langbot.stub", "a", "b")
        self._results = results
        self.top_k_seen: list[int] = []

    async def retrieve(
        self, kb_uuid: str, query: str, top_k: int = 5, search_type: str = "vector"
    ) -> list[dict[str, Any]]:
        self.top_k_seen.append(top_k)
        return list(self._results)


def _results(*file_names: str) -> list[dict[str, Any]]:
    return [
        {"content": [{"text": f"{name} 正文", "file_name": name}], "score": 0.9 - i * 0.1}
        for i, name in enumerate(file_names)
    ]


def _client(db_session: Any, stub: LangBotClient, user_id: str) -> TestClient:
    from app.api.v1 import chat as chat_module

    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_langbot_client] = lambda: stub
    chat_module._llm_http_factory = lambda: httpx.AsyncClient(transport=_llm_echo_transport())
    return TestClient(app)


async def _seed_space(session: Any, *, sub: str, name: str, kb_uuid: str = "kb-mf") -> tuple[str, str]:
    user = UserEntity(sub=sub, email=f"{sub}@mf.local", nickname="MF")
    session.add(user)
    await session.flush()
    space = await SpaceRepository(session).create(user_id=user.id, name=name, langbot_kb_uuid=kb_uuid)
    await session.flush()
    return user.id, space.id


async def _seed_source(session: Any, external_id: str) -> Source:
    source = Source(type="wechat_oa", external_id=external_id, name=f"源{external_id}")
    session.add(source)
    await session.flush()
    return source


async def _seed_doc(
    session: Any,
    *,
    space_id: str,
    source_id: str,
    external_id: str,
    file_id: str,
    published_at: datetime | None = None,
    asset_created_at: datetime | None = None,
    status: str = "READY",
) -> None:
    asset = ContentAsset(
        source_id=source_id,
        external_id=external_id,
        url=f"https://mp.weixin.qq.com/s/{external_id}",
        title=f"标题{external_id}",
        content_hash=f"hash-{external_id}",
        content_markdown="# 正文",
        published_at=published_at,
    )
    session.add(asset)
    await session.flush()
    if asset_created_at is not None:
        asset.created_at = asset_created_at
    doc = await DocumentRepository(session).create(asset_id=asset.id, space_id=space_id)
    doc.status = status
    doc.langbot_file_id = file_id
    await session.flush()


# ------------------------------------------------------------------ 仓库层


async def test_allowed_file_ids_source_and_time_window(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """READY+file_id 硬门、源过滤、时间窗（published_at）与空集合法性。"""
    _, space_id = await _seed_space(db_session, sub="sub-mf-repo-1", name="过滤仓库空间")
    src_a = await _seed_source(db_session, "mf-biz-A")
    src_b = await _seed_source(db_session, "mf-biz-B")
    now = datetime.now(UTC)
    await _seed_doc(
        db_session,
        space_id=space_id,
        source_id=src_a.id,
        external_id="a-new",
        file_id="f-a-new",
        published_at=now - timedelta(days=2),
    )
    await _seed_doc(
        db_session,
        space_id=space_id,
        source_id=src_a.id,
        external_id="a-old",
        file_id="f-a-old",
        published_at=now - timedelta(days=30),
    )
    await _seed_doc(
        db_session,
        space_id=space_id,
        source_id=src_b.id,
        external_id="b-new",
        file_id="f-b-new",
        published_at=now - timedelta(days=1),
    )
    await _seed_doc(
        db_session,
        space_id=space_id,
        source_id=src_a.id,
        external_id="a-pending",
        file_id="f-a-pending",
        status="FETCHED",
    )
    await _seed_doc(db_session, space_id=space_id, source_id=src_a.id, external_id="a-nofid", file_id="")
    repo = DocumentRepository(db_session)

    assert await repo.allowed_file_ids(space_id) == {"f-a-new", "f-a-old", "f-b-new"}
    assert await repo.allowed_file_ids(space_id, [src_a.id]) == {"f-a-new", "f-a-old"}
    since = now - timedelta(days=7)
    assert await repo.allowed_file_ids(space_id, since=since) == {"f-a-new", "f-b-new"}
    assert await repo.allowed_file_ids(space_id, [src_a.id], since) == {"f-a-new"}
    assert await repo.allowed_file_ids(space_id, ["no-such-source"]) == set()


async def test_allowed_file_ids_space_isolation_and_created_fallback(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """空间隔离 + published_at 缺失时以 created_at 兜底。"""
    _, space_a = await _seed_space(db_session, sub="sub-mf-repo-2a", name="过滤空间A")
    _, space_b = await _seed_space(db_session, sub="sub-mf-repo-2b", name="过滤空间B")
    src = await _seed_source(db_session, "mf-biz-C")
    now = datetime.now(UTC)
    await _seed_doc(
        db_session,
        space_id=space_a,
        source_id=src.id,
        external_id="c-fresh",
        file_id="f-c-fresh",
        asset_created_at=now - timedelta(days=1),
    )
    await _seed_doc(
        db_session,
        space_id=space_a,
        source_id=src.id,
        external_id="c-stale",
        file_id="f-c-stale",
        asset_created_at=now - timedelta(days=30),
    )
    await _seed_doc(
        db_session, space_id=space_b, source_id=src.id, external_id="c-other", file_id="f-c-other", published_at=now
    )
    repo = DocumentRepository(db_session)
    since = now - timedelta(days=7)

    assert await repo.allowed_file_ids(space_a, since=since) == {"f-c-fresh"}
    assert await repo.allowed_file_ids(space_b, since=since) == {"f-c-other"}


# ------------------------------------------------------------------ 端点层


async def _endpoint_seed(session: Any, *, sub: str, name: str) -> tuple[str, str, Source, Source]:
    user_id, space_id = await _seed_space(session, sub=sub, name=name)
    src_a = await _seed_source(session, f"{sub}-A")
    src_b = await _seed_source(session, f"{sub}-B")
    now = datetime.now(UTC)
    await _seed_doc(
        session,
        space_id=space_id,
        source_id=src_a.id,
        external_id="ep-a",
        file_id="f-ep-a",
        published_at=now - timedelta(days=1),
    )
    await _seed_doc(
        session,
        space_id=space_id,
        source_id=src_b.id,
        external_id="ep-b",
        file_id="f-ep-b",
        published_at=now - timedelta(days=1),
    )
    return user_id, space_id, src_a, src_b


async def test_ask_filters_narrow_citations_and_widen_candidates(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """过滤开启：citations 全部落在候选范围内，且 retrieve 走 20 宽候选。"""
    user_id, space_id, src_a, _ = await _endpoint_seed(db_session, sub="sub-mf-ep-1", name="端点过滤空间")
    stub = _RecordingLangBot(_results("f-ep-a", "f-ep-b"))
    client = _client(db_session, stub, user_id)

    resp = client.post(
        "/api/v1/chat/ask",
        json={"spaceId": space_id, "question": "q", "filters": {"sourceIds": [src_a.id], "days": 7}},
    )
    assert resp.status_code == 200
    frames = _frames(resp.text)
    assert frames[0]["type"] == "meta"
    assert [c["title"] for c in frames[0]["citations"]] == ["标题ep-a"]
    assert stub.top_k_seen == [20]
    assert frames[-1]["type"] == "done"


async def test_ask_without_filters_scopes_to_space_docs(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """B25：缺省不收窄即为默认收窄——收窄到本空间 READY doc，宽度自动 5→20。

    KB 内会滞留 DB 未追踪的文件（重跑覆盖未删旧文件，B27）；若缺省不挡，
    孤儿会被 retrieve 命中写进答案，形成内容越界。显式空 filters 同语义。
    """
    user_id, space_id, _, _ = await _endpoint_seed(db_session, sub="sub-mf-ep-2", name="端点无过滤空间")
    stub = _RecordingLangBot(_results("f-ep-a", "f-ep-b"))
    client = _client(db_session, stub, user_id)

    frames = _frames(client.post("/api/v1/chat/ask", json={"spaceId": space_id, "question": "q"}).text)
    assert [c["title"] for c in frames[0]["citations"]] == ["标题ep-a", "标题ep-b"]
    assert stub.top_k_seen == [20]
    frames2 = _frames(
        client.post(
            "/api/v1/chat/ask",
            json={"spaceId": space_id, "question": "q", "filters": {}},
        ).text
    )
    assert len(frames2[0]["citations"]) == 2
    assert stub.top_k_seen == [20, 20]


async def test_ask_without_filters_drops_untracked_engine_file(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """B25 隔离门：引擎返回 DB 未追踪文件时必被裁掉，不进 citations。

    实测量证：该空间 KB 13 文件 vs DB 3 doc，10 个孤儿由此累积——即越界答案的成因。
    """
    user_id, space_id, _, _ = await _endpoint_seed(db_session, sub="sub-mf-ep-5", name="端点孤儿隔离空间")
    stub = _RecordingLangBot(_results("f-ep-a", "f-orphan"))
    client = _client(db_session, stub, user_id)

    frames = _frames(client.post("/api/v1/chat/ask", json={"spaceId": space_id, "question": "q"}).text)
    assert [c["title"] for c in frames[0]["citations"]] == ["标题ep-a"]
    assert stub.top_k_seen == [20]


async def test_ask_without_filters_all_untracked_reports_no_content(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """全部命中孤儿 → 空候选：meta 空引用 + error 30002，不由 LLM 就孤儿内容自由作答。"""
    user_id, space_id = await _seed_space(db_session, sub="sub-mf-ep-6", name="端点全孤儿空间")
    src = await _seed_source(db_session, "sub-mf-ep-6-A")
    await _seed_doc(
        db_session,
        space_id=space_id,
        source_id=src.id,
        external_id="ep-real",
        file_id="f-ep-real",
        published_at=datetime.now(UTC),
    )
    stub = _RecordingLangBot(_results("f-orphan-1", "f-orphan-2"))
    client = _client(db_session, stub, user_id)

    frames = _frames(client.post("/api/v1/chat/ask", json={"spaceId": space_id, "question": "q"}).text)
    assert frames[0]["citations"] == []
    assert frames[-1]["type"] == "error" and frames[-1]["code"] == 30002
    assert not any(f["type"] == "delta" for f in frames)


async def test_ask_filter_with_no_candidate_reports_no_content(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """空候选：meta 空引用 + error 30002；无 delta（不编造、不无过滤回退）。"""
    user_id, space_id = await _seed_space(db_session, sub="sub-mf-ep-3", name="端点空候选空间")
    src = await _seed_source(db_session, "sub-mf-ep-3-A")
    now = datetime.now(UTC)
    await _seed_doc(
        db_session,
        space_id=space_id,
        source_id=src.id,
        external_id="ep-old",
        file_id="f-ep-old",
        published_at=now - timedelta(days=40),
    )
    stub = _RecordingLangBot(_results("f-ep-old"))
    client = _client(db_session, stub, user_id)

    frames = _frames(
        client.post(
            "/api/v1/chat/ask",
            json={"spaceId": space_id, "question": "q", "filters": {"days": 7}},
        ).text
    )
    # T3.1 契约演进：meta 帧增量 intent 字段（五分类之一），citations 语义不变
    assert frames[0]["type"] == "meta" and frames[0]["citations"] == []
    assert frames[0]["intent"] in {"chat", "fact", "precise", "list", "summary"}
    assert frames[-1]["type"] == "error" and frames[-1]["code"] == 30002
    assert not any(f["type"] == "delta" for f in frames)


@pytest.mark.parametrize(
    "filters",
    [
        {"days": 0},
        {"days": 366},
        {"sourceIds": [f"s{i}" for i in range(21)]},
    ],
)
async def test_ask_filter_validation_rejects_out_of_range(db_session: Any, filters: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
    """参数上限：days 越界 / sourceIds 超 20 → 10005/422，且不触发检索。"""
    user_id, space_id = await _seed_space(db_session, sub="sub-mf-ep-4", name="端点校验空间")
    stub = _RecordingLangBot(_results("f-x"))
    client = _client(db_session, stub, user_id)

    resp = client.post(
        "/api/v1/chat/ask",
        json={"spaceId": space_id, "question": "q", "filters": filters},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 10005
    assert stub.top_k_seen == []
