"""问答端点 + SSE（B-T9，契约 v0.4）。

POST /api/v1/chat/ask：body {spaceId, question} → 200 text/event-stream。
帧结构（v0.4 草案，交付确认即定稿）：
- 每帧 `data: <单行JSON>`，事件以 type 判别（不使用 event: 行——契约原文口径）；
- meta（首帧，引用先行）→ delta ×N → done；流中错误 → error 帧 + 关流；
- 心跳 ping（空闲 ≥15s 时插入，前端忽略）。
流前错误（10001/10005/30004）不走流：标准 HTTP 4xx + JSON 信封（C 非流式回退承接）。

生成链路（B-T10R 方案 A，A 批复 2026-09-08）：OpenAI 兼容直连流式——检索块入 prompt，
上游 chunk 透传 delta 帧；首 token 15s / 生成期空闲 30s（连读 2 次判死）→ error 50002；
上游 4xx → error 30002；断连即中止上游（不烧 token）。零新码位。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, get_db, get_langbot_client, get_reranker
from app.core.config import get_settings
from app.core.errors import (
    AppError,
    DependencyUnavailableError,
    ForbiddenError,
    LangbotApiError,
    RequestInvalidError,
    ResourceNotFoundError,
)
from app.models.entities import ContentAsset, KnowledgeDocument, KnowledgeSpace
from app.providers.engine_port import ENGINE_UNAVAILABLE_HINT, EngineRouter
from app.providers.langbot.client import LangBotClient
from app.providers.reranker import NoopReranker, RerankerPort
from app.repositories.asset import DocumentRepository
from app.repositories.space import SpaceRepository
from app.services.intent import classify_intent, intent_retrieval_width

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

PING_INTERVAL_SECONDS = 15.0

# 阶段 3.1.1 / 3.2（检索质量）：结果条数与候选宽度
RESULT_TOP_K = 5  # 送入引用/生成的结果条数（沿用 B-T9 的 top_k=5 口径）
CANDIDATE_TOP_K = 20  # 候选宽度：元数据过滤或重排开启时先宽取后收窄，防召回塌陷

# LLM 生成通道（B-T10R 批复 PLAN 语义）
LLM_CONNECT_TIMEOUT = 5.0
LLM_FIRST_TOKEN_TIMEOUT = 15.0
LLM_STREAM_IDLE_TIMEOUT = 30.0
LLM_MAX_CONSECUTIVE_IDLE = 2  # 生成期连续 2 次空闲超时 → 判死流（50002）


def _build_llm_http() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(connect=LLM_CONNECT_TIMEOUT, read=10.0, write=10.0, pool=5.0))


_llm_http_factory = _build_llm_http  # 模块级注入点（测试换桩；生产保持默认）


def _context_texts(results: list[dict[str, Any]]) -> list[str]:
    """检索结果 → 引用块文本列表（空结果由调用方判 30002）。"""
    parts: list[str] = []
    for entry in results:
        content = entry.get("content")
        items = content if isinstance(content, list) else [content]
        for it in items:
            if isinstance(it, dict) and it.get("text"):
                parts.append(str(it["text"]))
    return parts


def _filter_by_allowed(results: list[dict[str, Any]], allowed_file_ids: set[str]) -> list[dict[str, Any]]:
    """阶段 3.1.1：检索结果收窄到候选 doc 集合（entry 内任一 file_name 命中即保留）。

    引擎 retrieve 无 doc 级过滤入参，故以「宽取 top_k=20 → 候选集合收窄 → 截断 5」等效
    实现预过滤：保证 citations 与生成上下文全部落在 space+sourceIds+时间窗 的候选范围内。
    """
    kept: list[dict[str, Any]] = []
    for entry in results:
        content = entry.get("content")
        items = content if isinstance(content, list) else [content]
        names = {str(it.get("file_name")) for it in items if isinstance(it, dict) and it.get("file_name")}
        if names & allowed_file_ids:
            kept.append(entry)
    return kept


def _entry_text(entry: dict[str, Any]) -> str:
    """单条检索结果 → 文本（复用 _context_texts 的抽取口径，供重排打分）。"""
    parts = _context_texts([entry])
    return parts[0] if parts else ""


async def _maybe_rerank(question: str, results: list[dict[str, Any]], reranker: RerankerPort) -> list[dict[str, Any]]:
    """阶段 3.2.1：候选重排取前 RESULT_TOP_K；不可用/失败 → 按上游 score 降序截断。

    - reranker 可用时：reranker 分数降序 + 稳定 tie-break；
    - reranker 不可用/失败时：按上游 score 降序（同分保持原序），
      确保排序确定性；score 缺失则保原序截断。
    - 上游返回长度不符/缺分 → 视为失败，退回原序（不猜分、不静默改写顺序语义）。
    """
    if not results:
        return results
    if reranker.available():
        scores = await reranker.rerank(question, [_entry_text(entry) for entry in results])
        if scores is not None and len(scores) == len(results):
            order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:RESULT_TOP_K]
            return [results[i] for i in order]
    all_have_score = all(isinstance(r.get("score"), int | float) for r in results)
    if all_have_score:
        order = sorted(range(len(results)), key=lambda i: (-results[i].get("score", 0), i))[:RESULT_TOP_K]
        return [results[i] for i in order]
    return results[:RESULT_TOP_K]


def _llm_messages(question: str, results: list[dict[str, Any]]) -> list[dict[str, str]]:
    """prompt 组装：系统指令 + 引用块文本 + 用户问题。"""
    context = "\n\n".join(_context_texts(results))
    return [
        {
            "role": "system",
            "content": "你是知识库问答助手，只依据给定的引用内容回答问题；引用中没有的信息如实说明不知道，不要编造。",
        },
        {"role": "user", "content": f"引用内容：\n{context}\n\n问题：{question}"},
    ]


class AskFilters(BaseModel):
    """阶段 3.1.1 元数据过滤（可选）：信息源集合 + 时间窗。

    - sourceIds 空 = 不限信息源；days=None = 不限时间；二者皆空 = 过滤未开启；
    - 上限：sourceIds 最多 20 条、days in [1, 365]（越界 → 10005/422 信封）；
    - 时间窗口径：COALESCE(published_at, created_at) >= now - days（缺发布时间用入库时间兜底）。
    """

    sourceIds: list[str] = Field(default_factory=list, max_length=20)
    days: int | None = Field(default=None, ge=1, le=365)

    @property
    def active(self) -> bool:
        return bool(self.sourceIds) or self.days is not None


class AskRequest(BaseModel):
    spaceId: str
    question: str
    filters: AskFilters | None = None


def _sse_frame(payload: dict[str, Any]) -> str:
    """单行 JSON 帧（契约：data: <单行JSON>，type 判别）。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _anext(iterator: Any) -> Any:
    return await iterator.__anext__()


