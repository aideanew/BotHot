"""STEP-00R 机器证明：测试出站的代理隔离与同形脆弱点收口（纯 stdlib，不启服务、不装依赖）。

为什么不能 `import conftest`：按「本项目无需安装开发环境和依赖」约束，本机没有
sqlalchemy / httpx / dotenv（实测 `python -c "import httpx"` → ModuleNotFoundError），
而 `apps/api/tests/conftest.py` 在模块级 import 它们。此处沿用 EVD-V2-00/prove_dsn_policy.py
的机制：解析 AST、剔除三方 import、只执行前缀语句，再单独 exec `_isolate_proxy_env` 的
**当前函数体**（剥掉装饰器，注入按 pytest.MonkeyPatch 语义实现的替身）。被执行的是文件
里的真实代码，不是抄本——改了函数体，这里的结论就会变。

`--self-test` 提供 G-23 反证，先要求**基准（未变异的 conftest）全绿**（否则「变异体让 X 变红」
这个信号没有意义），再走三条通道（条数一律由末行按 `len(...)` 动态打印，本文档不写死数字）：
① MUTANTS——把夹具改成「看起来还在但已失效」的 conftest 变异体（去掉 autouse / 删掉 delenv 循环 /
   换 raising=True / 换 NO_PROXY 值 / 直写 os.environ 绕过 monkeypatch / 不再写小写 no_proxy /
   大写那遍写非契约值 / 同名先好后坏的双写 / 平台守卫后的坏写 / 清理循环与常量脱钩 /
   真接线循环塞进 `if False` 而活路径改硬写 / 删掉常量定义 / scope 改 session / 广播行挪走 /
   夹具误删 DSN），逐条确认对应断言**变红**；
② TEXT_PROBES——读**其它真实文件**的判据（NR-8、NR-9-a/b/c、NR-10-a/b、NR-11、NR-12）改 conftest
   变不红它，故在**内存样本**上跑同一个判定函数，要求基准为真、变异样本为假；
③ EQUIV_REFACTORINGS——方向相反的反证：`setenv(name=…, value=…)`、`delenv(_n, False)`、
   `list(_PROXY_ENV_VARS)` 这些**等价改写必须一条都不判红**。判据把合法写法也判红就是假红，
   门禁会被人当噪声关掉；这一通道是第四轮复审用真实重构实测出脆性之后加的。

win32 特有的一条：`os.environ` 键大小写不敏感，「有没有写小写 no_proxy」在行为层不可观测，
故 NR-14 用结构判据兜住（两种拼写的**每一次**写入都要取契约值——只记第一次写入会被
「先契约值、后坏写」的双写绕过，第四轮复审实测如此）。NR-15 钉「清理遍历模块级常量」这一
结构面，NR-16 再用**运行期哨兵**（往常量表追加一项，看夹具跟不跟删）钉行为面：结构判据看不见
死代码里的循环，哨兵看得见；哨兵看不见纯写法变化，结构判据看得见。两者互为盲区补位。
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import os
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):  # 与既有证明脚本同口径：Windows 控制台默认 GBK
    sys.stdout.reconfigure(encoding="utf-8")  # ty: ignore[unresolved-attribute]

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[4]
API = ROOT / "apps" / "api"
TESTS = API / "tests"
CONF = TESTS / "conftest.py"
VAR = "AIDEANBOT_TEST_PG_DSN"
# 契约字面量：夹具必须把回环地址排除在代理之外。刻意写死而不是读 conftest 的常量——
# 否则「把常量改成 localhost」这类变异体会跟着一起改，断言就永远不可能失败（G-23）。
EXPECTED_NO_PROXY = "127.0.0.1,localhost,::1"
# Windows 的 os.environ 键大小写不敏感（CPython 在 win32 上按 upper() 归一，实测
# `os.environ['NO_PROXY']='A'; os.environ['no_proxy']='B'` 后只剩一个条目）。夹具在两个
# 平台上都仍然正确（覆写两次、undo 复原宿主值），但「宿主本没有小写 no_proxy ⇒ undo 后应
# 消失」这一条在 win32 上不可观测——它与 NO_PROXY 是同一个键，undo 只能复原成宿主原值。
# 分档写明，而不是假装判据跨平台一致（Linux CI 上仍要求 None）。
_HOST_NO_PROXY = "internal.example"
POST_UNDO_NO_PROXY = _HOST_NO_PROXY if sys.platform == "win32" else None
POST_UNDO_HTTP_PROXY = "http://127.0.0.1:10808"
PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
CONSUMERS = (
    "test_alerting_drill.py",
    "test_bots_logs_filter.py",
    "test_wb_push_hardening.py",
    "test_w3_push_scheduler.py",
    # 复审 N-4：本步新增的用例自己也是消费方（:54 有 `webhook_url=REFUSED_HTTP_URL`），
    # 不列进去 ⇒ 它退回字面量时无人报警。
    "test_env_isolation.py",
)

FAILURES: list[str] = []
CHECKS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    (CHECKS if ok else FAILURES).append(f"{'PASS' if ok else 'FAIL'} {label}{f' :: {detail}' if detail else ''}")


def load_sibling(name: str):
    """按路径加载 EVD-V2-00 的同目录证明脚本，复用其 exec_prefix（同一套解析口径）。"""
    path = ROOT / "docs" / "06_validation" / "evidence" / "EVD-V2-00" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def fixture_node(tree: ast.Module, name: str = "_isolate_proxy_env") -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def decorator_kwargs(node: ast.FunctionDef) -> dict[str, str]:
    """取 `@pytest.fixture(...)` / `@fixture(...)` 的关键字参数（unparse 后的字面量）。"""
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        fname = dec.func.attr if isinstance(dec.func, ast.Attribute) else getattr(dec.func, "id", "")
        if fname == "fixture":
            return {k.arg: ast.unparse(k.value) for k in dec.keywords if k.arg}
    return {}


def first_executable(body: list[ast.stmt]) -> ast.stmt | None:
    """函数体首条**可执行**语句——跳过文档字符串（它是 Expr(Constant)，会挡在守卫前面）。"""
    for stmt in body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            continue
        return stmt
    return None


def exec_fixture(src_text: str, ns_seed: dict) -> object:
    """剥掉装饰器后 exec 夹具函数体，返回可调用对象（真实代码，非重写）。"""
    tree = ast.parse(src_text)
    fn = fixture_node(tree)
    if fn is None:
        raise LookupError("conftest 里没有 _isolate_proxy_env")
    fn = copy.deepcopy(fn)
    fn.decorator_list = []
    future = ast.parse("from __future__ import annotations").body[0]
    mod = ast.fix_missing_locations(ast.Module(body=[future, fn], type_ignores=[]))
    ns = dict(ns_seed)
    exec(compile(mod, str(CONF), "exec"), ns)
    return ns["_isolate_proxy_env"]


class FakeMonkeyPatch:
    """只实现夹具用到的两个方法，语义与 pytest.MonkeyPatch 对 os.environ 的部分一致。"""

    def __init__(self) -> None:
        self._undo: list[tuple[str, str | None]] = []

    def setenv(self, name: str, value: str) -> None:
        self._undo.append((name, os.environ.get(name)))
        os.environ[name] = value

    def delenv(self, name: str, raising: bool = True) -> None:
        if name in os.environ:
            self._undo.append((name, os.environ[name]))
            del os.environ[name]
        elif raising:
            raise KeyError(name)

    def undo(self) -> None:
        for name, prev in reversed(self._undo):
            if prev is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = prev


class sandbox:
    """进出时完整快照/恢复相关环境变量，保证证明本身不污染调用方进程。"""

    NAMES = (*PROXY_VARS, "NO_PROXY", "no_proxy", VAR)

    def __enter__(self) -> None:
        self._saved = {n: os.environ.get(n) for n in self.NAMES}
        for n in self.NAMES:
            os.environ.pop(n, None)

    def __exit__(self, *exc) -> None:
        for n, v in self._saved.items():
            if v is None:
                os.environ.pop(n, None)
            else:
                os.environ[n] = v


# `setenv(名, 值)` 里「值」允许的两种形态：引用 conftest 常量，或直接落契约字面量。
CONTRACT_VALUE_EXPRS = {"NO_PROXY_ISOLATION_VALUE", repr(EXPECTED_NO_PROXY)}

#: NR-16 运行期注入的假代理变量：只在「夹具真的遍历常量」时才会被删掉。
SENTINEL_VAR = "AIDEANBOT_SENTINEL_PROXY_VAR"


def call_arg(call: ast.Call, index: int, param: str) -> ast.expr | None:
    """按形参槽位取实参——位置写法与关键字写法等价，两种都要认。

    第四轮复审用 `setenv(name="NO_PROXY", value=…)`、`delenv(_name, False)`、
    `delenv(name=_name, raising=False)` 三条**合法重构**实测出「改法等价却判红」，
    那是判据自身的缺陷（假红会把人训练成忽略门禁）。槽位名取自 pytest.MonkeyPatch 签名。
    """
    if len(call.args) > index:
        return call.args[index]
    for kw in call.keywords:
        if kw.arg == param:
            return kw.value
    return None


def setenv_writes(node: ast.AST) -> dict[str, list[str]]:
    """夹具内所有 `setenv(名, 值)` 调用，按名收集**每一次**写入的值表达式。

    只记第一次（`setdefault`）是第四轮复审抓出的 fail-open：`NO_PROXY` 先契约值、
    后 `"localhost"` 的连写，以及 `if os.name != "nt": setenv("NO_PROXY", "evil")`
    这一类平台守卫后的坏写，都能在全绿的情况下让夹具在非本平台上失效。
    """
    writes: dict[str, list[str]] = {}
    for call in ast.walk(node):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "setenv"):
            continue
        name = call_arg(call, 0, "name")
        value = call_arg(call, 1, "value")
        if isinstance(name, ast.Constant) and isinstance(name.value, str):
            writes.setdefault(name.value, []).append(ast.unparse(value) if value is not None else "（缺值实参）")
    return writes


def no_proxy_pairings(node: ast.AST) -> tuple[bool, str]:
    """NR-14 的加强形态：两种拼写的**每一次**写入都必须取契约值。

    口径演进（每一版都是被反证逼出来的，不是自己想到就写下的）：
    - v1 只比「字面量名集合」⇒ `setenv("NO_PROXY", "localhost")` 混过去；
    - v2 按位置取 (名, 值) 配对，但 `setdefault` 只记第一条 ⇒ 好写之后追加坏写全绿；
    - v3（本版）收集全部写入 + 位置/关键字通吃 + `ast.walk` 深入嵌套分支 ⇒
      双写覆写、平台守卫坏写都红，而合法的关键字写法不假红。
    """
    writes = setenv_writes(node)
    bad = [
        f"{n}→{v!r}"
        for n in ("NO_PROXY", "no_proxy")
        for v in (writes.get(n) or ["（未写）"])
        if v not in CONTRACT_VALUE_EXPRS
    ]
    pairing = "、".join(f"{k}→[{', '.join(v)}]" for k, v in sorted(writes.items())) or "无"
    return not bad, f"写入={pairing}" + (f"｜不合格={bad}" if bad else "")


def delenv_loop_wired(node: ast.AST, tree: ast.Module) -> tuple[bool, str]:
    """清理动作必须「遍历 `_PROXY_ENV_VARS` 常量」，且 `delenv(<循环变量>, raising=False)`。

    行为判据（NR-4-a）预设的是**本脚本自己抄的那份清单**，所以「夹具改成硬写六个字面量」在当下
    照样绿——将来常量新增一项（如新代理变量）而夹具没跟上时，无人报警。这条结构判据把
    「单一真值来源」钉住。
    两个细节都是被反证逼出来的（不做反证就不会发现）：
    - 只查「循环源码里出现 `_PROXY_ENV_VARS` 这个名字」不够：把常量定义整行删掉后名字还在，
      运行时才 NameError ⇒ 必须同时确认它是 **conftest 模块级真实赋值过的名字**；
    - 迭代源必须是 `Name` 节点，元组字面量（哪怕内容与常量一模一样）不算接线。
    """
    assigned: set[str] = set()
    for n in tree.body:
        # getattr 的默认值是**即时求值**的，写成 getattr(n, "targets", [n.target]) 会在
        # ast.Assign 上 AttributeError（它只有 targets）——所以按节点类型分支取目标。
        if isinstance(n, ast.Assign):
            targets = n.targets
        elif isinstance(n, ast.AnnAssign):
            targets = [n.target]
        else:
            continue
        assigned.update(t.id for t in targets if isinstance(t, ast.Name))
    if "_PROXY_ENV_VARS" not in assigned:
        return False, "conftest 模块级没有 `_PROXY_ENV_VARS` 的赋值（夹具无从引用）"
    for loop in ast.walk(node):
        if not (isinstance(loop, ast.For) and _iterates_constant(loop)):
            continue
        target = ast.unparse(loop.target)
        for call in ast.walk(loop):
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "delenv"
                and (arg0 := call_arg(call, 0, "name")) is not None
                and ast.unparse(arg0) == target
                and (arg1 := call_arg(call, 1, "raising")) is not None
                and ast.unparse(arg1) == "False"
            ):
                return True, f"遍历模块级 _PROXY_ENV_VARS，循环体内 delenv({target}, raising=False) 就位"
        break
    return False, "找不到「遍历模块级 _PROXY_ENV_VARS + delenv(循环变量, raising=False)」的循环"


_ITER_WRAPPERS = {"list", "tuple", "sorted"}


def _iterates_constant(loop: ast.For) -> bool:
    """迭代源必须是模块常量本身，或它的一层可迭代包装（`list(_PROXY_ENV_VARS)`）。

    硬写的同值元组不算接线——那正是 NR-15 要抓的形态；包装只放宽**写法**，
    「夹具与常量同源」这条语义不变（行为面另由 NR-16 的运行期哨兵兜住）。
    包装形态是第四轮复审用合法重构实测出假红后补的。
    """
    it = loop.iter
    if isinstance(it, ast.Name):
        return it.id == "_PROXY_ENV_VARS"
    if isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id in _ITER_WRAPPERS and it.args:
        first = it.args[0]
        return isinstance(first, ast.Name) and first.id == "_PROXY_ENV_VARS"
    return False


def literal_hits(texts: dict[str, str], needle: str) -> list[str]:
    """在「名字→源码」映射里找包含式命中（NR-8/NR-11 的判据本体，便于用内存样本反证）。"""
    return sorted(name for name, text in texts.items() if needle in text)


def tests_tree_texts() -> dict[str, str]:
    return {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8") for p in TESTS.rglob("*.py")}


def isolation_case_layout(text: str) -> dict[str, tuple[bool, str]]:
    """`test_env_isolation.py` 的三条结构判据（NR-12-a/b/c），按面返回便于逐面反证。"""
    tree = ast.parse(text)
    cases = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")]
    counts = {n.name: sum(isinstance(x, ast.Assert) for x in ast.walk(n)) for n in cases}
    # 快照只有在「任何用例定义之前」的模块级求值才等于收集期宿主环境；放进用例里就晚了。
    # 两种赋值形态（Assign / AnnAssign）都要认，否则判定会因写法而假红。
    snap_line = next(
        (n.lineno for n in tree.body
         if isinstance(n, (ast.Assign, ast.AnnAssign)) and "_HOST_PROXY_VARS_AT_COLLECT" in ast.unparse(n)),
        None,
    )
    first_case_line = min((n.lineno for n in cases), default=0)
    return {
        "a": (len(cases) == 3, f"用例={list(counts)}"),
        "b": (bool(counts) and all(c > 0 for c in counts.values()), str(counts) or "无用例"),
        "c": (snap_line is not None and snap_line < first_case_line,
              f"快照 :{snap_line}、首个用例 :{first_case_line}"),
    }


def webhook_url_wired_to_constant(text: str) -> tuple[bool, str]:
    """NR-9-b 的判据：常量不只是「出现在文件里」，而是真的接到 `webhook_url=` 形参上。

    弱判据（子串包含）会让「import 了却没用」「又写回字面量」两种回归都探不到，
    故此处走 AST：①必须有 `from fixtures.net import REFUSED_HTTP_URL`；
    ②收集该常量的别名（含 `_REFUSED_WEBHOOK_URL = REFUSED_HTTP_URL` 这类模块级别名）；
    ③必须存在 `webhook_url=<常量或别名>` 的关键字实参。
    """
    tree = ast.parse(text)
    imported = any(
        isinstance(n, ast.ImportFrom)
        and (n.module or "").endswith("fixtures.net")
        and any(a.name == "REFUSED_HTTP_URL" for a in n.names)
        for n in ast.walk(tree)
    )
    aliases = {"REFUSED_HTTP_URL"}
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Name) and n.value.id in aliases:
            aliases.update(t.id for t in n.targets if isinstance(t, ast.Name))
    sites = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.keyword) and n.arg == "webhook_url" and isinstance(n.value, ast.Name)
        and n.value.id in aliases
    ]
    return imported and bool(sites), f"import={imported}、实参行={sorted(sites)}"


def refused_url_shape(text: str) -> tuple[bool, str]:
    """NR-9-a 的判据本体（提出成函数，才能用内存样本反证——见 TEXT_PROBES）。"""
    m = re.search(r'REFUSED_HTTP_URL\s*=\s*"([^"]+)"', text)
    val = m.group(1) if m else None
    return bool(m) and str(val).startswith("http://127.0.0.1:1/"), f"值={val!r}"


def alias_only(text: str) -> tuple[bool, str]:
    """NR-9-c 的判据：旧常量收敛成 `REFUSED_HTTP_URL` 的别名，且本文件不再自带字面量。"""
    alias_line = next((i for i, line in enumerate(text.splitlines(), 1) if line == "_REFUSED_WEBHOOK_URL = REFUSED_HTTP_URL"), None)
    ok = "_REFUSED_WEBHOOK_URL = REFUSED_HTTP_URL" in text and REFUSED_URL_LITERAL not in text
    return ok, f"别名行=:{alias_line}｜自带字面量={REFUSED_URL_LITERAL in text}"


REFUSED_URL_LITERAL = '"http://127.0.0.1:1/bothot-hook-no-listener"'

SMOKE_CASE = "test_ask_real_full_chain_smoke"


def smoke_guard_shape(text: str) -> tuple[bool, str]:
    """NR-10-a 的判据：冒烟用例的**首条可执行语句**就是「未配置 DSN → skip」守卫。

    位置很关键：守卫若落在引擎构造之后，未配置时先在 try 外抛错，pytest 报 error 而非 skip。
    """
    tree = ast.parse(text)
    target = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == SMOKE_CASE), None
    )
    if target is None:
        return False, f"找不到 {SMOKE_CASE}"
    first = first_executable(target.body)
    txt = ast.unparse(first) if first is not None else ""
    detail = f"首条可执行语句={type(first).__name__ if first else '无'} :{getattr(first, 'lineno', 0)}"
    if not (isinstance(first, ast.If) and "_PG_URL_SOURCE" in txt and re.search(r"(['\"])unset\1", txt)):
        return False, detail + "（首行不是 unset 守卫）"
    ok = "pytest.skip(SKIP_UNSET_REASON)" in txt
    return ok, detail + ("（守卫体内已 skip）" if ok else "（守卫体内未 skip）")


def guard_symbols_imported(text: str) -> tuple[bool, str]:
    """NR-10-b 的判据：守卫用到的两个符号确实从 conftest 导入了（否则守卫自身 NameError）。"""
    line = next((ln for ln in text.splitlines() if ln.startswith("from conftest import")), "")
    ok = "_PG_URL_SOURCE" in line and "SKIP_UNSET_REASON" in line
    return ok, f"import 行={line!r}"


def main() -> int:
    src = CONF.read_text(encoding="utf-8")
    prefix_mod = load_sibling("prove_dsn_policy")
    ns = prefix_mod.exec_prefix(CONF, {})
    seed = {
        "os": os,
        "pytest": type("_P", (), {"fixture": lambda *a, **k: (lambda f: f), "MonkeyPatch": object}),
        "_PROXY_ENV_VARS": ns["_PROXY_ENV_VARS"],
        "NO_PROXY_ISOLATION_VALUE": ns["NO_PROXY_ISOLATION_VALUE"],
        # 夹具本体不引用它，但变异体（NR-7 的捕手）会引用；缺这一项会让变异体抛 NameError，
        # 于是「夹具误删 DSN」这个缺陷被 NameError 掩盖成 NR-4/NR-5 的红。
        "_TEST_PG_ENV_VAR": VAR,
    }
    fixture = exec_fixture(src, seed)

    # ── NR-1/NR-2：装饰器口径（autouse 必须为 True，scope 必须为函数级）────────────
    tree = ast.parse(src)
    fn = fixture_node(tree)
    assert fn is not None
    kw = decorator_kwargs(fn)
    check("NR-1 夹具带 @pytest.fixture(autouse=True)", kw.get("autouse") == "True", f"装饰器关键字={kw or '无'}")
    check("NR-2 夹具为函数级 scope（缺省或 'function'）", kw.get("scope", '"function"') == '"function"',
          f"scope={kw.get('scope', '缺省')}")

    # ── NR-3：不打断 DSN 广播（广播语句必须在夹具定义之前）───────────────────────
    broadcast_line = next(
        (n.lineno for n in tree.body
         if isinstance(n, ast.Assign) and ast.unparse(n).startswith("os.environ[_TEST_PG_ENV_VAR]")),
        None,
    )
    check("NR-3 夹具定义在 DSN 广播之后（不改广播语义）",
          broadcast_line is not None and fn.lineno > broadcast_line,
          f"广播 :{broadcast_line}、夹具 :{fn.lineno}")

    # ── NR-4：真执行——脏环境调用后代理全清、NO_PROXY 为契约值 ────────────────────
    with sandbox():
        for name in PROXY_VARS:
            os.environ[name] = POST_UNDO_HTTP_PROXY
        os.environ["NO_PROXY"] = _HOST_NO_PROXY
        mp = FakeMonkeyPatch()
        fixture(mp)  # ty: ignore[not-callable]
        leaked = [n for n in PROXY_VARS if n in os.environ]
        np_val, np_low = os.environ.get("NO_PROXY"), os.environ.get("no_proxy")
        mp.undo()
        # 取样必须在 sandbox 退出**之前**：`sandbox.__exit__` 自己会把环境还原一遍，
        # 若在块外断言，测到的是 sandbox 的还原而不是夹具 undo 的还原——那条断言永远不可能红（G-23）。
        post_undo = (
            os.environ.get("NO_PROXY"),
            os.environ.get("no_proxy"),
            os.environ.get("HTTP_PROXY"),
        )
    check("NR-4-a 脏环境下 6 个代理变量被清空", leaked == [], f"残留={leaked}")
    check("NR-4-b NO_PROXY 与 no_proxy 均写成契约值（win32 上两键折叠，小写那一半由 NR-14 兜）",
          np_val == EXPECTED_NO_PROXY and np_low == EXPECTED_NO_PROXY,
          f"NO_PROXY={np_val!r} no_proxy={np_low!r}（期望 {EXPECTED_NO_PROXY!r}）")
    check("NR-6 undo() 后宿主原貌恢复（夹具经 monkeypatch 而非直写 os.environ）",
          post_undo == (_HOST_NO_PROXY, POST_UNDO_NO_PROXY, POST_UNDO_HTTP_PROXY),
          f"undo 后 NO_PROXY={post_undo[0]!r} no_proxy={post_undo[1]!r} HTTP_PROXY={post_undo[2]!r}"
          f"｜宿主原貌 = {_HOST_NO_PROXY!r} / {POST_UNDO_NO_PROXY!r} / 代理 URL（win32 大小写合并，见常量注释）")

    # ── NR-5：干净环境调用不得抛（delenv 必须 raising=False）──────────────────────
    with sandbox():
        try:
            exec_fixture(src, seed)(FakeMonkeyPatch())  # ty: ignore[operator]
            clean_ok, err = True, ""
        except Exception as exc:  # noqa: BLE001 - 反证目标就是捕获任何异常形态
            clean_ok, err = False, f"{type(exc).__name__}: {exc}"
    check("NR-5 无代理的干净环境调用夹具不抛异常", clean_ok, err or "delenv(raising=False) 生效")

    # ── NR-7：夹具不得波及 DSN 广播值 ───────────────────────────────────────────
    with sandbox():
        os.environ[VAR] = "postgresql+psycopg://x:y@127.0.0.1:5547/z"
        exec_fixture(src, seed)(FakeMonkeyPatch())  # ty: ignore[operator]
        dsn_kept = os.environ.get(VAR)
    check("NR-7 清理代理不影响 AIDEANBOT_TEST_PG_DSN", dsn_kept == "postgresql+psycopg://x:y@127.0.0.1:5547/z", f"夹具后={dsn_kept!r}")

    # ── NR-8/NR-9：同形端口假设清零 + 地址常量单点 ──────────────────────────────
    tree_texts = tests_tree_texts()
    hits = literal_hits(tree_texts, "localhost:9999")
    check("NR-8 tests 全树无 localhost:9999 字面量", hits == [], f"命中={hits}")

    net_src = (TESTS / "fixtures" / "net.py").read_text(encoding="utf-8")
    ok_a, why_a = refused_url_shape(net_src)
    check("NR-9-a fixtures/net.py 导出 REFUSED_HTTP_URL 且端口为 1", ok_a, why_a)
    bad, report = [], []
    for fname in CONSUMERS:
        ok, why = webhook_url_wired_to_constant((TESTS / fname).read_text(encoding="utf-8"))
        report.append(f"{fname}:{why}")
        if not ok:
            bad.append(fname)
    check(f"NR-9-b {len(CONSUMERS)} 个消费方均把该常量接到 webhook_url 实参上（AST）", not bad,
          f"未接线={bad or '无'}｜" + " ".join(report))
    w3 = (TESTS / "test_w3_push_scheduler.py").read_text(encoding="utf-8")
    ok_c, why_c = alias_only(w3)
    check("NR-9-c test_w3 旧常量收敛为别名（单一真值：本文件不再自带 URL 字面量）", ok_c, why_c)

    # ── NR-10：chat_sse 冒烟的未配置守卫（AST 位置断言）──────────────────────────
    sse_src = (TESTS / "test_chat_sse.py").read_text(encoding="utf-8")
    ok_10a, why_10a = smoke_guard_shape(sse_src)
    check("NR-10-a 冒烟首行守卫：未配置 DSN → skip 而非 error", ok_10a, why_10a)
    ok_10b, why_10b = guard_symbols_imported(sse_src)
    check("NR-10-b 守卫所需符号已从 conftest 导入", ok_10b, why_10b)

    # ── NR-11/NR-12：陈旧注释与新用例结构 ──────────────────────────────────────
    stale = literal_hits(tree_texts, "conftest 警告")
    check("NR-11 「见 conftest 警告」陈旧注释清零", stale == [], f"残留={stale}")

    # 直接按路径读，不用 tree_texts 的键——relative_to 的分隔符随平台变（win32 反斜杠、CI 正斜杠），
    # 拿它当字典键会让本脚本在非 win32 上 KeyError。
    layout = isolation_case_layout((TESTS / "test_env_isolation.py").read_text(encoding="utf-8"))
    check("NR-12-a test_env_isolation 有 3 条用例", layout["a"][0], layout["a"][1])
    check("NR-12-b 每条用例至少 1 个 assert（无空断言）", layout["b"][0], layout["b"][1])
    check("NR-12-c 宿主代理快照在模块级、用例定义之前（收集期即夹具运行前）", layout["c"][0], layout["c"][1])

    # ── NR-13：conftest 侧常量的契约下限 ────────────────────────────────────────
    check("NR-13-a _PROXY_ENV_VARS 覆盖大小写 6 个键",
          tuple(ns["_PROXY_ENV_VARS"]) == PROXY_VARS, f"实测={tuple(ns['_PROXY_ENV_VARS'])}")
    check("NR-13-b NO_PROXY_ISOLATION_VALUE 含回环地址",
          "127.0.0.1" in ns["NO_PROXY_ISOLATION_VALUE"] and ns["NO_PROXY_ISOLATION_VALUE"] == EXPECTED_NO_PROXY,
          f"实测={ns['NO_PROXY_ISOLATION_VALUE']!r}")

    # ── NR-14：两种拼写各以「字面量名 + 契约值实参」成对写入（win32 行为面分辨不了的那一半）──
    paired, pair_detail = no_proxy_pairings(fn)
    check("NR-14 夹具对 NO_PROXY 与 no_proxy 的每一次写入都取契约值（配对判据，与平台无关）", paired, pair_detail)

    # ── NR-15：清理必须遍历 _PROXY_ENV_VARS 常量（单一真值来源，防「夹具与常量脱钩」漂移）──
    wired, wired_detail = delenv_loop_wired(fn, tree)
    check("NR-15 清理循环以 _PROXY_ENV_VARS 为迭代源且 delenv(循环变量, raising=False)", wired, wired_detail)

    # ── NR-16：运行期哨兵——往常量表加一项，夹具必须跟着删（结构判据 NR-15 的盲区）────────
    # 捕手来自第四轮复审 P-3 的反例：把「真接线」的循环塞进 `if False:`、活路径改硬写同值元组
    # ⇒ 结构判据照绿（那个循环确实还在文件里），但夹具与常量已经脱钩。
    # 只有「改常量的运行期值，看夹具的行为跟不跟」能分辨这两种形态。
    sentinel = SENTINEL_VAR
    with sandbox():
        os.environ[sentinel] = POST_UNDO_HTTP_PROXY
        mp16 = FakeMonkeyPatch()
        try:
            exec_fixture(src, {**seed, "_PROXY_ENV_VARS": (*tuple(ns["_PROXY_ENV_VARS"]), sentinel)})(mp16)  # ty: ignore[operator]
            survived = os.environ.get(sentinel)
            err = ""
        except Exception as exc:  # noqa: BLE001
            survived, err = None, f"{type(exc).__name__}: {exc}"
        mp16.undo()
        os.environ.pop(sentinel, None)
    check(
        "NR-16 运行期往常量表追加一项，夹具跟着删除它（夹具读常量而非抄一份）",
        survived is None and not err,
        f"哨兵残留={survived!r}｜异常={err or '无'}",
    )

    print("\n".join(CHECKS))
    for line in FAILURES:
        print(line)
    print(f"\n合计 PASS={len(CHECKS)} FAIL={len(FAILURES)}")
    if FAILURES:
        print("结论：STEP-00R 测试侧收口未达成——见上方 FAIL。")
        return 1
    print("结论：代理隔离夹具真实执行有效、同形端口假设清零；"
          "chat_sse 冒烟的首行守卫按 AST 位置判定为「文本层就位」（该用例本身未执行，见 H-1）。")
    print("边界（刻意不由本脚本判定）：test_env_isolation.py 的三条用例需 venv+httpx 真实运行；"
          "连库全量 failed=0 需隔离 PG——均交 STEP-00R S0R.1.3/S0R.3.2（人工/有依赖环境）。")
    return 0


MUTANTS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("去掉 autouse", "@pytest.fixture(autouse=True)", "@pytest.fixture", ("NR-1",)),
    ("删掉 delenv 循环体", "        monkeypatch.delenv(_name, raising=False)", "        pass", ("NR-4-a", "NR-15")),
    ("delenv 改 raising=True", "monkeypatch.delenv(_name, raising=False)", "monkeypatch.delenv(_name, raising=True)", ("NR-5",)),
    ("NO_PROXY 值去掉回环", 'NO_PROXY_ISOLATION_VALUE = "127.0.0.1,localhost,::1"', 'NO_PROXY_ISOLATION_VALUE = "localhost"', ("NR-4-b", "NR-13-b")),
    ("夹具直写 os.environ 而非经 monkeypatch", 'monkeypatch.setenv("NO_PROXY", NO_PROXY_ISOLATION_VALUE)',
     'os.environ["NO_PROXY"] = NO_PROXY_ISOLATION_VALUE', ("NR-6",)),
    # win32 上删掉小写那行，行为观测（NR-4-b）不会红——NR-14 是它唯一的捕手
    ("夹具不再写小写 no_proxy", 'monkeypatch.setenv("no_proxy", NO_PROXY_ISOLATION_VALUE)', "pass", ("NR-14",)),
    # 配对判据的捕手：大写那遍写了错值，但小写那遍随后把同一个键覆写成契约值
    # ⇒ win32 上 NR-4-b 仍绿（键折叠、后写覆盖先写），只有 NR-14 能红
    ("大写 NO_PROXY 写了非契约值（小写那遍把它盖回来）", 'monkeypatch.setenv("NO_PROXY", NO_PROXY_ISOLATION_VALUE)',
     'monkeypatch.setenv("NO_PROXY", "localhost")', ("NR-14",)),
    # 行为面（NR-4-a）预设的是本脚本自己抄的清单，所以「夹具改成硬写六个字面量」在当下不会红；
    # 将来常量新增一项而夹具没跟上就无人报警 ⇒ NR-15/NR-16 是唯一的捕手
    ("清理循环与 _PROXY_ENV_VARS 常量脱钩", "for _name in _PROXY_ENV_VARS:",
     'for _name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):',
     ("NR-15", "NR-16")),
    # 把常量整个删掉：exec 前缀时 KeyError ⇒ 必须由 evaluate 兜住并判红（NR-13-a/NR-15），
    # 不能让 harness 自己崩掉（崩了就没有「哪条断言红」的可核对信号）
    ("删掉 _PROXY_ENV_VARS 常量定义",
     '_PROXY_ENV_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")',
     "pass", ("NR-13-a", "NR-15")),
    # ── 第四轮补：evaluate() 此前只重放 NR-1/4/5/6/13/14/15，其余 conftest 判据是隐形的 ──
    ('夹具 scope 改成 "session"（autouse 仍是 True，只有 NR-2 能红）',
     "@pytest.fixture(autouse=True)", '@pytest.fixture(autouse=True, scope="session")', ("NR-2",)),
    ("广播行被改名/挪走（夹具定义不再晚于广播）",
     "os.environ[_TEST_PG_ENV_VAR] = PG_URL", "_UNUSED_BROADCAST = PG_URL", ("NR-3",)),
    ("夹具顺手删掉 DSN 变量（把广播值清了，连库配置消失）",
     'monkeypatch.setenv("NO_PROXY", NO_PROXY_ISOLATION_VALUE)',
     'monkeypatch.delenv(_TEST_PG_ENV_VAR, raising=False)\n    monkeypatch.setenv("NO_PROXY", NO_PROXY_ISOLATION_VALUE)',
     ("NR-7",)),
    # 配对判据 v2 的漏检：同名「先好后坏」双写，setdefault 只记第一条 ⇒ 曾经全绿
    ("同一拼写好写之后追加坏写（win32 上后写覆写先写）",
     'monkeypatch.setenv("NO_PROXY", NO_PROXY_ISOLATION_VALUE)',
     'monkeypatch.setenv("NO_PROXY", NO_PROXY_ISOLATION_VALUE)\n    monkeypatch.setenv("NO_PROXY", "localhost")',
     ("NR-14",)),
    # 第四轮 P-2：坏写藏在平台守卫里，win32 上根本不执行 ⇒ 行为面看不见，只有结构面能红
    ("平台守卫后的坏写（Linux 上隔离失效，win32 行为面不可观测）",
     'monkeypatch.setenv("no_proxy", NO_PROXY_ISOLATION_VALUE)',
     'monkeypatch.setenv("no_proxy", NO_PROXY_ISOLATION_VALUE)\n'
     '    if os.name != "nt":\n        monkeypatch.setenv("NO_PROXY", "evil.example")',
     ("NR-14",)),
    # 第四轮 P-3：真接线循环留在 `if False:` 里（结构判据照绿），活路径改硬写同值元组
    ("真接线循环塞进 if False、活路径改硬写（结构判据的盲区）",
     "    for _name in _PROXY_ENV_VARS:\n        monkeypatch.delenv(_name, raising=False)\n",
     "    if False:\n        for _name in _PROXY_ENV_VARS:\n            monkeypatch.delenv(_name, raising=False)\n"
     '    for _n in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):\n'
     "        monkeypatch.delenv(_n, raising=False)\n",
     ("NR-16",)),
)


# 第三条反证通道（第四轮新增，方向相反）：**等价重构必须保持全绿**。
# 前两条证明「改坏会红」，这一条证明「改写法不会假红」——判据若把合法写法也判红，
# 门禁就会被人当成噪声关掉，而这类脆性是用 `setenv(name=..., value=...)` 这类
# 完全等价的写法实测出来的（复审实测：修之前 red=['NR-14']，修之后 red=[]）。
EQUIV_REFACTORINGS: tuple[tuple[str, str, str], ...] = (
    ("setenv 名与值都改关键字实参", 'monkeypatch.setenv("NO_PROXY", NO_PROXY_ISOLATION_VALUE)',
     'monkeypatch.setenv(name="NO_PROXY", value=NO_PROXY_ISOLATION_VALUE)'),
    ("delenv 的 raising 改位置实参", "monkeypatch.delenv(_name, raising=False)", "monkeypatch.delenv(_name, False)"),
    ("delenv 名与 raising 都改关键字", "monkeypatch.delenv(_name, raising=False)",
     "monkeypatch.delenv(name=_name, raising=False)"),
    ("迭代源加 list() 包装", "for _name in _PROXY_ENV_VARS:", "for _name in list(_PROXY_ENV_VARS):"),
)


# 第二条反证通道：读**其它真实文件**的判据（NR-8、NR-9-a/b/c、NR-10-a/b、NR-11、NR-12）
# 不能用「改 conftest」来变红，故改为对**内存中的样本源码**跑同一个判定函数——
# 基准必须成立、变异样本必须不成立，否则那条判据是空洞的（G-23）。
# 覆盖集与 main() 的判据一一对应；判据函数（refused_url_shape / alias_only /
# smoke_guard_shape / guard_symbols_imported / webhook_url_wired_to_constant /
# literal_hits / isolation_case_layout）都是从 main() 里提出来的同一份代码，不是抄本。
#
# NR-12 用的内存样本：三条用例 + 模块级代理快照，形状与 test_env_isolation.py 同构。
# 刻意不用真文件当基准（判据本身要读真文件，基准得由本脚本自己造），变异体靠字符串改写生成。
_ISO_BASE = (
    "_HOST_PROXY_VARS_AT_COLLECT: tuple[str, ...] = ()\n"
    "\n"
    "\n"
    "def test_a() -> None:\n"
    "    assert True\n"
    "\n"
    "\n"
    "async def test_b() -> None:\n"
    "    assert True\n"
    "\n"
    "\n"
    "async def test_c() -> None:\n"
    "    assert True\n"
)

# NR-10 用的内存样本：首行守卫 + 后续 import，形状与 test_chat_sse.py::test_ask_real_full_chain_smoke 同构。
_SMOKE_BASE = (
    "from conftest import PG_URL, SKIP_UNSET_REASON, _PG_URL_SOURCE\n"
    "\n"
    "\n"
    "async def test_ask_real_full_chain_smoke() -> None:\n"
    '    if _PG_URL_SOURCE == "unset":\n'
    "        pytest.skip(SKIP_UNSET_REASON)\n"
    "    import asyncio\n"
)
_SMOKE_LATE = (
    "from conftest import PG_URL, SKIP_UNSET_REASON, _PG_URL_SOURCE\n"
    "\n"
    "\n"
    "async def test_ask_real_full_chain_smoke() -> None:\n"
    "    import asyncio\n"
    '    if _PG_URL_SOURCE == "unset":\n'
    "        pytest.skip(SKIP_UNSET_REASON)\n"
)
_NET_BASE = 'REFUSED_HTTP_URL = "http://127.0.0.1:1/bothot-hook-no-listener"\n'
_ALIAS_BASE = "from fixtures.net import REFUSED_HTTP_URL\n\n_REFUSED_WEBHOOK_URL = REFUSED_HTTP_URL\n"

TEXT_PROBES: tuple[tuple[str, object, object, object], ...] = (
    (
        "NR-9-b 实参退回 URL 字面量",
        'from fixtures.net import REFUSED_HTTP_URL\n\nf = P(webhook_url=REFUSED_HTTP_URL)\n',
        'from fixtures.net import REFUSED_HTTP_URL\n\nf = P(webhook_url="http://127.0.0.1:1/x")\n',
        lambda t: webhook_url_wired_to_constant(t)[0],
    ),
    (
        "NR-9-b 只 import 从不接到形参",
        'from fixtures.net import REFUSED_HTTP_URL\n\nf = P(webhook_url=REFUSED_HTTP_URL)\n',
        'from fixtures.net import REFUSED_HTTP_URL\n\nEXPECTED = REFUSED_HTTP_URL\n',
        lambda t: webhook_url_wired_to_constant(t)[0],
    ),
    (
        "NR-9-b 丢掉 import 行",
        'from fixtures.net import REFUSED_HTTP_URL\n\nf = P(webhook_url=REFUSED_HTTP_URL)\n',
        'f = P(webhook_url=REFUSED_HTTP_URL)\n',
        lambda t: webhook_url_wired_to_constant(t)[0],
    ),
    (
        "NR-9-b 经模块级别名接线（test_w3 形态）",
        'from fixtures.net import REFUSED_HTTP_URL\n\n_A = REFUSED_HTTP_URL\n\nf = P(webhook_url=_A)\n',
        'from fixtures.net import REFUSED_HTTP_URL\n\n_A = "http://x"\n\nf = P(webhook_url=_A)\n',
        lambda t: webhook_url_wired_to_constant(t)[0],
    ),
    # ── 第三轮补：NR-8/NR-11/NR-12 原先「0 命中就绿」却无通道证明它们能红 ──────────
    (
        "NR-8 用例退回 localhost:9999 字面量",
        {"a.py": "URL = REFUSED_HTTP_URL\n", "b.py": "URL = REFUSED_HTTP_URL\n"},
        {"a.py": "URL = REFUSED_HTTP_URL\n", "b.py": 'URL = "http://localhost:9999/hook"\n'},
        lambda texts: literal_hits(texts, "localhost:9999") == [],
    ),
    (
        "NR-11 陈旧注释「见 conftest 警告」回潮",
        {"t.py": "# 未设则 skip，原因见 conftest SKIP_UNSET_REASON\n"},
        {"t.py": "# 未设则 skip，原因见 conftest 警告\n"},
        lambda texts: literal_hits(texts, "conftest 警告") == [],
    ),
    (
        "NR-12-a 用例数退化为 2 条",
        _ISO_BASE,
        _ISO_BASE.replace("async def test_c() -> None:\n    assert True\n", ""),
        lambda t: isolation_case_layout(t)["a"][0],
    ),
    (
        "NR-12-b 某条用例一条 assert 都没有",
        _ISO_BASE,
        _ISO_BASE.replace("def test_a() -> None:\n    assert True", "def test_a() -> None:\n    pass"),
        lambda t: isolation_case_layout(t)["b"][0],
    ),
    (
        "NR-12-c 宿主代理快照移到用例之后（收集期原貌丢失）",
        _ISO_BASE,
        _ISO_BASE.replace("_HOST_PROXY_VARS_AT_COLLECT: tuple[str, ...] = ()\n\n\n", "")
        + "_HOST_PROXY_VARS_AT_COLLECT: tuple[str, ...] = ()\n",
        lambda t: isolation_case_layout(t)["c"][0],
    ),
    # ── 第四轮补：NR-9-a/NR-9-c/NR-10-a/NR-10-b 此前只读真实文件、没有任何反证通道 ────
    # （复审列出「无通道证明能红」的判据即这七条中的四条；另三条 NR-2/NR-3/NR-7 改由
    #   evaluate() 重放，见 MUTANTS 末四条。）
    (
        "NR-9-a 地址常量退回 9999 端口假设",
        _NET_BASE,
        'REFUSED_HTTP_URL = "http://localhost:9999/bothot-hook-no-listener"\n',
        lambda t: refused_url_shape(t)[0],
    ),
    (
        "NR-9-a 常量定义整行被删",
        _NET_BASE,
        "X = 1\n",
        lambda t: refused_url_shape(t)[0],
    ),
    (
        "NR-9-c 别名退回自带 URL 字面量（单点被破）",
        _ALIAS_BASE,
        _ALIAS_BASE.replace(
            "_REFUSED_WEBHOOK_URL = REFUSED_HTTP_URL",
            '_REFUSED_WEBHOOK_URL = "http://127.0.0.1:1/bothot-hook-no-listener"',
        ),
        lambda t: alias_only(t)[0],
    ),
    (
        "NR-9-c 别名行整体消失",
        _ALIAS_BASE,
        "from fixtures.net import REFUSED_HTTP_URL\n",
        lambda t: alias_only(t)[0],
    ),
    (
        "NR-10-a 守卫挪到 import asyncio 之后（未配置时报 error 而非 skip）",
        _SMOKE_BASE,
        _SMOKE_LATE,
        lambda t: smoke_guard_shape(t)[0],
    ),
    (
        "NR-10-a 守卫条件在、体内不 skip",
        _SMOKE_BASE,
        _SMOKE_BASE.replace("pytest.skip(SKIP_UNSET_REASON)", "pass"),
        lambda t: smoke_guard_shape(t)[0],
    ),
    (
        "NR-10-a 用例函数被改名",
        _SMOKE_BASE,
        _SMOKE_BASE.replace("test_ask_real_full_chain_smoke", "test_ask_real_smoke"),
        lambda t: smoke_guard_shape(t)[0],
    ),
    (
        "NR-10-b 导入行少了 SKIP_UNSET_REASON",
        _SMOKE_BASE,
        _SMOKE_BASE.replace("PG_URL, SKIP_UNSET_REASON, _PG_URL_SOURCE", "PG_URL, _PG_URL_SOURCE"),
        lambda t: guard_symbols_imported(t)[0],
    ),
    (
        "NR-10-b 导入行整体缺失（守卫自身 NameError）",
        _SMOKE_BASE,
        _SMOKE_BASE.replace("from conftest import PG_URL, SKIP_UNSET_REASON, _PG_URL_SOURCE\n\n\n", ""),
        lambda t: guard_symbols_imported(t)[0],
    ),
)


def self_test() -> int:
    """G-23 反证：每个变异体都必须让对应断言变红，否则那条断言是空洞的。"""
    src = CONF.read_text(encoding="utf-8")
    rc = 0
    # 基准必须先全绿：变异体若「红了」但其实基准也红，那个 OK 就没有意义。
    baseline = evaluate(src)
    if baseline:
        print(f"BAD 基准（未变异 conftest）就有红项：{sorted(baseline)}——self-test 的结论不可用，先修 main()")
        rc = 1
    for label, needle, replacer, expected_red in MUTANTS:
        if needle not in src:
            print(f"BAD {label}：conftest 里找不到 {needle!r}，变异体构造失败")
            rc = 1
            continue
        red = evaluate(src.replace(needle, replacer, 1))
        missing = [name for name in expected_red if name not in red]
        ok = not missing
        print(f"{'OK ' if ok else 'BAD'} {label} → 应变红 {list(expected_red)}｜实际红项={sorted(red) or ['（无，断言空洞！）']}")
        if not ok:
            rc = 1
    for label, base, mutant, judge in TEXT_PROBES:
        base_ok, mutant_ok = bool(judge(base)), bool(judge(mutant))
        ok = base_ok and not mutant_ok
        print(f"{'OK ' if ok else 'BAD'} {label}：基准={base_ok}（应 True）｜变异体={mutant_ok}（应 False）")
        if not ok:
            rc = 1
    for label, needle, replacer in EQUIV_REFACTORINGS:
        if needle not in src:
            print(f"BAD {label}：conftest 里找不到 {needle!r}")
            rc = 1
            continue
        red = evaluate(src.replace(needle, replacer, 1))
        ok = red == []
        print(f"{'OK ' if ok else 'BAD'} 等价重构 {label} → 应变 0 红｜实际红项={sorted(red) or '（无）'}")
        if not ok:
            rc = 1
    print("SELF-TEST " + (
        f"PASS：{len(MUTANTS)} 个 conftest 变异体各自让对应断言变红 + {len(TEXT_PROBES)} 个源码探针敏感"
        f" + {len(EQUIV_REFACTORINGS)} 个等价重构不假红"
        if rc == 0 else "FAIL"))
    return rc


def evaluate(conftest_src: str) -> list[str]:
    """在变异源码上重跑 conftest 侧全部可重放判定，返回失败项标签。

    与 main() 的分工：main() 打印人读的 PASS/FAIL；evaluate() 是 self-test 的载体，
    必须把 main() 里**每一条只依赖 conftest 文本**的判据都重放一遍——否则那条判据
    在反证通道里是隐形的，「没有变异体能让它红」这件事就没人发现（第四轮复审 P-6 即此）。
    依赖其它文件的判据（NR-8/NR-9/NR-10/NR-11/NR-12）改由 TEXT_PROBES 喂内存样本反证。
    """
    red: list[str] = []
    tree = ast.parse(conftest_src)
    fn = fixture_node(tree)
    prefix_mod = load_sibling("prove_dsn_policy")
    ns = prefix_mod.exec_prefix(Path("apps/api/tests/conftest.py"), {}, src_text=conftest_src)
    # 变异体可能把常量本身删掉（复审三-4 的 `del _PROXY_ENV_VARS` 形态）：那正是 NR-13-a/NR-15
    # 该报的红，不能让 harness 先 KeyError 崩掉——崩了就没有「哪条断言红了」这个可核对的信号。
    try:
        proxy_const = tuple(ns["_PROXY_ENV_VARS"])
    except KeyError:
        proxy_const = ()
        red.append("NR-13-a")
    try:
        iso_const = str(ns["NO_PROXY_ISOLATION_VALUE"])
    except KeyError:
        iso_const = ""
        red.append("NR-13-b")
    seed = {
        "os": os,
        "pytest": type("_P", (), {"fixture": lambda *a, **k: (lambda f: f), "MonkeyPatch": object}),
        "_PROXY_ENV_VARS": proxy_const,
        "NO_PROXY_ISOLATION_VALUE": iso_const,
        "_TEST_PG_ENV_VAR": VAR,
    }
    kw = decorator_kwargs(fn) if fn is not None else {}
    if kw.get("autouse") != "True":
        red.append("NR-1")
    if kw.get("scope", '"function"') != '"function"':
        red.append("NR-2")
    # NR-3：夹具必须定义在 DSN 广播之后（否则 autouse 夹具会把广播吃掉）
    broadcast_line = next(
        (
            n.lineno
            for n in tree.body
            if isinstance(n, ast.Assign) and ast.unparse(n).startswith("os.environ[_TEST_PG_ENV_VAR]")
        ),
        None,
    )
    if broadcast_line is None or fn is None or fn.lineno <= broadcast_line:
        red.append("NR-3")
    with sandbox():
        for name in PROXY_VARS:
            os.environ[name] = POST_UNDO_HTTP_PROXY
        os.environ["NO_PROXY"] = _HOST_NO_PROXY
        try:
            fixture = exec_fixture(conftest_src, seed)
            mp = FakeMonkeyPatch()
            fixture(mp)  # ty: ignore[not-callable]
            if [n for n in PROXY_VARS if n in os.environ]:
                red.append("NR-4-a")
            if os.environ.get("NO_PROXY") != EXPECTED_NO_PROXY or os.environ.get("no_proxy") != EXPECTED_NO_PROXY:
                red.append("NR-4-b")
            mp.undo()
            if (os.environ.get("NO_PROXY"), os.environ.get("no_proxy"), os.environ.get("HTTP_PROXY")) != (
                _HOST_NO_PROXY,
                POST_UNDO_NO_PROXY,
                POST_UNDO_HTTP_PROXY,
            ):
                red.append("NR-6")
        except Exception as exc:  # noqa: BLE001
            red.append(f"NR-4-a(异常 {type(exc).__name__})")
    with sandbox():
        try:
            exec_fixture(conftest_src, seed)(FakeMonkeyPatch())  # ty: ignore[operator]
        except KeyError:
            red.append("NR-5")
        except Exception:  # noqa: BLE001
            red.append("NR-5")
    if "127.0.0.1" not in iso_const and "NR-13-b" not in red:
        red.append("NR-13-b")
    # NR-7：夹具只许动代理变量，不许波及 DSN 广播值
    with sandbox():
        os.environ[VAR] = "postgresql+psycopg://x:y@127.0.0.1:5547/z"
        try:
            exec_fixture(conftest_src, seed)(FakeMonkeyPatch())  # ty: ignore[operator]
        except Exception:  # noqa: BLE001 - 崩了由 NR-4/NR-5 报，这里只判「DSN 是否还在」
            pass
        if os.environ.get(VAR) != "postgresql+psycopg://x:y@127.0.0.1:5547/z":
            red.append("NR-7")
    # NR-16：运行期往常量表追加哨兵，夹具必须跟着删（否则说明它抄了一份而不是读常量）
    with sandbox():
        os.environ[SENTINEL_VAR] = POST_UNDO_HTTP_PROXY
        mp = FakeMonkeyPatch()
        try:
            exec_fixture(conftest_src, {**seed, "_PROXY_ENV_VARS": (*proxy_const, SENTINEL_VAR)})(mp)  # ty: ignore[operator]
            if SENTINEL_VAR in os.environ:
                red.append("NR-16")
        except Exception as exc:  # noqa: BLE001
            red.append(f"NR-16(异常 {type(exc).__name__})")
        mp.undo()
        os.environ.pop(SENTINEL_VAR, None)
    if fn is not None:
        if not no_proxy_pairings(fn)[0]:
            red.append("NR-14")
        if not delenv_loop_wired(fn, tree)[0]:
            red.append("NR-15")
    return red


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    sys.exit(main())
