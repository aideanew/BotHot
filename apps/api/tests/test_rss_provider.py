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

from datetime import UTC, datetime

import httpx
import pytest

from app.providers.article_sources.rss import (
    _MAX_ITEMS_PER_FEED,
    RSSFeedConfig,
    RSSFeedProvider,
    _parse_feed,
)
from app.services.manifest import _map_row

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


def _one_item_feed(pub_date: str) -> str:
    """造一个只含一条 item 的 RSS2，`pubDate` 由参数决定（S3.1.2 的三种形状）。"""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n  <channel>\n    <title>t</title>\n'
        '    <item>\n      <title>文章</title>\n'
        '      <link>https://example.com/a/1</link>\n'
        f'      <pubDate>{pub_date}</pubDate>\n'
        '      <guid>guid-rfc</guid>\n    </item>\n  </channel>\n</rss>\n'
    )


class TestPublishTimeRfc822:
    """S3.1.2：RSS 的 RFC 822 时间必须解得出，且**解不出也不许丢行**。

    改前的红：`manifest._parse_time` 只认 ISO 与 epoch，`Wed, 02 Oct 2024 07:30:00 GMT`
    走 `fromisoformat` 抛 ValueError ⇒ `publish_time=None`（P-1 的 rss 那一半）。
    三条各判一个维度：数字时区偏移、英文时区缩写、非法值——
    只测第一条会把"缩写表没覆盖"放过去，只测前两条会把"非法值炸掉整行"放过去。
    """

    def test_rfc822_with_numeric_offset(self) -> None:
        mapped = _map_row(_parse_feed(_one_item_feed("Mon, 02 Oct 2026 10:00:00 +0800"))[0])
        assert mapped is not None
        assert mapped["publish_time"] == datetime(2026, 10, 2, 2, 0, tzinfo=UTC), mapped["publish_time"]

    def test_rfc822_with_gmt_abbreviation(self) -> None:
        mapped = _map_row(_parse_feed(_one_item_feed("Wed, 02 Oct 2024 07:30:00 GMT"))[0])
        assert mapped is not None
        assert mapped["publish_time"] == datetime(2024, 10, 2, 7, 30, tzinfo=UTC), mapped["publish_time"]

    def test_rfc822_with_named_zone_est(self) -> None:
        mapped = _map_row(_parse_feed(_one_item_feed("Wed, 02 Oct 2024 07:30:00 EST"))[0])
        assert mapped is not None
        # EST = -05:00（`parsedate_to_datetime` 认这三个字母；自己列格式表就会漏掉这一族）
        assert mapped["publish_time"] == datetime(2024, 10, 2, 12, 30, tzinfo=UTC), mapped["publish_time"]

    def test_illegal_time_keeps_the_row(self) -> None:
        """非法时间 ⇒ `publish_time` 为 None，但**这一行必须还在**。

        这条是"时间"与"行"的分离判据：把解析失败升级成丢行，就等于把 P-1 换了个入口再来一次。
        """
        row = _parse_feed(_one_item_feed("2026年10月02日 10:00"))[0]
        mapped = _map_row(row)
        assert mapped is not None, "时间解不出不得连带丢掉整行"
        assert mapped["publish_time"] is None
        assert mapped["external_id"] == "guid-rfc", "身份来自 guid，不该被时间失败牵连"


# ── 抓取路径与解析兜底（S3.4.1 / P-14：rss 是覆盖率报告里的第五个模块）──────
#
# 上面那几类判的都是 `_parse_feed` 这个纯函数——`query_work_list` 的**抓取**那半
# （112-128 行）与 `_get_client`/`aclose` 的连接生命周期（77-83、141-143）此前无人判，
# 而 RSS 恰恰是 STEP-09 卡面上的一等信息源：抓取路径一崩，整源零行且日志像成功。


