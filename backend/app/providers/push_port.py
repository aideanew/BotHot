"""SPEC-M3 批次 5 / T6.2 推送通道端口层（扩展点④，引 ADR-0002）。

PushProvider：通道最小契约（单一 push 方法）+ `channel → PushProvider` 注册表。
本批为**诚实占位**（2026-09-23 管理者裁定）：两个通道都落接口与注册表，但都
不实接，且**绝不返回「已投递」的假回执**——回执里的 `delivered` 为假时必须
给出可读 `reason`，否则等同于 F-4 那类「显示成功、实际没发生」。

- **web**：站内通知占位。项目内无通知表、无站内读端点，投递面不存在。
  **不新建通知表**：web 若无读侧就变成第二个 `BotBinding` 死表（F-8 先例）。
- **clawbot**：出站契约在项目内不存在。ADR-0002 附录 A 记录的是 clawbot →
  backend 的**入站验签**契约（校验请求签名）；backend → 微信用户 的出站发消息
  API 无契约可引（`LangBotClient` 仅 LangBot 管理面 KB/ingest/retrieve），且
  T6.1 已裁定 HTTP Bot 路径从未存在并由 A 批复否决。活体半程挂微信凭据 +
  出站契约缺口登记，**不谎报为已通**。

通道未就绪时由服务层转 **50002**（依赖不可用）——与 T5.4「主密钥缺失」同口径：
不是权限问题（10004，operator 有角色）、也不是请求错误（10005，请求没问题），
是能力未就绪。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PushMessage:
    """一次推送的内容：通道侧目标 + 可选空间/文档引用 + 可选正文。

    三者（message / space_id / doc_id）至少一项非空——由服务层校验，本层不判。
    """

    external_user_id: str
    space_id: str = ""
    doc_id: str = ""
    message: str = ""


@dataclass(frozen=True)
class PushResult:
    """推送回执。`delivered=False` 时 `reason` 必须非空且可读。"""

    channel: str
    delivered: bool
    reason: str


class PushProvider(Protocol):
    """通道最小契约：一个通道一个 push 方法。

    `implemented` 与 `reason` 成对出现：未实接的通道必须给出可读拒绝原因，
    注册表据此显式回报就绪度（就绪度不该只能靠试推撞出 50002）。
    """

    name: str
    implemented: bool
    reason: str

    async def push(self, message: PushMessage) -> PushResult:
        """投递一条消息。未实接的通道必须返回 delivered=False + reason。"""
        ...


class WebPushProvider:
    """web 通道——站内通知占位。无投递面，显式拒绝（不假装已投递）。"""

    name = "web"
    implemented = False
    reason = "web 通道无站内投递面（无通知表、无读端点），本批不构建"

    async def push(self, message: PushMessage) -> PushResult:
        return PushResult(self.name, False, self.reason)


class ClawbotPushProvider:
    """clawbot 通道——接口与注册表已落，出站契约缺口 + 挂微信凭据。"""

    name = "clawbot"
    implemented = False
    reason = (
        "clawbot 出站契约项目内不存在（ADR-0002 附录 A 仅入站验签），"
        "且微信凭据未注入——活体半程未通"
    )

    async def push(self, message: PushMessage) -> PushResult:
        return PushResult(self.name, False, self.reason)


PUSH_CHANNELS: tuple[str, ...] = ("web", "clawbot")

_PROVIDERS: dict[str, PushProvider] = {
    WebPushProvider.name: WebPushProvider(),
    ClawbotPushProvider.name: ClawbotPushProvider(),
}


def make_push_provider(channel: str) -> PushProvider:
    """按通道名取 provider；未知通道不臆造（调用方转 10005）。"""
    provider = _PROVIDERS.get(channel)
    if provider is None:
        raise ValueError(f"未知推送通道: {channel}（合法：{'/'.join(PUSH_CHANNELS)}）")
    return provider


def registered_channels() -> list[dict[str, object]]:
    """注册表全景——让通道就绪度可被显式查询，而非只能靠试推撞出 50002。

    `implemented=False` 即「接口在位、投递未实接」，与 `reason` 一起构成
    不谎报的口径（同 T5.4 的 `masterKeyConfigured` / `activeSource` 纪律）。
    """
    return [
        {"channel": channel, "implemented": bool(provider.implemented), "reason": provider.reason}
        for channel, provider in _PROVIDERS.items()
    ]
