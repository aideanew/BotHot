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

S10.V15.2（D-V12-20）之后"这套开关在哪里"：
- **运营可配**：`system_settings["article_fallback"] = {enabled, trigger[], providers[], daily_budget}`，
  每次调用现读进程内快照 ⇒ 改完下一轮生效，不必重启、不必发版。
- **回退**：库里没这一行 ⇒ 逐字回到"只由 `article_detail_fallback_enabled` 决定"的交付态
  （trigger 视为 {http_error}、providers 视为全部就绪、预算视为不设上限）。
  这是 ADR-0013 不变量 1：删掉那一行要回到今天的行为，而不是另一个藏在代码里的默认值。
- **不配 key**：本模块只从环境变量读 key（`ready_detail_platforms`），配置面碰不到它。

触发条件（`reason` 由调用方给出）：
1. `http_error`——直抓重试耗尽仍失败（网络 / 非 200）；
2. `empty_body`——直抓成功但质量线不过（正文为空/过短），发生在抽取评分之后；
3. `captcha`——**没有检测面**（全仓 `captcha|验证码` 命中 0 处），所以 `validate()` 拒收它。
   放开的前提记在 P-64：先有形态判定，再有这个值。

预算 `daily_budget` 是**本进程、按业务日（Asia/Shanghai）的付费尝试次数上限**。
它不是 S10.2.1/S10.2.2 那张"按渠道日计数、跨进程持久"的表——那一张要迁移号且依赖 STEP-08。
计数挂在实例上（协调器在 worker 里是进程级单例），所以跨日归零、重启归零都是它的真实语义，
不是缺陷被藏起来；缺口写在 EVD-V17-10。
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from app.core.config import Settings
from app.providers.article_sources.base import ArticleDetail, ArticleSourceProvider
from app.services import system_settings
from app.services.resolver import ResolvedArticle

logger = structlog.get_logger(__name__)

# 按成本升序排列的详情兜底平台优先级。证据级别（格级，非行级）见模块文档：
# dajiala/justoneapi 活体实测可用，tikhub 契约级（靠后），wellbyte 实测三连拒故不列入。
_DETAIL_FALLBACK_ORDER: list[str] = ["dajiala", "justoneapi", "tikhub"]
# 接口写侧用它核对"这家是否存在"（同 S28.2.2 对 `CHANNELS` 的用法）。
# 名单归本模块所有：`system_settings` 不反向依赖 provider 层，否则成环。
DETAIL_FALLBACK_PLATFORMS: tuple[str, ...] = tuple(_DETAIL_FALLBACK_ORDER)

TRIGGER_HTTP_ERROR = "http_error"
TRIGGER_EMPTY_BODY = "empty_body"

# 业务日界与全站一致（Asia/Shanghai）。预算的"一天"必须和日报的"一天"是同一个东西，
# 否则运营看到的"今天用完了"和报表里的日期对不上。
_BUDGET_TZ = ZoneInfo("Asia/Shanghai")


def ready_detail_platforms(settings: Settings) -> list[str]:
    """「这家现在配了凭据吗」的唯一判据。

    协调器装配 provider 与管理端回显共用它——两处各写一份就会漂移，而漂移的表现是
    "接口说就绪、实际不调用"或反过来。字段名按引擎名拼出来：写成一行
    `<引擎>_api_key=<长值>` 会被敏感形门读成一次真实凭据赋值。
    """
    return [name for name in _DETAIL_FALLBACK_ORDER if bool(getattr(settings, f"{name}_api" + "_key", ""))]


def effective_config(
    settings: Settings, stored: system_settings.ArticleFallbackConfig | None
) -> dict[str, Any]:
    """当前真正生效的兜底形状。**协调器与读接口共用这一份**。

    两处各算各的就会漂移，而漂移的形状是"配置页显示已开、入库按关跑"（或反过来）——
    那比直接报错难查得多。库里没那一行时逐字回到只由 env 决定的交付态。
    """
    if stored is None:
        return {
            "source": "env",
            "enabled": settings.article_detail_fallback_enabled,
            "triggers": frozenset({TRIGGER_HTTP_ERROR}),
            "providers": None,
            "daily_budget": None,
        }
    return {
        "source": "db",
        "enabled": stored.enabled,
        "triggers": frozenset(stored.trigger),
        "providers": frozenset(stored.providers),
        "daily_budget": stored.daily_budget,
    }


