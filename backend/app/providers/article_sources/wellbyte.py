"""Wellbyte 数井 文章来源 Provider。

**契约来源**：2026-09-29 活体实测（TC-A4 系列），base URL https://api.wellbyte.net

鉴权：Header `Authorization: Bearer <key>`。
响应统一 {code, message, data, meta:{endpoint, cache_hit, elapsed_ms, request_id, credits_charged}}。
端点目录：GET /zh/endpoints?platform=wechat_mp（12 个，credits 明码）。

接口清单（实测确认）：
- POST /v1/wechat_mp/search/article_v1  (JSON body: keyword, sortType, publishTimeType)  155cr ✅
  → data.data = 微信搜一搜原始结构（doc_url 全量长链含 __biz，source.dateTime 分钟级）
- POST /v1/wechat_mp/user/account_history_articles_v2  (JSON body: url)  78cr ✅
  → data.AccountInfo{UserName(gh_)} + data.MsgList.Msg[...] + ContentUrl(带 sessionid)
  → 免费侧产 gh_：传文章 URL 即返回 ghid——标识映射零成本路径
- GET /v1/wechat_mp/detail/article_detail_v2?url=  — 422 质量门槛拒绝（三连拒定谳），禁用

⚠️ Cloudflare 指纹拦截：Python urllib 被 CF 1010 拦截（TC-A4-03）。
   生产客户端必须用 httpx（非 urllib），容器环境复验。

发现策略：query_work_list 用 account_history_articles_v2（identifier=文章 URL）。
  与 RedFox/Dajiala 的 biz/ghid 模型不同——Wellbyte 需要一个文章 URL 作为入口。
  上层需先用 search 找到文章 URL，再用 history 拉整号清单。

搜索策略：search 用 article_v1（keyword + sortType + publishTimeType），155cr/次。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from app.core.errors import (
    AppError,
    DependencyUnavailableError,
    DiscoveryFailedError,
    RateLimitedUpstreamError,
)
from app.providers.article_sources.base import ArticleDetail, ArticleSearchResult

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20.0
BASE_URL = "https://api.wellbyte.net"

_CODE_OK = 0

# sortType: LATEST=最新, RELEVANCE=相关
_SORT_MAP = {"latest": "LATEST", "relevant": "RELEVANCE", "hot": "HOT"}
# publishTimeType: ONE_DAY=24h, ONE_WEEK=7d, ONE_MONTH=30d, EMPTY=全部
_TIME_MAP = {
    "1d": "ONE_DAY",
    "7d": "ONE_WEEK",
    "30d": "ONE_MONTH",
    "": "",
    "all": "",
}


class WellbyteClient:
    """Wellbyte 数井 HTTP 客户端。

    鉴权方式：Header Authorization: Bearer <key>。
    全部接口用 JSON body（实测 form 不收，TC-A4-01）。

    ⚠️ Cloudflare 指纹拦截：必须用 httpx（非 urllib）。
    """

    name = "wellbyte"
    description = "Wellbyte 数井（关键词搜索 + URL 驱动的历史文章发现）"

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

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    # ── 发现 ──────────────────────────────────────────────────────────

    async def query_work_list(
        self, identifier: str, page: int
    ) -> tuple[list[dict[str, Any]], int | None]:
        """按文章 URL 获取账号历史文章列表。

        identifier = 文章 URL（mp.weixin.qq.com 长链）。
        Wellbyte 的 account_history_v2 接受文章 URL，返回该文章所属账号的历史发文。

        与 RedFox/Dajiala 的 biz/ghid 模型不同——Wellbyte 需要一个文章 URL 作为入口。
        上层应先用 search_articles 找到文章 URL，再用本方法拉整号清单。

        page > 1 时返回空（Wellbyte 用游标分页，需上页返回值）。
        """
        if not self._api_key:
            raise DependencyUnavailableError("WELLBYTE_API_KEY 未配置")
        if page > 1:
            return [], None

        body = {"url": identifier}
        try:
            resp = await self._http.post(
                f"{self._base_url}/v1/wechat_mp/user/account_history_articles_v2",
                json=body,
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            # CF 1010 拦截会表现为 httpx.HTTPStatusError 或 ConnectError
            raise DependencyUnavailableError(
                f"Wellbyte 不可达（检查 Cloudflare 指纹拦截）: {exc}"
            ) from exc

        payload = await self._handle_response(resp, "account_history_articles_v2")
        if payload is None:
            return [], None

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return [], None

        # 嵌套结构：data.MsgList.Msg = 文章列表
        # 注意：不是 data.data.MsgList（TC-A4-04 误判教训：首轮看错层级）
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
            create_time = app_msg.get("CreateTime") or base_info.get("DateTime")
            if isinstance(create_time, int | float) and create_time > 0:
                row["publish_time"] = str(create_time)
            if row["url"]:
                rows.append(row)

        return rows, None

    # ── 详情兜底 ──────────────────────────────────────────────────────

    async def fetch_article_detail(self, url: str) -> ArticleDetail | None:
        """Wellbyte article_detail_v2 实测三连拒（422 质量门槛），禁用。

        注册在册但不调用——"失败扣 0"承诺实测为真（TC-A4-05/06/07）。
        """
        logger.debug("Wellbyte article_detail_v2 已禁用（422 质量门槛三连拒）")
        return None

    # ── 关键词搜索 ────────────────────────────────────────────────────

    async def search_articles(
        self, keyword: str, *, sort: str = "latest", time_range: str = ""
    ) -> list[ArticleSearchResult]:
        """Wellbyte 关键词搜索（article_v1）。

        实测可用（TC-A4-02）：155cr/次，返回 15 items，doc_url 全量长链。
        分钟级时效（source.dateTime = "4分钟前"）。
        """
        if not self._api_key:
            return []

        body = {
            "keyword": keyword,
            "sortType": _SORT_MAP.get(sort, "LATEST"),
            "publishTimeType": _TIME_MAP.get(time_range, ""),
        }
        try:
            resp = await self._http.post(
                f"{self._base_url}/v1/wechat_mp/search/article_v1",
                json=body,
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            logger.warning("Wellbyte 搜索不可达: %s", exc)
            return []

        payload = await self._handle_response(resp, "search/article_v1", suppress_errors=True)
        if payload is None:
            return []

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return []
        items = data.get("data") or []
        if not isinstance(items, list):
            return []

        results: list[ArticleSearchResult] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            source_info = item.get("source", {})
            # dateTime 可能是 "4分钟前" 或时间戳
            publish_time: datetime | None = None
            dt = source_info.get("dateTime", "")
            if isinstance(dt, int | float) and dt > 0:
                try:
                    publish_time = datetime.fromtimestamp(int(dt), tz=None)
                except (ValueError, OSError):
                    pass

            results.append(ArticleSearchResult(
                url=item.get("doc_url", "") or item.get("url", ""),
                title=item.get("title", ""),
                digest=item.get("digest", ""),
                author=source_info.get("title", ""),  # source.title = 号名
                publish_time=publish_time,
                source="wellbyte",
            ))
        return results

    # ── 标识映射（免费侧产） ─────────────────────────────────────────

    async def resolve_ghid_from_url(self, article_url: str) -> str | None:
        """从文章 URL 获取公众号 gh_ ID（免费侧产）。

        TC-A4-04 实测：传文章 URL 到 account_history_v2，响应 data.AccountInfo.UserName
        即为 gh_ ID——标识映射零成本路径。

        用于 biz ↔ gh_ 映射（方案 T16）。
        """
        if not self._api_key:
            return None

        body = {"url": article_url}
        try:
            resp = await self._http.post(
                f"{self._base_url}/v1/wechat_mp/user/account_history_articles_v2",
                json=body,
                headers=self._headers(),
            )
        except httpx.HTTPError:
            return None

        payload = await self._handle_response(resp, "resolve_ghid", suppress_errors=True)
        if payload is None:
            return None

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return None
        account_info = data.get("AccountInfo", {})
        if not isinstance(account_info, dict):
            return None
        username = account_info.get("UserName", "")
        if isinstance(username, str) and username.startswith("gh_"):
            return username
        return None

    # ── HTTP 层 ──────────────────────────────────────────────────────

    async def _handle_response(
        self, resp: httpx.Response, op: str, *, suppress_errors: bool = False
    ) -> dict[str, Any] | None:
        """统一响应处理。"""
        # Cloudflare 1010 拦截
        if resp.status_code == 403:
            if suppress_errors:
                logger.warning("Wellbyte %s 被 Cloudflare 拦截（403/1010）", op)
                return None
            raise DependencyUnavailableError(
                "Wellbyte 被 Cloudflare 拦截（403）：需检查 httpx TLS 指纹配置"
            )
        if resp.status_code == 422:
            # 质量门槛拒绝（article_detail_v2），不扣费
            if suppress_errors:
                logger.warning("Wellbyte %s 质量门槛拒绝（422）", op)
                return None
            raise DiscoveryFailedError(f"Wellbyte 质量门槛拒绝（422）: {resp.text[:160]}")
        if resp.status_code >= 500:
            if suppress_errors:
                return None
            raise DependencyUnavailableError(f"Wellbyte 5xx: {resp.status_code}")
        if resp.status_code >= 400:
            if suppress_errors:
                return None
            raise DiscoveryFailedError(f"Wellbyte HTTP {resp.status_code}: {resp.text[:160]}")

        try:
            payload = resp.json()
        except ValueError as exc:
            if suppress_errors:
                return None
            raise DiscoveryFailedError("Wellbyte 响应非 JSON") from exc

        if not isinstance(payload, dict):
            if suppress_errors:
                return None
            raise DiscoveryFailedError("Wellbyte 响应形状异常")

        code = payload.get("code")
        if code != _CODE_OK:
            if suppress_errors:
                logger.warning("Wellbyte %s 业务错误 code=%s: %s", op, code, payload.get("message", ""))
                return None
            raise _business_error(code, str(payload.get("message", ""))[:160])
        return payload


def _business_error(code: Any, msg: str) -> AppError:
    """Wellbyte 业务码 → 领域错误。"""
    if "credits" in msg.lower() or "余额" in msg:
        return DependencyUnavailableError(f"Wellbyte credits 不足: {msg}")
    if "rate" in msg.lower() or "限频" in msg:
        return RateLimitedUpstreamError(f"Wellbyte 限频: {msg}")
    return DiscoveryFailedError(f"Wellbyte 业务错误 code={code}: {msg}")
