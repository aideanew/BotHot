"""FastAPI 应用入口：路由装配、中间件、全局异常处理与 OpenAPI 安全方案标注。

R4.9.3：标注会话 cookie 安全方案（见 `app.openapi`）。此前 `components.securitySchemes`
恒为空——Swagger UI 不显示锁形标识、不出现 Authorize 按钮，「哪些端点要登录」只能靠
读代码或撞 10001 才知道。
"""

from collections.abc import Sequence
from contextlib import asynccontextmanager
from functools import partial
from typing import Any

import structlog
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.dependencies.models import Dependant
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import get_current_sub
from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.bots import router as bots_router
from app.api.v1.chat import router as chat_router
from app.api.v1.engines import engines_router, space_engine_router
from app.api.v1.extract import router as extract_router
from app.api.v1.hot import router as hot_router
from app.api.v1.onboarding import router as onboarding_router
from app.api.v1.resolve import router as resolve_router
from app.api.v1.spaces import router as spaces_router
from app.api.v1.subscriptions import jobs_router, sources_router, subscriptions_router
from app.api.v1.system import router as system_router
from app.core.config import assert_production_ready, get_settings
from app.core.errors import AppError, http_status_for
from app.core.logging import configure_logging
from app.core.metrics import MetricsMiddleware, metrics_router
from app.core.middleware import ErrorEnvelopeMiddleware, RequestIdMiddleware
from app.core.response import failure
from app.db import get_session_factory
from app.services.push_scheduler import start_push_scheduler, stop_push_scheduler

# ------------------------------------------------------------------ R4.9.3 OpenAPI 安全方案

SECURITY_SCHEME_NAME = "BotHotSessionCookie"

logger = structlog.get_logger(__name__)

# 不经 get_current_sub 依赖、在处理器内自查 cookie 的路由：依赖树推导捕不到它们。
# 新增此类路由必须在此登记，否则文档会把它误标为公开端点（少标比多标危险——
# 后者只是文档冗字，前者会让读者以为无需登录即可调用）。
MANUAL_SESSION_ROUTES = frozenset({("get", "/api/v1/auth/me")})


def _uses_session(dependant: Dependant) -> bool:
    """依赖树里是否出现 get_current_sub（递归展开）。

    `require_roles(...)` 每次调用都返回新的函数对象，按函数身份匹配不可靠；但它的
    依赖树里含 get_current_user_id → get_current_sub，故从 get_current_sub 这一个锚点
    递归即可同时覆盖用户域与全部 admin 域路由。判定取自**声明的依赖**而非路径白名单，
    新增端点自动纳入，无需回改清单。
    """
    for dep in dependant.dependencies:
        if dep.call is get_current_sub or _uses_session(dep):
            return True
    return False


def _annotate_session_security(routers: Sequence[APIRouter], schema: dict[str, Any]) -> None:
    """向已生成的 OpenAPI 补 `components.securitySchemes` 与逐操作的 `security` 标注。"""
    cookie_name = get_settings().session_cookie_name
    schema.setdefault("components", {})["securitySchemes"] = {
        SECURITY_SCHEME_NAME: {
            "type": "apiKey",
            "in": "cookie",
            "name": cookie_name,
            "description": (
                f"会话 cookie（{cookie_name}）：SSO 回调后由后端下发，HttpOnly + "
                "SameSite=Lax。本系统没有 Bearer Token、也没有 token 交换端点——"
                "GET /api/v1/auth/login 与 /callback 是浏览器重定向式 SSO。"
                "Authorize 里填该 cookie 的值即等价于浏览器自动携带。"
                "角色门禁（admin / operator）不在方案层表达，见各端点描述。"
            ),
        }
    }

    for router in routers:
        for route in router.routes:
            if not isinstance(route, APIRoute) or not route.include_in_schema:
                continue
            if not route.methods:
                continue
            # 过滤 HEAD/OPTIONS：FastAPI 自动补的这两个动词不进 OpenAPI
            methods = {m.lower() for m in route.methods if m not in ("HEAD", "OPTIONS")}
            protected = _uses_session(route.dependant) or any(
                (m, route.path) in MANUAL_SESSION_ROUTES for m in methods
            )
            if not protected:
                continue
            ops = schema.get("paths", {}).get(route.path, {})
            for method in sorted(methods):
                if method in ops:
                    ops[method]["security"] = [{SECURITY_SCHEME_NAME: []}]


def _openapi_with_security(
    app: FastAPI, routers: Sequence[APIRouter]
) -> dict[str, Any]:
    """`FastAPI.openapi` 的包装：生成后再补安全方案标注。

    直接调类方法 `FastAPI.openapi(app)` 而非 `app.openapi()`，避免实例属性遮蔽后自引用
    递归；原实现的 openapi_schema 缓存仍生效，本包装只在其结果上补标注。
    """
    schema = FastAPI.openapi(app)
    _annotate_session_security(routers, schema)
    return schema


