"""知识空间仓库（B-T4）：KnowledgeSpace CRUD 与 1:1 LangBot KB 映射回写。

事务约定：repo 只 flush 不 commit，事务边界归调用方（测试借外层事务回滚隔离）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sqlalchemy import Select, delete, exists, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import ContentAsset, KnowledgeDocument, KnowledgeSpace, Source, User


@runtime_checkable
class SpaceRepoProto(Protocol):
    """空间仓库契约（Service 依赖此协议，测试注入内存桩）。"""

    async def create(
        self,
        user_id: str,
        name: str,
        langbot_kb_uuid: str = ...,
        description: str | None = ...,
    ) -> KnowledgeSpace: ...

    async def get_by_id(self, space_id: str) -> KnowledgeSpace | None: ...

    async def get_by_name(self, user_id: str, name: str) -> KnowledgeSpace | None: ...

    async def list_by_user(self, user_id: str) -> list[KnowledgeSpace]: ...

    async def list_with_owner(self) -> list[tuple[KnowledgeSpace, User | None]]: ...

    async def set_langbot_kb_uuid(self, space_id: str, kb_uuid: str) -> None: ...

    async def set_description(self, space_id: str, description: str | None) -> None: ...

    async def update_doc_count(self, space_id: str, delta: int) -> None: ...

    async def count_docs(self, space_id: str, category: str | None = None) -> int: ...

    async def count_docs_many(self, space_ids: list[str]) -> dict[str, int]: ...

    async def count_chunks(self, space_id: str) -> int | None: ...

    async def list_docs(
        self,
        space_id: str,
        limit: int | None = None,
        offset: int = 0,
        category: str | None = None,
    ) -> list[dict]: ...

    async def list_doc_categories(self, space_id: str) -> list[str]: ...

    async def delete_space_cascade(self, space_id: str) -> dict[str, int]: ...

    async def delete_doc(self, doc_id: str) -> dict[str, int]: ...


class SpaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: str,
        name: str,
        langbot_kb_uuid: str = "",
        description: str | None = None,
    ) -> KnowledgeSpace:
        """创建空间；同名冲突由 uq_space_user_name 唯一约束抛 IntegrityError
        （API 层错误码映射待 A 裁决，见交付报告）。

        R0.5.2（F-4）：description 落库——原实参缺位导致契约声明的字段被静默丢弃。"""
        space = KnowledgeSpace(
            user_id=user_id,
            name=name,
            langbot_kb_uuid=langbot_kb_uuid,
            description=description,
        )
        self._session.add(space)
        await self._session.flush()
        return space

    async def get_by_id(self, space_id: str) -> KnowledgeSpace | None:
        return await self._session.get(KnowledgeSpace, space_id)

    async def get_by_name(self, user_id: str, name: str) -> KnowledgeSpace | None:
        return await self._session.scalar(
            select(KnowledgeSpace).where(
                KnowledgeSpace.user_id == user_id, KnowledgeSpace.name == name
            )
        )

    async def list_by_user(self, user_id: str) -> list[KnowledgeSpace]:
        result = await self._session.scalars(
            select(KnowledgeSpace)
            .where(KnowledgeSpace.user_id == user_id)
            .order_by(KnowledgeSpace.created_at)
        )
        return list(result)

    async def list_with_owner(self) -> list[tuple[KnowledgeSpace, User | None]]:
        """跨用户空间列表（/admin）用：单查询取全部空间 + 归属账号。

        归属信息必须随空间同查——逐空间查 owner 会把这里变成 N+1
        （doc 计数的同类缺陷 T1.5.3 已修过一次）。LEFT JOIN：users 行缺失时
        空间仍返回、归属记为 None，不得因孤儿行静默丢空间。
        """
        stmt = (
            select(KnowledgeSpace, User)
            .outerjoin(User, User.id == KnowledgeSpace.user_id)
            .order_by(KnowledgeSpace.created_at)
        )
        # LEFT JOIN 的 NULL 可空性 SQLAlchemy 静态类型表达不了，显式标注返回值收窄
        result: list[tuple[KnowledgeSpace, User | None]] = [
            (space, owner) for space, owner in (await self._session.execute(stmt)).all()
        ]
        return result

    async def set_langbot_kb_uuid(self, space_id: str, kb_uuid: str) -> None:
        """LangBot KB 建库成功后回写（1:1 映射，ADR-0001）。"""
        space = await self.get_by_id(space_id)
        if space is None:
            return
        space.langbot_kb_uuid = kb_uuid
        await self._session.flush()

    async def set_description(self, space_id: str, description: str | None) -> None:
        """R0.5.2（F-4）：简介写路径（Service 校验通过后调用）。"""
        space = await self.get_by_id(space_id)
        if space is None:
            return
        space.description = description
        await self._session.flush()

    # ------------------------------------------------------------------ AB-P004 P1 公共库

    async def list_public_spaces(self) -> list[KnowledgeSpace]:
        """公共库列表（is_public=1 系统空间）。"""
        result = await self._session.scalars(
            select(KnowledgeSpace).where(KnowledgeSpace.is_public.is_(True)).order_by(KnowledgeSpace.created_at)
        )
        return list(result)

    async def get_public_space(self, space_id: str) -> KnowledgeSpace | None:
        """按 id 查公共库空间；非公共/不存在 → None（不泄露存在性）。"""
        space = await self.get_by_id(space_id)
        if space is None or not space.is_public:
            return None
        return space

    async def create_public_space(self, user_id: str, name: str) -> KnowledgeSpace:
        """创建公共库系统空间（is_public=1, owner_type=system）。"""
        space = KnowledgeSpace(user_id=user_id, name=name, is_public=True, owner_type="system")
        self._session.add(space)
        await self._session.flush()
        return space

    async def update_doc_count(self, space_id: str, delta: int) -> None:
        space = await self.get_by_id(space_id)
        if space is None:
            return
        space.doc_count = max(0, space.doc_count + delta)
        await self._session.flush()

    # ------------------------------------------------------------------ 聚合查询（v0.3 契约）

    async def count_docs(self, space_id: str, category: str | None = None) -> int:
        """knowledge_documents 真实 count（禁 mock；docCount 字段数据源）。

        R0.1.1：可选分类过滤，与 list_docs 共用 _docs_stmt——total 与 items 必须走
        同一过滤谓词，否则会出现「过滤后的列表配未过滤的 total」。
        """
        stmt = self._docs_stmt(space_id, category).with_only_columns(func.count())
        result = await self._session.scalar(stmt)
        return int(result or 0)

    async def count_docs_many(self, space_ids: list[str]) -> dict[str, int]:
        """T1.5.3（N+1 修复）：多空间文档计数单查询（GROUP BY），替代逐空间 count 循环。

        未出现在结果中的空间 = 0 篇（调用方以 .get(sid, 0) 取值）。"""
        if not space_ids:
            return {}
        rows = await self._session.execute(
            select(KnowledgeDocument.space_id, func.count())
            .where(KnowledgeDocument.space_id.in_(space_ids))
            .group_by(KnowledgeDocument.space_id)
        )
        return {sid: int(cnt) for sid, cnt in rows.all()}

    async def count_chunks(self, space_id: str) -> int | None:
        """chunk 计数：本地无 chunk 记账列，数据源在 LangBot 侧。

        R0.5.3（F-5）：返回 None 而非 0——0 会被前端渲成「已索引 0 块」，
        把「数据源未接线」谎报成「真的没有分块」。None 让前端可以隐藏该指标。

        接线前置条件（本批未做，登记为开放项）：
        LangBot v4.10.9 客户端侧仅有 list_kb_files（文件级 status），无 KB 级 chunk 统计端点；
        用文件数冒充 chunk 数是换一个假数。接线需要新增 client 方法 + 缓存层，
        且缓存层必须存在——否则每次 GET /spaces 都打一次 LangBot。"""
        return None

    def _docs_stmt(self, space_id: str, category: str | None = None) -> Select:
        """文档清单查询基座（join asset/source + 分类过滤谓词），list_docs / count_docs 共用。

        分类过滤建在 ContentAsset 上（category 是资产级列），故本方法始终带上两个
        join；两个调用方共用它即保证过滤谓词不会各写一份后漂移（F-3 同类缺陷）。
        `category` 为空串即「未分类」（资产无分类标签），哨兵已在 Service 层译好。
        """
        stmt = select(
            KnowledgeDocument.id,
            ContentAsset.title,
            Source.name,
            KnowledgeDocument.status,
            KnowledgeDocument.updated_at,
            ContentAsset.category,
        ).join(ContentAsset, KnowledgeDocument.asset_id == ContentAsset.id).join(
            Source, ContentAsset.source_id == Source.id
        )
        stmt = stmt.where(KnowledgeDocument.space_id == space_id)
        if category is not None:
            stmt = stmt.where(ContentAsset.category == category)
        return stmt

    async def list_docs(
        self,
        space_id: str,
        limit: int | None = None,
        offset: int = 0,
        category: str | None = None,
    ) -> list[dict]:
        """空间文档清单（join asset/source），供 GET /spaces/{id}/docs。

        T1.5.7：可选 limit/offset（offset 分页简版，默认 None=全量向后兼容）；
        R0.1.1：可选 category 过滤（走已建索引 content_assets.category）。
        总数由调用方以 count_docs 取得（同空间双查询，胜过全量拉取内存切片）。

        排序稳定性（实测缺陷修复）：`created_at` 为 `server_default=now()`，而 PostgreSQL
        的 `now()` 返回**事务开始时刻**——同一事务内批量入库的 doc 时间戳完全相同，
        仅凭 `created_at` 排序属**未定序**（PG 排序非稳定），会让 offset 分页出现
        重复页/漏行。故追加 `id` 作确定性兜底（分页健全性；不改变单页内容集）。
        """
        stmt = self._docs_stmt(space_id, category).order_by(
            KnowledgeDocument.created_at, KnowledgeDocument.id
        )
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = await self._session.execute(stmt)
        return [
            {
                "id": row.id,
                "title": row.title,
                "source": row.name,
                "status": row.status,
                "updated_at": row.updated_at,
                "category": row.category or "",
            }
            for row in rows
        ]

    async def list_doc_categories(self, space_id: str) -> list[str]:
        """本空间 doc 关联资产已出现的分类取值（去重；含空串=未分类）。

        R0.1.2：供 GET /docs:categories——服务端枚举，替代前端按当前页数据推导
        （分页后单页推导会漏掉不在本页的分类）。category 是资产级列，故本方法
        天然返回资产级集合：跨空间共享资产被改分类，另一空间的集合同步变化。
        排序与哨兵翻译在 Service 层（仓库只给库内原值）。
        """
        rows = await self._session.scalars(
            select(ContentAsset.category)
            .join(KnowledgeDocument, KnowledgeDocument.asset_id == ContentAsset.id)
            .where(KnowledgeDocument.space_id == space_id)
            .distinct()
        )
        return [str(category) for category in rows]

    async def delete_space_cascade(self, space_id: str) -> dict[str, int]:
        """删除空间的 docs 行 + 本空间独占资产行 + space 行（AB-T11，只 flush 不 commit）。

        范围收敛（任务包④「该空间的 docs/assets/space 行」）：先取本空间资产的
        id 集合 → 删本空间 knowledge_documents → 删「曾属本空间且已不再被任何
        doc 引用」的 content_assets（共享给他空间的资产不删，孤儿判定用 NOT EXISTS
        惯用法，兼容 PG/SQLite）→ 删 space 行。
        """
        asset_ids = list(
            await self._session.scalars(
                select(KnowledgeDocument.asset_id).where(KnowledgeDocument.space_id == space_id)
            )
        )
        r_docs = await self._session.execute(
            delete(KnowledgeDocument).where(KnowledgeDocument.space_id == space_id)
        )
        r_assets = await self._session.execute(
            delete(ContentAsset)
            .where(ContentAsset.id.in_(asset_ids))
            .where(
                ~exists(
                    select(KnowledgeDocument.id).where(
                        KnowledgeDocument.asset_id == ContentAsset.id
                    )
                )
            )
        )
        r_space = await self._session.execute(
            delete(KnowledgeSpace).where(KnowledgeSpace.id == space_id)
        )
        await self._session.flush()
        return {
            "docs": _rowcount(r_docs),
            "assets": _rowcount(r_assets),
            "spaces": _rowcount(r_space),
        }

    async def delete_doc(self, doc_id: str) -> dict[str, int]:
        """删除单篇 doc 行 + 该资产「已不再被任何 doc 引用」的行（AB-T11 同款孤儿判定）。

        孤儿判定复用 delete_space_cascade 的 NOT EXISTS 惯用法（兼容 PG/SQLite）：
        资产仍被其他空间 doc 引用则不删——content_assets 是跨空间共享的唯一真源，
        删掉会让「改文重算分类」「素材复用命中」等上游语义丢数据。
        """
        doc = await self._session.get(KnowledgeDocument, doc_id)
        if doc is None:
            return {"docs": 0, "assets": 0}
        r_doc = await self._session.execute(
            delete(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
        )
        r_asset = await self._session.execute(
            delete(ContentAsset)
            .where(ContentAsset.id == doc.asset_id)
            .where(~exists(select(KnowledgeDocument.id).where(KnowledgeDocument.asset_id == ContentAsset.id)))
        )
        await self._session.flush()
        return {"docs": _rowcount(r_doc), "assets": _rowcount(r_asset)}


def _rowcount(result: object) -> int:
    """DELETE 执行结果的受影响行数（mypy：Result 无 rowcount，DML 实为 CursorResult）。"""
    return int(getattr(result, "rowcount", 0) or 0) if isinstance(result, CursorResult) else 0
