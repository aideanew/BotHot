"""SSO state 存储：CSRF 防护的核心（铁律：state 强校验 + 单次消费）。

登录时 put(state)，回调时 pop(state)：
- pop 命中 → 合法且立即失效（单次消费，重放/二次使用一律拒绝）；
- pop 未命中 → SsoStateInvalidError（10002）。
"""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable

from app.core.errors import SsoStateInvalidError


@runtime_checkable
class SsoStateStore(Protocol):
    """state 存储契约（单次消费语义）。"""

    async def put(self, state: str, ttl_seconds: int) -> None: ...

    async def pop(self, state: str) -> bool:
        """存在则删除并返回 True；否则 False。"""
        ...


class InMemorySsoStateStore:
    """进程内实现（单测/单实例开发）。"""

    def __init__(self) -> None:
        self._expiry: dict[str, float] = {}

    async def put(self, state: str, ttl_seconds: int) -> None:
        self._expiry[state] = time.monotonic() + ttl_seconds

    async def pop(self, state: str) -> bool:
        expires_at = self._expiry.pop(state, 0.0)  # pop = 单次消费
        return expires_at > time.monotonic()


class RedisSsoStateStore:
    """Redis 实现（多实例部署）：SETEX 写入 / GETDEL 单次消费。"""

    def __init__(self, redis) -> None:  # redis.asyncio.Redis
        self._redis = redis
        self._prefix = "sso:state:"

    async def put(self, state: str, ttl_seconds: int) -> None:
        await self._redis.setex(f"{self._prefix}{state}", ttl_seconds, "1")

    async def pop(self, state: str) -> bool:
        # GETDEL（Redis >= 6.2）：原子取+删，天然单次消费
        value = await self._redis.getdel(f"{self._prefix}{state}")
        return value is not None


async def consume_state(store: SsoStateStore, state: str) -> None:
    """校验并消费 state；不合法直接抛 10002（Service 层唯一入口，避免漏检）。"""
    if not state or not await store.pop(state):
        raise SsoStateInvalidError("state 缺失、已过期或不匹配")
