"""TASK-016：web 实时帧 id 与 notifications 行 id 同源。

三层证据，各自独立可判：
- 载荷层（零 Redis/PG 依赖）：fake client 捕获 publish 入参，断言 id 有/无两种口径；
- **管道层**（零 DB 依赖，fake session + fake provider 跑真 `_execute_task`）：
  断言"投递前自铸的 id"确实同时进入发布载荷与落库对象——**删掉
  `push_scheduler.py:184` 的 `notification_id=notification_id` 必须让本文件变红**；
- 落库层（连库，PG 不可达时 `db_session` 自动 skip）：真 INSERT 后行 id == 帧 id。

直投路径（`bots.py:341` 测试推送 / `:624` run-now）不落库也不预铸 ⇒ 载荷里**没有** id 键，
前端据此退回内容窗口去重（见 remaining-outline.md R.11 G-19 / R.6.1.3）。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bothot_entities import Notification
from app.providers.push.base import PushMessage, PushResult
from app.providers.push.web import WebPushProvider
from app.services.push_scheduler import PushTaskScheduler, persist_web_notification


class _FakeRedis:
    """只记录 publish 入参，不连真 Redis。"""

    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, payload: str) -> int:
        self.published.append((channel, payload))
        return 1


async def _publish(msg: PushMessage) -> tuple[str, dict]:
    fake = _FakeRedis()
    with (
        patch("app.core.config.get_settings", return_value=type("S", (), {"redis_url": "redis://x"})()),
        patch("app.core.security.get_shared_redis", return_value=fake),
    ):
        result = await WebPushProvider().push(msg)
    assert result.delivered is True
    channel, raw = fake.published[0]
    return channel, json.loads(raw)


def _msg(**kw) -> PushMessage:
    kw.setdefault("title", "测试标题")
    kw.setdefault("message", "测试正文")
    return PushMessage(**kw)


# ── 载荷层 ───────────────────────────────────────────────────


async def test_frame_carries_id_when_pregen():
    channel, payload = await _publish(_msg(notification_id="11111111-1111-1111-1111-111111111111"))
    assert payload["id"] == "11111111-1111-1111-1111-111111111111"
    assert channel == "bothot:notifications:broadcast"


async def test_frame_omits_id_key_when_absent():
    """直投路径不预铸 ⇒ 载荷里没有 id 键（而不是 id: null）。"""
    _, payload = await _publish(_msg(external_user_id="sub-abc"))
    assert "id" not in payload
    assert payload["title"] == "测试标题"


# ── 管道层：跑真 _execute_task ───────────────────────────────


class _FakeNested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """按被查询的表名分派结果；记录 add() 进来的 ORM 对象。"""

    def __init__(self, channel) -> None:
        self._channel = channel
        self.added: list[object] = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        text = str(stmt)
        if "push_tasks" in text:
            obj = SimpleNamespace(id="t1", status="active", retry_count=0, next_retry_at=None)
        elif "bot_channels" in text:
            obj = self._channel
        else:  # pragma: no cover - 分派表外的查询说明实现漂移了
            raise AssertionError(f"未预期的语句：{text[:80]}")
        return SimpleNamespace(scalar_one_or_none=lambda: obj)

    def add(self, obj) -> None:
        self.added.append(obj)

    def begin_nested(self):
        return _FakeNested()

    async def commit(self) -> None:
        self.commits += 1


class _RecordingProvider:
    def __init__(self, channel_name: str) -> None:
        self.channel_name = channel_name
        self.messages: list[PushMessage] = []

    async def push(self, message: PushMessage) -> PushResult:
        self.messages.append(message)
        return PushResult(self.channel_name, True, "", "fake")


async def _run_execute_task(channel_type: str):
    ch = SimpleNamespace(
        id="c1",
        status="active",
        channel_type=channel_type,
        webhook_url="",
        secret_enc="",
        extra_config="",
        # :243-245 会对计数做 +=，未初始化会 AttributeError
        total_push_count=0,
        success_push_count=0,
    )
    task = SimpleNamespace(
        id="t1",
        bot_channel_id="c1",
        name="任务名",
        content_template="正文",
        status="active",
        retry_count=0,
        next_retry_at=None,
    )
    session = _FakeSession(ch)
    provider = _RecordingProvider(channel_type)
    scheduler = PushTaskScheduler(lambda: session)
    with (
        patch("app.services.push_scheduler.make_push_provider", return_value=provider),
        patch("app.services.push_scheduler.decrypt_channel_secret", return_value=""),
        patch("app.services.push_scheduler.decrypt_extra_config", return_value=""),
    ):
        await scheduler._execute_task(task, datetime.now(UTC))
    return session, provider


async def test_scheduler_frame_id_equals_persisted_row_id():
    """管道层主证据：同一 id 既在发布载荷里，也在落库对象上。"""
    session, provider = await _run_execute_task("web")
    assert len(provider.messages) == 1
    frame_id = provider.messages[0].notification_id
    assert frame_id

    rows = [o for o in session.added if isinstance(o, Notification)]
    assert len(rows) == 1, "web 渠道投递成功必须落 1 行通知"
    assert rows[0].id == frame_id


async def test_scheduler_mints_empty_id_for_non_web_channel():
    """非 web 渠道不自铸（且不调用落库）——判据绑定 `ch.channel_type == "web"` 谓词。"""
    session, provider = await _run_execute_task("feishu")
    assert provider.messages[0].notification_id == ""
    assert [o for o in session.added if isinstance(o, Notification)] == []


# ── 落库层（连库；PG 不可达自动 skip） ──────────────────────


async def test_frame_id_equals_row_id(db_session: AsyncSession):
    channel, payload = await _publish(_msg(external_user_id="sub-xyz", notification_id="frame-id-1"))
    assert channel == "bothot:notifications:sub-xyz"

    await persist_web_notification(db_session, _msg(external_user_id="sub-xyz", notification_id="frame-id-1"))
    row = (
        (await db_session.execute(select(Notification).where(Notification.sub == "sub-xyz")))
        .scalars()
        .one()
    )
    assert row.id == payload["id"] == "frame-id-1"
    assert row.is_broadcast is False


async def test_row_gets_id_without_frame(db_session: AsyncSession):
    """回归护栏（非本卡验收项）：未预铸时落库仍自铸主键——改动前后都应绿。"""
    await persist_web_notification(db_session, _msg())
    row = (
        (await db_session.execute(select(Notification).where(Notification.is_broadcast.is_(True))))
        .scalars()
        .one()
    )
    assert row.id and len(row.id) == 36
