"""RSS Feed 发现 Provider。

将 RSS/Atom feed 的 item 映射为 query_work_list 行（与 RedFox/Dajiala 同形），
manifest._map_row 的字段别名（link/url, title, pubDate/publishTime, guid/id）
直接消化 RSS item 字段，无需修改 manifest 层。

使用场景：
- 自建 RSS 桥（如 RSSHub）暴露公众号文章清单为 RSS feed
- 通用 RSS 源（新闻、博客等）作为文章发现渠道
- 多 feed 聚合：identifier 参数为 feed URL 或预配置的 feed 别名

依赖：httpx（已有）+ xml.etree.ElementTree（标准库），无额外依赖。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

import httpx
import structlog

from app.providers.article_sources.base import (
    ArticleDetail,
    ArticleSearchResult,
)

logger = structlog.get_logger(__name__)

# RSS item 字段 → work_list 行字段的映射（_map_row 的别名已覆盖）
# RSS 2.0: title, link, description, pubDate, guid
# Atom: title, link(href), summary, published, id

_DEFAULT_TIMEOUT = 20.0
_MAX_ITEMS_PER_FEED = 100


@dataclass(frozen=True, slots=True)
class RSSFeedConfig:
    """一个 RSS feed 的配置。"""

    url: str
    alias: str = ""  # 短名，供 identifier 参数引用
    category: str = ""  # 分类标签


class RSSFeedProvider:
    """RSS Feed 发现 Provider。

    实现 WorkListProvider 协议（query_work_list + aclose）。
    identifier 参数：
    - feed URL（http(s)://...）→ 直接抓取该 feed
    - 预配置别名 → 查找 self._feeds 中匹配的 URL
    - 空串 → 抓取第一个配置的 feed
    """

    def __init__(
        self,
        feeds: list[RSSFeedConfig] | None = None,
        *,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._feeds = feeds or []
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "rss"

    @property
    def description(self) -> str:
        return "RSS Feed 文章发现（RSS 2.0 / Atom 解析，零额外依赖）"

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=True,
                headers={"User-Agent": "BotHot-RSS/1.0 (+https://github.com/aideanew/BotHot)"},
            )
        return self._client

    def _resolve_feed_url(self, identifier: str) -> str:
        """将 identifier 解析为 feed URL。"""
        if identifier.startswith("http://") or identifier.startswith("https://"):
            return identifier
        # 按别名查找
        for feed in self._feeds:
            if feed.alias == identifier:
                return feed.url
        # 空标识符 → 第一个 feed
        if not identifier and self._feeds:
            return self._feeds[0].url
        # 当作 URL 直接用
        return identifier

    async def query_work_list(self, identifier: str, page: int) -> tuple[list[dict[str, Any]], int | None]:
        """抓取并解析 RSS feed，返回 work_list 行。

        RSS feed 通常不分页——page=1 返回全部 item，page>1 返回空。
        """
        if page > 1:
            return [], 0

        feed_url = self._resolve_feed_url(identifier)
        if not feed_url:
            logger.warning("RSS: 无法解析 feed URL（identifier=%r）", identifier)
            return [], 0

        client = self._get_client()
        try:
            resp = await client.get(feed_url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("RSS: 抓取失败 %s: %s", feed_url, exc)
            return [], 0

        items = _parse_feed(resp.text)
        if not items:
            logger.warning("RSS: 解析无 item %s", feed_url)
            return [], 0

        # 限制条数
        items = items[:_MAX_ITEMS_PER_FEED]
        logger.info("RSS: 解析 %d 条 item from %s", len(items), feed_url)
        return items, len(items)

    async def fetch_article_detail(self, url: str) -> ArticleDetail | None:
        """RSS provider 不提供详情兜底——正文由免费直抓主路径处理。"""
        return None

    async def search_articles(
        self, keyword: str, *, sort: str = "latest", time_range: str = ""
    ) -> list[ArticleSearchResult]:
        """RSS provider 不支持关键词搜索。"""
        return []

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# ── RSS/Atom 解析（纯函数，无外部依赖）──────────────────────────────


def _parse_feed(xml_text: str) -> list[dict[str, Any]]:
    """解析 RSS 2.0 / Atom feed，返回 work_list 行列表。

    每行字段对齐 manifest._map_row 的别名：
    - title → _TITLE_KEYS
    - link/url → _URL_KEYS
    - pubDate/publishTime → _TIME_KEYS
    - guid/id → _ID_KEYS
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("RSS: XML 解析失败: %s", exc)
        return []

    # 检测 feed 类型
    tag = root.tag.lower()
    if "rss" in tag:
        return _parse_rss2(root)
    if "feed" in tag and "atom" in tag:
        return _parse_atom(root)
    # 容错：RSS 2.0 的 root 是 <rss>，子元素 <channel>
    channel = root.find("channel")
    if channel is not None:
        return _parse_rss2(root)
    # Atom 的 root 是 <feed>
    if root.tag.endswith("feed"):
        return _parse_atom(root)
    logger.warning("RSS: 未知 feed 格式 (root.tag=%s)", root.tag)
    return []


