#!/usr/bin/env python
"""STEP-02 S2.1.3 机器证明：`kb._biz_from_url` 真的委托了 `parse_wechat_url`。

为什么不能直接 pytest：`app.services.kb` 在模块级 import `structlog` 与 `sqlalchemy`
（`kb.py:22-25`，本机两者皆无——实测收集期 `ModuleNotFoundError: No module named 'structlog'`），
连 import 都过不去。这里用的是 EVD-V2-00 已确立、EVD-V2-00R 沿用的机制——
**从磁盘上的 kb.py 里按 AST 取出 `_biz_from_url` 这一个函数节点，单独 compile + exec**。
函数体里的依赖全是局部导入（`from app.services.article_identity import …`），
所以不需要执行整个模块，也就绕开了 sqlalchemy。被执行的是文件里的当前代码，不是抄本：
改了函数体，这里的结论就会变。**取哪个函数节点按 Python 的模块作用域语义取最后一个顶层定义**——
同名重复定义时后者才是真实绑定，取第一个会证明到一段已经死掉的代码（第五轮复审 id 10）。

判据分四面：
- 行为面 BD-1…BD-6：长链出号主、与解析侧在**差分语料**上恒等、伪 biz 向后兼容、百分号等价、脏类型不抛；
- 结构面 BD-7…BD-9：函数体里必须真的出现对 `parse_wechat_url` 的调用（且该名字**没被本地重新绑定**）、
  导入源必须是 `app.services.article_identity`、且不得再有第二份解析（`parse_qs`/`urlparse` 归零）；
- 反面 BD-10：委托点不许用 `except` 兜底伪造返回值（把异常吞成非空串 = 数据黑洞+静默）；
- 反面 BD-11：函数体里不许再出现 `biz`/`__biz`/`mid`/`sn` 字面量（防「委托了但本地又解一遍」的半委托）；
- 反面 BD-12/BD-13（第五轮复审 id 3/id 10 的处置）：函数体**形状**白名单（只允许 文档串 / 委托导入 /
  委托绑定 / 返回委托结果的 `.biz`，此外任何嵌套定义、控制流、越界调用、越界属性一律红）+
  顶层同名定义必须**只有一个**。

三档裁决（rc 可分流，别让「没测到」冒充「测出红」）：
`0` 全绿 / `1` 有判据红 / `2` INCONCLUSIVE——`_biz_from_url` 整个不在文件里时判据无从判定，
这种状态若也打印 FAIL 清单，读者会把它当成普通的红基线（A–G 报告 B3/B4 的教训）。
`--self-test` 里这条映射测**两层**：内存里 `run()` 的返回值，以及真实子进程的退出码（后者用
临时目录副本 + `--kb=` 驱动，工作树不动）——第五轮复审 id 5 指出只测前者等于没测到 `sys.exit`。

`--self-test` 三条反证通道（与 prove_article_identity.py 同一方法论）：
① `MUTANTS` 把函数体改成「看起来还在但已失效」的形态（含**退回旧实现**），逐条要求指定判据红；
② `PROBES` 对内存样本跑同一判定函数，要求真实样本判真、坏样本判假；
③ `EQUIVS` 方向相反——语义等价的写法必须不假红。这条通道是 BD-7 认别名（`import … as pw`、
   转绑局部变量）的依据：只认裸名会把合法重构判成缺陷，正是「门禁被当噪音关掉」的失效模式。
②③ 的样本体一律先过 `_parses()`：解析不了的样本会让判据以 SyntaxError 的形式「变红」，
看起来像抓到了缺陷，实际是锚的缩进写错。
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
API = REPO / "apps" / "api"
KB = API / "app" / "services" / "kb.py"
TESTS = API / "tests"
#: 本步的被证明对象。模块作用域里凡是动过这个名字的绑定都算「换了实现」，见 `_module_bindings`。
TARGET_NAME = "_biz_from_url"

_p = str(API)
_t = str(TESTS)
if _p not in sys.path:
    sys.path.insert(0, _p)
if _t not in sys.path:
    sys.path.insert(0, _t)

RC_GREEN, RC_FAIL, RC_INCONCLUSIVE = 0, 1, 2

passed: list[str] = []
failed: list[str] = []
_quiet = False  # self-test 里复用 run() 时抑制逐条打印，但绝不抑制裁决本身


def check(label: str, ok: bool, detail: object = "") -> None:
    (passed if ok else failed).append(label)
    if not _quiet:
        print(f"{'PASS' if ok else 'FAIL'} {label}" + ("" if ok else f" :: {detail!r}"))


def say(text: str) -> None:
    if not _quiet:
        print(text)


def _top_defs(src: str) -> list[ast.FunctionDef]:
    """只取**模块顶层**的同名定义：嵌在别的函数里的同名 def 不是 `kb._biz_from_url`，
    `from app.services.kb import _biz_from_url` 拿到的是顶层那个，所以判定也只看顶层。"""
    return [n for n in ast.parse(src).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == TARGET_NAME]


#: 会绕过 AST 绑定分析的「动态写入」——只看这几个 callee，不多做猜测
_DYNAMIC_REBIND_CALLEES = frozenset({"globals", "locals", "vars", "exec", "eval", "setattr", "delattr"})


def _target_names(target: ast.AST | None, out: set[str]) -> None:
    """把一个绑定目标（含 `a, b = …` / `*rest` 的嵌套形状）摊平成名字集合。"""
    if isinstance(target, ast.Name):
        out.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            _target_names(elt, out)
    elif isinstance(target, ast.Starred):
        _target_names(target.value, out)


def _binds_target(node: ast.AST) -> bool:
    """这个**语句**是否动过模块作用域里的 `kb._biz_from_url` 绑定（含解绑）。"""
    out: set[str] = set()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        out.add(node.name)
    elif isinstance(node, ast.Assign):
        for t in node.targets:
            _target_names(t, out)
    elif isinstance(node, ast.AnnAssign) and node.value is not None:
        # 光有注解（`x: str`）不产生绑定，只有带右值的那条才算
        _target_names(node.target, out)
    elif isinstance(node, (ast.AugAssign, ast.NamedExpr)):
        _target_names(node.target, out)
    elif isinstance(node, ast.Delete):
        for t in node.targets:
            _target_names(t, out)
    elif isinstance(node, (ast.Import, ast.ImportFrom)):
        for a in node.names:
            out.add(a.asname or a.name.split(".")[0])
    elif isinstance(node, (ast.For, ast.AsyncFor)):
        _target_names(node.target, out)
    elif isinstance(node, (ast.With, ast.AsyncWith)):
        for item in node.items:
            _target_names(item.optional_vars, out)
    return TARGET_NAME in out


def _dynamic_rebind(stmt: ast.AST) -> str | None:
    """语句里是否出现「callee 是 globals()/exec()/setattr() 之类」且同时提到目标名。

    这类写入 AST 的绑定扫描看不见（`globals()['_biz_from_url'] = lambda …` 在语法上只是
    一次下标赋值），但运行时确实换掉了活绑定，所以按名字共现保守判红。"""
    if TARGET_NAME not in ast.unparse(stmt):
        return None
    for n in ast.walk(stmt):
        if not isinstance(n, ast.Call):
            continue
        func = n.func
        callee = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else "")
        if callee in _DYNAMIC_REBIND_CALLEES:
            return f"{callee}@{n.lineno}"
    return None


def _module_bindings(src: str) -> list[tuple[int, str]]:
    """按源码顺序列出模块作用域内**所有动过目标名绑定**的语句。

    为什么不能只看顶层 `def`：Python 的模块命名空间后写覆盖，`_biz_from_url = lambda …`、
    `globals()['_biz_from_url'] = …`、`if True: def _biz_from_url`、`del _biz_from_url`
    都会让「我们 exec 的那份 def」不再是 `import` 拿到的那份（第六轮复审 D1 四发全部空过）。
    只跳过函数/类体（那是局部作用域）；顶层 if/try/with/for 里的绑定必须收——
    **模块作用域没有块级作用域**，`if` 里的 def 绑的就是模块属性。"""
    hits: list[tuple[int, str]] = []

    def walk(body: list[ast.stmt]) -> None:
        for st in body:
            if _binds_target(st):
                hits.append((st.lineno, type(st).__name__))
            dyn = _dynamic_rebind(st)
            if dyn:
                hits.append((st.lineno, f"动态重绑[{dyn}]"))
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for field in ("body", "orelse", "finalbody"):
                blk = getattr(st, field, None)
                if isinstance(blk, list) and blk and isinstance(blk[0], ast.stmt):
                    walk(blk)
            for handler in getattr(st, "handlers", []) or []:
                walk(handler.body)
            for case in getattr(st, "cases", []) or []:
                walk(case.body)

    walk(ast.parse(src).body)
    return sorted(set(hits))


def has_target(src: str) -> bool:
    """目标函数在不在文件的顶层——纯 AST 判断，不需要 kb.py 能 import。"""
    return bool(_top_defs(src))


def get_fn_node(src: str) -> ast.FunctionDef:
    defs = _top_defs(src)
    if not defs:
        raise AssertionError("kb.py 顶层没有 _biz_from_url——本步的委托目标已不存在（或被嵌进别的函数），"
                             "必须显式复核")
    return defs[-1]


def load_biz(src: str):  # noqa: ANN201 - 返回被 exec 出来的函数对象
    """只 exec 这一个函数节点，得到**文件里当前实现**的真实可调用对象。"""
    fn = get_fn_node(src)
    mod = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    ns: dict[str, object] = {"__name__": "kb_sliced"}
    exec(compile(mod, str(KB), "exec"), ns)  # noqa: S102 - 执行仓库内受审代码
    return ns[TARGET_NAME]


def _try_load(src: str) -> tuple[object | None, str | None]:
    """`load_biz` 的安全版：把 exec 失败变成**一句可打印的原因**，而不是把调用方带崩。"""
    try:
        return load_biz(src), None
    except BaseException as exc:  # noqa: BLE001 - 变异体的破坏方式不受我们控制
        return None, f"{type(exc).__name__}: {exc}"


# ── 结构判据（返回 (ok, detail)，供 main 与反证样本共用）─────────────────────

DELEGATE_SRC = "app.services.article_identity"


def _delegate_aliases(fn: ast.AST) -> set[str]:
    """收出委托目标在函数内可见的**别名**（`import … as A`、转绑给局部变量 `A = …`）。

    只认三条绑定途径，其余一律不认，否则「随便调个函数」也算委托：
    1. `from app.services.article_identity import parse_wechat_url as A`；
    2. `A = parse_wechat_url` / `A = <某模块>.parse_wechat_url`（右值必须落到委托目标上）；
    3. 传递绑定 `B = A`（迭代到不动点）。
    导入源是否正确由 BD-8 单独判，这里不重复设口径；
    名字**是否又被别的东西绑过一次**由 `delegate_names()`/`_shadowed()` 负责剔除，
    两者合起来才是「调用点真的落到委托目标上」。
    """
    names: set[str] = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.ImportFrom) and n.module == DELEGATE_SRC:
            names.update(a.asname or a.name for a in n.names if a.name == "parse_wechat_url")
    for _ in range(3):
        added = False
        for n in ast.walk(fn):
            if not isinstance(n, ast.Assign) or len(n.targets) != 1 or not isinstance(n.targets[0], ast.Name):
                continue
            val = n.value
            if isinstance(val, ast.Name):
                ref = val.id
            elif isinstance(val, ast.Attribute):
                ref = val.attr
            else:
                ref = None
            dst = n.targets[0].id
            if ref is not None and ref in names and dst not in names:
                names.add(dst)
                added = True
        if not added:
            break
    return names


def _refs_delegate(val: ast.AST, watch: set[str]) -> bool:
    """右值是否真的落到委托目标上：裸名、已知别名、或 `<模块>.parse_wechat_url`。"""
    if isinstance(val, ast.Name):
        return val.id == "parse_wechat_url" or val.id in watch
    if isinstance(val, ast.Attribute):
        return val.attr == "parse_wechat_url" or val.attr in watch
    return False


def _shadowed(fn: ast.AST, watch: set[str]) -> set[str]:
    """别名在函数体内被**别的东西**重新绑定 ⇒ 调用点拿到的不是委托目标。

    第五轮复审 id 3 实测：只收集「谁可能被绑定到委托目标」而不检查「谁又被绑了一次」，
    `import parse_wechat_url as pw` + 本地 `def pw(u)` 的手搓解析器可以 11 条判据全绿。"""
    bad: set[str] = set()
    for n in ast.walk(fn):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bad |= {n.name} & watch
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                dst = a.asname or a.name.split(".")[0]
                legit = isinstance(n, ast.ImportFrom) and n.module == DELEGATE_SRC and a.name == "parse_wechat_url"
                if dst in watch and not legit:
                    bad.add(dst)
        elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            dst = n.targets[0].id
            if dst in watch and not _refs_delegate(n.value, watch):
                bad.add(dst)
    return bad


def delegate_names(fn: ast.AST) -> tuple[set[str], bool]:
    """返回（可用的委托别名集合, 裸名 `parse_wechat_url` 是否可信）。"""
    names = _delegate_aliases(fn)
    watch = names | {"parse_wechat_url"}
    bad = _shadowed(fn, watch)
    return names - bad, "parse_wechat_url" not in bad


def j_calls_delegate(src: str) -> tuple[bool, object]:
    """函数体内必须出现对委托目标的调用：裸名、`模块.函数`、改名导入、转绑局部变量都算，
    但**被本地定义或本地赋值遮蔽过的名字不算**。

    收紧到「只认裸名」会把等价重构判成缺陷（1a–6 报告 3e 实测：`import … as pw` 与
    `p = parse_wechat_url` 两种写法行为完全正确却红 BD-7）；放开的同时由 PROBES 里
    「别名链造假 / 别名被本地 def 遮蔽」两条坏样本保证判据仍不可空过。"""
    fn = get_fn_node(src)
    names, bare = delegate_names(fn)
    calls = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and (
            (isinstance(n.func, ast.Name) and ((bare and n.func.id == "parse_wechat_url") or n.func.id in names))
            or (isinstance(n.func, ast.Attribute) and ((bare and n.func.attr == "parse_wechat_url")
                                                       or n.func.attr in names))
        )
    ]
    return bool(calls), f"调用点 {len(calls)} 处、可用别名 {sorted(names) or '无'}、裸名可信={bare}"


def j_import_source(src: str) -> tuple[bool, object]:
    """委托目标必须来自 `app.services.article_identity`，不能是本地另写的同名函数。

    三种等价写法都要认：`from X import f`、`import X`、`from pkg import X`（后者按
    `pkg.X` 拼接比对）——只认第一种会把合法重构判成缺陷，正是反证③要防的假红。"""
    mods = set()
    for n in ast.walk(get_fn_node(src)):
        if isinstance(n, ast.ImportFrom):
            if n.module:
                mods.add(n.module)
                mods.update(f"{n.module}.{a.name}" for a in n.names)
        elif isinstance(n, ast.Import):
            mods.update(a.name for a in n.names)
    return DELEGATE_SRC in mods, sorted(mods)


def j_no_second_parser(src: str) -> tuple[bool, object]:
    """口径单点：kb 侧不得再出现第二份 URL 解析（`parse_qs`/`urlparse` 的任何形态）。"""
    bad = sorted(
        {
            (n.func.id if isinstance(n.func, ast.Name) else n.func.attr)
            for n in ast.walk(get_fn_node(src))
            if isinstance(n, ast.Call)
            and (
                (isinstance(n.func, ast.Name) and n.func.id in {"parse_qs", "urlparse", "parse_qsl"})
                or (isinstance(n.func, ast.Attribute) and n.func.attr in {"parse_qs", "urlparse", "parse_qsl"})
            )
        }
    ) + sorted(
        {
            f"import:{m}"
            for m in [
                (n.module or "") if isinstance(n, ast.ImportFrom) else ",".join(a.name for a in n.names)
                for n in ast.walk(get_fn_node(src))
                if isinstance(n, (ast.Import, ast.ImportFrom))
            ]
            if "urllib" in m
        }
    )
    return not bad, bad


def j_no_swallow(src: str) -> tuple[bool, object]:
    """不许用 except 把异常兜成返回值：那会把「解析失败」变成「解析出一个假身份」。"""
    handlers = [n for n in ast.walk(get_fn_node(src)) if isinstance(n, ast.ExceptHandler)]
    return not handlers, f"except 分支 {len(handlers)} 处"


def j_reads_both(src: str) -> tuple[bool, object]:
    """函数体里不该再出现字面量参数名——读参逻辑必须整体交给解析层（防半委托）。"""
    literals = sorted(
        {
            n.value
            for n in ast.walk(get_fn_node(src))
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in {"biz", "__biz", "mid", "sn"}
        }
    )
    return not literals, literals


# ── 形状与唯一定义判据（第五轮复审 id 3 / id 10 的处置）──────────────────────

_ALLOWED_IMPORT_PREFIXES = ("app.services", "app\\services")
_ALLOWED_IMPORTS = {DELEGATE_SRC, "app.services"}
_ALLOWED_ATTRS = {"biz", "parse_wechat_url"}
_STMT_KINDS = (ast.ImportFrom, ast.Import, ast.Assign, ast.AnnAssign, ast.Return)
_FORBIDDEN_NODES = (
    ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.If, ast.For, ast.AsyncFor,
    ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match, ast.ListComp, ast.SetComp,
    ast.DictComp, ast.GeneratorExp, ast.Lambda, ast.Await, ast.Yield, ast.NamedExpr,
    ast.AugAssign, ast.Global, ast.Nonlocal, ast.Assert, ast.Raise, ast.Delete,
    ast.IfExp, ast.BoolOp, ast.Subscript,
)
#: 调用点不许自己动字符串加工（第六轮复审 D2 的变异体就是 `url.split("__biz=")[-1]…`）
_CALLER_PARSE_METHODS = frozenset({"split", "rsplit", "splitlines", "partition", "rpartition",
                                   "removeprefix", "removesuffix", "lstrip", "rstrip", "strip"})


def _docstring(node: ast.FunctionDef) -> ast.Expr | None:
    first = node.body[0] if node.body else None
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        return first
    return None


def _callee(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return f"<{type(call.func).__name__}>"


def _arg_is_param(call: ast.Call, fn: ast.FunctionDef) -> bool:
    """委托调用的实参必须就是本函数的入参本身，不许加工（加工 = kb 侧又长了一份口径）。"""
    params = {a.arg for a in fn.args.args}
    if len(call.args) == 1 and not call.keywords:
        return isinstance(call.args[0], ast.Name) and call.args[0].id in params
    if not call.args and len(call.keywords) == 1:
        kw = call.keywords[0]
        return kw.arg in params and isinstance(kw.value, ast.Name) and kw.value.id in params
    return False


def _bind_value_ok(val: ast.AST, names: set[str], bare: bool) -> bool:
    """绑定语句的右值只许是三种：委托本体/别名本身、对委托的调用、调用结果上的 `.biz`。"""
    roots = names | ({"parse_wechat_url"} if bare else set())
    return (
        _refs_delegate(val, roots)
        or (isinstance(val, ast.Call) and _callee(val) in roots)
        or (isinstance(val, ast.Attribute) and val.attr == "biz" and isinstance(val.value, (ast.Call, ast.Name)))
    )


def j_body_shape(src: str) -> tuple[bool, object]:
    """BD-12：函数体形状白名单——只允许「文档串 / 委托导入 / 委托绑定 / 返回委托结果的 `.biz`」。

    为什么要有这条：BD-7~BD-11 全是**正面**证据（有导入、有调用、没有 `parse_qs` 字样），
    第五轮复审实测三发全部空过——本地 `def pw` 遮蔽别名、`parse_wechat_url = 手搓解析器`、
    以及用 `str.split("?")` 自己解析（既不含 `parse_qs`/`urlparse`，又把 `"biz"` 拆成
    `"bi" + "z"` 绕过字面量清单）。负面证据只能靠形状：白名单之外多一个节点就红。"""
    fn = get_fn_node(src)
    names, bare = delegate_names(fn)
    doc = _docstring(fn)
    params = {a.arg for a in fn.args.args}
    bad: list[str] = []

    if fn.decorator_list:
        # 装饰器会在 def 之后再换一层绑定：被 exec 的那份和 import 拿到的那份就不是同一个东西
        first = fn.decorator_list[0]
        name = _callee(first) if isinstance(first, ast.Call) else ast.unparse(first)
        bad.append(f"装饰器 {len(fn.decorator_list)} 处（首个 {name}）")

    for st in fn.body:
        if st is doc or isinstance(st, _STMT_KINDS):
            continue
        bad.append(f"语句 {type(st).__name__}@{st.lineno}")

    for n in ast.walk(fn):
        if n is fn:  # 被检函数自己不是「嵌套定义」
            continue
        if n is doc or n is (doc.value if doc else None):
            continue
        if isinstance(n, _FORBIDDEN_NODES):
            bad.append(f"嵌套/控制流 {type(n).__name__}@{getattr(n, 'lineno', '?')}")
            continue
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            bad.append(f"字符串字面量 {n.value[:12]!r}@{n.lineno}")
            continue
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            mods = [n.module or ""] if isinstance(n, ast.ImportFrom) else [a.name for a in n.names]
            bad += [f"越界导入 {m}" for m in mods
                    if m not in _ALLOWED_IMPORTS and not m.startswith(_ALLOWED_IMPORT_PREFIXES)]
            continue
        if isinstance(n, ast.Call):
            ref_ok = (isinstance(n.func, ast.Name) and ((bare and n.func.id == "parse_wechat_url")
                                                         or n.func.id in names)) or (
                isinstance(n.func, ast.Attribute) and ((bare and n.func.attr == "parse_wechat_url")
                                                        or n.func.attr in names)
            )
            if not ref_ok:
                bad.append(f"非委托调用 {_callee(n)}@{n.lineno}")
            elif not _arg_is_param(n, fn):
                bad.append(f"委托调用的实参不是入参 {sorted(params)}@{n.lineno}")
            continue
        if isinstance(n, ast.Attribute) and n.attr not in _ALLOWED_ATTRS:
            bad.append(f"越界属性 .{n.attr}@{n.lineno}")

        # 绑定语句：目标形状 + 右值来源，两个方向都要查（第六轮复审 D4：原先只查了
        # 单元组 Name 目标的 ast.Assign，`url: str = …`、`a, b = …` 整条被跳过）
        dst: str | None = None
        val: ast.AST | None = None
        if isinstance(n, ast.Assign):
            if len(n.targets) != 1 or not isinstance(n.targets[0], ast.Name):
                bad.append(f"绑定目标不是单个名字@{n.lineno}")
                continue
            dst, val = n.targets[0].id, n.value
        elif isinstance(n, ast.AnnAssign):
            if not isinstance(n.target, ast.Name):
                bad.append(f"注解绑定目标不是单个名字@{n.lineno}")
                continue
            if n.value is None:
                bad.append(f"只有注解没有右值@{n.lineno}")
                continue
            dst, val = n.target.id, n.value
        if dst is None or val is None:
            continue
        if dst in params:
            bad.append(f"入参 {dst} 被重新赋值@{n.lineno}")
        if not _bind_value_ok(val, names, bare):
            bad.append(f"绑定右值不合法 {type(val).__name__}@{n.lineno}")
    return not bad, sorted(set(bad))


def j_single_definition(src: str) -> tuple[bool, object]:
    """BD-13：模块作用域里**只允许一条语句**动过 `_biz_from_url` 的绑定，且那条就是被 exec 的 def。

    Python 按模块作用域后写覆盖，多出一份 `_biz_from_url` 时真实被 import 的是最后那份，
    而按「找到一个就证明」的写法会去证明一段死代码（第五轮复审 id 10 实测：追加
    `def _biz_from_url(url): return ''` 后 11 条判据全绿）。第六轮复审 D1 又把「非 def 的绑定」
    四发全部实测空过：`_biz_from_url = lambda url: ''`、`globals()['_biz_from_url'] = …`、
    `if True: def _biz_from_url`、`del _biz_from_url`——函数体判据全绿，而 `import` 拿到的是假的。
    所以本条判的不是「def 数量」，而是「被证明的那份 def 是不是当前活绑定」。"""
    defs = _top_defs(src)
    binds = _module_bindings(src)
    ok = len(defs) == 1 and len(binds) == 1 and binds[0] == (defs[0].lineno, "FunctionDef")
    return ok, (f"动过绑定的语句 {binds}；顶层 def {len(defs)} 处 {[d.lineno for d in defs]}；"
                f"被 exec 的是 {defs[0].lineno if defs else '无'} 行那份")


def j_executable(src: str) -> tuple[bool, object]:
    """BD-15：目标函数必须能被**单独 exec**——这是 BD-1…BD-6 六条行为判据的前提。

    第六轮复审 D5 实测：给 `_biz_from_url` 加一个引用模块级名字的装饰器后，
    `run()` 带着 `NameError` traceback 直接崩，三档退出码一条都没打印。
    崩掉既不是绿也不是红，门禁一旦常崩就会被当噪音关掉，所以把「能不能 exec」升格成判据本身。"""
    biz, err = _try_load(src)
    return err is None and biz is not None, err


def _caller_anchor_fn(tree: ast.AST) -> ast.AST | None:
    """找 `_find_source_by_anchor`（kb.py:336 的**async** def，它是 kb.py:343 那处委托调用的宿主）。"""
    return next(
        (n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_find_source_by_anchor"),
        None,
    )


def j_call_site(src: str) -> tuple[bool, object]:
    """BD-14：委托结果必须真的**喂进锚定查询**，且调用点不许自己解析 URL。

    为什么要有这条：BD-1…BD-13 全部只围着 `_biz_from_url` 自己转（`get_fn_node` 只取那个函数），
    第六轮复审 D2 实测把 `kb.py:343` 的 `_biz_from_url(url)` 换成 `url.split("__biz=")[-1]…`
    之后 13 条判据照样全绿——「函数内部正确」和「这个正确实现真的在起作用」是两件事，
    卡面标题写的是后者。"""
    tree = ast.parse(src)
    fn = _caller_anchor_fn(tree)
    if fn is None:
        return False, "kb.py 里没有 _find_source_by_anchor——锚定查询改名了，本判据的口径需要重定"
    bad: list[str] = []
    params = {a.arg for a in fn.args.args}
    calls = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == TARGET_NAME
    ]
    if not calls:
        bad.append("调用点没有对 _biz_from_url 的调用（委托结果到不了查询）")
    if not any(_arg_is_param(c, fn) for c in calls):
        bad.append(f"调用点的实参不是它自己的入参 {sorted(params)}")
    sql = [n for n in ast.walk(fn)
           if isinstance(n, ast.Compare) and ast.unparse(n.left).startswith("Source.external_id")]
    if not sql:
        bad.append("没有 Source.external_id 比较——锚点没进查询条件")
    for n in ast.walk(fn):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr in _CALLER_PARSE_METHODS
                and isinstance(n.func.value, ast.Name) and n.func.value.id in params):
            bad.append(f"调用点自己解析入参 .{n.func.attr}()@{n.lineno}")
    return not bad, bad or [f"调用 {len(calls)} 处、external_id 比较 {len(sql)} 处@{fn.lineno}"]


# ── 行为面 ────────────────────────────────────────────────────────────────

#: 差分语料：夹具之外再补发对抗形态，每条对应解析层的一条已定或待定口径
#: （`article_identity.py:57-66` 的三条解码口径、`__biz` 优先、空值回落、重复参数取首个、
#: 键名百分号解码、大小写、片段边界、host 无关、短链带 query）。只用于「两侧口径是否一致」，
#: 不给解析层本身下对错结论。
CORPUS: tuple[str, ...] = (
    "https://mp.weixin.qq.com/s?biz=OTHER&__biz=MjM5MjgwNTQ1MQ==&mid=1",
    "https://mp.weixin.qq.com/s?__biz=MjM5+MjgwNTQ1MQ==",
    "https://mp.weixin.qq.com/s?__biz=MjM5%2BMjgwNTQ1MQ==",
    "https://mp.weixin.qq.com/s?__biz=MjM5MjgwNTQ1MQ%3D%3D",
    "https://mp.weixin.qq.com/s?%5F%5Fbiz=MjM5MjgwNTQ1MQ==",
    "https://mp.weixin.qq.com/s?__biz=&biz=FALLBACK",
    "https://mp.weixin.qq.com/s?__biz=AAA&__biz=BBB",
    "https://mp.weixin.qq.com/s?__BIZ=AAA",
    "https://mp.weixin.qq.com/s?__biz",
    "https://mp.weixin.qq.com/s?__biz=AAA&",
    "https://mp.weixin.qq.com/s?__biz=AAA;mid=1",
    "https://mp.weixin.qq.com/s?__biz=AAA#x?__biz=BBB",
    "https://mp.weixin.qq.com/s#__biz=AAA",
    "https://example.com/x?__biz=AAA",
    "https://MP.WEIXIN.QQ.COM/s?__biz=AAA",
    "//mp.weixin.qq.com/s?__biz=AAA",
    "https://mp.weixin.qq.com/s/AbCdEfGh123?__biz=AAA",
    "https://mp.weixin.qq.com/s?__biz=AAA%26mid%3D2",
    "",
    "?__biz=AAA",
)


def behavior_probes(biz) -> list[tuple[str, bool, object]]:
    from app.services.article_identity import parse_wechat_url
    from fixtures.wechat_urls import (
        BIZ_A,
        LONG_A,
        LONG_A_TRACKING,
        LONG_B,
        OFFSITE,
        SHORT_1,
        SHORT_WITH_FAKE_BIZ_PARAM,
    )

    out = []

    def _biz(u: object) -> object:
        """变异体可能在**调用时**炸（比如导了个不存在的模块）。不兜住的话，
        evaluate() 会带着 traceback 一起崩，反证通道自身就失效了——崩掉不等于判红。"""
        try:
            return biz(u)
        except BaseException as exc:  # noqa: BLE001 - 判据要能把「抛异常」读成「不给空串」
            return f"<raised {type(exc).__name__}>"

    got_a = _biz(LONG_A)
    out.append(("BD-1 长链解出号主 biz（改前红：旧实现返回空串）", got_a == BIZ_A, f"_biz_from_url(LONG_A)={got_a!r}"))
    got_b = _biz(LONG_B)
    out.append(("BD-2 同 biz 不同 mid 的两篇都能解出同一号主", got_b == BIZ_A, f"={got_b!r}"))
    # 差分语料 = 夹具样本 + 解析层每条解码口径各挑一发对抗形态。期望值不写死：
    # 一律取 parse_wechat_url(u).biz，故本条判的是「kb 侧与解析侧是否同一个口径」，
    # 不是「解析侧自己对不对」（后者由 S2.1.2 的 14 条用例负责）。
    pairs = [LONG_A, LONG_A_TRACKING, LONG_B, OFFSITE, SHORT_1, SHORT_WITH_FAKE_BIZ_PARAM, *CORPUS]
    diff = [(u[:48], _biz(u), parse_wechat_url(u).biz) for u in pairs if _biz(u) != parse_wechat_url(u).biz]
    out.append((f"BD-3 与 parse_wechat_url(...).biz 恒等（口径单点，{len(pairs)} 个样本含 {len(CORPUS)} 条差分）",
                not diff, diff[:6]))
    short = _biz(SHORT_WITH_FAKE_BIZ_PARAM)
    out.append(("BD-4 短链伪 biz= 向后兼容（旧实现能解，委托后不许退化）", short == BIZ_A, f"={short!r}"))
    from urllib.parse import quote

    enc = LONG_A.replace(BIZ_A, quote(BIZ_A, safe=""))
    out.append(("BD-5 `%3D%3D` 与 `==` 同值（前提：样本确有差异，否则失去判定力）",
                enc != LONG_A and _biz(enc) == _biz(LONG_A) == BIZ_A, f"enc→{_biz(enc)!r} raw→{_biz(LONG_A)!r}"))
    raised = []
    nonempty = []
    for bad in (None, b"https://mp.weixin.qq.com/s?__biz=AAA", 42):
        try:
            if biz(bad) != "":
                nonempty.append((repr(bad), biz(bad)))
        except BaseException as exc:  # noqa: BLE001
            raised.append((repr(bad), f"{type(exc).__name__}: {exc}"))
    out.append(("BD-6 脏类型归零且不抛（None/bytes/int；旧实现只对 int 抛 AttributeError，"
                "对 None 与 bytes 静默返回空串——实测，非推断）",
                not raised and not nonempty, f"抛={raised} 非空={nonempty}"))
    return out


def run(src: str, label: str = "") -> int:
    """对一份 kb.py 源码下裁决并打印。可重复调用（先清空全局账）。"""
    passed.clear()
    failed.clear()
    if not has_target(src):
        say(
            "INCONCLUSIVE kb.py 里没有 _biz_from_url 这个函数——S2.1.3 未落地，或函数被改名。\n"
            "              此时任何判据都无从判定，故与「有判据红」分档返回，不打印 FAIL 清单冒充红基线。"
        )
        say(f"合计 未判定 PASS=0 FAIL=0（INCONCLUSIVE，rc={RC_INCONCLUSIVE}）")
        return RC_INCONCLUSIVE
    say(f"目标：{label or KB.relative_to(REPO).as_posix()} 的 {TARGET_NAME}"
        "（按模块作用域活绑定取那份 def，真实 exec 后再下裁决）\n")
    biz, exec_err = _try_load(src)
    check("BD-15 目标函数能被单独 exec（行为面六条的前提）", exec_err is None, exec_err)
    for label, ok, detail in behavior_probes(biz if biz is not None else _unloaded(exec_err)):
        check(label, ok, detail)
    check("BD-7 函数体内确有对 parse_wechat_url 的调用", *j_calls_delegate(src))
    check(f"BD-8 委托源必须是 {DELEGATE_SRC}", *j_import_source(src))
    check("BD-9 kb 侧无第二份 URL 解析（parse_qs/urlparse/urllib 导入归零）", *j_no_second_parser(src))
    check("BD-10 无 except 兜底（不许把失败伪造成身份）", *j_no_swallow(src))
    check("BD-11 无残留参数字面量（不许半委托）", *j_reads_both(src))
    check("BD-12 函数体形状在白名单内（不许长出自己的逻辑）", *j_body_shape(src))
    check("BD-13 模块作用域只有被 exec 的那一份绑定", *j_single_definition(src))
    check("BD-14 委托结果确实喂进锚定查询（调用点不许自己解析）", *j_call_site(src))
    say(f"\n合计 PASS={len(passed)} FAIL={len(failed)}")
    for lbl in failed:
        say(f"  FAIL {lbl}")
    say(
        "边界：本脚本只证明委托接线与解析口径；`test_kb_longlink_ingest.py` 的 pytest 实跑需 "
        "structlog+sqlalchemy（kb.py:22-25 模块级导入，本机皆无，实测收集期 ModuleNotFoundError），"
        "交 EVD-V2-02 §5 J-1/J-5。"
    )
    return RC_FAIL if failed else RC_GREEN


def _kb_override() -> Path | None:
    """`--kb=<路径>`：让档位自证能在**临时副本**上跑真实子进程，不动工作树。"""
    for arg in sys.argv:
        if arg.startswith("--kb="):
            return Path(arg.split("=", 1)[1])
    return None


def main() -> int:
    path = _kb_override() or KB
    if not path.exists():
        print(f"FAIL kb.py 不存在：{path}")
        return RC_FAIL
    label = path.relative_to(REPO).as_posix() if path.is_relative_to(REPO) else str(path)
    return run(path.read_text(encoding="utf-8"), label)


# ── 反证①：函数体变异必须让指定判据红 ──────────────────────────────────────

OLD_BODY = (
    '    """URL 中的 biz 参数（短链/长链 query 携带）；无则空串。"""\n'
    "    from urllib.parse import parse_qs, urlparse\n\n"
    "    qs = parse_qs(urlparse(url).query)\n"
    '    val = qs.get("biz", [""])\n'
    "    return val[0] if val else \"\"\n"
)
NEW_BODY = (
    '    """URL 中的号主标识；口径单点取自 article_identity。"""\n'
    "    from app.services.article_identity import parse_wechat_url\n\n"
    "    return parse_wechat_url(url).biz\n"
)

#: 第五轮复审 id 3 用的攻击体：不含 `parse_qs`/`urlparse` 字样（绕过 BD-9 的名单），
#: 也不含 `"biz"` 字面量（`"bi" + "z"` 绕过 BD-11 的清单），并且对夹具那 6 个样本全部给对
#: 答案 ⇒ 在只有正面判据时 11 条全绿。留在这里当变异/样本两条通道的靶子。
_HANDROLLED = (
    "    def {fname}(u):\n"
    "        class R:\n"
    "            biz = ''\n"
    "        r = R()\n"
    '        if isinstance(u, str) and "?" in u:\n'
    '            for part in u.split("?", 1)[1].split("&"):\n'
    '                k, _, v = part.partition("=")\n'
    '                if k.strip("_") == "bi" + "z":\n'
    '                    r.biz = v.replace("%3D", "=")\n'
    "                    break\n"
    "        return r\n"
)
_ALIAS_IMPORT = "    from app.services.article_identity import parse_wechat_url as pw\n\n"
_PLAIN_IMPORT = "    from app.services.article_identity import parse_wechat_url\n\n"

MUTANTS: list[tuple[str, str, str, set[str]]] = [
    ("退回旧实现：只读 biz（D-01b 本体复活）", NEW_BODY, OLD_BODY,
     {"BD-1", "BD-2", "BD-3", "BD-6", "BD-7", "BD-8", "BD-9", "BD-11"}),
    ("取错字段：返回 mid", "return parse_wechat_url(url).biz", "return parse_wechat_url(url).mid",
     {"BD-1", "BD-2", "BD-3"}),
    ("篡改返回值：把 base64 尾巴削掉", "return parse_wechat_url(url).biz",
     'return parse_wechat_url(url).biz.rstrip("=")', {"BD-1", "BD-3", "BD-5"}),
    # 多行替换体一律用**带缩进的锚**（锚含 4 空格），否则替换后首行变 8 空格 ⇒
    # 变异体根本解析不了，结构判据会以 IndentationError 冒充「致红」，反证通道失效。
    ("半委托：委托但空串时回退到本地再解析一次", "    return parse_wechat_url(url).biz",
     "    result = parse_wechat_url(url).biz\n"
     "    if result:\n        return result\n"
     "    from urllib.parse import parse_qs, urlparse\n\n"
     '    return parse_qs(urlparse(url).query).get("biz", [""])[0]\n',
     {"BD-9", "BD-11"}),
    ("except 兜底伪造身份（失败静默变假数据）", "    return parse_wechat_url(url).biz",
     "    try:\n        return parse_wechat_url(url).biz\n"
     '    except Exception:\n        return "MjM5MjgwNTQ1MQ=="\n',
     {"BD-10"}),
    # 以下三条来自第五轮复审 id 3 / id 10：改前实测**全部空过**（rc=0、11 条判据全绿）。
    ("别名被本地 def 遮蔽（导入是真的，调的是同名假函数）", NEW_BODY,
     _ALIAS_IMPORT + _HANDROLLED.format(fname="pw") + "\n    return pw(url).biz\n",
     {"BD-7", "BD-12"}),
    ("委托名被重绑到手搓解析器（正面判据仍看得见那次导入与那次调用）", NEW_BODY,
     _PLAIN_IMPORT + _HANDROLLED.format(fname="_ext") + "\n    parse_wechat_url = _ext\n\n"
     "    return parse_wechat_url(url).biz\n",
     {"BD-7", "BD-12"}),
    ("顶层同名重复定义·前置式（真委托仍在最后，只有 BD-13 抓得到）", "def _biz_from_url(url: str) -> str:",
     "def _biz_from_url(url: str) -> str:\n    return ''\n\n\ndef _biz_from_url(url: str) -> str:",
     {"BD-13"}),
    ("顶层同名重复定义·追加式（报告 id 10 原样攻击：live 是假函数）", "    return parse_wechat_url(url).biz\n",
     "    return parse_wechat_url(url).biz\n\n\ndef _biz_from_url(url: str) -> str:\n    return ''\n",
     {"BD-13", "BD-1", "BD-3"}),
    # 补强的是**反证通道自身**：加 `_biz()` 兜住调用期异常之前，这条变异体会让 evaluate()
    # 带 traceback 一起崩——通道崩掉不等于判红，self-test 也就无从给出结论。
    ("调用期抛异常（导入不存在的模块）：判据必须记下红而不是把通道崩掉", NEW_BODY,
     "    from app.services.article_identity import parse_wechat_url\n\n"
     "    from nonexistent_probe_module import probe_only\n\n    return parse_wechat_url(url).biz\n",
     {"BD-1", "BD-3", "BD-12"}),
    # ── 第六轮复审 D1：四发「def 还在、活绑定已换」的空过，改前实测 15 条判据全绿 ──
    ("模块作用域把名字改绑成 lambda（import 拿到的不是被证明的那份 def）", NEW_BODY,
     NEW_BODY + "\n" + TARGET_NAME + " = lambda url: ''\n", {"BD-13"}),
    ("顶层 if 里再 def 一份（模块作用域没有块级作用域，def 绑的是模块属性）", NEW_BODY,
     NEW_BODY + "\nif True:\n    def " + TARGET_NAME + "(url: str) -> str:\n        return ''\n", {"BD-13"}),
    ("globals() 动态重绑（AST 的绑定扫描看不见这次写入）", NEW_BODY,
     NEW_BODY + f"\nglobals()['{TARGET_NAME}'] = lambda url: ''\n", {"BD-13"}),
    ("del 掉目标名（活绑定直接消失，判据面却什么都没看见）", NEW_BODY,
     NEW_BODY + f"\ndel {TARGET_NAME}\n", {"BD-13"}),
    # 第六轮复审 D2：函数体内全绿，但委托结果根本不再进查询——证明面越过了函数边界才算数
    ("调用点换成就地 split 解析（BD-1…BD-13 只管函数体，抓不到）",
     "(_biz_from_url(url), article_key)", '(url.split("__biz=")[-1].split("&")[0], article_key)', {"BD-14"}),
    # 第六轮复审 D5：装饰器引用模块级名字 ⇒ 单独 exec 必崩；改前是 traceback，不是裁决
    ("装饰器引用未定义名字（行为面压根没跑，必须判红而不是把脚本崩掉）",
     "def _biz_from_url(url: str) -> str:", "@_probe_cache\ndef _biz_from_url(url: str) -> str:",
     {"BD-1", "BD-3", "BD-12", "BD-15"}),
]

# ── 反证②：结构判据的坏样本必须判假 ────────────────────────────────────────

_WRAP = 'def _biz_from_url(url: str) -> str:\n'

#: BD-13 的模块级坏样本要在**整份源码**上说话（函数级样本没有模块作用域可改）
_FULL_DELEGATION = _WRAP + NEW_BODY + "\n"

#: BD-14 的宿主样本：`_find_source_by_anchor` 的最小骨架，好样本保留委托调用 + external_id 比较
_CALLER_OK = (
    "def _find_source_by_anchor(self, article_key: str, url: str):\n"
    "    for anchor in (a for a in (_biz_from_url(url), article_key) if a):\n"
    "        return select(Source).where(Source.external_id == anchor)\n"
)
_CALLER_BAD = _CALLER_OK.replace(
    "(_biz_from_url(url), article_key)", '(url.split("__biz=")[-1].split("&")[0], article_key)'
)

PROBES: list[tuple[str, object, str, str]] = [
    ("BD-7 调用被删（只剩导入）", j_calls_delegate,
     _WRAP + "    from app.services.article_identity import parse_wechat_url\n    return ''\n", NEW_BODY),
    # BD-7 认别名之后必须有这条：调的名字看着像委托链，实际没绑定到委托目标。
    # 没有它，「放开别名」就等于把判据调松到不可失败。
    ("BD-7 别名链造假（改名的导入没被调用，调的是本地假函数）", j_calls_delegate,
     _WRAP + "    from app.services.article_identity import parse_wechat_url as pw\n\n"
     "    def _fake(u):\n        return ''\n\n    return _fake(url)\n", NEW_BODY),
    ("BD-8 委托到别的模块", j_import_source,
     _WRAP + "    from app.services.kb_legacy import parse_wechat_url\n\n    return parse_wechat_url(url).biz\n",
     NEW_BODY),
    ("BD-9 第二份解析回潮", j_no_second_parser,
     _WRAP + "    from urllib.parse import urlparse\n\n    return urlparse(url).path\n", NEW_BODY),
    ("BD-10 except 兜底回潮", j_no_swallow,
     "    try:\n        from app.services.article_identity import parse_wechat_url\n\n"
     "        return parse_wechat_url(url).biz\n    except Exception:\n        return ''\n", NEW_BODY),
    ("BD-11 参数字面量回潮", j_reads_both,
     _WRAP + '    from app.services.article_identity import parse_wechat_url\n\n'
     '    return parse_wechat_url(url).biz or "biz"\n', NEW_BODY),
    # 第五轮复审 id 3：这三发在改前都空过（判据说真），现在必须是判据抓到假。
    ("BD-7 别名被本地 def 遮蔽（看着像委托，调的是假函数）", j_calls_delegate,
     _WRAP + _ALIAS_IMPORT + _HANDROLLED.format(fname="pw") + "\n    return pw(url).biz\n", NEW_BODY),
    ("BD-12 函数体长出自己的逻辑（手搓解析器，无 parse_qs 字样）", j_body_shape,
     _WRAP + _PLAIN_IMPORT + _HANDROLLED.format(fname="_ext") + "\n    return _ext(url).biz\n", NEW_BODY),
    ("BD-13 顶层出现第二个同名定义（后者遮蔽前者）", j_single_definition,
     _WRAP + NEW_BODY + "\n\ndef _biz_from_url(url: str) -> str:\n    return ''\n", NEW_BODY),
    # 报告 id 3-LEGIT：BD-8 是集合归属，一次未被使用的正确导入就能满足它。
    # 这条坏样本钉的是「BD-7 负责绑定、BD-8 负责来源」的分工——BD-8 在这里仍判真，是预期的，
    # 真正挡住它的是 BD-7 的遮蔽剔除（判据级实测，不 exec 所以不碰不存在的模块）。
    ("BD-7 正确导入未被使用、同名伪源导入把它遮蔽", j_calls_delegate,
     _WRAP + "    from app.services.article_identity import parse_wechat_url\n"
     "    from app.services.kb_legacy import parse_wechat_url\n\n"
     "    return parse_wechat_url(url).biz\n", NEW_BODY),
    # ── 第六轮复审 D1/D2/D4/D5 的判据级样本对（坏样本判假 + 好样本判真，两个方向都要有）──
    ("BD-13 模块作用域被 lambda 覆盖（def 还在但不是活绑定）", j_single_definition,
     _FULL_DELEGATION + f"\n{TARGET_NAME} = lambda url: ''\n", NEW_BODY),
    ("BD-13 顶层 if 内再 def 一份（模块作用域没有块级作用域）", j_single_definition,
     _FULL_DELEGATION + f"\nif True:\n    def {TARGET_NAME}(url: str) -> str:\n        return ''\n", NEW_BODY),
    ("BD-13 globals() 动态重绑（绑定扫描的盲区）", j_single_definition,
     _FULL_DELEGATION + f"\nglobals()['{TARGET_NAME}'] = lambda url: ''\n", NEW_BODY),
    ("BD-13 del 掉目标名", j_single_definition,
     _FULL_DELEGATION + f"\ndel {TARGET_NAME}\n", NEW_BODY),
    ("BD-12 AnnAssign 把入参重新绑定（原先只查 ast.Assign）", j_body_shape,
     _WRAP + _PLAIN_IMPORT + "    url: str = parse_wechat_url(url).biz\n    return url\n", NEW_BODY),
    ("BD-12 多目标绑定换掉委托名", j_body_shape,
     _WRAP + _PLAIN_IMPORT + "    parse_wechat_url, extra = parse_wechat_url, None\n\n"
     "    return parse_wechat_url(url).biz\n", NEW_BODY),
    ("BD-12 下标绕回字符串加工", j_body_shape,
     _WRAP + _PLAIN_IMPORT + "    return [parse_wechat_url(url).biz][0]\n", NEW_BODY),
    ("BD-12 装饰器换了最终绑定", j_body_shape,
     "@staticmethod\n" + _WRAP + _PLAIN_IMPORT + "    return parse_wechat_url(url).biz\n", NEW_BODY),
    ("BD-15 装饰器引用模块级名字 ⇒ 单独 exec 必崩", j_executable,
     "@_probe_cache\n" + _WRAP + _PLAIN_IMPORT + "    return parse_wechat_url(url).biz\n", NEW_BODY),
    ("BD-14 调用点不再用委托结果", j_call_site,
     _CALLER_BAD, _CALLER_OK),
    ("BD-14 调用点没有 external_id 比较", j_call_site,
     _CALLER_OK.replace("Source.external_id == anchor", "Source.title == anchor"), _CALLER_OK),
]

# ── 反证③：等价写法必须不假红 ──────────────────────────────────────────────

EQUIVS: list[tuple[str, str, str]] = [
    ("关键字实参形式", "return parse_wechat_url(url).biz", "return parse_wechat_url(url=url).biz"),
    ("模块属性调用形式", "    from app.services.article_identity import parse_wechat_url\n\n"
     "    return parse_wechat_url(url).biz",
     "    from app.services import article_identity\n\n    return article_identity.parse_wechat_url(url).biz"),
    ("先取局部变量再返回", "    return parse_wechat_url(url).biz",
     "    parts = parse_wechat_url(url)\n    return parts.biz"),
    # 1a–6 报告 3e 实测：这两种写法行为完全正确，却被「只认裸名」的 BD-7 判成缺陷。
    # 假红门禁的代价是被人当噪音关掉，所以补进等价通道，由通道本身盯着。
    ("改名导入后调用（import … as pw）",
     "    from app.services.article_identity import parse_wechat_url\n\n"
     "    return parse_wechat_url(url).biz",
     "    from app.services.article_identity import parse_wechat_url as pw\n\n"
     "    return pw(url).biz"),
    ("转绑局部变量后调用", "    return parse_wechat_url(url).biz",
     "    _delegate = parse_wechat_url\n    return _delegate(url).biz"),
    # BD-12 是白名单，风险全在假红：把「仍然委托、只是换个写法」的形态钉进通道里盯着。
    ("先把 .biz 取到局部变量再返回", "    return parse_wechat_url(url).biz",
     "    biz = parse_wechat_url(url).biz\n    return biz"),
    ("导入整模块并改名后调用", _PLAIN_IMPORT + "    return parse_wechat_url(url).biz",
     "    from app.services import article_identity as ai\n\n    return ai.parse_wechat_url(url).biz"),
    # 第六轮新增判据也要有各自的「换个写法不该红」：BD-12 的带注解绑定、BD-14 的调用点局部变量。
    ("带类型注解的局部绑定（AnnAssign 与 Assign 同权）", "    return parse_wechat_url(url).biz",
     "    parts: object = parse_wechat_url(url)\n    return parts.biz"),
    ("调用点先把委托结果存成局部变量", "        for anchor in (a for a in (_biz_from_url(url), article_key) if a):",
     "        biz_anchor = _biz_from_url(url)\n"
     "        for anchor in (a for a in (biz_anchor, article_key) if a):"),
]


def _parses(src: str) -> bool:
    """反证通道自身的守门：变异体必须能解析。解析不了的变异体会让结构判据以
    SyntaxError 的形式「变红」，看起来像缺陷被抓住，实际是锚写错了——必须单独判 FAIL。"""
    try:
        ast.parse(src)
        return True
    except SyntaxError:
        return False


def _strip_target(src: str) -> str:
    """按行删掉顶层的 `_biz_from_url`（只在内存里，不动工作树），用于档位自证。"""
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == "_biz_from_url":
            lines = src.splitlines(keepends=True)
            del lines[node.lineno - 1 : node.end_lineno]
            return "".join(lines)
    return src


def self_test() -> int:
    rc = 0
    # `--self-test --kb=<路径>`：基准跟着换（第六轮复审指出改前这里恒读真实 kb.py，
    # 于是「在副本上自证」的通道名不副实）。基准里没有委托锚就说明副本不对，早退。
    src = (_kb_override() or KB).read_text(encoding="utf-8")
    if not has_target(src):
        print("INCONCLUSIVE kb.py 里连 _biz_from_url 都没有 ⇒ S2.1.3 未落地或函数被改名，"
              "变异/样本两条通道的基准都无从构造")
        return RC_INCONCLUSIVE
    if NEW_BODY not in src:
        print("FAIL 基准异常：函数在，但文件里找不到**委托后**的函数体锚点 NEW_BODY "
              "⇒ S2.1.3 尚未落地（仍是旧实现）或锚对应的源码被改写过名；"
              "MUTANTS/EQUIVS 的替换锚无从定位，self-test 的结论不可用")
        return RC_FAIL

    # 档位自证：三档裁决必须互不相同，否则「没测到」会被读成「测出红」（A–G 报告 B3/B4）。
    global _quiet
    _quiet = True
    rc_base = run(src)
    rc_missing = run(_strip_target(src))
    rc_red = run(src.replace(NEW_BODY, OLD_BODY))
    _quiet = False
    for name, got, want in (
        ("基准（未变形）", rc_base, RC_GREEN),
        ("删掉目标函数", rc_missing, RC_INCONCLUSIVE),
        ("退回旧实现", rc_red, RC_FAIL),
    ):
        if got != want:
            print(f"FAIL 档位自证：{name} 应返回 rc={want}，实得 rc={got}")
            rc = 1
    if rc == 0:
        print(f"OK   档位自证：绿 rc={RC_GREEN} / 目标缺失 rc={RC_INCONCLUSIVE}（INCONCLUSIVE）"
              f" / 有判据红 rc={RC_FAIL} 三档分得开")

    # 退出码自证：三档必须真的映射到**进程退出码**，而不只是停在 run() 的返回值上
    # （第五轮复审 id 5 的坦白：`sys.exit` 那一步没被跑到，等于没测）。
    # 用临时目录里的 kb.py 副本 + `--kb=` 驱动，工作树一个字节都不动。
    tmp = Path(tempfile.mkdtemp(prefix="bd_tiers_"))
    offenders: list[str] = []
    try:
        for name, want, body in (
            ("基准（未变形）", RC_GREEN, src),
            ("删掉目标函数", RC_INCONCLUSIVE, _strip_target(src)),
            ("退回旧实现", RC_FAIL, src.replace(NEW_BODY, OLD_BODY)),
        ):
            copy = tmp / "kb.py"
            copy.write_text(body, encoding="utf-8")
            got = subprocess.run(  # noqa: S603 - 只跑本文件自己
                [sys.executable, str(Path(__file__).resolve()), f"--kb={copy}"],
                capture_output=True, text=True, encoding="utf-8",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"}, check=False,
            ).returncode
            if got != want:
                offenders.append(f"{name} 应 rc={want}，子进程实得 rc={got}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if offenders:
        print("FAIL 退出码自证：" + "；".join(offenders))
        rc = 1
    else:
        print(f"OK   退出码自证：子进程真实退出码三档分得开"
              f"（绿 {RC_GREEN} / 目标缺失 {RC_INCONCLUSIVE} / 有判据红 {RC_FAIL}）")

    base = evaluate(src)
    if base:
        print(f"FAIL 基准（未变异）就有红判据：{sorted(base)}——self-test 结论不可用")
        rc = 1
    else:
        print("OK   基准：未变形的 kb.py 判据全绿")

    for label, old, new, must_red in MUTANTS:
        if src.count(old) != 1:
            print(f"FAIL 变异锚失配（出现 {src.count(old)} 次）：{label}")
            rc = 1
            continue
        mutated = src.replace(old, new)
        if not _parses(mutated):
            print(f"FAIL 变异体无法解析（锚缩进错）：{label}")
            rc = 1
            continue
        red = evaluate(mutated)
        miss = {k for k in must_red if k not in red}
        if miss:
            print(f"FAIL {label}｜应红未红：{sorted(miss)}｜实际红：{sorted(red)}")
            rc = 1
        else:
            print(f"OK   {label} → 致红 {sorted(red)}")

    for label, judge, bad_body, good_body in PROBES:
        bad_src = _wrap_body(bad_body)
        good_src = _wrap_body(good_body)
        # 判据通道也要过 _parses：坏样本自己解析不了时，judge 抛的 SyntaxError 会
        # 冒充「判到了假」，而实际是锚的缩进写错——这正是我给 MUTANTS 补门的原因。
        if not _parses(bad_src) or not _parses(good_src):
            print(f"FAIL {label}：样本无法解析（锚缩进错），判据结论不可用")
            rc = 1
            continue
        ok_bad = judge(bad_src)[0]
        ok_good = judge(good_src)[0]
        if ok_bad:
            print(f"FAIL {label}：坏样本仍判真（判据不可失败）")
            rc = 1
        elif not ok_good:
            print(f"FAIL {label}：好样本判假，基准选错")
            rc = 1
        else:
            print(f"OK   {label}：好样本判真 / 坏样本判假")

    for label, old, new in EQUIVS:
        mutated = src.replace(old, new)
        if src.count(old) != 1:
            print(f"FAIL 等价重构锚失配：{label}")
            rc = 1
            continue
        if not _parses(mutated):
            print(f"FAIL 等价重构体无法解析（锚缩进错）：{label}")
            rc = 1
            continue
        red = evaluate(mutated)
        if red:
            print(f"FAIL 等价重构被判成缺陷：{label}｜假红={sorted(red)}")
            rc = 1
        else:
            print(f"OK   等价重构 {label} → 判据全绿")

    print(
        f"\nSELF-TEST {'PASS' if rc == 0 else 'FAIL'}："
        f"{len(MUTANTS)} 个函数体变异各自让指定判据变红 + {len(PROBES)} 个判据样本对敏感"
        f" + {len(EQUIVS)} 个等价写法不假红"
    )
    return rc


def _wrap_body(body: str) -> str:
    # 已经是**整份源码**（顶层 def / async def / 装饰器开头）的样本不再套壳，
    # 否则套出来的东西缩进错、`_parses()` 直接判死，判据通道等于没跑。
    head = body if body.startswith(("def ", "async def ", "@")) else _WRAP + body
    return head + "\n"


def evaluate(src: str) -> set[str]:
    """返回变红的判据 id 集合（结构面 + 行为面，行为面异常按「该判据红」处理）。"""
    red: set[str] = set()
    structural = {
        "BD-7": j_calls_delegate,
        "BD-8": j_import_source,
        "BD-9": j_no_second_parser,
        "BD-10": j_no_swallow,
        "BD-11": j_reads_both,
        "BD-12": j_body_shape,
        "BD-13": j_single_definition,
        "BD-14": j_call_site,
    }
    for bid, judge in structural.items():
        try:
            if not judge(src)[0]:
                red.add(bid)
        except (AssertionError, SyntaxError) as exc:
            red.add(f"{bid}(异常 {type(exc).__name__})")
    biz, exec_err = _try_load(src)
    if exec_err is not None:
        # exec 失败不是「没测到」而是「行为面确实不成立」——按 BD-15 红处理，并让六条行为判据各红一次
        red.add("BD-15")
    for label, ok, _detail in behavior_probes(biz if biz is not None else _unloaded(exec_err)):
        if not ok:
            red.add(label.split()[0])
    return red


def _unloaded(exec_err: str | None):  # noqa: ANN201 - 占位可调用对象
    """行为面无法 exec 时用它代替真实实现：调用即抛，六条判据逐条落下红迹。"""

    def _raise(url: object) -> object:  # noqa: ARG001 - 签名与 _biz_from_url 对齐
        raise RuntimeError(f"目标函数未能 exec：{exec_err}")

    return _raise


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else main())
