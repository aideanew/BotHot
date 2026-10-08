"""T1.5.1（G9）RedisSessionStore 真实回环验收测试。

- 连真实 Redis（默认 redis://localhost:6380/0 = 容器映射口；不可达自动 skip）；
- 覆盖 create/get/update_tokens/delete 全契约 + TTL 生效 + 反序列化保真；
- 会话铁律（模块头）：refresh 轮换后最新一代必须可靠持久化——update_tokens
  回读断言即该铁律的机器门。
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest

from app.services.auth.session_store import RedisSessionStore, SessionRecord

TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6380/0")


def _record(sid: str) -> SessionRecord:
    return SessionRecord(
        session_id=sid,
        sub="sub-t151",
        email="t151@test.local",
        nickname="T151",
        access_token="access-1",
        refresh_token="refresh-1",
        access_expires_at=time.time() + 600,
    )


@pytest.fixture
async def redis_client():  # type: ignore[no-untyped-def]
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(TEST_REDIS_URL, decode_responses=True)
        await client.ping()
    except Exception as exc:  # pragma: no cover - Redis 不可达窗口
        pytest.skip(f"测试 Redis 不可达（{type(exc).__name__}），拉起容器后复跑")
    yield client
    await client.aclose()


async def test_session_roundtrip_and_token_rotation(redis_client) -> None:  # type: ignore[no-untyped-def]
    """契约回环：create → get 保真 → update_tokens 轮换持久化（铁律门）→ delete。

    注意：RedisSessionStore 内部自管 sso:session: 前缀，用例直接传 session_id。
    """
    store = RedisSessionStore(redis_client)
    rec = _record("t151-roundtrip")
    sid = rec.session_id

    await store.create(rec, ttl_seconds=300)
    got = await store.get(sid)
    assert got is not None
    assert got.sub == "sub-t151" and got.refresh_token == "refresh-1"

    # 轮换：最新一代 refresh 必须可靠持久化（模块铁律）
    await store.update_tokens(sid, "access-2", "refresh-2", time.time() + 900)
    rotated = await store.get(sid)
    assert rotated is not None
    assert rotated.access_token == "access-2" and rotated.refresh_token == "refresh-2"

    await store.delete(sid)
    assert await store.get(sid) is None


async def test_session_ttl_and_missing_key(redis_client) -> None:  # type: ignore[no-untyped-def]
    """TTL 生效（1s 窗口后自然过期）+ 未创建键返回 None（不抛）。"""
    store = RedisSessionStore(redis_client)
    sid = "t151-ttl-case"
    await store.create(_record(sid), ttl_seconds=1)
    assert await store.get(sid) is not None
    ttl = await redis_client.ttl(f"sso:session:{sid}")
    assert 0 <= ttl <= 1
    await asyncio.sleep(1.2)
    assert await store.get(sid) is None
    assert await store.get("t151-never-created") is None