def _parse_rss2(root: ET.Element) -> list[dict[str, Any]]:
    """解析 RSS 2.0 feed。"""
    channel = root.find("channel")
    if channel is None:
        return []
    items = []
    for item_elem in channel.findall("item"):
        item = _extract_rss_item(item_elem)
        if item:
            items.append(item)
    return items


def _extract_rss_item(item_elem: ET.Element) -> dict[str, Any] | None:
    """从 RSS <item> 元素提取 work_list 行。"""
    title = _text(item_elem, "title")
    link = _text(item_elem, "link")
    pub_date = _text(item_elem, "pubDate")
    guid = _text(item_elem, "guid")
    description = _text(item_elem, "description")

    # link 为空时尝试 <link> 子元素的 href（部分 RSS 变体）
    if not link:
        link_elem = item_elem.find("link")
        if link_elem is not None:
            # or 兜底链收口为 str（ET.get 签名返回 str|None，直接赋值 mypy 不通过）
            link = link_elem.text or (link_elem.get("href") or "")

    # guid 为空时用 link 作 ID
    if not guid:
        guid = link

    if not guid and not link:
        return None

    return {
        "title": title,
        "url": link,
        "link": link,
        "pubDate": pub_date,
        "publishTime": pub_date,
        "guid": guid,
        "id": guid,
        "description": description,
        "digest": description,
    }


def _parse_atom(root: ET.Element) -> list[dict[str, Any]]:
    """解析 Atom feed。"""
    items = []
    # Atom namespace
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("atom:entry", ns) or root.findall("entry"):
        item = _extract_atom_entry(entry, ns)
        if item:
            items.append(item)
    return items


def _extract_atom_entry(entry: ET.Element, ns: dict[str, str]) -> dict[str, Any] | None:
    """从 Atom <entry> 元素提取 work_list 行。"""
    title = _text_ns(entry, "atom:title", ns) or _text(entry, "title")
    link = ""
    # Atom link 可有多个（rel=alternate 是正文链接）
    for link_elem in entry.findall("atom:link", ns) or entry.findall("link"):
        rel = link_elem.get("rel", "alternate")
        if rel == "alternate" or not link:
            link = link_elem.get("href", "")
    pub_date = (
        _text_ns(entry, "atom:published", ns)
        or _text(entry, "published")
        or _text_ns(entry, "atom:updated", ns)
        or _text(entry, "updated")
    )
    entry_id = _text_ns(entry, "atom:id", ns) or _text(entry, "id")
    summary = _text_ns(entry, "atom:summary", ns) or _text(entry, "summary")

    if not entry_id:
        entry_id = link
    if not entry_id and not link:
        return None

    return {
        "title": title,
        "url": link,
        "link": link,
        "pubDate": pub_date,
        "publishTime": pub_date,
        "guid": entry_id,
        "id": entry_id,
        "description": summary,
        "digest": summary,
    }


def _text(elem: ET.Element, tag: str) -> str:
    """安全提取子元素文本。"""
    child = elem.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return ""


def _text_ns(elem: ET.Element, tag: str, ns: dict[str, str]) -> str:
    """带命名空间的安全提取。"""
    child = elem.find(tag, ns)
    if child is not None and child.text:
        return child.text.strip()
    return ""


