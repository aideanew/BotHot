"""飞书自定义机器人推送。

支持两种安全设置：
1. 自定义关键词（默认，webhook_url 即可）
2. 加签模式（需要 secret，计算 HMAC-SHA256 签名）

消息格式：交互式卡片（含标题 + 正文 + 跳转链接）
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import httpx

from .base import PushMessage, PushResult

_FEISHU_TIMEOUT = 10


def _sign(secret: str, timestamp: int) -> str:
    """飞书加签：HMAC-SHA256(timestamp + "\n" + secret)。"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


class FeishuPushProvider:
    name = "feishu"
    description = "飞书自定义机器人 webhook（支持加签验证、交互式卡片消息）"

    async def push(self, message: PushMessage) -> PushResult:
        if not message.webhook_url:
            return PushResult("feishu", False, "飞书 webhook_url 未配置")

        timestamp = int(time.time())
        # 构建卡片消息
        card: dict = {
            "header": {
                "title": {"tag": "plain_text", "content": message.title or "BotHot 推送通知"},
                "template": "blue",
            },
            "elements": [],
        }

        if message.message:
            card["elements"].append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": message.message},
            })

        if message.url:
            card["elements"].append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看详情"},
                    "url": message.url,
                    "type": "primary",
                }],
            })

        payload: dict = {"msg_type": "interactive", "card": card}

        # 加签模式
        if message.secret:
            payload["timestamp"] = str(timestamp)
            payload["sign"] = _sign(message.secret, timestamp)

        try:
            async with httpx.AsyncClient(timeout=_FEISHU_TIMEOUT) as client:
                resp = await client.post(message.webhook_url, json=payload)
                data = resp.json()
                # 飞书成功响应：{"StatusCode":0,"StatusMessage":"success"} 或 {"code":0}
                code = data.get("StatusCode", data.get("code", -1))
                if code == 0:
                    return PushResult("feishu", True, "", json.dumps(data, ensure_ascii=False)[:500])
                return PushResult(
                    "feishu",
                    False,
                    f"飞书返回错误: {data}",
                    json.dumps(data, ensure_ascii=False)[:500],
                    retryable=False,
                )
        except httpx.TimeoutException:
            return PushResult("feishu", False, "飞书 webhook 请求超时", retryable=True)
        except Exception as e:
            return PushResult("feishu", False, f"飞书推送异常: {e}", retryable=True)
