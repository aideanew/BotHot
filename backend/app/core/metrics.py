"""Prometheus 指标面（W6 A.2）：指标族 + HTTP 中间件 + /metrics 独立路由。

暴露的自定义指标族（≥6，叠加 prometheus_client 默认的进程/Python 采集器，
`/metrics` 的 `# HELP` 族数远超验收线 8）：

- `http_request_duration_seconds`（Histogram，label：method/path/status）
  —— 由 `MetricsMiddleware` 在每个 HTTP 请求结束时的墙钟耗时记录。
- `http_requests_in_flight`（Gauge，label：method）—— 进入 +1 / 结束 -1，观测并发。
- `db_pool_in_use`（Gauge）—— 抓取时从 SQLAlchemy 引擎连接池读「已借出」连接数。
- `bothot_jobs_by_status`（Gauge，label：status）—— 抓取时按 `jobs` 表实况 GROUP BY 回填，
  故无论 Job 由哪个进程（worker）推进，backend 的 `/metrics` 都能如实反映队列积压。
- `push_deliveries_total`（Counter，label：channel/outcome）—— 每次投递完成 +1
  （outcome=success/failed/dead），由 `push_scheduler` 的投递收敛点记录。
- `hot_cluster_duration_seconds`（Histogram）—— `run_clustering` 一轮耗时，由
  `job_worker` 的热点任务计时观测。

关键取舍
--------------------------------------
- **path 标签低基数**：`_normalize_path` 把路径里的 id 段（纯数字 / UUID / 长 hex）折叠为
  `{id}`，否则 `/api/v1/spaces/<36位uuid>` 会把每个资源变成一个 label，撑爆时间序列基数。
- **DB 回填在抓取时做、非在热路径做**：`jobs_by_status` / `db_pool_in_use` 用带标签的
  Gauge，Prometheus 的 GaugeFunc 回调不支持多标签，故改为「/metrics 被请求时」按需刷；
  这样 backend 只读共享 Postgres 的实况，不侵入 worker 热循环，也天然跨进程一致。
- **降级优先**：DB 不可达时刷写用 try 包裹跳过，`/metrics` 仍返回其余（进程/HTTP）指标——
  可观测性端点自身绝不能因依赖抖动而 500。
"""

from __future__ import annotations

import re
import time

from fastapi import APIRouter
from fastapi import Response as FastResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import text as sa_text
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# 已知 Job 状态全集：抓取时逐个 set（缺行归 0），避免消失的标签残留旧值。
KNOWN_JOB_STATUSES: tuple[str, ...] = (
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "PARTIAL_SUCCESS",
    "FAILED",
    "CANCELLED",
)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path", "status"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
HTTP_REQUESTS_IN_FLIGHT = Gauge(
    "http_requests_in_flight",
    "Number of HTTP requests currently being served.",
    ["method"],
)
DB_POOL_IN_USE = Gauge(
    "db_pool_in_use",
    "Database connections currently checked out from the pool.",
)
JOBS_BY_STATUS = Gauge(
    "bothot_jobs_by_status",
    "Jobs currently in each lifecycle status (scraped from Postgres).",
    ["status"],
)
PUSH_DELIVERIES_TOTAL = Counter(
    "push_deliveries_total",
    "Total push delivery attempts by channel and outcome.",
    ["channel", "outcome"],
)
HOT_CLUSTER_DURATION = Histogram(
    "hot_cluster_duration_seconds",
    "Duration of one hot-topic clustering run.",
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_LONG_HEX_RE = re.compile(r"^[0-9a-fA-F]{16,}$")

# 自监控豁免：/metrics 自身与存活/就绪探针不记延迟直方图，防抓取行为污染指标。
_EXEMPT_PATHS = frozenset({"/metrics", "/api/v1/system/live", "/api/v1/system/ready"})


def normalize_path(path: str) -> str:
    """把路径里的 id 段折叠为 `{id}`，压住 label 基数（纯数字 / UUID / 长 hex 段）。"""
    if not path:
        return "/"
    parts = path.split("/")
    folded = [
        "{id}" if seg and (seg.isdigit() or _UUID_RE.match(seg) or _LONG_HEX_RE.match(seg)) else seg for seg in parts
    ]
    return "/".join(folded)


def record_push_outcome(channel: str, delivered: bool, dead: bool = False) -> None:
    """投递收敛点调用：outcome ∈ {success, failed, dead}。"""
    outcome = "success" if delivered else ("dead" if dead else "failed")
    PUSH_DELIVERIES_TOTAL.labels(channel=channel, outcome=outcome).inc()


class MetricsMiddleware:
    """纯 ASGI 指标中间件：记录请求耗时与并发数（不依赖 BaseHTTPMiddleware）。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
        started = time.perf_counter()
        HTTP_REQUESTS_IN_FLIGHT.labels(method=method).inc()
        status_holder = {"status": "500"}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = str(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            HTTP_REQUESTS_IN_FLIGHT.labels(method=method).dec()
            elapsed = time.perf_counter() - started
            HTTP_REQUEST_DURATION.labels(
                method=method, path=normalize_path(path), status=status_holder["status"]
            ).observe(elapsed)


def _refresh_db_pool() -> None:
    """从进程级引擎连接池读「已借出」连接数（同步、廉价，失败即跳过）。"""
    try:
        from app.db import get_engine

        # QueuePool.checkedout() 运行时存在；SQLAlchemy 存根未在 Pool 基类声明，故 ignore。
        DB_POOL_IN_USE.set(float(get_engine().pool.checkedout()))  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001  # 可观测性刷写绝不打断 /metrics
        pass


async def _refresh_jobs_by_status() -> None:
    """按 `jobs` 表实况回填各状态计数；DB 不可达时静默跳过。"""
    try:
        from app.db import get_session_factory

        async with get_session_factory()() as session:
            rows = (await session.execute(sa_text("SELECT status, COUNT(*) FROM jobs GROUP BY status"))).all()
        counts = {str(status): float(n) for status, n in rows}
        for status in KNOWN_JOB_STATUSES:
            JOBS_BY_STATUS.labels(status=status).set(counts.get(status, 0.0))
        # 表里出现的、但不在已知全集的状态也如实补一个标签，避免漏报。
        for status, value in counts.items():
            if status not in KNOWN_JOB_STATUSES:
                JOBS_BY_STATUS.labels(status=status).set(value)
    except Exception:  # noqa: BLE001  # 降级：保留上次读数，不 500
        pass


metrics_router = APIRouter(tags=["observability"])


@metrics_router.get("/metrics", include_in_schema=False)
async def metrics_endpoint() -> FastResponse:
    """Prometheus 抓取端点：先刷 DB 侧 Gauge，再序列化全注册表。

    `include_in_schema=False`：这是给 infra 抓取的运维面，不是产品 API——既不进 OpenAPI
    文档，也就游离于 R4.9.3 的公开端点契约与 APP_ROUTERS 覆盖性核对之外（保持纯净）。
    """
    _refresh_db_pool()
    await _refresh_jobs_by_status()
    return FastResponse(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
