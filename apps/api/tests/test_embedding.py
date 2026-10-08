"""B-T1 验收测试：嵌入配置读取 + OpenAI 兼容嵌入客户端契约。

不使用真实网络：全部走 httpx.MockTransport；密钥只经环境变量注入。
"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.providers.embedding import (
    EmbeddingProviderError,
    OpenAICompatEmbeddingClient,
    build_embedding_client,
)


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    """构造带 MockTransport 的测试客户端（base_url 与生产形态一致）。"""
    return httpx.AsyncClient(transport=handler, base_url="https://api.siliconflow.cn/v1")


def _ok_body(*vectors: list[float]) -> dict:
    return {
        "model": "BAAI/bge-m3",
        "data": [{"index": i, "embedding": vec} for i, vec in enumerate(vectors)],
        "usage": {"prompt_tokens": 8, "total_tokens": 8},
    }


# ---------------------------------------------------------------- 配置读取


def test_settings_embedding_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认值与 docker/compose.yml 的兜底一致（env 无关化：真实冒烟轮注入 Key 不影响本用例）。"""
    for key in (
        "EMBEDDING_API_BASE",
        "EMBEDDING_API_KEY",
        "EMBEDDING_MODEL",
        "LLM_API_BASE",
        "LLM_API_KEY",
        "LLM_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]  # pydantic-settings 运行时合法，类型桩缺失
    assert settings.embedding_api_base == "https://api.siliconflow.cn/v1"
    assert settings.embedding_api_key == ""
    assert settings.embedding_model == "BAAI/bge-m3"


def test_settings_embedding_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """三项环境变量均生效（大小写不敏感由 pydantic-settings 保证）。"""
    monkeypatch.setenv("EMBEDDING_API_BASE", "https://emb.example.com/v1")
    monkeypatch.setenv("EMBEDDING_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("EMBEDDING_MODEL", "BAAI/bge-large-zh-v1.5")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]  # pydantic-settings 运行时合法，类型桩缺失
    assert settings.embedding_api_base == "https://emb.example.com/v1"
    assert settings.embedding_api_key == "sk-test-not-real"
    assert settings.embedding_model == "BAAI/bge-large-zh-v1.5"


def test_build_embedding_client_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """工厂按 Settings 构造客户端，模型名可被 LangBot 注册复用。"""
    monkeypatch.setenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    get_settings.cache_clear()
    try:
        client = build_embedding_client()
    finally:
        get_settings.cache_clear()
    assert isinstance(client, OpenAICompatEmbeddingClient)
    assert client.model == "BAAI/bge-m3"


# ---------------------------------------------------------------- 请求契约


async def test_embed_request_body_and_auth() -> None:
    """请求路径、JSON body、Bearer 头均符合 OpenAI 兼容协议。"""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_ok_body([0.1, 0.2], [0.3, 0.4]))

    async with _client(httpx.MockTransport(handler)) as http:
        client = OpenAICompatEmbeddingClient(
            "https://api.siliconflow.cn/v1/", "sk-test-key", "BAAI/bge-m3", client=http
        )
        vectors = await client.embed(["第一篇", "第二篇"])

    assert len(captured) == 1
    request = captured[0]
    # base_url 含 /v1 前缀，与 /embeddings 拼接后即硅基流动真实端点 /v1/embeddings
    assert request.url.path == "/v1/embeddings"
    assert request.headers["Authorization"] == "Bearer sk-test-key"
    body = httpx.Response(200, content=request.content).json()
    assert body["model"] == "BAAI/bge-m3"
    assert body["input"] == ["第一篇", "第二篇"]
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


async def test_embed_no_auth_header_when_key_empty() -> None:
    """Key 缺失时不伪造鉴权头，交由上游返回 401（符合"密钥不硬编码"铁律）。"""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(401, json={"error": "invalid api key"})

    async with _client(httpx.MockTransport(handler)) as http:
        client = OpenAICompatEmbeddingClient("https://api.siliconflow.cn/v1", "", "BAAI/bge-m3", client=http)
        with pytest.raises(EmbeddingProviderError) as exc:
            await client.embed(["文本"])

    assert "Authorization" not in captured[0].headers
    assert exc.value.status_code == 401


async def test_embed_empty_input_skips_request() -> None:
    """空入参直接返回，不发起请求（避免无意义计费）。"""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_ok_body([0.1]))

    async with _client(httpx.MockTransport(handler)) as http:
        client = OpenAICompatEmbeddingClient("https://x/v1", "k", "m", client=http)
        assert await client.embed([]) == []
    assert calls == 0


# ---------------------------------------------------------------- 响应解析


async def test_embed_restores_input_order_by_index() -> None:
    """上游乱序返回时按 index 还原入参顺序。"""
    body = {
        "data": [
            {"index": 1, "embedding": [0.9, 0.9]},
            {"index": 0, "embedding": [0.1, 0.1]},
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    async with _client(httpx.MockTransport(handler)) as http:
        client = OpenAICompatEmbeddingClient("https://x/v1", "k", "m", client=http)
        vectors = await client.embed(["A", "B"])

    assert vectors == [[0.1, 0.1], [0.9, 0.9]]


async def test_embed_one_returns_single_vector() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_body([1.0, 2.0, 3.0]))

    async with _client(httpx.MockTransport(handler)) as http:
        client = OpenAICompatEmbeddingClient("https://x/v1", "k", "m", client=http)
        assert await client.embed_one("单条") == [1.0, 2.0, 3.0]


@pytest.mark.parametrize(
    "body",
    [
        {"data": []},  # 条数不符
        {"data": [{"index": 0}]},  # 缺 embedding
        {"data": [{"index": 0, "embedding": []}]},  # 空向量
        {"data": [{"index": 0, "embedding": ["x", 1]}]},  # 非数值
        {"error": "bad request"},  # 无 data
    ],
)
async def test_embed_malformed_response_raises(body: dict) -> None:
    """响应形态不符一律视为上游异常，不静默降级。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    async with _client(httpx.MockTransport(handler)) as http:
        client = OpenAICompatEmbeddingClient("https://x/v1", "k", "m", client=http)
        with pytest.raises(EmbeddingProviderError):
            await client.embed(["文本"])


async def test_embed_upstream_5xx_and_network_error() -> None:
    """5xx 保留状态码；网络异常不伪装成业务错误。"""

    def server_error(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    async with _client(httpx.MockTransport(server_error)) as http:
        client = OpenAICompatEmbeddingClient("https://x/v1", "k", "m", client=http)
        with pytest.raises(EmbeddingProviderError) as exc:
            await client.embed(["文本"])
    assert exc.value.status_code == 503

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with _client(httpx.MockTransport(boom)) as http:
        client = OpenAICompatEmbeddingClient("https://x/v1", "k", "m", client=http)
        with pytest.raises(EmbeddingProviderError) as exc:
            await client.embed(["文本"])
    assert exc.value.status_code is None