_ensure_future = asyncio.ensure_future  # 注入点（测试追踪任务生命周期；生产保持默认）

_create_task = asyncio.create_task  # 注入点（测试追踪 retrieve 任务生命周期；生产保持默认）


def _citations_from(
    results: list[dict[str, Any]], space: KnowledgeSpace, title_map: dict[str, str]
) -> list[dict[str, str]]:
    """retrieve 结果 → 引用块（title 优先本地 doc.title，回退文件名尾段；spaceName 固定）。

    AB-P004 P4：citations 追加 engine（ADR-0004 三元 {title, spaceName, engine}）。"""
    engine = getattr(space, "engine", "builtin") or "builtin"
    citations: list[dict[str, str]] = []
    seen_titles: set[str] = set()
    for entry in results:
        content = entry.get("content")
        items = content if isinstance(content, list) else [content]
        text = next(
            (str(it.get("text", "")) for it in items if isinstance(it, dict) and it.get("text")),
            "",
        )
        if not text:
            continue
        file_name = next((str(it.get("file_name", "")) for it in items if isinstance(it, dict)), "")
        title = title_map.get(file_name) or (file_name.rsplit("/", 1)[-1].rsplit(".", 1)[0] if file_name else text[:24])
        if title in seen_titles:
            continue  # 同一文档的多个 chunk 命中不重复出引用（空间名/引擎在本次请求内恒定）
        seen_titles.add(title)
        citations.append({"title": title, "spaceName": space.name, "engine": engine})
    return citations


