"""RedFox Discovery 防腐层验收测试：契约形状 + 四类错误映射（mock httpx，零真实网络）。

契约以 R8 活体实测（2026-09-28，广域库）为准回写：
`POST /story/api/gzh/data/queryWorkList`，body `{bizInfo, offset, sortType}`，
响应 `{code: 2000, data: {list: [...], total: N}}`（**total 在 data 下，非顶层**）。

错误映射：3103/3105/3107→10004、3201→50002+充值提示、4004→20005 可重试、
网络/5xx→50002；无 Key → 显式失败不造数。
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.core.errors import (
    AppError,
    DependencyUnavailableError,
    DiscoveryFailedError,
    ForbiddenError,
    RateLimitedUpstreamError,
)
from app.providers.redfox.client import PAGE_SIZE, QUERY_WORK_LIST_PATH, RedfoxClient

# 合法形态的 __biz（M 前缀 + Base64），与注册入口的形态校验同源
BIZ = "MzA5NDQ2MjkzOQ=="


def _client_with(handler: Any, api_key: str = "sk-test") -> tuple[RedfoxClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def _wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(_wrapped))
    return RedfoxClient("https://redfox.example", api_key, http=http), seen


def _ok_body(*, total: Any = 2, rows: list[dict[str, Any]] | None = None) -> str:
    return json.dumps(
        {
            "code": 2000,
            "msg": "ok",
            "data": {
                "list": rows
                or [
                    {
                        "workUuid": "u-1",
                        "workUrl": "https://mp.weixin.qq.com/s/a",
                        "title": "文章一",
                        "publishTime": "2026-09-27 07:42:00",
                    },
                    {
                        "workUuid": "u-2",
                        "workUrl": "https://mp.weixin.qq.com/s/b",
                        "title": "文章二",
                        "publishTime": "2026-09-26 08:00:00",
                    },
                ],
                "total": total,
            },
        }
    )


async def test_query_work_list_success_contract() -> None:
    """成功：广域库路径 + X-API-KEY 头 + {bizInfo,offset,sortType} 体 → (原始行, data.total)。"""
    client, seen = _client_with(lambda _r: httpx.Response(200, text=_ok_body()))
    rows, total = await client.query_work_list(BIZ, 1)
    assert [row["workUuid"] for row in rows] == ["u-1", "u-2"]
    assert total == 2
    assert len(seen) == 1
    req = seen[0]
    assert str(req.url) == f"https://redfox.example{QUERY_WORK_LIST_PATH}"
    assert req.headers["x-api-key"] == "sk-test"
    assert json.loads(req.content) == {"bizInfo": BIZ, "offset": 0, "sortType": "2"}


async def test_query_work_list_page_offset_is_zero_based_20_step() -> None:
    """分页：offset = (page-1) × 20（上游实测步长 20，页间零重叠）。"""
    client, seen = _client_with(lambda _r: httpx.Response(200, text=_ok_body()))
    for page, expected_offset in ((1, 0), (2, PAGE_SIZE), (3, PAGE_SIZE * 2)):
        await client.query_work_list(BIZ, page)
        assert json.loads(seen[-1].content)["offset"] == expected_offset
    assert len(seen) == 3


async def test_missing_key_fails_explicitly_without_request() -> None:
    """无 Key：显式失败（50002）且零请求——绝不返回空清单冒充成功。"""
    client, seen = _client_with(lambda _r: httpx.Response(200, text=_ok_body()), api_key="")
    with pytest.raises(DependencyUnavailableError, match="REDFOX_API_KEY"):
        await client.query_work_list(BIZ, 1)
    assert seen == []


@pytest.mark.parametrize(
    ("code", "cls", "code_"),
    [
        pytest.param(3107, ForbiddenError, 10004, id="3107-live-recorded-10004"),
        pytest.param(3103, ForbiddenError, 10004, id="3103-docs-auth-10004"),
        pytest.param(3105, ForbiddenError, 10004, id="3105-docs-auth-10004"),
        pytest.param(3201, DependencyUnavailableError, 50002, id="3201-no-points-50002"),
        pytest.param(4004, RateLimitedUpstreamError, 20005, id="4004-rate-limited-20005"),
    ],
)
async def test_business_error_mapping(code: int, cls: type[Exception], code_: int) -> None:
    """业务码映射：鉴权族 3103/3105/3107→10004 / 3201→50002（带充值提示）/ 4004→20005。"""
    client, _ = _client_with(
        lambda _r: httpx.Response(200, text=json.dumps({"code": code, "msg": "err", "data": None}))
    )
    with pytest.raises(cls, match=str(code)) as exc_info:
        await client.query_work_list(BIZ, 1)
    assert exc_info.value.code == code_  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("code", "expect_charge_hint"),
    [
        pytest.param(3201, True, id="3201-hints-recharge"),
        pytest.param(3107, False, id="3107-no-recharge-hint"),
        pytest.param(3103, False, id="3103-no-recharge-hint"),
    ],
)
async def test_charge_hint_only_on_3201(code: int, expect_charge_hint: bool) -> None:
    """充值提示只出现在 3201：鉴权失败提示用户去充值是错误引导；单价不写死在错误信息里。"""
    client, _ = _client_with(lambda _r: httpx.Response(200, text=json.dumps({"code": code, "msg": "m", "data": None})))
    with pytest.raises(AppError, match=str(code)) as exc_info:
        await client.query_work_list(BIZ, 1)
    assert ("充值" in str(exc_info.value)) is expect_charge_hint
    assert "0.4" not in str(exc_info.value)


async def test_unknown_business_code_maps_discovery_failed() -> None:
    """未知业务码 → 20004 DISCOVERY_FAILED（不吞不猜）。"""
    client, _ = _client_with(lambda _r: httpx.Response(200, text=json.dumps({"code": 9999, "msg": "??", "data": None})))
    with pytest.raises(DiscoveryFailedError, match="9999") as exc_info:
        await client.query_work_list(BIZ, 1)
    assert exc_info.value.code == 20004  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "handler",
    [
        pytest.param(lambda _r: httpx.Response(502, text="bad gateway"), id="5xx"),
        pytest.param(lambda _r: (_ for _ in ()).throw(httpx.ConnectError("boom")), id="network"),
    ],
)
async def test_transport_failures_map_dependency_unavailable(handler: Any) -> None:
    """5xx / 网络不可达 → 50002 DEPENDENCY_UNAVAILABLE（可重试依赖故障）。"""
    client, _ = _client_with(handler)
    with pytest.raises(DependencyUnavailableError, match="RedFox"):
        await client.query_work_list(BIZ, 1)


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        pytest.param({"code": 2000, "msg": "ok", "data": {}}, "data.list", id="missing-list"),
        pytest.param({"code": 2000, "msg": "ok", "data": ["not-a-dict"]}, "data 对象", id="data-not-dict"),
        pytest.param(None, "非 JSON", id="non-json"),
    ],
)
async def test_shape_failures_map_discovery_failed(body: Any, fragment: str) -> None:
    """响应形状异常 / 非 JSON → 20004 DISCOVERY_FAILED。"""
    text = body if body is None else json.dumps(body)
    client, _ = _client_with(lambda _r: httpx.Response(200, text=text))
    with pytest.raises(DiscoveryFailedError, match=fragment):
        await client.query_work_list(BIZ, 1)


async def test_http_4xx_maps_discovery_failed() -> None:
    """HTTP 4xx → 20004 DISCOVERY_FAILED（与业务码 500 语义区分开）。"""
    client, _ = _client_with(lambda _r: httpx.Response(403, text="forbidden"))
    with pytest.raises(DiscoveryFailedError, match="HTTP 403"):
        await client.query_work_list(BIZ, 1)


@pytest.mark.parametrize(
    ("total", "expected"),
    [
        pytest.param(173, 173, id="int-passthrough"),
        pytest.param(0, 0, id="zero-total"),
        pytest.param(None, None, id="missing"),
        pytest.param(True, None, id="bool-rejected"),
        pytest.param("173", None, id="string-rejected"),
        pytest.param(-5, None, id="negative-rejected"),
    ],
)
async def test_total_extraction_is_defensive(total: Any, expected: int | None) -> None:
    """data.total 缺失或类型异常 → None（上层退化按空页终止），不让脏值污染增量游标。"""
    client, _ = _client_with(lambda _r: httpx.Response(200, text=_ok_body(total=total)))
    _, got = await client.query_work_list(BIZ, 1)
    assert got == expected


async def test_non_dict_rows_are_filtered() -> None:
    """list 中混入非对象行 → 过滤丢弃（解析前置的净行保证）。"""
    body = json.dumps({"code": 2000, "msg": "ok", "data": {"list": [{"workUuid": "u-1"}, "junk", 42], "total": 1}})
    client, _ = _client_with(lambda _r: httpx.Response(200, text=body))
    rows, total = await client.query_work_list(BIZ, 1)
    assert rows == [{"workUuid": "u-1"}]
    assert total == 1
