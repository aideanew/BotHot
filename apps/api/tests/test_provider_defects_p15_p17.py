"""STEP-20：付费源适配器三处契约缺陷（发布清单 P-15 / P-16 / P-17）。

三条缺陷的共同点是**症状在上游、责任在本仓**，所以每条都判"喂什么形状、出什么结果"，
而不是断言上游行为。本文件用 `httpx.MockTransport` 把上游完全接管，并保留它真实发出的请求。

- **P-15**（`dajiala.py:162`、`justoneapi.py:196`、`wellbyte.py:229`）
  `datetime.fromtimestamp(int(x), tz=None)` 产出的是**宿主机本地时区的 naive 墙上钟**，而冻结契约
  `WorkListRow.publish_time` 是 `AwareDatetime`（稿面字段说明自己写着「provider 内即转为带时区
  时间」）。同一仓库的消费端 `services/manifest.py::_parse_time` 对同一个数字解出的是 aware UTC
  ⇒ 两套规范并存，换主机墙上钟就漂移。
- **P-16**（`tikhub.py` 的 detail/search 两个调用点）
  `base.py:91-97` 的协议与 `tikhub.py` 自己的 docstring 都写「失败返回 None，不抛异常，由
  coordinator 降级」，但 `_handle_response` 只对 402/404 降级，5xx 抛 `DependencyUnavailableError`、
  其余 4xx 抛 `DiscoveryFailedError`，两个调用点都不接。今天被
  `article_detail_fallback.py:99` 的宽 `except Exception` 吞掉，表现为"兜底没生效"而不是"报错"。
- **P-17**（`wellbyte.py:223`）
  `item.get("source", {})` 的默认值只在**键缺失**时生效，上游给 `"source": null` 时拿到 None，
  下一行 `.get("dateTime")` 抛 `AttributeError` ⇒ **已经映射好的行一起丢**，155cr 白烧。
  同一文件清单侧 `:142/:145` 用的是能兜 null 的 `or {}`，说明这是漏改而不是设计。

为什么 discovery 那条路径必须**继续抛**（本文件专门钉一次反向）：
`query_work_list` 的失败是采集链的主失败，静默成空页就等于「一轮同步看起来正常而实际零入库」
——那是 STEP-03 整张卡在消灭的那族。P-16 只降级 detail/search 两个**兜底**入口。
"""

from __future__ import annotations

import ast
import inspect
import pathlib
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app.contracts.collection import WorkListRow
from app.core.errors import DependencyUnavailableError
from app.providers.article_sources import tikhub
from app.providers.article_sources.dajiala import DajialaClient
from app.providers.article_sources.justoneapi import JustOneApiClient
from app.providers.article_sources.tikhub import TikhubClient
from app.providers.article_sources.wellbyte import WellbyteClient
from app.services.manifest import _parse_time

_ARTICLE_URL = "https://mp.weixin.qq.com/s?__biz=MzA5&mid=2650&idx=1&sn=abc"
_IDENTIFIER = "MjM5MjgwNTQ1MQ=="
_EPOCH = 1700000000
# 期望值**写死常量**，不用被测函数算：`fromtimestamp(_EPOCH, tz=UTC)` 当期望值等于没判。
_EPOCH_UTC = datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)

_BUILDERS: dict[str, Any] = {
    "dajiala": lambda http: DajialaClient(api_key="test-key", http=http),
    "justoneapi": lambda http: JustOneApiClient(api_key="test-key", http=http),
    "tikhub": lambda http: TikhubClient(api_key="test-key", http=http),
    "wellbyte": lambda http: WellbyteClient(api_key="test-key", http=http),
}


def _provider(channel: str, payload: Any, *, status: int = 200) -> tuple[Any, list[httpx.Request]]:
    """把上游完全接管，返回 (provider, 它真实发出的请求)。

    `seen` 是判据的一半：没有它，"根本没发请求就说降级" 也能装作 "发了但上游失败"。
    """
    seen: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=payload)

    http = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    return _BUILDERS[channel](http), seen


# 各家成功响应里 detail/search 真正吃的最小形状（其余字段与该判据无关）
_OK_PAYLOAD: dict[str, Any] = {
    "dajiala": {"code": 0, "data": {"html": "<p>正文</p>", "title": "T", "post_time": _EPOCH}},
    "justoneapi": {"code": 0, "data": {"data": [{"content": "<p>正文</p>", "create_time": _EPOCH}]}},
    "wellbyte": {
        "code": 0,
        "data": {"data": [{"title": "T", "doc_url": _ARTICLE_URL, "source": {"title": "号名", "dateTime": _EPOCH}}]},
    },
}


