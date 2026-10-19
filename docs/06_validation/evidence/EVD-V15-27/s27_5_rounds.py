"""S27.5 轮次门扩判据的读数：四条反证各自给出判定（不靠"读代码觉得对"）。

用法（仓库根）：python docs/06_validation/evidence/EVD-V15-27/s27_5_rounds.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SPEC = importlib.util.spec_from_file_location("guards_probe", ROOT / "scripts" / "guards.py")
assert SPEC is not None and SPEC.loader is not None
guards = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guards)

CASES = [
    ("fix(STEP-00T): 第三轮复验——中文数字轮号", "红：卡 00T 出现第 3 轮"),
    ("fix(STEP-01 S1.3.2 第 3 轮): 只写 L3 号", "红：按第一段反推卡 01"),
    ("fix(STEP-20/22/23 第 3 轮): 跨卡提及三张", "红：只计主卡 20，22/23 不连坐"),
    ("fix(STEP-24 S24.1 第 1 轮): background-3 轮询抖动", "绿：background-3 不是轮号"),
    ("docs(STEP-27 @ci): 三绿读数", "绿：@ci 记录不是返工标记"),
]


def main() -> int:
    ok = True
    for subject, expect in CASES:
        marks = guards._is_round_marker(subject)
        card = guards._primary_card(subject)
        nums = guards._round_numbers(subject)
        violations = guards.rounds_violations([subject])
        red = bool(violations)
        named = [v["step"] for v in violations]
        print(f"主题：{subject}")
        print(f"  标记={marks} 主卡={card} 轮号={nums} ⇒ {'红' if red else '绿'}"
              f"{'（点名 ' + '/'.join(map(str, named)) + '）' if red else ''}")
        print(f"  期望：{expect}")
        if red != expect.startswith("红"):
            ok = False
            print("  ❌ 与期望不符")
        if red and named and card and named != [card]:
            ok = False
            print(f"  ❌ 归属不是主卡：{named} != [{card}]")
    print("结论：" + ("✅ 五条反证与期望一致" if ok else "❌ 存在与期望不符的反证"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