def _fed_provider(
    body: str, status: int = 200, transport_error: Exception | None = None
) -> tuple[RSSFeedProvider, httpx.AsyncClient, list[httpx.Request]]:
    """把 MockTransport 塞进 provider 的私有 `_client`。

    为什么要碰私有属性：`RSSFeedProvider.__init__` 没有注入 http 的参数
    （其余四家都有）——这是实现的可测性缺口，改生产签名不在本卡授权内，
    所以这里按 provider 自己的装配点（`self._client`）注入，并把它一起返回交给用例收尾。
    """
    seen: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if transport_error is not None:
            raise transport_error
        return httpx.Response(status, text=body)

    http = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    provider = RSSFeedProvider()
    provider._client = http
    return provider, http, seen


class TestFetchPath:
    async def test_query_work_list_fetches_alias_resolved_feed_and_parses(self) -> None:
        provider, http, seen = _fed_provider(RSS2_SAMPLE)
        try:
            rows, total = await provider.query_work_list("https://example.com/feed.xml", 1)
        finally:
            await http.aclose()
        assert len(rows) == 2 and total == 2
        assert seen[0].url == "https://example.com/feed.xml", "identifier 是 URL 时不该再走别名表"
        assert all(_map_row(row) is not None for row in rows), "抓回来的行必须能被消费端接住"

    async def test_second_page_never_fetches(self) -> None:
        """RSS 不分页：page>1 必须**不发请求**返回空（发了也不会翻页，只是白拿一次抓取）。"""
        provider, http, seen = _fed_provider(RSS2_SAMPLE)
        try:
            assert await provider.query_work_list("https://example.com/feed.xml", 2) == ([], 0)
        finally:
            await http.aclose()
        assert seen == []

    async def test_http_status_error_degrades_to_empty_page(self) -> None:
        """feed 端点 500 ⇒ 空页而不抛异常（发现链的一路失败不该打断整轮同步）。"""
        provider, http, seen = _fed_provider("boom", status=500)
        try:
            assert await provider.query_work_list("https://example.com/feed.xml", 1) == ([], 0)
        finally:
            await http.aclose()
        assert len(seen) == 1, "降级之前确实问过上游"

    async def test_transport_error_degrades_to_empty_page(self) -> None:
        provider, http, _ = _fed_provider("", transport_error=httpx.ConnectError("connection refused"))
        try:
            assert await provider.query_work_list("https://example.com/feed.xml", 1) == ([], 0)
        finally:
            await http.aclose()

    async def test_unparsable_body_degrades_to_empty_page(self) -> None:
        """200 但正文不是 XML ⇒ 空页（`_parse_feed` 自己吞 ParseError，这里判整链收口）。"""
        provider, http, seen = _fed_provider(INVALID_XML)
        try:
            assert await provider.query_work_list("https://example.com/feed.xml", 1) == ([], 0)
        finally:
            await http.aclose()
        assert len(seen) == 1

    async def test_item_cap_bounds_one_feed(self) -> None:
        """单 feed 条数封顶 `_MAX_ITEMS_PER_FEED`：上游灌一万条也不能全量进发现链。"""
        items = "".join(
            f"<item><title>文章{i}</title><link>https://example.com/a/{i}</link></item>"
            for i in range(_MAX_ITEMS_PER_FEED + 5)
        )
        body = f'<?xml version="1.0"?><rss version="2.0"><channel>{items}</channel></rss>'
        provider, http, _ = _fed_provider(body)
        try:
            rows, total = await provider.query_work_list("https://example.com/feed.xml", 1)
        finally:
            await http.aclose()
        assert len(rows) == _MAX_ITEMS_PER_FEED
        assert total == _MAX_ITEMS_PER_FEED, "total 要报截断后的条数，否则上层按上游条数规划下一页"

    async def test_get_client_is_lazy_reused_and_fully_closed(self) -> None:
        """`_get_client()` 懒建 + 复用，`aclose()` 关掉并清空引用（否则下次拿到已关闭客户端）。"""
        provider = RSSFeedProvider()
        assert provider._client is None, "客户端不该在构造时就建好（provider 会被批量实例化）"
        first = provider._get_client()
        assert provider._get_client() is first, "第二次调用又造了一个客户端 ⇒ 连接池翻倍"
        await provider.aclose()
        assert first.is_closed is True
        assert provider._client is None, "aclose 后仍留着已关闭的客户端引用"
        assert provider._get_client() is not first, "关闭后必须能重新建一个可用的"
        await provider.aclose()


