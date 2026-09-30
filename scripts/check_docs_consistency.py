#!/usr/bin/env python3
"""
check_docs_consistency.py — 文档一致性检查

功能：
1. 解析 docs/04_engineering/backlog.md 中所有标记为 ✅ 的条目
2. 提取条目中声称的文件路径（file:line 格式）
3. 验证这些路径是否真实存在
4. 如果路径不存在，报警并退出非零（CI 门禁）

使用：
    python scripts/check_docs_consistency.py           # 检查
    python scripts/check_docs_consistency.py --verbose # 详细输出

注意：
- 这是防"虚标完成"复发的历史病根
- 接入 ci.yml 独立 step
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKLOG_FILE = PROJECT_ROOT / "docs" / "04_engineering" / "backlog.md"

# 匹配 file:line 格式的正则（审查修复：backlog 实际用单冒号 `path:45`，
# 原实现要求双冒号 `path::45` 导致解析到 0 条、检查形同虚设）
PATH_PATTERN = re.compile(
    r"`([a-zA-Z0-9_/\.-]+\.(?:py|ts|tsx|mjs)):(\d+)(?:-(\d+))?`"
)

# 匹配 ✅ 条目的正则
COMPLETED_PATTERN = re.compile(r"^###\s+.*✅.*$", re.MULTILINE)


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

    for i, line in enumerate(lines, 1):
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


def main() -> None:
    parser = argparse.ArgumentParser(description="文档一致性检查")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="详细输出",
    )
    args = parser.parse_args()

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
    if not verify_paths(paths, args.verbose):
        print("\n[error] 文档一致性检查失败：存在虚假 ✅ 标记")
        sys.exit(1)

    print("\n[ok] 文档一致性检查通过")


if __name__ == "__main__":
    main()