# ── P-15：detail/search 的发布时间必须是 aware UTC ────────────────────────────

_P15_CASES = (
    pytest.param("dajiala", "detail", id="dajiala详情"),
    pytest.param("justoneapi", "detail", id="justoneapi详情"),
    pytest.param("wellbyte", "search", id="wellbyte搜索"),
)


async def _publish_time_of(channel: str, entry: str) -> tuple[datetime, int]:
    """返回 (解出的 publish_time, 真实发出的请求数)。映射坏掉时当场红，红话说清是映射坏了。"""
    provider, seen = _provider(channel, _OK_PAYLOAD[channel])
    try:
        if entry == "detail":
            detail = await provider.fetch_article_detail(_ARTICLE_URL)
            assert detail is not None, f"{channel} 的详情映射本身坏了，本条的时区判据会失去意义"
            produced = detail.publish_time
        else:
            results = await provider.search_articles("关键词")
            assert results, f"{channel} 的搜索映射没出行，本条要判的东西不存在"
            produced = results[0].publish_time
    finally:
        await provider.aclose()
    assert produced is not None, f"{channel} 根本没解出时间（{_OK_PAYLOAD[channel]}）"
    return produced, len(seen)


@pytest.mark.parametrize(("channel", "entry"), _P15_CASES)
async def test_p15_publish_time_is_utc_aware_not_host_wall_clock(channel: str, entry: str) -> None:
    """卡面目标句的第一半：三家产出的每一行 `publish_time.tzinfo is not None`。

    只判 `tzinfo is not None` 是不够的（P-15 的修法可以是"改成宿主机时区"，那还是两套规范），
    所以三段各钉一次：有 tzinfo、偏移是 0、瞬间等于写死的常量。
    """
    produced, requests = await _publish_time_of(channel, entry)
    assert requests == 1, f"{channel} 没走上游就产出了时间"
    assert produced.tzinfo is not None, f"{channel} 产出 naive 墙上钟（P-15 原样）"
    assert produced.utcoffset() == timedelta(0), f"{channel} 的时区是 {produced.tzinfo}，不是 UTC"
    assert produced == _EPOCH_UTC, f"{channel} 把 {_EPOCH} 解成了 {produced}"


@pytest.mark.parametrize("channel", ["dajiala", "justoneapi", "wellbyte"])
async def test_p15_the_aware_value_feeds_the_frozen_contract_unchanged(channel: str) -> None:
    """卡面目标句的第二半：修好的值必须能**原样**进 `WorkListRow`。

    判据不许写成「转换之后再进」——那是把缺陷绕过去而不是修掉。
    """
    entry = "search" if channel == "wellbyte" else "detail"
    produced, _ = await _publish_time_of(channel, entry)
    WorkListRow(id="s2015", url=_ARTICLE_URL, title="T", publish_time=produced)


async def test_p15_provider_and_consumer_agree_on_one_instant_one_shape() -> None:
    """同一上游数字，provider 侧与消费端 `_parse_time` 必须**同瞬间且同形状**。

    这条是从被退役的见证用例里留下来的唯一有长期价值的段（见证处置见 EVD-V13-20）：
    只判 provider 侧 aware 的话，改天消费端漂到本地时区照样看不见。
    """
    produced, _ = await _publish_time_of("dajiala", "detail")
    consumer = _parse_time(str(_EPOCH))
    assert consumer is not None and consumer.tzinfo is not None
    assert produced.timestamp() == consumer.timestamp(), "同一数字解出两个瞬间"
    assert produced.utcoffset() == consumer.utcoffset(), "同瞬间不同形状 = 两套时区规范并存，正是 P-15 本身"


