"""信息源解析服务（B-T5）：归一化 → 直抓 → 锚点解析 → ResolvedArticle。

失败语义（契约）：
- 归一化失败 → 10006（畸形 URL，A 备案中）；
- 抓取网络失败/非 200 → 20002（EXTRACT_FAILED）；
- 内容形态异常（非文章页，锚点缺失）→ 20001（SOURCE_URL_UNRECOGNIZED）。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import SourceUrlUnrecognizedError
from app.providers.source_resolver import (
    FetchedPage,
    WechatArticleFetcher,
    has_article_anchors,
    normalize_article_url,
    parse_author,
    parse_biz,
    parse_content,
    parse_publish_time,
    parse_title,
)


@dataclass(slots=True)
class ResolvedArticle:
    """解析产物（camelCase 视图经 to_view 输出；html 仅供 B-T6 extractor 内部消费）。"""

    title: str
    author: str
    publish_time: str | None  # ISO 8601
    content: str
    url: str  # 直抓最终 URL（短链跳转后为长链）
    biz: str  # 公众号账号 ID（M2 广域库定位键；短链反解即得）
    html: str = ""  # 原始页面 HTML（不进契约视图；extractor 结构化清洗输入）

    def to_view(self) -> dict:
        return {
            "title": self.title,
            "author": self.author,
            "publishTime": self.publish_time or "",
            "content": self.content,
            "url": self.url,
            "biz": self.biz,
        }


class SourceResolverService:
    """解析编排（fetcher 可注入——测试用 MockTransport 回放，不发真实请求）。"""

    def __init__(self, fetcher: WechatArticleFetcher | None = None) -> None:
        self._fetcher = fetcher or WechatArticleFetcher()

    async def resolve(self, raw_url: str) -> ResolvedArticle:
        url = normalize_article_url(raw_url)  # 10006
        page: FetchedPage = await self._fetcher.fetch(url)  # 20002
        if not has_article_anchors(page.html):
            raise SourceUrlUnrecognizedError("页面不是公众号文章（锚点缺失）")  # 20001
        return ResolvedArticle(
            title=parse_title(page.html),
            author=parse_author(page.html),
            publish_time=parse_publish_time(page.html),
            content=parse_content(page.html),
            url=page.url,
            biz=parse_biz(page.html),
            html=page.html,
        )
