"""文章详情兜底协调器。

当直抓（WechatArticleFetcher）失败或正文为空时，按优先级尝试付费详情 API
获取文章正文。各平台详情能力不同：

- Dajiala article_html    ¥0.04/次  ✅ HTML 全文
- JustOneAPI detail v1    ¥0.15/次  ✅ 带正文 content + 60+ 字段
- TikHub detail           端点已下线（404）  ❌
- Wellbyte detail v2      422 质量门槛三连拒  ❌

协调器按成本升序尝试：Dajiala → JustOneAPI →（TikHub/Wellbyte 跳过）。
首个返回有效 ArticleDetail 的平台即止，不重复消费。

触发条件（由调用方判断）：
1. 直抓 HTTP 失败（网络错误 / 非 200）
2. 直抓成功但 extractor 判定正文为空（ExtractQualityLowError）
3. item_show_type ≠ 8（非图集类，图集类天然无文字正文，不应触发兜底）

开关：settings.article_detail_fallback_enabled（默认 False，按需开）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.config import Settings
from app.core.errors import ConfigurationError
from app.providers.article_sources.base import ArticleDetail, ArticleSourceProvider

if TYPE_CHECKING:
    from app.providers.article_sources import (
        DajialaClient,
        JustOneApiClient,
        TikhubClient,
        WellbyteClient,
    )

logger = logging.getLogger(__name__)

# 按成本升序排列的详情兜底平台优先级
# TikHub 和 Wellbyte 的详情端点不可用，不列入
_DETAIL_FALLBACK_ORDER: list[str] = ["dajiala", "justoneapi"]


class ArticleDetailFallbackCoordinator:
    """协调多平台付费详情 API 的兜底获取。

    启动时从 settings 创建所有已配置 key 的平台 Provider，
    按 _DETAIL_FALLBACK_ORDER 优先级逐个尝试。

    使用方式：
        coordinator = ArticleDetailFallbackCoordinator(settings)
        detail = await coordinator.fetch_detail(url)
        if detail:
            # 用 detail.content_html 喂 extractor
        await coordinator.aclose()
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._enabled = settings.article_detail_fallback_enabled
        self._providers: dict[str, ArticleSourceProvider] = {}
        if self._enabled:
            self._providers = self._init_providers()

    def _init_providers(self) -> dict[str, ArticleSourceProvider]:
        """初始化所有已配置 key 的平台 Provider。"""
        from app.providers.article_sources import make_all_article_source_providers

        providers = make_all_article_source_providers(self._settings)
        # 只保留有详情能力的平台（按 _DETAIL_FALLBACK_ORDER 过滤）
        return {
            name: provider
            for name, provider in providers.items()
            if name in _DETAIL_FALLBACK_ORDER
        }

    async def fetch_detail(self, url: str) -> ArticleDetail | None:
        """按优先级尝试付费详情 API。

        首个返回有效 ArticleDetail 的平台即止。
        开关关闭或无可用平台时返回 None（调用方降级到原有失败处理）。
        """
        if not self._enabled:
            logger.debug("详情兜底未启用（article_detail_fallback_enabled=False）")
            return None

        if not self._providers:
            logger.warning("详情兜底已启用但无可用平台（未配置 API key）")
            return None

        for name in _DETAIL_FALLBACK_ORDER:
            provider = self._providers.get(name)
            if provider is None:
                continue

            try:
                detail = await provider.fetch_article_detail(url)
            except Exception as exc:
                logger.warning("详情兜底 %s 异常: %s", name, exc)
                continue

            if detail is not None and (detail.content_html or detail.content_text):
                logger.info(
                    "详情兜底命中 %s（url=%s..., title=%s...）",
                    name,
                    url[:60],
                    detail.title[:40],
                )
                return detail
            logger.debug("详情兜底 %s 未返回有效内容", name)

        logger.info("详情兜底全部未命中（url=%s...）", url[:60])
        return None

    async def aclose(self) -> None:
        """释放所有 Provider 的 HTTP 连接。"""
        for provider in self._providers.values():
            try:
                await provider.aclose()
            except Exception as exc:
                logger.warning("Provider aclose 异常: %s", exc)
        self._providers.clear()

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def available_platforms(self) -> list[str]:
        """当前已就绪的详情兜底平台列表。"""
        return [name for name in _DETAIL_FALLBACK_ORDER if name in self._providers]
