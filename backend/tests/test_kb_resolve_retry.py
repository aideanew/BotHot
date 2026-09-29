"""回归：非文章链接不得被 NameError 吞掉重试语义（浏览器实测缺陷）。

`_resolve_with_retry` 的 except 子句本意是「业务异常不重试、原样上抛」，但 kb.py 曾漏引
`SourceUrlUnrecognizedError`：该子句一执行就抛 NameError，于是所有非文章链接都被当成
未预期异常退避重试 3 次（1s+2s），最终把
"NameError: name 'SourceUrlUnrecognizedError' is not defined" 原样写进 job_items.error，
在任务中心的篇目明细里暴露给用户。
"""

import pytest

from app.core.errors import ExtractQualityLowError, SourceUrlUnrecognizedError
from app.services.kb import KnowledgeBaseService


class _StubResolver:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    async def resolve(self, url: str):  # noqa: ANN201
        self.calls += 1
        raise self.exc


def _kb(exc: Exception):
    """只挂 resolver 的最小实例：_resolve_with_retry 仅依赖 self._resolver。"""
    svc = KnowledgeBaseService.__new__(KnowledgeBaseService)
    svc._resolver = _StubResolver(exc)
    return svc, svc._resolver


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """退避基数置零：真值 1.0s 会让瞬时错误用例实睡 3 秒。"""
    monkeypatch.setattr(KnowledgeBaseService, "_RESOLVE_BACKOFF_BASE", 0.0)


async def test_source_unrecognized_not_retried_and_not_masked() -> None:
    """域错误一次即抛（不重试），且抛出的仍是域错误而非 NameError。"""
    exc = SourceUrlUnrecognizedError("页面不是公众号文章（锚点缺失）")
    svc, resolver = _kb(exc)

    with pytest.raises(SourceUrlUnrecognizedError) as raised:
        await svc._resolve_with_retry("https://mp.weixin.qq.com/s/nope")

    assert resolver.calls == 1, f"域错误不应重试，实际调用 {resolver.calls} 次"
    assert raised.value.code == 20001


async def test_quality_low_not_retried() -> None:
    """低质同样是域错误：不重试、原样上抛。"""
    svc, resolver = _kb(ExtractQualityLowError())

    with pytest.raises(ExtractQualityLowError):
        await svc._resolve_with_retry("https://mp.weixin.qq.com/s/low")

    assert resolver.calls == 1


async def test_transient_error_retries_then_raises() -> None:
    """未预期异常仍走有限重试（口径未被域错误分支误伤）。"""
    svc, resolver = _kb(RuntimeError("网络抖动"))

    with pytest.raises(RuntimeError):
        await svc._resolve_with_retry("https://mp.weixin.qq.com/s/flaky")

    assert resolver.calls == KnowledgeBaseService._RESOLVE_MAX_ATTEMPTS
