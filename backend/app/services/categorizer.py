"""阶段 C-8/G6（T3.2.2）分类赋值：规则版六类 taxonomy（确定性、离线可测、零外部依赖）。

- 分类仅服务站内筛选（D5=站内公共库先行口径；不承诺通用语义分类）；
- 命中优先级：标题 > 正文（标题主题性强）；同标题多类命中时按 CATEGORIES 声明序取首个
  （顺序即粒度设计：技术域最常用置首）；
- LLM 分类为升级位（categorize 预留语义；接缓存层后可替换内部实现，签名不变）。
"""

from __future__ import annotations

# 声明序即优先级（多命中取首）；前端筛选项顺序与此一致
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
            "AI", "人工智能", "大模型", "LLM", "GPT", "算法", "模型", "智能体",
            "Agent", "RAG", "推理", "训练", "技术", "架构", "开发", "代码",
            "编程", "开源", "芯片", "算力", "数据",
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


def categorize(title: str, content: str) -> str:
    """规则版分类：标题命中优先，其次正文计数；零命中 → 其他。"""
    t = (title or "").strip()
    c = (content or "").strip()
    if not t and not c:
        return DEFAULT_CATEGORY

    for category, keywords in _RULES:
        if any(k.lower() in t.lower() for k in keywords):
            return category
    # 正文按命中数计（≥2 个不同关键词才算主题命中，防正文偶然提及）
    best_category, best_hits = DEFAULT_CATEGORY, 0
    for category, keywords in _RULES:
        hits = sum(1 for k in keywords if k.lower() in c.lower())
        if hits > best_hits:
            best_category, best_hits = category, hits
    return best_category if best_hits >= 2 else DEFAULT_CATEGORY
