"""STEP-05 S5.1.1 先红：采集静默必须出声（指标 + 事件 + 一天一次的告警）。

判据形状取自**冻结契约**（`app/contracts/collection.py`），不是本文件自造：

- `ManifestSyncReport.all_skipped_pages`（稿 `:176`，"skipped == rows > 0 的页数；>0 记 ERROR + 告警"）；
- `CollectionEvent`（稿 `:210-233`）：`event` 词表含 `discovery.page_all_skipped`，
  `idempotency_key` 是 page 级 `{source_id}:{channel}:{yyyymmdd}:{page}`，"告警按此键一天一次"；
- `DiscoveryChannelView.lastSuccessAt/lastError`（稿 `:204-207`）。

本文件全部不连库：同步用桩会话（`_known_count` 走 `session.scalar`，全丢弃页不写库），
投递换 `alerting._deliver` 的捕获桩，探测用桩 session 返回固定行，
P-9 的查库 miss 与 P-30 的落库异常同样用桩注入。
"""

from __future__ import annotations

import dataclasses
import re
from datetime import UTC, datetime
from typing import Any

import pytest
from prometheus_client import REGISTRY, generate_latest
from structlog.testing import capture_logs

from app.contracts.collection import CollectionEvent
from app.contracts.collection import ManifestSyncReport as ContractReport
from app.core import alerting, metrics
from app.core.errors import DependencyUnavailableError
from app.services.manifest import ManifestSyncReport, ManifestSyncService

_SOURCE = "s05-source-1"
_BIZ = "S05BIZ"
_FRAMEWORK_KEYS = {"event", "log_level", "level", "timestamp", "logger"}


class _StubSyncSession:
    """只满足 `sync_source` 实际用到的两个方法：`scalar`（本地已入库数）与 `flush`。"""

    def __init__(self) -> None:
        self.flushed = 0

    async def scalar(self, _stmt: Any) -> int:
        return 0

    async def flush(self) -> None:
        self.flushed += 1


class _StubProvider:
    name = "redfox"

    def __init__(self, pages: list[list[dict[str, Any]]], *, fail: bool = False) -> None:
        self.pages = pages
        self.fail = fail
        self.calls = 0

    async def query_work_list(self, _biz: str, page: int) -> tuple[list[dict[str, Any]], int | None]:
        self.calls += 1
        if self.fail:
            raise DependencyUnavailableError("上游 5xx")
        rows = self.pages[page - 1] if page - 1 < len(self.pages) else []
        return rows, None

    async def aclose(self) -> None:
        pass


def _dropped_row(tag: str) -> dict[str, Any]:
    """既无 id 又无 URL —— `_map_row` 唯一返回 None 的形状。"""
    return {"title": f"脏行-{tag}"}


def _clean_row(work_id: str) -> dict[str, Any]:
    return {"id": work_id, "workUrl": f"https://mp.weixin.qq.com/s?__biz=MzA5&sn={work_id}", "title": "T"}


def _fallback_row() -> dict[str, Any]:
    """无 id、有 URL：S3.3.3 的规范键兜底建行（计 fallback，不计 dropped）。"""
    return {"workUrl": "https://mp.weixin.qq.com/s?__biz=MzA5&sn=fallback1", "title": "只有 URL"}


async def _sync(
    provider: _StubProvider,
    *,
    page_size: int = 2,
    max_pages: int = 1,
    session: _StubSyncSession | None = None,
) -> ManifestSyncReport:
    svc = ManifestSyncService(session or _StubSyncSession(), provider, page_size=page_size)  # type: ignore[arg-type]
    return await svc.sync_source(_SOURCE, _BIZ, max_pages=max_pages)


def _counter(metric: str, **labels: str) -> float:
    family = REGISTRY._names_to_collectors.get(metric)  # noqa: SLF001
    assert family is not None, f"指标族未注册：{metric}"
    return float(family.labels(**labels)._value.get())  # noqa: SLF001


@pytest.fixture(autouse=True)
def _state_reset() -> Any:
    alerting.reset_alert_cooldown_state()
    yield
    alerting.reset_alert_cooldown_state()


