"""STEP-34 S34.1 守卫用例：S00X.2.2.1「只降不升」判据锚到调用形（P-100）。

旧判据是 @win 侧一行 grep（`grep -rn "open(" scripts | grep -v encoding=`），抓的是
字符串 `open(`——`_enclosing_open(` 的定义与调用点都被算成命中（2026-10-23 复算字面 2、
语义 0，见 EVD-V5-00X 补记 4 §4.3）。任何一次把 `open` 写进标识符的重构都会让它自红。

新判据本体在 `scripts/guards.py::open_call_violations`：用 tokenize 只认**调用形**。
四发极性（真调用红 / 函数名不红 / 属性不红 / 注释不红）+ 带 encoding 的绿 + 真仓扫描，
都钉在这里常驻跑（两平台 CI 各一遍）。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_ROOTS = [
    up for up in Path(__file__).resolve().parents
    if (up / "scripts" / "guards.py").is_file() and (up / "Makefile").is_file()
]
assert _ROOTS, "向上找不到同时含 scripts/guards.py 与 Makefile 的仓库根"
_ROOT = _ROOTS[0]

_spec = importlib.util.spec_from_file_location("bothot_guards_open_call", _ROOT / "scripts" / "guards.py")
assert _spec is not None and _spec.loader is not None
guards: Any = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guards)


def test_a_real_open_call_without_encoding_is_red() -> None:
    """极性①真调用红：不带 encoding 的 `open(` 必须被点名（文件与行号）。"""
    src = 'text = open("data.txt", "r").read()\n'
    v = guards.open_call_violations(src, "x.py")
    assert len(v) == 1, v
    assert v[0]["line"] == "1" and "encoding" in v[0]["why"], v


def test_a_function_named_open_is_not_a_violation() -> None:
    """极性②函数名不红：`_enclosing_open(` 的定义与调用都是标识符，不是文件打开。

    P-100 的两处假阳（guards.py 的 `def _enclosing_open` 与其调用点）在新判据下必须零命中。
    """
    src = (
        "def _enclosing_open(text: str, pos: int) -> tuple[int, int]:\n"
        "    return pos, pos\n"
        "\n"
        "open_at, commas = _enclosing_open(rhs, start)\n"
    )
    assert guards.open_call_violations(src, "guards.py") == []


def test_attribute_access_is_not_a_violation() -> None:
    """极性③属性不红：`f.open(` 前面是 `.`——S00X 判的是裸 `open()`，属性访问不归它管。"""
    src = "stream.open('x')\nzipfile.Path('a').open('r')\n"
    assert guards.open_call_violations(src, "x.py") == []


def test_comments_and_strings_are_not_violations() -> None:
    """极性④注释不红：说明文字与字符串字面量里的 `open(` 不改变门的结论（反自洗）。"""
    src = (
        '# open("x", "r") 这是一句说明\n'
        'doc = "调用 open( 打开文件"\n'
        'x = 1  # 行尾注释 open("y")\n'
    )
    assert guards.open_call_violations(src, "x.py") == []


def test_open_with_encoding_is_green() -> None:
    """判据要抓的是"没写 encoding 的打开"，写对的形状必须绿——否则门把正确写法也判红。"""
    src = 'text = open("data.txt", "r", encoding="utf-8").read()\n'
    assert guards.open_call_violations(src, "x.py") == []


def test_definitions_of_open_and_bare_references_are_not_calls() -> None:
    """`def open(` / `class open(` 是定义位，`import open` / `as open` 是引用位——都不算调用。"""
    src = (
        "def open(path: str):\n"
        "    return path\n"
        "\n"
        "class open:\n"
        "    pass\n"
        "\n"
        "from io import open\n"
    )
    assert guards.open_call_violations(src, "x.py") == []


def test_all_repo_scripts_are_clean_under_the_call_form_pattern() -> None:
    """真仓面（S00X.2.2.1 的"只降不升"常驻化）：scripts/** 现读零违规。

    P-100 出门判据的前半句：锚到调用形后复算，计数必须是 0（语义计数，不是字面计数）。
    变异读数（临时加一行不带 encoding 的 open ⇒ 0→1，删掉 ⇒ 回 0）在 EVD-V18-34 留案。
    """
    scripts = sorted(p for p in (_ROOT / "scripts").rglob("*.py") if "__pycache__" not in p.parts)
    assert scripts, "scripts/ 下没有任何 .py ⇒ 扫描面失效"
    hits = [
        f"{p.relative_to(_ROOT)}:{item['line']} {item['why']}"
        for p in scripts
        for item in guards.open_call_violations(
            p.read_text(encoding="utf-8"), str(p.relative_to(_ROOT))
        )
    ]
    assert not hits, "scripts/** 出现不带 encoding 的 open( 调用：\n" + "\n".join(hits)
