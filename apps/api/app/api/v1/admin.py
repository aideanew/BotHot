"""M3 后台管理路由族（SPEC-M3 批次 2/3/4/5，A-2 叠加裁定 2026-09-23）。

A-2：既有用户端点（/api/v1/spaces、/api/v1/sources）一律不动——admin 的跨用户
能力全部走本模块新增端点，既有契约零回归。授权统一经 deps.require_roles →
services.roles.require_role（单一来源，禁在路由层散落 role 判断）；服务层方法
不做角色校验，只做数据操作。

批次 3（T5.4）：引擎 Key 登记（operator+）。写侧为 operator 可登记 Key；
读侧的引擎全景由既有 GET /api/v1/engines 承担（登录即可见），故不在 admin 域
重复一个更窄的只读端点。

批次 4（T5.7）：批量文档操作授权收口（admin）。既有 POST /spaces/{id}/docs:delete
与 docs:recategorize 强制本人空间，本批新增跨用户变体；共用 Service 的单一实现，
仅放开归属判据。「doc 属于所给空间」是数据事实校验，不随之放宽。
T5.6 计费预留按管理者裁定**不建任何计费面**（无表、无消费者；建写入面即第二个
BotBinding 死表），登记为独立开放项。

批次 5（T6.2）：推送通道注册表 + 推送触发（operator+）。**诚实占位**
（2026-09-23 管理者裁定）：两个通道都落接口与注册表，但都不实接，故本批
**从不返回 200 假成功**——通道未就绪即转 50002（依赖不可用），带通道名与
拒绝原因。

批次 2 读面（2026-09-23 管理者裁定补齐）：GET /admin/spaces 与 GET /admin/spaces/{id}/docs。
批次 2 竣工时 SPEC 登记「文章列表/分类/状态端点亦在，仅剩前端浏览视图」——**失实**：
既有读端点的归属判据硬拒绝他人空间，本模块此前八条路径全是写面、零读面，
批量端点要 doc_id 却无任何路径可列出别人的 doc。「仅剩前端」把「端点存在」当成了
「能力可用」，与 §六 compose.prod 锚点失实同类，已一并更正。

批次 6 / R4.8（2026-09-23）：作业与订阅的跨用户读面——GET /admin/jobs、
GET /admin/jobs/{id}、GET /admin/subscriptions。缺口与批次 2 读面同源：
jobs/subscriptions 的既有读端点全带本人归属谓词，admin 无法回答
「全系统哪条号卡住了 / 谁在跑同步」。信息源清单**不**在此重复：`sources` 无
user_id 列，既有 GET /api/v1/sources 本就是全用户共享清单（登录即可见），
再加一个 /admin/sources 只是同一份数据的第二条路径。

R7.4（2026-09-24）：Admin 能力补全——Job 取消/重试、Subscription admin 侧取消、
Sources admin 读面与删除。补齐 R4.8 仅读面而缺操作性这一缺口。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_db,
    get_job_service,
    get_langbot_client,
    get_space_service,
    limit_offset_query,
    require_roles,
)
from app.api.v1.spaces import BatchDocCategoryRequest, BatchDocIdsRequest, PatchSpaceRequest
from app.core.cache import get_or_set
from app.core.config import get_settings
from app.core.engine_keyring import KEYABLE_ENGINES, master_key, resolve_engine_key
from app.core.errors import DependencyUnavailableError
from app.core.response import success
from app.models.entities import User
from app.providers.discovery.registry import describe_channels
from app.providers.langbot.client import LangBotClient
from app.providers.push import registered_channels
from app.services.engine_keys import EngineKeyService
from app.services.jobs import JobService
from app.services.process_heartbeat import DEFAULT_MAX_AGE_SECONDS, describe_liveness
from app.services.push import PushService
from app.services.spaces import SpaceService, SpaceValidationError
from app.services.subscription import SourceSubscriptionService

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


async def _wrap(value: Any) -> Any:
    """把同步值包装为协程，供 cache.get_or_set 的 loader（同步注册表读）。"""
    return value


@router.patch("/spaces/{space_id}", summary="跨用户管理操作：改空间简介")
async def admin_update_space(
    space_id: str,
    payload: PatchSpaceRequest,
    actor: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[SpaceService, Depends(get_space_service)],
) -> JSONResponse:
    """M3 批次 2（T5.3，A-2）：admin 跨用户改空间简介。

    与 PATCH /api/v1/spaces/{id} 的差异仅在授权：既有端点强制
    space.user_id == 本人，本端点绕过归属校验。既有端点保持不动。

    契约：description 必填（本端点唯一可写字段，null 即可写内容缺失）→ 10005；
    取值非法（超长/控制字符）→ 10005；无效空间 → 30004（404，不泄露存在性）。
    未登录 → 10001；非 admin → 10004/403。

    响应为写回执而非空间详情视图（详情视图带本人归属语义，跨用户取视图另议），
    形状 {ok, id, description}。
    """
    if payload.description is None:
        raise SpaceValidationError("description 必填")
    result = await svc.update_space_any(space_id, payload.description)
    body = success(data={"ok": True, **result})
    return JSONResponse(status_code=200, content=body.model_dump())


@router.delete("/spaces/{space_id}/docs/{doc_id}", summary="跨用户管理操作：删单篇文档")
async def admin_delete_doc(
    space_id: str,
    doc_id: str,
    actor: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[SpaceService, Depends(get_space_service)],
    kb: Annotated[LangBotClient, Depends(get_langbot_client)],
) -> JSONResponse:
    """M3 批次 2（T5.3，A-2）：admin 跨用户删单篇文档。

    与 DELETE /api/v1/spaces/{id}/docs/{doc_id} 的差异仅在授权：既有端点强制
    本人空间，本端点绕过归属校验。引擎文件先删 → 成功才删 PG 行 → 失败整体
    回滚，顺序与既有端点完全一致（共用 SpaceService._delete_doc 单一实现）。

    未登录 → 10001；非 admin → 10004/403；无效空间 / doc 不存在或不属于该
    空间 → 30004；引擎删除失败 → 错误信封（30002/502 等，PG 无残留）。
    200 {ok, docId, docs, assets}（assets=被连带清理的孤儿资产数）。
    """
    counts = await svc.delete_doc_any(space_id, doc_id, kb)
    body = success(data={"ok": True, "docId": doc_id, **counts})
    return JSONResponse(status_code=200, content=body.model_dump())


@router.delete("/spaces/{space_id}", summary="跨用户管理操作：删空间（级联）")
async def admin_delete_space(
    space_id: str,
    actor: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[SpaceService, Depends(get_space_service)],
    kb: Annotated[LangBotClient, Depends(get_langbot_client)],
) -> JSONResponse:
    """M3 批次 2（T5.8，A-2 叠加）：admin 跨用户删空间。

    与 DELETE /api/v1/spaces/{id} 的差异仅在授权：既有端点强制 space.user_id == 本人，
    本端点绕过归属校验。引擎删库先行、失败整体回滚、级联删 docs/assets/space 行
    （跨空间共享资产因 NOT EXISTS 孤儿判定不被误删）——全部走
    SpaceService._delete_space 单一实现，既有端点保持不动（A-2 裁定：零回归）。

    未登录 → 10001；非 admin → 10004/403；无效空间 → 30004（404，不泄露存在性）；
    引擎删库失败 → 错误信封（30002/502 等，PG 无残留）。
    200 {ok, docs, assets, spaces}——返回级联删除计数，admin 操作应可见影响面。
    """
    counts = await svc.delete_space_any(space_id, kb)
    body = success(data={"ok": True, **counts})
    return JSONResponse(status_code=200, content=body.model_dump())


# ------------------------------------------------------------------ 批次 2 读面（2026-09-23 管理者裁定补齐）
#
# 批次 2 竣工时登记「文章列表/分类/状态端点亦在，仅剩前端浏览视图」——失实。
# 既有读端点（GET /spaces、GET /spaces/{id}/docs）的归属判据硬拒绝他人空间，
# admin 域此前八条路径全是写面、零读面：批量端点要 doc_id，而没有任何路径能列出
# 别人的 doc。读面缺位即「端点存在」被当成了「能力可用」，与 compose.prod 锚点失实同类。


@router.get("/spaces", summary="跨用户管理操作：空间清单")
async def admin_list_spaces(
    actor: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[SpaceService, Depends(get_space_service)],
    paging: Annotated[tuple[int, int], Depends(limit_offset_query)],
) -> JSONResponse:
    """M3 批次 2（T5.2/T5.3 读面）：admin 跨用户空间清单，每条带归属。

    data.items 与 GET /api/v1/spaces 同形（id/name/description/docCount/updatedAt/
    engine/engineKbId/isPublic），增量三字段 ownerId/ownerSub/ownerNickname 表示归属账号。
    本人端点不带这三字段——admin 端点单独存在，既有契约零回归。
    归属随空间单次 JOIN 取得（逐空间查 owner 会是 N+1，doc 计数同类缺陷 T1.5.3 已修过）。

    C.1：LIMIT/OFFSET 下沉 service/repo SQL（路由层切片已移除）。

    未登录 → 10001；非 admin → 10004/403。
    """
    limit, offset = paging
    items, total = await svc.list_space_views_any(limit=limit, offset=offset)
    body = success(data={"items": items, "total": total, "limit": limit, "offset": offset})
    return JSONResponse(status_code=200, content=body.model_dump())


@router.get("/spaces/{space_id}/docs", summary="跨用户管理操作：空间文档清单")
async def admin_list_space_docs(
    space_id: str,
    actor: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[SpaceService, Depends(get_space_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    category: Annotated[str | None, Query(max_length=32)] = None,
) -> JSONResponse:
    """M3 批次 2（T5.3 读面）：admin 跨用户文档清单——批量操作面板的目标来源。

    形状与 GET /api/v1/spaces/{id}/docs 完全一致（items/total/limit/offset；
    status∈pending|ready|failed；category 含 `__uncategorized__` 哨兵语义），分页与
    过滤谓词共用 SpaceService._list_space_docs 单一实现，故 total 不会虚高。
    既有端点保持不动。

    与写面同口径：无效空间 → 30004（404），不校验存在性会让「空间不存在」与
    「空间为空」无法区分。未登录 → 10001；非 admin → 10004/403。
    """
    items, total = await svc.list_space_docs_any(
        space_id, limit=limit, offset=offset, category=category
    )
    body = success(data={"items": items, "total": total, "limit": limit, "offset": offset})
    return JSONResponse(status_code=200, content=body.model_dump())


# ------------------------------------------------------------------ 批次 6 / R4.8 作业与订阅跨用户读面
#
# 既有 jobs/subscriptions 读端点全部带本人归属谓词（GET /jobs 只列本人 Job，
# GET /spaces/{id}/subscriptions 先校验 space.user_id == 本人）。admin 无法回答
# 「全系统哪条号卡住了 / 谁在跑同步」，与批次 2 读面缺位同源。


@router.get("/jobs", summary="跨用户管理操作：Job 清单")
async def admin_list_jobs(
    actor: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[JobService, Depends(get_job_service)],
    type_: Annotated[str | None, Query(alias="type")] = None,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    """R4.8（A-2 叠加）：admin 跨用户 Job 清单——不按 user_id 过滤。

    形状与 GET /api/v1/jobs 一致（items/total/limit/offset；`type`/`status` 为取值
    过滤，limit/offset 为资源约束）；每条带 ownerId（JobService._view 统一产出）。
    分页、排序、total 谓词共用 JobService.list_job_views 单一实现，
    故 total 不会因跨用户口径而虚高。既有端点保持不动。

    未登录 → 10001；非 admin → 10004/403。
    """
    result = await svc.list_job_views_any(
        status=status, job_type=type_, limit=limit, offset=offset
    )
    body = success(data=result)
    return JSONResponse(status_code=200, content=body.model_dump())


@router.get("/jobs/{job_id}", summary="跨用户管理操作：Job 详情")
async def admin_get_job(
    job_id: str,
    actor: Annotated[User, Depends(require_roles("admin"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """R4.8（A-2 叠加）：admin 跨用户查 Job 详情（含 JobItem counts 与 error 文本）。

    跨用户排障「这条号为什么卡住」必须能看到子任务级进度与失败原因，而既有
    GET /api/v1/jobs/{id} 对他人 Job 一律 30004——无法区分「不存在」与「无权」。

    data: {jobId, type, status, progress, error, counts{total,succeeded,failed,pending},
           createdAt}
    无效 id → 30004/404；未登录 → 10001；非 admin → 10004/403。
    """
    svc = SourceSubscriptionService(session)
    result = await svc.get_job_view_any(job_id)
    body = success(data=result)
    return JSONResponse(status_code=200, content=body.model_dump())


@router.get("/subscriptions", summary="跨用户管理操作：订阅清单")
async def admin_list_subscriptions(
    actor: Annotated[User, Depends(require_roles("admin"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    paging: Annotated[tuple[int, int], Depends(limit_offset_query)],
    space_id: Annotated[str | None, Query()] = None,
) -> JSONResponse:
    """R4.8（A-2 叠加）：admin 跨用户订阅清单。

    space_id 省略 → 全系统所有空间的订阅（既有端点强制本人空间，无法表达跨空间视图，
    而「为什么这条号没人同步」必须跨空间看）；给定 space_id → 仅该空间，不做归属校验。

    形状与 GET /api/v1/spaces/{id}/subscriptions 一致，每条带 spaceId/spaceName/
    ownerId/ownerNickname 表示归属（既有端点不带归属字段，admin 端点单独存在）。
    归属信息经单次批量查询取得，不逐条 get（与 spaces 域 T1.5.3 同口径）。

    C.1：LIMIT/OFFSET 下沉 service/repo SQL（路由层切片已移除）。

    给定不存在的 space_id → 30004/404（不校验存在性会让「空间不存在」与「空间无订阅」
    无法区分）；未登录 → 10001；非 admin → 10004/403。
    """
    limit, offset = paging
    svc = SourceSubscriptionService(session)
    items, total = await svc.list_subscriptions_any(space_id=space_id, limit=limit, offset=offset)
    body = success(data={"items": items, "total": total, "limit": limit, "offset": offset})
    return JSONResponse(status_code=200, content=body.model_dump())


# ------------------------------------------------------------------ 批次 3 / T5.4 引擎 Key 登记

class RegisterEngineKeyRequest(BaseModel):
    key: str = Field(min_length=1, max_length=1024, description="引擎 API Key 明文（仅用于加密落库）")


@router.get("/engines/keys")
async def admin_list_engine_keys(
    actor: Annotated[User, Depends(require_roles("operator"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """M3 批次 3（T5.4）：operator 查引擎 Key 登记状态（不含明文）。

    每个可登记引擎位回报三件事：是否已登记、当前生效来源（env / registered）、
    以及登记行元数据。envConfigured 表示「仅凭 env 是否已配置」，
    configured 表示「登记表 + env 合并后是否已配置」——两者可比，
    登记覆盖 env 因此是可见的，不是静默的。

    masterKeyConfigured=false 表示 ENGINE_KEY_MASTER_KEY 未配置：此时登记接口
    会 50002 拒绝，本列表仍可用（只反映 env 侧）。
    未登录 → 10001；非 operator/admin → 10004/403。
    """
    try:
        master_key()
        master_ok = True
    except DependencyUnavailableError:
        master_ok = False

    loaded = await EngineKeyService(session).load()
    settings = get_settings()
    by_engine = {str(m["engine"]): m for m in loaded.rows}
    items: list[dict[str, object]] = []
    for engine in KEYABLE_ENGINES:
        row = by_engine.get(engine)
        items.append(
            {
                "engine": engine,
                "registered": row is not None,
                "configured": resolve_engine_key(engine, settings, loaded.plaintext).configured,
                "activeSource": resolve_engine_key(engine, settings, loaded.plaintext).source,
                "envConfigured": resolve_engine_key(engine, settings).configured,
                "decryptFailed": bool(engine in loaded.decrypt_bad),
                "keyEnv": resolve_engine_key(engine, settings).env_var,
                "keyId": (row or {}).get("keyId", ""),
                "registeredBy": (row or {}).get("registeredBy", ""),
                "updatedAt": (row or {}).get("updatedAt", ""),
            }
        )

    body = success(data={"masterKeyConfigured": master_ok, "items": items})
    return JSONResponse(status_code=200, content=body.model_dump())


@router.post("/engines/keys/{engine}")
async def admin_register_engine_key(
    engine: str,
    payload: RegisterEngineKeyRequest,
    actor: Annotated[User, Depends(require_roles("operator"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """M3 批次 3（T5.4）：operator 登记/覆盖引擎 Key（AES-256-GCM 加密落库）。

    同一引擎位重复登记 = 覆盖（一行一引擎位，key_id 换新）。明文不落库、
    不回显——响应只给 keyId 作为轮换句柄。

    builtin → 10005（内置引擎无 Key）；未知引擎位 → 10005；空 Key/控制字符 → 10005；
    ENGINE_KEY_MASTER_KEY 未配置或畸形 → 50002（绝不回落明文）；
    未登录 → 10001；非 operator/admin → 10004/403。
    """
    result = await EngineKeyService(session).register(actor.id, engine, payload.key)
    body = success(data={"ok": True, **result})
    return JSONResponse(status_code=200, content=body.model_dump())


@router.delete("/engines/keys/{engine}")
async def admin_revoke_engine_key(
    engine: str,
    actor: Annotated[User, Depends(require_roles("operator"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """M3 批次 3（T5.4）：operator 撤销引擎 Key 登记（回落 env；env 亦空则不可用）。

    无登记行 → 30004（不谎报已撤销）；未登录 → 10001；非 operator/admin → 10004/403。
    """
    result = await EngineKeyService(session).revoke(actor.id, engine)
    body = success(data={"ok": True, **result})
    return JSONResponse(status_code=200, content=body.model_dump())


# ------------------------------------------------------------------ 批次 4 / T5.7 批量文档操作

@router.post("/spaces/{space_id}/docs:delete", summary="跨用户管理操作：批量删文档")
async def admin_delete_docs_batch(
    space_id: str,
    payload: BatchDocIdsRequest,
    actor: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[SpaceService, Depends(get_space_service)],
    kb: Annotated[LangBotClient, Depends(get_langbot_client)],
) -> JSONResponse:
    """M3 批次 4（T5.7，A-2）：admin 跨用户批量删文档（单次上限 50）。

    与 POST /api/v1/spaces/{id}/docs:delete 的差异仅在授权：既有端点强制本人空间，
    本端点绕过归属校验。共用 SpaceService._delete_docs 单一实现，篇级部分成功、
    两阶段切分（引擎先行）、逐篇提交、全批失败上抛首个异常全部不变；既有端点保持不动。

    200 {ok, requested, docs, assets, failed:[{docId, code, error}]}：failed 非空即
    部分成功（引擎侧失败篇的 PG 行完整保留，可原样重试）；全批失败 → 错误信封
    （30002/502 等，避免「200 但一篇都没删」被误读为成功）。

    空批/超上限 → 10005/422；无效空间或任一篇 doc 缺失或不属于该空间 → 30004
    （零副作用，发生在任何引擎调用之前）；未登录 → 10001；非 admin → 10004/403。

    「doc 属于所给空间」是数据事实校验，不随 admin 跨用户授权放宽——否则可凭任意
    doc_id 越界批量删除。
    """
    counts = await svc.delete_docs_any(space_id, payload.ids, kb)
    body = success(data={"ok": True, **counts})
    return JSONResponse(status_code=200, content=body.model_dump())


@router.post("/spaces/{space_id}/docs:recategorize", summary="跨用户管理操作：批量改分类")
async def admin_recategorize_docs_batch(
    space_id: str,
    payload: BatchDocCategoryRequest,
    actor: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[SpaceService, Depends(get_space_service)],
) -> JSONResponse:
    """M3 批次 4（T5.7，A-2）：admin 跨用户批量改文档分类（单次上限 50）。

    与 POST /api/v1/spaces/{id}/docs:recategorize 的差异仅在授权；共用
    SpaceService._recategorize_docs 单一实现，整批原子、先校验后取行、category 的
    **资产级**生效范围（对本资产在其他空间的呈现一并生效）全部不变；既有端点保持不动。

    200 {ok, requested, docs, category}；取值不在规则版六类或空串 → 10005/422；
    空批/超上限 → 10005/422；无效空间或任一篇 doc 缺失或不属于该空间 → 30004
    （全批不生效，无「改了一半」中间态）；未登录 → 10001；非 admin → 10004/403。
    """
    result = await svc.recategorize_docs_any(space_id, payload.ids, payload.category)
    body = success(data={"ok": True, **result})
    return JSONResponse(status_code=200, content=body.model_dump())


# ------------------------------------------------------------------ 批次 5 / T6.2 推送通道

class PushRequest(BaseModel):
    """推送请求。channel/external_user_id 必填；space_id/doc_id/message 至少一项非空。

    约束全部在 PushService 内做（带可读错误信息与 strip），pydantic 层不设
    min/max——否则会以「请求参数校验失败: [...]」的通用文案先截断。
    """

    channel: str
    external_user_id: str
    space_id: str = ""
    doc_id: str = ""
    message: str = ""


@router.get("/push/channels", summary="推送通道清单")
async def admin_list_push_channels(
    actor: Annotated[User, Depends(require_roles("operator"))],
) -> JSONResponse:
    """M3 批次 5（T6.2）：operator 查推送通道就绪度（注册表全景）。

    每个通道回报 implemented（接口在位、投递是否实接）与 reason（未实接时的
    拒绝原因）。加这个读侧是因为能力就绪度不该只能靠试推撞出 50002 才知道
    ——同 T5.4 的 masterKeyConfigured / activeSource 显式回报纪律。

    未登录 → 10001；非 operator/admin → 10004/403。
    C.4：注册表为代码静态（无写路径），走读缓存 TTL=300s（Redis 不可达直穿）。
    """
    channels = await get_or_set(
        "admin:push:channels", 300, lambda: _wrap(registered_channels())
    )
    body = success(data={"channels": channels})
    return JSONResponse(status_code=200, content=body.model_dump())


@router.get("/discovery/channels", summary="发现渠道就绪度")
async def admin_list_discovery_channels(
    actor: Annotated[User, Depends(require_roles("operator"))],
) -> JSONResponse:
    """R7.6：operator 查发现渠道就绪度（注册表全景 + 当前默认渠道解析结果）。

    发现渠道由后台配置（`discovery_channels` 启用白名单 + `discovery_default_channel`），
    此处回报每个渠道的 implemented（代码实接）/ enabled（在白名单内）/ available
    （凭据就位）与 reason（当前不可用的具体原因）。三者刻意不合并成单一布尔——
    否则「功能没做」和「功能没配」无法区分，配置缺失会被伪装成渠道故障。

    `defaultChannel=null` 即「本轮调度不做发现、仅按既有清单 Diff」，与调度器的跳过
    日志同源，不必翻日志才能判断。沿用 `push/channels` 的显式回报纪律。

    未登录 → 10001；非 operator/admin → 10004/403。
    C.4：注册表+配置读，走读缓存 TTL=120s（Redis 不可达直穿）。
    """
    channels = await get_or_set(
        "admin:discovery:channels", 120, lambda: _wrap(describe_channels(get_settings()))
    )
    body = success(data=channels)
    return JSONResponse(status_code=200, content=body.model_dump())


@router.get("/ops/liveness", summary="常驻进程存活")
async def admin_ops_liveness(
    actor: Annotated[User, Depends(require_roles("operator"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    max_age_seconds: Annotated[int, Query(ge=10, le=3600)] = DEFAULT_MAX_AGE_SECONDS,
) -> JSONResponse:
    """R7.7：operator 查 scheduler / worker 到底在不在跑（读 `process_heartbeats`）。

    把「后台健康」与「采集在跑」分开的唯一读侧：backend 健康检查全绿时，
    scheduler / worker 可能整个从未启动——2026-09-28 实测，三服务 2026-09-23
    才进 compose、栈建于 2026-09-08，而 `docker restart` 无法创建容器，
    结果静默失效 5 天无人察觉。

    `lastHeartbeatAt=null` 与「有值但很久没更新」是**两种不同故障**，处置不同：
    前者=进程从未启动（`docker compose up -d`），后者=启动后卡死（查进程日志）。
    故按 `EXPECTED_PROCESSES` 全景回报、缺失也占位——只回报「已有行」会让缺进程
    查不出来，那就把这次要防的盲区又原样造了一遍。

    未登录 → 10001；非 operator/admin → 10004/403。
    """
    snap = await describe_liveness(session, max_age_seconds=max_age_seconds)
    body = success(data=snap)
    return JSONResponse(status_code=200, content=body.model_dump())


@router.post("/push", summary="跨用户管理操作：触发推送")
async def admin_push(
    payload: PushRequest,
    actor: Annotated[User, Depends(require_roles("operator"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """M3 批次 5（T6.2）+ R7.5.4：operator 触发一次推送（按 space/doc 或自由正文）。

    本批诚实占位：校验全落地、投递未实接。通道未就绪时返回 200 + delivered=False +
    reason（R7.5.4 修正：不再抛 503，让调用方可读回执而不是撞异常）。

    校验顺序 通道 → 内容 → 目标，任一失败无副作用：未知通道 → 10005；
    空目标/空内容/超长/控制字符 → 10005；空间或文档不存在、文档不属于该
    空间 → 30004。
    未登录 → 10001；非 operator/admin → 10004/403。

    A-2 口径：operator 以上可代用户操作，故不做归属校验；但「文档属于所给
    空间」是数据事实校验，不随之放宽。
    """
    result = await PushService(session).push(
        payload.channel,
        payload.external_user_id,
        payload.space_id,
        payload.doc_id,
        payload.message,
    )
    if not result.delivered:
        body = success(data={
            "ok": False,
            "channel": result.channel,
            "delivered": False,
            "reason": result.reason,
        })
        return JSONResponse(status_code=200, content=body.model_dump())
    body = success(data={"ok": True, "channel": result.channel, "delivered": True})
    return JSONResponse(status_code=200, content=body.model_dump())


# ------------------------------------------------------------------ R7.4 Admin 操作性补全
#
# R4.8 仅补了跨用户读面（GET /admin/jobs、GET /admin/subscriptions），操作性为零——
# admin 看到「卡住的 Job」却无法取消/重试、看到「异常订阅」却无法退订。本批补齐。


@router.post("/jobs/{job_id}:cancel", summary="跨用户管理操作：取消 Job")
async def admin_cancel_job(
    job_id: str,
    actor: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[JobService, Depends(get_job_service)],
) -> JSONResponse:
    """R7.4.1：admin 跨用户取消 Job（仅 QUEUED → CANCELLED）。

    与 POST /api/v1/jobs/{id}/cancel 的差异仅在授权：既有端点强制 job.user_id == 本人，
    本端点绕过归属校验。状态机语义不变：RUNNING 拒绝取消（已投入执行的作业不半途作废），
    终态同理拒绝。

    200 {ok, jobId, status, ...}；RUNNING → 10005（附当前进度）；终态 → 10005；
    无效 id → 30004/404；未登录 → 10001；非 admin → 10004/403。
    """
    result = await svc.cancel_job_any(job_id)
    body = success(data={"ok": True, **result})
    return JSONResponse(status_code=200, content=body.model_dump())


@router.post("/jobs/{job_id}:retry", summary="跨用户管理操作：重试 Job")
async def admin_retry_job(
    job_id: str,
    actor: Annotated[User, Depends(require_roles("admin"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """R7.4.2：admin 跨用户重试终态 Job（FAILED/CANCELLED/PARTIAL_SUCCESS → 新 Job）。

    不原地复活旧 Job（状态机单向），而是基于旧 Job 的 type 与参数创建新 Job。
    旧 Job 保留作为审计记录（status 不变），新 Job 以 `retried_from` 关联旧 Job。

    batch_ingest：按旧 Job 的 space_id + fingerprint 重建；sync_account：按旧 Job
    的 subscription_id 重建。两者均走既有 submit_batch / run_incremental_sync 单一实现。

    200 {ok, oldJobId, newJobId, type}；非终态 → 10005；无效 id → 30004/404；
    未登录 → 10001；非 admin → 10004/403。
    """
    svc = SourceSubscriptionService(session)
    result = await svc.retry_job_any(job_id)
    body = success(data={"ok": True, **result})
    return JSONResponse(status_code=200, content=body.model_dump())


@router.delete("/subscriptions/{subscription_id}", summary="跨用户管理操作：退订")
async def admin_cancel_subscription(
    subscription_id: str,
    actor: Annotated[User, Depends(require_roles("admin"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """R7.4.3：admin 跨用户退订（软取消，幂等）。

    与 DELETE /api/v1/spaces/{id}/subscriptions/{sub_id} 的差异仅在授权：既有端点强制
    归属校验（_get_owned_subscription），本端点绕过。退订语义不变：
    status=CANCELLED + next_run_at=None，不删除任何文档/资产/清单。

    200 {ok, subscriptionId, cancelled}；无效 id → 30004/404；
    未登录 → 10001；非 admin → 10004/403。
    """
    svc = SourceSubscriptionService(session)
    result = await svc.cancel_subscription_any(subscription_id)
    body = success(data={"ok": True, **result})
    return JSONResponse(status_code=200, content=body.model_dump())


@router.get("/sources", summary="跨用户管理操作：来源清单含引用计数")
async def admin_list_sources(
    actor: Annotated[User, Depends(require_roles("admin"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    paging: Annotated[tuple[int, int], Depends(limit_offset_query)],
    type_: Annotated[str | None, Query(alias="type")] = None,
) -> JSONResponse:
    """R7.4.4：admin 信息源清单（含引用计数）。

    既有 GET /api/v1/sources 不带引用计数（面向用户，不需要）；admin 需要知道
    「这个源有多少订阅/资产/清单」来决策是否可安全删除，故本端点增量三字段：
    subscriptionCount / assetCount / manifestCount。

    无归属过滤（sources 无 user_id 列，本就是全局资源）。type 过滤可选。
    C.1：LIMIT/OFFSET 下沉 service/repo SQL（路由层切片已移除）。
    未登录 → 10001；非 admin → 10004/403。
    """
    limit, offset = paging
    svc = SourceSubscriptionService(session)
    items, total = await svc.list_sources_with_counts(source_type=type_, limit=limit, offset=offset)
    body = success(data={"items": items, "total": total, "limit": limit, "offset": offset})
    return JSONResponse(status_code=200, content=body.model_dump())


@router.delete("/sources/{source_id}", summary="跨用户管理操作：删除来源")
async def admin_delete_source(
    source_id: str,
    actor: Annotated[User, Depends(require_roles("admin"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """R7.4.5：admin 删除信息源（仅当零下游引用）。

    与 DELETE /api/v1/sources/{id} 完全共用 SourceSubscriptionService.delete_source
    单一实现（零引用闸门 + CASCADE 链保护），既有端点保持不动。
    注：既有端点已在 admin 角色闸门后（R4.8 收口），本端点为 admin 域的显式路径。

    200 {sourceId, deleted, references}；仍有引用 → 10005/422；
    无效 id → 30004/404；未登录 → 10001；非 admin → 10004/403。
    """
    svc = SourceSubscriptionService(session)
    result = await svc.delete_source(source_id)
    body = success(data={"ok": True, **result})
    return JSONResponse(status_code=200, content=body.model_dump())
