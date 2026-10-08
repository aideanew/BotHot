"""微信 ClawBot 推送。

通过 ClawBot HTTP API 发送出站消息给微信用户。
ClawBot 的出站 API 契约：POST {clawbot_base_url}/api/send
Body: {"to": external_user_id, "content": message}

注意：ClawBot 出站 API 需要实际部署 ClawBot 服务后方可使用。
未配置 base_url 时返回明确的未配置回执。
"""

from __future__ import annotations

import json

import httpx

from .base import PushMessage, PushResult

_CLAWBOT_TIMEOUT = 15


class WechatClawbotPushProvider:
    name = "wechat_clawbot"
    description = "微信 ClawBot 出站消息推送（需部署 ClawBot 服务）"

    async def push(self, message: PushMessage) -> PushResult:
        if not message.webhook_url:
            return PushResult("wechat_clawbot", False, "ClawBot base_url 未配置（webhook_url 字段）")

        if not message.external_user_id:
            return PushResult("wechat_clawbot", False, "推送目标 external_user_id 未配置")

        payload = {
            "to": message.external_user_id,
            "content": message.message,
            "title": message.title,
            "url": message.url,
        }

        # secret 作为 Bearer token
        headers = {"Content-Type": "application/json"}
        if message.secret:
            headers["Authorization"] = f"Bearer {message.secret}"

        try:
            async with httpx.AsyncClient(timeout=_CLAWBOT_TIMEOUT) as client:
                resp = await client.post(
                    f"{message.webhook_url.rstrip('/')}/api/send",
                    json=payload,
                    headers=headers,
                )
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                if 200 <= resp.status_code < 300:
                    return PushResult("wechat_clawbot", True, "", json.dumps(data, ensure_ascii=False)[:500])
                return PushResult(
                    "wechat_clawbot",
                    False,
                    f"ClawBot 返回 HTTP {resp.status_code}",
                    json.dumps(data, ensure_ascii=False)[:500],
                    retryable=resp.status_code >= 500,
                )
        except httpx.TimeoutException:
            return PushResult("wechat_clawbot", False, "ClawBot 请求超时", retryable=True)
        except Exception as e:
            return PushResult("wechat_clawbot", False, f"ClawBot 推送异常: {e}", retryable=True)
