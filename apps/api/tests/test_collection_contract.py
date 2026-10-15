"""STEP-01 S1.3.2 + S1.4.1 —— 采集域契约的语义比对与锚定测试。

要防的事（这条文件存在的唯一理由）：`gen_contracts --check` 只保证
「产物 == 模型的 JSON Schema」，**不保证「模型 == 冻结稿」**。
中间那一段如果没人管，唯一源就退化成"我以为它是唯一源"。

三条纪律，每条都有对应的反证测试，不是口号：
1. **归一不免费** —— 比对器每用一次归一，都必须有对应 kind 的登记；
   反过来登记表里每条 `rule` 也必须真被消费（被比对器用到，或被本文件某个断言兑现）。
   双向核对见 `test_registry_rules_are_all_consumed`。
   第三轮独立验证就是拿这个打的：`x-not`、"另设 dump 形状检查"、`strictness` 三条当时是
   **只有承诺、没有实现者**的装饰条目。
2. **未知关键词两侧都查** —— 稿**和生成物**任一出现比对器没实现的关键词 ⇒ 红。
   第一版只查稿侧，所以往生成物塞 `minItems` / `const` 能静默溜过去。
3. **pattern 比文本推导，不只比语料** —— 稿的 `oneOf` 三支去掉 `^`/`$` 折成
   `^(?:A|B|C)$` 后必须与生成物 pattern **逐字符相等**。
   11 条语料会被 `{32}`→`{31,32}`、字符类去掉 `-`、`{1,12}`→`{1,13}` 绕过：
   量词与字符类是正则语义，有限样本罩不住。

`jsonschema` / `hypothesis` 都不在依赖里，也**不装**：比对器自己实现稿实际用到的关键词子集。
不起 TestClient（U-23 的挂起面就在那）、不连库、不联网。
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

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

REPO_ROOT = Path(__file__).resolve().parents[3]
FROZEN_PATH = REPO_ROOT / "docs" / "任务规划V0.12.0" / "contracts" / "collection.schema.json"
GENERATED_PATH = REPO_ROOT / "packages" / "contracts" / "schemas" / "collection.schema.json"
ERRORS_FROZEN_PATH = REPO_ROOT / "docs" / "任务规划V0.12.0" / "contracts" / "errors.global.schema.json"
GEN_CONTRACTS_PATH = REPO_ROOT / "scripts" / "gen_contracts.py"

# 比对器**实现了**的校验关键词。两侧任一出现别的关键词 ⇒ 红（宁可吵，不可静默少比）。
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
    }
)
# 人读面/默认值关键词：允许存在，但必须由登记表的 rule 解释
STRIPPED_KEYWORDS_TO_RULE = {
    "title": "strip-title",
    "description": "strip-description",
    "default": "dump-materializes-defaults",
}
# 这些键不参与"未映射关键词"判定（结构性或文档性，已由别处处理）
_NON_CONSTRAINT_KEYS = frozenset(
    {"$defs", "definitions", "$schema", "$id", "$ref", "title", "description", "default"}
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


_LOADED: dict[Path, dict[str, Any]] = {}


def load_cached(path: Path) -> dict[str, Any]:
    """两个文档要读很多次（9 个 def 各参数化一条），缓存掉：第一版没缓存时这文件跑 75s。"""
    if path not in _LOADED:
        _LOADED[path] = _load(path)
    return _LOADED[path]


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
    "",
)

_USED_RULES: set[str] = set()


def _note_rule(rule: str) -> None:
    _USED_RULES.add(rule)


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
    return f"{text}#{vector}"


def _canon(node: Any) -> dict[str, Any]:
    """归一成只含约束事实的字典。

    **没被本函数映射过的关键词不会被静默丢掉**：它们进 `unmapped` ⇒ 成为差异。
    第三轮验证往生成物塞 `minItems` / `const` 能溜过去，就是因为第一版只读它认识的那几个键。
    """
    node = node if isinstance(node, dict) else {}
    facts: dict[str, Any] = {}
    types: list[str] = []
    nullable = False
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
    ):
        if key in node:
            facts[key] = node[key]
    if "required" in node:
        facts["required"] = sorted(node["required"])  # required 是集合，不比顺序
        _note_rule("required-order")
    if "items" in node:
        facts["items"] = _canon(node["items"])
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
}


def compare_defs(
    divergences: tuple[Divergence, ...] = CONTRACT_DIVERGENCES,
) -> tuple[list[str], set[str]]:
    """逐 def 比对，返回 (未解释的差异, 实际用到的归一规则)。

    差异一律以 `def名:` 开头 ⇒ 参数化的"每 def 一条测试"才分得清是谁的责任。
    第一版属性级路径是 `WorkListRow.properties.title.maxLength`，而过滤器找 `WorkListRow:`，
    于是 9 条参数化测试全绿、只有汇总那条红——"每 def 可定位"是假的（第三轮验证抓到）。
    """
    _USED_RULES.clear()
    frozen = load_cached(FROZEN_PATH)
    generated = load_cached(GENERATED_PATH)
    fdefs, gdefs = frozen["$defs"], generated["$defs"]

    problems: list[str] = []
    for name, node in fdefs.items():
        _walk(node, f"稿.{name}", fdefs, problems, frozenset({name}))
    for name, node in gdefs.items():
        _walk(node, f"生成.{name}", gdefs, problems, frozenset({name}))
    if problems:
        return problems, set(_USED_RULES)

    diffs: list[str] = []
    for name in sorted(set(fdefs) | set(gdefs)):
        if name not in gdefs:
            if any(d.ref == name and d.kind == "structural" for d in divergences):
                _note_rule("ref-inlining")
                continue
            diffs.append(f"{name}: 生成物缺这个 def（且没有 rule={name} 的 structural 登记）")
            continue
        if name not in fdefs:
            diffs.append(f"{name}: 生成物多出一个 def（稿里没有 ⇒ 谁加的？）")
            continue
        a = _canon(_resolve(fdefs[name], fdefs))
        b = _canon(_resolve(gdefs[name], gdefs))
        if a != b:
            for path, fa, fb in _flat_diff(a, b, name):
                tail = path[len(name) + 1 :] if path.startswith(f"{name}.") else path
                diffs.append(f"{name}: {tail} 稿={fa} 生成={fb}")
    return diffs, set(_USED_RULES)


def _flat_diff(a: Any, b: Any, path: str) -> list[tuple[str, Any, Any]]:
    out: list[tuple[str, Any, Any]] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a:
                out.append((f"{path}.{key}", None, b[key]))
            elif key not in b:
                out.append((f"{path}.{key}", a[key], None))
            else:
                out.extend(_flat_diff(a[key], b[key], f"{path}.{key}"))
    elif a != b:
        out.append((path, a, b))
    return out


# ── 1. 结构与比对 ─────────────────────────────────────────────────────────────


def test_both_contract_files_exist() -> None:
    assert FROZEN_PATH.exists(), f"冻结稿不在位：{FROZEN_PATH}"
    assert GENERATED_PATH.exists(), f"生成物不在位:{GENERATED_PATH}（跑 scripts/gen_contracts.py）"


@pytest.mark.parametrize("side,path", [("稿", FROZEN_PATH), ("生成物", GENERATED_PATH)])
def test_neither_side_uses_a_keyword_the_comparator_does_not_implement(side: str, path: Path) -> None:
    """两侧都查未知关键词：漏一侧 = 那一侧可以随便加约束而门禁不响。"""
    doc = load_cached(path)
    defs = doc["$defs"]
    problems: list[str] = []
    for name, node in defs.items():
        _walk(node, f"{side}.{name}", defs, problems, frozenset({name}))
    assert not problems, "；".join(problems)


@pytest.mark.parametrize("def_name", sorted(load_cached(FROZEN_PATH)["$defs"].keys()))
def test_each_draft_def_is_explained_or_equal(def_name: str) -> None:
    diffs, _used = compare_defs()
    mine = [d for d in diffs if d.split(":", 1)[0] == def_name]
    assert not mine, f"{def_name} 与冻结稿不等且无登记：\n  " + "\n  ".join(mine)


def test_whole_domain_has_no_unexplained_divergence() -> None:
    diffs, _used = compare_defs()
    assert not diffs, "未登记的约束差异：\n  " + "\n  ".join(diffs)


# ── 2. 登记表与归一化的双向核对 ───────────────────────────────────────────────


def test_normalizations_used_are_all_backed_by_registry() -> None:
    """正向：比对器实际用到的每条归一，都必须有对应 kind 的登记。"""
    _diffs, used = compare_defs()
    kinds = {d.kind for d in CONTRACT_DIVERGENCES}
    for rule in used:
        need = _NORMALIZATION_TO_KIND[rule]
        assert need in kinds, f"归一 {rule} 用到，但登记表里没有 {need} 类支撑"


def test_registry_rules_are_all_consumed() -> None:
    """反向（第三轮验证逼出来的）：每条登记的 rule 都必须真有人消费。

    消费 = 被比对器用到，或本文件里有一个能跑断它的函数。
    第一版登记表里 `x-not`、"另设 dump 形状检查"、`strictness` 三条只有承诺没有实现者，
    那种条目让登记表**看起来**完备，实际是装饰。
    """
    _diffs, used = compare_defs()
    consumers: dict[str, Any] = {
        "pattern-equivalence": test_article_key_pattern_text_is_derivable_from_draft,
        "bounds-redundant": test_article_key_bounds_are_redundant,
        "x-not-by-witness": test_bare_s_is_rejected_by_witness,
        "timezone-required:publish_time": test_publish_time_requires_timezone_aware_value,
        "timezone-required:at": test_collection_event_at_requires_timezone,
        "timezone-required:lastSuccessAt": test_last_success_at_requires_timezone,
        "dump-materializes-defaults": test_optional_defaults_materialize_on_dump,
        "extra-dropped": test_unknown_fields_dropped_except_work_list_row,
    }
    unclaimed: list[str] = []
    for d in CONTRACT_DIVERGENCES:
        if d.rule in used:
            continue
        fn = consumers.get(d.rule)
        if fn is None:
            unclaimed.append(f"{d.rule}（{d.ref} / {d.field}）既没被比对器用到，也没有消费者函数")
            continue
        fn()
    assert not unclaimed, "登记表里的 dead claim：\n  " + "\n  ".join(unclaimed)


def test_every_draft_x_keyword_is_registered() -> None:
    """稿里每个 `x-*` 注释都必须在登记表里有归宿（reason 承诺过，这次真的实现）。"""
    keys: set[str] = set()

    def scan(node: Any) -> None:
        if isinstance(node, dict):
            keys.update(k for k in node if k.startswith("x-"))
            for value in node.values():
                scan(value)
        elif isinstance(node, list):
            for value in node:
                scan(value)

    scan(load_cached(FROZEN_PATH)["$defs"])
    claimed = {d.field for d in CONTRACT_DIVERGENCES} | {d.rule for d in CONTRACT_DIVERGENCES}
    missing = sorted(k for k in keys if k not in claimed)
    assert not missing, f"稿里的注释键 {missing} 在登记表里无人认领"


# ── 3. 比对器自己会不会被绕过（把外部验证者的击败方式钉成测试）─────────────────


def _compare_with_mutated_generated(mutate: Any) -> list[str]:
    """在内存里替换生成物跑比对，**不写任何仓库文件**。"""
    original = load_cached(GENERATED_PATH)
    mutated: dict[str, Any] = copy.deepcopy(original)
    mutate(mutated)
    _LOADED[GENERATED_PATH] = mutated
    try:
        return compare_defs()[0]
    finally:
        _LOADED[GENERATED_PATH] = original
        compare_defs()  # 复位 _USED_RULES，避免污染后面的核对


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
    ],
)
def test_comparator_bites_on_each_drift_class(label: str, mutate: Any) -> None:
    """十一类真实漂移，每类都必须被抓。

    这组直接来自第三轮独立验证——它用这些方式击败过第一版比对器。
    钉成测试的意思是：**下一次谁把比对器改坏，CI 会替那位验证者再问一遍。**
    """
    diffs = _compare_with_mutated_generated(mutate)
    assert diffs, f"比对器被绕过：注入「{label}」仍然 0 条差异"


def test_comparator_does_not_false_positive() -> None:
    """对照：什么都没改 ⇒ 必须 0 条（否则上面那组"红"没有意义）。"""
    assert compare_defs()[0] == []


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


# ── 9. 产物与模型的即时一致性（把 CI 那条链拉进本地测试）───────────────────────


def test_generated_artifact_matches_current_model() -> None:
    """有人改了模型却没重跑生成器时，这条必须红。

    `--check` 只在 CI 跑（`ci.yml:97-98`），提交前那段窗口本地是裸的；
    而 `compare_defs()` 读的是**两个文件**，模型改了在本地全组测试照样绿
    （第三轮验证点名的空档）。这里在进程内 import 生成器重算，不落盘。
    """
    spec = importlib.util.spec_from_file_location("gen_contracts_under_test", GEN_CONTRACTS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fresh = module.generate_schemas()["collection"]
    assert fresh == GENERATED_PATH.read_text(encoding="utf-8"), (
        "模型与已提交产物不一致：跑 `python scripts/gen_contracts.py` 重生成"
    )