def test_p15_the_criterion_rejects_both_wrong_forms() -> None:
    """判据自检：同一个谓词必须**放过** UTC 形状、**拒绝** naive 与宿主机偏移形状。

    三段都是纯函数计算，不需要上游也不需要数据库 ⇒ 本机 `@win` 就能判，不会随环境漂成 skip。
    """

    def accepted(value: datetime) -> bool:
        return value.tzinfo is not None and value.utcoffset() == timedelta(0) and value.timestamp() == _EPOCH

    assert accepted(datetime.fromtimestamp(_EPOCH, tz=UTC)), "修好的形状被判 False ⇒ 那条绿用例也判不出东西"
    assert not accepted(datetime.fromtimestamp(_EPOCH, tz=None)), "naive（P-15 原样）必须被拒"
    assert not accepted(datetime.fromtimestamp(_EPOCH, tz=timezone(timedelta(hours=8)))), (
        "带宿主机偏移的 aware 值也必须被拒——否则「tz=None 改成 tz=本机时区」算过关"
    )
    # 契约面独立复核：naive 值进 AwareDatetime 是 `timezone_aware`，不是别的错
    with pytest.raises(ValidationError) as excinfo:
        WorkListRow(id="s2015", url=_ARTICLE_URL, title="T", publish_time=datetime.fromtimestamp(_EPOCH, tz=None))
    assert excinfo.value.errors()[0]["type"] == "timezone_aware"


# ── P-16：TikHub 的两个兜底入口对任意 4xx/5xx 都降级 ──────────────────────────

_TIKHUB_DEGRADE_STATUSES = (400, 404, 500, 503)


@pytest.mark.parametrize("status", _TIKHUB_DEGRADE_STATUSES)
async def test_p16_tikhub_detail_and_search_degrade_instead_of_raising(status: int) -> None:
    """协议面（`base.py:91-97`）：detail 返回 None、search 返回空列表，**不抛异常**。

    改前 400/500/503 红；404 本来就绿，它留在这里的职责是防「把 404 那支顺手改掉」。
    """
    body = {"message": "upstream bad"}
    detail_provider, detail_seen = _provider("tikhub", body, status=status)
    search_provider, search_seen = _provider("tikhub", body, status=status)
    try:
        assert await detail_provider.fetch_article_detail(_ARTICLE_URL) is None
        assert len(detail_seen) == 1, "没发请求就返回 None：那是「该平台不支持」的形态，不是降级"
        assert await search_provider.search_articles("关键词") == []
        assert len(search_seen) == 1
    finally:
        await detail_provider.aclose()
        await search_provider.aclose()


@pytest.mark.parametrize("status", (500, 503))
async def test_p16_discovery_path_still_raises_on_the_same_status(status: int) -> None:
    """反向防过度降级：`query_work_list` 在同一条码上**必须继续抛**。

    这是本卡的极性护栏。删掉它，「detail/search 降级」就能被写成
    「`_handle_response` 对所有码一律 return None」——那会把 STEP-03 花一整张卡消灭的
    「空清单冒充成功」重新放回来。
    """
    provider, seen = _provider("tikhub", {"message": "upstream bad"}, status=status)
    try:
        with pytest.raises(DependencyUnavailableError):
            await provider.query_work_list(_IDENTIFIER, 1)
        assert len(seen) == 1
    finally:
        await provider.aclose()


@pytest.mark.parametrize("name", ("fetch_article_detail", "search_articles"))
def test_p16_the_degrade_is_narrower_than_a_blanket_except(name: str) -> None:
    """降级只兜「上游给了个 HTTP 错误码 / 响应形状不对」这一层，用的是**领域异常**。

    判法用源码而不是行为：`except Exception` 会把 KeyError/AttributeError 一类本仓自己的 bug
    也吞成「兜底未命中」——那正是 P-17 那族缺陷的隐身衣。
    """
    src = inspect.getsource(getattr(TikhubClient, name))
    assert "except Exception" not in src, "兜底入口写了宽 except：本仓 bug 会被吞成上游降级"
    assert "except AppError" in src, "没有按领域异常收窄，降级范围是猜出来的"


# ── P-17：一行脏数据不许打挂整页搜索结果 ──────────────────────────────────────


