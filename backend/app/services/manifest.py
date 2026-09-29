"""Manifest 同步（1.2）：RedFox 作品清单 → `ArticleManifest`（DISCOVERED）落库去重。

设计口径（大纲 v1.4 §8.1 序4 验收锚：「`_sync_manifests` 接 query_work_list 或
`_seed_manifests`；biz+article_id 唯一键幂等」）：
- **写入方**：把 Discovery Provider（默认 `RedfoxClient.query_work_list`）的原始行映射为
  `ArticleManifest` 并落库，本项之前该表**只有测试在写**（`_seed_manifests` 先例）；
- **幂等**：唯一键 `(source_id, external_id)`（entities.py `uq_manifest_source_external`）
  ——重复同步不产生重复行，仅更新可变字段（title/url/publish_time/content_hash）；
- **不造数**：Provider 缺 Key / 报错 → 异常上抛（承 RedfoxClient 反造假口径），
  本服务绝不用 fixture 占位冒充真实清单；
- **脱机可验**：Provider 为注入式 Protocol，单测用桩（= `_seed_manifests` 先例的等价物）。

字段口径（R8 活体实测 2026-09-28，广域库 `data.list[]` 20 键）：
`workUuid`（32 位小写 hex）、`workUrl`（**无 `url` 键**）、`title`、`summary`、
`publishTime`（**无时区的北京时间串**，如 `"2026-09-27 07:42:00"`）、
`readCount`/`likeCount` 等。故 `_map_row` 取 `workUrl` 与 `_parse_time` 按 `Asia/Shanghai`
解释无时区值——这两处此前的实现导致入库 `url=""`（JobWorker 硬失败）与 8 小时时差。

增量收敛（L1-2）：上游清单按发布时间倒序，故**未见篇恒构成前缀**。据此翻页直到「本页
出现任何一条既有行 / 末页 / 空页」为止，无需依赖上游自报的 `data.total` 算缺口——
`total` 漏报时漏报的新篇会让整页全为新行，自动触发继续翻页，不漏采。稳态与空日均为
**1 次/号/轮**（不调用就无法知道 `total` 变没变，这是信息论下界），首次回填
`⌈总数/20⌉` 次；`max_pages` 是回填硬上限。零 schema 变更。
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.entities import ArticleManifest

logger = logging.getLogger(__name__)

MANIFEST_STATUS_DISCOVERED = "DISCOVERED"
DEFAULT_MAX_PAGES = 20

# 广域库 `publishTime` 为无时区北京时间串；按 UTC 解析会整体早 8 小时（L1-1 修复）
UPSTREAM_TZ = ZoneInfo("Asia/Shanghai")

# 防御式字段别名（按活体实测字段形状排列：命中键在前，历史/未知变体在后兜底）
_ID_KEYS = ("workUuid", "work_uuid", "uuid", "id", "articleId", "article_id")
_URL_KEYS = ("workUrl", "work_url", "url", "link", "articleUrl", "article_url")
_TITLE_KEYS = ("title", "name", "articleTitle", "article_title")
_TIME_KEYS = ("publishTime", "publish_time", "pubTime", "pub_time", "createTime", "create_time")
_HASH_KEYS = ("contentHash", "content_hash", "hash")


class WorkListProvider(Protocol):
    """清单 Provider：与 `RedfoxClient.query_work_list` 同形（page 从 1 起）。

    返回 `(原始行, 上游 total)`：`total` 供增量游标算缺口；上游缺失时为 `None`。
    """

    async def query_work_list(
        self, biz: str, page: int
    ) -> tuple[list[dict[str, Any]], int | None]: ...

    async def aclose(self) -> None: ...


@dataclass
class ManifestSyncReport:
    """一轮清单同步的记账（供日志/断言；零假成功：各计数与真实写库一一对应）。"""

    pages: int = 0
    discovered: int = 0  # 新建 DISCOVERED 行
    updated: int = 0  # 既有行可变字段有变化
    unchanged: int = 0  # 既有行与远端一致
    skipped: int = 0  # 缺 external_id 等不可用行
    known_local: int = 0  # 同步前本地已入库条数（增量游标基线）
    total_remote: int | None = None  # 上游 data.total（缺失/异常 → None）
    pages_planned: int = 0  # 按缺口规划的分页数
    calls_made: int = 0  # 实际上游调用次数（成本口径）

    @property
    def total(self) -> int:
        return self.discovered + self.updated + self.unchanged + self.skipped


def _first_str(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for k in keys:
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _parse_time(value: Any) -> datetime | None:
    """宽松时间解析：epoch 秒/毫秒（数值或纯数字串）与 ISO/常见日期串。

    无时区值按上游口径 `Asia/Shanghai` 解释（广域库实测形状），不再默认 UTC。
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return _from_epoch(float(value))
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.isdigit():
            return _from_epoch(float(s))
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00").replace("/", "-"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=UPSTREAM_TZ)
    return None


