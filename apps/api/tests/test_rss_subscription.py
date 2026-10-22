"""STEP-09 S9.1/S9.2：RSS 作为一等信息源——三种"看起来能用其实不能用"的形状。

1. **未知标识被静默当成 URL**（`rss._resolve_feed_url` 的最后一行 `return identifier`）：
   传一个 biz 串进来，它会去 `GET "MjM5MjgwNTQ1MQ=="`，httpx 抛错后被 `except HTTPError` 收成
   空清单 ⇒ 一轮同步读起来像"这个 feed 今天没发文"。⇒ 改判据：未知标识显式 `DiscoveryFailedError`。
2. **外链进了清单就是进了入库队列**：D-V2-03 裁"外链不入库"（仅 `mp.weixin.qq.com` 入库），
   而裁决落地需要一处过滤 + 一个能看见的计数（`offsite_filtered`）。没有计数，
   "这一轮被滤掉 30 条"和"这个 feed 只有 3 条"在库里长得一样。
3. **10006 被当成可重试**：非微信域/超长/控制字符这类链接错误是**永久**失败，
   `_resolve_with_retry` 却会退避重试 3 次、worker 再从头重采 4 次——实测纯属浪费上游额度。

订阅侧另有一条：RSS 源的 `external_id` 不能是 feed URL 本身（`sources.external_id` 是 String(128)，
而真实 feed URL 可以更长），也不能拿 biz 顶——所以身份落在 `source_identifiers(kind='feed_url')`，
这是 STEP-08 刚建的那张表第一次被真正的第二个标识种类用上。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.core.errors import DiscoveryFailedError, MalformedUrlError
from app.models.entities import Source, SourceIdentifier
from app.providers.article_sources.rss import RSSFeedConfig, RSSFeedProvider
from app.providers.source_resolver import ALLOWED_HOSTS
from app.services import system_settings
from app.services.kb import KnowledgeBaseService
from app.services.subscription import SourceSubscriptionService

BIZ = "MjM5MjgwNTQ1MQ=="
FEED = "https://rsshub.example.com/wechat/mp/ruanyifeng"


@pytest.fixture(autouse=True)
def _no_settings_snapshot() -> Iterator[None]:
    """清掉进程内配置快照：`enabled_channels()` 是"库值优先、env 兜底"，
    别人留下的快照会无声覆盖这里传的 Settings ⇒ 判据判的不再是标识筛选。"""
    system_settings.reset_snapshot()
    yield
    system_settings.reset_snapshot()

#: 一份混合 feed：两条微信镜像长链（可入库）+ 三条外链（只发现，不入库）。
MIXED_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>混合源</title><link>https://rsshub.example.com</link>
<item><title>微信一</title><link>https://mp.weixin.qq.com/s?__biz=MjM5&amp;mid=1&amp;idx=1&amp;sn=aaa1</link>
<guid>w1</guid></item>
<item><title>外链一</title><link>https://blog.example.org/posts/one</link><guid>x1</guid></item>
<item><title>外链二</title><link>https://news.example.com/a/b/c</link><guid>x2</guid></item>
<item><title>微信二</title><link>https://mp.weixin.qq.com/s?__biz=MjM5&amp;mid=2&amp;idx=1&amp;sn=aaa2</link>
<guid>w2</guid></item>
<item><title>外链三</title><link>https://docs.example.io/three</link><guid>x3</guid></item>
</channel></rss>"""


