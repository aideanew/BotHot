"""W7 入站安全与上游治理验收测试。

覆盖五组性质（对应作业单 B.1–B.5）：

- **B.1 限流**：命中 429 且是统一信封 + requestId（响应头与响应体一致）；
  IP 与会话双维各自计数；敏感路径走独立配额；Redis 不可用 **fail-open**；
  探活/指标/文档路径豁免。
- **B.2 请求体上限**：`Content-Length` 预检与流式截断两条路径都 413。
- **B.3 上游治理**：并发闸被真正包住 HTTP 调用（不只看符号存在）；
  同一事件循环内同名信号量共享；超时拆 connect/read。
- **B.4 安全头**：四个头齐备；**短路响应（429/413）也带头**；HSTS 仅 https；
  **不得出现 CORS 头**。
- **B.5 守卫白名单化**：`prod-eu` / `staging` / `PRD` 一类非标准命名被拦截（负例）；
  既有开发环境名仍放行。

另有 **装配契约**测试：`install_security_middlewares` 可独立 import、
安装期零 Redis 副作用、且与既有 `RequestIdMiddleware` 的相对顺序正确
（短路响应自行解析 requestId 正是因为它在 RequestId 之外层）。
"""

from __future__ import annotations

import asyncio
import importlib
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core import security as sec
from app.core.config import NON_PRODUCTION_ENVS, Settings, get_settings
from app.core.errors import (
    ERROR_CODES,
    PayloadTooLargeError,
    RateLimitedError,
    http_status_for,
)
from app.core.response import success
from app.main import create_app
from app.providers.push.base import PushMessage
from app.providers.push.web import WebPushProvider

REQUEST_ID_HEADER = "X-Request-ID"

# 探活/限流共用路径（勿用于限流断言：该路径豁免计数）
HEALTH_PATH = "/api/v1/system/health"
# 非豁免业务路径（限流规则 "chat"）——不要求存在路由，短路发生在路由之前
CHAT_PATH = "/api/v1/chat"


# ═══════════════════════════════════════════════════════ 夹具与替身


class _ScriptedCounter:
    """按固定值返回计数的假计数器，并记录全部 (key, window)。"""

    def __init__(self, value: int | None) -> None:
        self.value = value
        self.calls: list[tuple[str, int]] = []

    async def incr_window(self, key: str, window_seconds: int) -> int | None:
        self.calls.append((key, window_seconds))
        return self.value


@pytest.fixture(autouse=True)
def _reset_security_state() -> Any:
    """每个用例后恢复默认计数器并清共享 Redis，防跨用例串扰。"""
    yield
    sec.set_rate_limit_counter(None)
    sec.reset_shared_redis()


_APP: FastAPI | None = None


def _secured_app() -> FastAPI:
    """真实 `create_app()` + 生产装配顺序（W6 的 main.py 将做同一调用）。

    模块级缓存：`create_app()` 内含 schema 一致性探测（会尝试连 PG），
    不必每个用例重付一次代价。
    """
    global _APP
    if _APP is None:
        app = create_app()
        sec.install_security_middlewares(app)

        @app.post("/api/v1/system/_w7_echo")
        async def _w7_echo(request: Request) -> object:  # pragma: no cover - 仅测试用
            raw = await request.body()
            return success(data={"len": len(raw)})

        _APP = app
    return _APP


def _client(base_url: str = "http://testserver") -> TestClient:
    """不跟随重定向：限流断言针对**单个请求路径**，重定向目标会引入第二条规则。

    例：`/api/v1/auth/login` 会 302 到 SSO，若跟随则 `global` 规则也被计数，
    规则断言变成「测了个复合路径」。
    """
    return TestClient(
        _secured_app(),
        base_url=base_url,
        raise_server_exceptions=False,
        follow_redirects=False,
    )


# ═══════════════════════════════════════════════════════ 装配契约


def test_error_codes_registered_and_mapped() -> None:
    """10007/10008 已登记且 HTTP 映射正确（单一来源 = errors.py 的异常类）。"""
    assert ERROR_CODES[10007] == "RATE_LIMITED"
    assert ERROR_CODES[10008] == "PAYLOAD_TOO_LARGE"
    assert RateLimitedError.http_status == 429
    assert PayloadTooLargeError.http_status == 413
    assert http_status_for(10007) == 429
    assert http_status_for(10008) == 413
    assert sec.RATE_LIMITED_CODE == 10007
    assert sec.PAYLOAD_TOO_LARGE_CODE == 10008


