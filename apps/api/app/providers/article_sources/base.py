"""文章来源 Provider 基类与协议。

每个平台实现 ArticleSourceProvider 协议，提供两种能力：
1. **发现**（query_work_list）：获取公众号文章清单，喂入 ManifestSyncService
2. **详情兜底**（fetch_article_detail）：付费获取文章正文，直抓失败时触发

统一产物 ArticleDetail 汇入 extractor → normalizer → ContentAsset 同一入库链。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ArticleDetail:
    """付费详情 API 的归一化产物。

    各平台响应字段不同，防腐层统一到此结构后汇入入库链。
    """

    url: str
    title: str
    content_html: str        # 原始 HTML 正文（extractor 可直接消费）
    content_text: str        # 纯文本正文（兜底用，extractor 优先用 html）
    author: str = ""
    biz: str = ""            # 公众号 __biz（base64）
    ghid: str = ""           # 公众号 gh_ ID
    publish_time: datetime | None = None
    source: str = ""         # 来源平台名（dajiala/justoneapi/...）


@dataclass(frozen=True, slots=True)
class ArticleSearchResult:
    """关键词搜索结果（Wellbyte/TikHub/Dajiala 支持）。"""

    url: str
    title: str
    digest: str = ""
    author: str = ""
    publish_time: datetime | None = None
    source: str = ""


class ArticleSourceProvider(Protocol):
    """文章来源 Provider 协议：发现 + 详情兜底。

    query_work_list 的 identifier 参数：
    - RedFox：biz（base64 __biz）
    - Dajiala/JustOneAPI/TikHub：ghid（gh_xxx）
    - Wellbyte：文章 URL（account_history）或关键词（search）

    各 Provider 内部按自身 API 契约解释 identifier。
    """

    name: str
    description: str

    async def query_work_list(
        self, identifier: str, page: int
    ) -> tuple[list[dict[str, Any]], int | None]:
        """获取公众号文章清单一页（page 从 1 起）。

        返回 (原始行列表, 上游 total)。行字段经 manifest._map_row 的别名消化。
        上游缺失 total 时为 None，上层退化按空页终止。
        """
        ...

    async def fetch_article_detail(self, url: str) -> ArticleDetail | None:
        """付费获取文章详情（正文 + 元数据）。

        直抓失败且非图集类时由 fallback coordinator 调用。
        返回 None 表示该平台不支持详情或获取失败（不抛异常，由 coordinator 降级）。
        """
        ...

    async def search_articles(
        self, keyword: str, *, sort: str = "latest", time_range: str = ""
    ) -> list[ArticleSearchResult]:
        """关键词搜索文章（可选能力，不支持的平台返回空列表）。"""
        ...

    async def aclose(self) -> None:
        """释放 HTTP 连接。"""
        ...
