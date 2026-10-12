"""G-24 静态自检：本机无 ruff/mypy（venv 不存在，实测 `import httpx` → ModuleNotFoundError），
用标准库复核 CI `ruff check app tests` 选中的规则族 E/F/I/W/UP/B 的可机检子集。

覆盖：E501 E302 E303 E711 E712 | F401 F841 | W291 W292 W293 | I001（isort 段内
「先 import X 后 from X import」顺序，锚点：app/services/manifest.py 现行通过 CI 的排布）
| UP006 UP007 UP017 | B006
不覆盖：mypy 类型判定、ruff 其余规则——CI 才是终判，本脚本只是提交前的降险。

用法：python docs/06_validation/evidence/EVD-V2-00/g24_static_check.py [文件...]
无参数时检查 STEP-00 触碰的全部 Python。退出码 0=无违规。
"""

from __future__ import annotations

import ast
import py_compile
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # ty: ignore[unresolved-attribute]

ROOT = Path(__file__).resolve().parents[4]
LINE_LENGTH = 120  # apps/api/pyproject.toml [tool.ruff] line-length

DEFAULT_FILES = [
    "apps/api/tests/conftest.py",
    "apps/api/tests/test_w3_push_scheduler.py",
    "apps/api/tests/fixtures/wechat_urls.py",
]

FUTURE_OR_FIRST = {"app", "tests", "conftest"}


def _section(mod: str) -> int:
    """0=__future__ 1=stdlib 2=third-party 3=first-party（ruff isort 分段）。"""
    top = mod.split(".")[0]
    if top == "__future__":
        return 0
    if top in FUTURE_OR_FIRST:
        return 3
    # 本机无法可靠判定第三方（无 venv），用 Python 3.11 stdlib 前缀集白名单
    stdlib_names = {
        "abc", "argparse", "array", "ast", "asyncio", "base64", "bisect", "calendar",
        "collections", "contextlib", "contextvars", "copy", "csv", "ctypes", "dataclasses",
        "datetime", "decimal", "enum", "functools", "graphlib", "hashlib", "heapq", "http",
        "importlib", "inspect", "io", "ipaddress", "itertools", "json", "logging", "math",
        "mimetypes", "numbers", "operator", "os", "pathlib", "pickle", "platform",
        "py_compile", "queue", "random", "re", "secrets", "select", "shutil", "signal",
        "socket", "sqlite3", "statistics", "string", "struct", "subprocess", "sys",
        "sysconfig", "tempfile", "textwrap", "time", "traceback", "types", "typing",
        "unicodedata", "unittest", "urllib", "uuid", "warnings", "weakref", "xml",
        "zoneinfo",
    }
    return 1 if top in stdlib_names else 2


