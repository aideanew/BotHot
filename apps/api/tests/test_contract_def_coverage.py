"""STEP-56 S56.1（V0.21.0，D-V21-16，闭合 P-126）：契约 def 的**覆盖面孤儿判据**。

P-126 的死角：真端点反向核只逐条判 `MOCK_ROUTE_CONTRACTS` 里登记过的那些名字。一个既没登记、
也没被任何"被核过的 def"用 `$ref` 引到的 def，会照样进 `dto.ts`，而覆盖面门、探针门、
运行时形状门当时都读不到它——引擎域连同类守卫都没有。本文件把判据从"登记表点到的那些"
换成"整棵 def 树"：种子从两个测试模块**现读**（不手抄名字表），沿 `$ref` 求可达闭包，
要求 `全部 def − 可达集 == ∅`，红时打印孤儿名。

种子按**调用点**取，不按整篇正则：删掉一条反向核用例，它的种子跟着消失，那个 def 立刻成孤儿。
"覆盖被人删了"必须是判据能看见的事，而不只是"名字写错"看得见。

只读源码与生成好的 JSON，不连库（卡面字段 10：`SKIP_BASELINE_WIN` 不动）。
"""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = REPO_ROOT / "packages" / "contracts" / "schemas"
TEST_DIR = REPO_ROOT / "apps" / "api" / "tests"
SHAPES_TEST = TEST_DIR / "test_shapes_response_contract.py"
ENGINE_TEST = TEST_DIR / "test_engine_response_contract.py"
SHAPES_SRC = SHAPES_TEST.read_text("utf-8")
ENGINE_SRC = ENGINE_TEST.read_text("utf-8")

#: 域 → 生成好的 schema 文档。两域同一条判据，引擎域不再例外。
DOCS: dict[str, dict[str, Any]] = {
    "shapes": json.loads((SCHEMA_DIR / "shapes.schema.json").read_text("utf-8")),
    "engine": json.loads((SCHEMA_DIR / "engine.schema.json").read_text("utf-8")),
}

#: `$ref` 的走法：注释键与"装数据而不是装形状"的键不进，其余键一律下钻。
#: 本项目把散文写在 `x-*` 里（`x-retry-policy` 里就有 `maxRetries` 这种键名），而 validator 从不求值
#: 那些子树：往 `x-note` 里塞一条 `$ref` 就能替一个 def 买到"有人核过它"的假象——这正是
#: `test_collection_contract.py` 的 `_referenced_by` 当年被 G3 打穿后收紧的那一刀。
#: `enum`/`const`/`default`/`examples`/`required` 带的是**实例数据**，里面的字符串长得像 `$ref`
#: 也不算引用；`dependencies`/`propertyNames` 这类不同——它们的值是子 schema，validator 会求值，
#: 所以留在下钻面里。刻意不做"只放形状键"的白名单：产物将来换一个容器键（`not`/`contains`…）
#: 就会让真引用被漏掉、把一个本有人核的 def 读成孤儿——那种假红比多下钻一层更难查。
_DATA_KEYS = frozenset({"enum", "const", "default", "examples", "required"})

#: 现读的真实 def 名，只用来在反证里挑"顶层响应"与"只被引用的下游"两个样本，不构成名字表真源。
_ROOT_SEED = "MeView"  # 没有入边：只能靠种子活着
_LEAF_SEED = "MeUser"  # 只被 MeView 引用：种子或上游任一断掉就成孤儿


def _ref_target(value: str) -> str:
    """`#/$defs/Foo` / `#/definitions/Foo` ⇒ `Foo`；别的形制原样返回（交给"本域不存在"那条判定）。"""
    return value.rsplit("/", 1)[-1]