async def test_p17_null_source_keeps_the_page_and_the_dirty_row_survives_empty() -> None:
    """`"source": null` ⇒ 该行仍进清单（作者留空、时间留空），**其余行不陪葬**。

    取「3 行都在」而不是「2 行」：判据以 `wellbyte.py` 现有缺字段分支为准——那里对缺失字段
    一直是留空而不是丢行（`author=source_info.get("title", "")`），新造「跳过整行」的语义不归本卡。
    """
    payload = {
        "code": 0,
        "data": {
            "data": [
                {"title": "第一行", "doc_url": _ARTICLE_URL, "source": {"title": "号名", "dateTime": _EPOCH}},
                {"title": "脏行", "doc_url": "https://example.invalid/x", "source": None},
                {"title": "第三行", "doc_url": "https://example.invalid/y", "source": {"title": "另一个号"}},
            ]
        },
    }
    provider, seen = _provider("wellbyte", payload)
    try:
        results = await provider.search_articles("关键词")
    finally:
        await provider.aclose()
    assert [r.title for r in results] == ["第一行", "脏行", "第三行"], "一行 null 让别的行一起丢了"
    assert len(seen) == 1
    assert results[1].author == "", "脏行的作者该留空而不是编一个"
    assert results[1].publish_time is None, "脏行没时间就留空，不拿入库时间冒充发布时间"
    assert results[0].publish_time is not None, "同页好行的时间不能受牵连"


@pytest.mark.parametrize("bad_source", ["号名字符串", 1234, ["数组"], True], ids=["str", "int", "list", "true"])
async def test_p17_truthy_non_dict_source_also_never_kills_the_page(bad_source: Any) -> None:
    """`or {}` 只兜 falsy；上游给 `"source": "字符串"` 这类**真值但非对象**时同样会炸。

    这是 P-17 的同一缺陷类（一行坏 = 整页丢），卡面 S20.2.3 的「同类形态一并改」指的就是它。
    仓内先例也是两件套：`wellbyte.py:142` 用 `or {}`，紧接着 `:143` 再 `isinstance` 判一次。
    """
    payload = {
        "code": 0,
        "data": {
            "data": [
                {"title": "好行", "doc_url": _ARTICLE_URL, "source": {"title": "号名"}},
                {"title": "坏形状行", "doc_url": "https://example.invalid/z", "source": bad_source},
            ]
        },
    }
    provider, _ = _provider("wellbyte", payload)
    try:
        results = await provider.search_articles("关键词")
    finally:
        await provider.aclose()
    assert [r.title for r in results] == ["好行", "坏形状行"], f"source={bad_source!r} 让整页又丢了"


async def test_p17_whole_response_shape_and_single_row_dirty_are_two_layers() -> None:
    """整次形状坏 ⇒ 返回 []；单行脏 ⇒ 那一行留空、整页保住。两层判据不许合成一层。

    后半个尤其关键：把单行 null 处理成「整次返回 []」也算失败——那等于把一行的错罚成全页的空。
    """
    provider, _ = _provider("wellbyte", {"code": 0, "data": "不是对象"})
    try:
        assert await provider.search_articles("关键词") == [], "整次形状守卫被改坏了"
    finally:
        await provider.aclose()

    payload = {"code": 0, "data": {"data": [{"title": "只有一行", "doc_url": _ARTICLE_URL, "source": None}]}}
    only, _ = _provider("wellbyte", payload)
    try:
        rows = await only.search_articles("关键词")
    finally:
        await only.aclose()
    assert len(rows) == 1, "单行 null 被处理成了整次空返回——换了代价，没换缺陷"


# ── P-17 同族（返工轮）：清单侧一处 `null` 同样打挂整轮付费抓取 ─────────────────

_DISCOVERY_NULL_CASES = (
    pytest.param("wellbyte", "AppMsg", id="wellbyte的AppMsg为null"),
    pytest.param("wellbyte", "BaseInfo", id="wellbyte的BaseInfo为null"),
    pytest.param("justoneapi", "AppMsg", id="justoneapi的AppMsg为null"),
    pytest.param("justoneapi", "BaseInfo", id="justoneapi的BaseInfo为null"),
)


