"""JustOneAPI 文章来源 Provider。

**契约来源**：2026-09-29 活体实测（TC-A3 系列），base URL https://api.justoneapi.com

鉴权：URL 参数 ?token=<key>（官方文档逐字：「必须以 URL 参数形式携带访问令牌」）。
响应统一包裹 {code, message, data, recordTime, requestId}。

接口清单（实测确认）：
- POST /api/weixin/get-account-history-articles/v2  (form: token, ghid)  ¥0.40 ✅
  → data.MsgList.Msg[10 条]，每条 AppMsg{Title, Digest, ContentUrl, CreateTime, UpdateTime}
  → data.AccountInfo{UserName(gh_), NickName, HeadImgUrl, Signature}
  → data.PagingInfo{Offset, IsEnd}
- GET /api/weixin/get-article-detail/v1?token&articleUrl  ¥0.15 ✅
  → data.data[0].content (HTML 正文) + content_multi_text (富文本) + 60+ 字段
- GET /api/weixin/get-article-detail/v5?token&articleUrl  ¥0.15
  → 仅元数据 + 阅读指标，无正文 content 字段
- convert-article-link/v1 — 实测不可用（405/参数名不符），禁用

POST/GET 口径：history=POST form；detail v1/v5=GET query（同平台参数名不统一：history=ghid，detail=articleUrl）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import structlog

from app.core.errors import (
    AppError,
    DependencyUnavailableError,
    DiscoveryFailedError,
    RateLimitedUpstreamError,
)
from app.core.security import upstream_semaphore, upstream_timeout
from app.providers.article_sources.base import ArticleDetail, ArticleSearchResult

logger = structlog.get_logger(__name__)

DEFAULT_TIMEOUT = 20.0
BASE_URL = "https://api.justoneapi.com"

# W7：进程内并发闸名（`UPSTREAM_CONCURRENCY_JUSTONEAPI` 可覆盖上限）
UPSTREAM_NAME = "justoneapi"

_CODE_OK = 0


class JustOneApiClient:
    """JustOneAPI HTTP 客户端。

    鉴权方式：URL 参数 ?token=<key>。
    POST 接口用 x-www-form-urlencoded（token 放 body）；GET 接口用 query 参数。
    """

    name = "justoneapi"
    description = "JustOneAPI（公众号历史文章发现 + 带正文详情兜底）"

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

    # ── 发现 ──────────────────────────────────────────────────────────

    async def query_work_list(
        self, identifier: str, page: int
    ) -> tuple[list[dict[str, Any]], int | None]:
        """按 ghid 获取账号历史文章列表。

        identifier = ghid（gh_xxx 格式）。
        POST /api/weixin/get-account-history-articles/v2，form 编码：token + ghid。
        响应 data.MsgList.Msg = 10 条/页，data.PagingInfo{Offset, IsEnd} 控制翻页。
        """
        if not self._api_key:
            raise DependencyUnavailableError("JUSTONEAPI_API_KEY 未配置")

        # JustOneAPI 用 Offset 游标翻页（首页 Offset=0，后续用 PagingInfo 返回的 Offset）
        # 简化：page=1 → Offset=0；page>1 时返回空（需上页 Offset，无法预构）
        if page > 1:
            return [], None

        form_data = {"token": self._api_key, "ghid": identifier}
        try:
            resp = await self._post(
                f"{self._base_url}/api/weixin/get-account-history-articles/v2",
                data=form_data,
            )
        except httpx.HTTPError as exc:
            raise DependencyUnavailableError(f"JustOneAPI 不可达: {exc}") from exc

        payload = await self._handle_response(resp, "get-account-history-articles")
        if payload is None:
            return [], None

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return [], None

        # 嵌套结构：data.MsgList.Msg = 文章列表
        msg_list = data.get("MsgList") or {}
        if not isinstance(msg_list, dict):
            return [], None
        msgs = msg_list.get("Msg") or []
        if not isinstance(msgs, list):
            msgs = []

        rows: list[dict[str, Any]] = []
        for msg in msgs:
            if not isinstance(msg, dict):
                continue
            app_msg = msg.get("AppMsg", {})
            base_info = msg.get("BaseInfo", {})
            row: dict[str, Any] = {
                "url": app_msg.get("ContentUrl", ""),
                "title": app_msg.get("Title", ""),
                "digest": app_msg.get("Digest", ""),
            }
            # CreateTime 是 Unix 时间戳
            create_time = app_msg.get("CreateTime") or base_info.get("DateTime")
            if isinstance(create_time, int | float) and create_time > 0:
                row["publish_time"] = str(create_time)
            if row["url"]:
                rows.append(row)

        return rows, None  # IsEnd 控制翻页，不返回 total

    # ── 详情兜底 ──────────────────────────────────────────────────────

    async def fetch_article_detail(self, url: str) -> ArticleDetail | None:
        """用 get-article-detail/v1 获取带正文的详情。

        实测可用（TC-A3-07）：¥0.15/次，返回 content (HTML) + 60+ 字段。
        """
        if not self._api_key:
            return None

        params = {"token": self._api_key, "articleUrl": url}
        try:
            resp = await self._get(
                f"{self._base_url}/api/weixin/get-article-detail/v1",
                params=params,
            )
        except httpx.HTTPError as exc:
            logger.warning("JustOneAPI detail 不可达: %s", exc)
            return None

        payload = await self._handle_response(resp, "get-article-detail", suppress_errors=True)
        if payload is None:
            return None

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return None
        # data.data[0] 含详情
        items = data.get("data")
        if not isinstance(items, list) or not items:
            return None
        item = items[0]
        if not isinstance(item, dict):
            return None

        content_html = item.get("content", "")
        content_text = item.get("content_multi_text", "")
        if not content_html and not content_text:
            return None

        # 解析发布时间
        publish_time: datetime | None = None
        create_time = item.get("create_time") or item.get("public_time")
        if isinstance(create_time, int | float) and create_time > 0:
            try:
                publish_time = datetime.fromtimestamp(int(create_time), tz=None)
            except (ValueError, OSError):
                pass

        # 纯文本兜底
        if not content_text:
            import re
            content_text = re.sub(r"<[^>]+>", "", content_html).strip()[:200]

        return ArticleDetail(
            url=url,
            title=item.get("title", ""),
            content_html=content_html,
            content_text=content_text,
            author=item.get("author", "") or item.get("nick_name", ""),
            biz=item.get("biz", ""),
            ghid=item.get("ghid", "") or item.get("user_name", ""),
            publish_time=publish_time,
            source="justoneapi",
        )

    # ── 关键词搜索 ────────────────────────────────────────────────────
    # 证据级别：契约级（未实测）——价目表（justoneapi-pricing-20260929-110843.xlsx，
    # 293 接口）确认以下搜索端点在册但本轮未调用：
    #   search-article/v1  ¥0.80   搜索文章
    #   search-article/v2  ¥0.80   搜索文章（支持 latest 类目）
    #   search-account/v1  ¥0.40   搜索公众号
    #   search-account/v2  ¥1.50   搜索公众号
    # 参数名/响应形状均未实测——实现按 JustOneAPI 统一包裹 {code, message, data} 推断，
    # suppress_errors 降级返回空列表。充值后需补 TC-A3-08 活体用例。

    async def search_articles(
        self, keyword: str, *, sort: str = "latest", time_range: str = ""
    ) -> list[ArticleSearchResult]:
        """关键词搜索文章（search-article/v1，¥0.80/次）。

        ⚠️ 契约级实现（未实测）：端点在价目表在册，但参数名/响应形状未活体验证。
        失败时降级返回空列表（suppress_errors），不抛异常。
        """
        if not self._api_key:
            return []

        # JustOneAPI 鉴权方式：URL 参数 ?token=（与 detail 接口一致）
        params = {"token": self._api_key, "keyword": keyword}
        try:
            resp = await self._get(
                f"{self._base_url}/api/weixin/search-article/v1",
                params=params,
            )
        except httpx.HTTPError as exc:
            logger.warning("JustOneAPI search 不可达: %s", exc)
            return []

        payload = await self._handle_response(resp, "search-article/v1", suppress_errors=True)
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
                url=item.get("url", "") or item.get("content_url", ""),
                title=item.get("title", ""),
                digest=item.get("digest", ""),
                author=item.get("author", "") or item.get("nick_name", ""),
                source="justoneapi",
            ))
        return results

    # ── HTTP 层 ──────────────────────────────────────────────────────

    async def _handle_response(
        self, resp: httpx.Response, op: str, *, suppress_errors: bool = False
    ) -> dict[str, Any] | None:
        """统一响应处理。suppress_errors=True 时不抛异常（详情兜底用）。"""
        if resp.status_code >= 500:
            if suppress_errors:
                logger.warning("JustOneAPI %s 5xx: %d", op, resp.status_code)
                return None
            raise DependencyUnavailableError(f"JustOneAPI 5xx: {resp.status_code}")
        if resp.status_code >= 400:
            if suppress_errors:
                logger.warning("JustOneAPI %s HTTP %d: %s", op, resp.status_code, resp.text[:160])
                return None
            raise DiscoveryFailedError(f"JustOneAPI HTTP {resp.status_code}: {resp.text[:160]}")

        try:
            payload = resp.json()
        except ValueError as exc:
            if suppress_errors:
                return None
            raise DiscoveryFailedError("JustOneAPI 响应非 JSON") from exc

        if not isinstance(payload, dict):
            if suppress_errors:
                return None
            raise DiscoveryFailedError("JustOneAPI 响应形状异常")

        code = payload.get("code")
        if code != _CODE_OK:
            if suppress_errors:
                logger.warning("JustOneAPI %s 业务错误 code=%s: %s", op, code, payload.get("message", ""))
                return None
            raise _business_error(code, str(payload.get("message", ""))[:160])
        return payload


def _business_error(code: Any, msg: str) -> AppError:
    """JustOneAPI 业务码 → 领域错误。"""
    if "余额" in msg or "balance" in msg.lower():
        return DependencyUnavailableError(f"JustOneAPI 余额不足: {msg}")
    if "限频" in msg or "rate" in msg.lower():
        return RateLimitedUpstreamError(f"JustOneAPI 限频: {msg}")
    return DiscoveryFailedError(f"JustOneAPI 业务错误 code={code}: {msg}")
