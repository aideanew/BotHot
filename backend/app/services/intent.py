"""阶段 3.3.1（T3.1）意图解析：轻量五分类 → 检索宽度路由。

设计口径（2026-09-22，本卡落地）：
- 分类器 = 规则版（确定性、零额外 LLM 往返、离线可测）；LLM 分类为升级位
  （classify_intent 预留 llm 参数形状，接缓存层后再排产，避免 ask 热路径加延迟）；
- 宽度路由单调放宽原则：意图宽度只可能 **大于等于** 原基线（过滤/重排开启=20、
  否则 5），即 max(基线, 意图宽度)——对既有行为零回归（绝不收窄）；
- 五分类与宽度：
    chat    寒暄/身份类          → 5（窄，问答无实义）
    fact    事实型（是什么/如何）  → 5（窄）
    precise 精确指代/其他         → 5（窄）
    list    列举型（有哪些/列出）  → 20（宽，防召回塌陷）
    summary 总结型（总结/概括）    → 20（宽）
"""

from __future__ import annotations

CHAT_PATTERNS = ("你好", "您好", "hi", "hello", "你是谁", "谢谢", "再见")
SUMMARY_PATTERNS = ("总结", "概括", "摘要", "归纳")
LIST_PATTERNS = ("有哪些", "列举", "列出", "多少种", "哪些", "几条")
FACT_PATTERNS = ("什么", "如何", "怎么", "为什么", "何时", "哪里", "谁")

INTENT_WIDTHS: dict[str, int] = {
    "chat": 5,
    "fact": 5,
    "precise": 5,
    "list": 20,
    "summary": 20,
}


def classify_intent(question: str) -> str:
    """规则版五分类：chat → summary → list → fact → precise（先命中先得）。"""
    q = (question or "").strip().lower()
    if not q:
        return "precise"
    if any(p in q for p in CHAT_PATTERNS):
        return "chat"
    if any(p in q for p in SUMMARY_PATTERNS):
        return "summary"
    if any(p in q for p in LIST_PATTERNS):
        return "list"
    if any(p in q for p in FACT_PATTERNS):
        return "fact"
    return "precise"


def intent_retrieval_width(intent: str) -> int:
    """意图 → 检索宽度（INTENT_WIDTHS 未知名回落 5，防新意图漏配走窄）。"""
    return INTENT_WIDTHS.get(intent, 5)
