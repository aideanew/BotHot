"""公众号文章直抓 Provider（B-T5）：URL 归一化 + httpx 直抓 + 锚点解析。

事实锚点（M0 报告 §三 T0.3 实证，wandao 移植）：
- DOM：正文 #js_content、标题 #activity-name、作者 #js_name；#publish_time 已失效勿用；
- publish_time：`var ct = "1718154000"`（Unix 秒，优先）→ `var createTime = '2024-06-12 09:00'` 兜底；
- biz：`var biz = ""||"MzU0OTkwODU2MA=="`（短链直抓后同样可得——主路径非死路）；
- 图片：仅信任 mmbiz.qpic.cn 且 data-src 优先。
本卡为轻量实现（文本+图片行），完整 Markdown 清洗归 B-T6（ContentExtractor）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx

from app.core.errors import ExtractFailedError, MalformedUrlError

# 白名单域名（当前仅公众号；web 域随 M4 扩展）
ALLOWED_HOSTS = {"mp.weixin.qq.com"}
MAX_URL_LENGTH = 512
REQUEST_TIMEOUT = 10.0
# 微信内置浏览器 UA（wandao 同款策略；普通桌面 UA 会命中验证页）
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "MicroMessenger/8.0.49(0x18003133) NetType/WIFI Language/zh_CN"
)

_WS = re.compile(r"\s+")
_BIZ_RE = re.compile(
    # biz 值为 base64（实证形态 Mz…/Mj… 等多种前缀），约束：M 开头 + 12~26 位 base64 字符
    r'var\s+biz\s*=\s*"(M[A-Za-z0-9+/]{11,25}={0,2})"'       # 形态A：var biz = "M…"（2026-09 真实页面，值在前）
    r'|var\s+biz\s*=\s*""\s*\|\|\s*"(M[A-Za-z0-9+/]{11,25}={0,2})"'  # 形态B：var biz = "" || "M…"（M0 样本）
)
_CT_RE = re.compile(r'var\s+ct\s*=\s*"(\d{10})"')
_CREATE_TIME_RE = re.compile(r"var\s+createTime\s*=\s*['\"](\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)['\"]")


def normalize_article_url(raw: str) -> str:
    """URL 归一化：5 类非法输入 → 10006（A 备案中）；合法则去空白返回。"""
    if raw is None:
        raise MalformedUrlError("URL 不能为空")
    url = raw.strip()
    if not url:
        raise MalformedUrlError("URL 不能为空")
    if len(url) > MAX_URL_LENGTH:
        raise MalformedUrlError(f"URL 超长（>{MAX_URL_LENGTH}）")
    if any(ord(ch) < 32 or ch == "\x7f" for ch in url):
        raise MalformedUrlError("URL 含非法控制字符")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise MalformedUrlError("仅支持 http(s) URL")
    if parts.netloc.lower() not in ALLOWED_HOSTS:
        raise MalformedUrlError(f"不支持的域名: {parts.netloc or '(缺省)'}")
    return url


def is_short_link(url: str) -> bool:
    """裸短链判定：/s/ 路径且无 __biz 参数（需直抓反解 biz，主路径）。"""
    parts = urlsplit(url)
    return parts.path.startswith("/s") and "__biz" not in parts.query


def parse_biz(html: str) -> str:
    """`var biz` 提取（M0 实证形态 `var biz = ""||"Mz..."`；短链页面同锚点）。"""
    match = _BIZ_RE.search(html)
    if not match:
        return ""
    return match.group(1) or match.group(2) or ""


def parse_publish_time(html: str) -> str | None:
    """publish_time：var ct（Unix 秒）优先，var createTime 兜底；ISO 8601 返回。"""
    ct = _CT_RE.search(html)
    if ct:
        return datetime.fromtimestamp(int(ct.group(1)), tz=UTC).isoformat()
    create = _CREATE_TIME_RE.search(html)
    if create:
        raw = create.group(1).replace("T", " ")
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S" if raw.count(":") == 2 else "%Y-%m-%d %H:%M")
        except ValueError:
            return None
        return parsed.isoformat()
    return None


def _extract_by_id(html: str, element_id: str) -> str:
    """按 id 提取元素内文本（去标签、折叠空白）——activity-name/js_name 共用。"""
    match = re.search(
        rf'<[^>]*id="{element_id}"[^>]*>(.*?)</', html, re.IGNORECASE | re.DOTALL
    )
    if not match:
        return ""
    return _WS.sub(" ", re.sub(r"<[^>]+>", "", match.group(1))).strip()


def parse_title(html: str) -> str:
    return _extract_by_id(html, "activity-name")


def parse_author(html: str) -> str:
    return _extract_by_id(html, "js_name")


def has_article_anchors(html: str) -> bool:
    """文章页判定：正文或标题锚点任一存在（缺失 → 20001 非文章页）。"""
    return 'id="js_content"' in html or 'id="activity-name"' in html


class _ContentParser(HTMLParser):
    """#js_content 内轻量提取：文本 + mmbiz 图片（data-src 优先）→ 行式内容。

    完整 Markdown 结构化（标题层级/列表/引用）归 B-T6 ContentExtractor。
    """

    _TRUSTED_IMG_HOST = "mmbiz.qpic.cn"

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self._skip = 0
        self._lines: list[str] = []
        self._buf: list[str] = []
        self._img: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag in ("script", "style"):
            self._skip += 1
            return
        if tag == "section":  # js_content 由 section 嵌套构成
            self._depth += 1
        if tag == "img":
            src = attr.get("data-src") or attr.get("src") or ""
            if src and self._TRUSTED_IMG_HOST in src:
                self._img = src
        if tag in ("p", "br", "section", "img", "blockquote"):
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag == "section" and self._depth:
            self._depth -= 1
        if tag in ("p", "section", "blockquote"):
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self._buf.append(data.strip())

    def close(self) -> None:  # noqa: D102
        self._flush()
        super().close()

    def _flush(self) -> None:
        if self._img is not None:
            self._lines.append(f"![]({self._img})")
            self._img = None
        if self._buf:
            text = _WS.sub(" ", " ".join(self._buf)).strip()
            if text:
                self._lines.append(text)
            self._buf = []

    @property
    def text(self) -> str:
        self._flush()
        return "\n".join(self._lines).strip()


def parse_content(html: str) -> str:
    """提取 #js_content：文本行 + 受信图片；锚点缺失返回空串（由调用方判 20001）。"""
    match = re.search(r'<[^>]*id="js_content"[^>]*>(.*)', html, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    body = match.group(1)
    # js_content 无显式闭合标记可依赖——截断到后续主脚本区（id="js_content" 后首个 </div> 深度归零近似）
    parser = _ContentParser()
    parser.feed(body)
    parser.close()
    return parser.text


@dataclass(slots=True)
class FetchedPage:
    """直抓产物（html + 最终 URL，短链跳转后即长链）。"""

    url: str
    html: str


class WechatArticleFetcher:
    """httpx 直抓（国内直连，容器 NO_PROXY 覆盖；UA 用微信内置浏览器）。"""

    def __init__(self, client: httpx.AsyncClient | None = None, timeout: float = REQUEST_TIMEOUT) -> None:
        self._client = client
        self._timeout = timeout

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=True)
        return self._client

    async def fetch(self, url: str) -> FetchedPage:
        """直抓文章页；网络不可达/超时/非 200 → 20002（EXTRACT_FAILED）。"""
        try:
            http = await self._get_client()
            resp = await http.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"},
            )
        except httpx.HTTPError as exc:
            raise ExtractFailedError(f"文章页抓取失败(网络): {type(exc).__name__}") from exc
        if resp.status_code != 200:
            raise ExtractFailedError(f"文章页抓取失败: HTTP {resp.status_code}")
        return FetchedPage(url=str(resp.url), html=resp.text)
