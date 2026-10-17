"""STEP-23：手动 / 测试直投也要写站内通知历史（REQ-F-001 的未闭环项）。

需求原文把"手动"与"定时、事件"并列为三种触发方式，而 `persist_web_notification` 在
314d7f2 上只有**一个**调用点（`services/push_scheduler.py:229`）⇒ web 渠道走 Cron/事件会进
离线补投历史，走"手动触发 / 一键测试"**永不进历史**。需求文档自己登记了这条不一致，
V0.12.0 的 31 张卡无一张认领（`grep -rn persist_web_notification docs/任务规划V0.12.0/steps` 0 命中）。

两层判据，因为这两层能在不同机器上判：

- **第 1 节（本机 `@win` 可判）**：结构性守卫——两条直投函数必须调用 `persist_web_notification`
  且带 `web ∧ delivered` 的门槛。这一层不需要数据库，也正是它能立刻抓住缺陷的原因。
- **第 2 节（连库，`@ci` ubuntu 判，D-V4-01）**：真的数 `notifications` 行。
  本机无 PG 时这些用例 skip，**skip 不是通过**。

CI 侧为什么用桩 provider 而不是 HTTP：web provider 的第一件事是问 Redis
（`providers/push/web.py:30-31`，不可用就 `delivered=False`），而 `backend` job 没有 Redis 服务。
用桩把"投递成功"这件事与被测的落库面解耦，才是本卡要判的那条——否则在 CI 上会拿到一个
"因为环境没 Redis 所以没落库"的假红。
"""

from __future__ import annotations

import inspect
import uuid
from typing import Any

import pytest
from sqlalchemy import func, select

from app.api.v1 import bots as bots_module
from app.models.bothot_entities import BotChannel, Notification, PushTask
from app.models.entities import User
from app.providers.push.base import PushMessage, PushResult


class _StubProvider:
    """可指定回执的 provider：只回答"投递成没成"，不碰网络、不碰 Redis。"""

    def __init__(self, result: PushResult) -> None:
        self._result = result
        self.sent: list[PushMessage] = []

    async def push(self, message: PushMessage) -> PushResult:
        self.sent.append(message)
        return self._result


# ── 1. 结构守卫（本机可判）────────────────────────────────────────────────────

_DIRECT_CALLERS = ("test_push", "run_push_task_now")


def _calls_persist(fn: Any) -> bool:
    return "persist_web_notification(" in inspect.getsource(fn)


def test_structural_guard_predicate_has_both_polarities() -> None:
    """判据自检：对**不该**落库的函数必须为 False，否则下一节的绿没有含义。

    `list_channels` 是纯读函数；若这个扫描器恒真，第二节的四条连库用例即使全 skip
    也会让本卡看起来"已交付"。
    """
    assert _calls_persist(bots_module.list_push_logs) is False
    assert _calls_persist(bots_module.list_channels) is False


@pytest.mark.parametrize("name", _DIRECT_CALLERS)
def test_direct_push_paths_delegate_to_the_shared_persist_fn(name: str) -> None:
    """S23.1.2 的机械面：两条直投都必须复用**同一个**落库函数，且不复制函数体。

    D-V10-05 的取舍是"直投复用调度器同一落库函数"。复制一份 `Notification(...)` 构造会造出
    第二个落库真源——广播/定向判定（`external_user_id` 有无）与 id 口径就会在两处漂移。
    """
    fn = getattr(bots_module, name)
    src = inspect.getsource(fn)
    assert _calls_persist(fn), f"{name} 没有调用 persist_web_notification ⇒ 手动/测试推送永不进历史"
    assert "Notification(" not in src, f"{name} 自己构造了 Notification 行（第二个落库真源）"
    assert 'channel_type == "web"' in src and "result.delivered" in src, (
        f"{name} 的落库没有 web ∧ delivered 门槛：失败或非 web 渠道也会被写进历史"
    )


