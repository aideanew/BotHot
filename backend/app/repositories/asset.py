"""内容资产与知识文档仓库（B-T4）。

- ContentAsset：幂等键 = source_id + external_id（同键 content_hash 变化 → version+1）；
- KnowledgeDocument：资产入库映射状态机（FETCHED → INDEXED → READY），校验在 Service 层。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import ContentAsset, KnowledgeDocument


class AssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, **fields: object) -> ContentAsset:
        asset = ContentAsset(**fields)  # type: ignore[arg-type]
        self._session.add(asset)
        await self._session.flush()
        return asset

    async def get_by_id(self, asset_id: str) -> ContentAsset | None:
        return await self._session.get(ContentAsset, asset_id)

    async def get_by_source_external(self, source_id: str, external_id: str) -> ContentAsset | None:
        return await self._session.scalar(
            select(ContentAsset).where(ContentAsset.source_id == source_id, ContentAsset.external_id == external_id)
        )

    async def get_by_url_fragment(self, source_id: str, fragment: str) -> ContentAsset | None:
        """BE-02 D-2/D-3 兼容存量：源下 URL 含指定片段的资产（biz 锚源 + article_key 资产失配兜底）。

        仅用于缓存命中/版本管理的前置查找，不改变幂等键语义（external_id 仍为主锚）。
        """
        if not fragment:
            return None
        return await self._session.scalar(
            select(ContentAsset)
            .where(
                ContentAsset.source_id == source_id,
                ContentAsset.url.like(f"%{fragment}%"),
            )
            .limit(1)
        )

    async def upsert_content(self, **fields: object) -> tuple[ContentAsset, bool]:
        """按 (source_id, external_id) upsert：hash 相同返回原资产(False)，
        hash 变化则更新正文并 version+1(True)——作者改文语义。

        AB-P004 P0：同键资产在命中/未命中两路径均幂等，hit_count 透传防盲写。"""
        asset = await self.get_by_source_external(str(fields["source_id"]), str(fields["external_id"]))
        if asset is None:
            # T2.7 竞态兜底：同 URL 并发首抓时两事务可能同时查空后并插——savepoint 捕获
            # uq_asset_source_external 冲突后重查既有资产（DB 唯一约束保证零重复，兜底不 500）。
            try:
                async with self._session.begin_nested():
                    asset = await self.create(**fields)
            except IntegrityError:
                asset = await self.get_by_source_external(str(fields["source_id"]), str(fields["external_id"]))
                if asset is None:  # 非常见冲突如实上抛
                    raise
            return asset, True
        new_hash = str(fields.get("content_hash", ""))
        if new_hash and new_hash == asset.content_hash:
            # hash 相同：透传 hit_count（防未命中路径盲写 0 冲掉命中计数）
            raw_hit = fields.get("hit_count")
            if isinstance(raw_hit, int):
                asset.hit_count = raw_hit
            elif raw_hit is not None:
                asset.hit_count = int(str(raw_hit))
            else:
                asset.hit_count = int(asset.hit_count or 0)
            return asset, False
        # hash 变化：版本管理——旧 doc 标 superseded，新 doc 走 ingest；hit_count 重置为 0（新内容）
        asset.content_hash = new_hash
        asset.content_markdown = str(fields.get("content_markdown", asset.content_markdown))
        asset.title = str(fields.get("title", asset.title))
        asset.raw_uri = str(fields.get("raw_uri", asset.raw_uri))
        asset.quality_score = float(fields.get("quality_score", asset.quality_score))  # type: ignore[arg-type]
        # T3.2.2：内容变化 → 分类随新内容重算（调用方传入时）
        raw_category = fields.get("category")
        if isinstance(raw_category, str) and raw_category:
            asset.category = raw_category
        asset.version += 1
        asset.hit_count = 0  # 新内容版本：命中计数归零（旧版本已 superseded）
        await self._session.flush()
        return asset, True

    async def hit(self, asset: ContentAsset) -> None:
        """AB-P004 P0 素材复用：命中缓存计数 +1（仅计数，不改 hash/version/status）。"""
        asset.hit_count = int(asset.hit_count or 0) + 1
        await self._session.flush()

    async def mark_stale_docs(self, asset_id: str, current_hash: str) -> int:
        """号主改文（version+1）→ 该资产下**内容已落后**的 doc 标 FAILED（superseded）。

        判定轴是内容指纹而非空间归属：资产按 `uq_asset_source_external` 全局共享，
        一次重抓覆写的是所有空间共用的那一行。若按调用方 space_id 过滤，他人空间的 doc
        会静默指向已变正文（F-11：无错误、无告警、无 stale 标记）。`status != FAILED`
        保留——已因别的原因失败的 doc 不覆写其 last_error。返回影响行数。
        """
        docs = await self._session.scalars(
            select(KnowledgeDocument).where(
                KnowledgeDocument.asset_id == asset_id,
                KnowledgeDocument.status != "FAILED",
                KnowledgeDocument.content_hash != current_hash,
            )
        )
        n = 0
        for doc in docs:
            doc.status = "FAILED"
            doc.last_error = "superseded"
            n += 1
        if n:
            await self._session.flush()
        return n

    async def set_category(self, asset_id: str, category: str) -> None:
        """人工纠偏规则分类（站内筛选维度）。只改 category，不动 hash/version/status。"""
        asset = await self.get_by_id(asset_id)
        if asset is None:
            return
        asset.category = category
        await self._session.flush()

    async def set_category_many(self, asset_ids: list[str], category: str) -> int:
        """R0.2.5 批量纠偏：单条 IN 更新（避免逐条 flush 的 N+1），返回受影响行数。

        与 set_category 同口径——只改 category，不动 hash/version/status。
        """
        if not asset_ids:
            return 0
        result = await self._session.execute(
            update(ContentAsset).where(ContentAsset.id.in_(asset_ids)).values(category=category)
        )
        await self._session.flush()
        return int(getattr(result, "rowcount", 0) or 0)


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, asset_id: str, space_id: str, content_hash: str = "") -> KnowledgeDocument:
        doc = KnowledgeDocument(asset_id=asset_id, space_id=space_id, content_hash=content_hash)
        self._session.add(doc)
        await self._session.flush()
        return doc

    async def get_by_id(self, doc_id: str) -> KnowledgeDocument | None:
        return await self._session.get(KnowledgeDocument, doc_id)

    async def list_by_ids(self, doc_ids: list[str]) -> list[KnowledgeDocument]:
        """R0.2.5 批量操作预取：单条 IN 查询取回全部行（含不属本空间的，由调用方判定）。"""
        if not doc_ids:
            return []
        rows = await self._session.scalars(select(KnowledgeDocument).where(KnowledgeDocument.id.in_(doc_ids)))
        return list(rows)

    async def get_by_asset_space(self, asset_id: str, space_id: str) -> KnowledgeDocument | None:
        return await self._session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.asset_id == asset_id, KnowledgeDocument.space_id == space_id
            )
        )

    async def list_pending_ingest(self, limit: int = 50) -> list[KnowledgeDocument]:
        """仍在入库中的文档（FETCHED/INDEXED 且已拿到引擎 file_id），供后台状态推进。

        按 `updated_at` 升序：最久未推进的先探，避免最新一批挤占本轮名额。
        """
        stmt = (
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.status.in_(["FETCHED", "INDEXED"]),
                KnowledgeDocument.langbot_file_id.isnot(None),
                KnowledgeDocument.langbot_file_id != "",
            )
            .order_by(KnowledgeDocument.updated_at.asc())
            .limit(limit)
        )
        rows = await self._session.scalars(stmt)
        return list(rows)

    async def set_status(self, doc_id: str, status: str, last_error: str = "") -> None:
        doc = await self.get_by_id(doc_id)
        if doc is None:
            return
        doc.status = status
        doc.last_error = last_error
        await self._session.flush()

    async def set_content_hash(self, doc_id: str, content_hash: str) -> None:
        """记录该 doc 实际入库的正文指纹（R4.4/F-11 跨空间 stale 判定依据）。"""
        doc = await self.get_by_id(doc_id)
        if doc is None:
            return
        doc.content_hash = content_hash
        await self._session.flush()

    async def set_langbot_file_id(self, doc_id: str, file_id: str) -> None:
        doc = await self.get_by_id(doc_id)
        if doc is None:
            return
        doc.langbot_file_id = file_id
        await self._session.flush()

    async def allowed_file_ids(
        self,
        space_id: str,
        source_ids: list[str] | None = None,
        since: datetime | None = None,
    ) -> set[str]:
        """阶段 3.1.1 元数据预过滤：空间内候选 doc 的 langbot_file_id 集合。

        - 仅 READY（已入库可检索）且 file id 非空——未就绪 doc 检索侧本就无命中；
        - source_ids 非空 → 限定这些信息源（content_assets.source_id）；
        - since 非空 → 文章时间窗：COALESCE(published_at, created_at) >= since
          （缺 publish_time 的源用入库时间兜底，避免静默丢文档）；
        - 空集合是合法结果：调用方据此收窄为「无可回答内容」，不做无过滤回退。
        """
        stmt = (
            select(KnowledgeDocument.langbot_file_id)
            .join(ContentAsset, KnowledgeDocument.asset_id == ContentAsset.id)
            .where(
                KnowledgeDocument.space_id == space_id,
                KnowledgeDocument.status == "READY",
                KnowledgeDocument.langbot_file_id != "",
            )
        )
        if source_ids:
            stmt = stmt.where(ContentAsset.source_id.in_(source_ids))
        if since is not None:
            stmt = stmt.where(func.coalesce(ContentAsset.published_at, ContentAsset.created_at) >= since)
        rows = (await self._session.execute(stmt)).scalars().all()
        return {str(row) for row in rows}
