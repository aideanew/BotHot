"""R4.9.3 验收：OpenAPI 安全方案（会话 cookie）声明与逐操作标注。

此前 `components.securitySchemes` 恒为空——Swagger UI 不显示锁形标识、不出现
Authorize 按钮，「哪些端点要登录」只能靠读代码或撞 10001 才知道。

标注取自**路由声明的依赖树**（出现 get_current_sub 即需登录会话），不是手维护的
路径白名单——新增端点自动纳入，无需回改清单。唯一例外是经 `MANUAL_SESSION_ROUTES`
显式登记的处理器（它们自查 cookie 而不走 get_current_sub 依赖）。

本文件的漂移锁是**公开端点集合的精确匹配**：任何新端点若漏挂登录依赖，会落进
「未标注」集合使本测失败——方向是「少标比多标危险」（后者只是文档冗字，前者会
让读者以为无需登录即可调用）。
"""

from __future__ import annotations

from fastapi.routing import APIRoute

from app.core.config import get_settings
from app.main import (
    MANUAL_SESSION_ROUTES,
    SECURITY_SCHEME_NAME,
    _uses_session,
    create_app,
)

# 精确公开集合：漏挂登录依赖的新端点会落进「未标注」集合，使 test_public_operations
# 失败。新增真正的公开端点时在此登记并说明为何无需会话。
EXPECTED_PUBLIC = {
    ("get", "/api/v1/auth/login"),  # 浏览器重定向到 IdP
    ("get", "/api/v1/auth/callback"),  # IdP 回跳，尚未建会话
    ("post", "/api/v1/auth/logout"),  # 幂等：无会话也返回成功
    # OIDC Back-Channel Logout 1.0：主平台按用户广播 logout_token，**不携带任何
    # 客户端凭据**——JWT 签名本身就是全部鉴权。若挂会话依赖，主平台（没有
    # BotHot 的 session cookie）必然 10001，整个 back-channel 静默失效。
    ("post", "/api/v1/auth/backchannel-logout"),  # R9：公开但验签 fail-closed
    ("get", "/api/v1/system/health"),  # 存活探针，容器/编排层轮询
    # W6 A.3：/live（进程存活，不触依赖）与 /ready（就绪：PG+Redis+schema）供编排层
    # 探活/摘流，与 /health 同类——由容器/负载均衡轮询，无会话上下文，故公开。
    ("get", "/api/v1/system/live"),
    ("get", "/api/v1/system/ready"),
    ("get", "/api/v1/onboarding/steps"),  # 静态默认值，不含任何用户数据
}


def _classify() -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """返回 (需登录集合, 未标注集合)。"""
    paths = create_app().openapi()["paths"]
    protected: set[tuple[str, str]] = set()
    unmarked: set[tuple[str, str]] = set()
    for path, ops in paths.items():
        for method, op in ops.items():
            (protected if op.get("security") else unmarked).add((method, path))
    return protected, unmarked


def test_security_scheme_declared_as_session_cookie() -> None:
    """声明会话 cookie 方案；名称取自配置而非硬编码字面量。"""
    scheme = create_app().openapi()["components"]["securitySchemes"]
    assert set(scheme) == {SECURITY_SCHEME_NAME}
    declared = scheme[SECURITY_SCHEME_NAME]
    assert declared["type"] == "apiKey"
    assert declared["in"] == "cookie"
    assert declared["name"] == get_settings().session_cookie_name

    # 本系统是重定向式 SSO，无 Bearer Token——文档须明说，避免读者去填 Authorization 头
    assert "Bearer" in declared["description"]
    assert get_settings().session_cookie_name in declared["description"]


def test_public_operations_exact_set() -> None:
    """漂移锁：未标注集合必须精确等于 EXPECTED_PUBLIC。"""
    _protected, unmarked = _classify()
    assert unmarked == EXPECTED_PUBLIC, (
        f"未标注端点与预期不符：多 {sorted(unmarked - EXPECTED_PUBLIC)}"
        f" / 少 {sorted(EXPECTED_PUBLIC - unmarked)}"
    )


def test_protected_operations_reference_declared_scheme() -> None:
    """每个已标注操作的 security 都指向已声明的方案（无悬空引用）。"""
    paths = create_app().openapi()["paths"]
    for path, ops in paths.items():
        for method, op in ops.items():
            security = op.get("security")
            if not security:
                continue
            assert security == [{SECURITY_SCHEME_NAME: []}], (method, path, security)


def test_manual_cookie_routes_are_marked() -> None:
    """MANUAL_SESSION_ROUTES 登记的路由确实被标注（依赖树推导捕不到它们）。

    GET /api/v1/auth/me 在处理器内自查 cookie 并抛 10001，但不走 get_current_sub
    依赖——不登记就会被文档误标为公开端点。
    """
    protected, _unmarked = _classify()
    for method, path in MANUAL_SESSION_ROUTES:
        assert (method, path) in protected, (method, path)


def test_dependency_tree_covers_role_gated_routes() -> None:
    """require_roles 的角色工厂每次返回新函数，但依赖树含 get_current_sub。

    按函数身份匹配角色工厂不可靠；这里直接核对 admin 域路由的依赖树可被锚点捕获，
    防止将来有人把 require_roles 改成不经过 get_current_sub 的旁路。
    """
    from app.api.v1 import admin as admin_module

    routes = [r for r in admin_module.router.routes if isinstance(r, APIRoute)]
    assert routes, "admin 路由表为空"
    for route in routes:
        assert _uses_session(route.dependant), route.path


def test_every_included_route_reaches_schema() -> None:
    """覆盖性核对：APP_ROUTERS 里每条进 schema 的路由都在 OpenAPI 中可被标注。

    标注器遍历 create_app 内登记的 router 列表；若某路由 include 进 app 却漏登记
    进 APP_ROUTERS，它会静默缺席标注（既不标 security 也不进 EXPECTED_PUBLIC 核对）。
    """
    from app.main import APP_ROUTERS

    paths = create_app().openapi()["paths"]
    seen: set[tuple[str, str]] = set()
    for router in APP_ROUTERS:
        for route in router.routes:
            if not isinstance(route, APIRoute) or not route.include_in_schema:
                continue
            assert route.path in paths, route.path
            for method in route.methods:
                if method not in ("HEAD", "OPTIONS"):
                    seen.add((method.lower(), route.path))

    # 反方向：schema 里的操作都要能追溯到 APP_ROUTERS，否则该路由没被登记
    schema_ops = {
        (method, path) for path, ops in paths.items() for method in ops
    }
    assert schema_ops == seen, (
        f"schema 多 {sorted(schema_ops - seen)} / APP_ROUTERS 多 {sorted(seen - schema_ops)}"
    )
