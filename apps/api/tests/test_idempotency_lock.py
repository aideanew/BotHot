"""T2.7 幂等回归锁定：kb.py 五层链 + asset.py version/superseded + uq 约束簇 + 同 URL 并发竞态。

机器门口径（大纲 v1.4 §8.1 T2.7）：
- ① 短链映射层：短链首抓落 ShortLinkMap（short→long article_key），二次同短链 0 抓取；
- ② READY 缓存层：同 URL 二次 ingest hitCache=True、resolver 0 网络请求；
- ③ uq_doc_asset_space 层：同资产同空间恒单 doc 行（应用级收敛断言）；
- ④ version+1 层：号主改文 → version+1、旧 doc FAILED/superseded（既有 test_p0 覆盖，此处并入全链）；
- ⑤ 公共库 copy 层：已 copy 的 doc 二次 link 全 skipped；
- ⑥ 并发竞态：同 URL 并发 ingest 收敛为单 asset+单 doc，无未捕获 IntegrityError；
- ⑦ 空公共空间 link：0 抄，不得退化为「全系统 READY 资产」（跨用户数据越界）。

桩复用 test_langbot/test_p0_asset_cache 风格，零真实网络请求。
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, func, select, text
from test_langbot import _client, _StubResolver  # noqa: F401  (桩复用)
from test_p0_asset_cache import _CountingStubResolver, _svc  # noqa: F401  (桩复用)

from app.models.entities import (
    ContentAsset,
    KnowledgeDocument,
    KnowledgeSpace,
    ShortLinkMap,
    Source,
    User,
)
from app.repositories.asset import AssetRepository
from app.repositories.space import SpaceRepository
from app.repositories.user import SqlAlchemyUserStore
from app.services.article_identity import canonical_article_key
from app.services.kb import _short_link_key
from app.services.public_library import PublicLibraryService
from app.services.resolver import ResolvedArticle

# 短链 + 长链两形态（同文）：短链解析后指向长链末段 long-key-001
SHORT_URL = "https://mp.weixin.qq.com/s/short-key-t27?biz=MjM5MjgwNTQ1MQ==&hid=t27"
LONG_URL = "https://mp.weixin.qq.com/s/long-key-001?biz=MjM5MjgwNTQ1MQ==&hid=t27"
# 键一律现取自生产真源（S2.3.1），不写末段字面量：字面量在规范键上线后会拿**旧键**查
# **新行**，红得像是"实现坏了"，实际是测试前提过期——@ci run 38889655890 的 6 条红全部源于此。
LONG_KEY = canonical_article_key(LONG_URL)
# `short_link_maps.short_key` 与 S2.2.4 的只读兜底锚都用**裸 token**（`_short_link_key` 不经
# 规范键，迁移前后同形），所以这一条保持字面量才是对的，不是漏改。
SHORT_KEY = "short-key-t27"
# 映射表里 LONG_URL 那一支的 short_key：`_is_short_link` 是 `/s/` 子串判，所以形态上像长链的
# 夹具 URL 也会被当短链并落一行映射——键一律现取自生产函数，免得测试里再养一份形状判断。
LONG_MAP_KEY = _short_link_key(LONG_URL)

# T2.7 自身命名空间（清理夹具按此收敛，绝不触碰命名空间外数据）
# DSN 允许环境变量覆盖：CI 无 PG 时走 skip 分支，本地/CI service container 可指向他处
PG_DSN = os.environ.get("AIDEANBOT_TEST_PG_DSN", "postgresql+psycopg://bothot:bothot@localhost:5433/bothot")
_T27_USER_SUBS = ("sub-t27-idem", "sub-t27-race", "sub-t27-f22")
# 清理集要同时覆盖规范键与迁移前的裸 token：本机的 PG 可能留有直写上线前的行，
# 只清新键会让旧行残留继续影响 `_find_source_by_anchor` 的第三条锚。
_T27_ASSET_KEYS = (SHORT_KEY, LONG_KEY, canonical_article_key(SHORT_URL), "long-key-001")
_T27_SOURCE_BIZ = "MjM5MjgwNTQ1MQ=="
_T27_SPACE_PREFIX = "T27"


@pytest.fixture(autouse=True)
def _require_pg() -> None:
    """PG 不可达 → skip（与 conftest db_session 同口径）。

    必要性：并发竞态用例自建真提交连接、不经 db_session 夹具，若无本守卫则 CI
    （无 PG）会以 ConnectionError **报错**而非 skip，把门禁染红——"并入 CI 必跑集"
    的前提是该文件在无 PG 环境下**体面跳过**。
    """
    try:
        engine = create_engine(PG_DSN, connect_args={"connect_timeout": 3})
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
    except Exception as exc:  # noqa: BLE001 不可达统一 skip 并标注原因
        pytest.skip(f"PG 不可达（{type(exc).__name__}），Docker 引擎恢复后复跑本用例")


def _purge_t27() -> None:
    """清理 T2.7 自有残留，保证本套件可重复运行。

    必要性（缺陷根因）：本套断言依赖**全局**资产态（`external_id=LONG_KEY` 的 READY
    资产）与固定空间名，而 `db_session` 夹具是外层事务回滚隔离——唯有并发竞态用例走
    独立真提交连接会留下持久行。任一次中途失败即残留，二次运行必撞
    `uq_space_user_name` / `uq_source_type_external`，并让 `fetch_count==1` 断言落空。
    幂等回归套件自身若不幂等，其绿灯即不可信，故用例前后各清一次。
    PG 不可达时静默返回（由 db_session 夹具统一 skip 并标注原因）。
    """
    try:
        engine = create_engine(PG_DSN, connect_args={"connect_timeout": 3})
    except Exception:  # noqa: BLE001 引擎不可用交由夹具 skip
        return
    try:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM short_link_maps WHERE short_key = ANY(:ks)"),
                {"ks": [SHORT_KEY, LONG_MAP_KEY]},
            )
            conn.execute(
                text("DELETE FROM content_assets WHERE external_id = ANY(:ks)"),
                {"ks": list(_T27_ASSET_KEYS)},
            )
            # 用户级联清 spaces/subscriptions/jobs/job_items/docs（FK ondelete=CASCADE）
            conn.execute(text("DELETE FROM users WHERE sub = ANY(:ss)"), {"ss": list(_T27_USER_SUBS)})
            conn.execute(text("DELETE FROM knowledge_spaces WHERE name LIKE :p"), {"p": f"{_T27_SPACE_PREFIX}%"})
            # 孤儿 source（ingest 自动建，FK 指向 sources 的资产已删）
            conn.execute(
                text(
                    "DELETE FROM sources WHERE type = 'wechat_oa' AND external_id = :biz "
                    "AND NOT EXISTS (SELECT 1 FROM content_assets a WHERE a.source_id = sources.id)"
                ),
                {"biz": _T27_SOURCE_BIZ},
            )
    except Exception:  # noqa: BLE001 清理失败不掩盖用例本身的判定
        return
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def _t27_isolation() -> Iterator[None]:
    """用例级隔离：前后各清一次 T2.7 命名空间，使套件幂等可重复。"""
    _purge_t27()
    yield
    _purge_t27()


class _ShortToLongResolver(_CountingStubResolver):
    """短链→长链跳转桩：输入短链/长链一律返回 LONG_URL 末段，模拟真实跳转。
    计数由父类 _CountingStubResolver.resolve 负责（本类不再自增，避免双重计数）。"""

    async def resolve(self, raw_url: str) -> ResolvedArticle:
        article = await super().resolve(raw_url)  # 父类 fetch_count+=1 且置 url=raw_url
        article.url = LONG_URL  # 跳转后 url 即稳定长链
        return article


def _article_key(url: str) -> str:
    """测试侧取键：**必须与生产同一真源**（S2.3.1）。

    这里曾是自己 `re.sub` 复刻的一份末段算法——生产改口径后，本文件会拿旧键去查新写入的行，
    表现为"测试前提变了"而不是"实现坏了"，属于最难查的那一类假失败。
    键算法本身的判定力在 `test_article_identity.py` 与 `test_batch_ingest_key_drift.py`，
    不在这里重复一份实现。
    """
    return canonical_article_key(url)


async def _seeder(db_session, name: str):
    """upsert 用户 + get-or-create 空间（双重幂等：sub 唯一锚 + uq_space_user_name 兜底）。

    原实现直接 create 固定名空间，二次运行必撞 uq_space_user_name——即便夹具已清场，
    此处仍收敛为 get-or-create，杜绝"夹具失效即崩"的单点依赖。
    """
    store = SqlAlchemyUserStore(db_session)
    user = await store.upsert_by_sub("sub-t27-idem", "t27@test.local", "T27")
    space = (
        await db_session.execute(
            select(KnowledgeSpace).where(KnowledgeSpace.user_id == user.id, KnowledgeSpace.name == name)
        )
    ).scalar_one_or_none()
    if space is None:
        space = await SpaceRepository(db_session).create(user_id=user.id, name=name)
    await db_session.commit()
    return user, space


async def _count_rows(db_session, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    for w in where:
        stmt = stmt.where(w)
    return int((await db_session.execute(stmt)).scalar_one())


# ---------- ① 短链映射层 ----------


async def test_short_link_map_created_and_reused_zero_fetch(db_session) -> None:  # type: ignore[no-untyped-def]
    """短链首抓落映射；二次同短链 0 抓取（映射 + READY 复用双链生效）。"""
    user, space = await _seeder(db_session, "T27短链空间")
    resolver = _ShortToLongResolver()
    svc = _svc(db_session, resolver)

    first = await svc.ingest_url(space.id, SHORT_URL)
    assert first["hitCache"] is False
    assert resolver.fetch_count == 1  # 首抓 1 次

    # 映射落库（short → long article_key）
    mapping = (
        await db_session.execute(select(ShortLinkMap).where(ShortLinkMap.short_key == SHORT_KEY))
    ).scalar_one_or_none()
    assert mapping is not None, "短链映射应落库"
    assert mapping.article_key == LONG_KEY

    # 资产落库键 = 长链的**规范键**（与 `_persist_document` 的 `_article_key(url)` 同口径）
    asset = (
        await db_session.execute(select(ContentAsset).where(ContentAsset.external_id == LONG_KEY))
    ).scalar_one_or_none()
    assert asset is not None, "资产应按长链 article_key 落库"

    second = await svc.ingest_url(space.id, SHORT_URL)
    assert resolver.fetch_count == 1, "二次短链必须 0 抓取（映射命中复用）"
    assert second["hitCache"] is True
    assert second["docId"] == first["docId"]


# ---------- ②③ READY 缓存 + uq 单 doc 收敛 ----------


async def test_full_chain_double_ingest_single_doc_row(db_session) -> None:  # type: ignore[no-untyped-def]
    """全链：同 URL 二次 ingest → 恒单 asset + 单 doc（uq_doc_asset_space 应用级收敛）。"""
    user, space = await _seeder(db_session, "T27全链空间")
    resolver = _CountingStubResolver()
    svc = _svc(db_session, resolver)

    await svc.ingest_url(space.id, LONG_URL)
    await svc.ingest_url(space.id, LONG_URL)
    assert resolver.fetch_count == 1  # 二次 0 抓取

    asset = (await db_session.execute(select(ContentAsset).where(ContentAsset.external_id == LONG_KEY))).scalar_one()
    doc_count = await _count_rows(
        db_session,
        KnowledgeDocument,
        KnowledgeDocument.asset_id == asset.id,
        KnowledgeDocument.space_id == space.id,
    )
    assert doc_count == 1, f"uq_doc_asset_space 应保证单 doc，实际 {doc_count}"


# ---------- ④ version+1 superseded（并入全链：改文路径） ----------


async def test_content_change_bumps_version_and_stales(db_session) -> None:  # type: ignore[no-untyped-def]
    """号主改文（hash 变化）→ version+1 + 旧 doc FAILED/superseded（T2.7 回归锁定）。"""
    from app.services.kb import _hash

    user, space = await _seeder(db_session, "T27版本空间")
    svc = _svc(db_session, _CountingStubResolver())
    await svc.ingest_url(space.id, LONG_URL)

    asset0 = (await db_session.execute(select(ContentAsset).where(ContentAsset.external_id == LONG_KEY))).scalar_one()
    old_version = asset0.version
    old_doc_id = (
        await db_session.execute(
            select(KnowledgeDocument.id).where(
                KnowledgeDocument.asset_id == asset0.id,
                KnowledgeDocument.space_id == space.id,
            )
        )
    ).scalar_one()
    await db_session.commit()

    new_md = "# T2.7 改文新版\n版本管理回归锁定段落。"
    new_hash = _hash(new_md)
    asset_repo = AssetRepository(db_session)
    asset1, updated = await asset_repo.upsert_content(
        source_id=asset0.source_id,
        external_id=LONG_KEY,
        url=LONG_URL,
        title="改文新版",
        author="样本作者",
        content_markdown=new_md,
        content_hash=new_hash,
        raw_uri=LONG_URL,
        quality_score=80.0,
        status="READY",
        hit_count=0,
    )
    assert updated is True and asset1.version == old_version + 1
    stale = await asset_repo.mark_stale_docs(asset1.id, new_hash)
    assert stale >= 1
    old_doc = await db_session.get(KnowledgeDocument, old_doc_id)
    assert old_doc is not None and old_doc.status == "FAILED"
    assert old_doc.last_error == "superseded"


# ---------- ⑤ 公共库 copy 幂等 ----------


async def test_public_copy_second_link_all_skipped(db_session) -> None:  # type: ignore[no-untyped-def]
    """公共库 link 幂等：二次 link 已 copy 的 doc 全 skipped（copied=0, skipped≥1）。"""
    owner, pub_space = await _seeder(db_session, "T27公共空间")
    # 置 is_public=1：正规 API create_public_space（is_public=1 + owner_type=system，双闸语义）
    pub_name = "T27公共库系统空间"
    pub_space = (
        await db_session.execute(
            select(KnowledgeSpace).where(KnowledgeSpace.user_id == owner.id, KnowledgeSpace.name == pub_name)
        )
    ).scalar_one_or_none()
    if pub_space is None:
        pub_space = await SpaceRepository(db_session).create_public_space(owner.id, pub_name)
    await db_session.commit()

    # 公共空间入一篇 READY 资产 + doc
    resolver = _CountingStubResolver()
    svc = _svc(db_session, resolver)
    await svc.ingest_url(pub_space.id, LONG_URL)

    # 目标用户空间
    target_user, target = await _seeder(db_session, "T27目标空间")

    pl = PublicLibraryService(db_session)
    first = await pl.link_public_space(target_user.id, target.id, pub_space.id)
    assert first["copied"] >= 1, f"首次 link 应至少 copy 1 篇，实际 {first}"

    second = await pl.link_public_space(target_user.id, target.id, pub_space.id)
    assert second["copied"] == 0, f"二次 link 应 0 新增，实际 {second}"
    assert second["skipped"] >= 1, f"二次 link 应全 skipped，实际 {second}"
    assert second["total"] == first["total"]


async def test_public_copy_empty_public_space_copies_nothing(db_session) -> None:  # type: ignore[no-untyped-def]
    """⑦ 空公共空间 link → 0 抄：不得退化为「全系统 READY 资产」。

    历史回退条件 `id.in_(ids) if ids else status == 'READY'` 在公共空间无 doc 时选中
    **全部** READY 资产，把其他用户空间的私有资产抄进请求者空间——跨用户数据越界，
    也违背本模块「不误抄全局其他资产」的契约口径。
    """
    # 干扰项：另一用户空间的私有 READY 资产——旧实现下会被错误抄走
    stranger = await SqlAlchemyUserStore(db_session).upsert_by_sub("sub-t27-f22", "f22@test.local", "F22")
    stranger_space = await SpaceRepository(db_session).create(user_id=stranger.id, name="T27F22私有空间")
    await _svc(db_session, _CountingStubResolver()).ingest_url(stranger_space.id, LONG_URL)

    pub_owner, _ = await _seeder(db_session, "T27F22空公共库")
    pub_space = await SpaceRepository(db_session).create_public_space(pub_owner.id, "T27F22空公共库系统空间")
    target_user, target = await _seeder(db_session, "T27F22目标空间")
    await db_session.commit()

    result = await PublicLibraryService(db_session).link_public_space(target_user.id, target.id, pub_space.id)
    assert result == {"copied": 0, "skipped": 0, "total": 0}, result

    copied = (
        await db_session.execute(
            select(func.count()).select_from(KnowledgeDocument).where(KnowledgeDocument.space_id == target.id)
        )
    ).scalar_one()
    assert copied == 0, f"空公共空间不得抄任何 doc（含他人私有资产），实际 {copied} 篇"


# ---------- ⑥ 并发竞态收敛 ----------


async def test_concurrent_same_url_converges(db_session) -> None:  # type: ignore[no-untyped-def]
    """同 URL 并发 ingest → 收敛为单 asset + 单 doc，无未捕获 IntegrityError 冒泡（竞态兜底）。

    注意：夹具 savepoint 事务对独立连接不可见，故预置与清理走独立真提交连接；
    收敛断言用独立只读连接读已提交数据（MVCC 口径）。
    """
    from sqlalchemy.ext.asyncio import (
        async_sessionmaker,
        create_async_engine,
    )

    engine = create_async_engine(PG_DSN, pool_pre_ping=True, connect_args={"connect_timeout": 3})
    RaceSession = async_sessionmaker(bind=engine, expire_on_commit=False)

    # 预置用户+空间（真提交，供并发连接可见）；空间 get-or-create 防上一轮残留
    setup = RaceSession()
    space_id = user_id = ""
    try:
        store = SqlAlchemyUserStore(setup)
        user = await store.upsert_by_sub("sub-t27-race", "t27race@test.local", "T27RACE")
        space = (
            await setup.execute(
                select(KnowledgeSpace).where(KnowledgeSpace.user_id == user.id, KnowledgeSpace.name == "T27竞态空间")
            )
        ).scalar_one_or_none()
        if space is None:
            space = await SpaceRepository(setup).create(user_id=user.id, name="T27竞态空间")
        await setup.commit()
        space_id, user_id = space.id, user.id
    finally:
        await setup.close()

    async def _run(label: str) -> tuple[str, str | None]:
        try:
            session = RaceSession()
            svc2 = _svc(session, _CountingStubResolver())
            await svc2.ingest_url(space_id, LONG_URL)
            await session.close()
            return label, None  # 成功无错误
        except Exception as exc:  # noqa: BLE001 竞态面如实捕获上报
            return label, f"{type(exc).__name__}: {str(exc)[:120]}"

    results = await asyncio.gather(_run("A"), _run("B"))
    errors = [(label, err) for label, err in results if err is not None]
    print(f"[T2.7 并发竞态登记] errors={errors}")

    # 收敛断言（独立只读连接读已提交数据）
    with create_engine(PG_DSN, connect_args={"connect_timeout": 3}).connect() as conn:
        final_assets = conn.execute(
            select(func.count()).select_from(ContentAsset).where(ContentAsset.external_id == LONG_KEY)
        ).scalar_one()
        final_docs = conn.execute(
            select(func.count()).select_from(KnowledgeDocument).where(KnowledgeDocument.space_id == space_id)
        ).scalar_one()

    # 清理（零残留）：doc → asset → source → space → user
    # 注：必须用 RaceSession（异步工厂）；模块级 Session 是同步会话，await 必炸
    cleanup = RaceSession()
    try:
        await cleanup.execute(KnowledgeDocument.__table__.delete().where(KnowledgeDocument.space_id == space_id))
        await cleanup.execute(ContentAsset.__table__.delete().where(ContentAsset.external_id == LONG_KEY))
        await cleanup.execute(
            Source.__table__.delete().where(Source.type == "wechat_oa", Source.external_id == _T27_SOURCE_BIZ)
        )
        await cleanup.execute(KnowledgeSpace.__table__.delete().where(KnowledgeSpace.id == space_id))
        await cleanup.execute(User.__table__.delete().where(User.id == user_id))
        await cleanup.commit()
    finally:
        await cleanup.close()
    await engine.dispose()

    assert final_assets == 1, f"并发应收敛单 asset，实际 {final_assets}"
    assert final_docs == 1, f"并发应收敛单 doc，实际 {final_docs}"
    assert not errors, f"并发竞态不得未捕获异常冒泡（应被生产兜底收敛），实际 {errors}"


class _BarrieredResolver(_ShortToLongResolver):
    """两条并发各自 resolve 完之后才继续——把"都还查不到映射行"的那一刻钉住。

    `test_concurrent_same_url_converges` 判的是 asset/doc 收敛，是否踩到映射双写取决于时序，
    它在 `@ci` 上就是间歇红的（run 38908795127 红在这里）。对齐之后两条都会 select 到空、
    然后各自 insert ⇒ 后发者**必然**撞 `uq_shortlink_key`，兜底在不在位一测就分得开。
    带 timeout 是因为对手若在中途炸掉，没有超时的 wait 会把用例挂成 CI 超时（U-23 那种形状）。
    """

    def __init__(self, gate: asyncio.Barrier) -> None:
        super().__init__()
        self._gate = gate

    async def resolve(self, raw_url: str) -> ResolvedArticle:
        article = await super().resolve(raw_url)
        await asyncio.wait_for(self._gate.wait(), timeout=25)
        return article


async def test_concurrent_short_link_map_write_is_absorbed(db_session) -> None:  # type: ignore[no-untyped-def]
    """同 URL 并发首抓时，短链映射的后写者必须被 savepoint 吞掉，不得把 IntegrityError 冒到调用面。

    真实缺陷（`@ci` run 38908795127，`test_concurrent_same_url_converges` 实测）：
    `_save_short_link` 是"先查后插"而无并发兜底，两个事务都查到空 ⇒ 后发者撞
    `uq_shortlink_key`，异常冒泡成 HTTP 500。S2.2.3 之后写入条件恒真（规范键带 `s:` 前缀，
    永不等于裸 token），每个短链首抓都落一行，这条路径的并发量从偶发变常态。

    与 `test_concurrent_same_url_converges` 的分工：那条判 asset/doc 收敛（时序相关，
    间歇暴露本洞），这条判**映射写入的兜底**（barrier 对齐，确定性暴露）。
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    map_key = LONG_MAP_KEY
    assert map_key, "LONG_URL 取不到 short_key，本用例的写入点就不存在"

    engine = create_async_engine(PG_DSN, pool_pre_ping=True, connect_args={"connect_timeout": 3})
    RaceSession = async_sessionmaker(bind=engine, expire_on_commit=False)

    setup = RaceSession()
    try:
        store = SqlAlchemyUserStore(setup)
        user = await store.upsert_by_sub("sub-t27-idem", "t27@test.local", "T27")
        space = (
            await setup.execute(
                select(KnowledgeSpace).where(
                    KnowledgeSpace.user_id == user.id, KnowledgeSpace.name == "T27映射竞态空间"
                )
            )
        ).scalar_one_or_none()
        if space is None:
            space = await SpaceRepository(setup).create(user_id=user.id, name="T27映射竞态空间")
        await setup.commit()
        space_id = space.id
    finally:
        await setup.close()

    gate = asyncio.Barrier(2)
    resolver = _BarrieredResolver(gate)

    # 正证据：数一数到底有几条 INSERT 打到映射表。两次 = 两边都查空、后发者真的撞了唯一约束；
    # 一次 = 某一方在 select 时就看见了对手已提交的行而早退 ⇒ 本次并没有走到竞态，
    # 用例对此**明说**（skip 并报原因），绝不把"没测到"读成"通过"（U-20 的口径）。
    from sqlalchemy import event

    insert_attempts: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _count_inserts(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if "INSERT INTO short_link_maps" in statement:
            insert_attempts.append(statement)

    async def _one(tag: str) -> tuple[str, str]:
        try:
            session = RaceSession()
            try:
                svc = _svc(session, resolver)
                out = await svc.ingest_url(space_id, LONG_URL)
            finally:
                await session.close()
            return tag, str(out.get("docId") or "")
        except BaseException as exc:  # noqa: BLE001 竞态面如实上报，不掩盖
            return tag, f"__ERROR__ {type(exc).__name__}: {str(exc)[:140]}"

    try:
        results = await asyncio.gather(_one("A"), _one("B"))
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count_inserts)
    errors = [r for r in results if "__ERROR__" in r[1]]
    await engine.dispose()

    assert not errors, (
        f"并发写短链映射把异常冒了出来（期望被 _save_short_link 的 savepoint 吸收；"
        f"本次 INSERT 尝试 {len(insert_attempts)} 次）：{errors}"
    )
    if len(insert_attempts) < 2:
        pytest.skip(
            f"本次运行只有 {len(insert_attempts)} 条 INSERT 打到 short_link_maps ⇒ 没有形成双写交错，"
            "兜底分支未被执行，本用例这次没有判定力（不是通过）"
        )
    with create_engine(PG_DSN, connect_args={"connect_timeout": 3}).connect() as conn:
        maps = conn.execute(
            select(func.count()).select_from(ShortLinkMap).where(ShortLinkMap.short_key == map_key)
        ).scalar_one()
    assert maps == 1, f"映射行应收敛为单行，实际 {maps}（0 表示两边都没写进行）"


