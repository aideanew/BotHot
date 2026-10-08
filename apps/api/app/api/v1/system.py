"""系统路由：健康检查（匿名）与站内通知 SSE（登录）。

- GET /api/v1/system/health          匿名功能探活（compose healthcheck 依赖，绝不加登录门禁）
- GET /api/v1/system/notifications   站内通知 SSE（EventSource，须登录）
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_sub, get_db, limit_offset_query
from app.core import schema_guard
from app.core.config import get_settings
from app.core.response import failure, success
from app.models.bothot_entities import Notification
from app.models.entities import User
from app.providers.push.web import _CHANNEL_PREFIX

router = APIRouter(prefix="/api/v1/system", tags=["system"])
logger = structlog.get_logger(__name__)


async def _check_pg() -> str:
    try:
        from app.db import get_engine

        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return "ok"
    except Exception:
        return "unreachable"


async def _check_redis() -> str:
    try:
        import redis.asyncio as aioredis

        settings = get_settings()
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2, protocol=2)
        await r.ping()
        await r.aclose()
        return "ok"
    except Exception:
        return "unreachable"


async def _check_langbot() -> str:
    """LangBot 2.x **没有** `/api/health`，而 `/health` 是前端 SPA 的 catch-all
    ——API 层挂了它照样返 200（返回 index.html），拿它当探针会把真故障判成健康。

    改探测一个真实存在的路由 `/api/v1/knowledge/engines`：未登录时它回 LangBot 的
    JSON 错误信封（证明 API 路由在应答），未知路径才落到 SPA 兜底返 HTML。
    判据取「响应是 LangBot 的信封」而非单看状态码——两者都成立才算活，
    避免 LangBot 调整状态码时探针静默失效。
    """
    try:
        import httpx

        settings = get_settings()
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{settings.langbot_base_url}/api/v1/knowledge/engines")
        if resp.status_code != 401:
            return "unhealthy"
        try:
            body = resp.json()
        except ValueError:
            return "unhealthy"
        return "ok" if isinstance(body, dict) and "code" in body else "unhealthy"
    except Exception:
        return "unreachable"


@router.get("/health")
async def health() -> object:
    """R6.1.5：功能探活——依赖活性逐项暴露（存活仍 200，降级面可见）。

    deps 中各项：ok / unreachable / unhealthy；
    任一非 ok 说明功能降级（如 Redis 不可达→会话回退 memory，LangBot 不可达→检索/入库不可用）。
    """
    settings = get_settings()
    pg = await _check_pg()
    redis = await _check_redis()
    langbot = await _check_langbot()
    deps = {"postgres": pg, "redis": redis, "langbot": langbot}
    all_ok = all(v == "ok" for v in deps.values())
    return success(
        data={
            "status": "ok" if all_ok else "degraded",
            "app": settings.app_name,
            "env": settings.app_env,
            "deps": deps,
        }
    )


async def _check_schema() -> dict[str, object]:
    """schema/code 一致性（复用 `core.schema_guard`，与启动守卫同源）。

    ok=current==head；head 探测不可用视为 ok（不可判定不误伤就绪）；
    current 取不到（库不可达/无表）时标 unreachable。"""
    from app.db import get_engine

    head = schema_guard.get_alembic_head()
    current = await schema_guard.read_current_version_async(get_engine())
    if head is None:
        return {"ok": True, "state": "head_unknown", "current": current, "head": head}
    if current is None:
        return {"ok": False, "state": "unreachable", "current": current, "head": head}
    return {"ok": current == head, "state": "ok" if current == head else "mismatch", "current": current, "head": head}


@router.get("/live")
async def live() -> object:
    """存活探针：进程在跑即 200，不触任何依赖——供容器 HEALTHCHECK 用。

    与 /health（功能探活、逐项降级可见）、/ready（就绪门禁）分层：
    live 回答「该不该重启我」，ready 回答「能不能给我流量」。"""
    return success(data={"status": "alive", "app": get_settings().app_name})


@router.get("/ready")
async def ready() -> JSONResponse:
    """就绪探针：PG ping + Redis ping + schema 一致，任一不过返 503（带逐项明细）。

    全部 ok → 200；任一失败 → 503，body 仍为标准信封，`data.checks` 点名失败项，
    让编排器（compose/k8s readiness）在依赖未就绪时摘流量而非把故障当健康。"""
    pg = await _check_pg()
    redis = await _check_redis()
    schema = await _check_schema()
    checks = {
        "postgres": {"ok": pg == "ok", "state": pg},
        "redis": {"ok": redis == "ok", "state": redis},
        "schema": schema,
    }
    all_ok = all(bool(c["ok"]) for c in checks.values())
    body = success(
        data={
            "status": "ready" if all_ok else "not_ready",
            "checks": checks,
        }
    )
    return JSONResponse(status_code=200 if all_ok else 503, content=body.model_dump())


# ── 站内通知 SSE 订阅（WE 5.1）───────────────────────────────────────────────
#
# 连接生命周期：客户端 EventSource 连上本端点 → 后端订阅 Redis pub/sub
#   bothot:notifications:{sub}（定向）+ bothot:notifications:broadcast（广播兑底，
#   web provider 无 external_user_id 时落此频道）→ 每条消息以 `data: <原 JSON>`
#   原样转发。心跳：空闲满 NOTIFICATION_PING_SECONDS 发一行 `: ping` 注释帧，
#   防反向代理（Nginx/网关）按空闲超时断连。清理：客户端断开（request.is_disconnected）
#   或流中异常 → finally 退订并关闭 pubsub/client 连接，不留悬挂订阅。
# 优雅降级：Redis 未配置/不可达 → 转发一帧 {"type":"service_unavailable"} 后
#   正常收尾关流（不 500、不拖垮进程），前端据此提示而非崩渲染。
# 鉴权：Depends(get_current_sub)——未登录在流建立前即 401；/health 保持匿名，
#   故门禁加在端点级、非 router 级。
#
# web 渠道验收口径：providers/push/web.py 投递侧 + 本订阅侧上线后端到端闭环打通，
#   web 渠道验收口径由此从 5/6 升 6/6（仅改本 docstring，docs 口径归 WD）。

# 与 providers/push/web.py 的 _CHANNEL_PREFIX 单一来源，杜绝频道命名漂移。
_BROADCAST_SUFFIX = "broadcast"
NOTIFICATION_PING_SECONDS = 25.0


class _RedisSubscriber:
    """Redis pub/sub 订阅者薄封装：隔离 redis.asyncio 细节，便于测试注入假对象。"""

    def __init__(self, client: object, pubsub: object) -> None:
        self._client = client
        self._pubsub = pubsub

    async def get_message(self, timeout: float) -> dict | None:
        return await self._pubsub.get_message(  # type: ignore[attr-defined]
            ignore_subscribe_messages=True, timeout=timeout
        )

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            await self._pubsub.aclose()  # type: ignore[attr-defined]
        with contextlib.suppress(Exception):
            await self._client.aclose()  # type: ignore[attr-defined]


async def _default_open_subscriber(redis_url: str, channels: list[str]) -> _RedisSubscriber:
    """真实订阅者：延迟导入 redis.asyncio（无 Redis 环境不在 import 期就硬故）。"""
    import redis.asyncio as aioredis

    client = aioredis.from_url(redis_url, socket_connect_timeout=3, protocol=2)
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    await pubsub.subscribe(*channels)
    return _RedisSubscriber(client, pubsub)


# 模块级注入点（测试换假订阅者；生产保持默认）——与 chat._llm_http_factory 同纪律。
_open_subscriber = _default_open_subscriber


def _notification_channels(sub: str, user_id: str | None = None) -> list[str]:
    """订阅频道（审查缝合：双锚覆盖）。

    发布侧存在两种锚：手动/服务推送用 external_user_id（调用方语义，通常为 SSO
    sub）；渠道绑定推送（bots.py test_push 传 bot_channels.user_id）是 users.id。
    订阅侧同时覆盖 sub 与 users.id + broadcast 兜底，任一发布锚都能到达；
    user_id 解析失败（无对应行）只降级为 sub + broadcast，不阻断连接。
    """
    channels = [f"{_CHANNEL_PREFIX}:{sub}"]
    if user_id and user_id != sub:
        channels.append(f"{_CHANNEL_PREFIX}:{user_id}")
    channels.append(f"{_CHANNEL_PREFIX}:{_BROADCAST_SUFFIX}")
    return channels


def _data_frame(payload: object) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _notification_stream(request: Request, sub: str, user_id: str | None = None) -> AsyncIterator[str]:
    """站内通知 SSE 主循环（见上方生命周期注释）。异常一律收敛为优雅关流。"""
    settings = get_settings()
    if not settings.redis_url:
        yield _data_frame({"type": "service_unavailable", "message": "Redis 未配置，站内通知不可用"})
        return
    try:
        subscriber = await _open_subscriber(settings.redis_url, _notification_channels(sub, user_id))
    except Exception:  # noqa: BLE001  # Redis 不可达：降级不 500
        logger.warning("站内通知订阅建立失败（Redis 不可达），优雅降级", exc_info=True)
        yield _data_frame({"type": "service_unavailable", "message": "通知服务暂不可用，请稍后重试"})
        return

    yield ": connected\n\n"  # 立即 flush 响应头，令 EventSource 进入 open 态
    try:
        while True:
            if await request.is_disconnected():
                break
            msg = await subscriber.get_message(NOTIFICATION_PING_SECONDS)
            if msg is None:
                yield ": ping\n\n"  # 空闲心跳，防代理超时断连
                continue
            if msg.get("type") != "message":
                continue
            raw = msg.get("data")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", "replace")
            if not raw:
                continue
            yield f"data: {raw}\n\n"  # 原样转发 web provider 发布的 JSON
    except Exception:  # noqa: BLE001  # 流中异常（连接抖动）：收敛关流，不裸抛
        logger.warning("站内通知流异常中断", exc_info=True)
    finally:
        await subscriber.close()


@router.get("/notifications")
async def notifications(
    request: Request,
    sub: Annotated[str, Depends(get_current_sub)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    """GET /api/v1/system/notifications——站内通知 SSE（EventSource）。

    须登录（get_current_sub）；订阅/心跳/降级/清理语义见上方模块内注释。
    双锚解析（审查缝合）：sub → users.id，覆盖渠道绑定发布与 SSO 锚发布两种口径。
    """
    user_id: str | None = None
    try:
        row = await session.execute(select(User.id).where(User.sub == sub))
        user_id = row.scalar_one_or_none()
    except Exception:  # noqa: BLE001  # 解析失败不阻断订阅（降级 sub + broadcast）
        logger.warning("站内通知订阅：sub→users.id 解析失败，仅订阅 sub 频道", exc_info=True)
    return StreamingResponse(
        _notification_stream(request, sub, user_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── S1.2/S1.3（R1.2）：通知历史查询 + 已读回执 ──────────────────
# 存储底座：notifications 表（ab1005w5a），写侧在 push_scheduler.persist_web_notification。
# 可见性口径与 SSE 频道一致：定向（sub==me）+ 广播（is_broadcast）两类全覆盖。
# 热路：(sub, created_at) 复合索引 ix_notifications_sub_created 支撑定向倒序分页。


def _notification_scope(sub: str):
    """定向 + 广播统一可见性谓词（与 persist_web_notification 落库口径互补）。"""
    return or_(Notification.sub == sub, Notification.is_broadcast.is_(True))


def _notification_dto(n: Notification) -> dict[str, object]:
    """载荷字段与 SSE 通知帧一一对应（AppNotification 契约），另附回执元数据。"""
    return {
        "id": n.id,
        "is_broadcast": n.is_broadcast,
        "title": n.title,
        "message": n.message,
        "url": n.url or None,
        "space_id": n.space_id or None,
        "doc_id": n.doc_id or None,
        "read_at": n.read_at.isoformat() if n.read_at else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


class NotificationReadRequest(BaseModel):
    """已读回执请求：id 单条 / before 批量（created_at <= before 的未读全标）二选一。"""

    id: str | None = Field(default=None, description="单条通知 id")
    before: datetime | None = Field(default=None, description="批量截止时间（含）")


@router.get("/notifications/history")
async def notifications_history(
    sub: Annotated[str, Depends(get_current_sub)],
    session: Annotated[AsyncSession, Depends(get_db)],
    paging: Annotated[tuple[int, int], Depends(limit_offset_query)],
) -> JSONResponse:
    """GET /api/v1/system/notifications/history——离线通知补投（分页倒序）。

    须登录；响应 {items,total,limit,offset,unread_total}（C.1 冻结口径 + 未读数免二次拉取）。
    unread_total = 可见范围内 read_at IS NULL 计数，供前端未读徽标与服务端对账。
    """
    limit, offset = paging
    scope = _notification_scope(sub)
    total = (
        await session.execute(select(func.count()).select_from(Notification).where(scope))
    ).scalar_one()
    unread_total = (
        await session.execute(
            select(func.count())
            .select_from(Notification)
            .where(scope, Notification.read_at.is_(None))
        )
    ).scalar_one()
    rows = (
        await session.execute(
            select(Notification)
            .where(scope)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    body = success(
        data={
            "items": [_notification_dto(n) for n in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "unread_total": unread_total,
        }
    )
    return JSONResponse(status_code=200, content=body.model_dump())


@router.put("/notifications/read")
async def notifications_read(
    payload: NotificationReadRequest,
    sub: Annotated[str, Depends(get_current_sub)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """PUT /api/v1/system/notifications/read——已读回执（单条 id / 批量 before 二选一）。

    须登录；只更新**可见范围**（sub==me OR is_broadcast）内的行，越权 id 视同不存在
    （rowcount=0，不泄露他人通知的存在性）。返回 {updated}。
    """
    if (payload.id is None) == (payload.before is None):
        body = failure(10005, "id 与 before 必须二选一")
        return JSONResponse(status_code=400, content=body.model_dump())

    scope = _notification_scope(sub)
    stmt = update(Notification).where(scope, Notification.read_at.is_(None))
    if payload.id is not None:
        stmt = stmt.where(Notification.id == payload.id)
    else:
        stmt = stmt.where(Notification.created_at <= payload.before)
    result = await session.execute(stmt.values(read_at=datetime.now(UTC)))
    await session.commit()
    # ORM execute 返回的 Result 泛型不暴露 rowcount；运行时实为 CursorResult（UPDATE 必有）
    updated = result.rowcount  # type: ignore[attr-defined]
    body = success(data={"updated": updated})
    return JSONResponse(status_code=200, content=body.model_dump())
