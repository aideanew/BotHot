"""W6 观测面单元验收（A.1 / A.2 / A.3 / A.5）。

覆盖四块，均为纯函数/内存级测试，不连真实 DB/Redis：
- **logging（A.1）**：双模渲染（json/console）、单 handler 防重复行、request_id 经
  contextvars 注入、幂等重装。
- **metrics（A.2）**：normalize_path 压基数、MetricsMiddleware 记耗时/并发与豁免路径、
  record_push_outcome 计数、/metrics 暴露 ≥8 族。
- **schema_guard（A.3）**：head 探测可用、坏引擎降级为 None。
- **alerting（A.5）**：env 解析、未启用即空、投递 seam 走 make_push_provider、
  启用后三类命中各自投递。
"""

from __future__ import annotations

import json
import logging

import pytest
import structlog
from fastapi.testclient import TestClient

from app.core import alerting, schema_guard
from app.core import logging as blog
from app.core import metrics as m
from app.main import app


# --------------------------------------------------------------------------- #
# A.1  logging
# --------------------------------------------------------------------------- #
@pytest.fixture
def clean_logging(monkeypatch: pytest.MonkeyPatch):
    """隔离全局日志装配：进出各存/恢复 root handler，避免污染其它用例。"""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    structlog.reset_defaults()
    blog.reset_logging()
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    structlog.reset_defaults()
    blog.reset_logging()


def _ours(root: logging.Logger) -> list[logging.Handler]:
    return [h for h in root.handlers if getattr(h, "_bothot_structlog_handler", False)]


def test_configure_json_mode_emits_single_parseable_line(clean_logging, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOG_FORMAT", "json")
    blog.configure_logging(force=True)
    structlog.get_logger("w6.json").info("hello_event", user_id=42)
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "hello_event" in ln]
    assert len(lines) == 1  # 无重复行
    data = json.loads(lines[0])
    assert data["event"] == "hello_event"
    assert data["user_id"] == 42
    assert data["level"] == "info"
    assert data["logger"] == "w6.json"
    assert "timestamp" in data


def test_configure_console_mode_is_not_json(clean_logging, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOG_FORMAT", "console")
    blog.configure_logging(force=True)
    structlog.get_logger("w6.console").warning("console_marker")
    out = capsys.readouterr().out
    assert "console_marker" in out
    hit = [ln for ln in out.splitlines() if "console_marker" in ln]
    assert len(hit) == 1
    with pytest.raises(json.JSONDecodeError):
        json.loads(hit[0])


def test_single_handler_and_foreign_lib_no_duplicate_lines(clean_logging, monkeypatch, capsys) -> None:
    """第三方经 stdlib 的日志也在同一 handler 渲染一次——既无双写也不漏。"""
    monkeypatch.setenv("LOG_FORMAT", "json")
    blog.configure_logging(force=True)
    root = logging.getLogger()
    assert len(_ours(root)) == 1
    blog.configure_logging(force=True)  # 幂等重装
    assert len(_ours(root)) == 1
    logging.getLogger("some.third.party").error("foreign_marker")
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "foreign_marker" in ln]
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "foreign_marker"


def test_request_id_injected_via_contextvars(clean_logging, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOG_FORMAT", "json")
    blog.configure_logging(force=True)
    structlog.contextvars.bind_contextvars(request_id="req-abc-123")
    try:
        structlog.get_logger("w6.ctx").info("with_request")
    finally:
        structlog.contextvars.unbind_contextvars("request_id")
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "with_request" in ln]
    assert len(lines) == 1
    assert json.loads(lines[0])["request_id"] == "req-abc-123"
    # 解绑后不再带入
    structlog.get_logger("w6.ctx").info("after_unbind")
    tail = [ln for ln in capsys.readouterr().out.splitlines() if "after_unbind" in ln]
    assert "request_id" not in json.loads(tail[0])


