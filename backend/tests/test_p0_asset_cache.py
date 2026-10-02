"""AB-P004 P0 资产缓存验收测试：先查后抓 + hit_count + 版本管理（复用 test_langbot 桩风格，零真实网络请求）。

机器门口径（T-016）：
- ① 命中复用不抓：同一 URL 第二次 ingest_url 不产生 resolver 网络请求，hit_count 自增；
- ② hash 变化 version+1 且旧 doc 标 superseded；
- ③ hit_count 计数 SQL 直查。
"""

from __future__ import annotations

from sqlalchemy import select
from test_langbot import _client, _lb_transport, _StubResolver  # noqa: F401  (桩工厂复用)

from app.models.entities import ContentAsset, KnowledgeDocument, Source
from app.repositories.asset import AssetRepository
from app.repositories.space import SpaceRepository
from app.services.kb import KnowledgeBaseService
from app.services.resolver import ResolvedArticle

# T-016 修复（测试写法缺陷①）：URL 携 biz 锚参数——P0 锚点设计为「biz 参数锚 +
# article_key 兜底」（kb._find_source_by_anchor），裸长链无 biz 参数时首抓落库的
# source 行以页面 biz（MjM5MjgwNTQ1MQ==）为 external_id，二次入库先查必然失配。
# URL_A 对齐带 biz 短链形态后，机器门①③可在不改生产逻辑下自洽（②的门面缺口
# 属生产设计缺陷 D-2/D-3，见 t016-analysis.md，由 worker-b 修复）。
URL_A = "https://mp.weixin.qq.com/s/p0-cache-001?biz=MjM5MjgwNTQ1MQ==&hid=h0"


class _CountingStubResolver(_StubResolver):
    """记录抓取次数：命中缓存路径必须 0 次（机器门①的判据）。"""

    def __init__(self) -> None:
        super().__init__()
        self.fetch_count = 0

    async def resolve(self, raw_url: str) -> ResolvedArticle:
        self.fetch_count += 1
        article = await super().resolve(raw_url)
        # 短链跳转后 url 即稳定长链——按 P0 口径：article_key 取最终 URL 末段
        article.url = raw_url
        return article


def _svc(db_session, resolver=None):
    return KnowledgeBaseService(_client(), db_session, resolver or _CountingStubResolver())


async def _seeder_space(db_session, name: str):
    """upsert 用户锚（sub=p0-ab004）：连库夹具外层事务回滚后用户行仍可能被既有测试残留占用，
    故幂等 upsert 而非固定 sub 盲插。"""
    from app.repositories.user import SqlAlchemyUserStore

    store = SqlAlchemyUserStore(db_session)
    user = await store.upsert_by_sub("sub-p0-ab004", "p0ab004@test.local", "P0-AB004")
    space = await SpaceRepository(db_session).create(user_id=user.id, name=name)
    await db_session.commit()
    return user, space


def _biz_anchor() -> str:
    """SAMPLE_RICH 中 biz = MjM5MjgwNTQ1MQ==（与既有测试同一锚点口径）。"""
    return "MjM5MjgwNTQ1MQ=="


def _article_key(url: str) -> str:
    import re

    return re.sub(r"[?&#].*$", "", url).rstrip("/").rsplit("/", 1)[-1] or url


async def _asset(db_session, url: str) -> ContentAsset:
    """按 biz 锚定位 source 行，再按 (source_id, article_key) 直查资产。

    T-016 修复（测试写法缺陷）：旧实现把 biz 字符串误当 source_id 传入
    get_by_source_external，永远查空 → ②③ 两用例误判"asset 不存在"。
    """
    source = (
        await db_session.execute(select(Source).where(Source.type == "wechat_oa", Source.external_id == _biz_anchor()))
    ).scalar_one()
    asset = await AssetRepository(db_session).get_by_source_external(source.id, _article_key(url))
    assert asset is not None
    return asset


