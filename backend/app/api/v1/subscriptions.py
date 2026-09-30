"""AB-P004 P2 整号订阅路由：sources/subscriptions/jobs 端点。

- POST /api/v1/sources {biz|profile_url}（登录保护 10001；uq_source_type_external 幂等）
- GET  /api/v1/sources?type=wechat_oa（登录保护；返回**全用户共享**源清单，非「我的信息源」）
- PATCH /api/v1/sources/{source_id}（R4.8；admin，改全局源展示名/上游地址）
- DELETE /api/v1/sources/{source_id}（R0.2.3；admin 且仅零下游引用可删）
- POST /api/v1/spaces/{id}/subscriptions {source_id, sync_policy}（幂等订阅）
- GET  /api/v1/spaces/{id}/subscriptions
- PATCH /api/v1/spaces/{id}/subscriptions/{sub_id}（R0.2.3；改策略/间隔）
- DELETE /api/v1/spaces/{id}/subscriptions/{sub_id}（R0.2.3；退订，软取消幂等）
- GET  /api/v1/jobs?type=&status=&limit=&offset=（R0.4.1；清单分页，type/status 为取值过滤）
- GET  /api/v1/jobs/{id}（Job 状态 + JobItem 进度，轮询用）
- POST /api/v1/jobs/{id}/retry（PARTIAL 场景 FAILED JobItem 单篇重试）
- POST /api/v1/jobs/{id}/cancel（R0.4.2；仅 QUEUED → CANCELLED，RUNNING 回当前 progress）

错误码：复用 20001/20002/20003/30003；整号级 30005（Job PARTIAL_SUCCESS 状态表达）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_sub, get_current_user_id, get_db, limit_offset_query, require_roles
from app.core.response import success
from app.models.entities import User
from app.repositories.job import JobRepository
from app.services.jobs import JobService
from app.services.subscription import SourceSubscriptionService

sources_router = APIRouter(prefix="/api/v1/sources", tags=["sources"])
subscriptions_router = APIRouter(prefix="/api/v1/spaces", tags=["subscriptions"])
jobs_router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


class RegisterSourceRequest(BaseModel):
    biz: str = Field(default="", max_length=128)
    profile_url: str = Field(default="", max_length=512)
    name: str = Field(default="", max_length=255)


class CreateSubscriptionRequest(BaseModel):
    source_id: str = Field(min_length=1, max_length=36)
    sync_policy: str = Field(default="auto", max_length=32)
    # 每天 HH 点触发（0..23，调度器时区口径）；省略 = 按间隔滑动。
    # 不加 Field(ge/le) 约束：越界须走服务层 10005 错误信封（与 sync_interval_minutes 同纪律），
    # 而不是被 pydantic 截成无 code 的裸 422。
    sync_anchor_hour: int | None = None


# ------------------------------------------------------------------ sources


@sources_router.post("")
async def register_source(
    payload: RegisterSourceRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """注册公众号 Source（biz 或 profile_url 二选一；幂等）。201 创建 / 200 已存在。"""
    svc = SourceSubscriptionService(session)
    result = await svc.register_source(user_id, biz=payload.biz, profile_url=payload.profile_url, name=payload.name)
    body = success(data=result)
    return JSONResponse(status_code=201, content=body.model_dump())


@sources_router.get("")
async def list_sources(
    sub: Annotated[str, Depends(get_current_sub)],
    session: Annotated[AsyncSession, Depends(get_db)],
    paging: Annotated[tuple[int, int], Depends(limit_offset_query)],
    type: Annotated[str, Query()] = "wechat_oa",
) -> JSONResponse:
    """GET /sources?type=wechat_oa → data.items（**全用户共享**源清单）。

    `sub` 只作登录闸门、不参与过滤：`sources` 表无 user_id 列
    （uq_source_type_external 按 type+external_id 全局去重），「我的信息源」无定义。
    旧实现把 user_id 透传给服务层却被忽略，属契约误导（F-23），参数已移除。
    C.1：LIMIT/OFFSET 下沉 service/repo SQL（原无分页，全量返回）。
    """
    limit, offset = paging
    svc = SourceSubscriptionService(session)
    items, total = await svc.list_sources(source_type=type, limit=limit, offset=offset)
    body = success(data={"items": items, "total": total, "limit": limit, "offset": offset})
    return JSONResponse(status_code=200, content=body.model_dump())


class PatchSourceRequest(BaseModel):
    """R4.8：全局源可调字段（部分更新，省略 = 不改）。type/external_id 不可写。"""

    name: str | None = Field(default=None, max_length=255)
    url: str | None = Field(default=None, max_length=512)


@sources_router.patch("/{source_id}")
async def update_source(
    source_id: str,
    payload: PatchSourceRequest,
    actor: Annotated[User, Depends(require_roles("admin"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """R4.8：admin 改全局源的展示名 / 上游地址（部分更新）。

    与 DELETE /sources/{id} 同口径收口到 admin：`sources` 无 user_id 列，改一条记录
    影响所有订阅该源的用户，属全局副作用，不给普通登录用户。
    type/external_id 不可写（uq_source_type_external 去重锚，改 = 删后重建并打断级联链）。

    200 {sourceId, biz, name, url}；无效 id → 30004/404；非 admin → 10004/403。
    """
    svc = SourceSubscriptionService(session)
    result = await svc.update_source(source_id, name=payload.name, url=payload.url)
    body = success(data=result)
    return JSONResponse(status_code=200, content=body.model_dump())


@sources_router.delete("/{source_id}")
async def delete_source(
    source_id: str,
    actor: Annotated[User, Depends(require_roles("admin"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """R0.2.3：删除信息源——仅当零下游引用（订阅 / 资产 / 清单三者皆空）。

    200 {sourceId, deleted, references}；仍有引用 → 10005/422（附引用计数与前置动作）；
    无效 id → 30004/404；非 admin → 10004/403。

    闸门为何是三者而非仅订阅：三张子表全是 ondelete=CASCADE，而 content_assets 又被
    knowledge_documents CASCADE 引用——只挡订阅会级联删掉资产与文档行。
    为何要 admin 而非「登录即可」：sources 表**没有 user_id 列**（按 type+external_id
    跨用户去重的全局资源），「我的信息源」无定义。零引用闸门挡住的是级联破坏，
    挡不住「删掉他人已注册但尚未订阅的源」这类全局副作用——故按治理动作收口到 admin。
    前端无任何调用点（grep 全仓零命中），收紧无回归。
    """
    svc = SourceSubscriptionService(session)
    result = await svc.delete_source(source_id)
    body = success(data=result)
    return JSONResponse(status_code=200, content=body.model_dump())


class PatchSubscriptionRequest(BaseModel):
    """R0.2.3：订阅可调字段（部分更新，省略 = 不改）。"""

    sync_policy: str | None = Field(default=None, max_length=32)
    sync_interval_minutes: int | None = None
    # 每天 HH 点触发（0..23，调度器时区口径）；显式传 null 清除锚定、回到滑动窗口。
    # 不加 Field(ge/le)：越界须走服务层 10005 错误信封，而非 pydantic 裸 422。
    sync_anchor_hour: int | None = None


# ------------------------------------------------------------------ subscriptions


@subscriptions_router.post("/{space_id}/subscriptions")
async def create_subscription(
    space_id: str,
    payload: CreateSubscriptionRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """订阅整号（幂等；首次建 Job(sync_account)）。201 创建 / 200 已订阅。

    越权/无效空间 → 30004；无效 source → 30004。
    """
    svc = SourceSubscriptionService(session)
    result = await svc.subscribe(
        user_id, space_id, payload.source_id, payload.sync_policy, payload.sync_anchor_hour
    )
    status_code = 201 if result.get("created") else 200
    body = success(data=result)
    return JSONResponse(status_code=status_code, content=body.model_dump())


@subscriptions_router.get("/{space_id}/subscriptions")
async def list_subscriptions(
    space_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
    paging: Annotated[tuple[int, int], Depends(limit_offset_query)],
) -> JSONResponse:
    """GET /spaces/{id}/subscriptions → data.items（号名/biz/同步策略/下次同步）。

    C.1：LIMIT/OFFSET 下沉 service/repo SQL（原无分页，全量返回）。
    """
    limit, offset = paging
    svc = SourceSubscriptionService(session)
    items, total = await svc.list_subscriptions(user_id, space_id, limit=limit, offset=offset)
    body = success(data={"items": items, "total": total, "limit": limit, "offset": offset})
    return JSONResponse(status_code=200, content=body.model_dump())


@subscriptions_router.patch("/{space_id}/subscriptions/{subscription_id}")
async def update_subscription(
    space_id: str,
    subscription_id: str,
    payload: PatchSubscriptionRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """R0.2.3：改同步策略 / 同步间隔 / 固定时点锚（部分更新，省略字段 = 不改）。

    200 {subscriptionId, syncPolicy, syncIntervalMinutes, syncAnchorHour, nextRunAt, status}；
    越权/无效空间或订阅 → 30004；策略取值非法或间隔/锚值越界 → 10005/422。

    间隔只可能把 next_run_at 往前拉（更频繁），绝不把已逾期的一次同步往后推；
    `sync_anchor_hour` 显式传 null = 清除锚定回到滑动窗口（省略 ≠ null）；
    已退订的订阅允许改值但不再重排 next_run_at。
    """
    svc = SourceSubscriptionService(session)
    # 显式传 null = 清除锚定；省略 = 不改。pydantic 对二者都落成 None，须看 model_fields_set。
    clear_anchor = "sync_anchor_hour" in payload.model_fields_set and payload.sync_anchor_hour is None
    result = await svc.update_subscription(
        user_id,
        space_id,
        subscription_id,
        sync_policy=payload.sync_policy,
        sync_interval_minutes=payload.sync_interval_minutes,
        sync_anchor_hour=payload.sync_anchor_hour,
        clear_anchor=clear_anchor,
    )
    body = success(data=result)
    return JSONResponse(status_code=200, content=body.model_dump())


@subscriptions_router.delete("/{space_id}/subscriptions/{subscription_id}")
async def cancel_subscription(
    space_id: str,
    subscription_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """R0.2.3：退订（软取消，幂等）。

    200 {subscriptionId, syncPolicy, syncIntervalMinutes, nextRunAt, status, cancelled}；
    越权/无效空间或订阅 → 30004。

    只置 status=CANCELLED + next_run_at=None，**不删除任何文档/资产/清单**——
    退订是「停止未来同步」，已入库内容的删除走单篇 / 批量端点（语义不同）。
    幂等：已退订 → 200 且 cancelled=False。
    """
    svc = SourceSubscriptionService(session)
    result = await svc.cancel_subscription(user_id, space_id, subscription_id)
    body = success(data=result)
    return JSONResponse(status_code=200, content=body.model_dump())


# ------------------------------------------------------------------ jobs


@jobs_router.get("")
async def list_jobs(
    user_id: Annotated[str, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
    type_: Annotated[str | None, Query(alias="type")] = None,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JSONResponse:
    """GET /jobs：Job 清单分页（R0.4.1）。

    data: {items[{jobId,type,status,progress,error,workerHeartbeatAt,createdAt,updatedAt}],
           total, limit, offset}
    `type`/`status` 是**取值过滤**而非域校验：未知取值返空列表（读路径不设校验闸门）。
    limit/offset 是资源约束（防大页 DoS），不是领域规则。
    """
    svc = JobService(JobRepository(session), session)
    result = await svc.list_job_views(user_id, status=status, job_type=type_, limit=limit, offset=offset)
    body = success(data=result)
    return JSONResponse(status_code=200, content=body.model_dump())


@jobs_router.get("/{job_id}")
async def get_job(
    job_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """GET /jobs/{id}：Job 状态 + JobItem 进度（轮询 5s）。

    data: {jobId, type, status, progress, error, counts{total,succeeded,failed,pending}, createdAt}
    他人/无效 job → 30004。
    """
    svc = SourceSubscriptionService(session)
    result = await svc.get_job_view(user_id, job_id)
    body = success(data=result)
    return JSONResponse(status_code=200, content=body.model_dump())


@jobs_router.post("/{job_id}/retry")
async def retry_job(
    job_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """POST /jobs/{id}/retry：FAILED JobItem 单篇重试（PARTIAL_SUCCESS 场景）。

    data: {jobId, retried, status}；全 SUCCEEDED → retried=0 不报错（幂等）。
    """
    svc = SourceSubscriptionService(session)
    result = await svc.retry_job(user_id, job_id)
    body = success(data=result)
    return JSONResponse(status_code=200, content=body.model_dump())


@jobs_router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """POST /jobs/{id}/cancel（R0.4.2）：仅 QUEUED 可取消 → CANCELLED。

    data: {jobId, type, status, progress, error, workerHeartbeatAt, createdAt, updatedAt}
    RUNNING → 30005（message 带当前 progress）；终态 → 30005；他人/无效 job → 30004。
    """
    svc = JobService(JobRepository(session), session)
    result = await svc.cancel_job(user_id, job_id)
    body = success(data=result)
    return JSONResponse(status_code=200, content=body.model_dump())
