"""C.4 读缓存：get_or_set(key, ttl, loader)。

设计（fail-open 直穿）：
- Redis 不可达 / 未配置 / 命令失败 → 直穿 loader，不缓存，不抛（缓存故障不得拖垮业务）；
- loader 返回 None 不缓存（None 语义为"无值"，缓存空值会污染）；
- 序列化用 JSON（str/bytes 经 decode_responses=True 自动 str）。

接入范围（W8 所有权内）：admin 枚举读路径（push 渠道类型清单、发现渠道就绪度）。
动态读路径（如 bots 渠道列表）的写路径显式失效属其域所有者（W4/W7），cache.py 提供
invalidate(key) 供调用；本模块不替域写路径决定何时失效。

不引入新依赖：redis.asyncio 已在 pyproject（>=5.2.0），与 providers/push/web.py 同口径。
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client_inst: Any = None  # 进程级 Redis 客户端单例（lazy）


def _get_client() -> Any:
    """进程级 Redis 客户端单例；未配置 / import 失败 → None（直穿）。"""
    global _client_inst
    if _client_inst is not None:
        return _client_inst
    url = os.environ.get("REDIS_URL") or get_settings().redis_url
    if not url:
        return None
    try:
        import redis.asyncio as aioredis

        _client_inst = aioredis.from_url(url, decode_responses=True)
        return _client_inst
    except Exception:  # noqa: BLE001 Redis 不可达 → 直穿
        logger.debug("cache: Redis 客户端创建失败，直穿模式", exc_info=True)
        return None


async def get_or_set(
    key: str,
    ttl: int,
    loader: Callable[[], Awaitable[Any]],
) -> Any:
    """读缓存：命中返回反序列化值；未命中/不可达调 loader 并回填。

    Redis 任一环节失败均直穿 loader（fail-open），绝不抛。
    """
    client = _get_client()
    if client is not None:
        try:
            cached = await client.get(key)
            if cached is not None:
                return json.loads(cached)
        except Exception:  # noqa: BLE001
            logger.debug("cache get 失败，直穿: key=%s", key, exc_info=True)

    value = await loader()
    if client is not None and value is not None:
        try:
            await client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
        except Exception:  # noqa: BLE001 回填失败不影响返回
            logger.debug("cache set 失败: key=%s", key, exc_info=True)
    return value


async def invalidate(key: str) -> None:
    """写路径显式失效：删除单个 key。Redis 不可达静默（fail-open）。"""
    client = _get_client()
    if client is None:
        return
    try:
        await client.delete(key)
    except Exception:  # noqa: BLE001
        logger.debug("cache invalidate 失败: key=%s", key, exc_info=True)


async def invalidate_pattern(pattern: str) -> None:
    """按 glob 模式批量失效（SCAN 遍历，不阻塞）。Redis 不可达静默。"""
    client = _get_client()
    if client is None:
        return
    try:
        async for k in client.scan_iter(match=pattern, count=100):
            await client.delete(k)
    except Exception:  # noqa: BLE001
        logger.debug("cache invalidate_pattern 失败: pattern=%s", pattern, exc_info=True)