def _ref_names(node: Any) -> set[str]:
    """一个 def 里 validator 会求值的那些 `$ref` 目标名（递归；注释键与数据键的子树不进）。"""
    out: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                out.add(_ref_target(value))
            elif key.startswith("x-") or key in _DATA_KEYS:
                continue
            else:
                out |= _ref_names(value)
    elif isinstance(node, list):
        for value in node:
            out |= _ref_names(value)
    return out


def _test_funcs(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test_")
    ]


def _shapes_seeds(src: str) -> set[str]:
    """shapes 域种子：任一 `test_*` 里 `_check("<契约名>", <响应值>)` 的第一个字面量实参。

    第二个实参也要看：它写成容器字面量（`{...}` / `[...]` / `set(...)` 这类）就说明这条 `_check`
    判的是合成对象而不是真端点响应，那样的"覆盖"是测试自己造的，不算覆盖面。
    """
    seeds: set[str] = set()
    for fn in _test_funcs(ast.parse(src)):
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "_check" or len(node.args) < 2:
                continue
            first, second = node.args[0], node.args[1]
            if isinstance(second, ast.Dict | ast.List | ast.Set | ast.Tuple):
                continue
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                seeds.add(first.value)
    return seeds


def _dict_ref_pairs(node: ast.AST) -> set[str]:
    """在一个赋值里找出 `{"$ref": "#/$defs/<名>"}` 的目标名。

    刻意不用正则在 `ast.unparse` 的文本上扫：那条口径只认 `#/$defs/` 前缀、且被字符类截断，
    而产物侧取 `$ref` 走的是 `rsplit("/")`——两套取名规则迟早对同一个 def 给出不同答案。
    ast 没有父键指针，所以自己按 Dict 的键值配对走一遍。
    """
    out: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Dict):
            continue
        for key, value in zip(child.keys, child.values, strict=True):  # Dict.keys[i] 与 values[i] 恒等长
            if isinstance(key, ast.Constant) and key.value == "$ref" and isinstance(value, ast.Constant):
                if isinstance(value.value, str):
                    out.add(_ref_target(value.value))
    return out


def _engine_seeds(src: str) -> set[str]:
    """engine 域种子：**连库真端点**用例用到的 validator 变量所绑定的 def 名。

    这个文件的 def 名绑在模块常量上（`_LIST = Draft202012Validator({**SCHEMA, "$ref":
    "#/$defs/EngineList"})`），用例里只出现变量名，所以"这条名字被哪条真端点判过"必须按 ast 从
    常量绑定与用例体两处对起来才知道。两条不连库的"契约有牙齿"用例同样引用这两个变量，
    但它们打的是合成字面量、不是真端点响应，**不算覆盖**——否则删掉两条反向核用例还剩牙齿用例顶着，
    判据就看不见"覆盖被删"。
    """
    tree = ast.parse(src)
    bound: dict[str, set[str]] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name):
            names = _dict_ref_pairs(stmt.value)
            if names:
                bound[stmt.targets[0].id] = names
    seeds: set[str] = set()
    for fn in _test_funcs(tree):
        # 形参只看 args 一种不够——夹具将来换成 keyword-only 也要认得出"这是一条真端点用例"
        if not any(a.arg == "db_session" for a in (*fn.args.args, *fn.args.posonlyargs, *fn.args.kwonlyargs)):
            continue
        for expr in ast.walk(fn):
            # 只认"拿这个 validator 去判一份 data"的调用点：一条 `del _LIST` 或把常量抄进别处
            # 都不算覆盖，否则删掉断言、留着引用也读绿
            if not isinstance(expr, ast.Call) or not isinstance(expr.func, ast.Name) or expr.func.id != "_errors":
                continue
            for arg in expr.args:
                if isinstance(arg, ast.Name) and arg.id in bound:
                    seeds |= bound[arg.id]
    return seeds


def _seed_names(shapes_src: str, engine_src: str) -> dict[str, set[str]]:
    return {"shapes": _shapes_seeds(shapes_src), "engine": _engine_seeds(engine_src)}


