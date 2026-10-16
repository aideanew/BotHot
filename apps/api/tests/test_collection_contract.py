"""STEP-01 S1.3.2 + S1.4.1 —— 采集域契约的语义比对与锚定测试。

要防的事（这条文件存在的唯一理由）：`gen_contracts --check` 只保证
「产物 == 模型的 JSON Schema」，**不保证「模型 == 冻结稿」**。
中间那一段如果没人管，唯一源就退化成"我以为它是唯一源"。

三条纪律，每条都有对应的反证测试，不是口号：
1. **归一不免费** —— 比对器每用一次归一，都必须有对应 kind 的登记；
   反过来登记表里每条 `rule` 也必须真被消费。第五轮验证把"消费"收窄成两档：
   **被比对器当归一用到**，或**由本文件某个具名断言兑现**——
   "它解释过一处差异"不再算消费，因为一条专门用来遮差异的登记会自己给自己发消费者。
   双向核对见 `test_registry_rules_are_all_consumed`。
   第三轮独立验证就是拿这个打的：`x-not`、"另设 dump 形状检查"、`strictness` 三条当时是
   **只有承诺、没有实现者**的装饰条目。
2. **未知关键词两侧都查** —— 稿**和生成物**任一出现比对器没实现的关键词 ⇒ 红。
   第一版只查稿侧，所以往生成物塞 `minItems` / `const` 能静默溜过去。
3. **pattern 比文本推导，不只比语料** —— 稿的 `oneOf` 三支去掉 `^`/`$` 折成
   `^(?:A|B|C)$` 后必须与生成物 pattern **逐字符相等**。
   有限语料会被 `{32}`→`{31,32}`、字符类去掉 `-`、`{1,12}`→`{1,13}` 绕过：
   量词与字符类是正则语义，样本再多也罩不住（`_PATTERN_CORPUS` 只是第二层）。

`jsonschema` / `hypothesis` 都不在依赖里，也**不装**：比对器自己实现稿实际用到的关键词子集。
不起 TestClient（U-23 的挂起面就在那）、不连库、不联网。
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, get_type_hints

import pytest
from pydantic import TypeAdapter, ValidationError

from app.contracts import events as events_contract
from app.contracts import identity as identity_contract
from app.contracts.collection import (
    ARTICLE_KEY_PATTERN,
    CONTRACT_DIVERGENCES,
    ArticleKey,
    ChannelName,
    CollectionEvent,
    DiscoveryChannelView,
    Divergence,
    ManifestStatus,
    ManifestSyncReport,
    WorkListPage,
    WorkListRow,
)
from app.core.errors import ERROR_CODES
from app.providers.discovery.registry import CHANNELS
from app.providers.push.base import PushResult
from app.services.push_events import VALID_EVENT_TYPES
from app.services.push_scheduler import MAX_PUSH_RETRIES, RETRY_BACKOFF_BASE_SECONDS
from app.services.roles import ROLE_RANK

REPO_ROOT = Path(__file__).resolve().parents[3]
FROZEN_PATH = REPO_ROOT / "docs" / "任务规划V0.12.0" / "contracts" / "collection.schema.json"
GENERATED_PATH = REPO_ROOT / "packages" / "contracts" / "schemas" / "collection.schema.json"
ERRORS_FROZEN_PATH = REPO_ROOT / "docs" / "任务规划V0.12.0" / "contracts" / "errors.global.schema.json"
GEN_CONTRACTS_PATH = REPO_ROOT / "scripts" / "gen_contracts.py"
CONTRACT_DIR = REPO_ROOT / "docs" / "任务规划V0.12.0" / "contracts"
SCHEMA_DIR = REPO_ROOT / "packages" / "contracts" / "schemas"

# 每个域一行：稿、生成物、该域的登记表。加域就加一行——比对器不该只服务 collection。
DOMAINS: dict[str, tuple[Path, Path, tuple[Divergence, ...]]] = {
    "collection": (FROZEN_PATH, GENERATED_PATH, CONTRACT_DIVERGENCES),
    "identity": (
        CONTRACT_DIR / "identity.schema.json",
        SCHEMA_DIR / "identity.schema.json",
        identity_contract.CONTRACT_DIVERGENCES,
    ),
    "events": (
        CONTRACT_DIR / "events.schema.json",
        SCHEMA_DIR / "events.schema.json",
        events_contract.CONTRACT_DIVERGENCES,
    ),
}

# 比对器**实现了**的校验关键词。两侧任一出现别的关键词 ⇒ 红（宁可吵，不可静默少比）。
# `default` 从"剥离表"移进来了（第五轮验证 I10/I10b/X3：两侧随便改 default 都读出 0 条差异）。
SUPPORTED_VALIDATING_KEYWORDS = frozenset(
    {
        "type",
        "enum",
        "const",
        "pattern",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "minItems",
        "items",
        "required",
        "additionalProperties",
        "format",
        "properties",
        "$ref",
        "oneOf",
        "anyOf",
        "default",
    }
)
# 人读面关键词：允许存在，但必须由登记表的 rule 解释
STRIPPED_KEYWORDS_TO_RULE = {
    "title": "strip-title",
    "description": "strip-description",
}
# 这些键不参与"未映射关键词"判定（结构性或文档性，已由别处处理）。
# `default` 以前在这里——第五轮验证证明那正是"两侧随便改默认值都不响"的根因，已移进校验面。
_NON_CONSTRAINT_KEYS = frozenset({"$defs", "definitions", "$schema", "$id", "$ref", "title", "description"})


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


_LOADED: dict[Path, dict[str, Any]] = {}


def load_cached(path: Path) -> dict[str, Any]:
    """两个文档要读很多次（9 个 def 各参数化一条），缓存掉：第一版没缓存时这文件跑 75s。"""
    if path not in _LOADED:
        _LOADED[path] = _load(path)
    return _LOADED[path]


def _defs_of(doc: dict[str, Any]) -> dict[str, Any]:
    """collection 的稿用 2020-12 的 `$defs`，其余四域的稿用 draft-07 的 `definitions`。

    生成物一律 `$defs`。两种方言并存是稿子内部的不一致，比对时按同一语义处理；
    不做这层归一，后四个域会整域报「生成物缺 def」。
    """
    return doc.get("$defs") or doc.get("definitions") or {}


def _ref_name(node: dict[str, Any]) -> str:
    return str(node["$ref"]).rsplit("/", 1)[-1]


def _walk(node: Any, where: str, defs: dict[str, Any], problems: list[str], seen: frozenset[str]) -> None:
    """未知关键词 ⇒ 记一条问题。**稿侧与生成物侧都要跑**。

    只从已知结构位下钻（`properties` 的每个值、`items`、`oneOf/anyOf` 分支、`$ref` 目标）。
    第一版把 `properties` 容器当关键词表遍历，踩了两个坑：空 dict 自我递归（RecursionError）、
    名叫 `title` / `description` 的**属性**被当成 schema 关键词 continue 掉 ⇒ 静默没比。
    """
    if isinstance(node, list):
        for i, item in enumerate(node):
            _walk(item, f"{where}[{i}]", defs, problems, seen)
        return
    if not isinstance(node, dict) or not node:
        return
    for key in node:
        if (
            key in SUPPORTED_VALIDATING_KEYWORDS
            or key in STRIPPED_KEYWORDS_TO_RULE
            or key in _NON_CONSTRAINT_KEYS
            or key.startswith("x-")
        ):
            continue
        problems.append(f"{where}: 比对器不认识关键词 {key!r}（要么实现它，要么改一侧——不能忽略）")
    for name, sub in (node.get("properties") or {}).items():
        _walk(sub, f"{where}.{name}", defs, problems, seen)
    if node.get("items") is not None:
        _walk(node["items"], f"{where}.items", defs, problems, seen)
    for i, branch in enumerate(node.get("oneOf") or node.get("anyOf") or []):
        _walk(branch, f"{where}.oneOf[{i}]", defs, problems, seen)
    if "$ref" in node:
        target_name = _ref_name(node)
        if target_name in seen:
            return
        if target_name not in defs:
            problems.append(f"{where}: $ref 指向不存在的 {node['$ref']}")
            return
        _walk(defs[target_name], f"{where}->{target_name}", defs, problems, seen | {target_name})


def _resolve(node: Any, defs: dict[str, Any]) -> Any:
    """展开 `$ref`。2020-12 允许 `$ref` 与兄弟关键词并存且**两者都生效** ⇒ 必须合并。

    第一版只在"整节点就是 $ref"时展开，于是 `{"$ref":…, "description":…}`
    被当成无约束，稿侧比出 None（假差异）。
    """
    if isinstance(node, dict):
        if "$ref" in node:
            name = _ref_name(node)
            if name not in defs:
                return {"__unresolved_ref__": node["$ref"]}
            siblings = {k: v for k, v in node.items() if k != "$ref"}
            return {**_resolve(defs[name], defs), **siblings}
        return {k: _resolve(v, defs) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve(x, defs) for x in node]
    return node


def canonical_alternation(patterns: list[str]) -> str:
    """把多条带锚 pattern 折成一条 alternation（与 `ARTICLE_KEY_PATTERN` 的构造方式一致）。"""
    stripped = [re.sub(r"^\^", "", re.sub(r"\$$", "", p)) for p in patterns]
    return "^(?:" + "|".join(stripped) + ")$"


# 语料是**第二层**（第一层是文本推导）。补齐第三轮验证指出缺的边界见证：
# 连字符 token、biz 长度边界、hex 长度边界、mid/idx 位数边界。
_PATTERN_CORPUS = (
    "b:MzI4NjA5NTU4Mg:2650635316:1",
    "b:MzI4NjA5NTU4Mg:2650635316:12",
    "b:ab-cd_ef-gh:1:1",
    "b:short:1:1",
    "b:MzI4NjA5NTU4Mg:1234567890123:1",
    "b:MzI4NjA5NTU4Mg:2650635316:123",
    "s:abcDEF12",
    "s:ab-cd_ef",
    "s:tooShort",
    "h:0123456789abcdef0123456789abcdef",
    "h:0123456789abcdef0123456789abcde",
    "h:0123456789abcdef0123456789abcdef0",
    "h:0123456789ABCDEF0123456789abcdef",
    "s",
    "ssssssss",
    "x:abcdefgh",
    "s:abcDEF12XYZ",
    "xs:abcDEF12",
    "",
)

_USED_RULES: set[str] = set()
_USED_EXPLAINERS: set[str] = set()


def _note_rule(rule: str) -> None:
    """记"比对器用了这条**归一**"（要在 kind 映射表里有归属）。"""
    _USED_RULES.add(rule)


def _note_explainer(rule: str) -> None:
    """记"某条登记解释了**一处具体差异**"。

    与归一分开记是必要的：tightening/strictness 这类条目本来就不属于归一表，
    混在一起会让正向核对要么 KeyError、要么被放宽成没意义的断言。
    """
    _USED_EXPLAINERS.add(rule)


def _pattern_fact(node: dict[str, Any]) -> str:
    """一个节点的 pattern 事实：canonical 文本 + 语料接受向量。

    两层都比：改文本被抓，改语义也被抓，只留一层就会漏（第一版只留了语料那层）。
    """
    branches = [str(b["pattern"]) for b in (node.get("oneOf") or []) if isinstance(b, dict) and "pattern" in b]
    if "pattern" in node:
        branches.append(str(node["pattern"]))
    if not branches:
        return ""
    text = canonical_alternation(branches) if len(branches) > 1 else branches[0]
    vector = "".join("1" if any(re.search(p, w) for p in branches) else "0" for w in _PATTERN_CORPUS)
    if len(branches) > 1:
        _note_rule("oneOf-to-pattern-set")
    # 锚保真：canonical_alternation 会去掉^/$再补回来，所以**它对锚天生不敏感**
    # （第四轮验证正是用"s: 分支丢掉结尾 $"穿过来的）。因此额外记录每条分支自己是否带锚，
    # 锚与量词改动都会改变上面这三段中的某一段；不比较"分支原文"本身，
    # 因为多支折成一条正是登记过的 structural 差异（比原文等于把登记当没写过）。
    # 逐支记录 would 让"三支折成一条"这件事本身变成差异（"111" vs "1"），
    # 所以只记"是否全部带锚"这一个布尔：掉锚仍然被抓，而折叠不再制造假差异。
    anchored = "1" if all(p.startswith("^") and p.endswith("$") for p in branches) else "0"
    return f"{text}#{anchored}#{vector}"


def _canon(node: Any) -> dict[str, Any]:
    """归一成只含约束事实的字典。

    **没被本函数映射过的关键词不会被静默丢掉**：它们进 `unmapped` ⇒ 成为差异。
    第三轮验证往生成物塞 `minItems` / `const` 能溜过去，就是因为第一版只读它认识的那几个键。
    """
    node = node if isinstance(node, dict) else {}
    facts: dict[str, Any] = {}
    types: list[str] = []
    nullable = False
    merged_single_anyof = False
    if isinstance(node.get("type"), list):
        types = [t for t in node["type"] if t != "null"]
        nullable = "null" in node["type"]
    elif "type" in node:
        types = [str(node["type"])]
    if "anyOf" in node:
        branches = node["anyOf"]
        nullable = any(b == {"type": "null"} for b in branches if isinstance(b, dict))
        real = [b for b in branches if b != {"type": "null"}]
        if len(real) == 1 and isinstance(real[0], dict):
            sub = _canon(real[0])
            types = sub.pop("types", [])
            nullable = nullable or bool(sub.pop("nullable", False))
            facts.update(sub)
            merged_single_anyof = True
    branches = node.get("oneOf") or node.get("anyOf") or []
    all_pattern_branches = bool(branches) and all(
        isinstance(b, dict) and set(b) <= {"pattern", "title"} for b in branches
    )
    if branches and not all_pattern_branches and not merged_single_anyof:
        # oneOf/anyOf 的分支**不是纯 pattern 包装**时，它是真约束（const/minimum/type 分支…）。
        # 第一版只把分支里的 pattern 折走、其余静默丢弃 ⇒ 第四轮验证塞一个
        # `oneOf: [{"const": 0}]` 进去，门禁 0 条差异。
        # 第五轮验证又抓到两个洞：条件里写的 `"anyOf" not in node` 让**两支及以上**的 anyOf
        # 整块消失（稿 `[{"const":0},{"const":1}]` vs 生成物 `[{"const":0},{"const":2}]` 读 0 条），
        # 而"合并单支"那种可空写法（nullable-form 归一）必须继续合并、不能再比分支。
        # 所以判据换成"有没有被当可空合并掉"，而不是"是不是 anyOf"。
        facts["branches"] = sorted(json.dumps(_canon(b), sort_keys=True, ensure_ascii=False) for b in branches)
    pf = _pattern_fact(node)
    if pf:
        facts["pattern"] = pf
    for key in (
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "format",
        "enum",
        "additionalProperties",
        "const",
        "minItems",
        "default",
    ):
        if key in node:
            facts[key] = node[key]
    if "required" in node:
        facts["required"] = sorted(node["required"])  # required 是集合，不比顺序
        _note_rule("required-order")
    if "items" in node:
        # 数组形式的 items（tuple 校验）第一版被 `_canon(list)` 折成空事实 ⇒ 两支各写
        # maxLength 5 / 9 读出来是 0 条差异（第五轮验证 I9/I9b）。逐位比，不比顺序之外的东西。
        items = node["items"]
        facts["items"] = [_canon(x) for x in items] if isinstance(items, list) else _canon(items)
    if "properties" in node:
        facts["properties"] = {k: _canon(v) for k, v in node["properties"].items()}
    unmapped = sorted(
        k
        for k in node
        if k not in SUPPORTED_VALIDATING_KEYWORDS
        and k not in STRIPPED_KEYWORDS_TO_RULE
        and k not in _NON_CONSTRAINT_KEYS
        and not k.startswith("x-")
    )
    if unmapped:
        facts["unmapped"] = unmapped
    facts["types"] = sorted(types)
    facts["nullable"] = nullable
    for k in node:
        if k in STRIPPED_KEYWORDS_TO_RULE:
            _note_rule(STRIPPED_KEYWORDS_TO_RULE[k])
    if isinstance(node.get("type"), list) or "anyOf" in node:
        _note_rule("nullable-form")
    return facts


# 归一规则 → 它必须由哪种 kind 的登记撑腰
_NORMALIZATION_TO_KIND = {
    "strip-title": "documentation",
    "strip-description": "documentation",
    "dump-materializes-defaults": "serialization",
    "nullable-form": "structural",
    "oneOf-to-pattern-set": "structural",
    "ref-inlining": "structural",
    "required-order": "structural",
    "alias-inlining": "structural",
    "not-a-shape": "structural",
    "definitions-vs-refs-dialect": "structural",
}

# 登记表 `kind` 的合法取值（`app/contracts/__init__.py` 的 Divergence 文档注释里就这五种）。
# 第五轮验证点名"kind 从来没被校验过"：写个 `kind="magic"` 等于给这条登记凭空造第六种放行能力。
# `conflict` 是第六轮验证之后加的**第六种**：稿与实测类型不相交（不是等价写法、也不是宽严关系），
# 只能靠"取实测 + 引一条台账裁决号"过关，见 `test_conflict_entries_cite_a_live_decision_id`。
DIVERGENCE_KINDS = frozenset(
    {"structural", "tightening", "serialization", "strictness", "documentation", "conflict"}
)

# 声明"这个 def 不是形状"时，**允许**出现的校验关键词只有这两个：
# 纯注释块也总要写个 `type`，而 `$ref` 由 `_referenced_by` 单独管。
# 其余每一个校验关键词都是真约束——带了它还想退出比对，等于把约束静默删掉。
# 第六轮验证 G1 正是这样让 `IdempotencyKey.maxLength=128` 凭空消失的：
# 那条 def 被标成非形状之后，不仅约束离开了产物，连"必须有见证测试"的强制也不再触发。
_MARK_FORBIDDEN_KEYWORDS = frozenset(SUPPORTED_VALIDATING_KEYWORDS - {"type", "$ref"})

# 归一之后的**叶子事实名**。一条登记的 `field` 不许直接写这些词——
# 写了就等于"这个 def 里这类差异我全权解释"，而登记的意义必须是**点名到契约字段**。
# 第六轮验证的 D5：identity 的 `exp-required` 用 `field="exp, required"` 解释了
# `SessionClaims.required=[]`（把必填 `sub` 删掉），一句"exp 变必填"买到了整类放行。
_BARE_FACT_KEYS = frozenset(
    {
        "type",
        "types",
        "nullable",
        "required",
        "default",
        "enum",
        "const",
        "pattern",
        "format",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "minItems",
        "items",
        "properties",
        "additionalProperties",
        "branches",
        "unmapped",
    }
)

# 每一类事实**允许**由哪种 kind 解释。空集 = 永远不可解释（未知关键词）。
# 这一张表是第六轮验证 D4/D8 的直接回应：`kind` 过去在 `_explains` 里完全不参与判定，
# 所以一条 `kind="documentation"` 的登记可以解释"类型改了"。
FACT_ALLOWED_KINDS: dict[str, frozenset[str]] = {
    "types": frozenset({"structural", "conflict"}),
    "nullable": frozenset({"structural", "conflict"}),
    "required": frozenset({"structural", "tightening"}),
    "enum": frozenset({"structural"}),
    "pattern": frozenset({"structural"}),
    "items": frozenset({"structural"}),
    "branches": frozenset({"structural"}),
    "const": frozenset({"structural"}),
    "minItems": frozenset({"structural"}),
    "format": frozenset({"structural", "tightening"}),
    "additionalProperties": frozenset({"structural", "strictness"}),
    "maxLength": frozenset({"structural", "tightening"}),
    "minLength": frozenset({"structural", "tightening"}),
    "maximum": frozenset({"structural", "tightening"}),
    "minimum": frozenset({"structural", "tightening"}),
    "default": frozenset({"serialization"}),
    "properties": frozenset({"structural"}),
    "unmapped": frozenset(),
}


def _is_empty_value(value: Any) -> bool:
    """"物化出来的默认值确实是空值"——`False` 不算（它是一个语义决定，不是"缺失即空"）。"""
    if value is None or value == "":
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return value == 0
    return isinstance(value, list | dict | set) and len(value) == 0


class _Missing:
    """"这一侧根本没有这个键"的哨兵。必须在 `_explains` 之前定义——
    它同时是那两个参数的默认值，而默认值在 import 期求值。"""

    def __repr__(self) -> str:
        return "（无此键）"


MISSING = _Missing()


def _direction_ok(leaf: str, fa: Any, fb: Any, entry: Divergence, fields: set[str]) -> bool:
    """同样被"允许"的 kind，还得**方向对**：登记说的是收紧，实际就必须是收紧。

    没有这一层，kind 表只是一份更漂亮的词表——第六轮验证的 D5/D4 都是"kind 对了、方向反了"：
    把必填删掉被 `tightening` 解释、把 maxLength 放宽被 `tightening` 解释。
    （两侧的 MISSING 情形由 `_explains` 在第 6 道闸处理，不会走到这里。）
    """
    if leaf == "required":
        if entry.kind == "structural":
            return True
        # tightening 只接受"产物比稿更严且增量都在点名字段里"
        return isinstance(fa, list) and isinstance(fb, list) and set(fa) <= set(fb) and set(fb) - set(fa) <= fields
    if leaf in {"maxLength", "maximum"}:
        tighter = isinstance(fb, int | float) and isinstance(fa, int | float) and fb <= fa
        return entry.kind == "structural" or tighter
    if leaf in {"minLength", "minimum"}:
        tighter = isinstance(fb, int | float) and isinstance(fa, int | float) and fb >= fa
        return entry.kind == "structural" or tighter
    if leaf == "additionalProperties":
        # strictness 的方向只有一个：稿没说话（或明说允许）而产物**禁止**多余键。
        return entry.kind == "structural" or (fb is False and (fa is MISSING or fa in (None, True)))
    return True



def _raw_marks(frozen: dict[str, Any]) -> set[str]:
    """稿根 `x-not-in-single-source` 里**确实是 def** 的那些键（根层治理注释不在此列）。"""
    mark = frozen.get("x-not-in-single-source") or {}
    if not isinstance(mark, dict):
        return set()
    return {str(k) for k in mark if k in _defs_of(frozen)}


def _constraint_bearing(node: Any) -> set[str]:
    """这个 def 带了真约束吗？带了就不许声明「自己不是形状」。

    第六轮验证 G1：`IdempotencyKey` 的 `{type, maxLength:128}` 里只有 `type` 被我原来的
    `_SHAPE_BEARING_KEYWORDS` 认下来，于是「它不是形状」这句话**通过了所有检查**，
    128 这条约束无声离开产物，连"消失的 def 必须有见证测试"那条强制也不再触发
    （因为它已经不在「消失的 def」那张表里了）。判据必须是「除 type/$ref 外无任何校验关键词」。
    """
    if not isinstance(node, dict):
        return set()
    return {k for k in node if k in _MARK_FORBIDDEN_KEYWORDS}


def _not_a_shape_names(frozen: dict[str, Any]) -> tuple[set[str], list[str]]:
    """返回 (合法退出的注释性 def 名, 非法标记的差异说明)。

    非法标记不进 `excluded`——它不会让那个 def 消失，只会额外产出一条差异；
    这样「想靠一句声明删约束」从**放行**变成**必红**。
    """
    defs = _defs_of(frozen)
    ok: set[str] = set()
    bad: list[str] = []
    for name in _raw_marks(frozen):
        offending = _constraint_bearing(defs[name])
        if offending:
            bad.append(
                f"{name}: 稿把它标成「不在唯一源里」，但它带着校验关键词 {sorted(offending)} "
                "⇒ 那是约束不是注释，必须收编或点名见证测试"
            )
            continue
        if not str(frozen["x-not-in-single-source"][name]).strip():
            bad.append(f"{name}: 标了「不在唯一源里」却没写理由/责任人")
            continue
        ok.add(name)
    return ok, bad


# 文档根层要比的校验键（第六轮验证 G6：过去只比 `$defs`，根层整片没人管）。
_ROOT_VALIDATING_KEYS = ("type", "required", "additionalProperties", "$id", "$schema")


def _explains_root(divergences: tuple[Divergence, ...], key: str, fa: Any, fb: Any) -> Divergence | None:
    """根层差异的解释：`ref` 写明是文档根、`field` 点名该键，**并且方向要合法**。

    第一版我只做了前两条，第六轮验证的 G6a/b/c 立刻证明这不够：一条同时点名 `type` 与 `$id`
    的宽登记，把"往产物根塞 `type: string`"也一起洗白了——和 def 层那条 `field="*"` 是同一种病。
    - 稿声明、产物没声明（`fb is MISSING`）⇒ `structural` 可以解释：容器文档根层不声明单一形状；
    - 产物声明、稿没声明（`fa is MISSING`）⇒ 源在凭空加约束，必须 `conflict`；
    - 两侧都声明但值不同 ⇒ 不是等价写法，必须 `conflict`，并由
      `test_conflict_entries_cite_a_live_decision_id` 要求它引一条真实台账行。
    """
    for d in divergences:
        if "文档根" not in d.ref or key not in _field_tokens(d.field):
            continue
        if fb is MISSING and d.kind == "structural":
            return d
        if d.kind == "conflict":
            return d
    return None


def _stale_root_entries(divergences: tuple[Divergence, ...], frozen: dict, generated: dict) -> list[str]:
    """登记了根层某个键的不等价，但现在两侧一致 ⇒ 这条登记已经过期，必须红。

    没有这一条，"把稿根的 `type` 删掉"（G6b）会让差异**消失**而不是变红：
    宽登记继续挂在那里，谁也不会发现契约面被偷偷改过。
    """
    out: list[str] = []
    for d in divergences:
        if "文档根" not in d.ref:
            continue
        for token in _field_tokens(d.field):
            if token not in _ROOT_VALIDATING_KEYS:
                continue
            if frozen.get(token, MISSING) == generated.get(token, MISSING):
                out.append(f"*: 登记（{d.rule}）声称根层 {token} 不等价，但两侧现在一致 ⇒ 过期登记")
    return out




def _default_explainer(divergences: tuple[Divergence, ...], def_name: str, prop: str) -> Divergence | None:
    """`default` 差异**只接受一个方向、且必须点名到具体属性**。

    - 方向：稿里没写、模型物化出来了（serialization 类登记）才算合法；
      反向（稿有 default 而生成物没有）与"两侧都有但不同"都是硬差异——
      否则"把稿里声明的默认改掉"就变成一件登记一下就合法的事。
    - 点名：登记的 `field` 必须列出这个属性名。第五轮验证的第二类洞正在这：
      只按 def 放行的话，把 `pages` 的默认从 0 改成 7 也是"稿没写 ⇒ 模型物化"，
      照样溜过去。现在没列名的属性一旦物化出默认值就红，
      于是"哪些属性有物化默认值"这件事变成登记表里一份**必须维护的清单**。
    """
    for d in divergences:
        if d.kind != "serialization":
            continue
        if d.ref.strip() != def_name and def_name not in _ref_tokens(d.ref):
            continue
        if prop in _field_tokens(d.field):
            return d
    return None


def _referenced_by(node: Any, name: str) -> bool:
    """稿侧某个 def 里是否**在形状位**上 `$ref` 指向 name。

    只走形状位（def 根本身、`properties` 的值、`items`、`additionalProperties`、
    `oneOf/anyOf/allOf` 的分支、`$ref` 的兄弟位）。第六轮验证 G3 的打法是往
    `x-fake` 这种**注释位**塞一条 `{"$ref": "#/definitions/IdempotencyKey"}`：
    `_canon`/`_resolve` 从不比较注释位，所以那条引用没有任何约束落点，
    却把"别名已内联"讲成了事实——见证测试从此不再被触发。
    """
    if isinstance(node, list):
        return any(_referenced_by(x, name) for x in node)
    if not isinstance(node, dict):
        return False
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.rsplit("/", 1)[-1] == name:
        return True
    for sub in (node.get("properties") or {}).values():
        if _referenced_by(sub, name):
            return True
    for key in ("items", "additionalProperties"):
        if _referenced_by(node.get(key), name):
            return True
    for key in ("oneOf", "anyOf", "allOf"):
        if _referenced_by(node.get(key), name):
            return True
    return False



def _ref_tokens(ref: str) -> set[str]:
    return {x.strip() for x in ref.replace("（", " ").replace("）", " ").replace("/", " ").split() if x.strip()}


def _field_tokens(field: str) -> set[str]:
    return {x.strip() for x in field.replace(",", " ").split() if x.strip()}


def _explains(entry: Divergence, def_name: str, path: str, fa: Any = MISSING, fb: Any = MISSING) -> bool:
    """这条登记能否解释这个位置的差异。**七道闸，缺一道就退化成橡皮章**：

    1. `path == ""`（整个 def 在产物里缺席）只接受 **structural 且 ref 点名叫到该 def**；
    2. `field == "*"` 在任何非空 path 上一律不解释（第五轮：一条 `*` 吞掉整 def 五类漂移）；
    3. `field` 里**不许出现 def 名**，也不许出现裸事实名（`required`/`types`/`default`…）——
       这两种写法都是"整类放行"：第六轮验证 D4 用 `field="PushRetryState"` 吞掉五处真漂移，
       D5 用 `field="exp, required"` 把"删掉必填 sub"解释成"exp 变必填"；
    4. `kind` 必须落在该**事实类**允许的档位里（`FACT_ALLOWED_KINDS`）——
       第六轮验证 D8 就是 `kind="documentation"` 解释了"类型改了"，因为 kind 过去完全不参与判定；
    5. **方向**必须与登记说的一致（`_direction_ok`）：说收紧就得真的更严，
       `required` 只允许"产物比稿多必填、且增量全在被点名字段里"；
    6. 产物**丢掉**稿里已有的东西（`fb is MISSING`）除 structural 外一律不放行，
       而 structural 也只许在"完整路径点名"时解释新增（`fa is MISSING`）。

    窄的一档仍然保留：登记可以把 `field` 写成完整叶子路径
    （`properties.responseData.types`），那是"只解释这一个位置这一件事"。
    """
    tokens = _ref_tokens(entry.ref)
    if path == "":
        return entry.kind == "structural" and def_name in tokens
    if entry.field.strip() == "*":
        return False
    fields = _field_tokens(entry.field)
    if def_name in fields:
        return False
    if entry.ref.strip() != def_name and def_name not in tokens:
        return False
    leaf = path.rsplit(".", 1)[-1].split(":", 1)[0] if path else ""
    exact = path in fields
    if fields & _BARE_FACT_KEYS and not exact:
        return False  # 裸事实名只接受"完整路径点名"这一档：叶子匹配等于整类事实放行
    if fb is MISSING:
        return False  # 产物丢掉稿里已有的东西：没有任何「等价写法」能替一次删除说话
    if fa is MISSING and not exact:
        return False  # 产物凭空多出事实：必须有一条把该完整路径点名的登记接住
    if leaf == "required":
        licensed = fields - _BARE_FACT_KEYS
        return entry.kind == "tightening" and _direction_ok("required", fa, fb, entry, licensed)
    if entry.kind not in FACT_ALLOWED_KINDS.get(leaf, frozenset({"structural"})):
        return False
    if not (exact or leaf in fields):
        return False
    return _direction_ok(leaf, fa, fb, entry, fields)


def compare_defs(domain: str = "collection") -> tuple[list[str], set[str]]:
    """按域比对。返回 (未解释的差异, 实际用到的归一 rule)。"""
    """逐 def 比对，返回 (未解释的差异, 实际用到的归一规则)。

    差异一律以 `def名:` 开头 ⇒ 参数化的"每 def 一条测试"才分得清是谁的责任。
    第一版属性级路径是 `WorkListRow.properties.title.maxLength`，而过滤器找 `WorkListRow:`，
    于是 9 条参数化测试全绿、只有汇总那条红——"每 def 可定位"是假的（第三轮验证抓到）。
    """
    _USED_RULES.clear()
    _USED_EXPLAINERS.clear()
    frozen_path, generated_path, divergences = DOMAINS[domain]
    frozen = load_cached(frozen_path)
    generated = load_cached(generated_path)
    fdefs, gdefs = _defs_of(frozen), _defs_of(generated)
    excluded, invalid_marks = _not_a_shape_names(frozen)
    if "definitions" in frozen:
        _note_rule("definitions-vs-refs-dialect")  # 只有稿真用了 draft-07 方言才记账

    problems: list[str] = []
    for name, node in fdefs.items():
        if name in excluded:
            continue  # 稿声明"这不是形状" ⇒ 不按 schema 要求它可理解，但由 narrow 测试反向核验
        _walk(node, f"{domain}.稿.{name}", fdefs, problems, frozenset({name}))
    for name, node in gdefs.items():
        _walk(node, f"{domain}.生成.{name}", gdefs, problems, frozenset({name}))
    if problems:
        return problems, set(_USED_RULES)

    # 根层：第六轮验证 G6 点名"只比 `$defs`、整篇文档根没比过"——
    # 于是生成物根 `type: object→string`、稿根删 `type`、稿根加 `additionalProperties:false`
    # 三种改动全部读绿，而 `$id` 两边本来就长得不一样却无人记账（实测：collection 稿已被
    # 会话说成 `bothot://contracts/collection/v1`，identity/events 稿仍是
    # `https://bothot/contracts/<域>.schema.json`，产物一律 `bothot://contracts/<域>/v1`）。
    # 现在根层的**校验事实**逐键比：每个不一致都必须由一条 `ref` 含"文档根"、
    # 且 `field` 点名该键的登记解释；溯源键仍按 generated-provenance-keys 走。
    provenance = {"x-generated-by", "x-source-module"}
    containers = {"$defs", "definitions"}  # 方言差异由 definitions-vs-refs-dialect 那条登记负责
    extra_root = sorted(set(generated) - set(frozen) - provenance - containers)
    diffs_root = [f"*: 生成物根层多出键 {extra_root}"] if extra_root else []
    if set(generated) & provenance:
        if any(d.rule == "generated-provenance-keys" for d in divergences):
            # 这是"某条登记解释了一处差异"，不是归一 ⇒ 记进 explainers，
            # 否则会跑进 `_NORMALIZATION_TO_KIND` 查表并 KeyError（第一版就撞在这）。
            _note_explainer("generated-provenance-keys")
        else:
            diffs_root.append("*: 生成物带溯源键，但登记表里没有 generated-provenance-keys 条目")
    for key in _ROOT_VALIDATING_KEYS:
        fa, fb = frozen.get(key, MISSING), generated.get(key, MISSING)
        if fa == fb:
            continue
        hit = _explains_root(divergences, key, fa, fb)
        if hit is None:
            diffs_root.append(
                f"*: 根层 {key} 稿={fa} 生成={fb}"
                "（没有「文档根 + 点名该键 + 方向合法」的登记；两侧都声明而值不同 ⇒ 需 conflict 类并引台账）"
            )
            continue
        _note_explainer(hit.rule)
    diffs_root.extend(_stale_root_entries(divergences, frozen, generated))

    diffs: list[str] = list(invalid_marks)
    for name in sorted(set(fdefs) | set(gdefs)):
        if name in excluded:
            hit = next((d for d in divergences if d.kind == "structural" and _explains(d, name, "")), None)
            if hit is None:
                diffs.append(f"{name}: 稿声明它不在唯一源里，但登记表没有 structural 条目点名叫它")
            elif name in gdefs:
                diffs.append(f"{name}: 稿声明它不是形状，生成物里却有这个 def（标记已过期，二选一）")
            else:
                _note_rule(hit.rule if hit.rule in _NORMALIZATION_TO_KIND else "not-a-shape")
            continue
        if name not in gdefs:
            hit = next((d for d in divergences if d.kind == "structural" and _explains(d, name, "")), None)
            if hit is None:
                diffs.append(f"{name}: 生成物缺这个 def（没有任何 structural 登记点名它）")
                continue
            # 第六轮验证 G1/G2：光有一条 structural 登记就能让一个 def 无声消失。
            # 现在"登记 + 可核验的去处"两件事都必须成立：
            # 要么它**真的**被某个已收编 def 在形状位 `$ref` 走了（约束在使用处现形，由逐 def 比对验），
            # 要么它在 `ALIAS_WITNESSES` 里点名了一个可执行见证测试（约束只在源模块与测试里）。
            inlined = any(_referenced_by(fdefs[k], name) for k in set(fdefs) & set(gdefs))
            witnessed = name in ALIAS_WITNESSES.get(domain, {})
            if not (inlined or witnessed):
                diffs.append(
                    f"{name}: 有 structural 登记，但它既没被任何已收编 def 在形状位引用、"
                    "也没在 ALIAS_WITNESSES 里点名见证测试 ⇒ 缺席无据（登记不能凭空让约束退场）"
                )
                continue
            _note_rule(hit.rule if hit.rule in _NORMALIZATION_TO_KIND else "alias-inlining")
            continue
        if name not in fdefs:
            diffs.append(f"{name}: 生成物多出一个 def（稿里没有 ⇒ 谁加的？）")
            continue
        a = _canon(_resolve(fdefs[name], fdefs))
        b = _canon(_resolve(gdefs[name], gdefs))
        for path in _description_losses(fdefs[name], gdefs[name], name):
            diffs.append(f"{path} 稿有说明、生成物没有（唯一源把话弄丢了）")
        for path in _extra_x_keys(fdefs[name], gdefs[name], name):
            diffs.append(f"{path} 生成物私带稿里没有的注释键")
        if a != b:
            for path, fa, fb in _flat_diff(a, b, name):
                tail = path[len(name) + 1 :] if path.startswith(f"{name}.") else path
                if tail == "default" or tail.endswith(".default"):
                    prop = tail.rsplit(".", 2)[-2] if "." in tail else tail
                    dhit = _default_explainer(divergences, name, prop)
                    if fa is MISSING and fb is not MISSING and dhit is not None and _is_empty_value(fb):
                        _note_explainer(dhit.rule)
                        continue
                    diffs.append(
                        f"{name}: {tail} 稿={fa} 生成={fb}（default 只放行「稿没写、模型物化出一个**空值**、"
                        "且该属性被 serialization 登记点名」这一个方向；把默认值改成非空值不是「物化」，"
                        "是改契约——第六轮验证 G7）"
                    )
                    continue
                hit = next((d for d in divergences if _explains(d, name, tail, fa, fb)), None)
                if hit is not None:
                    _note_explainer(hit.rule)
                    continue
                diffs.append(f"{name}: {tail} 稿={fa} 生成={fb}")
    diffs.extend(diffs_root)
    return diffs, set(_USED_RULES)


def _description_losses(draft_node: Any, gen_node: Any, path: str) -> list[str]:
    """稿里某处有 description、生成物没有 ⇒ 报。

    登记表 `strip-description` 的 reason 承诺过"只要求稿里有 ⇒ 生成物也得有"，
    第四轮验证证明那句当时是**空头承诺**（删掉稿侧 description 读出 0 条差异）。
    """
    out: list[str] = []
    if isinstance(draft_node, dict) and isinstance(gen_node, dict):
        if draft_node.get("description") and not gen_node.get("description"):
            out.append(path)
        dprops, gprops = draft_node.get("properties") or {}, gen_node.get("properties") or {}
        for prop in sorted(set(dprops) & set(gprops)):
            out.extend(_description_losses(dprops[prop], gprops[prop], f"{path}.{prop}"))
    return out


def _extra_x_keys(draft_node: Any, gen_node: Any, path: str) -> list[str]:
    """生成物**多出来**的 x-* 注释键：产物不该携带稿里没有的契约语义。"""
    out: list[str] = []
    if isinstance(draft_node, dict) and isinstance(gen_node, dict):
        extra = sorted(k for k in gen_node if k.startswith("x-") and k not in draft_node)
        out.extend(f"{path}.{k}" for k in extra)
        dprops, gprops = draft_node.get("properties") or {}, gen_node.get("properties") or {}
        for prop in sorted(set(gprops) - set(dprops)):
            out.append(f"{path}.{prop}（稿里没有这个属性）")
        for prop in sorted(set(dprops) & set(gprops)):
            out.extend(_extra_x_keys(dprops[prop], gprops[prop], f"{path}.{prop}"))
    return out


def _flat_diff(a: Any, b: Any, path: str) -> list[tuple[str, Any, Any]]:
    """叶子级差异。缺键用 `MISSING` 哨兵而**不是 None**：
    `"default": null` 是合法的 JSON Schema，用 None 当"没有这个键"的记号会让
    「稿里没写 default、模型物化出一个 null 默认值」读起来像"两侧都是 None"，
    于是方向判据（只放行"稿没写 ⇒ 模型物化"）失效，比对器把一批真差异报成硬差异。
    """
    out: list[tuple[str, Any, Any]] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a:
                out.append((f"{path}.{key}", MISSING, b[key]))
            elif key not in b:
                out.append((f"{path}.{key}", a[key], MISSING))
            else:
                out.extend(_flat_diff(a[key], b[key], f"{path}.{key}"))
    elif a != b:
        out.append((path, a, b))
    return out


# ── 1. 结构与比对（每个域都跑一遍）─────────────────────────────────────────────


def _all_domain_def_pairs() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for domain, (frozen_path, _gen, _div) in DOMAINS.items():
        pairs.extend((domain, name) for name in sorted(_defs_of(load_cached(frozen_path))))
    return pairs


def test_every_declared_contract_file_exists() -> None:
    """域表里登记的每个文件都必须在位——缺文件要红，不能靠"那个域还没做完"混过去。"""
    missing = []
    for domain, (frozen_path, generated_path, _div) in DOMAINS.items():
        if not frozen_path.exists():
            missing.append(f"{domain}.稿 {frozen_path.name}")
        if not generated_path.exists():
            missing.append(f"{domain}.生成物 {generated_path.name}（跑 scripts/gen_contracts.py）")
    assert not missing, "缺失：" + ", ".join(missing)


@pytest.mark.parametrize(
    "domain,side,path",
    [
        (domain, side, path)
        for domain, (frozen_path, generated_path, _div) in DOMAINS.items()
        for side, path in (("稿", frozen_path), ("生成物", generated_path))
    ],
    ids=lambda v: str(v.name if isinstance(v, Path) else v),
)
def test_neither_side_uses_a_keyword_the_comparator_does_not_implement(domain: str, side: str, path: Path) -> None:
    """两侧都查未知关键词：漏一侧 = 那一侧可以随便加约束而门禁不响。"""
    doc = load_cached(path)
    defs = _defs_of(doc)
    excluded = _not_a_shape_names(doc)[0] if side == "稿" else set()
    problems: list[str] = []
    for name, node in defs.items():
        if name in excluded:
            continue
        _walk(node, f"{domain}.{side}.{name}", defs, problems, frozenset({name}))
    assert not problems, "；".join(problems)


@pytest.mark.parametrize("domain,def_name", _all_domain_def_pairs(), ids=lambda v: str(v))
def test_each_draft_def_is_explained_or_equal(domain: str, def_name: str) -> None:
    diffs, _used = compare_defs(domain)
    mine = [d for d in diffs if d.split(":", 1)[0] == def_name]
    assert not mine, f"{domain}/{def_name} 与冻结稿不等且无登记：\n  " + "\n  ".join(mine)


def test_every_domain_has_no_unexplained_divergence() -> None:
    """整仓库层面的一次总检查：任一域有未解释差异都算失败，并点名是哪个域。"""
    report = {domain: compare_defs(domain)[0] for domain in DOMAINS}
    bad = {k: v for k, v in report.items() if v}
    assert not bad, "\n".join(f"[{k}]\n  " + "\n  ".join(v) for k, v in bad.items())


# ── 2. 登记表与归一化的双向核对 ───────────────────────────────────────────────


def test_normalizations_used_are_all_backed_by_registry() -> None:
    """正向：比对器实际用到的每条归一，都必须有对应 kind 的登记。"""
    for domain in DOMAINS:
        _diffs, used = compare_defs(domain)
        kinds = {d.kind for d in DOMAINS[domain][2]}
        for rule in used:
            need = _NORMALIZATION_TO_KIND[rule]
            assert need in kinds, f"{domain}: 归一 {rule} 用到，但登记表里没有 {need} 类支撑"
        assert used, f"{domain}: 一个归一都没用到 ⇒ 要么域太薄，要么归一表是摆设"


# rule → 替它兑现承诺的可执行断言。放模块级是为了让"漏挂消费者"在 import 期就暴露成 KeyError。
RULE_CONSUMERS: dict[str, str] = {
    "pattern-equivalence": "test_article_key_pattern_text_is_derivable_from_draft",
    "bounds-redundant": "test_article_key_bounds_are_redundant",
    "x-not-by-witness": "test_bare_s_is_rejected_by_witness",
    "timezone-required:publish_time": "test_publish_time_requires_timezone_aware_value",
    "timezone-required:at": "test_collection_event_at_requires_timezone",
    "timezone-required:lastSuccessAt": "test_last_success_at_requires_timezone",
    "dump-materializes-defaults": "test_optional_defaults_materialize_on_dump",
    "extra-dropped": "test_unknown_fields_dropped_except_work_list_row",
    "exp-required": "test_session_claims_requires_exp",
    "identity-dump-defaults": "test_identity_defaults_materialize_on_dump",
    "identity-extra-forbid": "test_session_claims_rejects_unknown_claim",
    "role-rank-anchor": "test_role_values_match_role_rank",
    "identity-x-annotations": "test_identity_annotations_have_owners",
    "generated-provenance-keys": "test_artifact_provenance_keys_are_declared",
    "event-name-set-anchor": "test_event_name_set_equals_valid_event_types",
    "push-retry-annotations": "test_retry_policy_constants_match_frozen_draft",
    "response-data-type-conflict": "test_push_retry_state_tracks_runtime_push_result",
    "events-dump-materializes-defaults": "test_push_retry_default_materializes_on_dump",
    "root-is-a-container": "test_document_root_divergences_are_named",
    "root-identifier-conflict": "test_conflict_entries_cite_a_live_decision_id",
}

# 稿里有、生成物里**没有**、又没被任何已收编 def 引用的约束型条目 ⇒ 必须点名一个见证测试。
# 这类条目过去只靠一句"别名会被内联到使用处"过关，而 identity 的 `UserId` 根本没有使用处
# （第五轮验证抓到）：约束在产物里彻底不存在，登记表的解释却是假的。
# 已登记在册的「随机 uuid 幂等键」违规点（唯一一条，带行号锚）。
# 修掉它就把它从这份清单里删除；往里加新项等于承认新增一处违反 events 稿的 x-rule。
KNOWN_UUID_IDEMPOTENCY_SITES = {"apps/api/app/api/v1/hot.py:192"}

ALIAS_WITNESSES: dict[str, dict[str, str]] = {
    "identity": {"UserId": "test_user_id_pattern_witnesses"},
    "events": {"IdempotencyKey": "test_idempotency_key_alias_witness"},
}


def test_registry_rules_are_all_consumed() -> None:
    """反向：每条登记的 rule 都必须真有人消费——**被比对器当归一用到**，或有断言替它兑现。

    没有这条，登记表就会长"只有承诺没有实现者"的条目（第三轮验证抓到过三条）。

    第五轮验证把"解释过一次差异"从消费里剔了出去：`compare_defs` 命中某条登记时会
    `_note_explainer(hit.rule)`，于是**一条专门用来遮差异的登记会自己给自己发消费者**
    （验证者演示：塞 `ref="WorkListRow", field="*", kind="structural"` 那条，五类真漂移
    全被吞，同时它把本测试也刷绿）。归一（`_USED_RULES`）是比对器代码里真在跑的等价处理，
    算消费；解释（`_USED_EXPLAINERS`）只是"某处差异被放行了"，不算——放行条目必须另有人钉。
    """
    module = sys.modules[__name__]
    for domain, (_f, _g, divergences) in DOMAINS.items():
        _diffs, used_norms = compare_defs(domain)
        unclaimed: list[str] = []
        for d in divergences:
            fn_name = RULE_CONSUMERS.get(d.rule)
            if d.rule not in used_norms and fn_name is None:
                unclaimed.append(
                    f"{d.rule}（{d.ref} / {d.field}）既没被比对器当归一用到，也没登记消费者"
                    f"（它解释过 {len(_USED_EXPLAINERS & {d.rule})} 处差异，但那不算兑现承诺）"
                )
                continue
            if fn_name is None:
                continue
            fn = getattr(module, fn_name, None)
            if fn is None:
                unclaimed.append(f"{d.rule} 声称由 {fn_name} 兑现，但该函数不存在")
                continue
            # 关键改动：**被比对器用到不等于它的行为承诺成立**。第一版 `continue` 掉了
            # 这种条目的消费者调用，等于"归一被用了就不用再验它说的事"（第四轮验证点名）。
            fn()
        assert not unclaimed, f"{domain} 登记表里有 dead claim：\n  " + "\n  ".join(unclaimed)


def test_registry_kinds_are_the_documented_five() -> None:
    """`kind` 从来没人校验过（第五轮验证点名）：写错一种 = 凭空多第六种放行能力。

    `_explains` 只认 structural、`_default_explainer` 只认 serialization、
    `_NORMALIZATION_TO_KIND` 只查这五种里的若干种——但登记表里出现 `kind="magic"`
    不会有任何人响，那条条目就只是一段自由文本。
    """
    for domain, (_f, _g, divergences) in DOMAINS.items():
        bad = [f"{d.rule}: kind={d.kind!r}" for d in divergences if d.kind not in DIVERGENCE_KINDS]
        assert not bad, f"{domain} 登记表里有非法 kind：\n  " + "\n  ".join(bad)


def test_absent_draft_defs_are_accounted_for() -> None:
    """稿里有、生成物里没有的 def 只有三种正当去向，且**逐条验**，不是一句"别名内联"包打天下。

    第五轮验证打脸的那条就在 (c)：identity 的 `UserId` 带着 UUID pattern，却没有任何模型引用它
    ⇒ 约束在产物里彻底不存在，而登记表写的是"Sub/UserId 的约束被内联进使用处"——那是假的。
    现在 (c) 必须点名一个可执行的见证测试，本条会真的调用它。
    """
    module = sys.modules[__name__]
    for domain, (frozen_path, generated_path, _div) in DOMAINS.items():
        fdefs, gdefs = _defs_of(load_cached(frozen_path)), _defs_of(load_cached(generated_path))
        absorbed = set(fdefs) & set(gdefs)
        witnesses = ALIAS_WITNESSES.get(domain, {})
        unaccounted: list[str] = []
        for name in sorted(set(fdefs) - set(gdefs)):
            if name in _not_a_shape_names(load_cached(frozen_path))[0]:
                continue
            if any(_referenced_by(fdefs[k], name) for k in absorbed):
                continue
            fn_name = witnesses.get(name)
            if fn_name is None:
                unaccounted.append(f"{name}: 既不是「稿声明非形状」、也没有已收编 def 引用它，还没点名见证测试")
                continue
            fn = getattr(module, fn_name, None)
            if fn is None:
                unaccounted.append(f"{name}: 见证测试 {fn_name} 不存在")
                continue
            fn()
        assert not unaccounted, f"{domain} 有消失的 def 无人负责：\n  " + "\n  ".join(unaccounted)


def test_not_a_shape_claims_are_narrow() -> None:
    """"它不是形状"这句话必须**又窄又有人接手**，否则就是关掉一整块门禁的许可证。

    三条都是硬的：①被点名的 def 确实不含形状关键词（含就不许退出）；
    ②它确实不在生成物里（在 ⇒ 标记过期）；③有 structural 登记点名叫它（注释也要有责任人）。
    """
    for domain, (frozen_path, generated_path, divergences) in DOMAINS.items():
        frozen = load_cached(frozen_path)
        fdefs, gdefs = _defs_of(frozen), _defs_of(load_cached(generated_path))
        ok, bad = _not_a_shape_names(frozen)
        assert not bad, f"{domain}: 有非法的非形状声明：\n  " + "\n  ".join(bad)
        for name in sorted(ok):
            body = fdefs[name]
            shape_keys = sorted(_constraint_bearing(body))
            assert not shape_keys, f"{domain}/{name}: 带真约束 {shape_keys} ⇒ 它是形状，不许声明「不是形状」"
            assert name not in gdefs, f"{domain}/{name}: 稿说不是形状，生成物却有这个 def"
            hit = next((d for d in divergences if d.kind == "structural" and _explains(d, name, "")), None)
            assert hit is not None, f"{domain}/{name}: 没有 structural 登记点名接手注释"


def test_every_x_keyword_on_an_absorbed_def_is_claimed() -> None:
    """稿里挂在**已收编 def** 上的 `x-*` 注释必须在登记表里有归宿。

    范围刻意收窄到"已收编的 def"：没进生成物的 def（别名、纯注释对象）由 `compare_defs`
    的缺-def 判定负责，在那里重复要求只会让两处门禁互相顶包。
    """
    for domain, (frozen_path, generated_path, divergences) in DOMAINS.items():
        fdefs, gdefs = _defs_of(load_cached(frozen_path)), _defs_of(load_cached(generated_path))
        claimed = {x.strip() for d in divergences for x in d.field.replace(",", " ").split()}
        claimed |= {d.rule for d in divergences}
        for name in set(fdefs) & set(gdefs):
            for key in [k for k in fdefs[name] if k.startswith("x-")]:
                assert key in claimed, f"{domain}/{name}: 注释键 {key} 在登记表里无人认领"
            for prop, sub in (fdefs[name].get("properties") or {}).items():
                if not isinstance(sub, dict):
                    continue
                for key in [k for k in sub if k.startswith("x-")]:
                    assert key in claimed, f"{domain}/{name}.{prop}: 注释键 {key} 无人认领"


# ── 3. 比对器自己会不会被绕过（把外部验证者的击败方式钉成测试）─────────────────


def _compare_with_mutated_draft(mutate: Any, domain: str = "collection") -> list[str]:
    """在内存里替换**稿**跑比对。

    方向很重要：漂移可以是"稿改了、产物没跟上"，也可以反过来。只测生成物侧的注入器
    就永远测不到"稿侧掉锚"这一类——第四轮验证的 A1/A2 正是从稿侧穿过来的。
    """
    frozen_path = DOMAINS[domain][0]
    original = load_cached(frozen_path)
    mutated: dict[str, Any] = copy.deepcopy(original)
    mutate(mutated)
    _LOADED[frozen_path] = mutated
    try:
        return compare_defs(domain)[0]
    finally:
        _LOADED[frozen_path] = original
        compare_defs(domain)


def _compare_with_mutated_generated(mutate: Any, domain: str = "collection") -> list[str]:
    """在内存里替换生成物跑比对，**不写任何仓库文件**。"""
    generated_path = DOMAINS[domain][1]
    original = load_cached(generated_path)
    mutated: dict[str, Any] = copy.deepcopy(original)
    mutate(mutated)
    _LOADED[generated_path] = mutated
    try:
        return compare_defs(domain)[0]
    finally:
        _LOADED[generated_path] = original
        compare_defs(domain)  # 复位 _USED_RULES，避免污染后面的核对


@pytest.mark.parametrize(
    "label,mutate",
    [
        (
            "放宽量词：hex 32 → 31,32",
            lambda g: g["$defs"]["ArticleManifest"]["properties"]["article_key"].__setitem__(
                "pattern", ARTICLE_KEY_PATTERN.replace("[0-9a-f]{32}", "[0-9a-f]{31,32}")
            ),
        ),
        (
            "改字符类：s: 分支去掉连字符",
            lambda g: g["$defs"]["ArticleManifest"]["properties"]["article_key"].__setitem__(
                "pattern", ARTICLE_KEY_PATTERN.replace("[A-Za-z0-9_-]{8,64}", "[A-Za-z0-9_]{8,64}")
            ),
        ),
        (
            "放宽 mid 位数上界 12 → 13",
            lambda g: g["$defs"]["ArticleManifest"]["properties"]["article_key"].__setitem__(
                "pattern", ARTICLE_KEY_PATTERN.replace("[0-9]{1,12}", "[0-9]{1,13}")
            ),
        ),
        (
            "给生成物塞一个稿里没有的关键词 minItems",
            lambda g: g["$defs"]["WorkListPage"]["properties"]["rows"].__setitem__("minItems", 1),
        ),
        (
            "给生成物塞一个稿里没有的关键词 const",
            lambda g: g["$defs"]["ManifestStatus"].__setitem__("const", "DISCOVERED"),
        ),
        (
            "把可空字段改成非空（删 null 分支）",
            lambda g: g["$defs"]["WorkListPage"]["properties"]["next_cursor"].__setitem__(
                "anyOf", [{"type": "string"}]
            ),
        ),
        (
            "改类型 integer → number",
            lambda g: g["$defs"]["ManifestSyncReport"]["properties"]["pages"].__setitem__("type", "number"),
        ),
        (
            "翻掉 additionalProperties",
            lambda g: g["$defs"]["WorkListRow"].__setitem__("additionalProperties", False),
        ),
        (
            "加一个稿里没有的属性",
            lambda g: g["$defs"]["WorkListRow"]["properties"].__setitem__("surprise", {"type": "string"}),
        ),
        (
            "枚举换序",
            lambda g: g["$defs"]["ChannelName"].__setitem__("enum", list(reversed(g["$defs"]["ChannelName"]["enum"]))),
        ),
        (
            "删一个必填",
            lambda g: g["$defs"]["WorkListPage"].__setitem__("required", ["rows", "page_size"]),
        ),
        (
            "生成物整条 pattern 丢掉结尾锚",
            lambda g: g["$defs"]["ArticleManifest"]["properties"]["article_key"].__setitem__(
                "pattern", ARTICLE_KEY_PATTERN[:-1]
            ),
        ),
        (
            "塞一个非 pattern 的 oneOf 分支（const）",
            lambda g: g["$defs"]["ManifestSyncReport"]["properties"]["pages"].__setitem__(
                "oneOf", [{"const": 0}]
            ),
        ),
        (
            "生成物私带一个稿里没有的 x-* 键",
            lambda g: g["$defs"]["WorkListRow"].__setitem__("x-sneaky", "1"),
        ),
        (
            "生成物根层多出一个键",
            lambda g: g.__setitem__("x-root-sneaky", "1"),
        ),
    ],
)
def test_comparator_bites_on_each_drift_class(label: str, mutate: Any) -> None:
    """每一类真实漂移一条参数化反证，**类数不写在文档字符串里**。

    这组直接来自第三轮独立验证——它用这些方式击败过第一版比对器。
    钉成测试的意思是：**下一次谁把比对器改坏，CI 会替那位验证者再问一遍。**

    第一版这里写着"十一类"，加到十五条后没人回头改数字（第五轮验证抓到）：
    写死的读数会在下一次改动时变成假话，而假话比空话更有害。条数由 pytest 自己报。
    """
    diffs = _compare_with_mutated_generated(mutate)
    assert diffs, f"比对器被绕过：注入「{label}」仍然 0 条差异"


def test_comparator_does_not_false_positive() -> None:
    """对照：什么都没改 ⇒ 每个域都必须 0 条（否则上面那组"红"没有意义）。"""
    assert {d: compare_defs(d)[0] for d in DOMAINS} == {d: [] for d in DOMAINS}


def test_comparator_bites_on_draft_side_anchor_loss() -> None:
    """稿侧 `s:` 分支丢掉结尾 `$` ⇒ 必须报。

    `canonical_alternation()` 去锚再补锚，对锚**天生不敏感**（第四轮验证点名的绕过面），
    所以锚保真由 `_pattern_fact` 里的 anchored 布尔承担——这条就是钉它的。
    """

    def mutate(doc: dict[str, Any]) -> None:
        branches = doc["$defs"]["ArticleKey"]["oneOf"]
        for b in branches:
            if b["pattern"].startswith("^s:"):
                b["pattern"] = b["pattern"][:-1]

    diffs = _compare_with_mutated_draft(mutate)
    assert any("article_key" in d or "ArticleKey" in d for d in diffs), f"稿侧掉锚没被抓：{diffs}"


def test_comparator_bites_on_patternless_oneof_branch() -> None:
    """稿里给某字段加一个**非 pattern** 的 oneOf 分支（const）⇒ 必须成为差异。

    第一版 `_canon` 只折 pattern 分支，其余分支静默丢弃——注入 `oneOf:[{"const":0}]`
    读出来是 0 条差异，等于"随便加约束都不响"。
    """

    def mutate(doc: dict[str, Any]) -> None:
        doc["$defs"]["ManifestStatus"]["oneOf"] = [{"const": "DISCOVERED"}]

    assert _compare_with_mutated_draft(mutate), "非 pattern 的 oneOf 分支被静默吞掉"


def test_comparator_bites_when_generated_loses_a_description() -> None:
    """生成物侧丢了稿里有的说明 ⇒ 必须报。

    方向是登记 `strip-description` 写死的那个方向（「稿里有 ⇒ 生成物也得有」）。
    反方向——稿里删文字而模型 docstring 还在——**不该**红：比较文本就把已登记的
    "文本不参与校验"又推翻了。我第一版把测试写成了删稿侧 description，那是我自己
    给门禁加了个登记里没写的要求，写反了。
    """

    def mutate(doc: dict[str, Any]) -> None:
        doc["$defs"]["ChannelName"].pop("description", None)

    assert _compare_with_mutated_generated(mutate), "生成物丢说明读出 0 条差异"


# 第五轮独立验证（读 `git show 983a356`）拿这三类击败过比对器，逐类钉成反证。
@pytest.mark.parametrize(
    "label,side,mutate",
    [
        (
            "default：生成物把空串默认值改成别的字符串",
            "生成物",
            lambda g: g["$defs"]["ManifestSyncReport"]["properties"]["pages"].__setitem__("default", 7),
        ),
        (
            "default：稿声明一个模型没有的默认值",
            "稿",
            lambda d: d["$defs"]["ManifestStatus"].__setitem__("default", "DISCOVERED"),
        ),
        (
            "default：稿把模型物化出来的默认值改掉（两侧都有但不同）",
            "稿",
            lambda d: d["$defs"]["WorkListRow"]["properties"]["digest"].__setitem__("default", "not-empty"),
        ),
        (
            "tuple items：两侧都写数组形式而第 0 位约束不同",
            "both",
            None,  # 需要同时改两侧，单独写不了 lambda ⇒ 见下面的具名函数
        ),
        (
            "多支 anyOf：两支都不是 pattern 包装",
            "both",
            None,  # 同上
        ),
        (
            "kind 写错 = 凭空第六种放行能力",
            "registry",
            None,  # 登记表不在 JSON 文件里，改由具名测试直接构造
        ),
    ],
    ids=lambda v: str(v),
)
def test_comparator_bites_on_fifth_round_blind_spots(label: str, side: str, mutate: Any) -> None:
    """三类"两侧都改 ⇒ 第一版读 0 条差异"的注入必须各自变红。

    `side="both"` 的两类无法用单侧注入器表达（第一版正是因为只测单侧才漏掉它们），
    所以这里走 `_compare_with_both_sides_mutated()`；`side="registry"` 那类
    是直接构造一条恶意登记喂给 `compare_defs`，验证 kind 值域那条测试真的在管。
    """
    if side == "生成物":
        assert _compare_with_mutated_generated(mutate), f"注入「{label}」仍然 0 条差异"
        return
    if side == "稿":
        assert _compare_with_mutated_draft(mutate), f"注入「{label}」仍然 0 条差异"
        return
    if side == "both":
        fn = _BOTH_SIDE_PROOFS[label]
        assert fn(), f"注入「{label}」仍然 0 条差异"
        return
    assert _malformed_kind_entry_is_rejected(), "kind 值域核对没咬住非法 kind"


def _mutate_tuple_items(doc_a: dict[str, Any], doc_b: dict[str, Any]) -> None:
    """稿侧 items 写成 tuple 形式 `[{"maxLength":5}]`、生成物侧 `[{"maxLength":9}]`。

    第一版 `_canon(node["items"])` 对一个 **list** 调用自己 ⇒ 走到
    `node if isinstance(node, dict) else {}` 折成空事实，两侧都空 = 没差异。
    """
    for doc, ml in ((doc_a, 5), (doc_b, 9)):
        doc["$defs"]["WorkListPage"]["properties"]["rows"]["items"] = [{"maxLength": ml}]


def _mutate_multi_anyof(doc_a: dict[str, Any], doc_b: dict[str, Any]) -> None:
    """两支及以上的 anyOf（都不是纯 pattern 包装）——第一版条件 `"anyOf" not in node` 整块丢弃。"""
    doc_a["$defs"]["ManifestSyncReport"]["properties"]["pages"]["anyOf"] = [{"const": 0}, {"const": 1}]
    doc_b["$defs"]["ManifestSyncReport"]["properties"]["pages"]["anyOf"] = [{"const": 0}, {"const": 2}]


_BOTH_SIDE_PROOFS: dict[str, Any] = {
    "tuple items：两侧都写数组形式而第 0 位约束不同": lambda: _compare_with_both_sides_mutated(_mutate_tuple_items),
    "多支 anyOf：两支都不是 pattern 包装": lambda: _compare_with_both_sides_mutated(_mutate_multi_anyof),
}


def _compare_with_both_sides_mutated(mutate: Any) -> list[str]:
    """同时改两侧再跑比对——单侧注入器**结构上**测不到"两侧都改但改得不一样"这一类。"""
    frozen_path, generated_path = DOMAINS["collection"][0], DOMAINS["collection"][1]
    f_original, g_original = load_cached(frozen_path), load_cached(generated_path)
    f_mut, g_mut = copy.deepcopy(f_original), copy.deepcopy(g_original)
    mutate(f_mut, g_mut)
    _LOADED[frozen_path], _LOADED[generated_path] = f_mut, g_mut
    try:
        return compare_defs("collection")[0]
    finally:
        _LOADED[frozen_path], _LOADED[generated_path] = f_original, g_original
        compare_defs("collection")


def _malformed_kind_entry_is_rejected() -> bool:
    """构造一条 `kind` 不在值域里的登记，`test_registry_kinds_are_the_documented_five` 必须红。"""
    from app.contracts.collection import CONTRACT_DIVERGENCES as CD

    poisoned = CD + (Divergence("WorkListRow", "*", "magic", "adv-swallower", "x", "y", "z"),)
    original = DOMAINS["collection"]
    try:
        DOMAINS["collection"] = (original[0], original[1], poisoned)
        module = sys.modules[__name__]
        try:
            module.test_registry_kinds_are_the_documented_five()
        except AssertionError:
            return True
        return False
    finally:
        DOMAINS["collection"] = original


def test_star_wildcard_entry_no_longer_buys_a_free_pass() -> None:
    """第五轮验证的杀手锏：`ref="WorkListRow"` + `field="*"` + `kind="structural"` 曾吞掉该 def 全部差异。

    现在 `field=="*"` 在非根路径上一律不解释（`_explains` 第二条）。这条测试直接注入那条
    恶意登记 + 五类真漂移，要求**每一类仍然报**；顺带验它没能把自己洗成"有消费者"。
    """
    from app.contracts.collection import CONTRACT_DIVERGENCES as CD

    swallower = Divergence("WorkListRow", "*", "structural", "adv-swallower", "x", "y", "z")
    original = DOMAINS["collection"]

    def drift(g: dict[str, Any]) -> None:
        row = g["$defs"]["WorkListRow"]
        row["additionalProperties"] = False
        row["required"] = ["url", "title"]
        row["properties"]["url"]["format"] = "email"
        row["properties"].pop("id", None)
        row["properties"]["publish_time"]["format"] = "date"

    try:
        DOMAINS["collection"] = (original[0], original[1], CD + (swallower,))
        diffs = _compare_with_mutated_generated(drift)
        assert diffs, "整片放行的登记仍然能把 WorkListRow 的差异全吞掉"
        # 这条登记本身没有 RULE_CONSUMERS 消费者 ⇒ 「解释过一次差异」不算兑现承诺
        unclaimed = [d.rule for d in CD + (swallower,) if d.rule not in _used_norms("collection")]
        assert "adv-swallower" in unclaimed, "恶意登记靠解释差异给自己发了消费者"
    finally:
        DOMAINS["collection"] = original
        compare_defs("collection")


def _used_norms(domain: str) -> set[str]:
    return compare_defs(domain)[1]


# ── 4. 键不变量（ADR-0011 §3；2/3 两条要 URL，留 STEP-02）──────────────────────

_ARTICLE_KEY_ADAPTER = TypeAdapter(ArticleKey)

KEY_ACCEPT = [
    "b:MzI4NjA5NTU4Mg:2650635316:1",
    "s:abcDEF12",
    "h:0123456789abcdef0123456789abcdef",
]
KEY_REJECT = [
    "s",  # 不变量 1：退化形状（P0-1 回归锚）
    "ssssssss",
    "b:a:b:c",
    "h:0123456789ABCDEF0123456789abcdef",  # 大写 hex 不进 h:
    "x:abcdefgh",  # 未知前缀
    "h:0123456789abcdef0123456789abcdef\n",  # 尾随换行不得绕过 $
    "",
]


@pytest.mark.parametrize("key", KEY_ACCEPT)
def test_article_key_accepts_the_three_prefix_shapes(key: str) -> None:
    assert _ARTICLE_KEY_ADAPTER.validate_python(key) == key


@pytest.mark.parametrize("key", KEY_REJECT)
def test_article_key_rejects_degenerate_and_foreign_shapes(key: str) -> None:
    with pytest.raises(ValidationError):
        _ARTICLE_KEY_ADAPTER.validate_python(key)


def test_bare_s_is_rejected_by_witness() -> None:
    """稿的 `x-not`（禁止单字符/纯 s）这条注释的实际责任人。"""
    with pytest.raises(ValidationError) as exc:
        _ARTICLE_KEY_ADAPTER.validate_python("s")
    assert exc.value.errors()[0]["type"] == "string_too_short"


def test_article_key_pattern_text_is_derivable_from_draft() -> None:
    """pattern 等价性的**第一层**证明：文本推导，不是语料抽样。"""
    draft_branches = [b["pattern"] for b in load_cached(FROZEN_PATH)["$defs"]["ArticleKey"]["oneOf"]]
    gen_pattern = load_cached(GENERATED_PATH)["$defs"]["ArticleManifest"]["properties"]["article_key"]["pattern"]
    assert canonical_alternation(draft_branches) == gen_pattern == ARTICLE_KEY_PATTERN


def test_article_key_bounds_are_redundant() -> None:
    """登记 `bounds-redundant` 的兑现：三支分支的极值都落在 minLength/maxLength 之内。"""
    node = load_cached(FROZEN_PATH)["$defs"]["ArticleKey"]
    assert (node["minLength"], node["maxLength"]) == (3, 128)
    per_branch = {
        "b": ("b:" + "A" * 8 + ":1:1", "b:" + "A" * 64 + ":" + "9" * 12 + ":" + "99"),
        "s": ("s:" + "a" * 8, "s:" + "a" * 64),
        "h": ("h:" + "0" * 32, "h:" + "f" * 32),
    }
    for lo, hi in per_branch.values():
        assert 3 <= len(lo) <= 128 and 3 <= len(hi) <= 128
    assert len("s:aaaaaaaa") == 10  # 最短可过串 ⇒ minLength=3 永不先生效
    assert len(per_branch["b"][1]) <= 82  # 最长分支 ⇒ maxLength=128 同理


# ── 5. 渠道 / 状态机 / 事件 ───────────────────────────────────────────────────


def test_channel_name_set_equals_registry_channels() -> None:
    """与实现比**集合**：dict 插入序是实现细节，不该被契约依赖（第二轮验证的口径纠正）。"""
    assert {c.value for c in ChannelName} == set(CHANNELS.keys())


def test_channel_name_order_matches_the_frozen_draft() -> None:
    assert [c.value for c in ChannelName] == load_cached(FROZEN_PATH)["$defs"]["ChannelName"]["enum"]


def test_manifest_status_values_match_draft() -> None:
    assert [s.value for s in ManifestStatus] == load_cached(FROZEN_PATH)["$defs"]["ManifestStatus"]["enum"]


def test_collection_event_enums_match_draft() -> None:
    gen = load_cached(GENERATED_PATH)["$defs"]["CollectionEvent"]["properties"]["event"]["enum"]
    draft = load_cached(FROZEN_PATH)["$defs"]["CollectionEvent"]["properties"]["event"]["enum"]
    assert gen == draft


# ── 6. WorkListRow / WorkListPage ─────────────────────────────────────────────


def test_work_list_row_required_fields_match_draft() -> None:
    draft = load_cached(FROZEN_PATH)["$defs"]["WorkListRow"]["required"]
    assert sorted(WorkListRow.model_json_schema()["required"]) == sorted(draft)


def test_work_list_row_passes_through_unknown_fields() -> None:
    row = WorkListRow.model_validate({"id": "1", "url": "https://x.test/a", "title": "t", "upstream_extra": 7})
    assert row.model_dump().get("upstream_extra") == 7


@pytest.mark.parametrize(
    "payload,expect_ok",
    [
        ({"id": "1", "url": "https://x.test/a", "title": "t"}, True),
        ({"url": "https://x.test/a", "title": "t"}, False),
        ({"id": "", "url": "https://x.test/a", "title": "t"}, False),
        ({"id": "1", "url": "http:/", "title": "t"}, False),
        ({"id": "1", "url": "https://x.test/a"}, False),
    ],
)
def test_work_list_row_accept_set(payload: dict[str, str], expect_ok: bool) -> None:
    if expect_ok:
        WorkListRow.model_validate(payload)
        return
    with pytest.raises(ValidationError):
        WorkListRow.model_validate(payload)


def test_work_list_page_next_cursor_is_required_nullable() -> None:
    """S1.2.1 第一轮验证抓到的那条：缺字段 ≠ 末页，必须显式 null。"""
    assert sorted(load_cached(FROZEN_PATH)["$defs"]["WorkListPage"]["required"]) == [
        "next_cursor",
        "page_size",
        "rows",
    ]
    with pytest.raises(ValidationError):
        WorkListPage.model_validate({"rows": [], "page_size": 1})
    assert WorkListPage.model_validate({"rows": [], "next_cursor": None, "page_size": 1}).next_cursor is None


# ── 7. 三条 tightening 与两条 dump/extra 行为（比对器看不见，只能在这里兑现）──


def test_publish_time_requires_timezone_aware_value() -> None:
    with pytest.raises(ValidationError):
        WorkListRow.model_validate({"id": "1", "url": "https://x.test/a", "title": "t", "publish_time": "2024-01-01"})
    row = WorkListRow.model_validate(
        {"id": "1", "url": "https://x.test/a", "title": "t", "publish_time": "2024-01-01T00:00:00+08:00"}
    )
    assert row.publish_time is not None and row.publish_time.utcoffset() is not None


def test_collection_event_at_requires_timezone() -> None:
    with pytest.raises(ValidationError):
        CollectionEvent.model_validate(
            {"event": "discovery.failed", "source_id": "s1", "channel": "rss", "at": "2024-01-01"}
        )
    ev = CollectionEvent.model_validate(
        {"event": "discovery.failed", "source_id": "s1", "channel": "rss", "at": "2024-01-01T00:00:00+08:00"}
    )
    assert ev.at.utcoffset() is not None


def test_last_success_at_requires_timezone() -> None:
    base = {
        "name": "rss",
        "description": "d",
        "implemented": True,
        "enabled": True,
        "available": True,
        "reason": "",
    }
    with pytest.raises(ValidationError):
        DiscoveryChannelView.model_validate({**base, "lastSuccessAt": "2024-01-01"})
    view = DiscoveryChannelView.model_validate({**base, "lastSuccessAt": "2024-01-01T00:00:00+08:00"})
    assert view.last_success_at is not None


def test_optional_defaults_materialize_on_dump() -> None:
    """兑现 `dump-materializes-defaults`：稿里没有 default，模型会物化出来。"""
    row = WorkListRow.model_validate({"id": "1", "url": "https://x.test/a", "title": "t"})
    assert set(row.model_dump()) == {"id", "url", "title", "publish_time", "digest", "author"}
    report = ManifestSyncReport.model_validate(
        {
            "channel": "rss",
            "pages": 0,
            "rows": 0,
            "new": 0,
            "updated": 0,
            "unchanged": 0,
            "skipped": 0,
            "id_fallback": 0,
        }
    )
    assert report.all_skipped_pages == 0  # 稿里这个字段没有 default
    ev = CollectionEvent.model_validate(
        {"event": "manifest.enqueued", "source_id": "s", "channel": "rss", "at": "2024-01-01T00:00:00+08:00"}
    )
    dumped = ev.model_dump()
    assert dumped["idempotency_key"] == "" and dumped["count"] == 0


def test_unknown_fields_dropped_except_work_list_row() -> None:
    """兑现 `extra-dropped`：不对称是**有意**的，所以必须有人钉着它。"""
    row = WorkListRow.model_validate({"id": "1", "url": "https://x.test/a", "title": "t", "zzz": 1})
    assert "zzz" in row.model_dump()
    report = ManifestSyncReport.model_validate(
        {
            "channel": "rss",
            "pages": 0,
            "rows": 0,
            "new": 0,
            "updated": 0,
            "unchanged": 0,
            "skipped": 0,
            "id_fallback": 0,
            "zzz": 1,
        }
    )
    assert "zzz" not in report.model_dump()


# ── 8. 错误码映射（S1.4.1 第四条锚）───────────────────────────────────────────


def test_error_code_names_match_frozen_errors_contract() -> None:
    table = load_cached(ERRORS_FROZEN_PATH)["x-table"]
    assert len(table) == len(ERROR_CODES)
    mismatched = [
        (e["code"], e["name"], ERROR_CODES.get(e["code"])) for e in table if ERROR_CODES.get(e["code"]) != e["name"]
    ]
    assert not mismatched, f"逐条对号失败：{mismatched}"


def test_error_code_enum_in_contract_covers_backend_registry() -> None:
    contract_codes = set(load_cached(ERRORS_FROZEN_PATH)["definitions"]["ErrorCode"]["enum"])
    contract_codes.discard(0)
    assert contract_codes == set(ERROR_CODES)




# ── 10. identity 域：替登记表的每条 rule 兑现承诺 ─────────────────────────────


def test_session_claims_requires_exp() -> None:
    """rule `exp-required`（tightening）的消费者：缺 exp 与 null 都要拒。"""
    with pytest.raises(ValidationError):
        identity_contract.SessionClaims.model_validate({"sub": "s-1"})
    with pytest.raises(ValidationError):
        identity_contract.SessionClaims.model_validate({"sub": "s-1", "exp": None})
    ok = identity_contract.SessionClaims.model_validate({"sub": "s-1", "exp": 1_800_000_000})
    assert ok.exp == 1_800_000_000


def test_identity_defaults_materialize_on_dump() -> None:
    """rule `identity-dump-defaults` 的消费者：iss/aud 在 dump 里物化成空串。"""
    dumped = identity_contract.SessionClaims.model_validate({"sub": "s-1", "exp": 1}).model_dump()
    assert dumped["iss"] == "" and dumped["aud"] == ""


def test_session_claims_rejects_unknown_claim() -> None:
    """rule `identity-extra-forbid` 的消费者：未知 claim 直接拒，而不是静默吞。"""
    with pytest.raises(ValidationError):
        identity_contract.SessionClaims.model_validate({"sub": "s-1", "exp": 1, "balance": 100})


def test_role_values_match_role_rank() -> None:
    """role 取值集与 `ROLE_RANK` 的键集相等——等级表在 services，契约只钉值集。

    两边不等就是"授权面与契约面分家"，这条是本域唯一源的真正落点。
    """
    assert {r.value for r in identity_contract.Role} == set(ROLE_RANK)


def test_user_id_pattern_witnesses() -> None:
    """兑现 `alias-inlining` 里那句"UserId"——它**没有**使用处，所以约束只能由本测试见证。

    直接 `TypeAdapter` 跑 UUID 形状：大写、少一段、多一段都必须拒。第五轮验证指出
    登记表原文写的是"Sub/UserId 的约束被内联进使用处"，那是把没发生的事写成已发生；
    现在文本已更正，本测试就是更正后唯一的落点（并由 `ALIAS_WITNESSES` 强制它存在）。
    """
    adapter: TypeAdapter[identity_contract.UserId] = TypeAdapter(identity_contract.UserId)
    assert adapter.validate_python("3f2504e0-4f89-11d4-993c-00cc940563e1")
    for bad in (
        "3F2504E0-4F89-11D4-993C-00CC940563E1",  # 大写不算 UUID 文本（稿里钉的是小写类）
        "3f2504e0-4f89-11d4-993c-00cc940563e",  # 少一位
        "3f2504e04f8911d4993c00cc940563e1",  # 没连字符
        "3f2504e0-4f89-11d4-993c-00cc940563e1x",  # 尾部多一字符（pattern 带锚 ⇒ 必须拒）
        "",
    ):
        with pytest.raises(ValidationError):
            adapter.validate_python(bad)
    draft = _defs_of(load_cached(DOMAINS["identity"][0]))["UserId"]
    assert draft["pattern"] == identity_contract.USER_ID_PATTERN


def test_artifact_provenance_keys_are_declared() -> None:
    """兑现 `generated-provenance-keys`：产物必须自证是谁生成的，且每个域都带。"""
    for domain, (_f, generated_path, _div) in DOMAINS.items():
        doc = load_cached(generated_path)
        assert doc["x-generated-by"] == "scripts/gen_contracts.py", domain
        assert doc["x-source-module"] == f"app.contracts.{domain}", domain


def test_identity_annotations_have_owners() -> None:
    """`identity-x-annotations` 的消费者：四条治理注释确实由本测试与 x-key 核对盯着。

    这里断言的是"注释键存在于稿且未出现在生成物里"——若哪天有人把它们抄进模型，
    `test_every_x_keyword_on_an_absorbed_def_is_claimed` 会要求登记表改名，
    而不是让两份真源悄悄并存。
    """
    draft_defs = _defs_of(load_cached(DOMAINS["identity"][0]))
    generated_defs = _defs_of(load_cached(DOMAINS["identity"][1]))
    for name, body in draft_defs.items():
        if name not in generated_defs or not isinstance(body, dict):
            continue
        leaked = [k for k in body if k.startswith("x-") and k not in generated_defs[name]]
        claimed = {x.strip() for d in DOMAINS["identity"][2] for x in d.field.replace(",", " ").split()}
        assert all(k in claimed for k in leaked), f"{name}: 注释键 {leaked} 既没进生成物也没登记责任人"


# ── 11. events 域：替登记表的每条 rule 兑现承诺 ───────────────────────────────


def test_event_name_set_equals_valid_event_types() -> None:
    """rule `event-name-set-anchor` 的消费者：稿、枚举、实现常量**三方**等值且同序。

    稿里那条 `x-source-of-truth` 说的是"新增事件名须三处同改"——那是件可以机器判的事，
    所以它不该只活在文本里。顺序也钉：比对器比 enum 原序，这里同步。
    """
    draft = _defs_of(load_cached(DOMAINS["events"][0]))["EventName"]["enum"]
    assert [e.value for e in events_contract.EventName] == draft
    assert {e.value for e in events_contract.EventName} == VALID_EVENT_TYPES
    assert _defs_of(load_cached(DOMAINS["events"][1]))["EventName"]["enum"] == draft


def test_idempotency_key_alias_witness() -> None:
    """`IdempotencyKey` 在本域**没有使用处** ⇒ 约束只能由本测试见证（ALIAS_WITNESSES 强制它存在）。

    实测两个键形状必须能过（`hot_rescore:yyyyMMddHH` / `sync_account:{sourceId}`），
    长度上界与稿一致（String(128)）。稿里另外两条（禁随机 uuid、禁拼用户可控串）不是形状，
    由 `test_random_uuid_idempotency_keys_are_a_closed_list` 与登记表点名的评审各自负责。
    """
    adapter: TypeAdapter[events_contract.IdempotencyKey] = TypeAdapter(events_contract.IdempotencyKey)
    assert adapter.validate_python("hot_rescore:2026101601")
    assert adapter.validate_python("sync_account:" + "0" * 36)
    with pytest.raises(ValidationError):
        adapter.validate_python("x" * 129)
    assert _defs_of(load_cached(DOMAINS["events"][0]))["IdempotencyKey"]["maxLength"] == 128


def test_retry_policy_constants_match_frozen_draft() -> None:
    """`push-retry-annotations` 的消费者：退避注释必须是**可执行事实**，不是散文。

    稿里写 `maxRetries: 3` / `backoffSeconds: [60, 240, 960]` / 公式 `60 * 4^(n-1)`。
    这里读 `push_scheduler` 的两个真实常量算出前三次再比——有人改公式而忘了改稿，
    或改了稿而忘了改实现，本测试都会红。
    """
    policy = _defs_of(load_cached(DOMAINS["events"][0]))["PushRetryState"]["x-retry-policy"]
    assert MAX_PUSH_RETRIES == policy["maxRetries"]
    assert [RETRY_BACKOFF_BASE_SECONDS * 4**n for n in range(MAX_PUSH_RETRIES)] == policy["backoffSeconds"]


def test_push_retry_state_tracks_runtime_push_result() -> None:
    """`response-data-type-conflict` 的消费者：钉住契约与运行时 `PushResult` 的当前真实关系。

    三方各说各话，必须**继续可见**而不是被"取实测"抹平：
    - 稿：`responseData: [object, null]`
    - 实现：`providers/push/base.py:50` 的 `response_data: str = ""`
    - 契约/产物：`string`
    裁决落地（改实现成结构化，或改稿）时这条会红——那是它应有的行为，不是回归。
    差集也点名：运行时多一个 `channel`（路由信息，不进响应面），不许默默少一列。
    """
    # `providers/push/base.py` 带 `from __future__ import annotations` ⇒ dataclass 的
    # `field.type` 是**字符串** `'str'`，直接 `is str` 永远假。取真正解析后的类型注解。
    runtime = get_type_hints(PushResult)
    assert runtime["response_data"] is str
    assert (runtime["delivered"], runtime["retryable"], runtime["reason"]) == (bool, bool, str)
    draft_props = _defs_of(load_cached(DOMAINS["events"][0]))["PushRetryState"]["properties"]
    gen_props = _defs_of(load_cached(DOMAINS["events"][1]))["PushRetryState"]["properties"]
    assert draft_props["responseData"]["type"] == ["object", "null"]
    assert gen_props["responseData"]["type"] == "string"
    python_names = set(events_contract.PushRetryState.model_fields)
    assert set(runtime) - {"channel"} == python_names
    assert events_contract.PushRetryState.model_fields["response_data"].alias == "responseData"


def test_push_retry_default_materializes_on_dump() -> None:
    """`events-dump-materializes-defaults` 的消费者：稿没写默认值，dump 会物化出空串。"""
    dumped = events_contract.PushRetryState.model_validate(
        {"delivered": False, "reason": "webhook 502", "retryable": True}
    ).model_dump()
    assert dumped["response_data"] == ""
    assert set(dumped) == {"delivered", "reason", "response_data", "retryable"}


# ── 12. "它不是形状"这套退出机制自己会不会被滥用 ──────────────────────────────


def test_comparator_bites_when_not_a_shape_marker_is_dropped() -> None:
    """删掉稿里的 `x-not-in-single-source` 标记 ⇒ 必须立刻红。

    红的原因是那个 def 带着比对器不实现的关键词（`enumStatus` / `legalEdges` /
    `illegalEdgesMustBeRejected`）。这条钉的是"退出比对要有**稿侧**声明"这半边——
    否则只要删标记，注释性 def 就变成"没人认识的关键词"而被静默跳过。
    """

    def mutate(doc: dict[str, Any]) -> None:
        doc["x-not-in-single-source"].pop("ManifestTransition", None)

    diffs = _compare_with_mutated_draft(mutate, domain="events")
    assert any("ManifestTransition" in d for d in diffs), f"删标记后仍然 0 条差异：{diffs}"


def test_comparator_bites_when_a_real_shape_is_declared_not_a_shape() -> None:
    """把**真形状** `PushRetryState` 标成"不是形状" ⇒ 必须红，而且红两处。

    ①`compare_defs` 发现它其实还在生成物里（标记过期）；
    ②narrow 测试发现它含 `properties`/`required`（根本不许退出比对）。
    这条是这套机制的正面防线：退出许可证只能给真正没有约束的东西。
    """

    def mutate(doc: dict[str, Any]) -> None:
        doc["x-not-in-single-source"]["PushRetryState"] = "我想让它消失"

    diffs = _compare_with_mutated_draft(mutate, domain="events")
    assert any("PushRetryState" in d for d in diffs), f"真形状被一句声明放走了：{diffs}"
    frozen = load_cached(DOMAINS["events"][0])
    marked = copy.deepcopy(frozen)
    marked["x-not-in-single-source"]["PushRetryState"] = "我想让它消失"
    shape_keys = _constraint_bearing(_defs_of(marked)["PushRetryState"])
    assert shape_keys, "narrow 判据找不到形状关键词 ⇒ 这条声明其实放得过去"


def test_registered_conflict_entry_does_not_swallow_neighbouring_drift() -> None:
    """`response-data-type-conflict` 只解释 `responseData` 的**类型**那一处。

    稿里把 `reason.maxLength` 从 512 改成 511，必须仍然报——否则"登记一条已知冲突"
    就等于给整个 def 买了免检票（第五轮验证对 `field=\"*\"` 的批评是同一件事）。
    """

    def mutate(doc: dict[str, Any]) -> None:
        doc["definitions"]["PushRetryState"]["properties"]["reason"]["maxLength"] = 511

    diffs = _compare_with_mutated_draft(mutate, domain="events")
    assert any("maxLength" in d for d in diffs), f"冲突登记越界吞掉了 maxLength 差异：{diffs}"


def test_default_materialization_must_be_named_property_by_property() -> None:
    """给一个**没被登记点名**的属性物化出默认值 ⇒ 必须红。

    这条钉的是 `default` 的方向判据里"点名"那一半：只按 def 放行的话，
    把 `pages` 的默认从 0 改成 7 也算"稿没写 ⇒ 模型物化"，照样溜过去（第五轮 I10b）。
    """

    def mutate(gen: dict[str, Any]) -> None:
        gen["$defs"]["EventName"]["default"] = "new_article"

    diffs = _compare_with_mutated_generated(mutate, domain="events")
    assert any("default" in d for d in diffs), f"未点名的默认物化被放走：{diffs}"


def test_document_root_divergences_are_named() -> None:
    """兑现 `root-is-a-container`：根层每一处不等价都必须有一条"文档根 + 点名该键"的登记。

    第六轮验证 G6 之前，比对器只看 `$defs`——往产物根塞 `type: string`、把稿根 `type` 删掉、
    给稿根加 `additionalProperties: false` 三种改动全部读绿，而且 `$id` 两边本来就不一样却无人记账
    （实测：collection 稿 `bothot://contracts/collection/v1`、identity/events 稿
    `https://bothot/contracts/<域>.schema.json`、产物一律 `bothot://contracts/<域>/v1`）。
    """
    for domain, (frozen_path, generated_path, divergences) in DOMAINS.items():
        frozen, generated = load_cached(frozen_path), load_cached(generated_path)
        for key in _ROOT_VALIDATING_KEYS:
            fa, fb = frozen.get(key, MISSING), generated.get(key, MISSING)
            if fa == fb:
                continue
            hit = _explains_root(divergences, key, fa, fb)
            assert hit is not None, f"{domain}: 根层 {key} 不等价（稿={fa} 生成={fb}）却没有方向合法的登记"
            if fa is not MISSING and fb is not MISSING:
                assert hit.kind == "conflict", (
                    f"{domain}: 根层 {key} 两侧都声明而值不同，用 {hit.kind} 解释等于把冲突写成等价写法"
                )
        assert not _stale_root_entries(divergences, frozen, generated)


def test_conflict_entries_cite_a_live_decision_id() -> None:
    """`conflict` 是第六种 kind，它**必须引一条台账行**——否则它只是"我不改了"的另一种写法。

    与 `structural`（等价写法）和 `tightening`（更严）都不同：`conflict` 承认稿与实测不相交。
    这种状态不能长期挂在比对器里而不带责任人，所以要求 reason 里写明的 `D-V<n>-<nn>`
    确实存在于 `decision-log.md`。台账行被删掉 ⇒ 本测试红 ⇒ 冲突重新变成待办。
    """
    ledger = (REPO_ROOT / "docs" / "03_solution" / "decisions" / "decision-log.md").read_text(encoding="utf-8")
    live = set(re.findall(r"D-V\d+-\d\d", ledger))
    assert live, "台账里一个裁决 ID 都找不到——文件路径或格式变了，本测试失去意义"
    for domain, (_f, _g, divergences) in DOMAINS.items():
        for d in divergences:
            if d.kind != "conflict":
                continue
            cited = set(re.findall(r"D-V\d+-\d\d", d.reason))
            assert cited, f"{domain}/{d.rule}: conflict 类登记没引台账裁决号"
            missing = sorted(cited - live)
            assert not missing, f"{domain}/{d.rule}: 引了台账里不存在的裁决号 {missing}"


def test_idempotency_key_bound_matches_the_column_that_enforces_it() -> None:
    """契约里那条 `maxLength: 128` 的真正执法者是 DB 列，不是 JSON Schema。

    第六轮验证点名：这个别名没有任何模型引用 ⇒ 128 在**线上形状**上无人执行，
    唯一硬约束是 `entities.py:202` 的 `String(128) unique=True`。
    长度与唯一性都必须与本条别名一致，否则契约写的是一个没人守的数。
    """
    from app.models.entities import Job

    column = Job.__table__.columns["idempotency_key"]
    assert column.type.length == 128, f"DB 列长度 {column.type.length} 与契约 maxLength 不一致"
    assert column.unique is True, "幂等靠这个键去重；列上的 unique 若被删，幂等语义整体失效"


def test_random_uuid_idempotency_keys_are_a_closed_list() -> None:
    """稿的 `x-rule` 禁止用随机 uuid 当幂等键——实测今天就有一处违反，而且是有意的。

    我第一版把这条注释的责任人写成「转 STEP-03 的作业创建路径评审」，那是把
    「现在就与契约冲突」讲成「以后再看」（第六轮验证点名）。实测锚：
    `apps/api/app/api/v1/hot.py:192` 用 `f"hot_cluster:{today}:{days}:{uuid4().hex[:8]}"`，
    它自己的注释解释动机是「已终结 job 不阻塞重跑」——与稿的规则直接对立。
    所以把它钉成一份**闭合清单**：新增一处 uuid 幂等键就红；
    而这处现存违规要么改代码、要么改稿并登记台账，不能靠「以后再说」隐身。
    """
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "apps" / "api" / "app").rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "idempotency_key=" in line and "uuid" in line:
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{lineno}")
    unexpected = sorted(set(offenders) - KNOWN_UUID_IDEMPOTENCY_SITES)
    assert not unexpected, (
        f"新增的随机 uuid 幂等键：{unexpected}（稿 events.IdempotencyKey.x-rule 明令禁止："
        "随机键等于没有幂等，重复入队）"
    )
    assert sorted(offenders) == sorted(KNOWN_UUID_IDEMPOTENCY_SITES), (
        f"闭合清单过期：实测 {offenders}，登记的是 {sorted(KNOWN_UUID_IDEMPOTENCY_SITES)}"
        "——违规被修掉就从清单里删掉它，留着是把历史当现状"
    )



# ── 13. 第六轮验证的击败方式，逐条钉成永久反证 ────────────────────────────────
# 验证者用下面这些注入把我的四条新机制全打穿过（它给的判据是 FAIL）。
# 每一条都在这里重生：**下一次谁把判定改松，CI 会替那位验证者再问一遍。**


def _swap_real_ref_for_fake(doc: dict[str, Any]) -> None:
    """identity：把 `SessionClaims.properties.sub` 的真 `$ref` 换成裸 `type`，假引用藏进注释位。

    验证者的 G3 原版（只加假引用）在修复后仍然是绿——那是**正确**的：
    `IdempotencyKey` 本来就靠 `ALIAS_WITNESSES` 那条合法去处过关，假引用没换来任何新放行。
    真正能证伪机制的是这个变体：撤掉真引用位，"已内联"就再也站不住，
    `Sub` 的 min/maxLength 必须当场变成三条差异。
    """
    claims = doc["definitions"]["SessionClaims"]
    claims["properties"]["sub"] = {"type": "string"}
    claims["x-note"] = {"$ref": "#/definitions/Sub"}


def _with_extra_entry(domain: str, entry: Divergence):
    """临时往某域的登记表里塞一条登记（用完必须还原，否则后面的测试读到脏域表）。"""
    original = DOMAINS[domain]

    class _Patched:
        def __enter__(self):
            DOMAINS[domain] = (original[0], original[1], original[2] + (entry,))
            return self

        def __exit__(self, *exc):
            DOMAINS[domain] = original
            compare_defs(domain)
            return False


    return _Patched()


@pytest.mark.parametrize(
    "label,domain,side,mutate",
    [
        (
            "G1 给带约束的别名发「不是形状」许可证",
            "events",
            "稿",
            lambda d: d["x-not-in-single-source"].__setitem__("IdempotencyKey", "想要它消失"),
        ),
        (
            "G2a 删掉 QueueMechanism 的非形状声明",
            "events",
            "稿",
            lambda d: d["x-not-in-single-source"].pop("QueueMechanism", None),
        ),
        (
            "G2b 删掉 EventPayloadRules 的非形状声明",
            "events",
            "稿",
            lambda d: d["x-not-in-single-source"].pop("EventPayloadRules", None),
        ),
        (
            "G3 把真引用位换成注释位里的假 $ref（别名『已内联』是编的）",
            "identity",
            "稿",
            _swap_real_ref_for_fake,
        ),
        (
            "G5a 产物丢掉稿点名的可选属性",
            "events",
            "生成物",
            lambda g: g["$defs"]["PushRetryState"]["properties"].pop("responseData", None),
        ),
        (
            "G5b 产物丢掉 collection 的可选属性",
            "collection",
            "生成物",
            lambda g: g["$defs"]["WorkListRow"]["properties"].pop("digest", None),
        ),
        (
            "G5c 产物清空 required（把必填 sub 删掉）",
            "identity",
            "生成物",
            lambda g: g["$defs"]["SessionClaims"].__setitem__("required", []),
        ),
        (
            "G6a 生成物根层 type 改成 string",
            "events",
            "生成物",
            lambda g: g.__setitem__("type", "string"),
        ),
        (
            "G6b 稿根层 type 被删（登记随即过期）",
            "events",
            "稿",
            lambda d: d.pop("type", None),
        ),
        (
            "G6c 稿根新增 additionalProperties:false 而产物没做",
            "events",
            "稿",
            lambda d: d.__setitem__("additionalProperties", False),
        ),
        (
            "G7 把物化默认值从空串改成别的值",
            "identity",
            "生成物",
            lambda g: g["$defs"]["SessionClaims"]["properties"]["iss"].__setitem__("default", "PWNED"),
        ),
    ],
    ids=lambda v: str(v),
)
def test_sixth_round_bypasses_are_now_blocked(label: str, domain: str, side: str, mutate: Any) -> None:
    """每一条都必须在 `compare_defs` 里留下差异——"红"是唯一可接受的读数。"""
    if side == "稿":
        diffs = _compare_with_mutated_draft(mutate, domain=domain)
    else:
        diffs = _compare_with_mutated_generated(mutate, domain=domain)
    assert diffs, f"比对器被绕过：注入「{label}」仍然 0 条差异"



def test_field_named_after_the_def_is_not_a_license() -> None:
    """第六轮 D4：`field` 写成 def 名 = 给整个 def 买免检票。五类漂移必须逐一仍红。"""
    swallower = Divergence(
        "PushRetryState", "PushRetryState", "tightening", "adv-def-name-swallower", "", "", "复现用"
    )
    def prs(g: dict[str, Any]) -> dict[str, Any]:
        return g["$defs"]["PushRetryState"]

    drifts = [
        ("required 变短", lambda g: prs(g).__setitem__("required", ["delivered"])),
        ("reason.maxLength 放宽", lambda g: prs(g)["properties"]["reason"].__setitem__("maxLength", 999)),
        ("delivered 改类型", lambda g: prs(g)["properties"]["delivered"].__setitem__("type", "string")),
        ("retryable 删除", lambda g: prs(g)["properties"].pop("retryable", None)),
        ("私加 additionalProperties", lambda g: prs(g).__setitem__("additionalProperties", False)),
    ]
    with _with_extra_entry("events", swallower):
        for label, mutate in drifts:
            diffs = _compare_with_mutated_generated(mutate, domain="events")
            assert diffs, f"登记写 def 名就能吞差异：「{label}」读 0 条"
            # 这条登记也必须过"必须有消费者"那关：它解释过差异不算兑现承诺
            assert "adv-def-name-swallower" not in compare_defs("events")[1], "恶意登记靠解释差异自证消费"


def test_bare_fact_token_cannot_explain_a_property_level_drift() -> None:
    """第六轮 D8：`kind="documentation" + field="types"` 曾解释掉属性级类型改动。

    裸事实名现在只许"完整路径点名"，而 `documentation` 也不在 `types` 这一档的允许集合里，
    所以两道闸任意一道都能拦住它。这里两条分别验，免得日后有人只修一半。
    """
    for kind in ("documentation", "tightening"):
        evil = Divergence("PushRetryState", "types", kind, f"adv-bare-{kind}", "", "", "复现用")
        with _with_extra_entry("events", evil):
            diffs = _compare_with_mutated_generated(
                lambda g: g["$defs"]["PushRetryState"]["properties"]["delivered"].__setitem__("type", "string"),
                domain="events",
            )
            assert diffs, f"裸事实名 + kind={kind} 仍能解释属性级类型改动"


def test_conflict_kind_needs_a_live_ledger_row() -> None:
    """`conflict` 不是"我不改了"的另一种写法：它必须引一条真实存在的台账裁决号。"""
    from app.contracts.events import CONTRACT_DIVERGENCES as EV

    forged = tuple(
        d._replace(reason="台账行：**D-V9-99**（并不存在）") if d.kind == "conflict" else d for d in EV
    )
    original = DOMAINS["events"]
    try:
        DOMAINS["events"] = (original[0], original[1], forged)
        module = sys.modules[__name__]
        try:
            module.test_conflict_entries_cite_a_live_decision_id()
        except AssertionError:
            return
        raise AssertionError("引了不存在的裁决号却没红——conflict 的台账链接是装饰")
    finally:
        DOMAINS["events"] = original
        compare_defs("events")


# ── 9. 产物与模型的即时一致性（把 CI 那条链拉进本地测试）───────────────────────


def test_generated_artifact_matches_current_model() -> None:
    """有人改了模型却没重跑生成器时，这条必须红——**每个域都查**。

    `--check` 只在 CI 跑（`ci.yml:97-98`），提交前那段窗口本地是裸的；
    而 `compare_defs()` 读的是**两个文件**，模型改了在本地全组测试照样绿
    （第三轮验证点名的空档）。这里在进程内 import 生成器重算，不落盘。

    第五轮验证抓到的正是范围问题：本条第一版硬编码 `["collection"]`，
    于是 identity 域"模型 ≠ 已提交产物"这段窗口本地完全没门禁——
    上面三条新盲区（default / 多支 anyOf / tuple items）也全落在这段裸窗口里。
    """
    spec = importlib.util.spec_from_file_location("gen_contracts_under_test", GEN_CONTRACTS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fresh = module.generate_schemas()
    assert set(fresh) == set(DOMAINS), f"生成器覆盖的域与域表不一致：{sorted(fresh)} vs {sorted(DOMAINS)}"
    for domain, path in ((d, DOMAINS[d][1]) for d in sorted(DOMAINS)):
        assert fresh[domain] == path.read_text(encoding="utf-8"), (
            f"{domain}: 模型与已提交产物不一致，跑 `python scripts/gen_contracts.py` 重生成"
        )
