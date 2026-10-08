"""T1.4.1 公共库发布双闸验收测试（大纲 v1.1）。

口径（D9=c 过渡裁决 2026-09-22）：
- 闸① env allowlist：操作者 user_id 须在 PUBLIC_ADMIN_ALLOWLIST；
- 闸② owner_type=system：仅系统空间可发布/回收；
- 纯函数 check_publish_gate 离线单测全覆盖；PG 连库用例验证服务层置位持久化
  （PG 不可达自动 skip，与既有口径一致）。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.errors import ForbiddenError, ResourceNotFoundError
from app.repositories.space import SpaceRepository
from app.services import public_library as pl
from app.services.public_library import PublicLibraryService, check_publish_gate

OP_OK = "11111111-1111-1111-1111-111111111111"
OP_OTHER = "22222222-2222-2222-2222-222222222222"


def _patch_allowlist(monkeypatch: pytest.MonkeyPatch, allowlist: str) -> None:
    """把 allowlist 注入 public_library.get_settings（测试专用，不入生产路径）。"""
    monkeypatch.setattr(
        pl,
        "get_settings",
        lambda: SimpleNamespace(public_admin_allowlist=allowlist),
    )


# ------------------------------------------------------------------ 纯函数双闸（离线口径）


def test_gate_rejects_operator_not_in_allowlist() -> None:
    """闸①：操作者不在 allowlist → 10004，即使空间是 system。"""
    with pytest.raises(ForbiddenError):
        check_publish_gate(OP_OK, OP_OTHER, "system")


def test_gate_rejects_empty_allowlist() -> None:
    """闸①空表：allowlist 未配置 = 无人可发布（安全默认）。"""
    with pytest.raises(ForbiddenError):
        check_publish_gate("", OP_OK, "system")


def test_gate_rejects_non_system_space() -> None:
    """闸②：操作者在 allowlist 但目标空间 owner_type=user → 10004。"""
    with pytest.raises(ForbiddenError):
        check_publish_gate(OP_OK, OP_OK, "user")


def test_gate_allows_system_space_with_allowlisted_operator() -> None:
    """双闸全过：allowlist 命中（含空白容错）+ owner_type=system → 不抛。"""
    check_publish_gate(f"  {OP_OK} , {OP_OTHER} ", OP_OK, "system")


# ------------------------------------------------------------------ 服务层（PG 连库口径）


async def test_set_public_status_publish_and_unpublish(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    """双闸全过：发布 → is_public=True 落库；回收 → False 落库（幂等可逆）。"""
    from sqlalchemy import select

    from app.models.entities import KnowledgeSpace

    user = await _make_operator(db_session)
    space = await SpaceRepository(db_session).create_public_space(user.id, "发布闸验收库")
    await db_session.commit()
    _patch_allowlist(monkeypatch, OP_OK)

    svc = PublicLibraryService(db_session)
    out = await svc.set_public_status(OP_OK, space.id, True)
    assert out["isPublic"] is True and out["spaceId"] == space.id
    row = (
        await db_session.execute(select(KnowledgeSpace).where(KnowledgeSpace.id == space.id))
    ).scalar_one()
    assert row.is_public is True

    out2 = await svc.set_public_status(OP_OK, space.id, False)
    assert out2["isPublic"] is False


async def test_set_public_status_rejects_user_space(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    """闸②连库口径：owner_type=user 的普通空间 → 10004（is_public 不被改写）。"""
    user = await _make_operator(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="普通用户空间")
    await db_session.commit()
    _patch_allowlist(monkeypatch, OP_OK)

    svc = PublicLibraryService(db_session)
    with pytest.raises(ForbiddenError):
        await svc.set_public_status(OP_OK, space.id, True)


async def test_set_public_status_space_not_found(db_session) -> None:  # type: ignore[no-untyped-def]
    """空间不存在 → 30004（先于双闸判定，404 不泄露存在性）。"""
    svc = PublicLibraryService(db_session)
    with pytest.raises(ResourceNotFoundError):
        await svc.set_public_status(OP_OK, "00000000-0000-0000-0000-000000000000", True)


# ------------------------------------------------------------------ 夹具/工具


async def _make_operator(db_session):  # type: ignore[no-untyped-def]
    """操作者用户行（allowlist 校验锚 = 本地 users.id）。"""
    from app.repositories.user import SqlAlchemyUserStore

    return await SqlAlchemyUserStore(db_session).upsert_by_sub(
        "sub-t141-admin", "t141@test.local", "T141-Admin"
    )