async def test_short_link_map_conflict_branch_is_actually_taken(db_session) -> None:  # type: ignore[no-untyped-def]
    """兜底分支的确定性证据：让对手的提交**正好落在**"前置查"与"插入"之间。

    为什么还要这一条：上面那条 barrier 用例判的是整条并发链不冒异常，但它仍由调度决定；
    而"后发者撞唯一约束"这个分支只要没被执行过，绿灯就说明不了兜底在位——
    若交错退化成"一方早退"，实现有洞也照样绿（独立验证报的正是这个判定力缺口）。
    这里用一层只代理 `execute` 的会话壳，把一次真提交插在第一次查询之后 ⇒
    生产的 insert 必然撞 `uq_shortlink_key` ⇒ 必然走 `except IntegrityError` + 重查。

    断言里"必须发生两次查询"就是正证据；只断言"没抛"是负证据，挡不住"根本没走到"。
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    side = create_async_engine(PG_DSN, connect_args={"connect_timeout": 3})
    main = create_async_engine(PG_DSN, connect_args={"connect_timeout": 3})
    SideSession = async_sessionmaker(bind=side, expire_on_commit=False)
    MainSession = async_sessionmaker(bind=main, expire_on_commit=False)
    probe_key = f"probe-race-{uuid.uuid4().hex[:12]}"

    class _InterposingSession:
        """代理到真会话，只在第一次 execute 之后替对手提交同键行。"""

        def __init__(self, inner) -> None:
            self._inner = inner
            self.selects = 0

        async def execute(self, stmt):
            self.selects += 1
            result = await self._inner.execute(stmt)
            if self.selects == 1:
                async with SideSession() as other:
                    other.add(ShortLinkMap(short_key=probe_key, article_key="s:opponent", biz=""))
                    await other.commit()
            return result

        def __getattr__(self, name):
            return getattr(self._inner, name)

    try:
        async with MainSession() as raw:
            wrapper = _InterposingSession(raw)
            svc = _svc(wrapper, _CountingStubResolver())
            await svc._save_short_link(probe_key, "s:mine", "")  # noqa: SLF001
            await raw.commit()
            assert wrapper.selects == 2, (
                f"期望「前置查 + 冲突后重查」两次查询，实得 {wrapper.selects} ⇒ 兜底分支没被执行，"
                "本用例这次没有判定力（不是通过）"
            )
            rows = (
                await raw.execute(select(ShortLinkMap).where(ShortLinkMap.short_key == probe_key))
            ).scalars().all()
            assert len(rows) == 1, f"表里应只剩对手那一行，实际 {len(rows)}"
            assert rows[0].article_key == "s:opponent", "兜底的语义是承认对手已写入，不是把自己的键覆盖上去"
    finally:
        async with SideSession() as cleaner:
            await cleaner.execute(text("DELETE FROM short_link_maps WHERE short_key = :k"), {"k": probe_key})
            await cleaner.commit()
        await side.dispose()
        await main.dispose()
