"""钉钉自定义机器人推送。

支持三种安全设置：
1. 自定义关键词
2. 加签模式（需要 secret）
3. IP 地址段

消息格式：Markdown（含标题 + 正文 + 跳转链接）
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.parse

import httpx

from .base import PushMessage, PushResult

_DINGTALK_TIMEOUT = 10


def _sign(secret: str, timestamp: int) -> tuple[str, str]:
    """钉钉加签：HMAC-SHA256(timestamp + "\n" + secret)，base64 + urlencode。"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode("utf-8"))
    return str(timestamp), sign


class DingtalkPushProvider:
    name = "dingtalk"
    description = "钉钉自定义机器人 webhook（支持加签验证、Markdown 消息）"

    async def push(self, message: PushMessage) -> PushResult:
        if not message.webhook_url:
            return PushResult("dingtalk", False, "钉钉 webhook_url 未配置")

        url = message.webhook_url
        # 加签模式：URL 追加 timestamp & sign
        if message.secret:
            timestamp, sign = _sign(message.secret, int(time.time() * 1000))
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}timestamp={timestamp}&sign={sign}"

        # 构建 Markdown 消息
        title = message.title or "BotHot 推送通知"
        md_lines = [f"### {title}"]
        if message.message:
            md_lines.append(message.message)
        if message.url:
            md_lines.append(f"\n[查看详情]({message.url})")
        md_text = "\n\n".join(md_lines)

        payload = {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": md_text},
            "at": {"isAtAll": False},
        }

        try:
            async with httpx.AsyncClient(timeout=_DINGTALK_TIMEOUT) as client:
                resp = await client.post(url, json=payload)
                data = resp.json()
                # 钉钉成功响应：{"errcode":0,"errmsg":"ok"}
                if data.get("errcode") == 0:
                    return PushResult("dingtalk", True, "", json.dumps(data, ensure_ascii=False)[:500])
                return PushResult(
                    "dingtalk",
                    False,
                    f"钉钉返回错误: {data.get('errmsg', '')}",
                    json.dumps(data, ensure_ascii=False)[:500],
                    retryable=False,
                )
        except httpx.TimeoutException:
            return PushResult("dingtalk", False, "钉钉 webhook 请求超时", retryable=True)
        except Exception as e:
            return PushResult("dingtalk", False, f"钉钉推送异常: {e}", retryable=True)
