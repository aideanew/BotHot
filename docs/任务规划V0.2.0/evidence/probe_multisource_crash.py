"""探针 P-4：库内已有 ≥2 个 source 时，入库一条长链文章是否崩溃。

根因链：kb._biz_from_url 读的是 `biz` 参数而非 `__biz`（kb.py `_biz_from_url`）⇒ 长链 biz 锚为空；
_article_key(长链) == "s" ⇒ _find_source_by_anchor 兜底走 `Source.url LIKE '%s%'`，
几乎所有 https URL 都含字母 s ⇒ scalar_one_or_none() 命中多行 ⇒ MultipleResultsFound。
2026-10-12 @61739f0 实测输出：PROBE2 EXC MultipleResultsFound Multiple rows were found when one or none was required
修复后期望：PROBE2 ok False（正常抓取，不命中缓存）
用法同 probe_longlink_collision.py（复制到 apps/api/tests/ 下跑完即删）。
"""
from test_langbot import _client, _lb_transport, _StubResolver  # noqa: F401
from test_p0_asset_cache import _CountingStubResolver, _seeder_space
from app.services.kb import KnowledgeBaseService
from app.models.entities import Source

A = "https://mp.weixin.qq.com/s?__biz=MjM5MjgwNTQ1MQ==&mid=2650000001&idx=1&sn=aaaa1111"


async def test_probe_multi_source(db_session):
    _, space = await _seeder_space(db_session, "probe-ms")
    for i in range(2):
        db_session.add(Source(type="wechat_oa", external_id=f"MzOther{i}", name="o",
                              url=f"https://mp.weixin.qq.com/s/other{i}"))
    await db_session.commit()
    svc = KnowledgeBaseService(_client(), db_session, _CountingStubResolver())
    try:
        r = await svc.ingest_url(space.id, A)
        print("\nPROBE2 ok", r["hitCache"])
    except Exception as e:  # noqa: BLE001
        print("\nPROBE2 EXC", type(e).__name__, str(e)[:120])
