"""STEP-02 / S2.1.4：`kb._find_source_by_anchor` 的锚定顺序与「多源不崩」（探针 P-4 转正）。

卡面 S2.1.4.1 要求把 P-4 探针转成常驻用例、S2.1.4.3 要求另加「已有 biz 源时优先命中 biz 源」，
两条都在这里；**STEP-R0（V0.7.0）又把短链缓存回归的两条常驻用例并进来**（本文件共 4 条）。
四条都是**连库**用例：判据是「向 DB 要了什么、DB 回了几行」，
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

from fixtures.wechat_urls import BIZ_A, LONG_A, SHORT_1, SHORT_TOKEN_1

from app.models.entities import ContentAsset, Source
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

    开头那句 `assert key.startswith("b:")` 是本用例的前提而不是结论：S2.2.3 之前这里是
    `assert key == "s"`——长链幂等键退化成一个字母，正是 D-01b 那条坍缩链的现场；
    规范键上线后前提换成"取到的是 b: 支"，两处形态各由 `test_article_identity.py` 与
    `test_batch_ingest_key_drift.py` 守着，本行只保证**这条用例在测的那件事没变**。
    哪天键口径又漂（比如误并到 `h:` 支），这一行会先出声，免得「优先命中 biz 源」
    悄悄变成在测另一件事。
    """
    from test_langbot import _client  # noqa: PLC0415
    from test_p0_asset_cache import _CountingStubResolver  # noqa: PLC0415

    key = _article_key(LONG_A)
    assert key.startswith("b:"), f"长链规范键不再是 b: 支（本用例的前提变了）：{key!r}"

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


async def test_short_key_does_not_trigger_asset_reverse_lookup(db_session) -> None:  # type: ignore[no-untyped-def]
    """R0.2.2 ①：长度 < `MIN_FRAGMENT_LEN` 的键**不得**走第三条资产反查。

    S2.2.3 之后生产路径不再产出 `"s"`（规范键恒 ≥8、`h:` 恒 34），所以这条从
    "现网护栏"转成**回归护栏**：它显式喂一个短键，保证将来有人把闸拆掉时这里先红。
    形状刻意摆成"反查能命中"的样子：一条 external_id 既非 `s` 也非 BIZ_A 的源，
    挂一条 `external_id="s"` 的资产。若守卫被拆掉，第三条锚会用资产等值查把这条源捞出来
    ⇒ 本用例红；有守卫时三个锚全空 ⇒ 返回 None。

    这条守的是 P-3（长链键曾坍缩为 `"s"`）那类形态：短键无区分能力，一旦放它走反查，
    「同号第一篇的资产」会把任意第二篇领到同一个源上——冒名从"同号"扩散到"跨源"。
    变异反证（卡面 R0.2.2.1）：把 `anchor_keys` 的长度过滤拆掉 ⇒ 本用例必红。
    """
    from test_langbot import _client  # noqa: PLC0415
    from test_p0_asset_cache import _CountingStubResolver  # noqa: PLC0415

    from app.services.kb import _biz_from_url

    # 前提钉桩：锚① 在 LONG_A 上确实解出 BIZ_A，而本用例库里没有 external_id=BIZ_A 的源
    # ——这才是"期望 None"成立的条件。前提变了却不改用例，会让这条变成在测别的事。
    assert _biz_from_url(LONG_A) == BIZ_A, (
        f"LONG_A 的 biz 解析口径已变（实得 {_biz_from_url(LONG_A)!r}），"
        "本用例的「锚①必空」前提失效，需随 `_biz_from_url` 一起重写"
    )

    src = Source(
        type="wechat_oa",
        external_id="PAGEBIZ-NOT-SHORT-TOKEN",
        name="页面 biz 源",
        url="https://mp.weixin.qq.com/s/other-page",
    )
    db_session.add(src)
    await db_session.commit()
    db_session.add(
        ContentAsset(
            source_id=src.id,
            external_id="s",
            content_hash="0" * 64,
            content_markdown="placeholder",
        )
    )
    await db_session.commit()

    svc = KnowledgeBaseService(_client(), db_session, _CountingStubResolver())
    got = await svc._find_source_by_anchor("s", LONG_A)  # noqa: SLF001
    assert got is None, (
        f'"s" 只有 1 个字符、短于 MIN_FRAGMENT_LEN，不该走资产反查却拿到 {got!r}；'
        "长度守卫已失效——P-3 的同号冒名会经此扩散为跨源冒名"
    )
    assert BIZ_A  # 前提未被重构掉：LONG_A 的 biz 仍是 BIZ_A（若夹具改了，上面那条 None 会失去意义）


async def test_asset_reverse_lookup_recovers_biz_keyed_source(db_session) -> None:  # type: ignore[no-untyped-def]
    """R0.2.2 ②：无参短链二次入库时，第三条锚经资产把「以页面 biz 建键的源」找回来。

    这是 078dc30 删掉 URL 子串兜底后失去的能力（`test_be02_engine_routing.py:301` 那条
    `assert 2 == 1` 回归的本体）。形状照回归现场摆：
      - 源以 **页面 biz** 为键（`_ensure_source` 的 `biz or _article_key(url)` 口径），
      - 资产以**短链 token** 为键（`_article_key(入参 URL)` 口径）。
    锚①：`SHORT_1` 无 query ⇒ `_biz_from_url` 解不出 biz ⇒ 空；
    锚②：token 对不上以 biz 为键的源 ⇒ 空；
    锚③：token ≥8 字符 ⇒ 走资产等值反查，经 `source_id` join 回源 ⇒ 命中。

    用等值而不是 `Source.url.like` 是本修复的要点：资产表 `uq_asset_source_external`
    的键就是文章身份，等值足够，不会像子串匹配那样一字母命中全表（那正是 P-4 的成因）。
    """
    from test_langbot import _client  # noqa: PLC0415
    from test_p0_asset_cache import _CountingStubResolver  # noqa: PLC0415

    assert len(SHORT_TOKEN_1) >= 8, f"夹具 token 长度变了，本用例的前提（过守卫）不成立：{SHORT_TOKEN_1!r}"

    src = Source(
        type="wechat_oa",
        external_id=BIZ_A,
        name="页面 biz 源（短链首抓所建）",
        url=SHORT_1,
    )
    db_session.add(src)
    await db_session.commit()
    db_session.add(
        ContentAsset(
            source_id=src.id,
            external_id=SHORT_TOKEN_1,
            content_hash="1" * 64,
            content_markdown="placeholder",
        )
    )
    await db_session.commit()

    svc = KnowledgeBaseService(_client(), db_session, _CountingStubResolver())
    got = await svc._find_source_by_anchor(SHORT_TOKEN_1, SHORT_1)  # noqa: SLF001
    assert got is not None, (
        f"短链 token {SHORT_TOKEN_1!r} 经资产反查应能领回源 {src.id}；"
        "拿到 None 说明第三条锚没跑——二次入库会重新抓取（078dc30 那一条回归）"
    )
    assert got.id == src.id, f"应返回资产所属源 {src.id}，实得 {got.id}（{got.name}）"
