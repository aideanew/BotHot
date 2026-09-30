"""WC 3.2 引擎删除降级单测：未实接引擎 delete_kb 返回 None（本地可清信号）不抛。"""

from __future__ import annotations

import pytest

from app.providers.engine_port import LangBotAdapter, RagflowAdapter, SaasAdapter


class _FakeLangbotClient:
    """记录 delete_kb 调用的桩客户端。"""

    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete_kb(self, kb_uuid: str) -> None:
        self.deleted.append(kb_uuid)


@pytest.mark.asyncio
async def test_ragflow_delete_kb_noop_when_unimplemented() -> None:
    """RagflowAdapter（implemented=False）delete_kb 返回 None，不抛 NotImplementedError。"""
    a = RagflowAdapter(api_base="http://x", api_key="k")
    assert a.implemented is False
    result = await a.delete_kb("kb-1")
    assert result is None  # 本地可清信号


@pytest.mark.asyncio
async def test_saas_delete_kb_noop_when_unimplemented() -> None:
    """SaasAdapter（implemented=False）delete_kb 返回 None，不抛。"""
    for name in ("coze", "dify", "fastgpt"):
        a = SaasAdapter(name, api_key="k")
        assert a.implemented is False
        assert await a.delete_kb("kb-1") is None


@pytest.mark.asyncio
async def test_unimplemented_other_methods_still_raise() -> None:
    """降级只针对 delete_kb：其余方法（retrieve/delete_file）未实接仍明确报错。"""
    a = RagflowAdapter(api_base="http://x", api_key="k")
    # implemented=False → available=False → _require() 抛 RuntimeError（未配置可用）
    with pytest.raises(RuntimeError):
        await a.retrieve("kb-1", "q")
    with pytest.raises(RuntimeError):
        await a.delete_file("kb-1", "f-1")


@pytest.mark.asyncio
async def test_langbot_delete_kb_calls_client() -> None:
    """builtin 引擎删除行为零回归：仍调 client.delete_kb。"""
    fake = _FakeLangbotClient()
    a = LangBotAdapter(fake)
    await a.delete_kb("kb-1")
    assert fake.deleted == ["kb-1"]