async def test_p0_second_ingest_is_zero_fetch_reuse(db_session) -> None:  # type: ignore[no-untyped-def]
    """机器门①：同一 URL 第二次入库 0 微信请求（resolver 不进入抓取），hitCache=True。"""
    user, space = await _seeder_space(db_session, "P0缓存空间")
    resolver = _CountingStubResolver()
    svc = _svc(db_session, resolver)

    first = await svc.ingest_url(space.id, URL_A)
    assert first["hitCache"] is False
    assert first["hitCount"] == 0
    assert resolver.fetch_count == 1  # 第一次真实抓取

    second = await svc.ingest_url(space.id, URL_A)
    assert resolver.fetch_count == 1  # 第二次 0 网络请求（先查后抓命中 READY 资产）
    assert second["hitCache"] is True
    assert second["hitCount"] == 1  # hit_count 0→1
    assert second["docId"] == first["docId"]  # 同资产同空间复用同一 doc 行

    third = await svc.ingest_url(space.id, URL_A)
    assert third["hitCache"] is True and third["hitCount"] == 2
    assert resolver.fetch_count == 1


async def test_p0_hash_change_bumps_version_and_stales_old_doc(db_session) -> None:  # type: ignore[no-untyped-def]
    """机器门②：号主改文（正文 hash 变化）→ asset.version+1，旧 doc 标 FAILED/superseded。"""
    user, space = await _seeder_space(db_session, "P0版本空间")
    svc = _svc(db_session)
    await svc.ingest_url(space.id, URL_A)

    asset = await _asset(db_session, URL_A)
    old_hash, old_version = asset.content_hash, asset.version
    old_doc_id = (
        await db_session.execute(
            select(KnowledgeDocument.id).where(
                KnowledgeDocument.asset_id == asset.id, KnowledgeDocument.space_id == space.id
            )
        )
    ).scalar_one()
    await db_session.commit()

    # 机器门②：号主改文走非命中路径——asset 已 READY 但 hash 变化 → version+1 + 旧 doc superseded。
    # 命中路径绕过 resolver，直接用 AssetRepository.upsert_content 模拟号主改文后的 upsert 行为，
    # 验证 version+1 与 mark_stale_docs 联动。

    from app.repositories.asset import AssetRepository
    from app.services.kb import _hash

    asset_repo = AssetRepository(db_session)
    old_asset = await _asset(db_session, URL_A)
    new_md = "# 号主追加的新正文版本\n素材资产化版本管理验证段落。"
    new_hash = _hash(new_md)
    assert new_hash != old_hash

    asset2, updated = await asset_repo.upsert_content(
        source_id=old_asset.source_id,
        external_id=_article_key(URL_A),
        url=URL_A,
        title="号主改文新版",
        author="样本作者",
        content_markdown=new_md,
        content_hash=new_hash,
        raw_uri=URL_A,
        quality_score=80.0,
        status="READY",
        hit_count=0,
    )
    assert updated is True, "hash 变化应触发 upsert（version+1）"
    assert asset2.version == old_version + 1, f"version 应递增：{asset2.version} != {old_version + 1}"
    assert asset2.content_hash != old_hash, "hash 应变化（号主改文）"
    assert asset2.hit_count == 0, "新内容版本 hit_count 归零"

    # 旧 doc 应被 mark_stale_docs 标 FAILED/superseded（按新正文指纹判定，见 R4.4/F-11）
    stale_count = await asset_repo.mark_stale_docs(old_asset.id, new_hash)
    assert stale_count >= 1, f"旧 doc 应被标 superseded（{stale_count} 条）"
    stale_doc = await db_session.get(KnowledgeDocument, old_doc_id)
    assert stale_doc is not None
    assert stale_doc.status == "FAILED" and stale_doc.last_error == "superseded"

    asset2 = await _asset(db_session, URL_A)  # T-016 修复（测试写法缺陷②）：同 _asset 修法
    assert asset2 is not None
    assert asset2.version == old_version + 1
    assert asset2.content_hash != old_hash

    stale_doc = await db_session.get(KnowledgeDocument, old_doc_id)
    assert stale_doc is not None
    assert stale_doc.status == "FAILED" and stale_doc.last_error == "superseded"


