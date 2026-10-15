#!/usr/bin/env python3
"""STEP-00X 的一致性门禁：Makefile 的目标名必须都能在 scripts/entry.py 里找到。

为什么需要它：Makefile 的 26 个开发类目标已改成薄转调（实体在 entry.py）。
转调是"名字对名字"的绑定，改名/删目标/漏注册都不会有任何一侧报错——
直到有人 `make xxx` 才发现"未知任务"。这类漂移必须机检，不能靠记性。

判据方向是单向的（Makefile ⊆ entry.py）：entry.py 可以多带任务（新工具先落 entry 再补 make），
Makefile 不可以引用一个不存在的任务。
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def entry_tasks() -> set[str]:
    spec = importlib.util.spec_from_file_location("bothot_entry", ROOT / "scripts" / "entry.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 scripts/entry.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return set(mod.BY_NAME)


def make_targets() -> list[str]:
    """收集 Makefile 目标名，含带前置的目标（`install: install-backend install-frontend ## …`）。"""
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    out = []
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z][A-Za-z0-9_.-]*):(?!=)(.*)$", line)
        if not m:
            continue
        name = m.group(1)
        if name == "help" or name.endswith(".py") or name.endswith(".md"):
            continue
        out.append(name)
    return out


def forwarded(text: str, target: str) -> bool:
    """recipe 是否已交给实体脚本：转调 entry.py、转调 guards.py，或复合目标用 `@:` 靠前置。"""
    lines = text.splitlines()
    try:
        idx = next(i for i, l in enumerate(lines) if l.startswith(f"{target}:"))
    except StopIteration:
        return False
    for l in lines[idx + 1:]:
        if not l.startswith("\t"):
            break
        if "$(ENTRY)" in l or "$(GUARDS)" in l or l.strip().startswith("@:"):
            return True
    return False


def main() -> int:
    tasks = entry_tasks()
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    targets = make_targets()
    missing = [t for t in targets if t not in tasks]
    inline = [t for t in targets if t in tasks and not forwarded(text, t)]
    print(f"Makefile 目标 {len(targets)} 个；entry.py 任务 {len(tasks)} 个；"
          f"实体文件 entry.py={int((ROOT/'scripts/entry.py').exists())} "
          f"guards.py={int((ROOT/'scripts/guards.py').exists())}")
    if missing:
        print("❌ Makefile 引用了 entry.py 里不存在的任务：", ", ".join(missing))
        return 1
    if inline:
        # help 是刻意的例外：它是 Makefile 自身的目录页（grep/awk），不是执行面
        real = [t for t in inline if t != "help"]
        print(f"ℹ️  仍带内联 recipe 的目标（除 help 外应为 0）：{', '.join(inline) or '（无）'}")
        if real:
            print(f"❌ 这些目标没有转调实体脚本，Windows 侧不可运行：{', '.join(real)}")
            return 1
    print("✅ 每个 Makefile 目标都能在 entry.py/guards.py 找到实体，且 recipe 已转调")
    extra = sorted(tasks - set(targets))
    if extra:
        print(f"ℹ️  entry.py 独有（Makefile 未暴露，不算违规）：{', '.join(extra)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
