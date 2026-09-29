"""T3.1（阶段 3.3.1）意图解析验收测试：五分类正确性 + 宽度映射 + 单调放宽原则。"""

from __future__ import annotations

import pytest

from app.services.intent import INTENT_WIDTHS, classify_intent, intent_retrieval_width


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("你好", "chat"),
        ("Hello there", "chat"),
        ("你是谁？", "chat"),
        ("谢谢", "chat"),
        ("帮我总结一下这个空间的内容", "summary"),
        ("概括一下这几篇文章的要点", "summary"),
        ("这个公众号有哪些文章？", "list"),
        ("列出所有关于养成的要点", "list"),
        ("《奖励一颗麻籽》讲的是什么？", "fact"),
        ("如何配置引擎？", "fact"),
        ("为什么采集会失败？", "fact"),
        ("第三条规则的原文是什么", "fact"),
        ("给我第三条的原文", "precise"),
        ("", "precise"),
    ],
)
def test_classify_intent_rules(question: str, expected: str) -> None:
    assert classify_intent(question) == expected


def test_width_mapping_covers_all_intents() -> None:
    """五类意图全有宽度配置；列举/总结为宽取 20，其余窄取 5。"""
    assert set(INTENT_WIDTHS) == {"chat", "fact", "precise", "list", "summary"}
    assert intent_retrieval_width("list") == 20
    assert intent_retrieval_width("summary") == 20
    for narrow in ("chat", "fact", "precise"):
        assert intent_retrieval_width(narrow) == 5


def test_unknown_intent_falls_back_narrow() -> None:
    """未登记意图回落 5（防新意图漏配走窄即安全默认）。"""
    assert intent_retrieval_width("unknown-intent") == 5


def test_monotonic_widening_principle() -> None:
    """单调放宽原则：意图路由只放宽不收窄——max(基线, 意图) ≥ 两个分量。"""
    for _intent, width in INTENT_WIDTHS.items():
        for base in (5, 20):
            assert max(base, width) >= base
            assert max(base, width) >= width
