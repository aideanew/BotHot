"""运营与管理写操作的结构化审计日志（STEP-31，D-V17-02）。

纯 ASGI 实现：在请求结束后按**最终**响应状态与信封业务码写一条 `event="audit"`
的 info 日志。绝不记录请求体、响应体、查询串、请求头；`path_params` 只取路由
声明的路径参数。操作者由 `app.api.deps.record_audit_actor` 依赖写入
`request.state`，本中间件不自行解析会话。

边界：本中间件装在 W7 入站防护（体限/限流）之内，被它们短路的 413/429 走不到
操作者依赖；401 同理。这三类没有操作者，按 D-V17-02 不写审计。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_context import get_request_id

logger = structlog.get_logger(__name__)

AUDIT_PREFIXES: tuple[str, ...] = ("/api/v1/bots", "/api/v1/admin", "/api/v1/sources")
AUDIT_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# 信封远小于此；上限只防非常规大响应把内存拖住，超限时 code 退化为 null。
_MAX_CAPTURED_BODY = 64 * 1024


def is_audited_path(path: str) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in AUDIT_PREFIXES)


class AuditMiddleware:
    """写操作审计：401 与无操作者的请求不写；被拒的 4xx 照写。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") not in AUDIT_METHODS
            or not is_audited_path(scope.get("path", ""))
        ):
            await self.app(scope, receive, send)
            return

        status = 0
        body_chunks: list[bytes] = []
        captured = 0

        async def send_with_capture(message: Message) -> None:
            nonlocal status, captured
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body" and captured < _MAX_CAPTURED_BODY:
                chunk = message.get("body", b"")
                body_chunks.append(chunk)
                captured += len(chunk)
            await send(message)

        await self.app(scope, receive, send_with_capture)
        _write_audit(scope, status, b"".join(body_chunks))


def _write_audit(scope: Scope, status: int, body: bytes) -> None:
    if status == 401:  # 没有操作者
        return
    route_path = getattr(scope.get("route"), "path", None)
    if not route_path or not is_audited_path(route_path):
        return
    actor = (scope.get("state") or {}).get("audit_actor")
    if not actor:
        return

    logger.info(
        "audit",
        actor_sub=actor["sub"],
        actor_role=actor["role"],
        method=scope["method"],
        route=route_path,
        path_params=dict(scope.get("path_params") or {}),
        status=status,
        code=_envelope_code(body),
        request_id=get_request_id() or "",
        ts=datetime.now(UTC).isoformat(),
    )


def _envelope_code(body: bytes) -> int | None:
    """从统一信封里取业务码；非 JSON/非信封一律 null（绝不上报正文）。"""
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    code = payload.get("code") if isinstance(payload, dict) else None
    return code if isinstance(code, int) else None
