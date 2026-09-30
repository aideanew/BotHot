"""推送模板渲染与校验。

支持变量：{date} {time} {space_name} {doc_title} {hot_topic} {topic_count} {report_title}
未知变量剔除并 logging.warning。
时区口径（WB）：{date}/{time} 用热点业务日界 Asia/Shanghai（与 hot.py/hot_cluster.py
的 BUSINESS_TZ 同口径），不再用 UTC。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

BUSINESS_TZ = ZoneInfo("Asia/Shanghai")

_KNOWN_VARS = {"date", "time", "space_name", "doc_title", "hot_topic", "topic_count", "report_title"}

_VAR_PATTERN = re.compile(r"\{(\w+)\}")


def render(template: str, variables: dict) -> str:
    now = datetime.now(BUSINESS_TZ)
    ctx = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "space_name": variables.get("space_name", ""),
        "doc_title": variables.get("doc_title", ""),
        "hot_topic": variables.get("hot_topic", ""),
        "topic_count": str(variables.get("topic_count", "")),
        "report_title": variables.get("report_title", ""),
    }

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        if var_name not in _KNOWN_VARS:
            logger.warning("未知模板变量 {%s}，已剔除", var_name)
            return ""
        return ctx.get(var_name, "")

    return _VAR_PATTERN.sub(_replace, template)


def validate_template(template: str) -> str | None:
    if not template or not template.strip():
        return "模板内容不能为空"

    for match in _VAR_PATTERN.finditer(template):
        var_name = match.group(1)
        if var_name not in _KNOWN_VARS:
            return f"未知变量 {{{var_name}}}，合法变量：{', '.join(sorted(_KNOWN_VARS))}"

    return None
