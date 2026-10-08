"""W3 推送调度器并发安全与事件 outbox 测试。

连库口径（审查缝合后与 test_job_worker 同法）：
- 涉及「跨连接/并发」语义的用例（并发领取）走**真提交独立连接** + 用例级清场——
  不能用 db_session.bind 共享连接做并发：同一连接上交错 SAVEPOINT 必然
  InvalidSavepointSpecification；
- 涉及「全表扫描」断言的用例（claim_pending_events / PushLog 计数）先真提交清场
  push 域残留——隔离 rollback 只覆盖 savepoint，覆盖不了此前真提交落库的行；
- 纯 savepoint 隔离（db_session）足够其余单连接用例。
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.bothot_entities import BotChannel, PushEvent, PushLog, PushTask
from app.models.entities import User
from app.services.push_events import claim_pending_events, emit_event
from app.services.push_scheduler import PushTaskScheduler
from app.services.push_template import render, validate_template

# PushTask.created_by FK → users.id：连库用例必须落真实用户行（审查缝合修复，
# 此前 created_by="test-user" 无对应 users 行，PG 外键一律拒绝）。
_TEST_USER_SUB = "w3-scheduler-test-user"

_PG_DSN = os.environ.get("AIDEANBOT_TEST_PG_DSN", "postgresql+psycopg://bothot:bothot@localhost:5433/bothot")


def _real_factory() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """真提交连接（test_job_worker 同口径）。"""
    engine = create_async_engine(_PG_DSN, pool_pre_ping=True, connect_args={"connect_timeout": 3})
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _purge_tables(engine: AsyncEngine, *models: type) -> None:
    """用例级清场：真提交删除 push 域残留，保住全表扫描断言的确定性。"""
    async with engine.begin() as conn:
        for model in models:
            await conn.execute(delete(model))


@pytest.fixture
async def scheduler_user(db_session: AsyncSession):
    user = (await db_session.execute(select(User).where(User.sub == _TEST_USER_SUB))).scalar_one_or_none()
    if user is None:
        user = User(
            sub=_TEST_USER_SUB,
            email=f"{_TEST_USER_SUB}@test.local",
            nickname="W3 调度测试",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
    return user


@pytest.fixture
async def channel(db_session: AsyncSession):
    ch = BotChannel(
        name="test-channel",
        channel_type="webhook",
        webhook_url="http://localhost:9999/test",
        secret_enc="",
        extra_config="{}",
        status="active",
    )
    db_session.add(ch)
    await db_session.commit()
    await db_session.refresh(ch)
    return ch


@pytest.fixture
async def cron_task(db_session: AsyncSession, channel, scheduler_user):
    task = PushTask(
        name="test-cron",
        bot_channel_id=channel.id,
        trigger_type="cron",
        cron_expr="*/5 * * * *",
        content_template="test {date}",
        status="active",
        next_run_at=datetime.now(UTC) - timedelta(minutes=1),
        created_by=scheduler_user.id,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    return task


@pytest.fixture
async def event_task(db_session: AsyncSession, channel, scheduler_user):
    task = PushTask(
        name="test-event",
        bot_channel_id=channel.id,
        trigger_type="event",
        trigger_event="new_article",
        content_template="new: {doc_title}",
        status="active",
        created_by=scheduler_user.id,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    return task


async def test_concurrent_claim_no_duplicate():
    """双 worker 真连接并发领取：SKIP LOCKED 必须保证零重复领取。

    两个并发事务各自独立连接（真提交口径）；若 SKIP LOCKED 失效，两者会取到
    同一任务 → 断言失败。取件范围 = 本用例 seed 的 3 条到期任务（先清场 push_tasks，
    防此前运行的残留任务混入断言——test_job_worker 的 D19 同教训）。
    """
    engine, factory = _real_factory()
    try:
        # 本用例不经 db_session 夹具（需要真连接并发），须自带与 conftest 同口径的
        # 不可达 skip——否则 PG 缺席时会以丑陋报错染色门禁
        try:
            await _purge_tables(engine, PushTask, PushLog, PushEvent)
        except SQLAlchemyError as exc:
            pytest.skip(f"PG 不可达（{type(exc).__name__}），环境恢复后复跑本用例")

        async with factory() as seed:
            user = User(
                sub="w3-concurrent-user",
                email="w3-concurrent@test.local",
                nickname="W3 并发测试",
            )
            seed.add(user)
            await seed.flush()
            ch = BotChannel(
                name="w3-concurrent-channel",
                channel_type="webhook",
                webhook_url="http://localhost:9999/test",
                status="active",
            )
            seed.add(ch)
            await seed.flush()
            now = datetime.now(UTC)
            for i in range(3):
                seed.add(
                    PushTask(
                        name=f"concurrent-{i}",
                        bot_channel_id=ch.id,
                        trigger_type="cron",
                        cron_expr="*/5 * * * *",
                        content_template=f"task{i}",
                        status="active",
                        next_run_at=now - timedelta(minutes=1),
                        created_by=user.id,
                    )
                )
            await seed.commit()

        async def claim_one() -> list[str]:
            scheduler = PushTaskScheduler(factory)
            tasks = await scheduler._claim_due_cron_tasks(datetime.now(UTC))
            return [t.id for t in tasks]

        first, second = await asyncio.gather(claim_one(), claim_one())

        claimed = [*first, *second]
        assert len(claimed) == 3, f"3 条到期任务必须各被领取一次，实际 {len(claimed)}"
        assert len(set(claimed)) == 3, "SKIP LOCKED 失效：同一任务被重复领取"
    finally:
        try:
            async with engine.begin() as conn:
                await conn.execute(delete(PushTask).where(PushTask.name.like("concurrent-%")))
                await conn.execute(delete(BotChannel).where(BotChannel.name == "w3-concurrent-channel"))
                await conn.execute(delete(User).where(User.sub == "w3-concurrent-user"))
        except SQLAlchemyError:
            pass  # skip 路径（engine 已 dispose / 连接不可达）：清场无意义，不遮蔽 skip
        await engine.dispose()


async def test_cron_next_run_advanced(db_session: AsyncSession, cron_task):
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    scheduler = PushTaskScheduler(factory)

    now = datetime.now(UTC)
    tasks = await scheduler._claim_due_cron_tasks(now)

    assert len(tasks) == 1
    assert tasks[0].next_run_at > now
    assert tasks[0].last_run_at is not None


async def test_cron_parse_failure_pauses_task(db_session: AsyncSession, channel, scheduler_user):
    task = PushTask(
        name="bad-cron",
        bot_channel_id=channel.id,
        trigger_type="cron",
        cron_expr="not-a-cron",
        content_template="test",
        status="active",
        next_run_at=datetime.now(UTC) - timedelta(minutes=1),
        created_by=scheduler_user.id,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    scheduler = PushTaskScheduler(factory)
    await scheduler._claim_due_cron_tasks(datetime.now(UTC))

    await db_session.refresh(task)
    assert task.status == "paused"


async def test_emit_event_invalid_type_rejected(db_session: AsyncSession):
    from app.core.errors import RequestInvalidError

    with pytest.raises(RequestInvalidError):
        await emit_event(db_session, "invalid_type", {})


async def test_event_full_pipeline(db_session: AsyncSession, event_task):
    engine, _factory = _real_factory()
    try:
        # 清场跨运行残留的未消费事件（claim 扫全表，残留破坏确定性断言）
        await _purge_tables(engine, PushEvent)
    finally:
        await engine.dispose()

    await emit_event(db_session, "new_article", {"doc_title": "test-doc"})
    await db_session.commit()

    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    scheduler = PushTaskScheduler(factory)

    events = await claim_pending_events(db_session)
    assert len(events) == 1
    assert events[0].consumed_at is not None

    await scheduler._dispatch_event(events[0], datetime.now(UTC))

    result = await db_session.execute(select(PushLog))
    logs = result.scalars().all()
    assert len(logs) >= 1


async def test_same_event_multiple_tasks(db_session: AsyncSession, channel, scheduler_user):
    engine, _factory = _real_factory()
    try:
        # 清场跨运行残留（事件与投递日志都是全表计数断言）
        await _purge_tables(engine, PushEvent, PushLog)
    finally:
        await engine.dispose()

    for i in range(2):
        task = PushTask(
            name=f"event-task-{i}",
            bot_channel_id=channel.id,
            trigger_type="event",
            trigger_event="new_article",
            content_template=f"task{i}",
            status="active",
            created_by=scheduler_user.id,
        )
        db_session.add(task)
    await db_session.commit()

    await emit_event(db_session, "new_article", {})
    await db_session.commit()

    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    scheduler = PushTaskScheduler(factory)

    events = await claim_pending_events(db_session)
    await scheduler._dispatch_event(events[0], datetime.now(UTC))

    result = await db_session.execute(select(PushLog))
    logs = result.scalars().all()
    assert len(logs) == 2


async def test_event_delivery_failure_no_reclaim(db_session, channel, scheduler_user):
    """R1.2（S3.6）：outbox 消费失败分支端到端。

    链路：emit → claim（consumed_at 置位）→ 派发 → webhook 投递失败（不可达端口）
    → failed PushLog + 重试簿记 → **重投领取为空**（at-most-once 锚定：
    consumed_at 在 claim 时已置，投递结果不影响事件生命周期，不产生重复投递）。
    成功分支已有 test_event_full_pipeline / test_same_event_multiple_tasks 覆盖。
    """
    engine, _factory = _real_factory()
    try:
        await _purge_tables(engine, PushEvent, PushLog)
    finally:
        await engine.dispose()

    task = PushTask(
        name="event-fail-task",
        bot_channel_id=channel.id,
        trigger_type="event",
        trigger_event="new_article",
        content_template="fail: {doc_title}",
        status="active",
        created_by=scheduler_user.id,
    )
    db_session.add(task)
    await db_session.commit()

    await emit_event(db_session, "new_article", {"doc_title": "fail-doc"})
    await db_session.commit()

    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    scheduler = PushTaskScheduler(factory)

    # claim：事件被消费标记（投递尚未发生——at-most-once 的先标记语义）
    events = await claim_pending_events(db_session)
    assert len(events) == 1
    assert events[0].consumed_at is not None

    # 派发：channel 夹具 webhook_url 指向 localhost:9999 不可达端口
    # → webhook provider 走 except Exception 分支，PushResult(delivered=False, retryable=True)
    await scheduler._dispatch_event(events[0], datetime.now(UTC))

    # 投递回执：failed PushLog 落库且错误信息非空
    logs = (await db_session.execute(select(PushLog))).scalars().all()
    assert len(logs) == 1
    assert logs[0].status == "failed"
    assert logs[0].error_message != ""

    # 重试簿记：retryable 失败 → retry_count 推进 + next_retry_at 计划退避
    # （跨会话读：refresh 强制回库，绕开本会话 identity map 的 fixture 期旧值——
    #   同 test_cron_parse_failure_pauses_task:224 的既有口径）
    await db_session.refresh(task)
    assert task.retry_count == 1
    assert task.next_retry_at is not None

    # at-most-once 核心断言：事件已消费，重投领取为空（失败不回队）
    again = await claim_pending_events(db_session)
    assert again == []


async def test_render_known_variables():
    result = render("hello {date} {time}", {})
    assert "hello" in result
    assert "{" not in result


async def test_render_unknown_variable_stripped():
    result = render("hello {unknown_var} world", {})
    assert result == "hello  world"


async def test_validate_template_valid():
    assert validate_template("hello {date}") is None


async def test_validate_template_invalid():
    result = validate_template("hello {bad_var}")
    assert result is not None
    assert "bad_var" in result
