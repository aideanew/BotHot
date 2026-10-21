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
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.collection import ChannelName, CollectionEvent, ManifestStatus, WorkListPage
from app.core import metrics
from app.core.alerting import discovery_idempotency_key, notify_discovery_event
from app.core.config import Settings
from app.models.entities import ArticleManifest
from app.services.article_identity import canonical_article_key

logger = structlog.get_logger(__name__)

# 四态的真源是契约枚举（`app/contracts/collection.py:ManifestStatus`，D-V2-02），
# 这里只取它的值——迁移表在 `app/services/state_machine.py` 的 "manifest" 域。
# 再写一份字符串字面量就等于给状态机造第二个真源（本仓库为这类重复付过多次费）。
MANIFEST_STATUS_DISCOVERED = ManifestStatus.DISCOVERED.value
MANIFEST_STATUS_ENQUEUED = ManifestStatus.ENQUEUED.value
MANIFEST_STATUS_INGESTED = ManifestStatus.INGESTED.value
MANIFEST_STATUS_FAILED = ManifestStatus.FAILED.value
DEFAULT_MAX_PAGES = 20

# 广域库 `publishTime` 为无时区北京时间串；按 UTC 解析会整体早 8 小时（L1-1 修复）
UPSTREAM_TZ = ZoneInfo("Asia/Shanghai")

# 防御式字段别名（按活体实测字段形状排列：命中键在前，历史/未知变体在后兜底）
# S3.3.2：规范名 `id` 排在最前——各家 provider 归一后写的就是它，上游别名（workUuid/uuid/…）
# 留在后面只为兼容既有渠道（redfox 原样透传 `workUuid`）。
_ID_KEYS = ("id", "workUuid", "work_uuid", "uuid", "articleId", "article_id")
_URL_KEYS = ("workUrl", "work_url", "url", "link", "articleUrl", "article_url")
_TITLE_KEYS = ("title", "name", "articleTitle", "article_title")
_TIME_KEYS = ("publishTime", "publish_time", "pubTime", "pub_time", "createTime", "create_time")
_HASH_KEYS = ("contentHash", "content_hash", "hash")


class WorkListProvider(Protocol):
    """清单 Provider 的**旧端口**：与 `RedfoxClient.query_work_list` 同形（page 从 1 起）。

    返回 `(原始行, 上游 total)`：`total` 供增量游标算缺口；上游缺失时为 `None`。

    S8.3.1 之后还有一条**新端口**（不在本协议里，是刻意的）：
    `async def query_work_list_page(identity, cursor, *, page_size) -> WorkListPage`。
    五家 article_sources provider 实现它，`_fetch_page` 优先用它；
    只实现本协议的 Provider（RedFox，它的文件不在本卡所有权内）由旧形状适配，
    适配出的游标就是下一页页号。不把新端口写进本协议 = 不逼一个不能改的文件加一个方法。

    `name` 是指标/告警的 `channel` 维度来源（与发现注册表 `CHANNELS` 同一词表）；
    缺该属性的 Provider 记为 `unknown`，宁可让标签难看，也不要拿 URL 或类型去猜渠道。
    声明成只读 property：`RSSFeedProvider` 就是这样暴露它的，写成可变属性会让协议拒收只读实现。
    """

    @property
    def name(self) -> str: ...

    async def query_work_list(self, biz: str, page: int) -> tuple[list[dict[str, Any]], int | None]: ...

    async def aclose(self) -> None: ...


