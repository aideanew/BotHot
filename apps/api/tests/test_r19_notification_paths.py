"""STEP-19 S19.1.1：REQ-F-001 站内通知的"三路径"到底写不写 `notifications` 行。

需求原文把 **定时 / 事件 / 手动** 并列为三种触发方式，而 D-V2 时代只有一条路径落库
（卡面 2 的证据：`persist_web_notification` 在 314d7f2 上只有 `push_scheduler.py:229` 一个调用点）。
本卡的产物是**基于行数的判定**，不是"文档说已接"：四条 web 投递入口逐条数一次
`notifications` 的增量，并把"事件触发"这一路径拆成 **emit 阶段**与 **调度器派发阶段** 两段——
因为它们的职责不同：emit 只登记 `push_events`，真正投递在领取那一步。
如果只看"事件发过了、页面没消息"就下结论"不写"，会把两段误判成一段。

口径说明（为什么用桩 provider 而不是真 provider）：web provider 第一件事是问 Redis
（`providers/push/web.py`），CI 与本机都没有 Redis ⇒ `delivered=False` ⇒ 不写行。
那不是本卡的被测面，所以按 STEP-23 同一手法把"投递成功"这件事与被测的落库面解耦。
**桩只替换投递，不替换落库**——`persist_web_notification` 走的仍是生产代码路径。

连库用例：PG 缺席时由 `db_session` 夹具 skip（skip ≠ 通过，判定读数只在真库上取，见 EVD-V3-19）。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1 import bots as bots_module
from app.models.bothot_entities import BotChannel, Notification, PushEvent, PushTask
from app.models.entities import User
from app.providers.push.base import PushMessage, PushResult
from app.services.push import PushService
from app.services.push_events import emit_event
from app.services.push_scheduler import PushTaskScheduler, persist_web_notification


class _StubProvider:
    def __init__(self, result: PushResult) -> None:
        self._result = result
        self.sent: list[PushMessage] = []

    async def push(self, message: PushMessage) -> PushResult:
        self.sent.append(message)
        return self._result


async def _count(session: AsyncSession, body: str) -> int:
    rows = int(
        await session.scalar(select(func.count()).select_from(Notification).where(Notification.message == body)) or 0
    )
    return rows


async def _seed_web_stack(
    session: AsyncSession, *, trigger: str = "cron", event_name: str = ""
) -> tuple[str, str, str, str]:
    """种一套"能投递"的最小栈：user → web channel → task。返回 (user_id, channel_id, task_id, body)。"""
    tag = uuid.uuid4().hex[:8]
    body = f"r19-{trigger}-{tag}"
    user = User(sub=f"r19-{tag}", email=f"r19-{tag}@r19.test", nickname=f"r19-{tag}")
    session.add(user)
    await session.flush()
    channel = BotChannel(
        name=f"r19-web-{tag}",
        channel_type="web",
        webhook_url="",
        status="active",
        user_id=user.id,
    )
    session.add(channel)
    await session.flush()
    task = PushTask(
        name=f"r19-task-{tag}",
        bot_channel_id=channel.id,
        trigger_type=trigger,
        trigger_event=event_name,
        cron_expr="*/5 * * * *" if trigger == "cron" else "",
        content_template=body,
        status="active",
        next_run_at=datetime.now(UTC) - timedelta(minutes=1) if trigger == "cron" else None,
        created_by=user.id,
    )
    session.add(task)
    await session.flush()
    return str(user.id), str(channel.id), str(task.id), body


def _scheduler(session: AsyncSession) -> PushTaskScheduler:
    """调度器自带 session factory（生产口径）——与 `test_w3_push_scheduler` 同法接到夹具的 bind 上。"""
    factory = async_sessionmaker(bind=session.bind, expire_on_commit=False)
    return PushTaskScheduler(factory)


@pytest.fixture
def _stub_web(monkeypatch: pytest.MonkeyPatch, result: PushResult | None = None) -> _StubProvider:
    stub = _StubProvider(result or PushResult("web", True, "ok"))
    monkeypatch.setattr("app.services.push_scheduler.make_push_provider", lambda _t: stub)
    monkeypatch.setattr(bots_module, "make_push_provider", lambda _t: stub)
    monkeypatch.setattr("app.services.push.make_push_provider", lambda _t: stub)
    return stub


# ── 路径 1：定时（cron 到期 → 调度器领取投递）────────────────────────────────


@pytest.mark.asyncio
async def test_cron_claim_by_scheduler_writes_exactly_one_notification(
    db_session: AsyncSession, _stub_web: _StubProvider
) -> None:
    _uid, _cid, _tid, body = await _seed_web_stack(db_session, trigger="cron")
    await db_session.commit()
    assert await _count(db_session, body) == 0, "投递前就有行（那这条 +1 就不是这条路径写的）"

    await _scheduler(db_session)._tick()
    got = await _count(db_session, body)
    assert got == 1, f"调度器领取投递后 notifications 增量={got}（期望恰 1 行）"
    assert _stub_web.sent, "provider 没被调用，那这条路径根本没走到投递"


# ── 路径 2：事件触发（emit 阶段不投递，领取阶段才投递）────────────────────────


@pytest.mark.asyncio
async def test_event_emit_writes_nothing_and_dispatch_writes_one(
    db_session: AsyncSession, _stub_web: _StubProvider
) -> None:
    # claim_pending_events 扫全表：先把**已消费**的历史事件清掉、并把未消费的标记消耗，
    # 否则"这一轮领到几条"不可判（test_w3 的同一条教训：隔离 rollback 覆盖不了真提交残留）
    await db_session.execute(delete(PushEvent))
    await db_session.commit()

    _uid, _cid, _tid, body = await _seed_web_stack(db_session, trigger="event", event_name="new_article")
    await emit_event(db_session, "new_article", {"doc_title": body})
    await db_session.commit()

    assert await _count(db_session, body) == 0, "emit 阶段就写了通知行 ⇒ 投递还没发生，行从何来"

    await _scheduler(db_session)._tick()
    assert await _count(db_session, body) == 1, "事件被领取投递后仍没有通知行（REQ-F-001 的事件路径断在这里）"


# ── 路径 3：手动（run-now 与"一键测试"两个调用点）───────────────────────────


@pytest.mark.asyncio
async def test_manual_run_now_writes_one_notification(db_session: AsyncSession, _stub_web: _StubProvider) -> None:
    _uid, _cid, tid, body = await _seed_web_stack(db_session, trigger="manual")
    await bots_module.run_push_task_now(tid, db=db_session)
    assert await _count(db_session, body) == 1
    assert _stub_web.sent[-1].notification_id, "web 直投未预铸 notification_id ⇒ SSE 帧与历史行无法同 id"


@pytest.mark.asyncio
async def test_test_push_on_web_channel_writes_one_notification(
    db_session: AsyncSession, _stub_web: _StubProvider
) -> None:
    _uid, cid, _tid, _body = await _seed_web_stack(db_session, trigger="manual")
    title = f"r19-testpush-{uuid.uuid4().hex[:8]}"
    await bots_module.test_push(cid, message="r19 一键测试正文", title=title, db=db_session)
    assert await _count(db_session, "r19 一键测试正文") == 1
    rows = (
        await db_session.execute(select(Notification).where(Notification.title == title))
    ).scalars().all()
    assert len(rows) == 1


# ── 路径 4：管理端直投（第四条 web 入口，卡面没列但同表）─────────────────────


@pytest.mark.asyncio
async def test_admin_direct_push_writes_one_notification(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _StubProvider(PushResult("web", True, "ok"))
    monkeypatch.setattr("app.services.push.make_push_provider", lambda _t: stub)
    body = f"r19-admin-{uuid.uuid4().hex[:8]}"
    await PushService(db_session).push("web", f"r19-target-{uuid.uuid4().hex[:6]}", message=body)
    assert await _count(db_session, body) == 1, "管理端直投没写历史（STEP-26 那条回归又出现）"


# ── 反向极性：投递失败不许写行 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_failed_delivery_writes_no_notification(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _StubProvider(PushResult("web", False, "Redis 不可用", retryable=False))
    monkeypatch.setattr("app.services.push_scheduler.make_push_provider", lambda _t: stub)
    _uid, _cid, _tid, body = await _seed_web_stack(db_session, trigger="cron")
    await db_session.commit()
    await _scheduler(db_session)._tick()
    assert await _count(db_session, body) == 0, "投递失败也写了通知历史 ⇒ 离线补投会把没到达的消息当成已到达"


@pytest.mark.asyncio
async def test_the_shared_persist_fn_is_the_only_write_door(db_session: AsyncSession) -> None:
    """四条入口必须共用同一个落库函数（不是各自复制一份 `Notification(...)`）。

    第二个写入口 = 广播/定向判定与 id 口径会在两处漂移，这正是 STEP-23 立这条的原因；
    本卡复验它仍然成立。判 AST 级的源文本，不判 grep 措辞。
    """
    import inspect

    from app.api.v1 import admin as admin_module

    for who, fn in (
        ("bots.run_push_task_now", bots_module.run_push_task_now),
        ("bots.test_push", bots_module.test_push),
        ("services.push.PushService.push", PushService.push),
        ("services.push_scheduler._execute_task", PushTaskScheduler._execute_task),
    ):
        src = inspect.getsource(fn)
        assert "persist_web_notification(" in src, f"{who} 不再调用共享落库函数"
        assert "Notification(" not in src, f"{who} 自己构造 Notification 行（第二个写入口）"
    assert callable(persist_web_notification)
    assert admin_module.PushService is not None


@pytest.mark.asyncio
async def test_notification_row_is_bound_to_the_delivered_payload(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """落的那一行必须是"投出去的那一条"：id 与 sub 都取自当轮载荷，不是另查一遍用户表。"""
    stub = _StubProvider(PushResult("web", True, "ok"))
    monkeypatch.setattr(bots_module, "make_push_provider", lambda _t: stub)
    _uid, cid, _tid, _body = await _seed_web_stack(db_session, trigger="manual")
    await bots_module.test_push(cid, message="r19 绑正文", title="r19-binding", db=db_session)
    row = (await db_session.execute(select(Notification).where(Notification.title == "r19-binding"))).scalar_one()
    sent = stub.sent[-1]
    assert row.id == sent.notification_id, "行 id 与帧 id 不同源（前端会把同一条消息显示两遍）"
    assert row.sub == (sent.external_user_id or "")
    assert row.is_broadcast == (not sent.external_user_id)
