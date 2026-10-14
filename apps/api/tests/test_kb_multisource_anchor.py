"""STEP-02 / S2.1.4：`kb._find_source_by_anchor` 的锚定顺序与「多源不崩」（探针 P-4 转正）。

卡面 S2.1.4.1 要求把 P-4 探针转成常驻用例、S2.1.4.3 要求另加「已有 biz 源时优先命中 biz 源」，
两条都在这里。两条都是**连库**用例：判据是「向 DB 要了什么、DB 回了几行」，
假会话证不了「多行命中时 `scalar_one_or_none()` 抛不抛」这一件事。

改前的红（有依赖环境实测读数 `docs/任务规划V0.3.0/evidence/probes_4afaedd.txt:19`：
`PROBE2 EXC MultipleResultsFound Multiple rows were found when one or none was required`）：
长链的 article_key 是 URL 末段 `s`（`kb._article_key`），旧实现两条锚都不中时落到
`Source.url.like("%s%")` 兜底 ⇒ 库里只要有 ≥2 条 https 源就命中多行，`scalar_one_or_none()` 抛错，
整条入库链路 500。S2.1.4 删掉那条兜底、两条锚查询各带 `.limit(1)`。

本机跑不起来（`kb.py:22-25` 模块级 import `structlog`/`sqlalchemy`，本机皆无）⇒ 卡面验收命令
`cd apps/api && uv run pytest tests/test_kb_multisource_anchor.py -q`（连库，需 `bash scripts/test-env.sh up`）；
本机侧等价证明在 `docs/06_validation/evidence/EVD-V2-02/prove_anchor_fallback.py`：
行为面 AF-B1…B5 用 AST 取出**磁盘上 kb.py 的当前函数体**真实执行，配一台如实实现 `limit(1)`
截断与多行抛错的记账假会话；结构面 AF-S1/S2/S6 机检「函数体内不再有 `.like(`」这类否定式声明，
不靠人眼读 diff。
"""

from __future__ import annotations

from fixtures.wechat_urls import BIZ_A, LONG_A

from app.models.entities import Source
from app.services.kb import KnowledgeBaseService, _article_key


async def test_multi_source_no_crash(db_session) -> None:  # type: ignore[no-untyped-def]
    """S2.1.4.1：库内已有 ≥2 个 source 时入库长链不得崩（探针 P-4 的常驻版）。

    夹具里两条种子源的 URL 都含字母 `s`（凡是 https 的都含）——这正是旧兜底
    `Source.url.like("%s%")` 会一次捞到多行的形状。改后期望：不抛、正常抓取一条
    （`hitCache` False、resolver 恰好进 1 次）。这里刻意不断言「命中了哪个 source」：
    P-4 的判据只有一条，兜底不许把入库打崩；源的选择由下一条用例判。
    """
    from test_langbot import _client  # noqa: PLC0415  (仅本用例需要，纯函数用例不背这条链)
    from test_p0_asset_cache import _CountingStubResolver, _seeder_space  # noqa: PLC0415

    _, space = await _seeder_space(db_session, "S2.1.4 多源不崩")
    for i in range(2):
        db_session.add(
            Source(
                type="wechat_oa",
                external_id=f"MzOther{i}",
                name="probe-source",
                url=f"https://mp.weixin.qq.com/s/other{i}",
            )
        )
    await db_session.commit()

    resolver = _CountingStubResolver()
    svc = KnowledgeBaseService(_client(), db_session, resolver)
    first = await svc.ingest_url(space.id, LONG_A)
    assert first["hitCache"] is False, f"多源场景不应命中缓存，实际 {first!r}"
    assert resolver.fetch_count == 1, f"应恰好一次真实抓取，实际 {resolver.fetch_count}"


async def test_biz_anchor_wins_when_both_anchors_exist(db_session) -> None:  # type: ignore[no-untyped-def]
    """S2.1.4.3：biz 锚源与 article_key 锚源同时存在时，返回的是 biz 锚源。

    这条判的是**顺序**而不是「有没有结果」：两条种子行的 `external_id` 分别等于
    `_biz_from_url(LONG_A)` 与 `_article_key(LONG_A)`，谁先查谁被返回。
    SQL 本身不保证行的顺序，所以把两条锚的次序写进判据里才有意义——
    把实现改成先查 article_key，本用例立刻红（而不是碰巧还是绿的）。

    开头那句 `assert key == "s"` 是本用例的前提而不是结论：长链的幂等键退化成一个字母，
    正是 D-01b 那条坍缩链的现场。哪天 `_article_key` 换了口径，这一行会先出声，
    免得「优先命中 biz 源」这句话悄悄变成在测另一件事。
    """
    from test_langbot import _client  # noqa: PLC0415
    from test_p0_asset_cache import _CountingStubResolver  # noqa: PLC0415

    key = _article_key(LONG_A)
    assert key == "s", f"夹具长链的 article_key 不再是末段 `s`（本用例的前提变了）：{key!r}"

    biz_src = Source(
        type="wechat_oa", external_id=BIZ_A, name="biz 锚源", url="https://mp.weixin.qq.com/s/biz-anchored"
    )
    key_src = Source(
        type="wechat_oa", external_id=key, name="article_key 锚源", url="https://mp.weixin.qq.com/s/key-anchored"
    )
    db_session.add_all([biz_src, key_src])
    await db_session.commit()

    svc = KnowledgeBaseService(_client(), db_session, _CountingStubResolver())
    got = await svc._find_source_by_anchor(key, LONG_A)  # noqa: SLF001
    assert got is not None, "两条锚都在库里却返回 None——锚定根本没跑"
    assert got.id == biz_src.id, f"应优先命中 biz 锚源 {biz_src.id}，实得 {got.id}（{got.name}）"
