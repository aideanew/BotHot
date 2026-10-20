"""STEP-03 / S3.1.1：全渠道清单行契约的参数化门（P-1 的常驻版）。

一句话判据：**每家 provider 的样本清单行，经 `manifest._map_row` 都必须得到非 None**，
且行内 `id` / `url` / `title` 三个键齐备。

改前的红（P-1 读数）：dajiala / justoneapi / tikhub / wellbyte 四家**整页被静默丢掉**——
它们的行里没有任何 id 类键（改前只有 `url`/`title`/`digest`/`publish_time`，本批把时间键统一成
`publishTime` 并补上 `id`），而 `_map_row` 在缺 id 时 `return None`（`app/services/manifest.py`
的 `_ID_KEYS` 那一支），`sync_source` 对 None 行
`return None`（`app/services/manifest.py` 的 `_ID_KEYS` 那一支），`sync_source` 对 None 行
直接 `continue` 且不记 `skipped` 之外的账 ⇒ 上游返回 4 条、本地落 0 条，而日志看着像成功。
redfox 绿（上游给 `workUuid`）、rss 绿（自己合成 id）。

为什么门开在"样本 × 行"而不是"provider 单测"：
1. 参数化 id 用**样本文件名** ⇒ 新样本自动纳入，不需要改测试（卡面 S3.1.1.2）；
2. 本文件还有一条"样本必须被认领"的守卫（`test_every_sample_is_claimed_by_a_case`）——
   自动纳入这件事本身要有人守，否则加进去的样本目录与用例表会分叉，
   而分叉的方向恰好是"新渠道静默不测"，那正是这张卡要消灭的形状。

样本是**合成占位值**（见 `tests/fixtures/provider_payloads/README.md`），
所以本文件判的是"形状与链路"，不判"上游真实字段"——活体核实归 STEP-08 S8.5.1，
卡面 R-1 明写本步以样本为准。

────────────────────────────────────────────────────────────────────────────
**同一文件的第二段（S3.4.1 / P-14）判的是详情兜底面**：`fetch_article_detail`、
`search_articles`、`resolve_ghid_from_url`，以及各家 `_request`/`_handle_response` 的
**错误映射**。为什么门开在这里（而不是另起一个文件）：卡面 S3.4.1 的判据命令只收
`test_provider_contract.py + test_rss_provider.py + test_manifest_sync.py` 三个文件算覆盖率，
覆盖率缺口要补就得补在这三个文件里——写在别处的用例对判据读数不存在。

这一段的判据不是「调用一下不炸」，每一条都钉一个**能假的东西**（docstring 里逐条写明）：
1. **降级 vs 抛错的分界**——`base.py` 的协议写死「返回 None 表示该平台不支持详情或获取失败
   （不抛异常，由 coordinator 降级）」，`article_detail_fallback.py` 就是照这句接的；
2. **错误类分界**——上游 5xx/余额/Cloudflare 拦截必须落 `DependencyUnavailableError`
   （502 形状、可重试、该告警），参数/形状/业务码必须落 `DiscoveryFailedError`；写反了
   就是把「付费上游挂了」读成「我方请求错了」，重试与告警两头都失真；
3. **参数名与端点路径**——同平台不同接口参数名不统一（JustOneAPI 发现用 `ghid`、详情用
   `articleUrl`），改一个字母就是调用一个不存在的接口；
4. **字段真来自载荷**——title/author/biz/ghid/正文/时间逐个按 payload 里的具体值判，
   并钉住别名的**优先序**（`nickname` 压 `author`、`create_time` 压 `public_time`、
   `doc_url` 压 `url`……），因为「取错一个键」和「取错优先级」是两种不同的事故。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import (
    ConfigurationError,
    DependencyUnavailableError,
    DiscoveryFailedError,
    RateLimitedUpstreamError,
)
from app.providers.article_sources import (
    ARTICLE_SOURCE_PROVIDERS,
    make_all_article_source_providers,
    make_article_source_provider,
)
from app.providers.article_sources.base import work_list_row_id
from app.providers.article_sources.dajiala import DajialaClient
from app.providers.article_sources.justoneapi import JustOneApiClient
from app.providers.article_sources.tikhub import TikhubClient
from app.providers.article_sources.wellbyte import WellbyteClient
from app.providers.redfox.client import RedfoxClient
from app.services.manifest import _ID_KEYS, _TITLE_KEYS, _URL_KEYS, _first_str, _map_row

SAMPLE_DIR = Path(__file__).parent / "fixtures" / "provider_payloads"

# 样本名 → (构造器, identifier)。构造器收到一个已注入 MockTransport 的 http 客户端。
_BUILDERS: dict[str, Callable[[httpx.AsyncClient], Any]] = {
    "dajiala": lambda http: DajialaClient(api_key="test-" + "key", http=http),
    "justoneapi": lambda http: JustOneApiClient(api_key="test-" + "key", http=http),
    "tikhub": lambda http: TikhubClient(api_key="test-" + "key", http=http),
    "wellbyte": lambda http: WellbyteClient(api_key="test-" + "key", http=http),
    "redfox": lambda http: RedfoxClient(base_url="https://redfox.test", api_key="test-" + "key", http=http),
}
# identifier 只是占位入参（清单键的形状与它无关）；RSS 走 test_rss_provider.py，不在这里。
_IDENTIFIER = "MjM5MjgwNTQ1MQ=="

# S3.2.1–4 的改造范围：这四家必须输出字面 `id`（`WorkListRow.id`）。
# redfox 不在其中——它是上游原样透传的参照实现，键名归一不归本卡。
_CANONICAL_ID = ("dajiala", "justoneapi", "tikhub", "wellbyte")

# 样本认领表：payload 名（顶层文件用不含后缀的文件名，子目录用相对 POSIX 路径）→ 认领它的用例。
# 这张表是 `test_every_sample_is_claimed_by_a_case` 的唯一分母，与 `_BUILDERS` 并行存在是故意的：
# `_BUILDERS` 只说「谁能吃这份样本」，这张表还说「哪个判据在吃」——加样本不加判据时它会红。
_SAMPLE_CLAIMS: dict[str, str] = {
    # 清单行面（S3.1.1，按 _BUILDERS 参数化自动纳入）
    "dajiala": "test_sample_yields_rows / test_rows_carry_id_url_title / "
    "test_canonical_id_key_on_normalized_channels / test_rows_survive_map_row / "
    "test_missing_key_fails_loudly_instead_of_empty_list",
    "justoneapi": "同上（清单行五件套，样本名参数化）",
    "tikhub": "同上（清单行五件套，样本名参数化）",
    "wellbyte": "同上（清单行五件套，样本名参数化）",
    "redfox": "同上（清单行五件套；redfox 只判别名组那一层）",
    # RSS 的 XML 载荷：由证明件读，解析面另有常驻用例
    "rss2": "docs/06_validation/evidence/EVD-V2-00/prove_provider_shapes.py 逐行喂给 _parse_feed；"
    "解析面本身由 tests/test_rss_provider.py::TestRSS2Parse 与 TestPublishTimeRfc822 判",
    "atom": "同上证明件的 atom 分支；解析面由 tests/test_rss_provider.py::TestAtomParse 判",
    # 详情兜底面（S3.4.1 / P-14）
    "dajiala_detail": "test_dajiala_detail_maps_every_field_from_payload / "
    "test_dajiala_detail_content_text_is_stripped_html",
    "dajiala_search": "test_dajiala_search_maps_payload_rows_and_request_shape",
    "justoneapi_detail": "test_justoneapi_detail_maps_items_first_row_and_field_aliases",
    "justoneapi_search": "test_justoneapi_search_maps_rows_and_url_alias_priority",
    "tikhub_detail": "test_tikhub_detail_maps_fields_and_request_shape",
    "tikhub_search": "test_tikhub_search_maps_rows_with_doc_url_priority",
    "wellbyte_search": "test_wellbyte_search_maps_rows_and_request_shape / "
    "test_wellbyte_search_publish_time_accepts_epoch_only",
}

# 详情/搜索入参（值本身不参与断言，除「产物 url 必须回显入参」那一条）
_ARTICLE_URL = "https://mp.weixin.qq.com/s?__biz=MjM5MjgwNTQ1MQ==&mid=2650000001&idx=1&sn=aaaa1111"
_KEYWORD = "人工智能观测"
_EPOCH = 1790659200  # 与清单样本同口径的合成时间戳


def _payload_of(sample: str) -> Any:
    return json.loads((SAMPLE_DIR / f"{sample}.json").read_text(encoding="utf-8"))


def _client(sample: str) -> httpx.AsyncClient:
    """把样本原样回成上游响应：任何 URL 都返回它，provider 自己的解析路径照常走。"""
    path = SAMPLE_DIR / f"{sample}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(_handler))


async def _rows(sample: str) -> list[dict[str, Any]]:
    provider = _BUILDERS[sample](_client(sample))
    try:
        rows, _total = await provider.query_work_list(_IDENTIFIER, 1)
    finally:
        await provider.aclose()
    return rows


@pytest.mark.parametrize("sample", sorted(_BUILDERS))
async def test_sample_yields_rows(sample: str) -> None:
    """前提守卫：样本必须真的产出行。空列表会让下面两条断言**空转成真**。"""
    rows = await _rows(sample)
    assert rows, f"{sample} 的样本经 provider 解析后一行都没有——链路或样本变了，下面两条会失去判定力"


@pytest.mark.parametrize("sample", sorted(_BUILDERS))
async def test_rows_carry_id_url_title(sample: str) -> None:
    """契约面（第一层，全渠道）：每行都必须能解出 id/url/title —— 按**别名组**判，不按字面键名判。

    为什么不写死 `row["id"]`：redfox 是上游原样透传（`workUuid`/`workUrl`/`publishTime`，
    `client.py` 的 `query_work_list` 零归一），而卡面 S3.2 的改造范围是四家付费 provider，
    改 redfox 的输出键名不在本卡授权内（它会连带动 `test_manifest_sync` 的一串上游形状断言）。
    别名组就是 `_map_row` 自己用的那一组 ⇒ 这一层判的是"消费端能不能解出来"，与 P-1 同源。

    第二层（`test_canonical_id_key_on_normalized_channels`）才判字面 `id`：
    那是 S3.2.1–4 的产出物，缺了就说明"归一"没真发生。
    """
    for i, row in enumerate(await _rows(sample)):
        assert _first_str(row, _ID_KEYS), f"{sample} 第 {i} 行解不出 id：{_keys(row)}"
        assert _first_str(row, _URL_KEYS), f"{sample} 第 {i} 行解不出 url：{_keys(row)}"
        assert _first_str(row, _TITLE_KEYS), f"{sample} 第 {i} 行解不出 title：{_keys(row)}"


@pytest.mark.parametrize("sample", sorted(_CANONICAL_ID))
async def test_canonical_id_key_on_normalized_channels(sample: str) -> None:
    """契约面（第二层，S3.2 改造范围内的渠道）：行里必须**真的**有 `id` 键。

    只在别名组上判会放过一种情况：provider 依旧只写 `workUuid`，测试照样绿，
    而卡面"所有 provider 输出 `WorkListRow`"从未成立——所以这一层单独钉。
    """
    for i, row in enumerate(await _rows(sample)):
        assert str(row.get("id") or ""), f"{sample} 第 {i} 行没有规范键字段 `id`：{_keys(row)}"


@pytest.mark.parametrize("sample", sorted(_BUILDERS))
async def test_rows_survive_map_row(sample: str) -> None:
    """消费面：`_map_row` 不许再把任何一行判成 None（整页静默丢弃的那条路径）。

    这条与上面两条**不是重复**：上面判 provider 产出，这条判 manifest 消费；
    任一端回退都会红，两端同时退化也照样红。
    """
    for i, row in enumerate(await _rows(sample)):
        mapped = _map_row(row)
        assert mapped is not None, f"{sample} 第 {i} 行被 `_map_row` 判成不可用（P-1 形状）：{_keys(row)}"
        assert mapped["external_id"] == _first_str(row, _ID_KEYS), (
            f"{sample} 第 {i} 行的 id 没被当 external_id 用：{mapped['external_id']!r}"
        )


def _keys(row: dict[str, Any]) -> list[str]:
    return sorted(row)


@pytest.mark.parametrize("sample", sorted(_BUILDERS))
async def test_missing_key_fails_loudly_instead_of_empty_list(sample: str) -> None:
    """没有 Key 必须**显式失败**，不许返回空清单冒充成功（仓库既有口径，redfox 那条注释写得很清楚）。

    这条与上面三条判的是同一族缺陷的另一半：`_map_row` 丢整行是"静默"，
    `query_work_list` 返回 `[]` 也是"静默"——两者都会让一轮同步看起来正常而实际零入库。
    """
    provider = _BUILDERS[sample](_client(sample))
    provider._api_key = ""  # noqa: SLF001  四家与 redfox 都用同一个 `self._api_key` 名字
    try:
        with pytest.raises(DependencyUnavailableError):
            await provider.query_work_list(_IDENTIFIER, 1)
    finally:
        await provider.aclose()


# ══════════════════════════════════════════════════════════════════════════
# S3.4.1（P-14）：详情兜底 / 关键词搜索 / `_request` 错误映射
#
# 上面那五条判据把「清单行」这一族钉死了，覆盖率却停在 43–52%——缺口正是
# `fetch_article_detail`、`search_articles` 与错误映射三族（卡面 P-14 现读锚）。
# 这一段把它们补齐；每条 docstring 都写明「改坏什么它就会红」，
# 反证实际跑过的那几发记在 docs/06_validation/evidence/EVD-V2-02/s341_provider_coverage.md。
# ══════════════════════════════════════════════════════════════════════════

_MISSING = object()

# 构造「自己持有 httpx 客户端」的 provider（不注入 http ⇒ 走 `_owns_http=True` 那一支）
_OWNED_BUILDERS: dict[str, Callable[[], Any]] = {
    "dajiala": lambda: DajialaClient(api_key="test-" + "key"),
    "justoneapi": lambda: JustOneApiClient(api_key="test-" + "key"),
    "tikhub": lambda: TikhubClient(api_key="test-" + "key"),
    "wellbyte": lambda: WellbyteClient(api_key="test-" + "key"),
}


@pytest.fixture
async def make_upstream_provider():
    """造「注入 MockTransport 的 provider + 它发出的请求清单」，用例结束统一关连接。

    载荷来源四选一：`sample=`（读本目录样本）、`payload=`（用例内联的异常形状）、
    `status=`/`body_text=`（HTTP 层错误映射）、`transport_error=`（连不上上游）。
    默认回该渠道的清单样本，让 detail/search 的判据能复用同一份构造器注册表。
    """
    opened: list[tuple[Any, httpx.AsyncClient]] = []

    def _build(
        channel: str,
        *,
        sample: str | None = None,
        payload: Any = _MISSING,
        status: int = 200,
        body_text: str | None = None,
        transport_error: Exception | None = None,
    ) -> tuple[Any, list[httpx.Request]]:
        seen: list[httpx.Request] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            if transport_error is not None:
                raise transport_error
            if body_text is not None:
                return httpx.Response(status, text=body_text)
            body = payload if payload is not _MISSING else _payload_of(sample or channel)
            return httpx.Response(status, json=body)

        http = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
        provider = _BUILDERS[channel](http)
        opened.append((provider, http))
        return provider, seen

    yield _build
    for provider, http in opened:
        await provider.aclose()
        await http.aclose()


def _json_body(request: httpx.Request) -> Any:
    """请求体（provider 用 json= 发的东西）——参数名打错一个字母就是一次 404。"""
    return json.loads(request.content)


def _query(request: httpx.Request) -> dict[str, str]:
    return dict(request.url.params)


@pytest.mark.parametrize("channel", sorted(_CANONICAL_ID))
async def test_owned_http_client_is_closed_and_injected_one_is_not(channel: str) -> None:
    """`aclose()` 的归属判据：自己造的客户端必须关，注入的必须**不**关。

    两半各有靶：把 `_owns_http` 恒置 False ⇒ 自建客户端永远不关（连接泄漏）；
    去掉那个 `if` ⇒ 把调用方注入的客户端也关掉，下一个调用点拿到已关闭的连接池。
    """
    owned = _OWNED_BUILDERS[channel]()
    assert owned._owns_http is True
    assert owned._http.is_closed is False
    await owned.aclose()
    assert owned._http.is_closed is True, "自己造的客户端 aclose 后仍是开的"

    borrowed_http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    borrowed = _BUILDERS[channel](borrowed_http)
    assert borrowed._owns_http is False
    await borrowed.aclose()
    assert borrowed_http.is_closed is False, "aclose 不许替调用方关掉它注入的连接"
    await borrowed_http.aclose()


@pytest.mark.parametrize("channel", sorted(_CANONICAL_ID))
async def test_list_page_beyond_the_first_makes_no_upstream_call(channel: str, make_upstream_provider) -> None:
    """四家的 page>1 都必须**不发请求**就返回空（游标要上页返回值，无法预构）。

    这条判的是额度：post_condition ¥0.14/次、Wellbyte 78cr/次，翻页参数在上游根本不存在，
    发出去就是白烧。变异：把 `if page > 1` 那行删掉 ⇒ 本条红（seen 非空）。
    """
    provider, seen = make_upstream_provider(channel)
    rows, total = await provider.query_work_list(_IDENTIFIER, 2)
    assert rows == []
    assert total in (0, None), f"{channel} 的末页语义漂移：total={total!r}（0=按空页终止，None=自报无 total）"
    assert seen == []


# ── Dajiala ─────────────────────────────────────────────────────────────


async def test_dajiala_detail_maps_every_field_from_payload(make_upstream_provider) -> None:
    """article_html 的每个产物字段都要落到载荷里的具体键，并打对端点、带对参数。

    能让它红的变异：`data.get("html")` 改成 `data.get("content")`（载荷无此键 ⇒ 整条降级
    None）；`nickname or author` 优先级对调 ⇒ author 变「占位作者名」；
    删掉 `fromtimestamp(post_time)` ⇒ publish_time 为 None；端点写成 docstring 里
    标注「data 恒 null、已禁用」的 `article_detail`，或 body 的 `url` 改名 ⇒ 末两条红。
    """
    provider, seen = make_upstream_provider("dajiala", sample="dajiala_detail")
    data = _payload_of("dajiala_detail")["data"]

    detail = await provider.fetch_article_detail(_ARTICLE_URL)

    assert detail is not None, "活体实测 TC-A1-07 可用的端点，载荷齐备却判成 None"
    assert detail.url == _ARTICLE_URL, "详情产物要回显被查询的 URL，不是上游某字段"
    assert detail.title == data["title"]
    assert detail.content_html == data["html"]
    assert detail.author == data["nickname"], "作者别名优先序：nickname 压 author"
    assert detail.biz == data["biz"]
    assert detail.ghid == data["gh_id"]
    assert detail.source == "dajiala"
    assert detail.publish_time is not None
    assert detail.publish_time.timestamp() == data["post_time"]

    assert len(seen) == 1, "一次详情一次上游（¥0.04/次），重试归上层不归这里"
    request = seen[0]
    assert request.url.path.endswith("/fbmain/monitor/v3/article_html")
    assert _json_body(request) == {"key": "test-key", "verifycode": "", "url": _ARTICLE_URL}


async def test_dajiala_detail_content_text_is_stripped_and_capped(make_upstream_provider) -> None:
    """`content_text` 是「去标签再截 200 字」的兜底纯文本：不许残留标签、不许超 200。

    红的变异：去掉 `[:200]` ⇒ 后半段红；`_strip_html` 改成原样返回 ⇒ 前半段红。
    """
    provider, _ = make_upstream_provider("dajiala", sample="dajiala_detail")
    detail = await provider.fetch_article_detail(_ARTICLE_URL)
    assert detail is not None
    assert "<" not in detail.content_text, "兜底纯文本里还留着标签"
    assert "第一段正文" in detail.content_text

    long_html = "<p>" + "长正文占位句。" * 80 + "</p>"
    roomy, _ = make_upstream_provider("dajiala", payload={"code": 0, "data": {"html": long_html}})
    capped = await roomy.fetch_article_detail(_ARTICLE_URL)
    assert capped is not None
    assert len(capped.content_text) == 200, "200 字是兜底口径上限（正式清洗交给 extractor）"
    assert capped.title == "", "载荷没给 title ⇒ 留空串，不许拿正文顶上"


async def test_dajiala_detail_without_key_never_calls_the_paid_endpoint(make_upstream_provider) -> None:
    """没有 key 就不许问上游：详情端点按次扣费，缺凭据的那一问是白烧。

    红的变异：把 `if not self._api_key: return None` 删掉 ⇒ seen 非空。
    """
    provider, seen = make_upstream_provider("dajiala", sample="dajiala_detail")
    provider._api_key = ""
    assert await provider.fetch_article_detail(_ARTICLE_URL) is None
    assert seen == []


_DAJIALA_DETAIL_FAILURES = [
    pytest.param({"status": 503}, id="上游5xx"),
    pytest.param({"status": 400, "body_text": "bad request"}, id="上游4xx"),
    pytest.param({"body_text": "<html>nginx 502</html>"}, id="响应体不是JSON"),
    pytest.param({"transport_error": httpx.ConnectError("connection refused")}, id="传输层不可达"),
    pytest.param({"payload": {"code": -1, "msg": "参数错误"}}, id="业务码-1"),
    pytest.param({"payload": {"code": 700, "msg": "余额不足，请充值"}}, id="业务码余额不足"),
]


@pytest.mark.parametrize("kwargs", _DAJIALA_DETAIL_FAILURES)
async def test_dajiala_detail_swallows_domain_errors_for_the_coordinator(
    make_upstream_provider, kwargs: dict[str, Any]
) -> None:
    """详情兜底的六种失败必须一律降成 None，不许把 AppError 抛给协调器。

    `base.py` 的协议写死「返回 None 表示不支持或获取失败（不抛异常，由 coordinator 降级）」，
    而 `article_detail_fallback.py::fetch_detail` 正是照这句接的（降级由本文件里
    `fetch_article_detail` 的 `except AppError` 那一支兑现）。
    红的变异：把 `except AppError` 收窄成 `except DiscoveryFailedError` ⇒ 「上游5xx」与
    「传输层不可达」两发直接穿透成异常；整段 try 删掉 ⇒ 六发全红。
    """
    provider, seen = make_upstream_provider("dajiala", **kwargs)
    assert await provider.fetch_article_detail(_ARTICLE_URL) is None
    assert len(seen) <= 1, "降级路径不该自己重试"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"code": 0, "data": None}, id="data为null"),
        pytest.param({"code": 0, "data": [{"html": "<p>串了清单形状</p>"}]}, id="data是数组"),
        pytest.param({"code": 0, "data": {"title": "有标题没正文"}}, id="data里没有html键"),
        pytest.param({"code": 0, "data": {"html": ""}}, id="html是空串"),
    ],
)
async def test_dajiala_detail_returns_none_on_unusable_payload(
    make_upstream_provider, payload: dict[str, Any]
) -> None:
    """载荷「在但没用」时判 None——而判 None 之前确实问过上游（不是没调用就当失败）。

    红的变异：删掉 `if not isinstance(data, dict): return None` ⇒ 前两发在
    `data.get(...)` 上抛 AttributeError；删掉 `if not html: return None` ⇒
    后两发返回一条正文空白的 ArticleDetail，协调器收下并计入命中。
    """
    provider, seen = make_upstream_provider("dajiala", payload=payload)
    assert await provider.fetch_article_detail(_ARTICLE_URL) is None
    assert len(seen) == 1


async def test_dajiala_detail_keeps_the_paid_body_when_the_epoch_is_out_of_range(
    make_upstream_provider,
) -> None:
    """上游把毫秒当秒（常见事故）时：时间留空，但**已付费的正文必须留下**。

    红的变异：把 `try/except (ValueError, OSError)` 摘掉 ⇒ fromtimestamp 越界直接抛穿，
    整条详情消失；或把 `publish_time` 兜成 `datetime.now()` ⇒ 「留空」这条判据红
    （编出来的时间会污染日报的业务日界）。
    """
    provider, _ = make_upstream_provider(
        "dajiala",
        payload={
            "code": 0,
            "data": {"html": "<p>花钱买到的正文</p>", "title": "示例：毫秒时间戳", "post_time": 1790659200000},
        },
    )
    detail = await provider.fetch_article_detail(_ARTICLE_URL)
    assert detail is not None
    assert detail.content_html == "<p>花钱买到的正文</p>"
    assert detail.publish_time is None, "epoch 越界应只丢时间，不丢整条详情"


async def test_dajiala_search_maps_rows_and_sends_only_the_keyword(make_upstream_provider) -> None:
    """kw_search（端点存在但未实测）：行字段逐一对应载荷，请求体只有 key/verifycode/keyword。

    红的变异：`item.get("url")` 改名 ⇒ 第一发（映射）红；把 `sort`/`time_range` 顺手塞进
    body ⇒ 第二发（参数形状）红——这两个形参在 dajiala 上目前**不生效**，是契约级实现的
    已知缺口，把它悄悄变成「发出去但上游不认」比留空更坏，所以这里钉住现状。
    """
    provider, seen = make_upstream_provider("dajiala", sample="dajiala_search")
    rows = _payload_of("dajiala_search")["data"]

    results = await provider.search_articles(_KEYWORD, sort="relevant", time_range="7d")

    assert len(results) == len(rows) == 2
    assert results[0].url == rows[0]["url"]
    assert results[0].title == rows[0]["title"]
    assert results[0].digest == rows[0]["digest"]
    assert results[0].author == rows[0]["nickname"]
    assert results[1].author == ""
    assert results[0].source == "dajiala"
    assert all(r.publish_time is None for r in results), "kw_search 未实测，不许假装解得出时间"

    request = seen[0]
    assert request.url.path.endswith("/fbmain/monitor/v3/kw_search")
    assert _json_body(request) == {"key": "test-key", "verifycode": "", "keyword": _KEYWORD}


@pytest.mark.parametrize("kwargs", _DAJIALA_DETAIL_FAILURES)
async def test_dajiala_search_degrades_to_empty_list(make_upstream_provider, kwargs: dict[str, Any]) -> None:
    """搜索的六种失败一律降成 []——空列表在这里是「没有结果」，不是「没调用成功」。

    与详情那六发用的是同一张失败表（`_request` 抛什么，搜索就吞什么）。
    红的变异：删掉 `except AppError` ⇒ 5xx/传输层/业务码三发抛穿；
    「data 不是数组」那一族不在本表里，由
    `test_dajiala_search_drops_non_dict_rows_and_bails_on_object_data` 单独判（删掉
    `isinstance(data, list)` 守卫会在那里红，而不是在这里）。
    """
    provider, _ = make_upstream_provider("dajiala", **kwargs)
    assert await provider.search_articles(_KEYWORD) == []


async def test_dajiala_search_drops_non_dict_rows_and_bails_on_object_data(make_upstream_provider) -> None:
    """上游在 data 里混进字符串 ⇒ 跳该行、保住其余行；data 是对象 ⇒ 整次判空而不是崩。

    红的变异：把 `if not isinstance(item, dict): continue` 删掉 ⇒ 第一发在
    `item.get` 上 AttributeError；把 `if not isinstance(data, list): return []` 删掉 ⇒
    第二发把 dict 的键当行遍历、产出一条 url 为空串的假结果。
    """
    mixed, _ = make_upstream_provider(
        "dajiala",
        payload={"code": 0, "data": ["字符串行", {"url": _ARTICLE_URL, "title": "唯一有效行"}]},
    )
    results = await mixed.search_articles(_KEYWORD)
    assert [r.title for r in results] == ["唯一有效行"]
    assert [r.url for r in results] == [_ARTICLE_URL]

    objecty, seen = make_upstream_provider("dajiala", payload={"code": 0, "data": {"items": []}})
    assert await objecty.search_articles(_KEYWORD) == []
    assert len(seen) == 1


async def test_dajiala_detail_without_key_and_search_without_key_stay_silent(make_upstream_provider) -> None:
    """详情/搜索缺 key 是「降级」，清单缺 key 是「显式失败」——同一个 key，两种口径。

    这条钉的是**分界本身**（清单那半边由 `test_missing_key_fails_loudly_instead_of_empty_list`
    判，这里判详情/搜索那半边）：兜底路径在协调器里，抛异常会把整条采集链打断。
    红的变异：给 `fetch_article_detail` 的缺 key 分支加上 `raise` ⇒ 本条红。
    """
    detail_provider, detail_seen = make_upstream_provider("dajiala", sample="dajiala_detail")
    search_provider, search_seen = make_upstream_provider("dajiala", sample="dajiala_search")
    detail_provider._api_key = ""
    search_provider._api_key = ""

    assert await detail_provider.fetch_article_detail(_ARTICLE_URL) is None
    assert await search_provider.search_articles(_KEYWORD) == []
    assert detail_seen == [] and search_seen == []


# ── Dajiala 的 HTTP 层（`_request` 的错误映射，P-14 点名的最贵一族）──────


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        pytest.param(500, DependencyUnavailableError, id="500→依赖不可用"),
        pytest.param(502, DependencyUnavailableError, id="502→依赖不可用"),
        pytest.param(503, DependencyUnavailableError, id="503→依赖不可用"),
        pytest.param(400, DiscoveryFailedError, id="400→发现失败"),
        pytest.param(401, DiscoveryFailedError, id="401→发现失败"),
        pytest.param(404, DiscoveryFailedError, id="404→发现失败"),
    ],
)
async def test_dajiala_status_code_error_class_split(make_upstream_provider, status: int, expected: type) -> None:
    """5xx ⇒ `DependencyUnavailableError`（上游挂了，可重试、该告警）；
    4xx ⇒ `DiscoveryFailedError`（我们的请求不对，重试也不会有变化）。

    写反的后果不是日志难看：502 形状的异常才会让上层把「付费上游不可用」当依赖故障处理，
    反过来则会把上游故障读成我方参数错误。
    红的变异：把 `>= 500` 与 `>= 400` 两支的异常类对调 ⇒ 六发里至少两发红。
    """
    provider, _ = make_upstream_provider(
        "dajiala", status=status, body_text="upstream exploded" if status >= 500 else "bad request"
    )
    with pytest.raises(expected):
        await provider.query_work_list(_IDENTIFIER, 1)


async def test_dajiala_body_and_shape_error_mapping(make_upstream_provider) -> None:
    """非 JSON 体与顶层非对象各自落 `DiscoveryFailedError`，且异常文案只带截断后的响应。

    红的变异：把「非 JSON ⇒ 抛」改成「非 JSON ⇒ 兜成空 dict」⇒ 第一发不再抛，而是把
    一个空载荷当成功（P-1 的静默族）；删掉顶层 `isinstance(payload, dict)` 守卫 ⇒
    第二发在 `payload.get` 上抛 AttributeError 而不是 DiscoveryFailedError；
    去掉 `resp.text[:160]` 的截断 ⇒ 最后那段红（整页上游 HTML 进异常文案与日志）。
    """
    non_json, _ = make_upstream_provider("dajiala", body_text="<html><body>502 Bad Gateway</body></html>")
    with pytest.raises(DiscoveryFailedError, match="非 JSON"):
        await non_json.query_work_list(_IDENTIFIER, 1)

    array, _ = make_upstream_provider("dajiala", payload=[{"url": _ARTICLE_URL}])
    with pytest.raises(DiscoveryFailedError, match="非对象"):
        await array.query_work_list(_IDENTIFIER, 1)

    huge_msg = "E" * 400
    noisy, _ = make_upstream_provider("dajiala", status=400, body_text=huge_msg)
    with pytest.raises(DiscoveryFailedError) as excinfo:
        await noisy.query_work_list(_IDENTIFIER, 1)
    assert "E" * 160 in str(excinfo.value)
    assert "E" * 161 not in str(excinfo.value), "响应体截断失效：整段上游 HTML 进异常文案"


async def test_dajiala_transport_error_becomes_dependency_unavailable(make_upstream_provider) -> None:
    """传输层异常（DNS/拒连/超时）必须映射成依赖不可用，且保留 `from exc` 的因。

    红的变异：把 `except httpx.HTTPError` 换成 `except httpx.ConnectError` ⇒
    读超时那一发（`ReadTimeout`）抛穿；把 `raise ... from exc` 的 `from` 去掉 ⇒
    最后一条断言红（丢因之后，运维只看到「不可达」而看不到是哪一层先炸）。
    """
    for error in (httpx.ConnectError("connection refused"), httpx.ReadTimeout("read timeout")):
        provider, _ = make_upstream_provider("dajiala", transport_error=error)
        with pytest.raises(DependencyUnavailableError) as excinfo:
            await provider.query_work_list(_IDENTIFIER, 1)
        assert isinstance(excinfo.value.__cause__, httpx.HTTPError)


@pytest.mark.parametrize(
    ("code", "msg", "expected"),
    [
        pytest.param(-1, "参数错误", DiscoveryFailedError, id="code=-1→参数错误"),
        pytest.param(403, "余额不足，请充值", DependencyUnavailableError, id="余额→依赖不可用"),
        pytest.param(403, "no money left", DependencyUnavailableError, id="money→依赖不可用"),
        pytest.param(500, "系统繁忙", DiscoveryFailedError, id="其它码→发现失败"),
    ],
)
async def test_dajiala_business_code_routing(make_upstream_provider, code: Any, msg: str, expected: type) -> None:
    """业务码三分类：-1 是参数错（不扣费）、含「余额/money」是额度耗尽（依赖不可用）、其余是发现失败。

    这条最贵的一发是「余额不足 ⇒ DependencyUnavailableError」：额度耗尽是**上游不可用**，
    判成 DiscoveryFailed 就没人去充值，发现链会一直红着但形状像「我方参数错了」。
    红的变异：删掉 `if "余额" in msg or "money" in msg.lower()` 那一支 ⇒ 两发红。
    """
    provider, _ = make_upstream_provider("dajiala", payload={"code": code, "msg": msg, "data": []})
    with pytest.raises(expected):
        await provider.query_work_list(_IDENTIFIER, 1)


async def test_dajiala_list_payload_defence(make_upstream_provider) -> None:
    """清单端点的 data 不是数组 ⇒ 显式失败；数组里混入非对象 ⇒ 只跳那一行。

    红的变异：把 `if not isinstance(data, list): raise DiscoveryFailedError` 改成
    `return [], 0` ⇒ 第一发红（响应形状坏了却读成「今天没有新文章」，正是 P-1 的静默族）；
    删掉行级 isinstance 守卫 ⇒ 第二发 AttributeError。
    """
    not_list, _ = make_upstream_provider("dajiala", payload={"code": 0, "data": {"url": _ARTICLE_URL}})
    with pytest.raises(DiscoveryFailedError, match="缺 data 数组"):
        await not_list.query_work_list(_IDENTIFIER, 1)

    mixed, _ = make_upstream_provider("dajiala", payload={"code": 0, "data": ["字符串行",
                                                                            {"url": _ARTICLE_URL, "title": "T"}]})
    rows, total = await mixed.query_work_list(_IDENTIFIER, 1)
    assert [r["url"] for r in rows] == [_ARTICLE_URL]
    assert total == 1


# ── JustOneAPI ──────────────────────────────────────────────────────────


async def test_justoneapi_detail_maps_first_row_and_field_aliases(make_upstream_provider) -> None:
    """详情取 `data.data[0]`，正文/号名/ghid/时间逐个按载荷具体键判，GET 参数名逐字钉住。

    红的变异：`items[0]` 改成 `items[-1]` ⇒ title 断言红（样本第二行标题不同，是故意的）；
    `content` 读成 `content_url` ⇒ 正文空 ⇒ 整条降 None ⇒ 第一条断言红；
    `create_time or public_time` 的优先序对调 ⇒ 两行时间断言同时红；
    端点写成 `/v5`（docstring 记它「仅元数据、无正文」）或把参数名 `articleUrl` 写成 `url`
    ⇒ 最后两条红。参数名不统一是同平台实测踩过的（发现用 ghid、详情用 articleUrl）。
    """
    provider, seen = make_upstream_provider("justoneapi", sample="justoneapi_detail")
    item = _payload_of("justoneapi_detail")["data"]["data"][0]

    detail = await provider.fetch_article_detail(_ARTICLE_URL)

    assert detail is not None, "活体实测 TC-A3-07 含正文的端点，载荷齐备却判成 None"
    assert detail.url == _ARTICLE_URL
    assert detail.title == item["title"], "只该取 data.data[0]"
    assert detail.content_html == item["content"]
    assert detail.content_text == item["content_multi_text"]
    assert detail.author == item["nick_name"], "author 为空串时必须回落 nick_name"
    assert detail.ghid == item["user_name"], "ghid 为空串时必须回落 user_name"
    assert detail.biz == item["biz"]
    assert detail.source == "justoneapi"
    assert detail.publish_time is not None
    assert detail.publish_time.timestamp() == item["create_time"]
    assert detail.publish_time.timestamp() != item["public_time"], "create_time 优先于 public_time"

    request = seen[0]
    assert request.method == "GET"
    assert request.url.path.endswith("/api/weixin/get-article-detail/v1")
    assert _query(request) == {"token": "test-" + "key", "articleUrl": _ARTICLE_URL}


async def test_justoneapi_detail_derives_text_when_rich_text_is_absent(make_upstream_provider) -> None:
    """上游没给 `content_multi_text` 时，纯文本由 HTML 去标签兜出（截 200），不许留空。

    红的变异：删掉「content_text 为空则 re.sub」那一支 ⇒ content_text == "" ⇒ 本条红；
    反过来把它改成「永远用 re.sub」⇒ 上一条（rich text 优先）红。两支合起来才钉住优先级。
    """
    html = "<div><p>只有 HTML 的正文</p><img src=x></div>" + "<p>补长用。</p>" * 60
    provider, _ = make_upstream_provider(
        "justoneapi", payload={"code": 0, "data": {"data": [{"title": "T", "content": html}]}}
    )
    detail = await provider.fetch_article_detail(_ARTICLE_URL)
    assert detail is not None
    assert "只有 HTML 的正文" in detail.content_text
    assert "<" not in detail.content_text
    assert len(detail.content_text) == 200
    assert detail.publish_time is None, "载荷没给时间 ⇒ 留空，不拿入库时间冒充发布时间"


async def test_justoneapi_detail_without_key_never_calls_the_paid_endpoint(make_upstream_provider) -> None:
    provider, seen = make_upstream_provider("justoneapi", sample="justoneapi_detail")
    provider._api_key = ""
    assert await provider.fetch_article_detail(_ARTICLE_URL) is None
    assert seen == []


_JUSTONEAPI_DETAIL_FAILURES = [
    pytest.param({"status": 500}, id="上游5xx"),
    pytest.param({"status": 404, "body_text": "not found"}, id="上游404"),
    pytest.param({"body_text": "token invalid"}, id="响应体不是JSON"),
    pytest.param({"payload": ["顶层是数组"]}, id="顶层形状异常"),
    pytest.param({"payload": {"code": 40001, "message": "余额不足"}}, id="业务码余额不足"),
    pytest.param({"payload": {"code": 42901, "message": "请求限频，请稍后"}}, id="业务码限频"),
    pytest.param({"transport_error": httpx.ConnectError("connection refused")}, id="传输层不可达"),
]


@pytest.mark.parametrize("kwargs", _JUSTONEAPI_DETAIL_FAILURES)
async def test_justoneapi_detail_suppresses_every_upstream_failure(
    make_upstream_provider, kwargs: dict[str, Any]
) -> None:
    """详情走 `suppress_errors=True` 那一支：七种上游失败全部降成 None。

    这条与 dajiala 那条判的是同一个契约、但不同的实现支路——这里降级发生在
    `_handle_response` 内部（每支都 `if suppress_errors: return None`），
    所以它同时是「suppress 分支存在」的判据。
    红的变异：把 `suppress_errors` 默认值改成 False ⇒ 前五发抛穿；把 5xx 那支的
    `return None` 删掉 ⇒ 「上游5xx」一发红。
    """
    provider, _ = make_upstream_provider("justoneapi", **kwargs)
    assert await provider.fetch_article_detail(_ARTICLE_URL) is None


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"code": 0, "data": "字符串"}, id="data不是对象"),
        pytest.param({"code": 0, "data": {"data": "字符串"}}, id="data.data不是数组"),
        pytest.param({"code": 0, "data": {"data": []}}, id="data.data是空数组"),
        pytest.param({"code": 0, "data": {"data": ["字符串行"]}}, id="首行不是对象"),
        pytest.param({"code": 0, "data": {"data": [{"title": "两个正文字段都没有"}]}}, id="正文两键全空"),
    ],
)
async def test_justoneapi_detail_returns_none_on_unusable_payload(
    make_upstream_provider, payload: dict[str, Any]
) -> None:
    """嵌套形状坏在任何一层都判 None——而不是抛 AttributeError 把协调器打断。

    红的变异：删掉 `if not isinstance(items, list) or not items` ⇒ 第 2/3 发红；
    删掉 `if not content_html and not content_text: return None` ⇒ 最后一发返回空正文详情。
    """
    provider, seen = make_upstream_provider("justoneapi", payload=payload)
    assert await provider.fetch_article_detail(_ARTICLE_URL) is None
    assert len(seen) == 1


async def test_justoneapi_detail_keeps_the_paid_body_when_the_epoch_is_out_of_range(
    make_upstream_provider,
) -> None:
    """毫秒当秒的 create_time（与 dajiala 同一族上游事故）⇒ 时间留空、正文留下。

    红的变异：摘掉 `except (ValueError, OSError): pass` ⇒ fromtimestamp 越界抛穿，
    整条已付费详情消失；或让它退回 `public_time` ⇒ 「不许退回次选键」那条红。
    """
    provider, _ = make_upstream_provider(
        "justoneapi",
        payload={
            "code": 0,
            "data": {
                "data": [
                    {"title": "毫秒时间戳", "content": "<p>花钱买到的正文</p>",
                     "create_time": 1790659200000, "public_time": _EPOCH}
                ]
            },
        },
    )
    detail = await provider.fetch_article_detail(_ARTICLE_URL)
    assert detail is not None
    assert detail.content_html == "<p>花钱买到的正文</p>"
    assert detail.publish_time is None, "越界 epoch 只该丢时间，不该退回次选键也不该丢掉正文"


async def test_justoneapi_search_maps_rows_and_url_alias_priority(make_upstream_provider) -> None:
    """搜索（契约级实现）：`url` 压 `content_url`、`author` 压 `nick_name`，GET 带 token+keyword。

    红的变异：把 `item.get("url","") or item.get("content_url","")` 的次序对调 ⇒
    第一行 URL 红；删掉 `or item.get("nick_name","")` ⇒ 第二行作者红；
    端点写成 `/v2` 或把 keyword 改名 ⇒ 末两条红。
    """
    provider, seen = make_upstream_provider("justoneapi", sample="justoneapi_search")
    rows = _payload_of("justoneapi_search")["data"]

    results = await provider.search_articles(_KEYWORD)

    assert len(results) == 2
    assert results[0].url == rows[0]["url"], "url 优先于 content_url"
    assert results[0].author == rows[0]["author"]
    assert results[1].url == rows[1]["content_url"], "没有 url 时才回落 content_url"
    assert results[1].author == rows[1]["nick_name"]
    assert results[0].title == rows[0]["title"]
    assert results[0].digest == rows[0]["digest"]
    assert results[0].source == "justoneapi"
    assert all(r.publish_time is None for r in results), "搜索形状未实测，不许假装解得出时间"

    request = seen[0]
    assert request.method == "GET"
    assert request.url.path.endswith("/api/weixin/search-article/v1")
    assert _query(request) == {"token": "test-" + "key", "keyword": _KEYWORD}


@pytest.mark.parametrize("kwargs", _JUSTONEAPI_DETAIL_FAILURES)
async def test_justoneapi_search_degrades_to_empty_list(make_upstream_provider, kwargs: dict[str, Any]) -> None:
    provider, _ = make_upstream_provider("justoneapi", **kwargs)
    assert await provider.search_articles(_KEYWORD) == []


async def test_justoneapi_search_skips_non_dict_rows_and_object_data(make_upstream_provider) -> None:
    """data 里混入字符串 ⇒ 只跳那一行；data 是对象 ⇒ 整次判空。

    红的变异：删掉行级 isinstance ⇒ 第一发 AttributeError；删掉 `isinstance(data, list)` ⇒
    第二发把 dict 的键当行、产出一条 url/title 全空的假结果。
    """
    mixed, _ = make_upstream_provider(
        "justoneapi", payload={"code": 0, "data": ["字符串行", {"url": _ARTICLE_URL, "title": "唯一有效行"}]}
    )
    assert [r.title for r in await mixed.search_articles(_KEYWORD)] == ["唯一有效行"]

    objecty, _ = make_upstream_provider("justoneapi", payload={"code": 0, "data": {"list": []}})
    assert await objecty.search_articles(_KEYWORD) == []

    keyless, seen = make_upstream_provider("justoneapi", sample="justoneapi_search")
    keyless._api_key = ""
    assert await keyless.search_articles(_KEYWORD) == []
    assert seen == []


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        pytest.param({"status": 500}, DependencyUnavailableError, id="5xx→依赖不可用"),
        pytest.param({"status": 400, "body_text": "bad ghid"}, DiscoveryFailedError, id="4xx→发现失败"),
        pytest.param({"body_text": "<html>gate</html>"}, DiscoveryFailedError, id="非JSON→发现失败"),
        pytest.param({"payload": [1, 2]}, DiscoveryFailedError, id="顶层非对象→发现失败"),
        pytest.param({"payload": {"code": 1, "message": "余额不足"}}, DependencyUnavailableError, id="余额→依赖不可用"),
        pytest.param({"payload": {"code": 1, "message": "insufficient balance"}}, DependencyUnavailableError,
                     id="balance→依赖不可用"),
        pytest.param({"payload": {"code": 2, "message": "触发限频"}}, RateLimitedUpstreamError, id="限频→上游限频"),
        pytest.param({"payload": {"code": 2, "message": "rate limit exceeded"}}, RateLimitedUpstreamError,
                     id="rate→上游限频"),
        pytest.param({"payload": {"code": 9, "message": "未知错误"}}, DiscoveryFailedError, id="其它码→发现失败"),
        pytest.param({"transport_error": httpx.ConnectError("refused")}, DependencyUnavailableError,
                     id="传输层→依赖不可用"),
    ],
)
async def test_justoneapi_discovery_error_mapping_is_the_raising_branch(
    make_upstream_provider, kwargs: dict[str, Any], expected: type
) -> None:
    """发现路径用的是 `_handle_response(suppress_errors=False)` 的另一整支：逐类**抛**。

    与详情那七发是同一函数的两个分支，两支都要有人判——只判 suppress 支会把
    「发现链该红就红」这条契约整个漏掉（P-1 的教训就是静默比抛错贵）。
    红的变异：把 5xx 那支的 `raise DependencyUnavailableError` 换成 `raise DiscoveryFailedError` ⇒
    第一发红（重试与告警按依赖故障走的分支就没了）；把 `限频` 两支并进 else ⇒ 两发红。
    """
    provider, _ = make_upstream_provider("justoneapi", **kwargs)
    with pytest.raises(expected):
        await provider.query_work_list(_IDENTIFIER, 1)


async def test_justoneapi_discovery_nested_shape_defence(make_upstream_provider) -> None:
    """data/MsgList/Msg 三层各坏一次都不许抛，坏行只跳不丢整页；时间能落 BaseInfo.DateTime。

    红的变异：`create_time = app_msg.get("CreateTime") or base_info.get("DateTime")` 去掉后半段 ⇒
    最后一发的 publishTime 消失；删掉 MsgList 的 isinstance 守卫 ⇒ 第二发 AttributeError。
    """
    not_dict, _ = make_upstream_provider("justoneapi", payload={"code": 0, "data": []})
    assert await not_dict.query_work_list(_IDENTIFIER, 1) == ([], None)

    bad_msg_list, _ = make_upstream_provider("justoneapi", payload={"code": 0, "data": {"MsgList": "字符串"}})
    assert await bad_msg_list.query_work_list(_IDENTIFIER, 1) == ([], None)

    bad_msgs, _ = make_upstream_provider("justoneapi", payload={"code": 0, "data": {"MsgList": {"Msg": "字符串"}}})
    assert await bad_msgs.query_work_list(_IDENTIFIER, 1) == ([], None)

    second_url = "https://mp.weixin.qq.com/s?__biz=MjM5MjgwNTQ1MQ==&mid=2650000002&idx=1&sn=bbbb2222"
    mixed, _ = make_upstream_provider(
        "justoneapi",
        payload={
            "code": 0,
            "data": {
                "MsgList": {
                    "Msg": [
                        "字符串行",
                        {"AppMsg": {"Title": "T", "ContentUrl": _ARTICLE_URL, "CreateTime": _EPOCH}},
                        {"AppMsg": {"Title": "无 URL 行", "CreateTime": _EPOCH}},
                        {"AppMsg": {"Title": "时间只在 BaseInfo", "ContentUrl": second_url},
                         "BaseInfo": {"DateTime": _EPOCH + 60}},
                    ]
                }
            },
        },
    )
    rows, total = await mixed.query_work_list(_IDENTIFIER, 1)
    assert [r["url"] for r in rows] == [_ARTICLE_URL, second_url], "空 ContentUrl 的行必须丢，别建行"
    assert total is None and len(rows) == 2
    assert rows[0]["publishTime"] == str(_EPOCH)
    assert rows[1]["publishTime"] == str(_EPOCH + 60), "AppMsg.CreateTime 缺失时要回落 BaseInfo.DateTime"


# ── TikHub ──────────────────────────────────────────────────────────────


async def test_tikhub_detail_maps_fields_and_request_shape(make_upstream_provider) -> None:
    """v2 详情（契约级实现）：字段按载荷取值，GET 带 `url` 参数与 Bearer 头。

    红的变异：端点写成 docstring 里标注「已下线 404」的 `fetch_mp_article_detail_json` ⇒
    path 断言红；把鉴权从 Header 挪进 query（TikHub 的口径是 `Authorization: Bearer`）⇒
    后两条红；`content or html` 的别名次序改动、或 `author or nick_name` 对调 ⇒ 字段断言红。
    """
    provider, seen = make_upstream_provider("tikhub", sample="tikhub_detail")
    data = _payload_of("tikhub_detail")["data"]

    detail = await provider.fetch_article_detail(_ARTICLE_URL)

    assert detail is not None, "载荷给了 content，详情却判 None——别名支路变了"
    assert detail.url == _ARTICLE_URL
    assert detail.content_html == data["content"]
    assert detail.title == data["title"]
    assert detail.author == data["nick_name"], "author 空串时要回落 nick_name"
    assert detail.ghid == data["user_name"], "gh_id 空串时要回落 user_name"
    assert detail.biz == data["biz"]
    assert detail.source == "tikhub"
    assert detail.publish_time is None, "TikHub 详情路径根本不解析时间（见证据件的缺口登记）"

    request = seen[0]
    assert request.method == "GET"
    assert request.url.path.endswith("/api/v1/wechat_mp/v2/fetch_article_detail_h5")
    assert _query(request) == {"url": _ARTICLE_URL}
    assert request.headers.get("authorization") == "Bearer test-key"


async def test_tikhub_detail_falls_back_to_html_and_text_only_payloads(make_upstream_provider) -> None:
    """`content` 缺失时用 `html`；两个正文字段都没有、只有 `content_text` 时也接受。

    红的变异：删掉 `or data.get("html","")` ⇒ 第一发降成 None；
    把「正文都空才判 None」的条件写成 `and` ⇒ 第二发（只有纯文本）被误判成失败。
    """
    html_only, _ = make_upstream_provider("tikhub", payload={"data": {"html": "<p>只有 html</p>", "title": "T"}})
    detail = await html_only.fetch_article_detail(_ARTICLE_URL)
    assert detail is not None and detail.content_html == "<p>只有 html</p>"

    text_only, _ = make_upstream_provider("tikhub", payload={"data": {"content_text": "只有纯文本"}})
    plain = await text_only.fetch_article_detail(_ARTICLE_URL)
    assert plain is not None and plain.content_text == "只有纯文本" and plain.content_html == ""

    for unusable in ({"data": "字符串"}, {"data": {"content": "", "content_text": ""}}, {"data": {}}):
        empty, seen = make_upstream_provider("tikhub", payload=unusable)
        assert await empty.fetch_article_detail(_ARTICLE_URL) is None
        assert len(seen) == 1


async def test_tikhub_detail_without_key_never_calls_the_paid_endpoint(make_upstream_provider) -> None:
    provider, seen = make_upstream_provider("tikhub", sample="tikhub_detail")
    provider._api_key = ""
    assert await provider.fetch_article_detail(_ARTICLE_URL) is None
    assert seen == []


_TIKHUB_DEGRADE_CASES = [
    pytest.param({"status": 402}, id="402余额不足"),
    pytest.param({"status": 404, "body_text": "gone"}, id="404端点已下线"),
    pytest.param({"transport_error": httpx.ConnectError("connection refused")}, id="传输层不可达"),
    pytest.param({"transport_error": httpx.ReadTimeout("read timeout")}, id="读超时"),
]


@pytest.mark.parametrize("kwargs", _TIKHUB_DEGRADE_CASES)
async def test_tikhub_degrades_to_none_on_402_and_404(make_upstream_provider, kwargs: dict[str, Any]) -> None:
    """TikHub 的两条专属降级：402（余额为 0，TC-A2-02b 实测）与 404（旧端点已下线）都要返回空。

    这两支是 TikHub「契约级实现 + 禁用态注册」的日常态而非异常态——现读余额 0，
    每次真实调用必然落在这两支上；把它们改成抛错就等于把「未充值」报成采集故障。
    红的变异：`suppress_402` 参数不再传给详情/搜索调用点 ⇒ 402 两发红；
    把 404 那支改成 raise ⇒ 404 两发红。
    """
    provider, _ = make_upstream_provider("tikhub", **kwargs)
    assert await provider.fetch_article_detail(_ARTICLE_URL) is None
    assert await provider.search_articles(_KEYWORD) == []




async def test_tikhub_search_maps_rows_with_doc_url_priority(make_upstream_provider) -> None:
    """搜索：`doc_url` 压 `url`、只取 title/digest（作者字段根本不填），POST body 两键。

    红的变异：别名次序对调 ⇒ 第一行 URL 红；把 body 的 `business_type` 改掉或漏传 ⇒
    末条红（那是 TikHub 搜索接口的必填维度）。
    """
    provider, seen = make_upstream_provider("tikhub", sample="tikhub_search")
    rows = _payload_of("tikhub_search")["data"]

    results = await provider.search_articles(_KEYWORD, sort="hot", time_range="30d")

    assert len(results) == 2
    assert results[0].url == rows[0]["doc_url"], "doc_url 优先于 url"
    assert results[1].url == rows[1]["url"], "没有 doc_url 时才回落 url"
    assert results[0].title == rows[0]["title"]
    assert results[0].digest == rows[0]["digest"]
    assert all(r.author == "" for r in results), "TikHub 搜索不填作者（形状未实测，别按别家补齐）"
    assert all(r.publish_time is None for r in results)
    assert results[0].source == "tikhub"

    request = seen[0]
    assert request.url.path.endswith("/api/v1/wechat_search/v2/fetch_search")
    assert _json_body(request) == {"keyword": _KEYWORD, "business_type": "account"}
    assert request.headers.get("authorization") == "Bearer test-key"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"data": "字符串"}, id="data不是数组"),
        pytest.param({"data": ["字符串行", {"title": "有效行", "url": _ARTICLE_URL}]}, id="行级非对象"),
    ],
)
async def test_tikhub_search_payload_shape_defence(make_upstream_provider, payload: Any) -> None:
    """data 坏形状 ⇒ 空列表 / 只跳坏行，都不许抛。

    红的变异：删掉 `isinstance(item, dict)` ⇒ 第二发 AttributeError；
    删掉 `isinstance(data, list)` ⇒ 第一发把字符串按字符遍历、产出垃圾行。
    """
    provider, _ = make_upstream_provider("tikhub", payload=payload)
    results = await provider.search_articles(_KEYWORD)
    assert [r.title for r in results] == ([] if isinstance(payload["data"], str) else ["有效行"])


async def test_tikhub_search_without_key_returns_empty_without_calling(make_upstream_provider) -> None:
    provider, seen = make_upstream_provider("tikhub", sample="tikhub_search")
    provider._api_key = ""
    assert await provider.search_articles(_KEYWORD) == []
    assert seen == []


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        pytest.param({"status": 402}, DependencyUnavailableError, id="402→依赖不可用（需充值）"),
        pytest.param({"status": 500}, DependencyUnavailableError, id="5xx→依赖不可用"),
        pytest.param({"status": 400, "body_text": "bad username"}, DiscoveryFailedError, id="其它4xx→发现失败"),
        pytest.param({"body_text": "<html>gate</html>"}, DiscoveryFailedError, id="非JSON→发现失败"),
        pytest.param({"payload": [1, 2]}, DiscoveryFailedError, id="顶层非对象→发现失败"),
        pytest.param({"transport_error": httpx.ConnectError("refused")}, DependencyUnavailableError,
                     id="传输层→依赖不可用"),
    ],
)
async def test_tikhub_discovery_never_silently_returns_empty_on_failure(
    make_upstream_provider, kwargs: dict[str, Any], expected: type
) -> None:
    """发现路径不传 `suppress_402` ⇒ 402 必须**显式失败并报「需充值后启用」**。

    这是 P-1 的另一半：余额为 0 时返回空清单会被上层读成「该号今天没有新文章」，
    而抛 DependencyUnavailableError 才会让它显式不可用。文案里的「充值」也是判据——
    402 与 500 都映射成同一个类，靠文案把「缺钱」和「上游坏了」分开。
    红的变异：给发现调用点补 `suppress_402=True` ⇒ 第一发降级成空列表；
    把 402 那支的异常消息改掉 ⇒ match 红。
    """
    provider, _ = make_upstream_provider("tikhub", **kwargs)
    if expected is DependencyUnavailableError and kwargs.get("status") == 402:
        with pytest.raises(DependencyUnavailableError, match="充值"):
            await provider.query_work_list(_IDENTIFIER, 1)
    else:
        with pytest.raises(expected):
            await provider.query_work_list(_IDENTIFIER, 1)


async def test_tikhub_404_on_discovery_degrades_to_empty_page(make_upstream_provider) -> None:
    """发现端点 404（旧 web/* 已下线的实测形状）⇒ 记 warn 后返回空页，不抛。

    红的变异：把 404 那支并入 4xx 抛错 ⇒ 本条红（把「端点漂移」读成「我方请求错」，
    上层会重试一个根本不存在的 URL）。
    """
    provider, seen = make_upstream_provider("tikhub", status=404, body_text="no such endpoint")
    assert await provider.query_work_list(_IDENTIFIER, 1) == ([], None)
    assert len(seen) == 1


async def test_tikhub_discovery_row_mapping_and_alias_branches(make_upstream_provider) -> None:
    """行映射的四条兜底：`data.articles` 别名、顶层 content_url/title/digest/create_time、
    非对象行只跳、空 URL 行不建。

    红的变异：删掉 `or data.get("articles")` ⇒ 第一发空手而归；
    删掉 `or item.get("content_url", "")` ⇒ 第二发的行被 `if row["url"]` 丢掉（整页空）；
    `create_time` 只从 comm_msg_info 取 ⇒ 第二发没有 publishTime。
    """
    articles_alias, _ = make_upstream_provider(
        "tikhub",
        payload={"data": {"articles": [{"app_msg_ext_info": {"content_url": _ARTICLE_URL, "title": "别名标题"},
                                        "comm_msg_info": {"create_time": _EPOCH}}]}},
    )
    rows, _ = await articles_alias.query_work_list(_IDENTIFIER, 1)
    assert [r["url"] for r in rows] == [_ARTICLE_URL]
    assert rows[0]["title"] == "别名标题"
    assert rows[0]["publishTime"] == str(_EPOCH)

    flat, _ = make_upstream_provider(
        "tikhub",
        payload={
            "data": {
                "data": [
                    "字符串行",
                    {"content_url": _ARTICLE_URL, "title": "顶层标题", "digest": "顶层摘要",
                     "create_time": _EPOCH + 60},
                    {"app_msg_ext_info": {"title": "没有 URL 的行"}},
                ]
            }
        },
    )
    rows, _ = await flat.query_work_list(_IDENTIFIER, 1)
    assert len(rows) == 1, "非对象行与空 URL 行都不该建行"
    assert rows[0]["id"] == work_list_row_id(_ARTICLE_URL)
    assert rows[0]["digest"] == "顶层摘要"
    assert rows[0]["publishTime"] == str(_EPOCH + 60)

    not_dict, _ = make_upstream_provider("tikhub", payload={"data": "字符串"})
    assert await not_dict.query_work_list(_IDENTIFIER, 1) == ([], None)

    items_not_list, _ = make_upstream_provider("tikhub", payload={"data": {"data": "字符串"}})
    assert await items_not_list.query_work_list(_IDENTIFIER, 1) == ([], None)


# ── Wellbyte 数井 ───────────────────────────────────────────────────────


async def test_wellbyte_detail_is_disabled_and_must_not_call_upstream(make_upstream_provider) -> None:
    """详情端点 article_detail_v2 实测 422 三连拒（TC-A4-05/06/07）⇒ 禁用 = **一个字都不发**。

    这条判的不是「返回 None」而是「没花钱」：端点在册、每次调用扣 30cr，
    把它当普通降级用 `make_upstream_provider` 喂载荷照样能返回 None，但 seen 会非空。
    红的变异：任何人把 `fetch_article_detail` 接回真实请求 ⇒ 本条立刻红（要重新启用得先补活体）。
    """
    provider, seen = make_upstream_provider("wellbyte", sample="wellbyte_search")
    assert await provider.fetch_article_detail(_ARTICLE_URL) is None
    assert seen == [], "详情已按 422 三连拒禁用，发请求就是白烧 30cr"


async def test_wellbyte_search_maps_rows_and_request_shape(make_upstream_provider) -> None:
    """搜索（TC-A4-02 实测 155cr）：doc_url 压 url、作者取 `source.title`，body 三键齐备。

    红的变异：`source_info.get("title")` 换成 `item.get("author")` ⇒ 作者两行全空；
    `doc_url or url` 次序对调 ⇒ 第一行 URL 红；body 少一个键或端点路径改动 ⇒ 末两条红。
    """
    provider, seen = make_upstream_provider("wellbyte", sample="wellbyte_search")
    rows = _payload_of("wellbyte_search")["data"]["data"]

    results = await provider.search_articles(_KEYWORD)

    assert len(results) == 2
    assert results[0].url == rows[0]["doc_url"], "doc_url 优先于 url"
    assert results[1].url == rows[1]["url"]
    assert results[0].title == rows[0]["title"]
    assert results[0].digest == rows[0]["digest"]
    assert results[0].author == rows[0]["source"]["title"], "Wellbyte 的号名在 source.title"
    assert results[0].source == "wellbyte"

    request = seen[0]
    assert request.url.path.endswith("/v1/wechat_mp/search/article_v1")
    assert _json_body(request) == {"keyword": _KEYWORD, "sortType": "LATEST", "publishTimeType": ""}
    assert request.headers.get("authorization") == "Bearer test-key"


async def test_wellbyte_search_publish_time_accepts_epoch_only(make_upstream_provider) -> None:
    """`source.dateTime` 有两种口径：数字 epoch ⇒ 解析；「4分钟前」这类相对串 ⇒ 留空。

    判的是「宁缺勿编」：把「4分钟前」硬解成一个时间戳就是拿客户端时钟猜发布时刻，
    而相对串没有可比性。红的变异：给这条加 `datetime.now() - timedelta(...)` 之类的兜底 ⇒
    第二行不再是 None；删掉 isinstance 守卫 ⇒ 第一发 TypeError。
    """
    provider, _ = make_upstream_provider("wellbyte", sample="wellbyte_search")
    results = await provider.search_articles(_KEYWORD)
    assert results[0].publish_time is not None
    assert results[0].publish_time.timestamp() == _EPOCH
    assert results[1].publish_time is None, "相对时间串不编造绝对时刻"


async def test_wellbyte_search_keeps_rows_when_an_epoch_is_out_of_range(make_upstream_provider) -> None:
    """毫秒 epoch 混进 `source.dateTime` ⇒ 那一行仍要留下（只有时间留空）。

    一次搜索 155cr：把一条有标题有 URL 的行因为时间坏掉而丢掉，就是拿额度换残缺。
    红的变异：摘掉 `except (ValueError, OSError): pass` ⇒ 本条抛穿；
    把「时间坏 ⇒ 丢行」写成 `continue` ⇒ 本条红（results 少一行）。
    """
    provider, _ = make_upstream_provider(
        "wellbyte",
        payload={
            "code": 0,
            "data": {
                "data": [
                    {"title": "毫秒时间的行", "doc_url": _ARTICLE_URL,
                     "source": {"title": "占位号名", "dateTime": 1790659200000}}
                ]
            },
        },
    )
    results = await provider.search_articles(_KEYWORD)
    assert [r.title for r in results] == ["毫秒时间的行"]
    assert results[0].publish_time is None
    assert results[0].url == _ARTICLE_URL


@pytest.mark.parametrize(
    ("sort", "time_range", "expected_sort", "expected_time"),
    [
        pytest.param("latest", "1d", "LATEST", "ONE_DAY", id="latest+1d"),
        pytest.param("relevant", "7d", "RELEVANCE", "ONE_WEEK", id="relevant+7d"),
        pytest.param("hot", "30d", "HOT", "ONE_MONTH", id="hot+30d"),
        pytest.param("latest", "all", "LATEST", "", id="all→不限时"),
        pytest.param("latest", "", "LATEST", "", id="空时间范围"),
        pytest.param("乱写的排序", "乱写的范围", "LATEST", "", id="未知值→各自兜底"),
    ],
)
async def test_wellbyte_search_translates_sort_and_time_range(
    make_upstream_provider, sort: str, time_range: str, expected_sort: str, expected_time: str
) -> None:
    """上层传的口语口径（latest/7d）必须翻译成上游的枚举（LATEST/ONE_WEEK），未知值兜到默认。

    这条判的是**真的把参数发出去**了：`_SORT_MAP.get(sort, "LATEST")` 的第二个参数、
    以及 `time_range="" → ""`（全部）而不是漏传键。
    红的变异：把 `.get(sort, "LATEST")` 的兜底改成 `""` ⇒ 「未知值」那发红；
    把 `_TIME_MAP` 的 `"all"` 条目删掉 ⇒ 「all→不限时」那发红（虽然结果都是 ""，
    所以这条真正抓的是「键名拼错时静默降级成默认」那一族）。
    """
    provider, seen = make_upstream_provider("wellbyte", sample="wellbyte_search")
    await provider.search_articles(_KEYWORD, sort=sort, time_range=time_range)
    body = _json_body(seen[0])
    assert body["sortType"] == expected_sort
    assert body["publishTimeType"] == expected_time
    assert body["keyword"] == _KEYWORD


_WELLBYTE_FAILURES = [
    pytest.param({"status": 403, "body_text": "cloudflare block"}, id="403被CF拦截"),
    pytest.param({"status": 422, "body_text": "quality gate"}, id="422质量门槛"),
    pytest.param({"status": 500}, id="上游5xx"),
    pytest.param({"status": 400, "body_text": "bad keyword"}, id="上游4xx"),
    pytest.param({"body_text": "<html>cf 1010</html>"}, id="响应体不是JSON"),
    pytest.param({"payload": [1, 2]}, id="顶层非对象"),
    pytest.param({"payload": {"code": 402, "message": "credits 不足"}}, id="业务码credits"),
    pytest.param({"transport_error": httpx.ConnectError("connection refused")}, id="传输层不可达"),
]


@pytest.mark.parametrize("kwargs", _WELLBYTE_FAILURES)
async def test_wellbyte_search_degrades_to_empty_list(make_upstream_provider, kwargs: dict[str, Any]) -> None:
    """搜索的八种失败全部降成 []（suppress 支）：搜索是可选能力，不该打断采集链。

    红的变异：`_handle_response(..., suppress_errors=True)` 的 suppress 参数漏传 ⇒
    前六发抛穿；把行级 `isinstance(items, list)` 守卫删掉 ⇒ 载荷形状一变就 TypeError。
    """
    provider, _ = make_upstream_provider("wellbyte", **kwargs)
    assert await provider.search_articles(_KEYWORD) == []


@pytest.mark.parametrize(
    ("payload", "expected_titles"),
    [
        pytest.param({"code": 0, "data": "字符串"}, [], id="data不是对象"),
        pytest.param({"code": 0, "data": {"data": "字符串"}}, [], id="data.data不是数组"),
        pytest.param(
            {"code": 0, "data": {"data": ["字符串行", {"title": "有效行", "doc_url": _ARTICLE_URL}]}},
            ["有效行"],
            id="行级非对象只跳那一行",
        ),
    ],
)
async def test_wellbyte_search_payload_shape_defence(
    make_upstream_provider, payload: dict[str, Any], expected_titles: list[str]
) -> None:
    """三层坏形状各自收口：整次空 / 整次空 / 只跳坏行保住好行。

    红的变异：删掉行级守卫 ⇒ 第三发 AttributeError 并丢掉整页（正是 P-1 的形状换了入口）；
    删掉 `isinstance(items, list)` ⇒ 第二发按字符遍历字符串、产出一串空标题的假结果。
    """
    provider, _ = make_upstream_provider("wellbyte", payload=payload)
    results = await provider.search_articles(_KEYWORD)
    assert [r.title for r in results] == expected_titles
    assert all(r.url == _ARTICLE_URL for r in results)




async def test_wellbyte_search_without_key_returns_empty_without_calling(make_upstream_provider) -> None:
    provider, seen = make_upstream_provider("wellbyte", sample="wellbyte_search")
    provider._api_key = ""
    assert await provider.search_articles(_KEYWORD) == []
    assert seen == []


async def test_wellbyte_resolve_ghid_takes_username_from_account_info(make_upstream_provider) -> None:
    """标识映射零成本路径（TC-A4-04）：传文章 URL ⇒ 取 `data.AccountInfo.UserName` 的 gh_。

    红的变异：层级写成 `data.data.AccountInfo`（TC-A4-04 记着的「首轮看错层级」教训）⇒ 返回
    None；把 `startswith("gh_")` 守卫删掉 ⇒ 下面那发红；端点或 body 键名改动 ⇒ 末两条红。
    """
    provider, seen = make_upstream_provider("wellbyte", sample="wellbyte")
    assert await provider.resolve_ghid_from_url(_ARTICLE_URL) == "gh_b9465228558d"
    request = seen[0]
    assert request.url.path.endswith("/v1/wechat_mp/user/account_history_articles_v2")
    assert _json_body(request) == {"url": _ARTICLE_URL}
    assert request.headers.get("authorization") == "Bearer test-key"


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        pytest.param({"payload": {"code": 0, "data": "字符串"}}, None, id="data不是对象"),
        pytest.param({"payload": {"code": 0, "data": {"AccountInfo": "字符串"}}}, None, id="AccountInfo不是对象"),
        pytest.param({"payload": {"code": 0, "data": {"AccountInfo": {}}}}, None, id="没有UserName"),
        pytest.param({"payload": {"code": 0, "data": {"AccountInfo": {"UserName": "公众号自定义名"}}}}, None,
                     id="UserName不带gh_前缀"),
        pytest.param({"payload": {"code": 0, "data": {"AccountInfo": {"UserName": None}}}}, None,
                     id="UserName是null"),
        pytest.param({"status": 403, "body_text": "cf"}, None, id="403被CF拦截"),
        pytest.param({"payload": {"code": 7, "message": "credits 不足"}}, None, id="业务码credits"),
        pytest.param({"transport_error": httpx.ConnectError("refused")}, None, id="传输层不可达"),
    ],
)
async def test_wellbyte_resolve_ghid_returns_none_for_every_unusable_answer(
    make_upstream_provider, kwargs: dict[str, Any], expected: Any
) -> None:
    """映射失败一律返回 None（不抛、不返回空串）——调用方按「映射不到」处理，别按「账号名是空串」。

    红的变异：`username.startswith("gh_")` 去掉 ⇒ 「自定义名」那发返回脏值；
    `if not self._api_key: return None` 去掉 ⇒ 额外那条无 key 判据红。
    """
    provider, seen = make_upstream_provider("wellbyte", **kwargs)
    assert await provider.resolve_ghid_from_url(_ARTICLE_URL) is expected
    assert len(seen) <= 1

    keyless, keyless_seen = make_upstream_provider("wellbyte", sample="wellbyte")
    keyless._api_key = ""
    assert await keyless.resolve_ghid_from_url(_ARTICLE_URL) is None
    assert keyless_seen == []


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        pytest.param({"status": 403, "body_text": "cf 1010"}, DependencyUnavailableError, id="403→依赖不可用"),
        pytest.param({"status": 422, "body_text": "质量门槛"}, DiscoveryFailedError, id="422→发现失败"),
        pytest.param({"status": 500}, DependencyUnavailableError, id="5xx→依赖不可用"),
        pytest.param({"status": 400, "body_text": "bad url"}, DiscoveryFailedError, id="其它4xx→发现失败"),
        pytest.param({"body_text": "<html>gate</html>"}, DiscoveryFailedError, id="非JSON→发现失败"),
        pytest.param({"payload": [1, 2]}, DiscoveryFailedError, id="顶层非对象→发现失败"),
        pytest.param({"payload": {"code": 1, "message": "余额不足"}}, DependencyUnavailableError, id="余额→依赖不可用"),
        pytest.param({"payload": {"code": 1, "message": "not enough credits"}}, DependencyUnavailableError,
                     id="credits→依赖不可用"),
        pytest.param({"payload": {"code": 2, "message": "触发限频"}}, RateLimitedUpstreamError, id="限频→上游限频"),
        pytest.param({"payload": {"code": 2, "message": "rate limited, retry later"}}, RateLimitedUpstreamError,
                     id="rate文案→上游限频"),
        pytest.param({"payload": {"code": 9, "message": "未知错误"}}, DiscoveryFailedError, id="其它码→发现失败"),
        pytest.param({"payload": {"code": 2, "message": "Too Many Requests"}}, DiscoveryFailedError,
                     id="注意：标准429文案落不进限频支路"),
        pytest.param({"transport_error": httpx.ConnectError("refused")}, DependencyUnavailableError,
                     id="传输层→依赖不可用"),
    ],
)
async def test_wellbyte_discovery_error_mapping_is_the_raising_branch(
    make_upstream_provider, kwargs: dict[str, Any], expected: type
) -> None:
    """发现路径（suppress=False 那一整支）逐类抛错，其中 403 单独判「Cloudflare 指纹拦截」。

    403 在 Wellbyte 上不是「鉴权失败」而是 CF 的 1010 指纹拒绝（TC-A4-03），
    重试同一个请求必然还是 403，该报的是依赖不可用而不是我方错误；
    422 反过来是质量门槛拒绝（不扣费），属请求侧问题。
    「Too Many Requests」那行钉的是分类器的边界：限频识别只认 `rate` / `限频` 两个子串，
    HTTP 标准文案落不进那一支、会被当普通发现失败。上游真实文案未活体核实，
    所以这里只登记现状、不判成缺陷——STEP-08 S8.5.1 拿到活体响应后再回来定性。

    红的变异：把 403 那支的异常类换成 DiscoveryFailedError ⇒ 第一发红；
    把 422 与 4xx 两支合并 ⇒ 第二发红（丢掉「不扣费」这条可核对的事实）。
    """
    provider, _ = make_upstream_provider("wellbyte", **kwargs)
    with pytest.raises(expected):
        await provider.query_work_list(_ARTICLE_URL, 1)


async def test_wellbyte_discovery_nested_shape_defence(make_upstream_provider) -> None:
    """清单三层坏形状都不抛；空 ContentUrl 的行不建；时间回落 BaseInfo.DateTime。

    红的变异：把层级写成 `data.data.MsgList`（TC-A4-04 的首轮误判）⇒ 第一发就空手而归；
    删掉 `or base_info.get("DateTime")` ⇒ 最后一行的 publishTime 消失。
    """
    not_dict, _ = make_upstream_provider("wellbyte", payload={"code": 0, "data": []})
    assert await not_dict.query_work_list(_ARTICLE_URL, 1) == ([], None)

    bad_msg_list, _ = make_upstream_provider("wellbyte", payload={"code": 0, "data": {"MsgList": "字符串"}})
    assert await bad_msg_list.query_work_list(_ARTICLE_URL, 1) == ([], None)

    bad_msgs, _ = make_upstream_provider("wellbyte", payload={"code": 0, "data": {"MsgList": {"Msg": "字符串"}}})
    assert await bad_msgs.query_work_list(_ARTICLE_URL, 1) == ([], None)

    second_url = "https://mp.weixin.qq.com/s?__biz=MjM5MjgwNTQ1MQ==&mid=2650000002&idx=1&sn=bbbb2222"
    mixed, _ = make_upstream_provider(
        "wellbyte",
        payload={
            "code": 0,
            "data": {
                "MsgList": {
                    "Msg": [
                        0,
                        {"AppMsg": {"Title": "T", "ContentUrl": _ARTICLE_URL, "CreateTime": _EPOCH}},
                        {"AppMsg": {"Title": "无 URL 行"}},
                        {"AppMsg": {"Title": "只有 BaseInfo 时间", "ContentUrl": second_url},
                         "BaseInfo": {"DateTime": _EPOCH + 60}},
                    ]
                }
            },
        },
    )
    rows, _ = await mixed.query_work_list(_ARTICLE_URL, 1)
    assert [r["url"] for r in rows] == [_ARTICLE_URL, second_url]
    assert rows[1]["publishTime"] == str(_EPOCH + 60)


# ── STEP-20 退役了三条「生产缺陷见证」（P-15 naive 时间 / P-16 TikHub 4xx-5xx 抛穿 / P-17 source:null 打挂整页）──
# 它们的原文各自写着「修好后本条转红，那时该把这段见证删掉/更新」，所以这三处红是**修复的证据**
# 而不是回归。修复后的判据与极性反证在 apps/api/tests/test_provider_defects_p15_p17.py；
# 登记见发布清单 P-27，读数见 docs/06_validation/evidence/EVD-V13-20/。

def test_article_source_factory_fails_loudly_on_unknown_and_unconfigured_names() -> None:
    """工厂的两条显式失败：名字不在册、名字在册但没配 key——都不许返回一个空壳 provider。

    红的变异：把 `if cls is None: raise ConfigurationError` 删掉 ⇒ 第一发变成 KeyError
    （错误类不对，上层按配置错误处理的分支就找不到它）；把 `if not api_key` 那支删掉 ⇒
    第二发返回一个每次都抛「KEY 未配置」的客户端，注册表里看上去一切正常。
    """
    with pytest.raises(ConfigurationError, match="未知文章来源平台"):
        make_article_source_provider("nosuchchannel", Settings())
    with pytest.raises(ConfigurationError, match="api_key 未配置"):
        make_article_source_provider("dajiala", Settings())
    assert make_all_article_source_providers(Settings()) == {}, "全没配 key ⇒ 一个 provider 都不该造出来"


async def test_article_source_factory_builds_only_the_configured_channels() -> None:
    """只配两家 ⇒ 只造两家，且 key/base_url 真的传进去了（不是造完再默认）。

    红的变异：`key_map` 里把某个 settings 字段名写错 ⇒ KeyError（本条红）；
    注册表与 `_CANONICAL_ID` 分叉（新增一家却没进 S3.2 的字面 id 名单）⇒ 末条红。
    """
    settings = Settings(dajiala_api_key="k-" + "dajiala", wellbyte_api_key="k-" + "wellbyte")
    providers = make_all_article_source_providers(settings)
    try:
        assert set(providers) == {"dajiala", "wellbyte"}
        assert isinstance(providers["dajiala"], DajialaClient)
        assert providers["dajiala"]._api_key == "k-dajiala"
        assert providers["wellbyte"]._api_key == "k-wellbyte"
        assert set(ARTICLE_SOURCE_PROVIDERS) == set(_CANONICAL_ID)
    finally:
        for provider in providers.values():
            await provider.aclose()


def test_every_sample_is_claimed_by_a_case() -> None:
    """样本目录里的每个 payload 都必须被某个用例认领——"自动纳入"这件事本身要有门。

    没有这条，新增一家渠道的样本会静静躺在目录里、谁都看不见，
    而上面三条的绿灯会被读成"全渠道已覆盖"。

    S3.4.1 把认领表从「`_BUILDERS` 的补集」升级为一张显式登记表 `_SAMPLE_CLAIMS`，
    并且扫描改成递归——否则把新样本丢进子目录就能绕过这道门（绕过方向恰好又是静默）。
    现在四向都对得上：目录里的每个文件都要有人认领、认领表里的每个名字都要有文件、
    `_BUILDERS` 的每家都要有认领行、`_CANONICAL_ID` 的每家都要在 `_BUILDERS` 里。
    """
    files: set[str] = set()
    for path in list(SAMPLE_DIR.rglob("*.json")) + list(SAMPLE_DIR.rglob("*.xml")):
        relative = path.relative_to(SAMPLE_DIR).as_posix()
        files.add(relative.rsplit(".", 1)[0] if "/" in relative else path.stem)

    unclaimed = sorted(files - set(_SAMPLE_CLAIMS))
    assert not unclaimed, (
        f"样本未被任何用例认领：{unclaimed}——请在 `_SAMPLE_CLAIMS` 里登记「哪个用例在吃它」"
    )
    dangling = sorted(set(_SAMPLE_CLAIMS) - files)
    assert not dangling, f"认领表指向不存在的样本（改名/删除没同步）：{dangling}"
    unregistered_builders = sorted(set(_BUILDERS) - set(_SAMPLE_CLAIMS))
    assert not unregistered_builders, f"_BUILDERS 里有人没登记消费判据：{unregistered_builders}"
    # 第二层的名单必须是第一层的子集：写错一个名字，那家渠道就从"判字面 id"里静默消失。
    stray = sorted(set(_CANONICAL_ID) - set(_BUILDERS))
    assert not stray, f"_CANONICAL_ID 里有不在 _BUILDERS 的名字（参数化会空转）：{stray}"
