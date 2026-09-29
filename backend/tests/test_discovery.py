"""R7.6 发现渠道注册表验收：后台配置的渠道选择 + 显式默认解析 + 就绪度回报。

口径（见 `app/providers/discovery/registry.py` 模块文档）：
- **向后兼容**：`discovery_channels` 空串 = 不过滤，行为与渠道硬编码时代逐字一致
  （RedFox 有 Key → 装配 provider；无 Key → None，调度器跳过发现）。
- **需求口径**：后台只配置了 redfox、没配其他 → redfox 既是唯一渠道也是默认渠道。
- **诚实回报**：implemented / enabled / available 三者分离，reason 点名具体缺口
  （未实接 / 未启用 / 凭据缺失），不合并成单一布尔。
- **不静默放行**：白名单含未知渠道 → 忽略并告警；默认渠道不在可用集 → 回落并告警。
  拼错配置项若被当成有效渠道，效果是发现静默停摆且无任何回报，比报错更难查。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user_id, get_db
from app.core.config import Settings
from app.main import create_app
from app.models.entities import User
from app.providers.discovery.registry import (
    CHANNELS,
    available_channels,
    describe_channels,
    enabled_channels,
    make_default_provider,
    resolve_default_channel,
)
from app.services import scheduler as scheduler_module


def _settings(*, channels: str = "", default: str = "redfox", key: str = "") -> Settings:
    """三值全部显式指定——否则 Settings 会继承 .env，用例失去确定性。"""
    return Settings(discovery_channels=channels, discovery_default_channel=default, redfox_api_key=key)


# ------------------------------------------------------------------ 默认解析：兼容与需求口径


def test_empty_config_with_key_matches_hardcoded_era() -> None:
    """向后兼容：空配置 + 有 Key → 取 redfox（与硬编码 `make_redfox_provider` 同结果）。"""
    assert resolve_default_channel(_settings(key="k-1")) == "redfox"
    provider = make_default_provider(_settings(key="k-1"))
    assert provider is not None and hasattr(provider, "query_work_list")


def test_empty_config_without_key_returns_none() -> None:
    """向后兼容：空配置 + 无 Key → None（调度器跳过发现，不造数）。"""
    assert resolve_default_channel(_settings(key="")) is None
    assert make_default_provider(_settings(key="")) is None


def test_only_redfox_configured_is_sole_default() -> None:
    """需求口径：只配置了 redfox、没配其他 → redfox 是唯一渠道也是默认渠道。"""
    s = _settings(channels="redfox", default="redfox", key="k-1")
    assert enabled_channels(s) == ["redfox"]
    assert available_channels(s) == ["redfox"]
    assert resolve_default_channel(s) == "redfox"


def test_whitelist_without_credentials_yields_no_channel() -> None:
    """启用但未配凭据 → 无可用渠道（不能因为「已启用」就假装可用）。"""
    assert resolve_default_channel(_settings(channels="redfox", key="")) is None
    assert make_default_provider(_settings(channels="redfox", key="")) is None


def test_whitelist_ignores_unknown_channel() -> None:
    """白名单含未知渠道 → 忽略未知项，仍能从已知渠道解析出结果（不整体失败）。"""
    assert resolve_default_channel(_settings(channels="redfox,typos", key="k-1")) == "redfox"
    # 仅剩未知项 → 无可用渠道
    assert resolve_default_channel(_settings(channels="typos", key="k-1")) is None


def test_whitelist_unknown_channel_is_warned(caplog: pytest.LogCaptureFixture) -> None:
    """未知渠道必须留痕——静默忽略会让「拼错了」与「没配置」不可区分。"""
    with caplog.at_level("WARNING"):
        enabled_channels(_settings(channels="typos", key="k-1"))
    assert "typos" in caplog.text


def test_unimplemented_channel_is_never_selected() -> None:
    """未实接渠道（rss）永不可选：available 恒假，不会因被写进白名单而假装可用。"""
    s = _settings(channels="rss", key="k-1")
    assert enabled_channels(s) == ["rss"]
    assert available_channels(s) == []
    assert resolve_default_channel(s) is None
    assert make_default_provider(s) is None


def test_default_falls_back_when_preferred_unavailable() -> None:
    """默认渠道不在可用集 → 回落注册序首个可用渠道。"""
    assert resolve_default_channel(_settings(channels="rss,redfox", default="rss", key="k-1")) == "redfox"


def test_unknown_default_falls_back_to_registration_order() -> None:
    """默认渠道名写错 → 不整体失败，回落首个可用渠道（行为可预期）。"""
    assert resolve_default_channel(_settings(channels="", default="nosuch", key="k-1")) == "redfox"


def test_whitelist_is_order_insensitive() -> None:
    """白名单顺序不影响解析；输出按注册序而非配置序。"""
    a = _settings(channels="redfox", default="redfox", key="k-1")
    b = _settings(channels=" redfox , rss ", default="redfox", key="k-1")
    assert resolve_default_channel(a) == resolve_default_channel(b) == "redfox"
    assert enabled_channels(b) == ["redfox", "rss"]


# ------------------------------------------------------------------ 就绪度回报


def test_describe_reports_all_three_axes_separately() -> None:
    """可用渠道：三轴全真，reason 为空串（是「无原因」的显式值，不是缺失字段）。"""
    data = describe_channels(_settings(channels="redfox", key="k-1"))
    entry = next(c for c in data["channels"] if c["name"] == "redfox")
    assert entry["implemented"] is True and entry["enabled"] is True and entry["available"] is True
    assert entry["reason"] == ""
    assert data["defaultChannel"] == "redfox"
    assert data["selectionReason"] == "configured"
    assert data["configuredChannels"] == ["redfox"]


def test_describe_reports_contract_evidence_status() -> None:
    """证据状态独立回报：`available=True` 不等于「契约已实测」。

    R8 的红狐渠道只验证到契约层，端到端尚未实测——这个事实必须能被后台查询到，
    否则「能启用」会被误读成「字段形状已确认」。未实接渠道两字段为空串。
    """
    data = describe_channels(_settings(channels="redfox", key="k-1"))
    redfox = next(c for c in data["channels"] if c["name"] == "redfox")
    assert redfox["contractVerifiedAt"] == "2026-09-28"
    assert "契约层" in str(redfox["verifiedScope"])
    rss = next(c for c in data["channels"] if c["name"] == "rss")
    assert rss["contractVerifiedAt"] == "" and rss["verifiedScope"] == ""


def test_describe_reason_names_the_missing_credential() -> None:
    """启用但未配凭据 → reason 点名配置项名（照抄即可修正）。"""
    data = describe_channels(_settings(channels="redfox", key=""))
    entry = next(c for c in data["channels"] if c["name"] == "redfox")
    assert entry["available"] is False
    assert "REDFOX_API_KEY" in str(entry["reason"])
    assert data["defaultChannel"] is None
    assert data["selectionReason"] == "none-available"


def test_describe_reason_distinguishes_unimplemented_from_disabled() -> None:
    """「功能没做」与「功能没配」必须可区分：文案不同源，不共用一条 reason。"""
    data = describe_channels(_settings(channels="redfox", key="k-1"))
    rss = next(c for c in data["channels"] if c["name"] == "rss")
    assert rss["implemented"] is False and rss["enabled"] is False and rss["available"] is False
    assert "未实接" in str(rss["reason"])


def test_describe_empty_config_marks_all_enabled() -> None:
    """空配置 = 不过滤：所有渠道 enabled，来源标注 registration-order。"""
    data = describe_channels(_settings(channels="", key="k-1"))
    assert data["configuredChannels"] == []
    assert data["selectionReason"] == "registration-order"
    assert all(c["enabled"] is True for c in data["channels"])


# ------------------------------------------------------------------ 调度器接线


def test_default_runner_delegates_channel_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    """make_default_sync_runner 只做装配，渠道选择委托注册表（不在调度器里判渠道）。"""
    calls: list[Settings] = []

    def _record(s: Settings) -> object:
        calls.append(s)
        return object()

    monkeypatch.setattr(scheduler_module, "make_default_provider", _record)
    settings = _settings(channels="redfox", key="k-1")
    assert scheduler_module.make_default_sync_runner(settings) is not None
    assert calls == [settings]


def test_default_runner_skips_when_no_channel_available(caplog: pytest.LogCaptureFixture) -> None:
    """无可用渠道 → 仍返回 runner（只跳过发现），并在装配期留痕原因。"""
    with caplog.at_level("WARNING"):
        runner = scheduler_module.make_default_sync_runner(_settings(key=""))
    assert runner is not None
    assert "发现渠道全部不可用" in caplog.text


# ------------------------------------------------------------------ 管理端读侧


async def _seed_operator(db_session: Any) -> str:  # type: ignore[no-untyped-def]
    op = User(sub="r76-op", email="r76-op@r76.test", nickname="op", role="operator")
    db_session.add(op)
    await db_session.flush()
    return op.id


async def test_admin_discovery_channels_endpoint(
    db_session: Any, monkeypatch: pytest.MonkeyPatch  # type: ignore[no-untyped-def]
) -> None:
    """operator+ 放行；回报注册表全景 + 当前默认渠道解析（就绪度不靠翻日志）。"""
    from app.api.v1 import admin as admin_module

    monkeypatch.setattr(admin_module, "get_settings", lambda: _settings(channels="redfox", key="k-1"))
    operator_id = await _seed_operator(db_session)

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user_id] = lambda: operator_id

    resp = TestClient(app).get("/api/v1/admin/discovery/channels")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert [c["name"] for c in data["channels"]] == list(CHANNELS)
    assert data["defaultChannel"] == "redfox"
    assert data["selectionReason"] == "configured"


async def test_admin_discovery_channels_role_gates(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """门禁：user 秩 → 10004/403；未登录 → 10001/401（与 push/channels 同口径）。"""
    plain = User(sub="r76-plain", email="r76-plain@r76.test", nickname="plain")
    db_session.add(plain)
    await db_session.flush()

    gated = create_app()
    gated.dependency_overrides[get_db] = lambda: db_session
    gated.dependency_overrides[get_current_user_id] = lambda: plain.id
    resp = TestClient(gated).get("/api/v1/admin/discovery/channels")
    assert resp.status_code == 403 and resp.json()["code"] == 10004

    anonymous = create_app()
    anonymous.dependency_overrides[get_db] = lambda: db_session
    resp = TestClient(anonymous).get("/api/v1/admin/discovery/channels")
    assert resp.status_code == 401 and resp.json()["code"] == 10001
