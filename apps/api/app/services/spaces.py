"""知识空间服务（B-T4R）：CRUD + 30006 重名冲突 + v0.3 视图组装。

- 视图形状（camelCase / docCount / status 三值映射）是业务逻辑，收敛在本层；
  Route 层只做鉴权与信封包装（AGENTS 铁律）。
- description：R0.5.1 迁移 ab1004m5a 落列后由实体回读（原「实体暂无该列」缺口已闭合，
  空串表示「未填写简介」，与前端空态文案对齐）。
- stats.chunks：本地无 chunk 记账，数据源在 LangBot 侧；R0.5.3 起返回 None（不下发 0，
  避免把「数据源未接线」谎报成「真的没有分块」），接线前置条件见 SpaceRepo.count_chunks。
"""

from __future__ import annotations

from typing import Any, Protocol

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import (
    AppError,
    InternalError,
    LangbotApiError,
    RequestInvalidError,
    ResourceNotFoundError,
    SpaceNameConflictError,
)
from app.models.entities import KnowledgeDocument, KnowledgeSpace, User
from app.providers.engine_port import EngineRouter
from app.repositories.asset import AssetRepository, DocumentRepository
from app.repositories.space import SpaceRepoProto
from app.services.categorizer import CATEGORIES, DEFAULT_CATEGORY, UNCATEGORIZED

logger = structlog.get_logger(__name__)

# 名称约束（最小可执行）：非空、≤128 字符、不含控制字符；更复杂规则随 UI 落地再收敛
_SPACE_NAME_MAX = 128

# 简介约束（R0.5.2，F-4）：允许空串（=「未填写简介」），≤512 字符与列宽一致
_SPACE_DESC_MAX = 512

# 分类人工纠偏：仅允许规则版六类或空串（清空回默认），不接受自由文本
CATEGORY_ALLOWLIST = frozenset(CATEGORIES) | {""}

# R0.2.5 批量文档操作（:delete / :recategorize）业务上限；路由侧另有 1..500 体量硬闸
DEFAULT_MAX_DOC_IDS = 50

# v0.3 契约：docs 端点 status ∈ pending|ready|failed（本地状态机 → 契约三值映射）
DOC_STATUS_VIEW = {
    "FETCHED": "pending",
    "INDEXED": "pending",
    "READY": "ready",
    "FAILED": "failed",
}


class SpaceValidationError(RequestInvalidError):
    """空间入参不合法（10005/422）。

    继承 RequestInvalidError 而非 ValueError：此前为裸 ValueError 会冒泡成 500，
    与 errors.py「业务路由统一抛 AppError」的裁决相悖（create_space 的三条分支同样受益）。
    """


def doc_status_view(status: str) -> str:
    """本地文档状态 → 契约三值；未知状态兜底 pending（不 500）。"""
    return DOC_STATUS_VIEW.get(status, "pending")


def _iso(dt: object) -> str:
    """datetime → ISO 8601 字符串（camelCase 时间字段的统一出口）。"""
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt or "")


def validate_category(category: str) -> None:
    """分类人工纠偏取值校验（单篇 PATCH 与批量 :recategorize 共用）：非法 → 10005。

    单点定义，避免两个端点各持一份白名单谓词后漂移。
    """
    if category not in CATEGORY_ALLOWLIST:
        raise SpaceValidationError(f"分类取值非法：{category}（可选 {'/'.join(CATEGORIES)} 或空串）")


def order_categories(categories: list[str]) -> list[str]:
    """分类集合呈现序（R0.1.2）：按 CATEGORIES 声明序，未分类以哨兵置末。

    categorizer 约定「声明序即前端筛选项顺序」，故响应不按入库顺序返回——否则下拉
    顺序随数据抖动。未登记的取值排在已知类之后（只读路径不删值）。
    空串在此译为 `__uncategorized__`：`:categories` 返回值可直接回传 `?category=`，
    与 R0.1.1 的查询入参口径对称。
    """
    present = set(categories)
    ordered = [c for c in CATEGORIES if c in present]
    ordered += [c for c in categories if c not in CATEGORIES and c != ""]
    if "" in present:
        ordered.append(UNCATEGORIZED)
    return ordered


class LangbotKbProto(Protocol):
    """删除空间/单篇文档所需的最小 LangBot 面（AB-T11 / R0.2.1；生产注入真 LangBotClient）。"""

    async def delete_kb(self, kb_uuid: str) -> None: ...

    async def delete_kb_file(self, kb_uuid: str, file_id: str) -> None: ...


