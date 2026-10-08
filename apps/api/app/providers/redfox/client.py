"""RedFox Discovery 防腐层：全部 RedFox HTTP 细节收口于此，上层只见领域语义。

**契约来源（R8 活体实测，2026-09-28 实测通过）**：广域库
`POST /story/api/gzh/data/queryWorkList`，body `{"bizInfo": <__biz>, "offset": <0-based>,
"sortType": "2"}`，响应 `{"code": 2000, "data": {"list": [...], "total": <int>}}`。

已实测排除的上游路径（勿回退）：
- 优质库 `POST /story/api/gzhData/queryWorkList`（旧实现的口径）→ `code 500`
  「请求异常，请仔细检查填写的参数是否有误」，官方文档示例参数同样失败。
- `POST /story/api/gzh/data/searchUser`（关键词搜号，含文档自带示例关键词）→ 同 500。
故仅 `bizInfo` 定位可用；`account` / `keyword` 定位不可用。

错误映射（复用既有码，未新增）：
- 无 Key（显式失败不造数）→ 50002 DEPENDENCY_UNAVAILABLE
- 3103 / 3105 / 3107 鉴权族（3107 为台账 2026-09-17 活体实证；3103/3105 为官方文档列示）
  → 10004 FORBIDDEN，取「实测 ∪ 文档」并集，不删任一侧
- 3201 积分余额不足 → 50002 DEPENDENCY_UNAVAILABLE
- 4004 限频 → 20005 RATE_LIMITED_UPSTREAM（可重试）
- 其他业务码 / 响应形状异常 / HTTP 4xx → 20004 DISCOVERY_FAILED
- HTTP 5xx / 网络不可达 / 超时 → 50002 DEPENDENCY_UNAVAILABLE

`query_work_list` 返回 `(rows, total)`：`total` 取自 `data.total`（**非顶层**，官方文档示例
有误），供 `ManifestSyncService` 做缺口驱动的增量化分页；上游缺失或类型异常时为 `None`，
上层退化为按空页终止。
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.errors import (
    AppError,
    DependencyUnavailableError,
    DiscoveryFailedError,
    ForbiddenError,
    RateLimitedUpstreamError,
)
from app.core.security import upstream_semaphore, upstream_timeout

DEFAULT_TIMEOUT = 15.0

# W7：进程内并发闸名（`UPSTREAM_CONCURRENCY_REDFOX` 可覆盖上限）。
# 同 provider 的所有请求共享一个信号量——限的是「我们对上游的并发」，与客户端数无关。
UPSTREAM_NAME = "redfox"

QUERY_WORK_LIST_PATH = "/story/api/gzh/data/queryWorkList"

# 广域库实测：固定 20 行/页，`offset` 以 20 为步长，页间零重叠。
PAGE_SIZE = 20

# sortType "2" = 按发布时间倒序（实测口径，倒序时间线可无缝拼接）
_SORT_LATEST = "2"

_CODE_OK = 2000

# 鉴权失败族：3107（活体实证）+ 3103/3105（官方文档列示）
_AUTH_FAILED_CODES = frozenset({3103, 3105, 3107})


class RedfoxClient:
    """RedFox HTTP 客户端（鉴权头 X-API-KEY；单实例进程内复用）。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        http: httpx.AsyncClient | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        # W7：超时拆分（connect 短 / read 长）——`timeout` 参数语义保留为读超时
        self._http = http or httpx.AsyncClient(timeout=upstream_timeout(timeout))
        self._owns_http = http is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def _post(self, url: str, **kwargs: Any) -> httpx.Response:
        """带并发闸的 POST（W7）：限「我们对上游的并发」，不改请求/响应语义。"""
        async with upstream_semaphore(UPSTREAM_NAME):
            return await self._http.post(url, **kwargs)

    async def query_work_list(self, biz: str, page: int) -> tuple[list[dict[str, Any]], int | None]:
        """公众号作品清单一页 `(原始行, 上游 total)`（biz=__biz，page 从 1 起）。

        无 Key → 显式失败（50002），绝不返回空清单冒充成功。
        """
        if not self._api_key:
            raise DependencyUnavailableError("REDFOX_API_KEY 未配置：整号清单不可用（显式失败，不造数）")
        payload = await self._request(
            QUERY_WORK_LIST_PATH,
            {"bizInfo": biz, "offset": max(page - 1, 0) * PAGE_SIZE, "sortType": _SORT_LATEST},
        )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise DiscoveryFailedError("RedFox 清单响应缺 data 对象")
        items = data.get("list")
        if not isinstance(items, list):
            raise DiscoveryFailedError("RedFox 清单响应缺 data.list")
        rows = [row for row in items if isinstance(row, dict)]
        return rows, _as_int_total(data.get("total"))

    async def _request(self, path: str, json_payload: dict[str, Any]) -> dict[str, Any]:
        """带 X-API-KEY 请求；HTTP/业务错误 → 领域错误映射。"""
        url = f"{self._base_url}{path}"
        headers = {"X-API-KEY": self._api_key}
        try:
            resp = await self._post(url, json=json_payload, headers=headers)
        except httpx.HTTPError as exc:
            raise DependencyUnavailableError(f"RedFox 不可达: {exc}") from exc
        if resp.status_code >= 500:
            raise DependencyUnavailableError(f"RedFox 5xx: {resp.status_code}")
        if resp.status_code >= 400:
            raise DiscoveryFailedError(f"RedFox HTTP {resp.status_code}: {resp.text[:160]}")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise DiscoveryFailedError("RedFox 响应非 JSON") from exc
        if not isinstance(payload, dict):
            raise DiscoveryFailedError("RedFox 响应形状异常（非对象）")
        code = payload.get("code")
        if code != _CODE_OK:
            raise _business_error(code, str(payload.get("msg", ""))[:160])
        return payload


def _as_int_total(value: Any) -> int | None:
    """`data.total` → int；缺失/类型异常（含 bool）→ None，让上层退化按空页终止。"""
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) and value >= 0 else None


def _business_error(code: Any, msg: str) -> AppError:
    """RedFox 业务码 → 领域错误（未知码归 20004）。"""
    if code in _AUTH_FAILED_CODES:
        return ForbiddenError(f"RedFox API Key 无效（{code}）：请检查 REDFOX_API_KEY")
    if code == 3201:
        return DependencyUnavailableError("RedFox 积分余额不足（3201）：请充值或领免费积分后重试")
    if code == 4004:
        return RateLimitedUpstreamError("RedFox 限频（4004）：请稍后重试")
    return DiscoveryFailedError(f"RedFox 业务错误 code={code}: {msg}")
