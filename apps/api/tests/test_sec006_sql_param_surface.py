"""STEP-49 S49.2（SEC-006 后半）：SQL 参数化面 AST 门。

判据：`apps/api/app/**/*.py` 里凡 `text(...)` / `sa_text(...)` / `sqlalchemy.text(...)`
的首个位置实参是——
  ① f-string（JoinedStr）；
  ② `+` / `%` 拼接（BinOp）；
  ③ `.format(...)` 调用——
即记违规（运行时值有机会进 SQL 文本）。唯一放行形状：f-string 内**只**插值
「本模块顶层全大写常量名」，且 (文件, 常量名) 在 ALLOWLIST 里逐对登记
（现恰一对：process_heartbeat 的 TABLE_NAME——模块常量表名，非运行时值）。

判据本体是纯函数 `sql_param_violations(sources)`（可喂合成源码自测），文件扫描
只是它的驱动。自测负例见文件尾：合成 `text(f"...{user_input}")` 必须被抓。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1] / "app"

#: (相对路径 posix, 常量名) —— D-V21 规划卡 S49.2：允许表恰 1 条，多了须先改卡
ALLOWLIST: dict[str, set[str]] = {
    "services/process_heartbeat.py": {"TABLE_NAME"},
}

_TEXT_NAMES = {"text", "sa_text"}
_ALL_CAPS = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _is_text_call(node: ast.AST) -> bool:
    """text(...) / sa_text(...) / sqlalchemy.text(...) / <别名>.text(...)。"""
    if isinstance(node, ast.Name):
        return node.id in _TEXT_NAMES
    if isinstance(node, ast.Attribute):
        return node.attr in _TEXT_NAMES
    return False


def _module_toplevel_consts(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            for t in stmt.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            out.add(stmt.target.id)
    return out


def _violations_in(src: str, rel: str) -> list[str]:
    """一个源文件 ⇒ 违规描述清单（空 = 通过）。纯函数，可喂合成源码。"""
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [f"{rel}: 解析失败 ⇒ fail-closed（{exc}）"]
    consts = _module_toplevel_consts(tree)
    allowed = ALLOWLIST.get(rel, set())
    out: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _is_text_call(node.func)):
            continue
        arg = node.args[0] if node.args else None
        if arg is None:
            continue
        where = f"{rel}:{node.lineno}"
        if isinstance(arg, ast.JoinedStr):
            bad: list[str] = []
            for fv in arg.values:
                if not isinstance(fv, ast.FormattedValue):
                    continue
                v = fv.value
                if isinstance(v, ast.Name):
                    if not (_ALL_CAPS.match(v.id) and v.id in consts and v.id in allowed):
                        bad.append(v.id)
                else:
                    bad.append("<表达式>")
            if bad:
                out.append(f"{where}: text() 首参是 f-string，插值 {bad} 不在允许表内")
        elif isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add | ast.Mod):
            out.append(f"{where}: text() 首参是 {'+' if isinstance(arg.op, ast.Add) else '%'} 拼接")
        elif (
            isinstance(arg, ast.Call)
            and isinstance(arg.func, ast.Attribute)
            and arg.func.attr == "format"
        ):
            out.append(f"{where}: text() 首参是 .format() 调用")
    return out


def sql_param_violations(sources: dict[str, str]) -> tuple[list[str], int]:
    """{相对路径: 源码} ⇒ (违规清单, text 调用点总数)。判据本体。"""
    violations: list[str] = []
    calls = 0
    for rel, src in sorted(sources.items()):
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_text_call(node.func):
                calls += 1
        violations.extend(_violations_in(src, rel))
    return violations, calls


def _app_sources() -> dict[str, str]:
    return {
        str(p.relative_to(APP_ROOT)).replace("\\", "/"): p.read_text(encoding="utf-8")
        for p in sorted(APP_ROOT.rglob("*.py"))
    }


def test_allowlist_has_exactly_one_entry() -> None:
    """允许表恰 1 条（卡面 S49.2：多一条都是口径变化，须先改卡）。"""
    assert set(ALLOWLIST) == {"services/process_heartbeat.py"}
    assert ALLOWLIST["services/process_heartbeat.py"] == {"TABLE_NAME"}


def test_app_sql_surface_is_parameterized() -> None:
    """现仓库面：app/** 内不允许任何运行时值拼进 SQL 文本的入口。"""
    violations, calls = sql_param_violations(_app_sources())
    # 护栏口径（2026-10-24 现读）：AST 真实计数 12 处（grep 的 31 含 `richtext(` 一类
    # 字面误匹配，不能当判据）。地板取 10：扫描器失明（认不出 text 调用）时这里先红。
    assert calls >= 10, f"text() 调用点计数异常（{calls}）——扫描面失效"
    assert violations == [], "\n".join(violations)


def test_negative_fstring_with_runtime_value_is_caught() -> None:
    """自测负例①：合成 `text(f"...{user_input}")` ⇒ 必须抓到。"""
    src = "from sqlalchemy import text\n\ndef q(u):\n    return text(f\"SELECT * FROM t WHERE x = {u}\")\n"
    v, _ = sql_param_violations({"services/_synthetic.py": src})
    assert len(v) == 1 and "user_input" in v[0] or "u" in v[0], v
    assert any("_synthetic.py" in line for line in v), v


def test_negative_binop_and_format_are_caught() -> None:
    """自测负例②③：`+` 拼接与 .format() ⇒ 必须抓到。"""
    src = (
        "from sqlalchemy import text\n"
        "def q(u):\n"
        '    return text("SELECT * FROM t WHERE x = " + u)\n'
        "def r(u):\n"
        '    return text("SELECT * FROM t WHERE x = {}".format(u))\n'
    )
    v, _ = sql_param_violations({"services/_synthetic2.py": src})
    assert len(v) == 2, v
    assert any("拼接" in line for line in v), v
    assert any("format" in line for line in v), v


def test_allowed_shape_all_caps_const_in_allowlisted_file_passes() -> None:
    """正例：允许表内的 (文件, 常量) 形状放行——恰好是 process_heartbeat 的真身。"""
    real = _app_sources()["services/process_heartbeat.py"]
    v, _ = sql_param_violations({"services/process_heartbeat.py": real})
    assert v == [], v


def test_same_const_shape_outside_allowlist_is_caught() -> None:
    """负例④：同样只插全大写常量，但文件不在允许表 ⇒ 抓（防允许表被当成通配）。"""
    src = (
        "from sqlalchemy import text\n"
        "TABLE = \"t\"\n"
        "def q():\n"
        '    return text(f"SELECT 1 FROM {TABLE}")\n'
    )
    v, _ = sql_param_violations({"services/_not_allowed.py": src})
    assert len(v) == 1 and "TABLE" in v[0], v