class SpaceService:
    def __init__(
        self,
        repo: SpaceRepoProto,
        session: AsyncSession | None = None,
        engine_router: EngineRouter | None = None,
    ) -> None:
        # session：生产装配传入（commit 边界在 Service，B-T8R）；内存桩测试传 None
        self._repo = repo
        self._session = session
        self._router = engine_router

    async def _commit(self) -> None:
        if self._session is not None:
            await self._session.commit()

    async def _rollback(self) -> None:
        if self._session is not None:
            await self._session.rollback()

    def _session_or_raise(self) -> AsyncSession:
        """文档写路径必需请求作用域 session（内存桩测试仅覆盖读/建路径）。"""
        if self._session is None:
            raise InternalError("文档写路径缺少数据库会话装配")
        return self._session

    # ------------------------------------------------------------------ 写路径

    async def create_space(
        self, user_id: str, name: str, description: str = ""
    ) -> KnowledgeSpace:
        """创建空间；重名 IntegrityError → 30006（v0.3a，Service 层映射契约）。

        R0.5.2（F-4）：description 落库——此前契约声明该字段但 Service 只取 name，
        值被静默丢弃且前端消费恒为空。"""
        self._validate_name(name)
        self._validate_description(description)
        try:
            space = await self._repo.create(
                user_id=user_id, name=name, description=description
            )
            await self._commit()  # B-T8R：漏 commit → 请求末回滚 → 空间不持久化
            return space
        except IntegrityError as exc:
            # uq_space_user_name 冲突；session 由调用方（请求作用域）回收
            if "uq_space_user_name" in str(exc.orig or exc):
                raise SpaceNameConflictError("空间名称已存在") from exc
            raise

    async def update_space(self, user_id: str, space_id: str, description: str) -> dict:
        """R0.5.2（F-4）：改空间简介（当前唯一可变业务字段；name/is_public 各有专端点）。

        契约：取值非法 → 10005（先校验后取行，零副作用，与 update_doc_category 同纪律）；
        越权/无效空间 → 30004。传 "" 表示清空为「未填写」。"""
        return await self._update_space(space_id, description, owner=user_id)

    async def update_space_any(self, space_id: str, description: str) -> dict:
        """M3 批次 2（T5.3，A-2 叠加）：admin 跨用户改空间简介——不做归属校验。

        与 update_space 共用 _update_space 单一实现，仅放开归属判据（owner=None）。
        既有用户端点保持不动（A-2 裁定：零回归），admin 跨用户能力走 /admin/* 新端点。
        无效空间仍 → 30004（存在性判据不变），不校验调用者角色（授权在路由层）。
        """
        return await self._update_space(space_id, description)

    async def _update_space(
        self, space_id: str, description: str, owner: str | None = None
    ) -> dict:
        """简介写路径单一实现。owner=None 表示无归属约束（/admin 跨用户路径）。

        两条入口的全部差异就是这一处判据，不另写一份实现——否则简介校验顺序与
        commit 纪律会在两份拷贝里各自漂移。先校验后取行，非法取值在任何 DB 读之前拒绝。
        """
        self._validate_description(description)
        space = await self._repo.get_by_id(space_id)
        if space is None or (owner is not None and space.user_id != owner):
            raise ResourceNotFoundError(space_id)
        await self._repo.set_description(space_id, description)
        await self._commit()
        return {"id": space_id, "description": description}

    # ------------------------------------------------------------------ 删除（AB-T11）

    async def delete_space(
        self,
        user_id: str,
        space_id: str,
        kb_client: LangbotKbProto | None = None,
    ) -> dict[str, Any]:
        """删除空间（AB-T11）：先按引擎删库 → 成功才删 PG 行并提交；失败整体回滚。

        契约（AB-T11）：
        - 无效 id / 他人空间 → 30004（不泄露存在性，与详情端点同语义）；
        - 任务包③顺序：引擎 delete_kb 先行，PG 删除（docs/assets/space 行）仅在
          其成功后执行并 commit；delete_kb 抛任意异常 → session.rollback()（撤销
          本请求内一切未提交改动，PG 零残留）→ 原样上抛，由全局处理器转错误信封
          （引擎错误 30002/502、引擎 404=30004、不可达=50002/503）；
        - 空间尚无 KB（builtin 无 langbot_kb_uuid / 非 builtin 无 engine_kb_id）→
          无需删库，直接删 PG 提交；
        - 返回 {docs, assets, spaces} 删除计数（Route 层组装 {ok:true}）。

        BE-02：删库按 space.engine 分发——builtin 走 kb_client.delete_kb(langbot_kb_uuid)；
        非 builtin 走 router.adapter_for(space).delete_kb(engine_kb_id)（Key 缺失 → 10004）。
        """
        return await self._delete_space(space_id, kb_client, owner=user_id)

    async def delete_space_any(
        self,
        space_id: str,
        kb_client: LangbotKbProto | None = None,
    ) -> dict[str, Any]:
        """M3 批次 2（T5.8，A-2 叠加）：admin 跨用户删空间——不做归属校验。

        与 delete_space 共用 _delete_space 单一实现（引擎删库先行、失败整体回滚、
        级联删 docs/assets/space 行全部不变），仅放开归属判据。既有用户端点保持不动
        （A-2 裁定：零回归），admin 跨用户能力走 /admin/* 新端点。不校验调用者角色
        （授权在路由层，与本文件其余 _any 变体同纪律）。
        """
        return await self._delete_space(space_id, kb_client)

    async def _delete_space(
        self,
        space_id: str,
        kb_client: LangbotKbProto | None = None,
        owner: str | None = None,
    ) -> dict[str, Any]:
        """删空间单一实现。owner=None 表示无归属约束（/admin 跨用户路径）。

        C.5 引擎删除闭环：非 builtin 未实接引擎（adapter 不可用 / delete_kb 降级 no-op）
        不再整体回滚——清 engine_kb_id 本地映射，PG 级联删除继续，响应加 engineResidue=True
        标注引擎侧残留（WC adapter 层 delete_kb 降级的 service 层闭环）。
        builtin 走 kb_client.delete_kb（实接，失败仍整体回滚）。
        """
        space = await self._repo.get_by_id(space_id)
        if space is None or (owner is not None and space.user_id != owner):
            raise ResourceNotFoundError(space_id)

        engine = str(getattr(space, "engine", "builtin") or "builtin")
        engine_residue = False
        if engine == "builtin":
            kb_uuid = str(getattr(space, "langbot_kb_uuid", "") or "")
            if kb_uuid:
                if kb_client is None:  # 装配缺失：宁失败不误删 PG（防 PG 删了库没删）
                    raise InternalError("删除空间缺少 LangBot 客户端装配")
                try:
                    await kb_client.delete_kb(kb_uuid)  # LangBot 删库先行（任务包③）
                except Exception:
                    await self._rollback()  # 失败 → 整体回滚（防御性：撤销本请求未提交改动）
                    raise
        else:
            engine_kb_id = str(getattr(space, "engine_kb_id", "") or "")
            if engine_kb_id:
                if self._router is None:
                    engine_residue = True  # 无路由装配 → 无法删引擎侧，残留
                else:
                    try:
                        adapter = self._router.adapter_for(space)  # ValueError if not available
                        await adapter.delete_kb(engine_kb_id)
                        if not getattr(adapter, "implemented", True):
                            engine_residue = True  # adapter 降级 no-op，引擎侧残留
                    except ValueError:
                        # 引擎不可用（未实接/Key 缺）→ 不阻断删除（WC 降级闭环），
                        # 清本地映射，引擎侧残留。原实现此处 raise ForbiddenError 致空间无法删
                        engine_residue = True
                    except Exception:
                        await self._rollback()
                        raise  # 已实接引擎真实 API 故障 → 整体回滚（防 PG 删了库没删）
                # 清本地映射（space 行即将 cascade 删除，显式置空便于事务内审计可见）
                space.engine_kb_id = ""
        counts = await self._repo.delete_space_cascade(space_id)
        await self._commit()
        return {**counts, "engineResidue": engine_residue}

    async def delete_doc(
        self,
        user_id: str,
        space_id: str,
        doc_id: str,
        kb_client: LangbotKbProto | None = None,
    ) -> dict[str, int]:
        """删除单篇文档（R0.2.1）：引擎文件先删 → 成功才删 PG 行 → 失败整体回滚。

        顺序与 delete_space 同（引擎先行，防「PG 删了库没删」的孤儿文件）；
        builtin 走 kb_client.delete_kb_file（不经 EngineRouter，避免 allowlist 误配
        把 builtin 判为不可用而拦住删除——与 delete_space 的 builtin 分支同口径）。

        契约：
        - 无效/他人空间 → 30004；doc 不存在或不属该空间 → 30004（不泄露存在性）；
        - `langbot_file_id` 为空的 doc 无需引擎删除（公共库 link 引入的副本只建 PG 行、
          未上传引擎）——这是「跳过副本」的判定依据，而非 doc.source：所有 doc 的
          source 默认值都是 "copy"（entities.py），无法区分来源；
        - 引擎抛任意异常 → rollback 上抛，PG 零残留；
        - 资产按 NOT EXISTS 孤儿判定收敛删除（跨空间共享则保留）；
        - 返回 {docs, assets}。
        """
        return await self._delete_doc(space_id, doc_id, kb_client, owner=user_id)

    async def delete_doc_any(
        self,
        space_id: str,
        doc_id: str,
        kb_client: LangbotKbProto | None = None,
    ) -> dict[str, int]:
        """M3 批次 2（T5.3，A-2 叠加）：admin 跨用户删单篇文档——不做归属校验。

        与 delete_doc 共用 _delete_doc 单一实现（引擎先行、失败整体回滚、资产孤儿
        收敛、docCount 递减全部不变），仅放开归属判据。既有用户端点保持不动，
        admin 跨用户能力走 /admin/* 新端点。不校验调用者角色（授权在路由层）。
        """
        return await self._delete_doc(space_id, doc_id, kb_client)

    async def _delete_doc(
        self,
        space_id: str,
        doc_id: str,
        kb_client: LangbotKbProto | None = None,
        owner: str | None = None,
    ) -> dict[str, int]:
        """单篇删除单一实现。owner=None 表示无归属约束（/admin 跨用户路径）。

        owner 提供时非本人/无效空间 → 30004；两条入口的全部差异就是这一处判据。
        """
        space = await self._repo.get_by_id(space_id)
        if space is None or (owner is not None and space.user_id != owner):
            raise ResourceNotFoundError(space_id)

        doc = await DocumentRepository(self._session_or_raise()).get_by_id(doc_id)
        if doc is None or doc.space_id != space_id:
            raise ResourceNotFoundError(doc_id)

        try:
            counts = await self._delete_doc_core(space, doc, kb_client)
        except Exception:
            await self._rollback()
            raise
        await self._commit()
        return counts

    async def _delete_engine_file(
        self,
        space: KnowledgeSpace,
        doc: KnowledgeDocument,
        kb_client: LangbotKbProto | None,
    ) -> None:
        """引擎文件先删（外部副作用，且**无 DB 写在先**）；`langbot_file_id` 为空则跳过。

        单独成层：批量路径按此切分两阶段，引擎失败时无待回滚的 DB 状态——
        连续两篇失败若各回滚一次，async SQLAlchemy savepoint 会话会报 MissingGreenlet。

        结构性失败降级为告警（B34）：404 = 文件已不在引擎侧，删除意图已满足；
        405 = 该 LangBot 版本无文件级 DELETE 路由（v4.10.9 实测，重试永远无效）。
        两者继续删 PG 行都安全——ask() 候选集收窄（B25）只认 DB 行，已删 doc 的
        残留文件不可能进入检索结果与引用。5xx / 网络错误仍是硬失败，保住
        「引擎删失败则 PG 零残留」的原契约。
        """
        file_id = str(doc.langbot_file_id or "")
        if not file_id:
            return
        engine = str(getattr(space, "engine", "builtin") or "builtin")
        if engine == "builtin":
            kb_uuid = str(getattr(space, "langbot_kb_uuid", "") or "")
            if not kb_uuid:
                raise InternalError("空间尚无内置知识库标识，无法定位引擎文件")
            if kb_client is None:  # 装配缺失：宁失败不误删 PG
                raise InternalError("删除文档缺少 LangBot 客户端装配")
            delete_call = kb_client.delete_kb_file(kb_uuid, file_id)
        else:
            engine_kb_id = str(getattr(space, "engine_kb_id", "") or "")
            if not engine_kb_id:
                raise InternalError("空间尚无引擎知识库标识，无法定位引擎文件")
            if self._router is None:
                raise InternalError("删除文档缺少引擎路由装配")
            delete_call = self._router.adapter_for(space).delete_file(engine_kb_id, file_id)

        try:
            await delete_call
        except ResourceNotFoundError as exc:
            logger.warning(
                "引擎文件已不存在，跳过删除继续删本地行: kb_file=%s engine=%s err=%s",
                file_id,
                engine,
                str(exc)[:160],
            )
        except LangbotApiError as exc:
            if exc.upstream_status != 405:
                raise
            logger.warning(
                "引擎无文件级删除路由（405），继续删本地行（B25 已挡检索越界）: "
                "kb_file=%s engine=%s",
                file_id,
                engine,
            )

    async def _delete_doc_core(
        self,
        space: KnowledgeSpace,
        doc: KnowledgeDocument,
        kb_client: LangbotKbProto | None,
    ) -> dict[str, int]:
        """单篇删除核心：引擎文件先删 → 成功才删 PG 行 → 递减空间计数。

        不触碰事务状态（无 commit / rollback）——提交权完全归调用方。
        """
        await self._delete_engine_file(space, doc, kb_client)
        counts = await self._repo.delete_doc(doc.id)
        await self._repo.update_doc_count(space.id, -counts["docs"])
        return counts

    @staticmethod
    def _failure_entry(doc_id: str, exc: BaseException) -> dict[str, str | int]:
        """篇级失败明细：带已登记错误码，供前端按码映射友好文案。"""
        return {
            "docId": doc_id,
            "code": exc.code if isinstance(exc, AppError) else 50001,
            "error": exc.message if isinstance(exc, AppError) else str(exc),
        }

    async def update_doc_category(
        self,
        user_id: str,
        space_id: str,
        doc_id: str,
        category: str,
    ) -> dict[str, str]:
        """人工纠偏文档分类（R0.2.2）：仅改 category，不改正文。

        范围说明（数据模型决定，非偷懒）：category 是 **ContentAsset 级**属性（跨空间
        共享），故此处改写对本资产在其他空间的呈现一并生效；站内分类本就是资产级
        筛选维度。若需空间级覆盖须加 KnowledgeDocument.category_override 列（迁移），
        未立项——登记为 R0.5 候选而非在本批私自加列。

        另一处已知覆盖：号主改文使 content_hash 变化时，upsert_content 会按新内容
        重算 category（asset.py），人工值随之失效——不静默伪装成永久标签。

        契约：越权/无效空间或 doc → 30004；category 不在规则版六类或空串 → 10005。
        """
        validate_category(category)

        space = await self._repo.get_by_id(space_id)
        if space is None or space.user_id != user_id:
            raise ResourceNotFoundError(space_id)
        doc = await DocumentRepository(self._session_or_raise()).get_by_id(doc_id)
        if doc is None or doc.space_id != space_id:
            raise ResourceNotFoundError(doc_id)

        await AssetRepository(self._session_or_raise()).set_category(doc.asset_id, category)
        await self._commit()
        return {"docId": doc.id, "category": category or DEFAULT_CATEGORY}

    # ------------------------------------------------------------------ 批量写路径（R0.2.5）

    async def _normalize_doc_ids(self, raw_ids: list[str]) -> list[str]:
        """批量 id 归一化：strip → 丢弃空值 → 保序去重 → 空批/超上限 → 10005。

        与 BatchIngestService._normalize 同构的双层闸：路由侧 pydantic 只做体量硬闸
        （1..500，挡掉异常大的请求体），业务上限在本层走错误信封——避免同一份校验
        规则在路由与服务两层漂移。
        """
        seen: set[str] = set()
        ids: list[str] = []
        for raw in raw_ids or []:
            doc_id = str(raw).strip()
            if not doc_id or doc_id in seen:
                continue
            seen.add(doc_id)
            ids.append(doc_id)
        if not ids:
            raise SpaceValidationError("批量列表为空或全部无效，请至少提交一篇有效文档")
        max_ids = int(getattr(get_settings(), "batch_docs_max_ids", DEFAULT_MAX_DOC_IDS))
        if len(ids) > max_ids:
            raise SpaceValidationError(f"批量条数 {len(ids)} 超过单次上限 {max_ids}")
        return ids

    async def _resolve_owned_docs(
        self, space_id: str, ids: list[str], owner: str | None = None
    ) -> tuple[KnowledgeSpace, list[KnowledgeDocument]]:
        """取「本批 id 中确实存在且属于该空间」的 doc 行；有缺失 → 30004。

        缺失（不存在 / 不属该空间 / 他人空间）统一 30004 且不回显缺失明细——
        与单篇 DELETE/PATCH 同口径，不泄露存在性。按提交顺序返回，供前端对齐。

        owner=None 表示无归属约束（/admin 跨用户路径，批次 4）。「doc 属于所给
        空间」是数据事实校验，不随 owner 放开——否则可凭任意 doc_id 越界批量操作。
        """
        space = await self._repo.get_by_id(space_id)
        if space is None or (owner is not None and space.user_id != owner):
            raise ResourceNotFoundError(space_id)

        rows = await DocumentRepository(self._session_or_raise()).list_by_ids(ids)
        owned = {doc.id: doc for doc in rows if doc.space_id == space_id}
        if len(owned) != len(ids):
            raise ResourceNotFoundError(f"其中 {len(ids) - len(owned)} 篇文档不存在或不属于该空间")
        return space, [owned[doc_id] for doc_id in ids]

    async def delete_docs(
        self,
        user_id: str,
        space_id: str,
        raw_ids: list[str],
        kb_client: LangbotKbProto | None = None,
    ) -> dict[str, Any]:
        """批量删除文档（R0.2.5）：篇级部分成功，已删篇立即生效、失败篇可重试。"""
        return await self._delete_docs(space_id, raw_ids, kb_client, owner=user_id)

    async def delete_docs_any(
        self,
        space_id: str,
        raw_ids: list[str],
        kb_client: LangbotKbProto | None = None,
    ) -> dict[str, Any]:
        """M3 批次 4（T5.7，A-2 叠加）：admin 跨用户批量删文档——不做归属校验。

        与 delete_docs 共用 _delete_docs 单一实现（篇级部分成功、两阶段切分、逐篇
        提交、全批失败上抛首个异常全部不变），仅放开归属判据。既有用户端点保持不动，
        admin 跨用户能力走 /admin/* 新端点。不校验调用者角色（授权在路由层）。
        """
        return await self._delete_docs(space_id, raw_ids, kb_client)

    async def _delete_docs(
        self,
        space_id: str,
        raw_ids: list[str],
        kb_client: LangbotKbProto | None = None,
        owner: str | None = None,
    ) -> dict[str, Any]:
        """批量删除单一实现。owner=None 表示无归属约束（/admin 跨用户路径）。

        为什么不是整体事务（与单篇 DELETE 的 all-or-nothing 相反）：引擎文件删除是外部
        副作用，整体回滚会抹掉已成功的 PG 删除、同时留下引擎文件已删的孤儿——即「PG 有行
        但文件没了」，该 doc 此后每次重试都因文件不存在而失败，成为永久死档。逐篇提交则
        保证失败篇的 PG 行完整保留、可原样重试。

        两阶段切分（不可合并）：先做引擎删除，再做 PG 写。引擎失败时会话无 pending DB 写，
        无需回滚——连续两篇失败若各回滚一次，savepoint 会话会报 MissingGreenlet。

        请求形态错误仍整体拒绝且零副作用（10005 空批/超上限、30004 任一篇缺失或越权）——
        它们发生在任何引擎调用之前。

        契约：200 {requested, docs, assets, failed:[{docId, code, error}]}；failed 非空即
        部分成功；全批失败则上抛首个异常（保持原异常码位，如 30002/502）。
        """
        ids = await self._normalize_doc_ids(raw_ids)
        space, docs = await self._resolve_owned_docs(space_id, ids, owner=owner)

        total_docs = 0
        total_assets = 0
        failed: list[dict[str, str | int]] = []
        first_error: BaseException | None = None
        space_pk = space.id  # 事务边界前提取；项目会话 expire_on_commit=False（app/db.py）
        for doc in docs:
            doc_id = doc.id
            try:
                # 阶段 1：外部副作用（引擎文件删除），此时会话无 pending DB 写
                await self._delete_engine_file(space, doc, kb_client)
            except Exception as exc:
                if first_error is None:
                    first_error = exc
                failed.append(self._failure_entry(doc_id, exc))
                continue
            try:
                counts = await self._repo.delete_doc(doc_id)
                await self._repo.update_doc_count(space_pk, -counts["docs"])
                await self._commit()  # 逐篇提交：已删篇不被后续篇的失败回滚
            except Exception as exc:
                if first_error is None:
                    first_error = exc
                await self._rollback()
                failed.append(self._failure_entry(doc_id, exc))
                continue
            total_docs += counts["docs"]
            total_assets += counts["assets"]

        if total_docs == 0 and first_error is not None:
            raise first_error  # 全批失败走错误信封，避免「200 但一篇都没删」被误读为成功

        return {
            "requested": len(ids),
            "docs": total_docs,
            "assets": total_assets,
            "failed": failed,
        }

    async def recategorize_docs(
        self,
        user_id: str,
        space_id: str,
        raw_ids: list[str],
        category: str,
    ) -> dict[str, Any]:
        """批量人工纠偏文档分类（R0.2.5）：与单篇 PATCH 同语义，仅改 category，不改正文。"""
        return await self._recategorize_docs(space_id, raw_ids, category, owner=user_id)

    async def recategorize_docs_any(
        self,
        space_id: str,
        raw_ids: list[str],
        category: str,
    ) -> dict[str, Any]:
        """M3 批次 4（T5.7，A-2 叠加）：admin 跨用户批量改分类——不做归属校验。

        与 recategorize_docs 共用 _recategorize_docs 单一实现（整批原子、先校验后取行、
        资产级生效范围全部不变），仅放开归属判据。既有用户端点保持不动，admin 跨用户能力
        走 /admin/* 新端点。不校验调用者角色（授权在路由层）。
        """
        return await self._recategorize_docs(space_id, raw_ids, category)

    async def _recategorize_docs(
        self,
        space_id: str,
        raw_ids: list[str],
        category: str,
        owner: str | None = None,
    ) -> dict[str, Any]:
        """批量改分类单一实现。owner=None 表示无归属约束（/admin 跨用户路径）。

        整批原子（与批量删除的篇级部分成功相反）：本路径是纯 DB 写、无外部副作用，
        单事务即可；任一篇缺失或越权都整体回滚并 30004，不产生「改了一半」的中间态。

        范围说明承袭 update_doc_category：category 是 **ContentAsset 级**属性（跨空间
        共享），故本批改写对本资产在其他空间的呈现一并生效。

        契约：取值非法 → 10005（先校验后取行，零副作用）；越权/无效空间或任一篇缺失
        → 30004；200 {requested, docs, category}。
        """
        validate_category(category)
        ids = await self._normalize_doc_ids(raw_ids)
        _space, docs = await self._resolve_owned_docs(space_id, ids, owner=owner)

        await AssetRepository(self._session_or_raise()).set_category_many(
            [doc.asset_id for doc in docs], category
        )
        await self._commit()
        return {"requested": len(ids), "docs": len(ids), "category": category or DEFAULT_CATEGORY}

    # ------------------------------------------------------------------ 读路径（v0.3 视图）

    async def list_space_views(
        self, user_id: str, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict], int]:
        """GET /spaces → data.items 形状。

        AB-P004 P4：追加 engine/engineKbId/isPublic（ADR-0004 空间视图增量）。
        T1.5.3：doc 计数改 GROUP BY 单查询（原逐空间 count 为 N+1）。
        R0.5.2（F-4）：description 改由实体回读（原为硬编码空串，契约声明的字段恒为空）。
        C.1：LIMIT/OFFSET 下沉到 repo SQL，返回 (items, total)。"""
        spaces = await self._repo.list_by_user(user_id, limit=limit, offset=offset)
        total = await self._repo.count_by_user(user_id)
        counts = await self._repo.count_docs_many([s.id for s in spaces])
        return [self._space_view(s, counts.get(s.id, 0)) for s in spaces], total

    async def list_space_views_any(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict], int]:
        """GET /admin/spaces → 跨用户全量空间视图，每条带归属（批次 2 读面）。

        与 list_space_views 的全部差异只在归属约束：既有端点经 list_by_user 硬过滤本人，
        本方法取全量并把 owner 归属随空间同查（JOIN，单查询）。视图字段构造共用
        _space_view——engine/isPublic/description 这些增量字段在两份拷贝里各写一份会漂移
        （AB-P004 P4、R0.5.2 F-4 都是字段恒空/漏传的同类缺陷）。
        既有本人列表不带 owner 字段（owner=None 时不注入），契约零回归。
        C.1：LIMIT/OFFSET 下沉到 repo SQL，返回 (items, total)。
        """
        rows = await self._repo.list_with_owner(limit=limit, offset=offset)
        total = await self._repo.count_with_owner()
        counts = await self._repo.count_docs_many([s.id for s, _ in rows])
        return [self._space_view(s, counts.get(s.id, 0), owner=u) for s, u in rows], total

    @staticmethod
    def _space_view(space: KnowledgeSpace, doc_count: int, owner: User | None = None) -> dict:
        """空间视图的单一构造点（本人列表与 admin 跨用户列表共用）。"""
        view = {
            "id": space.id,
            "name": space.name,
            "description": str(space.description or ""),
            "docCount": doc_count,
            "updatedAt": _iso(space.updated_at),
            "engine": getattr(space, "engine", "builtin"),
            "engineKbId": getattr(space, "engine_kb_id", "") or "",
            "isPublic": bool(getattr(space, "is_public", False)),
        }
        if owner is not None:
            view["ownerId"] = owner.id
            view["ownerSub"] = owner.sub
            view["ownerNickname"] = owner.nickname
        return view

    async def get_space_view(self, user_id: str, space_id: str) -> dict:
        """GET /spaces/{id} → 详情形状；无效 id / 他人空间 → 30004（不泄露存在性）。

        AB-P004 P4：追加 engine/engineKbId/isPublic。
        T1.5.3：doc 计数单次取得（原 docCount 与 stats.docs 各查一次，同值双查）。
        R0.5.2（F-4）：description 改由实体回读（原为硬编码空串，契约声明的字段恒为空）；
        R0.5.3（F-5）：stats.chunks 可为 None。"""
        space = await self._repo.get_by_id(space_id)
        if space is None or space.user_id != user_id:
            raise ResourceNotFoundError(space_id)
        doc_count = await self._repo.count_docs(space.id)
        return {
            "id": space.id,
            "name": space.name,
            "description": str(space.description or ""),
            "docCount": doc_count,
            "createdAt": _iso(space.created_at),
            "updatedAt": _iso(space.updated_at),
            "stats": {
                "docs": doc_count,
                "chunks": await self._repo.count_chunks(space.id),
            },
            "engine": getattr(space, "engine", "builtin"),
            "engineKbId": getattr(space, "engine_kb_id", "") or "",
            "isPublic": bool(getattr(space, "is_public", False)),
        }

    async def list_space_docs(
        self,
        user_id: str,
        space_id: str,
        limit: int | None = None,
        offset: int = 0,
        category: str | None = None,
    ) -> tuple[list[dict], int]:
        """GET /spaces/{id}/docs → (items, total)；空间越权/无效 → 30004。

        T1.5.7：limit/offset 透传仓库层（None=全量向后兼容），total 独立计数，
        响应形状 {items,total,limit,offset}（items 键不变，旧调用方零回归）。
        R0.1.1：可选 category 过滤——哨兵 `__uncategorized__` 在本层译为空串精确匹配
        （库里不存哨兵值）；未登记的取值合法地返回空列表，读路径不设校验闸门。
        """
        return await self._list_space_docs(
            space_id, limit=limit, offset=offset, category=category, owner=user_id
        )

    async def list_space_docs_any(
        self,
        space_id: str,
        limit: int | None = None,
        offset: int = 0,
        category: str | None = None,
    ) -> tuple[list[dict], int]:
        """GET /admin/spaces/{id}/docs → admin 跨用户文档清单（批次 2 读面）。

        与 list_space_docs 的全部差异只在归属约束，故共用 _list_space_docs 单一实现
        （owner=None 表示无归属约束，承 delete_docs_any 手法）。无效空间仍 30004：
        不校验存在性会让「空间不存在」与「空间为空」无法区分，admin 会把前者当空库。
        不校验调用者角色（授权在路由层）。
        """
        return await self._list_space_docs(space_id, limit=limit, offset=offset, category=category)

    async def _list_space_docs(
        self,
        space_id: str,
        limit: int | None = None,
        offset: int = 0,
        category: str | None = None,
        owner: str | None = None,
    ) -> tuple[list[dict], int]:
        """文档清单单一实现。owner=None 表示无归属约束（/admin 跨用户路径）。

        归属判据与批次 2/4 写面同口径：space 缺失或 (owner 给定且不一致) → 30004，
        不泄露存在性，且发生在任何 doc 查询之前。
        """
        space = await self._repo.get_by_id(space_id)
        if space is None or (owner is not None and space.user_id != owner):
            raise ResourceNotFoundError(space_id)
        filtered = "" if category == UNCATEGORIZED else category
        rows = await self._repo.list_docs(
            space_id, limit=limit, offset=offset, category=filtered
        )
        total = await self._repo.count_docs(space_id, category=filtered)
        items = [
            {
                "id": row["id"],
                "title": row["title"],
                "source": row["source"],
                "status": doc_status_view(row["status"]),
                "updatedAt": _iso(row["updated_at"]),
                "category": row.get("category", ""),
            }
            for row in rows
        ]
        return items, total

    async def list_doc_categories(self, user_id: str, space_id: str) -> list[str]:
        """GET /spaces/{id}/docs:categories → 本空间**实际存在**的分类集合。

        R0.1.2：服务端枚举，替代前端按当前页数据推导——分页后单页推导会漏掉不在本页
        的分类（F-9 的另一半）。空空间返回空集合（不含哨兵：没有任何 doc 即没有「未分类」）。
        空间越权/无效 → 30004（与 docs 列表同口径，不泄露存在性）。
        """
        space = await self._repo.get_by_id(space_id)
        if space is None or space.user_id != user_id:
            raise ResourceNotFoundError(space_id)
        return order_categories(await self._repo.list_doc_categories(space_id))

    # ------------------------------------------------------------------ 保留 CRUD（B-T4 既有验收面）

    async def get_space(self, user_id: str, space_id: str) -> KnowledgeSpace | None:
        space = await self._repo.get_by_id(space_id)
        if space is None or space.user_id != user_id:
            return None
        return space

    async def list_spaces(self, user_id: str) -> list[KnowledgeSpace]:
        return await self._repo.list_by_user(user_id)

    @staticmethod
    def _validate_name(name: str) -> None:
        stripped = (name or "").strip()
        if not stripped:
            raise SpaceValidationError("空间名称不能为空")
        if len(stripped) > _SPACE_NAME_MAX:
            raise SpaceValidationError(f"空间名称超长（>{_SPACE_NAME_MAX}）")
        if any(ord(ch) < 32 for ch in stripped):
            raise SpaceValidationError("空间名称含非法控制字符")

    @staticmethod
    def _validate_description(description: str | None) -> None:
        """简介校验：空串合法（=「未填写简介」），故不做非空断言。"""
        stripped = (description or "").strip()
        if len(stripped) > _SPACE_DESC_MAX:
            raise SpaceValidationError(f"空间简介超长（>{_SPACE_DESC_MAX}）")
        if any(ord(ch) < 32 for ch in stripped):
            raise SpaceValidationError("空间简介含非法控制字符")
