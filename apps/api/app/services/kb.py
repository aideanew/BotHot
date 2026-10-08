"""知识库编排服务（B-T8）：空间 ↔ 引擎 KB 1:1（ADR-0001 内置默认 / ADR-0004 引擎可插拔）+ 单篇 ingest 全链。

事务约定：本 Service 是编排层，**显式 commit**（repo 只 flush；get_db 请求末回滚，
不 commit 即丢）——这是 B-T8 起写路径落库的既定边界。

状态机映射（本地 KnowledgeDocument ↔ 引擎文件状态）：
- 本地 FETCHED（已解析待入库）→ ingest 触发后置 INDEXED；
- 引擎 completed → 本地 READY；processing/pending → INDEXED（进行中）；
  failed/timeout → FAILED（上次错误记录 last_error，轮询抛 30003/502）。

引擎路由（BE-02）：ensure_kb/upload/status/delete 全走 EngineRouter（按 space.engine 分发）；
builtin 保持 LangBot 原行为零变更；非 builtin Key 未配置 → 10004/403 不可用语义。
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any, Protocol

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import (
    ExtractQualityLowError,
    ForbiddenError,
    IngestFailedError,
    LangbotApiError,
    ResourceNotFoundError,
    SourceUrlUnrecognizedError,
)
from app.models.entities import KnowledgeDocument, Source
from app.providers.engine_port import ENGINE_UNAVAILABLE_HINT, EngineRouter, KnowledgeEnginePort
from app.providers.langbot.client import LangBotClient
from app.providers.raw_store import RawStore, make_raw_store
from app.repositories.asset import AssetRepository, DocumentRepository
from app.repositories.space import SpaceRepository
from app.services.categorizer import categorize
from app.services.extractor import ExtractedContent, ExtractorService
from app.services.feed_service import on_article_indexed
from app.services.normalizer import normalize_extracted
from app.services.quality import score_quality
from app.services.resolver import SourceResolverService

logger = structlog.get_logger(__name__)

# LangBot 文件状态 → 本地文档状态机（SPEC §3.2 冻结映射 + timeout 同失败态）
_LB_STATUS_MAP = {
    "completed": "READY",
    "processing": "INDEXED",
    "pending": "INDEXED",
    "failed": "FAILED",
    "timeout": "FAILED",  # 超时同失败 → 30003/502（管理者口径 2026-09-11）
}


class _SpaceRepoProto(Protocol):
    async def set_langbot_kb_uuid(self, space_id: str, kb_uuid: str) -> None: ...


class KnowledgeBaseService:
    def __init__(
        self,
        client: LangBotClient,
        session: AsyncSession,
        resolver: SourceResolverService,
        settings: Settings | None = None,
        raw_store: RawStore | None = None,
        engine_router: EngineRouter | None = None,
    ) -> None:
        self._client = client
        self._session = session
        self._resolver = resolver
        self._settings = settings or get_settings()
        self._raw_store = raw_store or make_raw_store()
        self._router = engine_router or EngineRouter(self._settings, client)
        # AB-P004 P0：素材复用时直接上传缓存正文（零微信请求）
        self._reupload_cache_hits: list[dict[str, Any]] = []
        self._cache_hits: int = 0
        # R6.6.10（F-6）：并发同 URL 去重锁
        self._ingest_locks: dict[str, asyncio.Lock] = {}

    # -------------------------------------------------------------- 引擎路由（BE-02）

    def _adapter(self, space: Any) -> KnowledgeEnginePort:
        """按 space.engine 取适配器；不可用（Key 未配/未开放）→ 10004/403（不泄露细节）。"""
        try:
            return self._router.adapter_for(space)
        except ValueError as exc:
            raise ForbiddenError(str(exc) or ENGINE_UNAVAILABLE_HINT % getattr(space, "engine", "builtin")) from exc

    def _kb_id(self, space: Any) -> str:
        """空间当前引擎的 KB 标识；空 = 引擎未实接（非 builtin 未回填）→ 50002 语义 30002。"""
        kb_id = self._router.kb_id_for(space)
        if not kb_id:
            raise LangbotApiError(f"空间引擎 {getattr(space, 'engine', 'builtin')} 尚未建立知识库")
        return kb_id

    # -------------------------------------------------------------- 孤儿文件清理（B27）

    async def _purge_superseded_file(
        self, space_id: str, kb_uuid: str, doc: Any, new_file_id: str
    ) -> None:
        """重跑覆盖 langbot_file_id 前尽力删除被取代的引擎文件。

        覆盖不删会让旧文件永久滞留 KB：检索可命中已删/过期内容，向量库无界增长
        （实测该空间 KB 13 文件 vs DB 3 doc，10 个孤儿由此累积）。
        顺序「外部先删、DB 后写」：删除成功才回写 DB，故任何时刻 DB 指向的文件
        在引擎侧都真实存在。
        本步骤是清理副作用，非正确性前置——问答侧的正确性由 ask() 候选集收窄（B25）
        独立保证，故这里任何失败都只告警不阻断入库：LangBot v4.10.9 对文件级 DELETE
        返回 405（client.delete_kb_file 注释实测），若抛错则重采集整条链路不可用，
        严格劣于修复前；失败时新旧文件并存、指针不悬空，下次入库仍会重试。
        """
        old_file_id = str(getattr(doc, "langbot_file_id", "") or "")
        if not old_file_id or old_file_id == new_file_id:
            return
        space = await SpaceRepository(self._session).get_by_id(space_id)
        engine = "builtin" if space is None else str(getattr(space, "engine", "builtin") or "builtin")
        try:
            if engine == "builtin":
                await self._client.delete_kb_file(kb_uuid, old_file_id)
            else:
                await self._adapter(space).delete_file(kb_uuid, old_file_id)
        except Exception as exc:  # noqa: BLE001  # 清理失败不阻断入库，见函数说明
            logger.warning(
                "被取代的引擎文件清理失败（不阻断入库，B25 已挡检索越界）: "
                "kb=%s file=%s engine=%s err=%s",
                kb_uuid,
                old_file_id,
                engine,
                str(exc)[:160],
            )

    # -------------------------------------------------------------- 知识库 1:1

    async def ensure_kb(self, space_id: str, repo: SpaceRepository | None = None) -> str:
        """空间无 KB 则建库并回写引擎标识；幂等（ADR-0001 1:1，ADR-0004 按引擎双写）。

        builtin → 回写 langbot_kb_uuid（原路径）；非 builtin → 回写 engine_kb_id。
        """
        space_repo = repo or SpaceRepository(self._session)
        space = await space_repo.get_by_id(space_id)
        if space is None:
            raise ResourceNotFoundError(space_id)

        engine = str(getattr(space, "engine", "builtin") or "builtin")
        kb_id = self._router.kb_id_for(space)
        if kb_id:
            return kb_id

        if engine == "builtin":
            engine_id = await self._pick_engine()
            embedding_uuid = await self.ensure_embedding_model()
            kb_uuid = await self._client.create_kb(
                f"bothot-{space.name}", engine_id, embedding_uuid
            )
            await space_repo.set_langbot_kb_uuid(space.id, kb_uuid)
            await self._session.commit()  # 编排层提交（建库成功必须落库，防重复建库）
            return kb_uuid

        # 非 builtin：走端口 create_kb（Key 缺失时 _adapter 已拦 10004）
        adapter = self._adapter(space)
        engine_kb_id = await adapter.create_kb(space.name)
        space.engine_kb_id = engine_kb_id
        await self._session.commit()
        return engine_kb_id

    async def _pick_engine(self) -> str:
        """取第一个具备 doc_ingestion 能力的引擎插件 id（LangRAG）。"""
        for engine in await self._client.list_engines():
            caps = engine.get("capabilities") or engine.get("caps") or []
            if "doc_ingestion" in caps or engine.get("plugin_id"):
                pid = engine.get("plugin_id") or engine.get("id")
                if pid:
                    return str(pid)
        raise LangbotApiError("无可用知识引擎（LangRAG 未安装？）")

    async def ensure_embedding_model(self) -> str:
        """按 config（embedding_api_base/model）匹配已注册模型；缺失则注册 provider+模型。

        compose env 已注入硅基流动 Key，但模型注册是独立 API 步骤（M0 仅注册过
        fake-embed），故此处做幂等自举。清单形状：data.models[]，provider 内嵌。
        """
        models = await self._client.list_embedding_models()
        for model in models:
            provider = model.get("provider") or {}
            if provider.get("base_url", "").rstrip("/") == self._settings.embedding_api_base.rstrip("/"):
                uuid = model.get("uuid")
                if uuid:
                    return str(uuid)
        provider_uuid = await self._client.register_provider(
            "bothot-embedding",
            self._settings.embedding_api_base,
            self._settings.embedding_api_key,
        )
        return await self._client.register_embedding_model(self._settings.embedding_model, provider_uuid)

    # -------------------------------------------------------------- 单篇 ingest 全链

    async def ingest_url(self, space_id: str, url: str) -> dict[str, Any]:
        """URL → resolve → extract → normalize → score → KB 入库（异步任务）。

        返回 {docId, title, status, langbotFileId, taskId}（v0.3g 备案形状）。
        R6.6.10（F-6）：并发同 URL 按空间+URL 加锁，避免双份微信请求。
        """
        lock_key = f"{space_id}:{url}"
        lock = self._ingest_locks.setdefault(lock_key, asyncio.Lock())
        async with lock:
            return await self._ingest_url_inner(space_id, url)

    async def _ingest_url_inner(self, space_id: str, url: str) -> dict[str, Any]:
        repo = SpaceRepository(self._session)
        space = await repo.get_by_id(space_id)
        if space is None:
            raise ResourceNotFoundError(space_id)

        # BE-02 前置引擎可用性检查：非 builtin 且 Key 未配/未开放 → 10004/403，
        # 在 resolve 之前拦截（不浪费一次微信抓取才拒绝）
        engine = str(getattr(space, "engine", "builtin") or "builtin")
        if engine != "builtin":
            if not self._router.available(engine):
                raise ForbiddenError(ENGINE_UNAVAILABLE_HINT % engine)

        # AB-P004 P0①：URL 归一——短链先查映射表（0 请求），未落映射才走真实抓取（唯一网络请求点）；
        # 长链 0 额外请求；最终 article_key 以直抓后 URL 末段为准（与 _persist_document 口径一致）
        norm_url = url
        is_short = _is_short_link(url)
        short_key = _short_link_key(url)
        # D-04/L-01：短链已落映射 → 直接取长链 article_key 锚（0 请求，不重复反解）
        mapped_article_key = await self._lookup_short_link(short_key) if short_key else ""
        if mapped_article_key:
            norm_url = url  # 保持短链原文（资产 url 列语义不变）
            article_key = mapped_article_key
        else:
            article_key = _article_key(norm_url)
        asset_repo = AssetRepository(self._session)
        source = await self._find_source_by_anchor(article_key, norm_url)

        # AB-P004 P0②：先查后抓——同 (source,external) 有 READY 资产 → 0 微信请求，直接复用
        if source is not None:
            cached = await asset_repo.get_by_source_external(source.id, article_key)
            # BE-02 D-2/D-3 兼容存量：source 以页面 biz 落库（external_id=biz）而资产以
            # article_key 落库时，上查询失配——按「该源下 URL 含 article_key」兜底查资产
            if cached is None:
                cached = await asset_repo.get_by_url_fragment(source.id, article_key)
            if cached is not None and cached.status == "READY":
                self._cache_hits += 1
                await asset_repo.hit(cached)
                # 短链归一：资产 url 列写最终长链（去重键统一锚点；长链场景 url 不变）
                if is_short:
                    cached.url = norm_url
                    cached.raw_uri = cached.url
                kb_uuid = await self.ensure_kb(space.id, repo)
                doc, file_id = await self._reuse_cached_asset(space.id, cached, kb_uuid, asset_repo)
                await self._session.commit()
                return {
                    "docId": doc.id,
                    "title": cached.title,
                    "status": "INDEXED",
                    "langbotFileId": file_id,
                    "taskId": "",
                    "hitCache": True,
                    "hitCount": int(cached.hit_count or 0),
                }
        # P0③：未命中 → 抓取解析（唯一真实网络请求点；短链跳转后 article.url 即稳定长链）
        # R6.3.5：单篇路径有限重试（1~2 次指数退避，仅对网络类错误重试；业务错误不重试）
        article = await self._resolve_with_retry(norm_url)
        extracted = normalize_extracted(ExtractorService().extract(article))
        verdict = score_quality(extracted)
        if not verdict.passed:
            # v0.3h④：低质 → 20003/422（与 B-T6/B-T7 护栏同码），非 30003/502
            raise ExtractQualityLowError(f"内容质量不足 qualityScore={verdict.score}：{verdict.reasons[0]}")

        # D-04/L-01：短链首次抓取后落映射（短链 key → 长链 article_key），同文两形态二次 0 请求
        if short_key:
            final_key = _article_key(article.url)
            if final_key and final_key != short_key:
                await self._save_short_link(short_key, final_key, article.biz)

        # P0④：号主改文版本管理——旧 asset 存在且 hash 变化 → version+1，旧 doc 标 superseded
        if source is not None:
            stale = await asset_repo.get_by_source_external(source.id, article_key)
            if stale is None:  # BE-02 D-2/D-3 兼容存量：biz 锚源按 URL 兜底
                stale = await asset_repo.get_by_url_fragment(source.id, article_key)
            new_hash = _hash(extracted.langbot_format)
            if stale is not None and stale.content_hash and stale.content_hash != new_hash:
                # F-11：按新正文指纹跨空间判定过期（不按本空间过滤，见 mark_stale_docs）
                await asset_repo.mark_stale_docs(stale.id, new_hash)

        # 2) KB 就绪（1:1，按引擎路由）
        kb_uuid = await self.ensure_kb(space.id, repo)

        # 3) 上传 langbotFormat 文本 → 触发异步 ingest（按 space.engine 分发；builtin 原路径零变更）
        filename = _safe_filename(extracted.title) + ".md"
        engine = str(getattr(space, "engine", "builtin") or "builtin")
        if engine == "builtin":
            # v0.3h①：LangBot v4.10.9 无 task_id，轮询走文件清单——返回值仅触发用，
            # 契约字段 taskId 恒空串（前端禁止依赖其非空）
            file_id = await self._client.upload_document(filename, extracted.langbot_format)
            await self._client.trigger_ingest(kb_uuid, file_id)
        else:
            adapter = self._adapter(space)
            file_id = await adapter.upload_file(kb_uuid, filename, extracted.langbot_format)

        # 4) 本地资产/文档落库（source by biz upsert；doc = asset↔space 映射）
        doc = await self._persist_document(space.id, article, extracted, kb_uuid, file_id)
        await self._session.commit()

        return {
            "docId": doc.id,
            "title": extracted.title,
            "status": "INDEXED",  # 已触发异步入库
            "langbotFileId": file_id,
            "taskId": "",  # SPEC §3.1 冻结：恒空串（形状稳定位）
            "hitCache": False,  # AB-P004 P0：缓存未命中，本次为真实抓取
            "hitCount": 0,
        }

    _RESOLVE_MAX_ATTEMPTS = 3
    _RESOLVE_BACKOFF_BASE = 1.0

    async def _resolve_with_retry(self, norm_url: str):
        """R6.3.5：单篇路径有限重试（指数退避，仅网络类错误重试）。"""
        last_exc: Exception | None = None
        for attempt in range(self._RESOLVE_MAX_ATTEMPTS):
            try:
                return await self._resolver.resolve(norm_url)
            except (SourceUrlUnrecognizedError, ExtractQualityLowError):
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < self._RESOLVE_MAX_ATTEMPTS - 1:
                    await asyncio.sleep(self._RESOLVE_BACKOFF_BASE * (2 ** attempt))
        raise last_exc  # type: ignore[misc]

    async def _find_source_by_anchor(self, article_key: str, url: str) -> Source | None:
        """先 biz 参数锚、后 article_key 锚查既有 source；未命中再按「源 URL 含该 article_key」兜底。

        BE-02 D-2/D-3 修复：无 biz 参数短链首抓后 source.external_id=article_key（见
        _ensure_source 同口径），二次入库以 article_key 锚必然命中；对历史遗留
        （source.external_id=页面 biz 且 URL 含 article_key）做 URL 兜底，兼容存量数据。
        """
        for anchor in (a for a in (_biz_from_url(url), article_key) if a):
            row = (
                await self._session.execute(
                    select(Source).where(
                        Source.type == "wechat_oa",
                        Source.external_id == anchor,
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                return row
        # 兜底：源 URL 含当前 article_key（历史 biz 锚 source 行，其 url 列带原文链接）
        row = (
            await self._session.execute(
                select(Source).where(
                    Source.type == "wechat_oa",
                    Source.url.like(f"%{article_key}%"),
                )
            )
        ).scalar_one_or_none()
        return row

    async def _lookup_short_link(self, short_key: str) -> str:
        """D-04/L-01：短链 key → 长链 article_key（映射未落则空串，走真实抓取路径）。"""
        from app.models.entities import ShortLinkMap

        if not short_key:
            return ""
        row = (
            await self._session.execute(
                select(ShortLinkMap.article_key).where(ShortLinkMap.short_key == short_key)
            )
        ).scalar_one_or_none()
        return row or ""

    async def _save_short_link(self, short_key: str, article_key: str, biz: str = "") -> None:
        """短链映射幂等落库（uq_shortlink_key：同短链重复入库不重插）。"""
        from app.models.entities import ShortLinkMap

        if not short_key or not article_key:
            return
        exists = (
            await self._session.execute(
                select(ShortLinkMap.id).where(ShortLinkMap.short_key == short_key)
            )
        ).scalar_one_or_none()
        if exists is None:
            self._session.add(ShortLinkMap(short_key=short_key, article_key=article_key, biz=biz or ""))
            await self._session.flush()

    async def _reuse_cached_asset(
        self, space_id: str, asset: Any, kb_uuid: str, asset_repo: AssetRepository
    ) -> tuple[KnowledgeDocument, str]:
        """P0 复用：以 asset.content_markdown 直传引擎（零微信请求），doc 覆盖 file_id 重走 ingest。"""
        filename = _safe_filename(asset.title) + ".md"
        space = await SpaceRepository(self._session).get_by_id(space_id)
        engine = str(getattr(space, "engine", "builtin") or "builtin") if space else "builtin"
        if engine == "builtin":
            file_id = await self._client.upload_document(filename, asset.content_markdown)
            await self._client.trigger_ingest(kb_uuid, file_id)
        else:
            adapter = self._adapter(space)  # type: ignore[arg-type]
            file_id = await adapter.upload_file(kb_uuid, filename, asset.content_markdown)
        doc_repo = DocumentRepository(self._session)
        doc = await doc_repo.get_by_asset_space(asset.id, space_id)
        if doc is None:
            doc = await doc_repo.create(asset_id=asset.id, space_id=space_id)
        # 本路径以 asset.content_markdown 直传引擎，故 doc 入库的即资产当前正文——
        # 指纹必须同步，否则该 doc 会被下一次 mark_stale_docs 误判为落后。
        await self._purge_superseded_file(space_id, kb_uuid, doc, file_id)
        await doc_repo.set_langbot_file_id(doc.id, file_id)
        await doc_repo.set_content_hash(doc.id, asset.content_hash)
        await doc_repo.set_status(doc.id, "INDEXED")
        # W2：文章入库后写 FeedItem(article) + 发 new_article 事件（feed_service upsert）
        await on_article_indexed(self._session, asset, space_id)
        self._reupload_cache_hits.append({"asset_id": asset.id, "file_id": file_id, "kb": kb_uuid})
        return doc, file_id

    async def _persist_document(
        self, space_id: str, article: Any, extracted: ExtractedContent, kb_uuid: str, file_id: str
    ) -> KnowledgeDocument:
        """source（按 biz 幂等）→ asset（hash 幂等）→ document（FETCHED→INDEXED）。

        AB-P004 P0：upsert 时透传既有 hit_count（防盲写 0 冲掉命中计数）。"""
        url = article.url
        source = await self._ensure_source(article.biz, extracted, url)
        asset_repo = AssetRepository(self._session)
        prior = await asset_repo.get_by_source_external(source.id, _article_key(url))
        hit_count = int(prior.hit_count or 0) if prior is not None else 0
        # BE-02：raw_uri 走存储抽象（默认 url 透传零回归；local 后端落盘可切换）
        raw_uri = await self._raw_store.save(
            url=url, content_markdown=extracted.langbot_format, title=extracted.title
        )
        asset, _ = await asset_repo.upsert_content(
            source_id=source.id,
            external_id=_article_key(url),
            url=url,
            title=extracted.title,
            author=extracted.author,
            content_markdown=extracted.langbot_format,
            content_hash=_hash(extracted.langbot_format),
            raw_uri=raw_uri,
            quality_score=float(score_quality(extracted).score),
            # T3.2.2：采集时规则版分类赋值（标题+正文；hash 变化路径会随内容重算）
            category=categorize(extracted.title, extracted.langbot_format),
            status="READY",
            hit_count=hit_count,
        )
        doc_repo = DocumentRepository(self._session)
        doc = await doc_repo.get_by_asset_space(asset.id, space_id)
        if doc is None:
            try:
                async with self._session.begin_nested():
                    doc = await doc_repo.create(asset_id=asset.id, space_id=space_id)
            except IntegrityError:
                doc = await doc_repo.get_by_asset_space(asset.id, space_id)
                if doc is None:
                    raise
        # 同资产重复入库：覆盖 file_id 重走 ingest，指纹对齐本次 upsert 写入的正文
        await self._purge_superseded_file(space_id, kb_uuid, doc, file_id)
        await doc_repo.set_langbot_file_id(doc.id, file_id)
        await doc_repo.set_content_hash(doc.id, asset.content_hash)
        await doc_repo.set_status(doc.id, "INDEXED")
        # W2：文章入库后写 FeedItem(article) + 发 new_article 事件（feed_service upsert）
        await on_article_indexed(self._session, asset, space_id)
        return doc

    async def _ensure_source(self, biz: str, extracted: ExtractedContent, url: str) -> Source:
        """公众号源按 biz 幂等（uq_source_type_external）；biz 缺失降级用 article_key 锚。

        BE-02 D-2/D-3 兼容：biz 非空仍以 biz 为 external_id（订阅语义 + P0 测试锚点）；
        biz 缺失（无参数 URL）时以 article_key 落库——短链场景二次入库经
        _find_source_by_anchor 的 URL 兜底可命中。
        """
        external_id = biz or _article_key(url)
        row = (
            await self._session.execute(
                select(Source).where(Source.type == "wechat_oa", Source.external_id == external_id)
            )
        ).scalar_one_or_none()
        if row is not None:
            return row
        # T2.7 竞态兜底：同 URL 并发首抓时两个事务都可能走到这里，先查后插的
        # 后发者会撞 uq_source_type_external——savepoint 捕获 IntegrityError 后
        # 回滚该插入并重查既有行（DB 唯一约束保证零重复，兜底保证不 500 冒泡）。
        try:
            async with self._session.begin_nested():
                source = Source(
                    type="wechat_oa", external_id=external_id,
                    name=extracted.author or "未知公众号", url=url,
                )
                self._session.add(source)
                await self._session.flush()
        except IntegrityError:
            row = (
                await self._session.execute(
                    select(Source).where(
                        Source.type == "wechat_oa", Source.external_id == external_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:  # 非常见冲突（非唯一约束）如实上抛，不做掩盖
                raise
            return row
        return source

    # -------------------------------------------------------------- ingest 状态查询

    async def get_doc_ingest_status(self, space_id: str, doc_id: str) -> dict[str, Any]:
        """以引擎文件状态为准刷新本地状态并返回（v0.3g 备案形状）。

        BE-02：builtin 走 LangBot 文件清单（原路径零变更）；非 builtin 走 adapter.ingest_status。
        """
        space_repo = SpaceRepository(self._session)
        space = await space_repo.get_by_id(space_id)
        if space is None:
            raise ResourceNotFoundError(space_id)
        engine = str(getattr(space, "engine", "builtin") or "builtin")
        kb_id = self._router.kb_id_for(space)
        if not kb_id:
            raise ResourceNotFoundError(space_id)
        doc_repo = DocumentRepository(self._session)
        doc = await doc_repo.get_by_id(doc_id)
        if doc is None or doc.space_id != space_id:
            raise ResourceNotFoundError(doc_id)  # 他人空间/无效 id 同语义，不泄露存在性

        status, last_error = doc.status, doc.last_error or ""
        if doc.langbot_file_id and doc.status in ("FETCHED", "INDEXED"):
            if engine == "builtin":
                lb_status = await self._poll_file_status(kb_id, doc.langbot_file_id)
            else:
                adapter = self._adapter(space)
                lb_status = await adapter.ingest_status(kb_id, doc.langbot_file_id)
            mapped = _LB_STATUS_MAP.get(lb_status)
            if mapped and mapped != doc.status:
                await doc_repo.set_status(doc.id, mapped, last_error=lb_status)
                await self._session.commit()
            status = mapped or doc.status
            if lb_status == "failed":
                last_error = "LangBot ingest failed"
        if status == "FAILED":
            raise IngestFailedError(last_error or "ingest 失败")
        return {"docId": doc.id, "status": status, "langbotFileId": doc.langbot_file_id}

    async def _poll_file_status(self, kb_uuid: str, file_id: str) -> str:
        """单文件状态探测（无轮询等待——由客户端重试驱动的拉模式，避免请求内长阻塞）。"""
        for entry in await self._client.list_kb_files(kb_uuid):
            # 实测 v4.10.9：文件身份在 file_name（= 上传返回的 file_id），uuid 另有所指
            identity = str(entry.get("file_name") or entry.get("uuid") or entry.get("id"))
            if identity == file_id:
                return str(entry.get("status", "unknown"))
        return "unknown"


# ------------------------------------------------------------------ 内部工具


def _article_key(url: str) -> str:
    """URL → 文章幂等键（末段；短链跳转后即稳定 id）。"""
    tail = re.sub(r"[?&#].*$", "", url).rstrip("/").rsplit("/", 1)[-1]
    return tail or url


def _hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_short_link(url: str) -> bool:
    """短链判定（表面归一，0 额外请求）：mp.weixin.qq.com/s/{key} 形态。

    SPEC §四 口径：短链直抓一次得 biz——抓取由 resolver（follow_redirects=True）完成，
    本函数只做形态识别；最终 article_key 以直抓后 URL 末段为锚。"""
    return "/s/" in url and "mp.weixin.qq.com" in url


def _short_link_key(url: str) -> str:
    """短链 key（/s/{key} 末段）；非短链返回空串。

    AB-P004 D-04/L-01：短链与长链可能同指一篇文章（不同短链/长链形态），
    以「短链 key → 长链 article_key」映射落库后，两形态二次入库均 0 请求。"""
    if not _is_short_link(url):
        return ""
    from urllib.parse import urlparse

    path = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    return path or ""


def _biz_from_url(url: str) -> str:
    """URL 中的 biz 参数（短链/长链 query 携带）；无则空串。"""
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(url).query)
    val = qs.get("biz", [""])
    return val[0] if val else ""


def _safe_filename(title: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "_", title.strip())[:80]
    return cleaned or f"article_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
