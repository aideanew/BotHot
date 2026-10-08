"""B-T6 验收测试：ContentExtractor 完整清洗（样本回放，零真实网络）。

覆盖（任务卡质量护栏）：
- 广告块/二维码区块剔除；隐藏节点剔除；尾部噪音文本剔除；
- 尾部推荐区块（近期文章精选/往期推荐…）命中即终止正文，段落与图片一并截断；
  反向护栏：正文里以「推荐阅读 / 延伸阅读」开头的长句不误截；
- 图片：仅 mmbiz 域、data-src 优先、wx_fmt 识别、alt→caption、外域图过滤；
- 空段丢弃与连续空行收敛；语义换行；
- wordCount 中文计数口径；langbotFormat 形状；
- 空文章（全噪音）→ 20003 EXTRACT_QUALITY_LOW（既有码，未新增码位）；
- POST /api/v1/extract：登录保护 10001、端到端桩链。
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user_id
from app.api.v1.extract import get_resolver_service_internal
from app.core.errors import ExtractQualityLowError
from app.main import create_app
from app.services.extractor import ExtractorService, count_words
from app.services.resolver import ResolvedArticle

# ------------------------------------------------------------------ 样本（B-T5 样本扩展：广告/隐藏/噪音/alt/外域图）

SAMPLE_RICH = """
<html><head><script>var biz = "MjM5MjgwNTQ1MQ==" || "";
var ct = "1718154000";</script></head>
<body>
<div id="activity-name">清洗规则验证文章</div>
<a id="js_name">麻籽研究所</a>
<div id="js_content">
  <section>
    <p>麻籽是核心货币。</p>
    <p><img src="https://other.example.com/pic.jpg"></p>
    <p><img data-src="https://mmbiz.qpic.cn/mmbiz_jpg/abc/640?wx_fmt=jpeg" alt="养成循环图"></p>
    <div class="qr_code"><p>关注公众号二维码</p><img src="https://mmbiz.qpic.cn/qr.png?wx_fmt=png"></div>
    <p style="display:none">这段隐藏文字不应出现</p>
    <p>第二段：抓鸟→驯养→进化。</p>
    <section><p>   </p><p></p><p>空段之后的第三段。</p></section>
    <p>轻点阅读，阅读原文，点个在看。</p>
    <p>-End-</p>
    <p>▼点击名片 ⭐标关注我们▼</p>
  </section>
</div>
</body></html>
"""

SAMPLE_ALL_NOISE = """
<html><body>
<div id="activity-name">纯噪音文章</div>
<div id="js_content">
  <div class="rich_media_tool"><p>轻点阅读</p></div>
  <p style="visibility:hidden">隐藏段落</p>
</div>
</body></html>
"""

SAMPLE_WITH_FOOTER = """
<html><body>
<div id="activity-name">正文与页脚分离</div>
<div id="js_content">
  <section><p>第一段正文。</p></section>
  <section><p>第二段正文。</p></section>
  <section>
    <p>近期文章精选:</p>
    <p>小米18Pro发布!全球首发第六代骁龙8至尊版</p>
    <p>OPPO Find X10系列发布!打造移动影像新高度</p>
    <p><img src="https://mmbiz.qpic.cn/mmbiz_png/footer/640?wx_fmt=png"></p>
    <p>微信扫一扫关注该公众号</p>
  </section>
</div>
</body></html>
"""

SAMPLE_FORWARD_REFERENCE_IN_BODY = """
<html><body>
<div id="activity-name">推荐类正文</div>
<div id="js_content">
  <p>推荐阅读：《深入理解 Transformer》适合工程团队作为入门读物，书中覆盖注意力机制的完整推导。</p>
  <p>延伸阅读部分对训练稳定性另有更多讨论，本文不重复展开。</p>
