"""把 42 条先红读数重新取一份**可入库**的副本（编号 s27_red.txt）。

为什么要重取：先红原文是 pytest 的完整回栈，里面逐行带着夹具形状（`键名=值` 的完整文本），
按 S00P.2.1（文档里不内联敏感形字面量）**不能入库**——敏感形门扫到 19 条 HIGH，整批被挡。
所以这里把实现侧还原到交付前（`git show 8135f1a:scripts/guards.py`，逐字节还原），
用 `-q --tb=line` 重跑同三个用例文件：只看失败的用例与断言消息，不看源码回栈。

原始读数（就地实现时取的完整回栈版）：`42 failed, 103 passed in 19.16s`。

用法（仓库根）：python docs/06_validation/evidence/EVD-V15-27/s27_red_repro.py
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "scripts" / "guards.py"
API = ROOT / "apps" / "api"
OUT = Path(__file__).resolve().parent / "s27_red.txt"
SUITES = [
    "tests/test_secret_shape_gate.py",
    "tests/test_guard_rounds.py",
    "tests/test_startup_probe_timeout.py",
]
BASE = "8135f1a"


def main() -> int:
    current = TARGET.read_bytes()
    before = hashlib.sha256(current).hexdigest()
    old = subprocess.run(["git", "show", f"{BASE}:scripts/guards.py"],
                         cwd=str(ROOT), capture_output=True).stdout
    assert old, "取不到交付前的 guards.py"
    try:
        TARGET.write_bytes(old)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *SUITES, "-q", "--tb=line"],
            cwd=str(API), capture_output=True, text=True,
            encoding="utf-8", errors="replace")
        body = proc.stdout
    finally:
        TARGET.write_bytes(current)
    after = hashlib.sha256(TARGET.read_bytes()).hexdigest()
    assert before == after, "guards.py 没有逐字节还原"

    head = (
        "# STEP-27 / S27.V15.1 先红读数（重取版，可入库）\n"
        "#\n"
        "# 为什么是重取版：就地实现时取的完整回栈版逐行带着夹具形状，按 S00P.2.1\n"
        "# 不得入库（敏感形门在它上面读 19 条 HIGH，整批被挡）。这里把实现侧逐字节还原到\n"
        "# 交付前（git show 8135f1a:scripts/guards.py），并用 --tb=line 重跑：只留失败用例\n"
        "# 与断言消息，不留源码回栈。还原前后 sha256 一致（见本脚本输出）。\n"
        "# 原始就地读数：42 failed, 103 passed in 19.16s（42 条 = §H/§I 新增的先红用例）。\n"
        "#\n"
        "# 落盘前还有一步机械去形：敏感形门自己的错误消息形如「键名=<已打码，值长 N 字符>」，\n"
        "# 打码值仍是值类字面量（门会读它会读的东西）。统一换成 <masked>，只损失长度读数。\n"
        "#\n"
    )
    body = re.sub(r"=<已打码，值长 \d+ 字符>", "=<masked>", body)
    OUT.write_text(head + body.replace("\\", "\\\\").replace("\r\n", "\n"), encoding="utf-8")
    summary = [ln for ln in body.splitlines() if ln.strip()][-1:]
    print("先红分轮：", summary[0] if summary else "(无)")
    print(f"guards.py sha256(前)={before}")
    print(f"guards.py sha256(后)={after}")
    print("结论：" + ("✅ 还原逐字节一致，先红读数已落盘" if before == after else "❌ 还原不完整"))
    return 0 if before == after else 1


if __name__ == "__main__":
    sys.exit(main())
