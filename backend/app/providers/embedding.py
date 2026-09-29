"""嵌入服务客户端（OpenAI 兼容 `/embeddings` 协议）。

定位：外部系统的唯一防腐层之一。只做协议适配，不做任何业务判断。
密钥只经 Settings（环境变量）注入，禁止硬编码、禁止写入测试与文档。

契约要点（与 M0 报告 §四 中 LangBot embedding 模型注册配套）：
  - 请求：POST {base_url}/embeddings，body {"model": ..., "input": [text, ...]}
  - 鉴权：Authorization: Bearer <key>（key 为空时不发该头，由上游返回 401）
  - 响应：{"data": [{"index": 0, "embedding": [float, ...]}, ...]}
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings, get_settings


class EmbeddingProviderError(RuntimeError):
    """嵌入服务调用失败或响应不可解析。

    只承载上游事实（HTTP 状态、原始原因），**不定义业务错误码**；
    到统一信封的映射由全局异常处理器负责（契约归 A，见 B-T2）。
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class OpenAICompatEmbeddingClient:
    """OpenAI 兼容的嵌入客户端。

    支持注入 httpx.AsyncClient（测试用 MockTransport 或自定义 transport），
    便于在不发起真实网络请求的前提下验证请求体与响应解析。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        # 仅当客户端由本类创建时才负责关闭，避免误关调用方传入的连接池
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    @property
    def model(self) -> str:
        """当前生效的模型名（供 LangBot 模型注册复用）。"""
        return self._model

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> OpenAICompatEmbeddingClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """对一批文本取向量，返回顺序与入参一致。

        空列表直接返回，不发起请求（避免无意义的上游计费）。
        """
        if not texts:
            return []

        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            response = await self._client.post(
                "/embeddings",
                json={"model": self._model, "input": texts},
                headers=headers,
            )
        except httpx.HTTPError as exc:  # 连接失败/超时：上游不可用
            raise EmbeddingProviderError(f"嵌入服务不可达: {exc}") from exc

        if response.status_code >= 400:
            raise EmbeddingProviderError(
                f"嵌入服务返回 {response.status_code}: {response.text[:200]}",
                status_code=response.status_code,
            )
        return self._parse_embeddings(response.json(), expected=len(texts))

    async def embed_one(self, text: str) -> list[float]:
        """单条文本便捷入口。"""
        vectors = await self.embed([text])
        return vectors[0]

    @staticmethod
    def _parse_embeddings(body: Any, *, expected: int) -> list[list[float]]:
        """解析 OpenAI 兼容响应；任何形态不符都视为上游异常而非静默降级。"""
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list) or len(data) != expected:
            raise EmbeddingProviderError("嵌入响应缺少 data 或条数与入参不一致")

        vectors: list[list[float]] = []
        # 上游不保证 data 顺序，按 index 还原入参顺序
        for item in sorted(data, key=lambda row: (row or {}).get("index", 0)):
            vector = (item or {}).get("embedding") if isinstance(item, dict) else None
            if not isinstance(vector, list) or not vector:
                raise EmbeddingProviderError("嵌入响应缺少 embedding 向量")
            if not all(isinstance(value, int | float) for value in vector):
                raise EmbeddingProviderError("嵌入向量含非数值元素")
            vectors.append([float(value) for value in vector])
        return vectors


def build_embedding_client(
    settings: Settings | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> OpenAICompatEmbeddingClient:
    """按配置构造嵌入客户端（生产入口）。"""
    settings = settings or get_settings()
    return OpenAICompatEmbeddingClient(
        base_url=settings.embedding_api_base,
        api_key=settings.embedding_api_key,
        model=settings.embedding_model,
        client=client,
    )
