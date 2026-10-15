"""STEP-01 S1.3.2 + S1.4.1 —— 采集域契约的语义比对与锚定测试。

要防的事（这条文件存在的唯一理由）：`gen_contracts --check` 只保证
「产物 == 模型的 JSON Schema」，**不保证「模型 == 冻结稿」**。
中间那一段如果没人管，唯一源就退化成"我以为它是唯一源"。

所以这里做三件事：
1. 把 `packages/contracts/schemas/collection.schema.json`（生成物）与
   `docs/任务规划V0.12.0/contracts/collection.schema.json`（冻结稿）按**约束面**逐字段比；
2. 比之前先归一，而**每条归一都必须由 `CONTRACT_DIVERGENCES` 里的一条登记撑腰**——
   没登记就归一 = 把差异藏起来；
3. 反证（S1.2.2.3 同族）：故意把某条登记删掉 ⇒ 比对必须红。
   没有这一条，"表里没有的差异一律红"只是个口号。

纯函数测试：不起 TestClient（U-23 的挂起面就在这）、不连库、不联网。
`jsonschema` 库**未安装也不装**——比对器自己实现稿里实际用到的关键字子集，
遇到不认识的关键词直接红，而不是忽略（忽略 = 静默少比一项，比报错危险）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from app.contracts.collection import (
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

# 冻结稿里实际用到的、参与**校验语义**的关键词。新增关键词必须先在这里登记，
# 否则比对器会把它当"未知关键词"直接红（故意：漏比一个关键词比报错危险得多）。
SUPPORTED_VALIDATING_KEYWORDS = frozenset(
    {
        "type",
        "enum",
        "pattern",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
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
# 非校验语义（文档/扩展）关键词：允许存在，但**必须**被登记表解释才有资格出现在生成物差异里。
NON_VALIDATING_KEYWORDS = frozenset({"title", "description", "default", "x-not", "$schema", "$id"})


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


_LOADED: dict[Path, dict[str, Any]] = {}


def load_cached(path: Path) -> dict[str, Any]:
    """两个 schema 文档要读很多次（9 个 def 各参数化一条测试），缓存掉：
    第一版没缓存时这个"纯函数文件"跑了 75s，缓存后应当是个位数秒。"""
    if path not in _LOADED:
        _LOADED[path] = _load(path)
    return _LOADED[path]


def _ref_name(node: dict[str, Any]) -> str:
    return str(node["$ref"]).rsplit("/", 1)[-1]


def _walk(node: Any, where: str, defs: dict[str, Any], problems: list[str], seen: frozenset[str]) -> None:
    """稿里出现未知关键词 ⇒ 记一条问题（宁可红，不可静默少比）。

    只从**已知结构位**下钻（`properties` 的每个值、`items`、`oneOf/anyOf` 分支、`$ref` 目标）。
    第一版把 `properties` 容器当关键词表遍历，踩了两个坑：
    ① 空 dict 的自我递归（`_walk({})` 又去取 `{}.get("properties")` ⇒ RecursionError）；
    ② 名叫 `title` / `description` 的**属性**被当成 schema 关键词 `continue` 掉 ⇒ 静默没比。
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
            or key in NON_VALIDATING_KEYWORDS
            or key.startswith("x-")
            or key in {"$defs", "definitions"}
        ):
            continue
        problems.append(f"{where}: 比对器不认识关键词 {key!r}（要么实现它，要么改稿——不能忽略）")
    for name, sub in (node.get("properties") or {}).items():
        _walk(sub, f"{where}.{name}", defs, problems, seen)
    if node.get("items") is not None:
        _walk(node["items"], f"{where}.items", defs, problems, seen)
    for i, branch in enumerate(node.get("oneOf") or node.get("anyOf") or []):
        _walk(branch, f"{where}.oneOf[{i}]", defs, problems, seen)
    if "$ref" in node:
        target_name = _ref_name(node)
        if target_name in seen:
            return  # 循环引用：已经进去过一次，别再进
        if target_name not in defs:
            problems.append(f"{where}: $ref 指向不存在的 {node['$ref']}")
            return
        _walk(defs[target_name], f"{where}->{target_name}", defs, problems, seen | {target_name})


