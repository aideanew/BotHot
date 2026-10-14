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
（形状见 `tests/fixtures/wechat_urls.py:45`）⇒ 长链入库时 biz 恒为空串，
`_find_source_by_anchor`（`kb.py:343`）的锚点只剩 article_key，而长链的 article_key
又是 URL 末段 `s`（`kb.py:554-557`）⇒ 同账号所有长链坍缩到同一个锚。
本文件证的是这条链的**上游那一环**（锚不该是空串）；坍缩之后那句 `like('%s%')` 兜底
由 S2.1.4 处理，不在这里。

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