def test_install_is_exported_and_import_safe() -> None:
    """冻结接口存在；空 URL 不建客户端；模块可独立 import（无 Redis 环境）。"""
    sec.reset_shared_redis()
    assert callable(sec.install_security_middlewares)
    assert sec.get_shared_redis("") is None
    # import 期若有副作用（建连/建客户端），`_redis_clients` 必非空
    assert sec._redis_clients == {}


def test_install_middlewares_creates_no_redis_client() -> None:
    """装配本身零副作用：只读 env，不连 Redis（`from_url` 惰性）。"""
    sec.reset_shared_redis()
    app = create_app()
    sec.install_security_middlewares(app)
    assert sec._redis_clients == {}


def test_fail_open_counter_default_is_redis_backed() -> None:
    """默认计数器是 Redis 固定窗口实现（非静默 no-op）。"""
    assert isinstance(sec.get_rate_limit_counter(), sec.RedisFixedWindowCounter)


# ═══════════════════════════════════════════════════════ B.1 限流


def test_rate_limit_hits_429_envelope_with_request_id() -> None:
    """超限 → 429 + 统一信封 + 响应头/体 requestId 一致 + Retry-After。"""
    sec.set_rate_limit_counter(_ScriptedCounter(10_000))
    resp = _client().get(CHAT_PATH)

    assert resp.status_code == 429
    body = resp.json()
    assert body["code"] == 10007
    assert body["message"]
    assert body["requestId"] == resp.headers[REQUEST_ID_HEADER]
    assert resp.headers["Retry-After"].isdigit()


def test_rate_limit_preserves_upstream_request_id() -> None:
    """短路响应沿用上游网关注入的 requestId（与 RequestIdMiddleware 同口径）。"""
    sec.set_rate_limit_counter(_ScriptedCounter(10_000))
    resp = _client().get(CHAT_PATH, headers={REQUEST_ID_HEADER: "trace-w7-429"})

    assert resp.status_code == 429
    assert resp.json()["requestId"] == "trace-w7-429"
    assert resp.headers[REQUEST_ID_HEADER] == "trace-w7-429"


def test_rate_limit_generates_request_id_when_absent() -> None:
    """无上游头时自行生成，且响应头与响应体同值（不得各生成一个）。"""
    sec.set_rate_limit_counter(_ScriptedCounter(10_000))
    resp = _client().get(CHAT_PATH)

    header_id = resp.headers[REQUEST_ID_HEADER]
    assert header_id and len(header_id) >= 32  # uuid4
    assert resp.json()["requestId"] == header_id


def test_rate_limit_fails_open_when_counter_unavailable() -> None:
    """Redis 不可用（计数器返回 None）→ 放行，绝不把限流变成全站 429。"""
    sec.set_rate_limit_counter(_ScriptedCounter(None))
    resp = _client().get(CHAT_PATH)
    assert resp.status_code != 429


def test_rate_limit_skips_exempt_paths() -> None:
    """探活路径豁免计数；业务路径计数（两者共享同一计数器替身）。"""
    counter = _ScriptedCounter(1)
    sec.set_rate_limit_counter(counter)
    client = _client()

    client.get(HEALTH_PATH)
    assert counter.calls == [], "探活路径不应被计数（编排高频轮询会误伤）"

    client.get(CHAT_PATH)
    assert counter.calls, "业务路径必须计数"


def test_rate_limit_counts_ip_and_session_dimensions() -> None:
    """双维：带会话 cookie 时同时按 ip 与 id 计数。"""
    counter = _ScriptedCounter(1)
    sec.set_rate_limit_counter(counter)
    cookie_name = get_settings().session_cookie_name

    client = _client()
    client.cookies.set(cookie_name, "sess-w7")  # 直接设在客户端上（httpx 推荐用法）
    client.get(CHAT_PATH)

    dimensions = {key.split(":")[3] for key, _ in counter.calls}
    assert dimensions == {"ip", "id"}
    assert any("sess-w7" in key for key, _ in counter.calls)


def test_rate_limit_ip_only_without_session() -> None:
    """未登录请求只有 ip 维（不能因为缺 cookie 就不计数）。"""
    counter = _ScriptedCounter(1)
    sec.set_rate_limit_counter(counter)

    _client().get(CHAT_PATH)

    dimensions = {key.split(":")[3] for key, _ in counter.calls}
    assert dimensions == {"ip"}