def _orphan_report(docs: dict[str, dict[str, Any]], seeds: dict[str, set[str]]) -> list[str]:
    """列出"这个 def 没有任何真端点反向核、也不被任何可达 def 引用"，连带三类相邻的静默面。

    四类写进同一份清单，因为四类都能让某条判据静默：
    ① 孤儿 def——P-126 的正身；
    ② `$ref` 指向本域不存在的 def——可达性若沿着坏边继续算，等于给下游发了假通行证；
    ③ `$ref` 指向另一个域的 def——真端点用 `{**SHAPES, "$ref": …}` 建 validator，跨域引用会在
       `_check` 当场抛（error，不是 fail），很容易被当成环境问题放过去；
    ④ 种子名在 schema 里根本不存在——测试自己写错了名字，同一份清单里立刻可见，而不是悄悄少一个种子。
    """
    problems: set[str] = set()
    for domain, doc in docs.items():
        defs: dict[str, Any] = doc.get("$defs", {})
        unknown = sorted(n for n in seeds.get(domain, set()) if n not in defs)
        if unknown:
            problems.add(f"{domain}: 种子名不在本域 $defs 里（测试里的名字与产物对不上）：{unknown}")
        reachable: set[str] = {n for n in seeds.get(domain, set()) if n in defs}
        frontier = sorted(reachable)
        while frontier:
            current = frontier.pop()
            for target in sorted(_ref_names(defs[current])):
                if target in defs and target not in reachable:
                    reachable.add(target)
                    frontier.append(target)
        # 坏边要扫**每一个** def，不能只扫可达的：孤儿 def 上挂着一条指错地方的 `$ref`，
        # 若只走可达集，它就只剩"孤儿"这一句，坏边要等有人把它接上可达链才露出来。
        for name in sorted(defs):
            for target in sorted(_ref_names(defs[name])):
                if target in defs:
                    continue
                elsewhere = sorted(d for d in docs if d != domain and target in docs[d].get("$defs", {}))
                suffix = f"（{elsewhere} 域里有同名 def ⇒ 跨域引用，validator 解析不到）" if elsewhere else ""
                problems.add(f"{domain}/{name}: $ref 指向本域不存在的 def {target}{suffix}")
        for orphan in sorted(set(defs) - reachable):
            blocked = sorted(n for n in defs if orphan in _ref_names(defs[n]) and n not in reachable)
            tail = f"（引用它的 {blocked} 自己也不可达）" if blocked else ""
            problems.add(f"{domain}/{orphan}: 没有任何真端点反向核，也不被可达 def 引用{tail}")
    return sorted(problems)


def _live_report() -> list[str]:
    return _orphan_report(DOCS, _seed_names(SHAPES_SRC, ENGINE_SRC))


# ── 1. 正面读数：整棵 def 树没有孤儿 ────────────────────────────────────────────


def test_no_contract_def_is_an_orphan() -> None:
    problems = _live_report()
    counts = " + ".join(f"{d} {len(doc.get('$defs', {}))} 个 def" for d, doc in DOCS.items())
    assert not problems, f"契约覆盖面有洞（{counts}，全部要有落点）：\n  " + "\n  ".join(problems)


def test_both_domains_contribute_seeds() -> None:
    """某一域种子为空 ⇒ 可达集退化，`test_no_contract_def_is_an_orphan` 就只在一个域里判。

    这一条把"某一域整片失去覆盖"与"某条用例被删"分开报，读数更可归因；也防抽取器与被测代码
    脱钩后（改名、换形制）自己变成一条空转的门。
    """
    seeds = _seed_names(SHAPES_SRC, ENGINE_SRC)
    assert seeds["shapes"], "shapes 域一条 `_check(...)` 都没读到 ⇒ 种子抽取已与被测代码脱钩"
    assert seeds["engine"], "engine 域没有任何连库真端点绑定到 def ⇒ 引擎覆盖整片消失"


