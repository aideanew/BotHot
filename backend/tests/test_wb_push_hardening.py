"""WB（审查补完）推送域加固测试：事件 payload 自足 + 业务时区 + 投递重试 + 生产守卫。

连库口径（与 test_w3 同法）：调度器执行路径用 db_session.bind 共享连接（savepoint
隔离足够单线程用例）；PG 不可达 → conftest 夹具 skip，不染色门禁。
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from app.models.bothot_entities import (
    BotChannel,
    DailyReport,
    HotTopic,
    PushEvent,
    PushLog,
    PushTask,
)
from app.models.entities import ContentAsset, Source, User
from app.providers.push.base import PushResult
from app.services.push_events import emit_event
from app.services.push_scheduler import (
    MAX_PUSH_RETRIES,
    PushTaskScheduler,
)
from app.services.push_template import render, validate_template

_TEST_USER_SUB = "wb-hardening-test-user"
_BUSINESS_TZ = ZoneInfo("Asia/Shanghai")


# ── 2.1.2 业务时区 + 变量注册表 ─────────────────────────────────────


class TestRenderBusinessTz:
    def test_date_time_use_business_tz(self) -> None:
        now_sh = datetime.now(_BUSINESS_TZ)
        out = render("{date} {time}", {})
        assert now_sh.strftime("%Y-%m-%d") in out
        assert now_sh.strftime("%H:%M") in out

    def test_report_title_is_known_variable(self) -> None:
        assert validate_template("日报 {report_title}") is None
        out = render("{report_title}", {"report_title": "BotHot 热点日报"})
        assert out == "BotHot 热点日报"

    def test_unknown_variable_still_stripped(self) -> None:
        assert validate_template("{nope}") is not None
        assert render("{nope}", {}) == ""


# ── 2.1.1 payload 自足（PG 集成）────────────────────────────────────


@pytest.fixture
async def wb_user(db_session: Any):
    user = (await db_session.execute(select(User).where(User.sub == _TEST_USER_SUB))).scalar_one_or_none()
    if user is None:
        user = User(sub=_TEST_USER_SUB, email=f"{_TEST_USER_SUB}@test.local", nickname="WB 测试")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
    return user


@pytest.fixture
async def wb_channel(db_session: Any, wb_user):
    ch = BotChannel(
        name=f"wb-channel-{os.urandom(3).hex()}",
        channel_type="webhook",
        webhook_url="http://localhost:9999/hook",
        secret_enc="",
        extra_config="{}",
        status="active",
    )
    db_session.add(ch)
    await db_session.commit()
    await db_session.refresh(ch)
    return ch


async def test_emit_event_hydrates_doc_title(db_session: Any) -> None:
    """new_article 事件落库前查库补 doc_title 快照（WB 2.1.1）。"""
    source = Source(
        type="wechat_oa",
        external_id=f"wb-{os.urandom(3).hex()}",
        name="WB 源",
    )
    db_session.add(source)
    await db_session.flush()
    asset = ContentAsset(
        source_id=source.id,
        external_id=f"wb-asset-{os.urandom(3).hex()}",
        url="https://example.com/wb",
        title="WB 测试文章标题",
        content_hash="h-wb",
        content_markdown="# WB",
    )
    db_session.add(asset)
    await db_session.flush()

    await emit_event(db_session, "new_article", {"asset_id": asset.id})
    await db_session.flush()

    row = (
        (await db_session.execute(select(PushEvent).where(PushEvent.event_type == "new_article").limit(1)))
        .scalars()
        .first()
    )
    import json

    payload = json.loads(row.payload)
    assert payload["doc_title"] == "WB 测试文章标题"


async def test_emit_event_hydrates_topic_fields(db_session: Any) -> None:
    topic = HotTopic(
        title="WB 测试热点",
        article_count=3,
        status="rising",
        topic_date="2026-09-30",
        category="",
    )
    db_session.add(topic)
    await db_session.flush()
    await emit_event(db_session, "hot_topic_update", {"topic_id": topic.id})
    await db_session.flush()

    import json

    row = (
        (await db_session.execute(select(PushEvent).where(PushEvent.event_type == "hot_topic_update").limit(1)))
        .scalars()
        .first()
    )
    payload = json.loads(row.payload)
    assert payload["hot_topic"] == "WB 测试热点"
    assert payload["topic_count"] == "3"


async def test_emit_event_hydrates_daily_report_title(db_session: Any) -> None:
    report = DailyReport(
        report_date="2099-12-31",
        title="BotHot 热点日报 · 测试",
    )
    db_session.add(report)
    await db_session.flush()
    await emit_event(db_session, "daily_report", {"report_date": report.report_date})
    await db_session.flush()

    import json

    row = (
        (await db_session.execute(select(PushEvent).where(PushEvent.event_type == "daily_report").limit(1)))
        .scalars()
        .first()
    )
    payload = json.loads(row.payload)
    assert payload["report_title"] == "BotHot 热点日报 · 测试"


# ── 2.2.2/2.2.3 投递重试（PG 集成，mock provider）──────────────────


class _FakeProvider:
    """受控 Provider：按脚本逐次返回结果。"""

    name = "webhook"
    description = "test fake"

    def __init__(self, results: list[PushResult]) -> None:
        self._results = list(results)
        self.calls = 0

    async def push(self, message: Any) -> PushResult:
        self.calls += 1
        idx = min(self.calls, len(self._results)) - 1
        return self._results[idx]


@pytest.fixture
async def retry_task(db_session: Any, wb_user, wb_channel):
    task = PushTask(
        name="wb-retry-task",
        bot_channel_id=wb_channel.id,
        trigger_type="event",
        trigger_event="new_article",
        content_template="推送 {doc_title}",
        status="active",
        created_by=wb_user.id,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    return task


def _install_provider(monkeypatch: pytest.MonkeyPatch, provider: _FakeProvider) -> None:
    import app.services.push_scheduler as ps

    monkeypatch.setattr(ps, "make_push_provider", lambda channel_type: provider)


async def _task_row(db_session: Any, task_id: str) -> PushTask | None:
    # populate_existing：绕开 db_session 身份映射的陈旧对象（跨 session 更新后
    # 普通 SELECT 不会覆盖已缓存属性）
    return (
        await db_session.execute(
            select(PushTask).where(PushTask.id == task_id).execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


@pytest.mark.parametrize(
    ("results", "expected_counts"),
    [
        # 首次失败(可重试) → 次成功：retry_count 先 1 后清零
        (
            [PushResult("webhook", False, "boom", retryable=True), PushResult("webhook", True, "")],
            [1, 0],
        ),
    ],
)
async def test_retry_then_success(
    db_session: Any,
    retry_task: PushTask,
    monkeypatch: pytest.MonkeyPatch,
    results: list[PushResult],
    expected_counts: list[int],
) -> None:
    provider = _FakeProvider(results)
    _install_provider(monkeypatch, provider)
    scheduler = PushTaskScheduler(async_sessionmaker(bind=db_session.bind, expire_on_commit=False))
    now = datetime.now(UTC)

    await scheduler._execute_task(retry_task, now)
    row = await _task_row(db_session, retry_task.id)
    assert row is not None
    assert row.retry_count == expected_counts[0]
    assert row.next_retry_at is not None and row.next_retry_at > now

    await scheduler._execute_task(retry_task, datetime.now(UTC))
    row = await _task_row(db_session, retry_task.id)
    assert row is not None
    assert row.retry_count == expected_counts[1]
    assert row.next_retry_at is None
    assert provider.calls == 2

    logs = (await db_session.execute(select(PushLog).where(PushLog.push_task_id == retry_task.id))).scalars().all()
    assert [log.status for log in logs] == ["failed", "success"]


async def test_retry_exhausted_becomes_dead(
    db_session: Any, retry_task: PushTask, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeProvider([PushResult("webhook", False, "still down", retryable=True)])
    _install_provider(monkeypatch, provider)
    scheduler = PushTaskScheduler(async_sessionmaker(bind=db_session.bind, expire_on_commit=False))

    # 首投 + MAX_PUSH_RETRIES 次重投全部失败 → 第 MAX+1 次转 dead
    for _ in range(MAX_PUSH_RETRIES + 1):
        await scheduler._execute_task(retry_task, datetime.now(UTC))

    row = await _task_row(db_session, retry_task.id)
    assert row is not None
    assert row.status == "failed"
    assert row.next_retry_at is None

    logs = (await db_session.execute(select(PushLog).where(PushLog.push_task_id == retry_task.id))).scalars().all()
    statuses = [log.status for log in logs]
    assert statuses[-1] == "dead"
    assert statuses.count("failed") == MAX_PUSH_RETRIES
    assert provider.calls == MAX_PUSH_RETRIES + 1


async def test_non_retryable_failure_never_reschedules(
    db_session: Any, retry_task: PushTask, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = _FakeProvider([PushResult("webhook", False, "signature invalid", retryable=False)])
    _install_provider(monkeypatch, provider)
    scheduler = PushTaskScheduler(async_sessionmaker(bind=db_session.bind, expire_on_commit=False))
    await scheduler._execute_task(retry_task, datetime.now(UTC))

    row = await _task_row(db_session, retry_task.id)
    assert row is not None
    assert row.retry_count == 0
    assert row.next_retry_at is None
    assert row.status == "active"


async def test_claim_picks_retry_due_and_keeps_cron_schedule(db_session: Any, wb_user, wb_channel) -> None:
    """重试到期但 cron 未到期的任务被领取，且 next_run_at 不被推进（节奏正交）。"""
    task = PushTask(
        name="wb-retry-only",
        bot_channel_id=wb_channel.id,
        trigger_type="cron",
        cron_expr="0 9 * * *",
        status="active",
        next_run_at=datetime.now(UTC) + timedelta(hours=5),  # cron 未到期
        next_retry_at=datetime.now(UTC) - timedelta(seconds=1),  # 重试已到期
        retry_count=1,
        created_by=wb_user.id,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    original_next_run = task.next_run_at

    scheduler = PushTaskScheduler(async_sessionmaker(bind=db_session.bind, expire_on_commit=False))
    claimed = await scheduler._claim_due_cron_tasks(datetime.now(UTC))
    assert [t.id for t in claimed] == [task.id]

    await db_session.refresh(task)
    # 重试领取不得改写 cron 节奏（next_run_at 保持原值）
    assert task.next_run_at == original_next_run
    assert task.last_run_at is not None


# ── 2.3 生产守卫 ────────────────────────────────────────────────────


class TestProductionGuard:
    def _settings(self, **overrides: Any) -> Settings:
        base: dict[str, Any] = {
            "app_env": "production",
            "oidc_client_secret": "real-secret",
            "session_cookie_secure": True,
            "session_store_backend": "redis",
            "oidc_issuer_expected": "https://issuer.example.com",
            "oidc_audience_expected": "bothot",
            "push_secret_master_key": "",
            "engine_key_master_key": "",
        }
        base.update(overrides)
        return Settings(**base)

    def test_missing_push_master_key_is_violation(self) -> None:
        violations = self._settings().production_guard_violations()
        assert any("PUSH_SECRET_MASTER_KEY" in v for v in violations)

    def test_missing_engine_master_key_is_violation(self) -> None:
        violations = self._settings().production_guard_violations()
        assert any("ENGINE_KEY_MASTER_KEY" in v for v in violations)

    def test_configured_keys_pass_guard(self) -> None:
        import base64

        mk = base64.b64encode(os.urandom(32)).decode()
        violations = self._settings(push_secret_master_key=mk, engine_key_master_key=mk).production_guard_violations()
        assert not any("MASTER_KEY" in v for v in violations)