def check(path: Path) -> list[str]:
    viol: list[str] = []
    raw = path.read_text(encoding="utf-8")
    lines = raw.split("\n")
    try:
        # cfile 必须落在临时目录：默认写法会在源码旁边留 .pyc，污染工作树（首版即如此）
        with tempfile.TemporaryDirectory() as td:
            py_compile.compile(str(path), cfile=str(Path(td) / "x.pyc"), doraise=True, quiet=1)
    except py_compile.PyCompileError as exc:
        return [f"{path.name}: 语法错误 {exc}"]
    if not raw.endswith("\n"):
        viol.append(f"{path.name}: W292 文件末尾缺换行")
    for i, line in enumerate(lines, 1):
        if len(line.rstrip("\r")) > LINE_LENGTH:
            viol.append(f"{path.name}:{i} E501 行长 {len(line)} > {LINE_LENGTH}")
        if line != line.rstrip():
            viol.append(f"{path.name}:{i} W291 行尾空格")
        if line.strip() == "" and line != "":
            viol.append(f"{path.name}:{i} W293 空行含空白")
    tree = ast.parse(raw, filename=str(path))

    # ── I001：逐个 import 区块检查分段与段内排序 ──────────────────
    # 区块 = 连续的 import 语句；被可执行语句（如 conftest 的事件循环策略设置）打断即另起
    # 一块，各块独立排序——否则会把 conftest.py:29 的第二个块误判为 I001（首版即如此）。
    blocks: list[list[tuple[int, int, int, str]]] = []
    cur: list[tuple[int, int, int, str]] = []
    prev_line = 0
    for node in tree.body:
        entries: list[tuple[int, int, int, str]] = []
        if isinstance(node, ast.Import):
            entries = [(node.lineno, _section(a.name), 0, a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            entries = [(node.lineno, _section(node.module or ""), 1, node.module or ".")]
        if not entries:
            if cur:
                blocks.append(cur)
                cur = []
            continue
        if cur and node.lineno - prev_line > 6:  # 中间隔了注释/空行的可执行段
            blocks.append(cur)
            cur = []
        cur.extend(entries)
        prev_line = node.lineno
    if cur:
        blocks.append(cur)
    for blk in blocks:
        prev_key: tuple[int, int, str] | None = None
        for lineno, sec, kind, mod in blk:
            key = (sec, kind, mod.lower())
            if prev_key is not None and key < prev_key:
                viol.append(
                    f"{path.name}:{lineno} I001 import 未排序：{('from ' if kind else '') + mod} "
                    f"应排在 {prev_key[2]} 之前（段 {sec}，先 import 后 from）"
                )
            prev_key = key

    # ── F401：导入未使用 ───────────────────────────────────────────
    # 「使用」= import 语句之外出现的名字：AST 里的 Load 名、字符串字面量里的词
    # （from __future__ annotations 使注解只是字符串）、以及注释里的引用。
    # 首版把整份源码的词并进 used，等于任何导入都算被用——F401 永不为真，
    # 属 G-23 型「不可能失败的断言」，已改为按来源收窄。
    used: set[str] = set()
    import_lines = {n.lineno for n in tree.body if isinstance(n, ast.Import | ast.ImportFrom)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            continue
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            base = node
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                used.add(base.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            used.update(_words(node.value))
    for i, line in enumerate(lines, 1):
        if "#" in line:
            used.update(_words(line.split("#", 1)[1]))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            if node.lineno in import_lines and isinstance(node, ast.ImportFrom) and node.module == "__future__":
                continue
            for alias in node.names:
                name = alias.name.split(".")[0] if isinstance(node, ast.Import) else (alias.asname or alias.name)
                if alias.name == "*" or name == "annotations":
                    continue
                if name not in used:
                    viol.append(f"{path.name}:{node.lineno} F401 未使用导入 {name}")

    # ── F841：赋值后未使用的局部变量（保守：仅函数体内 Name 目标） ──
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]:
        body_words: set[str] = set()
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                body_words.add(sub.id)
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Assign) and len(sub.targets) == 1 and isinstance(sub.targets[0], ast.Name):
                t = sub.targets[0].id
                if t.startswith("_"):
                    continue
                if t not in body_words and t not in _aug_targets(fn):
                    viol.append(f"{path.name}:{sub.lineno} F841 局部变量 {t} 赋值后未被读取")

    # ── UP / B 轻量项 ──────────────────────────────────────────────
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in {"Optional", "Union"} and isinstance(node.ctx, ast.Load):
            viol.append(f"{path.name}:{node.lineno} UP007 用 X | None / X | Y 替代 typing.{node.id}")
        if isinstance(node, ast.Attribute) and node.attr in {"Dict", "List", "Set", "Tuple"}:
            if isinstance(node.value, ast.Name) and node.value.id == "typing":
                viol.append(f"{path.name}:{node.lineno} UP006 用内置 dict/list/set/tuple")
        if isinstance(node, ast.Attribute) and node.attr == "utc":
            if isinstance(node.value, ast.Name) and node.value.id == "timezone":
                viol.append(f"{path.name}:{node.lineno} UP017 用 datetime.UTC")
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]:
        for d in list(fn.args.defaults) + [x for x in fn.args.kw_defaults if x is not None]:
            if isinstance(d, ast.List | ast.Dict | ast.Set):
                viol.append(f"{path.name}:{d.lineno} B006 可变默认参数")
    # E711/E712：AST 比较运算判定（文本匹配会被本脚本自己的字符串字面量触发误报）
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            op = node.ops[0]
            if not isinstance(op, ast.Eq | ast.NotEq):
                continue
            for comp in node.comparators:
                if isinstance(comp, ast.Constant) and comp.value is None:
                    viol.append(f"{path.name}:{node.lineno} E711 用 `is None` / `is not None`")
                elif isinstance(comp, ast.Constant) and comp.value is True:
                    viol.append(f"{path.name}:{node.lineno} E712 与 True 比较，直接用真值表达式")
                elif isinstance(comp, ast.Constant) and comp.value is False:
                    viol.append(f"{path.name}:{node.lineno} E712 与 False 比较，用 not 表达式")
    # E303：连续 >2 空行；E302：顶层 def/class 前不足 2 空行
    blank = 0
    for i, line in enumerate(lines, 1):
        if line.strip() == "":
            blank += 1
            if blank > 2:
                viol.append(f"{path.name}:{i} E303 空行超过 2")
            continue
        if blank > 0 and (line.startswith("def ") or line.startswith("class ") or line.startswith("async def ")):
            if i > 2 and blank < 2 and not lines[i - 2].lstrip().startswith("@"):
                viol.append(f"{path.name}:{i} E302 顶层定义前需 2 空行（现有 {blank}）")
        blank = 0
    return viol


def _aug_targets(fn: ast.AST) -> set[str]:
    out: set[str] = set()
    for sub in ast.walk(fn):
        if isinstance(sub, ast.AugAssign) and isinstance(sub.target, ast.Name):
            out.add(sub.target.id)
        if isinstance(sub, ast.For) and isinstance(sub.target, ast.Name):
            out.add(sub.target.id)
        if isinstance(sub, (ast.With, ast.AsyncWith)):
            for item in sub.items:
                if isinstance(item.optional_vars, ast.Name):
                    out.add(item.optional_vars.id)
    return out


def _words(src: str) -> set[str]:
    """把源码里出现的所有标识符收集起来（用于 F401 的宽松豁免：字符串/注解/文档引用）。"""
    return {tok for tok in _ident_iter(src)}


def _ident_iter(src: str):
    buf = []
    for ch in src:
        if ch.isalnum() or ch == "_":
            buf.append(ch)
        else:
            if buf:
                yield "".join(buf)
                buf = []
    if buf:
        yield "".join(buf)


def self_test() -> int:
    """变异测试：故意植入 6 类违规，确认检查器真的会报——否则「无违规」是空话（G-23）。"""
    samples = {
        "F401": "import json\nimport os\n\nprint(os.getcwd())\n",
        "E501": "x = 1  # " + "长" * 130 + "\n",
        "W291": "y = 2 \n",
        "W292": "z = 3",
        "E711": "a = None\nif a == None:  # noqa: E501\n    pass\n",
        "B006": "def f(items=[]):\n    return items\n",
        "I001": "import sys\nimport os\nprint(sys.argv, os.name)\n",
    }
    bad = 0
    for rule, src in samples.items():
        tmp = Path(__file__).with_name(f"_selftest_{rule}.py")
        tmp.write_text(src, encoding="utf-8", newline="\n")
        try:
            hits = [v for v in check(tmp) if rule in v]
        finally:
            tmp.unlink()  # 自建临时物，用完即删
        if hits:
            print(f"  自检 {rule}: 捕获 {hits[0].split(':')[-1].strip()[:60]}")
        else:
            print(f"  自检 {rule}: ❌ 未捕获——检查器该项失效，结论不可信")
            bad += 1
    print(f"自检结果：{len(samples) - bad}/{len(samples)} 规则可捕获\n")
    return 1 if bad else 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    files = [Path(a) for a in args] if args else [ROOT / f for f in DEFAULT_FILES]
    total = 0
    for path in files:
        if not path.is_absolute():
            path = ROOT / path
        viol = check(path)
        print(f"=== {path.relative_to(ROOT)} ===")
        for v in viol:
            print(f"  {v}")
        total += len(viol)
        if not viol:
            print("  无违规（E/F/I/W/UP/B 机检子集）")
    print(f"\n合计违规 {total} 条。注：CI 的 ruff/mypy 为终判，本表只降提交风险。")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
