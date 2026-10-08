"""请求上下文：requestId 的进程内传递。

统一信封、日志、异常处理器都从这里取同一个 requestId，
保证"一条请求一个 ID"，避免各处自行 uuid4 导致无法串联排查。
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token

_REQUEST_ID: ContextVar[str | None] = ContextVar("bothot_request_id", default=None)

REQUEST_ID_HEADER = "X-Request-ID"


def set_request_id(request_id: str) -> Token:
    """绑定 requestId 到当前上下文，返回用于复位（reset）的 Token。"""
    return _REQUEST_ID.set(request_id)


def reset_request_id(token: Token) -> None:
    """释放上下文变量，防止请求间串扰（尤其协程复用场景）。"""
    _REQUEST_ID.reset(token)


def get_request_id() -> str | None:
    """取当前 requestId；不存在时返回 None。"""
    return _REQUEST_ID.get()


def get_or_create_request_id() -> str:
    """取当前 requestId；中间件未覆盖时（如单测直调）兜底生成。"""
    return _REQUEST_ID.get() or str(uuid.uuid4())
