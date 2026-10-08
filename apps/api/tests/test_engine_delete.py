"""C.5 引擎删除闭环单测：engineResidue 三分支（builtin / 未实接 / 已实接）。

直接测 SpaceService._delete_space（不连库），用桩 repo + 桩 router + 桩 adapter。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.spaces import SpaceService


class _StubRepo:
    def __init__(self, space) -> None:
        self._space = space
        self.deleted = False

    async def get_by_id(self, space_id):  # noqa: ANN001, ANN202
        return self._space

    async def delete_space_cascade(self, space_id):  # noqa: ANN001, ANN202
        self.deleted = True
        return {"docs": 0, "assets": 0, "spaces": 1}


class _StubAdapter:
    def __init__(self, implemented: bool, raises: bool = False) -> None:
        self.implemented = implemented
        self._raises = raises
        self.delete_called = False

    async def delete_kb(self, kb_id):  # noqa: ANN001, ANN202
        self.delete_called = True
        if self._raises:
            raise RuntimeError("engine API down")


class _StubRouter:
    """桩路由：adapter_for 按预设返回 adapter（或抛 ValueError 模拟不可用）。"""

    def __init__(self, adapter: _StubAdapter | None, available: bool = True) -> None:
        self._adapter = adapter
        self._available = available

    def adapter_for(self, space):  # noqa: ANN001, ANN202
        if not self._available:
            raise ValueError("engine not available")
        return self._adapter


def _svc(space, router: _StubRouter | None = None) -> SpaceService:
    return SpaceService(_StubRepo(space), session=None, engine_router=router)


async def _delete(space, *, router: _StubRouter | None = None, kb=None) -> dict:  # noqa: ANN001
    svc = _svc(space, router=router)
    return await svc._delete_space("s1", kb)


@pytest.mark.asyncio
async def test_builtin_delete_no_residue() -> None:
    """builtin 引擎删除：engineResidue=False（LangBot 实接删库）。"""
    space = SimpleNamespace(id="s1", user_id="u", engine="builtin", langbot_kb_uuid="kb-1", engine_kb_id="")

    class _Kb:
        deleted: list[str] = []

        async def delete_kb(self, kb_uuid):  # noqa: ANN001, ANN202
            self.deleted.append(kb_uuid)

    kb = _Kb()
    result = await _delete(space, kb=kb)
    assert result["engineResidue"] is False
    assert kb.deleted == ["kb-1"]


@pytest.mark.asyncio
async def test_unimplemented_engine_delete_has_residue() -> None:
    """非 builtin 未实接引擎（adapter 不可用）：engineResidue=True，PG 仍删除。"""
    space = SimpleNamespace(id="s1", user_id="u", engine="main", langbot_kb_uuid="", engine_kb_id="ext-kb")
    router = _StubRouter(adapter=None, available=False)  # adapter_for raises ValueError
    result = await _delete(space, router=router)
    assert result["engineResidue"] is True
    assert result["spaces"] == 1  # PG 级联仍执行


@pytest.mark.asyncio
async def test_unimplemented_adapter_noop_has_residue() -> None:
    """非 builtin adapter 可取但 implemented=False（WC 降级 no-op）：engineResidue=True。"""
    space = SimpleNamespace(id="s1", user_id="u", engine="coze", langbot_kb_uuid="", engine_kb_id="ext-kb")
    adapter = _StubAdapter(implemented=False)
    router = _StubRouter(adapter=adapter, available=True)
    result = await _delete(space, router=router)
    assert result["engineResidue"] is True
    assert adapter.delete_called is True  # delete_kb 被调（no-op）


@pytest.mark.asyncio
async def test_implemented_engine_delete_no_residue() -> None:
    """非 builtin 已实接 adapter delete_kb 成功：engineResidue=False。"""
    space = SimpleNamespace(id="s1", user_id="u", engine="main", langbot_kb_uuid="", engine_kb_id="ext-kb")
    adapter = _StubAdapter(implemented=True)
    router = _StubRouter(adapter=adapter, available=True)
    result = await _delete(space, router=router)
    assert result["engineResidue"] is False
    assert adapter.delete_called is True