@pytest.mark.parametrize(("channel", "key"), _DISCOVERY_NULL_CASES)
async def test_p17_family_null_nested_object_keeps_the_rest_of_the_page(channel: str, key: str) -> None:
    """`msg.get("AppMsg", {})` 的默认值只在**键缺失**时生效：上游给 `null` 拿到 None ⇒ 整轮抛穿。

    这是 P-17 的同一缺陷类换了入口（清单侧而非搜索侧），由独立复核现跑证实：
    单行 `{"AppMsg": null}` 让 `query_work_list` 抛 `AttributeError`，钱已经花了。
    判据只钉一件事：**好行必须还在**（坏行自己怎么处置按各文件既有分支，不新造语义）。
    """
    good = {"AppMsg": {"ContentUrl": _ARTICLE_URL, "Title": "好行", "CreateTime": _EPOCH}, "BaseInfo": {}}
    bad = dict(good)
    bad["AppMsg"] = {"ContentUrl": f"{_ARTICLE_URL}&sn=bad", "Title": "坏行"}
    bad[key] = None
    payload = {"code": 0, "data": {"MsgList": {"Msg": [good, bad]}}}
    provider, seen = _provider(channel, payload)
    try:
        rows, _total = await provider.query_work_list(_IDENTIFIER, 1)
    finally:
        await provider.aclose()
    assert len(seen) == 1, "上游根本没被调用，那条「页保住了」就是空的"
    urls = [r["url"] for r in rows]
    assert _ARTICLE_URL in urls, f"{channel} 的一处 `{key}: null` 让整轮清单丢了（P-17 同族）"
    # 坏行自己怎么处置按既有分支：AppMsg 炸 ⇒ url 空 ⇒ 被 `if row["url"]` 丢掉；
    # 只有 BaseInfo 炸 ⇒ url 还在 ⇒ 该行照常入列。**这里不把两种情况钉成同一个期望**，
    # 因为"该不该留这一行"不是本卡的缺陷面，把它写死就等于替别人的语义做主。
    assert len(urls) in (1, 2), f"清单行数超出两种既有语义：{urls}"


async def test_p17_family_tikhub_nested_null_keeps_the_page() -> None:
    """TikHub 清单侧的两个嵌套对象同形：`app_msg_ext_info` / `comm_msg_info` 为 null。"""
    good = {"app_msg_ext_info": {"content_url": _ARTICLE_URL, "title": "好行"}, "comm_msg_info": {"id": 1}}
    for key in ("app_msg_ext_info", "comm_msg_info"):
        bad = dict(good)
        bad[key] = None
        provider, seen = _provider("tikhub", {"code": 0, "data": {"data": [good, bad]}})
        try:
            rows, _ = await provider.query_work_list(_IDENTIFIER, 1)
        finally:
            await provider.aclose()
        assert len(seen) == 1
        assert any(r.get("url") == _ARTICLE_URL for r in rows), f"{key}: null 让 TikHub 整轮清单抛穿或全丢"


async def test_p17_family_truthy_nested_object_is_not_treated_as_a_dict() -> None:
    """真值但非对象（`"AppMsg": ["数组"]`）走同一支：不许只兜住 `null` 就宣布修完。"""
    payload = {
        "code": 0,
        "data": {
            "MsgList": {
                "Msg": [
                    {"AppMsg": {"ContentUrl": _ARTICLE_URL, "Title": "好行"}, "BaseInfo": {}},
                    {"AppMsg": ["这不是对象"], "BaseInfo": 7},
                ]
            }
        },
    }
    provider, _ = _provider("wellbyte", payload)
    try:
        rows, _ = await provider.query_work_list(_IDENTIFIER, 1)
    finally:
        await provider.aclose()
    assert [r["url"] for r in rows if r.get("url")] == [_ARTICLE_URL]


# ── 结构守卫：这三处的修法不许漂回第二种形态 ─────────────────────────────────

_APP_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _naive_timestamp_offenders(source: str, label: str) -> list[str]:
    """AST 扫一处源码：每个 `fromtimestamp(...)` 调用必须带一个不是 `None` 的 `tz=` 关键字。

    为什么不用子串正则：上一版写的是 `fromtimestamp\\([^)]*tz=None`，而真实代码是
    `fromtimestamp(int(post_time), tz=None)` —— `[^)]*` 跨不过 `int(...)` 的右括号，
    **在改前的树上也是 0 命中**（独立复核实测出来的，等于这条常驻守卫从来没在工作）。
    AST 不受嵌套括号影响，还顺带抓住同形的另一种：`fromtimestamp(x)` 干脆不给 `tz`
    （隐式本机时区，和 P-15 是同一件事）。
    """
    tree = ast.parse(source, filename=label)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "fromtimestamp"):
            continue
        tz_kw = next((kw for kw in node.keywords if kw.arg == "tz"), None)
        if tz_kw is None or (isinstance(tz_kw.value, ast.Constant) and tz_kw.value.value is None):
            offenders.append(f"{label}:{node.lineno}")
    return offenders