def _provider(body: str, seen: list[httpx.Request] | None = None) -> RSSFeedProvider:
    recorded = seen if seen is not None else []

    def _handler(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        return httpx.Response(200, text=body, headers={"content-type": "application/xml"})

    provider = RSSFeedProvider()
    provider._client = httpx.AsyncClient(  # type: ignore[attr-defined]
        transport=httpx.MockTransport(_handler), base_url="https://upstream.invalid"
    )
    return provider


# ── ① 未知标识：显式失败，不静默当 URL ────────────────────────────────────────


async def test_a_non_url_identifier_fails_instead_of_becoming_a_request() -> None:
    """biz 串不是 feed 地址：以前会被 `return identifier` 当成 URL 去打，现在必须在发请求之前就失败。

    判"一次请求都没发"是关键：只看抛错的话，"先打出去再失败"也算过，
    而那正是白烧一次上游请求的形状。
    """
    seen: list[httpx.Request] = []
    provider = _provider("<rss/>", seen)
    with pytest.raises(DiscoveryFailedError):
        await provider.query_work_list(BIZ, 1)
    assert seen == [], f"未知标识还是发出了请求：{[str(r.url) for r in seen]}"


async def test_the_three_legitimate_identifier_shapes_still_resolve() -> None:
    """三条合法形状一条都不能因为"加严"而退回来：别名 / 直链 / 空标识取首个。"""
    feeds = [
        RSSFeedConfig(url="https://first.example.com/feed.xml", alias="first"),
        RSSFeedConfig(url="https://second.example.com/feed.xml", alias="second"),
    ]
    provider = RSSFeedProvider(feeds=feeds)
    assert provider._resolve_feed_url("first") == "https://first.example.com/feed.xml"
    assert provider._resolve_feed_url("https://direct.example.com/feed.xml") == (
        "https://direct.example.com/feed.xml"
    )
    assert provider._resolve_feed_url("") == "https://first.example.com/feed.xml"
    await provider.aclose()


# ── ② 外链不入库，且滤掉的条数看得见 ─────────────────────────────────────────


async def test_offsite_links_are_dropped_and_the_count_is_visible() -> None:
    """五条里两条微信镜像、三条外链 ⇒ 只交 2 行，但"滤掉 3 条"必须是一个数而不是一句日志。

    计数挂在 provider 实例上（`filtered_offsite`，卡面给的名字）：`WorkListPage` 的契约形状
    归 STEP-08 所有，本卡不许往里加字段，所以这个数暂时只有 provider 级出口（登记 P 项）。
    旧端口 `query_work_list` 的返回形状不许被改——STEP-03 的契约测试打的是它。
    """
    provider = _provider(MIXED_FEED)
    page = await provider.query_work_list_page(FEED)
    assert [r.url for r in page.rows] == [
        "https://mp.weixin.qq.com/s?__biz=MjM5&mid=1&idx=1&sn=aaa1",
        "https://mp.weixin.qq.com/s?__biz=MjM5&mid=2&idx=1&sn=aaa2",
    ], [r.url for r in page.rows]
    assert provider.filtered_offsite == 3
    assert page.total == 5, "total 要说「上游给了几行」，不然滤掉的那几条在账上就消失了"


async def test_the_offsite_filter_shares_one_host_list_with_the_ingest_path() -> None:
    """外链判据必须与入库主路径同一个名单：两处各写一份 host 白名单，就是 P-28 那一族。

    判法不是"import 了 ALLOWED_HOSTS"，而是给一个**不在名单里但确实能解析的** URL：
    它必须被滤掉；同时 `ALLOWED_HOSTS` 里的域名必须留下。名单一改，两条断言一起动。
    """
    assert "mp.weixin.qq.com" in ALLOWED_HOSTS
    body = (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>'
        '<item><title>名单内</title><link>https://mp.weixin.qq.com/s?__biz=MjM5&amp;mid=9&amp;idx=1&amp;sn=z</link>'
        "<guid>in</guid></item>"
        '<item><title>名单外</title><link>https://other.example.net/s/xyz</link><guid>out</guid></item>'
        "</channel></rss>"
    )
    page = await _provider(body).query_work_list_page(FEED)
    assert [r.url for r in page.rows] == ["https://mp.weixin.qq.com/s?__biz=MjM5&mid=9&idx=1&sn=z"]


def test_no_second_host_allowlist_is_written_in_the_provider() -> None:
    """rss.py 里不许出现第二份域名名单（字面量集合或元组）——判 AST，不判 grep 措辞。"""
    import ast
    from pathlib import Path

    src = Path("app/providers/article_sources/rss.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and ".qq.com" in node.value
    }
    assert literals == set(), f"provider 里自带了域名字面量：{literals}"


async def test_the_counter_accumulates_across_feeds_of_one_provider() -> None:
    """一个 provider 服务多个 feed ⇒ 计数是"这一轮一共滤掉多少"，不是"最后一个 feed 滤掉多少"。

    只读一次的话，第二轮会把第一轮的数覆盖掉：账面上看像"这轮没滤东西"，
    而那正是本卡要避免的"渠道可用而清单恒空"的姊妹形状。
    """
    provider = _provider(MIXED_FEED)
    await provider.query_work_list_page(FEED)
    await provider.query_work_list_page("https://rsshub.example.com/other")
    assert provider.filtered_offsite == 6


def test_the_registered_identifier_is_the_one_the_router_reads() -> None:
    """S9.1.1 写下的那一格，必须正是 S8.4 路由要读的那一格——不然穿透链在中间断开。

    卡面 3『执行逻辑穿透』的两端：`select_channels` 按 `CHANNELS["rss"].required_identifier` 筛源，
    名字对不上时注册成功、feed 也抓得到，但每轮调度都不派 rss ⇒「订阅建好了却永远不采」。
    判这一条而不是判整条调度链，是因为路由侧的形状 STEP-08 已钉过；这里只钉**接得上**。
    """
    from app.providers.discovery.registry import CHANNELS, select_channels

    assert CHANNELS["rss"].required_identifier == "feed_url"
    # 只钉与 rss 有关的三个键；其余凭据让 Settings 走默认——断言只问"rss 进不进候选"，
    # 别家渠道进不进都不改变结论。
    settings = Settings(discovery_channels="", discovery_default_channel="redfox", discovery_rss_feeds=FEED)
    assert "rss" in select_channels({"feed_url": FEED}, settings), "注册好的 RSS 源派不出 rss 渠道"
    assert "rss" not in select_channels({"biz": BIZ}, settings), "只有 biz 的源不该拿到要 feed_url 的渠道"


# ── ③ 10006 是永久失败：不重试、不重采 ───────────────────────────────────────


def test_malformed_url_counts_as_a_permanent_error() -> None:
    from app.services.job_worker import _is_permanent_error

    exc: Exception = MalformedUrlError("不支持的域名: example.net")
    assert _is_permanent_error(exc), "10006 被当成可重试 ⇒ worker 从头再跑四遍同一条链接"


class _StubResolver:
    def __init__(self, exc: Exception) -> None:
        self.calls = 0
        self._exc = exc

    async def resolve(self, url: str) -> Any:
        self.calls += 1
        raise self._exc


def _kb(resolver: _StubResolver) -> KnowledgeBaseService:
    return KnowledgeBaseService(
        client=object(),  # type: ignore[arg-type]
        session=object(),  # type: ignore[arg-type]
        resolver=resolver,  # type: ignore[arg-type]
        settings=None,  # type: ignore[arg-type]
        raw_store=object(),  # type: ignore[arg-type]
        engine_router=object(),  # type: ignore[arg-type]
    )


async def test_resolve_does_not_retry_a_malformed_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """解析前先判过的错再重试一遍不会变好：只打一次。"""
    monkeypatch.setattr(KnowledgeBaseService, "_RESOLVE_BACKOFF_BASE", 0.0)
    resolver = _StubResolver(MalformedUrlError("仅支持 http(s) URL"))
    service = _kb(resolver)
    with pytest.raises(MalformedUrlError):
        await service._resolve_with_retry("https://mp.weixin.qq.com/s/x")
    assert resolver.calls == 1, f"10006 被重试了 {resolver.calls} 次"


async def test_network_errors_are_still_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """反向防过度收窄：网络类错误仍走满重试预算，否则一条抖动就被判永久失败。"""
    from app.core.errors import ExtractFailedError

    monkeypatch.setattr(KnowledgeBaseService, "_RESOLVE_BACKOFF_BASE", 0.0)
    resolver = _StubResolver(ExtractFailedError("HTTP 500"))
    service = _kb(resolver)
    with pytest.raises(ExtractFailedError):
        await service._resolve_with_retry("https://mp.weixin.qq.com/s/x")
    assert resolver.calls == KnowledgeBaseService._RESOLVE_MAX_ATTEMPTS


# ── ④ RSS 源的注册：身份在标识表里，不在 external_id 里硬塞 ──────────────────


async def _user_and_space(db_session: Any) -> tuple[str, str]:
    from app.repositories.space import SpaceRepository
    from app.repositories.user import SqlAlchemyUserStore

    user = await SqlAlchemyUserStore(db_session).upsert_by_sub("s09-user", "s09@t.test", "S09")
    space = await SpaceRepository(db_session).create(user_id=user.id, name="s09-space")
    return str(user.id), str(space.id)


async def _identifiers(db_session: Any, source_id: str) -> dict[str, str]:
    rows = (
        await db_session.execute(
            select(SourceIdentifier.kind, SourceIdentifier.value).where(SourceIdentifier.source_id == source_id)
        )
    ).all()
    return {kind: value for kind, value in rows}


async def test_rss_registration_stores_the_feed_url_as_an_identifier(db_session: Any) -> None:
    """`{type:'rss', feedUrl}` ⇒ `sources(type='rss')` + `source_identifiers(kind='feed_url')`。

    这一条同时是 STEP-08 那套路由的入口判据：`select_channels` 靠 `feed_url` 这一格
    决定 rss 渠道能不能被派出去，注册时不写它，路由就永远看不见这个源。
    """
    user_id, _space_id = await _user_and_space(db_session)
    svc = SourceSubscriptionService(db_session)
    got = await svc.register_source(user_id, source_type="rss", feed_url=FEED, name="阮一峰")
    source = await db_session.get(Source, got["sourceId"])
    assert source is not None and source.type == "rss"
    assert source.url == FEED
    assert await _identifiers(db_session, got["sourceId"]) == {"feed_url": FEED}


async def test_rss_registration_is_idempotent_on_the_feed_url(db_session: Any) -> None:
    """同一 feedUrl 注册两次 ⇒ 同一个源，且不产生第二行标识。"""
    user_id, _ = await _user_and_space(db_session)
    svc = SourceSubscriptionService(db_session)
    first = await svc.register_source(user_id, source_type="rss", feed_url=FEED)
    second = await svc.register_source(user_id, source_type="rss", feed_url=FEED)
    assert first["sourceId"] == second["sourceId"]
    assert await _identifiers(db_session, second["sourceId"]) == {"feed_url": FEED}


async def test_an_unknown_source_type_is_rejected_not_treated_as_biz(db_session: Any) -> None:
    """卡面"未知标识 ⇒ 不静默"的服务侧那一半：类型不认识就报错，不许回落到 wechat_oa 的 biz 通道。"""
    from app.core.errors import RequestInvalidError

    user_id, _ = await _user_and_space(db_session)
    svc = SourceSubscriptionService(db_session)
    with pytest.raises(RequestInvalidError) as err:
        await svc.register_source(user_id, source_type="telegram", feed_url=FEED)
    blob = str(err.value)
    assert "rss" in blob and "wechat_oa" in blob, f"错误没有点名可用类型：{blob}"


async def test_a_feed_url_still_cannot_be_registered_as_a_biz(db_session: Any) -> None:
    """公众号那条通道不许被 feed URL 冒充（形态校验是 R8 L1-3 加的，本卡不许放宽）。"""
    from app.core.errors import RequestInvalidError

    user_id, _ = await _user_and_space(db_session)
    svc = SourceSubscriptionService(db_session)
    with pytest.raises(RequestInvalidError):
        await svc.register_source(user_id, biz=FEED)


def test_the_route_body_accepts_the_card_camel_case_shape() -> None:
    """路由的请求模型必须吃卡面写的那个形状：`{type:'rss', feedUrl}`（camelCase）。

    判模型而不是打 HTTP：跑一遍 TestClient 要过登录闸门，那样红的时候分不清是模型不收
    还是鉴权没过——这条只判"体能不能被解出来"，登录与幂等由服务层那几条判。
    """
    from app.api.v1.subscriptions import RegisterSourceRequest

    payload = {"type": "rss", "feedUrl": FEED, "name": "阮一峰"}
    parsed = RegisterSourceRequest.model_validate(payload)
    assert parsed.type == "rss"
    assert parsed.feed_url == FEED, "camelCase 没接上 ⇒ 卡面写的这个体传进来会被丢成空串"