# --------------------------------------------------------------------------- #
# A.2  metrics
# --------------------------------------------------------------------------- #
def test_normalize_path_folds_id_segments() -> None:
    assert m.normalize_path("") == "/"
    assert m.normalize_path("/api/v1/system/health") == "/api/v1/system/health"
    assert m.normalize_path("/api/v1/spaces/123") == "/api/v1/spaces/{id}"
    assert m.normalize_path("/api/v1/spaces/550e8400-e29b-41d4-a716-446655440000") == "/api/v1/spaces/{id}"
    assert m.normalize_path("/api/v1/docs/deadbeefdeadbeef") == "/api/v1/docs/{id}"


def test_record_push_outcome_counts_each_variant() -> None:
    def _val(channel: str, outcome: str) -> float:
        return m.PUSH_DELIVERIES_TOTAL.labels(channel=channel, outcome=outcome)._value.get()

    before = _val("w6ch", "success")
    m.record_push_outcome("w6ch", delivered=True)
    assert _val("w6ch", "success") == before + 1
    b_failed = _val("w6ch", "failed")
    m.record_push_outcome("w6ch", delivered=False, dead=False)
    assert _val("w6ch", "failed") == b_failed + 1
    b_dead = _val("w6ch", "dead")
    m.record_push_outcome("w6ch", delivered=False, dead=True)
    assert _val("w6ch", "dead") == b_dead + 1


def _hist_count(hist, suffix="_count", **labels) -> float:
    """从 Histogram 采集结果里按标签取样本值（避开私有属性）。"""
    for metric in hist.collect():
        for s in metric.samples:
            if s.name.endswith(suffix) and all(s.labels.get(k) == v for k, v in labels.items()):
                return float(s.value)
    return 0.0


