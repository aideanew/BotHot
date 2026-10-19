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


# make 自带/环境提供的名字，不需要在本文件里定义
MAKE_BUILTINS = {"MAKEFILE_LIST", "CURDIR", "MAKE", "MAKEFLAGS", "SHELL", "OS", "PWD", "RM"}
# 由**调用方**在命令行赋值的变量（用法写在 help 里，如 `make migrate-new MSG="描述"`）。
# 判据：只允许在 recipe 里以 `VAR="$(MSG)"` 这种转发形式出现，不允许出现在命令位。
CALLER_VARS = {"MSG"}


def undefined_variables(text: str) -> list[str]:
    """Makefile 里 `$(VAR)` 用到了、却没有任何一处定义 ⇒ 展开成空串。

    为什么必须机检（现读到实证）：`GUARDS` 从未被定义，于是
    `make guard-ports / guard-structure / guard-versions / evidence-check` 四条目标
    全部退化成"把子命令名当可执行文件跑"，实测 `Error 2`（见 EVD-V14-00T §5）。
    而本脚本网上的 `forwarded()` 只查 recipe 文本里有没有 `$(GUARDS)` 字样，
    所以"每个目标都已转调实体脚本"这句声明自己也是空头的——**声明与可运行是两个维度**。

    调用变量（`MSG`）只在**每一个**出现点都处于 `NAME="$(MSG)"` 这种赋值位时才放行；
    一旦有人把它放到命令位（`@$(MSG)`），它同样会被判未定义。
    """
    defined = set(re.findall(r"^([A-Za-z_][A-Za-z0-9_]*)\s*[:?+]?=", text, re.MULTILINE))
    used = set(re.findall(r"\$\(([A-Za-z_][A-Za-z0-9_]*)\)", text))
    # make 的单字符形式 `$X` 也是变量引用（`$MYVAR` 实际是 `$(M)` + 字面量 "YVAR"），
    # 只看 `$(...)` 会漏掉整类写法（评审实测：`@echo $FROMMK` 判成"没有未定义变量"）。
    used |= set(re.findall(r"(?<!\$)\$([A-Za-z])", text))
    out: list[str] = []
    for var in sorted(used - defined - MAKE_BUILTINS):
        total = len(re.findall(rf"\$\({var}\)", text))
        assign_sites = len(re.findall(rf'[A-Za-z_][A-Za-z0-9_]*="\$\({var}\)"', text))
        if var in CALLER_VARS and total and assign_sites == total:
            continue
        out.append(var)
    return out


def main() -> int:
    tasks = entry_tasks()
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    targets = make_targets()
    missing = [t for t in targets if t not in tasks]
    undef = undefined_variables(text)
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
    if undef:
        print(f"❌ recipe 用了未定义的变量（展开成空串 ⇒ 子命令名被当成可执行文件跑）：{', '.join(undef)}")
        return 1
    print("✅ 每个 Makefile 目标都能在 entry.py/guards.py 找到实体，且 recipe 已转调")
    extra = sorted(tasks - set(targets))
    if extra:
        print(f"ℹ️  entry.py 独有（Makefile 未暴露，不算违规）：{', '.join(extra)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