@dataclass
class ManifestSyncReport:
    """一轮清单同步的记账（供日志/断言；零假成功：各计数与真实写库一一对应）。"""

    pages: int = 0
    discovered: int = 0  # 新建 DISCOVERED 行
    updated: int = 0  # 既有行可变字段有变化
    unchanged: int = 0  # 既有行与远端一致
    skipped: int = 0  # 缺 external_id 等不可用行
    # STEP-03 S3.3.3：行缺 id、以 canonical key 兜底的次数（契约 `ManifestSyncReport.id_fallback`）。
    # **刻意不计进 `total`**：那些行已经落在 discovered/updated/unchanged 里了，
    # 再加一次就是同一行计两遍——这是口径，不是漏加。
    id_fallback: int = 0
    # STEP-05 S5.2.2：`skipped == rows > 0` 的页数（冻结稿 collection.py:176 的告警语义载体）。
    # 与 `skipped` 分工：后者答"丢了几行"，本字段答"有没有整页丢光"——后者才是
    # 采集静默失败（P0-3）的形状，单行丢失不构成告警。
    all_skipped_pages: int = 0
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
            # RFC 822 / 2822：RSS `pubDate` 的形状（`Wed, 02 Oct 2024 07:30:00 GMT`）不是 ISO，
            # 旧实现走到这里直接 return None ⇒ 整源时间戳恒空（P-1 的 rss 那一半）。
            return _parse_rfc822(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=UPSTREAM_TZ)
    return None


def _parse_rfc822(value: str) -> datetime | None:
    """RFC 822/2822 时间 → 带时区的 UTC datetime；解不出返回 None（**行照样保留**）。

    用标准库而不是手写格式表：`parsedate_to_datetime` 覆盖 RSS 规范允许的那一长串变体
    （`GMT`/`+0800`/`EST`/省略秒），自己列格式就是在维护一份永远少一条的名单。
    无时区的按 RFC 822 的默认读成 GMT（不是北京时间）——上游省略时区时它说的是 GMT。
    """
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


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


def _row_identity(row: dict[str, Any]) -> tuple[str, bool]:
    """清单行的身份：`(external_id, 是否走了规范键兜底)`；两者都解不出时返回 `("", False)`。

    单独成一个函数而不是把标记塞进 `_map_row` 的返回 dict：
    那种做法要求调用方**记得** pop 一个混在模型字段里的键，忘了会在插入路径炸
    `TypeError`，却在**更新路径**静默通过（`_apply_update` 只遍历固定字段名）——
    半有声半无声的门不当门。现在 `_map_row` 与 `sync_source` 都问这同一个函数，
    判据只有一处，返回的 dict 永远是纯模型字段。
    """
    direct = _first_str(row, _ID_KEYS)
    if direct:
        return direct, False
    url = _first_str(row, _URL_KEYS)
    return (canonical_article_key(url), True) if url else ("", False)


def _map_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """原始清单行 → ArticleManifest 字段。

    字段口径集中于此；上游字段形状变化时只改本函数。

    S3.3.3（P-1 的消费端那一半）：**缺 id 不再丢整行**——有 URL 就用
    `canonical_article_key(url)` 兜底建键（判据在 `_row_identity`，与 `sync_source`
    的计数同一个真源）。返回 None 的只剩一种：**id 与 URL 都没有**的行——那种行
    既没有渠道身份也没有正文地址，落库等于把脏数据固化，所以它必须是 skipped 而不是 discovered。
    只有 id、没有 URL 的行仍然收（它是"见过这篇"的真实记录），但它的 `article_key` 是
    **NULL**，于是 Diff 永远不通它入列，并由 `manifest.diff.null_key_backlog` 计数出声——
    不是静默无用行。

    S4.3.1（STEP-04）：`article_key` 与 `external_id` **同时写但不同源**——前者恒为
    `canonical_article_key(url)`（跨渠道文章身份，与 `content_assets.external_id` 同一键空间），
    后者是渠道内幂等键。P-2 的根因正是拿后者去减资产（`D-V3-01`）。
    URL 为空的行给 **None 而不是 `""`**：`""` 不是合法 `ArticleKey`，且会让所有无键行
    在 Diff 里互相撞成同一个键（`D-V9-04`）。
    """
    external_id, _fallback = _row_identity(row)
    if not external_id:
        return None
    url = _first_str(row, _URL_KEYS)
    title = _first_str(row, _TITLE_KEYS)
    content_hash = _first_str(row, _HASH_KEYS) or hashlib.sha256(f"{url}|{title}".encode()).hexdigest()
    publish_time: datetime | None = None
    for k in _TIME_KEYS:
        if k in row:
            publish_time = _parse_time(row.get(k))
            break
    return {
        "external_id": external_id,
        "article_key": canonical_article_key(url) if url else None,
        "url": url,
        "title": title,
        "publish_time": publish_time,
        "content_hash": content_hash,
        "status": MANIFEST_STATUS_DISCOVERED,
    }


