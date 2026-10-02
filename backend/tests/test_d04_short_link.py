"""AB-P004 D-04/L-01 短链映射验收测试：短链 key → 长链 article_key 幂等落库 + 复用路径 0 请求。

机器门口径（T-023）：
- ① _save_short_link 幂等（uq_shortlink_key：同 short_key 重复不重插）；
- ② _lookup_short_link 命中返回 article_key，未落映射返回空串；
- ③ _short_link_key 表面判定（/s/ 短链提取 key，非短链空串）。
"""

from __future__ import annotations

from sqlalchemy import select

from app.models.entities import ShortLinkMap
from app.services.kb import _article_key, _is_short_link, _short_link_key


def test_short_link_key_surface_parsing() -> None:
    """机器门③：/s/ 短链形态提取末段 key；非短链/长链空串。"""
    assert _is_short_link("https://mp.weixin.qq.com/s/ABC-123") is True
    assert _short_link_key("https://mp.weixin.qq.com/s/ABC-123") == "ABC-123"
    # 非短链：长链 /s?__biz= 或普通 URL
    assert _short_link_key("https://mp.weixin.qq.com/s?__biz=Mz0&id=1") == ""
    assert _short_link_key("https://example.com/a") == ""
    # 末段 article_key 口径（与 _article_key 一致）
    assert _article_key("https://mp.weixin.qq.com/s/FINAL-KEY").rstrip("/") == "FINAL-KEY"


async def test_short_link_map_idempotent_upsert(db_session) -> None:  # type: ignore[no-untyped-def]
    """机器门①：_save_short_link 同 short_key 重复调用不重插（uq_shortlink_key 幂等）。"""
    from test_langbot import _client
    from test_p0_asset_cache import _CountingStubResolver

    from app.services.kb import KnowledgeBaseService

    svc = KnowledgeBaseService(_client(), db_session, _CountingStubResolver())
    await svc._save_short_link("SLK-001", "FINAL-KEY-001", biz="Mzbiz")
    await db_session.commit()

    # 二次同 key 不重插
    await svc._save_short_link("SLK-001", "FINAL-KEY-001", biz="Mzbiz")
    rows = (await db_session.execute(select(ShortLinkMap).where(ShortLinkMap.short_key == "SLK-001"))).scalars().all()
    assert len(rows) == 1, "同 short_key 应幂等不重插"
    assert rows[0].article_key == "FINAL-KEY-001" and rows[0].biz == "Mzbiz"
    await db_session.commit()


async def test_short_link_lookup_hit_and_miss(db_session) -> None:  # type: ignore[no-untyped-def]
    """机器门②：_lookup_short_link 命中返回长链 article_key；未落映射返回空串（走真实抓取）。"""
    from test_langbot import _client
    from test_p0_asset_cache import _CountingStubResolver

    from app.services.kb import KnowledgeBaseService

    svc = KnowledgeBaseService(_client(), db_session, _CountingStubResolver())
    await svc._save_short_link("SLK-002", "FINAL-KEY-002")
    await db_session.commit()

    hit = await svc._lookup_short_link("SLK-002")
    assert hit == "FINAL-KEY-002"
    # 幂等校验：重查映射行完整（列值口径）
    row = (await db_session.execute(select(ShortLinkMap).where(ShortLinkMap.short_key == "SLK-002"))).scalar_one()
    assert row.article_key == "FINAL-KEY-002"
    miss = await svc._lookup_short_link("SLK-NOPE")
    assert miss == "", "未落映射应返回空串（调用方走真实抓取路径）"
    empty = await svc._lookup_short_link("")
    assert empty == ""
    await db_session.commit()