# ── 2. 真落库（连库，@ci 判）───────────────────────────────────────────────────


async def _seed_channel(db_session: Any, channel_type: str = "web", user_id: str | None = None) -> str:
    cid = str(uuid.uuid4())
    db_session.add(
        BotChannel(
            id=cid,
            name=f"s23-{channel_type}-{cid[:6]}",
            channel_type=channel_type,
            webhook_url="https://example.invalid/hook/s23" if channel_type != "web" else "",
            status="active",
            user_id=user_id,
        )
    )
    await db_session.flush()
    return cid


async def _seed_user(db_session: Any, sub: str | None = None) -> tuple[str, str]:
    """种一个"两个锚天然不同"的用户：`User.id` 是本地 UUID、`User.sub` 是 SSO 锚。

    本卡的收件人判据只有在 `sub != id` 时才判得出东西——如果测试夹具让两者相等，
    "写错锚"和"写对锚"会同时通过。
    """
    sid = str(uuid.uuid4())
    user = User(
        id=sid,
        sub=sub if sub is not None else f"s23-sub-{sid[:8]}",
        email=f"s23-{sid[:8]}@s23.test",
        nickname="s23-owner",
    )
    db_session.add(user)
    await db_session.flush()
    return sid, user.sub


async def _seed_task(db_session: Any, channel_id: str) -> str:
    """播种一条手动任务。

    `created_by` 是 `users.id` 的 **NOT NULL 外键**（`bothot_entities.py:88-90`），
    所以必须先有一行 user——漏了它会拿到 `NotNullViolation`，而这条只在真库上现形：
    本机无 PG 时整组用例 skip，`skip 不是通过`。
    """
    tid = str(uuid.uuid4())
    owner = User(sub=f"s23-owner-{tid[:8]}", email=f"s23-owner-{tid[:8]}@s23.test", nickname="s23-owner")
    db_session.add(owner)
    # **必须先 flush 再读 `owner.id`**：`User.id` 是 Python 侧默认值（`default=gen_uuid`），
    # SQLAlchemy 要到 flush 才把它落到对象上——上一版我把 add 与构造 PushTask 连在一起写，
    # 于是 `created_by` 拿到的就是 None，`@ci` 报的还是同一条 NotNullViolation。
    await db_session.flush()
    db_session.add(
        PushTask(
            id=tid,
            name=f"s23-task-{tid[:6]}",
            bot_channel_id=channel_id,
            trigger_type="manual",
            content_template="S23 直投正文",
            status="active",
            created_by=owner.id,
        )
    )
    await db_session.flush()
    return tid


async def _count_notifications(db_session: Any, title: str) -> int:
    return int(
        (await db_session.scalar(select(func.count()).select_from(Notification).where(Notification.title == title)))
        or 0
    )


async def test_test_push_on_web_channel_writes_one_notification(db_session: Any) -> None:
    """S23.1.1 的正体（改前红）：`POST /bots/{id}/test` 成功投递后 `notifications` +1 行。

    D-V10-05 明确选"也进"：web 渠道的一次"测试"对收件人就是一条真实到达的消息，
    历史缺它会让离线补投漏发。若产品改意，删掉那一行调用即可（可逆）。
    """
    cid = await _seed_channel(db_session)
    title = f"s23-test-{uuid.uuid4().hex[:8]}"
    stub = _StubProvider(PushResult("web", True, "ok"))
    original = bots_module.make_push_provider
    bots_module.make_push_provider = lambda _t: stub
    try:
        await bots_module.test_push(cid, message="S23 测试正文", title=title, db=db_session)
    finally:
        bots_module.make_push_provider = original

    assert stub.sent, "provider 根本没被调用，那条 +1 就无从谈起"
    # 预铸的 id 必须真的进了载荷：没有它，落库行与 SSE 帧会是两个 id，前端把同一条消息显示两遍
    # （TASK-016 的口径；`test_notification_frame_id.py` 里"直投不预铸"那句已被本卡推翻，见 P-24）。
    assert stub.sent[-1].notification_id, "web 直投未预铸 notification_id ⇒ 帧与行无法同 id"
    assert await _count_notifications(db_session, title) == 1, "web 直投没有写站内通知历史"


