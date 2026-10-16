"""STEP-02 / S2.1.1：`parse_wechat_url` 的先红用例（P0-1 前半，不依赖 ADR-0011）。

存在理由：改前 `app/services/kb.py` 的 `_biz_from_url` 只读 `biz`，而微信长链的真实参数名
是 `__biz`（形状见 `tests/fixtures/wechat_urls.py:45`）⇒ 长链入库时 biz 恒为空串，
`_find_source_by_anchor` 只剩 article_key 锚 + `Source.url.like(f"%{article_key}%")` 兜底
（`kb.py:359`）——D-01b 与探针 P-4 崩溃都从这条路径进来。本文件先把**解析层**的语义钉住，
实现见 `app/services/article_identity.py`（S2.1.2）；`kb._biz_from_url` 已委托它（S2.1.3，
`kb.py:587-591`，证明在 `EVD-V2-02/prove_biz_delegation.py`）。

口径来源（逐条对应卡面 S2.1.1 交付项）：
- 同 biz 不同 mid：`tests/fixtures/wechat_urls.py:45-46`（探针 P-3 的坍缩对）
- `__biz` 编码形态：`wechat_urls.py:20-23` 声明由本用例自行 `quote()` 生成
- 追踪参数不改变身份：`wechat_urls.py:50-54`
- 短链 token：`wechat_urls.py:57-58`
- `__biz` 优先于 `biz`：`wechat_urls.py:71-74` 的反例 + `test_p0_asset_cache.py:25` 现有语义
- 畸形长链缺 mid：`wechat_urls.py:60-62`
- 非微信域名：`wechat_urls.py:66`

本文件不 import pytest，只用 builtins 断言 ⇒ 两条执行通道都能跑它：
- 真实 pytest：`cd apps/api && PYTHONPATH=. python -m pytest tests/test_article_identity.py -q
  --noconftest`（本机装有 pytest 9.1.1，但没有 sqlalchemy/httpx ⇒ `--noconftest` 是必需的，
  否则 `conftest.py:33` 的 sqlalchemy 导入会让收集失败；本文件不消费任何 conftest 夹具）；
- 纯 stdlib 证明：`python docs/06_validation/evidence/EVD-V2-02/prove_article_identity.py`
  直接调用这些测试函数，并额外做变异反证与语句覆盖（本机无 coverage，实测 ModuleNotFoundError）。
CI 侧走 `uv run pytest`（有 conftest、有依赖），两条通道跑的是同一份代码。
"""

from __future__ import annotations

import ast
import dataclasses
import json
import re
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

from fixtures.wechat_urls import (
    BIZ_A,
    LONG_A,
    LONG_A_TRACKING,
    LONG_B,
    MALFORMED_LONG,
    OFFSITE,
    SHORT_1,
    SHORT_TOKEN_1,
    SHORT_WITH_FAKE_BIZ_PARAM,
)

from app.services import article_identity
from app.services.article_identity import (
    WechatUrlParts,
    canonical_article_key,
    normalize_url,
    parse_wechat_url,
)

WECHAT_HOST = "mp.weixin.qq.com"


def test_long_links_share_biz_but_differ_mid():
    """D-01 的坍缩对：两篇同号文章必须在解析层就分得开（biz 同、mid 异）。"""
    a = parse_wechat_url(LONG_A)
    b = parse_wechat_url(LONG_B)
    assert a.biz == BIZ_A, f"长链应解出 __biz：{a!r}"
    assert b.biz == BIZ_A, f"长链应解出 __biz：{b!r}"
    assert a.mid == "2650000001", f"mid 解析错：{a!r}"
    assert b.mid == "2650000002", f"mid 解析错：{b!r}"
    assert a.biz == b.biz and a.mid != b.mid, f"同 biz 不同 mid 未区分：{a!r} / {b!r}"
    assert a.sn and b.sn and a.sn != b.sn, f"sn 应各自解析且不混：{a.sn!r} / {b.sn!r}"


