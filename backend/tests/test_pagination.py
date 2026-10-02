r"""C.1 分页单测：验证 service 层 (items, total) 形状 + limit/offset 透传到 repo（SQL 层）。

用桩 repo 验证 service 不再全量取、切片在 repo（SQL LIMIT/OFFSET 由 repo 实现，
test_indexes.py 的 EXPLAIN 留证）。路由层切片清零由 `grep items\[offset app/ ==0` 断言。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.spaces import SpaceService


def _space(sid: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=sid,
        name=f"s{sid}",
        description="d",
        updated_at=None,
        engine="builtin",
        engine_kb_id="",
        langbot_kb_uuid="",
        is_public=False,
        owner_type="user",
    )


class _StubRepo:
    """桩 repo：记录 limit/offset 透传，返回可控页与总数。"""

    def __init__(self, spaces: list, total: int) -> None:
        self._spaces = spaces
        self._total = total
        self.last_limit: int | None = None
        self.last_offset: int | None = None

    async def list_by_user(self, user_id, *, limit=50, offset=0):  # noqa: ANN001, ANN202
        self.last_limit, self.last_offset = limit, offset
        return self._spaces

    async def count_by_user(self, user_id):  # noqa: ANN001, ANN202
        return self._total

    async def list_with_owner(self, *, limit=50, offset=0):  # noqa: ANN202
        self.last_limit, self.last_offset = limit, offset
        return [(s, None) for s in self._spaces]

    async def count_with_owner(self):  # noqa: ANN202
        return self._total

    async def count_docs_many(self, ids):  # noqa: ANN001, ANN202
        return {i: 0 for i in ids}


@pytest.mark.asyncio
async def test_list_space_views_returns_items_total_and_passes_paging() -> None:
    """list_space_views(limit, offset) → (items, total)；limit/offset 透传 repo。"""
    repo = _StubRepo([_space("1"), _space("2")], total=75)
    svc = SpaceService(repo, session=None, engine_router=None)
    items, total = await svc.list_space_views("u", limit=20, offset=40)
    assert total == 75
    assert len(items) == 2
    assert repo.last_limit == 20
    assert repo.last_offset == 40  # 透传到 repo（SQL LIMIT/OFFSET 在 repo 层）


@pytest.mark.asyncio
async def test_list_space_views_any_returns_items_total_and_passes_paging() -> None:
    """list_space_views_any(limit, offset) → (items, total)；limit/offset 透传 repo。"""
    repo = _StubRepo([_space("a")], total=60)
    svc = SpaceService(repo, session=None, engine_router=None)
    items, total = await svc.list_space_views_any(limit=50, offset=0)
    assert total == 60
    assert len(items) == 1
    assert repo.last_limit == 50
    assert repo.last_offset == 0


@pytest.mark.asyncio
async def test_list_space_views_defaults() -> None:
    """缺省 limit=50/offset=0（与 limit_offset_query 依赖默认一致）。"""
    repo = _StubRepo([], total=0)
    svc = SpaceService(repo, session=None, engine_router=None)
    _, _ = await svc.list_space_views("u")
    assert repo.last_limit == 50
    assert repo.last_offset == 0
