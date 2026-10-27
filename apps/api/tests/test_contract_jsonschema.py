"""STEP-01 S1.3.2 第五轮 / D-V8-05（签 A）：契约语义的真源交给标准库 `jsonschema`（Draft 2020-12）。

为什么另起一个文件：`test_collection_contract.py` 的自研比对器九轮被打穿，击穿点每次都是
"判据绑在我自己的实现上"（没实现的关键词、没登记的叶子事实、不相干的台账引用）。D-V8-05 的选择是
**不再自己实现关键词语义**：两份 schema 接受的实例集合是否相同，由标准库 validator 逐条实例判；
自研比对器退役为"差异登记 + 覆盖率守卫"，它原有的用例保留，但"语义对不对"不再由它说了算。

三层，每层都有反证：
1. **元校验**：每份冻结稿与生成物都必须是合法的 Draft 2020-12 schema（`check_schema`）。
2. **探针等价**：同名形状（稿 `definitions` ↔ 产物 `$defs`，以及 `api.envelope` 的根）在同一批探针实例上
   必须给出相同的接受/拒绝结论。探针 = 两侧出现的枚举值、边界长度与边界数值、模式语料、常见类型的代表值，
   再加上**从两侧各自合成的合法对象**及其"缺一个必填 / 多一个键 / 换一个字段值"的变体。
   判定只有 validator 一家，我只负责造实例。
3. **登记兜底**：结论不一致的形状必须在本域 `CONTRACT_DIVERGENCES` 里有 `tightening` 或 `conflict`
   登记；只有"接受集不变"那四种登记的——登记说没变、validator 说变了，以 validator 为准、红。
4. **名字集差集**（STEP-56 S56.3）：两侧 def 的名字集要么相等，要么每个差集都指得出一条既有登记；
   反向还有一条——探针列表必须等于那个交集、且装饰器吃下去的就是这一串。交集比对不再自己决定
   "谁不参与判定"，也不再由 `_shape_pairs()` 单方面决定"谁被探针判"。

探针是有限集，所以这一层仍是**下界**：它保证"能被这些实例分辨的差异一定被看见"，
不保证无穷接受集逐点相等。正则量词与字符类那一类差异仍由旧文件的"pattern 逐字符相等"守着。
"""
from __future__ import annotations

import copy
import itertools
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from test_collection_contract import ALIAS_WITNESSES, _not_a_shape_names, _referenced_by

from app.contracts import collection as collection_contract
from app.contracts import engine as engine_contract
from app.contracts import envelope as envelope_contract
from app.contracts import events as events_contract
from app.contracts import identity as identity_contract
from app.contracts import resources as resources_contract
from app.contracts import shapes as shapes_contract

REPO_ROOT = Path(__file__).resolve().parents[3]
DRAFT_DIR = REPO_ROOT / "docs" / "任务规划V0.12.0" / "contracts"
SCHEMA_DIR = REPO_ROOT / "packages" / "contracts" / "schemas"

DOMAINS: dict[str, tuple[str, Any]] = {
    "collection": ("collection.schema.json", collection_contract.CONTRACT_DIVERGENCES),
    "identity": ("identity.schema.json", identity_contract.CONTRACT_DIVERGENCES),
    "events": ("events.schema.json", events_contract.CONTRACT_DIVERGENCES),
    "resources": ("resources.schema.json", resources_contract.CONTRACT_DIVERGENCES),
    "api.envelope": ("api.envelope.schema.json", envelope_contract.CONTRACT_DIVERGENCES),
    "engine": ("engine.schema.json", engine_contract.CONTRACT_DIVERGENCES),
    "shapes": ("shapes.schema.json", shapes_contract.CONTRACT_DIVERGENCES),
}

#: `Divergence` 文档里"接受集不变"的四种登记（structural / serialization / strictness / documentation）。
#: 只靠这几种登记的形状如果被 validator 判出不同结论 ⇒ 登记本身是假的。会改变接受集的只有
#: `tightening`（模型更严）与 `conflict`（两侧不可判宽严、引台账裁决）。
SAME_ACCEPTANCE_KINDS = frozenset({"structural", "serialization", "strictness", "documentation"})

