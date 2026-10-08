"""健康检查契约测试（M0 CI 基线）。"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.v1.system import _check_langbot
from app.main import app


def test_health_envelope() -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/system/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["data"]["status"] in ("ok", "degraded")
    assert "deps" in body["data"]
    assert "requestId" in body


class _FakeResp:
    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> object:
        return json.loads(self._body)


class _FakeAsyncClient:
    """替代 httpx.AsyncClient：固定返回预设状态码/响应体，实现 async 上下文协议。"""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self._body = body

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get(self, url: str) -> _FakeResp:
        return _FakeResp(self.status_code, self._body)


@pytest.mark.parametrize(
    ("status_code", "body", "expected"),
    [
        # 未登录但路由在应答（LangBot 的错误信封）= 活
        (401, '{"code":-1,"msg":"No valid authentication provided"}', "ok"),
        # 200 + HTML = SPA catch-all 兜底，API 可能根本没挂上——不得判成健康
        (200, "<!doctype html><html><title>LangBot</title></html>", "unhealthy"),
        # 401 但不是 LangBot 信封（可能是中间层/代理的拦截页）
        (401, "<html>401 Unauthorized</html>", "unhealthy"),
        # 路径不存在时 LangBot 落 SPA 兜底
        (404, "{}", "unhealthy"),
    ],
)
async def test_check_langbot_probes_api_route_not_spa_fallback(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    body: str,
    expected: str,
) -> None:
    """实测缺陷：旧实现探测 LangBot 不存在的 `/api/health`，恒返 unhealthy，
    平台健康度永久 degraded——真故障与常态无法区分。探针必须落到真实 API 路由。"""
    # 传**工厂**而非实例：被测代码以 `httpx.AsyncClient(timeout=3)` 的方式调用
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **k: _FakeAsyncClient(status_code, body),
    )
    assert await _check_langbot() == expected


async def test_check_langbot_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args: object, **_kwargs: object) -> _FakeAsyncClient:
        raise OSError("connection refused")

    monkeypatch.setattr(httpx, "AsyncClient", _boom)
    assert await _check_langbot() == "unreachable"