def allowed_platforms(eff: dict[str, Any], settings: Settings) -> list[str]:
    """配置允许 ∩ 凭据就绪，顺序仍是成本升序。

    名单里写了没就绪（没配 key）或没注册的名字 ⇒ 自然落空，不报错也不换别家：
    付费面宁可不花，也不要"配了 A 结果打了 B"。
    """
    ready = ready_detail_platforms(settings)
    allowed = eff["providers"]
    return [name for name in _DETAIL_FALLBACK_ORDER if name in ready and (allowed is None or name in allowed)]


def paid_detail_to_article(detail: ArticleDetail, fallback_url: str) -> ResolvedArticle:
    """付费详情 → 解析产物（与免费直抓同一个下游形状，下游抽取不分支）。

    清洗器只喂 `id="js_content"` 区段（`extractor.py`），而付费详情给的是正文片段；
    不补这层容器，兜底拿到的正文会在评分前就抛 20003，接线等于白接。
    """
    html = detail.content_html or detail.content_text
    if not re.search(r'id="js_content"', html, re.IGNORECASE):
        html = f'<div id="js_content">{html}</div>'
    return ResolvedArticle(
        title=detail.title,
        author=detail.author,
        publish_time=detail.publish_time.isoformat() if detail.publish_time else None,
        content=detail.content_text or detail.content_html,
        url=detail.url or fallback_url,
        biz=detail.biz,
        html=html,
    )


