"""SPEC-M3 批次 5 / T6.2（2026-09-23）验收测试：推送通道注册表 + 推送触发。

本批为**诚实占位**（管理者裁定 2026-09-23）：通道接口与注册表落地，投递不实接。
验收口径相应改写为「**链路可分发 + 拒绝原因可测**」——取代 SPEC-M3 §五 原口径
「web 通道端到端可发」（该口径与同节「web 内置实现=站内通知占位」自相矛盾，
实测两案不可能同真）。

四层覆盖：
- provider 层：注册表顺序与全景、两个通道的拒绝原因**逐字锁定**（这是不谎报的
  唯一证据）、未知通道不臆造、占位 provider 永不报 delivered=True；
- service 层：校验顺序 通道 → 内容 → 目标、目标事实校验（空间/文档存在且文档
  属于所给空间）、校验失败在分发前完成（零副作用）；
- 路由层：operator+ 门禁、未投递转 50002/503（绝不 200 假成功）、校验错误仍为
  10005（不降级成能力未就绪）、读侧显式回报 implemented=False；
- 分发层：注入会真正投递的 provider，锁 200 回执形状（真通道落地时的回归网）。

不覆盖：真实微信出站（出站契约项目内不存在，ADR-0002 附录 A 仅入站验签；
LangBotClient 仅管理面 KB/ingest/retrieve）——活体挂凭据 + 契约缺口登记。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user_id, get_db
from app.main import create_app
from app.models.entities import ContentAsset, KnowledgeDocument, KnowledgeSpace, Source, User
from app.providers import push_port
from app.providers.push_port import (
    PUSH_CHANNELS,
    ClawbotPushProvider,
    PushMessage,
    PushResult,
    WebPushProvider,
    make_push_provider,
    registered_channels,
)
from app.services import push as push_module
from app.services.push import PushService

SPACE_ID_MISSING = "00000000-0000-0000-0000-000000000001"
DOC_ID_MISSING = "00000000-0000-0000-0000-000000000002"

WEB_REASON = WebPushProvider.reason
CLAWBOT_REASON = ClawbotPushProvider.reason


# ------------------------------------------------------------------ ① provider 层


def test_channels_registry_order_and_full_view() -> None:
    """注册表顺序即契约顺序；全景必须回报就绪度而非只给通道名。"""
    assert PUSH_CHANNELS == ("web", "clawbot")
    view = registered_channels()
    assert [c["channel"] for c in view] == list(PUSH_CHANNELS)
    for entry in view:
        assert entry["implemented"] is False
        assert entry["reason"]


def test_web_refusal_reason_verbatim() -> None:
    """web 的拒绝原因逐字锁定：这是「不谎报」的唯一证据，改文案即改契约。"""
    assert WEB_REASON == "web 通道无站内投递面（无通知表、无读端点），本批不构建"


def test_clawbot_refusal_reason_verbatim() -> None:
    assert CLAWBOT_REASON == (
        "clawbot 出站契约项目内不存在（ADR-0002 附录 A 仅入站验签），且微信凭据未注入——活体半程未通"
    )


def test_unknown_channel_not_invented() -> None:
    """未知通道必须报错而非臆造一个 provider（否则会静默丢消息）。"""
    with pytest.raises(ValueError, match="未知推送通道"):
        make_push_provider("sms")
    with pytest.raises(ValueError, match="web/clawbot"):
        make_push_provider("")


@pytest.mark.parametrize("provider_cls", [WebPushProvider, ClawbotPushProvider])
async def test_placeholder_never_reports_delivered(provider_cls: Any) -> None:
    """占位 provider 在任何输入下都不得返回 delivered=True。"""
    result = await provider_cls().push(
        PushMessage(external_user_id="wx-1", space_id="s", doc_id="d", message="hi")
    )
    assert result.delivered is False
    assert result.reason


# ------------------------------------------------------------------ ② service 层


def _svc(db_session: Any) -> PushService:
    return PushService(db_session)


async def test_validation_order_channel_then_content_then_targets(db_session) -> None:  # type: ignore[no-untyped-def]
    """校验顺序固定：通道错误优先于内容错误，内容错误优先于目标错误。

    顺序即契约——调用方依赖错误文案定位问题，乱序会让人误判。
    """
    svc = _svc(db_session)
    with pytest.raises(Exception, match="未知推送通道"):  # type: ignore[misc]
        await svc.push("sms", external_user_id="")  # 通道错优先于目标错
    with pytest.raises(Exception, match="不能为空"):  # type: ignore[misc]
        await svc.push("web", external_user_id="")  # 目标错优先于下游分发
    with pytest.raises(Exception, match="推送内容为空"):  # type: ignore[misc]
        await svc.push("web", external_user_id="wx-1")


async def test_content_validation_rejects_bad_inputs() -> None:
    svc = _svc(None)  # 内容校验不触库
    with pytest.raises(Exception, match="过长"):  # type: ignore[misc]
        await svc.push("web", external_user_id="wx" * 100)
    with pytest.raises(Exception, match="控制字符"):  # type: ignore[misc]
        await svc.push("web", external_user_id="wx-1", message="line1\nline2")
    with pytest.raises(Exception, match="过长"):  # type: ignore[misc]
        await svc.push("web", external_user_id="wx-1", message="x" * 2001)


async def test_target_validation_requires_existing_refs(db_session) -> None:  # type: ignore[no-untyped-def]
    svc = _svc(db_session)
    with pytest.raises(Exception, match="空间不存在"):  # type: ignore[misc]
        await svc.push("web", external_user_id="wx-1", space_id=SPACE_ID_MISSING)
    with pytest.raises(Exception, match="文档不存在"):  # type: ignore[misc]
        await svc.push("web", external_user_id="wx-1", doc_id=DOC_ID_MISSING)
    with pytest.raises(Exception, match="过长"):  # type: ignore[misc]
        await svc.push("web", external_user_id="wx-1", space_id="s" * 40)


async def test_doc_must_belong_to_given_space(db_session) -> None:  # type: ignore[no-untyped-def]
    """doc 不属于所给 space → 30004。不因 operator 跨用户授权而放宽数据事实校验。"""
    rows = await _seed(db_session)
    svc = _svc(db_session)
    with pytest.raises(Exception, match="不属于该空间"):  # type: ignore[misc]
        await svc.push(
            "web", external_user_id="wx-1", space_id=rows["space"], doc_id=rows["doc_b"]
        )


async def test_validation_failure_has_zero_side_effects(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    """校验失败不得触达 provider——半成功推送是最坏的失败模式。"""
    rows = await _seed(db_session)
    provider = _RecordingProvider()
    monkeypatch.setattr(push_port, "_PROVIDERS", {"web": provider, "clawbot": ClawbotPushProvider()})

    svc = _svc(db_session)
    with pytest.raises(Exception, match="不属于该空间"):  # type: ignore[misc]
        await svc.push("web", external_user_id="wx-1", space_id=rows["space"], doc_id=rows["doc_b"])
    with pytest.raises(Exception, match="文档不存在"):  # type: ignore[misc]
        await svc.push("web", external_user_id="wx-1", doc_id=DOC_ID_MISSING)
    with pytest.raises(Exception, match="控制字符"):  # type: ignore[misc]
        await svc.push("web", external_user_id="wx-1", message="a\nb")
    assert provider.pushed == []  # 三次失败，零次分发


# ------------------------------------------------------------------ ③ 路由层


async def _seed(db_session: Any) -> dict[str, str]:
    """两个互不相干的用户链 + 三个角色账号（与 test_r11_admin_routes 同构）。"""
    owner = User(sub="r11-push-owner", email="r11-push-owner@r11.test", nickname="owner")
    second = User(sub="r11-push-second", email="r11-push-second@r11.test", nickname="second")
    admin = User(sub="r11-push-admin", email="r11-push-admin@r11.test", nickname="admin", role="admin")
    operator = User(
        sub="r11-push-operator", email="r11-push-operator@r11.test", nickname="operator", role="operator"
    )
    plain = User(sub="r11-push-user", email="r11-push-user@r11.test", nickname="user")
    db_session.add_all([owner, second, admin, operator, plain])
    await db_session.flush()

    source = Source(type="wechat_oa", external_id="biz-r11-push", name="推送测试号")
    db_session.add(source)
    await db_session.flush()

    space = KnowledgeSpace(user_id=owner.id, name="推送租户A", langbot_kb_uuid="kb-push-a")
    space_b = KnowledgeSpace(user_id=second.id, name="推送租户B", langbot_kb_uuid="kb-push-b")
    db_session.add_all([space, space_b])
    await db_session.flush()

    asset_a = ContentAsset(
        source_id=source.id, external_id="pa-1", title="A文", content_hash="h-pa1", content_markdown="# A"
    )
    asset_b = ContentAsset(
        source_id=source.id, external_id="pb-1", title="B文", content_hash="h-pb1", content_markdown="# B"
    )
    db_session.add_all([asset_a, asset_b])
    await db_session.flush()

    doc_a = KnowledgeDocument(asset_id=asset_a.id, space_id=space.id, langbot_file_id="file-a")
    doc_b = KnowledgeDocument(asset_id=asset_b.id, space_id=space_b.id, langbot_file_id="file-b")
    db_session.add_all([doc_a, doc_b])
    await db_session.flush()
    await db_session.commit()

    return {
        "space": space.id,
        "space_b": space_b.id,
        "doc": doc_a.id,
        "doc_b": doc_b.id,
        "owner": owner.id,
        "operator": operator.id,
        "admin": admin.id,
        "user": plain.id,
    }


def _app(db_session: Any, actor_id: str | None) -> TestClient:
    app = create_app()
    if actor_id is not None:
        app.dependency_overrides[get_current_user_id] = lambda: actor_id
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def _hit(client: TestClient, method: str, path: str, **kwargs: Any) -> tuple[int, int]:
    resp = getattr(client, method)(path, **kwargs)
    return resp.status_code, resp.json().get("code", -1)


async def test_push_channels_gate_and_read_side(db_session) -> None:  # type: ignore[no-untyped-def]
    """operator+ 门禁；读侧显式回报 implemented=False（就绪度不靠试推撞出来）。"""
    rows = await _seed(db_session)

    assert _hit(_app(db_session, rows["user"]), "get", "/api/v1/admin/push/channels") == (403, 10004)

    resp = _app(db_session, rows["operator"]).get("/api/v1/admin/push/channels")
    assert resp.status_code == 200 and resp.json()["code"] == 0
    channels = resp.json()["data"]["channels"]
    assert [c["channel"] for c in channels] == list(PUSH_CHANNELS)
    for entry in channels:
        assert entry["implemented"] is False and entry["reason"]

    assert _app(db_session, rows["admin"]).get("/api/v1/admin/push/channels").status_code == 200


async def test_push_undelivered_returns_honest_receipt(db_session) -> None:  # type: ignore[no-untyped-def]
    """R7.5.4 口径：校验全过、通道未实接 → 200 + delivered=False + reason（诚实回执，不抛 503）。"""
    rows = await _seed(db_session)
    client = _app(db_session, rows["operator"])

    resp = client.post(
        "/api/v1/admin/push",
        json={"channel": "web", "external_user_id": "wx-1", "space_id": rows["space"], "message": "看新文"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["ok"] is False
    assert body["delivered"] is False
    assert body["channel"] == "web"
    assert WEB_REASON in body["reason"]

    resp = client.post(
        "/api/v1/admin/push",
        json={"channel": "clawbot", "external_user_id": "wx-1", "doc_id": rows["doc"]},
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["delivered"] is False
    assert CLAWBOT_REASON in body["reason"]


async def test_push_validation_errors_stay_10005(db_session) -> None:  # type: ignore[no-untyped-def]
    """请求问题不得被降级成 50002「能力未就绪」——那是给调用方的错误指引。"""
    rows = await _seed(db_session)
    client = _app(db_session, rows["operator"])

    status, code = _hit(
        client,
        "post",
        "/api/v1/admin/push",
        json={"channel": "sms", "external_user_id": "wx-1", "message": "hi"},
    )
    assert (status, code) == (422, 10005)
    status, code = _hit(
        client,
        "post",
        "/api/v1/admin/push",
        json={"channel": "web", "external_user_id": "   ", "message": "hi"},
    )
    assert (status, code) == (422, 10005)
    status, code = _hit(
        client,
        "post",
        "/api/v1/admin/push",
        json={"channel": "web", "external_user_id": "wx-1"},
    )
    assert (status, code) == (422, 10005)
    status, code = _hit(
        client,
        "post",
        "/api/v1/admin/push",
        json={"channel": "web", "external_user_id": "wx-1", "space_id": SPACE_ID_MISSING},
    )
    assert (status, code) == (404, 30004)


async def test_push_requires_login(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    client = _app(db_session, None)
    resp = client.post(
        "/api/v1/admin/push", json={"channel": "web", "external_user_id": "wx-1", "message": "hi"}
    )
    assert resp.status_code == 401 and resp.json()["code"] == 10001


# ------------------------------------------------------------------ ④ 分发层


class _RecordingProvider:
    """会真正投递的 provider：锁 200 回执形状，供真通道落地时做回归网。"""

    name = "web"
    implemented = True

    def __init__(self) -> None:
        self.pushed: list[PushMessage] = []

    async def push(self, message: PushMessage) -> PushResult:
        self.pushed.append(message)
        return PushResult(self.name, True, "")


async def test_dispatch_delivers_and_returns_200(db_session, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    """链路可分发：provider 就位即出 200 回执，目标校验仍先于分发。"""
    rows = await _seed(db_session)
    provider = _RecordingProvider()

    def fake(channel: str) -> Any:
        if channel != "web":
            raise ValueError(f"未知推送通道: {channel}")
        return provider

    monkeypatch.setattr(push_port, "_PROVIDERS", {"web": provider})
    monkeypatch.setattr(push_module, "make_push_provider", fake)
    monkeypatch.setattr(push_port, "PUSH_CHANNELS", ("web",))

    client = _app(db_session, rows["operator"])
    resp = client.post(
        "/api/v1/admin/push",
        json={"channel": "web", "external_user_id": " wx-1 ", "space_id": rows["space"], "message": "  看新文  "},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {"ok": True, "channel": "web", "delivered": True}
    assert len(provider.pushed) == 1
    sent = provider.pushed[0]
    assert sent.external_user_id == "wx-1" and sent.message == "看新文" and sent.space_id == rows["space"]

    # 目标校验仍在分发前：非法目标不得触达 provider
    _hit(client, "post", "/api/v1/admin/push", json={"channel": "web", "external_user_id": "wx-1",
                                                     "space_id": SPACE_ID_MISSING, "message": "x"})
    assert len(provider.pushed) == 1
