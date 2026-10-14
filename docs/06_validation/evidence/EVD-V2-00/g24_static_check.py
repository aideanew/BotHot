"""G-24 静态自检：本机无 ruff/mypy（venv 不存在，实测 `import httpx` → ModuleNotFoundError），
用标准库复核 CI `ruff check app tests` 选中的规则族 E/F/I/W/UP/B 的可机检子集。

覆盖：E501 E302 E303 E711 E712 | F401 F841 | W291 W292 W293 | I001（isort 三条：段序、
from-import 的**成员序**、同一段被空行拆开；段表按 `sys.stdlib_module_names` + 「`apps/api/` 下
确有其物才算第一方」+ 相对导入算 local-folder，与 ruff 同口径——锚点：`evidence/65f508b/
ruff_65f508b.txt` 那四条红与实测通过的补丁）
| UP006 UP007 UP017 | B006
不覆盖：mypy 类型判定、ruff 其余规则——CI 才是终判，本脚本只是提交前的降险。
本表与 ruff 已知的一处**方向性差异**（本表更严，不更宽）：ruff 的 E501 有 pragma 例外——
代码部分本身不超限、只是行尾那句 `# type: ignore[...]` / `# noqa: ARG002` 把整行推过 120 列时，
ruff 放行。实测四处正是这一形状（`test_kb_orphan_purge.py:91` 总 122 / 代码段 92，
`test_metadata_filter.py:174` 总 126 / 代码段 96，`:233` 总 122 / 代码段 92，
`test_manifest_sync.py:481` 总 123 / 代码段 109），而 `evidence/65f508b/ruff_65f508b.txt` 里
ruff 对这四处一条都没报。本表按总长一律报，所以「本表 0 违规」比「CI ruff 0 违规」更强，
反过来不成立——读的时候别把两者当同一个数。

用法：python docs/06_validation/evidence/EVD-V2-00/g24_static_check.py [文件...]
无参数时检查 STEP-00 触碰的全部 Python。退出码 0=无违规。
"""

from __future__ import annotations

import ast
import py_compile
import re
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

#: 第一段之外还算「本项目自己的包」的名字。**`conftest` 从前在这里，是错的**：
#: 证据 `docs/任务规划V0.5.0/evidence/65f508b/ruff_65f508b.txt` 记 ruff 0.12.12 在 `test_chat_sse.py`
#: 报的那条 I001，实测通过的修复（`evidence/65f508b/STEP-00C_simulated_65f508b.patch`，ruff 读数 0 错）
#: **只重排了 from-import 的成员**，`from conftest import …` 仍与 httpx/pytest/fastapi 同一段——
#: 说明 ruff 把 `conftest` 判成第三方段（它只认 `apps/api/` 那层直接子目录/模块为第一方，
#: `conftest.py` 在 `apps/api/tests/` 下，不在那一层）。把它留在第一方表里，本近似就在**反方向**报错：
#: 于是那两条 I001 挂了好几轮修不掉，因为要改的是本表而不是那两个文件。
#: 后端根：`apps/api/`——ruff 的 isort 用它判「第一方」，本表跟它同口径（不再手抄名单）。
BACKEND = ROOT / "apps" / "api"

#: stdlib 名单直接用解释器自带的 `sys.stdlib_module_names`（3.10+）。
#: 从前这里是一份手抄的白名单，**漏了 `hmac`/`binascii`/`html` 这类**，于是整批文件被误报 I001
#: （实测：`dingtalk.py` 的 `import hmac` 被当成第三方段，`import json` 就被判成「倒序」）。
#: 手抄名单还有一个方向性的错：把 `conftest` 当第一方，而 ruff 0.12.12 实测把它留在第三方段
#: （证据见 `FUTURE_OR_FIRST` 上方那段）——那两条挂了好几轮的「I001 修不掉」就是这么造出来的。
_STDLIB = set(getattr(sys, "stdlib_module_names", ()))

#: 仍按名字点名的第一方（防御 `src` 推断不到的形状）；`conftest` **不在**这里。
FUTURE_OR_FIRST = {"app", "tests"}


def _is_first_party(top: str) -> bool:
    """与 ruff 的 `src` 同口径：`apps/api/<top>.py` 或 `apps/api/<top>/` 确有其物才算第一方。

    这条判据是可核的：`conftest.py` 在 `apps/api/tests/` 下而不是 `apps/api/` 直接子层，
    所以它**不是**第一方——与 ruff 实测通过的补丁一致（`from conftest import …` 与 httpx/pytest 同段）。
    """
    if top in FUTURE_OR_FIRST:
        return True
    return (BACKEND / f"{top}.py").is_file() or (BACKEND / top / "__init__.py").is_file()


