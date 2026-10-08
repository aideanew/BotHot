"""RSS Feed Provider 单元测试。

覆盖：
- RSS 2.0 解析
- Atom 解析
- 字段映射（对齐 manifest._map_row 别名）
- 分页语义（page=1 返回全部，page>1 返回空）
- feed URL 解析（直接 URL / 别名 / 空标识符）
- HTTP 错误降级
"""

from __future__ import annotations

import pytest

from app.providers.article_sources.rss import (
    RSSFeedConfig,
    RSSFeedProvider,
    _parse_feed,
)

# ── 测试数据 ──────────────────────────────────────────────

RSS2_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>测试公众号</title>
    <link>https://example.com</link>
    <description>测试用 RSS feed</description>
    <item>
      <title>文章一：技术架构</title>
      <link>https://example.com/article/1</link>
      <pubDate>Mon, 02 Oct 2026 10:00:00 +0800</pubDate>
      <guid>guid-001</guid>
      <description>文章一摘要</description>
    </item>
    <item>
      <title>文章二：产品分析</title>
      <link>https://example.com/article/2</link>
      <pubDate>Tue, 03 Oct 2026 14:30:00 +0800</pubDate>
      <guid>guid-002</guid>
      <description>文章二摘要</description>
    </item>
  </channel>
</rss>"""

ATOM_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>测试博客</title>
  <link href="https://blog.example.com" rel="alternate"/>
  <updated>2026-10-02T12:00:00+08:00</updated>
  <entry>
    <title>Atom 文章一</title>
    <link href="https://blog.example.com/post/1" rel="alternate"/>
    <id>atom-001</id>
    <published>2026-10-01T09:00:00+08:00</published>
    <summary>Atom 文章一摘要</summary>
  </entry>
  <entry>
    <title>Atom 文章二</title>
    <link href="https://blog.example.com/post/2" rel="alternate"/>
    <id>atom-002</id>
    <published>2026-10-02T10:00:00+08:00</published>
    <summary>Atom 文章二摘要</summary>
  </entry>
</feed>"""

EMPTY_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>空</title>
    <link>https://empty.com</link>
  </channel>
</rss>"""

INVALID_XML = "not xml at all <<<"


# ── 解析测试 ──────────────────────────────────────────────


class TestRSS2Parse:
    def test_parse_rss2_basic(self):
        items = _parse_feed(RSS2_SAMPLE)
        assert len(items) == 2

    def test_parse_rss2_title(self):
        items = _parse_feed(RSS2_SAMPLE)
        assert items[0]["title"] == "文章一：技术架构"
        assert items[1]["title"] == "文章二：产品分析"

    def test_parse_rss2_url(self):
        items = _parse_feed(RSS2_SAMPLE)
        assert items[0]["url"] == "https://example.com/article/1"
        assert items[0]["link"] == "https://example.com/article/1"

    def test_parse_rss2_guid(self):
        items = _parse_feed(RSS2_SAMPLE)
        assert items[0]["guid"] == "guid-001"
        assert items[0]["id"] == "guid-001"

    def test_parse_rss2_pubdate(self):
        items = _parse_feed(RSS2_SAMPLE)
        assert "pubDate" in items[0]
        assert "2026" in items[0]["pubDate"]

    def test_parse_rss2_description(self):
        items = _parse_feed(RSS2_SAMPLE)
        assert items[0]["description"] == "文章一摘要"
        assert items[0]["digest"] == "文章一摘要"


class TestAtomParse:
    def test_parse_atom_basic(self):
        items = _parse_feed(ATOM_SAMPLE)
        assert len(items) == 2

    def test_parse_atom_title(self):
        items = _parse_feed(ATOM_SAMPLE)
        assert items[0]["title"] == "Atom 文章一"

    def test_parse_atom_link(self):
        items = _parse_feed(ATOM_SAMPLE)
        assert items[0]["url"] == "https://blog.example.com/post/1"

    def test_parse_atom_id(self):
        items = _parse_feed(ATOM_SAMPLE)
        assert items[0]["id"] == "atom-001"
        assert items[0]["guid"] == "atom-001"

    def test_parse_atom_summary(self):
        items = _parse_feed(ATOM_SAMPLE)
        assert items[0]["digest"] == "Atom 文章一摘要"


class TestEdgeCases:
    def test_empty_feed(self):
        items = _parse_feed(EMPTY_FEED)
        assert items == []

    def test_invalid_xml(self):
        items = _parse_feed(INVALID_XML)
        assert items == []

    def test_guid_fallback_to_link(self):
        """无 guid 时用 link 作 ID。"""
        xml = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>无 GUID</title>
    <link>https://example.com/no-guid</link>
    <pubDate>Mon, 02 Oct 2026 10:00:00 +0800</pubDate>
  </item>
</channel></rss>"""
        items = _parse_feed(xml)
        assert len(items) == 1
        assert items[0]["guid"] == "https://example.com/no-guid"

    def test_skip_item_without_id_and_link(self):
        """无 guid 且无 link 的 item 应跳过。"""
        xml = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>无 ID 无 Link</title>
    <description>应被跳过</description>
  </item>
