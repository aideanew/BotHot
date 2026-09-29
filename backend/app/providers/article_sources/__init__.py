"""文章来源 Provider 包（providers/article_sources/）。

4 个第三方 API 平台作为文章发现 + 详情兜底渠道，与 RedFox 共存于发现注册表。

平台概览：
- Dajiala    极致了    发现(ghid) + 详情(HTML)     ¥0.04~0.14/次
- JustOneAPI            发现(ghid) + 详情(正文)      ¥0.15~0.40/次
- TikHub               发现(ghid) + 搜索(关键词)    需付费余额（当前禁用）
- Wellbyte   数井      搜索(关键词) + 发现(文章URL) 78~155cr/次  详情禁用(422)

统一接口：ArticleSourceProvider 协议（query_work_list + fetch_article_detail + search_articles）
工厂函数：make_article_source_provider(name, settings) / make_all_providers(settings)

参见 ADR-0008（文章来源平台接入策略）。
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings
from app.core.errors import ConfigurationError

from app.providers.article_sources.base import (
    ArticleDetail,
    ArticleSearchResult,
    ArticleSourceProvider,
)
from app.providers.article_sources.dajiala import DajialaClient
from app.providers.article_sources.justoneapi import JustOneApiClient
from app.providers.article_sources.tikhub import TikhubClient
from app.providers.article_sources.wellbyte import WellbyteClient

logger = logging.getLogger(__name__)

__all__ = [
    "ArticleDetail",
    "ArticleSearchResult",
    "ArticleSourceProvider",
    "DajialaClient",
    "JustOneApiClient",
    "TikhubClient",
    "WellbyteClient",
    "make_article_source_provider",
    "make_all_article_source_providers",
    "ARTICLE_SOURCE_PROVIDERS",
]

# 平台注册名 → 工厂
ARTICLE_SOURCE_PROVIDERS: dict[str, type] = {
    "dajiala": DajialaClient,
    "justoneapi": JustOneApiClient,
    "tikhub": TikhubClient,
    "wellbyte": WellbyteClient,
}


def make_article_source_provider(
    name: str, settings: Settings
) -> ArticleSourceProvider:
    """按名称创建文章来源 Provider 实例。

    各 Provider 从 settings 读取自己的 API key + base_url。
    未配置 key 的平台抛 ConfigurationError（调用方应先检查 availability）。
    """
    cls = ARTICLE_SOURCE_PROVIDERS.get(name)
    if cls is None:
        raise ConfigurationError(f"未知文章来源平台: {name}")

    # 按 name 取对应的 settings 字段
    key_map = {
        "dajiala": (settings.dajiala_api_key, settings.dajiala_base_url),
        "justoneapi": (settings.justoneapi_api_key, settings.justoneapi_base_url),
        "tikhub": (settings.tikhub_api_key, settings.tikhub_base_url),
        "wellbyte": (settings.wellbyte_api_key, settings.wellbyte_base_url),
    }
    api_key, base_url = key_map[name]
    if not api_key:
        raise ConfigurationError(f"{name}_api_key 未配置")

    return cls(api_key=api_key, base_url=base_url)  # type: ignore[arg-type]


def make_all_article_source_providers(
    settings: Settings,
) -> dict[str, ArticleSourceProvider]:
    """创建所有已配置 key 的文章来源 Provider 实例。

    未配置 key 的平台跳过（不抛异常），返回的 dict 仅含可用平台。
    用于启动时批量注册到发现注册表。
    """
    providers: dict[str, ArticleSourceProvider] = {}
    for name in ARTICLE_SOURCE_PROVIDERS:
        try:
            provider = make_article_source_provider(name, settings)
            providers[name] = provider
            logger.info("文章来源 Provider 已就绪: %s", name)
        except ConfigurationError:
            logger.debug("文章来源 Provider %s 未配置 key，跳过", name)
    return providers
