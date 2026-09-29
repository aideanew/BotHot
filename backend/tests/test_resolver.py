"""B-T5 验收测试：SourceResolver（录制样本回放，零真实网络请求）。

覆盖（任务卡）：
- 5 类畸形输入 → 10006；
- ct/createTime/biz/标题/作者/正文+data-src 图片锚点解析；
- 裸短链直抓反解 biz（MockTransport 回放跳转）；
- 非文章页 → 20001；网络失败 → 20002；
- POST /api/v1/resolve：登录保护 10001、桩 service 走通 camelCase 视图。
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user_id
from app.api.v1.resolve import get_resolver_service
from app.core.errors import ExtractFailedError, MalformedUrlError, SourceUrlUnrecognizedError
from app.main import create_app
from app.providers.source_resolver import (
    WechatArticleFetcher,
    has_article_anchors,
    normalize_article_url,
    parse_author,
    parse_biz,
    parse_content,
    parse_publish_time,
    parse_title,
)
from app.services.resolver import SourceResolverService

# ------------------------------------------------------------------ 录制样本（精简重构，锚点保真）


# 2026-09-07 真实页面实证形态：值在前 || "" 在后（与 M0 样本相反），B 未漏报此变体
SAMPLE_CT = """
<html><head><script>var biz = "MjM5MjgwNTQ1MQ==" || "";
var ct = "1718154000";
var createTime = '2024-06-12 09:00';</script></head>
<body>
<div class="rich_media_title" id="activity-name">  深度解析：奖励一颗麻籽的养成循环  </div>
<a id="js_name"> 麻籽研究所 </a>
<div id="js_content">
<section><p>麻籽是核心货币。</p>
<p><img src="https://mmbiz.qpic.cn/mmbiz_jpg/abc/640?wx_fmt=jpeg" data-src="https://mmbiz.qpic.cn/mmbiz_jpg/abc/640?wx_fmt=jpeg"></p>
<section><p>嵌套段落：抓鸟→驯养→进化。</p></section>
<script>console.log("should be skipped");</script>
</section>
</div>
</body></html>
"""

SAMPLE_BIZ_SWAPPED = '<script>var biz = "" || "MzU0OTkwODU2MA==";</script>'  # M0 形态（向后兼容）

SAMPLE_CREATETIME_ONLY = """
<html><body>
<h1 id="activity-name">仅 createTime 的样本</h1>
<a id="js_name">二号公众号</a>
<div id="js_content"><p>正文内容。</p></div>
<script>var createTime = '2024-06-12 09:00';</script>
</body></html>
"""

SAMPLE_NOT_ARTICLE = "<html><body><h1>环境异常</h1><p>完成验证即可继续访问</p></body></html>"

LONG_URL = "https://mp.weixin.qq.com/s?__biz=MzU0OTkwODU2MA==&mid=2247485000&idx=1&sn=abcdef1234567890"
SHORT_URL = "https://mp.weixin.qq.com/s/AbCdEfGh123"


def _client_of(html: str, *, status: int = 200) -> SourceResolverService:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=html, headers={"content-type": "text/html; charset=utf-8"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)
    return SourceResolverService(WechatArticleFetcher(client=http))


# ------------------------------------------------------------------ 归一化：5 类畸形 → 10006


@pytest.mark.parametrize(
    "bad_url",
    [
        "",  # 空串
        "ftp://mp.weixin.qq.com/s/abc",  # 非 http(s)
        "https://evil.example.com/s/abc",  # 非白名单域名
        "https://mp.weixin.qq.com/s/" + "a" * 600,  # 超长
        "https://mp.weixin.qq.com/s/ab\x00cd",  # 控制字符
        "   ",  # 纯空白
    ],
)
def test_normalize_rejects_malformed_with_10006(bad_url: str) -> None:
    with pytest.raises(MalformedUrlError) as exc_info:
        normalize_article_url(bad_url)
    assert exc_info.value.code == 10006
    assert exc_info.value.http_status == 400


def test_normalize_accepts_long_and_short_links() -> None:
    assert normalize_article_url(f"  {LONG_URL}  ") == LONG_URL  # 去空白
    assert normalize_article_url(SHORT_URL) == SHORT_URL


# ------------------------------------------------------------------ 锚点解析（样本回放）


def test_parse_anchors_from_ct_sample() -> None:
    """ct 优先 → Unix 秒转 ISO；biz/标题/作者/正文/图片 data-src 全链。"""
    assert parse_biz(SAMPLE_CT) == "MjM5MjgwNTQ1MQ=="  # 真实页面形态（值在前）
    assert parse_biz(SAMPLE_BIZ_SWAPPED) == "MzU0OTkwODU2MA=="  # M0 形态（空串在前）
    assert parse_publish_time(SAMPLE_CT) == "2024-06-12T01:00:00+00:00"  # 1718154000=UTC；北京 09:00 与 createTime 自洽
    assert parse_title(SAMPLE_CT) == "深度解析：奖励一颗麻籽的养成循环"
    assert parse_author(SAMPLE_CT) == "麻籽研究所"
    content = parse_content(SAMPLE_CT)
    assert "麻籽是核心货币。" in content
    assert "嵌套段落：抓鸟→驯养→进化。" in content
    assert "should be skipped" not in content  # script 被剔除
    assert "![](https://mmbiz.qpic.cn/mmbiz_jpg/abc/640?wx_fmt=jpeg)" in content  # data-src 优先


def test_parse_publish_time_falls_back_to_createtime() -> None:
    assert parse_publish_time(SAMPLE_CREATETIME_ONLY) == "2024-06-12T09:00:00"
    assert parse_publish_time(SAMPLE_NOT_ARTICLE) is None


def test_resolve_full_pipeline_with_stub_fetcher() -> None:
    """Service 全链（桩 fetcher）：ResolvedArticle 形状 + camelCase 视图。"""
    svc = _client_of(SAMPLE_CT)
    article = svc_sync_resolve(svc, LONG_URL)
    view = article.to_view()
    assert set(view.keys()) == {"title", "author", "publishTime", "content", "url", "biz"}
    assert view["biz"] == "MjM5MjgwNTQ1MQ=="
    assert view["publishTime"] == "2024-06-12T01:00:00+00:00"


def svc_sync_resolve(svc: SourceResolverService, url: str):
    import asyncio

    return asyncio.run(svc.resolve(url))


def test_resolve_short_link_replays_biz() -> None:
    """裸短链：直抓反解 biz（主路径非死路；MockTransport 回放最终页）。"""
    svc = _client_of(SAMPLE_CT)
    article = svc_sync_resolve(svc, SHORT_URL)
    assert article.biz == "MjM5MjgwNTQ1MQ=="


def test_resolve_non_article_page_maps_20001() -> None:
    """内容形态异常（验证页/非文章）→ 20001。"""
    svc = _client_of(SAMPLE_NOT_ARTICLE)
    with pytest.raises(SourceUrlUnrecognizedError) as exc_info:
        svc_sync_resolve(svc, LONG_URL)
    assert exc_info.value.code == 20001
    assert not has_article_anchors(SAMPLE_NOT_ARTICLE)


def test_resolve_network_failure_maps_20002() -> None:
    """网络不可达（MockTransport 抛 ConnectError）→ 20002。"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)
    svc = SourceResolverService(WechatArticleFetcher(client=http))
    with pytest.raises(ExtractFailedError) as exc_info:
        svc_sync_resolve(svc, LONG_URL)
    assert exc_info.value.code == 20002


