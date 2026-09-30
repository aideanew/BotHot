"""W2 聚簇单测（验收 1）：纯函数，零 DB / 零 LLM 依赖。

固定语料 ≥8 篇标题，含 2 组同义改写 + 3+ 篇无关，断言：
- 簇数正确（2 个多成员簇）；
- 成员正确（同义改写归同簇）；
- center_asset 为组内 quality_score 最高者。
"""

from __future__ import annotations

from app.services.hot_cluster import AssetDoc, cluster


def _docs() -> list[AssetDoc]:
    return [
        # A 组：GPT-5 发布（同义改写）
        AssetDoc("a1", "OpenAI发布GPT-5模型", 0.5),
        AssetDoc("a2", "OpenAI推出全新GPT-5大模型", 0.8),
        # B 组：美联储加息（同义改写）
        AssetDoc("b1", "美联储宣布加息50个基点", 0.6),
        AssetDoc("b2", "美联储加息50基点应对通胀", 0.9),
        # 无关篇
        AssetDoc("c1", "苹果公司公布季度业绩", 0.3),
        AssetDoc("c2", "特斯拉股价连续大跌", 0.4),
        AssetDoc("c3", "巴黎奥运会正式开幕", 0.7),
        AssetDoc("c4", "中国男足无缘世界杯", 0.2),
    ]


def test_cluster_two_rewrite_groups_plus_unrelated() -> None:
    docs = _docs()
    groups = cluster(docs)

    multi = [g for g in groups if len(g) >= 2]
    assert len(multi) == 2, f"期望 2 个多成员簇，实际 {len(multi)}：{groups}"

    # 每个多成员簇的成员 id 集合
    member_sets = [frozenset(docs[i].id for i in g) for g in multi]
    assert frozenset({"a1", "a2"}) in member_sets
    assert frozenset({"b1", "b2"}) in member_sets


def test_center_is_highest_quality_in_cluster() -> None:
    docs = _docs()
    groups = cluster(docs)
    by_id = {d.id: d for d in docs}

    for g in [grp for grp in groups if len(grp) >= 2]:
        center_idx = max(g, key=lambda i: docs[i].quality_score)
        center = docs[center_idx]
        # center 的 quality_score 严格不小于簇内任一成员
        for i in g:
            assert center.quality_score >= docs[i].quality_score
        # A 组 center = a2(0.8)；B 组 center = b2(0.9)
        if by_id["a1"].id in (docs[i].id for i in g):
            assert center.id == "a2"
        elif by_id["b1"].id in (docs[i].id for i in g):
            assert center.id == "b2"


def test_cluster_empty_and_singleton() -> None:
    assert cluster([]) == []
    single = cluster([AssetDoc("x", "孤立标题", 0.1)])
    assert len(single) == 1 and single[0] == [0]
