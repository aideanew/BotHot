"""用户仓库：按 sub（主平台 User.id）upsert 本地账号快照。

- UserStore 协议 + InMemoryUserStore：SSO 服务依赖此协议（B-T3，测试/开发注入）；
- SqlAlchemyUserStore：生产实现（B-T4，连真实 PG；session 由调用方持有，
  repo 只 flush 不 commit，事务边界归调用方）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import User


@dataclass(slots=True)
class UserSnapshot:
    """users 行的最小投影（SSO 链路所需字段 + role 授权判据）。"""

    id: str
    sub: str
    email: str
    nickname: str
    role: str = "user"


def _to_snapshot(user: User) -> UserSnapshot:
    return UserSnapshot(
        id=user.id, sub=user.sub, email=user.email,
        nickname=user.nickname, role=user.role,
    )


@runtime_checkable
class UserStore(Protocol):
    """用户存储契约（身份锚点 = sub，同一用户跨会话复用本地行）。"""

    async def upsert_by_sub(self, sub: str, email: str, nickname: str) -> UserSnapshot: ...

    async def get_by_id(self, user_id: str) -> UserSnapshot | None: ...


class InMemoryUserStore:
    """进程内实现（单测/开发）。"""

    def __init__(self) -> None:
        self._by_sub: dict[str, UserSnapshot] = {}
        self._seq = 0
        self.calls: list[tuple[str, str, str]] = []  # upsert 调用记录（测试断言用）

    async def upsert_by_sub(self, sub: str, email: str, nickname: str) -> UserSnapshot:
        self.calls.append((sub, email, nickname))
        existing = self._by_sub.get(sub)
        if existing is not None:
            existing.email = email
            existing.nickname = nickname
            return existing
        self._seq += 1
        snapshot = UserSnapshot(id=f"local-{self._seq:06d}", sub=sub, email=email, nickname=nickname)
        self._by_sub[sub] = snapshot
        return snapshot

    def get_by_sub(self, sub: str) -> UserSnapshot | None:
        return self._by_sub.get(sub)

    async def get_by_id(self, user_id: str) -> UserSnapshot | None:
        return next((s for s in self._by_sub.values() if s.id == user_id), None)


class SqlAlchemyUserStore:
    """生产实现：users 表按 sub upsert（并发首登靠 sub 唯一索引 + savepoint 兜底）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_by_sub(self, sub: str, email: str, nickname: str) -> UserSnapshot:
        existing = await self._session.scalar(select(User).where(User.sub == sub))
        if existing is not None:
            existing.email = email
            existing.nickname = nickname
            await self._session.flush()
            return _to_snapshot(existing)
        user = User(sub=sub, email=email, nickname=nickname)
        self._session.add(user)
        try:
            await self._session.flush()
        except IntegrityError:
            # 并发首登竞态：另一请求已插入同 sub → 整体回滚后取现值
            await self._session.rollback()
            existing = await self._session.scalar(select(User).where(User.sub == sub))
            if existing is None:
                raise
            return _to_snapshot(existing)
        return _to_snapshot(user)

    async def get_by_sub(self, sub: str) -> User | None:
        return await self._session.scalar(select(User).where(User.sub == sub))

    async def get_by_id(self, user_id: str) -> User | None:
        return await self._session.scalar(select(User).where(User.id == user_id))