@pytest.mark.parametrize(
    ("path", "rule"),
    [
        ("/api/v1/auth/login", "auth"),
        ("/api/v1/chat", "chat"),
        ("/api/v1/extract", "extract"),
        ("/api/v1/hot/topics/cluster", "hot_cluster"),
        ("/api/v1/bots/tasks/task-1/run", "push_task_run"),
        ("/api/v1/spaces", "global"),
    ],
)
def test_sensitive_paths_use_dedicated_quota_rules(path: str, rule: str) -> None:
    """敏感路径各自成规则（配额可独立收紧），其余落 global。"""
    counter = _ScriptedCounter(1)
    sec.set_rate_limit_counter(counter)

    _client().get(path)

    rules = {key.split(":")[2] for key, _ in counter.calls}
    assert rules == {rule}


def test_rate_limit_window_bucket_is_configured_window() -> None:
    """窗口秒数来自 settings（单一来源），而非散落常量。"""
    counter = _ScriptedCounter(1)
    sec.set_rate_limit_counter(counter)

    _client().get(CHAT_PATH)

    assert {window for _, window in counter.calls} == {
        get_settings().rate_limit_window_seconds
    }


# ═══════════════════════════════════════════════════════ B.2 请求体上限


def test_body_limit_413_by_content_length() -> None:
    """Content-Length 预检：超限直接 413，不进业务路由。"""
    sec.set_rate_limit_counter(_ScriptedCounter(1))
    limit = get_settings().max_request_body_bytes
    resp = _client().post(
        "/api/v1/system/_w7_echo", content=b"x" * (limit + 1024)
    )

    assert resp.status_code == 413
    body = resp.json()
    assert body["code"] == 10008
    assert body["requestId"] == resp.headers[REQUEST_ID_HEADER]


def test_body_limit_allows_body_under_limit() -> None:
    """限额内的请求体照常送达路由（不得误伤正常写请求）。"""
    sec.set_rate_limit_counter(_ScriptedCounter(1))
    resp = _client().post("/api/v1/system/_w7_echo", content=b"y" * 1024)

    assert resp.status_code == 200
    assert resp.json()["data"]["len"] == 1024


def test_body_limit_413_by_streaming_without_content_length() -> None:
    """无 Content-Length（分块/伪造长度）→ 有界缓冲兜底 413。

    直接驱动 ASGI 栈：httpx 客户端在此路径上会自行补长度头，测不到流式分支。
    """
    limit = 1024
    stack = sec.BodyLimitMiddleware(_noop_app, max_bytes=limit)
    messages: list[dict[str, Any]] = [
        {"type": "http.request", "body": b"a" * 800, "more_body": True},
        {"type": "http.request", "body": b"b" * 800, "more_body": False},
    ]
    sent = asyncio.run(_drive(stack, messages))

    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413


def test_body_limit_is_transparent_for_body_methods_under_limit() -> None:
    """限额内流式请求体完整重放给下游（不丢字节、不改 more_body 语义）。"""
    stack = sec.BodyLimitMiddleware(_noop_app, max_bytes=4096)
    messages: list[dict[str, Any]] = [
        {"type": "http.request", "body": b"a" * 100, "more_body": True},
        {"type": "http.request", "body": b"b" * 100, "more_body": False},
    ]
    sent = asyncio.run(_drive(stack, messages))

    assert sent[0]["status"] == 200


def test_body_limit_ignores_get() -> None:
    """GET/HEAD 无请求体，不进缓冲路径（省一次读取）。"""
    stack = sec.BodyLimitMiddleware(_noop_app, max_bytes=1)
    sent = asyncio.run(
        _drive(stack, [], method="GET", headers=[])
    )
    assert sent[0]["status"] == 200


# ═══════════════════════════════════════════════════════ B.4 安全头


def test_security_headers_present_on_normal_response() -> None:
    """四个安全头齐备；CSP 为 Report-Only（先观测后强制）。"""
    resp = _client().get(HEALTH_PATH)

    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in resp.headers["Content-Security-Policy-Report-Only"]


