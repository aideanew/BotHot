"""推送 Provider 基类与协议。

PushProvider 协议：每个渠道实现一个 async push 方法。
- PushMessage：入参（目标 + 内容）
- PushResult：回执（成功/失败 + 原因）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PushMessage:
    """一次推送的内容。"""

    # 投递目标标识（webhook 模式下可为空，用 BotChannel.webhook_url）
    external_user_id: str = ""
    # 推送正文
    message: str = ""
    # 可选：关联空间/文档（用于卡片消息的跳转链接）
    space_id: str = ""
    doc_id: str = ""
    # 可选：标题（卡片消息用）
    title: str = ""
    # 可选：来源 URL（卡片消息的跳转链接）
    url: str = ""
    # 渠道配置（webhook_url, secret 等）——由 PushService 注入
    webhook_url: str = ""
    secret: str = ""
    extra_config: str = "{}"


@dataclass(frozen=True)
class PushResult:
    """推送回执。"""

    channel: str
    delivered: bool
    reason: str = ""
    response_data: str = ""


class PushProvider(Protocol):
    """渠道最小契约：一个 push 方法 + 元数据。"""

    name: str
    description: str

    async def push(self, message: PushMessage) -> PushResult:
        """投递一条消息。"""
        ...
