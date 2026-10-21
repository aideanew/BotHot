"""阶段 C-8/G6（T3.2.2）分类赋值：规则版六类 taxonomy（确定性、离线可测、零外部依赖）。

- 分类仅服务站内筛选（D5=站内公共库先行口径；不承诺通用语义分类）；
- 命中优先级：标题 > 正文（标题主题性强）；同标题多类命中时按声明序取首个
  （顺序即粒度设计：技术域最常用置首）；
- LLM 分类为升级位（categorize 预留语义；接缓存层后可替换内部实现，签名不变）。

STEP-28（D-V12-12）：清单与每类关键词改成**库值优先、代码默认兜底**。
`CATEGORIES` / `_RULES` 因此从"事实"降级成"默认值"，读它们的人改用
`active_categories()` / `enabled_rules()`。库里没有那一行时两者与改前逐字相等——
这条不是兼容姿态，而是 ADR-0013 不变量 1 的定义：删掉配置行必须回到今天的行为，
而不是回到另一个藏在代码里的默认值。

`categorize()` 仍是同步的（`kb.py` 在入库链里直接调它），所以库值走
`system_settings.peek()` 的进程内快照，不查库。
"""

from __future__ import annotations

from typing import Any

from app.services import system_settings

# 声明序即优先级（多命中取首）；前端筛选项顺序与此一致。无库值时的默认清单。
CATEGORIES: list[str] = [
    "AI·技术",
    "产品·商业",
    "行业·动态",
    "观点·评论",
    "教程·实践",
    "其他",
]

DEFAULT_CATEGORY = "其他"

# 分类过滤哨兵（R0.1.1）：契约层表达「未分类」（content_assets.category 为空串的行）。
# 库里不存这个值——它只出现在查询入参，由 SpaceService 译为空串精确匹配。
UNCATEGORIZED = "__uncategorized__"

_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "AI·技术",
        (
            "AI",
            "人工智能",
            "大模型",
            "LLM",
            "GPT",
            "算法",
            "模型",
            "智能体",
            "Agent",
            "RAG",
            "推理",
            "训练",
            "技术",
            "架构",
            "开发",
            "代码",
            "编程",
            "开源",
            "芯片",
            "算力",
            "数据",
        ),
    ),
    (
        "产品·商业",
        ("产品", "商业", "创业", "增长", "营销", "融资", "商业模式", "定价", "用户", "市场"),
    ),
    (
        "行业·动态",
        ("行业", "动态", "发布", "大会", "周报", "日报", "榜单", "融资新闻", "政策", "监管"),
    ),
    (
        "观点·评论",
        ("观点", "思考", "评论", "反思", "随笔", "随想", "杂谈", "研判", "解读"),
    ),
    (
        "教程·实践",
        ("教程", "指南", "实践", "入门", "攻略", "方法论", "手把手", "避坑", "笔记", "心得"),
    ),
]


def default_categories() -> list[dict[str, Any]]:
    """代码默认清单的**库形状**（有序、全启用）。无库值时的读侧回显与写侧起点都取自这里。

    为什么要有这个函数而不是让接口自己拼：接口拼出来的顺序与 `CATEGORIES` 是两份口径，
    漂移的时候没人能看出哪一份是权威的。
    """
    rules = dict(_RULES)
    return [
        {"name": name, "keywords": list(rules.get(name, ())), "enabled": True} for name in CATEGORIES
    ]


def _db_items() -> list[Any] | None:
    """库里的分类清单（`CategorySpec` 列表，有序）；None = 这一行不存在 ⇒ 用代码默认。"""
    return system_settings.peek(system_settings.CATEGORIES_KEY)


def active_categories() -> list[str]:
    """呈现序与筛选可见性用的全清单：**含停用的类**。

    停用只是"不再自动分进来"；历史行还在，筛选项也必须还在——否则运营停用一个类的那一刻，
    库里那些行在界面上同时消失，等于用配置把一个可见的数据集弄没了。
    """
    items = _db_items()
    if items is None:
        return list(CATEGORIES)
    return [str(item.name) for item in items]


def enabled_rules() -> list[tuple[str, tuple[str, ...]]]:
    """参与自动分类的规则（启用项，声明序即优先级）。"""
    items = _db_items()
    if items is None:
        return list(_RULES)
    return [(str(item.name), tuple(str(kw) for kw in item.keywords)) for item in items if item.enabled]


def category_allowlist() -> frozenset[str]:
    """人工纠偏允许的取值：库里登记过的类（含停用）+ 空串（清空回默认）。"""
    return frozenset(active_categories()) | {""}


def categorize(title: str, content: str) -> str:
    """规则版分类：标题命中优先，其次正文计数；零命中 → 其他。"""
    t = (title or "").strip()
    c = (content or "").strip()
    if not t and not c:
        return DEFAULT_CATEGORY

    rules = enabled_rules()
    for category, keywords in rules:
        if any(k.lower() in t.lower() for k in keywords):
            return category
    # 正文按命中数计（≥2 个不同关键词才算主题命中，防正文偶然提及）
    best_category, best_hits = DEFAULT_CATEGORY, 0
    for category, keywords in rules:
        hits = sum(1 for k in keywords if k.lower() in c.lower())
        if hits > best_hits:
            best_category, best_hits = category, hits
    return best_category if best_hits >= 2 else DEFAULT_CATEGORY
