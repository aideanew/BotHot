"""BotHot 渠道管理与推送 API。

提供完整的 CRUD + 测试推送 + 推送日志查询：
- POST   /api/v1/bots              创建渠道
- GET    /api/v1/bots              列表
- GET    /api/v1/bots/{id}         详情
- PUT    /api/v1/bots/{id}         更新
- DELETE /api/v1/bots/{id}         删除
- POST   /api/v1/bots/{id}/test    测试推送
- GET    /api/v1/bots/{id}/logs    推送日志
- GET    /api/v1/bots/channels     可用渠道类型
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_sub, get_db, require_roles
from app.core.errors import (
    RequestInvalidError,
    ResourceNotFoundError,
)
from app.core.response import success
from app.models.bothot_entities import BotChannel, PushLog, PushTask
from app.providers.push import PushMessage, make_push_provider, registered_channels

router = APIRouter(
    prefix="/api/v1/bots",
    tags=["bots"],
    # 全域登录门禁：渠道 CRUD / 测试推送 / 日志含 webhook 与密钥，绝不可匿名访问。
    # 逐端点补 Depend 会随新端点复发，故在 router 层一次性收口。
    dependencies=[Depends(get_current_sub)],
)

# 推送内容上限
MAX_MESSAGE_CHARS = 2000
MAX_NAME_CHARS = 128
MAX_WEBHOOK_CHARS = 512


def _validate_channel_type(channel_type: str) -> None:
    """校验渠道类型合法性。"""
    valid = {str(c["channel"]) for c in registered_channels()}
    if channel_type not in valid:
        raise RequestInvalidError(
            f"未知渠道类型: {channel_type}（合法：{', '.join(sorted(valid))}）"
        )


def _encrypt_secret(secret: str) -> str:
    """加密 secret（简单 base64，生产环境应使用 AES-256-GCM）。

    TODO: 接入 core.engine_keyring 的 AES-256-GCM 加密。
    """
    import base64
    if not secret:
        return ""
    return base64.b64encode(secret.encode("utf-8")).decode("utf-8")


def _decrypt_secret(enc: str) -> str:
    """解密 secret。"""
    import base64
    if not enc:
        return ""
    try:
        return base64.b64decode(enc.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""


def _serialize_channel(ch: BotChannel) -> dict:
    """序列化渠道（不暴露 secret）。"""
    return {
        "id": ch.id,
        "name": ch.name,
        "channel_type": ch.channel_type,
        "webhook_url": ch.webhook_url,
        "has_secret": bool(ch.secret_enc),
        "extra_config": ch.extra_config,
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


# ── 渠道类型查询 ──────────────────────────────────────────────────────

@router.get("/channels")
async def list_channel_types():
    """查询所有可用渠道类型。"""
    return success(registered_channels())


# ── CRUD ──────────────────────────────────────────────────────────────

@router.post("")
async def create_channel(
    name: str = "",
    channel_type: str = "",
    webhook_url: str = "",
    secret: str = "",
    extra_config: str = "{}",
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_roles("admin", "operator")),
):
    """创建机器人渠道。"""
    name = name.strip()
    channel_type = channel_type.strip()
    if not name:
        raise RequestInvalidError("渠道名称不能为空")
    if len(name) > MAX_NAME_CHARS:
        raise RequestInvalidError(f"渠道名称过长（上限 {MAX_NAME_CHARS} 字符）")
    _validate_channel_type(channel_type)
    if len(webhook_url) > MAX_WEBHOOK_CHARS:
        raise RequestInvalidError(f"webhook_url 过长（上限 {MAX_WEBHOOK_CHARS} 字符）")

    # 检查名称唯一
    existing = (await db.execute(select(BotChannel).where(BotChannel.name == name))).scalar_one_or_none()
    if existing:
        raise RequestInvalidError(f"渠道名称已存在: {name}")

    ch = BotChannel(
        name=name,
        channel_type=channel_type,
        webhook_url=webhook_url,
        secret_enc=_encrypt_secret(secret),
        extra_config=extra_config,
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

    return success({
        "items": [_serialize_channel(ch) for ch in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/{channel_id}")
async def get_channel(channel_id: str, db: AsyncSession = Depends(get_db)):
    """查询单个渠道详情。"""
    ch = (await db.execute(select(BotChannel).where(BotChannel.id == channel_id))).scalar_one_or_none()
    if ch is None:
        raise ResourceNotFoundError(f"渠道不存在: {channel_id}")
    return success(_serialize_channel(ch))


@router.put("/{channel_id}")
async def update_channel(
    channel_id: str,
    name: str = "",
    webhook_url: str = "",
    secret: str = "",
    extra_config: str = "",
    status: str = "",
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_roles("admin", "operator")),
):
    """更新渠道配置。"""
    ch = (await db.execute(select(BotChannel).where(BotChannel.id == channel_id))).scalar_one_or_none()
    if ch is None:
        raise ResourceNotFoundError(f"渠道不存在: {channel_id}")

    if name.strip():
        if len(name) > MAX_NAME_CHARS:
            raise RequestInvalidError(f"渠道名称过长（上限 {MAX_NAME_CHARS} 字符）")
        ch.name = name.strip()
    if webhook_url is not None:
        ch.webhook_url = webhook_url
    if secret:
        ch.secret_enc = _encrypt_secret(secret)
    if extra_config:
        ch.extra_config = extra_config
    if status in ("active", "disabled"):
        ch.status = status

    await db.commit()
    await db.refresh(ch)
    return success(_serialize_channel(ch))


@router.delete("/{channel_id}")
async def delete_channel(
    channel_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_roles("admin", "operator")),
):
    """删除渠道（软删除：status → deleted）。"""
    ch = (await db.execute(select(BotChannel).where(BotChannel.id == channel_id))).scalar_one_or_none()
    if ch is None:
        raise ResourceNotFoundError(f"渠道不存在: {channel_id}")

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
    _: str = Depends(require_roles("admin", "operator")),
):
    """向指定渠道发送测试消息。"""
    ch = (await db.execute(select(BotChannel).where(BotChannel.id == channel_id))).scalar_one_or_none()
    if ch is None:
        raise ResourceNotFoundError(f"渠道不存在: {channel_id}")
    if ch.status != "active":
        raise RequestInvalidError(f"渠道已禁用: {channel_id}")

    provider = make_push_provider(ch.channel_type)
    push_msg = PushMessage(
        external_user_id=ch.user_id or "",
        message=message,
        title=title,
        webhook_url=ch.webhook_url,
        secret=_decrypt_secret(ch.secret_enc),
        extra_config=ch.extra_config,
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

    await db.commit()

    return success({
        "delivered": result.delivered,
        "reason": result.reason,
        "channel": result.channel,
    })


# ── 推送日志 ──────────────────────────────────────────────────────────

@router.get("/{channel_id}/logs")
async def list_push_logs(
    channel_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """查询某渠道的推送日志。"""
    ch = (await db.execute(select(BotChannel).where(BotChannel.id == channel_id))).scalar_one_or_none()
    if ch is None:
        raise ResourceNotFoundError(f"渠道不存在: {channel_id}")

    q = select(PushLog).where(PushLog.bot_channel_id == channel_id).order_by(PushLog.created_at.desc())
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return success({
        "items": [_serialize_log(log) for log in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


# ── 推送任务管理 ──────────────────────────────────────────────────────

@router.post("/tasks")
async def create_push_task(
    name: str = "",
    bot_channel_id: str = "",
    trigger_type: str = "manual",
    cron_expr: str = "",
    trigger_event: str = "",
    content_template: str = "",
    space_id: str = "",
    created_by: str = "",
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_roles("admin", "operator")),
):
    """创建推送任务（定时/事件触发/手动）。"""
    name = name.strip()
    if not name:
        raise RequestInvalidError("任务名称不能为空")
    if not bot_channel_id:
        raise RequestInvalidError("目标渠道不能为空")
    if trigger_type not in ("cron", "event", "manual"):
        raise RequestInvalidError(f"触发类型非法: {trigger_type}")

    # 验证渠道存在
    ch = (await db.execute(select(BotChannel).where(BotChannel.id == bot_channel_id))).scalar_one_or_none()
    if ch is None:
        raise ResourceNotFoundError(f"渠道不存在: {bot_channel_id}")

    task = PushTask(
        name=name,
        bot_channel_id=bot_channel_id,
        trigger_type=trigger_type,
        cron_expr=cron_expr,
        trigger_event=trigger_event,
        content_template=content_template,
        space_id=space_id or None,
        created_by=created_by or "system",
        status="active" if trigger_type != "manual" else "paused",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    return success({
        "id": task.id,
        "name": task.name,
        "bot_channel_id": task.bot_channel_id,
        "trigger_type": task.trigger_type,
        "status": task.status,
    })


@router.get("/tasks")
async def list_push_tasks(
    status: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
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

    return success({
        "items": [
            {
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
            for t in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.delete("/tasks/{task_id}")
async def delete_push_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_roles("admin", "operator")),
):
    """删除推送任务。"""
    from sqlalchemy import delete as sa_delete
    await db.execute(sa_delete(PushTask).where(PushTask.id == task_id))
    await db.commit()
    return success({"id": task_id, "deleted": True})


@router.post("/tasks/{task_id}/run")
async def run_push_task_now(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_roles("admin", "operator")),
):
    """手动触发推送任务。"""
    task = (await db.execute(select(PushTask).where(PushTask.id == task_id))).scalar_one_or_none()
    if task is None:
        raise ResourceNotFoundError(f"推送任务不存在: {task_id}")

    ch = (await db.execute(select(BotChannel).where(BotChannel.id == task.bot_channel_id))).scalar_one_or_none()
    if ch is None:
        raise ResourceNotFoundError("任务关联的渠道不存在")

    provider = make_push_provider(ch.channel_type)
    content = task.content_template or "BotHot 推送通知"
    push_msg = PushMessage(
        message=content,
        title=task.name,
        webhook_url=ch.webhook_url,
        secret=_decrypt_secret(ch.secret_enc),
        extra_config=ch.extra_config,
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
    task.last_run_at = func.now()
    await db.commit()

    return success({
        "delivered": result.delivered,
        "reason": result.reason,
        "channel": result.channel,
    })
