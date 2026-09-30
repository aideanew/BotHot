"""W2 LLM 摘要：httpx 非流式直连 SiliconFlow（OpenAI 兼容协议）。

口径（AGENTS.md 关键约束 5）：LLM 直连 SiliconFlow，不经 LangBot 转发。
本模块用**非流式** chat/completions（日报摘要场景无需流式）。

失败语义（任务 2.5a）：超时 / 非 2xx / 空返回 / 配置缺失 → 一律返回 None，**绝不抛穿**。
调用方（feed_service.build_daily_report）对 None 走降级（中心文章正文首段截断），
日报永不因 LLM 故障缺失。
"""

from __future__ import annotations

import httpx
import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = 30.0
_MAX_BODY_CHARS = 2000  # 入 prompt 的素材正文上限，控成本


async def chat_completion(messages: list[dict[str, str]], *, timeout: float = _DEFAULT_TIMEOUT) -> str | None:
    """非流式 chat/completions；任何失败返回 None。"""
    s = get_settings()
    if not s.llm_api_key:
        logger.info("llm_summary 跳过：llm_api_key 未配置")
        return None
    url = s.llm_api_base.rstrip("/") + "/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {s.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": s.llm_model,
                    "messages": messages,
                    "stream": False,
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                return None
            content = choices[0].get("message", {}).get("content")
            if not content:
                return None
            return str(content).strip() or None
    except Exception:  # noqa: BLE001 绝不抛穿：调用方走降级
        logger.warning("llm_summary 调用失败（已降级）", exc_info=True)
        return None


async def summarize_topic(title: str, body: str, *, max_chars: int = 200) -> str | None:
    """为单个热点生成中文摘要；失败返回 None（由调用方降级）。"""
    snippet = (body or "")[:_MAX_BODY_CHARS]
    user_msg = (
        f"你是热点新闻编辑。请用不超过 {max_chars} 字的简体中文，为以下热点写一段客观摘要，"
        f"概括事件核心，不要复述标题、不要加无关套话。\n\n"
        f"标题：{title}\n\n素材：\n{snippet}"
    )
    return await chat_completion(
        [
            {"role": "system", "content": "你是资深热点新闻编辑，擅长精炼中文摘要。"},
            {"role": "user", "content": user_msg},
        ]
    )
