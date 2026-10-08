"""T1.5.3/T1.5.7 验收测试：doc 计数批量查询（N+1 修复）+ docs 列表分页（连库，不可达自动 skip）。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.errors import ResourceNotFoundError
from app.models.entities import ContentAsset
from app.repositories.asset import DocumentRepository
from app.repositories.space import SpaceRepository
from app.services.categorizer import UNCATEGORIZED
from app.services.spaces import SpaceService


async def _seed_user_and_space(session: Any, sub: str, name: str):  # type: ignore[no-untyped-def]
    from app.repositories.user import SqlAlchemyUserStore

    user = await SqlAlchemyUserStore(session).upsert_by_sub(sub, f"{sub}@test.local", sub)
    space = await SpaceRepository(session).create(user_id=user.id, name=name)
    await session.flush()
    return user, space


async def _seed_source(session: Any, external_id: str):  # type: ignore[no-untyped-def]
    from app.models.entities import Source

    source = Source(type="wechat_oa", external_id=external_id, name=f"源{external_id}")
    session.add(source)
    await session.flush()
    return source


async def _seed_doc(
    session: Any,
    space_id: str,
    source_id: str,
    external_id: str,
    category: str = "",
) -> None:  # type: ignore[no-untyped-def]
    asset = ContentAsset(
        source_id=source_id,
        external_id=external_id,
        url=f"https://mp.weixin.qq.com/s/{external_id}",
        title=f"标题{external_id}",
        content_hash=f"hash-{external_id}",
        content_markdown="# 正文",
        published_at=datetime.now(UTC),
        category=category,
    )
    session.add(asset)
    await session.flush()
    await DocumentRepository(session).create(asset_id=asset.id, space_id=space_id)


async def test_count_docs_many_batch(db_session) -> None:  # type: ignore[no-untyped-def]
    """T1.5.3：count_docs_many 单查询返回多空间计数；未命中空间=0；空列表安全。"""
    user_a, space_a = await _seed_user_and_space(db_session, "sub-pg-a", "批量计数A")
    _user_b, space_b = await _seed_user_and_space(db_session, "sub-pg-b", "批量计数B")
    src = await _seed_source(db_session, "pg-batch-biz")
    for i in range(3):
        await _seed_doc(db_session, space_a.id, src.id, f"pg-batch-a{i}")
    await db_session.flush()

    repo = SpaceRepository(db_session)
    counts = await repo.count_docs_many([space_a.id, space_b.id])
    assert counts == {space_a.id: 3}, "GROUP BY 只返回有文档的空间"
    assert counts.get(space_b.id, 0) == 0, "未命中空间按 0 取值（.get 语义）"
    assert await repo.count_docs_many([]) == {}
    # 交叉核对：单空间 count 与批量口径一致
    assert await repo.count_docs(space_a.id) == counts[space_a.id]
    await db_session.commit()


async def test_list_docs_pagination_window(db_session) -> None:  # type: ignore[no-untyped-def]
    """T1.5.7：limit/offset 窗口正确 + total 独立于窗口 + 默认全量向后兼容。"""
    user, space = await _seed_user_and_space(db_session, "sub-pg-page", "分页空间")
    src = await _seed_source(db_session, "pg-page-biz")
    for i in range(5):
        await _seed_doc(db_session, space.id, src.id, f"pg-page-{i}")
    await db_session.flush()

    svc = SpaceService(SpaceRepository(db_session))
    # 全量（不传参）→ 5 条，total=5
    items_all, total_all = await svc.list_space_docs(user.id, space.id)
    assert len(items_all) == 5 and total_all == 5
    # 第一页 2 条，total 仍 5
    items_p1, total_1 = await svc.list_space_docs(user.id, space.id, limit=2, offset=0)
    assert len(items_p1) == 2 and total_1 == 5
    # 第二页 2 条，与第一页不重叠
    items_p2, _ = await svc.list_space_docs(user.id, space.id, limit=2, offset=2)
    assert len(items_p2) == 2 and total_1 == 5
    assert {r["id"] for r in items_p1}.isdisjoint({r["id"] for r in items_p2})
    # 越界页 → 空列表 + total 5
    items_p3, total_3 = await svc.list_space_docs(user.id, space.id, limit=2, offset=4)
    assert len(items_p3) == 1 and total_3 == 5
    await db_session.commit()


async def test_list_space_docs_category_filter_matches_total(db_session):  # type: ignore[no-untyped-def]
    """R0.1.1：category 服务端过滤命中子集，total 与 items 同谓词（分页下不虚高）。"""
    user, space = await _seed_user_and_space(db_session, "sub-pg-cat", "分类过滤空间")
    src = await _seed_source(db_session, "pg-cat-biz")
    await _seed_doc(db_session, space.id, src.id, "pg-cat-a1", category="AI·技术")
    await _seed_doc(db_session, space.id, src.id, "pg-cat-a2", category="AI·技术")
    await _seed_doc(db_session, space.id, src.id, "pg-cat-b1", category="教程·实践")
    await db_session.flush()

    svc = SpaceService(SpaceRepository(db_session))
    items, total = await svc.list_space_docs(user.id, space.id, category="AI·技术")
    assert total == 2 and len(items) == 2
    assert {r["category"] for r in items} == {"AI·技术"}

    # 分页 + 过滤：total 仍是过滤后的数（不是全量 3）
    items_p, total_p = await svc.list_space_docs(
        user.id, space.id, limit=1, offset=0, category="AI·技术"
    )
    assert len(items_p) == 1 and total_p == 2

    # 未登记的取值：读路径不设校验闸门，合法地返回空列表
    items_none, total_none = await svc.list_space_docs(
        user.id, space.id, category="随手写的标签"
    )
    assert items_none == [] and total_none == 0

    # 不传参数：向后兼容全量
    _items_all, total_all = await svc.list_space_docs(user.id, space.id)
    assert total_all == 3
    await db_session.commit()


async def test_list_space_docs_uncategorized_sentinel(db_session):  # type: ignore[no-untyped-def]
    """R0.1.1：`__uncategorized__` 哨兵 = 资产无分类标签（库里是空串，不存哨兵值）。"""
    user, space = await _seed_user_and_space(db_session, "sub-pg-unc", "未分类空间")
    src = await _seed_source(db_session, "pg-unc-biz")
    await _seed_doc(db_session, space.id, src.id, "pg-unc-1")  # category 默认空串
    await _seed_doc(db_session, space.id, src.id, "pg-unc-2")
    await _seed_doc(db_session, space.id, src.id, "pg-unc-3", category="观点·评论")
    await db_session.flush()

    svc = SpaceService(SpaceRepository(db_session))
    items, total = await svc.list_space_docs(user.id, space.id, category=UNCATEGORIZED)
    assert total == 2 and len(items) == 2
    assert {r["category"] for r in items} == {""}, "响应保持空串，不回填哨兵值"

    # 直接传空串与哨兵等价（哨兵只是契约层的表达）
    _items, total_empty = await svc.list_space_docs(user.id, space.id, category="")
    assert total_empty == 2
    await db_session.commit()


async def test_list_space_docs_other_user_404(db_session) -> None:  # type: ignore[no-untyped-def]
    """越权访问他人空间 → 30004（分页参数不改变鉴权语义）。"""
    _owner, space = await _seed_user_and_space(db_session, "sub-pg-owner", "越权空间")
    stranger, _ = await _seed_user_and_space(db_session, "sub-pg-stranger", "路人空间")
    svc = SpaceService(SpaceRepository(db_session))
    with pytest.raises(ResourceNotFoundError):
        await svc.list_space_docs(stranger.id, space.id, limit=2, offset=0)
    await db_session.commit()


async def test_list_doc_categories_returns_existing_only(db_session):  # type: ignore[no-untyped-def]
    """R0.1.2：只返回本空间实际存在的分类（声明序 + 哨兵置末），不混入他空间分类。"""
    user, space = await _seed_user_and_space(db_session, "sub-pg-cats", "分类集合空间")
    src = await _seed_source(db_session, "pg-cats-biz")
    await _seed_doc(db_session, space.id, src.id, "pg-cats-1", category="教程·实践")
    await _seed_doc(db_session, space.id, src.id, "pg-cats-2", category="AI·技术")
    await _seed_doc(db_session, space.id, src.id, "pg-cats-2b", category="AI·技术")  # 去重
    await _seed_doc(db_session, space.id, src.id, "pg-cats-3")  # 未分类

    other_owner, other = await _seed_user_and_space(db_session, "sub-pg-cats2", "他空间")
    await _seed_doc(db_session, other.id, src.id, "pg-cats-x", category="观点·评论")
    u3, empty = await _seed_user_and_space(db_session, "sub-pg-cats3", "空空间")
    await db_session.flush()

    svc = SpaceService(SpaceRepository(db_session))
    assert await svc.list_doc_categories(user.id, space.id) == [
        "AI·技术",      # 按 CATEGORIES 声明序，而非入库顺序
        "教程·实践",
        UNCATEGORIZED,  # 未分类以哨兵置末
    ]
    # 空间隔离：他空间的分类不混入
    assert await svc.list_doc_categories(other_owner.id, other.id) == ["观点·评论"]
    # 空空间 → 空集合（没有任何 doc 即没有「未分类」，不回填哨兵）
    assert await svc.list_doc_categories(u3.id, empty.id) == []

    # 越权 → 30004（与 docs 列表同口径，不泄露存在性）
    with pytest.raises(ResourceNotFoundError):
        await svc.list_doc_categories(other_owner.id, space.id)
    await db_session.commit()


async def test_list_pending_ingest_only_nonterminal_with_file_id(db_session) -> None:  # type: ignore[no-untyped-def]
    """后台状态推进候选集：仅「未就绪 + 已拿到引擎 file_id」的 doc。

    READY 已收敛（再探是浪费）；无 file_id 无从探测（不能拿空 id 去问引擎）。
    """
    user, space = await _seed_user_and_space(db_session, "sub-pg-pend", "推进候选")
    src = await _seed_source(db_session, "pg-pending-biz")
    assets = [
        ContentAsset(
            source_id=src.id, external_id=f"pg-pend-{c}",
            url=f"https://mp.weixin.qq.com/s/pg-pend-{c}", title=f"标题{c}",
            content_hash=f"hash-{c}", content_markdown="# 正文",
            published_at=datetime.now(UTC),
        )
        for c in "abc"
    ]
    db_session.add_all(assets)
    await db_session.flush()

    repo = DocumentRepository(db_session)
    docs = [await repo.create(asset_id=a.id, space_id=space.id) for a in assets]
    await repo.set_status(docs[0].id, "FETCHED")                     # 无 file_id → 排除
    await repo.set_status(docs[1].id, "INDEXED")
    await repo.set_langbot_file_id(docs[1].id, "file-1")            # 唯一候选
    await repo.set_status(docs[2].id, "READY")
    await repo.set_langbot_file_id(docs[2].id, "file-2")           # 已就绪 → 排除
    await db_session.flush()

    pending = await repo.list_pending_ingest()
    # 候选集是**全库**口径（推进不区分归属）；只断言本用例空间内的结果，
    # 避免共享开发库里他用的非终态 doc 干扰（同 test_scheduler 的命名空间口径）。
    mine = [d.id for d in pending if d.space_id == space.id]
    assert mine == [docs[1].id], mine
    assert await repo.list_pending_ingest(limit=0) == []
