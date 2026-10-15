#!/usr/bin/env python3
"""提交前的凭据形门（STEP-00P 的机械判据，本卡顺手落成可跑脚本）。

为什么不用 gitleaks 做这一步：gitleaks 的工作树模式在 Windows 上给反斜杠路径，
`.gitleaks.toml` 的 allowlist 是 POSIX 斜杠 ⇒ 507 条 vendored 假命中（EVD-V5-00S §4）。
本脚本只跑 `.gitleaks.toml:30` 那条 regex 本身，跨平台、零依赖、判据可复核。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# 与 .gitleaks.toml 的 connection-string-embedded-password 规则逐字符一致
SHAPE = re.compile(r'(?i)[a-z][a-z0-9+.\-]*://[^:/\s"\\\']+:[^@/\s"\\\']+@')
API = re.compile(r'(?i)(api[_-]?key|secret|token)\s*[:=]\s*["\'][A-Za-z0-9_\-]{20,}["\']')


def main(argv: list[str]) -> int:
    if not argv:
        print("用法：python secret_shape_gate.py <文件或目录>…")
        return 2
    targets: list[Path] = []
    for a in argv:
        p = Path(a)
        if p.is_dir():
            targets += [x for x in p.rglob("*") if x.is_file() and x.suffix in
                        (".md", ".txt", ".py", ".json", ".yml", ".yaml", ".toml", ".ignore")]
            if (p / ".gitleaksignore").exists():
                targets.append(p / ".gitleaksignore")
        elif p.exists():
            targets.append(p)
    hits = 0
    for f in targets:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for rx, label in ((SHAPE, "connection-string"), (API, "key-assignment")):
                for m in rx.finditer(line):
                    print(f"HIGH {label} {f}:{i}: {m.group(0)[:60]}")
                    hits += 1
    print(f"扫描文件 {len(targets)} 个，HIGH 命中 {hits}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
