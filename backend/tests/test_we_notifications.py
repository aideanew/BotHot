"""WE 5.3 后端验收：站内通知 SSE（/api/v1/system/notifications）。

- 鉴权（确定性，零外部依赖）：未登录 → 401/10001（_require_session 无 cookie 即时抛，
  不触 DB/Redis）；/health 保持匿名 200（compose healthcheck 不回归）；
- 降级（假订阅者，零 Redis）：Redis 不可达 / 未配置 → service_unavailable 控制帧，
  不 500、不裸抛；
- 转发（假订阅者直接驱动生成器）：connected 起手帧 → 消息原样转发 data 帧 →
  aclose 触发 finally 清理（退订/close）；
- 真实轮（连 Redis 标记）：publish → 生成器实时收到转发帧；不可达贴 skip。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections import deque
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import system as system_module
from app.main import create_app
from app.providers.push.web import _CHANNEL_PREFIX


class _FakeSubscriber:
    """假订阅者：按队列回放消息，队列空后恒返 None（即空闲 → 调用方只见 ping）。"""

    def __init__(self, messages: list[dict[str, Any]] | None = None) -> None:
        self._messages: deque[dict[str, Any]] = deque(messages or [])
        self.closed = False

    async def get_message(self, timeout: float) -> dict | None:  # noqa: ARG002
        if self._messages:
            return self._messages.popleft()
        return None

    async def close(self) -> None:
        self.closed = True


def _stub_request() -> Any:
    """Request 桩：is_disconnected 恒 False（用例手动驱动有限帧后 aclose，不死循环）。"""

    async def _never() -> bool:
        return False

    return SimpleNamespace(is_disconnected=_never)


def _data_frames(items: list[str]) -> list[dict[str, Any]]:
    """SSE 文本片段列表 → data 帧 JSON 列表（注释帧 ": xxx" 丢弃）。"""
    frames = []
    for block in items:
        if block.startswith("data: "):
            frames.append(json.loads(block[len("data: ") :]))
    return frames


# ------------------------------------------------------------------ 鉴权（确定性）


def test_notifications_unauthenticated_401() -> None:
    """WE 验收1：未登录访问 SSE 端点 → 401 + 10001 信封（不建流）。"""
    client = TestClient(create_app())
    resp = client.get("/api/v1/system/notifications")
    assert resp.status_code == 401
    assert resp.json()["code"] == 10001


def test_health_remains_anonymous() -> None:
    """WE 验收2：/health 仍匿名可达（门禁加端点级非 router 级，healthcheck 不回归）。"""
    client = TestClient(create_app())
    resp = client.get("/api/v1/system/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["status"] in ("ok", "degraded")  # 依赖宕机也只降级不 5xx
    assert "deps" in body["data"]


# ------------------------------------------------------------------ 转发 / 清理（假订阅者）


async def test_stream_forwards_messages_and_cleans_up(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """5.1 核心：connected 起手 → web provider 载荷原样转发 → aclose 触发 finally 清理。"""
    payload = {"title": "空间更新", "message": "新文档已入库", "url": "/spaces/x", "space_id": "s1", "doc_id": "d1"}
    fake = _FakeSubscriber([{"type": "message", "data": json.dumps(payload, ensure_ascii=False)}])
    opened_channels: list[list[str]] = []

    async def _fake_open(redis_url: str, channels: list[str]) -> _FakeSubscriber:
        opened_channels.append(channels)
        return fake

    monkeypatch.setattr(system_module, "_open_subscriber", _fake_open)
    gen = system_module._notification_stream(_stub_request(), "sub-42")

    first = await gen.__anext__()
    assert first == ": connected\n\n", "起手应有一帧注释令 EventSource 进入 open 态"
    # 频道口径：定向 {prefix}:{sub} + 广播兜底（web provider 无 external_user_id 时落此）
    assert opened_channels[0] == [f"{_CHANNEL_PREFIX}:sub-42", f"{_CHANNEL_PREFIX}:broadcast"]

    second = await gen.__anext__()
    assert _data_frames([second]) == [payload], "消息应原样转发（不改写载荷）"

    await gen.aclose()  # GeneratorExit 注入 yield 点 → finally 清理路径
    assert fake.closed, "断流后未退订/关闭订阅者（悬挂连接泄漏）"


async def test_stream_idle_emits_ping_comment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """空闲（get_message 超时返 None）→ 心跳注释帧 ": ping"，防代理超时断连。"""
    fake = _FakeSubscriber([])

    async def _fake_open(redis_url: str, channels: list[str]) -> _FakeSubscriber:
        return fake

    assert system_module.NOTIFICATION_PING_SECONDS == 25.0, "心跳口径 25s（任务书：每 25s 一条 : ping）"
    monkeypatch.setattr(system_module, "_open_subscriber", _fake_open)
    gen = system_module._notification_stream(_stub_request(), "sub-1")
    await gen.__anext__()  # connected
    msg = await gen.__anext__()
    assert msg == ": ping\n\n", "空闲应发注释心跳帧（EventSource 自动忽略，不触发 onmessage）"
    await gen.aclose()


async def test_stream_bytes_payload_decoded(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """redis 返回 bytes 载荷 → UTF-8 解码后转发，中文不乱码。"""
    payload = {"title": "热点日报", "message": "今日 42 条"}
    fake = _FakeSubscriber([{"type": "message", "data": json.dumps(payload, ensure_ascii=False).encode("utf-8")}])

    async def _fake_open(redis_url: str, channels: list[str]) -> _FakeSubscriber:
        return fake

    monkeypatch.setattr(system_module, "_open_subscriber", _fake_open)
    gen = system_module._notification_stream(_stub_request(), "sub-1")
    await gen.__anext__()  # connected
    frame = await gen.__anext__()
    assert _data_frames([frame]) == [payload]
    await gen.aclose()


async def test_redis_subscriber_close_swallows_errors() -> None:
    """生产清理面 _RedisSubscriber.close：pubsub/client 各自抛错均被抑制，不裸抛。

    生成器 finally 依赖该抑制契约——连接已死时的退订失败绝不能升级成断流异常。
    """

    class _Boom:
        async def aclose(self) -> None:
            raise RuntimeError("conn already gone")

        async def get_message(self, **_kw: Any) -> None:
            return None

    subscriber = system_module._RedisSubscriber(_Boom(), _Boom())
    await subscriber.close()  # 不抛即通过


async def test_stream_cleanup_runs_on_disconnect(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """request.is_disconnected 转 True → 循环 break → finally 清理（客户端断连路径）。"""
    flags = iter([False, False, True])

    async def _eventually() -> bool:
        return next(flags)

    fake = _FakeSubscriber([])

    async def _fake_open(redis_url: str, channels: list[str]) -> _FakeSubscriber:
        return fake

    monkeypatch.setattr(system_module, "_open_subscriber", _fake_open)
    req = SimpleNamespace(is_disconnected=_eventually)
    frames = [item async for item in system_module._notification_stream(req, "sub-1")]
    assert frames == [": connected\n\n", ": ping\n\n", ": ping\n\n"]
    assert fake.closed, "断连收敛后未清理订阅者"


# ------------------------------------------------------------------ 优雅降级（零 Redis）


async def test_stream_degrades_when_redis_unreachable(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """订阅建立失败（Redis 不可达）→ 单帧 service_unavailable 后正常收尾，不裸抛。"""

    async def _fail_open(redis_url: str, channels: list[str]) -> Any:
        raise ConnectionRefusedError("Connection refused")

    monkeypatch.setattr(system_module, "_open_subscriber", _fail_open)
    frames = [item async for item in system_module._notification_stream(_stub_request(), "sub-1")]
    assert len(frames) == 1
    control = _data_frames(frames)[0]
    assert control["type"] == "service_unavailable"
    assert isinstance(control.get("message"), str) and control["message"]


async def test_stream_degrades_when_redis_unconfigured(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """redis_url 未配置 → 同口径控制帧（不尝试连接、不 500）。"""
    monkeypatch.setattr(system_module, "get_settings", lambda: SimpleNamespace(redis_url=""))
    frames = [item async for item in system_module._notification_stream(_stub_request(), "sub-1")]
    assert len(frames) == 1
    assert _data_frames(frames)[0]["type"] == "service_unavailable"


def test_endpoint_unavailable_envelope_via_testclient() -> None:
    """端点级降级冒烟：override 登录依赖 + 注入必败订阅 → 200 SSE 体含控制帧（非 500）。"""
    from app.api.deps import get_current_sub

    async def _fail_open(redis_url: str, channels: list[str]) -> Any:
        raise ConnectionRefusedError("Connection refused")

    original = system_module._open_subscriber
    system_module._open_subscriber = _fail_open
    try:
        app = create_app()
        app.dependency_overrides[get_current_sub] = lambda: "sub-degrade"
        client = TestClient(app)
        resp = client.get("/api/v1/system/notifications")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers.get("x-accel-buffering") == "no"
        control = _data_frames([resp.text])[0]
        assert control["type"] == "service_unavailable"
    finally:
        system_module._open_subscriber = original


# ------------------------------------------------------------------ 真实轮（连 Redis）


async def test_notifications_real_redis_forwarding() -> None:
    """真实 Redis pub/sub 端到端：publish → _notification_stream 实时转发。

    前置：settings.redis_url 可达（compose 宿主侧 6380）。不可达 → skip。
    """
    import uuid

    import redis.asyncio as aioredis

    from app.core.config import get_settings

    settings = get_settings()
    probe = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
    try:
        await probe.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Redis 不可达（{settings.redis_url}，{type(exc).__name__}），恢复后复跑本用例")
    finally:
        with contextlib.suppress(Exception):
            await probe.aclose()

    sub = f"we-real-{uuid.uuid4().hex[:8]}"  # 定向频道后缀；订阅频道 = prefix:sub
    payload = {"title": "真实轮", "message": "pub/sub 闭环"}
    pub = aioredis.from_url(settings.redis_url)
    gen = system_module._notification_stream(_stub_request(), sub)
    try:
        assert await gen.__anext__() == ": connected\n\n"  # 默认注入点=真实订阅者，订阅已建立
        await asyncio.sleep(0.3)  # 给订阅注册一次网络往返窗口，避免 publish 早于 SUBSCRIBE 生效
        await pub.publish(f"{_CHANNEL_PREFIX}:{sub}", json.dumps(payload, ensure_ascii=False))
        # 订阅后首个 get_message 可能先返 None（ping），循环越过注释/心跳帧直至拿到 data 帧；
        # 外层预算 30s > 生成器 25s 心跳，避免 wait_for 取消挂起中的生成器造成状态损坏
        frame = ""
        for _ in range(5):
            item = await asyncio.wait_for(gen.__anext__(), timeout=30)
            if item.startswith("data: "):
                frame = item
                break
        assert _data_frames([frame]) == [payload], "真实 publish 应实时转发到流"
    finally:
        with contextlib.suppress(Exception):
            await gen.aclose()
        with contextlib.suppress(Exception):
            await pub.aclose()