def test_encoded_biz_param_decodes_to_same_value():
    """`%3D%3D` 与 `==` 是同一个 biz 的两种书写，解析必须收敛为未编码值。"""
    encoded = f"https://{WECHAT_HOST}/s?__biz={quote(BIZ_A, safe='')}&mid=2650000001&idx=1&sn=aaaa1111"
    assert parse_wechat_url(encoded) == parse_wechat_url(LONG_A), "URL 编码形态与明文形态解析结果不同"


def test_tracking_params_do_not_change_identity():
    """追加 chksm/scene/sessionid/srcid/from 与 `#wechat_redirect` 后仍是同一篇。"""
    plain, tracked = parse_wechat_url(LONG_A), parse_wechat_url(LONG_A_TRACKING)
    assert (plain.biz, plain.mid, plain.idx) == (tracked.biz, tracked.mid, tracked.idx), (
        f"追踪参数改变了文章身份：{plain!r} → {tracked!r}")
    assert plain.sn == tracked.sn == "aaaa1111", f"sn 被追踪参数污染：{tracked!r}"


def test_biz_takes_precedence_over_short_biz_param():
    """同时出现 `__biz` 与 `biz` 时取 `__biz`（保持 test_p0_asset_cache 现有语义）。"""
    both = f"https://{WECHAT_HOST}/s?__biz={BIZ_A}&biz=NOT_THE_REAL_ONE&mid=2650000001&idx=2&sn=dddd"
    assert parse_wechat_url(both).biz == BIZ_A, "__biz 未优先于 biz"


def test_short_link_yields_token():
    p = parse_wechat_url(SHORT_1)
    assert p.short_token == SHORT_TOKEN_1, f"短链 token 解析错：{p!r}"
    assert p.biz == "" and p.mid == "", f"短链不该凭空造出 biz/mid：{p!r}"
    assert p.host == WECHAT_HOST


def test_short_link_with_fake_biz_param_still_yields_biz():
    """反例形态（短链路径 + 伪 `biz=`）仍要解出 biz：`kb._biz_from_url` 的历史语义依赖它。"""
    p = parse_wechat_url(SHORT_WITH_FAKE_BIZ_PARAM)
    assert p.biz == BIZ_A, f"短链上的 biz 参数应被识别：{p!r}"
    assert p.short_token == "p0-cache-001", f"短链路径丢了：{p!r}"


def test_malformed_long_link_has_empty_mid():
    """`/s?` 带 `__biz` 却只有 `id`（无 `mid`）⇒ mid 为空串，交由规范键降级分支处理。"""
    p = parse_wechat_url(MALFORMED_LONG)
    assert p.biz == BIZ_A and p.mid == "", f"畸形长链应 biz 有值、mid 空：{p!r}"


def test_idx_defaults_to_one_when_absent():
    """微信长链省略 `idx` 时语义即「第 1 篇」（卡面 S2.1.2：idx 缺省 '1'）。"""
    no_idx = f"https://{WECHAT_HOST}/s?__biz={BIZ_A}&mid=2650000001&sn=eeee"
    assert parse_wechat_url(no_idx).idx == "1", "缺 idx 未落到默认值 '1'"
    assert parse_wechat_url(LONG_A_TRACKING).idx == "1", "正常长链的 idx 被默认值覆盖"


def test_offsite_url_is_not_wechat():
    p = parse_wechat_url(OFFSITE)
    assert p.host != WECHAT_HOST, f"外链被误判为微信：{p!r}"
    assert p.host == "www.ruanyifeng.com"
    assert p.biz == "" and p.short_token == "", f"外链不该造出微信身份：{p!r}"