# ── 2. 反证：四类会让判据静默的写法，各自要证明会红 ─────────────────────────────


def test_teeth_orphan_def_is_reported() -> None:
    """往 $defs 里塞一个没人引用的 def ⇒ 它自己进孤儿清单（卡面验收①的机械版）。"""
    docs = copy.deepcopy(DOCS)
    docs["shapes"]["$defs"]["S56OrphanProbe"] = {"type": "object", "properties": {}, "additionalProperties": False}
    report = _orphan_report(docs, _seed_names(SHAPES_SRC, ENGINE_SRC))
    assert any("shapes/S56OrphanProbe" in line for line in report), report


def test_teeth_deleting_a_live_check_reaches_the_orphans() -> None:
    """把真端点反向核的调用点摘掉（改名，不删文件）⇒ 它核过的 def 立刻成孤儿。

    钉的是 P-126 的正身：覆盖面门只跟着 `MOCK_ROUTE_CONTRACTS` 走，删一条用例它读绿；
    这里种子取自调用点，删一条就少一个种子。
    """
    src = SHAPES_SRC.replace(f'_check("{_ROOT_SEED}"', f'_retired("{_ROOT_SEED}"')
    seeds = _seed_names(src, ENGINE_SRC)
    assert _ROOT_SEED not in seeds["shapes"], "摘调用点没摘干净，反证不算跑过"
    report = _orphan_report(DOCS, seeds)
    assert any(line.startswith(f"shapes/{_ROOT_SEED}:") for line in report), report


def test_teeth_losing_the_upstream_takes_the_leaf_with_it() -> None:
    """上游断供 ⇒ 只靠 `$ref` 活着的下游 def 一起成孤儿（引用链不是第二张通行证）。"""
    src = SHAPES_SRC.replace(f'_check("{_ROOT_SEED}"', f'_retired("{_ROOT_SEED}"')
    report = _orphan_report(DOCS, _seed_names(src, ENGINE_SRC))
    assert any(line.startswith(f"shapes/{_LEAF_SEED}:") for line in report), report


def test_teeth_synthetic_object_is_not_coverage() -> None:
    """`_check("<名>", {…})` 判的是合成对象而不是真端点响应 ⇒ 不给它记覆盖面。

    锚点用 `LogoutResult` 的调用点（`test_shapes_response_contract.py:340`，全文件只出现一次）：
    实参换成空字典后，这个名字应当从种子里消失并出现在孤儿清单里。
    """
    src = SHAPES_SRC.replace('_check("LogoutResult", out.json()["data"])', '_check("LogoutResult", {})')
    assert src != SHAPES_SRC, "锚点没打上，这条反证不算跑过"
    seeds = _seed_names(src, ENGINE_SRC)
    assert "LogoutResult" not in seeds["shapes"], "把响应换成合成对象应当不再算覆盖"
    report = _orphan_report(DOCS, seeds)
    assert any(line.startswith("shapes/LogoutResult:") for line in report), report


def test_teeth_keeping_the_reference_is_not_coverage() -> None:
    """把真端点用例里的 validator 换掉、但**留着对常量的引用** ⇒ 不再算覆盖。

    这一条钉的是种子抽取"认调用点而不是认引用"的那一半：只按"函数体里出现过 `_LIST`"取种子的话，
    删掉断言、留一句 `del _LIST` 或把常量抄进别处也照样读绿。
    """
    src = ENGINE_SRC.replace("_errors(_LIST,", "_errors(_NOT_A_VALIDATOR,")
    assert src != ENGINE_SRC, "锚点没打上，这条反证不算跑过"
    seeds = _seed_names(SHAPES_SRC, src)
    assert "EngineList" not in seeds["engine"], "引用还在但已不再拿它判 data ⇒ 不该记覆盖"
    assert "SpaceEngineBinding" in seeds["engine"], "另一条真端点用例不受影响，红面要收窄到被打的那条"
    report = _orphan_report(DOCS, seeds)
    assert any(line.startswith("engine/EngineList:") for line in report), report


