"""统一错误码登记表（先登记后实现）。

段位约定（对齐主平台风格）：
  1xxxx 用户/认证 | 2xxxx 采集/信息源 | 3xxxx 知识库/机器人 | 5xxxx 系统
"""

import re

ERROR_CODES: dict[int, str] = {
    # 1xxxx 用户/认证
    10001: "UNAUTHENTICATED",
    10002: "SSO_STATE_INVALID",
    10003: "SSO_TOKEN_EXCHANGE_FAILED",
    10004: "FORBIDDEN",
    10005: "REQUEST_INVALID",
    10006: "MALFORMED_URL",
    # 2xxxx 采集/信息源
    20001: "SOURCE_URL_UNRECOGNIZED",
    20002: "EXTRACT_FAILED",
    20003: "EXTRACT_QUALITY_LOW",
    20004: "DISCOVERY_FAILED",
    20005: "RATE_LIMITED_UPSTREAM",
    # 3xxxx 知识库/机器人
    30001: "SPACE_NOT_FOUND",
    30002: "LANGBOT_API_ERROR",
    30003: "INGEST_FAILED",
    30004: "RESOURCE_NOT_FOUND",
    30005: "JOB_STATE_INVALID",
    30006: "SPACE_NAME_CONFLICT",
    # 5xxxx 系统
    50001: "INTERNAL_ERROR",
    50002: "DEPENDENCY_UNAVAILABLE",
}


class AppError(Exception):
    """业务异常基类：携带已登记的错误码，由全局异常处理器统一转信封。

    只使用上表已登记的 code；新增码位属契约变更，须先报 A 登记。
    """

    code: int = 50001
    http_status: int = 500

    def __init__(self, message: str | None = None) -> None:
        self.message = message or ERROR_CODES.get(self.code, "INTERNAL_ERROR")
        super().__init__(f"[{self.code}] {self.message}")


# ---------------------------------------------------------------- 1xxxx 认证


class UnauthenticatedError(AppError):
    code = 10001
    http_status = 401


class SsoStateInvalidError(AppError):
    code = 10002
    http_status = 400


class SsoTokenExchangeError(AppError):
    code = 10003
    http_status = 401


class ForbiddenError(AppError):
    code = 10004
    http_status = 403


class RequestInvalidError(AppError):
    """框架级请求错误：FastAPI 请求体校验失败(422) / 框架 HTTPException(<500)。

    业务路由自 M1 起统一抛 AppError，禁用 HTTPException（A 裁决 2026-09-07）。
    """

    code = 10005
    http_status = 422


class MalformedUrlError(AppError):
    """畸形 URL（B-T5 登记，A 备案中）：空串/非 http(s)/非白名单域名/超长/控制字符。

    归入 1xxxx 段为 A 指定码位（10006）；语义上是用户输入错误（400）。
    """

    code = 10006
    http_status = 400


# ---------------------------------------------------------------- 2xxxx 采集


class SourceUrlUnrecognizedError(AppError):
    code = 20001
    http_status = 400


class ExtractFailedError(AppError):
    code = 20002
    http_status = 502


class ExtractQualityLowError(AppError):
    code = 20003
    http_status = 422


class DiscoveryFailedError(AppError):
    code = 20004
    http_status = 502


class RateLimitedUpstreamError(AppError):
    code = 20005
    http_status = 429


# ---------------------------------------------------------------- 3xxxx 知识库


class SpaceNotFoundError(AppError):
    code = 30001
    http_status = 404


class LangbotApiError(AppError):
    """LangBot 上游错误 → 30002/502。

    `upstream_status` 保留上游 HTTP 状态码（仅 `_request` 的 4xx 分支会填）：
    调用方据此区分**结构性失败**（404 资源已不存在 / 405 该版本无此路由，重试无用）
    与**可重试失败**（5xx、网络断开）。删除路径依赖此区分决定能否安全继续。
    """

    code = 30002
    http_status = 502

    def __init__(self, message: str | None = None, upstream_status: int | None = None) -> None:
        super().__init__(message)
        self.upstream_status = upstream_status


class IngestFailedError(AppError):
    code = 30003
    http_status = 502


class JobStateInvalidError(AppError):
    code = 30005
    http_status = 409


class ResourceNotFoundError(AppError):
    """资源不存在 → 30004/404（v0.3 契约 §五：空间详情无效 id → 30004）。

    登记名 RESOURCE_NOT_FOUND（B-T9R 起，对齐台账 v0.3c 裁决）：空间详情/任务等
    各域资源不存在统一复用本码。

    message 契约（v0.4a，A 打回项）：必须可读文案、禁止裸 id——调用点若直接传
    space_id/doc_id 等裸标识，此处统一回填"资源不存在或无权限: <id>"（code 不变，
    仅 message 可读化，不泄露内部栈）。
    """

    code = 30004
    http_status = 404

    def __init__(self, message: str | None = None) -> None:
        if message and _BARE_ID_PATTERN.match(message):
            message = f"资源不存在或无权限: {message}"
        super().__init__(message or "资源不存在或无权限")


# 裸标识形态（UUID / 纯 ASCII id 串，无空格无中文）：识别后回填可读文案
_BARE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class SpaceNameConflictError(AppError):
    """空间重名冲突（uq_space_user_name）→ 30006/409（v0.3a 契约，A 批准）。"""

    code = 30006
    http_status = 409


# ---------------------------------------------------------------- 5xxxx 系统


class InternalError(AppError):
    code = 50001
    http_status = 500


class DependencyUnavailableError(AppError):
    """外部依赖不可用（主平台/LangBot/Redis 等）。"""

    code = 50002
    http_status = 503


# code → 异常类注册表：http_status_for() 的单一来源（与 ERROR_CODES 登记表同序）
_CODE_TO_CLASS: dict[int, type[AppError]] = {
    cls.code: cls
    for cls in (
        UnauthenticatedError,
        SsoStateInvalidError,
        SsoTokenExchangeError,
        ForbiddenError,
        RequestInvalidError,
        MalformedUrlError,
        SourceUrlUnrecognizedError,
        ExtractFailedError,
        ExtractQualityLowError,
        DiscoveryFailedError,
        RateLimitedUpstreamError,
        SpaceNotFoundError,
        LangbotApiError,
        IngestFailedError,
        JobStateInvalidError,
        ResourceNotFoundError,
        SpaceNameConflictError,
        InternalError,
        DependencyUnavailableError,
    )
}


def http_status_for(code: int) -> int:
    """错误码 → HTTP 状态映射（供全局异常处理器使用）。

    单一来源：从各 AppError 子类的 http_status 类属性派生（A 验收返工项，DRY），
    新增错误类后无需再同步本函数。
    """
    cls = _CODE_TO_CLASS.get(code)
    return cls.http_status if cls is not None else 500
