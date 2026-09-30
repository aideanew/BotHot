"""AB-P004 P1 公共库拷贝式服务：GET /spaces/public + POST /spaces/{id}/links 批量 copy。

- GET /spaces/public：列出 is_public=1 系统空间（文档数/引擎/更新时间），登录保护；
- POST /spaces/{id}/links {public_space_id}：把公共空间 READY 资产批量 copy 进目标用户空间，
  幂等：已 copy 的 doc（同 asset_id+space_id）跳过，返回 {copied, skipped, total}；
- 公共库文档 source=copy，citations.spaceName 标注来源（SSE 链路不动，零检索改动）。

过滤口径：公共空间的 doc → asset 映射，只 copy 属于该公共空间的 READY 资产（不误抄全局其他资产）。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ForbiddenError, ResourceNotFoundError
from app.models.entities import ContentAsset, KnowledgeDocument
from app.repositories.asset import DocumentRepository
from app.repositories.space import SpaceRepository

logger = logging.getLogger(__name__)


def check_publish_gate(allowlist_text: str, operator_id: str, owner_type: str) -> None:
    """公共库发布双闸（T1.4.1，D9=c 过渡裁决）——纯函数，离线单测可覆盖。

    闸① env allowlist：操作者本地 user_id 须在 PUBLIC_ADMIN_ALLOWLIST（逗号分隔）内；
    闸② owner_type=system：仅系统空间可发布/回收（防任意登录用户自置发布）。
    任一不满足 → ForbiddenError(10004/403)。SPEC-M3 批次 3 双闸收敛（2026-09-23
    裁「按角色分通道」）确认本闸**保留为发布专属语义**：require_role 不读本字段。
    """
    allowlist = {x.strip() for x in str(allowlist_text or "").split(",") if x.strip()}
    if operator_id not in allowlist:
        if not allowlist:
            raise ForbiddenError(
                "无公共库发布权限：PUBLIC_ADMIN_ALLOWLIST 未配置（空串=无人可发布），"
                "请在 .env 或 compose.yml 中设置该变量并指定操作者 user_id"
            )
        raise ForbiddenError("无公共库发布权限（管理员 allowlist 未包含该操作者），请联系管理员")
    if owner_type != "system":
        raise ForbiddenError("仅系统空间（owner_type=system）可发布或回收公共库")


class PublicLibraryService:
    """P1 公共库拷贝式服务（编排层显式 commit，repo 只 flush）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = SpaceRepository(session)

    async def list_public_views(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict], int]:
        """GET /spaces/public → data.items：公共库卡（name/docCount/engine/updatedAt/isPublic）。

        T1.5.3：doc 计数改 GROUP BY 单查询（原逐空间 count 为 N+1）。
        C.1：LIMIT/OFFSET 下沉到 repo SQL，返回 (items, total)。"""
        spaces = await self._repo.list_public_spaces(limit=limit, offset=offset)
        total = await self._repo.count_public_spaces()
        counts = await self._repo.count_docs_many([s.id for s in spaces])
        items = []
        for space in spaces:
            items.append(
                {
                    "id": space.id,
                    "name": space.name,
                    "description": "AI前沿库（采自公众号，系统空间）",
                    "docCount": counts.get(space.id, 0),
                    "engine": getattr(space, "engine", "builtin"),
                    "isPublic": True,
                    "updatedAt": space.updated_at.isoformat()
                    if hasattr(space.updated_at, "isoformat")
                    else str(space.updated_at or ""),
                }
            )
        return items, total

    async def get_public_space(self, space_id: str):
        """公共库空间校验（非公共/不存在 → None，不泄露存在性）。"""
        return await self._repo.get_public_space(space_id)

    async def set_public_status(self, operator_id: str, space_id: str, is_public: bool) -> dict[str, object]:
        """T1.4.1：is_public 写端点服务层（双闸后置位，显式 commit）。

        返回 {spaceId, name, isPublic}；空间不存在 → 30004；
        双闸不过（allowlist / owner_type）→ 10004（见 check_publish_gate）。
        """
        space = await self._repo.get_by_id(space_id)
        if space is None:
            raise ResourceNotFoundError(space_id)
        check_publish_gate(
            str(get_settings().public_admin_allowlist),
            operator_id,
            str(getattr(space, "owner_type", "user") or "user"),
        )
        space.is_public = bool(is_public)
        await self._session.commit()
        logger.info(
            "T1.4.1 set_public_status: operator=%s space=%s isPublic=%s",
            operator_id,
            space_id,
            is_public,
        )
        return {"spaceId": space.id, "name": space.name, "isPublic": space.is_public}

    async def link_public_space(self, user_id: str, space_id: str, public_space_id: str) -> dict[str, int]:
        """POST /spaces/{id}/links：批量 copy 公共空间 READY 资产进目标用户空间（幂等）。

        返回 {copied, skipped, total}。目标空间须归属 user_id；公共空间须 is_public=1。
        只 copy 属于该公共空间的 READY 资产（按 doc 映射过滤，不误抄全局其他空间资产）。
        """
        target = await self._repo.get_by_id(space_id)
        if target is None or target.user_id != user_id:
            raise ResourceNotFoundError(space_id)

        public_space = await self._repo.get_public_space(public_space_id)
        if public_space is None:
            raise ResourceNotFoundError(public_space_id)

        doc_repo = DocumentRepository(self._session)

        # 公共空间内的 doc → asset 映射（只取 READY 资产，不误抄其他空间资产）
        pub_asset_ids = set(
            await self._session.scalars(
                select(KnowledgeDocument.asset_id).where(KnowledgeDocument.space_id == public_space.id)
            )
        )
        # 空公共空间 → 无 doc 可映射 → 无资产可抄。此处**不能**退化为「全部 READY 资产」：
        # 那会把系统内其他用户的私有资产抄进请求者空间（跨用户数据越界，违背本模块
        # 「不误抄全局其他资产」契约）。update_doc_count(+0) 是恒等操作，可安全跳过。
        if not pub_asset_ids:
            return {"copied": 0, "skipped": 0, "total": 0}

        ready_assets = (
            await self._session.scalars(
                select(ContentAsset)
                .where(ContentAsset.status == "READY", ContentAsset.id.in_(pub_asset_ids))
                .order_by(ContentAsset.id)
            )
        ).all()

        copied = 0
        skipped = 0
        for asset in ready_assets:
            existing = await doc_repo.get_by_asset_space(asset.id, space_id)
            if existing is not None:
                skipped += 1
                continue
            # 指纹随公共资产当前正文记录（R4.4/F-11）：留空会让该 doc 在资产任一版本
            # 变化时被误判为内容落后——「从未同步过」与「已同步到最新」必须可区分。
            doc = await doc_repo.create(
                asset_id=asset.id, space_id=space_id, content_hash=asset.content_hash
            )
            doc.source = "copy"
            await self._session.flush()
            copied += 1
        await self._repo.update_doc_count(space_id, copied)
        await self._session.commit()
        logger.info(
            "P1 link_public_space: user=%s target=%s public=%s copied=%d skipped=%d",
            user_id,
            space_id,
            public_space_id,
            copied,
            skipped,
        )
        return {"copied": copied, "skipped": skipped, "total": copied + skipped}