async def test_run_now_on_web_channel_writes_one_notification(db_session: Any) -> None:
    """另一半（需求原文的"手动"触发）：`POST /bots/tasks/{id}/run` 也必须 +1 行。

    这条与上一条各判一个调用点——只修一处会留下"手动触发仍不进历史"的半个缺陷，
    而两处的症状在页面上是同一个。
    """
    cid = await _seed_channel(db_session)
    task_id = await _seed_task(db_session, cid)
    stub = _StubProvider(PushResult("web", True, "ok"))
    original = bots_module.make_push_provider
    bots_module.make_push_provider = lambda _t: stub
    try:
        await bots_module.run_push_task_now(task_id, db=db_session)
    finally:
        bots_module.make_push_provider = original

    rows = int(
        (
            await db_session.scalar(
                select(func.count()).select_from(Notification).where(Notification.channel_type == "web")
            )
        )
        or 0
    )
    assert rows == 1, f"/run 之后 web 通知应有 1 行，实得 {rows}"
    # 载荷里的 id 与落库行同值（TASK-016 的帧/行同 id 口径，直投也遵守）
    row = (await db_session.scalars(select(Notification).where(Notification.channel_type == "web"))).one()
    assert row.id == stub.sent[-1].notification_id, "直投预铸的 id 与落库行不同 ⇒ SSE 帧与历史行会各说一遍"


async def test_failed_delivery_writes_no_notification(db_session: Any) -> None:
    """反向：投递**失败**不得留下历史行。

    没有这条，"无条件落库"也能通过上面两条——而"通知历史"记的是"用户收到过"，
    把失败也算进去会让补投逻辑对同一条消息二次打扰。
    """
    cid = await _seed_channel(db_session)
    title = f"s23-fail-{uuid.uuid4().hex[:8]}"
    stub = _StubProvider(PushResult("web", False, "对端拒绝"))
    original = bots_module.make_push_provider
    bots_module.make_push_provider = lambda _t: stub
    try:
        await bots_module.test_push(cid, message="S23 失败正文", title=title, db=db_session)
    finally:
        bots_module.make_push_provider = original

    assert stub.sent, "provider 未被调用则这条用例是空转"
    assert await _count_notifications(db_session, title) == 0, "失败的投递也进了站内通知历史"


async def test_non_web_channel_writes_no_notification(db_session: Any) -> None:
    """反向：非 web 渠道（飞书）投递成功也不许进**站内**历史。

    它有自己的 PushLog；写进 notifications 会让站内铃铛出现一条"根本没在站内发生过"的消息。
    """
    cid = await _seed_channel(db_session, channel_type="feishu")
    stub = _StubProvider(PushResult("feishu", True, "ok"))
    original = bots_module.make_push_provider
    bots_module.make_push_provider = lambda _t: stub
    before = int((await db_session.scalar(select(func.count()).select_from(Notification))) or 0)
    try:
        await bots_module.test_push(cid, message="S23 飞书正文", title=f"s23-fs-{uuid.uuid4().hex[:8]}", db=db_session)
    finally:
        bots_module.make_push_provider = original

    after = int((await db_session.scalar(select(func.count()).select_from(Notification))) or 0)
    assert after == before, "非 web 渠道被写进了站内通知历史"


# ── 3. 收件人锚（返工轮：卡目标第二句"对收件人可见"的正面判据）──────────────────


