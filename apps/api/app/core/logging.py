"""结构化日志枢纽（W6 A.1）：structlog 双模 + stdlib 桥接。

设计要点（为何这样装配）
--------------------------------------
- **双模渲染**：`LOG_FORMAT=json`（或 `APP_ENV=production` 缺省）走 `JSONRenderer`
  供日志采集器（Loki/ELK/CloudWatch）解析；开发缺省走 `ConsoleRenderer` 供人眼彩色直读。
  显式 `LOG_FORMAT` 恒优先于环境推断，便于本地复现生产 JSON。
- **单一出口，杜绝重复行**：全进程只有一个 `StreamHandler` 挂在 root 上，其
  `Formatter` 是 structlog 的 `ProcessorFormatter`。
    * 本框架原生日志（`structlog.get_logger`）：处理器链末端是
      `ProcessorFormatter.wrap_for_formatter`，它**不渲染**，只把 event_dict 打包进
      stdlib `LogRecord`，交给同一个 `ProcessorFormatter` 在 emit 时渲染一次；
    * 第三方库经 stdlib 的日志（uvicorn / sqlalchemy / redis 等）：经
      `foreign_pre_chain` 补齐 level/timestamp/logger 名，再走同一渲染器。
  两条路径在**同一个 handler 收敛、各渲染一次**，因此不会出现「structlog 先打一行、
  stdlib 再打一行」的双写。这也是全项目**唯一**直接摆弄 stdlib `logging` 的地方——
  其余模块一律 `import structlog` + `structlog.get_logger(__name__)`（见验收：裸
  `logging.getLogger` 仅存于本文件）。
- **requestId 贯穿**：`merge_contextvars` 置于链首，`RequestIdMiddleware` 经
  `structlog.contextvars.bind_contextvars(request_id=...)` 绑定后，同一请求的每条日志
  自动带同一 `request_id`，与响应头 `X-Request-ID`、信封 `requestId` 三者一致。
- **幂等装配**：`configure_logging()` 可安全重复调用（create_app 与两个常驻进程入口都会
  调）；`force=True` 供测试重置。用 `cache_logger_on_first_use=True` 时，模块级
  `get_logger` 返回的是惰性代理，真正物化发生在**首次 emit**——只要装配先于任何日志输出
  （进程启动即装配），已缓存的 logger 就用的是本配置，无「导入期抢跑用默认配置」之患。

局限：`uvicorn` 以 `--log-config` 或自身 `log_config` 接管 root 时会覆盖本装配；
本项目经 `app.main:app` 工厂模式启动（uvicorn 无 log_config），root 由本模块掌控。
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog

_configured = False

# 挂在 root 上、由本模块安装的唯一 handler 的识别标记，用于幂等重装时先摘旧的。
_OUR_HANDLER_ATTR = "_bothot_structlog_handler"

_VALID_LEVELS = {
    "CRITICAL",
    "ERROR",
    "WARNING",
    "WARN",
    "INFO",
    "DEBUG",
    "NOTSET",
}


def _resolve_level() -> int:
    raw = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
    if raw not in _VALID_LEVELS:
        return logging.INFO
    # WARN 是 WARNING 的别名；getattr 取 stdlib 数值级别。
    return getattr(logging, raw, logging.INFO)


def _resolve_format() -> str:
    """显式 LOG_FORMAT 优先；否则生产=JSON、开发=Console。返回 "json" 或 "console"。"""
    explicit = os.environ.get("LOG_FORMAT", "").strip().lower()
    if explicit in ("json", "console"):
        return explicit
    env = os.environ.get("APP_ENV", "").strip().lower()
    return "json" if env == "production" else "console"


def _shared_processors() -> list[Any]:
    """原生日志与外来 stdlib 日志共用的前置处理器链（决定日志里出现哪些字段）。"""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        # 兼容既有 %-风格位置参数调用：logger.warning("...%s", x)
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=False),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]


def _resolve_stream() -> Any:
    """返回日志出口流，尽力切到 UTF-8。

    Windows 控制台默认 GBK 码页，会让含中文/emoji 的结构化日志（如启动守卫的
    `⚠️` 告警）在 `stream.write` 时抛 `UnicodeEncodeError`——logging 虽会吞掉该异常
    仅打 `--- Logging error ---`，但那行日志就此丢失。生产跑 Docker（UTF-8）无此问题，
    此处为本地 Windows 开发体验兜底：能 `reconfigure` 就切 UTF-8；被测试捕获对象等
    不支持 `reconfigure` 的场景静默回退原流。
    """
    stream = sys.stdout
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass
    return stream


def configure_logging(force: bool = False) -> None:
    """装配 structlog + stdlib 双模日志。幂等：重复调用无副作用（除非 force=True）。"""
    global _configured
    if _configured and not force:
        return

    level = _resolve_level()
    renderer: Any
    if _resolve_format() == "json":
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty() and sys.stdout.isatty())

    shared = _shared_processors()

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )

    handler = logging.StreamHandler(_resolve_stream())
    handler.setFormatter(formatter)
    setattr(handler, _OUR_HANDLER_ATTR, True)

    # 全项目唯一的 stdlib root logger 操作点：先摘掉本模块上次装的 handler（幂等重装），
    # 再挂唯一出口。绝不触碰第三方各自命名的小 logger，让它们继续向 root 冒泡。
    root = logging.getLogger()
    for old in list(root.handlers):
        if getattr(old, _OUR_HANDLER_ATTR, False):
            root.removeHandler(old)
    root.addHandler(handler)
    root.setLevel(level)

    _configured = True


def reset_logging() -> None:
    """测试钩子：清除装配标记，使下次 configure_logging() 真正重配。"""
    global _configured
    root = logging.getLogger()
    for old in list(root.handlers):
        if getattr(old, _OUR_HANDLER_ATTR, False):
            root.removeHandler(old)
    _configured = False


def ensure_configured() -> None:
    """惰性装配：任何取 logger 的路径都保证配置已就位（进程 import 顺序无关）。"""
    if not _configured:
        configure_logging()


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """便捷工厂（保证装配先行）。模块亦可直接用 `structlog.get_logger(__name__)`。"""
    ensure_configured()
    return structlog.get_logger(name)
