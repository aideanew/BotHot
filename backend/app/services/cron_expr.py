"""Cron 表达式解析与校验。

接口契约（W1 交付，W3 消费）：
- parse_cron_next(expr: str, now: datetime) -> datetime | None
- validate_cron(expr: str) -> str | None（合法返回 None，非法返回错误描述）

支持标准 5 段 cron 表达式（分 时 日 月 周），使用 croniter 库。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from croniter import croniter
except ImportError:
    croniter = None  # type: ignore[assignment]


def _translate_shorthand(expr: str) -> str:
    """将简写 cron 表达式转为标准 5 段格式。

    - HH:MM → M H * * *  （如 10:00 → 0 10 * * *）
    - */N   → 0 */N * * * （如 */2  → 0 */2 * * *）
    - N     → */N * * *   （如 5    → */5 * * *）
    """
    expr = expr.strip()

    if re.fullmatch(r"\d{1,2}:\d{2}", expr):
        hh, mm = expr.split(":")
        return f"{int(mm)} {int(hh)} * * *"

    if re.fullmatch(r"\*/\d+", expr):
        return f"0 {expr} * * *"

    if re.fullmatch(r"\d+", expr):
        return f"*/{expr} * * * *"

    return expr


def validate_cron(expr: str) -> str | None:
    """校验 cron 表达式合法性。

    Returns:
        None 表示合法，否则返回错误描述字符串。
    """
    if croniter is None:
        return "croniter 库未安装，无法校验 cron 表达式"

    expr = expr.strip()
    if not expr:
        return "cron 表达式不能为空"

    translated = _translate_shorthand(expr)
    try:
        croniter(translated)
        return None
    except Exception as exc:
        return f"非法 cron 表达式: {exc}"


def parse_cron_next(expr: str, now: datetime) -> datetime | None:
    """计算 cron 表达式在 now 之后的下次执行时间。

    Args:
        expr: 标准 5 段 cron 表达式
        now: 当前时间（带时区）

    Returns:
        下次执行时间；解析失败返回 None。
    """
    if croniter is None:
        logger.warning("croniter 库未安装，parse_cron_next 返回 None")
        return None

    expr = expr.strip()
    if not expr:
        return None

    translated = _translate_shorthand(expr)
    try:
        itr = croniter(translated, now)
        return itr.get_next(datetime)
    except Exception as exc:
        logger.warning("cron 表达式解析失败: %s (translated=%s), error=%s", expr, translated, exc)
        return None
