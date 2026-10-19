"""S27.3 五轮变异：每一轮都必须被 `tests/test_secret_shape_gate.py` 抓住（5/5 红）。

做法：逐字节备份 `scripts/guards.py` → 施加一处定点变异 → 跑该用例文件 → 记录 rc →
从备份还原 → 用 sha256 证明还原是逐字节的（不是"看起来一样"）。

为什么必须做：判据的正确性不能只靠"改完是绿的"——绿也可能是用例没牙。变异把
"用例能分辨这一处判据"变成机检读数。

用法（仓库根）：python docs/06_validation/evidence/EVD-V15-27/s27_3_mutation.py
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "scripts" / "guards.py"
TESTS = ROOT / "apps" / "api"
SUITE = "tests/test_secret_shape_gate.py"

# (名字, 原文, 变异后) —— 每条都只动一处判据，且都必须让用例红
MUTATIONS = [
    (
        "M1 表达式全放行（_source_hit 恒 False）",
        '    """源码面的一条候选：报还是放行。判据见本节开头的四条。"""\n'
        '    if kinds[key_start] != "c":',
        '    """源码面的一条候选：报还是放行。判据见本节开头的四条。"""\n'
        "    return False\n"
        '    if kinds[key_start] != "c":',
    ),
    (
        "M2 源码面等同文档面（_source_hit 恒 True）",
        '    """源码面的一条候选：报还是放行。判据见本节开头的四条。"""\n'
        '    if kinds[key_start] != "c":',
        '    """源码面的一条候选：报还是放行。判据见本节开头的四条。"""\n'
        "    return True\n"
        '    if kinds[key_start] != "c":',
    ),
    (
        "M3 下标键位失效（[ 分支永不成立）",
        '    if rhs[i] == "[":\n        return True',
        '    if rhs[i] == "\\x00":\n        return True',
    ),
    (
        "M4 值类阈值失效（去掉 ≥8 字符下界）",
        "    if len(literal) < 8 or SECRET_FAKE.match(literal):",
        "    if SECRET_FAKE.match(literal):",
    ),
    (
        "M5 路径分流失效（源码文件走文档面）",
        "    lang = _source_language(Path(rel).suffix)\n"
        "    if lang is None:\n"
        "        return secret_scan(text)",
        "    lang = _source_language(Path(rel).suffix)\n"
        "    if True:\n"
        "        return secret_scan(text)",
    ),
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    original = TARGET.read_bytes()
    before = digest(original)
    # 行尾必须跟着文件本身走：Windows 工作树是 CRLF，锚点写死 \n 会一条都命中不了
    nl = "\r\n" if b"\r\n" in original else "\n"
    print(f"guards.py sha256(前)={before} 行尾={nl!r}")
    rows = []
    try:
        for name, old, new in MUTATIONS:
            text = original.decode("utf-8")
            old = old.replace("\n", nl)
            new = new.replace("\n", nl)
            assert text.count(old) == 1, f"{name}：锚点命中 {text.count(old)} 次，变异无法定点"
            TARGET.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            proc = subprocess.run([sys.executable, "-m", "pytest", SUITE, "-q"],
                                  cwd=str(TESTS), capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
            tail = [ln for ln in proc.stdout.splitlines() if ln.strip()][-1:]
            rows.append((name, proc.returncode, tail[0] if tail else ""))
            print(f"  {name} → rc={proc.returncode} | {tail[0] if tail else ''}")
            TARGET.write_bytes(original)
    finally:
        TARGET.write_bytes(original)
    after = digest(TARGET.read_bytes())
    print(f"guards.py sha256(后)={after}")
    restored = before == after
    caught = sum(1 for _n, rc, _t in rows if rc != 0)
    print(f"变异被抓：{caught}/{len(MUTATIONS)}；还原逐字节一致={restored}")
    ok = caught == len(MUTATIONS) and restored
    print("结论：" + ("✅ 5/5 全红且还原一致" if ok else "❌ 存在未被抓的变异或还原不完整"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
