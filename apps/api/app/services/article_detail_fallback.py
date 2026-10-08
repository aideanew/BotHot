"""文章详情兜底协调器。

⚠️ 架构前提：详情主路径 = 免费直抓（WechatArticleFetcher，实测 6/6 成功率），
所有付费详情 API 仅作兜底——默认关闭（article_detail_fallback_enabled=False），
仅在直抓失败且非图集类（item_show_type ≠ 8）时触发。

格级证据级别（每个平台的能力格自带证据状态，不用行级标签覆盖）：
- Dajiala article_html    ¥0.04/次   活体实测 TC-A1-07 ✅稳定可用（HTML 全文+元数据）
- JustOneAPI detail v1    ¥0.15/次   活体实测 TC-A3-07 ✅含正文 content+content_multi_text
- TikHub v2 fetch_*_h5    $0.001~0.01 契约级（OpenAPI 在案，TC-A2-02b 402 未实测）⚠️
  ※ 仅 web/* 旧端点已下线（TC-A2-04 404），v2 组详情端点仍在现行 OpenAPI
- Wellbyte detail_v2      30cr       活体实测 TC-A4-05/06/07 ❌422三连拒禁用（0扣费）

协调器按成本升序尝试：Dajiala → JustOneAPI → TikHub（Wellbyte 禁用不列入）。
首个返回有效 ArticleDetail 的平台即止，不重复消费。

触发条件（由调用方判断）：
1. 直抓 HTTP 失败（网络错误 / 非 200）
2. 直抓成功但 extractor 判定正文为空（ExtractQualityLowError）
3. item_show_type ≠ 8（非图集类，图集类天然无文字正文，不应触发兜底）

开关：settings.article_detail_fallback_enabled（默认 False，按需开）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.core.config import Settings
from app.providers.article_sources.base import ArticleDetail, ArticleSourceProvider

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

# 按成本升序排列的详情兜底平台优先级
# 证据级别（格级，非行级）：
#   dajiala   article_html      ¥0.04/次    活体实测 TC-A1-07 ✅稳定可用
#   justoneapi detail/v1        ¥0.15/次    活体实测 TC-A3-07 ✅含正文
#   tikhub    v2 fetch_*_h5     $0.001~0.01 契约级（OpenAPI 在案，402 未实测）⚠️
#   wellbyte  detail_v2         30cr        活体实测 TC-A4-05/06/07 ❌422三连拒禁用
# Wellbyte detail_v2 禁用不列入；TikHub v2 端点契约在案但未实测，列入但靠后
_DETAIL_FALLBACK_ORDER: list[str] = ["dajiala", "justoneapi", "tikhub"]


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
