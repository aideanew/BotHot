"""STEP-26 S26.1.1：管理端直投（`POST /admin/push`）的 web 成功也要写站内历史。

调度器与两处直投之外，管理端还藏着第三条不经过调度器的 web 投递路径。
S26.2.1 让 `PushService.push` 在 web 投递成功后复用 `persist_web_notification`。
两条判据：

- web 成功 ⇒ 收件人按自己的 SSO sub 能从历史接口读回这条消息；
- webhook 成功 ⇒ 不写站内历史（防过度落库：它不是站内消息）。
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import func, select

from app.api.v1 import system as system_module
from app.api.v1.admin import PushRequest, admin_push
from app.models.bothot_entities import Notification
from app.models.entities import User
from app.providers.push.base import PushMessage, PushResult
from app.services import push as push_module


class _StubProvider:
    """只回答投递成功，不碰 Redis；同时记录是否预铸了 id。"""

    def __init__(self, channel: str) -> None:
        self.channel = channel
        self.sent: list[PushMessage] = []

    async def push(self, message: PushMessage) -> PushResult:
        self.sent.append(message)
        return PushResult(self.channel, True, "", "fake")


async def _seed_user(db_session: Any) -> tuple[User, str]:
    sid = str(uuid.uuid4())
    user = User(
        id=sid,
        sub=f"s26-admin-sub-{sid[:8]}",
        email=f"s26-{sid[:8]}@s26.test",
        nickname="s26-operator",
        role="operator",
    )
    db_session.add(user)
    await db_session.flush()
    return user, user.sub


async def _push(
    db_session: Any,
    monkeypatch: Any,
    *,
    actor: User,
    channel: str,
    recipient: str,
    message: str,
) -> _StubProvider:
    provider = _StubProvider(channel)
    monkeypatch.setattr(push_module, "make_push_provider", lambda _channel: provider)
    response = await admin_push(
        payload=PushRequest(channel=channel, external_user_id=recipient, message=message),
        actor=actor,
        session=db_session,
    )
    assert response.status_code == 200, response.body
    return provider


async def _notification_count(db_session: Any, message: str) -> int:
    return int(
        (
            await db_session.scalar(
                select(func.count()).select_from(Notification).where(Notification.message == message)
            )
        )
        or 0
    )


async def test_admin_web_push_is_visible_to_the_recipient(db_session: Any, monkeypatch: Any) -> None:
    """S26.1.1 正体（改前红）：web 成功 ⇒ 历史行存在且收件人读得回来。"""
    actor, usub = await _seed_user(db_session)
    body = f"s26-admin-{uuid.uuid4().hex[:8]}"

    provider = await _push(
        db_session, monkeypatch, actor=actor, channel="web", recipient=usub, message=body
    )

    assert provider.sent, "provider 未被调用，后面的历史断言就无从谈起"
    row = (await db_session.scalars(select(Notification).where(Notification.message == body))).one_or_none()
    assert row is not None, "管理端 web 直投没有写站内通知历史"
    assert provider.sent[-1].notification_id, "管理端 web 直投没有预铸 id ⇒ SSE 帧与历史行无法同值"
    assert row.sub == usub, "历史行没按收件人的 SSO sub 落库"
    assert row.is_broadcast is False, "定向消息被写成了广播"

    response = await system_module.notifications_history(sub=usub, session=db_session, paging=(50, 0))
    payload = json.loads(response.body)
    data = payload.get("data", payload)
    assert body in [item["message"] for item in data["items"]], "收件人按自己的 sub 读不到刚写入的消息"


async def test_admin_non_web_push_does_not_write_in_app_history(db_session: Any, monkeypatch: Any) -> None:
    """S26.1.1.a 反向：webhook 投递成功也不写站内历史（防过度落库）。"""
    actor, usub = await _seed_user(db_session)
    body = f"s26-webhook-{uuid.uuid4().hex[:8]}"

    provider = await _push(
        db_session, monkeypatch, actor=actor, channel="webhook", recipient=usub, message=body
    )

    assert provider.sent, "provider 未被调用，这条反向用例是空转"
    assert await _notification_count(db_session, body) == 0, "非 web 渠道被写进了站内通知历史"
