"""S27.3 / S27.V15.1 读数：新旧命中集合对照（计数由脚本产生，不手填）。

P-46 / D-V16-02 起，少报/新增按（文件,行号,规则）逐行对照；文件净差会把同文件
一增一减抵掉（test_auth.py 少 3 多 6），旧口径 26/10 与逐行口径 31/15 的差别
正来自同行的规则名变化。

输出：
1. 两个扫描面的总命中：自有源码面（`git ls-files` 里 7 种源码后缀、排除 `.project/`）
   与全仓可读文本面（全部 tracked 文本文件，排除 `.project/` 与二进制）；
2. 逐文件命中数（旧 → 新）与逐（文件,行号,规则）的少报/新增明细；
3. 被放掉的行里有多少含**值位**值类字面量（必须为 0）与新增行是否全部来自 `_TOKEN` 后缀族。

旧口径 = 文档面严格口径（`secret_scan`）；新口径 = 按扩展名分流的源码模式（`secret_scan_for_path`）。
两者都从本脚本所在树的 `scripts/guards.py` 加载；复算 8135f1a↔28c0d2e 时，在
`git worktree add --detach <tmp> 28c0d2e` 的临时树里覆盖本脚本后运行（该树自带 28c0d2e
的 guards 与文件集）。

"值位"= 不在键位（`[` 之后、`.get(`/`.pop(`/`.setdefault(` 的第一个实参）上的字面量。
键位里的是字段名，`body["access_token"]` 的右值来自 `body`，不是那串名字。

用法（仓库根）：python docs/06_validation/evidence/EVD-V15-27/s27_3_counts.py
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SPEC = importlib.util.spec_from_file_location("guards_probe", ROOT / "scripts" / "guards.py")
assert SPEC is not None and SPEC.loader is not None
guards = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guards)

EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
KEYED_CALL = re.compile(r"\.(?:get|pop|setdefault|getlist|getall)\s*\(\s*$")
LITERAL = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`")


def tracked() -> list[str]:
    out = subprocess.run(["git", "-c", "core.quotepath=false", "ls-files"],
                         cwd=str(ROOT), capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stdout
    return sorted(p for p in out.splitlines() if not p.startswith(".project/"))


def readable_text(rel: str) -> str | None:
    path = ROOT / rel
    if not path.is_file():
        return None
    data = path.read_bytes()
    if b"\x00" in data[:4096]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def value_pos_literals(line: str) -> list[str]:
    """行内**值位**的值类字面量；键位不算（独立复写，不调实现里的私有判据）。"""
    out: list[str] = []
    for m in LITERAL.finditer(line):
        lit = m.group(0)[1:-1]
        if not guards._src_value_like(lit):
            continue
        i = m.start() - 1
        while i >= 0 and line[i] in " \t":
            i -= 1
        if i >= 0 and line[i] == "[":
            continue
        if i >= 0 and line[i] == "(" and KEYED_CALL.search(line[:i + 1]):
            continue
        out.append(lit)
    return out


def main() -> int:
    files = tracked()
    dropped_with_value: list[str] = []
    added_not_suffix: list[str] = []
    rows = []
    faces = {"src": [0, 0, 0], "all": [0, 0, 0]}  # [文件数, 旧命中, 新命中]
    # P-46 / D-V16-02：按（文件,行号,规则）逐行对照，不用文件净差——
    # 净差会把同文件一增一减抵掉（test_auth.py 少 3 多 6）。
    diff_keys = {"src": [set(), set()], "all": [set(), set()]}
    for rel in files:
        text = readable_text(rel)
        if text is None:
            continue
        old = guards.secret_scan(text)[0]
        new = guards.secret_scan_for_path(text, rel)[0]
        old_keys = {(rel, no, name) for name, no, _ in old}
        new_keys = {(rel, no, name) for name, no, _ in new}
        faces["all"][0] += 1
        faces["all"][1] += len(old)
        faces["all"][2] += len(new)
        diff_keys["all"][0] |= old_keys - new_keys
        diff_keys["all"][1] |= new_keys - old_keys
        if Path(rel).suffix in EXTS:
            faces["src"][0] += 1
            faces["src"][1] += len(old)
            faces["src"][2] += len(new)
            diff_keys["src"][0] |= old_keys - new_keys
            diff_keys["src"][1] |= new_keys - old_keys
        if old or new:
            rows.append((rel, len(old), len(new)))
        lines = text.splitlines()
        old_lines = {h[1] for h in old}
        new_lines = {h[1] for h in new}
        for no in sorted(old_lines - new_lines):
            if value_pos_literals(lines[no - 1]):
                dropped_with_value.append(f"{rel}:{no}")
        for no in sorted(new_lines - old_lines):
            if not guards.SECRET_ASSIGN_SUFFIX.search(lines[no - 1]):
                added_not_suffix.append(f"{rel}:{no}")

    for label, key in (("自有源码面", "src"), ("全仓可读文本面", "all")):
        n, a, b = faces[key]
        drop, gain = (len(s) for s in diff_keys[key])
        print(f"{label}：{n} 个文件｜旧口径命中 {a} 条 → 新口径命中 {b} 条"
              f"（少报 {drop} 条 / 新增 {gain} 条）")
    print("")
    print("逐文件（旧 → 新，只列有变化的）：")
    for rel, a, b in rows:
        if a != b:
            print(f"  {a:3d} → {b:3d}  {rel}")
    print("")
    print("少报明细（文件:行号:规则，旧有新无）：")
    for rel, no, name in sorted(diff_keys["src"][0]):
        print(f"  {rel}:{no}:{name}")
    print("新增明细（文件:行号:规则，新有旧无）：")
    for rel, no, name in sorted(diff_keys["src"][1]):
        print(f"  {rel}:{no}:{name}")
    print("")
    print(f"被放掉但含值位值类字面量的行：{len(dropped_with_value)} {dropped_with_value[:5]}")
    print(f"新增但不属于 _TOKEN 后缀族的行：{len(added_not_suffix)} {added_not_suffix[:5]}")
    ok = not dropped_with_value and not added_not_suffix
    print("结论：" + ("✅ 只少报表达式，未少报任何含值类字面量的行" if ok else "❌ 判据出现倒退"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