def test_resolve_http_500_maps_20002() -> None:
    svc = _client_of("boom", status=500)
    with pytest.raises(ExtractFailedError) as exc_info:
        svc_sync_resolve(svc, LONG_URL)
    assert exc_info.value.code == 20002


# ------------------------------------------------------------------ 端点层（桩 service）


class _StubResolver:
    """端点桩：固定产物，验证信封与鉴权装配。"""

    async def resolve(self, url: str):
        from app.services.resolver import ResolvedArticle

        return ResolvedArticle(
            title="桩标题", author="桩作者", publish_time="2024-06-12T09:00:00",
            content="桩正文", url=url, biz="MzSTUB==",
        )


def _endpoint_client(**overrides) -> TestClient:
    app = create_app()
    if overrides.get("logged_in", True):
        app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_resolver_service] = lambda: _StubResolver()
    return TestClient(app)


def test_resolve_endpoint_requires_login_10001() -> None:
    client = _endpoint_client(logged_in=False)
    resp = client.post("/api/v1/resolve", json={"url": LONG_URL})
    assert resp.status_code == 401
    assert resp.json()["code"] == 10001


def test_resolve_endpoint_returns_camel_view() -> None:
    client = _endpoint_client()
    resp = client.post("/api/v1/resolve", json={"url": LONG_URL})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data.keys()) == {"title", "author", "publishTime", "content", "url", "biz"}
    assert data["title"] == "桩标题" and data["biz"] == "MzSTUB=="


def test_resolve_endpoint_malformed_url_maps_10006() -> None:
    """端点层畸形 URL → 10006 信封（真 service + 桩 fetcher，不触网）。"""
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_resolver_service] = lambda: _client_of(SAMPLE_CT)
    client = TestClient(app)
    resp = client.post("/api/v1/resolve", json={"url": "https://evil.example.com/s/abc"})
    assert resp.status_code == 400
    assert resp.json()["code"] == 10006