_FORMAT = FormatChecker()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _draft(domain: str) -> dict[str, Any]:
    return _load(DRAFT_DIR / DOMAINS[domain][0])


def _generated(domain: str) -> dict[str, Any]:
    return _load(SCHEMA_DIR / f"{domain}.schema.json")


def _defs_key(doc: dict[str, Any]) -> str:
    return "$defs" if "$defs" in doc else "definitions"


def _defs(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get(_defs_key(doc), {}) or {}


def _validator(doc: dict[str, Any], node: dict[str, Any] | None = None) -> Draft202012Validator:
    """对 `node`（默认：文档根）建 validator，并把本文档的定义表带上，让 `#/definitions/X` 能解析。"""
    key = _defs_key(doc)
    if node is None:
        schema = doc
    else:
        schema = {**node, key: _defs(doc)}
        if "$id" in doc:
            schema["$id"] = doc["$id"]
    return Draft202012Validator(schema, format_checker=_FORMAT)


def _root(doc: dict[str, Any]) -> dict[str, Any]:
    """文档根上的形状（去掉定义表本身）。"""
    return {k: v for k, v in doc.items() if k not in ("$defs", "definitions")}


def _def_validator(doc: dict[str, Any], name: str) -> Draft202012Validator:
    key = _defs_key(doc)
    return _validator(doc, {"$ref": f"#/{key}/{name}"})


# ── 1. 元校验 ────────────────────────────────────────────────────────────────

ALL_DOCS = sorted(
    [p for p in DRAFT_DIR.glob("*.json") if "$schema" in p.read_text(encoding="utf-8")]
    + list(SCHEMA_DIR.glob("*.schema.json"))
)


@pytest.mark.parametrize("path", ALL_DOCS, ids=[p.parent.name + "/" + p.name for p in ALL_DOCS])
def test_every_schema_document_is_valid_draft_2020_12(path: Path) -> None:
    Draft202012Validator.check_schema(_load(path))


def test_meta_validation_has_teeth() -> None:
    """反证：`maxLength` 写成字符串必须被元校验拒绝——否则第 1 层是装饰。"""
    with pytest.raises(SchemaError):
        Draft202012Validator.check_schema({"type": "string", "maxLength": "512"})


def test_every_domain_has_a_generated_counterpart() -> None:
    """域稿 ↔ 产物一一对应（`api.envelope` 是 S1.2.2 最后收编的一域，`engine` 由 STEP-13 新冻结）。"""
    assert {p.name for p in SCHEMA_DIR.glob("*.schema.json")} == {f"{d}.schema.json" for d in DOMAINS}


# ── 2. 探针 ──────────────────────────────────────────────────────────────────

_BASE_PROBES: tuple[Any, ...] = (
    None, True, False, 0, 1, -1, 2, 1.5, "", "x", "ok", [], [1], ["x"], {}, {"k": 1},
    "2026-10-20T10:00:00+08:00", "2026-10-20T10:00:00", "not-a-date",
    "https://example.com/a", "not a uri",
    "0f8fad5b-d9cb-469f-a165-70867728950e", "0F8FAD5B-D9CB-469F-A165-70867728950E",
    "b:MzI4NjA5NTU4Mg:2650635316:1", "b:MzI4NjA5NTU4Mg:2650635316:123", "b:short:1:1",
    "s:abcDEF12", "s:tooShort", "s:" + "a" * 64, "s:" + "a" * 65,
    "h:0123456789abcdef0123456789abcdef", "h:0123456789abcdef0123456789abcde",
)


def _walk(node: Any) -> Any:
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _probe_pool(*docs: dict[str, Any]) -> list[Any]:
    pool: list[Any] = list(_BASE_PROBES)
    for doc in docs:
        for node in _walk(doc):
            for value in node.get("enum", []) if isinstance(node.get("enum"), list) else []:
                pool.append(value)
            if "const" in node:
                pool.append(node["const"])
            for key in ("minLength", "maxLength"):
                n = node.get(key)
                if isinstance(n, int):
                    pool += ["a" * max(n - 1, 0), "a" * n, "a" * (n + 1)]
            for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
                n = node.get(key)
                if isinstance(n, int | float) and not isinstance(n, bool):
                    pool += [n - 1, n, n + 1]
    out: list[Any] = []
    seen: set[str] = set()
    for value in pool:
        tag = json.dumps(value, sort_keys=True)
        if tag not in seen:
            seen.add(tag)
            out.append(value)
    return out


def _synthesize(doc: dict[str, Any], node: dict[str, Any], pool: list[Any], depth: int = 0) -> Any:
    """按 `node` 从探针池里挑（或递归拼）一个它接受的实例；挑不到返回 `_NOTHING`。"""
    if depth > 6:
        return _NOTHING
    v = _validator(doc, node)
    if "$ref" in node:
        ref = node["$ref"].split("/")[-1]
        target = _defs(doc).get(ref)
        if isinstance(target, dict):
            got = _synthesize(doc, target, pool, depth + 1)
            if got is not _NOTHING and v.is_valid(got):
                return got
    for branch_key in ("anyOf", "oneOf", "allOf"):
        for branch in node.get(branch_key, []) or []:
            got = _synthesize(doc, {**branch}, pool, depth + 1)
            if got is not _NOTHING and v.is_valid(got):
                return got
    if node.get("type") == "object" or "properties" in node:
        obj: dict[str, Any] = {}
        props = node.get("properties", {}) or {}
        for name in node.get("required", []) or []:
            sub = props.get(name, {})
            got = _synthesize(doc, sub if isinstance(sub, dict) else {}, pool, depth + 1)
            if got is _NOTHING:
                return _NOTHING
            obj[name] = got
        if v.is_valid(obj):
            return obj
    if node.get("type") == "array":
        items = node.get("items", {})
        got = _synthesize(doc, items if isinstance(items, dict) else {}, pool, depth + 1)
        for candidate in ([got] if got is not _NOTHING else []) + [[]]:
            if v.is_valid(candidate):
                return candidate
    for value in pool:
        if v.is_valid(value):
            return value
    return _NOTHING


class _Nothing:
    pass


_NOTHING: Any = _Nothing()


def _object_variants(seed: Any, node_a: dict[str, Any], node_b: dict[str, Any], pool: list[Any]) -> list[Any]:
    """合法对象的邻居：缺一个必填、多一个未知键、每个已知字段换成池里每个值（池截断控制规模）。"""
    if not isinstance(seed, dict):
        return []
    out: list[Any] = [seed]
    names = set(seed) | set(node_a.get("properties") or {}) | set(node_b.get("properties") or {})
    for name in sorted(names):
        if name in seed:
            out.append({k: v for k, v in seed.items() if k != name})
        for value in pool[:60]:
            out.append({**seed, name: value})
    out.append({**seed, "__unknown_key__": 1})
    return out


def _resolved(doc: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in node:
        target = _defs(doc).get(node["$ref"].split("/")[-1])
        if isinstance(target, dict):
            return target
    return node


def _disagreements(
    doc_a: dict[str, Any], node_a: dict[str, Any], doc_b: dict[str, Any], node_b: dict[str, Any]
) -> list[tuple[Any, bool, bool]]:
    pool = _probe_pool(doc_a, doc_b)
    va, vb = _validator(doc_a, node_a), _validator(doc_b, node_b)
    probes: list[Any] = list(pool)
    for doc, node in ((doc_a, node_a), (doc_b, node_b)):
        seed = _synthesize(doc, node, pool)
        if seed is not _NOTHING:
            probes += _object_variants(seed, _resolved(doc_a, node_a), _resolved(doc_b, node_b), pool)
    out: list[tuple[Any, bool, bool]] = []
    seen: set[str] = set()
    for probe in probes:
        tag = json.dumps(probe, sort_keys=True, ensure_ascii=False)
        if tag in seen:
            continue
        seen.add(tag)
        a, b = va.is_valid(probe), vb.is_valid(probe)
        if a != b:
            out.append((probe, a, b))
    return out


def _shape_pairs() -> list[tuple[str, str]]:
    """要逐对探针比对的 `(域, def 名)`——只取两侧都有的名字。

    STEP-56 S56.3：交集本身不再是判据。"某一侧没有这个名字"过去等于"整条静默跳过"，
    现在由下面 `test_def_name_sets_are_equal_or_every_drop_is_accounted` 逐名要落点，
    `test_probe_parametrization_covers_every_pair` 反向要探针——两侧都差一个名都会红，
    只是红在那两条门上而不是在这里。
    """
    pairs: list[tuple[str, str]] = []
    for domain in DOMAINS:
        draft, gen = _draft(domain), _generated(domain)
        for name in sorted(set(_defs(draft)) & set(_defs(gen))):
            pairs.append((domain, name))
        if "properties" in draft and "properties" in gen:
            pairs.append((domain, "<root>"))
    return pairs


SHAPE_PAIRS = _shape_pairs()


# ── S56.3：名字集的差集必须逐个指得出既有登记 ───────────────────────────────────

#: 稿侧独有 def 的三种既有正当去处（读的是 `test_collection_contract.py` 里同一批判据源，
#: 这里不再抄一份名字表——抄了就等于造第二个真源，迟早漂）：
#: ①稿根层 `x-not-in-single-source` 声明它不是形状；②它被某个已收编 def 在形状位 `$ref` 引走
#: （约束在产物里现形）；③它在 `ALIAS_WITNESSES` 里点名了可执行见证测试。
#: 三条都不成立 ⇒ 这个 def 从产物里无声消失，就是 P-126 那一类"覆盖面靠登记表点名"的病。


def _name_problems_for(domain: str, draft: dict[str, Any], gen: dict[str, Any]) -> list[str]:
    dnames, gnames = set(_defs(draft)), set(_defs(gen))
    ddefs = _defs(draft)
    problems: list[str] = []
    for name in sorted(gnames - dnames):
        problems.append(f"{domain}/{name}: 生成物多出一个稿里没有的 def（交集比对会把它整条跳过 ⇒ 没人判它）")
    for name in sorted(dnames - gnames):
        if name in _not_a_shape_names(draft)[0]:
            continue
        if any(_referenced_by(ddefs[k], name) for k in dnames & gnames):
            continue
        if name in ALIAS_WITNESSES.get(domain, {}):
            continue
        problems.append(
            f"{domain}/{name}: 稿里有而生成物没有，且「稿声明非形状 / 被已收编 def 引用 / 点名见证测试」"
            "三条既有去处都不成立 ⇒ 缺席无据"
        )
    return problems


def _live_name_problems() -> list[str]:
    return [p for domain in DOMAINS for p in _name_problems_for(domain, _draft(domain), _generated(domain))]


def test_def_name_sets_are_equal_or_every_drop_is_accounted() -> None:
    """两侧 def 的名字集要么相等，要么每个差集都指得出一条既有登记（P-126 的覆盖面口径补全）。"""
    problems = _live_name_problems()
    assert not problems, "契约名字集有无人负责的差集：\n  " + "\n  ".join(problems)


def test_probe_parametrization_covers_every_pair() -> None:
    """探针列表要等于"两侧名字集的交"，而且装饰器吃下去的必须是同一串。

    这条判的东西与上面那条不同，所以不是重复：`test_def_name_sets_are_equal_or_every_drop_is_accounted`
    只看稿与产物两份 JSON，永远不看 `SHAPE_PAIRS` 怎么被构造出来的。今天 `_shape_pairs()` 就是逐域取交集，
    于是这条按构造成立；它会红的情形是**将来有人在取列表那一步加了筛选或切片**（"这个 def 太难合成先跳过"
    就是这么进来的），或者把装饰器的实参换成另一张表——那两种写法都不会让名字集门红，只会让探针静默少判。
    """
    for domain in DOMAINS:
        draft, gen = _draft(domain), _generated(domain)
        listed = {name for d, name in SHAPE_PAIRS if d == domain and name != "<root>"}
        intersect = set(_defs(draft)) & set(_defs(gen))
        assert listed == intersect, f"{domain} 探针列表与两侧名字集的交不一致：少 {sorted(intersect - listed)}"
    mark = next(m for m in test_draft_and_generated_agree_on_every_probe.pytestmark if m.name == "parametrize")
    assert list(mark.args[1]) == SHAPE_PAIRS, "装饰器吃下去的不是 SHAPE_PAIRS 这一串 ⇒ 探针列表改了地方"


def test_name_set_gate_has_teeth_gen_only_name() -> None:
    """反证一：产物凭空多一个 def ⇒ 红（今天的交集对这个是完全静默的）。"""
    gen = copy.deepcopy(_generated("engine"))
    gen["$defs"]["S56Ghost"] = {"type": "string"}
    problems = _name_problems_for("engine", _draft("engine"), gen)
    assert any("S56Ghost" in p and "多出一个" in p for p in problems), problems


def test_name_set_gate_has_teeth_unaccounted_drop() -> None:
    """反证二：稿里一个 def 没进产物、也没走那三条去处 ⇒ 红（交集同样静默）。"""
    draft = copy.deepcopy(_draft("engine"))
    draft.setdefault("$defs", {})["S56Dropped"] = {"type": "string", "maxLength": 9}
    problems = _name_problems_for("engine", draft, _generated("engine"))
    assert any("S56Dropped" in p and "缺席无据" in p for p in problems), problems


def test_name_set_gate_has_teeth_a_stripped_claim_reddens() -> None:
    """反证三：把 events 稿根层的 `x-not-in-single-source` 里 `QueueMechanism` 那条摘掉 ⇒ 红。

    这一条证明放行不是写死的名字：三条去处**摘掉**立刻变成"缺席无据"，
    同时也证明 `test_def_name_sets_are_equal_or_every_drop_is_accounted` 现在读绿不是因为
    它从不调用——`QueueMechanism` 走的就是①。
    """
    draft = copy.deepcopy(_draft("events"))
    assert not _name_problems_for("events", draft, _generated("events"))
    draft.get("x-not-in-single-source", {}).pop("QueueMechanism", None)
    problems = _name_problems_for("events", draft, _generated("events"))
    assert any("QueueMechanism" in p and "缺席无据" in p for p in problems), problems


def _refs_of(ref: str) -> set[str]:
    """登记的 `ref` 可能一次点名多个形状（`"ContentAsset / ShortLinkMap"`），或以 `*` 打头的全域通配。"""
    return {part.strip() for part in ref.split("/")}


def _registered_kinds(domain: str, name: str) -> set[str]:
    kinds = set()
    for d in DOMAINS[domain][1]:
        refs = _refs_of(d.ref)
        if name in refs or any(r.startswith("*") for r in refs):
            kinds.add(d.kind)
    return kinds


@pytest.mark.parametrize(("domain", "name"), SHAPE_PAIRS, ids=[f"{d}:{n}" for d, n in SHAPE_PAIRS])
def test_draft_and_generated_agree_on_every_probe(domain: str, name: str) -> None:
    """第 2+3 层：同名形状在探针上结论一致；不一致必须有"会改变接受集"的登记。"""
    draft, gen = _draft(domain), _generated(domain)
    if name == "<root>":
        diff = _disagreements(draft, {k: v for k, v in draft.items() if k not in ("$defs", "definitions")},
                              gen, {k: v for k, v in gen.items() if k not in ("$defs", "definitions")})
        kinds = _registered_kinds(domain, envelope_contract.__contract_root__ if domain == "api.envelope" else name)
    else:
        diff = _disagreements(draft, {"$ref": f"#/{_defs_key(draft)}/{name}"}, gen, {"$ref": f"#/$defs/{name}"})
        kinds = _registered_kinds(domain, name)
    if not diff:
        return
    sample = "; ".join(f"{json.dumps(p, ensure_ascii=False)[:90]} 稿={a} 产物={b}" for p, a, b in diff[:4])
    changing = kinds - SAME_ACCEPTANCE_KINDS
    assert changing, (
        f"{domain}:{name} 稿与产物接受集不同（{len(diff)} 条探针），而登记种类={sorted(kinds) or '无'}"
        f"（只有 tightening / conflict 才允许接受集不同）。样例：{sample}"
    )


def test_probe_equivalence_has_teeth() -> None:
    """反证：把产物根 `message.maxLength` 从 512 改成 511 ⇒ 探针必须分辨出来。"""
    gen = _generated("api.envelope")
    mutated = copy.deepcopy(gen)
    mutated["properties"]["message"]["maxLength"] = 511
    node = _root(gen)
    assert not _disagreements(gen, node, gen, node), "同一份 schema 自比必须零差异"
    diff = _disagreements(gen, node, mutated, _root(mutated))
    assert any(isinstance(p, dict) and p.get("message") == "a" * 512 for p, _, _ in diff), diff[:3]


def test_probe_equivalence_catches_a_dropped_required_field() -> None:
    """反证二：产物把 `requestId` 从 required 里删掉 ⇒ "缺 requestId" 的变体必须分辨出来。"""
    gen = _generated("api.envelope")
    mutated = copy.deepcopy(gen)
    mutated["required"] = [r for r in mutated["required"] if r != "requestId"]
    diff = _disagreements(gen, _root(gen), mutated, _root(mutated))
    assert any(isinstance(p, dict) and "requestId" not in p and "code" in p for p, _, _ in diff), diff[:3]


def test_every_shape_pair_synthesizes_a_valid_instance() -> None:
    """覆盖率守卫：每对形状至少一侧要能合成合法实例——合成不出来，变体层就空转，等价只剩标量探针。"""
    starved = []
    for domain, name in SHAPE_PAIRS:
        draft, gen = _draft(domain), _generated(domain)
        if name == "<root>":
            nodes = [(draft, {k: v for k, v in draft.items() if k != "definitions"}),
                     (gen, {k: v for k, v in gen.items() if k != "$defs"})]
        else:
            nodes = [(draft, {"$ref": f"#/{_defs_key(draft)}/{name}"}), (gen, {"$ref": f"#/$defs/{name}"})]
        pool = _probe_pool(draft, gen)
        if all(_synthesize(d, n, pool) is _NOTHING for d, n in nodes):
            starved.append(f"{domain}:{name}")
    assert not starved, f"这些形状两侧都合成不出合法实例：{starved}"


# ── 4. 运行时信封 ⊆ 契约：`core/response.py` 产出的每个信封都必须被产物根接受 ───────────


def test_runtime_envelopes_satisfy_the_generated_root() -> None:
    from app.core.response import failure, success

    root = _validator(_generated("api.envelope"))
    for env in (success(), success({"items": []}), success([1, 2]), failure(30004, "资源不存在")):
        body = env.model_dump()
        errors = [e.message for e in root.iter_errors(body)]
        assert not errors, (body, errors)


def test_pagination_shells_are_distinct_contracts() -> None:
    """三个分页壳两两接受集不同（它们是三份合同，不是一份的三个别名）。"""
    gen = _generated("api.envelope")
    names = ("PageStyleA", "PageStyleB", "PageTargetUnified")
    for a, b in itertools.combinations(names, 2):
        assert _disagreements(gen, {"$ref": f"#/$defs/{a}"}, gen, {"$ref": f"#/$defs/{b}"}), (a, b)