def test_host_case_folding_keeps_short_token():
    """宿主名大小写混写仍要认出短链（`netloc` 折叠是 host 比较的前提，本步补充口径）。"""
    p = parse_wechat_url(f"https://{WECHAT_HOST.upper()}/s/{SHORT_TOKEN_1}")
    assert p.host == WECHAT_HOST, f"host 未折叠：{p.host!r}"
    assert p.short_token == SHORT_TOKEN_1, f"大小写宿主下丢了短链 token：{p!r}"


def test_parse_returns_frozen_parts():
    """返回类型必须是值对象（纯函数、零 IO），调用方不能靠改字段伪造身份。"""
    p = parse_wechat_url(LONG_A)
    assert isinstance(p, WechatUrlParts)
    assert dataclasses.is_dataclass(p)
    try:
        p.mid = "9999999999"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("WechatUrlParts 可变 ⇒ 文章身份可被就地篡改")


def test_plus_sign_in_biz_is_literal_not_space():
    """`__biz` 是 base64、字符集含 `+` ⇒ 同一 biz 的两种书写必须解出同一个值。

    修前形态：`parse_qs` 按 `x-www-form-urlencoded` 口径把裸 `+` 还原成空格，于是
    `a+b` 与 `a%2Bb` 解出两个不同 biz ⇒ 同一篇文章裂成两条资产（静默、无告警）。
    """
    biz_plus = "MjM5+abc=="
    raw = f"https://{WECHAT_HOST}/s?__biz={biz_plus}&mid=2650000009&sn=cccc"
    enc = f"https://{WECHAT_HOST}/s?__biz={quote(biz_plus, safe='')}&mid=2650000009&sn=cccc"
    assert parse_wechat_url(raw).biz == biz_plus, "裸 + 被当成空格还原"
    assert parse_wechat_url(raw).biz == parse_wechat_url(enc).biz, "同一 biz 的两种书写解出不同值"


def test_non_string_input_yields_empty_parts_without_raising():
    """`Source.url` 可为 NULL 或脏类型 ⇒ 解析层归零返回，不把数据质量问题抛成链路异常。

    本用例同时钉住一条易被「顺手优化」掉的细节：bytes 入参若直送 `urlparse` 会得到
    **bytes 型 host**（`b'' != ''`），于是下游所有 `host == WECHAT_HOST` 比较恒为假——
    不抛异常但静默判错，比抛出来更坏。
    """
    for bad in (None, b"https://mp.weixin.qq.com/s?__biz=AAA", SimpleNamespace(url="x"), 42):
        parts = parse_wechat_url(bad)  # type: ignore[arg-type]
        assert parts == WechatUrlParts(), f"非 str 入参未归零：{bad!r} → {parts!r}"


def test_wechat_params_on_foreign_host_are_still_parsed():
    """当前口径：解析与 host 无关——外链带微信参数照样解出 biz/mid/idx/sn。

    这条不是「漏洞尚未修」，而是**被用例钉住的待定项**：委托后的 `kb._biz_from_url`
    （`kb.py:587-591`）口径即本模块，同样只看查询串，若擅自加 host 闸门，所有非微信源解析出的
    biz 都会变成空串 ⇒ 影响面超出本卡，须经裁决定案。将来定案后要**同步改这条用例**——
    它变绿不代表回归，代表口径已变更。
    """
    parts = parse_wechat_url("https://evil.example.com/s?__biz=MjM5&mid=1&idx=2&sn=aa")
    assert parts.host == "evil.example.com", f"host 未原样保留：{parts!r}"
    assert (parts.biz, parts.mid, parts.idx, parts.sn) == ("MjM5", "1", "2", "aa"), (
        f"查询参数解析与 host 解耦的口径被破：{parts!r}"
    )
    assert parts.short_token == "", "路径不是 /s/ 前缀时不应造出 short_token"


# ── S2.2.1：规范键用例（ADR-0011 §3 的三条不变量逐条对应）──────────────────────


