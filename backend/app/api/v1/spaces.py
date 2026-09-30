"""知识空间路由（B-T4R）：v0.3 契约三端点 + POST 创建 + AB-P004 P1 公共库端点。

- 字段 camelCase、data.items 解包，形状全部由 SpaceService 组装（Route 只鉴权+信封）；
- 登录保护：未登录 → 10001；他人空间/无效 id → 30004（不泄露存在性）；
- POST 重名 → 30006/409（v0.3a，Service 层映射）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, get_db, get_kb_service, get_langbot_client, get_space_service
from app.core.response import success
from app.providers.langbot.client import LangBotClient
from app.services.batch_ingest import BatchIngestService
from app.services.kb import KnowledgeBaseService
from app.services.public_library import PublicLibraryService
from app.services.spaces import SpaceService

router = APIRouter(prefix="/api/v1/spaces", tags=["spaces"])


class CreateSpaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=512)  # R0.5.1 落列，由 SpaceService 校验


class PatchSpaceRequest(BaseModel):
    """R0.5.2（F-4）：空间简介写端点请求体。

    description 缺省即不改（PATCH 部分更新语义），传 "" 表示清空。
    无 name 字段——改名触及 uq_space_user_name 与既有空间链接语义，需单独裁决。
    """

    description: str | None = Field(default=None, max_length=512)


# ------------------------------------------------------------------ AB-P004 P1 公共库端点


class LinkPublicSpaceRequest(BaseModel):
    public_space_id: str = Field(min_length=1, max_length=36)


class PatchSpacePublicRequest(BaseModel):
    """T1.4.1：is_public 写端点请求体（camelCase 主形态，snake 兼容）。"""

    model_config = ConfigDict(populate_by_name=True)

    is_public: bool = Field(alias="isPublic")


@router.get("/public")
async def list_public_spaces(
    user_id: Annotated[str, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    """AB-P004 P1：公共库列表（is_public=1 系统空间）。

    data.items=[{id,name,description,docCount,engine,isPublic,updatedAt}]。
    分页（3.3，limit/offset 与 knowledge 域 docs 同口径）：路由层切片；service 层
    limit/offset 待 WA/WB 下沉。登录保护 10001；无需空间归属校验（公共库对全用户开放）。
    """
    svc = PublicLibraryService(session)
    items = await svc.list_public_views()
    total = len(items)
    page = items[offset : offset + limit]
    body = success(data={"items": page, "total": total, "limit": limit, "offset": offset})
    return JSONResponse(status_code=200, content=body.model_dump())


@router.post("/{space_id}/links")
async def link_public_space(
    space_id: str,
    payload: LinkPublicSpaceRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """AB-P004 P1：批量 copy 公共空间 READY 资产进目标用户空间（幂等）。

    200 返回 {copied, skipped, total}；
    目标空间越权/无效 → 30004；公共空间无效/非公共 → 30004。
    已 copy 的 doc 跳过（skipped），重复调用幂等不报错。
    """
    svc = PublicLibraryService(session)
    result = await svc.link_public_space(user_id, space_id, payload.public_space_id)
    body = success(data=result)
    return JSONResponse(status_code=200, content=body.model_dump())


@router.patch("/{space_id}/public")
async def patch_space_public(
    space_id: str,
    payload: PatchSpacePublicRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """T1.4.1：公共库发布/回收写端点（双闸：env allowlist ∩ owner_type=system）。

    200 {spaceId,name,isPublic}；
    未登录 → 10001；空间不存在 → 30004；
    操作者不在 PUBLIC_ADMIN_ALLOWLIST → 10004/403；
    目标空间非系统空间（owner_type!=system）→ 10004/403。
    M3 批次 3 双闸收敛（2026-09-23 裁「按角色分通道」）后本双闸原样保留。
    """
    svc = PublicLibraryService(session)
    result = await svc.set_public_status(user_id, space_id, payload.is_public)
    body = success(data=result)
    return JSONResponse(status_code=200, content=body.model_dump())


@router.get("")
async def list_spaces(
    user_id: Annotated[str, Depends(get_current_user_id)],
    svc: Annotated[SpaceService, Depends(get_space_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    """空间列表：data.items=[{id,name,description,docCount,updatedAt}]。

    分页（3.3，limit/offset 与 knowledge 域 docs 同口径）：路由层切片；service 层
    limit/offset 待 WA/WB 下沉。
    """
    items = await svc.list_space_views(user_id)
    total = len(items)
    page = items[offset : offset + limit]
    body = success(data={"items": page, "total": total, "limit": limit, "offset": offset})
    return JSONResponse(status_code=200, content=body.model_dump())


@router.post("")
async def create_space(
    payload: CreateSpaceRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    svc: Annotated[SpaceService, Depends(get_space_service)],
) -> JSONResponse:
    """创建空间（重名 → 30006/409）；响应复用详情形状（契约未单独定，最小假设见报告）。"""
    space = await svc.create_space(user_id, payload.name, payload.description)
    view = await svc.get_space_view(user_id, space.id)
    body = success(data=view)
    return JSONResponse(status_code=201, content=body.model_dump())


@router.get("/{space_id}")
async def get_space(
    space_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    svc: Annotated[SpaceService, Depends(get_space_service)],
) -> JSONResponse:
    """空间详情：{id,name,description,docCount,createdAt,updatedAt,stats{docs,chunks}}；
    无效 id / 他人空间 → 30004（404）。

    R0.5.3（F-5）：stats.chunks 可为 null——数据源（LangBot KB 统计）未接线，
    null 表示「无该指标」而非 0，前端应隐藏而非显示「已索引 0 块」。"""
    view = await svc.get_space_view(user_id, space_id)
    body = success(data=view)
    return JSONResponse(status_code=200, content=body.model_dump())


@router.patch("/{space_id}")
async def update_space(
    space_id: str,
    payload: PatchSpaceRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    svc: Annotated[SpaceService, Depends(get_space_service)],
) -> JSONResponse:
    """改空间简介（R0.5.2，F-4）；响应复用详情形状。

    description 缺省即不改，传 "" 表示清空；取值非法（超长/控制字符）→ 10005；
    无效 id / 他人空间 → 30004（404，不泄露存在性）。
    """
    if payload.description is not None:
        await svc.update_space(user_id, space_id, payload.description)
    view = await svc.get_space_view(user_id, space_id)
    body = success(data=view)
    return JSONResponse(status_code=200, content=body.model_dump())


@router.delete("/{space_id}")
async def delete_space(
    space_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    svc: Annotated[SpaceService, Depends(get_space_service)],
    kb: Annotated[LangBotClient, Depends(get_langbot_client)],
) -> JSONResponse:
    """删除空间（AB-T11）：先 LangBot 删库，失败整体回滚；成功 → {ok:true}。

    未登录 → 10001；无效 id / 他人空间 → 30004（404，不泄露存在性）；
    LangBot 删库失败 → 错误信封（30002/502 等，PG 无残留）。
    """
    await svc.delete_space(user_id, space_id, kb)
    body = success(data={"ok": True})
    return JSONResponse(status_code=200, content=body.model_dump())


@router.get("/{space_id}/docs")
async def list_space_docs(
    space_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    svc: Annotated[SpaceService, Depends(get_space_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    category: Annotated[str | None, Query(max_length=32)] = None,
) -> JSONResponse:
    """空间文档清单：data={items:[{id,title,source,status,updatedAt,category}],total,limit,offset}，
    status∈pending|ready|failed。

    T1.5.7：可选分页（limit 上限 200 / offset ≥0，默认 100+0）；items 键形状不变，
    total/limit/offset 为增量字段——旧调用方（仅取 items）零回归。
    R0.1.1：可选 `category` 服务端过滤（替代前端的客户端过滤，F-9）。
    `category=__uncategorized__` 表示「未分类」（资产无分类标签）；`total` 与 `items`
    走同一过滤谓词（仓库 _docs_stmt 单一来源），故分页后的 total 不会虚高。
    """
    items, total = await svc.list_space_docs(
        user_id, space_id, limit=limit, offset=offset, category=category
    )
    body = success(data={"items": items, "total": total, "limit": limit, "offset": offset})
    return JSONResponse(status_code=200, content=body.model_dump())


@router.get("/{space_id}/docs:categories")
async def list_doc_categories(
    space_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    svc: Annotated[SpaceService, Depends(get_space_service)],
) -> JSONResponse:
    """空间分类集合：data={items:[string]}（R0.1.2）。

    返回该空间**实际存在**的分类，按规则版声明序，未分类以 `__uncategorized__` 置末；
    空空间 → 空数组。用途：分类下拉的数据源——服务端枚举，替代前端按当前页数据推导
    （分页后单页推导会漏掉不在本页的分类，F-9 的另一半）。
    items 可直接回传 `?category=`，与 docs 列表查询入参口径对称。
    越权/无效空间 → 30004（404，不泄露存在性）。
    """
    items = await svc.list_doc_categories(user_id, space_id)
    body = success(data={"items": items})
    return JSONResponse(status_code=200, content=body.model_dump())


class PatchDocRequest(BaseModel):
    """R0.2.2：文档分类人工纠偏请求体。仅接受 category（正文不改——正文属采集事实）。"""

    category: str = Field(default="", max_length=32)


@router.delete("/{space_id}/docs/{doc_id}")
async def delete_doc(
    space_id: str,
    doc_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    svc: Annotated[SpaceService, Depends(get_space_service)],
    kb: Annotated[LangBotClient, Depends(get_langbot_client)],
) -> JSONResponse:
    """R0.2.1：删除单篇文档——引擎文件先删，成功才删 PG 行，失败整体回滚。

    未登录 → 10001；越权/无效空间 → 30004；doc 不存在或不属于该空间 → 30004；
    引擎删除失败 → 错误信封（30002/502 等，PG 无残留）。
    200 {ok, docId, docs, assets}（assets=被连带清理的孤儿资产数，跨空间共享则不删）。

    补齐 F-2：此前文档零删除入口，与 F-1（单页 100 条上限）组合成删不掉+看不全的死锁。
    """
    counts = await svc.delete_doc(user_id, space_id, doc_id, kb)
    body = success(data={"ok": True, "docId": doc_id, **counts})
    return JSONResponse(status_code=200, content=body.model_dump())


@router.patch("/{space_id}/docs/{doc_id}")
async def patch_doc(
    space_id: str,
    doc_id: str,
    payload: PatchDocRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    svc: Annotated[SpaceService, Depends(get_space_service)],
) -> JSONResponse:
    """R0.2.2：人工纠偏文档分类（不改正文）。

    200 {docId, category}；分类取值不在规则版六类或空串 → 10005/422；
    越权/无效空间或 doc → 30004。

    语义边界：category 是资产级属性（跨空间共享），改写对本资产在其他空间的呈现
    一并生效；号主改文（hash 变化）会按新内容重算覆盖。
    """
    result = await svc.update_doc_category(user_id, space_id, doc_id, payload.category)
    body = success(data=result)
    return JSONResponse(status_code=200, content=body.model_dump())


# ------------------------------------------------------------------ R0.2.5 批量文档操作


class BatchDocIdsRequest(BaseModel):
    """R0.2.5：批量文档操作请求体（:delete / :recategorize 共用 ids 侧）。

    pydantic 层只做**体量硬闸**（1..500）；业务上限（默认 50，`batch_docs_max_ids`）
    在 SpaceService._normalize_doc_ids 内统一走错误信封（10005），
    与 BatchIngestRequest 同款双层闸，避免同一份校验规则在路由与服务两层漂移。
    """

    ids: list[str] = Field(min_length=1, max_length=500)


class BatchDocCategoryRequest(BatchDocIdsRequest):
    """R0.2.5：批量改分类请求体。category 仅接受规则版六类或空串（服务层 10005）。"""

    category: str = Field(default="", max_length=32)


@router.post("/{space_id}/docs:delete")
async def delete_docs_batch(
    space_id: str,
    payload: BatchDocIdsRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    svc: Annotated[SpaceService, Depends(get_space_service)],
    kb: Annotated[LangBotClient, Depends(get_langbot_client)],
) -> JSONResponse:
    """R0.2.5：批量删除文档（上限 50）——篇级部分成功，已删篇立即生效。

    200 {ok, requested, docs, assets, failed:[{docId, code, error}]}：failed 非空即部分成功
    （引擎侧失败篇的 PG 行完整保留，可原样重试）；全批失败 → 错误信封（30002/502 等）。
    越权/无效空间 → 30004；任一篇 doc 缺失或不属于该空间 → 30004（零副作用）；
    空批或超过单次上限 → 10005/422。

    补齐 F-2 收尾：单篇 DELETE 已销账删除入口，但数百篇空间需逐篇点删；
    批量端点与 F-1（服务端分页）配套，才真正解开「删不掉 + 看不全」的死锁。
    """
    counts = await svc.delete_docs(user_id, space_id, payload.ids, kb)
    body = success(data={"ok": True, **counts})
    return JSONResponse(status_code=200, content=body.model_dump())


@router.post("/{space_id}/docs:recategorize")
async def recategorize_docs_batch(
    space_id: str,
    payload: BatchDocCategoryRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    svc: Annotated[SpaceService, Depends(get_space_service)],
) -> JSONResponse:
    """R0.2.5：批量人工纠偏文档分类（上限 50）——整批原子，无「改了一半」中间态。

    200 {ok, requested, docs, category}；分类取值不在规则版六类或空串 → 10005/422；
    越权/无效空间或任一篇 doc 缺失 → 30004（全批不生效）。

    语义边界与单篇 PATCH 同：category 是资产级属性（跨空间共享），改写对本资产在
    其他空间的呈现一并生效；号主改文（hash 变化）会按新内容重算覆盖。
    """
    result = await svc.recategorize_docs(user_id, space_id, payload.ids, payload.category)
    body = success(data={"ok": True, **result})
    return JSONResponse(status_code=200, content=body.model_dump())


# ------------------------------------------------------------------ B-T8 知识库对接（v0.3g 备案形状）


class IngestDocRequest(BaseModel):
    url: str


class BatchIngestRequest(BaseModel):
    """T2.6.1：批量粘贴入库请求体（urls 已由前端 parseBatchUrls 拆行去重）。

    pydantic 层只做**体量硬闸**（1..500）；业务上限（默认 50，`batch_ingest_max_urls`）
    与 URL 形态校验在 BatchIngestService 内统一走错误信封（10005/10006），
    避免同一份校验规则在路由与服务两层漂移。
    """

    urls: list[str] = Field(min_length=1, max_length=500)


@router.post("/{space_id}/docs", status_code=202)
async def ingest_doc(
    space_id: str,
    payload: IngestDocRequest,
    _user_id: Annotated[str, Depends(get_current_user_id)],
    svc: Annotated[KnowledgeBaseService, Depends(get_kb_service)],
) -> JSONResponse:
    """提交文章 URL 入库（异步）：resolve→extract→score→LangBot ingest。

    v0.3g 备案：body 仅 {url}（直传 resolved/extracted 形状延后，见交付报告）；
    202 Accepted + {docId,title,status,langbotFileId,taskId}。
    """
    result = await svc.ingest_url(space_id, payload.url)
    body = success(data=result)
    return JSONResponse(status_code=202, content=body.model_dump())


@router.post("/{space_id}/docs:batch", status_code=202)
async def ingest_docs_batch(
    space_id: str,
    payload: BatchIngestRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """T2.6.1：批量粘贴提交（提交即返，同步阶段零网络抓取）。

    202 data={jobId,status,counts,reused,urlCount}：仅校验并建 Job(batch_ingest)
    + 逐篇 JobItem(PENDING)，逐篇抓取交 T2.3 JobWorker 异步消费（完整复用 T2.7
    五层幂等链，重复 URL 不重复入库）。
    未登录 → 10001；越权/无效空间 → 30004；空批或超上限 → 10005；
    非 http(s)/超长 URL → 10006。
    前端刷新后凭 jobId 经 GET /jobs/{id} 恢复进度（提交即返、进度不丢）；
    PARTIAL_SUCCESS 由 POST /jobs/{id}/retry 单篇重试（T2.3.3）。
    """
    svc = BatchIngestService(session)
    result = await svc.submit_batch(user_id, space_id, payload.urls)
    body = success(data=result)
    return JSONResponse(status_code=202, content=body.model_dump())


@router.get("/{space_id}/docs/{doc_id}/status")
async def get_doc_ingest_status(
    space_id: str,
    doc_id: str,
    _user_id: Annotated[str, Depends(get_current_user_id)],
    svc: Annotated[KnowledgeBaseService, Depends(get_kb_service)],
) -> JSONResponse:
    """ingest 状态查询：{docId,status,langbotFileId}（LangBot 权威状态回写本地）。

    status ∈ FETCHED|INDEXED|READY；FAILED → 30003/502。
    """
    result = await svc.get_doc_ingest_status(space_id, doc_id)
    body = success(data=result)
    return JSONResponse(status_code=200, content=body.model_dump())