def test_no_cors_headers_ever() -> None:
    """**不得**出现 CORS 头：前端经 rewrites 同源代理，加 CORS 只扩大攻击面。"""
    resp = _client().get(HEALTH_PATH)
    assert "access-control-allow-origin" not in resp.headers
    assert "access-control-allow-credentials" not in resp.headers


def test_security_headers_present_on_short_circuit_responses() -> None:
    """429 短路响应也带安全头（SecurityHeaders 必须是最外层）。"""
    sec.set_rate_limit_counter(_ScriptedCounter(10_000))
    limited = _client().get(CHAT_PATH)

    assert limited.status_code == 429
    assert limited.headers["X-Content-Type-Options"] == "nosniff"
    assert limited.headers["X-Frame-Options"] == "DENY"


def test_security_headers_present_on_413() -> None:
    sec.set_rate_limit_counter(_ScriptedCounter(1))
    limit = get_settings().max_request_body_bytes
    resp = _client().post("/api/v1/system/_w7_echo", content=b"z" * (limit + 1))

    assert resp.status_code == 413
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_hsts_only_under_https() -> None:
    """明文请求不下发 HSTS；https（含 X-Forwarded-Proto）才下发。"""
    plain = _client().get(HEALTH_PATH)
    assert "Strict-Transport-Security" not in plain.headers

    secure = _client(base_url="https://testserver").get(HEALTH_PATH)
    assert "max-age=31536000" in secure.headers["Strict-Transport-Security"]


def test_hsts_honours_forwarded_proto() -> None:
    """反代终止 TLS 时（http 直连 + X-Forwarded-Proto: https）也下发 HSTS。"""
    resp = _client().get(HEALTH_PATH, headers={"X-Forwarded-Proto": "https"})
    assert "Strict-Transport-Security" in resp.headers


# ═══════════════════════════════════════════════════════ B.5 守卫白名单化


@pytest.mark.parametrize(
    "app_env",
    ["production", "PRODUCTION", " Production ", "prod", "prd", "prod-eu", "staging", "live"],
)
def test_production_guard_blocks_non_whitelisted_env_names(app_env: str) -> None:
    """负例（本项验收核心）：任何**不在**白名单里的 env 名一律按生产守卫。

    原实现 `!= "production"` 精确匹配时，`prod-eu` 可整体绕过红线。
    """
    settings = Settings(_env_file=None, app_env=app_env)  # type: ignore[call-arg]
    assert settings.production_guard_violations(), f"app_env={app_env!r} 未被守卫拦截"


@pytest.mark.parametrize("app_env", sorted(NON_PRODUCTION_ENVS))
def test_production_guard_whitelists_known_dev_envs(app_env: str) -> None:
    """白名单内的开发/测试环境仍放行（不得把本地开发卡死）。"""
    settings = Settings(_env_file=None, app_env=app_env)  # type: ignore[call-arg]
    assert settings.production_guard_violations() == []


def test_production_guard_still_reports_all_seven_items() -> None:
    """守卫条目数不变（白名单化只改闸门，不改判据集合）——防顺手削项。"""
    settings = Settings(_env_file=None, app_env="prod-eu")  # type: ignore[call-arg]
    violations = settings.production_guard_violations()
    assert len(violations) == 7
    for token in (
        "OIDC_CLIENT_SECRET",
        "SESSION_COOKIE_SECURE",
        "SESSION_STORE_BACKEND",
        "OIDC_ISSUER_EXPECTED",
        "OIDC_AUDIENCE_EXPECTED",
        "PUSH_SECRET_MASTER_KEY",
        "ENGINE_KEY_MASTER_KEY",
    ):
        assert any(token in item for item in violations), token


# ═══════════════════════════════════════════════════════ B.3 上游治理


async def test_upstream_semaphore_shared_within_event_loop() -> None:
    """同一循环内同名信号量复用（跨请求真限流），不同名互不影响。"""
    first = sec.upstream_semaphore("w7-probe")
    second = sec.upstream_semaphore("w7-probe")
    other = sec.upstream_semaphore("w7-probe-other")

    assert first is second
    assert first is not other


def test_upstream_concurrency_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """逐 provider 并发上限可经 `UPSTREAM_CONCURRENCY_<NAME>` 覆盖。"""
    monkeypatch.setenv("UPSTREAM_CONCURRENCY_W7PROBE", "2")
    assert sec.upstream_concurrency("w7probe") == 2

    monkeypatch.delenv("UPSTREAM_CONCURRENCY_W7PROBE")
    assert sec.upstream_concurrency("w7probe") == get_settings().upstream_concurrency_default