def test_same_article_with_tracking_or_fragment_shares_the_key():
    """不变量②：同一篇长链的多种书写（追踪参数、片段、参数乱序）必须得到**同一个** `b:` 键。"""
    assert canonical_article_key(LONG_A_TRACKING) == canonical_article_key(LONG_A), (
        "追踪参数改变了规范键 ⇒ 同一篇文章会裂成两条资产"
    )
    reordered = LONG_A.replace("__biz=", "zz=1&__biz=", 1)
    assert canonical_article_key(reordered) == canonical_article_key(LONG_A), (
        "多带一个无关参数就换键 ⇒ 键不该依赖参数顺序或无关项"
    )


def test_same_biz_different_mid_diverges():
    """不变量③，也是 P-3 的正身：同 `__biz` 只差 `mid` 的两篇**必须异键**。"""
    key_a, key_b = canonical_article_key(LONG_A), canonical_article_key(LONG_B)
    assert key_a != key_b, f"同号两篇文章坍缩成同一个键：{key_a}"
    assert key_a == f"b:{BIZ_A}:2650000001:1", f"b: 分支形状不符：{key_a}"


def test_bare_short_path_is_no_longer_the_letter_s():
    """`https://mp.weixin.qq.com/s`（无 query、无 token）旧算法返回字母 `s`——本卡的 P-3 根因。

    新算法必须把它降级成 `h:` 分支：既不是 `s`，也不会与任何真实文章键碰撞。
    """
    key = canonical_article_key(f"https://{WECHAT_HOST}/s")
    assert key != "s", "长链退化键回来了"
    assert key.startswith("h:") and len(key) == 34, f"降级分支形状不符：{key}"


def test_short_link_and_offsite_branches():
    """`s:` 分支保留 token 自描述性；非微信（含外链带伪微信参数）一律走 `h:`。"""
    assert canonical_article_key(SHORT_1) == f"s:{SHORT_TOKEN_1}"
    off = canonical_article_key(OFFSITE)
    assert off.startswith("h:") and len(off) == 34, off
    assert off == canonical_article_key(OFFSITE), "哈希分支不确定 ⇒ 同一 URL 两次入库算两条资产"
    assert canonical_article_key(SHORT_WITH_FAKE_BIZ_PARAM) == "s:p0-cache-001", (
        "短链上有伪 biz 参数时应当仍走 s: 分支（mid 缺失 ⇒ b: 条件不成立）"
    )


def test_malformed_long_link_falls_back_to_hash_branch():
    """有 `__biz` 却没有 `mid` 的畸形长链：`b:` 条件不成立、又没有 token ⇒ 降级 `h:`。"""
    key = canonical_article_key(MALFORMED_LONG)
    assert key.startswith("h:") and len(key) == 34, f"畸形长链未降级：{key}"


def test_every_input_yields_a_usable_key():
    """不变量①：任何输入都 ≠ `s` 且长度 ≥ 8（`ArticleKey` 的 pattern/minLength 也这么要求）。"""
    corpus = [
        LONG_A,
        LONG_A_TRACKING,
        LONG_B,
        SHORT_1,
        SHORT_WITH_FAKE_BIZ_PARAM,
        MALFORMED_LONG,
        OFFSITE,
        f"https://{WECHAT_HOST}/s",
        f"https://{WECHAT_HOST}/s/",
        "",
        "/",
        "not a url at all",
    ]
    for url in corpus:
        key = canonical_article_key(url)
        assert key != "s", f"退化键回来了：{url!r}"
        assert len(key) >= 8, f"键短于 8：{url!r} → {key!r}"
    # 唯一性只对"确实是不同文章"的输入主张：LONG_A_TRACKING 与 LONG_A **本该同键**（不变量②），
    # 把它一起放进集合去比长度，等于用一条守卫悄悄否定另一条。
    distinct = [u for u in corpus if u != LONG_A_TRACKING]
    keys = {canonical_article_key(u) for u in distinct}
    assert len(keys) == len(distinct), "两种不同输入得到同一个键（碰撞）"


