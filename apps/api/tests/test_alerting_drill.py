"""S2.2 告警演练：三类硬化信号（心跳缺失/Job 积压/推送连败）端到端触发留证。

隔离 PG + savepoint 隔离（同会话假 factory：run_alert_checks 内部 `async with
session_factory()` 打开的探测会话与造数会话为同一 db_session——未提交数据对
探测可见，事务结束自动回滚，零残留）。`_deliver` 截获——投递路径走通，不真发
webhook。对应 TASK-PLAN-v0.9 S2.2b；compose 注入见 backend_env 锚。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import alerting
from app.models.bothot_entities import BotChannel, PushLog
from app.models.entities import Job, ProcessHeartbeat, User
from app.services.process_heartbeat import EXPECTED_PROCESSES


class _SameSessionFactory:
    """把 db_session 包装成 async_sessionmaker 形状的假工厂（同会话探测）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def __call__(self) -> SimpleNamespace:
        return self

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *exc) -> bool:
        return False


@pytest.fixture
async def drill_user(db_session: AsyncSession) -> User:
    sub = "alert-drill-user"
    user = (
        await db_session.execute(select(User).where(User.sub == sub))
    ).scalar_one_or_none()
    if user is None:
        user = User(sub=sub, email=f"{sub}@test.local", nickname="告警演练")
        db_session.add(user)
        await db_session.flush()
    return user


@pytest.fixture
def alerting_on(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """开启告警 + 截获 _deliver 载荷（演练不真发 webhook）。"""
    monkeypatch.setenv("ALERTING_ENABLED", "1")
    monkeypatch.setenv("ALERT_CHANNEL", "web")
    sent: list[dict[str, str]] = []

    async def _capture(title: str, message: str) -> bool:
        sent.append({"title": title, "message": message})
        return True

    monkeypatch.setattr(alerting, "_deliver", _capture)
    return sent


async def test_drill_all_three_alerts_fire(
    db_session: AsyncSession, drill_user: User, alerting_on: list[dict[str, str]]
):
    now = datetime.now(UTC)
    # ① 心跳缺失：scheduler/worker 心跳过期（>300s 阈值 → stale）
    for key in EXPECTED_PROCESSES:
        row = (
            await db_session.execute(
                select(ProcessHeartbeat).where(ProcessHeartbeat.process_key == key)
            )
        ).scalar_one_or_none()
        if row is None:
            row = ProcessHeartbeat(process_key=key)
            db_session.add(row)
        row.last_heartbeat_at = now - timedelta(hours=1)

    # ② Job 积压：101 条 QUEUED（默认阈值 100）
    stamp = f"{now.timestamp():.0f}"
    for i in range(101):
        db_session.add(
            Job(
                type="alert_drill",
                user_id=drill_user.id,
                status="QUEUED",
                idempotency_key=f"alert-drill-{stamp}-{i}",
            )
        )

    # ③ 推送连败：最近 5 条全部 failed（默认窗口 5）
    ch = BotChannel(
        name=f"alert-drill-{stamp}",
        channel_type="webhook",
        webhook_url="http://localhost:9999/drill",
        secret_enc="",
        extra_config="{}",
        status="active",
        user_id=drill_user.id,
    )
    db_session.add(ch)
    await db_session.flush()
    for _ in range(5):
        db_session.add(
            PushLog(
                bot_channel_id=ch.id,
                status="failed",
                content_preview="",
                error_message="drill",
                response_summary="",
            )
        )
    await db_session.flush()

    fired = await alerting.run_alert_checks(_SameSessionFactory(db_session))  # type: ignore[arg-type]

    assert set(fired) == {"常驻进程心跳缺失", "Job 积压", "推送连续失败"}
    titles = [s["title"] for s in alerting_on]
    assert titles == [
        "BotHot 告警：进程心跳缺失",
        "BotHot 告警：Job 积压",
        "BotHot 告警：推送连续失败",
    ]
    # 载荷语义抽查：心跳点名进程、积压带计数与阈值、连败带窗口
    assert "scheduler" in alerting_on[0]["message"] and "worker" in alerting_on[0]["message"]
    assert "101" in alerting_on[1]["message"] and "100" in alerting_on[1]["message"]
    assert "5 条" in alerting_on[2]["message"]


async def test_alerting_disabled_short_circuits(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    """默认关闭：ALERTING_ENABLED 未置真 → 零探测零投递（开发/测试零副作用）。"""
    monkeypatch.delenv("ALERTING_ENABLED", raising=False)
    sent: list[str] = []

    async def _capture(title: str, message: str) -> bool:
        sent.append(title)
        return True

    monkeypatch.setattr(alerting, "_deliver", _capture)
    fired = await alerting.run_alert_checks(_SameSessionFactory(db_session))  # type: ignore[arg-type]
    assert fired == [] and sent == []