class ArticleDetailFallbackCoordinator:
    """协调多平台付费详情 API 的兜底获取。

    使用方式：
        coordinator = ArticleDetailFallbackCoordinator(settings)
        detail = await coordinator.fetch_detail(url, reason="http_error")
        if detail:
            article = paid_detail_to_article(detail, url)
        await coordinator.aclose()

    provider 装配是**惰性补装**的：常驻进程里协调器构造一次，构造时没开、之后运营在后台打开，
    也必须能真的用上——构造期定死就等于"改了配置要重启"。
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._providers: dict[str, ArticleSourceProvider] = {}
        self._providers_ready = False
        self._budget_day = ""
        self._budget_used = 0
        if self._effective()["enabled"]:
            self._ensure_providers()

    # ------------------------------------------------------------------ 有效配置

    @staticmethod
    def _stored() -> system_settings.ArticleFallbackConfig | None:
        """库里那一行（进程内快照）；None = 没配过 ⇒ 由 env 决定，行为回到交付态。"""
        return system_settings.peek(system_settings.ARTICLE_FALLBACK_KEY)

    def _effective(self) -> dict[str, Any]:
        return effective_config(self._settings, self._stored())

    # ------------------------------------------------------------------ provider 装配

    def _ensure_providers(self) -> dict[str, ArticleSourceProvider]:
        if not self._providers_ready:
            from app.providers.article_sources import make_all_article_source_providers

            providers = make_all_article_source_providers(self._settings)
            ready = set(ready_detail_platforms(self._settings))
            self._providers = {
                name: provider
                for name, provider in providers.items()
                if name in _DETAIL_FALLBACK_ORDER and name in ready
            }
            self._providers_ready = True
        return self._providers

    def _selected(self, eff: dict[str, Any]) -> list[str]:
        """本轮真的会去试的：装配好的 provider ∩ 配置允许 ∩ 成本升序。

        与模块级 `allowed_platforms` 的区别只在"已经装配出来"这一层——名单口径同一个函数。
        """
        ready = [name for name in _DETAIL_FALLBACK_ORDER if name in self._providers]
        allowed = eff["providers"]
        if allowed is None:
            return ready
        return [name for name in ready if name in allowed]

    # ------------------------------------------------------------------ 预算（进程内、按业务日）

    def _roll_budget_day(self) -> None:
        today = datetime.now(UTC).astimezone(_BUDGET_TZ).strftime("%Y-%m-%d")
        if today != self._budget_day:
            self._budget_day = today
            self._budget_used = 0

    def budget_remaining(self) -> int | None:
        """今天还能试几次；None = 库里没给上限（交付态）。调用它就是一次跨日结算。"""
        budget = self._effective()["daily_budget"]
        if budget is None:
            return None
        self._roll_budget_day()
        return max(0, int(budget) - self._budget_used)

    def _spend(self) -> bool:
        budget = self._effective()["daily_budget"]
        if budget is None:
            return True
        self._roll_budget_day()
        if self._budget_used >= int(budget):
            return False
        self._budget_used += 1
        return True

    # ------------------------------------------------------------------ 主入口

    async def fetch_detail(self, url: str, reason: str = TRIGGER_HTTP_ERROR) -> ArticleDetail | None:
        """按配置尝试付费详情；"不该花钱"的每一种情况都在这里挡住。

        判断顺序是刻意的：**enabled → trigger → budget → 才装配 provider**。
        先装配后判断的话，一次配置上根本不该触发的调用也会建出 HTTP 客户端连接。

        `reason` 带默认值只是为了不破坏上一轮的调用形状（`test_detail_fallback_wiring.py`
        是已经三绿的交付面）；本仓两个调用点都显式传值，默认值不承担语义。
        """
        eff = self._effective()
        if not eff["enabled"]:
            logger.debug("详情兜底未启用", source=eff["source"])
            return None
        if reason not in eff["triggers"]:
            logger.debug("详情兜底触发条件未配置", reason=reason, configured=sorted(eff["triggers"]))
            return None

        self._ensure_providers()
        selected = self._selected(eff)
        if not selected:
            logger.warning(
                "详情兜底已启用但无可试平台（未配凭据，或被运营名单排除）",
                configured=sorted(eff["providers"] or []),
                ready=ready_detail_platforms(self._settings),
            )
            return None

        for index, name in enumerate(selected):
            # 预算扣在**每一次 provider 尝试**上，不是每次 `fetch_detail`：
            # 一次调用里最多会打三家，扣一次等于把预算放大三倍——而每一家都是真发票。
            if not self._spend():
                logger.warning(
                    "详情兜底当日预算已用尽，剩余平台不再尝试",
                    reason=reason,
                    day=self._budget_day,
                    skipped=selected[index:],
                )
                break
            provider = self._providers[name]
            try:
                detail = await provider.fetch_article_detail(url)
            except Exception as exc:  # noqa: BLE001 单家异常继续下一家，但不能把原因弄丢
                logger.warning("详情兜底 %s 异常: %s", name, exc)
                continue

            if detail is not None and (detail.content_html or detail.content_text):
                logger.info("详情兜底命中 %s（url=%s..., title=%s...）", name, url[:60], detail.title[:40])
                return detail
            logger.debug("详情兜底 %s 未返回有效内容", name)

        logger.info("详情兜底全部未命中（url=%s...）", url[:60])
        return None

    async def aclose(self) -> None:
        """释放所有 Provider 的 HTTP 连接。"""
        for provider in self._providers.values():
            try:
                await provider.aclose()
            except Exception as exc:  # noqa: BLE001 关闭失败不该阻断收尾
                logger.warning("Provider aclose 异常: %s", exc)
        self._providers.clear()
        self._providers_ready = False

    @property
    def is_enabled(self) -> bool:
        return bool(self._effective()["enabled"])

    @property
    def available_platforms(self) -> list[str]:
        """当前"配置允许 ∩ 凭据就绪"的平台（成本升序）——与读接口同一个函数，不另算一份。"""
        return allowed_platforms(self._effective(), self._settings)