# ── 预置免费 RSS 源（全网收集）──────────────────────────────────────

FREE_RSS_FEEDS: list[dict[str, str]] = [
    # RSSHub 公共实例（公众号、知乎、微博等）
    {
        "name": "RSSHub 官方",
        "url": "https://rsshub.app/wechat/ce/CeBaoShi",
        "category": "wechat",
        "note": "RSSHub 官方实例，可能限流",
    },
    {
        "name": "RSSHub 1",
        "url": "https://rsshub.rssforever.com/wechat/ce/CeBaoShi",
        "category": "wechat",
        "note": "RSSHub 公共实例",
    },
    {
        "name": "RSSHub 2",
        "url": "https://rss.shab.fun/wechat/ce/CeBaoShi",
        "category": "wechat",
        "note": "RSSHub 公共实例",
    },
    # WeRSS（公众号 RSS 服务）
    {
        "name": "WeRSS",
        "url": "https://werss.app/feed/all",
        "category": "wechat",
        "note": "WeRSS 公众号 RSS 服务",
    },
    # feeddd（公众号全文 RSS）
    {
        "name": "feeddd",
        "url": "https://feeddd.org/feeds/all",
        "category": "wechat",
        "note": "公众号全文 RSS",
    },
    # 通用新闻 RSS
    {
        "name": "新华网-时政",
        "url": "http://www.xinhuanet.com/politics/news_politics.xml",
        "category": "news",
        "note": "新华网时政频道",
    },
    {
        "name": "人民网-国际",
        "url": "http://www.people.com.cn/rss/world.xml",
        "category": "news",
        "note": "人民网国际频道",
    },
    {
        "name": "中国新闻网",
        "url": "https://www.chinanews.com.cn/rss/scroll-news.xml",
        "category": "news",
        "note": "中国新闻网滚动新闻",
    },
    # 科技博客
    {
        "name": "阮一峰博客",
        "url": "https://www.ruanyifeng.com/blog/atom.xml",
        "category": "tech",
        "note": "阮一峰的网络日志",
    },
    {
        "name": "奇客Solidot",
        "url": "https://www.solidot.org/index.rss",
        "category": "tech",
        "note": "Solidot 科技新闻",
    },
    {
        "name": "V2EX",
        "url": "https://www.v2ex.com/index.xml",
        "category": "tech",
        "note": "V2EX 最新话题",
    },
    # RSSHub 知乎/微博/哔哩哔哩
    {
        "name": "知乎日报",
        "url": "https://rsshub.app/zhihu/daily",
        "category": "social",
        "note": "知乎日报",
    },
    {
        "name": "哔哩哔哩-热门",
        "url": "https://rsshub.app/bilibili/hot-search",
        "category": "social",
        "note": "B站热搜",
    },
    # Hacker News / TechCrunch（国际科技）
    {
        "name": "Hacker News",
        "url": "https://hnrss.org/frontpage",
        "category": "tech",
        "note": "Hacker News 头条",
    },
    {
        "name": "TechCrunch",
        "url": "https://techcrunch.com/feed/",
        "category": "tech",
        "note": "TechCrunch 科技新闻",
    },
    # 调研新增：可用公共实例和源（2026-10-02 验证）
    {
        "name": "RSSHub-injahow",
        "url": "https://rss.injahow.cn/wechat/ce/CeBaoShi",
        "category": "wechat",
        "note": "社区RSSHub实例，已验证可用",
    },
    {
        "name": "Wechat2RSS-安全",
        "url": "https://wechat2rss.xlab.app/list/all",
        "category": "wechat",
        "note": "Wechat2RSS公共列表，400+公众号(安全/开发)",
    },
    {
        "name": "36氪快讯",
        "url": "https://rsshub.app/36kr/newsflashes",
        "category": "news",
        "note": "36氪快讯新闻",
    },
    {
        "name": "澎湃新闻",
        "url": "https://rsshub.app/thepaper/featured",
        "category": "news",
        "note": "澎湃新闻精选",
    },
]
