"""BotHot 渠道管理与推送 API。

提供完整的 CRUD + 测试推送 + 推送日志查询 + 推送任务管理：
- POST   /api/v1/bots              创建渠道
- GET    /api/v1/bots              列表
- GET    /api/v1/bots/{id}         详情
- PUT    /api/v1/bots/{id}         更新
- DELETE /api/v1/bots/{id}         删除（软删除）
- POST   /api/v1/bots/{id}/test    测试推送
- GET    /api/v1/bots/{id}/logs    推送日志
- GET    /api/v1/bots/channels     可用渠道类型
- POST   /api/v1/bots/tasks        创建推送任务
- GET    /api/v1/bots/tasks        列表
- PUT    /api/v1/bots/tasks/{id}   编辑推送任务
- DELETE /api/v1/bots/tasks/{id}   删除（软删除）
- POST   /api/v1/bots/tasks/{id}/run  手动触发
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_sub, get_db, record_audit_actor, require_roles
from app.core.errors import (
    ForbiddenError,
    RequestInvalidError,
    ResourceNotFoundError,
)
from app.core.response import success
from app.core.secret_crypto import (
    decrypt_channel_secret,
    decrypt_extra_config,
    encrypt_channel_secret,
    encrypt_extra_config,
)
from app.models.base import gen_uuid
from app.models.bothot_entities import BotChannel, PushLog, PushTask
from app.models.entities import User
from app.providers.push import PushMessage, make_push_provider, registered_channels
from app.services.cron_expr import parse_cron_next, validate_cron
from app.services.push_scheduler import persist_web_notification
from app.services.push_template import validate_template
from app.services.roles import has_min_rank

router = APIRouter(
    prefix="/api/v1/bots",
    tags=["bots"],
    # 全域登录门禁：渠道 CRUD / 测试推送 / 日志含 webhook 与密钥，绝不可匿名访问。
    # 逐端点补 Depend 会随新端点复发，故在 router 层一次性收口。
    # record_audit_actor（STEP-31）：写操作审计的操作者来源，读接口也挂（方法过滤在中间件）。
    dependencies=[Depends(get_current_sub), Depends(record_audit_actor)],
)

# 推送内容上限
MAX_MESSAGE_CHARS = 2000
MAX_NAME_CHARS = 128
MAX_WEBHOOK_CHARS = 512

# 事件类型枚举（对齐 bothot_entities.py:72 注释）
VALID_TRIGGER_EVENTS = frozenset({"new_article", "hot_topic_update", "daily_report"})


# ── 请求模型（JSON body）──────────────────────────────────────────────
# 与 spaces.CreateSpaceRequest 同口径：写操作走 Pydantic body。
# 历史上本域用标量查询参数收参，而前端（lib/api/bots.ts）一致发 JSON body——
# body 被忽略、全按默认值处理，创建类请求恒 400、更新类静默 no-op（bots 页
# 无真后端 e2e 覆盖故从未暴露）。2026-09-30 集成审查改为 body 模型，前端零改动。
# Optional 字段语义：None = 不修改（区别于显式空串 = 清空）。


class ChannelCreateRequest(BaseModel):
    name: str
    channel_type: str
    webhook_url: str = ""
    secret: str = ""
    extra_config: str = "{}"


class ChannelUpdateRequest(BaseModel):
    name: str | None = None
    webhook_url: str | None = None
    secret: str | None = None
    extra_config: str | None = None
    status: str | None = None


class PushTaskCreateRequest(BaseModel):
    name: str
    bot_channel_id: str
    trigger_type: str = "manual"
    cron_expr: str = ""
    trigger_event: str = ""
    content_template: str = ""
    space_id: str = ""
    # 不收 `created_by`：归属只取当前登录者（STEP-24 / D-V11-02）。pydantic 默认忽略多余键，
    # 旧前端仍发来该字段也不会 422，只是不再生效。


class PushTaskUpdateRequest(BaseModel):
    name: str | None = None
    cron_expr: str | None = None
    trigger_event: str | None = None
    content_template: str | None = None
    status: str | None = None


def _validate_channel_type(channel_type: str) -> None:
    """校验渠道类型合法性。"""
    valid = {str(c["channel"]) for c in registered_channels()}
    if channel_type not in valid:
        raise RequestInvalidError(f"未知渠道类型: {channel_type}（合法：{', '.join(sorted(valid))}）")


# 角色门一律只写**一个**最低角色（D-V11-01；守卫 tests/test_require_roles_single_arg.py）。
# 权限边界按 D-V12-12：运营可建/改/删/执行推送任务、测试推送、改渠道名称与启停；
# 新建渠道（即写入凭据）、删除渠道、修改渠道凭据只给管理员。


def _serialize_channel(ch: BotChannel) -> dict:
    """序列化渠道。

    这里**会**回显 `webhook_url` 原文与解密后的 `extra_config`（飞书 app_secret、钉钉
    access_token 等）：对飞书/钉钉/企业微信而言 webhook URL 本身就是投递凭据，持有即可向群里
    发消息。所以这两个字段不是"不暴露 secret"，而是**只暴露给 operator 及以上**——
    调用方的角色门是这份回显成立的前提（D-V10-07 / STEP-22 S22.2.3），不是可选的加固。
    """
    return {
        "id": ch.id,
        "name": ch.name,
        "channel_type": ch.channel_type,
        "webhook_url": ch.webhook_url,
        "has_secret": bool(ch.secret_enc),
        # S2.1：存储态为 AES 密文，回显解密明文（维持既有 API 语义，前端零改动）
        "extra_config": decrypt_extra_config(ch.id, ch.extra_config),
        "status": ch.status,
        "user_id": ch.user_id,
        "total_push_count": ch.total_push_count,
        "success_push_count": ch.success_push_count,
        "created_at": ch.created_at.isoformat() if ch.created_at else None,
        "updated_at": ch.updated_at.isoformat() if ch.updated_at else None,
    }


def _serialize_log(log: PushLog) -> dict:
    return {
        "id": log.id,
        "bot_channel_id": log.bot_channel_id,
        "push_task_id": log.push_task_id,
        "status": log.status,
        "content_preview": log.content_preview,
        "error_message": log.error_message,
        "response_summary": log.response_summary,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _serialize_task(t: PushTask) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "bot_channel_id": t.bot_channel_id,
        "trigger_type": t.trigger_type,
        "cron_expr": t.cron_expr,
        "trigger_event": t.trigger_event,
        "content_template": t.content_template,
        "space_id": t.space_id,
        "next_run_at": t.next_run_at.isoformat() if t.next_run_at else None,
        "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
        "status": t.status,
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


# ── 渠道类型查询 ──────────────────────────────────────────────────────


@router.get("/channels")
async def list_channel_types():
    """查询所有可用渠道类型。"""
    return success(registered_channels())


# ── CRUD ──────────────────────────────────────────────────────────────


@router.post("")
async def create_channel(
    payload: ChannelCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_roles("admin")),
):
    """创建机器人渠道。"""
    name = payload.name.strip()
    channel_type = payload.channel_type.strip()
    if not name:
        raise RequestInvalidError("渠道名称不能为空")
    if len(name) > MAX_NAME_CHARS:
        raise RequestInvalidError(f"渠道名称过长（上限 {MAX_NAME_CHARS} 字符）")
    _validate_channel_type(channel_type)
    if len(payload.webhook_url) > MAX_WEBHOOK_CHARS:
        raise RequestInvalidError(f"webhook_url 过长（上限 {MAX_WEBHOOK_CHARS} 字符）")

    # 检查名称唯一
    existing = (await db.execute(select(BotChannel).where(BotChannel.name == name))).scalar_one_or_none()
    if existing:
        raise RequestInvalidError(f"渠道名称已存在: {name}")

    # AAD 绑定 channel id：id 由 default=gen_uuid 在 INSERT 时才生成，而加密必须
    # 发生在插入前——显式预生成 id，保证密文的 AAD 与读取侧 decrypt_channel_secret(ch.id) 一致。
    channel_id = gen_uuid()
    ch = BotChannel(
        id=channel_id,
        name=name,
        channel_type=channel_type,
        webhook_url=payload.webhook_url,
        secret_enc=encrypt_channel_secret(channel_id, payload.secret) if payload.secret else "",
        # S2.1：明文 JSON 落库前整字段加密（AAD 绑定 channel id + 字段域分隔）
        extra_config=encrypt_extra_config(channel_id, payload.extra_config),
        status="active",
    )
    db.add(ch)
    await db.commit()
    await db.refresh(ch)
    return success(_serialize_channel(ch))


@router.get("")
async def list_channels(
    channel_type: str = "",
    status: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_roles("operator")),
):
    """查询渠道列表（分页）。"""
    q = select(BotChannel)
    if channel_type:
        q = q.where(BotChannel.channel_type == channel_type)
    if status:
        q = q.where(BotChannel.status == status)
    q = q.order_by(BotChannel.created_at.desc())

    # 总数
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # 分页
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return success(
        {
            "items": [_serialize_channel(ch) for ch in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


# ── 推送任务管理 ──────────────────────────────────────────────────────


@router.post("/tasks")
async def create_push_task(
    payload: PushTaskCreateRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_roles("operator")),
):
    """创建推送任务（定时/事件触发/手动）。

    `created_by` 是 `users.id` 外键：由服务端取当前登录者的本地 id 写入，请求体无权指定
    （否则任何能建任务的人都可把归属写成任意用户；旧的 SSO sub / 字面量兜底则直接违反外键 ⇒ 500）。
    """
    name = payload.name.strip()
    if not name:
        raise RequestInvalidError("任务名称不能为空")
    if not payload.bot_channel_id:
        raise RequestInvalidError("目标渠道不能为空")
    if payload.trigger_type not in ("cron", "event", "manual"):
        raise RequestInvalidError(f"触发类型非法: {payload.trigger_type}")

    # 验证渠道存在
    ch = (await db.execute(select(BotChannel).where(BotChannel.id == payload.bot_channel_id))).scalar_one_or_none()
    if ch is None:
        raise ResourceNotFoundError("资源不存在或无权限")

    # trigger_type=cron：cron_expr 必填且可解析
    next_run_at: datetime | None = None
    cron_expr = payload.cron_expr.strip()
    if payload.trigger_type == "cron":
        if not cron_expr:
            raise RequestInvalidError("cron 触发类型必须指定 cron_expr")
        err = validate_cron(cron_expr)
        if err is not None:
            raise RequestInvalidError(err)
        next_run_at = parse_cron_next(cron_expr, datetime.now(UTC))

    # trigger_type=event：trigger_event 必填且限定枚举
    trigger_event = payload.trigger_event.strip()
    if payload.trigger_type == "event":
        if not trigger_event:
            raise RequestInvalidError("event 触发类型必须指定 trigger_event")
        if trigger_event not in VALID_TRIGGER_EVENTS:
            raise RequestInvalidError(
                f"事件类型非法: {trigger_event}（合法：{', '.join(sorted(VALID_TRIGGER_EVENTS))}）"
            )

    # 模板校验：未知变量创建期即拒绝，不让坏模板静默进调度
    content_template = payload.content_template.strip()
    if content_template:
        template_err = validate_template(content_template)
        if template_err is not None:
            raise RequestInvalidError(f"content_template 非法：{template_err}")

    task = PushTask(
        name=name,
        bot_channel_id=payload.bot_channel_id,
        trigger_type=payload.trigger_type,
        cron_expr=cron_expr,
        trigger_event=trigger_event,
        content_template=content_template,
        space_id=payload.space_id or None,
        created_by=actor.id,
        status="active" if payload.trigger_type != "manual" else "paused",
        next_run_at=next_run_at,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    return success(_serialize_task(task))


@router.get("/tasks")
async def list_push_tasks(
    status: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_roles("operator")),
):
    """查询推送任务列表。"""
    q = select(PushTask)
    if status:
        q = q.where(PushTask.status == status)
    q = q.order_by(PushTask.created_at.desc())

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return success(
        {
            "items": [_serialize_task(t) for t in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.put("/tasks/{task_id}")
async def update_push_task(
    task_id: str,
    payload: PushTaskUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_roles("operator")),
):
    """编辑推送任务：可修改 name/cron_expr/trigger_event/content_template/status。

    Optional 字段 None = 不修改。cron_expr 变更或 status 置 active 时重算 next_run_at。
    """
    task = (await db.execute(select(PushTask).where(PushTask.id == task_id))).scalar_one_or_none()
    if task is None:
        raise ResourceNotFoundError("资源不存在或无权限")

    need_recalc_next_run = False

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise RequestInvalidError("任务名称不能为空")
        task.name = name

    # cron_expr 变更：显式空串 = 清空（并清 next_run_at），非空 = 校验后更新
    if payload.cron_expr is not None:
        cron_expr = payload.cron_expr.strip()
        if cron_expr:
            err = validate_cron(cron_expr)
            if err is not None:
                raise RequestInvalidError(err)
            task.cron_expr = cron_expr
            need_recalc_next_run = True
        else:
            task.cron_expr = ""
            task.next_run_at = None

    # trigger_event 变更
    if payload.trigger_event is not None:
        trigger_event = payload.trigger_event.strip()
        if trigger_event and trigger_event not in VALID_TRIGGER_EVENTS:
            raise RequestInvalidError(
                f"事件类型非法: {trigger_event}（合法：{', '.join(sorted(VALID_TRIGGER_EVENTS))}）"
            )
        task.trigger_event = trigger_event

    # content_template 变更：显式空串 = 重置为默认文案
    if payload.content_template is not None:
        template = payload.content_template.strip()
        if template:
            template_err = validate_template(template)
            if template_err is not None:
                raise RequestInvalidError(f"content_template 非法：{template_err}")
        task.content_template = template

    # status 变更
    if payload.status is not None:
        if payload.status not in ("active", "paused"):
            raise RequestInvalidError(f"状态非法: {payload.status}（合法：active, paused）")
        task.status = payload.status
        if payload.status == "active" and task.trigger_type == "cron" and task.cron_expr:
            need_recalc_next_run = True
        if payload.status == "paused":
            task.next_run_at = None

    # 重算 next_run_at
    if need_recalc_next_run and task.trigger_type == "cron" and task.cron_expr:
        task.next_run_at = parse_cron_next(task.cron_expr, datetime.now(UTC))

    await db.commit()
    await db.refresh(task)
    return success(_serialize_task(task))


@router.delete("/tasks/{task_id}")
async def delete_push_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_roles("operator")),
):
    """删除推送任务（软删除：status → deleted）。"""
    task = (await db.execute(select(PushTask).where(PushTask.id == task_id))).scalar_one_or_none()
    if task is None:
        raise ResourceNotFoundError("资源不存在或无权限")

    task.status = "deleted"
    task.next_run_at = None
    await db.commit()
    return success({"id": task_id, "status": "deleted"})


@router.post("/tasks/{task_id}/run")
async def run_push_task_now(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_roles("operator")),
):
    """手动触发推送任务。"""
    task = (await db.execute(select(PushTask).where(PushTask.id == task_id))).scalar_one_or_none()
    if task is None:
        raise ResourceNotFoundError("资源不存在或无权限")

    ch = (await db.execute(select(BotChannel).where(BotChannel.id == task.bot_channel_id))).scalar_one_or_none()
    if ch is None:
        raise ResourceNotFoundError("任务关联的渠道不存在")

    provider = make_push_provider(ch.channel_type)
    content = task.content_template or "BotHot 推送通知"
    # TASK-016 同口径：web 渠道在投递前自铸 id，使 SSE 实时帧与 notifications 行同值
    # （`Notification.id` 是 Python 侧默认值，取回要等 flush ⇒ 只能提前铸）。
    notification_id = gen_uuid() if ch.channel_type == "web" else ""
    push_msg = PushMessage(
        notification_id=notification_id,
        message=content,
        title=task.name,
        webhook_url=ch.webhook_url,
        secret=decrypt_channel_secret(ch.id, ch.secret_enc),
        # S2.1：投递前解密（存量明文兼容读，密文 fail-closed）
        extra_config=decrypt_extra_config(ch.id, ch.extra_config),
    )

    result = await provider.push(push_msg)

    # 记录日志
    log = PushLog(
        bot_channel_id=ch.id,
        push_task_id=task.id,
        status="success" if result.delivered else "failed",
        content_preview=content[:200],
        error_message=result.reason if not result.delivered else "",
        response_summary=result.response_data[:500],
    )
    db.add(log)
    ch.total_push_count += 1
    if result.delivered:
        ch.success_push_count += 1

    now = datetime.now(UTC)
    task.last_run_at = now

    # cron 任务执行后补算 next_run_at
    if task.trigger_type == "cron" and task.cron_expr and task.status == "active":
        task.next_run_at = parse_cron_next(task.cron_expr, now)

    # STEP-23（REQ-F-001 的未闭环项）：web 渠道投递成功 → 补写站内通知历史。
    # 复用调度器同一个落库函数，不在这里自己构造通知行：广播/定向判定
    # （`external_user_id` 有无）与 id 口径必须只有一处实现，否则两条路径会漂移。
    # 放在 commit 之前 ⇒ 与 PushLog/计数同事务。D-V17-03 实测：`begin_nested()` 会先
    # flush 待写对象再开 savepoint ⇒ 上面的 PushLog 落在 persist 的 savepoint 之外，
    # 通知行回滚不会撤销它，也不存在「撤销后由 commit 重插」。
    if ch.channel_type == "web" and result.delivered:
        await persist_web_notification(db, push_msg)

    await db.commit()

    return success(
        {
            "delivered": result.delivered,
            "reason": result.reason,
            "channel": result.channel,
        }
    )


# 顺序约束（S22.2.1）：FastAPI 按**声明顺序**匹配，`/{channel_id}` 是一条能吞掉任意单段的
# 通配路由。静态段（`/tasks`、`/channels`……）一律声明在它**之前**，否则请求会被
# 当成「查一个 id 等于该段名的渠道」。守卫见 `tests/test_bots_read_authz.py`。
@router.get("/{channel_id}")
async def get_channel(
    channel_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_roles("operator")),
):
    """查询单个渠道详情。"""
    ch = (await db.execute(select(BotChannel).where(BotChannel.id == channel_id))).scalar_one_or_none()
    if ch is None:
        raise ResourceNotFoundError("资源不存在或无权限")
    return success(_serialize_channel(ch))


@router.put("/{channel_id}")
async def update_channel(
    channel_id: str,
    payload: ChannelUpdateRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_roles("operator")),
):
    """更新渠道配置。Optional 字段 None = 不修改（显式空串 = 清空）。

    运营可改名称与启停；凭据三项（`webhook_url` / `secret` / `extra_config`）只给管理员（D-V12-12）。
    凭据判定放在查库之前：先授权、后判存在，运营无法借 404/403 的差异探测渠道 id；
    同一请求夹带凭据字段时整单拒绝，不做部分生效。
    """
    touches_credentials = payload.webhook_url is not None or bool(payload.secret) or payload.extra_config is not None
    if touches_credentials and not has_min_rank(actor.role, "admin"):
        raise ForbiddenError("修改渠道凭据（webhook_url / secret / extra_config）仅限管理员")
    ch = (await db.execute(select(BotChannel).where(BotChannel.id == channel_id))).scalar_one_or_none()
    if ch is None:
        raise ResourceNotFoundError("资源不存在或无权限")

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise RequestInvalidError("渠道名称不能为空")
        if len(name) > MAX_NAME_CHARS:
            raise RequestInvalidError(f"渠道名称过长（上限 {MAX_NAME_CHARS} 字符）")
        ch.name = name
    if payload.webhook_url is not None:
        if len(payload.webhook_url) > MAX_WEBHOOK_CHARS:
            raise RequestInvalidError(f"webhook_url 过长（上限 {MAX_WEBHOOK_CHARS} 字符）")
        ch.webhook_url = payload.webhook_url
    if payload.secret:
        ch.secret_enc = encrypt_channel_secret(ch.id, payload.secret)
    if payload.extra_config is not None:
        # P-39：与 create_channel 同口径落密文（AAD 绑定 channel id）；改前这里写明文，
        # 读侧 decrypt_extra_config 的"{ 开头原样返回"兼容读把缺陷遮住了。
        ch.extra_config = encrypt_extra_config(ch.id, payload.extra_config)
    if payload.status is not None:
        if payload.status not in ("active", "disabled"):
            raise RequestInvalidError(f"状态非法: {payload.status}（合法：active, disabled）")
        ch.status = payload.status

    await db.commit()
    await db.refresh(ch)
    return success(_serialize_channel(ch))


@router.delete("/{channel_id}")
async def delete_channel(
    channel_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_roles("admin")),
):
    """删除渠道（软删除：status → deleted）。"""
    ch = (await db.execute(select(BotChannel).where(BotChannel.id == channel_id))).scalar_one_or_none()
    if ch is None:
        raise ResourceNotFoundError("资源不存在或无权限")

    ch.status = "deleted"
    await db.commit()
    return success({"id": channel_id, "status": "deleted"})


# ── 测试推送 ──────────────────────────────────────────────────────────


@router.post("/{channel_id}/test")
async def test_push(
    channel_id: str,
    message: str = "BotHot 测试推送 —— 如果您收到此消息，说明渠道配置正确！",
    title: str = "BotHot 测试推送",
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_roles("operator")),
):
    """向指定渠道发送测试消息。"""
    ch = (await db.execute(select(BotChannel).where(BotChannel.id == channel_id))).scalar_one_or_none()
    if ch is None:
        raise ResourceNotFoundError("资源不存在或无权限")
    if ch.status != "active":
        raise RequestInvalidError(f"渠道已禁用: {channel_id}")

    provider = make_push_provider(ch.channel_type)
    # 同 `/tasks/{id}/run`：web 渠道预铸 id，让实时帧与历史行同值（D-V10-05 选"也进"）。
    notification_id = gen_uuid() if ch.channel_type == "web" else ""
    # 收件人锚：`Notification.sub` 与 SSE 频道 `bothot:notifications:{sub}` 用的都是 **users.sub**
    # （AGENTS 关键约束 2），而 `bot_channels.user_id` 是 users.id。直接把 id 当收件人写进历史行，
    # 历史查询按 sub 过滤就永远匹配不上——实时帧之所以还能到，只是因为订阅侧同时挂了两个锚
    # （`system.py:_notification_channels`），那不是"写错锚也行"的理由。
    # 只改 web 一支：`wechat_clawbot` 等渠道把 `external_user_id` 解释成自己的收件人语义。
    recipient = ch.user_id or ""
    if ch.channel_type == "web" and ch.user_id:
        bound_sub = await db.scalar(select(User.sub).where(User.id == ch.user_id)) or ""
        # 解析不到 sub 时退回原锚，**绝不退回空串**：`external_user_id=""` 在
        # `persist_web_notification` 里等于 `is_broadcast=True` ⇒ 一条定向测试推送
        # 会升级成全站可见的站内通知，那是把身份缺陷换成越权缺陷。
        recipient = bound_sub or ch.user_id
    push_msg = PushMessage(
        notification_id=notification_id,
        external_user_id=recipient,
        message=message,
        title=title,
        webhook_url=ch.webhook_url,
        secret=decrypt_channel_secret(ch.id, ch.secret_enc),
        # S2.1：投递前解密（存量明文兼容读，密文 fail-closed）
        extra_config=decrypt_extra_config(ch.id, ch.extra_config),
    )

    result = await provider.push(push_msg)

    # 记录日志
    log = PushLog(
        bot_channel_id=ch.id,
        status="success" if result.delivered else "failed",
        content_preview=message[:200],
        error_message=result.reason if not result.delivered else "",
        response_summary=result.response_data[:500],
    )
    db.add(log)

    # 更新统计
    ch.total_push_count += 1
    if result.delivered:
        ch.success_push_count += 1

    # STEP-23（REQ-F-001 的未闭环项）：web 渠道投递成功 → 补写站内通知历史。
    # 复用调度器同一个落库函数，不在这里自己构造通知行：广播/定向判定
    # （`external_user_id` 有无）与 id 口径必须只有一处实现，否则两条路径会漂移。
    # 放在 commit 之前 ⇒ 与 PushLog/计数同事务。S37.1（P-51）按 D-V17-03 的 SQL 事件探针
    # 实证改正旧注释：`persist_web_notification` 内部的 `begin_nested()` 在 flush 待写对象
    # **之后**才开 savepoint ⇒ PushLog 落在 savepoint 之外，通知行回滚**不会**撤销它
    # （EVD-V14-26 §6：SAVEPOINT 事件序）。旧文案"把尚未 flush 的 PushLog 一并撤销、
    # 再由 commit 重新插入"与探针结果相反，据此删除。
    if ch.channel_type == "web" and result.delivered:
        await persist_web_notification(db, push_msg)

    await db.commit()

    return success(
        {
            "delivered": result.delivered,
            "reason": result.reason,
            "channel": result.channel,
        }
    )


# ── 推送日志 ──────────────────────────────────────────────────────────


@router.get("/{channel_id}/logs")
async def list_push_logs(
    channel_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="按投递状态过滤: success/failed/dead"),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_roles("operator")),
):
    """查询某渠道的推送日志（R3.1：分页既有，补 status 过滤）。"""
    ch = (await db.execute(select(BotChannel).where(BotChannel.id == channel_id))).scalar_one_or_none()
    if ch is None:
        raise ResourceNotFoundError("资源不存在或无权限")

    q = select(PushLog).where(PushLog.bot_channel_id == channel_id)
    if status is not None:
        if status not in {"success", "failed", "dead"}:
            raise RequestInvalidError(f"非法 status: {status}（合法：success/failed/dead）")
        q = q.where(PushLog.status == status)
    q = q.order_by(PushLog.created_at.desc())
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return success(
        {
            "items": [_serialize_log(log) for log in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )
