"""发现渠道注册表（R7.6）：后台可配置的发现渠道 + 显式默认解析。

背景：`ManifestSyncService` 只依赖 `WorkListProvider` 端口（`services/manifest.py`），
但调度器此前硬编码 `make_redfox_provider(settings)`——渠道是代码里的既定事实，不是
后台可配置项。需求口径是「多种采集方式自动化采集」，实现层却只有一个通道，且换通道要改码。

本模块只做**选择**，不做发现：注册表记录「实现了哪些渠道」，配置记录「启用了哪些」，
`resolve_default_channel` 算出两者的交集并解析出默认渠道。发现逻辑仍全在 `manifest.py`
与各自 provider 内。

诚实纪律沿用 `providers/push_port.registered_channels()`：每个渠道回报
`implemented`（代码是否实接）与 `available`（凭据就位、现在能否真的用），两者**刻意分离**
——「代码在位」≠「现在可用」，合并成单一布尔会把配置缺失伪装成渠道故障，
也让人无从区分「功能没做」与「功能没配」。

向后兼容：`discovery_channels` 为空串 = **不过滤**（所有已注册渠道参与选择），
此时行为与硬编码时代逐字一致（RedFox 有 Key 即用，无 Key 则跳过发现）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.services.manifest import WorkListProvider, make_redfox_provider

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ChannelSpec:
    """一个发现渠道的元数据 + 装配入口 + 就绪判定。

    `implemented`：代码是否实接。False = 端口在位、未接线，缺口写进 `reason`。
    `available`：给定配置现在能否真的用（凭据就位）。与 implemented 分离。
    `required_setting`：凭据缺失时在就绪度回报里点名的配置项名（便于照抄修正）。
    `factory`：装配 provider；不可用时返回 None（显式缺省，不造数）。
    """

    name: str
    description: str
    implemented: bool
    required_setting: str
    available: Callable[[Settings], bool]
    factory: Callable[[Settings], WorkListProvider | None]
    reason: str = ""
    # 证据状态：与 implemented / available **正交**。渠道可以 available=True 而契约从未
    # 活体实测过；两者必须分开，否则「能启用」会被误读成「字段形状已确认」。
    contract_verified_at: str = ""
    verified_scope: str = ""


CHANNELS: dict[str, ChannelSpec] = {
    "redfox": ChannelSpec(
        name="redfox",
        description="RedFox API 清单发现（按 biz 翻页拉取公众号文章清单）",
        implemented=True,
        required_setting="REDFOX_API_KEY",
        available=lambda s: bool(s.redfox_api_key),
        factory=make_redfox_provider,
        # R8 活体实测（2026-09-28）：仅验证到**契约层**——广域库 queryWorkList 的请求体、
        # 响应字段形状、分页步长、错误码映射。端到端（发现→清单→Job→worker 入库）
        # 尚未实测，那是 L1-6 的目标，不是已完成项。
        contract_verified_at="2026-09-28",
        verified_scope="契约层（请求体/响应字段/分页/错误码）；端到端未验证",
    ),
    "rss": ChannelSpec(
        name="rss",
        description="自建 RSS 桥清单发现（RSS item 即 query_work_list 形态，端口零改动可接）",
        implemented=False,
        required_setting="DISCOVERY_RSS_BASE_URL",
        available=lambda s: False,
        factory=lambda s: None,
        reason=(
            "未实接：需先把公众号清单暴露为 HTTP 接口（自建 RSS 桥或同类数据源），"
            "再实接 query_work_list。RSS item 的 {title, link, pubDate} 已由 "
            "manifest._map_row 的字段别名直接消化，接入点只有 _ID_KEYS 需补 guid"
        ),
    ),
}


def _whitelist(settings: Settings) -> set[str]:
    """启用的渠道白名单；空串 = 空集 = 不过滤（调用方据此回落到全量注册渠道）。"""
    return {item.strip() for item in settings.discovery_channels.split(",") if item.strip()}


def enabled_channels(settings: Settings) -> list[str]:
    """参与默认解析的渠道（已注册 ∩ 白名单；白名单为空 = 不过滤）。

    白名单里出现未知渠道名时**忽略并告警**，不静默放行——拼错配置项若被当成有效渠道，
    效果是发现静默停摆且无任何回报，比报错更难查。
    """
    wanted = _whitelist(settings)
    if wanted:
        unknown = wanted - set(CHANNELS)
        if unknown:
            logger.warning("发现渠道白名单含未知渠道（已忽略）: %s", ", ".join(sorted(unknown)))
        return [name for name in CHANNELS if name in wanted]
    return list(CHANNELS)


def available_channels(settings: Settings) -> list[str]:
    """启用且凭据就位的渠道（注册序稳定，dict 插入序）。"""
    return [name for name in enabled_channels(settings) if CHANNELS[name].available(settings)]


def resolve_default_channel(settings: Settings) -> str | None:
    """解析当前默认发现渠道；无可用渠道返回 None（调度器据此跳过发现）。

    选择顺序：`discovery_default_channel`（若在可用集内）→ 可用集中注册序首个 → None。
    由此，「后台只配置了 redfox、没配其他」时 redfox 既是唯一渠道也是默认渠道；
    一个渠道都没启用时返回 None，与历史行为一致。
    """
    available = available_channels(settings)
    if not available:
        return None
    preferred = settings.discovery_default_channel.strip()
    if preferred in available:
        return preferred
    logger.warning(
        "默认发现渠道 %r 不在可用集内（可用：%s），回落到 %r",
        preferred,
        ",".join(available),
        available[0],
    )
    return available[0]


def make_default_provider(settings: Settings) -> WorkListProvider | None:
    """按后台配置装配当前默认渠道的 provider；无可用渠道 → None（跳过发现）。"""
    name = resolve_default_channel(settings)
    if name is None:
        return None
    return CHANNELS[name].factory(settings)


def describe_channels(settings: Settings) -> dict[str, Any]:
    """渠道就绪度全景 + 当前默认解析结果——让「为什么没在发现」可被查询。

    沿用 `push_port.registered_channels()` 的显式回报纪律：`implemented` / `enabled` /
    `available` 三者各自独立，`reason` 说明当前不可用的具体原因（未实接 / 未启用 /
    凭据缺失）。不合并成单一布尔，否则配置缺失会被伪装成渠道故障。
    `defaultChannel=null` 即「本轮调度不做发现」，与调度器的跳过日志同源。
    """
    wanted = _whitelist(settings)
    default = resolve_default_channel(settings)
    channels: list[dict[str, object]] = []
    for name, spec in CHANNELS.items():
        enabled = not wanted or name in wanted
        if not spec.implemented:
            reason = spec.reason
        elif not enabled:
            reason = "未启用（需加入 discovery_channels 白名单）"
        elif spec.available(settings):
            reason = ""
        else:
            reason = f"{spec.required_setting} 未配置"
        channels.append(
            {
                "name": name,
                "description": spec.description,
                "implemented": spec.implemented,
                "enabled": enabled,
                "available": bool(spec.available(settings)),
                "reason": reason,
                "contractVerifiedAt": spec.contract_verified_at,
                "verifiedScope": spec.verified_scope,
            }
        )
    return {
        "channels": channels,
        "defaultChannel": default,
        "selectionReason": _selection_reason(settings, default),
        "configuredChannels": sorted(wanted),
    }


def _selection_reason(settings: Settings, default: str | None) -> str:
    """默认渠道的来源口径：显式配置 / 空配置回落注册序 / 无可用渠道。"""
    if default is None:
        return "none-available"
    return "configured" if _whitelist(settings) else "registration-order"
