"""B27 验收测试：重跑覆盖 langbot_file_id 前清理被取代的引擎文件（孤儿文件累积根因）。

证据链：某空间 KB 内 13 个引擎文件 vs DB 3 条 READY doc（missing=0 / ghost=10）。
根因是两条入库路径都用 `set_langbot_file_id` 覆盖指向而不删旧文件，旧文件永久滞留：
检索可命中已删/过期内容 + 向量库无界增长。

覆盖：
- 缓存命中重跑（生产主路径 `_reuse_cached_asset`）→ 删除**旧** id，DB 指向新 id；
- 全链覆盖写（`_persist_document`，含 hash 变化版本管理场景）→ 同语义；
- 404（引擎侧本就不存在）视为目标已达成，不重试不告警；
- 引擎不支持文件级 DELETE（LangBot v4.10.9 实测 405）→ 告警但不阻断入库，
  且 DB 指针仍指向引擎中真实存在的新文件（不悬空）。
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy import select
from test_langbot import BASE, _StubResolver

from app.core.errors import DependencyUnavailableError, LangbotApiError, ResourceNotFoundError
from app.models.entities import ContentAsset, KnowledgeDocument, Source
from app.providers.langbot.client import LangBotClient
from app.repositories.asset import AssetRepository, DocumentRepository
from app.repositories.space import SpaceRepository
from app.services.extractor import ExtractedContent
from app.services.kb import KnowledgeBaseService
from app.services.resolver import ResolvedArticle

URL_A = "https://mp.weixin.qq.com/s/p0-cache-001?biz=MjM5MjgwNTQ1MQ==&hid=h0"
KB_UUID = "kb-b27"


class _RecordingLangBot(LangBotClient):
    """LangBot 桩：每次上传返回递增 file_id；记录 delete_kb_file 调用；delete 可配注入失败。

    delete_status：none（默认成功）/ notfound（404→ResourceNotFoundError）/
    route405（v4.10.9 实测：路由不存在→LangbotApiError）/ unavailable（5xx→50002）。
    """

    def __init__(self, delete_status: str = "none") -> None:
        super().__init__(BASE, "a", "b", http=httpx.AsyncClient())
        self.deleted: list[tuple[str, str]] = []
        self.uploaded: list[str] = []
        self._n = 0
        self._delete_status = delete_status

    async def upload_document(self, filename: str, content: Any) -> str:
        self._n += 1
        file_id = f"lb-file-{self._n}"
        self.uploaded.append(file_id)
        return file_id

    async def trigger_ingest(self, kb_uuid: str, file_id: str) -> str:
        return ""

    async def delete_kb_file(self, kb_uuid: str, file_id: str) -> None:
        self.deleted.append((kb_uuid, file_id))
        if self._delete_status == "notfound":
            raise ResourceNotFoundError(file_id)
        if self._delete_status == "route405":
            raise LangbotApiError(f"LangBot 405: method not allowed (kb={kb_uuid})")
        if self._delete_status == "unavailable":
            raise DependencyUnavailableError("LangBot 5xx: 503")


async def _seed_space(db_session: Any, sub: str, name: str) -> Any:
    from app.models.entities import User

    user = User(sub=sub, email=f"{sub}@b27.local", nickname="B27")
    db_session.add(user)
    await db_session.flush()
    space = await SpaceRepository(db_session).create(user_id=user.id, name=name, langbot_kb_uuid=KB_UUID)
    await db_session.flush()
    return space


def _svc(db_session: Any, stub: _RecordingLangBot) -> KnowledgeBaseService:
    return KnowledgeBaseService(stub, db_session, _StubResolver())


async def _doc_file_id(db_session: Any, doc_id: str) -> str:
    return (
        await db_session.execute(select(KnowledgeDocument.langbot_file_id).where(KnowledgeDocument.id == doc_id))
    ).scalar_one()


async def test_reingest_cache_hit_deletes_superseded_engine_file(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """重跑（缓存命中，生产主路径）→ 删除旧 file_id、只留新文件，DB 指向新 id。"""
    space = await _seed_space(db_session, "sub-b27-reuse", "B27缓存重跑空间")
    stub = _RecordingLangBot()
    svc = _svc(db_session, stub)

    first = await svc.ingest_url(space.id, URL_A)
    assert first["langbotFileId"] == "lb-file-1"
    assert stub.deleted == []  # 首入库无前驱文件，不产生删除

    second = await svc.ingest_url(space.id, URL_A)
    assert second["hitCache"] is True
    assert second["langbotFileId"] == "lb-file-2"
    assert stub.deleted == [(KB_UUID, "lb-file-1")]  # 删旧不删新
    assert await _doc_file_id(db_session, second["docId"]) == "lb-file-2"
    assert second["docId"] == first["docId"]


async def test_persist_document_overwrite_purges_old_file(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """全链覆盖写（hash 变化版本管理场景）→ 同语义删除被取代文件。"""
    space = await _seed_space(db_session, "sub-b27-persist", "B27全链覆盖空间")
    stub = _RecordingLangBot()

    source = Source(type="wechat_oa", external_id="MjM5MjgwNTQ1MQ==", name="测试公众号", url=URL_A)
    db_session.add(source)
    await db_session.flush()
    asset = ContentAsset(
        source_id=source.id,
        external_id="p0-cache-001",
        url=URL_A,
        title="覆盖写文章",
        content_hash="hash-old",
        content_markdown="# 旧正文",
    )
    db_session.add(asset)
    await db_session.flush()
    doc = await DocumentRepository(db_session).create(asset_id=asset.id, space_id=space.id)
    await DocumentRepository(db_session).set_langbot_file_id(doc.id, "lb-file-old")
    await db_session.commit()

    extracted = ExtractedContent(
        title="覆盖写文章（已改）",
        author="测试公众号",
        publish_time=None,
        paragraphs=["新正文段落一", "新正文段落二"],
        langbot_format="# 新正文",
    )
    article = ResolvedArticle(
        title=extracted.title,
        author=extracted.author,
        publish_time=None,
        content="正文",
        url=URL_A,
        biz="MjM5MjgwNTQ1MQ==",
    )

    out = await _svc(db_session, stub)._persist_document(space.id, article, extracted, KB_UUID, "lb-file-new")

    assert stub.deleted == [(KB_UUID, "lb-file-old")]
    assert await _doc_file_id(db_session, out.id) == "lb-file-new"


@pytest.mark.parametrize(
    ("delete_status", "label"),
    [
        ("notfound", "引擎侧已不存在"),
        ("route405", "引擎不支持文件级删除"),
        ("unavailable", "引擎不可用"),
    ],
)
async def test_purge_failure_is_best_effort_and_does_not_break_ingest(
    db_session: Any, delete_status: str, label: str
) -> None:  # type: ignore[no-untyped-def]
    """清理失败不阻断入库：指针仍指向引擎中真实存在的新文件（不悬空），孤儿仅滞留。"""
    space = await _seed_space(db_session, f"sub-b27-{delete_status}", f"B27清理失败空间{label}")
    stub = _RecordingLangBot(delete_status=delete_status)
    svc = _svc(db_session, stub)

    first = await svc.ingest_url(space.id, URL_A)
    second = await svc.ingest_url(space.id, URL_A)

    assert stub.deleted == [(KB_UUID, first["langbotFileId"])]
    assert second["langbotFileId"] == "lb-file-2"
    assert await _doc_file_id(db_session, second["docId"]) == "lb-file-2"
    assert second["hitCache"] is True


async def test_asset_hash_stable_after_full_reingest(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """回归护栏：清理逻辑未改变正文指纹口径（重跑不得误标其他空间 doc 为过期）。"""
    space = await _seed_space(db_session, "sub-b27-hash", "B27指纹护栏空间")
    stub = _RecordingLangBot()
    svc = _svc(db_session, stub)

    await svc.ingest_url(space.id, URL_A)
    source = (
        await db_session.execute(
            select(Source).where(Source.type == "wechat_oa", Source.external_id == "MjM5MjgwNTQ1MQ==")
        )
    ).scalar_one()
    asset = await AssetRepository(db_session).get_by_source_external(source.id, "p0-cache-001")
    hash_before = asset.content_hash

    await svc.ingest_url(space.id, URL_A)
    asset = await AssetRepository(db_session).get_by_source_external(source.id, "p0-cache-001")
    assert asset.content_hash == hash_before  # 内容未变 → 指纹稳定
