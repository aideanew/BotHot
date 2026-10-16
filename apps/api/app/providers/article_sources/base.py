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


def work_list_row_id(url: str) -> str:
    """清单行 id = URL 的规范键（ADR-0011 的 `canonical_article_key`）。

    存在理由（STEP-03 的 P-1）：`manifest._map_row` 在解不出 id 时 `return None`，
    而 dajiala / justoneapi / tikhub / wellbyte 的清单样本里**没有任何 id 形状字段**
    ⇒ 上游返回 N 条、本地落 0 条，而一轮同步读起来像成功。
    生产端先补 `id`、消费端再兜一层（`_map_row` 的 fallback），任一端回退都不会丢整页。

    上游带 id 的渠道（redfox 的 `workUuid`、rss 的 `guid`/`id`）**不**走这里：
    它们的沿用由消费端 `_ID_KEYS` 的优先序负责，本函数只负责"上游没给"的那一侧，
    免得多处判上游 id 而各处判得还不一样。

    `url` 先 `strip()` 再算键：消费端兜底走的是 `_first_str`（它会 strip），
    生产端若用未 strip 的原串，同一个 ` https://x/a ` 会算出**另一个**哈希键——
    那就是 STEP-02 刚消灭的那族"两处各说各话的冒名键"，只是换了入口。
    """
    from app.services.article_identity import canonical_article_key

    cleaned = url.strip()
    return canonical_article_key(cleaned) if cleaned else ""


@dataclass(frozen=True, slots=True)
class ArticleDetail:
    """付费详情 API 的归一化产物。

    各平台响应字段不同，防腐层统一到此结构后汇入入库链。
    """

    url: str
    title: str
    content_html: str  # 原始 HTML 正文（extractor 可直接消费）
    content_text: str  # 纯文本正文（兜底用，extractor 优先用 html）
    author: str = ""
    biz: str = ""  # 公众号 __biz（base64）
    ghid: str = ""  # 公众号 gh_ ID
    publish_time: datetime | None = None
    source: str = ""  # 来源平台名（dajiala/justoneapi/...）


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

    async def query_work_list(self, identifier: str, page: int) -> tuple[list[dict[str, Any]], int | None]:
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
