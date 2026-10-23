"""日志出口的凭据遮蔽（STEP-40，P-113 / P-112②）。

为什么需要它
--------------
本进程有三类"把 URL 原样写进日志"的路，且都不经过任何业务代码：

1. ``httpx`` 在 INFO 级为**每一次出站请求**打一行 ``HTTP Request: POST <完整 URL>``，
   经 root 冒泡到本项目唯一的 handler（``app.core.logging``）。推送渠道的凭据就在 URL 里：
   钉钉 ``?access_token=``、企业微信 ``?key=``、飞书 ``/hook/<token>``；采集侧 JustOneAPI
   的 ``?token=`` 也一样。⇒ 每推一次、每采一次，凭据进一次日志。
2. ``httpx.HTTPStatusError`` 的 ``str(exc)`` 自带 ``for url '<完整 URL>'``，各 provider 的
   ``logger.warning("...: %s", exc)`` 会把它原样带出。
3. 访问日志 / 审计里的入站路径与 query 由调用方决定。

做法：不在每个调用点各修一遍（漏一处就白修），而是在**唯一出口**——handler 的
``ProcessorFormatter`` 渲染完成之后——对整行文本做一次遮蔽。原生 structlog 日志、
第三方 stdlib 日志、异常栈（渲染器把 exc_info 展开进同一字符串）都经过这里。

规则（只动 URL，不碰其他文本）
-------------------------------
- 绝对 URL（``scheme://host/...``）与以 ``/`` 开头的请求路径：``?`` 之后整段 query
  换成 ``?‹已省略›``；``#`` 片段同理。query 里全是诊断价值低、凭据风险高的东西，
  逐参数名白名单维护不起来（各家参数名都不同），所以整段省略。
- 绝对 URL 的路径段：形如令牌的段（≥ 16 个 ``[A-Za-z0-9_-]`` 字符，或 UUID 形）
  换成 ``‹已遮蔽›``。主机名保留——"打到了哪家"是排障要的信息，它不是凭据。
- 相对路径不做路径段遮蔽：入站路径里的 UUID 是资源 id，审计要它；入站路径由路由
  模板约束，自由文本形状的段另由审计侧处理（``app.core.audit``）。

局限：只认 ``http(s)://`` / ``ws(s)://`` 形的 URL 与 ``/`` 开头的路径；把凭据写成
裸字符串打日志（不在 URL 里）的路不归本函数管，那是调用点的错误，由审查与 gitleaks 兜。
"""

from __future__ import annotations

import re
from typing import Any

QUERY_PLACEHOLDER = "‹已省略›"
SEGMENT_PLACEHOLDER = "‹已遮蔽›"

# 绝对 URL：scheme://host[:port] + 可选路径 + 可选 query/fragment。
# 终止符取日志里常见的包围字符：空白、引号、尖括号、反斜杠（JSON 转义）。
_ABS_URL = re.compile(
    r"""(?P<head>\b(?:https?|wss?)://[^\s/?#"'<>\\]+)(?P<path>/[^\s?#"'<>\\]*)?(?P<rest>[?#][^\s"'<>\\]*)?"""
)

# 相对路径带 query：前面是行首、空白或引号，路径以 / 开头。
_REL_QUERY = re.compile(r"""(?P<lead>(?:^|(?<=[\s"'(=])))(?P<path>/[^\s?#"'<>\\]*)(?P<rest>[?#][^\s"'<>\\]*)""")

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_TOKENISH = re.compile(rf"^(?:[A-Za-z0-9_-]{{16,}}|{_UUID})$")


def _mask_segments(path: str) -> str:
    if not path:
        return path
    return "/".join(SEGMENT_PLACEHOLDER if _TOKENISH.match(seg) else seg for seg in path.split("/"))


def _abs_sub(m: re.Match[str]) -> str:
    out = m.group("head") + _mask_segments(m.group("path") or "")
    if m.group("rest"):
        out += m.group("rest")[0] + QUERY_PLACEHOLDER
    return out


def _rel_sub(m: re.Match[str]) -> str:
    return m.group("lead") + m.group("path") + m.group("rest")[0] + QUERY_PLACEHOLDER


def redact_text(text: str) -> str:
    """对一段已渲染的日志文本做 URL 遮蔽；不含 URL 的文本原样返回（同一对象）。"""
    if "/" not in text:
        return text
    out = _ABS_URL.sub(_abs_sub, text)
    return _REL_QUERY.sub(_rel_sub, out)


def redact_rendered(_logger: Any, _name: str, rendered: Any) -> Any:
    """挂在 ``ProcessorFormatter`` 渲染器**之后**的处理器：入参已是最终字符串。"""
    if isinstance(rendered, str):
        return redact_text(rendered)
    return rendered
