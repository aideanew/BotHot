"""WC 3.3 分页形状单测：验证 TOP5 修复端点的 items/total/limit/offset 形状与切片正确。

两种注入模式各取代表：
- list_spaces / admin_list_spaces：handler 接收 svc 依赖，直接注入桩 svc；
- list_public_spaces / admin_list_subscriptions：handler 内部 new service(session)，
  用 monkeypatch 替换 service 方法。
不连库、不起 HTTP，直接 await handler 验证响应形状。
"""

from __future__ import annotations

import json

import pytest

from app.api.v1.admin import admin_list_spaces, admin_list_subscriptions
from app.api.v1.spaces import list_public_spaces, list_spaces


def _body(resp) -> dict:  # noqa: ANN001
    return json.loads(resp.body)["data"]


class _StubSpaceSvc:
    def __init__(self, items: list[dict]) -> None:
        self._items = items

    async def list_space_views(self, user_id: str) -> list[dict]:  # noqa: ARG002
        return self._items

    async def list_space_views_any(self) -> list[dict]:
        return self._items


@pytest.mark.asyncio
async def test_list_spaces_pagination_slice() -> None:
    items = [{"id": str(i)} for i in range(75)]
    resp = await list_spaces("u", _StubSpaceSvc(items), limit=20, offset=10)
    data = _body(resp)
    assert data["total"] == 75
    assert data["limit"] == 20
    assert data["offset"] == 10
    assert len(data["items"]) == 20
    assert data["items"][0]["id"] == "10"
    assert data["items"][-1]["id"] == "29"


@pytest.mark.asyncio
async def test_admin_list_spaces_pagination_slice() -> None:
    items = [{"id": str(i)} for i in range(60)]
    resp = await admin_list_spaces(None, _StubSpaceSvc(items), limit=50, offset=0)  # type: ignore[arg-type]
    data = _body(resp)
    assert data["total"] == 60
    assert data["limit"] == 50
    assert data["offset"] == 0
    assert len(data["items"]) == 50


@pytest.mark.asyncio
async def test_list_public_spaces_pagination(monkeypatch) -> None:  # noqa: ANN001
    items = [{"id": str(i)} for i in range(55)]

    async def _stub(self) -> list[dict]:  # noqa: ANN001
        return items

    from app.services.public_library import PublicLibraryService

    monkeypatch.setattr(PublicLibraryService, "list_public_views", _stub)
    resp = await list_public_spaces("u", session=None, limit=10, offset=5)  # type: ignore[arg-type]
    data = _body(resp)
    assert data["total"] == 55
    assert data["limit"] == 10
    assert data["offset"] == 5
    assert len(data["items"]) == 10
    assert data["items"][0]["id"] == "5"


@pytest.mark.asyncio
async def test_admin_list_subscriptions_pagination(monkeypatch) -> None:  # noqa: ANN001
    items = [{"id": str(i)} for i in range(40)]

    async def _stub(self, space_id: str | None = None) -> list[dict]:  # noqa: ANN001
        return items

    from app.services.subscription import SourceSubscriptionService

    monkeypatch.setattr(SourceSubscriptionService, "list_subscriptions_any", _stub)
    resp = await admin_list_subscriptions(None, session=None, limit=25, offset=0)  # type: ignore[arg-type]
    data = _body(resp)
    assert data["total"] == 40
    assert data["limit"] == 25
    assert data["offset"] == 0
    assert len(data["items"]) == 25
