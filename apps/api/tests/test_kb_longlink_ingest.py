"""STEP-02 / S2.1.3：`kb._biz_from_url` 委托解析层（长链号主身份不再为空串）。

本文件只管 S2.1.3（biz 委托）：口径见下面第 1–5 条与 `prove_biz_delegation.py`。
它的**下游** S2.1.4（删 `Source.url.like('%s%')` 兜底）在 `test_kb_multisource_anchor.py`，
本机侧证明在 `prove_anchor_fallback.py`——后者同时是一道静态门：它从磁盘上的 kb.py 里取出
`_find_source_by_anchor` 的当前函数体，要求函数体内不再出现 `.like(`，且两条锚查询都带
`.limit(1)`。「删掉了兜底」这种否定式声明不能只靠人眼读 diff。

为什么这个文件在本机跑不起来、却仍然有价值：`kb.py:22-25` 在模块级 import `structlog`
与 `sqlalchemy`，本机两者皆无（实测 `PYTHONPATH=. python -m pytest
tests/test_kb_longlink_ingest.py -q --noconftest` → 收集期 `ModuleNotFoundError: No module
named 'structlog'`，rc=2）⇒ 下面的用例只能在有依赖的环境里真实执行：
`cd apps/api && uv run pytest tests/test_kb_longlink_ingest.py tests/test_article_identity.py -q -k biz`。
本机侧的等价证明在 `docs/06_validation/evidence/EVD-V2-02/prove_biz_delegation.py`：它用 AST
从**磁盘上的 kb.py** 里取出 `_biz_from_url` 的当前函数体并真实执行（不是抄本），
驱动同一组断言，并带三条反证通道（改坏必须红 / 判据必须能假 / 等价写法必须不假红）。

根因（D-01b）：`kb.py` 旧实现只读 `qs.get("biz")`，而微信长链的真实参数名是 `__biz`
（形状见 `tests/fixtures/wechat_urls.py` 的 `LONG_A`）⇒ 长链入库时 biz 恒为空串，
`_find_source_by_anchor` 的锚点就只剩 article_key，而当时 `_article_key` 取的是 URL 末段
⇒ 同账号所有长链坍缩到同一个锚。本文件证的是这条链的**上游那一环**（锚不该是空串）；
坍缩之后那句 `like('%s%')` 兜底由 S2.1.4 处理，坍缩本身由 S2.2.3 的规范键终结
（`test_two_distinct_long_links` 就是 P-3 的转正判据）。
（刻意只给符号名不给行号：本仓库行号每批都漂，`kb.py:343`/`:554-557` 这类锚在两批内就失效了。）

验收口径（卡面 S2.1.3「补测试」+ 本步补充，全部为本机实测行为）：
1. `_biz_from_url(LONG_A)` 非空且等于 `BIZ_A`；
2. 与 `parse_wechat_url(...).biz` **恒等**（口径单点，不允许两处各说各话），且每条参数化用例
   另带一个字面期望值——恒等式单独不够：委托实现下它天然成立，外链/短链两侧又都是空串。
3. 短链伪 `biz=` 仍解得出（保持既有语义，向后兼容）；
4. `%3D%3D` 与 `==` 两种书写同值；
5. `None`/bytes/int 一律归零且不抛。旧实形的实测行为并不一致：`urlparse(None)` 走
   urllib 的 bytes 强制分支（`query=b''`）⇒ 返回空串，bytes 入参同 ⇒ 静默空串，
   只有 int 抛 `AttributeError: 'int' object has no attribute 'decode'`——委托后三者统一。
"""

from __future__ import annotations

from urllib.parse import quote

import pytest
from fixtures.wechat_urls import (
    BIZ_A,
    LONG_A,
    LONG_A_TRACKING,
    LONG_B,
    OFFSITE,
    SHORT_1,
    SHORT_WITH_FAKE_BIZ_PARAM,
)

from app.services.article_identity import parse_wechat_url
from app.services.kb import _biz_from_url


