"""STEP-25 S25.1.1：`require_roles(...)` 只接受一个最低角色（结构守卫，AST，不用正则）。

缺陷来源（`docs/任务规划V0.14.0/evidence/fdad6dd/probe_push_write_roles_and_created_by.txt` ①）：
`require_roles("admin", "operator")` 经 `_required_rank` 的 `max(...)` 实际要求 admin，
写的人以为是"运营及以上"。冻结契约（`docs/任务规划V0.12.0/contracts/identity.schema.json`）
规定取最高秩，所以错的是调用点而不是实现——这里把"只写一个参数"变成机器约束（D-V11-01）。

本守卫只看源码形状：每个 `require_roles(` 调用必须恰好 1 个位置参数、0 个关键字参数、
且那个参数是字符串字面量（变量/星号展开会让守卫看不见真正要求的角色）。
"""

from __future__ import annotations

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _offenders_in_source(source: str, label: str) -> list[str]:
    out: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
        if name != "require_roles":
            continue
        args_ok = (
            len(node.args) == 1
            and not node.keywords
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        )
        if not args_ok:
            out.append(f"{label}:{node.lineno}")
    return out


def _scan_app() -> tuple[list[str], int]:
    offenders: list[str] = []
    total = 0
    for path in sorted(APP_DIR.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        if "require_roles(" not in src:
            continue
        rel = path.relative_to(APP_DIR.parent).as_posix()
        tree = ast.parse(src)
        total += sum(
            1
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", None)) == "require_roles"
        )
        offenders.extend(_offenders_in_source(src, rel))
    return offenders, total


def test_guard_has_teeth_on_synthetic_source() -> None:
    """S25.1.1.a：判据本身两个极性都要有，否则下面那条可以靠"恒空"假绿。"""
    bad = (
        "from app.api.deps import require_roles\n"
        "a = require_roles('admin', 'operator')\n"
        "b = deps.require_roles()\n"
        "c = require_roles(ROLE)\n"
        "d = require_roles(*roles)\n"
        "e = require_roles(role='admin')\n"
    )
    assert _offenders_in_source(bad, "syn") == ["syn:2", "syn:3", "syn:4", "syn:5", "syn:6"]
    good = "x = require_roles('operator')\ny = deps.require_roles('admin')\n"
    assert _offenders_in_source(good, "syn") == []


def test_every_require_roles_call_in_app_has_exactly_one_literal_role() -> None:
    offenders, total = _scan_app()
    # 扫描面读空 = 守卫是空的（路径或调用形状变了），不能让它安静地绿
    assert total >= 10, f"只扫到 {total} 个 require_roles 调用，扫描面可能失效"
    assert not offenders, f"这些 require_roles 调用不是单个字面量角色（多参数会被 max() 解释成最高秩）：{offenders}"