def test_structure_no_naive_timestamp_left_in_app() -> None:
    """整个 `app/` 里不许再有裸的或 `tz=None` 的 `fromtimestamp`（卡面验收第一条的常驻版）。"""
    offenders: list[str] = []
    for py in sorted((_APP_ROOT / "app").rglob("*.py")):
        offenders += _naive_timestamp_offenders(py.read_text(encoding="utf-8"), py.name)
    assert offenders == [], f"这些 `fromtimestamp` 少了 tz= 或写成 tz=None（P-15 同形）：{offenders}"


def test_structure_naive_timestamp_guard_has_polarity() -> None:
    """判据自检：这条守卫必须**咬得住改前那一行**，也要放过修好的写法。

    没有这一条，上一版的空正则可以一直"绿"下去——那正是它已经发生过的事实。
    """
    assert _naive_timestamp_offenders(
        "import datetime\nx = datetime.datetime.fromtimestamp(int(p), tz=None)\n", "old"
    ) == ["old:2"], "改前的形态抓不到 ⇒ 这条守卫还是空的"
    assert _naive_timestamp_offenders(
        "import datetime\nx = datetime.datetime.fromtimestamp(int(p))\n", "implicit"
    ) == ["implicit:2"], "`fromtimestamp` 不给 tz 也是同形缺陷（隐式本机时区）"
    assert _naive_timestamp_offenders(
        "import datetime\nfrom datetime import UTC\nx = datetime.datetime.fromtimestamp(int(p), tz=UTC)\n",
        "new",
    ) == [], "修好的形态被判红 ⇒ 守卫在逼大家写别的花活"


def test_structure_no_bare_default_dict_get_left_at_the_fixed_sites() -> None:
    """五处已修站点不许漂回 `.get(key, {})`（它兜不住上游给的 JSON `null`）。

    刻意**不**写成"整个 app 禁止这个写法"：`wellbyte.py` 的 `AccountInfo` 也用了它，
    但下一行紧跟 `isinstance` 守卫，是安全的。闸门的宽度应该等于缺陷的宽度，
    多宽一寸就会逼下一张卡去改与自己无关的形状。
    """
    forbidden = (
        'msg.get("AppMsg", {})',
        'msg.get("BaseInfo", {})',
        'item.get("app_msg_ext_info", {})',
        'item.get("comm_msg_info", {})',
        'item.get("source", {})',
    )
    corpus = {
        name: (_APP_ROOT / "app/providers/article_sources" / f"{name}.py").read_text(encoding="utf-8")
        for name in ("dajiala", "justoneapi", "tikhub", "wellbyte")
    }
    hits = [f"{name} :: {pat}" for name, text in corpus.items() for pat in forbidden if pat in text]
    assert hits == [], f"漂回兜不住 null 的写法：{hits}"
    # 同一个兜法：三家的 helper 定义 3 处 + 五处调用点，少于 8 就说明有人改回了就地写法
    assert sum(text.count("_as_dict") for text in corpus.values()) >= 8, "五处站点必须都走 `_as_dict`"


def test_structure_tikhub_degrade_wraps_both_call_sites_not_the_shared_handler() -> None:
    """P-16 的落点是**两个兜底调用点**，不是 `_handle_response`，也不是 `query_work_list`。

    写进结构判据的理由：改共用处理器让所有码返回 None 一样能让行为用例绿，
    而那会同时改掉 discovery 的语义（本卡明确不许）。用 AST 找 `try/except AppError`
    所在的方法，而不是数文本——文本计数能被注释凑够，也能被别人合法新增的 `except` 误判。
    """
    tree = ast.parse(pathlib.Path(tikhub.__file__).read_text(encoding="utf-8"), filename="tikhub.py")
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "TikhubClient")

    def catches_app_error(fn: ast.FunctionDef) -> bool:
        for node in ast.walk(fn):
            if not isinstance(node, ast.ExceptHandler) or node.type is None:
                continue
            names = (
                [node.type]
                if not isinstance(node.type, ast.Tuple)
                else list(node.type.elts)
            )
            if any(isinstance(n, ast.Name) and n.id == "AppError" for n in names):
                return True
        return False

    methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
    assert catches_app_error(methods["fetch_article_detail"]), "detail 入口没兜领域异常"
    assert catches_app_error(methods["search_articles"]), "search 入口没兜领域异常"
    assert not catches_app_error(methods["_handle_response"]), (
        "共用处理器被加了降级 ⇒ discovery 的 5xx 会一起变静默空页"
    )
    assert not catches_app_error(methods["query_work_list"]), "清单主失败不许被兜成空页"
