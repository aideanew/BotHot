"""统一响应信封（对齐主平台契约：code/message/data/requestId）。

requestId 取当前请求上下文（由 RequestIdMiddleware 注入），
保证响应体与 X-Request-ID 头、日志三者一致。
"""

from pydantic import BaseModel

from app.core.request_context import get_or_create_request_id


class Envelope(BaseModel):
    code: int = 0
    message: str = "ok"
    data: object | None = None
    requestId: str


def success(data: object = None) -> Envelope:
    return Envelope(data=data, requestId=get_or_create_request_id())


def failure(code: int, message: str) -> Envelope:
    return Envelope(code=code, message=message, requestId=get_or_create_request_id())
