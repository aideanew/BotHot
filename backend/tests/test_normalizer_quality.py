"""B-T7 验收测试：Normalizer 规范化 + 质量评分 + 全链护栏（样本回放，零真实网络）。

覆盖（任务卡）：
- 规范化规则逐条：NFC / 全角→半角 / 零宽剔除 / 空白收敛 / 实体兜底；
- 评分边界：阈值 30 上下、各惩罚项、reasons 可观测；
- 全链：低质样本（重复段落）→ 20003；正常样本响应含三字段（v0.3f 备案形状）。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.api.deps import get_current_user_id
from app.api.v1.extract import get_resolver_service_internal
from app.main import create_app
from app.providers.source_resolver import WechatArticleFetcher
from app.services.extractor import ExtractedContent, ImageInfo
from app.services.normalizer import normalize_extracted, normalize_text
from app.services.quality import QUALITY_PASS_THRESHOLD, score_quality
from app.services.resolver import SourceResolverService

# ------------------------------------------------------------------ 规范化逐条


def test_nfc_normalization() -> None:
    """NFC：分解形组合字符合并（U+0065+U+0301 → U+00E9）。"""
    assert normalize_text("e\u0301") == "é"  # noqa: RUF001


def test_fullwidth_to_halfwidth() -> None:
    """全角数字/字母/常用标点 → 半角；全角空格 → 半角空格。"""
    assert normalize_text("ＡＢＣ１２３：；！？") == "ABC123:;!?"
    assert normalize_text("全角　空格") == "全角 空格"


def test_zero_width_removed() -> None:
    """零宽字符（U+200B/200C/200D/2060/FEFF）剔除。"""
    assert normalize_text("麻\u200b籽\u200c齐\u2060飞\ufeff") == "麻籽齐飞"


def test_whitespace_collapsed() -> None:
    """段内连续空白（含不间断空格）收敛为单空格。"""
    assert normalize_text("a   b\t\tc\u00a0\u00a0d") == "a b c d"


def test_html_entity_fallback_decoded() -> None:
    """实体兜底：二次转义残片（&amp;amp; → &）解码。"""
    assert normalize_text("A&amp;amp;B") == "A&B"
    assert normalize_text("&lt;tag&gt;") == "<tag>"


def test_normalize_extracted_recomputes_and_rebuilds() -> None:
    """normalize_extracted：全字段应用 + wordCount 重算 + langbotFormat 重建。"""
    extracted = ExtractedContent(
        title="标题",
        author="作者",
        publish_time="2024-06-12T01:00:00+00:00",
        paragraphs=["全角ＡＢＣ段落。", "\u200b零宽开头段落。"],
        images=[ImageInfo(src="https://mmbiz.qpic.cn/a?wx_fmt=png", caption="图\u200b注")],
        word_count=999,  # 旧值，应被重算
        langbot_format="旧文本",
    )
    normalized = normalize_extracted(extracted)
    assert normalized.paragraphs == ["全角ABC段落。", "零宽开头段落。"]
    assert normalized.images[0].caption == "图注"
    assert normalized.word_count == count_of(normalized.paragraphs)
    assert "# 标题" in normalized.langbot_format and "全角ABC段落。" in normalized.langbot_format


def count_of(paragraphs: list[str]) -> int:
    from app.services.extractor import count_words

    return count_words("\n".join(paragraphs))


# ------------------------------------------------------------------ 评分（阈值 30 边界）


def _extracted(**overrides: Any) -> ExtractedContent:
    base = ExtractedContent(
        title="标题",
        author="作者",
        publish_time="2024-06-12T01:00:00+00:00",
        paragraphs=["段落一", "段落二", "段落三"],
        images=[],
        word_count=300,
        langbot_format="",
    )
    return replace(base, **overrides)


def test_score_high_quality_passes() -> None:
    """满配样本：60 长度 + 20 元信息 + 20 结构 = 100。"""
    verdict = score_quality(_extracted())
    assert verdict.score == 100 and verdict.passed and verdict.reasons == []


def test_score_threshold_boundary_below_30() -> None:
    """边界下侧精确构造：wordCount=50（10）+ 仅标题（10）+ 结构（20）- 重复 3 组（-15）= 25 < 30。"""
    p = ["A段", "A段", "B段", "B段", "C段", "C段"]
    verdict = score_quality(_extracted(word_count=50, paragraphs=p, publish_time=None, author=None))
    assert verdict.score == 25
    assert verdict.score < QUALITY_PASS_THRESHOLD
    assert not verdict.passed
    assert any("低于及格线" in r for r in verdict.reasons)


def test_score_threshold_boundary_above_30() -> None:
    """边界上侧：wordCount=100（20）+ 元信息 20 + 结构 20 = 60，无惩罚 → passed。"""
    verdict = score_quality(_extracted(word_count=100))
    assert verdict.score == 60
    assert verdict.passed


def test_score_penalties_textless_and_imbalance() -> None:
    """纯图无文本：无结构基准分 + 惩罚 -20（20+20-20=20，不通过）；图片失衡 -10（38，仍通过）。"""
    textless = score_quality(
        _extracted(
            word_count=100,
            paragraphs=[],
            images=[
                ImageInfo(src="https://mmbiz.qpic.cn/a?wx_fmt=png"),
                ImageInfo(src="https://mmbiz.qpic.cn/b?wx_fmt=png"),
            ],
        )
    )
    assert textless.score == 20  # 长度20 + 元信息20 + 结构0 - 惩罚20
    assert not textless.passed
    assert "纯图片无正文文本" in textless.reasons

    imbalance = score_quality(
        _extracted(
            word_count=25,
            paragraphs=["短"],
            images=[
                ImageInfo(src="https://mmbiz.qpic.cn/a?wx_fmt=png"),
            ],
        )
    )
    assert imbalance.score == 35  # 长度5 + 元信息20 + 结构20 - 失衡10
    assert any("图片占比过高" in r for r in imbalance.reasons)


def test_score_duplicate_paragraphs_capped() -> None:
    """重复段落每组 -5、上限 -15；3 组即触顶（4 组也只扣 15）。"""
    dup3 = score_quality(_extracted(word_count=300, paragraphs=["d1", "r1", "r1", "r2", "r2", "r3", "r3", "d2"]))
    dup5 = score_quality(
        _extracted(word_count=300, paragraphs=["d1", "r1", "r1", "r2", "r2", "r3", "r3", "r4", "r4", "r5", "r5", "d2"])
    )
    normal = score_quality(_extracted(word_count=300))
    assert normal.score - dup3.score == 15
    assert dup3.score == dup5.score == 85  # 上限封顶
    assert any("重复段落" in r for r in dup3.reasons)


def test_score_clamped_zero() -> None:
    """空文章形状（无段落无图无元信息）：结构分不给，总分 0。"""
    verdict = score_quality(_extracted(word_count=0, paragraphs=[], publish_time=None, author=None, title=""))
    assert verdict.score == 0 and not verdict.passed


# ------------------------------------------------------------------ 全链（端点）


def _endpoint_client(response_html: str) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=response_html, headers={"content-type": "text/html; charset=utf-8"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)
    app.dependency_overrides[get_resolver_service_internal] = lambda: SourceResolverService(
        WechatArticleFetcher(client=http)
    )
    return TestClient(app)


SAMPLE_GOOD = """
<html><head><script>var ct = "1718154000";</script></head><body>
<div id="activity-name">高质量样本</div><a id="js_name">麻籽研究所</a>
<div id="js_content"><section>
<p>第一段：麻籽是核心货币，抓鸟驯养进化对战收集构成完整循环。</p>
<p>第二段：三币经济系统中灵草为基础货币，麻籽为培养奖励。</p>
<p>第三段：星辉是高级货币，采用有限通缩设计。</p>
<p><img data-src="https://mmbiz.qpic.cn/mmbiz_jpg/x/640?wx_fmt=jpeg" alt="循环图"></p>
</section></div></body></html>
"""

SAMPLE_LOW_QUALITY = """
<html><head><script>var ct = "1718154000";</script></head><body>
<div id="activity-name">低质样本</div><a id="js_name">某号</a>
<div id="js_content"><section>
<p>重复一。</p><p>重复一。</p><p>重复二。</p><p>重复二。</p><p>重复三。</p><p>重复三。</p>
</section></div></body></html>
"""


def test_extract_endpoint_good_quality_includes_quality_fields() -> None:
    """正常样本：响应 data 追加 qualityScore/qualityPassed/qualityReasons（v0.3f 备案形状）。"""
    client = _endpoint_client(SAMPLE_GOOD)
    resp = client.post("/api/v1/extract", json={"url": "https://mp.weixin.qq.com/s/good"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data.keys()) == {
        "title",
        "author",
        "publishTime",
        "paragraphs",
        "images",
        "wordCount",
        "langbotFormat",
        "qualityScore",
        "qualityPassed",
        "qualityReasons",
    }
    assert data["qualityPassed"] is True and data["qualityScore"] >= QUALITY_PASS_THRESHOLD
    assert data["qualityReasons"] == []


def test_extract_endpoint_low_quality_maps_20003() -> None:
    """全链护栏：低质样本（重复段落+字数少）→ 20003 信封，reasons 进 message。"""
    client = _endpoint_client(SAMPLE_LOW_QUALITY)
    resp = client.post("/api/v1/extract", json={"url": "https://mp.weixin.qq.com/s/low"})
    assert resp.status_code == 422
    assert resp.json()["code"] == 20003
    assert "重复段落" in resp.json()["message"] or "字数" in resp.json()["message"]
