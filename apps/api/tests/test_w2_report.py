"""W2 日报组装与 LLM 降级单测（验收 5）：纯函数 / 注入 LLM，零 DB 依赖。

断言：
- LLM 成功 → 摘要为 LLM 输出；
- LLM 返回 None / 抛异常 → 降级为中心文章正文首段截断 150 字；
- assemble_report 含热度行与摘要段（无 LLM 也能产出日报）。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.feed_service import _fallback_summary, _topic_summary, assemble_report


def _topic(title: str, *, score: float = 5.0, sources: int = 2, articles: int = 3) -> SimpleNamespace:
    return SimpleNamespace(id="t1", title=title, hot_score=score, source_count=sources, article_count=articles)


async def _llm_ok(title: str, body: str) -> str | None:
    return "这是 LLM 生成的中文摘要。"


async def _llm_none(title: str, body: str) -> str | None:
    return None


async def _llm_raises(title: str, body: str) -> str | None:
    raise RuntimeError("LLM down")


@pytest.mark.asyncio
async def test_topic_summary_uses_llm_when_ok() -> None:
    t = _topic("测试热点")
    assert await _topic_summary(t, "正文内容", _llm_ok) == "这是 LLM 生成的中文摘要。"


@pytest.mark.asyncio
async def test_topic_summary_degrades_on_none() -> None:
    t = _topic("测试热点")
    body = "第一段正文内容比较长需要截断。" * 20
    summary = await _topic_summary(t, body, _llm_none)
    # 降级 = 首段（此处无换行即整段）截断 150 字
    assert summary == body.strip()[:150]


@pytest.mark.asyncio
async def test_topic_summary_degrades_on_exception() -> None:
    t = _topic("测试热点")
    body = "首段内容。"
    assert await _topic_summary(t, body, _llm_raises) == "首段内容。"


@pytest.mark.asyncio
async def test_topic_summary_default_uses_real_llm_then_degrades() -> None:
    """llm=None → 走真实 summarize_topic；无 API key 时返回 None → 降级正文首段。"""
    t = _topic("测试热点")
    body = "降级源正文。"
    assert await _topic_summary(t, body, None) == "降级源正文。"


def test_fallback_summary_first_paragraph_truncated() -> None:
    body = "首段内容。\n第二段不应出现。"
    assert _fallback_summary(body) == "首段内容。"
    long = "字" * 300
    assert len(_fallback_summary(long)) == 150


def test_assemble_report_with_and_without_topics() -> None:
    t = _topic("热点一", score=12.0)
    md = assemble_report("2026-09-30", [t], ["摘要一"])
    assert "# BotHot 热点日报 · 2026-09-30" in md
    assert "## 1. 热点一" in md
    assert "**热度**: 12.0" in md
    assert "摘要一" in md

    empty = assemble_report("2026-09-30", [], [])
    assert "今日暂无热点事件。" in empty
