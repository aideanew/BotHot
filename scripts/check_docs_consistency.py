#!/usr/bin/env python3
"""
check_docs_consistency.py — 文档一致性检查

功能：
1. 解析 docs/04_engineering/backlog.md 中所有标记为 ✅ 的条目，验证其 `path:line` 锚真实存在
2. （S34.4，P-108）扫描 docs/02_requirements/** 与 AGENTS.md 的**需求侧验收锚**：
   仓内文件锚（`apps/...` 等根路径形态）按 HEAD 的 blob 判存在；裸文件名与
   `文件::符号` 形态先对根路径锚全集做后缀/基名解析，再在文件体里按
   `def` / `async def` / `it(` / `test(` / `describe(` 判符号定义存在
3. 任何一处断链 ⇒ 退出非零（CI 门禁）

使用：
    python scripts/check_docs_consistency.py           # 检查
    python scripts/check_docs_consistency.py --verbose # 详细输出
    python scripts/check_docs_consistency.py --self-test

注意：
- 这是防"虚标完成"复发的历史病根
- 接入 ci.yml 独立 step
- S34.4 把 STEP-12 的一次性对账（`EVD-V17-12/req_anchor_reconciliation.txt`）做成常驻门；
  该探针的两类不判仍是盲区，写在这里免得被读成"全查过了"：
  ① 锚指向的文件存在，但"那条用例今天是否真跑"（pass vs skip）不在本门职责内；
  ② 带参数化 id 的引用（形如 `test_x[case]`）不匹配符号正则，不计入符号锚。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKLOG_FILE = PROJECT_ROOT / "docs" / "04_engineering" / "backlog.md"
REQUIREMENTS_DIR = PROJECT_ROOT / "docs" / "02_requirements"
AGENTS_FILE = PROJECT_ROOT / "AGENTS.md"

# 匹配 file:line 格式的正则（审查修复：backlog 实际用单冒号 `path:45`，
# 原实现要求双冒号 `path::45` 导致解析到 0 条、检查形同虚设）
PATH_PATTERN = re.compile(
    r"`([a-zA-Z0-9_/\.-]+\.(?:py|ts|tsx|mjs)):(\d+)(?:-(\d+))?`"
)

# 匹配 ✅ 条目的正则
COMPLETED_PATTERN = re.compile(r"^###\s+.*✅.*$", re.MULTILINE)

# ── S34.4 需求侧锚 ─────────────────────────────────────────────────────────────
# 仓内代码文件锚的扩展名集合（与 backlog 段同口径）
_CODE_EXT = r"(?:py|ts|tsx|mjs)"
# 裸文件 token：前后不能是标识符字符（防 `x.test_y.ts` 这类被切一半）
_CODE_TOKEN_RE = re.compile(rf"(?<![A-Za-z0-9_.\-/])([A-Za-z0-9_][A-Za-z0-9_/\.-]*\.{_CODE_EXT})\b")
# `文件::符号` 引用（文件可以是根路径，也可以是裸文件名）
_SYMBOL_REF_RE = re.compile(
    rf"(?<![A-Za-z0-9_.\-/])(?P<file>[A-Za-z0-9_][A-Za-z0-9_/\.-]*\.{_CODE_EXT})::(?P<sym>[A-Za-z_][A-Za-z0-9_]*)"
)
# 视为"仓内根路径"的前缀；不带前缀的写法按后缀/基名解析，解析不到即"写法不齐"
_KNOWN_ROOTS = ("apps/", "scripts/", "docs/", "packages/", ".github/")
# 符号定义形态：Python 的 def / async def；TS/TSX 的 it( / test( / describe(
_PY_DEF_RE = r"^\s*(?:async\s+)?def\s+{sym}\b"
_TS_DEF_RE = r"(?:it|test|describe)\(\s*['\"`]{sym}['\"`]"


def parse_backlog() -> list[tuple[str, int, str]]:
    """
    解析 backlog.md，提取所有 ✅ 条目及其声称的路径

    返回：[(文件路径, 行号, 条目标题), ...]
    """
    if not BACKLOG_FILE.exists():
        print(f"[error] backlog 文件不存在: {BACKLOG_FILE}")
        sys.exit(1)

    content = BACKLOG_FILE.read_text(encoding="utf-8")
    lines = content.split("\n")

    results: list[tuple[str, int, str]] = []
    current_section: str | None = None
    in_completed_section = False

    for line in lines:
        # 检测 ✅ 条目标题
        if line.startswith("### ") and "✅" in line:
            in_completed_section = True
            current_section = line.strip()
            continue

        # 检测非 ✅ 条目标题（结束当前 ✅ 区块）
        if line.startswith("### ") and "✅" not in line:
            in_completed_section = False
            current_section = None
            continue

        # 在 ✅ 区块中查找路径引用
        if in_completed_section and current_section:
            for match in PATH_PATTERN.finditer(line):
                file_path = match.group(1)
                line_num = int(match.group(2))
                results.append((file_path, line_num, current_section))

    return results


def verify_paths(paths: list[tuple[str, int, str]], verbose: bool = False) -> bool:
    """
    验证所有路径是否存在

    返回：True 如果所有路径都存在，False 否则
    """
    all_valid = True
    checked = 0
    failed = 0

    for file_path, line_num, section in paths:
        checked += 1
        full_path = PROJECT_ROOT / file_path

        if not full_path.exists():
            print(f"[error] {file_path}:{line_num} 文件不存在 ({section})")
            all_valid = False
            failed += 1
            continue
        # 行号越界校验：声称的 file:line 至少要落在文件行数内（防幻觉行号）
        total_lines = len(full_path.read_text(encoding="utf-8", errors="replace").splitlines())
        if line_num > total_lines:
            print(f"[error] {file_path}:{line_num} 行号越界（文件共 {total_lines} 行）({section})")
            all_valid = False
            failed += 1
            continue
        if verbose:
            print(f"[ok] {file_path}:{line_num} ({section})")

    print(f"\n检查完成：共 {checked} 个路径引用，{failed} 个不存在")
    return all_valid


# ═══ S34.4（P-108）：需求侧验收锚对账 ═══════════════════════════════════════════
#
# STEP-12 做过一次仓外对账（15 份语料、99 个文件锚、4 个 `::` 符号锚，全命中），
# 但那是**一次性读数**——明天谁往 REQ 文档里写一条不存在的用例文件，没有任何门会红。
# 本节把那次对账的判据搬进来常驻：文件锚按 HEAD blob 判存在（不看工作树，
# 与探针同口径），符号锚在文件体里判定义。判据本体保持纯函数（语料/HEAD 集合/
# 文件体全部注入），--self-test 用四发极性自证"门不是恒真"。


def collect_anchor_tokens(lines: list[str]) -> tuple[set[str], set[str]]:
    """一个语料文件的行 ⇒ (根路径锚, 非根路径写法)。

    根路径锚 = 以 `apps/ scripts/ docs/ packages/ .github/` 开头的代码文件 token；
    其余（裸文件名 `x.py`、半路径 `tests/x.py`）原样交回，由调用方对根路径锚全集解析。
    """
    rooted: set[str] = set()
    unrooted: set[str] = set()
    for line in lines:
        for token in _CODE_TOKEN_RE.findall(line):
            if token.startswith(_KNOWN_ROOTS):
                rooted.add(token)
            else:
                unrooted.add(token)
    return rooted, unrooted


def resolve_against_anchors(token: str, rooted: set[str]) -> bool:
    """裸文件名 / 半路径写法能否对根路径锚全集解析（基名或路径后缀命中）。"""
    return any(a == token or a.endswith("/" + token) or a.endswith(token) for a in rooted)


def resolve_against_head(token: str, head_files: set[str]) -> bool:
    """非根路径写法对 **HEAD 全集** 的兜底解析（语料里没写根路径形态时的合法速写）：
    裸名看基名（`bots.py` → `apps/api/app/api/v1/bots.py`），半路径看后缀
    （`core/logging.py` → `apps/api/app/core/logging.py`）。名字在仓库任何角落都不存在
    ⇒ 编造，判红。"""
    return any(h == token or h.endswith("/" + token) for h in head_files)


def symbol_defined(body: str, sym: str, path: str) -> bool:
    """文件体里是否有 `sym` 的定义形态（py: def/async def；ts: it(/test(/describe()。"""
    pattern = _PY_DEF_RE if path.endswith(".py") else _TS_DEF_RE
    return re.search(pattern.format(sym=re.escape(sym)), body, re.MULTILINE) is not None


def resolve_symbol_target(file_token: str, rooted: set[str], head_files: set[str]) -> list[str]:
    """`文件::符号` 的文件部 ⇒ 候选锚路径。

    根路径直接用；裸名先对语料根路径锚全集取基名匹配（精确），再对 HEAD 全集兜底。
    """
    if file_token.startswith(_KNOWN_ROOTS):
        return [file_token]
    precise = sorted(a for a in rooted if a.endswith("/" + file_token) or a == file_token)
    if precise:
        return precise
    return sorted(h for h in head_files if h.endswith("/" + file_token) or h == file_token)


def requirement_anchor_problems(
    corpus: dict[str, list[str]],
    head_files: set[str],
    read_body,
) -> list[str]:
    """判据本体（纯函数）：语料 ⇒ 断链问题清单（空 = 通过）。

    corpus: {相对路径: 行列表}；head_files: `git ls-tree -r --name-only HEAD` 的路径集合；
    read_body(锚路径) ⇒ 文件体文本（符号定义在此查找）。

    口径：根路径锚按 HEAD 判存在；裸名/半路径写法对语料锚全集、再对 HEAD 全集解析
    （两处都不中 ⇒ 写法不齐/编造）；`::` 符号在候选文件体里判定义。
    """
    problems: list[str] = []
    rooted_all: set[str] = set()
    unrooted_all: dict[str, str] = {}
    sym_refs: list[tuple[str, str, str]] = []
    for src, lines in corpus.items():
        rooted, unrooted = collect_anchor_tokens(lines)
        rooted_all |= rooted
        for token in unrooted:
            unrooted_all.setdefault(token, src)
        for line in lines:
            for m in _SYMBOL_REF_RE.finditer(line):
                sym_refs.append((src, m.group("file"), m.group("sym")))
    if not rooted_all:
        problems.append(
            f"[anchor] 语料里一个根路径文件锚都没有——解析器与文档格式脱节（{len(corpus)} 份语料）"
        )
        return problems
    for anchor in sorted(rooted_all):
        if anchor not in head_files:
            problems.append(f"[anchor] 文件锚不存在（按 HEAD）：{anchor}")
    for token, src in sorted(unrooted_all.items()):
        if not resolve_against_anchors(token, rooted_all) and not resolve_against_head(token, head_files):
            problems.append(f"[anchor] 写法不齐/文件不存在：{token}（{src}）")
    for src, file_token, sym in sorted(sym_refs):
        targets = resolve_symbol_target(file_token, rooted_all, head_files)
        if not targets:
            problems.append(f"[anchor] 符号锚的文件解析不到：{file_token}::{sym}（{src}）")
            continue
        bodies = [(t, read_body(t)) for t in targets]
        if not any(body is not None and symbol_defined(body, sym, t) for t, body in bodies):
            where = " / ".join(t for t, _ in bodies)
            problems.append(f"[anchor] 符号锚定义不存在：{file_token}::{sym}（{src}；找过 {where}）")
    return problems


def _head_file_set() -> set[str] | None:
    """`git ls-tree -r --name-only HEAD` ⇒ 路径集合；git 不可用/失败 ⇒ None（fail-closed）。"""
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotepath=false", "ls-tree", "-r", "--name-only", "HEAD"],
            cwd=str(PROJECT_ROOT), capture_output=True,
        )
    except OSError:
        return None
    if proc.returncode:
        return None
    return {line for line in proc.stdout.decode("utf-8", "replace").splitlines() if line}


def verify_requirement_anchors(verbose: bool = False) -> bool:
    """需求侧锚对账的门面：装语料、取 HEAD 集合、跑判据本体、打印读数。"""
    corpus: dict[str, list[str]] = {}
    if REQUIREMENTS_DIR.is_dir():
        for path in sorted(REQUIREMENTS_DIR.rglob("*.md")):
            corpus[path.relative_to(PROJECT_ROOT).as_posix()] = path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
    if AGENTS_FILE.exists():
        corpus["AGENTS.md"] = AGENTS_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    if not corpus:
        print("[error] [anchor] 语料为空：docs/02_requirements/** 与 AGENTS.md 都不存在")
        return False
    head_files = _head_file_set()
    if head_files is None:
        print("[error] [anchor] git ls-tree HEAD 失败 ⇒ 无法按 HEAD 判存在（fail-closed）")
        return False

    def read_body(anchor: str) -> str | None:
        full = PROJECT_ROOT / anchor
        return full.read_text(encoding="utf-8", errors="replace") if full.exists() else None

    problems = requirement_anchor_problems(corpus, head_files, read_body)
    rooted_total = sum(len(collect_anchor_tokens(lines)[0]) for lines in corpus.values())
    print(f"[anchor] 语料 {len(corpus)} 份，根路径文件锚 {rooted_total} 处（按 HEAD 判存在）")
    for problem in problems:
        print(f"[error] {problem}")
    if problems:
        print(f"\n[error] [anchor] 需求侧锚对账失败：{len(problems)} 处断链")
        return False
    if verbose:
        for token in sorted({t for lines in corpus.values() for t in collect_anchor_tokens(lines)[1]}):
            print(f"[ok] [anchor] 非根路径写法已解析：{token}")
    print("[ok] [anchor] 需求侧锚对账通过")
    return True


def self_test() -> bool:
    """四发极性（STEP-12 探针 §2 的同款）：证明判据不是恒真。

    ① 真实文件/符号/裸名速写应全通过 ② 编造符号应被点名 ③ 真实文件应判存在
    ④ 编造文件应判不存在；另加：⑤ HEAD 兜底解析成功 ⑥ 解析不到的裸名判写法不齐
    ⑦ 零锚语料 fail-closed。全部对合成数据。
    """
    head = {"apps/api/tests/test_a.py", "apps/api/tests/test_b.py", "apps/web/next.config.mjs"}
    corpus = {
        "REQ.md": [
            "验收锚：`apps/api/tests/test_a.py` 与裸写 `test_a.py`、符号 `test_a.py::test_ok`",
            "速写：`test_b.py`（本篇只写裸名，根路径在 HEAD 里）",
        ],
    }

    def read_body(anchor: str) -> str | None:
        if anchor == "apps/api/tests/test_a.py":
            return "def test_ok() -> None:\n    assert True\n"
        return None

    ok = requirement_anchor_problems(corpus, head, read_body) == []
    print(f"  ① 真实文件、真实符号、裸名速写（HEAD 兜底）应全通过: got={ok} want=True {'OK' if ok else 'BAD'}")

    bad_sym = {"REQ.md": ["基准 `apps/api/tests/test_a.py` 与 `test_a.py::test_missing`"]}
    p = requirement_anchor_problems(bad_sym, head, read_body)
    ok2 = len(p) == 1 and "test_missing" in p[0]
    print(f"  ② 编造符号应被点名: got={p} {'OK' if ok2 else 'BAD'}")

    bad_file = {"REQ.md": ["`apps/api/tests/test_no_such.py`"]}
    p = requirement_anchor_problems(bad_file, head, read_body)
    ok3 = len(p) == 1 and "test_no_such.py" in p[0]
    print(f"  ④ 编造文件应被点名: got={p} {'OK' if ok3 else 'BAD'}")

    unresolvable = {"REQ.md": ["基准 `apps/api/tests/test_a.py`；裸写 `no_such_file.py`"]}
    p = requirement_anchor_problems(unresolvable, head, read_body)
    ok4 = any("写法不齐" in x for x in p)
    print(f"  ⑥ 解析不到的裸名应判写法不齐: got={p} {'OK' if ok4 else 'BAD'}")

    empty = requirement_anchor_problems({"REQ.md": ["没有锚的一篇"]}, head, read_body)
    ok5 = len(empty) == 1 and "一个根路径文件锚都没有" in empty[0]
    print(f"  ⑦ 零锚语料应 fail-closed: got={empty} {'OK' if ok5 else 'BAD'}")

    # S50 负例：值不符 / 行号不符 / history 跳过（合成语料，不读仓库）
    lines_pkg = ['{', '  "next": "^15.5.28"', "}"]

    def _syn(p: str, n: int) -> str | None:
        return lines_pkg[n - 1] if p == "apps/web/package.json" and 0 < n <= len(lines_pkg) else None

    pv = stack_citation_problems(
        {"AGENTS.md": ['`apps/web/package.json:2` `"next": "^15.5.29"`']}, _syn
    )
    ok6 = len(pv) == 1 and "不符" in pv[0]
    print(f"  ⑧ 值写错一位必须被点名: got={pv} {'OK' if ok6 else 'BAD'}")
    pl = stack_citation_problems(
        {"AGENTS.md": ['`apps/web/package.json:1` `"next": "^15.5.28"`']}, _syn
    )
    ok7 = len(pl) == 1 and "不符" in pl[0]
    print(f"  ⑨ 行号指错必须被点名: got={pl} {'OK' if ok7 else 'BAD'}")
    ph = stack_citation_problems(
        {"AGENTS.md": ['`apps/web/package.json:2` `"next": "^15.5.24"` <!-- stack-history -->']}, _syn
    )
    ok8 = ph == []
    print(f"  ⑩ history 行跳过: got={ph} {'OK' if ok8 else 'BAD'}")

    return ok and ok2 and ok3 and ok4 and ok5 and ok6 and ok7 and ok8



# ═══ STEP-50（STACK-001）：技术栈版本声明 ↔ 实值一致性门 ═══════════════════════

#: 本门只认这两类被引文件（引用样本见 REQ-C-001 与 AGENTS 证据行）
_CITED_FILES = ("apps/web/package.json", "apps/api/pyproject.toml")
_JSON_PAIR = re.compile(r"`\"([A-Za-z0-9_.-]+)\": \"([^`\"]+)\"`")
_TOML_PAIR = re.compile(r"`([A-Za-z0-9_.-]+) = \"([^`\"]+)\"`")
_ANCHOR = re.compile(r"`?(apps/web/package\.json|apps/api/pyproject\.toml):(\d+)`?")
_ANCHOR_BARE = re.compile(r"`?:(\d+)`?")
_HISTORY_MARK = "<!-- stack-history -->"


def stack_citation_problems(corpus: dict[str, list[str]], read_line) -> list[str]:
    """判据本体（纯函数）：{文档名: 行列表} ⇒ 引用失配清单（空 = 通过）。

    抽取形如反引号包住的 ``"键": "值"``（package.json 形）或 ``键 = "值"``（pyproject 形）、
    且同一行带 `被引文件:行号` 锚的引用，断言被引文件该行**逐字包含**该键值对
    （package.json 行含 `"键": "值"`；pyproject 行含 `键 = "值"`）。
    行内含 ``<!-- stack-history -->`` 的整行跳过（叙述历史值，REQ-C-001:28 的先例）。
    ``:N`` 裸锚沿用本行先前出现的被引文件（AGENTS:84 的 ``、:28`` 写法）。
    ``read_line(path, n)`` 由调用方注入（判据可喂合成语料自测）。
    """
    problems: list[str] = []
    for doc, lines in sorted(corpus.items()):
        for idx, line in enumerate(lines, start=1):
            if _HISTORY_MARK in line:
                continue
            current_file = ""
            current_lineno = 0
            pos = 0
            while pos < len(line):
                # 三类 token 各取最靠前的一个，谁在前先处理谁——
                # `:28` 裸锚常出现在下一个键值对之前（AGENTS:84 的写法），顺序不能倒。
                cands: list[tuple[int, str, re.Match[str]]] = []
                a = _ANCHOR.search(line, pos)
                if a is not None:
                    cands.append((a.start(), "anchor", a))
                b = _ANCHOR_BARE.search(line, pos)
                if b is not None and current_file:
                    cands.append((b.start(), "bare", b))
                pairs = [m for m in (_JSON_PAIR.search(line, pos), _TOML_PAIR.search(line, pos)) if m]
                pair = min(pairs, key=lambda m: m.start()) if pairs else None
                if pair is not None:
                    cands.append((pair.start(), "pair", pair))
                if not cands:
                    break
                _, kind, m = min(cands, key=lambda t: t[0])
                if kind == "anchor":
                    current_file = m.group(1)
                    current_lineno = int(m.group(2))
                    pos = m.end()
                elif kind == "bare":
                    current_lineno = int(m.group(1))
                    pos = m.end()
                else:
                    # 卡面验收④（STACK-001）：脚本不比对 requires-python——
                    # 它声明的是"允许更宽"的版本区间，与 CI 钉的精确版本是两套口径，
                    # 文本比对会把这种合法的宽关系误判成漂移。
                    if m.group(1) == "requires-python":
                        pos = m.end()
                        continue
                    if current_file:
                        key, value = m.group(1), m.group(2)
                        actual = read_line(current_file, current_lineno)
                        if current_file.endswith("package.json"):
                            expected = f'"{key}": "{value}"'
                        else:
                            expected = f'{key} = "{value}"'
                        if actual is None or expected not in actual:
                            problems.append(
                                f"{doc}:{idx} 声明 {expected!r} 与 {current_file}:{current_lineno} 实值不符"
                            )
                    pos = m.end()
    return problems


def _real_read_line(path: str, n: int) -> str | None:
    full = PROJECT_ROOT / path
    if not full.exists():
        return None
    lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[n - 1] if 0 < n <= len(lines) else None


def _stack_corpus() -> dict[str, list[str]]:
    corpus: dict[str, list[str]] = {}
    if AGENTS_FILE.exists():
        corpus["AGENTS.md"] = AGENTS_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    if REQUIREMENTS_DIR.is_dir():
        for path in sorted(REQUIREMENTS_DIR.rglob("*.md")):
            corpus[str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")] = (
                path.read_text(encoding="utf-8", errors="replace").splitlines()
            )
    return corpus


def verify_stack_citations(verbose: bool = False) -> bool:
    """门面：扫 AGENTS.md 与需求文档的技术栈引用，与被引实值逐字比对。"""
    corpus = _stack_corpus()
    problems = stack_citation_problems(corpus, _real_read_line)
    checked = sum(
        1
        for lines in corpus.values()
        for line in lines
        if _HISTORY_MARK not in line and (_JSON_PAIR.search(line) or _TOML_PAIR.search(line))
    )
    print(f"[stack] 语料 {len(corpus)} 份，含键值引用的行 {checked} 行")
    for problem in problems:
        print(f"[error] {problem}")
    if problems:
        print(f"\n[error] [stack] 技术栈引用失配：{len(problems)} 处")
        return False
    print("[ok] [stack] 技术栈引用与实值一致")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="文档一致性检查")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="详细输出",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="对合成数据跑判据极性自检（不读仓库文档）",
    )
    args = parser.parse_args()

    if args.self_test:
        sys.exit(0 if self_test() else 1)

    if not BACKLOG_FILE.exists():
        print(f"[error] backlog 文件不存在: {BACKLOG_FILE}")
        sys.exit(1)

    print(f"[info] 解析 {BACKLOG_FILE}")
    paths = parse_backlog()

    if not paths:
        # 审查修复：0 条 = 解析器与文档格式脱节（本仓库病史），必须报警而非静默通过
        print("[error] 未找到任何 ✅ 条目的路径引用——解析器与 backlog 格式脱节，禁止静默通过")
        sys.exit(1)

    print(f"[info] 找到 {len(paths)} 个路径引用")
    backlog_ok = verify_paths(paths, args.verbose)
    anchors_ok = verify_requirement_anchors(args.verbose)
    if not backlog_ok:
        print("\n[error] 文档一致性检查失败：存在虚假 ✅ 标记")
        sys.exit(1)
    if not anchors_ok:
        sys.exit(1)
    stack_ok = verify_stack_citations(args.verbose)
    if not stack_ok:
        sys.exit(1)

    print("\n[ok] 文档一致性检查通过")


if __name__ == "__main__":
    main()
