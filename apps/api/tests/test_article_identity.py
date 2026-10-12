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

import dataclasses
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

from app.services.article_identity import WechatUrlParts, parse_wechat_url

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
