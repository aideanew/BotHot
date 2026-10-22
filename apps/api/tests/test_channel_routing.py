"""STEP-08 S8.3：清单端口（`WorkListPage`）的形状、游标的诚实性、以及服务层的止页判据。

判据分三面，每一面都对应一种"看起来做了其实没做"的失败：

1. **端口形状**——五家 provider 都得有 `query_work_list_page(identity, cursor, *, page_size)`，
   且旧端口 `query_work_list` 在一个版本内不许删（STEP-03 的契约测试打的是旧形状，
   而那些文件不在本卡所有权内 ⇒ 删了它们不会变红，会直接消失）。
2. **游标的诚实性**——本仓今天没有一家付费渠道实测到"响应里的游标放在哪个字段"，
   所以五家的 `next_cursor` 必须恒为 `None`。这条是**反着写**的：将来谁接出真游标，
   必须同时把 `CHANNELS_WITH_WIRED_CURSOR` 与"游标被原样回传"的用例一起补上，
   否则这里红（与 P-67/P-68 同一族防线：证据没到的地方只能写未测，不能写猜测）。
3. **止页判据在服务层**——`ManifestSyncService` 要真的按 `next_cursor` 与 `page_size` 止页，
   只实现旧端口的渠道（RedFox）继续按页号翻。只测 provider 的返回值的话，
   服务层把游标丢掉它也绿。

先红读数（改前形状）与四家夹具的游标检索见 `docs/06_validation/evidence/EVD-V17-08/s08_readings.md` §9。
"""

from __future__ import annotations

import ast
import inspect
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import structlog

from app.contracts.collection import WorkListPage
from app.core.config import Settings
from app.core.errors import DiscoveryFailedError
from app.models.entities import Source, SourceIdentifier, SourceSubscription
from app.providers.article_sources import base as base_module
from app.providers.article_sources.base import WORK_LIST_PAGE_SIZE, build_work_list_page
from app.providers.article_sources.dajiala import DajialaClient
from app.providers.article_sources.justoneapi import JustOneApiClient
from app.providers.article_sources.rss import RSSFeedProvider
from app.providers.article_sources.tikhub import TikhubClient
from app.providers.article_sources.wellbyte import WellbyteClient
from app.providers.discovery.registry import CHANNELS, identity_for, select_channels
from app.repositories.space import SpaceRepository
from app.repositories.user import SqlAlchemyUserStore
from app.services import system_settings
from app.services.manifest import ManifestSyncService
from app.services.scheduler import make_routed_sync_runner

API = Path(__file__).resolve().parents[1]
SAMPLE_DIR = API / "tests" / "fixtures" / "provider_payloads"
GHID = "gh_b9465228558d"

#: 已经**接到真游标**的渠道。今天为空。
#: 判据不是"上游有没有分页能力"，而是"响应游标字段 + 请求侧字段名是否都实测在案"：
#: 四家里只有 JustOneAPI 的响应侧在案（活体夹具 `justoneapi.json` 的
#: `data.PagingInfo{Offset, IsEnd}`），而它请求侧用什么字段接收 Offset 从未实测 ⇒ 不接。
#: 有人接出一家 ⇒ 本常量加一家，并必须补一条"第二次请求原样带回第一次的游标"的用例。
CHANNELS_WITH_WIRED_CURSOR: frozenset[str] = frozenset()

#: 五家的清单入参（形状取自各家 docstring 写死的 identifier 语义）。
_IDENTIFIER: dict[str, str] = {
    "dajiala": GHID,
    "justoneapi": GHID,
    "tikhub": GHID,
    "wellbyte": "https://mp.weixin.qq.com/s?__biz=MjM5MjgwNTQ1MQ==&mid=1&idx=1&sn=aaaa",
    "rss": "https://example.com/feed.xml",
}
_CHANNELS = tuple(sorted(_IDENTIFIER))


