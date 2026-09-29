"""通用 Webhook 推送。

POST JSON 到任意 URL，适用于自建通知服务、IFTTT、Zapier 等。
"""

from __future__ import annotations

import httpx

from .base import PushMessage, PushResult

_WEBHOOK_TIMEOUT = 10


class WebhookPushProvider:
    name = "webhook"
    description = "通用 webhook 推送（POST JSON，适用于自建通知/IFTTT/Zapier）"

    async def push(self, message: PushMessage) -> PushResult:
        if not message.webhook_url:
            return PushResult("webhook", False, "webhook_url 未配置")

        payload = {
            "title": message.title or "BotHot 推送通知",
            "message": message.message,
            "url": message.url,
            "space_id": message.space_id,
            "doc_id": message.doc_id,
            "external_user_id": message.external_user_id,
        }

        try:
            async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT) as client:
                resp = await client.post(
                    message.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                if 200 <= resp.status_code < 300:
                    return PushResult("webhook", True, "", resp.text[:500])
                return PushResult("webhook", False, f"webhook 返回 HTTP {resp.status_code}", resp.text[:500])
        except httpx.TimeoutException:
            return PushResult("webhook", False, "webhook 请求超时")
        except Exception as e:
            return PushResult("webhook", False, f"webhook 推送异常: {e}")
