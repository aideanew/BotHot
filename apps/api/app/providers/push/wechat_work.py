"""企业微信群机器人推送。

安全设置：webhook URL 本身含 key 即为鉴权。
消息格式：Markdown（含标题 + 正文 + 跳转链接）
"""

from __future__ import annotations

import json

import httpx

from .base import PushMessage, PushResult

_WECHAT_WORK_TIMEOUT = 10


class WechatWorkPushProvider:
    name = "wechat_work"
    description = "企业微信群机器人 webhook（Markdown 消息）"

    async def push(self, message: PushMessage) -> PushResult:
        if not message.webhook_url:
            return PushResult("wechat_work", False, "企业微信 webhook_url 未配置")

        title = message.title or "BotHot 推送通知"
        md_lines = [f"# {title}"]
        if message.message:
            md_lines.append(message.message)
        if message.url:
            md_lines.append(f"[查看详情]({message.url})")
        md_text = "\n".join(md_lines)

        payload = {
            "msgtype": "markdown",
            "markdown": {"content": md_text},
        }

        try:
            async with httpx.AsyncClient(timeout=_WECHAT_WORK_TIMEOUT) as client:
                resp = await client.post(message.webhook_url, json=payload)
                data = resp.json()
                # 企业微信成功响应：{"errcode":0,"errmsg":"ok"}
                if data.get("errcode") == 0:
                    return PushResult("wechat_work", True, "", json.dumps(data, ensure_ascii=False)[:500])
                return PushResult(
                    "wechat_work",
                    False,
                    f"企业微信返回错误: {data.get('errmsg', '')}",
                    json.dumps(data, ensure_ascii=False)[:500],
                    retryable=False,
                )
        except httpx.TimeoutException:
            return PushResult("wechat_work", False, "企业微信 webhook 请求超时", retryable=True)
        except Exception as e:
            return PushResult("wechat_work", False, f"企业微信推送异常: {e}", retryable=True)