def test_upstream_timeout_splits_connect_and_read() -> None:
    """超时拆分：connect 短（快速失败）、read 取 provider 既有默认。"""
    timeout = sec.upstream_timeout(20.0)

    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read == 20.0
    assert timeout.connect == get_settings().upstream_connect_timeout_seconds


async def test_redfox_http_call_is_wrapped_by_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """行为证明（非符号存在）：`query_work_list` 的 HTTP 调用确实经过并发闸。"""
    from app.providers.redfox import client as redfox_mod

    entered: list[int] = []

    class _SpyGate:
        async def __aenter__(self) -> None:
            entered.append(1)

        async def __aexit__(self, *exc: object) -> bool:
            return False

    monkeypatch.setattr(redfox_mod, "upstream_semaphore", lambda name: _SpyGate())

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"code": 2000, "data": {"list": [], "total": 0}})
    )
    http = httpx.AsyncClient(transport=transport)
    client = redfox_mod.RedfoxClient("https://example.invalid", "key", http=http)
    rows, total = await client.query_work_list("biz", 1)
    await http.aclose()

    assert (rows, total) == ([], 0)  # 语义未被并发闸改变
    assert entered == [1]  # 闸确实被持有


def test_all_upstream_clients_declare_gate_name() -> None:
    """五个上游客户端都声明了并发闸名（漏一个即留一个不受控出口）。"""
    cases = [
        ("app.providers.redfox.client", "RedfoxClient"),
        ("app.providers.article_sources.dajiala", "DajialaClient"),
        ("app.providers.article_sources.justoneapi", "JustOneApiClient"),
        ("app.providers.article_sources.tikhub", "TikhubClient"),
        ("app.providers.article_sources.wellbyte", "WellbyteClient"),
    ]
    names = set()
    for module_name, class_name in cases:
        module = importlib.import_module(module_name)
        assert getattr(module, "UPSTREAM_NAME", ""), module_name
        names.add(module.UPSTREAM_NAME)
        assert hasattr(getattr(module, class_name), "_post"), module_name

    assert len(names) == len(cases), f"并发闸名重复会导致跨平台共享预算：{names}"


def test_provider_http_calls_all_go_through_gate() -> None:
    """静态兜底：providers 内不得再出现裸 `self._http.post/get`（包装器自身除外）。

    R8 教训：只加不换＝加了闸但没人走闸，形同虚设。
    """
    import app.providers as providers_pkg

    root = Path(providers_pkg.__file__).resolve().parent
    targets = [root / "redfox" / "client.py", *sorted((root / "article_sources").glob("*.py"))]

    offenders: list[str] = []
    for path in targets:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "self._http.post(" in line or "self._http.get(" in line:
                if "return await self._http." not in line:  # 包装器内部允许
                    offenders.append(f"{path.name}:{lineno}")

    assert offenders == [], f"仍有未走并发闸的直连调用：{offenders}"


def test_push_web_reuses_shared_redis_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """站内通知投递复用共享客户端（原实现每次投递 `from_url` 新建连接池）。"""
    url = get_settings().redis_url
    published: list[tuple[str, str]] = []

    class _FakeRedis:
        async def publish(self, channel: str, payload: str) -> int:
            published.append((channel, payload))
            return 1

    monkeypatch.setitem(sec._redis_clients, url, _FakeRedis())

    provider = WebPushProvider()
    results = [
        asyncio.run(provider.push(PushMessage(external_user_id="u7", message="hi")))
        for _ in range(2)
    ]

    assert all(result.delivered for result in results)
    assert len(published) == 2
    assert published[0][0].endswith(":u7")  # 频道语义未变


def test_push_web_failure_stays_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    """改动不得动投递语义：共享客户端抛错时仍返回 retryable=True。"""
    url = get_settings().redis_url

    class _BoomRedis:
        async def publish(self, channel: str, payload: str) -> int:
            raise ConnectionError("redis down")

    monkeypatch.setitem(sec._redis_clients, url, _BoomRedis())

    result = asyncio.run(WebPushProvider().push(PushMessage(external_user_id="u7", message="x")))

    assert result.delivered is False
    assert result.retryable is True


# ═══════════════════════════════════════════════════════ 直接 ASGI 驱动工具


