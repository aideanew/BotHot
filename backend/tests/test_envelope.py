"""B-T2 验收测试：信封包装、requestId 稳定性与全局异常映射。

覆盖：任意路由异常返回 {code:5xxxx,...} 信封且 requestId 稳定；
AppError 各段位到 HTTP 状态的映射；请求校验与未捕获异常兜底。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import (
    AppError,
    DependencyUnavailableError,
    ExtractQualityLowError,
    JobStateInvalidError,
    SsoStateInvalidError,
    UnauthenticatedError,
    http_status_for,
)
from app.core.middleware import RequestIdMiddleware
from app.core.response import success
from app.main import create_app

REQUEST_ID_HEADER = "X-Request-ID"


def _app_with_raising(exc: Exception) -> FastAPI:
    """构造带异常抛出路由的最小应用（复用生产中间件与异常处理器）。"""
    app = create_app()

    @app.get("/api/v1/system/_boom")
    async def boom() -> object:
        raise exc

    return app


class _Payload(BaseModel):
    name: str


def test_health_envelope_and_request_id_header() -> None:
    """健康检查走信封，且响应头与响应体 requestId 一致。"""
    client = TestClient(create_app())
    resp = client.get("/api/v1/system/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0 and body["message"] == "ok"
    assert body["data"]["status"] in ("ok", "degraded")
    assert "deps" in body["data"]
    assert resp.headers[REQUEST_ID_HEADER] == body["requestId"]


def test_request_id_is_transparently_passed_through() -> None:
    """上游网关注入的 requestId 被沿用（跨服务串联）。"""
    client = TestClient(create_app())
    resp = client.get("/api/v1/system/health", headers={REQUEST_ID_HEADER: "trace-abc-123"})
    assert resp.json()["requestId"] == "trace-abc-123"
    assert resp.headers[REQUEST_ID_HEADER] == "trace-abc-123"


def test_unexpected_exception_returns_5xxxx_envelope() -> None:
    """未捕获异常也必须返回信封，不泄露栈，且 requestId 稳定。"""
    client = TestClient(_app_with_raising(RuntimeError("boom")), raise_server_exceptions=False)
    resp = client.get("/api/v1/system/_boom")
    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == 50001
    assert "boom" not in body["message"]
    assert body["data"] is None
    assert resp.headers[REQUEST_ID_HEADER] == body["requestId"]


@pytest.mark.parametrize(
    ("exc", "expected_code", "expected_status"),
    [
        (UnauthenticatedError("未登录"), 10001, 401),
        (SsoStateInvalidError("state 不符"), 10002, 400),
        (ExtractQualityLowError("质量过低"), 20003, 422),
        (JobStateInvalidError("非法流转"), 30005, 409),
        (DependencyUnavailableError("主平台不可达"), 50002, 503),
    ],
)
def test_app_error_maps_to_http_status(
    exc: AppError, expected_code: int, expected_status: int
) -> None:
    """各段位错误码到 HTTP 状态的映射（登记表中的 15 码语义不变）。"""
    client = TestClient(_app_with_raising(exc), raise_server_exceptions=False)
    resp = client.get("/api/v1/system/_boom")
    assert resp.status_code == expected_status
    assert resp.json()["code"] == expected_code
    assert http_status_for(expected_code) == expected_status


def test_default_app_error_code_is_50001() -> None:
    """未指定 code 的业务异常兜底 50001，消息默认取登记表。"""
    err = AppError()
    assert err.code == 50001
    assert err.message == "INTERNAL_ERROR"


def test_request_invalid_registered_and_defaults_to_registry_name() -> None:
    """10005 REQUEST_INVALID 已入登记表：裸抛时 message 取登记名（非 INTERNAL_ERROR）。"""
    import app.core.errors as errors_mod

    err = errors_mod.RequestInvalidError()
    assert err.code == 10005 and err.http_status == 422
    assert err.message == "REQUEST_INVALID"
    assert errors_mod.ERROR_CODES[10005] == "REQUEST_INVALID"
    assert http_status_for(10005) == 422


def test_30004_single_class_and_readable_bare_id_message() -> None:
    """30004 唯一类定义（JobNotFoundError 残留已清除）+ 裸 id 回填可读前缀。"""
    import app.core.errors as errors_mod

    assert not hasattr(errors_mod, "JobNotFoundError")  # 重复错误类残留清除
    assert errors_mod._CODE_TO_CLASS[30004] is errors_mod.ResourceNotFoundError

    err = errors_mod.ResourceNotFoundError("0f0e9d8c7b6a49388a7b6c5d4e3f2a1b")
    assert err.code == 30004 and err.http_status == 404
    assert err.message == "资源不存在或无权限: 0f0e9d8c7b6a49388a7b6c5d4e3f2a1b"
    # 非裸 id（可读文案）不回填前缀
    plain = errors_mod.ResourceNotFoundError("空间名称已存在")
    assert plain.message == "空间名称已存在"


def test_validation_error_returns_envelope() -> None:
    """请求体校验失败返回信封（422），不抛出 HTML 错误页。"""
    app = create_app()

    @app.post("/api/v1/system/_echo")
    async def echo(payload: _Payload) -> object:
        return success(data=payload.model_dump())

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/api/v1/system/_echo", json={"name": 123})
    assert resp.status_code == 422
    # 裁决 2026-09-07：请求校验失败 → 10005 REQUEST_INVALID（客户端错误，不再兜 50001）
    assert resp.json()["code"] == 10005


def test_http_exception_preserves_status() -> None:
    """业务路由抛出的 HTTPException 保留原状态码并转信封。"""
    app = create_app()

    @app.get("/api/v1/system/_missing")
    async def missing() -> object:
        raise HTTPException(status_code=404, detail="资源不存在")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/v1/system/_missing")
    assert resp.status_code == 404
    body = resp.json()
    # 裁决 2026-09-07：框架级 HTTPException(<500) → 10005，状态码透传
    assert body["code"] == 10005
    assert body["message"] == "资源不存在"
    assert resp.headers[REQUEST_ID_HEADER] == body["requestId"]


def test_request_id_context_isolated_between_requests() -> None:
    """并发/连续请求间 requestId 互不串扰。"""
    client = TestClient(create_app())
    first = client.get("/api/v1/system/health").json()["requestId"]
    second = client.get("/api/v1/system/health").json()["requestId"]
    assert first != second


def test_middleware_ignores_non_http_scope() -> None:
    """非 HTTP 作用域（如 lifespan）直接透传，不注入 requestId。"""
    calls: list[str] = []

    async def dummy_app(scope: dict, receive: object, send: object) -> None:
        calls.append(scope["type"])

    middleware = RequestIdMiddleware(dummy_app)  # type: ignore[arg-type]
    import asyncio

    asyncio.run(middleware({"type": "lifespan"}, None, None))  # type: ignore[arg-type]
    assert calls == ["lifespan"]


# ------------------------------------------------------------------ T1.5.2（G3）：405/404 信封收口


def test_unmatched_route_returns_404_envelope() -> None:
    """T1.5.2：未注册路径 → 404 但响应体必须是 {code,message,data,requestId} 信封，
    不得是 FastAPI 默认 {"detail": "Not Found"}（台账挂起项 3③a 家族收口）。"""
    client = TestClient(create_app())
    resp = client.get("/api/v1/definitely-not-a-route")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == 10005 and "detail" not in body
    assert body["requestId"] == resp.headers[REQUEST_ID_HEADER]


def test_wrong_method_returns_405_envelope() -> None:
    """T1.5.2：路径命中但动词未注册（PATCH 一个 GET-only 路由）→ 405 + 信封。"""
    client = TestClient(create_app())
    resp = client.patch("/api/v1/system/health", json={})
    assert resp.status_code == 405
    body = resp.json()
    assert body["code"] == 10005 and "detail" not in body
    assert body["requestId"] == resp.headers[REQUEST_ID_HEADER]