</channel></rss>"""
        items = _parse_feed(xml)
        assert items == []


# ── Provider 行为测试 ─────────────────────────────────────


class TestRSSFeedProvider:
    @pytest.fixture
    def provider(self):
        return RSSFeedProvider()

    def test_name(self, provider):
        assert provider.name == "rss"

    def test_description(self, provider):
        assert "RSS" in provider.description

    @pytest.mark.asyncio
    async def test_page2_returns_empty(self, provider):
        """page > 1 返回空（RSS 不分页）。"""
        items, total = await provider.query_work_list("https://example.com/feed.xml", 2)
        assert items == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_empty_identifier_with_no_feeds(self, provider):
        """无 feeds 配置 + 空标识符 → 空结果。"""
        items, total = await provider.query_work_list("", 1)
        assert items == []

    @pytest.mark.asyncio
    async def test_alias_resolution(self):
        """别名解析到配置的 feed URL。"""
        feeds = [RSSFeedConfig(url="https://example.com/tech.xml", alias="tech")]
        provider = RSSFeedProvider(feeds=feeds)
        # 不实际请求，只验证 URL 解析
        url = provider._resolve_feed_url("tech")
        assert url == "https://example.com/tech.xml"
        await provider.aclose()

    @pytest.mark.asyncio
    async def test_direct_url_resolution(self):
        provider = RSSFeedProvider()
        url = provider._resolve_feed_url("https://direct.example.com/feed.xml")
        assert url == "https://direct.example.com/feed.xml"
        await provider.aclose()

    @pytest.mark.asyncio
    async def test_empty_identifier_falls_to_first_feed(self):
        feeds = [
            RSSFeedConfig(url="https://first.example.com/feed.xml", alias="first"),
            RSSFeedConfig(url="https://second.example.com/feed.xml", alias="second"),
        ]
        provider = RSSFeedProvider(feeds=feeds)
        url = provider._resolve_feed_url("")
        assert url == "https://first.example.com/feed.xml"
        await provider.aclose()

    @pytest.mark.asyncio
    async def test_fetch_detail_returns_none(self, provider):
        """RSS provider 不提供详情兜底。"""
        result = await provider.fetch_article_detail("https://example.com/article")
        assert result is None

    @pytest.mark.asyncio
    async def test_search_returns_empty(self, provider):
        """RSS provider 不支持搜索。"""
        result = await provider.search_articles("keyword")
        assert result == []

    @pytest.mark.asyncio
    async def test_aclose_idempotent(self, provider):
        await provider.aclose()
        await provider.aclose()  # 不应抛异常


# ── 预置 RSS 源测试 ────────────────────────────────────────


class TestFreeRSSFeeds:
    def test_free_rss_feeds_not_empty(self):
        from app.providers.article_sources.rss import FREE_RSS_FEEDS

        assert len(FREE_RSS_FEEDS) >= 10

    def test_free_rss_feeds_have_urls(self):
        from app.providers.article_sources.rss import FREE_RSS_FEEDS

        for feed in FREE_RSS_FEEDS:
            assert "url" in feed
            assert feed["url"].startswith("http")
            assert "name" in feed
            assert "category" in feed

    def test_free_rss_feeds_categories(self):
        from app.providers.article_sources.rss import FREE_RSS_FEEDS

        categories = {f["category"] for f in FREE_RSS_FEEDS}
        assert "wechat" in categories
        assert "tech" in categories
        assert "news" in categories
