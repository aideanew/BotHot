"""服务端会话存储：令牌（access/refresh）只存服务端，Cookie 仅承载不透明 id。

铁律（接入指南 §3/§7）：
- 禁止把 refresh_token / client_secret 下发浏览器；
- refresh 轮换后必须可靠持久化最新一代（写入失败会被主平台判定重放、整链撤销）。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class SessionRecord:
    """一条服务端会话（本地 users 行通过 sub 关联，不在此冗余）。"""

    session_id: str
    sub: str  # 主平台 User.id（身份锚点）
    email: str
    nickname: str
    access_token: str
    refresh_token: str
    access_expires_at: float  # epoch 秒
    created_at: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(
            {
                "session_id": self.session_id,
                "sub": self.sub,
                "email": self.email,
                "nickname": self.nickname,
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "access_expires_at": self.access_expires_at,
                "created_at": self.created_at,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str | bytes) -> SessionRecord:
        data: dict[str, Any] = json.loads(raw)
        return cls(**data)


@runtime_checkable
class SessionStore(Protocol):
    """会话存储契约。"""

    async def create(self, record: SessionRecord, ttl_seconds: int) -> None: ...

    async def get(self, session_id: str) -> SessionRecord | None: ...

    async def update_tokens(
        self, session_id: str, access_token: str, refresh_token: str, access_expires_at: float
    ) -> None:
        """轮换后回写最新一代 refresh_token（必须成功，见模块铁律）。"""
        ...

    async def delete(self, session_id: str) -> None: ...

    async def delete_by_sub(self, sub: str) -> int:
        """按身份锚点删除该用户**全部**本地会话，返回被删条数。

        供 OIDC Back-Channel Logout 使用：主平台按「用户」粒度广播 logout_token，
        而 `sid`（链级标识）本方拿不到——`SessionRecord` 无 sid 字段、refresh JWT 全程不解析、
        `TokenPair` 不含 chainId。按 sub 全清的误杀代价=用户重新登录一次点击，
        远小于解析未验签的 refresh JWT 去伪造 sid 的攻击面。
        """
        ...


class InMemorySessionStore:
    """进程内实现（单测/单实例开发）。"""

    def __init__(self) -> None:
        self._sessions: dict[str, tuple[SessionRecord, float]] = {}

    async def create(self, record: SessionRecord, ttl_seconds: int) -> None:
        self._sessions[record.session_id] = (record, time.monotonic() + ttl_seconds)

    async def get(self, session_id: str) -> SessionRecord | None:
        item = self._sessions.get(session_id)
        if item is None:
            return None
        record, expires_at = item
        if expires_at <= time.monotonic():
            del self._sessions[session_id]
            return None
        return record

    async def update_tokens(
        self, session_id: str, access_token: str, refresh_token: str, access_expires_at: float
    ) -> None:
        item = self._sessions.get(session_id)
        if item is None:
            return
        record, expires_at = item
        record.access_token = access_token
        record.refresh_token = refresh_token
        record.access_expires_at = access_expires_at
        self._sessions[session_id] = (record, expires_at)

    async def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    async def delete_by_sub(self, sub: str) -> int:
        victims = [session_id for session_id, (record, _) in self._sessions.items() if record.sub == sub]
        for session_id in victims:
            self._sessions.pop(session_id, None)
        return len(victims)


class RedisSessionStore:
    """Redis 实现（多实例部署）：JSON 序列化 + TTL。"""

    def __init__(self, redis) -> None:  # redis.asyncio.Redis
        self._redis = redis
        self._prefix = "sso:session:"

    async def create(self, record: SessionRecord, ttl_seconds: int) -> None:
        await self._redis.setex(f"{self._prefix}{record.session_id}", ttl_seconds, record.to_json())

    async def get(self, session_id: str) -> SessionRecord | None:
        raw = await self._redis.get(f"{self._prefix}{session_id}")
        return SessionRecord.from_json(raw) if raw else None

    async def update_tokens(
        self, session_id: str, access_token: str, refresh_token: str, access_expires_at: float
    ) -> None:
        raw = await self._redis.get(f"{self._prefix}{session_id}")
        if not raw:
            return
        record = SessionRecord.from_json(raw)
        record.access_token = access_token
        record.refresh_token = refresh_token
        record.access_expires_at = access_expires_at
        # 回写并重置 TTL（活跃会话顺延；写入失败在 Redis 侧表现为后续刷新失败，可观测）
        await self._redis.setex(f"{self._prefix}{session_id}", 7 * 24 * 3600, record.to_json())

    async def delete(self, session_id: str) -> None:
        await self._redis.delete(f"{self._prefix}{session_id}")

    async def delete_by_sub(self, sub: str) -> int:
        """SCAN 全量比对，**不建二级索引**（R9 §5.4 裁决）。

        索引方案会让「`create` 的 setex 成功而 SADD 失败」产生对 delete_by_sub
        不可见的会话——登出静默漏杀且零可观测性。会话量百~千级（TTL 7 天），
        SCAN 的毫秒级代价不值得用正确性去换。
        """
        deleted = 0
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor=cursor, match=f"{self._prefix}*", count=200)
            for key in keys:
                raw = await self._redis.get(key)
                if not raw:
                    continue
                try:
                    record = SessionRecord.from_json(raw)
                except (TypeError, ValueError):
                    continue
                if record.sub == sub:
                    await self._redis.delete(key)
                    deleted += 1
            if cursor == 0:
                break
        return deleted
