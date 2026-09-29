"""阶段 3.2 检索重排端口（硅基流动 bge-reranker-v2-m3；ADR-0004 同级防腐层）。

口径（大纲 3.2.1）：retrieve 宽取候选（top_k=20）→ rerank → 取前 5。

设计约束（三条，都是纪律而非偏好）：
- **可选增强**：Key 未配置 / 显式关闭 → `NoopReranker`（显式不可用，不假装可用）；
- **失败不致命**：上游 4xx/5xx/网络异常/响应缺分 → 返回 `None`，调用方保序截断回退
  （不新增错误码，避免把可选优化变成问答硬依赖）；
- **Key 纪律**：只读 settings（env），代码零明文（ADR-0004 §三.4）。

实测契约（2026-09-17 活体探针，https://api.siliconflow.cn/v1/rerank）：
  POST {base}/rerank，头 `Authorization: Bearer <key>`
  body `{model, query, documents, top_n, return_documents:false}`
  200 → `{"results":[{"index":i,"relevance_score":s,"document":null}...],"meta":{...}}`
  注：上游 results 实测已按分数降序，但本端口**不依赖上游顺序**——按 index 回填成
  「原序等长分数表」后交由调用方排序（上游乱序/裁剪均可正确工作）。
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)

DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
DEFAULT_TIMEOUT = 10.0


class RerankerPort(Protocol):
    """重排端口：文档集合 → 与入参等长的相关性分数表（None = 不可用/失败）。"""

    name: str

    def available(self) -> bool: ...

    async def rerank(self, query: str, documents: list[str]) -> list[float] | None: ...


class NoopReranker:
    """停用态（Key 缺失 / 显式关闭）：显式不可用，调用方保序（零行为变更）。"""

    name = "none"

    def available(self) -> bool:
        return False

    async def rerank(self, query: str, documents: list[str]) -> list[float] | None:
        return None


class SiliconflowReranker:
    """硅基流动 rerank 适配器（BAAI/bge-reranker-v2-m3）。"""

    name = "siliconflow"

    def __init__(
        self,
        api_base: str,
        api_key: str,
        model: str = DEFAULT_RERANK_MODEL,
        http: httpx.AsyncClient | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._model = model or DEFAULT_RERANK_MODEL
        self._http = http
        self._timeout = timeout

    def available(self) -> bool:
        return bool(self._api_base and self._api_key)

    async def rerank(self, query: str, documents: list[str]) -> list[float] | None:
        if not documents:
            return []  # 空候选：零请求、零分数（不产生上游计费）
        if not self.available():
            return None
        payload = {
            "model": self._model,
            "query": query,
            "documents": documents,
            "top_n": len(documents),
            "return_documents": False,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._api_base}/rerank"
        try:
            if self._http is not None:
                resp = await self._http.post(url, json=payload, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as http:
                    resp = await http.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("rerank 调用失败（保序回退）: %s", exc)
            return None
        if resp.status_code >= 400:
            logger.warning("rerank 上游 %s（保序回退）: %s", resp.status_code, resp.text[:160])
            return None
        try:
            data = resp.json()
        except ValueError as exc:
            logger.warning("rerank 响应非 JSON（保序回退）: %s", exc)
            return None
        return _scores_from_payload(data, len(documents))


def _scores_from_payload(data: Any, expected: int) -> list[float] | None:
    """响应 → 原序等长分数表；缺项/越界/非数值 → None（保序回退，不猜分）。"""
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return None
    scores: list[float | None] = [None] * expected
    for entry in results:
        if not isinstance(entry, dict):
            continue
        index = entry.get("index")
        score = entry.get("relevance_score")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < expected:
            continue
        if isinstance(score, bool) or not isinstance(score, int | float):
            continue
        scores[index] = float(score)
    if any(score is None for score in scores):
        return None  # 上游未覆盖全部文档：排序不确定 → 交回调用方保序
    return [float(score) for score in scores if score is not None]


def make_reranker(settings: Any = None) -> RerankerPort:
    """按配置装配重排器（未配置/显式关闭 → NoopReranker，显式不可用不假装可用）。

    - `rerank_enabled=False` → 停用；
    - `rerank_api_base/key` 留空 → 回落 `embedding_*`（同供应商硅基流动，M0 起已配）；
    - 二者皆空 → 停用（本地/离线环境默认零外部依赖）。
    """
    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()
    if not bool(getattr(settings, "rerank_enabled", True)):
        return NoopReranker()
    api_base = str(getattr(settings, "rerank_api_base", "") or getattr(settings, "embedding_api_base", "") or "")
    api_key = str(getattr(settings, "rerank_api_key", "") or getattr(settings, "embedding_api_key", "") or "")
    if not api_base or not api_key:
        return NoopReranker()
    model = str(getattr(settings, "rerank_model", "") or DEFAULT_RERANK_MODEL)
    return SiliconflowReranker(api_base, api_key, model)
