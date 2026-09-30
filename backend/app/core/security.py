"""入站安全与上游资源治理（W7）。

同属「资源治理」的三块职责集中于此，避免散落各域：

1. **入站防护中间件**（纯 ASGI，不依赖 `BaseHTTPMiddleware`——后者会在子任务间
   丢失 contextvar，导致 429/413 拿不到 requestId）：
   - `BodyLimitMiddleware` —— 请求体上限（`Content-Length` 预检 + 有界缓冲）
   - `RateLimitMiddleware` —— Redis 固定窗口限流（IP + 会话双维）
   - `SecurityHeadersMiddleware` —— 响应安全头（须**最外层**，短路响应也要带头）
   由 `install_security_middlewares(app)` 统一装配（调用方是 `app.main.create_app`）。

2. **上游并发闸与超时**：`upstream_semaphore(name)` / `upstream_timeout()`，
   供 `providers/article_sources/*` 与 `providers/redfox/client.py` 使用。

3. **共享 Redis 客户端**：`get_shared_redis()` —— 限流计数器与站内通知发布共用，
   杜绝「每请求 `from_url`」的建连放大（旧 `providers/push/web.py` 每次投递新建连接）。

## 装配顺序（内 → 外，`add_middleware` 后注册者更外层）

    ErrorEnvelopeMiddleware        ← 既有（app/main.py）
    RequestIdMiddleware            ← 既有（app/main.py）
    BodyLimitMiddleware            ← 本模块（第一个注册 → 最内）
    RateLimitMiddleware
    SecurityHeadersMiddleware      ← 最后一个注册 → 最外层

由此得到两条必要性质：
- 短路响应（429/413）**绕过了** `RequestIdMiddleware`（它更内层），故本模块自行
  解析/生成 requestId 并写入 `X-Request-ID`，保证「响应头 == 响应体 requestId」；
- `SecurityHeadersMiddleware` 在最外层，故 429/413 也带全套安全头。

## 限流维度取「会话 ID」而非「sub」的取舍

`api/deps.get_current_sub()` 需要一次会话存储往返（memory/Redis）才能得到 sub；
在中间件层复刻等于**每请求 +1 次 IO**（限流本身就会成为放大器）。会话 ID 与 sub
在单会话内恒 1:1，且作为限流维度只需唯一与稳定两个性质——故直接取 cookie 值，
cookie 名与 `get_current_sub` 同源（`settings.session_cookie_name`）。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
import weakref
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from fastapi import FastAPI
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings
from app.core.errors import PayloadTooLargeError, RateLimitedError
from app.core.request_context import REQUEST_ID_HEADER, reset_request_id, set_request_id
from app.core.response import failure

logger = logging.getLogger(__name__)

# 错误码单一来源 = core/errors.py 的异常类（避免字面量在两处漂移）
RATE_LIMITED_CODE = RateLimitedError.code
PAYLOAD_TOO_LARGE_CODE = PayloadTooLargeError.code

# 携带请求体的方法（其余方法直接放行，不为 GET/HEAD/OPTIONS 付缓冲代价）
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# 豁免路径：探活/指标/API 文档。探活被编排系统高频轮询，限它没有安全收益却有
# 误伤风险（compose healthcheck 一旦被 429，容器会被反复重启）。
_EXEMPT_PATHS = frozenset(
    {
        "/api/v1/system/health",
        "/metrics",
        "/live",
        "/ready",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)


# ════════════════════════════════════════════════════════════════ 工具


def _header(scope: Scope, name: str) -> str | None:
    """按名取请求头（大小写不敏感），缺失返回 None。"""
    target = name.lower().encode("latin-1")
    for raw_key, raw_value in scope.get("headers") or []:
        if raw_key.lower() == target:
            return raw_value.decode("latin-1")
    return None


def _resolve_request_id(scope: Scope) -> str:
    """解析/生成 requestId（与 `RequestIdMiddleware` 同口径：沿用上游头，否则新生成）。"""
    incoming = _header(scope, REQUEST_ID_HEADER)
    if incoming and incoming.strip():
        return incoming.strip()
    return str(uuid.uuid4())


async def _send_envelope(
    scope: Scope,
    receive: Receive,
    send: Send,
    *,
    status: int,
    code: int,
    message: str,
    extra_headers: dict[str, str] | None = None,
) -> None:
    """短路响应：自行绑定 requestId 上下文后发信封（见模块头「装配顺序」）。"""
    request_id = _resolve_request_id(scope)
    token = set_request_id(request_id)
    try:
        body = failure(code, message).model_dump()
        body["requestId"] = request_id  # 与中间件解析值强一致，不依赖上下文兜底
        headers = {REQUEST_ID_HEADER: request_id}
        if extra_headers:
            headers.update(extra_headers)
        response = JSONResponse(status_code=status, content=body, headers=headers)
        await response(scope, receive, send)
    finally:
        reset_request_id(token)


# ════════════════════════════════════════════════════════════════ 共享 Redis


_redis_clients: dict[str, Any] = {}


def get_shared_redis(url: str | None = None) -> Any | None:
    """进程级共享 `redis.asyncio` 客户端（按 URL 缓存）。

    `from_url` 不触发网络 IO（首个命令才连接），故 import/构造期零副作用。
    URL 为空 → None（调用方自行降级）。命令超时取 `rate_limit_redis_timeout_seconds`
    （默认 1s）：这是**降级延迟上限**，必须远小于业务超时——Redis 挂掉时
    fail-open 要快，否则限流会成为全站延迟放大器。
    """
    settings = get_settings()
    target = url if url is not None else settings.redis_url
    if not target:
        return None
    client = _redis_clients.get(target)
    if client is None:
        import redis.asyncio as aioredis

        timeout = settings.rate_limit_redis_timeout_seconds
        client = aioredis.from_url(
            target, socket_connect_timeout=timeout, socket_timeout=timeout
        )
        _redis_clients[target] = client
    return client


def reset_shared_redis() -> None:
    """清空共享客户端缓存（测试隔离用；生产不调用）。"""
    _redis_clients.clear()


# ════════════════════════════════════════════════════════════════ 限流计数器


class RateLimitCounter(Protocol):
    """计数器协议：`incr_window` 返回当前窗口内第几次；Redis 不可用返回 None。"""

    async def incr_window(self, key: str, window_seconds: int) -> int | None: ...


class RedisFixedWindowCounter:
    """Redis 固定窗口计数器：`INCR` + 首命中 `EXPIRE`。

    窗口桶号（`int(now / window)`）编入 key，故过期由 Redis TTL 自然完成，
    无需在读取侧比对时间戳。**固定窗口**而非滑动窗口：边界处允许 2× 突刺，
    换来的是单次 `INCR` 的稳定开销；对「防打爆」这一目标足够。
    """

    async def incr_window(self, key: str, window_seconds: int) -> int | None:
        client = get_shared_redis()
        if client is None:
            return None  # 未配置 Redis：无状态可用 → 调用方 fail-open
        try:
            count = await client.incr(key)
            if int(count) == 1:
                await client.expire(key, window_seconds)
            return int(count)
        except Exception:  # noqa: BLE001  Redis 抖动/不可达：fail-open，不影响业务
            logger.warning("限流计数器 Redis 不可用，本轮 fail-open（不限流）", exc_info=True)
            return None


_counter: RateLimitCounter = RedisFixedWindowCounter()


def set_rate_limit_counter(counter: RateLimitCounter | None) -> None:
    """替换限流计数器（测试注入假实现；传 None 恢复默认）。"""
    global _counter
    _counter = counter if counter is not None else RedisFixedWindowCounter()


def get_rate_limit_counter() -> RateLimitCounter:
    return _counter


# ════════════════════════════════════════════════════════════════ 限流规则


@dataclass(frozen=True, slots=True)
class _Rule:
    name: str
    pattern: re.Pattern[str]
    per_minute: int


# 敏感路径独立配额（放宽到能容纳正常前端轮询，收紧到能挡住脚本化打点）。
# 数值可通过 `RATE_LIMIT_<NAME>_PER_MINUTE` 覆盖（见 _rule_limit）。
_SENSITIVE_RULES: tuple[tuple[str, str, int], ...] = (
    ("auth", r"^/api/v1/auth(?:/|$)", 60),  # 登录/回调/登出链路
    ("chat", r"^/api/v1/chat(?:/|$)", 60),  # LLM 流式对话（成本端点）
    ("extract", r"^/api/v1/extract(?:/|$)", 60),  # 抓取（外呼成本端点）
    ("hot_cluster", r"^/api/v1/hot/topics/cluster$", 10),  # 聚簇触发（重计算）
    ("push_task_run", r"^/api/v1/bots/tasks/[^/]+/run$", 30),  # 手工触发推送
)


def _rule_limit(name: str, default: int) -> int:
    raw = os.environ.get(f"RATE_LIMIT_{name.upper()}_PER_MINUTE")
    if raw and raw.strip().isdigit() and int(raw) > 0:
        return int(raw)
    return default


def _build_rules(default_per_minute: int) -> tuple[_Rule, ...]:
    return tuple(
        _Rule(name, re.compile(pattern), _rule_limit(name, limit))
        for name, pattern, limit in _SENSITIVE_RULES
    ) + (_Rule("global", re.compile(r".*"), default_per_minute),)


def _window_bucket(now: float, window_seconds: int) -> int:
    return int(now // window_seconds)


# ════════════════════════════════════════════════════════════════ 中间件


class RateLimitMiddleware:
    """入站限流（IP + 会话双维；任一超限即 429）。

    维度取舍见模块头。两维各自独立计数：IP 维挡单机脚本，会话维挡换 IP 的单账号滥用。
    **fail-open**：Redis 不可用 ⇒ 计数器返回 None ⇒ 放行（可用性 > 限流完整性；
    限流是加固不是准入门禁，宁可漏挡不可全挡）。
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        enabled: bool = True,
        default_per_minute: int = 600,
        window_seconds: int = 60,
        cookie_name: str = "bothot_session",
        trust_proxy_headers: bool = False,
    ) -> None:
        self.app = app
        self._enabled = enabled
        self._window = max(1, int(window_seconds))
        self._cookie_name = cookie_name
        self._trust_proxy = trust_proxy_headers
        self._rules = _build_rules(default_per_minute)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._enabled:
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if path in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        rule = next((r for r in self._rules if r.pattern.match(path)), self._rules[-1])
        now = time.time()
        bucket = _window_bucket(now, self._window)

        for dimension, value in self._dimensions(scope):
            key = f"bothot:rl:{rule.name}:{dimension}:{value}:{bucket}"
            count = await _counter.incr_window(key, self._window)
            if count is None:
                continue  # Redis 不可用：fail-open
            if count > rule.per_minute:
                retry_after = self._window - int(now) % self._window
                logger.warning(
                    "入站限流命中 rule=%s dim=%s limit=%d/%ds path=%s",
                    rule.name, dimension, rule.per_minute, self._window, path,
                )
                await _send_envelope(
                    scope, receive, send,
                    status=429,
                    code=RATE_LIMITED_CODE,
                    message=f"请求过于频繁，请于 {retry_after} 秒后重试",
                    extra_headers={"Retry-After": str(retry_after)},
                )
                return

        await self.app(scope, receive, send)

    def _dimensions(self, scope: Scope) -> list[tuple[str, str]]:
        dims: list[tuple[str, str]] = []
        client = scope.get("client")
        ip = client[0] if client else "unknown"
        if self._trust_proxy:
            xff = _header(scope, "x-forwarded-for")
            if xff:
                ip = xff.split(",")[0].strip() or ip
        dims.append(("ip", ip))

        identity = self._session_identity(scope)
        if identity:
            dims.append(("id", identity))
        return dims

    def _session_identity(self, scope: Scope) -> str | None:
        raw = _header(scope, "cookie")
        if not raw:
            return None
        for part in raw.split(";"):
            key, _, value = part.strip().partition("=")
            if key == self._cookie_name and value:
                return value
        return None


