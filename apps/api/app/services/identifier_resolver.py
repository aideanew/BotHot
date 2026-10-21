"""信息源标识的读取与补全（STEP-08 S8.2.1；形状与不变量见 ADR-0014）。

三件事，各自都有一种"看起来做了其实没做"的失败方式：

1. **读**：`identifiers(source_id)` 只回 `IDENTIFIER_KINDS` 里的种类。库里若有未知 kind 的行
   （手工写库、或未来某卡写错了），这里**跳过并告警**而不是当成一种可用标识——
   渠道选择拿一个没人认识的标识去装配 provider，表现是"清单为空"而不是报错。
2. **补 biz / sample_url / ghid**：`ensure_identifiers(source, html=...)`。
   为什么不能只靠迁移里那次回填：回填是有截止线的，之后每新建一个源都不会有行。
   所以生产里有一个固定调用点——入库落库那一步（`kb._persist_document`，AST 门钉住"只此一处"），
   再加上读取处也会补，让"新源没有标识"不是一颗等着被踩的雷。
3. **ghid 不从 biz 推，只从已在手的 HTML 读**：卡面 S8.2.1 写的是"从直抓 HTML 解析 `gh_`
   原始 id（以样本为准），入库成功时写 `ghid`（零额外请求）"。本模块照此实现 `ghid_from_html()`：
   只在**带键名的位置**取值（见 `_GHID_SHAPES`），正文里出现一串 `gh_` 开头的文字不会被当成标识。
   为什么必须这么窄：`(kind, value)` 是全局唯一的，一个错写的 ghid 不只是这一条脏——
   它会把真号主的后来者永久挡在门外（`_insert` 撞约束只能告警，不能覆盖）。
   至于"今天现网的直抓 HTML 到底把 gh_ 放在哪个键名下"：**本仓没有样本可证**（读数见
   EVD-V17-08 §7b），所以本模块同时保留 `GHID_MAPPING_CHANNELS`（从别的渠道换 ghid 的能力，现读为空）
   与一条 `未测` 声明，不假装解析规则已被活体确认。
"""

from __future__ import annotations

import re

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Source, SourceIdentifier
from app.services.article_identity import parse_wechat_url

logger = structlog.get_logger(__name__)

IDENTIFIER_KINDS: frozenset[str] = frozenset({"biz", "ghid", "sample_url", "feed_url"})
ORIGIN_SOURCE = "source"  # 来自源记录本身（external_id / url 字段）
ORIGIN_RESOLVER = "resolver"  # 由本模块从别的字段**推导**出来

# 能从**渠道侧**回答"给一个 biz，返回 gh_ 的人是谁"的渠道。现读为空：
#   dajiala / justoneapi / tikhub 都**以 ghid 为入参**（`dajiala.py:85`、`justoneapi.py:101`、
#   `tikhub.py:16`），拿不到 biz→ghid；`wellbyte.py:14` 有映射但形状是「文章 URL → gh_」且按 credits
#   计费（TC-A4-04 实测 78cr），不是零成本。⇒ 本模块的 ghid 只有下面 `ghid_from_html` 一条来源。
# 将来接上真支持 biz→ghid 的渠道时把这个常量填上，`test_no_channel_claims_the_biz_to_ghid_mapping`
# 会红着逼人来补"渠道兜底"分支与它的用例（读数与 P 项见 EVD-V17-08 §7b）。
GHID_MAPPING_CHANNELS: tuple[str, ...] = ()


def biz_from_sample_url(url: str) -> str:
    """从样例链接解析 biz。**委托** `article_identity.parse_wechat_url`，不自己写第二份。

    同一个事实在两处解析是本仓的老病（`kb._biz_from_url` 当年只读 `biz=` 而真实参数是 `__biz`，
    于是长链的号主身份恒为空串，见 D-01b）；委托加一条"与解析层恒等"的用例才是闭环。
    """
    return parse_wechat_url(url).biz or ""


_GHID_TOKEN = r"gh_[0-9A-Za-z]{6,40}"