def test_idx_defaults_to_one_inside_the_b_key():
    no_idx = f"https://{WECHAT_HOST}/s?__biz={BIZ_A}&mid=2650000001&sn=eeee"
    assert canonical_article_key(no_idx).endswith(":1"), canonical_article_key(no_idx)


ARTIFACT_PATH = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "schemas" / "collection.schema.json"


def _contract_article_key_pattern() -> tuple[str, int | None, int | None]:
    """从**生成的契约产物**里按内容取出 `ArticleKey` 的 pattern 与长度界。

    产物里 `ArticleKey` 是别名、会被内联到引用处（登记表 `alias-inlining` 说的就是这件事），
    照 `doc["$defs"]["ArticleKey"]` 读会 KeyError——那是我自己的探针犯过的布局假设错误。
    """
    doc = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))

    def walk(node: object) -> tuple[str, int | None, int | None] | None:
        if isinstance(node, dict):
            pat = node.get("pattern")
            if isinstance(pat, str) and pat.startswith("^(?:b:"):
                return pat, node.get("minLength"), node.get("maxLength")
            for value in node.values():
                found = walk(value)
                if found:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = walk(value)
                if found:
                    return found
        return None

    found = walk(doc)
    assert found, f"产物 {ARTIFACT_PATH.name} 里找不到 ArticleKey 的 pattern"
    return found


def test_every_emitted_key_is_accepted_by_the_contract():
    """不变量④：本函数**产出**的每个键都必须被契约 `ArticleKey` 接受（含对抗输入）。

    第二轮独立验证实测的洞（旧实现全绿通过，因为它从没被喂过这些输入）：
    `b:MjM5:1:1`（biz 短于 8）、`s:abc`（短于 minLength）、130 字符 biz 得到 136 字符键
    （超 `maxLength: 128`）、`/s/AA:BB` 与 `/s/a.b.c`（字符类不符）。
    这些都是 `Source.url` 这类自由字段真能装进去的东西，不是理论构造。
    """
    pattern_text, min_len, max_len = _contract_article_key_pattern()
    pattern = re.compile(pattern_text)
    adversarial = [
        f"https://{WECHAT_HOST}/s?__biz=MjM5&mid=1&idx=1",
        f"https://{WECHAT_HOST}/s?__biz={'A' * 130}&mid=1&idx=1",
        f"https://{WECHAT_HOST}/s/abc",
        f"https://{WECHAT_HOST}/s/AA:BB",
        f"https://{WECHAT_HOST}/s/a.b.c",
        LONG_A,
        LONG_A_TRACKING,
        LONG_B,
        SHORT_1,
        SHORT_WITH_FAKE_BIZ_PARAM,
        MALFORMED_LONG,
        OFFSITE,
        f"https://{WECHAT_HOST}/s",
        "",
        "/",
        "not a url at all",
    ]
    for url in adversarial:
        key = canonical_article_key(url)
        assert pattern.search(key), f"契约拒收本模块产出的键：{url!r} → {key!r}"
        assert key != "s", f"退化键回来了：{url!r}"
        assert (min_len or 0) <= len(key) <= (max_len or 10**9), f"长度越界：{key!r}"


def test_colon_in_biz_or_mid_cannot_forge_the_same_identity():
    """`b:` 三段用 `:` 分隔，所以 `:` 逃进 biz/mid 时会**冒名成同一个键**——P-3 的同族。

    实测旧写法：`__biz=AAAAAAAA:B&mid=C` 与 `__biz=AAAAAAAA&mid=B:C` 都吐
    `b:AAAAAAAA:B:C:1`（解析出的三元组不同、键串相同 ⇒ 两篇文章共用一个身份）。
    现在两支都因形状不合法降级 `h:`，而 `h:` 是归一后 URL 的哈希，两条输入必然不同键。
    """
    forged_a = f"https://{WECHAT_HOST}/s?__biz=AAAAAAAA:B&mid=C&idx=1"
    forged_b = f"https://{WECHAT_HOST}/s?__biz=AAAAAAAA&mid=B:C&idx=1"
    key_a, key_b = canonical_article_key(forged_a), canonical_article_key(forged_b)
    assert key_a != key_b, f"两种不同输入得到同一个文章身份：{key_a}"
    assert key_a.startswith("h:") and key_b.startswith("h:"), (key_a, key_b)
    assert parse_wechat_url(forged_a).biz == "AAAAAAAA:B", "降级必须发生在键层，不是把解析改了"