def test_teeth_engine_side_has_no_exception() -> None:
    """引擎域走的是同一条判据（P-126 说"引擎域连同类守卫都没有"）。

    打法不改签名、只打断 validator 常量与 def 名的绑定（把 `"$ref"` 这个键换成谁都不认的键名）：
    两条真端点用例照跑 `_LIST`/`_BINDING`，但没有任何 def 有落点 ⇒ 引擎域 def 全成孤儿。
    """
    src = ENGINE_SRC.replace('"$ref"', '"$rot"')
    seeds = _seed_names(SHAPES_SRC, src)
    assert not seeds["engine"], "种子没打断，反证不算跑过"
    report = _orphan_report(DOCS, seeds)
    engine_lines = [line for line in report if line.startswith("engine/")]
    assert len(engine_lines) == len(DOCS["engine"]["$defs"]), report


def test_teeth_ref_inside_annotation_does_not_grant_reachability() -> None:
    """`$ref` 藏在 `x-*` 注释子树里 ⇒ 不给通行证；同一条形制挂在 `properties` 上就给。

    两边都测是因为这判据只能有一条正确的边：只测"注释里不算"会放行，只测"形状位算"会误伤。
    validator 从来不求值 `x-*`，所以注释里的一条引用不能替一个 def 声称"有人核过它"。
    """
    seeds = _seed_names(SHAPES_SRC, ENGINE_SRC)

    annotation = copy.deepcopy(DOCS)
    annotation["shapes"]["$defs"]["S56AnnotatedTarget"] = {"type": "string"}
    annotation["shapes"]["$defs"]["MeView"]["x-note"] = {"$ref": "#/$defs/S56AnnotatedTarget"}
    rep_a = _orphan_report(annotation, seeds)
    assert any("shapes/S56AnnotatedTarget" in line for line in rep_a), rep_a

    structural = copy.deepcopy(DOCS)
    structural["shapes"]["$defs"]["S56StructuralTarget"] = {"type": "string"}
    structural["shapes"]["$defs"]["MeView"]["properties"]["s56"] = {"$ref": "#/$defs/S56StructuralTarget"}
    rep_b = _orphan_report(structural, seeds)
    assert not any("S56StructuralTarget" in line for line in rep_b), rep_b


def test_teeth_dangling_and_cross_domain_refs_are_reported() -> None:
    """`$ref` 指向不存在的 def / 指向另一个域的 def ⇒ 各自红，可达性不沿坏边继续算。"""
    docs = copy.deepcopy(DOCS)
    docs["shapes"]["$defs"]["S56DanglingProbe"] = {
        "type": "object",
        "properties": {"a": {"$ref": "#/$defs/NoSuchDef"}},
        "additionalProperties": False,
    }
    docs["engine"]["$defs"]["S56CrossProbe"] = {
        "type": "object",
        "properties": {"b": {"$ref": "#/$defs/MeWallet"}},
        "additionalProperties": False,
    }
    report = _orphan_report(docs, _seed_names(SHAPES_SRC, ENGINE_SRC))
    assert any("S56DanglingProbe" in line and "NoSuchDef" in line for line in report), report
    assert any("S56CrossProbe" in line and "跨域" in line for line in report), report


def test_teeth_unknown_seed_name_is_reported() -> None:
    """测试里把契约名写错 ⇒ 报"种子名不在本域 $defs 里"，而不是悄悄少一个种子。"""
    report = _orphan_report(DOCS, {"shapes": {_ROOT_SEED, f"{_ROOT_SEED}Typo"}, "engine": _engine_seeds(ENGINE_SRC)})
    assert any("种子名不在本域" in line and "Typo" in line for line in report), report
    assert not any(line.startswith(f"shapes/{_ROOT_SEED}:") for line in report), f"写错一条不该牵连真种子：{report}"