@pytest.fixture()
def delivered(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """投递捕获桩：本文件永不真发，且默认打开总开关。"""
    out: list[tuple[str, str]] = []

    async def _capture(title: str, message: str) -> bool:
        out.append((title, message))
        return True

    monkeypatch.setattr(alerting, "_deliver", _capture)
    monkeypatch.setenv("ALERTING_ENABLED", "1")
    return out


# ── S5.2.1 指标族上线 ──────────────────────────────────────────────────────────


def test_metrics_endpoint_exposes_the_discovery_families() -> None:
    text = generate_latest(REGISTRY).decode("utf-8")
    for name in (
        "bothot_discovery_calls_total",
        "bothot_manifest_rows_total",
        "bothot_discovery_page_all_skipped_total",
        "bothot_discovery_last_success_timestamp",
    ):
        assert re.search(rf"^# HELP {name} ", text, re.MULTILINE), f"/metrics 缺指标族 {name}"


# ── S5.2.2 埋点：整页全丢弃、行结果、调用结果、最近成功时间 ────────────────────


async def test_all_dropped_page_is_counted_and_emits_the_contract_event() -> None:
    provider = _StubProvider([[_dropped_row("a"), _dropped_row("b")]])
    before = _counter("bothot_discovery_page_all_skipped_total", channel="redfox")

    with capture_logs() as logs:
        report = await _sync(provider, page_size=2, max_pages=1)

    assert report.all_skipped_pages == 1, "整页全丢弃必须单独成计数（冻结稿 collection.py:176）"
    assert report.skipped == 2
    assert _counter("bothot_discovery_page_all_skipped_total", channel="redfox") == before + 1.0

    hits = [e for e in logs if e["event"] == "discovery.page_all_skipped"]
    assert len(hits) == 1, f"整页丢弃必须发一条 discovery.page_all_skipped，实际 {len(hits)} 条"
    assert hits[0]["log_level"] == "error"
    payload = {k: v for k, v in hits[0].items() if k not in _FRAMEWORK_KEYS}
    event = CollectionEvent.model_validate({"event": hits[0]["event"], **payload})
    # 期望值从**事件自带的时间戳**推出来，不再第二次调 `_page_date()`：
    # 本文件在 23:59 起跑过一次，动作时是 20 日、断言时已是 21 日，期望值被算成两天后。
    stamp = event.at.astimezone(alerting.DISCOVERY_TZ).strftime("%Y%m%d")
    assert event.idempotency_key == f"{_SOURCE}:redfox:{stamp}:1"
    assert event.count == 2


def test_day_key_uses_the_business_day_boundary_not_utc() -> None:
    """UTC 10-20 17:00 已是上海 10-21 01:00 ⇒ 键里的 yyyymmdd 必须是业务日，不是 UTC 日。

    跨零点的告警如果按 UTC 切日，同一件事在 8 小时内会被算成"两天各一次" ⇒ 一天一次不成立。
    """
    at = datetime(2026, 10, 20, 17, 0, tzinfo=UTC)
    assert alerting.discovery_day_key("s-1", "redfox", at) == "s-1:redfox:20261021"
    assert alerting.discovery_idempotency_key("s-1", "redfox", 3, at=at) == "s-1:redfox:20261021:3"


async def test_page_all_skipped_alert_fires_once_per_day(delivered: list[tuple[str, str]]) -> None:
    await _sync(_StubProvider([[_dropped_row("a"), _dropped_row("b")]]), page_size=2, max_pages=1)
    assert len(delivered) == 1, f"整页丢弃应投出一条告警，实际 {len(delivered)} 条"

    await _sync(_StubProvider([[_dropped_row("c"), _dropped_row("d")]]), page_size=2, max_pages=1)
    assert len(delivered) == 1, "同日同源同渠道不得重复投递（契约：告警按幂等键一天一次）"


async def test_p0_3_replay_alert_fires_on_the_pre_step_03_mapping(
    monkeypatch: pytest.MonkeyPatch,
    delivered: list[tuple[str, str]],
) -> None:
    """卡面 §1 的可证伪要求：把 `_map_row` 退回 STEP-03 之前（缺 id 就丢整行），同一页必须告警。

    输入用的是**今天会被兜底收下**的形状（有 URL 无 id）。所以这条判的不是我随手造的脏行，
    而是「上游返回正常、本仓零入库」那一整族——P0-3 当时的症状正是它。
    """
    rows = [_fallback_row(), {"workUrl": "https://mp.weixin.qq.com/s?__biz=MzA5&sn=fallback2", "title": "T2"}]

    def _legacy_map_row(_row: dict[str, Any]) -> None:
        return None

    monkeypatch.setattr("app.services.manifest._map_row", _legacy_map_row)

    report = await _sync(_StubProvider([rows]), page_size=4, max_pages=1)

    assert (report.discovered, report.skipped) == (0, 2)
    assert report.all_skipped_pages == 1, "P0-3 回放必须落在告警上：整页零入库"
    assert len(delivered) == 1, f"P0-3 回放没告警：{delivered}"


async def test_row_result_counters_cover_dropped_fallback_and_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_upsert(self: ManifestSyncService, _source_id: str, _mapped: dict[str, Any]) -> str:
        return "discovered"

    monkeypatch.setattr(ManifestSyncService, "_upsert", _fake_upsert)
    rows = [_dropped_row("x"), _fallback_row(), _clean_row("w1")]
    before = {
        r: _counter("bothot_manifest_rows_total", channel="redfox", result=r)
        for r in ("discovered", "dropped", "fallback")
    }

    report = await _sync(_StubProvider([rows]), page_size=4, max_pages=1)

    assert (report.discovered, report.skipped, report.id_fallback) == (2, 1, 1)
    assert _counter("bothot_manifest_rows_total", channel="redfox", result="discovered") == before["discovered"] + 2.0
    assert _counter("bothot_manifest_rows_total", channel="redfox", result="dropped") == before["dropped"] + 1.0
    assert _counter("bothot_manifest_rows_total", channel="redfox", result="fallback") == before["fallback"] + 1.0
    assert report.all_skipped_pages == 0, "有行被收下就不算整页丢弃"


async def test_call_outcome_and_last_success_are_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_upsert(self: ManifestSyncService, _source_id: str, _mapped: dict[str, Any]) -> str:
        return "discovered"

    monkeypatch.setattr(ManifestSyncService, "_upsert", _fake_upsert)
    before = _counter("bothot_discovery_calls_total", channel="redfox", outcome="success")
    await _sync(_StubProvider([[_clean_row("w1")]]), page_size=2, max_pages=1)
    assert _counter("bothot_discovery_calls_total", channel="redfox", outcome="success") == before + 1.0

    gauge = metrics.DISCOVERY_LAST_SUCCESS_TIMESTAMP.labels(channel="redfox")  # noqa: SLF001
    assert gauge._value.get() > 0, "最近成功时间必须被写入（Gauge）"  # noqa: SLF001


async def test_upstream_failure_is_counted_and_still_raises() -> None:
    before = _counter("bothot_discovery_calls_total", channel="redfox", outcome="failed")
    with pytest.raises(DependencyUnavailableError):
        await _sync(_StubProvider([], fail=True))
    assert _counter("bothot_discovery_calls_total", channel="redfox", outcome="failed") == before + 1.0


# ── S5.2.3 探测：连续 N 轮空轮询（跨进程，读既有库列）──────────────────────────


class _Rows:
    def __init__(self, rows: list[tuple[str, str, int]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[str, str, int]]:
        return self._rows


class _ProbeSession:
    def __init__(self, rows: list[tuple[str, str, int]]) -> None:
        self.rows = rows
        self.sql = ""

    async def execute(self, stmt: Any) -> _Rows:
        self.sql = str(stmt)
        return _Rows(self.rows)


async def test_silence_probe_returns_only_sources_at_or_over_threshold() -> None:
    session = _ProbeSession([("s-quiet", "安静公众号", 7), ("s-ok", "正常公众号", 2)])
    hits = await alerting.check_discovery_silence(session, threshold=3)  # type: ignore[arg-type]
    assert [(h["source_id"], h["rounds"]) for h in hits] == [("s-quiet", 7)], f"阈值判定错位：{hits}"


class _Factory:
    def __init__(self, rows: list[tuple[str, str, int]]) -> None:
        self.rows = rows

    def __call__(self) -> _Factory:
        return self

    async def __aenter__(self) -> _ProbeSession:
        return _ProbeSession(self.rows)

    async def __aexit__(self, *_exc: object) -> None:
        return None


def _stub_other_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_stale(_session: Any) -> list[str]:
        return []

    async def _no_backlog(_session: Any) -> int:
        return 0

    async def _no_failures(_session: Any, _window: int) -> bool:
        return False

    monkeypatch.setattr(alerting, "check_heartbeat_missing", _no_stale)
    monkeypatch.setattr(alerting, "check_job_backlog", _no_backlog)
    monkeypatch.setattr(alerting, "check_push_consecutive_failures", _no_failures)


async def test_run_alert_checks_fires_silence_alert_once_per_day(
    monkeypatch: pytest.MonkeyPatch,
    delivered: list[tuple[str, str]],
) -> None:
    _stub_other_probes(monkeypatch)
    monkeypatch.setenv("ALERT_DISCOVERY_SILENCE_ROUNDS", "3")
    factory = _Factory([("s-quiet", "安静公众号", 9)])

    fired = await alerting.run_alert_checks(factory)  # type: ignore[arg-type]
    assert any("采集静默" in title for title in fired), f"未触发静默告警：{fired}"
    assert len(delivered) == 1

    fired_again = await alerting.run_alert_checks(factory)  # type: ignore[arg-type]
    assert not any("采集静默" in title for title in fired_again), "同日重复必须被日幂等键挡住"
    assert len(delivered) == 1


async def test_alerting_disabled_delivers_nothing(
    monkeypatch: pytest.MonkeyPatch,
    delivered: list[tuple[str, str]],
) -> None:
    monkeypatch.delenv("ALERTING_ENABLED", raising=False)
    assert await alerting.run_alert_checks(_Factory([("s-quiet", "安静公众号", 99)])) == []  # type: ignore[arg-type]
    assert delivered == [], "总开关关掉时绝不能投递任何告警"


# ── P-9 / P-30：两处静默的可观测出口 ──────────────────────────────────────────


async def test_hydrate_counts_every_emptied_snapshot_field() -> None:
    from app.services.push_events import _hydrate_payload

    class _MissSession:
        async def get(self, _model: Any, _pk: Any) -> None:
            return None

    before = {
        f: _counter("bothot_event_payload_empty_total", name="new_article", field=f)
        for f in ("doc_title", "space_name")
    }

    with capture_logs() as logs:
        hydrated = await _hydrate_payload(_MissSession(), "new_article", {"asset_id": "a1", "space_id": "s1"})  # type: ignore[arg-type]

    assert hydrated["doc_title"] == "" and hydrated["space_name"] == "", "语义不许变：仍置空、仍发事件"
    for field, prev in before.items():
        got = _counter("bothot_event_payload_empty_total", name="new_article", field=field)
        assert got == prev + 1.0, f"字段 {field} 被静默置空未计数"
    assert [e for e in logs if e["event"] == "push_event.payload_empty"], "置空必须留结构化痕迹"


async def test_persist_failure_is_counted_without_breaking_the_receipt() -> None:
    from app.providers.push.base import PushMessage
    from app.services import push_scheduler

    class _BrokenSavepoint:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_exc: object) -> bool:
            return False

    class _BrokenSession:
        def begin_nested(self) -> _BrokenSavepoint:
            return _BrokenSavepoint()

        def add(self, _obj: Any) -> None:
            raise RuntimeError("通知落库必炸")

    before = _counter("web_notification_persist_failed_total", reason="RuntimeError")
    msg = PushMessage(external_user_id="sub-1", title="T", message="M")
    await push_scheduler.persist_web_notification(_BrokenSession(), msg)  # type: ignore[arg-type]
    assert _counter("web_notification_persist_failed_total", reason="RuntimeError") == before + 1.0


# ── 契约面：报告形状不因本卡漂移 ──────────────────────────────────────────────


def test_report_carries_the_two_alert_bearing_counters_of_the_frozen_view() -> None:
    """冻结稿的告警语义挂在两个计数上（`id_fallback` / `all_skipped_pages`，collection.py:173-179）。

    刻意不比对整个字段集：稿是 **HTTP 视图**（`rows`/`new`/`channel`），本地报告是内部记账
    （`discovered`/`known_local`/`calls_made`…），两者本就不同名，等值断言是在造一条假门。
    """
    local = {f.name for f in dataclasses.fields(ManifestSyncReport)}
    frozen = set(ContractReport.model_fields)
    assert {"id_fallback", "all_skipped_pages"} <= local, f"本地报告缺告警计数：{local}"
    assert {"id_fallback", "all_skipped_pages"} <= frozen, f"冻结稿视图缺告警计数：{frozen}"