class ManifestSyncService:
    """清单同步编排（显式 flush，事务边界交调用方——与 SourceSubscriptionService 同口径）。"""

    def __init__(self, session: AsyncSession, provider: WorkListProvider, *, page_size: int | None = None) -> None:
        self._session = session
        self._provider = provider
        # 注入式页大小让增量游标可脱机断言；缺省取上游常量。
        self._page_size = page_size if page_size and page_size > 0 else _upstream_page_size()
        # 指标/告警的渠道维度（STEP-05）。解不出就记 unknown，绝不拿 type/URL 猜一个真渠道名。
        self._channel = str(getattr(provider, "name", "") or "") or "unknown"

    async def sync_source(self, source_id: str, biz: str, *, max_pages: int = DEFAULT_MAX_PAGES) -> ManifestSyncReport:
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
        cursor: str | None = None
        while page <= max_pages:
            try:
                rows, next_cursor, total_remote = await self._fetch_page(biz, cursor, page, size)
            except Exception:
                metrics.record_discovery_call(self._channel, ok=False)
                raise
            metrics.record_discovery_call(self._channel, ok=True)
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
            # 页内计数（STEP-05）：指标按页出，跨页累加会丢掉"哪一页整页丢光"这一维。
            page_rows = 0
            page_dropped = 0
            page_fallback = 0
            page_kept = {"discovered": 0, "updated": 0, "unchanged": 0}
            for row in rows:
                page_rows += 1
                mapped = _map_row(row)
                if mapped is None:
                    report.skipped += 1
                    page_dropped += 1
                    continue
                # S3.3.3：兜底建行要**可见**——计一次数 + 一条结构化告警。
                # 只把行收下不吭声，就还是"采集静默失败"那个形状（STEP-05 的同族）。
                # 判据与 `_map_row` 同取 `_row_identity`，两边不会各判一套。
                if _row_identity(row)[1]:
                    report.id_fallback += 1
                    page_fallback += 1
                    logger.warning(
                        "discovery.id_fallback",
                        source_id=source_id,
                        url=mapped["url"],
                        external_id=mapped["external_id"],
                    )
                outcome = await self._upsert(source_id, mapped)
                setattr(report, outcome, getattr(report, outcome) + 1)
                page_kept[outcome] += 1
                if outcome != "discovered":
                    saw_existing = True
            metrics.record_manifest_rows(
                self._channel,
                discovered=page_kept["discovered"],
                updated=page_kept["updated"],
                unchanged=page_kept["unchanged"],
                dropped=page_dropped,
                fallback=page_fallback,
            )
            if page_rows and page_dropped == page_rows:
                await self._note_all_skipped_page(report, source_id, page, page_dropped)
            if len(rows) < size:
                break  # 末页：清单已到底
            if saw_existing:
                break  # 本页已含已知行 → 未见篇前缀到此为止（缺 id 的脏行不算）
            if not next_cursor:
                break  # 上游明说没有下一页（S8.3.2 的第二个止页条件）
            cursor = next_cursor
            page += 1
        await self._session.flush()
        logger.info(
            "Manifest 同步 source=%s biz=%s calls=%d gap_planned=%d pages=%d local=%d total=%s "
            "new=%d upd=%d same=%d skip=%d id_fallback=%d",
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
            report.id_fallback,
        )
        return report

    # ------------------------------------------------------------------ 内部

    async def _fetch_page(
        self, biz: str, cursor: str | None, page: int, size: int
    ) -> tuple[list[dict[str, Any]], str | None, int | None]:
        """两端口归一：新端口（游标进游标出）优先，旧端口（页号）适配一个版本。

        旧端口为什么必须留着：`redfox/client.py` 和 STEP-03 的一批契约用例都不在本卡所有权内，
        删掉旧形状等于把别人的判据一起删。适配时"游标"就是下一页页号——对页号型渠道
        （RedFox 的 `offset = (page-1) * PAGE_SIZE`）这是它唯一的游标语义，不是替上游编一个。
        """
        paged = getattr(self._provider, "query_work_list_page", None)
        if paged is None:
            rows, total = await self._provider.query_work_list(biz, page)
            return rows, (str(page + 1) if len(rows) >= size else None), total
        got: WorkListPage = await paged(biz, cursor, page_size=size)
        # `mode="json"` 不是随手选的：默认 python 模式会把 `publish_time` 落成 **datetime 对象**，
        # 而 `_parse_time` 只认数值与字符串 ⇒ 时间整列变 None（看起来像"上游没给时间"）。
        # 走 JSON 形状后它与升级前的字符串同形，消费端一条都不用改。
        return [row.model_dump(mode="json") for row in got.rows], got.next_cursor, got.total

    async def _note_all_skipped_page(
        self, report: ManifestSyncReport, source_id: str, page: int, dropped: int
    ) -> None:
        """整页全丢弃（`skipped == rows > 0`）：P0-3 那族「上游正常而本仓零入库」的形状。

        三步都要出声：报告计数（供调用方断言）、指标（供面板）、ERROR 结构化事件 +
        一天一次的告警（供人）。少任何一步都会退回"只在日志里留一行"的旧形态。
        """
        report.all_skipped_pages += 1
        metrics.record_discovery_page_all_skipped(self._channel)
        at = datetime.now(UTC)
        key = discovery_idempotency_key(source_id, self._channel, page, at=at)
        logger.error(
            "discovery.page_all_skipped",
            source_id=source_id,
            channel=self._channel,
            at=at.isoformat(),
            idempotency_key=key,
            count=dropped,
        )
        if self._channel not in {c.value for c in ChannelName}:
            # 词表外的渠道名（provider 没登记 name）只出声不投递：告警正文要过契约视图，
            # 拿一个假渠道去投递等于把标签体系搞脏——数与 ERROR 已经落了。
            logger.warning("discovery.channel_unlabelled", source_id=source_id, channel=self._channel)
            return
        await notify_discovery_event(
            CollectionEvent(
                event="discovery.page_all_skipped",
                source_id=source_id,
                channel=ChannelName(self._channel),
                at=at,
                idempotency_key=key,
                count=dropped,
            )
        )

    async def _known_count(self, source_id: str) -> int:
        """本地已入库清单条数（增量游标基线；走 `uq_manifest_source_external` 前缀索引）。"""
        # scalar() 的静态返回类型含 None（无行/无值），而 count() 在 GROUP BY 缺席时
        # 必然返回单行数值——先收窄 None 再转 int，避免 mypy arg-type 误报。
        total = await self._session.scalar(
            select(func.count()).select_from(ArticleManifest).where(ArticleManifest.source_id == source_id)
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
        """可变字段差异更新；全等则计 unchanged（幂等第二跑应为 unchanged）。

        `article_key` 在可变集里（S4.3.1.1）：同一 `(source_id, external_id)` 行的 URL
        变了（改文、公众号换了链接形态），身份键必须跟着重算——留着旧键等于让 Diff
        拿一篇的旧身份去减资产，正是要消灭的那族错。
        **但空值不许覆盖已有值**：上游偶尔会回一条"有 id、没 URL"的行（`_map_row` 对这种行给
        `url=""` 与 `article_key=None`），照单更新会把一个合法身份与可用地址一起降级——
        该行随即从 Diff 里消失（`article_key IS NOT NULL` 挡在门外），
        变成"身份被自己抹掉"的静默丢失。宁可留着旧值（它至多指向上一篇，可被 STEP-07 审计），
        也不要制造一行永远不可入列的僵尸。同一条理由对 `title`/`publish_time` 一样成立
        （上游缺字段的行没有"把标题清空"这种正当语义），所以规则对五个可变字段统一适用，
        不挑两列特判。
        **不**跟着改 `status`：四态由入列/回写/自愈三处持有，重新发现不该把已入库的行倒回 DISCOVERED。
        """
        changed = False
        for field in ("url", "article_key", "title", "publish_time", "content_hash"):
            new = mapped.get(field)
            if not new:
                # 空值不覆盖：可变集里没有任何一列有"被清空"的正当语义
                continue
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