async def test_directed_web_channel_history_row_is_keyed_by_the_recipient_sub(db_session: Any) -> None:
    """渠道绑了用户时，历史行的 `sub` 必须是**收件人的 SSO sub**，不是 `users.id`。

    这是 STEP-23 返工轮新增的一条，起因是独立复核抓到我第一版的夹具全都 `user_id=None`
    ⇒ 四条用例判的**只有广播那一支**，而定向那一支会把 `bot_channels.user_id`（users.id）
    原样写进 `Notification.sub`。`_notification_scope` 按 `sub == 当前用户的 SSO sub` 过滤，
    所以那条行是**死行**：写了，谁都查不到，而卡面那句"对收件人可见"恰好没被任何用例判过。
    """
    uid, usub = await _seed_user(db_session)
    cid = await _seed_channel(db_session, user_id=uid)
    title = f"s23-anchor-{uuid.uuid4().hex[:8]}"
    stub = _StubProvider(PushResult("web", True, "ok"))
    original = bots_module.make_push_provider
    bots_module.make_push_provider = lambda _t: stub
    try:
        await bots_module.test_push(cid, message="S23 锚点正文", title=title, db=db_session)
    finally:
        bots_module.make_push_provider = original

    row = (await db_session.scalars(select(Notification).where(Notification.title == title))).one()
    assert row.sub == usub, f"历史行写的是 {row.sub!r}，收件人按 sub 过滤查不到 ⇒ 又是一条死行"
    assert row.sub != uid, "sub 被填成了 users.id：这正是本卡第一版的形态"
    assert row.is_broadcast is False, "定向渠道的测试推送不许标成广播（那会让全站都看到别人的定向消息）"
    # 实时帧与历史行同锚：订阅侧 `system.py:_notification_channels` 同时挂 sub 与 users.id，
    # 所以"帧收到了"从来不能证明"行能查到"——这里判的是两处用同一个锚。
    assert stub.sent[-1].external_user_id == usub, "载荷锚与落库锚不同 ⇒ 帧与行各说一遍"


async def test_unresolvable_sub_never_upgrades_a_directed_push_to_broadcast(db_session: Any) -> None:
    """反向（返工轮的极性）：解析不到 sub 时**退回 users.id**，不许退回空串。

    空串在这条链上不是"没有收件人"，而是 `is_broadcast=True`（`persist_web_notification` 的
    分支就写在那里）。所以"为了健壮起见兜个默认值"会把一个身份缺陷换成**越权缺陷**：
    一条定向测试推送变成全站可见。这条用例就是为了让那种好心的改法当场红。
    """
    uid, _ = await _seed_user(db_session, sub="")
    cid = await _seed_channel(db_session, user_id=uid)
    title = f"s23-nosub-{uuid.uuid4().hex[:8]}"
    stub = _StubProvider(PushResult("web", True, "ok"))
    original = bots_module.make_push_provider
    bots_module.make_push_provider = lambda _t: stub
    try:
        await bots_module.test_push(cid, message="S23 无 sub 正文", title=title, db=db_session)
    finally:
        bots_module.make_push_provider = original

    row = (await db_session.scalars(select(Notification).where(Notification.title == title))).one()
    assert row.is_broadcast is False, "定向渠道落成了广播行"
    assert row.sub == uid, f"退回锚应是 users.id，实得 {row.sub!r}"


def test_direct_push_does_not_feed_channel_user_id_straight_into_the_recipient_anchor() -> None:
    """本机可判的**早期线**（不是行为判据）：`test_push` 必须显式解析 `User.sub`。

    写在这儿的理由是"等 CI 告诉我"太晚：这条返工在 `@ci` 上不会被任何既有用例抓住
    （原有四条全是广播形态夹具），而源码形态是本机就能判的。
    行为判据是上面两条连库用例（`@ci` ubuntu 判，D-V4-01）——**这条过了不代表锚点是对的**。
    """
    src = inspect.getsource(bots_module.test_push)
    assert "external_user_id=ch.user_id" not in src, "又回到把 users.id 直接当收件人锚的写法"
    assert "User.sub" in src, "没有解析 SSO sub 这一步，定向行就会写成谁都查不到的死行"