async def test_metrics_middleware_records_and_exempts() -> None:
    async def dummy(scope, receive, send):  # noqa: ANN001
        await send({"type": "http.response.start", "status": 201, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():
        return {"type": "http.request"}

    mw = m.MetricsMiddleware(dummy)

    sent: list[dict] = []

    async def send(msg):
        sent.append(msg)

    count_before = _hist_count(m.HTTP_REQUEST_DURATION, method="GET", path="/api/v1/ping", status="201")
    await mw(
        {"type": "http", "path": "/api/v1/ping", "method": "GET", "headers": []},
        receive,
        send,
    )
    assert _hist_count(m.HTTP_REQUEST_DURATION, method="GET", path="/api/v1/ping", status="201") == count_before + 1
    assert [msg["type"] for msg in sent] == ["http.response.start", "http.response.body"]
    # in_flight 结束后归零
    assert m.HTTP_REQUESTS_IN_FLIGHT.labels(method="GET")._value.get() == 0.0

    # 豁免路径：/metrics 不记录
    await mw({"type": "http", "path": "/metrics", "method": "GET", "headers": []}, receive, send)
    assert _hist_count(m.HTTP_REQUEST_DURATION, method="GET", path="/metrics", status="201") == 0.0


def test_metrics_endpoint_exposes_at_least_eight_families() -> None:
    resp = TestClient(app).get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    help_families = {ln.split()[2] for ln in body.splitlines() if ln.startswith("# HELP ")}
    assert len(help_families) >= 8  # 验收 #2
    for name in (
        "http_request_duration_seconds",
        "http_requests_in_flight",
        "db_pool_in_use",
        "bothot_jobs_by_status",
        "push_deliveries_total",
        "hot_cluster_duration_seconds",
    ):
        assert name in help_families, f"missing metric family: {name}"


# --------------------------------------------------------------------------- #
# A.3  schema_guard
# --------------------------------------------------------------------------- #
def test_get_alembic_head_returns_str_or_none() -> None:
    head = schema_guard.get_alembic_head()
    assert head is None or isinstance(head, str)


async def test_read_current_version_degrades_to_none_on_broken_engine() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(
        "postgresql+psycopg://nobody:nobody@127.0.0.1:1/nodb",
        connect_args={"connect_timeout": 1},
    )
    try:
        assert await schema_guard.read_current_version_async(engine) is None
    finally:
        await engine.dispose()


# --------------------------------------------------------------------------- #
# A.5  alerting
# --------------------------------------------------------------------------- #
def test_env_parsers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALERTING_ENABLED", "true")
    assert alerting._flag("ALERTING_ENABLED") is True
    monkeypatch.setenv("ALERTING_ENABLED", "0")
    assert alerting._flag("ALERTING_ENABLED") is False
    assert alerting._flag("W6_ABSENT_FLAG", default=True) is True
    monkeypatch.setenv("W6_INT", "abc")
    assert alerting._int_env("W6_INT", 7) == 7
    monkeypatch.setenv("W6_INT", "12")
    assert alerting._int_env("W6_INT", 7) == 12
    assert alerting._str_env("W6_STR_ABSENT", "fallback") == "fallback"


async def test_run_alert_checks_disabled_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALERTING_ENABLED", raising=False)
    # factory 传 None：未启用时在触达前即返回
    assert await alerting.run_alert_checks(None) == []  # type: ignore[arg-type]


async def test_deliver_routes_through_make_push_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.providers.push.base import PushResult

    captured: dict = {}

    class FakeProvider:
        async def push(self, message):  # noqa: ANN001
            captured["message"] = message
            return PushResult(channel="web", delivered=True, reason="ok")

    monkeypatch.setattr(alerting, "make_push_provider", lambda channel: FakeProvider())
    monkeypatch.setenv("ALERT_CHANNEL", "web")
    ok = await alerting._deliver("标题", "正文")
    assert ok is True
    assert captured["message"].title == "标题"
    assert captured["message"].message == "正文"


async def test_deliver_swallows_provider_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_channel):
        raise RuntimeError("provider down")

    monkeypatch.setattr(alerting, "make_push_provider", _boom)
    assert await alerting._deliver("t", "m") is False


async def test_run_alert_checks_enabled_fires_all_three(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALERTING_ENABLED", "1")
    monkeypatch.setenv("ALERT_JOB_BACKLOG", "1")

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

    class _Factory:
        def __call__(self):
            return _Session()

    delivered: list[str] = []

    async def fake_hb(_session):
        return ["scheduler:stale"]

    async def fake_backlog(_session):
        return 5

    async def fake_pushfail(_session, _window):
        return True

    async def fake_deliver(title, _message):
        delivered.append(title)
        return True

    monkeypatch.setattr(alerting, "check_heartbeat_missing", fake_hb)
    monkeypatch.setattr(alerting, "check_job_backlog", fake_backlog)
    monkeypatch.setattr(alerting, "check_push_consecutive_failures", fake_pushfail)
    monkeypatch.setattr(alerting, "_deliver", fake_deliver)

    fired = await alerting.run_alert_checks(_Factory())
    assert "常驻进程心跳缺失" in fired
    assert "Job 积压" in fired
    assert "推送连续失败" in fired
    assert len(delivered) == 3


async def test_run_alert_checks_isolated_when_one_probe_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单类探测异常不得连坐其余两类。"""
    monkeypatch.setenv("ALERTING_ENABLED", "1")
    monkeypatch.setenv("ALERT_JOB_BACKLOG", "1")

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

    class _Factory:
        def __call__(self):
            return _Session()

    async def _raise(_session):
        raise RuntimeError("db down")

    async def fake_backlog(_session):
        return 9

    async def fake_pushfail(_session, _window):
        return False

    async def fake_deliver(_title, _message):
        return True

    monkeypatch.setattr(alerting, "check_heartbeat_missing", _raise)
    monkeypatch.setattr(alerting, "check_job_backlog", fake_backlog)
    monkeypatch.setattr(alerting, "check_push_consecutive_failures", fake_pushfail)
    monkeypatch.setattr(alerting, "_deliver", fake_deliver)

    fired = await alerting.run_alert_checks(_Factory())
    assert "常驻进程心跳缺失" not in fired  # 该类异常被隔离
    assert "Job 积压" in fired  # 其余照常
    assert "推送连续失败" not in fired  # 未命中