</div>
</body></html>
"""


def _article_of(html: str) -> ResolvedArticle:
    return ResolvedArticle(
        title=html and "样本标题",
        author="样本作者",
        publish_time="2024-06-12T01:00:00+00:00",
        content="",
        url="https://mp.weixin.qq.com/s/xyz",
        biz="MjM5MjgwNTQ1MQ==",
        html=html,
    )


def _extract_of(html: str):
    return ExtractorService().extract(_article_of(html))


# ------------------------------------------------------------------ 清洗规则


def test_cleaning_extracts_paragraphs_and_filters_noise() -> None:
    """广告块/隐藏节点/尾部噪音剔除；空段收敛；语义换行保序。"""
    result = _extract_of(SAMPLE_RICH)
    assert result.paragraphs == ["麻籽是核心货币。", "第二段：抓鸟→驯养→进化。", "空段之后的第三段。"]


def test_footer_recommendation_block_truncates_body() -> None:
    """尾部推荐区块：命中「近期文章精选」标题即正文终止，其后段落与图片全不入库。"""
    result = _extract_of(SAMPLE_WITH_FOOTER)
    assert result.paragraphs == ["第一段正文。", "第二段正文。"]
    assert result.images == []


@pytest.mark.parametrize(
    "header",
    ["近期文章精选:", "近期文章", "近期精选", "往期精彩回顾", "相关文章推荐", "猜你喜欢", "历史文章"],
)
def test_various_footer_headers_truncate(header: str) -> None:
    """回指往期类标记变体一律终止正文。"""
    html = (
        f'<html><body><div id="activity-name">t</div><div id="js_content">'
        f"<p>正文段落。</p><p>{header}</p><p>页脚条目标题</p></div></body></html>"
    )
    assert _extract_of(html).paragraphs == ["正文段落。"]


def test_forward_reference_label_in_body_is_not_truncated() -> None:
    """只截断回指类标记：正文里以「推荐阅读 / 延伸阅读」开头的长句与后续正文均保留。"""
    assert len(_extract_of(SAMPLE_FORWARD_REFERENCE_IN_BODY).paragraphs) == 2


def test_image_rules_trusted_domain_and_alt_caption() -> None:
    """图片：仅 mmbiz 域、data-src 优先、wx_fmt 识别、alt→caption。"""
    result = _extract_of(SAMPLE_RICH)
    assert len(result.images) == 1
    img = result.images[0]
    assert img.src == "https://mmbiz.qpic.cn/mmbiz_jpg/abc/640?wx_fmt=jpeg"  # 外域图与二维码图均被剔
    assert img.caption == "养成循环图"
    assert img.fmt == "jpeg"


def test_word_count_chinese_semantics() -> None:
    """wordCount：CJK 逐字 + 英文/数字词计 1。"""
    assert count_words("麻籽奖励") == 4
    assert count_words("麻籽奖励 hello world 42") == 7  # 4 字 + 3 词
    result = _extract_of(SAMPLE_RICH)
    assert result.word_count == count_words("\n".join(result.paragraphs))


def test_langbot_format_shape() -> None:
    """langbotFormat：元信息头 + 正文段落 + 图片行（v0.3e 备案形态）。"""
    result = _extract_of(SAMPLE_RICH)
    fmt = result.langbot_format
    assert fmt.startswith("# 样本标题")
    assert "作者：样本作者" in fmt and "发布时间：2024-06-12T01:00:00+00:00" in fmt
    assert "来源：https://mp.weixin.qq.com/s/xyz" in fmt
    assert "![养成循环图](https://mmbiz.qpic.cn/mmbiz_jpg/abc/640?wx_fmt=jpeg)" in fmt
    assert "第二段：抓鸟→驯养→进化。" in fmt


def test_view_shape_camel_case() -> None:
    """契约视图：images 仅 {src, caption}（format 为内部字段不外泄）。"""
    view = _extract_of(SAMPLE_RICH).to_view()
    assert set(view.keys()) == {"title", "author", "publishTime", "paragraphs", "images", "wordCount", "langbotFormat"}
    assert view["images"] == [{"src": "https://mmbiz.qpic.cn/mmbiz_jpg/abc/640?wx_fmt=jpeg", "caption": "养成循环图"}]
    assert view["publishTime"] == "2024-06-12T01:00:00+00:00"


def test_all_noise_article_maps_20003() -> None:
    """空文章（全噪音剔除后无段落无图片）→ 20003 EXTRACT_QUALITY_LOW。"""
    with pytest.raises(ExtractQualityLowError) as exc_info:
        _extract_of(SAMPLE_ALL_NOISE)
    assert exc_info.value.code == 20003
    assert exc_info.value.http_status == 422


def test_extractor_needs_html_field() -> None:
    """html 缺失（B-T5 旧产物兼容路径）→ 视为空文章 → 20003，而非静默成功。"""
    article = ResolvedArticle(title="t", author="a", publish_time=None, content="x", url="u", biz="b", html="")
    with pytest.raises(ExtractQualityLowError):
        ExtractorService().extract(article)


# ------------------------------------------------------------------ 端点层


def _endpoint_client(logged_in: bool = True) -> TestClient:
    app = create_app()
    if logged_in:
        app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    # resolver 走 MockTransport 桩（真实解析链路 + 零网络）

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=SAMPLE_RICH, headers={"content-type": "text/html; charset=utf-8"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)
    from app.providers.source_resolver import WechatArticleFetcher as _F
    from app.services.resolver import SourceResolverService

    app.dependency_overrides[get_resolver_service_internal] = lambda: SourceResolverService(_F(client=http))
    return TestClient(app)


def test_extract_endpoint_requires_login_10001() -> None:
    client = _endpoint_client(logged_in=False)
    resp = client.post("/api/v1/extract", json={"url": "https://mp.weixin.qq.com/s/abc"})
    assert resp.status_code == 401
    assert resp.json()["code"] == 10001


def test_extract_endpoint_full_chain() -> None:
    """端到端（桩网络）：resolve→extract 全链，title 来自 DOM 解析，camelCase 形状。"""
    client = _endpoint_client()
    resp = client.post("/api/v1/extract", json={"url": "https://mp.weixin.qq.com/s/abc"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["title"] == "清洗规则验证文章"  # DOM 锚点解析产物
    assert data["author"] == "麻籽研究所"
    assert data["paragraphs"][0] == "麻籽是核心货币。"
    assert data["images"][0]["caption"] == "养成循环图"
    assert "langbotFormat" in data and data["wordCount"] > 0


def test_extract_endpoint_malformed_url_maps_10006() -> None:
    """畸形 URL → 10006 信封（真 service 链，不触网）。"""
    client = _endpoint_client()
    resp = client.post("/api/v1/extract", json={"url": "ftp://mp.weixin.qq.com/s/x"})
    assert resp.status_code == 400
    assert resp.json()["code"] == 10006
