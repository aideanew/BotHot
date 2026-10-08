"""C.4 读缓存单测：get_or_set miss/hit、invalidate、Redis 不可达直穿。

用伪 Redis 客户端（注入 cache._client_inst）验证命中/失效；_client_inst=None
验证 fail-open 直穿。不连真实 Redis。
"""

from __future__ import annotations

import fnmatch

import pytest

from app.core import cache


class _FakeRedis:
    """最小伪 Redis：实现 get/set/delete/scan_iter/aclose。"""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:  # noqa: ARG002
        self._store[key] = value

    async def delete(self, key: str) -> int:
        return 1 if self._store.pop(key, None) is not None else 0

    async def aclose(self) -> None:
        return None

    async def scan_iter(self, *, match: str, count: int = 100):  # noqa: ARG002
        for k in list(self._store):
            if fnmatch.fnmatch(k, match):
                yield k


@pytest.mark.asyncio
async def test_get_or_set_miss_then_hit(monkeypatch) -> None:  # noqa: ANN001
    """miss 调 loader 并回填；hit 不调 loader，返回缓存值。"""
    fake = _FakeRedis()
    monkeypatch.setattr(cache, "_client_inst", fake)
    calls = {"n": 0}

    async def loader():
        calls["n"] += 1
        return [{"id": "a"}, {"id": "b"}]

    v1 = await cache.get_or_set("k", 60, loader)
    assert v1 == [{"id": "a"}, {"id": "b"}]
    assert calls["n"] == 1  # miss 调一次

    v2 = await cache.get_or_set("k", 60, loader)
    assert v2 == [{"id": "a"}, {"id": "b"}]
    assert calls["n"] == 1  # hit 不调 loader


@pytest.mark.asyncio
async def test_invalidate_clears(monkeypatch) -> None:  # noqa: ANN001
    """invalidate 后下一次 get_or_set 重新调 loader。"""
    fake = _FakeRedis()
    monkeypatch.setattr(cache, "_client_inst", fake)
    calls = {"n": 0}

    async def loader():
        calls["n"] += 1
        return "v"

    await cache.get_or_set("k", 60, loader)
    assert calls["n"] == 1
    await cache.invalidate("k")
    await cache.get_or_set("k", 60, loader)
    assert calls["n"] == 2  # 失效后重调


@pytest.mark.asyncio
async def test_redis_unavailable_direct_pass(monkeypatch) -> None:  # noqa: ANN001
    """_get_client 返回 None（Redis 不可达）→ 直穿 loader，不抛、不缓存。"""
    monkeypatch.setattr(cache, "_get_client", lambda: None)
    calls = {"n": 0}

    async def loader():
        calls["n"] += 1
        return ["x"]

    v = await cache.get_or_set("k", 60, loader)
    assert v == ["x"]
    assert calls["n"] == 1
    # 再调一次仍直穿（无缓存）
    await cache.get_or_set("k", 60, loader)
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_loader_none_not_cached(monkeypatch) -> None:  # noqa: ANN001
    """loader 返回 None 不缓存（None 语义为无值）。"""
    fake = _FakeRedis()
    monkeypatch.setattr(cache, "_client_inst", fake)
    calls = {"n": 0}

    async def loader():
        calls["n"] += 1
        return None

    assert await cache.get_or_set("k", 60, loader) is None
    await cache.get_or_set("k", 60, loader)
    assert calls["n"] == 2  # None 未缓存，每次都调 loader


@pytest.mark.asyncio
async def test_invalidate_pattern(monkeypatch) -> None:  # noqa: ANN001
    """invalidate_pattern 按 glob 批量失效。"""
    fake = _FakeRedis()
    monkeypatch.setattr(cache, "_client_inst", fake)

    async def loader():
        return "v"

    await cache.get_or_set("a:1", 60, loader)
    await cache.get_or_set("a:2", 60, loader)
    await cache.get_or_set("b:1", 60, loader)
    await cache.invalidate_pattern("a:*")
    assert "a:1" not in fake._store
    assert "a:2" not in fake._store
    assert "b:1" in fake._store
