"""STEP-45（P-116）：`_next_anchored_run` 的两个分支必须由固定时钟覆盖，不能看 CI 几点跑。

背景：既有用例用真实时钟、锚 10 点/12 点（Asia/Shanghai）。上海时间 0～10 点之间跑，
"锚点已过 ⇒ 顺延一天"那一行永远走不到，`app/services/subscription.py` 少 1 行覆盖，
模块覆盖率门（85%）恰好掉到 84.95% 判红——main@7e4c10e 的 CI（00:22 CST）即如此。
这里冻结 `datetime.now`，两个分支各钉一次，与墙钟无关。
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import app.services.subscription as sub_mod
from app.services.subscription import SourceSubscriptionService

_SH = ZoneInfo("Asia/Shanghai")


def _freeze(monkeypatch: pytest.MonkeyPatch, frozen_local: datetime, zone: str = "Asia/Shanghai") -> None:
    frozen_utc = frozen_local.astimezone(UTC)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return frozen_utc if tz is None else frozen_utc.astimezone(tz)

    monkeypatch.setattr(sub_mod, "datetime", _FrozenDatetime)
    monkeypatch.setattr(sub_mod, "get_settings", lambda: SimpleNamespace(scheduler_timezone=zone))


def test_anchor_still_ahead_today_fires_today(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze(monkeypatch, datetime(2026, 10, 24, 0, 22, tzinfo=_SH))
    got = SourceSubscriptionService._next_anchored_run(10)
    assert got == datetime(2026, 10, 24, 10, 0, tzinfo=_SH)


def test_anchor_already_passed_rolls_to_tomorrow(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze(monkeypatch, datetime(2026, 10, 24, 15, 0, tzinfo=_SH))
    got = SourceSubscriptionService._next_anchored_run(10)
    assert got == datetime(2026, 10, 25, 10, 0, tzinfo=_SH)


def test_exactly_on_anchor_counts_as_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    """严格取"下一次"整点：恰好 10:00:00 也顺延（与调度器 `_anchor_base` 同口径）。"""
    _freeze(monkeypatch, datetime(2026, 10, 24, 10, 0, tzinfo=_SH))
    got = SourceSubscriptionService._next_anchored_run(10)
    assert got == datetime(2026, 10, 25, 10, 0, tzinfo=_SH)


def test_unknown_zone_falls_back_to_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze(monkeypatch, datetime(2026, 10, 24, 3, 0, tzinfo=UTC), zone="No/Such_Zone")
    got = SourceSubscriptionService._next_anchored_run(10)
    assert got == datetime(2026, 10, 24, 10, 0, tzinfo=UTC)


def test_no_anchor_means_now(monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = datetime(2026, 10, 24, 0, 22, tzinfo=_SH)
    _freeze(monkeypatch, frozen)
    assert SourceSubscriptionService._next_anchored_run(None) == frozen.astimezone(UTC)