def _sample(name: str) -> dict[str, Any]:
    return json.loads((SAMPLE_DIR / name).read_text(encoding="utf-8"))


#: RSS 的载荷不是 JSON（feed 是 XML，`test_rss_provider.RSS2_SAMPLE` 是它的形状源）⇒ 单列一份。
_XML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>测试公众号</title><link>https://example.com</link>
<item><title>文章一</title><link>https://example.com/article/1</link>
<guid>guid-001</guid><description>摘要一</description></item>
<item><title>文章二</title><link>https://example.com/article/2</link>
<guid>guid-002</guid><description>摘要二</description></item>
</channel></rss>"""


def _response_body(channel: str) -> httpx.Response:
    if channel == "rss":
        return httpx.Response(200, text=_XML_SAMPLE, headers={"content-type": "application/xml"})
    return httpx.Response(200, json=_sample(f"{channel}.json"))


def _provider(channel: str, *, seen: list[httpx.Request] | None = None) -> Any:
    """按 STEP-03 契约测试的同一构造形状装配（`http=` 形参与 `test_provider_contract._BUILDERS` 对齐）。

    `seen` 非空时请求一条条记下来——"带了游标就不该再发请求"这类判据只能数请求，
    不能只看返回的空列表（上游自己给空清单时，那个断言也成立）。
    """
    recorded = seen if seen is not None else []

    def _transport(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        return _response_body(channel)

    http = httpx.AsyncClient(transport=httpx.MockTransport(_transport), base_url="https://upstream.invalid")
    if channel == "dajiala":
        return DajialaClient(api_key="test-" + "key", http=http)
    if channel == "justoneapi":
        return JustOneApiClient(api_key="test-" + "key", http=http)
    if channel == "tikhub":
        return TikhubClient(api_key="test-" + "key", http=http)
    if channel == "wellbyte":
        return WellbyteClient(api_key="test-" + "key", http=http)
    provider = RSSFeedProvider()
    provider._client = http  # type: ignore[attr-defined]  # 与 test_rss_provider 的注入方式一致
    return provider


@contextmanager
def _logged() -> Iterator[list[dict[str, Any]]]:
    """`capture_logs()` + 给 base 模块换一个新代理。

    `core/logging.py` 以 `cache_logger_on_first_use=True` 装配，模块级 logger 在第一次被用时
    就绑死当时的全局配置 ⇒ 全量跑时窗外的首次使用会让捕获读不到东西（P-63 那一族）。
    """
    with structlog.testing.capture_logs() as logs:
        original = base_module._logger
        base_module._logger = structlog.get_logger("app.providers.article_sources.base")
        try:
            yield logs
        finally:
            base_module._logger = original


# ── ① 端口形状 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("channel", _CHANNELS)
def test_paged_port_signature_is_the_one_the_card_named(channel: str) -> None:
    """判签名而不是判"方法存在"。

    只要"存在"的话，写成 `query_work_list_page(self, identity)` 也过，而那等于没有游标——
    本卡要买的就是那一个参数；`page_size` 同理，没有它末页判据只能靠空页，白多打一次上游。
    """
    method = getattr(_provider(channel), "query_work_list_page", None)
    assert method is not None, f"{channel} 没有新端口"
    params = list(inspect.signature(method).parameters)
    assert params[:2] == ["identity", "cursor"], f"{channel} 的位置参数是 {params}"
    assert "page_size" in params, f"{channel} 的新端口没有 page_size：{params}"


@pytest.mark.parametrize("channel", _CHANNELS)
def test_legacy_port_is_still_there_one_version_longer(channel: str) -> None:
    """旧端口本卡不许删：STEP-03 的 `test_provider_contract.py` 打的正是它，而那个文件不在所有权内。

    删掉它的表现不是"本文件红"，而是**别人的**一批用时报错——下一轮改动的人会以为是自己的错。
    """
    assert callable(getattr(_provider(channel), "query_work_list", None)), f"{channel} 的旧端口被删了"


# ── ② 游标的诚实性 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("channel", _CHANNELS)
async def test_no_channel_hands_out_a_cursor_it_did_not_measure(channel: str) -> None:
    """五家的 `next_cursor` 今天都必须是 `None`——依据是证据集合为空，不是实现巧合。

    反面形状：把页号 +1 当游标回传。上层于是以为还有下一页，每轮多打一次付费调用买回
    同一批最新条目，表现是"清单一直不增长"，而不是"上游不支持翻页"。
    """
    got = await _provider(channel).query_work_list_page(_IDENTIFIER[channel])
    assert isinstance(got, WorkListPage), f"{channel} 的新端口没返回契约页"
    assert got.next_cursor is None, f"{channel} 交出了一个没实测过的游标：{got.next_cursor!r}"
    assert channel not in CHANNELS_WITH_WIRED_CURSOR, "接了游标却没补回传用例"


@pytest.mark.parametrize("channel", _CHANNELS)
async def test_a_cursor_given_to_a_single_page_channel_starts_no_request(channel: str) -> None:
    """不接受游标的渠道被传了游标，只能回空页，而且**一次上游都不发**。

    只断"返回空行"不够：上游偶尔也返回空清单，那条判据在真发过请求的情况下也成立。
    """
    seen: list[httpx.Request] = []
    got = await _provider(channel, seen=seen).query_work_list_page(_IDENTIFIER[channel], cursor="2")
    assert got.rows == [], f"{channel} 带着游标又去打了一次首页"
    assert seen == [], f"{channel} 明明不该发请求，还是发了 {len(seen)} 次"


def test_the_cursor_allowlist_stays_empty_until_someone_brings_evidence() -> None:
    """`CHANNELS_WITH_WIRED_CURSOR` 是**证据集合**，不是配置项。

    今天为空。有人给某家接上真游标时这条会红，逼他把活体读数（响应游标字段 + 请求侧字段名）
    与回传用例一起交出来——防的正是"顺手把猜的键名当成交付"。
    """
    assert CHANNELS_WITH_WIRED_CURSOR == frozenset()


def test_justoneapi_response_cursor_is_measured_but_still_not_wired() -> None:
    """本卡唯一"证据到了一半"的一家：响应侧 `PagingInfo{Offset, IsEnd}` 在案，请求侧字段名不在案。

    判据直接读活体夹具，所以夹具一改（上游真的给了 `IsEnd`）这条就红，提醒重估 P-68 的出门条件；
    而"没接上"这件事由上面那条 `next_cursor is None` 兜住。
    """
    paging = _sample("justoneapi.json")["data"]["PagingInfo"]
    assert set(paging) >= {"Offset", "IsEnd"}, f"PagingInfo 形状变了：{paging}"
    assert "justoneapi" not in CHANNELS_WITH_WIRED_CURSOR


# ── ③ 行级策略只有一份 ────────────────────────────────────────────────────────


def test_an_all_dropped_page_is_error_not_just_a_warning() -> None:
    """整页丢光必须比"丢一行"更响——服务层拿着空页会当"上游没内容"直接止页。

    这一族的原文状是 P0-3（上游正常返回而本仓零入库）。本卡没有指标面，
    所以判据取"日志级别"这一维：`warning` 在告警面里与丢一行同价，`error` 才是"整页没了"。
    缺口本身登记为 P-69（指标面属 STEP-05）。
    """
    bad = [
        {"id": "b" * 20, "url": "short", "title": "坏"},
        {"id": "c" * 20, "url": "", "title": "也没 url"},
    ]
    with _logged() as logs:
        page = build_work_list_page(bad, next_cursor=None, page_size=20, channel="tikhub")
    assert page.rows == []
    # 捕获字典里级别键是 `log_level`（structlog 的 `capture_logs` 用它），不是 `level`——
    # 读错键会得到 None 而与"级别对不对"无关，所以这条判据把键名也一起钉住。
    events = {str(e.get("event")): str(e.get("log_level")) for e in logs}
    assert events.get("discovery.page_all_dropped") == "error", logs


def test_build_work_list_page_drops_unrepresentable_rows_and_says_so() -> None:
    """契约行有硬约束（`url` 8~512、id/url/title 必填）⇒ 不合约束的行**丢且出声**。

    两条反面形状都在本仓历史上出现过：一条脏项打挂整页（P-17）与整页静默消失（P0-3）。
    """
    good = {"id": "a" * 20, "url": "https://mp.weixin.qq.com/s/good", "title": "好"}
    bad = {"id": "b" * 20, "url": "short", "title": "坏"}
    with _logged() as logs:
        page = build_work_list_page([good, bad], next_cursor=None, page_size=20, channel="dajiala")
    assert [r.url for r in page.rows] == ["https://mp.weixin.qq.com/s/good"]
    blob = " ".join(f"{e.get('event')} {e}" for e in logs)
    assert "discovery.row_unrepresentable" in blob, logs
    assert "discovery.page_rows_dropped" in blob, "整页计数也要出声：只报单行就数不出丢了几条"


def test_build_work_list_page_adds_the_typed_time_without_erasing_the_original_key() -> None:
    """typed `publish_time` 是**加一格**，不是把 `publishTime` 换掉。

    换掉的后果不是报错而是静默：`_map_row` 的别名表按 `publishTime` 优先，键没了就读不到；
    而 `_parse_time` 又不认 datetime 对象 ⇒ 时间整列变 None，看起来像"上游没时间"。
    """
    row = build_work_list_page(
        [{"id": "a" * 20, "url": "https://mp.weixin.qq.com/s/x", "title": "t", "publishTime": "1"}],
        next_cursor=None,
        page_size=20,
    ).rows[0]
    assert row.model_dump(mode="json")["publishTime"] == "1", "原键必须留着（旧消费端靠它）"
    assert isinstance(row.publish_time, datetime) and row.publish_time.utcoffset() is not None


def test_typed_time_and_original_key_are_the_same_instant() -> None:
    """两条路径必须解出**同一个瞬间**（P-28 那一族：同一个串在两条路径上差 8 小时）。"""
    epoch = "1790659200"
    raw = {"id": "a" * 20, "url": "https://mp.weixin.qq.com/s/y", "title": "t", "publishTime": epoch}
    row = build_work_list_page([raw], next_cursor=None, page_size=20).rows[0]
    assert row.publish_time is not None
    assert row.publish_time.timestamp() == float(epoch)


def test_non_numeric_time_shape_is_left_to_the_consumer() -> None:
    """RSS 的 `pubDate`（RFC 822）**不在 provider 层解析**：那份解析全仓只该有一份。

    所以这一行的 typed `publish_time` 是 None，而原键原样带着。判据取"消费端还能解出同一个
    瞬间"而不是"字段非空"，否则就是把 P-28 的口径问题搬到 provider 层再犯一遍。
    """
    raw = {
        "id": "g" * 20,
        "url": "https://ruanyifeng.example/post/1",
        "title": "t",
        "publishTime": "Wed, 02 Oct 2024 07:30:00 GMT",
    }
    page = build_work_list_page([raw], next_cursor=None, page_size=20, channel="rss")
    assert page.rows[0].publish_time is None
    dumped = page.model_dump(mode="json")["rows"][0]
    assert dumped["publishTime"] == "Wed, 02 Oct 2024 07:30:00 GMT"
    assert dumped["publish_time"] is None, "typed 格不该被硬填——那是第二份解析的起点"


# ── ④ 服务层止页与翻页 ────────────────────────────────────────────────────────


class _PagedProvider:
    """新端口假件：按 `next_cursor` 出页，并记下每次收到的游标。"""

    name = "dajiala"
    description = "fake paged"

    def __init__(self, pages: list[tuple[list[dict[str, Any]], str | None]]) -> None:
        self._pages = pages
        self.seen_cursors: list[str | None] = []
        self.calls = 0

    async def query_work_list_page(
        self, identity: str, cursor: str | None = None, *, page_size: int = WORK_LIST_PAGE_SIZE
    ) -> WorkListPage:
        self.calls += 1
        self.seen_cursors.append(cursor)
        rows, next_cursor = self._pages[min(self.calls - 1, len(self._pages) - 1)]
        return build_work_list_page(rows, next_cursor=next_cursor, page_size=page_size)

    async def aclose(self) -> None:
        return None


class _LegacyOnlyProvider:
    """只实现旧端口的假件（RedFox 的形状——它的文件不在本卡所有权内）。"""

    name = "redfox"
    description = "fake legacy"

    def __init__(self, pages: dict[int, list[dict[str, Any]]]) -> None:
        self._by_page = pages
        self.seen_pages: list[int] = []
        self.calls = 0

    async def query_work_list(self, biz: str, page: int) -> tuple[list[dict[str, Any]], int | None]:
        self.calls += 1
        self.seen_pages.append(page)
        return self._by_page.get(page, []), None

    async def aclose(self) -> None:
        return None


def _rows(count: int, *, start: int = 0) -> list[dict[str, Any]]:
    return [
        {
            "id": f"row-{start + i}",
            "url": f"https://mp.weixin.qq.com/s/{start + i}",
            "title": f"标题 {start + i}",
        }
        for i in range(count)
    ]


async def _source(db_session: Any, external_id: str) -> str:
    src = Source(type="wechat_oa", external_id=external_id, name=external_id, url="https://e.invalid/x")
    db_session.add(src)
    await db_session.flush()
    return str(src.id)


async def test_sync_follows_the_cursor_and_stops_when_there_is_none(db_session: Any) -> None:
    """第一页给**满** 20 行（`len(rows) < page_size` 止不住），只靠 `next_cursor=None` 止。

    同一条还判"第二次带的是第一次给的游标"：服务层若把游标丢掉、退回按页号请求，这条红——
    那正是"端口升级了但没人用"的形状。
    """
    source_id = await _source(db_session, "S08-CURSOR")
    provider = _PagedProvider([(_rows(WORK_LIST_PAGE_SIZE), "c2"), (_rows(3, start=20), None)])
    report = await ManifestSyncService(db_session, provider, page_size=WORK_LIST_PAGE_SIZE).sync_source(
        source_id, "gh_x", max_pages=5
    )
    assert provider.seen_cursors == [None, "c2"], "第二次没带上第一次给的游标"
    assert provider.calls == 2, "末页信号已经给了还继续打，就是花钱买重复"
    assert report.pages == 2 and report.calls_made == 2


async def test_sync_with_a_page_number_channel_is_unchanged(db_session: Any) -> None:
    """旧端口渠道走页号适配：第二次请求的 `page` 必须是 2，行为与升级前逐字一致。

    这条是"本卡不波及别的卡"的证据——RedFox 是默认 provider，也是本仓今天唯一真能翻页的渠道。
    """
    source_id = await _source(db_session, "S08-LEGACY")
    provider = _LegacyOnlyProvider({1: _rows(WORK_LIST_PAGE_SIZE), 2: _rows(3, start=20)})
    await ManifestSyncService(db_session, provider, page_size=WORK_LIST_PAGE_SIZE).sync_source(
        source_id, "biz-x", max_pages=5
    )
    assert provider.seen_pages == [1, 2]
    assert provider.calls == 2


def test_the_paged_port_branch_is_actually_taken_by_the_service() -> None:
    """接线证明：`manifest._fetch_page` 必须**两个端口都认**，且新端口优先。

    把 `getattr(..., "query_work_list_page", None)` 改成恒 None（只走旧端口）时，
    上面"跟着游标翻页"那条会红；但只改一半（比如把旧端口分支写死）不会——
    所以这里直接看分支里引用了哪两个名字。
    """
    tree = ast.parse((API / "app" / "services" / "manifest.py").read_text(encoding="utf-8"))
    func = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_fetch_page"
    )
    referenced: set[str] = {
        n.value for n in ast.walk(func) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    } | {n.attr for n in ast.walk(func) if isinstance(n, ast.Attribute)}
    assert "query_work_list_page" in referenced, "_fetch_page 不再检查新端口"
    assert "query_work_list" in referenced, "_fetch_page 把旧端口删了（RedFox 与 STEP-03 的用例失去落点）"


# ── ⑤ S8.4.1 按源标识选渠道 ──────────────────────────────────────────────────


ALL_KEYS = {
    "redfox_api_key": "k" * 24,
    "dajiala_api_key": "k" * 24,
    "justoneapi_api_key": "k" * 24,
    "tikhub_api_key": "k" * 24,
    "wellbyte_api_key": "k" * 24,
    "discovery_rss_feeds": "https://example.com/feed.xml",
}


def _settings(**overrides: Any) -> Settings:
    """六家凭据全配齐 + 白名单不过滤 ⇒ 候选集只由**标识**决定（这正是要判的那一维）。

    每个键都显式给值：`Settings()` 会继承 `.env`，不写死的用例在别人的机器上会换结论。
    """
    values = dict(ALL_KEYS)
    values.update({"discovery_channels": "", "discovery_default_channel": "redfox"})
    values.update(overrides)
    return Settings(**values)


@pytest.fixture(autouse=True)
def _no_settings_snapshot() -> Iterator[None]:
    """清掉进程内配置快照。

    `enabled_channels()` 是"库值优先、env 兜底"，而快照是进程级单例：
    全量跑时前面某张卡留下的快照会让这里传的 settings 被无声覆盖 ⇒ 判据判的不再是标识筛选。
    """
    system_settings.reset_snapshot()
    yield
    system_settings.reset_snapshot()


def test_biz_only_source_cannot_reach_a_ghid_channel() -> None:
    """S8.4.1.1：只有 biz 的源，候选里不许出现需要 ghid / sample_url / feed_url 的渠道。

    升级前的调度器不分标识——一律把 `external_id`（biz）传给当轮渠道。拿 biz 去打要 ghid 的接口
    通常不报错，只回空清单 ⇒ "渠道可用而清单恒空"，与"上游今天没发文"在日志里同形（P0-3 那一族）。
    """
    got = select_channels({"biz": "MjM5MjgwNTQ1MQ=="}, _settings())
    assert got == ["redfox"], f"biz-only 的候选集={got}"


def test_eligible_channels_come_back_in_cost_order() -> None:
    """同一源给了 biz + ghid ⇒ 候选是"要 biz 的那一家 + 要 ghid 的三家"，按成本序、未知成本垫底。

    判整个序列而不是判首个：只判首个的话，把列表缩成只剩默认渠道它也绿。
    `wellbyte` 与 `rss` 不在里面**是因为这一源没有 sample_url / feed_url 标识**，
    不是因为它们没启用——那正是上一条（biz-only）与这一条合起来要区分的维度。
    """
    got = select_channels({"biz": "MjM5MjgwNTQ1MQ==", "ghid": GHID}, _settings(), preferred=None)
    assert got == ["tikhub", "dajiala", "justoneapi", "redfox"], got


def test_each_channel_is_handed_its_own_identifier() -> None:
    """路由传给渠道的是**它那一种**标识，不是"反正都传 external_id"。

    针对升级前的形状：调度器一律把 `sources.external_id`（= biz）交给当轮渠道，而 dajiala/
    justoneapi/tikhub 要 ghid、wellbyte 要文章 URL——传错那种不报错，只回空清单。
    `rss` 那一支是负面判据：没有 `feed_url` 时必须拿不到值（空串），而不是把 biz 冒充过去——
    `rss._resolve_feed_url` 对"看起来像 URL 的入参"会直接发一次抓取，那等于拿一个号主 ID 当 feed 地址打。
    """
    identifiers = {"biz": "MjM5MjgwNTQ1MQ==", "ghid": GHID, "sample_url": "https://mp.weixin.qq.com/s/x"}
    assert identity_for("redfox", identifiers) == "MjM5MjgwNTQ1MQ=="
    assert identity_for("dajiala", identifiers) == GHID
    assert identity_for("wellbyte", identifiers) == "https://mp.weixin.qq.com/s/x"
    assert identity_for("rss", identifiers) == "", "没有 feed_url 时不许把别的标识冒充过去"



def test_channel_with_unmeasured_cost_is_not_treated_as_free() -> None:
    """`cost_rank=None`（单价未实测）排最后，而不是被当成 0 排最前。

    这条是口径判据：把未知读成"免费"会让最贵的那一家拿到每一次首发机会，
    而日志里只会看到"我们在用 redfox"。
    """
    assert CHANNELS["redfox"].cost_rank is None
    got = select_channels({"biz": "MjM5MjgwNTQ1MQ=="}, _settings(), preferred=None)
    assert got == ["redfox"], got  # 只有它凑得上 biz，成本序在这里没有对手
    with_ghid = select_channels({"biz": "B", "ghid": GHID}, _settings(), preferred=None)
    assert with_ghid.index("redfox") > with_ghid.index("tikhub")


def test_preferred_channel_leads_only_when_it_is_eligible() -> None:
    """首选渠道够不着这一源的标识时**不许硬顶到首位**：否则整轮发现停在它身上，靠降级补。"""
    only_ghid = select_channels({"ghid": GHID}, _settings(), preferred="redfox")
    assert "redfox" not in only_ghid, only_ghid
    assert only_ghid[0] == "tikhub", only_ghid


def test_the_degradation_switch_has_no_config_field_yet() -> None:
    """现状钉：`Settings` 里没有 `discovery_fallback_enabled` 这一项 ⇒ 开关在生产里结构性关着。

    这条刻意判"字段不存在"。有人加上那一行时它会红——红的是"机制终于能被运营打开了"，
    那时要一起改的是 EVD-V17-08 §10 与 P-70 的处置，而不是顺手把断言删掉。
    """
    assert "discovery_fallback_enabled" not in Settings.model_fields
    assert bool(getattr(Settings(), "discovery_fallback_enabled", False)) is False


class _RoutingProvider:
    """按渠道名记账的假 provider：可指定某些渠道抛 `DiscoveryFailedError`。

    旧端口形状（`query_work_list`）就够——本条判据在的是"选了哪家、调了几次"，
    翻页机制已由上面 §9 的服务层判据钉过。
    """

    def __init__(self, name: str, failing: set[str], calls: list[str]) -> None:
        self.name = name
        self.description = f"fake {name}"
        self._failing = failing
        self._calls = calls

    async def query_work_list(self, biz: str, page: int) -> tuple[list[dict[str, Any]], int | None]:
        self._calls.append(self.name)
        if self.name in self._failing:
            raise DiscoveryFailedError(f"{self.name} 清单上游失败")
        return [_rows(1)[0]], 1

    async def aclose(self) -> None:
        return None


def _patch_factories(monkeypatch: pytest.MonkeyPatch, calls: list[str], failing: set[str]) -> None:
    """把六家的 factory 换成记账假件。

    就地 `setitem` 而不是替换整个 `CHANNELS` 引用：调度器与注册表各自拿着同一个 dict 对象，
    换引用要补两处补丁、且漏一处就测到真工厂；`setitem` 由 monkeypatch 逐键还原。
    """
    for name in list(CHANNELS):
        monkeypatch.setitem(
            CHANNELS, name, replace(CHANNELS[name], factory=lambda _s, _n=name: _RoutingProvider(_n, failing, calls))
        )


async def _seed_subscription(db_session: Any) -> tuple[SourceSubscription, str]:
    """真实 user/space/source/subscription 四件（`run_incremental_sync` 会按它们建 Job ⇒ 不能是野指针）。"""
    user = await SqlAlchemyUserStore(db_session).upsert_by_sub("s08-route-user", "s08@r.test", "S08")
    space = await SpaceRepository(db_session).create(user_id=user.id, name="s08-route-space")
    src = Source(type="wechat_oa", external_id="S08-ROUTE-BIZ", name="S08-ROUTE-BIZ", url="https://e.invalid/x")
    db_session.add(src)
    await db_session.flush()
    sub = SourceSubscription(
        id="s08-route-sub",
        user_id=user.id,
        source_id=str(src.id),
        space_id=space.id,
        sync_interval_minutes=60,
    )
    db_session.add(sub)
    await db_session.flush()
    return sub, str(src.id)


async def _give_ghid(db_session: Any, source_id: str) -> None:
    """给这个源补一条 ghid 标识（`ensure_identifiers` 今天造不出它，见 §7b/P-66）。

    判据要的形状是"这一源确实凑得齐三家 ghid 渠道的入参"——标识行由运营录入或未来卡产出，
    这里直接写库，是为了不把"ghid 从哪来"混进本条要判的东西里。
    """
    db_session.add(SourceIdentifier(source_id=source_id, kind="ghid", value=GHID, origin="source"))
    await db_session.flush()


async def test_degradation_off_raises_and_never_touches_the_second_channel(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """开关关（缺省）⇒ 第一家抛错就如实上抛，第二家一次都不许被调。

    与下一条是一对：只看"降级能试第二个"会放过"开关关着也在试"——那是运营以为没花钱、
    而每轮实际多打一家。
    """
    calls: list[str] = []
    _patch_factories(monkeypatch, calls, failing={"tikhub"})
    sub, source_id = await _seed_subscription(db_session)
    await _give_ghid(db_session, source_id)
    runner = make_routed_sync_runner(
        _settings(), default_channel="tikhub", default_provider=None, fallback_enabled=False
    )
    with pytest.raises(DiscoveryFailedError):
        await runner(db_session, sub, "tok-off")
    assert calls == ["tikhub"], f"开关关却调了 {calls}"


async def test_degradation_on_calls_the_second_channel_exactly_once(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S8.4.1.2：降级开 ⇒ 第一家失败后**第二家被调 1 次**；第三家不试。

    "1 次"是判据而不是日志：试到第三家看起来更稳，但那是拿预算赌一条没人验证过的链路，
    而且每多一家的成本在本卡这一层是不可见的（协调器的预算面只管详情，不管发现）。
    """
    calls: list[str] = []
    _patch_factories(monkeypatch, calls, failing={"tikhub"})
    sub, source_id = await _seed_subscription(db_session)
    await _give_ghid(db_session, source_id)
    runner = make_routed_sync_runner(
        _settings(), default_channel="tikhub", default_provider=None, fallback_enabled=True
    )
    await runner(db_session, sub, "tok-on")
    assert calls == ["tikhub", "dajiala"], calls


async def test_degradation_on_still_raises_when_the_second_channel_fails(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """降级后第二家也失败 ⇒ 如实上抛，不许"试过两家"被读成"本轮成功"。"""
    calls: list[str] = []
    _patch_factories(monkeypatch, calls, failing={"tikhub", "dajiala"})
    sub, source_id = await _seed_subscription(db_session)
    await _give_ghid(db_session, source_id)
    runner = make_routed_sync_runner(
        _settings(), default_channel="tikhub", default_provider=None, fallback_enabled=True
    )
    with pytest.raises(DiscoveryFailedError):
        await runner(db_session, sub, "tok-both")
    assert calls == ["tikhub", "dajiala"], calls

