"""STEP-10 S10.V15.1：详情报文兜底接进入库链路（默认关，免费直抓永远先跑）。

先红判据（改前）：AST 现读全仓 `ArticleDetailFallbackCoordinator` 实例化 0 处；
`make_default_ingest` 没有把协调器注入 `KnowledgeBaseService`；开关开且免费直抓失败时
付费 provider 调用 0 次（因为根本没人接）。改后三档计数：关 ⇒ 0 次；开且免费成功 ⇒ 0 次；
开且免费失败 ⇒ 恰 1 次（按成本升序第一家命中即止）。
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.core.errors import ExtractFailedError
from app.providers.article_sources.base import ArticleDetail
from app.services.article_detail_fallback import ArticleDetailFallbackCoordinator
from app.services.extractor import ExtractorService
from app.services.kb import KnowledgeBaseService
from app.services.normalizer import normalize_extracted
from app.services.quality import score_quality
from app.services.resolver import ResolvedArticle

_APP = Path(__file__).resolve().parents[1] / "app"
_URL = "https://mp.weixin.qq.com/s/v15-wiring"


class _StubResolver:
    def __init__(self, *, result: ResolvedArticle | None = None, exc: Exception | None = None) -> None:
        self.result = result
        self.exc = exc
        self.calls = 0

    async def resolve(self, url: str) -> ResolvedArticle:
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        assert self.result is not None
        return self.result


class _CountingProvider:
    """只实现协调器会碰的两个方法；`calls` 是付费调用次数的唯一判据。"""

    def __init__(self, detail: ArticleDetail | None) -> None:
        self.detail = detail
        self.calls = 0

    async def fetch_article_detail(self, url: str) -> ArticleDetail | None:
        self.calls += 1
        return self.detail

    async def aclose(self) -> None:
        pass


def _settings(*, enabled: bool, key: str = "test-key") -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        article_detail_fallback_enabled=enabled,
        dajiala_api_key=key,
    )


def _free_article() -> ResolvedArticle:
    return ResolvedArticle(
        title="免费标题",
        author="免费作者",
        publish_time=None,
        content="免费正文",
        url=_URL,
        biz="MzA5",
        html="<p>免费正文</p>",
    )


def _paid_detail() -> ArticleDetail:
    return ArticleDetail(
        url=_URL,
        title="兜底标题",
        content_html="<p>付费正文</p>",
        content_text="付费正文",
        author="兜底作者",
        biz="MzA5",
        source="dajiala",
    )


def _service(resolver: _StubResolver, fallback: Any) -> KnowledgeBaseService:
    return KnowledgeBaseService(
        client=object(),  # type: ignore[arg-type]
        session=object(),  # type: ignore[arg-type]
        resolver=resolver,  # type: ignore[arg-type]
        settings=_settings(enabled=False),
        raw_store=object(),  # type: ignore[arg-type]
        engine_router=object(),  # type: ignore[arg-type]
        detail_fallback=fallback,
    )


def _patch_factory(
    monkeypatch: pytest.MonkeyPatch, providers: dict[str, _CountingProvider]
) -> list[Settings]:
    calls: list[Settings] = []

    def factory(settings: Settings) -> dict[str, _CountingProvider]:
        calls.append(settings)
        return providers

    monkeypatch.setattr("app.providers.article_sources.make_all_article_source_providers", factory)
    return calls


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _coordinator_calls(node: ast.AST) -> list[ast.Call]:
    return [
        item
        for item in ast.walk(node)
        if isinstance(item, ast.Call) and _call_name(item.func) == "ArticleDetailFallbackCoordinator"
    ]


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(KnowledgeBaseService, "_RESOLVE_BACKOFF_BASE", 0.0)


# ── 先红：调用图证明 ────────────────────────────────────────────────────────────


def test_coordinator_is_instantiated_exactly_once_in_app_code() -> None:
    hits: list[tuple[str, int]] = []
    for path in sorted(p for p in _APP.rglob("*.py") if "__pycache__" not in p.parts):
        count = len(_coordinator_calls(ast.parse(path.read_text(encoding="utf-8"))))
        if count:
            hits.append((path.relative_to(_APP).as_posix(), count))
    assert hits == [("services/job_worker.py", 1)], f"协调器实例化面={hits}"


def test_default_ingest_hands_the_coordinator_to_the_kb_service() -> None:
    tree = ast.parse((_APP / "services" / "job_worker.py").read_text(encoding="utf-8"))
    func = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "make_default_ingest"
    )
    assert len(_coordinator_calls(func)) == 1, "make_default_ingest 未实例化协调器"
    wired = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Call)
        and _call_name(node.func) == "KnowledgeBaseService"
        and any(kw.arg == "detail_fallback" for kw in node.keywords)
    ]
    assert len(wired) == 1, "协调器没有以 detail_fallback= 注入 KnowledgeBaseService"


# ── 三档付费调用计数 ────────────────────────────────────────────────────────────


async def test_flag_off_never_initialises_or_calls_paid_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paid = _CountingProvider(_paid_detail())
    factory_calls = _patch_factory(monkeypatch, {"dajiala": paid})
    resolver = _StubResolver(exc=ExtractFailedError("HTTP 500"))
    svc = _service(resolver, ArticleDetailFallbackCoordinator(_settings(enabled=False)))

    with pytest.raises(ExtractFailedError):
        await svc._resolve_with_retry(_URL)

    assert factory_calls == [], "开关关时不得因配置了 key 而初始化付费 provider"
    assert paid.calls == 0
    assert resolver.calls == KnowledgeBaseService._RESOLVE_MAX_ATTEMPTS


async def test_flag_on_free_success_never_pays(monkeypatch: pytest.MonkeyPatch) -> None:
    paid = _CountingProvider(_paid_detail())
    factory_calls = _patch_factory(monkeypatch, {"dajiala": paid})
    resolver = _StubResolver(result=_free_article())
    svc = _service(resolver, ArticleDetailFallbackCoordinator(_settings(enabled=True)))

    got = await svc._resolve_with_retry(_URL)

    assert got.title == "免费标题"
    assert resolver.calls == 1
    assert len(factory_calls) == 1, "开关开时应按 key 装配 provider"
    assert paid.calls == 0, "免费直抓成功时不得调用付费详情"


async def test_flag_on_free_failure_spends_exactly_one_paid_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dajiala = _CountingProvider(_paid_detail())
    justoneapi = _CountingProvider(_paid_detail())
    tikhub = _CountingProvider(_paid_detail())
    _patch_factory(
        monkeypatch, {"dajiala": dajiala, "justoneapi": justoneapi, "tikhub": tikhub}
    )
    resolver = _StubResolver(exc=ExtractFailedError("HTTP 500"))
    svc = _service(resolver, ArticleDetailFallbackCoordinator(_settings(enabled=True)))

    got = await svc._resolve_with_retry(_URL)

    assert resolver.calls == KnowledgeBaseService._RESOLVE_MAX_ATTEMPTS
    assert dajiala.calls == 1, "成本升序第一家命中即止，必须恰 1 次"
    assert justoneapi.calls == 0
    assert tikhub.calls == 0
    assert got.title == "兜底标题"
    assert got.html == '<div id="js_content"><p>付费正文</p></div>'
    assert got.url == _URL
    assert got.biz == "MzA5"


async def test_flag_on_fallback_miss_re_raises_the_free_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dajiala = _CountingProvider(None)
    _patch_factory(monkeypatch, {"dajiala": dajiala})
    resolver = _StubResolver(exc=ExtractFailedError("HTTP 500"))
    svc = _service(resolver, ArticleDetailFallbackCoordinator(_settings(enabled=True)))

    with pytest.raises(ExtractFailedError):
        await svc._resolve_with_retry(_URL)

    assert dajiala.calls == 1, "兜底未命中也要如实上抛原错误，不许伪装成功"


async def test_unexpected_error_does_not_spend_paid_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paid = _CountingProvider(_paid_detail())
    _patch_factory(monkeypatch, {"dajiala": paid})
    resolver = _StubResolver(exc=RuntimeError("本仓 bug"))
    svc = _service(resolver, ArticleDetailFallbackCoordinator(_settings(enabled=True)))

    with pytest.raises(RuntimeError):
        await svc._resolve_with_retry(_URL)

    assert paid.calls == 0, "只对直抓失败兜底，不拿付费调用掩盖本仓 bug"


def test_service_keeps_the_injected_coordinator() -> None:
    coordinator = object()
    svc = _service(_StubResolver(), coordinator)
    assert svc._detail_fallback is coordinator


async def test_fallback_body_survives_extractor_and_quality_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """兜底正文得真能过清洗与评分：否则接线只是把 20002 换成 20003，用户侧没变好。"""
    body = (
        "<p>公众号后台的作业队列用 PostgreSQL 的 SKIP LOCKED 领取任务，"
        "两个 worker 同时上线也不会把同一条作业领走两次。</p>"
        "<p>逐篇入库复用单篇流水线：先按资产键查缓存，命中即零请求，"
        "未命中才去抓取正文，失败时按退避重试三轮。</p>"
        "<p>清单状态机把发现、排队、入库、失败四态分开记账，"
        "回写失败时由巡检在滞后期结束后把排队态回收成发现态。</p>"
    )
    detail = ArticleDetail(
        url=_URL,
        title="作业队列与清单状态机",
        content_html=body,
        content_text="作业队列与清单状态机正文",
        author="运营组",
        biz="MzA5",
        publish_time=datetime(2026, 10, 20, 12, 0, tzinfo=UTC),
        source="dajiala",
    )
    paid = _CountingProvider(detail)
    _patch_factory(monkeypatch, {"dajiala": paid})
    resolver = _StubResolver(exc=ExtractFailedError("HTTP 503"))
    svc = _service(resolver, ArticleDetailFallbackCoordinator(_settings(enabled=True)))

    got = await svc._resolve_with_retry(_URL)

    assert got.publish_time == "2026-10-20T12:00:00+00:00"
    extracted = normalize_extracted(ExtractorService().extract(got))
    verdict = score_quality(extracted)
    assert verdict.passed, f"兜底正文过不了质量门：{verdict.to_view()}"
    assert "SKIP LOCKED" in extracted.langbot_format


async def test_fallback_page_html_is_not_double_wrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """provider 给整页形态（自带 js_content）时不再套第二层容器。"""
    detail = ArticleDetail(
        url=_URL,
        title="整页形态",
        content_html='<div class="rich_media" id="js_content"><p>整页正文在此。</p></div>',
        content_text="整页正文在此。",
        author="运营组",
        biz="MzA5",
        source="dajiala",
    )
    _patch_factory(monkeypatch, {"dajiala": _CountingProvider(detail)})
    resolver = _StubResolver(exc=ExtractFailedError("HTTP 500"))
    svc = _service(resolver, ArticleDetailFallbackCoordinator(_settings(enabled=True)))

    got = await svc._resolve_with_retry(_URL)

    assert got.html.count('id="js_content"') == 1