async def test_f11_hash_change_stales_docs_across_spaces(db_session) -> None:  # type: ignore[no-untyped-def]
    """R4.4（F-11）：号主改文覆写全局共享 asset → 他人空间的 doc 也必须标 superseded。

    资产按 `uq_asset_source_external` 全局共享（无 user_id），号主改文覆写的是所有
    空间共用的那一行。旧 `mark_stale_docs(asset_id, space_id)` 按调用方空间过滤，
    他人空间的 doc 会静默指向已变正文——无错误、无告警、无 stale 标记。现按内容
    指纹跨空间判定，两个方向都要锁住：跨空间不漏标、已对齐新版的 doc 不误标。
    """
    from app.repositories.user import SqlAlchemyUserStore
    from app.services.kb import _hash

    store = SqlAlchemyUserStore(db_session)
    owner_a = await store.upsert_by_sub("sub-f11-owner-a", "f11a@test.local", "F11-A")
    owner_b = await store.upsert_by_sub("sub-f11-owner-b", "f11b@test.local", "F11-B")
    space_a = await SpaceRepository(db_session).create(user_id=owner_a.id, name="F11空间A")
    space_b = await SpaceRepository(db_session).create(user_id=owner_b.id, name="F11空间B")
    await db_session.commit()

    resolver = _CountingStubResolver()
    svc = _svc(db_session, resolver)
    first = await svc.ingest_url(space_a.id, URL_A)  # A 首抓 → asset V1
    second = await svc.ingest_url(space_b.id, URL_A)  # B 复用同一 asset → 同正文

    # F-11 的前提：两个空间的 doc 指向同一行 asset（不同 doc 行，同 asset）
    assert second["hitCache"] is True
    assert second["docId"] != first["docId"]
    assert resolver.fetch_count == 1, "B 应走缓存命中（零真实抓取）"

    asset = await _asset(db_session, URL_A)
    old_version = asset.version  # 须在 upsert 前取：upsert 返回的是同一行实例（identity map）
    docs = dict(
        (
            await db_session.execute(
                select(KnowledgeDocument.space_id, KnowledgeDocument.id).where(KnowledgeDocument.asset_id == asset.id)
            )
        ).all()
    )
    assert set(docs) == {space_a.id, space_b.id}
    await db_session.commit()

    new_md = "# 号主改文新版\n跨空间 stale 判定验证段落。"
    new_hash = _hash(new_md)
    assert new_hash != asset.content_hash

    repo = AssetRepository(db_session)
    asset2, updated = await repo.upsert_content(
        source_id=asset.source_id,
        external_id=_article_key(URL_A),
        url=URL_A,
        title="号主改文新版",
        author="样本作者",
        content_markdown=new_md,
        content_hash=new_hash,
        raw_uri=URL_A,
        quality_score=80.0,
        status="READY",
        hit_count=0,
    )
    assert updated is True and asset2.version == old_version + 1

    # 方向一（不漏标）：两个空间的旧 doc 全标，A 自己的也不例外
    assert await repo.mark_stale_docs(asset2.id, new_hash) == 2
    for doc_id in docs.values():
        doc = await db_session.get(KnowledgeDocument, doc_id)
        assert doc is not None
        assert doc.status == "FAILED" and doc.last_error == "superseded"
    await db_session.commit()

    # 方向二（不误标）：B 重抓一次即对齐当前正文，此后不再被标 stale
    third = await svc.ingest_url(space_b.id, URL_A)
    assert third["hitCache"] is True
    assert resolver.fetch_count == 1, "重抓仍应走缓存命中"
    doc_b = await db_session.get(KnowledgeDocument, docs[space_b.id])
    assert doc_b is not None
    assert doc_b.status == "INDEXED"
    assert doc_b.content_hash == (await _asset(db_session, URL_A)).content_hash
    assert await repo.mark_stale_docs(asset2.id, new_hash) == 0, "已对齐新版的 doc 不得被误标"

    # A 的 doc 仍为 FAILED：无人替它重抓，分叉仍然存在——但现在是可见的，不再静默
    doc_a = await db_session.get(KnowledgeDocument, docs[space_a.id])
    assert doc_a is not None and doc_a.status == "FAILED"


async def test_p0_hit_count_counter_increments(db_session) -> None:  # type: ignore[no-untyped-def]
    """机器门③：hit_count 为资产级命中计数（首抓不算命中），SQL 直查。"""
    user, space = await _seeder_space(db_session, "P0计数空间")
    svc = _svc(db_session)
    await svc.ingest_url(space.id, URL_A)
    for _ in range(2):
        await svc.ingest_url(space.id, URL_A)

    asset = await _asset(db_session, URL_A)
    assert int(asset.hit_count) == 2  # 两次命中（首抓 hitCount=0 起算）
    await db_session.commit()
