"""S3.4.1 残项证明：justoneapi.py:115 与 wellbyte.py:134 是「按构造不可达」的返回体。

判法：AST 扫 `_handle_response`，每个 `return None` 都必须被某一层 `if suppress_errors` 包住；
再核对 `query_work_list` 调用点没传 suppress_errors（默认 False）。
两者同时成立 ⇒ 该 `if payload is None` 分支永不进入 ⇒ 覆盖率上无法判，只能显式说明。

跑法：`cd apps/api && .venv/Scripts/python.exe -X utf8 ../../.staging/prove_unreachable_branches.py`
"""

from __future__ import annotations

import ast
from pathlib import Path

API = Path(__file__).resolve().parents[4] / "apps" / "api" / "app" / "providers" / "article_sources"


def returns_none_guarded_by_suppress(tree: ast.Module, func_name: str) -> tuple[list[int], list[int]]:
    """返回 (函数里所有 `return None` 的行号, 其中没有被 `if suppress_errors` 包住的行号)。"""
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == func_name
    )
    all_none: list[int] = []
    unguarded: list[int] = []
    guarded_lines: set[int] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.If) and _reads_suppress(node.test):
            guarded_lines.update(
                child.lineno for child in ast.walk(node) if isinstance(child, ast.Return) and child.value is not None
            )
    for node in ast.walk(fn):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant) and node.value.value is None:
            all_none.append(node.lineno)
            if node.lineno not in guarded_lines:
                unguarded.append(node.lineno)
    return sorted(all_none), sorted(unguarded)


def _reads_suppress(test: ast.expr) -> bool:
    return any(
        isinstance(n, ast.Name) and n.id == "suppress_errors" for n in ast.walk(test)
    )


def suppress_at_call_site(tree: ast.Module, caller: str, callee: str) -> tuple[bool, bool]:
    """(调用点是否存在, 是否显式传了 suppress_errors=True)。"""
    found = False
    explicit_true = False
    for node in ast.walk(tree):
        if not (isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == caller):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == callee:
                found = True
                for kw in sub.keywords:
                    if kw.arg == "suppress_errors" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        explicit_true = True
    return found, explicit_true


def main() -> int:
    rc = 0
    for module, none_line in (("justoneapi.py", 115), ("wellbyte.py", 134)):
        tree = ast.parse((API / module).read_text(encoding="utf-8"))
        all_none, unguarded = returns_none_guarded_by_suppress(tree, "_handle_response")
        call_found, explicit_true = suppress_at_call_site(tree, "query_work_list", "_handle_response")
        print(f"── {module}")
        print(f"   _handle_response 的 `return None` 行号：{all_none}")
        print(f"   其中未被 `if suppress_errors` 包住的：{unguarded}（必须是空表）")
        print(f"   query_work_list 调用 _handle_response：存在={call_found} 显式 suppress=True={explicit_true}")
        ok = call_found and not explicit_true and not unguarded
        print(f"   ⇒ 该函数的 None 只能在 suppress=True 时产生，而 query_work_list 用的是默认 False"
              f" ⇒ 调用点后的 `if payload is None: return [], None` 按构造不可达：{ok}")
        if not ok:
            rc = 1
    print("证明成立" if rc == 0 else "证明不成立——那两行是可达的，必须补用例")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