async def _noop_app(scope: Any, receive: Any, send: Any) -> None:
    """最小下游 ASGI 应用：读完请求体后回 200。"""
    total = 0
    while True:
        message = await receive()
        if message["type"] != "http.request":
            break
        total += len(message.get("body", b""))
        if not message.get("more_body", False):
            break
    body = b'{"code":0,"message":"ok","data":%d,"requestId":"x"}' % total
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _drive(
    app: Any,
    messages: list[dict[str, Any]],
    *,
    method: str = "POST",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> list[dict[str, Any]]:
    """直接驱动 ASGI 栈，返回下游发出的全部消息。"""
    pending = list(messages)
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        if pending:
            return pending.pop(0)
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope: dict[str, Any] = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": "/probe",
        "raw_path": b"/probe",
        "query_string": b"",
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    await app(scope, receive, send)
    return sent


# ══════════════════════════════════════════════════════════════════════════
# B.6 —— 交付物的「形状」断言
# ══════════════════════════════════════════════════════════════════════════
# 为什么把 workflow / shell / 文档也放进 pytest：
#   这三件交付物各自的失效方式是**静默**的——
#     · `security.yml` 写错一个输入名 → 该扫描步骤用默认值跑，门禁变假绿（不报错）；
#     · 内嵌 bash/python 的引号或缩进错一处 → 整条 workflow 不执行，GitHub 只给一条
#       "workflow file issue"，而本地没有任何东西能在提交前拦住它；
#     · `rotate_keys.sh` 如果不是"默认 dry-run"，就可能被人手滑执行破坏性命令。
#   把这三件事变成会失败的测试，是从"提交后等 CI 报错"改成"提交前就报错"。
#   与 ci.yml 的 skip 门禁同一思路：纪律写成机制，而不是写在注释里。
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SECURITY_YML = _REPO_ROOT / ".github" / "workflows" / "security.yml"
_ROTATE_SH = _REPO_ROOT / "scripts" / "rotate_keys.sh"
_ROTATION_SOP = _REPO_ROOT / "docs" / "07_release" / "key-rotation-sop.md"

def _resolve_bash() -> str | None:
    """返回真正可执行脚本的 bash 路径，不可用则返回 None（触发用例 skip）。

    `shutil.which("bash")` 在 Windows 上会命中 WSL 启动器（system32/bash.exe），
    但当机器上没有已注册 Linux 发行版时，`bash -c` 会以 `execvpe(/bin/bash) failed`
    退出码 1 失败——「存在 ≠ 可用」。若只按 which 的返回值判断，本用例会在假阳性的
    bash 上执行 `bash -c`，得到 returncode=1 而误判工作流语法有误（本地必红）。
    这里做一次**功能探针**：实跑 `bash -c 'exit 0'`，非 0 或异常一律视同不可用。
    与 Linux CI 的真实校验等价：能跑就跑（真绿），跑不了就明确 skip（绝不做假绿）。
    """
    cand = shutil.which("bash")
    if cand is None:
        return None
    try:
        probe = subprocess.run(
            [cand, "-c", "exit 0"], capture_output=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return cand if probe.returncode == 0 else None


_BASH = _resolve_bash()


def _run_blocks(text: str) -> list[str]:
    """抽出所有 `run: |` 块，并按 YAML 块标量规则去掉公共缩进。

    刻意不 import yaml：PyYAML 只是 uvicorn[standard] 的传递依赖，不是直接声明依赖，
    测试依赖它会把"某天 uvicorn 去掉这个 extra"变成一次莫名的测试全红。
    这里只需要"按缩进切块"，自己实现比多一个隐式依赖更稳。
    """
    lines = text.split("\n")
    blocks: list[str] = []
    for i, line in enumerate(lines):
        if line.strip() != "run: |":
            continue
        key_indent = len(line) - len(line.lstrip())
        body: list[str] = []
        for nxt in lines[i + 1 :]:
            if not nxt.strip():
                body.append("")
                continue
            if len(nxt) - len(nxt.lstrip()) <= key_indent:
                break
            body.append(nxt)
        blocks.append(textwrap.dedent("\n".join(body)))
    return blocks


def _step_chunks(text: str) -> list[str]:
    """按 `- name:` / `- uses:` 切出每个 step 的文本块（含其后的正文）。"""
    lines = text.split("\n")
    starts = [i for i, ln in enumerate(lines) if re.match(r"^\s+- (name|uses):", ln)]
    chunks = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        chunks.append("\n".join(lines[start:end]))
    return chunks


def test_security_workflow_declares_all_four_scanners() -> None:
    """①pip-audit / ②pnpm audit / ③trivy / ④gitleaks 四步骤齐备。"""
    assert _SECURITY_YML.is_file(), f"缺少安全扫描工作流：{_SECURITY_YML}"
    text = _SECURITY_YML.read_text(encoding="utf-8")
    for mark, tool in (("①", "pip-audit"), ("②", "pnpm audit"), ("③", "trivy"), ("④", "gitleaks")):
        hit = [c for c in _step_chunks(text) if f"{mark} " in c.split("\n")[0]]
        assert hit, f"未找到步骤 {mark}"
        assert tool in hit[0].split("\n")[0], f"步骤 {mark} 应使用 {tool}：{hit[0].splitlines()[0]}"


def test_security_workflow_scan_steps_do_not_short_circuit_each_other() -> None:
    """四个扫描步骤都 continue-on-error：一步失败不得吞掉其余三步（裁决收归末尾汇总门禁）。"""
    text = _SECURITY_YML.read_text(encoding="utf-8")
    scan_chunks = [c for c in _step_chunks(text) if c.split("\n")[0].strip().startswith("- name: \"")]
    assert len(scan_chunks) == 4, f"应有 4 个带引号编号的扫描步骤，实际 {len(scan_chunks)}"
    for chunk in scan_chunks:
        assert "continue-on-error: true" in chunk, f"扫描步骤缺少 continue-on-error：{chunk.splitlines()[0]}"


def test_security_workflow_aggregate_gate_runs_always_and_archives_reports() -> None:
    text = _SECURITY_YML.read_text(encoding="utf-8")
    gate = [c for c in _step_chunks(text) if "汇总门禁" in c.split("\n")[0]]
    assert gate, "缺少汇总门禁步骤"
    assert "if: always()" in gate[0], "汇总门禁必须 if: always()（否则前序失败会跳过裁决）"
    assert "SCANNER_ERROR" in gate[0], "汇总门禁必须把 SCANNER_ERROR 视为阻断（fail-closed）"
    assert "actions/upload-artifact" in text, "缺少报告留档步骤"


def test_security_workflow_scans_full_git_history() -> None:
    """gitleaks 走全历史：浅克隆只有 1 个 commit，「曾经提交过、后来删掉」的密钥会整段漏掉。"""
    text = _SECURITY_YML.read_text(encoding="utf-8")
    checkout = [c for c in _step_chunks(text) if "actions/checkout" in c][0]
    assert "fetch-depth: 0" in checkout


def test_security_workflow_excludes_third_party_trees() -> None:
    """排除项必须是单行（trivy --skip-dirs 是 StringSlice，项前空白会被当成另一个路径）。"""
    text = _SECURITY_YML.read_text(encoding="utf-8")
    match = re.search(r"^\s+SCAN_EXCLUDES:\s*(.+)$", text, re.M)
    assert match, "未找到单行形式的 SCAN_EXCLUDES"
    value = match.group(1).strip()
    # 折行标量（> / |-）会把换行变成空格，而 trivy 的 --skip-dirs 是 StringSlice——
    # 项前多一个空格就等于多指定了一个不存在的目录（静默忽略，不报错）。
    assert not value.startswith((">", "|")), "SCAN_EXCLUDES 不得使用折行标量"
    value = value.strip('"').strip("'")
    assert "\n" not in value
    items = value.split(",")
    assert all(item == item.strip() and item for item in items), f"排除项含空白/空项：{items}"
    # .project 是实证必需：全仓 5057 个跟踪文件中 4385 个（86.7%）是第三方参考源码，
    # 不排除则本项目自己的文件被淹没在 4000+ 个第三方文件里，门禁形同虚设。
    assert ".project" in items
    # langbot_plugins 是原始指令的措辞（实为 docker/compose.yml 的卷名，仓库侧无同名目录），
    # 保留字面以便溯源。
    assert "langbot_plugins" in items


def test_security_workflow_embedded_bash_and_python_are_valid() -> None:
    """把 workflow 里嵌的 bash 与 python 各自拆出来单独做语法检查。

    这是本组测试里唯一能拦住"workflow 整条不执行"的判据：GitHub 对含语法错误的
    workflow 只会给一条含糊的 "workflow file issue"，而错误实际发生在第三层
    （YAML 里的 bash，bash 里的 python heredoc）。
    """
    if _BASH is None:  # pragma: no cover - 取决于运行环境
        pytest.skip("无 bash，跳过内嵌脚本语法检查")

    blocks = _run_blocks(_SECURITY_YML.read_text(encoding="utf-8"))
    assert len(blocks) >= 5, f"应抽到至少 5 个 run 块，实际 {len(blocks)}"

    py_checked = 0
    for index, block in enumerate(blocks):
        proc = subprocess.run(
            [_BASH, "-n"],
            input=block.encode("utf-8"),
            capture_output=True,
        )
        assert proc.returncode == 0, f"第 {index} 个 run 块 bash 语法错误：{proc.stderr.decode(errors='replace')}"

        for tag, body in re.findall(r"<<'(\w+)'\n(.*?)\n\s*\1", block, re.S):
            if tag != "PY":
                continue
            py_checked += 1
            try:
                compile(body, f"security.yml#run[{index}]", "exec")
            except SyntaxError as exc:  # pragma: no cover - 失败路径
                raise AssertionError(f"第 {index} 个 run 块内嵌 python 语法错误：{exc}") from exc
    assert py_checked == 4, f"应有 4 段内嵌 python（四扫描器的分类器），实际 {py_checked}"


def test_rotate_keys_defaults_to_dry_run_and_requires_explicit_apply() -> None:
    """默认必须是 dry-run，且破坏性路径只由 --apply 触发。"""
    assert _ROTATE_SH.is_file(), f"缺少轮换脚本：{_ROTATE_SH}"
    body = _ROTATE_SH.read_text(encoding="utf-8")
    assert 'MODE="plan"' in body, "默认模式必须是 plan（dry-run）"
    assert "--apply)" in body and "MODE=\"apply\"" in body
    # 反向断言：不允许出现"默认即写库"的形态
    assert 'MODE="apply"' not in body.split('MODE="plan"')[0], "MODE 的初始值必须是 plan"
    assert "新密钥与旧密钥相同" in body, "必须拒绝「新==旧」的假轮换"
    assert "backup_path" in body, "必须先备份后改写"


def test_rotate_keys_help_and_missing_dsn_are_side_effect_free() -> None:
    """--help 与「缺 DATABASE_URL」两条路径都不许碰数据库、不许落任何文件。"""
    if _BASH is None:  # pragma: no cover - 取决于运行环境
        pytest.skip("无 bash，跳过轮换脚本行为检查")

    workdir = _ROTATE_SH.parent.parent
    env = {k: v for k, v in os.environ.items() if k not in {"DATABASE_URL", "AIDEANBOT_TEST_PG_DSN"}}

    helped = subprocess.run(
        [_BASH, str(_ROTATE_SH), "--help"],
        cwd=str(workdir),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert helped.returncode == 0, helped.stderr
    assert "--apply" in helped.stdout

    blocked = subprocess.run(
        [_BASH, str(_ROTATE_SH)],
        cwd=str(workdir),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert blocked.returncode == 1, "缺 DATABASE_URL 必须失败，绝不能猜一个默认 DSN"
    assert "DATABASE_URL" in blocked.stderr
    assert not (workdir / "key-rotation-backups").exists(), "缺 DSN 时不许产出任何产物目录"


def test_key_rotation_sop_is_documented() -> None:
    """规程必须落盘，并与脚本、真实 env 名、真实表名互相对得上（防文档漂移）。"""
    assert _ROTATION_SOP.is_file(), f"缺少轮换规程：{_ROTATION_SOP}"
    text = _ROTATION_SOP.read_text(encoding="utf-8")
    for key in ("id:", "type:", "title:", "status:", "owner:", "created:", "updated:", "version:"):
        assert key in text.split("---")[1], f"SOP frontmatter 缺字段 {key}"
    for token in (
        "PUSH_SECRET_MASTER_KEY",
        "ENGINE_KEY_MASTER_KEY",
        "bot_channels.secret_enc",
        "engine_key_registrations",
        "scripts/rotate_keys.sh",
        # 最关键的一条：必须明确写出「只改 env 会让旧密文永久不可解」
        "只改 env",
    ):
        assert token in text, f"SOP 未提及 {token}"
