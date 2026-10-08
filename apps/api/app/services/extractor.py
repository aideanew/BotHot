"""正文完整清洗器（B-T6）：ResolvedArticle → ExtractedContent。

清洗规则（wandao 移植 + M0 §三 + B-T5 实证补登）：
- 剔除：script/style、隐藏节点（display:none / visibility:hidden / hidden 属性）、
  广告与二维码区块（id/class 关键词数据驱动）、"轻点阅读"类尾部噪音文本、
  尾部推荐区块（"近期文章精选 / 往期回顾"命中标题后正文即终止，其后段落与图片全弃）；
- 图片：仅信任 mmbiz.qpic.cn，data-src 优先，wx_fmt 识别格式（内部字段，B-T7 评分与
  LangBot ingest 判断用），img alt 补作 caption；
- 空段丢弃、段内空白折叠（连续空行收敛）；block 元素边界保留语义换行；
- wordCount 口径：CJK 字符逐字计 + 英文/数字词计 1（任务卡"按中文计数"的最小可执行口径）；
- 空文章（段落与图片全空）→ 20003 EXTRACT_QUALITY_LOW（既有码，语义精准，未新增码位）。

langbotFormat 为入库文本形态（标题/元信息头 + 正文段落 + 图片行）——拼装规则
随本卡报 A 登记 v0.3e 备案中。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from app.core.errors import ExtractQualityLowError
from app.services.resolver import ResolvedArticle

# ------------------------------------------------------------------ 噪音判定（数据驱动，可扩展）

BLOCK_TAG = {"p", "section", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "tr"}
CONTAINER_TAG = {"section", "div", "p", "figure"}
VOID_TAG = {"br", "img", "hr", "input", "meta", "link", "source", "wbr"}
NOISE_ID_CLASS_KEYWORDS = (
    "qr_code", "qrcode", "js_pc_qr_code",  # 二维码区块
    "reward_area", "reward-qrcode",  # 赞赏/打赏
    "content_bottom_area", "rich_media_tool",  # 底部工具条
    "ct_mpda_wap", "js_ad_link", "ad_banner",  # 广告
    "wx_follow_nickname", "profile_container",  # 关注引导
)
NOISE_TEXT_KEYWORDS = (
    "轻点阅读", "轻点上方", "阅读原文", "点个在看", "分享、点赞、在看",
    "微信扫一扫关注该公众号", "长按识别二维码", "点击上方蓝字",
    "点击名片",  # 名片卡引导（▼点击名片 ⭐标关注我们▼）
    "-End-",  # 文末终止标记（带两侧连字符，避免命中英文词中的 end）
)
HIDDEN_STYLE_MARKERS = ("display:none", "display: none", "visibility:hidden", "visibility: hidden")
TRUSTED_IMG_HOST = "mmbiz.qpic.cn"
# 尾部推荐区块标题（"近期文章精选 / 往期回顾 …"）命中即视为正文结束。
# 其后的段落与图片一律属于页脚噪音。
# 只收录「回指往期」类标记——它们按定义只能出现在文末。
# 刻意不含「推荐阅读 / 相关推荐」：书影音推荐类正文会以它们作正文小标题，
# 误截会丢掉正文本身（误杀代价远高于漏杀噪音）。
# 判定另加长度上限（_is_footer_sentinel），排除「推荐阅读：xxxx」这类正文长句。
FOOTER_SENTINELS = (
    "近期文章精选",
    "近期精选",
    "近期文章",
    "近期推荐",
    "近期文章推荐",
    "往期回顾",
    "往期文章",
    "往期精彩",
    "往期精彩回顾",
    "往期推荐",
    "历史文章",
    "相关文章推荐",
    "相关文章",
    "猜你喜欢",
    "更多内容推荐",
)
# 页脚标题是短标签；超过此长度的段按正文处理，不在此截断。
FOOTER_SENTINEL_MAX_LEN = 14
_WX_FMT_RE = re.compile(r"wx_fmt=(\w+)")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_FOOTER_TRAILING_RE = re.compile(r"[：:。，、；！？\s·—|｜~-]+$")


def count_words(text: str) -> int:
    """中文计数口径：CJK 字符逐字 + 英文/数字连续串计 1。"""
    return len(_CJK_RE.findall(text)) + len(_WORD_RE.findall(text))


def _is_noise_container(attrs: dict[str, str]) -> bool:
    marker = f'{attrs.get("id", "")} {attrs.get("class", "")}'.lower()
    return any(keyword in marker for keyword in NOISE_ID_CLASS_KEYWORDS)


def _is_hidden(attrs: dict[str, str]) -> bool:
    if "hidden" in attrs:
        return True
    style = attrs.get("style", "").lower()
    return any(marker in style for marker in HIDDEN_STYLE_MARKERS)


def _is_noise_text(text: str) -> bool:
    return any(keyword in text for keyword in NOISE_TEXT_KEYWORDS)


def _is_footer_sentinel(text: str) -> bool:
    """是否为尾部推荐区块标题（正文终止标志）。

    归一化后做前缀匹配，并卡长度上限：页脚标题是短标签，正文里以这些词开头的
    完整句子（「延伸阅读：本文提到的工具…」）远超上限，不会误判。
    """
    head = _FOOTER_TRAILING_RE.sub("", text.strip())
    if not head or len(head) > FOOTER_SENTINEL_MAX_LEN:
        return False
    return any(head.startswith(marker) for marker in FOOTER_SENTINELS)


@dataclass(slots=True)
class ImageInfo:
    """图片（format 为 wx_fmt 识别结果，仅内部使用不进契约视图）。"""

    src: str
    caption: str = ""
    fmt: str = ""


@dataclass(slots=True)
class ExtractedContent:
    """清洗产物（camelCase 视图经 to_view 输出）。"""

    title: str
    author: str
    publish_time: str | None
    url: str = ""  # 来源 URL（langbotFormat 元信息头用；B-T7 起 normalize 重建需要）
    paragraphs: list[str] = field(default_factory=list)
    images: list[ImageInfo] = field(default_factory=list)
    word_count: int = 0
    langbot_format: str = ""

    def to_view(self) -> dict:
        """响应形状（v0.3e 备案中，A 复核）：images 仅 {src, caption}。"""
        return {
            "title": self.title,
            "author": self.author,
            "publishTime": self.publish_time or "",
            "paragraphs": self.paragraphs,
            "images": [{"src": img.src, "caption": img.caption} for img in self.images],
            "wordCount": self.word_count,
            "langbotFormat": self.langbot_format,
        }


class _CleaningParser(HTMLParser):
    """#js_content 结构化清洗：→ (paragraphs, images)。

    语义模型：block 元素边界断段；嵌套 section 不重复断段（仅 p/br/h*/li/img 强制断）。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth = 0  # js_content 内 section/figure 嵌套深度
        self._skip_depth = 0  # script/style
        self._noise_depth = 0  # 广告/二维码容器
        self._hidden_depth = 0  # 隐藏节点
        self.paragraphs: list[str] = []
        self.images: list[ImageInfo] = []
        self._buf: list[str] = []
        self._truncated = False  # 命中尾部推荐区块后，正文终止

    # -------------------------------------------------- 标签

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        if tag in ("script", "style"):
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        is_void = tag in VOID_TAG
        if self._hidden_depth or _is_hidden(attr):
            if not is_void:
                self._hidden_depth += 1
            return
        if self._noise_depth:
            if tag in CONTAINER_TAG and not is_void:
                self._noise_depth += 1
            return
        if tag in CONTAINER_TAG and _is_noise_container(attr):
            self._noise_depth += 1
            return
        if tag in ("section", "figure"):
            self._depth += 1
            self._flush()
            return
        if tag == "img":
            self._handle_img(attr)
            return
        if tag in BLOCK_TAG or tag == "br":
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if self._hidden_depth and tag not in VOID_TAG:
            self._hidden_depth -= 1
            return
        if self._noise_depth and tag in CONTAINER_TAG:
            self._noise_depth -= 1
            return
        if tag in ("section", "figure") and self._depth:
            self._depth -= 1
        if tag in BLOCK_TAG:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._noise_depth or self._hidden_depth:
            return
        if data.strip():
            self._buf.append(data.strip())

    # -------------------------------------------------- 收敛

    def _handle_img(self, attr: dict[str, str]) -> None:
        src = attr.get("data-src") or attr.get("src") or ""
        if not src or TRUSTED_IMG_HOST not in src:
            return  # 仅信任 mmbiz.qpic.cn
        fmt_match = _WX_FMT_RE.search(src)
        self._flush()
        if self._truncated:
            return  # 页脚图片不入库
        self.images.append(
            ImageInfo(src=src, caption=attr.get("alt", "").strip(), fmt=fmt_match.group(1) if fmt_match else "")
        )

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", " ".join(self._buf)).strip()
        self._buf = []
        if self._truncated or not text or _is_noise_text(text):
            return  # 空段丢弃 + 尾部噪音剔除 + 页脚截断
        if _is_footer_sentinel(text):
            self._truncated = True  # 正文终止：其后段落与图片均为页脚
            return
        self.paragraphs.append(text)

    def result(self) -> tuple[list[str], list[ImageInfo]]:
        self._flush()
        return self.paragraphs, self.images