class BodyLimitMiddleware:
    """请求体上限（413）。

    两段式：
    1. `Content-Length` 预检 —— 命中即拒，**不读一个字节**（省带宽与内存）；
    2. 有界缓冲 —— chunked / 伪造长度绕不过（预检缺失时按实读字节数判定）。

    为什么缓冲而非流式包裹：流式拦截需在 `receive` 里抛异常中断下游，而更内层的
    `ErrorEnvelopeMiddleware` 会先把它兜成 500（错误语义被吃掉）。缓冲把判定权
    留在本中间件，`return` 即是 413，语义确定。上限 4 MiB 级，内存代价可接受。
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int = 4 * 1024 * 1024) -> None:
        self.app = app
        self._max_bytes = max(0, int(max_bytes))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._max_bytes <= 0:
            await self.app(scope, receive, send)
            return
        if (scope.get("method") or "").upper() not in _BODY_METHODS:
            await self.app(scope, receive, send)
            return

        declared = _header(scope, "content-length")
        if declared and declared.strip().isdigit() and int(declared) > self._max_bytes:
            await self._reject(scope, receive, send, int(declared))
            return

        buffered: list[Message] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                buffered.append(message)
                break
            total += len(message.get("body", b""))
            if total > self._max_bytes:
                await self._reject(scope, receive, send, total)
                return
            buffered.append(message)
            if not message.get("more_body", False):
                break

        replay_index = 0

        async def replay() -> Message:
            nonlocal replay_index
            if replay_index < len(buffered):
                message = buffered[replay_index]
                replay_index += 1
                return message  # type: ignore[return-value]
            return {"type": "http.request", "body": b"", "more_body": False}  # type: ignore[return-value]

        await self.app(scope, replay, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send, size: int) -> None:
        limit = self._max_bytes
        logger.warning("请求体超限：%d > %d bytes path=%s", size, limit, scope.get("path"))
        await _send_envelope(
            scope, receive, send,
            status=413,
            code=PAYLOAD_TOO_LARGE_CODE,
            message=f"请求体过大（上限 {limit} 字节）",
        )


class SecurityHeadersMiddleware:
    """响应安全头（最外层：短路响应也带头）。

    **不含 CORS**——前端经 `next.config.mjs` rewrites 同源代理 `/api/v1/*`，
    浏览器从不跨域直连后端；加 `Access-Control-Allow-Origin` 只扩大攻击面。
    CSP 先以 `Report-Only` 下发（不阻断，只观测），待资源清单收敛后再转强制。
    """

    _BASE_HEADERS: tuple[tuple[str, str], ...] = (
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "strict-origin-when-cross-origin"),
        (
            "Content-Security-Policy-Report-Only",
            "default-src 'self'; "
            "img-src 'self' data: https:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'",
        ),
    )

    def __init__(self, app: ASGIApp, *, hsts_max_age: int = 31536000) -> None:
        self.app = app
        self._hsts = ("Strict-Transport-Security", f"max-age={hsts_max_age}; includeSubDomains")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        secure = scope.get("scheme") == "https"
        if not secure:
            proto = (_header(scope, "x-forwarded-proto") or "").split(",")[0].strip().lower()
            secure = proto == "https"

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for key, value in self._BASE_HEADERS:
                    headers.setdefault(key, value)
                if secure:
                    headers.setdefault(*self._hsts)
            await send(message)

        await self.app(scope, receive, send_with_headers)


def install_security_middlewares(app: FastAPI) -> None:
    """装配入站防护中间件（**冻结接口**，由 `app.main.create_app` 调用）。

    内 → 外：BodyLimit → RateLimit → SecurityHeaders（`add_middleware` 后注册者更外层）。
    必须由调用方在既有 `ErrorEnvelopeMiddleware` / `RequestIdMiddleware` **之后**调用，
    否则短路响应拿不到 requestId 上下文（详见模块头）。

    import 无副作用：`get_settings()` 只读 env，Redis 客户端惰性创建。
    """
    settings = get_settings()
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    app.add_middleware(
        RateLimitMiddleware,
        enabled=settings.rate_limit_enabled,
        default_per_minute=settings.rate_limit_default_per_minute,
        window_seconds=settings.rate_limit_window_seconds,
        cookie_name=settings.session_cookie_name,
        trust_proxy_headers=settings.trust_proxy_headers,
    )
    app.add_middleware(SecurityHeadersMiddleware)


# ════════════════════════════════════════════════════════════════ 上游治理

# 每个事件循环一套信号量：`asyncio.Semaphore` 首次使用即绑定当时循环，
# 跨循环复用会 raise（pytest-asyncio 每用例新循环必踩）。按循环分表既避免该问题，
# 又保留了「同一循环（= 生产单进程）内跨请求真限流」这一目标性质。
_upstream_semaphores: weakref.WeakKeyDictionary[Any, dict[str, asyncio.Semaphore]] = (
    weakref.WeakKeyDictionary()
)


def upstream_concurrency(name: str) -> int:
    """单 provider 并发上限（`UPSTREAM_CONCURRENCY_<NAME>` 覆盖默认值）。"""
    raw = os.environ.get(f"UPSTREAM_CONCURRENCY_{name.upper()}")
    if raw and raw.strip().isdigit() and int(raw) > 0:
        return int(raw)
    return get_settings().upstream_concurrency_default


def upstream_semaphore(name: str) -> asyncio.Semaphore:
    """取 `name` 对应的事件循环内共享信号量（无运行循环时返回一次性信号量）。"""
    try:
        loop: Any = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.Semaphore(upstream_concurrency(name))

    per_loop = _upstream_semaphores.get(loop)
    if per_loop is None:
        per_loop = {}
        _upstream_semaphores[loop] = per_loop
    semaphore = per_loop.get(name)
    if semaphore is None:
        semaphore = asyncio.Semaphore(upstream_concurrency(name))
        per_loop[name] = semaphore
    return semaphore


def upstream_timeout(read_fallback: float | None = None) -> httpx.Timeout:
    """上游 httpx 超时：connect 短（快速失败）、read 长（大响应允许慢）。

    `read_fallback` 取各 provider 既有的 `DEFAULT_TIMEOUT`，保持其读超时语义不变；
    未传时用 `upstream_read_timeout_seconds`。
    """
    settings = get_settings()
    read = (
        float(read_fallback)
        if read_fallback is not None and read_fallback > 0
        else settings.upstream_read_timeout_seconds
    )
    return httpx.Timeout(
        connect=settings.upstream_connect_timeout_seconds,
        read=read,
        write=read,
        pool=settings.upstream_connect_timeout_seconds,
    )
