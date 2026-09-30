"""TikHub 文章来源 Provider。

**契约来源**：2026-09-29 活体实测（TC-A2 系列），base URL https://api.tikhub.io
OpenAPI 契约获取：GET /openapi.json（1050 paths，wechat_mp v2 仅 13 端点）。

鉴权：Header `Authorization: Bearer <key>`。

接口清单（OpenAPI 确认）：
- POST /api/v1/wechat_search/v2/fetch_search — 关键词搜索（需付费，free credit 不接受）
- POST /api/v1/wechat_mp/web/fetch_account_articles — 账号文章列表（username=gh_xxx，offset=base64 游标）
- fetch_mp_article_detail_json — Excel 标注免费但 OpenAPI 中已下线（404）

**实测状态**：key 有效（鉴权通过）但付费余额为 0，全部端点返回 402。
契约级实现 + 禁用态注册——充值后按 TC-A2-02b 形态补活体用例即可启用。

发现策略：query_work_list 用 fetch_account_articles（username=ghid，offset=base64 游标）。
详情策略：fetch_article_detail 调用 v2 组详情端点（fetch_article_detail 等），契约在案未实测。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.errors import (
    DependencyUnavailableError,
    DiscoveryFailedError,
)
from app.core.security import upstream_semaphore, upstream_timeout
from app.providers.article_sources.base import ArticleDetail, ArticleSearchResult

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
BASE_URL = "https://api.tikhub.io"

# W7：进程内并发闸名（`UPSTREAM_CONCURRENCY_TIKHUB` 可覆盖上限）
UPSTREAM_NAME = "tikhub"

# fetch_account_articles 请求体参数（OpenAPI 读取）：
# username: gh_xxx / gh_xxx@app / 自定义微信号
# offset: base64 游标，首页为空串
# item_show_type: 0=文章 5=视频 7=音频 8=贴图
# raw: 是否返回原始结构
ITEM_SHOW_ALL = 0


class TikhubClient:
    """TikHub HTTP 客户端。

    鉴权方式：Header Authorization: Bearer <key>。
    当前付费余额为 0，所有付费端点返回 402——注册但禁用。
    """

    name = "tikhub"
    description = "TikHub（公众号文章发现 + 搜索，契约级实现，需充值后启用）"

    def __init__(
        self,
        api_key: str,
        base_url: str = BASE_URL,
        http: httpx.AsyncClient | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
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

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        """带并发闸的 GET（W7）：与 `_post` 同闸，故发现与详情共享同一并发预算。"""
        async with upstream_semaphore(UPSTREAM_NAME):
            return await self._http.get(url, **kwargs)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    # ── 发现 ──────────────────────────────────────────────────────────

    async def query_work_list(
        self, identifier: str, page: int
    ) -> tuple[list[dict[str, Any]], int | None]:
        """按 username（gh_xxx）获取账号文章列表。

        TikHub 用 base64 游标分页：首页 offset=空串，后续页用上页返回的 cursor。
        当前实现：page=1 用空游标；page>1 时返回空（游标需上页返回值，无法预构）。
        """
        if not self._api_key:
            raise DependencyUnavailableError("TIKHUB_API_KEY 未配置")

        # page=1 用空 offset；page>1 无法预构游标，返回空让上层停止翻页
        if page > 1:
            return [], None

        body = {
            "username": identifier,
            "offset": "",  # 首页空游标
            "item_show_type": ITEM_SHOW_ALL,
            "raw": True,
        }

        try:
            resp = await self._post(
                f"{self._base_url}/api/v1/wechat_mp/web/fetch_account_articles",
                json=body,
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise DependencyUnavailableError(f"TikHub 不可达: {exc}") from exc

        payload = await self._handle_response(resp, "fetch_account_articles")
        if payload is None:
            return [], None

        # TikHub 返回结构：data.data = 文章列表（微信原始结构）
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return [], None
        items = data.get("data") or data.get("articles") or []
        if not isinstance(items, list):
            items = []

        rows: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            # 微信原始结构：app_msg_ext_info 或 comm_msg_info 内含标题/URL
            app_msg = item.get("app_msg_ext_info", {})
            comm_msg = item.get("comm_msg_info", {})
            row: dict[str, Any] = {
                "url": app_msg.get("content_url", "") or item.get("content_url", ""),
                "title": app_msg.get("title", "") or item.get("title", ""),
                "digest": app_msg.get("digest", "") or item.get("digest", ""),
            }
            # create_time 是 Unix 时间戳
            create_time = comm_msg.get("create_time") or item.get("create_time")
            if isinstance(create_time, int | float) and create_time > 0:
                row["publish_time"] = str(create_time)
            if row["url"]:
                rows.append(row)

        return rows, None  # TikHub 不返回 total，上层按空页终止

    # ── 详情兜底 ──────────────────────────────────────────────────────

    async def fetch_article_detail(self, url: str) -> ArticleDetail | None:
        """TikHub v2 组详情端点（fetch_article_detail），契约在案未实测。

        ⚠️ 范围澄清（2026-09-29 修正）：
        - Excel 报价表里的 /api/v1/wechat_mp/web/* 旧端点（含 fetch_mp_article_detail_json）
          已从现行 OpenAPI 下线（TC-A2-04 实测 404）。
        - 但 v2 组详情端点仍在现行 OpenAPI（api.tikhub.io/openapi.json，1050 paths）：
          /api/v1/wechat_mp/v2/fetch_article_detail、fetch_article_detail_h5（官方标推荐）、
          fetch_article_full 等 13 个端点。
        - 本方法调用 v2 组端点；因 TikHub 余额为 0（TC-A2-02b 402），从未活体实测。
        失败时降级返回 None（suppress_errors），不抛异常。
        """
        if not self._api_key:
            return None

        # v2 组详情端点（契约在案，未实测）
        # 优先尝试 fetch_article_detail_h5（官方标"推荐"）
        params = {"url": url}
        try:
            resp = await self._get(
                f"{self._base_url}/api/v1/wechat_mp/v2/fetch_article_detail_h5",
                params=params,
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            logger.warning("TikHub v2 detail 不可达: %s", exc)
            return None

        payload = await self._handle_response(resp, "v2/fetch_article_detail_h5", suppress_402=True)
        if payload is None:
            return None

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return None

        # v2 端点响应形状未实测，按 TikHub 统一结构推断
        content_html = data.get("content", "") or data.get("html", "")
        content_text = data.get("content_text", "")
        if not content_html and not content_text:
            return None

        return ArticleDetail(
            url=url,
            title=data.get("title", ""),
            content_html=content_html,
            content_text=content_text,
            author=data.get("author", "") or data.get("nick_name", ""),
            biz=data.get("biz", ""),
            ghid=data.get("gh_id", "") or data.get("user_name", ""),
            source="tikhub",
        )

    # ── 关键词搜索 ────────────────────────────────────────────────────

    async def search_articles(
        self, keyword: str, *, sort: str = "latest", time_range: str = ""
    ) -> list[ArticleSearchResult]:
        """TikHub 关键词搜索（fetch_search）。

        需付费余额，402 时返回空列表降级。
        """
        if not self._api_key:
            return []

        body = {"keyword": keyword, "business_type": "account"}
        try:
            resp = await self._post(
                f"{self._base_url}/api/v1/wechat_search/v2/fetch_search",
                json=body,
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            logger.warning("TikHub 搜索不可达: %s", exc)
            return []

        payload = await self._handle_response(resp, "fetch_search", suppress_402=True)
        if payload is None:
            return []

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return []

        results: list[ArticleSearchResult] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            results.append(ArticleSearchResult(
                url=item.get("doc_url", "") or item.get("url", ""),
                title=item.get("title", ""),
                digest=item.get("digest", ""),
                source="tikhub",
            ))
        return results

    # ── HTTP 层 ──────────────────────────────────────────────────────

    async def _handle_response(
        self, resp: httpx.Response, op: str, *, suppress_402: bool = False
    ) -> dict[str, Any] | None:
        """统一响应处理：402=余额不足（降级），4xx/5xx=错误。"""
        if resp.status_code == 402:
            if suppress_402:
                logger.warning("TikHub %s 余额不足（402），降级返回空", op)
                return None
            raise DependencyUnavailableError(
                f"TikHub 余额不足（402）：{op} 需付费，请充值后启用"
            )
        if resp.status_code >= 500:
            raise DependencyUnavailableError(f"TikHub 5xx: {resp.status_code}")
        if resp.status_code == 404:
            logger.warning("TikHub %s 端点不存在（404），可能已下线", op)
            return None
        if resp.status_code >= 400:
            raise DiscoveryFailedError(f"TikHub HTTP {resp.status_code}: {resp.text[:160]}")

        try:
            payload = resp.json()
        except ValueError as exc:
            raise DiscoveryFailedError("TikHub 响应非 JSON") from exc

        if not isinstance(payload, dict):
            raise DiscoveryFailedError("TikHub 响应形状异常")
        return payload
