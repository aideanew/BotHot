"""极致了 Dajiala 文章来源 Provider。

**契约来源**：2026-09-29 活体实测（TC-A1 系列），base URL https://www.dajiala.com/fbmain/monitor/v3/

鉴权：POST JSON body {key, verifycode}（verifycode 当前为空串）。

接口清单（实测确认）：
- post_condition  ¥0.14/次  — 按 ghid/alias/url/nickname 获取最新发文清单（4 条/次）
- post_history    ¥0.14/次  — 按 url+page 翻页获取历史发文（19 items/页）
- article_html    ¥0.04/次  — 全 HTML + 元数据（标题/biz/gh_id/作者/发布时间）✅
- article_detail  ¥0.045/次 — 实测缺陷（data 恒 null），禁用
- short2long      ¥0.015/次 — 短链转长链
- kw_search       ?/次      — 关键词搜索（⚠️ 端点存在但未实测：URL 从前端 SPA JS chunk 反解所得，单价/参数/响应形状全部未知，资费页口径约 ¥0.5/次起）

发现策略：query_work_list 用 post_condition（按 ghid 拉最新清单），字段映射到
manifest._map_row 的别名（url/title/digest/post_time）。

详情策略：fetch_article_detail 用 article_html，取 data.html + data.title/biz/gh_id 等。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.errors import (
    AppError,
    DependencyUnavailableError,
    DiscoveryFailedError,
    ForbiddenError,
    RateLimitedUpstreamError,
)
from app.providers.article_sources.base import ArticleDetail, ArticleSearchResult

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
BASE_URL = "https://www.dajiala.com/fbmain/monitor/v3"

_CODE_OK = 0


class DajialaClient:
    """极致了 Dajiala HTTP 客户端。

    鉴权方式：body 参数 {key, verifycode}。
    """

    name = "dajiala"
    description = "极致了 Dajiala（公众号文章发现 + HTML 详情兜底）"

    def __init__(
        self,
        api_key: str,
        base_url: str = BASE_URL,
        http: httpx.AsyncClient | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._http = http or httpx.AsyncClient(timeout=timeout)
        self._owns_http = http is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    # ── 发现 ──────────────────────────────────────────────────────────

    async def query_work_list(
        self, identifier: str, page: int
    ) -> tuple[list[dict[str, Any]], int | None]:
        """按 ghid 获取最新发文清单。

        identifier = ghid（gh_xxx 格式）。
        Dajiala post_condition 每次返回最新 4 条，不支持翻页——page > 1 时返回空。
        如需历史清单，上层应改用 fetch_article_detail 逐条或接入 post_history。
        """
        if not self._api_key:
            raise DependencyUnavailableError("DAJIALA_API_KEY 未配置")
        if page > 1:
            return [], 0  # post_condition 无翻页，仅返回最新批次

        payload = await self._request("post_condition", {
            "key": self._api_key,
            "verifycode": "",
            "ghid": identifier,
        })
        data = payload.get("data")
        if not isinstance(data, list):
            raise DiscoveryFailedError("Dajiala post_condition 响应缺 data 数组")

        rows: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            # 归一化到 manifest._map_row 的字段别名
            row: dict[str, Any] = {
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "digest": item.get("digest", ""),
            }
            # post_time 是 Unix 时间戳（如 1790659200）
            post_time = item.get("post_time")
            if isinstance(post_time, (int, float)) and post_time > 0:
                row["publish_time"] = str(post_time)
            rows.append(row)

        return rows, len(rows)

    # ── 详情兜底 ──────────────────────────────────────────────────────

    async def fetch_article_detail(self, url: str) -> ArticleDetail | None:
        """用 article_html 端点获取文章全 HTML + 元数据。

        实测可用（TC-A1-07）：¥0.04/次，返回 data.html（完整 DOCTYPE）+ 元数据。
        """
        if not self._api_key:
            return None

        try:
            payload = await self._request("article_html", {
                "key": self._api_key,
                "verifycode": "",
                "url": url,
            })
        except AppError as e:
            logger.warning("Dajiala article_html 失败: %s", e)
            return None

        data = payload.get("data")
        if not isinstance(data, dict):
            return None

        html = data.get("html", "")
        if not html:
            return None

        # 解析发布时间（post_time 是 Unix 时间戳）
        publish_time: datetime | None = None
        post_time = data.get("post_time")
        if isinstance(post_time, (int, float)) and post_time > 0:
            try:
                publish_time = datetime.fromtimestamp(int(post_time), tz=None)
            except (ValueError, OSError):
                pass

        # 纯文本提取（粗略：去标签）
        content_text = _strip_html(html)[:200]

        return ArticleDetail(
            url=url,
            title=data.get("title", ""),
            content_html=html,
            content_text=content_text,
            author=data.get("nickname", "") or data.get("author", ""),
            biz=data.get("biz", ""),
            ghid=data.get("gh_id", ""),
            publish_time=publish_time,
            source="dajiala",
        )

    # ── 关键词搜索 ────────────────────────────────────────────────────

    async def search_articles(
        self, keyword: str, *, sort: str = "latest", time_range: str = ""
    ) -> list[ArticleSearchResult]:
        """Dajiala kw_search 关键词搜索。

        ⚠️ 证据级别：文档级（未实测）——kw_search 端点 URL 从前端 SPA JS chunk 反解所得
        （static1.dajiala.com/static/js/{89,120,...}.*.js），仅证明端点存在；
        单价、参数名、响应形状全部未知（资费页口径约 ¥0.5/次起）。
        本实现按 Dajiala 统一包裹 {code, data} 推断，失败时降级返回空列表。
        充值后需补 TC-A1-10 活体用例确认参数/响应。
        """
        if not self._api_key:
            return []
        try:
            payload = await self._request("kw_search", {
                "key": self._api_key,
                "verifycode": "",
                "keyword": keyword,
            })
        except AppError as e:
            logger.warning("Dajiala kw_search 失败: %s", e)
            return []

        data = payload.get("data")
        if not isinstance(data, list):
            return []

        results: list[ArticleSearchResult] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            results.append(ArticleSearchResult(
                url=item.get("url", ""),
                title=item.get("title", ""),
                digest=item.get("digest", ""),
                author=item.get("nickname", ""),
                source="dajiala",
            ))
        return results

    # ── HTTP 层 ──────────────────────────────────────────────────────

    async def _request(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST JSON 到 {base_url}/{endpoint}；错误映射到领域异常。"""
        url = f"{self._base_url}/{endpoint}"
        try:
            resp = await self._http.post(url, json=body)
        except httpx.HTTPError as exc:
            raise DependencyUnavailableError(f"Dajiala 不可达: {exc}") from exc

        if resp.status_code >= 500:
            raise DependencyUnavailableError(f"Dajiala 5xx: {resp.status_code}")
        if resp.status_code >= 400:
            raise DiscoveryFailedError(f"Dajiala HTTP {resp.status_code}: {resp.text[:160]}")

        try:
            payload = resp.json()
        except ValueError as exc:
            raise DiscoveryFailedError("Dajiala 响应非 JSON") from exc

        if not isinstance(payload, dict):
            raise DiscoveryFailedError("Dajiala 响应形状异常（非对象）")

        code = payload.get("code")
        if code != _CODE_OK:
            raise _business_error(code, str(payload.get("msg", ""))[:160], payload)
        return payload


def _strip_html(html: str) -> str:
    """粗略去 HTML 标签取纯文本（详情兜底用，extractor 会做正式清洗）。"""
    import re
    text = re.sub(r"<[^>]+>", "", html)
    return text.strip()


def _business_error(code: Any, msg: str, payload: dict) -> AppError:
    """Dajiala 业务码 → 领域错误。"""
    if code in (-1,):
        # code=-1 通常为参数错误，不扣费
        return DiscoveryFailedError(f"Dajiala 参数错误: {msg}")
    if "余额" in msg or "money" in msg.lower():
        return DependencyUnavailableError(f"Dajiala 余额不足: {msg}")
    return DiscoveryFailedError(f"Dajiala 业务错误 code={code}: {msg}")