async def _local_title_map(session: AsyncSession, space_id: str, file_ids: list[str]) -> dict[str, str]:
    """langbot_file_id → 本地 asset.title（B-T10 任务4：引用标题接库内真名）。"""
    if not file_ids:
        return {}
    rows = (
        await session.execute(
            select(KnowledgeDocument.langbot_file_id, ContentAsset.title)
            .join(ContentAsset, KnowledgeDocument.asset_id == ContentAsset.id)
            .where(
                KnowledgeDocument.space_id == space_id,
                KnowledgeDocument.langbot_file_id.in_(file_ids),
            )
        )
    ).all()
    return {fid: title for fid, title in rows}


async def _llm_stream_delta(
    question: str,
    results: list[dict[str, Any]],
    is_disconnected: Any = None,
) -> AsyncIterator[tuple[str, str]]:
    """OpenAI 兼容直连流式生成（B-T10R 方案 A，A 批复 2026-09-08）。

    产出 ("delta", content) / ("ping", "") 二元组；语义：
    - 空引用 → LangbotApiError(30002)（知识库无可回答内容）；
    - 上游 4xx → LangbotApiError(30002)（批复②，与 LangBot 业务错误同族，M2 拆码复议）；
    - 首 token 超时 / 流连续空闲判死 → DependencyUnavailableError(50002)；
    - is_disconnected() 为真 → 立即 return（async with 退出断上游连接，不烧 token）；
    - 流中不重试（delta 已发不可撤回），零新码位。
    """
    texts = _context_texts(results)
    if not texts:
        raise LangbotApiError("知识库无可回答内容")

    settings = get_settings()
    api_key = settings.llm_api_key or settings.embedding_api_key  # 同供应商同 Key 兜底（冒烟口径）
    async with _llm_http_factory() as http:
        resp = http.stream(
            "POST",
            f"{settings.llm_api_base.rstrip('/')}/chat/completions",
            json={
                "model": settings.llm_model,
                "messages": _llm_messages(question, results),
                "stream": True,
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        async with resp as response:
            if response.status_code >= 400:
                body = (await response.aread())[:160].decode("utf-8", "replace")
                raise LangbotApiError(f"LLM 上游 {response.status_code}: {body}")

            lines = response.aiter_lines()
            pending: Any = None  # shield 保留挂起 anext，避免并发 __anext__ 冲突
            first_token = True
            idle_count = 0
            try:
                while True:
                    if is_disconnected is not None and await is_disconnected():
                        return
                    try:
                        if pending is None:
                            pending = _ensure_future(_anext(lines))
                        line = await asyncio.wait_for(
                            asyncio.shield(pending),
                            timeout=LLM_FIRST_TOKEN_TIMEOUT if first_token else LLM_STREAM_IDLE_TIMEOUT,
                        )
                        pending = None
                    except TimeoutError:
                        if first_token:
                            raise DependencyUnavailableError("LLM 首 token 超时") from None
                        idle_count += 1
                        if idle_count >= LLM_MAX_CONSECUTIVE_IDLE:
                            raise DependencyUnavailableError("LLM 流空闲超时") from None
                        yield ("ping", "")
                        continue
                    first_token = False
                    idle_count = 0
                    if not line.startswith("data: ") or "[DONE]" in line:
                        if "[DONE]" in line:
                            break
                        continue
                    chunk = json.loads(line[len("data: ") :])
                    content = (chunk.get("choices") or [{}])[0].get("delta", {}).get("content")
                    if content:
                        yield ("delta", str(content))
            finally:
                # B-T10R 补强：全部退出路径（首 token 超时/空闲判死/断连/上游异常/JSON 解析
                # 异常/[DONE] 正常结束/外层取消）统一清理挂起读取任务——response/http client
                # 在本 finally 之后才随 async with 退出，后台 anext 不允许存活到连接关闭。
                if pending is not None:
                    if not pending.done():
                        pending.cancel()
                    try:
                        await pending
                    except asyncio.CancelledError:
                        pass
                    except Exception:  # noqa: BLE001  # 挂起任务自身的读取异常：已在退出路径，不外泄
                        pass


async def _event_stream(
    request: Request,
    langbot: LangBotClient,
    kb_uuid: str,
    question: str,
    space: KnowledgeSpace,
    session: AsyncSession,
    router: EngineRouter | None = None,
    allowed_file_ids: set[str] | None = None,
    reranker: RerankerPort | None = None,
) -> AsyncIterator[str]:
    """SSE 主循环：ping(检索期) → meta → delta ×N → done；流中异常 → error 帧关流。

    BE-02：retrieve 按 space.engine 分发（builtin → LangBot 原路径；非 builtin → adapter）。

    retrieve_task 生命周期（B-T10 终版）：
    - shield 只防 wait_for 超时误杀任务，**不**防任务残留——外层必须负责收敛；
    - 全部退出路径（成功/断连/异常/外层取消）统一在 finally 收敛：
      未完成 → cancel + await（消费 CancelledError）；已完成 → exception() 消费，防
      "Task exception was never retrieved"；
    - 检索期检测到客户端断开 → 立即 return（不发 LLM、不烧 token）。
    """
    engine = str(getattr(space, "engine", "builtin") or "builtin")
    router = router or EngineRouter(get_settings(), langbot)
    # 引擎不可用（Key 未配/未开放）→ 流前 403 信封（不伪装可用）
    if not router.available(engine):
        raise ForbiddenError(ENGINE_UNAVAILABLE_HINT % engine)
    retrieve_kb_id = router.kb_id_for(space) or kb_uuid
    # 阶段 3.1.1/3.2：有候选集收窄或重排 → 先宽取候选、检索后再收窄（防召回塌陷）；
    # allowed_file_ids=None 仅当调用方显式放弃收窄（历史兼容/单测直驱），此时维持 top_k=5。
    reranker = reranker or NoopReranker()
    base_width = CANDIDATE_TOP_K if (allowed_file_ids is not None or reranker.available()) else RESULT_TOP_K
    # 阶段 3.3.1（T3.1）：意图五分类路由检索宽度——单调放宽（max），绝不收窄基线
    intent = classify_intent(question)
    retrieve_top_k = max(base_width, intent_retrieval_width(intent))

    retrieve_task: asyncio.Task[Any] | None = None
    try:
        # B-T10 任务2：retrieve 阻塞期持续发 ping（shield 保任务不被超时取消）
        if engine == "builtin":
            retrieve_call = langbot.retrieve(retrieve_kb_id, question, top_k=retrieve_top_k, search_type="vector")
        else:
            adapter = router.adapter_for(space)
            retrieve_call = adapter.retrieve(retrieve_kb_id, question, top_k=retrieve_top_k)
        retrieve_task = _create_task(retrieve_call)
        results: list[dict[str, Any]] = []
        while True:
            # 检索期断连即收敛：cancel+await retrieve_task 在 finally 完成
            if await request.is_disconnected():
                return
            try:
                results = await asyncio.wait_for(asyncio.shield(retrieve_task), timeout=PING_INTERVAL_SECONDS)
                break
            except TimeoutError:
                yield _sse_frame({"type": "ping"})

        if allowed_file_ids is not None:
            results = _filter_by_allowed(results, allowed_file_ids)
        results = await _maybe_rerank(question, results, reranker)

        file_ids: list[str] = []
        for entry in results:
            content = entry.get("content")
            items = content if isinstance(content, list) else [content]
            for it in items:
                if isinstance(it, dict) and it.get("file_name"):
                    file_ids.append(str(it["file_name"]))
        title_map = await _local_title_map(session, space.id, file_ids)
        citations = _citations_from(results, space, title_map)
        # T3.1：intent 随 meta 帧透出（增量字段，前端解析器忽略未知键，零回归）
        yield _sse_frame({"type": "meta", "citations": citations, "intent": intent})

        # B-T10R 方案 A：OpenAI 兼容直连流式生成（批复 PLAN 语义；独立生成器供冒烟复用）
        async for kind, content in _llm_stream_delta(question, results, request.is_disconnected):
            if kind == "ping":
                yield _sse_frame({"type": "ping"})  # 生成期心跳（空闲 30s 一帧）
            else:
                yield _sse_frame({"type": "delta", "content": content})
        yield _sse_frame({"type": "done", "messageId": str(uuid.uuid4())})
    except AppError as exc:
        # B-T9R P1：捕全业务异常基类——真实 client 把网络/404 预包装为 50002/30004 等
        # AppError 子类抛出（LangbotApiError 只是其中一种），窄捕会裸逃逸断流
        yield _sse_frame({"type": "error", "code": exc.code, "message": exc.message})
    except httpx.HTTPError:
        # 兜直抛场景（测试桩/未来直用 httpx），归一 50002
        yield _sse_frame({"type": "error", "code": 50002, "message": "LangBot 不可达"})
    except Exception:  # noqa: BLE001  # B-T10 终版：endpoint 兜底，非业务异常归一 50001
        # 覆盖 malformed JSON / 非预期 RuntimeError / SQLAlchemyError 等裸逃逸路径：
        # 否则流已开（meta 已发）后裸抛会让客户端拿到截断响应且无 error 帧。
        yield _sse_frame({"type": "error", "code": 50001, "message": "内部错误"})
    finally:
        # B-T10 终版：所有退出路径统一收敛 retrieve_task（shield 不防残留）——
        # 未完成 → cancel + await（消费取消）；已完成 → exception() 消费未读异常。
        if retrieve_task is not None:
            if not retrieve_task.done():
                retrieve_task.cancel()
                try:
                    await retrieve_task
                except asyncio.CancelledError:
                    pass
                except Exception:  # noqa: BLE001  # 取消竞争窗口的任务异常：退出路径不外泄
                    pass
            elif not retrieve_task.cancelled():
                try:
                    retrieve_task.exception()  # 消费未读任务异常，防 never-retrieved 告警
                except asyncio.CancelledError:
                    pass


@router.post("/ask")
async def ask(
    payload: AskRequest,
    request: Request,
    _user_id: Annotated[str, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
    langbot: Annotated[LangBotClient, Depends(get_langbot_client)],
    reranker: Annotated[RerankerPort, Depends(get_reranker)],
) -> StreamingResponse:
    """问答（SSE）：空间校验 → 候选集收窄 → 引擎检索 → 事件流。流前错误走 JSON 信封。

    阶段 3.1.1：body.filters 为可选二次收窄（信息源 + 时间窗）。**候选集恒收窄到本空间
    READY doc**——引擎 KB 内可能滞留 DB 未追踪的文件（重跑覆盖未删旧文件，见 B27），
    缺省不收窄则 retrieve 可命中并作答，引用越界。
    阶段 3.2：reranker 为可选增强（未配 Key → NoopReranker，等价旧行为）。
    """
    if not payload.question.strip():
        raise RequestInvalidError("question 不能为空")
    space = await SpaceRepository(session).get_by_id(payload.spaceId)
    if space is None or space.user_id != _user_id:
        # 30004：无效 id/越权同语义（v0.4a 契约：message 必须可读文案，非裸 id）
        raise ResourceNotFoundError(f"知识空间不存在或无权限: {payload.spaceId}")
    engine = str(getattr(space, "engine", "builtin") or "builtin")
    router = EngineRouter(get_settings(), langbot)
    # BE-02：引擎不可用（Key 未配/未开放）→ 403 流前信封；builtin 恒可用
    if not router.available(engine):
        raise ForbiddenError(ENGINE_UNAVAILABLE_HINT % engine)
    kb_uuid = router.kb_id_for(space)
    if not kb_uuid:
        raise LangbotApiError("空间知识库未初始化（尚未 ingest 任何内容）")

    filters = payload.filters
    since = (
        datetime.now(UTC) - timedelta(days=filters.days) if filters is not None and filters.days is not None else None
    )
    # 候选集默认为「本空间 READY 且已入库」的 doc；filters 只在其上做二次收窄。
    # 缺省也必须收窄：KB 内会滞留 DB 未追踪的文件（重跑覆盖未删旧文件，B27），
    # 不收窄则 retrieve 命中后直接写进答案与引用，形成内容越界。
    allowed_file_ids = await DocumentRepository(session).allowed_file_ids(
        space.id,
        filters.sourceIds if filters is not None else None,
        since,
    )

    return StreamingResponse(
        _event_stream(
            request,
            langbot,
            kb_uuid,
            payload.question.strip(),
            space,
            session,
            router,
            allowed_file_ids,
            reranker,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