def test_normalize_url_drops_tracking_and_sorts_params():
    """`h:` 分支的归一口径：去 fragment、去追踪参数（含 `utm_*`）、其余按键排序。"""
    messy = "https://ExAMPLE.com/Article?b=2&a=1#frag&chksm=xyz&utm_source=weixin&scene=27"
    assert normalize_url(messy) == "https://example.com/Article?a=1&b=2", normalize_url(messy)
    shuffled = normalize_url("https://example.com/a?z=1&a=0&a=0")
    assert shuffled == "https://example.com/a?a=0&a=0&z=1", shuffled
    assert normalize_url("https://example.com/a?a=0&z=1&a=0") == shuffled, (
        "同一组参数换个顺序，归一后不同 ⇒ 哈希分支会裂成两个身份"
    )
    assert normalize_url("") != normalize_url("/"), (
        "脏输入被归一折叠成同一个串 ⇒ 两种无关脏输入会得到同一个文章身份"
    )


def test_canonical_key_does_not_reparse_the_url():
    """不变量⑤：规范键**不许**自己再解析一遍 URL——必须委托 `parse_wechat_url`（单一来源）。

    判据写在源码文本上而不是行为上：行为等价但自己解析的实现，会在下一次改解析口径时
    悄悄与 `kb._biz_from_url`（同样委托本模块）分家——那正是本卡反复处理的双源病。

    读文件而不是 `inspect.getsource`：证明通道（`EVD-V2-02/prove_article_identity.py`）
    是把实现 exec 进内存的，那时 `getsource` 抛 `OSError: source code not available`，
    这条用例会**因为运行方式**而不是因为实现有缺陷而红——实测踩过（self-test 的等价重构
    PI-6 报它假红）。按 `__file__` 取源码在两条通道下都成立。
    """
    src = Path(article_identity.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == "canonical_article_key"
    )
    body_src = ast.get_source_segment(src, fn) or ""
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(ast.parse(body_src))
        if isinstance(node, ast.Call)
    }
    assert "parse_wechat_url" in called, f"规范键没有委托唯一解析源，实际调用：{sorted(called)}"
    for forbidden in ("urlparse", "urlsplit", "parse_qs", "parse_qsl"):
        assert forbidden not in called, f"规范键里出现了第二次解析：{forbidden}"


def test_non_string_input_raises_instead_of_a_constant_key():
    """脏输入必须抛，不能退化成某个固定键：常量键会让所有脏输入共享一个身份（静默碰撞）。

    与 `parse_wechat_url` 的"归零返回"口径**故意不同**：解析层归零是把判断交给调用方，
    而身份键层若归零成常量，就是在伪造身份。
    """
    for bad in (None, b"https://mp.weixin.qq.com/s/x", 42):
        try:
            canonical_article_key(bad)  # type: ignore[arg-type]
        except TypeError:
            continue
        raise AssertionError(f"非 str 入参未抛 TypeError：{bad!r}")
    # `normalize_url` 也是导出的公开面（ADR-0011 §2 把它单列），它自己的那道闸必须单独钉一次：
    # 只靠 canonical_article_key 先抛，等于把 normalize_url 的守卫留给"恰好没人直接调它"。
    for bad in (None, 42):
        try:
            normalize_url(bad)  # type: ignore[arg-type]
        except TypeError:
            continue
        raise AssertionError(f"normalize_url 非 str 入参未抛：{bad!r}")