def _section(mod: str, level: int = 0) -> int:
    """0=__future__ 1=stdlib 2=third-party 3=first-party 4=local-folder（ruff isort 的五段）。"""
    if level > 0:
        return 4  # `from .base import …` 是 local-folder，排在第一方之后（从前这里被当成第三方，
                  # 于是 models/bothot_entities.py 那种「sqlalchemy 段之后另起一段相对导入」被误报两处）
    top = mod.split(".")[0]
    if top == "__future__":
        return 0
    if top in _STDLIB:
        return 1
    if _is_first_party(top):
        return 3
    return 2


def _imp_section(node: ast.AST) -> int | None:
    """一条 import 语句所属的段；非 import 或取不到模块名时给 None（不参与「同段被拆开」的判定）。"""
    if isinstance(node, ast.ImportFrom):
        return _section(node.module or "", node.level)
    if isinstance(node, ast.Import) and node.names:
        return _section(node.names[0].name)
    return None


def _member_key(name: str) -> tuple[int, str]:
    """ruff isort 的成员排序键：常量先、类名次、函数与其它最后，同类内按小写名（`order-by-type` 默认开）。"""
    bare = name.replace("_", "")
    if bare and bare.isupper():
        rank = 0
    elif name[:1].isupper():
        rank = 1
    else:
        rank = 2
    return (rank, name.lower())


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
            entries = [(node.lineno, _section(node.module or "", node.level), 1, node.module or ".")]
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

    # ── I001 的第二半：from-import 的**成员序**与同段被空行拆开 ──────────
    # 这两类从前本机读不到，而 ruff 0.12.12 在 `65f508b` 报的三条 I001 恰好全是这两类
    # （成员序两处 + 同段空行一处，见 `evidence/65f508b/ruff_65f508b.txt`）。少了这两判，
    # 「本表也判 I001」这句话在真实缺陷上是空的——补上之后它必须既能报坏的、也不许咬好的。
    prev_import: ast.AST | None = None
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and node.names:
            names = [a.name for a in node.names]
            want = sorted(names, key=_member_key)
            if names != want:
                viol.append(
                    f"{path.name}:{node.lineno} I001 import 成员未排序：{names} "
                    f"应为 {want}（ruff isort：常量先于类再于函数，同类内按小写名）"
                )
        if isinstance(node, (ast.Import, ast.ImportFrom)) and prev_import is not None:
            if node.lineno - getattr(prev_import, "end_lineno", prev_import.lineno) == 2:
                sec_prev = _imp_section(prev_import)
                sec_now = _imp_section(node)
                if sec_prev is not None and sec_prev == sec_now:
                    viol.append(
                        f"{path.name}:{node.lineno} I001 同一段（段 {sec_now}）被空行拆开："
                        f"与上一条 import 之间不该留空行"
                    )
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            prev_import = node
        elif not isinstance(node, ast.Expr):
            prev_import = None

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
    """变异测试：植入违规确认会报，再喂**实测通过 CI 的形状**确认不报——两端都承重（G-23）。

    从前这里只有「必须报」的一半，于是 I001 把 `conftest` 的分段判反了也没人吱声：那两条挂了
    好几轮的「I001 修不掉」，要改的是本表的段表而不是那两个文件（第十四轮实测，见
    `FUTURE_OR_FIRST` 上方那段）。新增的两判（成员序、同段空行）同理——没有绿档，误报会长期隐身。
    """
    verified_green = (
        "from __future__ import annotations\n\nimport os\n\nimport httpx\nimport pytest\n"
        "from conftest import _PG_URL_SOURCE, PG_URL\nfrom test_repositories import _make_user\n\n"
        "from app.main import create_app\n\nprint(os, httpx, pytest, create_app, _PG_URL_SOURCE,"
        " PG_URL, _make_user)\n"
    )
    samples = [
        ("F401", "import json\nimport os\n\nprint(os.getcwd())\n", True),
        ("E501", "x = 1  # " + "长" * 130 + "\n", True),
        ("W291", "y = 2 \n", True),
        ("W292", "z = 3", True),
        ("E711", "a = None\nif a == None:  # noqa: E501\n    pass\n", True),
        ("B006", "def f(items=[]):\n    return items\n", True),
        ("I001", "import sys\nimport os\nprint(sys.argv, os.name)\n", True),
        ("I001", "from collections import defaultdict, OrderedDict\n"
                 "print(defaultdict, OrderedDict)\n", True),
        ("I001", "import json\n\nimport os\nprint(json, os)\n", True),
        # ↓ 三发不是编出来的样本，是 ruff 0.12.12 在 `65f508b` 真报的那三条 I001 的原样形状
        #   （`evidence/65f508b/ruff_65f508b.txt`），本表从前一条都读不到：成员序与同段空行都不判。
        ("I001", "import httpx\nimport pytest\nfrom conftest import PG_URL, SKIP_UNSET_REASON, "
                 "_PG_URL_SOURCE\nfrom fastapi.testclient import TestClient\n", True),
        ("I001", "import pytest\nfrom conftest import NO_PROXY_ISOLATION_VALUE, _PROXY_ENV_VARS\n", True),
        ("I001", "import pytest\n\nfrom fixtures.wechat_urls import BIZ_A\n", True),
        # 绿档：成员序与段都对了的那一份（就是上面三发改好之后的形状），本表也不许咬。
        ("I001", "import httpx\nimport pytest\nfrom conftest import _PG_URL_SOURCE, PG_URL, "
                 "SKIP_UNSET_REASON\nfrom fastapi.testclient import TestClient\n"
                 "print(httpx, pytest, TestClient, _PG_URL_SOURCE, PG_URL, SKIP_UNSET_REASON)\n", False),
        # 绿档：这一份的形状就是 ruff 0.12.12 在 65f508b 实测 0 错的那一份（补丁
        # `evidence/65f508b/STEP-00C_simulated_65f508b.patch`），本表不许在任何一条 I001 上咬它。
        ("I001", verified_green, False),
        ("E501", "x = 1  # " + "长" * 110 + "\n", False),
    ]
    bad = 0
    caught_n = green_n = 0
    for i, (rule, src, should_hit) in enumerate(samples):
        tmp = Path(__file__).with_name(f"_selftest_{rule}_{i}.py")
        tmp.write_text(src, encoding="utf-8", newline="\n")
        try:
            # 命中判定不能写 `rule in v`：违规串的前缀就是**这个临时文件名**（`_selftest_I001_12.py:1 …`），
            # 于是文件名里那个规则号会让任何一条违规都被算成「本规则捕获了」——绿档永远不可能静默，
            # 红档也可能因为咬错规则而算成通过。第十四轮加绿档时就是它自己把自己判红的。
            hits = [v for v in check(tmp) if re.search(rf" {rule} ", v)]
        finally:
            tmp.unlink()  # 自建临时物，用完即删
        if bool(hits) == should_hit:
            if should_hit:
                caught_n += 1
                print(f"  自检 {rule}: 捕获 {hits[0].split(':')[-1].strip()[:60]}")
            else:
                green_n += 1
                print(f"  自检 {rule}（绿档）: 未误报——实测通过 CI 的形状不许被本表咬")
        else:
            if should_hit:
                print(f"  自检 {rule}: ❌ 未捕获——检查器该项失效，结论不可信")
            else:
                print(f"  自检 {rule}（绿档）: ❌ 误报 {hits[0][:80]}——本表比 ruff 严，"
                      f"会把实测通过的形状判成违规")
            bad += 1
    total = len(samples)
    print(f"自检结果：{total - bad}/{total} 项判据两端都对（该报 {caught_n} 项、该静默 {green_n} 项）\n")
    return 1 if bad else 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    files = [Path(a) for a in args] if args else [ROOT / f for f in DEFAULT_FILES]
    total = 0
    # 仓库外的绝对路径从前会让 `path.relative_to(ROOT)` 在 main 里抛 ValueError（A 组 NI-3 实测
    # rc=1 + traceback）。那不是裁决而是崩溃，本项目的三档退出码里它有专属的一档：2 = INCONCLUSIVE。
    offside = [p for p in files if p.is_absolute() and ROOT not in p.parents and p != ROOT]
    if offside:
        for p in offside:
            print(f"INCONCLUSIVE {p} 不在仓库根 {ROOT} 下——本自检只量仓库内的文件，"
                  f"把它读成「0 违规」就是假绿，读成 FAIL 又是假红")
        print(f"合计 未判定（INCONCLUSIVE，rc=2）：{len(offside)} 个仓库外路径")
        return 2
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