class TestFormatFallbacks:
    def test_rss_root_without_channel_yields_nothing(self) -> None:
        assert _parse_feed('<?xml version="1.0"?><rss version="2.0"></rss>') == []

    def test_channel_child_under_an_unrelated_root_is_still_rss2(self) -> None:
        """root 不是 <rss> 但有 <channel> 子元素 ⇒ 按 RSS2 兜住（上游网关改写 root 标签的形状）。"""
        xml = (
            '<?xml version="1.0"?><feeds><channel>'
            '<item><title>兜住的行</title><link>https://example.com/a/1</link></item>'
            "</channel></feeds>"
        )
        rows = _parse_feed(xml)
        assert [r["title"] for r in rows] == ["兜住的行"]

    def test_bare_feed_root_without_namespace_is_treated_as_atom(self) -> None:
        xml = (
            '<?xml version="1.0"?><feed>'
            "<entry><title>无命名空间的条目</title><id>x</id></entry>"
            "</feed>"
        )
        rows = _parse_feed(xml)
        assert [r["title"] for r in rows] == ["无命名空间的条目"]

    def test_unrelated_root_is_rejected_not_crashed(self) -> None:
        """既不是 rss 也不是 feed、又没有 channel ⇒ 空列表 + 一条 warn，不抛。"""
        assert _parse_feed("<html><body>网关的登录页</body></html>") == []

    def test_rss_link_href_attribute_variant(self) -> None:
        """`<link>` 没文本但有 href 属性（部分 RSS 变体）⇒ URL 从属性取。"""
        xml = (
            '<?xml version="1.0"?><rss version="2.0"><channel>'
            '<item><title>属性形 link</title><link href="https://example.com/a/href"/>'
            "<guid>guid-href</guid></item>"
            "</channel></rss>"
        )
        rows = _parse_feed(xml)
        assert len(rows) == 1
        assert rows[0]["url"] == "https://example.com/a/href"
        assert rows[0]["link"] == "https://example.com/a/href"

    def test_atom_entry_without_id_falls_back_to_link_and_updated_time(self) -> None:
        """Atom 条目没有 <id> ⇒ 用 link 顶身份；published 缺失 ⇒ 回落 updated；title 缺失 ⇒ 空串。"""
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            "<entry>"
            '<link href="https://blog.example.com/post/9" rel="alternate"/>'
            "<summary>没有 id 也没有 title 的条目</summary>"
            "<updated>2026-10-03T10:00:00+08:00</updated>"
            "</entry>"
            "</feed>"
        )
        rows = _parse_feed(xml)
        assert len(rows) == 1
        assert rows[0]["id"] == "https://blog.example.com/post/9"
        assert rows[0]["guid"] == rows[0]["url"] == "https://blog.example.com/post/9"
        assert rows[0]["publishTime"] == "2026-10-03T10:00:00+08:00"
        assert rows[0]["title"] == ""
        assert _map_row(rows[0]) is not None

    def test_atom_entry_without_id_and_link_is_dropped(self) -> None:
        """既无 id 又无 link 的条目只能丢——留下它就等于往身份键空间里塞一个空壳。"""
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            "<entry><title>既无 id 又无 link</title></entry>"
            "<entry><title>正常条目</title><id>atom-ok</id>"
            '<link href="https://blog.example.com/post/10" rel="alternate"/></entry>'
            "</feed>"
        )
        rows = _parse_feed(xml)
        assert [r["id"] for r in rows] == ["atom-ok"]

