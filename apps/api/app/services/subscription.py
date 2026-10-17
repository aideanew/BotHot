"""AB-P004 P2 整号订阅服务：sources/subscriptions/jobs 端点 + Manifest Diff + PARTIAL_SUCCESS 重试。

流程（冻结口径 F2）：
  1) POST /sources {biz|profile_url} → 注册公众号 Source（uq_source_type_external 幂等）
  2) POST /spaces/{id}/subscriptions {source_id, sync_policy} → 建 SourceSubscription + 首次 Job(sync_account)
  3) Job + JobItem（Manifest Diff = DISCOVERED 减已有 READY Asset）→ worker 逐篇走 P0 单篇流水线
  4) Job 终态 SUCCEEDED / PARTIAL_SUCCESS(30005 语义) / FAILED
  5) GET /jobs/{id} 轮询进度；POST /jobs/{id}/retry 对 FAILED JobItem 单篇重试

清单获取：走现有 redfox 清单源（resolver 现有能力）；
真实外部 Key 不可用时不打桩（证据：后续按 REDFOX_API_KEY 配置接入）。
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import RequestInvalidError, ResourceNotFoundError
from app.models.entities import (
    ArticleManifest,
    ContentAsset,
    Job,
    JobItem,
    KnowledgeSpace,
    ShortLinkMap,
    Source,
    SourceSubscription,
    User,
)
from app.repositories.job import JobItemRepository, JobRepository
from app.repositories.space import SpaceRepository
from app.services.article_identity import parse_wechat_url
from app.services.manifest import MANIFEST_STATUS_DISCOVERED, MANIFEST_STATUS_ENQUEUED
from app.services.state_machine import validate_transition

logger = structlog.get_logger(__name__)

# 同步策略词表（R0.2.3）：调度器只认 `next_run_at` 驱动触发，`auto` 是当前唯一有定义语义的值。
# 建订阅与改订阅共用同一白名单——此前 `sync_policy` 是无校验自由文本（只限 max_length），
# 写进去的值调度器从不读取，属契约失实（同 F-3「一份数据两个谓词」一类）。
SYNC_POLICY_ALLOWLIST = frozenset({"auto"})

# 同步间隔（分钟）上下界：下限防打爆上游清单接口，上限防退化为「永不同步」。
# 空轮询退避最高 8× 生效在**间隔**之上，故上限 4320（30 天）对应退避后 15 天，仍可接受。
SYNC_INTERVAL_MIN_MINUTES = 5
SYNC_INTERVAL_MAX_MINUTES = 4320
# 默认间隔须与 entities.SourceSubscription.sync_interval_minutes 的列默认一致。
DEFAULT_SYNC_INTERVAL_MINUTES = 360

# 固定时点锚（每天 HH 点触发）取值域；NULL = 滑动窗口（now + interval × 退避）。
SYNC_ANCHOR_HOUR_MIN = 0
SYNC_ANCHOR_HOUR_MAX = 23

# 公众号 __biz 形态：`M` 前缀 + Base64（含可选 `=` 填充）。取自 source_resolver._BIZ_RE 的
# 取值域，此处独立一份是因为校验点在服务层（注册入口），不能为了让 Service 依赖 Provider
# 而去 import `app.providers.source_resolver`（会引入 httpx 抓取链路）。
_BIZ_SHAPE_RE = re.compile(r"^M[A-Za-z0-9+/]{11,25}={0,2}$")


def _assert_subscription_settings(
    sync_policy: str | None = None,
    sync_interval_minutes: int | None = None,
    sync_anchor_hour: int | None = None,
) -> None:
    """订阅可写字段校验（建/改共用同一谓词）。违规 → 10005/422。

    `None` = 未提交该字段，不校验（PATCH 的部分更新语义）。
    """
    if sync_policy is not None and sync_policy not in SYNC_POLICY_ALLOWLIST:
        raise RequestInvalidError(
            f"同步策略取值非法：{sync_policy}（当前仅支持 {'/'.join(sorted(SYNC_POLICY_ALLOWLIST))}）"
        )
    if sync_interval_minutes is not None and not (
        SYNC_INTERVAL_MIN_MINUTES <= int(sync_interval_minutes) <= SYNC_INTERVAL_MAX_MINUTES
    ):
        raise RequestInvalidError(
            f"同步间隔取值非法：{sync_interval_minutes}（须在 "
            f"{SYNC_INTERVAL_MIN_MINUTES}~{SYNC_INTERVAL_MAX_MINUTES} 分钟之间）"
        )
    # 判 `not in`（整数域内必然真）而非 `!=`：`True is 1` 会让 `sync_anchor_hour: true`
    # 这类 JSON 布尔值绕过范围校验（与 `0 in (0, 1)` 为真同源的 int/bool 混用陷阱）。
    if sync_anchor_hour is not None and not (SYNC_ANCHOR_HOUR_MIN <= int(sync_anchor_hour) <= SYNC_ANCHOR_HOUR_MAX):
        raise RequestInvalidError(
            f"固定同步时点取值非法：{sync_anchor_hour}（须在 {SYNC_ANCHOR_HOUR_MIN}~"
            f"{SYNC_ANCHOR_HOUR_MAX} 之间，表示每天该小时触发；不设置 = 按间隔滑动）"
        )


class SourceSubscriptionService:
    """P2 整号订阅编排层（显式 commit，repo 只 flush）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._job_repo = JobRepository(session)
        self._item_repo = JobItemRepository(session)
        self._space_repo = SpaceRepository(session)

    # ------------------------------------------------------------------ sources

    async def register_source(
        self, user_id: str, biz: str = "", profile_url: str = "", name: str = ""
    ) -> dict[str, Any]:
        """POST /sources：注册公众号 Source（biz 或 profile_url 二选一；uq_source_type_external 幂等）。

        biz 必须通过形态校验：RedFox 广域库仅接受 `__biz` 定位，落一个形态非法的 biz 等于
        注册一个永不可采的源（此前无任何校验，前端误贴红狐文档链接也照单全收）。
        """
        external_id = biz or self._biz_from_profile_url(profile_url)
        if not external_id:
            raise RequestInvalidError("biz 或 profile_url 至少提供一个")
        if not _BIZ_SHAPE_RE.match(external_id):
            raise RequestInvalidError(
                "biz 形态非法：须为 M 开头的 Base64 公众号 __biz（如 MzA5NDQ2MjkzOQ==）。"
                "redfox.hk/apis/... 是文档链接、mp.weixin.qq.com/s/... 是文章短链，"
                "二者都不是账号标识"
            )
        row = (
            await self._session.execute(
                select(Source).where(Source.type == "wechat_oa", Source.external_id == external_id)
            )
        ).scalar_one_or_none()
        if row is None:
            source = Source(
                type="wechat_oa",
                external_id=external_id,
                name=name or external_id,
                # 不拼默认 url：`redfox.hk/apis/gongzhonghao/{biz}` 不是真实可访问地址
                # （该路径只接受文档 interfaceNo），填一个假地址比留空更具误导性。
                url=profile_url or "",
            )
            self._session.add(source)
            await self._session.flush()
            row = source
        await self._session.commit()
        return {"sourceId": row.id, "biz": row.external_id, "name": row.name, "url": row.url}

    async def list_sources(
        self, source_type: str = "wechat_oa", *, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        """GET /sources?type=wechat_oa → **全用户共享**的源清单（不是「我的信息源」）。

        不带 user_id 参数：`sources` 表**没有 user_id 列**（`uq_source_type_external` 按
        type+external_id 全局去重），「我的信息源」无定义。旧签名收了 user_id 却从不过滤，
        是死参数 + 契约误导（F-23）——参数已移除，登录闸门由路由依赖承担。
        视图只暴露公开标识（biz/name/url/status），无用户可识别信息，故全局可见不构成越界。
        C.1：SQL 层 LIMIT/OFFSET，返回 (items, total)。
        """
        rows = (
            await self._session.scalars(
                select(Source)
                .where(Source.type == source_type)
                .order_by(Source.created_at, Source.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
        total = int(
            (await self._session.scalar(select(func.count()).select_from(Source).where(Source.type == source_type)))
            or 0
        )
        return [
            {"sourceId": r.id, "biz": r.external_id, "name": r.name, "url": r.url, "status": r.status} for r in rows
        ], total

    async def update_source(self, source_id: str, *, name: str | None = None, url: str | None = None) -> dict[str, Any]:
        """PATCH /sources/{id}：admin 改全局源的展示名 / 上游地址（部分更新）。

        无归属校验：`sources` 无 user_id 列，授权收口在路由层 require_roles("admin")
        （与 DELETE /sources/{id} 同口径）。**不改 type / external_id**——那是
        `uq_source_type_external` 去重锚，改了等于删后重建（并打断 CASCADE 引用链）。
        """
        source = await self._session.get(Source, source_id)
        if source is None:
            raise ResourceNotFoundError(source_id)
        if name is not None:
            source.name = name
        if url is not None:
            source.url = url
        await self._session.commit()
        return {"sourceId": source.id, "biz": source.external_id, "name": source.name, "url": source.url}

    # ------------------------------------------------------------------ subscriptions

    async def subscribe(
        self,
        user_id: str,
        space_id: str,
        source_id: str,
        sync_policy: str = "auto",
        sync_anchor_hour: int | None = None,
    ) -> dict[str, Any]:
        """POST /spaces/{id}/subscriptions：建订阅 + 首次 Job(sync_account)。

        幂等：uq_sub_user_source_space 冲突 → 返回既有订阅（不报错）。
        锚点：未显式传 `sync_anchor_hour` 时套用 `default_sync_anchor_hour`（可配，
        置 None 关闭），使新建订阅默认就是「每天固定时点一次」而非每 6 小时滑动。
        返回 {subscriptionId, jobIds, progress}。
        """
        _assert_subscription_settings(sync_policy=sync_policy, sync_anchor_hour=sync_anchor_hour)
        space = await self._space_repo.get_by_id(space_id)
        if space is None or space.user_id != user_id:
            raise ResourceNotFoundError(space_id)

        source = await self._session.get(Source, source_id)
        if source is None:
            raise ResourceNotFoundError(source_id)

        # 幂等订阅
        existing_sub = (
            await self._session.execute(
                select(SourceSubscription).where(
                    SourceSubscription.user_id == user_id,
                    SourceSubscription.source_id == source_id,
                    SourceSubscription.space_id == space_id,
                )
            )
        ).scalar_one_or_none()
        if existing_sub is not None:
            return {"subscriptionId": existing_sub.id, "jobIds": [], "created": False}

        anchor = self._effective_anchor(sync_anchor_hour)
        sub = SourceSubscription(
            user_id=user_id,
            source_id=source_id,
            space_id=space_id,
            sync_policy=sync_policy,
            sync_anchor_hour=anchor,
            next_run_at=self._next_anchored_run(anchor),
        )
        self._session.add(sub)
        await self._session.flush()

        # 首次 Job（Manifest Diff 初始全量）
        job = await self._create_sync_job(user_id, space_id, source_id, sub.id)
        await self._session.commit()
        return {"subscriptionId": sub.id, "jobIds": [job.id], "created": True}

    async def list_subscriptions(
        self, user_id: str, space_id: str, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        """GET /spaces/{id}/subscriptions（T1.4.3/T1.4.4 N11 呈现字段已并入）。

        每条订阅补三字段（数据列已在库、本卡只接线）：
        - discoveredCount：该源 DISCOVERED 清单计数 = U6"预计篇数"（ArticleManifest 权威）；
        - lastSuccessAt / consecutiveEmptySyncs：U7"自动同步可见性"（worker 未建前为
          空串/0，属诚实缺口呈现，不造假数据）。
        C.1：SQL 层 LIMIT/OFFSET，返回 (items, total)。
        """
        return await self._list_subscriptions(space_id, owner=user_id, limit=limit, offset=offset)

    async def list_subscriptions_any(
        self, space_id: str | None = None, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        """R4.8（A-2 叠加）：admin 跨用户订阅清单——不做归属校验。

        space_id=None → 全系统所有空间的订阅（admin 排查「为什么这条号没人同步」
        需要跨空间视图；既有端点强制本人空间，无法表达）。角色校验留在路由层。
        C.1：SQL 层 LIMIT/OFFSET，返回 (items, total)。
        """
        return await self._list_subscriptions(space_id, owner=None, limit=limit, offset=offset)

    async def _list_subscriptions(
        self, space_id: str | None, *, owner: str | None, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        """订阅清单单一实现。owner=None 表示无归属约束（/admin 跨用户路径）。

        owner 非 None 时先校验 space.user_id == owner（越权/无效空间 → 30004，不泄露存在性）；
        owner 为 None 时仍校验空间存在（space_id=None 表示不过滤，跳过该校验）。
        C.1：SQL 层 LIMIT/OFFSET，返回 (items, total)。
        C.6 审计：循环内 `session.get(Source, ...)` 与 per-row latest_job 查询为 N+1，
        已记入 N+1 审计表交 W10。
        """
        if space_id is not None:
            space = await self._space_repo.get_by_id(space_id)
            if space is None or (owner is not None and space.user_id != owner):
                raise ResourceNotFoundError(space_id)

        stmt = select(SourceSubscription).order_by(SourceSubscription.created_at, SourceSubscription.id)
        if space_id is not None:
            stmt = stmt.where(SourceSubscription.space_id == space_id)
        if owner is not None:
            stmt = stmt.where(SourceSubscription.user_id == owner)
        rows = (await self._session.scalars(stmt.limit(limit).offset(offset))).all()
        count_stmt = select(func.count()).select_from(SourceSubscription)
        if space_id is not None:
            count_stmt = count_stmt.where(SourceSubscription.space_id == space_id)
        if owner is not None:
            count_stmt = count_stmt.where(SourceSubscription.user_id == owner)
        total = int((await self._session.scalar(count_stmt)) or 0)
        # 归属呈现仅 admin 路径附加：本人清单里 spaceId/ownerId 恒等于调用方，纯噪声，
        # 且「admin 视图的 owner 字段是增量、靠独立端点承载」是 M3 批次 2 已确立的口径
        # （本人端点形状不变，跨用户读另走 /admin）。批量取一次，逐条 get 会是 N+1
        # （与 spaces 域 T1.5.3 修过的同类缺陷）。
        owners: dict[str, str] = {}
        spaces: dict[str, str] = {}
        if rows and owner is None:
            owners = {
                u.id: u.nickname
                for u in (await self._session.scalars(select(User).where(User.id.in_({r.user_id for r in rows})))).all()
            }
            spaces = {
                s.id: s.name
                for s in (
                    await self._session.scalars(
                        select(KnowledgeSpace).where(KnowledgeSpace.id.in_({r.space_id for r in rows}))
                    )
                ).all()
            }
        out = []
        for r in rows:
            src = await self._session.get(Source, r.source_id)
            # 该订阅最近一次 sync_account Job（幂等键前缀匹配）
            # 前缀匹配：既有首同步键 `sync_account:{sub}` 与 T2.4 增量键
            # `sync_account:{sub}:{run_token}` 同被覆盖，取最近一次
            # 归属取 r.user_id 而非 owner：owner=None（admin 路径）时订阅可能属于
            # 任意用户，用调用方身份会把他人的最新 Job 静默过滤掉（latestJobId 恒空）。
            latest_job = (
                (
                    await self._session.execute(
                        select(Job)
                        .where(
                            Job.user_id == r.user_id,
                            Job.type == "sync_account",
                            Job.idempotency_key.like(f"sync_account:{r.id}%"),
                        )
                        .order_by(Job.created_at.desc())
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
            discovered = await self._session.scalar(
                select(func.count())
                .select_from(ArticleManifest)
                .where(
                    ArticleManifest.source_id == r.source_id,
                    ArticleManifest.status == "DISCOVERED",
                )
            )
            view: dict[str, Any] = {
                "subscriptionId": r.id,
                "sourceId": r.source_id,
                "biz": src.external_id if src else "",
                "sourceName": src.name if src else "",
                "syncPolicy": r.sync_policy,
                "syncIntervalMinutes": r.sync_interval_minutes,
                "syncAnchorHour": r.sync_anchor_hour,
                "nextRunAt": r.next_run_at.isoformat() if r.next_run_at else "",
                "lastSuccessAt": r.last_success_at.isoformat() if r.last_success_at else "",
                "consecutiveEmptySyncs": r.consecutive_empty_syncs,
                "discoveredCount": int(discovered or 0),
                "status": r.status,
                "latestJobId": latest_job.id if latest_job else "",
            }
            if owner is None:
                view.update(
                    {
                        "spaceId": r.space_id,
                        "spaceName": spaces.get(r.space_id, ""),
                        "ownerId": r.user_id,
                        "ownerNickname": owners.get(r.user_id, ""),
                    }
                )
            out.append(view)
        return out, total

    # ------------------------------------------------------------------ R0.2.3 订阅生命周期

    async def update_subscription(
        self,
        user_id: str,
        space_id: str,
        subscription_id: str,
        *,
        sync_policy: str | None = None,
        sync_interval_minutes: int | None = None,
        sync_anchor_hour: int | None = None,
        clear_anchor: bool = False,
    ) -> dict[str, Any]:
        """PATCH /spaces/{id}/subscriptions/{sub_id}：改同步策略 / 间隔 / 固定时点锚（部分更新）。

        语义（四处已知，前端须知）：
        - `sync_interval_minutes` 只可能把 `next_run_at` **往前**拉（更频繁），绝不把
          已逾期的一次同步往后推——否则用户「想同步得更勤」反而跳过了到期同步；
        - `sync_anchor_hour` 非空 = 每天该小时触发（调度器时区口径）；改锚后 `next_run_at`
          对准下一次该整点——这是「改到点触发」的既有契约，不适用上面「只往前拉」的原则；
        - `clear_anchor=True`（请求体里**显式传 null**）= 撤销锚定、回到滑动窗口，
          `next_run_at` 以当前时刻为基准按间隔重排；
        - `status != "ACTIVE"`（已退订）的订阅允许改值但**不再重排** `next_run_at`；
        - 各字段取值校验在 `_assert_subscription_settings`（与建订阅同一谓词）。

        为何需要 `clear_anchor` 这个独立参数：pydantic 的 `int | None = None` 分不清
        「字段省略」与「显式传 null」，两者都落成 None——若只靠 `sync_anchor_hour`，
        用户设过一次锚点就永远回不到滑动窗口。路由层用 `model_fields_set` 判定后传入。
        """
        _assert_subscription_settings(
            sync_policy=sync_policy,
            sync_interval_minutes=sync_interval_minutes,
            sync_anchor_hour=sync_anchor_hour,
        )
        sub = await self._get_owned_subscription(user_id, space_id, subscription_id)
        if sync_policy is not None:
            sub.sync_policy = sync_policy
        if sync_interval_minutes is not None:
            sub.sync_interval_minutes = int(sync_interval_minutes)
        if clear_anchor:
            sub.sync_anchor_hour = None
        elif sync_anchor_hour is not None:
            sub.sync_anchor_hour = int(sync_anchor_hour)
        if sub.status == "ACTIVE":
            if sync_anchor_hour is not None:
                sub.next_run_at = self._next_anchored_run(int(sync_anchor_hour))
            elif clear_anchor:
                interval = int(sub.sync_interval_minutes or DEFAULT_SYNC_INTERVAL_MINUTES)
                sub.next_run_at = datetime.now(UTC) + timedelta(minutes=interval)
            elif sub.sync_anchor_hour is None:
                # 仅滑动窗口订阅遵守「只往前拉」；已锚定的订阅不在此分支（锚值未变 = 不动水位）
                if sync_interval_minutes is not None:
                    due = datetime.now(UTC) + timedelta(minutes=int(sync_interval_minutes))
                    if sub.next_run_at is None or due < sub.next_run_at:
                        sub.next_run_at = due
                else:
                    sub.next_run_at = datetime.now(UTC)
        await self._session.commit()
        return self._subscription_view(sub)

    async def cancel_subscription(
        self,
        user_id: str,
        space_id: str,
        subscription_id: str,
    ) -> dict[str, Any]:
        """DELETE /spaces/{id}/subscriptions/{sub_id}：退订（软取消，幂等）。

        只做两件事：`status=CANCELLED` + `next_run_at=None`。
        `claim_due` 要求 `status=ACTIVE AND next_run_at IS NOT NULL`，双保险后调度器永不再认领。

        **不删除任何文档/资产/清单**——退订是「停止未来同步」，不是「清空已入库内容」
        （已入库内容的删除走 R0.2.1 单篇 / R0.2.5 批量，语义不同）。
        幂等：已退订 → 200 且 `cancelled=False`（不报错）。
        """
        sub = await self._get_owned_subscription(user_id, space_id, subscription_id)
        was_active = sub.status != "CANCELLED"
        sub.status = "CANCELLED"
        sub.next_run_at = None
        await self._session.commit()
        view = self._subscription_view(sub)
        view["cancelled"] = was_active
        return view

    async def delete_source(self, source_id: str) -> dict[str, Any]:
        """DELETE /sources/{source_id}：删除信息源，**仅当零下游引用**。

        闸门为何是「订阅 + 资产 + 清单」三者而不仅是大纲所写的「订阅」：
        `sources.id` 的三张子表（source_subscriptions / article_manifests /
        content_assets）**全是 `ondelete=CASCADE`**，而 `content_assets.id` 又被
        `knowledge_documents.asset_id` CASCADE 引用——只挡订阅会级联删掉资产，
        进而**级联删掉知识空间的文档行**，且 `list_docs` 的 Source inner join
        会让整篇文档从清单里静默消失。故闸门必须覆盖整条级联链。

        无归属校验（登录即可）：`sources` 表**没有 user_id 列**——信息源是全用户共享
        的全局资源（`uq_source_type_external` 全局唯一）。零引用闸门保证不伤他人数据，
        但仍属全局操作，前端提示文案不应暗示「我的」。
        """
        source = await self._session.get(Source, source_id)
        if source is None:
            raise ResourceNotFoundError(source_id)
        counts = await self._source_reference_counts(source_id)
        if any(counts.values()):
            raise RequestInvalidError(
                f"信息源仍被引用（订阅 {counts['subscriptions']} / 资产 {counts['assets']} / "
                f"清单 {counts['manifests']}），无法删除——请先退订并清理对应空间文档"
            )
        await self._session.execute(delete(Source).where(Source.id == source_id))
        await self._session.commit()
        return {"sourceId": source_id, "deleted": True, "references": counts}

    async def _source_reference_counts(self, source_id: str) -> dict[str, int]:
        """三张子表的引用计数（单表 count，源表体量小）。"""
        out: dict[str, int] = {}
        for key, model in (
            ("subscriptions", SourceSubscription),
            ("assets", ContentAsset),
            ("manifests", ArticleManifest),
        ):
            n = await self._session.scalar(select(func.count()).select_from(model).where(model.source_id == source_id))
            out[key] = int(n or 0)
        return out

    async def _get_owned_subscription(self, user_id: str, space_id: str, subscription_id: str) -> SourceSubscription:
        """订阅归属校验：空间须属本人且订阅须同属本人与该空间（不泄露存在性）。"""
        space = await self._space_repo.get_by_id(space_id)
        if space is None or space.user_id != user_id:
            raise ResourceNotFoundError(space_id)
        sub = await self._session.get(SourceSubscription, subscription_id)
        if sub is None or sub.user_id != user_id or sub.space_id != space_id:
            raise ResourceNotFoundError(subscription_id)
        return sub

    @staticmethod
    def _effective_anchor(sync_anchor_hour: int | None) -> int | None:
        """新建订阅的锚点：调用方未指定时套用配置项 `default_sync_anchor_hour`。

        不套用则 `None` = 每 360 分钟滑动窗口（一天 4 次）；每天固定时点的需求要的是
        锚定（恒一天一次），故默认自动锚定而非默认滑动。仅作用于**新建**：幂等命中既有
        订阅与 PATCH 都不走本方法——后者 `None` 语义是「未提交该字段」，套用默认值会
        把用户刻意选定的滑动口径改写成锚定。

        配置项是外部输入（env），越界值在此拦截并回落滑动口径：若不拦，`replace(hour=99)`
        会让整条建订阅请求 500，为一个错误配置值牺牲主流程不值得。
        """
        if sync_anchor_hour is not None:
            return sync_anchor_hour
        configured = get_settings().default_sync_anchor_hour
        if configured is None or not (SYNC_ANCHOR_HOUR_MIN <= int(configured) <= SYNC_ANCHOR_HOUR_MAX):
            return None
        return int(configured)

    @staticmethod
    def _next_anchored_run(anchor_hour: int | None) -> datetime:
        """锚定订阅的首个触发点 = 调度器时区里下一次 `anchor_hour:00`；非锚定 = 立即（历史行为）。

        写在这里而非复用 `IncrementalScheduler._anchor_base`：调度器持有一整个 session
        工厂，而本服务只有一条业务 session，为了一个整点计算把工厂拖进来不划算。
        两处口径**必须保持一致**（都按 `scheduler_timezone`、都严格取下一次整点）。
        """
        if anchor_hour is None:
            return datetime.now(UTC)
        zone_name = str(get_settings().scheduler_timezone)
        tz: tzinfo
        try:
            tz = ZoneInfo(zone_name)
        except Exception:  # noqa: BLE001 与调度器同款兜底：时区数据缺失不回退成建单失败
            tz = UTC
        now = datetime.now(UTC).astimezone(tz)
        candidate = now.replace(hour=int(anchor_hour), minute=0, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    @staticmethod
    def _subscription_view(sub: SourceSubscription) -> dict[str, Any]:
        """订阅视图（camelCase，与 list_subscriptions 同口径 + 补 syncIntervalMinutes）。"""
        return {
            "subscriptionId": sub.id,
            "syncPolicy": sub.sync_policy,
            "syncIntervalMinutes": sub.sync_interval_minutes,
            "syncAnchorHour": sub.sync_anchor_hour,
            "nextRunAt": sub.next_run_at.isoformat() if sub.next_run_at else "",
            "status": sub.status,
        }

    # ------------------------------------------------------------------ R7.4 Admin 操作性补全

    async def cancel_subscription_any(self, subscription_id: str) -> dict[str, Any]:
        """R7.4.3：admin 跨用户退订——不做归属校验。

        与 cancel_subscription 的差异仅在归属：本方法直接按 id 取订阅，不检查 user_id/space_id。
        退订语义不变：status=CANCELLED + next_run_at=None，不删除文档/资产/清单。
        幂等：已退订 → cancelled=False。
        """
        sub = await self._session.get(SourceSubscription, subscription_id)
        if sub is None:
            raise ResourceNotFoundError(subscription_id)
        was_active = sub.status != "CANCELLED"
        sub.status = "CANCELLED"
        sub.next_run_at = None
        await self._session.commit()
        view = self._subscription_view(sub)
        view["cancelled"] = was_active
        return view

    async def retry_job_any(self, job_id: str) -> dict[str, Any]:
        """R7.4.2：admin 跨用户重试终态 Job——不做归属校验。

        对 FAILED/CANCELLED/PARTIAL_SUCCESS 的 Job，重置其 FAILED JobItem 为 PENDING
        并将 Job 回到 QUEUED（与用户侧 retry_job 同语义，仅绕过归属校验）。
        QUEUED → 无需重试；RUNNING → 不中断。
        """
        job = await self._job_repo.get_by_id(job_id)
        if job is None:
            raise ResourceNotFoundError(job_id)
        if job.status == "QUEUED":
            return {"oldJobId": job_id, "newJobId": job_id, "type": job.type, "note": "QUEUED 无需重试"}
        if job.status == "RUNNING":
            raise RequestInvalidError("任务执行中，无法重试")
        if job.status not in ("FAILED", "CANCELLED", "PARTIAL_SUCCESS"):
            raise RequestInvalidError(f"任务状态 {job.status} 不支持重试")
        failed = await self._item_repo.list_failed(job_id)
        for item in failed:
            await self._item_repo.set_status(item.id, "PENDING", "")
            await self._item_repo.bump_retry(item.id)
        if failed:
            await self._job_repo.set_status(job.id, "QUEUED", "retried: admin 重试")
        await self._session.commit()
        return {
            "oldJobId": job_id,
            "newJobId": job_id,
            "type": job.type,
            "retried": len(failed),
            "status": "QUEUED" if failed else job.status,
        }

    async def list_sources_with_counts(
        self, source_type: str | None = None, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        """R7.4.4：admin 信息源清单（含引用计数）。

        增量于 list_sources：每条源带 subscriptionCount / assetCount / manifestCount，
        供 admin 决策删除安全性。type 过滤可选（默认不过滤）。
        C.1：SQL 层 LIMIT/OFFSET，返回 (items, total)。
        C.6 审计：循环内 `_source_reference_counts(r.id)` 为 per-source 查询（N+1），
        大集合下应批量聚合——已记入 N+1 审计表交 W10。
        """
        stmt = select(Source)
        if source_type:
            stmt = stmt.where(Source.type == source_type)
        rows = (
            await self._session.scalars(stmt.order_by(Source.created_at, Source.id).limit(limit).offset(offset))
        ).all()
        count_stmt = select(func.count()).select_from(Source)
        if source_type:
            count_stmt = count_stmt.where(Source.type == source_type)
        total = int((await self._session.scalar(count_stmt)) or 0)
        items: list[dict[str, Any]] = []
        for r in rows:
            counts = await self._source_reference_counts(r.id)
            items.append(
                {
                    "sourceId": r.id,
                    "type": r.type,
                    "biz": r.external_id,
                    "name": r.name,
                    "url": r.url,
                    "status": r.status,
                    "subscriptionCount": counts["subscriptions"],
                    "assetCount": counts["assets"],
                    "manifestCount": counts["manifests"],
                }
            )
        return items, total

    # ------------------------------------------------------------------ jobs

    async def get_job_view(self, user_id: str, job_id: str) -> dict[str, Any]:
        """GET /jobs/{id}：Job 状态 + JobItem 进度（轮询用）。"""
        return await self._job_view(job_id, owner=user_id)

    async def get_job_view_any(self, job_id: str) -> dict[str, Any]:
        """R4.8（A-2 叠加）：admin 跨用户查 Job 详情——不做归属校验。

        跨用户排障「这条号为什么卡住」需要 JobItem 级 counts 与 error 文本，
        既有端点只给本人（他人 job 一律 30004，无法区分不存在与无权）。
        授权在路由层（require_roles("admin")）。
        """
        return await self._job_view(job_id, owner=None)

    async def _job_view(self, job_id: str, *, owner: str | None) -> dict[str, Any]:
        """Job 详情单一实现。owner=None 表示无归属约束（/admin 跨用户路径）。"""
        job = await self._job_repo.get_by_id(job_id)
        if job is None or (owner is not None and job.user_id != owner):
            raise ResourceNotFoundError(job_id)
        counts = await self._item_repo.counts(job_id)
        failed = await self._item_repo.list_failed(job_id)
        return {
            "jobId": job.id,
            "type": job.type,
            "status": job.status,
            "progress": job.progress,
            "error": job.error,
            "counts": counts,
            # 失败篇目明细：只有 job 级一行 error 时，用户看不出「哪几篇失败、
            # 为什么失败」，也就无从判断该不该重试——任务中心的排障承诺需要篇级。
            # 端点为按需钻取的详情路径，不在 worker 的收敛热路径上，多一次索引查询可接受。
            "failedItems": [
                {
                    "itemId": it.id,
                    "url": it.url,
                    "error": it.error,
                    "retryCount": it.retry_count,
                }
                for it in failed
            ],
            "createdAt": job.created_at.isoformat() if job.created_at else "",
        }

    async def retry_job(self, user_id: str, job_id: str) -> dict[str, Any]:
        """POST /jobs/{id}/retry：对 PARTIAL_SUCCESS/FAILED Job 的 FAILED JobItem 单篇重试。

        幂等：全 SUCCEEDED → {retried:0}；有 FAILED → 重置为 PENDING + retry_count+1，Job 回 QUEUED。

        重试语义是「重新入队」而非「正在执行」：worker 的 `claim_next_queued` 只认领
        QUEUED（`WHERE status == 'QUEUED'`），置 RUNNING 会让该 Job 对 worker 隐形，
        直到 `job_worker_stale_seconds`（默认 300s）后由自愈巡检回退——每次重试白等 5 分钟。
        """
        job = await self._job_repo.get_by_id(job_id)
        if job is None or job.user_id != user_id:
            raise ResourceNotFoundError(job_id)
        if job.status == "QUEUED":
            return {"jobId": job_id, "retried": 0, "note": "QUEUED 无需重试"}

        failed = await self._item_repo.list_failed(job_id)
        for item in failed:
            await self._item_repo.set_status(item.id, "PENDING", "")
            await self._item_repo.bump_retry(item.id)

        if failed:
            await self._job_repo.set_status(job.id, "QUEUED", "")
        await self._session.commit()
        return {"jobId": job_id, "retried": len(failed), "status": "QUEUED" if failed else job.status}

    @staticmethod
    def _biz_from_profile_url(profile_url: str) -> str:
        """profile_url → biz 锚：只认查询参数 `biz` / `__biz`。

        不再取路径末段——那会把两类非 biz 的值误认成 biz 并落成永不可采的源：
        ① `redfox.hk/apis/gongzhonghao/{interfaceNo}` 是红狐**文档深链**（如 `5Y84NI1D`），
           `interfaceNo` 是接口编号而非账号标识；
        ② `mp.weixin.qq.com/s/{随机串}` 的文章短链不含 biz（须抓 HTML 解析，属
           `source_resolver.parse_biz` 的职责，不是 URL 解析能解决的）。
        """
        from urllib.parse import parse_qs, urlparse

        if not profile_url:
            return ""
        u = urlparse(profile_url)
        if u.netloc.endswith("redfox.hk") and u.path.startswith("/apis/"):
            return ""
        qs = parse_qs(u.query)
        for key in ("biz", "__biz"):
            if qs.get(key):
                return qs[key][0]
        return ""

    # ------------------------------------------------------------------ 内部

    async def _create_sync_job(
        self,
        user_id: str,
        space_id: str,
        source_id: str,
        subscription_id: str,
        *,
        run_token: str | None = None,
        manifests: list[ArticleManifest] | None = None,
    ) -> Job:
        """建 Job(sync_account) + JobItem（Manifest Diff：DISCOVERED 减已有 READY Asset）。

        幂等键：首同步 = `sync_account:{订阅}`（同订阅重复触发不建双 Job，订阅端点依赖此
        语义）；增量轮 = `sync_account:{订阅}:{run_token}`（T2.4 调度器注入，跨轮次各不相同）。

        清单获取：走现有 redfox 清单源。Manifest Diff 以 ArticleManifest 表为权威，
        真实外部 Key 需 REDFOX_API_KEY 环境变量；未配置时不打桩，留空由前端/工作流
        层按业务规则兜底，证据中标注不冒充真实抓取。
        """

        payload = json.dumps(
            {"source_id": source_id, "space_id": space_id, "subscription_id": subscription_id},
            ensure_ascii=False,
        )
        idem_key = f"sync_account:{subscription_id}"
        if run_token:
            idem_key = f"{idem_key}:{run_token}"
        _TERMINAL = ("SUCCEEDED", "PARTIAL_SUCCESS", "FAILED", "CANCELLED")
        _REQUEUE = ("FAILED", "CANCELLED")
        job, created = await self._job_repo.create_or_get(
            type="sync_account",
            user_id=user_id,
            payload=payload,
            idempotency_key=idem_key,
        )
        if not created:
            # 首同步 Job 终结后永久卡死修复（R6.3.2）：
            # 旧逻辑「not created → 直接返回」不看 Job 状态，导致首次 Job 失败/取消后
            # 同订阅永远无法自动同步。修复：仅 FAILED/CANCELLED 重新入队；SUCCEEDED 保持终态。
            if job.status not in _TERMINAL:
                return job  # 在途（QUEUED/RUNNING），复用，零重复入队
            if job.status in _REQUEUE:
                # 失败/取消：复位为 QUEUED + 重新填充（幂等键不变，同一订阅仍是同一 Job 行）
                await self._job_repo.set_status(job.id, "QUEUED")
                await self._populate_job_items(job.id, source_id, subscription_id, manifests=manifests)
                await self._session.flush()
            return job
        await self._job_repo.set_status(job.id, "QUEUED")
        # Manifest Diff → JobItem（初始全量 DISCOVERED；真实清单源不可用时不打桩，后续按 REDFOX_API_KEY 配置接入）
        await self._populate_job_items(job.id, source_id, subscription_id, manifests=manifests)
        await self._session.flush()
        return job

    def _active_sync_job_ids(self, subscription_id: str) -> Select:
        """本订阅**仍在途**（QUEUED/RUNNING）的 `sync_account` Job id 子查询。

        Diff 的在途面与短链收敛面共用它：两处必须认同一个"什么算在途"。
        """
        return select(Job.id).where(
            Job.type == "sync_account",
            Job.idempotency_key.like(f"sync_account:{subscription_id}%"),
            Job.status.in_(("QUEUED", "RUNNING")),
        )

    async def _with_effective_keys(
        self, source_id: str, subscription_id: str, rows: list[ArticleManifest]
    ) -> list[tuple[ArticleManifest, str]]:
        """给每条候选行定出**跨形态收敛用的键**，并剔掉该键已入库/已在途的形态。

        为什么需要这一步：`article_key` 存的是 `canonical_article_key(url)`，同一篇文章的短链
        给 `s:<token>`、长链给 `b:<biz>:<mid>:<idx>`（`article_identity.py:162-170` 的两条分支），
        **两支天生不相等**——只在 Diff 里按键减的话 S4.1.2 要的"同篇两形态只入列一次"不成立，
        短链那一支还永远减不到 READY 资产（资产锚的是长链键）。

        并键的唯一既有真源是 `short_link_maps`：`kb.py:_save_short_link` 在短链**首抓**拿到长链后
        写入 `短链 token → 长链规范键`。本函数只读它，不自己再算一份键（键的算法定位在
        `canonical_article_key`，这是 S2.3.3 漂移守卫要保住的那条单一来源）。

        局限（一次性，不是每轮）：短链 token 还没有映射行 = 这篇还没被真实抓过，此时两种形态
        本轮各排一次队；抓取落地时映射就位，之后的轮次就收敛了。这与 D-V9-01 登记的
        "存量首次再入库各多一次抓取"是同一族代价。
        """
        # token 一律由 `parse_wechat_url` 给：它在 `/s/` 之前已经过 `host == WECHAT_HOST` 这道闸
        # （`article_identity.py:82`），与 `canonical_article_key` 采纳 `s:` 支的条件是**同一个条件**。
        # 在这里自己判 host/末段会造出第二个口径——`kb.py:_is_short_link` 那种子串判定就是前车之鉴
        # （已发布为 P-20）。非微信 host 的 `/s/x` 到这里一律空串 ⇒ 不查表、不并键、不误判已入库。
        def token_of(url: str | None) -> str:
            return parse_wechat_url(url).short_token if url else ""

        # 在途面必须按**解析后的键**减。`@ci` 真库实测到的那条红就是这里：入列的那一支完全可能
        # 是短链行，它 `article_key` 存的是 `s:` 一支，只拿候选行解析出来的长链键去查
        # `ArticleManifest.article_key IN (长链键)` 永远命中不了它 ⇒ 同一篇的长链形态在下一轮
        # 绕过在途保护再排一次队。所以把在途的那些清单行**也**做一次同样的解析。
        inflight = (
            await self._session.execute(
                select(ArticleManifest.id, ArticleManifest.article_key, ArticleManifest.url)
                .join(JobItem, JobItem.manifest_id == ArticleManifest.id)
                .where(JobItem.job_id.in_(self._active_sync_job_ids(subscription_id)))
            )
        ).all()
        wanted = sorted(
            {t for t in (token_of(row.url) for row in rows) if t}
            | {t for t in (token_of(url) for (_i, _k, url) in inflight) if t}
        )
        if not wanted:
            return [(row, str(row.article_key)) for row in rows]
        mapped: dict[str, str] = {
            short_key: long_key
            for short_key, long_key in (
                await self._session.execute(
                    select(ShortLinkMap.short_key, ShortLinkMap.article_key).where(
                        ShortLinkMap.short_key.in_(wanted)
                    )
                )
            ).all()
        }

        def effective_key(stored: str | None, url: str | None) -> str:
            """这一行在收敛坐标上的身份：有短链映射就用它指向的长链键，否则用存量键。"""
            return mapped.get(token_of(url)) or str(stored)

        pairs = [(row, effective_key(row.article_key, row.url)) for row in rows]
        # 在途行的坐标集合；`if stored` 那一路是 NULL 守卫的另一半——没有键的行不该参与并键
        inflight_keys = {
            effective_key(stored, url) for (_iid, stored, url) in inflight if stored
        }
        out: list[tuple[ArticleManifest, str]] = []
        # 只对"解析后换了键"的那些行去补查 READY 资产：存量键那一支 SQL 层已经减过了，
        # 重复查只会多要一次往返。
        probe_vals = sorted({key for row, key in pairs if str(row.article_key) != key})
        ready_hit: set[str] = set()
        if probe_vals:
            ready_hit = set(
                (
                    await self._session.scalars(
                        select(ContentAsset.external_id).where(
                            ContentAsset.source_id == source_id,
                            ContentAsset.status == "READY",
                            ContentAsset.external_id.in_(probe_vals),
                        )
                    )
                ).all()
            )
        for row, key in pairs:
            if key in ready_hit or key in inflight_keys:
                continue
            out.append((row, key))
        return out

    async def _compute_new_manifests(self, source_id: str, subscription_id: str) -> list[ArticleManifest]:
        """Manifest Diff（T2.4 / STEP-04 S4.4.1）：本订阅**尚未入列且未入库**的 DISCOVERED 清单行。

        差量口径（D-V3-01 改键，承 1.2 冻结「Diff 同步基准」）：
          DISCOVERED  ∧ article_key 非空
            − 已有 READY ContentAsset 的**同一规范键**（= 已成功入库）
            − 同一规范键已挂在**活动**（QUEUED/RUNNING）sync_account Job 下的行（= 在途）
          先按 `short_link_maps` 把 `s:` 形态换成它的长链键，再对剩余行**按这个键收敛到一行**
          （同篇两形态一轮只入列一次，S4.1.2；见 `_with_effective_keys` 的成立条件与局限）

        为什么键必须是 `article_key` 而不是 `external_id`（P-2 的整条根因）：
        `external_id` 是渠道内幂等键（`workUuid`），`content_assets.external_id` 装的是
        `canonical_article_key(url)`——两支键空间只在"上游缺 id 走兜底"时部分相交，
        于是 `external_id NOT IN (ready)` 恒真、已入库的篇每轮都被重新入列一次。
        在途面同理按键减：只按 `manifest_id` 减的话，同篇的第二种 URL 形态会在下一轮
        绕过在途保护再排一次队。

        两条 **NULL 守卫不是装饰**：
        ① `JobItem.manifest_id` 可空（S4.2.1 / D-V9-04），而 SQL 的 `x NOT IN (子查询)`
           一旦子查询含 NULL 就整体恒 UNKNOWN ⇒ 候选会被**全部**滤光，Diff 从"永远 1 条"
           变成"永远 0 条"，比原 bug 更坏，所以子查询显式 `isnot(None)`；
        ② `article_key IS NULL` 的存量行**故意不入列**（它们还没有跨渠道身份，拿 NULL 去减
           资产等于让所有无键行互撞）。这不是把它们藏起来：回填归 STEP-07，而"因此停采"这件事
           由下面的 `null_key_backlog` 计数告警出声。
        """
        ready_keys = select(ContentAsset.external_id).where(
            ContentAsset.source_id == source_id,
            ContentAsset.status == "READY",
        )
        active_job_ids = self._active_sync_job_ids(subscription_id)
        # 在途面按**文章键**减，不是按 manifest_id 减：同一篇的两种形态是两个 manifest_id，
        # 只按 id 减的话，第二轮会把还没入库的那一行也放进来（同篇二次入列，P-2 的另一半）。
        # 这里减的是**同键空间**的那一对；`s:`/`b:` 两支跨键空间的形态由 `_with_effective_keys` 并。
        # `is_not(None)` 同样是 NULL 守卫，不是装饰。
        inflight_keys = (
            select(ArticleManifest.article_key)
            .join(JobItem, JobItem.manifest_id == ArticleManifest.id)
            .where(JobItem.job_id.in_(active_job_ids), ArticleManifest.article_key.is_not(None))
            .distinct()
        )
        stmt = (
            select(ArticleManifest)
            .where(
                ArticleManifest.source_id == source_id,
                ArticleManifest.status == MANIFEST_STATUS_DISCOVERED,
                ArticleManifest.article_key.isnot(None),
                ArticleManifest.article_key.not_in(ready_keys),
                ArticleManifest.article_key.not_in(inflight_keys),
            )
            .order_by(ArticleManifest.created_at, ArticleManifest.id)
        )
        rows = list((await self._session.scalars(stmt)).all())
        # 短链形态先收敛到长链规范键，再按这个键做同轮去重（S4.1.2 的两形态就是 `s:` 与 `b:`）
        pairs = await self._with_effective_keys(source_id, subscription_id, rows)
        # 同一轮内的同篇多形态收敛成一次入列（S4.1.2）。
        # 剩下的行仍是 DISCOVERED，等这一篇入库后由 `ready_keys` 那一条减掉——
        # 所以这不是"少采"，是"同一篇只排一次队"。
        # 排序带 `id` 做 tie-break 不是讲究：`created_at` 是 `func.now()` = **事务**时间戳，
        # 同一批 flush 出来的行它全等，只按它排的话"留哪一行"由查询计划决定，
        # 用例就会今天过明天红。留的是"确定同一行"，不是"最早那一行"。
        unique: list[ArticleManifest] = []
        seen_keys: set[str] = set()
        for row, effective_key in pairs:
            if effective_key in seen_keys:
                continue
            seen_keys.add(effective_key)
            unique.append(row)
        backlog = int(
            await self._session.scalar(
                select(func.count())
                .select_from(ArticleManifest)
                .where(
                    ArticleManifest.source_id == source_id,
                    ArticleManifest.status == MANIFEST_STATUS_DISCOVERED,
                    ArticleManifest.article_key.is_(None),
                )
            )
            or 0
        )
        if backlog:
            logger.warning(
                "manifest.diff.null_key_backlog",
                source_id=source_id,
                subscription_id=subscription_id,
                rows=backlog,
                hint="这些 DISCOVERED 行还没有 article_key，按 D-V9-04 故意不入列；回填在 STEP-07",
            )
        return unique

    async def _populate_job_items(
        self,
        job_id: str,
        source_id: str,
        subscription_id: str,
        *,
        manifests: list[ArticleManifest] | None = None,
    ) -> int:
        """Manifest Diff：DISCOVERED 清单减已有 READY Asset → JobItem；返回入列篇数。

        `manifests` 已由调用方算出时直接复用（省一次 Diff 查询）；未传则现场算。

        S4.3.2（STEP-04）：一次入列同时做三件事——建 JobItem、写 `JobItem.manifest_id`、
        把清单置 `ENQUEUED`。分两步写（建条目、由别处再置位）会留一个崩溃窗口：
        条目已在队列里而清单仍是 DISCOVERED，下一轮 Diff 会把同篇**再入列一次**——
        那还是 P-2 的形状，只是触发条件从"键空间不相交"换成"进程中途死"。
        置位走 `state_machine.validate_transition`：非法流转当场 30005，
        而不是让四态变成"只有 DISCOVERED 被写过"的装饰字段。

        真实 redfox 清单源需 REDFOX_API_KEY（env 注入）；
        未配置时不使用 fixture 占位（证据：后续按 REDFOX_API_KEY 配置接入）。
        """
        if manifests is None:
            manifests = await self._compute_new_manifests(source_id, subscription_id)
        if not manifests:
            logger.info("P2 无新增 Manifest，JobItem 保持空，待 REDFOX_API_KEY 配置后接入")
            return 0
        # 为什么这里只校验、不"顺手把 ENQUEUED/FAILED 回退一下"：Diff 只选 DISCOVERED，
        # 而 `_create_sync_job` 的两个调用点要么传 None（现算 Diff）要么传**当轮**新鲜 Diff 的结果，
        # 永远不会把非 DISCOVERED 的行带进来——那条回退是死代码（第三轮验证实测）。
        # 真有人绕过 Diff 塞行进来，撞 30005 出声才是对的；自造一条
        # `ENQUEUED→DISCOVERED→ENQUEUED` 只会把校验变成装饰。
        for m in manifests:
            # 校验放在建条目**之前**：先 create 再抛 30005 会留下一条没人认领的 JobItem，
            # 而调用方捕获异常时并不一定会回滚（`_create_sync_job` 之外还有调度器的 savepoint 面）。
            validate_transition("manifest", m.status, MANIFEST_STATUS_ENQUEUED)
            item = await self._item_repo.create(job_id=job_id, external_id=m.external_id, url=m.url or "")
            item.manifest_id = m.id
            m.status = MANIFEST_STATUS_ENQUEUED
            await self._item_repo.set_status(item.id, "PENDING")
        await self._session.flush()
        return len(manifests)

    async def run_incremental_sync(self, sub: SourceSubscription, run_token: str) -> int:
        """T2.4 增量一轮：Diff 新篇 → 建 run-scoped sync Job + JobItem；返回新增篇数。

        空轮询（Diff 为空）→ **不建 Job**（避免空 Job 污染 `latestJobId` 与 Job 表），返回 0。
        **不 commit**：事务边界由调度器 `_process_one` 统一持有（认领+入列+水位推进原子）。
        """
        manifests = await self._compute_new_manifests(sub.source_id, sub.id)
        if not manifests:
            return 0
        job = await self._create_sync_job(
            sub.user_id,
            sub.space_id,
            sub.source_id,
            sub.id,
            run_token=run_token,
            manifests=manifests,
        )
        logger.info("T2.4 增量入列 subscription=%s job=%s 新增=%d", sub.id, job.id, len(manifests))
        return len(manifests)
