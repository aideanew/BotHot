"""STEP-02 S2.3.3：文章键的**跨模块漂移守卫**。

为什么单独一条文件级判据：`kb._article_key` 与 `batch_ingest._article_key` 曾经是同一算法的
两份手写副本（剥 `[?&#]` 取末段）。两份副本并存的后果不是"代码重复"，而是
`Source.external_id` / `ContentAsset.external_id` / `job_items.external_id` 三处落库键可以
在某个 URL 形态上安静分叉——那时同一篇文章在三个表里是三个身份，而没有任何一条断言会红。

S2.2.3/S2.3.3 之后两侧都委托 `article_identity.canonical_article_key`，真源只有一个；
本文件的职责是**盯住"以后有人把其中一侧改回本地实现"**：逐样本比对两个私有函数与规范键的返回值，
再额外用一条反证证明"若真的分叉，这条守卫会红"（否则它只是一个恒真的相等比较）。
"""

from __future__ import annotations

import pytest

from app.services.article_identity import canonical_article_key
from app.services.batch_ingest import _article_key as batch_key
from app.services.kb import _article_key as kb_key

# 覆盖三支各自的边界：b:（长链、乱序参数、带 sn）、s:（合法/过短/含点）、h:（外链、畸形长链、脏串）。
SAMPLES = (
    "https://mp.weixin.qq.com/s?__biz=MjM5MjgwNTQ1MQ==&mid=2650000001&idx=1&sn=aaaa1111",
    "https://mp.weixin.qq.com/s?__biz=MjM5MjgwNTQ1MQ==&mid=2650000002&idx=2&sn=bbbb2222#wechat_redirect",
    "https://mp.weixin.qq.com/s?chksm=xyz&__biz=MjM5MjgwNTQ1MQ==&mid=2650000001&idx=1&sn=aaaa1111",
    "https://mp.weixin.qq.com/s/p0-cache-001",
    "https://mp.weixin.qq.com/s/abc",
    "https://mp.weixin.qq.com/s/a.b.c",
    "https://mp.weixin.qq.com/s?__biz=MjM5&mid=1&idx=1",
    "https://www.ruanyifeng.com/blog/2026/01/x.html",
    "not a url at all",
    "",
    "https://mp.weixin.qq.com/s",
)


@pytest.mark.parametrize("url", SAMPLES, ids=lambda u: u[-42:] or "<empty>")
def test_both_modules_agree_with_the_single_source(url: str) -> None:
    """两个模块的私有取键函数必须与规范键**逐字符相等**，而不是"看起来差不多"。"""
    expected = canonical_article_key(url)
    assert kb_key(url) == expected, f"kb 侧漂移：{url!r} → {kb_key(url)!r} ≠ {expected!r}"
    assert batch_key(url) == expected, f"batch_ingest 侧漂移：{url!r} → {batch_key(url)!r} ≠ {expected!r}"


def test_drift_would_be_caught() -> None:
    """反证：把其中一侧改回旧算法，本文件的比较必须红——否则守卫是恒等式装饰。

    旧算法（剥 query 取末段）在长链上返回 `s`、在过短 token 上返回裸串，
    与规范键的差别正是 P-3 那批缺陷的形状，所以这里能稳定造出分叉。
    """
    import re

    def legacy(url: str) -> str:
        return re.sub(r"[?&#].*$", "", url).rstrip("/").rsplit("/", 1)[-1] or url

    diverged = [u for u in SAMPLES if legacy(u) != canonical_article_key(u)]
    assert diverged, "旧算法与规范键在这些样本上竟完全一致 ⇒ 语料失去判定力，请补长链样本"
    long_link = SAMPLES[0]
    assert legacy(long_link) == "s", f"样本形态变了：{legacy(long_link)!r}"
    with pytest.raises(AssertionError):
        assert legacy(long_link) == canonical_article_key(long_link)