# 取值只认两种**带键名**的位置，正文里出现 gh_ 开头的文字不算标识：
#   ① 页面 JS 变量——键名家族与形状照 `source_resolver._BIZ_RE` 的两支实证形态镜像
#      （`var X = "…"` = 2026-09 真实页面、`var X = "" || "…"` = M0 样本），只把 biz 换成 user_name；
#   ② 帐号信息框 `<span class="profile_weixin">gh_…</span>`。
# token 形状 `gh_ + 6~40 位`实测自四家 provider 的 JSON 字段（`gh_b9465228558d`，TC-A1-07/A3-07/A4-04）。
# ⚠️ 未测：现网直抓页面到底把 gh_ 挂在哪个变量名下，本仓没有样本可证（EVD-V17-08 §7b）⇒
# 两支都不命中时返回空串，入库照常，只是这一格留空。错写的代价不是"一条脏行"而是
# `(kind,value)` 全局唯一约束把真号主的后来者永久挡在门外，所以宁缺勿猜。
_GHID_SHAPES: tuple[re.Pattern[str], ...] = (
    re.compile(rf'var\s+user_name\s*=\s*"({_GHID_TOKEN})"'),
    re.compile(rf'var\s+user_name\s*=\s*""\s*\|\|\s*"({_GHID_TOKEN})"'),
    re.compile(rf'class="profile_weixin"[^>]*>\s*({_GHID_TOKEN})\s*<'),
)


def ghid_from_html(html: str) -> str:
    """从**已在手**的直抓 HTML 里读 `gh_` 原始 id；读不到就返回空串（不猜、不补请求）。"""
    for shape in _GHID_SHAPES:
        got = shape.search(html or "")
        if got is not None:
            return got.group(1)
    return ""


class IdentifierResolver:
    """一个源的标识集合的读写口。服务层用，路由（S8.4）也用它——不各处直查表。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def identifiers(self, source_id: str) -> dict[str, str]:
        """该源已登记的标识（未知 kind 跳过并告警，不参与渠道选择）。"""
        rows = (
            await self._session.execute(
                select(SourceIdentifier.kind, SourceIdentifier.value).where(
                    SourceIdentifier.source_id == source_id
                )
            )
        ).all()
        out: dict[str, str] = {}
        for kind, value in rows:
            if kind not in IDENTIFIER_KINDS:
                logger.warning("source_identifiers 含未登记的 kind（已忽略）: %s", kind)
                continue
            out.setdefault(kind, value)
        return out

    async def find_source_id(self, kind: str, value: str) -> str | None:
        """按标识反查源。`(kind, value)` 唯一 ⇒ 最多一个命中，这也是那条约束存在的理由。"""
        if kind not in IDENTIFIER_KINDS or not value:
            return None
        return (
            await self._session.execute(
                select(SourceIdentifier.source_id).where(
                    SourceIdentifier.kind == kind, SourceIdentifier.value == value
                )
            )
        ).scalars().first()

    async def ensure_identifiers(self, source: Source, html: str = "") -> dict[str, str]:
        """补齐并返回该源的标识：biz（external_id 优先，其次从样例链接解析）+ sample_url + ghid。

        `html` 是调用方**已经抓到手**的那篇文章页原文（入库路径天然有），传进来只为顺带读一个
        `gh_` ⇒ 零额外请求；不传则这一格留空，不影响别的标识。

        幂等靠"先查后插 + 撞唯一约束就当作已有"，不是靠 upsert 的 `DO NOTHING`：
        撞约束说明**另一个源**已经占了这个标识，那正是必须发生告警的一刻
        （号主身份被两个源共用 = P0-1 那一族的形状）。
        """
        wanted: list[tuple[str, str, str]] = []
        if source.external_id:
            wanted.append(("biz", str(source.external_id), ORIGIN_SOURCE))
        derived_biz = biz_from_sample_url(source.url or "")
        if derived_biz:
            wanted.append(("biz", derived_biz, ORIGIN_RESOLVER))
        if source.url:
            wanted.append(("sample_url", str(source.url), ORIGIN_SOURCE))
        derived_ghid = ghid_from_html(html)
        if derived_ghid:
            wanted.append(("ghid", derived_ghid, ORIGIN_RESOLVER))

        have = await self.identifiers(source.id)
        for kind, value, origin in wanted:
            if kind in have:
                continue
            if await self._insert(source.id, kind, value, origin):
                have[kind] = value
        return have

    async def _insert(self, source_id: str, kind: str, value: str, origin: str) -> bool:
        try:
            async with self._session.begin_nested():
                self._session.add(
                    SourceIdentifier(source_id=source_id, kind=kind, value=value, origin=origin)
                )
            await self._session.flush()
            return True
        except IntegrityError as exc:
            logger.warning(
                "标识 %s=%s 已属于别的源（不覆盖、不重复写）: %s", kind, _clip(value), type(exc).__name__
            )
            return False

    async def ghid_for(self, source: Source) -> str | None:
        """已登记的 ghid（若有）。ghid 的唯一来源是 `ensure_identifiers(..., html=)` 的解析结果。"""
        return (await self.identifiers(source.id)).get("ghid")


def _clip(value: str) -> str:
    """日志里给形状不给全文：标识可能是带参数的 URL，整段进日志没有意义。"""
    return value if len(value) <= 48 else value[:44] + f"…({len(value)} 字符)"