def build_langbot_format(
    title: str,
    author: str,
    publish_time: str | None,
    url: str,
    paragraphs: list[str],
    images: list[ImageInfo],
) -> str:
    """入库文本形态（v0.3e 备案中）：元信息头 + 正文段落 + 图片行。

    B-T7 起签名去 article 依赖（纯字段），供 extractor 首建与 normalizer 重建共用。
    """
    meta_lines = [f"# {title}"]
    meta_parts = []
    if author:
        meta_parts.append(f"作者：{author}")
    if publish_time:
        meta_parts.append(f"发布时间：{publish_time}")
    if url:
        meta_parts.append(f"来源：{url}")
    if meta_parts:
        meta_lines.append(" ｜ ".join(meta_parts))
    lines = ["\n".join(meta_lines), ""]
    for para in paragraphs:
        lines.append(para)
        lines.append("")
    # 图片行统一置于正文后（原文位置信息在轻量 content 中保留；此处保证干净可入库）
    for img in images:
        alt = img.caption or ""
        lines.append(f"![{alt}]({img.src})")
    return "\n".join(lines).strip() + "\n"


class ExtractorService:
    """清洗服务（纯计算，无 IO；输入 ResolvedArticle 携带的原始 HTML）。"""

    def extract(self, article: ResolvedArticle) -> ExtractedContent:
        parser = _CleaningParser()
        # 只喂 js_content 区段（复用 B-T5 定位逻辑），避免把页头导航计入
        match = re.search(
            r'<[^>]*id="js_content"[^>]*>(.*)', article.html or "", re.IGNORECASE | re.DOTALL
        )
        body = match.group(1) if match else ""
        parser.feed(body)
        parser.close()
        paragraphs, images = parser.result()

        if not paragraphs and not images:
            raise ExtractQualityLowError("正文为空（全部为噪音或非文章页）")

        word_count = count_words("\n".join(paragraphs))
        return ExtractedContent(
            title=article.title,
            author=article.author,
            publish_time=article.publish_time,
            url=article.url,
            paragraphs=paragraphs,
            images=images,
            word_count=word_count,
            langbot_format=build_langbot_format(
                article.title, article.author, article.publish_time, article.url, paragraphs, images
            ),
        )
