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
from app.services.public_library import PublicLibraryService
from app.services.resolver import ResolvedArticle

# 短链 + 长链两形态（同文）：短链解析后指向长链末段 long-key-001
SHORT_URL = "https://mp.weixin.qq.com/s/short-key-t27?biz=MjM5MjgwNTQ1MQ==&hid=t27"
LONG_URL = "https://mp.weixin.qq.com/s/long-key-001?biz=MjM5MjgwNTQ1MQ==&hid=t27"
SHORT_KEY = "short-key-t27"
LONG_KEY = "long-key-001"

# T2.7 自身命名空间（清理夹具按此收敛，绝不触碰命名空间外数据）
# DSN 允许环境变量覆盖：CI 无 PG 时走 skip 分支，本地/CI service container 可指向他处
PG_DSN = os.environ.get("AIDEANBOT_TEST_PG_DSN", "postgresql+psycopg://bothot:bothot@localhost:5433/bothot")
_T27_USER_SUBS = ("sub-t27-idem", "sub-t27-race", "sub-t27-f22")
_T27_ASSET_KEYS = (SHORT_KEY, LONG_KEY)
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
            conn.execute(text("DELETE FROM short_link_maps WHERE short_key = :k"), {"k": SHORT_KEY})
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
    """URL → article_key（与 kb.py 归一化同口径；断言比对用）。"""
    import re

    return re.sub(r"[?&#].*$", "", url).rstrip("/").rsplit("/", 1)[-1] or url


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

    # 资产落库键 = 长链末段（与 _persist_document 口径一致）
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