def _resolve(node: Any, defs: dict[str, Any]) -> Any:
    """展开 `$ref`。JSON Schema 2020-12 允许 `$ref` 与兄弟关键词并存且**两者都生效**，
    所以这里必须把目标 def 与兄弟键合并——第一版只在"整个节点就是 $ref"时展开，
    于是 `{"$ref":…, "description":…}` 这种写法被当成没有约束，稿侧比出 None（假差异）。
    """
    if isinstance(node, dict):
        if "$ref" in node:
            name = _ref_name(node)
            if name not in defs:
                return {"__unresolved_ref__": node["$ref"]}
            siblings = {k: v for k, v in node.items() if k != "$ref"}
            merged = {**_resolve(defs[name], defs), **siblings}
            return merged
        return {k: _resolve(v, defs) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve(x, defs) for x in node]
    return node


# 见证语料：给 pattern 做**接受集**比较用（不比 pattern 文本）。
# 故意不含带换行的串——Python 的 `$` 与 ECMA-262 的 `$` 在尾随换行上不同，
# 那个差异由 `test_article_key_rejects_degenerate_and_foreign_shapes` 直接打模型，
# 不在这里用一个两边同款（都是 Python 语义）的向量去假装证明。
_PATTERN_CORPUS = (
    "b:MzI4NjA5NTU4Mg:2650635316:1",
    "b:MzI4NjA5NTU4Mg:2650635316:12",
    "b:short:1:1",
    "s:abcDEF12",
    "s:tooShort",
    "h:0123456789abcdef0123456789abcdef",
    "h:0123456789ABCDEF0123456789abcdef",
    "s",
    "ssssssss",
    "x:abcdefgh",
    "",
)


def _pattern_acceptance(branches: list[str]) -> tuple[bool, ...]:
    return tuple(any(re.search(p, w) for p in branches) for w in _PATTERN_CORPUS)