def register_exception_handlers(app: FastAPI) -> None:
    """把各类异常统一收敛成 {code,message,data,requestId} 信封。"""

    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        body = failure(exc.code, exc.message)
        return JSONResponse(status_code=http_status_for(exc.code), content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 请求参数不合法：客户端错误 → 10005/422（裁决 2026-09-07）
        body = failure(10005, f"请求参数校验失败: {exc.errors()[:1]}")
        return JSONResponse(status_code=422, content=body.model_dump())

    @app.exception_handler(HTTPException)
    async def _handle_http_exception(_: Request, exc: HTTPException) -> JSONResponse:
        # 业务路由禁用 HTTPException（统一抛 AppError）；此处仅兜框架/中间件层遗留：
        # >=500 归系统语义 50001，<500 归请求语义 10005，HTTP 状态码均透传原值
        if exc.status_code >= 500:
            body = failure(50001, str(exc.detail))
        else:
            body = failure(10005, str(exc.detail))
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(StarletteHTTPException)
    async def _handle_starlette_http_exception(
        _: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        # T1.5.2（2026-09-22）405/404 信封收口：未注册路径/未注册动词由 Starlette 路由器
        # 抛 starlette.HTTPException（fastapi.HTTPException 之父类，MRO 不含子类 →
        # 上面的 fastapi 版处理器接不到，默认 {"detail": ...} 裸体曾泄漏到客户端）。
        # 现与 fastapi 版同语义收敛：>=500 → 50001，<500 → 10005，状态码透传。
        if exc.status_code >= 500:
            body = failure(50001, str(exc.detail))
        else:
            body = failure(10005, str(exc.detail))
        return JSONResponse(
            status_code=exc.status_code, content=body.model_dump(), headers=exc.headers
        )

    # 未捕获异常的兜底不放这里：Starlette 会把 `Exception` 处理器挂到最外层
    # ServerErrorMiddleware（在 requestId 之外），改由 ErrorEnvelopeMiddleware 内层兜底。


# ------------------------------------------------------------------ 路由表

# 按域登记的路由表，create_app 与 R4.9.3 的 OpenAPI 安全标注共用这一份。
# 不遍历 app.routes 取路由：FastAPI 0.141 把 include_router 的产物懒收敛成
# `_IncludedRouter` 私有节点，app.routes 上取不到 APIRoute。
APP_ROUTERS: tuple[APIRouter, ...] = (
    system_router,
    auth_router,
    onboarding_router,
    spaces_router,
    # SPEC-M3 批次 2（A-2 叠加）：admin 跨用户端点，既有 spaces 路由不动
    admin_router,
    resolve_router,
    extract_router,
    chat_router,
    # AB-P004 P2 整号订阅（sources/subscriptions/jobs）
    sources_router,
    subscriptions_router,
    jobs_router,
    # AB-P004 P4 引擎可插拔（engines/PATCH space engine）
    engines_router,
    space_engine_router,
    # BotHot 扩展：多渠道推送 + 热点聚簇/日报
    bots_router,
    hot_router,
)


def _assert_schema_current(settings) -> None:
    """R6.1.4：schema/code 版本一致性守卫（开发环境仅告警，生产拒启）。

    本函数在 create_app 的同步路径里做 async DB 探测，须满足两个前提：
    1) 无运行中的事件循环——生产由 uvicorn 在 import 期调 create_app（无 loop），
       守卫照跑；测试常在 async 用例内调 create_app（已有 loop），asyncio.run
       会抛 RuntimeError，此时跳过而非重抛；
    2) 用一次性独立引擎而非进程单例——asyncio.run 会创建并关闭新 loop，把单例
       引擎绑上去会让其连接池随 loop 关闭而失效（跨 loop 报错）。用完即 dispose。
    """
    try:
        import asyncio

        asyncio.get_running_loop()
    except RuntimeError:
        pass  # 无运行中的 loop：可安全 asyncio.run
    else:
        return  # 已在 async 上下文（多为测试），跳过启动期探测

    try:
        from app.core import schema_guard
        from app.db import create_engine_and_session, resolve_database_url

        head = schema_guard.get_alembic_head()

        engine, _ = create_engine_and_session(resolve_database_url(settings.database_url))

        async def _probe_and_dispose() -> str | None:
            try:
                return await schema_guard.read_current_version_async(engine)
            finally:
                # 一次性引擎用完即 dispose：asyncio.run 会关掉所在 loop，
                # 泄漏绑在已关 loop 上的连接池会污染进程单例（跨 loop 报错）。
                await engine.dispose()

        current = asyncio.run(_probe_and_dispose())
        if head is not None and current != head:
            msg = f"schema/code 版本不一致：DB={current}, HEAD={head}"
            if settings.app_env.strip().lower() == "production":
                raise RuntimeError(msg)
            logger.warning("⚠️ %s（开发环境仅告警）", msg)
    except RuntimeError:
        raise
    except Exception:
        pass


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """应用生命周期：启动/停止推送调度器。"""
    await start_push_scheduler(get_session_factory())
    try:
        yield
    finally:
        await stop_push_scheduler()


def create_app() -> FastAPI:
    configure_logging()  # W6 A.1：先装日志，使下方启动守卫的告警走结构化链路
    settings = get_settings()
    assert_production_ready(settings)  # 生产配置不合格即拒启（见 core.config）
    _assert_schema_current(settings)  # R6.1.4：schema/code 版本一致性守卫
    app = FastAPI(title=settings.app_name, version="0.1.0", docs_url="/docs", lifespan=_lifespan)

    # add_middleware 是"后注册者更外层"：先装异常兜底，再装 requestId，最后装 metrics
    # （metrics 居最外，连 requestId 上下文缺失的早期异常也能计时）。
    app.add_middleware(ErrorEnvelopeMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(MetricsMiddleware)

    for router in APP_ROUTERS:
        app.include_router(router)
    # W6 A.2：/metrics 独立路由（无鉴权、不入 APP_ROUTERS 的安全标注遍历）。
    app.include_router(metrics_router)
    register_exception_handlers(app)
    # R4.9.3：生成 OpenAPI 后补安全方案标注（见 _annotate_session_security）
    app.openapi = partial(_openapi_with_security, app, APP_ROUTERS)  # type: ignore[method-assign]

    # W6 冻结接口：W7 交付 `install_security_middlewares`；本批只在既有中间件之后装配，
    # 不实现。W7 未就位时 ImportError 静默跳过，零回归。
    try:
        from app.core.security import install_security_middlewares

        install_security_middlewares(app)
    except ImportError:
        pass

    return app


app = create_app()
