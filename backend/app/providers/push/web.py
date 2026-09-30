"""站内通知推送。

通过 Redis pub/sub 向前端 WebSocket 连接推送实时通知。
前端订阅 bothot:notifications:{user_id} 频道即可接收。

如果 Redis 不可用或无订阅者，消息被丢弃（fire-and-forget）。
"""

from __future__ import annotations

import json

from .base import PushMessage, PushResult

# Redis 频道前缀
_CHANNEL_PREFIX = "bothot:notifications"


class WebPushProvider:
    name = "web"
    description = "站内通知（Redis pub/sub → 前端 WebSocket 实时推送）"

    async def push(self, message: PushMessage) -> PushResult:
        # 尝试导入 Redis（延迟导入，避免在无 Redis 环境下启动失败）
        try:
            import redis.asyncio as aioredis

            from app.core.config import get_settings

            settings = get_settings()
            if not settings.redis_url:
                return PushResult("web", False, "Redis 未配置，站内通知不可用")

            notification = {
                "title": message.title or "BotHot 通知",
                "message": message.message,
                "url": message.url,
                "space_id": message.space_id,
                "doc_id": message.doc_id,
            }

            # 发布到用户专属频道
            channel = (
                f"{_CHANNEL_PREFIX}:{message.external_user_id}"
                if message.external_user_id
                else f"{_CHANNEL_PREFIX}:broadcast"
            )

            async with aioredis.from_url(settings.redis_url) as r:
                await r.publish(channel, json.dumps(notification, ensure_ascii=False))

            return PushResult("web", True, "", f"published to {channel}")
        except Exception as e:
            return PushResult("web", False, f"站内通知发送失败: {e}", retryable=True)
