"""WC 3.3 / W8 C.1 分页形状单测：验证端点 items/total/limit/offset 形状。

W8 C.1 后：路由层切片移除，handler 接 `paging=(limit,offset)` 依赖、service 返回
(items, total)。直接 await handler 验证响应形状（不连库、不起 HTTP）。
"""

from __future__ import annotations

import json

import pytest

from app.api.v1.admin import admin_list_spaces, admin_list_subscriptions
from app.api.v1.spaces import list_public_spaces, list_spaces


def _body(resp) -> dict:  # noqa: ANN001
    return json.loads(resp.body)["data"]


class _StubSpaceSvc:
    """桩 svc：list_space_views(_any) 返回 (items, total)，对齐 C.1 契约。"""

    def __init__(self, items: list[dict], total: int) -> None:
        self._items, self._total = items, total

    async def list_space_views(self, user_id: str, *, limit=50, offset=0):  # noqa: ANN001, ANN202, ARG002
        return self._items, self._total

    async def list_space_views_any(self, *, limit=50, offset=0):  # noqa: ANN202, ARG002
        return self._items, self._total


@pytest.mark.asyncio
async def test_list_spaces_pagination_shape() -> None:
    items = [{"id": str(i)} for i in range(20)]
    resp = await list_spaces("u", _StubSpaceSvc(items, 75), paging=(20, 10))
    data = _body(resp)
    assert data["total"] == 75
    assert data["limit"] == 20
    assert data["offset"] == 10
    assert len(data["items"]) == 20


@pytest.mark.asyncio
async def test_admin_list_spaces_pagination_shape() -> None:
    items = [{"id": str(i)} for i in range(50)]
    resp = await admin_list_spaces(None, _StubSpaceSvc(items, 60), paging=(50, 0))  # type: ignore[arg-type]
    data = _body(resp)
    assert data["total"] == 60
    assert data["limit"] == 50
    assert data["offset"] == 0
    assert len(data["items"]) == 50


@pytest.mark.asyncio
async def test_list_public_spaces_pagination(monkeypatch) -> None:  # noqa: ANN001
    items = [{"id": str(i)} for i in range(10)]

    async def _stub(self, *, limit=50, offset=0):  # noqa: ANN001, ANN202, ARG002
        return items, 55

    from app.services.public_library import PublicLibraryService

    monkeypatch.setattr(PublicLibraryService, "list_public_views", _stub)
    resp = await list_public_spaces("u", session=None, paging=(10, 5))  # type: ignore[arg-type]
    data = _body(resp)
    assert data["total"] == 55
    assert data["limit"] == 10
    assert data["offset"] == 5
    assert len(data["items"]) == 10


@pytest.mark.asyncio
async def test_admin_list_subscriptions_pagination(monkeypatch) -> None:  # noqa: ANN001
    items = [{"id": str(i)} for i in range(25)]

    async def _stub(self, space_id=None, *, limit=50, offset=0):  # noqa: ANN001, ANN202, ARG002
        return items, 40

    from app.services.subscription import SourceSubscriptionService

    monkeypatch.setattr(SourceSubscriptionService, "list_subscriptions_any", _stub)
    resp = await admin_list_subscriptions(None, session=None, paging=(25, 0))  # type: ignore[arg-type]
    data = _body(resp)
    assert data["total"] == 40
    assert data["limit"] == 25
    assert data["offset"] == 0
    assert len(data["items"]) == 25