def _from_epoch(ts: float) -> datetime | None:
    if ts <= 0:
        return None
    if ts > 1e11:  # 毫秒级
        ts /= 1000.0
    try:
        return datetime.fromtimestamp(ts, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _upstream_page_size() -> int:
    """上游每页条数；惰性导入以让非 RedFox 调用方不必牵动 httpx 依赖。"""
    from app.providers.redfox.client import PAGE_SIZE

    return PAGE_SIZE


def _map_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """原始清单行 → ArticleManifest 字段（缺 external_id 不可用 → None）。

    字段口径集中于此；上游字段形状变化时只改本函数。
    """
    external_id = _first_str(row, _ID_KEYS)
    if not external_id:
        return None
    url = _first_str(row, _URL_KEYS)
    title = _first_str(row, _TITLE_KEYS)
    content_hash = _first_str(row, _HASH_KEYS) or hashlib.sha256(
        f"{url}|{title}".encode()
    ).hexdigest()
    publish_time: datetime | None = None
    for k in _TIME_KEYS:
        if k in row:
            publish_time = _parse_time(row.get(k))
            break
    return {
        "external_id": external_id,
        "url": url,
        "title": title,
        "publish_time": publish_time,
        "content_hash": content_hash,
        "status": MANIFEST_STATUS_DISCOVERED,
    }


class ManifestSyncService:
    """清单同步编排（显式 flush，事务边界交调用方——与 SourceSubscriptionService 同口径）。"""

    def __init__(
        self, session: AsyncSession, provider: WorkListProvider, *, page_size: int | None = None
    ) -> None:
        self._session = session
        self._provider = provider
        # 注入式页大小让增量游标可脱机断言；缺省取上游常量。
        self._page_size = page_size if page_size and page_size > 0 else _upstream_page_size()

    async def sync_source(
        self, source_id: str, biz: str, *, max_pages: int = DEFAULT_MAX_PAGES
    ) -> ManifestSyncReport:
        """翻页拉取清单并幂等落库，直到「新增量已耗尽」。

        终止条件（任一命中即止，且始终受 `max_pages` 硬上限约束）：
        ① 空页；② 末页（不足整页）；③ **本页出现任何一条既有行**（缺 id 的脏行不算）。
        条件③取代了 R8 方案里「`⌈缺口/页⌉ + 1` 无条件缓冲页」：上游倒序列表中
        **未见篇恒构成前缀**（新篇总是插到最新端），故「本页混入已知行」精确等价于
        「新增量已全部落在前面」，无需盲猜一页。由此稳态与空日均为 1 次调用，
        而 `total` 漏报时仍不漏采（漏报的新篇会让整页全为新行 → 触发继续翻页）。

        幂等键 `(source_id, external_id)`：既有行只更新可变字段；并发插入撞唯一键时
        回退为「重新取行 → 更新」（与 asset.py `upsert_content` 同法，避免未捕获 IntegrityError）。
        即使上游 `offset` 语义劣化返回重复页，也只是多耗调用，不产生脏数据。
        """
        report = ManifestSyncReport()
        if not biz:
            logger.warning("Manifest 同步缺 biz，跳过（source=%s）", source_id)
            return report
        size = self._page_size
        report.known_local = await self._known_count(source_id)
        planned = max_pages
        page = 1
        while page <= max_pages:
            rows, total_remote = await self._provider.query_work_list(biz, page)
            report.calls_made += 1
            if total_remote is not None:
                report.total_remote = total_remote
                gap = max(total_remote - report.known_local, 0)
                planned = max(1, (gap + size - 1) // size)
                report.pages_planned = planned
            report.pages = page
            if not rows:
                break
            saw_existing = False
            for row in rows:
                mapped = _map_row(row)
                if mapped is None:
                    report.skipped += 1
                    continue
                outcome = await self._upsert(source_id, mapped)
                setattr(report, outcome, getattr(report, outcome) + 1)
                if outcome != "discovered":
                    saw_existing = True
            if len(rows) < size:
                break  # 末页：清单已到底
            if saw_existing:
                break  # 本页已含已知行 → 未见篇前缀到此为止（缺 id 的脏行不算）
            page += 1
        await self._session.flush()
        logger.info(
            "Manifest 同步 source=%s biz=%s calls=%d gap_planned=%d pages=%d local=%d total=%s "
            "new=%d upd=%d same=%d skip=%d",
            source_id,
            biz,
            report.calls_made,
            report.pages_planned,
            report.pages,
            report.known_local,
            report.total_remote,
            report.discovered,
            report.updated,
            report.unchanged,
            report.skipped,
        )
        return report

    # ------------------------------------------------------------------ 内部

    async def _known_count(self, source_id: str) -> int:
        """本地已入库清单条数（增量游标基线；走 `uq_manifest_source_external` 前缀索引）。"""
        # scalar() 的静态返回类型含 None（无行/无值），而 count() 在 GROUP BY 缺席时
        # 必然返回单行数值——先收窄 None 再转 int，避免 mypy arg-type 误报。
        total = await self._session.scalar(
            select(func.count()).select_from(ArticleManifest).where(
                ArticleManifest.source_id == source_id
            )
        )
        return int(total) if total is not None else 0

    async def _upsert(self, source_id: str, mapped: dict[str, Any]) -> str:
        """按唯一键写库；返回 "discovered" / "updated" / "unchanged" 之一。"""
        existing = await self._get(source_id, mapped["external_id"])
        if existing is None:
            manifest = ArticleManifest(source_id=source_id, **mapped)
            self._session.add(manifest)
            try:
                async with self._session.begin_nested():  # SAVEPOINT：并发撞键不毁外层事务
                    await self._session.flush()
            except IntegrityError:
                existing = await self._get(source_id, mapped["external_id"])
                if existing is None:
                    raise
                return self._apply_update(existing, mapped)
            return "discovered"
        return self._apply_update(existing, mapped)

    async def _get(self, source_id: str, external_id: str) -> ArticleManifest | None:
        return await self._session.scalar(
            select(ArticleManifest).where(
                ArticleManifest.source_id == source_id,
                ArticleManifest.external_id == external_id,
            )
        )

    @staticmethod
    def _apply_update(existing: ArticleManifest, mapped: dict[str, Any]) -> str:
        """可变字段差异更新；全等则计 unchanged（幂等第二跑应为 unchanged）。"""
        changed = False
        for field in ("url", "title", "publish_time", "content_hash"):
            new = mapped.get(field)
            if getattr(existing, field) != new:
                setattr(existing, field, new)
                changed = True
        return "updated" if changed else "unchanged"


def make_redfox_provider(settings: Settings) -> WorkListProvider | None:
    """按配置装配 RedFox 清单 Provider；**无 Key → None**（显式缺省，不造数）。

    返回 None 表示「未配置发现源」：调度器据此跳过发现、仅按既有清单做 Diff（日志留痕）。
    """
    if not settings.redfox_api_key:
        return None
    from app.providers.redfox.client import RedfoxClient

    return RedfoxClient(settings.redfox_base_url, settings.redfox_api_key)