async def test_two_distinct_long_links(db_session) -> None:  # type: ignore[no-untyped-def]
    """P-3 探针转正（卡面 S2.2.3.3）：**同号两篇长链必须各自独立入库，抓取计数 = 2**。

    改前的实测形态（`docs/任务规划V0.2.0/evidence/probe_longlink_collision.py`）：
    `kb._article_key` 取 URL 末段 ⇒ 两条长链同为 `"s"`，第二篇经"资产等值 `s`"命中
    第一篇的 READY 资产，`hitCache=True` 而正文是**另一篇**——静默错内容，比失败更坏。
    S2.2.3 之后两支各自是 `b:{biz}:{mid}:{idx}`，因此：

    - ①不同 mid 的两篇 ⇒ 两次真实抓取（`fetch_count == 2`）、两个不同 docId、第二篇不命中缓存；
    - ②同一篇的另一种书写（追加追踪参数）⇒ **不**多抓（`fetch_count` 仍为 2）且 `hitCache` 为真。

    两个方向必须同时断言：只断①，实现可以退化成"每次都抓"（缓存被拆掉也算过）；
    只断②，实现可以退化成"按末段坍缩"（正是原缺陷）。
    本机无 PG ⇒ 本条 skip；判定发生在 `@ci` ubuntu（D-V4-01 验收面）。
    """
    from test_langbot import _client  # noqa: PLC0415
    from test_p0_asset_cache import _CountingStubResolver  # noqa: PLC0415

    from app.repositories.space import SpaceRepository
    from app.repositories.user import SqlAlchemyUserStore
    from app.services.kb import KnowledgeBaseService

    user = await SqlAlchemyUserStore(db_session).upsert_by_sub(
        "sub-s223-p3", "s223p3@test.local", "S223-P3"
    )
    space = await SpaceRepository(db_session).create(user_id=user.id, name="S223规范键空间")
    await db_session.commit()

    resolver = _CountingStubResolver()
    svc = KnowledgeBaseService(_client(), db_session, resolver)

    first = await svc.ingest_url(space.id, LONG_A)
    assert first["hitCache"] is False, first
    assert resolver.fetch_count == 1, resolver.fetch_count

    second = await svc.ingest_url(space.id, LONG_B)
    assert resolver.fetch_count == 2, f"同号两篇只抓了一次 ⇒ 键又坍缩了：{second!r}"
    assert second["hitCache"] is False, f"第二篇领到了第一篇的资产：{second!r}"
    assert second["docId"] != first["docId"], (first, second)

    # 同一篇的另一种书写：不该多抓一次，也不该新建文档
    third = await svc.ingest_url(space.id, LONG_A_TRACKING)
    assert resolver.fetch_count == 2, f"追踪参数改变了文章身份 ⇒ 重复抓取：{third!r}"
    assert third["hitCache"] is True, f"同篇两形态没走缓存：{third!r}"


def test_long_link_yields_non_empty_biz() -> None:
    """改前红的那一条：长链的号主身份不得再是空串。"""
    assert _biz_from_url(LONG_A) == BIZ_A, f"长链 biz 仍为空/错值：{_biz_from_url(LONG_A)!r}"
    assert _biz_from_url(LONG_B) == BIZ_A, f"同号主另一篇：{_biz_from_url(LONG_B)!r}"


@pytest.mark.parametrize(
    ("url", "expected"),
    [(LONG_A, BIZ_A), (LONG_A_TRACKING, BIZ_A), (LONG_B, BIZ_A), (OFFSITE, ""), (SHORT_1, "")],
    ids=["long_a", "long_a_tracking", "long_b", "offsite", "short_1"],
)
def test_delegation_is_the_single_source_of_truth(url: str, expected: str) -> None:
    """两条独立的锚：字面期望值 + 与 `parse_wechat_url(...).biz` 恒等。

    恒等式只能抓「kb 侧与解析侧分叉」，抓不到两侧**共同退化**：本机实测把两边都换成
    恒返回 `""` 后，5 条恒等式全绿，而字面期望锚红 3 条（LONG_A / LONG_A_TRACKING / LONG_B）。
    另外 OFFSITE 与 SHORT_1 两侧本来就是空串，单看这一对是 `"" == ""`（复审报告 id 2，
    两条锚的分工实测在 `out_s213.txt` F 段）。
    下表五个期望值取自磁盘 kb.py 的真实执行（EVD-V2-02 通道 C），不是推断。
    """
    assert _biz_from_url(url) == expected, f"{url[:48]!r}… → {_biz_from_url(url)!r}，期望 {expected!r}"
    assert _biz_from_url(url) == parse_wechat_url(url).biz, (
        f"kb 侧与解析侧口径分叉：kb={_biz_from_url(url)!r} vs parse={parse_wechat_url(url).biz!r}"
    )


def test_short_link_pseudo_biz_still_resolves() -> None:
    """向后兼容：短链上的伪 `biz=` 参数仍要解得出（`kb.py:343` 的锚点语义依赖它）。"""
    assert _biz_from_url(SHORT_WITH_FAKE_BIZ_PARAM) == BIZ_A, (
        f"伪 biz 退化：{_biz_from_url(SHORT_WITH_FAKE_BIZ_PARAM)!r}"
    )


def test_percent_encoded_biz_is_equivalent() -> None:
    """`%3D%3D` 与 `==` 是同一个 biz 的两种书写（旧实现同样经 parse_qs，保持这一性质）。"""
    encoded = LONG_A.replace(BIZ_A, quote(BIZ_A, safe=""))
    assert encoded != LONG_A, "夹具 BIZ_A 已不含需编码字符 ⇒ 本用例失去判定力，应删除或换样本"
    assert _biz_from_url(encoded) == _biz_from_url(LONG_A) == BIZ_A, (
        f"{encoded!r} → {_biz_from_url(encoded)!r}｜{LONG_A!r} → {_biz_from_url(LONG_A)!r}"
    )


@pytest.mark.parametrize("bad", [None, b"https://mp.weixin.qq.com/s?__biz=AAA", 42])
def test_non_string_url_returns_empty_without_raising(bad: object) -> None:
    """`Source.url` 可为 NULL/脏类型：委托后统一归零，不再出现 int 那一路的抛错。"""
    assert _biz_from_url(bad) == "", f"非 str 入参未归零：{bad!r} → {_biz_from_url(bad)!r}"  # type: ignore[arg-type]
