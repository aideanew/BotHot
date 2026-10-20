"""STEP-26 S26.2.4：三条 web 投递路径的失败路径顺序护栏（连库）。

D-V17-03 把顺序统一为「先 `db.add(log)` 与计数，后 `persist_web_notification`，
最后 `commit`」。本文件不判顺序实现本身（那是 S26.2.2 的 EVD 面），而是判这条顺序
要保护的最终事实：**通知落库失败时，投递回执仍在**。

每条路径各一条用例，monkeypatch 让通知行在 flush 时违反列长度约束（PostgreSQL
`VARCHAR(256)`），`persist_web_notification` 的 savepoint 吞掉异常后：

- `push_logs` 有该次投递行；
- `total_push_count` / `success_push_count` 已 +1；
- `notifications` 无该条消息；
- 调度器/接口调用本身不抛错。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from app.api.v1 import bots as bots_module
from app.models.bothot_entities import BotChannel, Notification, PushLog, PushTask
from app.models.entities import User
from app.providers.push.base import PushMessage, PushResult
from app.services import push_scheduler as scheduler_module
from app.services.push_scheduler import PushTaskScheduler


class _StubProvider:
    def __init__(self) -> None:
        self.sent: list[PushMessage] = []

    async def push(self, message: PushMessage) -> PushResult:
        self.sent.append(message)
        return PushResult("web", True, "", "fake")


def _break_notification_insert(monkeypatch: Any) -> None:
    """让 persist 内的 Notification 行在 flush 时超长失败，而不是构造时就抛。

    构造即抛只能证明 `except` 有 catch；本卡要证明的是 savepoint 失败后同事务的
    投递回执（PushLog/计数）仍在，所以必须让错误发生在事务内。
    """

    def broken(**kwargs: Any) -> Notification:
        kwargs["title"] = "x" * 300
        return Notification(**kwargs)

    monkeypatch.setattr(scheduler_module, "Notification", broken)


async def _seed_channel(db_session: Any, *, channel_type: str = "web") -> tuple[str, str, str]:
    uid = str(uuid.uuid4())
    user = User(
        id=uid,
        sub=f"s26-order-sub-{uid[:8]}",
        email=f"s26-order-{uid[:8]}@s26.test",
        nickname="s26-order",
    )
    db_session.add(user)
    await db_session.flush()
    cid = str(uuid.uuid4())
    db_session.add(
        BotChannel(
            id=cid,
            name=f"s26-order-{cid[:6]}",
            channel_type=channel_type,
            webhook_url="",
            status="active",
            user_id=uid,
        )
    )
    await db_session.flush()
    return cid, uid, user.sub


async def _seed_task(db_session: Any, channel_id: str, created_by: str) -> tuple[str, str]:
    tid = str(uuid.uuid4())
    content = f"s26-order-body-{tid[:8]}"
    db_session.add(
        PushTask(
            id=tid,
            name=f"s26-order-task-{tid[:6]}",
            bot_channel_id=channel_id,
            trigger_type="manual",
            content_template=content,
            status="active",
            created_by=created_by,
        )
    )
    await db_session.flush()
    return tid, content


async def _assert_receipt_survived(db_session: Any, *, channel_id: str, task_id: str | None, body: str) -> None:
    logs = (
        (
            await db_session.execute(
                select(PushLog).where(
                    PushLog.bot_channel_id == channel_id,
                    PushLog.push_task_id == task_id if task_id is not None else PushLog.push_task_id.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(logs) == 1, f"投递回执行数应为 1，实得 {len(logs)}"
    assert logs[0].status == "success"

    ch = (await db_session.execute(select(BotChannel).where(BotChannel.id == channel_id))).scalar_one()
    assert ch.total_push_count == 1, f"total_push_count 应为 1，实得 {ch.total_push_count}"
    assert ch.success_push_count == 1, f"success_push_count 应为 1，实得 {ch.success_push_count}"

    rows = int(
        (
            await db_session.scalar(
                select(func.count()).select_from(Notification).where(Notification.message == body)
            )
        )
        or 0
    )
    assert rows == 0, "通知落库已失败，却留下了通知行"


class _SessionCtx:
    def __init__(self, session: Any) -> None:
        self._session = session

    async def __aenter__(self) -> Any:
        return self._session

    async def __aexit__(self, *exc: Any) -> bool:
        return False


async def test_scheduler_keeps_receipt_when_notification_insert_fails(
    db_session: Any, monkeypatch: Any
) -> None:
    cid, uid, _ = await _seed_channel(db_session)
    tid, body = await _seed_task(db_session, cid, uid)
    task = (await db_session.execute(select(PushTask).where(PushTask.id == tid))).scalar_one()

    _break_notification_insert(monkeypatch)
    provider = _StubProvider()
    monkeypatch.setattr(scheduler_module, "make_push_provider", lambda _channel: provider)
    monkeypatch.setattr(scheduler_module, "decrypt_channel_secret", lambda *_args: "")
    monkeypatch.setattr(scheduler_module, "decrypt_extra_config", lambda *_args: "")

    scheduler = PushTaskScheduler(lambda: _SessionCtx(db_session))
    await scheduler._execute_task(task, datetime.now(UTC))

    assert provider.sent, "provider 未被调用"
    await _assert_receipt_survived(db_session, channel_id=cid, task_id=tid, body=body)


async def test_run_now_keeps_receipt_when_notification_insert_fails(
    db_session: Any, monkeypatch: Any
) -> None:
    cid, uid, _ = await _seed_channel(db_session)
    tid, body = await _seed_task(db_session, cid, uid)

    _break_notification_insert(monkeypatch)
    provider = _StubProvider()
    monkeypatch.setattr(bots_module, "make_push_provider", lambda _channel: provider)
    monkeypatch.setattr(bots_module, "decrypt_channel_secret", lambda *_args: "")
    monkeypatch.setattr(bots_module, "decrypt_extra_config", lambda *_args: "")

    await bots_module.run_push_task_now(tid, db=db_session)

    assert provider.sent, "provider 未被调用"
    await _assert_receipt_survived(db_session, channel_id=cid, task_id=tid, body=body)


async def test_test_push_keeps_receipt_when_notification_insert_fails(
    db_session: Any, monkeypatch: Any
) -> None:
    cid, _uid, _usub = await _seed_channel(db_session)
    body = f"s26-order-test-{uuid.uuid4().hex[:8]}"

    _break_notification_insert(monkeypatch)
    provider = _StubProvider()
    monkeypatch.setattr(bots_module, "make_push_provider", lambda _channel: provider)
    monkeypatch.setattr(bots_module, "decrypt_channel_secret", lambda *_args: "")
    monkeypatch.setattr(bots_module, "decrypt_extra_config", lambda *_args: "")

    await bots_module.test_push(cid, message=body, title="S26 order", db=db_session)

    assert provider.sent, "provider 未被调用"
    assert provider.sent[-1].notification_id, "web 测试推送没有预铸 id"
    await _assert_receipt_survived(db_session, channel_id=cid, task_id=None, body=body)
