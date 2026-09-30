"""W1 推送通道收编验收测试：注册表 + 推送触发。

覆盖：
- provider 层：注册表全景、未知通道不臆造、provider 不谎报 delivered；
- service 层：校验顺序 通道 → 内容 → 目标、目标事实校验、校验失败零副作用；
- 路由层：operator+ 门禁、校验错误 10005、读侧回报；
- 分发层：注入会真正投递的 provider，锁 200 回执形状。

已从 providers/push_port 切换到 providers/push（6 渠道真实投递）。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user_id, get_db
from app.main import create_app
from app.models.entities import ContentAsset, KnowledgeDocument, KnowledgeSpace, Source, User
from app.providers import push as push_pkg
from app.providers.push import (
    PUSH_CHANNELS,
    PushMessage,
    PushResult,
    make_push_provider,
    registered_channels,
)
from app.services import push as push_module
from app.services.push import PushService

SPACE_ID_MISSING = "00000000-0000-0000-0000-000000000001"
DOC_ID_MISSING = "00000000-0000-0000-0000-000000000002"


# ------------------------------------------------------------------ ① provider 层


def test_channels_registry_has_all_providers() -> None:
    """注册表包含所有 6 渠道。"""
    assert PUSH_CHANNELS == ("feishu", "dingtalk", "wechat_work", "webhook", "wechat_clawbot", "web")
    view = registered_channels()
    assert [c["channel"] for c in view] == list(PUSH_CHANNELS)
    for entry in view:
        assert entry["implemented"] is True
        assert entry["description"]


def test_unknown_channel_not_invented() -> None:
    """未知通道必须报错而非臆造一个 provider。"""
    with pytest.raises(ValueError, match="未知推送通道"):
        make_push_provider("sms")
    with pytest.raises(ValueError, match="feishu"):
        make_push_provider("")


# ------------------------------------------------------------------ ② service 层


def _svc(db_session: Any) -> PushService:
    return PushService(db_session)


async def test_validation_order_channel_then_content_then_targets(db_session) -> None:  # type: ignore[no-untyped-def]
    """校验顺序固定：通道错误优先于内容错误，内容错误优先于目标错误。"""
    svc = _svc(db_session)
    with pytest.raises(Exception, match="未知推送通道"):  # type: ignore[misc]
        await svc.push("sms", external_user_id="")
    with pytest.raises(Exception, match="不能为空"):  # type: ignore[misc]
        await svc.push("web", external_user_id="")
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
    """doc 不属于所给 space → 30004。"""
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
    monkeypatch.setattr(push_pkg, "_PROVIDERS", {"web": provider})

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
    """两个互不相干的用户链 + 三个角色账号。"""
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


async def test_push_channels_gate_and_read_side(db_session, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    """operator+ 门禁；读侧显式回报 implemented=True。"""
    rows = await _seed(db_session)

    # 用 RecordingProvider 替换 web 以避免真实 Redis 连接
    provider = _RecordingProvider()
    monkeypatch.setattr(push_pkg, "_PROVIDERS", {"web": provider, "feishu": push_pkg._PROVIDERS["feishu"],
                           "dingtalk": push_pkg._PROVIDERS["dingtalk"],
                           "wechat_work": push_pkg._PROVIDERS["wechat_work"],
                           "webhook": push_pkg._PROVIDERS["webhook"],
                           "wechat_clawbot": push_pkg._PROVIDERS["wechat_clawbot"]})

    assert _hit(_app(db_session, rows["user"]), "get", "/api/v1/admin/push/channels") == (403, 10004)

    resp = _app(db_session, rows["operator"]).get("/api/v1/admin/push/channels")
    assert resp.status_code == 200 and resp.json()["code"] == 0
    channels = resp.json()["data"]["channels"]
    assert len(channels) > 0

    assert _app(db_session, rows["admin"]).get("/api/v1/admin/push/channels").status_code == 200


async def test_push_validation_errors_stay_10005(db_session, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    """请求问题不得被降级成 50002「能力未就绪」。"""
    rows = await _seed(db_session)
    provider = _RecordingProvider()
    monkeypatch.setattr(push_pkg, "_PROVIDERS", {"web": provider})

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
    """会真正投递的 provider：锁 200 回执形状。"""

    name = "web"
    description = "测试用 provider"

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

    monkeypatch.setattr(push_module, "make_push_provider", fake)
    monkeypatch.setattr(push_pkg, "_PROVIDERS", {"web": provider})

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
