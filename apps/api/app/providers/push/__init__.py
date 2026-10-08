"""BotHot 多渠道推送 Provider 包。

渠道一览：
- feishu：飞书自定义机器人 webhook（支持加签验证）
- dingtalk：钉钉自定义机器人 webhook（支持加签验证）
- wechat_work：企业微信群机器人 webhook
- webhook：通用 webhook（POST JSON）
- wechat_clawbot：微信 ClawBot（出站消息 API）
- web：站内通知（Redis pub/sub → 前端 SSE 订阅实时推送；订阅侧见 api/v1/system.py /notifications）

每个 Provider 实现 PushProvider 协议（一个 async push 方法）。
注册表 make_push_provider(channel) 按名取实例。
"""

from .base import PushMessage, PushProvider, PushResult
from .dingtalk import DingtalkPushProvider
from .feishu import FeishuPushProvider
from .web import WebPushProvider
from .webhook import WebhookPushProvider
from .wechat_clawbot import WechatClawbotPushProvider
from .wechat_work import WechatWorkPushProvider

# 注册表：channel_type → provider 实例
_PROVIDERS: dict[str, PushProvider] = {
    "feishu": FeishuPushProvider(),
    "dingtalk": DingtalkPushProvider(),
    "wechat_work": WechatWorkPushProvider(),
    "webhook": WebhookPushProvider(),
    "wechat_clawbot": WechatClawbotPushProvider(),
    "web": WebPushProvider(),
}

# 合法渠道列表
PUSH_CHANNELS: tuple[str, ...] = tuple(_PROVIDERS.keys())


def make_push_provider(channel: str) -> PushProvider:
    """按渠道名取 provider 实例；未知渠道抛 ValueError。"""
    provider = _PROVIDERS.get(channel)
    if provider is None:
        raise ValueError(f"未知推送通道: {channel}（合法：{'/'.join(PUSH_CHANNELS)}）")
    return provider


def registered_channels() -> list[dict[str, object]]:
    """注册表全景——管理端查询渠道就绪度。"""
    return [
        {
            "channel": channel,
            "implemented": True,
            "description": provider.description,
        }
        for channel, provider in _PROVIDERS.items()
    ]


__all__ = [
    "PushMessage",
    "PushProvider",
    "PushResult",
    "make_push_provider",
    "registered_channels",
    "PUSH_CHANNELS",
]
