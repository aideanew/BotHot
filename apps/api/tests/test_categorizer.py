"""T3.2 分类体系验收测试：categorizer 规则版离线单测 + 采集赋值/列表透出（连库）。"""

from __future__ import annotations

from typing import Any

from app.services.categorizer import CATEGORIES, DEFAULT_CATEGORY, categorize

# ------------------------------------------------------------------ 规则版分类器（离线口径）


def test_taxonomy_declaration() -> None:
    """六类声明齐全，默认类为「其他」，顺序即 UI 优先级。"""
    assert CATEGORIES == ["AI·技术", "产品·商业", "行业·动态", "观点·评论", "教程·实践", "其他"]
    assert DEFAULT_CATEGORY == "其他"


def test_title_hit_wins_over_content() -> None:
    """标题命中优先于正文计数（标题主题性强）。"""
    assert categorize("大模型训练新范式", "今天聊聊商业模式和增长") == "AI·技术"
    assert categorize("增长黑客的定价方法论", "提到了一些技术细节") in ("产品·商业", "教程·实践")


def test_content_count_threshold() -> None:
    """正文单次提及不算主题命中（≥2 个不同关键词），零命中回落其他。"""
    assert categorize("一篇没有主题的文章", "其中提到了一次算法") == DEFAULT_CATEGORY
    assert categorize("一篇没有主题的文章", "算法、模型与训练的粗浅看法") == "AI·技术"


def test_empty_fallback() -> None:
    """空输入 → 其他（不抛异常）。"""
    assert categorize("", "") == DEFAULT_CATEGORY


def test_deterministic() -> None:
    """同一输入多次分类结果一致（规则版确定性承诺）。"""
    q = ("大模型应用指南", "一份面向开发者的实践教程，含架构与代码示例")
    assert categorize(*q) == categorize(*q)


# ------------------------------------------------------------------ 采集赋值 + 列表透出（连库口径）


async def _seed_user_space_source(session: Any, sub: str, biz: str):  # type: ignore[no-untyped-def]
    from app.repositories.space import SpaceRepository
    from app.repositories.user import SqlAlchemyUserStore

    user = await SqlAlchemyUserStore(session).upsert_by_sub(sub, f"{sub}@test.local", sub)
    space = await SpaceRepository(session).create(user_id=user.id, name=f"{sub}-空间")
    from app.models.entities import Source

    source = Source(type="wechat_oa", external_id=biz, name=f"源{biz}")
    session.add(source)
    await session.flush()
    return user, space, source


async def test_ingest_assigns_category_and_docs_expose_it(db_session) -> None:  # type: ignore[no-untyped-def]
    """T3.2.2/T3.2.3 连库：入库赋分类 → docs 列表行携带 category。"""
    from app.models.entities import KnowledgeDocument
    from app.repositories.asset import DocumentRepository

    user, space, source = await _seed_user_space_source(db_session, "sub-t32", "t32-biz")

    # 直接构造 asset（category 由 kb._persist_document 在真实采集路径赋值；
    # 此处验证仓储/列表链路的透出语义 + upsert_content 分类写入）
    from app.repositories.asset import AssetRepository

    asset_repo = AssetRepository(db_session)
    asset, created = await asset_repo.upsert_content(
        source_id=source.id,
        external_id="t32-art-1",
        url="https://mp.weixin.qq.com/s/t32-1",
        title="大模型训练新范式",
        content_markdown="关于 AI 模型与算法的技术文章正文",
        content_hash="hash-t32-1",
        category="AI·技术",
        status="READY",
    )
    assert created is True and asset.category == "AI·技术"
    await DocumentRepository(db_session).create(asset_id=asset.id, space_id=space.id)
    await db_session.flush()

    from app.repositories.space import SpaceRepository

    rows = await SpaceRepository(db_session).list_docs(space.id)
    assert rows[0]["category"] == "AI·技术"

    # hash 变化 → 新内容重算分类（调用方传新 category 时覆盖）
    asset2, created2 = await asset_repo.upsert_content(
        source_id=source.id,
        external_id="t32-art-1",
        url="https://mp.weixin.qq.com/s/t32-1",
        title="创业公司的商业模式思考",
        content_markdown="增长、营销与市场策略",
        content_hash="hash-t32-2",
        category="产品·商业",
        status="READY",
    )
    assert created2 is True and asset2.id == asset.id and asset2.category == "产品·商业"
    docs = (
        await db_session.execute(
            __import__("sqlalchemy").select(KnowledgeDocument).where(
                KnowledgeDocument.asset_id == asset.id
            )
        )
    ).scalars().all()
    assert len(docs) >= 1
    await db_session.commit()
