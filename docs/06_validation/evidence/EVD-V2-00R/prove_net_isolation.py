"""STEP-00R 机器证明：测试出站的代理隔离与同形脆弱点收口（纯 stdlib，不启服务、不装依赖）。

为什么不能 `import conftest`：按「本项目无需安装开发环境和依赖」约束，本机没有
sqlalchemy / httpx / dotenv（实测 `python -c "import httpx"` → ModuleNotFoundError），
而 `apps/api/tests/conftest.py` 在模块级 import 它们。此处沿用 EVD-V2-00/prove_dsn_policy.py
的机制：解析 AST、剔除三方 import、只执行前缀语句，再单独 exec `_isolate_proxy_env` 的
**当前函数体**（剥掉装饰器，注入按 pytest.MonkeyPatch 语义实现的替身）。被执行的是文件
里的真实代码，不是抄本——改了函数体，这里的结论就会变。

`--self-test` 提供 G-23 反证：把夹具改成 4 种「看起来还在但已失效」的变异体（去掉
autouse / 删掉 delenv 循环 / 换 raising=True / 换 NO_PROXY 值），逐条确认对应断言**变红**。
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
PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
CONSUMERS = (
    "test_alerting_drill.py",
    "test_bots_logs_filter.py",
    "test_wb_push_hardening.py",
    "test_w3_push_scheduler.py",
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


def main() -> int:
    src = CONF.read_text(encoding="utf-8")
    prefix_mod = load_sibling("prove_dsn_policy")
    ns = prefix_mod.exec_prefix(CONF, {})
    seed = {
        "os": os,
        "pytest": type("_P", (), {"fixture": lambda *a, **k: (lambda f: f), "MonkeyPatch": object}),
        "_PROXY_ENV_VARS": ns["_PROXY_ENV_VARS"],
        "NO_PROXY_ISOLATION_VALUE": ns["NO_PROXY_ISOLATION_VALUE"],
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
            os.environ[name] = "http://127.0.0.1:10808"
        os.environ["NO_PROXY"] = "internal.example"
        mp = FakeMonkeyPatch()
        fixture(mp)  # ty: ignore[not-callable]
        leaked = [n for n in PROXY_VARS if n in os.environ]
        np_val, np_low = os.environ.get("NO_PROXY"), os.environ.get("no_proxy")
        mp.undo()
        restored = os.environ.get("NO_PROXY"), os.environ.get("internal_present")
    check("NR-4-a 脏环境下 6 个代理变量被清空", leaked == [], f"残留={leaked}")
    check("NR-4-b NO_PROXY 与 no_proxy 均写成契约值",
          np_val == EXPECTED_NO_PROXY and np_low == EXPECTED_NO_PROXY,
          f"NO_PROXY={np_val!r} no_proxy={np_low!r}（期望 {EXPECTED_NO_PROXY!r}）")
    check("NR-6 undo() 后宿主原貌恢复（夹具不是永久改环境）",
          "NO_PROXY" not in os.environ, f"undo 后 NO_PROXY={os.environ.get('NO_PROXY')!r}")

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
    hits = sorted(str(p.relative_to(ROOT)) for p in TESTS.rglob("*.py") if "localhost:9999" in p.read_text(encoding="utf-8"))
    check("NR-8 tests 全树无 localhost:9999 字面量", hits == [], f"命中={hits}")

    net_src = (TESTS / "fixtures" / "net.py").read_text(encoding="utf-8")
    refused = re.search(r'REFUSED_HTTP_URL\s*=\s*"([^"]+)"', net_src)
    check("NR-9-a fixtures/net.py 导出 REFUSED_HTTP_URL 且端口为 1",
          bool(refused) and refused.group(1).startswith("http://127.0.0.1:1/"), f"值={refused.group(1) if refused else None!r}")
    consumers_ok, missing = True, []
    for fname in CONSUMERS:
        text = (TESTS / fname).read_text(encoding="utf-8")
        if "REFUSED_HTTP_URL" not in text or "from fixtures.net import" not in text:
            consumers_ok = False
            missing.append(fname)
    check("NR-9-b 4 个消费方均改为引用该常量", consumers_ok, f"未引用={missing}")
    w3 = (TESTS / "test_w3_push_scheduler.py").read_text(encoding="utf-8")
    check("NR-9-c test_w3 旧常量收敛为别名（单一真值）",
          "_REFUSED_WEBHOOK_URL = REFUSED_HTTP_URL" in w3 and "127.0.0.1:1/bothot-hook" not in w3.split("REFUSED_HTTP_URL")[-1],
          "见 tests/test_w3_push_scheduler.py:44 区")

    # ── NR-10：chat_sse 冒烟的未配置守卫（AST 位置断言）──────────────────────────
    sse = ast.parse((TESTS / "test_chat_sse.py").read_text(encoding="utf-8"))
    target = next((n for n in ast.walk(sse) if isinstance(n, ast.AsyncFunctionDef) and n.name == "test_ask_real_full_chain_smoke"), None)
    guard_ok, guard_detail = False, "找不到 test_ask_real_full_chain_smoke"
    if target is not None:
        first = first_executable(target.body)
        txt = ast.unparse(first) if first is not None else ""
        guard_detail = f"首条可执行语句={type(first).__name__ if first else '无'} :{getattr(first, 'lineno', 0)}"
        if isinstance(first, ast.If) and "_PG_URL_SOURCE" in txt and re.search(r"(['\"])unset\1", txt):
            guard_ok = "pytest.skip(SKIP_UNSET_REASON)" in txt
            guard_detail += "（守卫已就位）" if guard_ok else "（守卫体内未 skip）"
    sse_imports = (TESTS / "test_chat_sse.py").read_text(encoding="utf-8").splitlines()
    imported = next((ln for ln in sse_imports if ln.startswith("from conftest import")), "")
    check("NR-10-a 冒烟首行守卫：未配置 DSN → skip 而非 error", guard_ok, guard_detail)
    check("NR-10-b 守卫所需符号已从 conftest 导入",
          "_PG_URL_SOURCE" in imported and "SKIP_UNSET_REASON" in imported, f"import 行={imported!r}")

    # ── NR-11/NR-12：陈旧注释与新用例结构 ──────────────────────────────────────
    stale = sorted(str(p.relative_to(ROOT)) for p in TESTS.rglob("*.py") if "conftest 警告" in p.read_text(encoding="utf-8"))
    check("NR-11 「见 conftest 警告」陈旧注释清零", stale == [], f"残留={stale}")

    iso = ast.parse((TESTS / "test_env_isolation.py").read_text(encoding="utf-8"))
    cases = [n for n in iso.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")]
    assert_counts = {n.name: sum(isinstance(x, ast.Assert) for x in ast.walk(n)) for n in cases}
    # 快照只有在「任何用例定义之前」的模块级求值才等于收集期宿主环境；放进用例里就晚了。
    # 用 AnnAssign 声明（带类型标注）——两种赋值形态都要认，否则判定会因写法而假红。
    snap_line = next(
        (n.lineno for n in iso.body
         if isinstance(n, (ast.Assign, ast.AnnAssign)) and "_HOST_PROXY_VARS_AT_COLLECT" in ast.unparse(n)),
        None,
    )
    first_case_line = min((n.lineno for n in cases), default=0)
    snapshot_first = snap_line is not None and snap_line < first_case_line
    check("NR-12-a test_env_isolation 有 3 条用例", len(cases) == 3, f"用例={list(assert_counts)}")
    check("NR-12-b 每条用例至少 1 个 assert（无空断言）", all(c > 0 for c in assert_counts.values()), str(assert_counts))
    check("NR-12-c 宿主代理快照在模块级、用例定义之前（收集期即夹具运行前）", snapshot_first,
          f"快照 :{snap_line}、首个用例 :{first_case_line}")

    # ── NR-13：conftest 侧常量的契约下限 ────────────────────────────────────────
    check("NR-13-a _PROXY_ENV_VARS 覆盖大小写 6 个键",
          tuple(ns["_PROXY_ENV_VARS"]) == PROXY_VARS, f"实测={tuple(ns['_PROXY_ENV_VARS'])}")
    check("NR-13-b NO_PROXY_ISOLATION_VALUE 含回环地址",
          "127.0.0.1" in ns["NO_PROXY_ISOLATION_VALUE"] and ns["NO_PROXY_ISOLATION_VALUE"] == EXPECTED_NO_PROXY,
          f"实测={ns['NO_PROXY_ISOLATION_VALUE']!r}")

    print("\n".join(CHECKS))
    for line in FAILURES:
        print(line)
    print(f"\n合计 PASS={len(CHECKS)} FAIL={len(FAILURES)}")
    if FAILURES:
        print("结论：STEP-00R 测试侧收口未达成——见上方 FAIL。")
        return 1
    print("结论：代理隔离夹具真实执行有效、同形端口假设清零、chat_sse 守卫到位。")
    print("边界（刻意不由本脚本判定）：test_env_isolation.py 的三条用例需 venv+httpx 真实运行；"
          "连库全量 failed=0 需隔离 PG——均交 STEP-00R S0R.1.3/S0R.3.2（人工/有依赖环境）。")
    return 0


MUTANTS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("去掉 autouse", "@pytest.fixture(autouse=True)", "@pytest.fixture", ("NR-1",)),
    ("删掉 delenv 循环体", "        monkeypatch.delenv(_name, raising=False)", "        pass", ("NR-4-a",)),
    ("delenv 改 raising=True", "monkeypatch.delenv(_name, raising=False)", "monkeypatch.delenv(_name, raising=True)", ("NR-5",)),
    ("NO_PROXY 值去掉回环", 'NO_PROXY_ISOLATION_VALUE = "127.0.0.1,localhost,::1"', 'NO_PROXY_ISOLATION_VALUE = "localhost"', ("NR-4-b", "NR-13-b")),
)


def self_test() -> int:
    """G-23 反证：每个变异体都必须让对应断言变红，否则那条断言是空洞的。"""
    src = CONF.read_text(encoding="utf-8")
    rc = 0
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
    print("SELF-TEST " + ("PASS：4 个变异体各自让对应断言变红" if rc == 0 else "FAIL"))
    return rc


def evaluate(conftest_src: str) -> list[str]:
    """在变异源码上重跑 NR-1..NR-7 的关键判定，返回失败项标签。"""
    red: list[str] = []
    tree = ast.parse(conftest_src)
    fn = fixture_node(tree)
    prefix_mod = load_sibling("prove_dsn_policy")
    ns = prefix_mod.exec_prefix(Path("apps/api/tests/conftest.py"), {}, src_text=conftest_src)
    seed = {
        "os": os,
        "pytest": type("_P", (), {"fixture": lambda *a, **k: (lambda f: f), "MonkeyPatch": object}),
        "_PROXY_ENV_VARS": ns["_PROXY_ENV_VARS"],
        "NO_PROXY_ISOLATION_VALUE": ns["NO_PROXY_ISOLATION_VALUE"],
    }
    kw = decorator_kwargs(fn) if fn is not None else {}
    if kw.get("autouse") != "True":
        red.append("NR-1")
    with sandbox():
        for name in PROXY_VARS:
            os.environ[name] = "http://127.0.0.1:10808"
        os.environ["NO_PROXY"] = "internal.example"
        try:
            fixture = exec_fixture(conftest_src, seed)
            mp = FakeMonkeyPatch()
            fixture(mp)  # ty: ignore[not-callable]
            if [n for n in PROXY_VARS if n in os.environ]:
                red.append("NR-4-a")
            if os.environ.get("NO_PROXY") != EXPECTED_NO_PROXY or os.environ.get("no_proxy") != EXPECTED_NO_PROXY:
                red.append("NR-4-b")
        except Exception as exc:  # noqa: BLE001
            red.append(f"NR-4-a(异常 {type(exc).__name__})")
    with sandbox():
        try:
            exec_fixture(conftest_src, seed)(FakeMonkeyPatch())  # ty: ignore[operator]
        except KeyError:
            red.append("NR-5")
        except Exception:  # noqa: BLE001
            red.append("NR-5")
    if "127.0.0.1" not in ns["NO_PROXY_ISOLATION_VALUE"]:
        red.append("NR-13-b")
    return red


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    sys.exit(main())
