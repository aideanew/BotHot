"""HTTP 中间件：requestId 生成/透传 + 响应头回填。

采用纯 ASGI 实现（不依赖 BaseHTTPMiddleware），避免上下文变量在
子任务间丢失，确保异常处理器与日志都能读到同一个 requestId。
"""

from __future__ import annotations

import uuid

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_context import (
    REQUEST_ID_HEADER,
    reset_request_id,
    set_request_id,
)
from app.core.response import failure


class RequestIdMiddleware:
    """为每条 HTTP 请求生成/沿用 requestId，并回填响应头。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._extract_incoming(scope) or str(uuid.uuid4())
        token = set_request_id(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            reset_request_id(token)

    @staticmethod
    def _extract_incoming(scope: Scope) -> str | None:
        """沿用上游网关注入的 requestId（便于跨服务串联）；未传则自行生成。"""
        for raw_key, raw_value in scope.get("headers") or []:
            if raw_key.decode("latin-1").lower() == REQUEST_ID_HEADER.lower():
                value = raw_value.decode("latin-1").strip()
                return value or None
        return None


class ErrorEnvelopeMiddleware:
    """兜底异常转信封：把未被业务处理器捕获的异常统一成 5xxxx 信封。

    为什么不放 FastAPI 的 `exception_handler(Exception)`：Starlette 会把
    `Exception` 的处理器挂到最外层 ServerErrorMiddleware，位于 RequestIdMiddleware
    之外，既拿不到 requestId，也补不上响应头。放在这里（内层）可继承请求上下文。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send)
        except Exception as exc:  # noqa: BLE001 - 兜底必须宽口径
            # AppError / HTTPException 已由内层 ExceptionMiddleware 转成响应，不会到达此处
            body = failure(50001, f"服务内部错误: {type(exc).__name__}")
            response = JSONResponse(status_code=500, content=body.model_dump())
            await response(scope, receive, send)
