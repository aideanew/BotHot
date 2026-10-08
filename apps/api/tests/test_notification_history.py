"""S1（R1.2）通知持久化四链路测试：落库 savepoint / history 可见性与分页 / 已读回执。

直调路由函数（Depends 作为默认值仅在 HTTP 路径生效），绕开登录门禁与 HTTP 层；
db_session 外层事务回滚隔离（Notification.sub 为 String 非 FK，无需 User 行）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.system import (
    NotificationReadRequest,
    notifications_history,
    notifications_read,
)
from app.models.bothot_entities import Notification
from app.providers.push.base import PushMessage
from app.services.push_scheduler import persist_web_notification


async def _seed(db: AsyncSession, **kw) -> Notification:
    n = Notification(**kw)
    db.add(n)
    await db.flush()
    return n


def _msg(**kw) -> PushMessage:
    kw.setdefault("title", "测试标题")
    kw.setdefault("message", "测试正文")
    return PushMessage(**kw)


# ── S1.1 落库 ────────────────────────────────────────────────


async def test_persist_broadcast_notification(db_session: AsyncSession):
    await persist_web_notification(db_session, _msg(space_id="sp1", doc_id="d1"))
    rows = (
        (await db_session.execute(select(Notification).where(Notification.is_broadcast.is_(True))))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    n = rows[0]
    assert n.sub == "" and n.channel_type == "web"
    assert (n.title, n.message, n.space_id, n.doc_id) == ("测试标题", "测试正文", "sp1", "d1")
    assert n.read_at is None


async def test_persist_directed_notification(db_session: AsyncSession):
    await persist_web_notification(db_session, _msg(external_user_id="sub-abc"))
    rows = (
        (await db_session.execute(select(Notification).where(Notification.sub == "sub-abc")))
        .scalars()
        .all()
    )
    assert len(rows) == 1 and rows[0].is_broadcast is False


async def test_persist_failure_rolls_back_only_notification(db_session: AsyncSession):
    """title 超长（String(256)）触发 DB 错误 → savepoint 回滚仅通知行，会话仍可用。"""
    await persist_web_notification(db_session, _msg(title="x" * 300))
    rows = (await db_session.execute(select(Notification))).scalars().all()
    assert rows == []  # 落库失败被吞，未留下半截数据
    # 会话仍可用：正常落一条不受影响
    await persist_web_notification(db_session, _msg())
    assert len((await db_session.execute(select(Notification))).scalars().all()) == 1


# ── S1.2 history ────────────────────────────────────────────


async def test_history_visibility_order_and_counts(db_session: AsyncSession):
    now = datetime.now(UTC)
    await _seed(db_session, sub="me", is_broadcast=False, title="mine-1", created_at=now)
    await _seed(db_session, sub="me", is_broadcast=False, title="mine-2", created_at=now)
    await _seed(db_session, sub="", is_broadcast=True, title="cast", created_at=now)
    await _seed(db_session, sub="other", is_broadcast=False, title="hidden", created_at=now)

    resp = await notifications_history(
        sub="me", session=db_session, paging=(50, 0)
    )
    data = resp.body and __import__("json").loads(resp.body)["data"]
    titles = [it["title"] for it in data["items"]]
    assert "hidden" not in titles
    assert set(titles) == {"mine-1", "mine-2", "cast"}
    assert data["total"] == 3 and data["unread_total"] == 3
    assert data["limit"] == 50 and data["offset"] == 0


async def test_history_pagination_window(db_session: AsyncSession):
    now = datetime.now(UTC)
    for i in range(5):
        await _seed(
            db_session, sub="me", is_broadcast=False, title=f"n{i}",
            created_at=now + timedelta(seconds=i),
        )
    resp = await notifications_history(sub="me", session=db_session, paging=(2, 1))
    data = __import__("json").loads(resp.body)["data"]
    # 倒序：n4 n3 n2 n1 n0，窗口 offset=1 limit=2 → [n3, n2]
    assert [it["title"] for it in data["items"]] == ["n3", "n2"]
    assert data["total"] == 5


# ── S1.3 已读回执 ───────────────────────────────────────────


async def test_read_single_and_unread_count(db_session: AsyncSession):
    n = await _seed(db_session, sub="me", is_broadcast=False, title="t1")
    resp = await notifications_read(
        NotificationReadRequest(id=n.id), sub="me", session=db_session
    )
    assert __import__("json").loads(resp.body)["data"]["updated"] == 1
    resp = await notifications_history(sub="me", session=db_session, paging=(50, 0))
    data = __import__("json").loads(resp.body)["data"]
    assert data["unread_total"] == 0 and data["items"][0]["read_at"] is not None
    # 已读行不重复计数
    resp2 = await notifications_read(
        NotificationReadRequest(id=n.id), sub="me", session=db_session
    )
    assert __import__("json").loads(resp2.body)["data"]["updated"] == 0


async def test_read_scope_blocks_foreign_rows(db_session: AsyncSession):
    foreign = await _seed(db_session, sub="other", is_broadcast=False, title="f1")
    resp = await notifications_read(
        NotificationReadRequest(id=foreign.id), sub="me", session=db_session
    )
    assert __import__("json").loads(resp.body)["data"]["updated"] == 0  # 越权视同不存在


async def test_read_batch_before_and_validation(db_session: AsyncSession):
    now = datetime.now(UTC)
    for i in range(3):
        await _seed(
            db_session, sub="me", is_broadcast=False, title=f"b{i}",
            created_at=now + timedelta(seconds=i),
        )
    cutoff = now + timedelta(seconds=1)
    resp = await notifications_read(
        NotificationReadRequest(before=cutoff), sub="me", session=db_session
    )
    assert __import__("json").loads(resp.body)["data"]["updated"] == 2  # b0/b1
    # id 与 before 同传 / 全空 → 400
    bad1 = await notifications_read(
        NotificationReadRequest(id="x", before=cutoff), sub="me", session=db_session
    )
    bad2 = await notifications_read(NotificationReadRequest(), sub="me", session=db_session)
    assert bad1.status_code == 400 and bad2.status_code == 400