def _canon(node: Any) -> dict[str, Any]:
    """归一成一个只含"约束事实"的字典；返回的键由登记表的规则决定该不该比。

    归一化本身**不是免费的**：每条都在 `_NORMALIZATION_TO_KIND` 里映射到登记表的 kind，
    比对时若真的靠某条归一才"相等"，就必须能在 CONTRACT_DIVERGENCES 找到同 kind 的登记。
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
    patterns = [str(b["pattern"]) for b in (node.get("oneOf") or []) if isinstance(b, dict) and "pattern" in b]
    if "pattern" in node:
        patterns.append(str(node["pattern"]))
    if patterns:
        # 不比 pattern 文本，比**接受集**（见 _PATTERN_CORPUS 的说明）
        facts["patternAccept"] = _pattern_acceptance(patterns)
    for key, fact in (
        ("minLength", "minLength"),
        ("maxLength", "maxLength"),
        ("minimum", "minimum"),
        ("maximum", "maximum"),
        ("format", "format"),
        ("enum", "enum"),
        ("additionalProperties", "additionalProperties"),
    ):
        if key in node:
            facts[fact] = node[key]
    if "required" in node:
        facts["required"] = sorted(node["required"])  # JSON Schema 的 required 是集合，不比顺序
    if "items" in node:
        facts["items"] = _canon(node["items"])
    if "properties" in node:
        facts["properties"] = {k: _canon(v) for k, v in node["properties"].items()}
    facts["types"] = sorted(types)
    facts["nullable"] = nullable
    return facts


# 每条归一化 → 它必须被哪种 kind 的登记撑腰
_NORMALIZATION_TO_KIND = {
    "strip-title": "documentation",
    "strip-description": "documentation",
    "strip-default": "serialization",
    "nullable-form": "structural",
    "oneOf-to-pattern-set": "structural",
    "ref-inlining": "structural",
    "required-order": "structural",
}


def _registry_kinds(divergences: tuple[Divergence, ...]) -> set[str]:
    return {d.kind for d in divergences}


def compare_defs(
    divergences: tuple[Divergence, ...] = CONTRACT_DIVERGENCES,
) -> tuple[list[str], set[str]]:
    """逐 def 比对。返回 (未解释的差异列表, 实际用到的归一规则名)。

    未解释的差异 = 生成物与稿在约束事实上不等，且没有对应的登记 ⇒ 测试必须红。
    """
    frozen = load_cached(FROZEN_PATH)
    generated = load_cached(GENERATED_PATH)
    fdefs, gdefs = frozen["$defs"], generated["$defs"]

    problems: list[str] = []
    for name, node in fdefs.items():
        _walk(node, f"稿.{name}", fdefs, problems, frozenset({name}))
    if problems:
        return problems, set()

    used: set[str] = {"strip-title", "strip-description", "required-order"}
    diffs: list[str] = []
    for name in sorted(set(fdefs) | set(gdefs)):
        if name not in gdefs:
            # 生成物没有这个 def：只有当登记表里**针对这个名字**有一条 structural 登记时才放行
            # （第一版写的是"registry 里有任意 structural 就放行"，那等于把删除某一条登记
            # 也照样放过 ⇒ 反证测试打不中，门禁是假的）
            covered = any(d.ref == name and d.kind == "structural" for d in divergences)
            if covered:
                used |= {"ref-inlining", "oneOf-to-pattern-set"}
                continue
            diffs.append(f"{name}: 生成物缺这个 def（且无针对该 def 的 structural 登记）")
            continue
        if name not in fdefs:
            diffs.append(f"{name}: 生成物多出一个 def（稿里没有 ⇒ 谁加的？）")
            continue
        a = _canon(_resolve(fdefs[name], fdefs))
        b = _canon(_resolve(gdefs[name], gdefs))
        if a != b:
            for path, fa, fb in _flat_diff(a, b, name):
                # 时间字段：稿用 format 注记、模型用 AwareDatetime ⇒ 形状可能同形，
                # 不同形时留给登记解释（tightening 类），这里只报告不吞。
                diffs.append(f"{path}: 稿={fa} 生成={fb}")
    return diffs, used


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


# ── 结构与比对 ────────────────────────────────────────────────────────────────


def test_both_contract_files_exist() -> None:
    assert FROZEN_PATH.exists(), f"冻结稿不在位：{FROZEN_PATH}"
    assert GENERATED_PATH.exists(), f"生成物不在位：{GENERATED_PATH}（跑 scripts/gen_contracts.py）"


def test_draft_has_no_keyword_the_comparator_does_not_understand() -> None:
    """比对器的覆盖面对稿负责：稿用了没实现的关键字 ⇒ 红，不静默少比。"""
    frozen = load_cached(FROZEN_PATH)
    problems: list[str] = []
    for name, node in frozen["$defs"].items():
        _walk(node, name, frozen["$defs"], problems, frozenset({name}))
    assert not problems, "；".join(problems)


@pytest.mark.parametrize("def_name", sorted(load_cached(FROZEN_PATH)["$defs"].keys()))
def test_each_draft_def_is_explained_or_equal(def_name: str) -> None:
    diffs, _used = compare_defs()
    mine = [d for d in diffs if d.startswith(f"{def_name}:") or f".{def_name}." in d]
    assert not mine, f"{def_name} 与冻结稿不等且无登记：\n  " + "\n  ".join(mine)


def test_whole_domain_has_no_unexplained_divergence() -> None:
    diffs, _ = compare_defs()
    assert not diffs, "未登记的约束差异：\n  " + "\n  ".join(diffs)


def test_normalizations_are_all_backed_by_registry() -> None:
    """用到的每条归一都必须有对应 kind 的登记——归一不是免费的。"""
    kinds = _registry_kinds(CONTRACT_DIVERGENCES)
    for rule, need in _NORMALIZATION_TO_KIND.items():
        assert need in kinds, f"归一 {rule} 要求 {need} 类登记，登记表里没有（现有 kind：{sorted(kinds)}）"


def test_comparator_bites_when_a_registry_entry_is_removed() -> None:
    """S1.2.2.3 同族反证：删掉 ArticleKey 那条 structural 登记 ⇒ 比对必须报差异。

    没有这条测试，"表里没有的差异一律红"就是句口号：门打不打得中从来没人验。
    """
    reduced = tuple(d for d in CONTRACT_DIVERGENCES if not (d.ref == "ArticleKey" and d.kind == "structural"))
    assert len(reduced) < len(CONTRACT_DIVERGENCES), "筛选没生效，反证无意义"
    diffs, _ = compare_defs(reduced)
    assert any("ArticleKey" in d for d in diffs), f"删了登记居然没红：{diffs}"


# ── 键不变量（ADR-0011 §3 的 1/4 两条；2/3 需要 URL，归 STEP-02）────────────────


_ARTICLE_KEY_ADAPTER = TypeAdapter(ArticleKey)

KEY_ACCEPT = [
    "b:MzI4NjA5NTU4Mg:2650635316:1",
    "s:abcDEF12",
    "h:0123456789abcdef0123456789abcdef",
]
KEY_REJECT = [
    "s",  # ADR-0011 不变量 1 的退化形状（P0-1 回归锚）
    "ssssssss",
    "b:a:b:c",
    "h:0123456789ABCDEF0123456789abcdef",  # 大写 hex 不进 h: 分支
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


# ── 渠道与状态机 ──────────────────────────────────────────────────────────────


def test_channel_name_set_equals_registry_channels() -> None:
    """与实现比**集合**（dict 插入序是实现细节，不该被契约依赖）。"""
    assert {c.value for c in ChannelName} == set(CHANNELS.keys())


def test_channel_name_order_matches_the_frozen_draft() -> None:
    """顺序只与冻结稿比——那才是合同。"""
    draft = load_cached(FROZEN_PATH)["$defs"]["ChannelName"]["enum"]
    assert [c.value for c in ChannelName] == draft


def test_manifest_status_values_and_transition_documentation() -> None:
    draft = load_cached(FROZEN_PATH)["$defs"]["ManifestStatus"]["enum"]
    assert [s.value for s in ManifestStatus] == draft
    # 迁移表不由枚举校验（由 STEP-04 服务层承担），所以这里钉的是**值集**，别把注释当校验读。


def test_collection_event_enums_match_draft() -> None:
    generated = load_cached(GENERATED_PATH)["$defs"]["CollectionEvent"]["properties"]["event"]["enum"]
    draft = load_cached(FROZEN_PATH)["$defs"]["CollectionEvent"]["properties"]["event"]["enum"]
    assert generated == draft


# ── WorkListRow / WorkListPage 的必填与透传 ───────────────────────────────────


def test_work_list_row_required_fields_match_draft() -> None:
    draft = load_cached(FROZEN_PATH)["$defs"]["WorkListRow"]["required"]
    assert sorted(WorkListRow.model_json_schema()["required"]) == sorted(draft)


def test_work_list_row_passes_through_unknown_fields() -> None:
    """`additionalProperties: true` 的实现面：上游字段差异大，契约只钉必填。"""
    row = WorkListRow.model_validate({"id": "1", "url": "https://x.test/a", "title": "t", "upstream_extra": 7})
    assert row.model_dump().get("upstream_extra") == 7


@pytest.mark.parametrize(
    "payload,expect_ok",
    [
        ({"id": "1", "url": "https://x.test/a", "title": "t"}, True),
        ({"url": "https://x.test/a", "title": "t"}, False),  # 缺 id
        ({"id": "", "url": "https://x.test/a", "title": "t"}, False),  # id 空
        ({"id": "1", "url": "http:/", "title": "t"}, False),  # url < 8 字符
        ({"id": "1", "url": "https://x.test/a"}, False),  # 缺 title
    ],
)
def test_work_list_row_accept_set(payload: dict[str, str], expect_ok: bool) -> None:
    if expect_ok:
        WorkListRow.model_validate(payload)
        return
    with pytest.raises(ValidationError):
        WorkListRow.model_validate(payload)


def test_publish_time_requires_timezone_aware_value() -> None:
    """登记表里的 tightening：稿的 `format: date-time` 只是注记，模型真校验。

    这一条**故意与稿的宽松度不同**，所以它必须同时出现在登记表和这里——
    登记表说明"为什么允许不同"，这里保证"确实不同"。
    """
    with pytest.raises(ValidationError):
        WorkListRow.model_validate({"id": "1", "url": "https://x.test/a", "title": "t", "publish_time": "2024-01-01"})
    row = WorkListRow.model_validate(
        {"id": "1", "url": "https://x.test/a", "title": "t", "publish_time": "2024-01-01T00:00:00+08:00"}
    )
    assert row.publish_time is not None and row.publish_time.utcoffset() is not None


def test_work_list_page_next_cursor_is_required_nullable() -> None:
    """S1.2.1 第一轮验证抓到的那条：缺字段 ≠ 末页，必须显式 null。"""
    draft = load_cached(FROZEN_PATH)["$defs"]["WorkListPage"]["required"]
    assert sorted(draft) == ["next_cursor", "page_size", "rows"]
    with pytest.raises(ValidationError):
        WorkListPage.model_validate({"rows": [], "page_size": 1})
    page = WorkListPage.model_validate({"rows": [], "next_cursor": None, "page_size": 1})
    assert page.next_cursor is None


def test_manifest_sync_report_counts_are_non_negative() -> None:
    base = {
        "channel": "rss",
        "pages": 0,
        "rows": 0,
        "new": 0,
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
        "id_fallback": 0,
    }
    ManifestSyncReport.model_validate(base)
    with pytest.raises(ValidationError):
        ManifestSyncReport.model_validate({**base, "rows": -1})


# ── 错误码映射（S1.4.1 第四条锚）──────────────────────────────────────────────


def test_error_code_names_match_frozen_errors_contract() -> None:
    """`app/core/errors.py` 的登记必须与 `errors.global.schema.json` 的 x-table 逐条相等。

    这是"错误码映射"的可执行版本：不是"看起来差不多"，而是 code 与 name **一一对号**。
    """
    table = load_cached(ERRORS_FROZEN_PATH)["x-table"]
    assert len(table) == len(ERROR_CODES), f"条数不等：稿 {len(table)} / 后端 {len(ERROR_CODES)}"
    mismatched = [
        (e["code"], e["name"], ERROR_CODES.get(e["code"]))
        for e in table
        if ERROR_CODES.get(e["code"]) != e["name"]
    ]
    assert not mismatched, f"逐条对号失败：{mismatched}"


def test_error_code_enum_in_contract_covers_backend_registry() -> None:
    contract_codes = set(load_cached(ERRORS_FROZEN_PATH)["definitions"]["ErrorCode"]["enum"])
    contract_codes.discard(0)  # 0 = 成功信封，不是错误码
    assert contract_codes == set(ERROR_CODES)


# ── 视图面的字段名（camelCase 契约）───────────────────────────────────────────


def test_discovery_channel_view_serializes_camel_case_keys() -> None:
    view = DiscoveryChannelView(
        name=ChannelName.RSS,
        description="d",
        implemented=True,
        enabled=False,
        available=False,
        reason="未启用",
    )
    dumped = set(view.model_dump(by_alias=True))
    assert {"contractVerifiedAt", "verifiedScope", "lastSuccessAt", "lastError"} <= dumped
    assert "contract_verified_at" not in dumped


def test_registry_channel_view_field_names_are_subset_of_contract() -> None:
    """后台真实输出的字段必须都在契约里（新增字段先改契约，不能反过来）。"""
    generated_props = set(load_cached(GENERATED_PATH)["$defs"]["DiscoveryChannelView"]["properties"])
    real_rows = {
        "name",
        "description",
        "implemented",
        "enabled",
        "available",
        "reason",
        "contractVerifiedAt",
        "verifiedScope",
    }
    assert real_rows <= generated_props, f"契约缺字段：{sorted(real_rows - generated_props)}"


# ── 正则自证的补充：确认 patterns 与生成物一致 ────────────────────────────────


def test_generated_article_key_pattern_is_the_registered_alternation() -> None:
    node = load_cached(GENERATED_PATH)["$defs"]["ArticleManifest"]["properties"]["article_key"]
    pattern = node["pattern"]
    assert pattern.startswith("^(?:") and pattern.endswith(")$"), f"不是一条带锚 alternation：{pattern}"
    assert re.match(pattern, "s:abcDEF12")
    draft = load_cached(FROZEN_PATH)["$defs"]["ArticleKey"]
    branch_patterns = [b["pattern"] for b in draft["oneOf"]]
    assert len(branch_patterns) == 3
    for branch in branch_patterns:
        assert re.match(branch, "b:MzI4NjA5NTU4Mg:2650635316:1") or re.match(branch, "s:abcDEF12") or re.match(
            branch, "h:0123456789abcdef0123456789abcdef"
        ), f"分支 {branch} 没有任何见证串能过"


def test_collection_event_import_shape() -> None:
    """CollectionEvent 的 `at` 也是 tightening（登记表里单独一条），这里钉住行为。"""
    with pytest.raises(ValidationError):
        CollectionEvent.model_validate(
            {"event": "discovery.failed", "source_id": "s1", "channel": "rss", "at": "2024-01-01"}
        )
