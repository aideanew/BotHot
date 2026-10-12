#!/usr/bin/env python3
"""离线重放 .gitleaks.toml 的判定（本机无 gitleaks 二进制时的等价复现器）。

用法：
    python "docs/任务规划V0.1.0/_workspace/gitleaks_replay.py" tree      # 扫工作树受跟踪文件
    python "docs/任务规划V0.1.0/_workspace/gitleaks_replay.py" history   # 扫全历史增量行
    python "docs/任务规划V0.1.0/_workspace/gitleaks_replay.py" line 01f6892 docker/compose.yml 157

原理与限制：
  * 只重放本仓库新增的自定义 rule（上游 150+ 内置 rule 不在本机复现，见文末 caveat）。
  * 判定链 = regex 命中 → 逐条 allowlist（regexes / paths / commits）放行 → 否则 flagged。
  * 与真 gitleaks 的差异：内置规则缺失 ⇒ 本机数字是「新规则效果」的下界证明，
    不能替代 CI 里 `gitleaks detect` 的结论。CI 数字必须在有二进制的环境复跑。
"""
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_override = os.environ.get("GITLEAKS_TOML")
CFG_PATH = Path(_override) if _override else ROOT / ".gitleaks.toml"
CFG = tomllib.loads(CFG_PATH.read_text(encoding="utf-8"))
RULES = [r for r in CFG.get("rules", []) if "regex" in r]
GLOBAL_PATHS = [re.compile(p) for p in CFG.get("allowlist", {}).get("paths", [])]


def tracked_files():
    out = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files", "-z"],
        cwd=ROOT, capture_output=True, check=True,
    ).stdout
    return [f for f in out.split(b"\0") if f]


def worktree_files(include_untracked=True):
    """tracked ∪ 未跟踪未忽略。

    必要性（本轮踩到）：只扫 `ls-files` 会**漏掉本次任务新增的文件**——
    `.gitleaks.toml` 在被提交前不在 ls-files 里，于是"0 告警"根本没覆盖到守卫配置自己，
    而它当时确实自命中。守卫的扫描域必须包含"将要提交的内容"，不是"上次提交的内容"。
    """
    files = [f.decode() for f in tracked_files()]
    if include_untracked:
        out = subprocess.run(
            ["git", "-c", "core.quotepath=false", "status", "--porcelain=v1",
             "--untracked-files=all", "-z", "--no-renames"],
            cwd=ROOT, capture_output=True, check=True,
        ).stdout.decode("utf-8", "replace")
        for tok in out.split("\0"):
            if not tok.strip():
                continue
            if tok[:2] in ("??", "! ") or tok.startswith("??"):
                files.append(tok[2:].strip().strip('"'))
    return files


def go_s(pattern):
    """把 Python 的 `\\s` 收窄成 RE2 的 `[\\t\\n\\f\\r ]`，让回放贴近 gitleaks 的真实引擎。

    必要性：Python3 的 `\\s`（str 模式）匹配 Unicode 空白，是 RE2 `\\s` 的**超集**；
    本文件所有正则里的 `\\s` 都在**取反字符类**中（`[^@/\\s\"']`），于是 Python
    排除得更多 ⇒ 命中得更少 ⇒ 回放数字是**下界**。已实证过分歧：
    口令段里夹一个 `\x0b`（垂直制表符）的 DSN 在 RE2 命中、在 Python 不命中。

    类内用裸转义序列替换（`\\t\\n\\f\\r `），类外用 `[\\t\\n\\f\\r ]`；
    遇到无法判定的上下文就报错退出，而不是悄悄给一个假的"0 告警"。
    """
    out, in_class, i = [], False, 0
    while i < len(pattern):
        c = pattern[i]
        if c == "\\":
            nxt = pattern[i + 1] if i + 1 < len(pattern) else ""
            if nxt == "s" and not in_class:
                out.append(r"[\t\n\f\r ]")
            elif nxt == "s":
                out.append(r"\t\n\f\r ")
            else:
                out.append(c + nxt)
            i += 2
            continue
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        out.append(c)
        i += 1
    return "".join(out)


def compile_rule_regex(rule):
    return re.compile(go_s(rule["regex"]))


def rule_hits(rule, text):
    rx = rule.setdefault("_rx", compile_rule_regex(rule))
    return [m.group(0) for m in rx.finditer(text)]


def allowed(rule, secret, line, path, commit=None):
    """按 gitleaks 语义判定一条 finding 是否被放行。

    关键口径（2026-10-12 由复审纠正）：`allowlists.regexes` 是对**单条 match**做 search，
    不是对整行。早期实现按整行判定，会产生假想的绕过——同一行放两条 DSN，
    其中一条是占位形状（`<password>` 一类），行级 search 会把它判给整行，
    于是同行的真口令那条也跟着被"污染放行"。改成 match 级后：
    真口令那条照常 FLAGGED，占位那条放行——这也让回放**更严**，
    此前"回放是下界"的结论在 match 数量维度上不再成立。
    """
    for a in rule.get("allowlists", []):
        if any(re.search(go_s(r), secret) for r in a.get("regexes", [])):
            return "regexes"
        if any(re.search(r, path) for r in a.get("paths", [])):
            return "paths"
        if commit and commit in a.get("commits", []):
            return "commits"
    return None


def _mask(seg):
    """告警行里只留形状，不留口令值。

    必要性（2026-10-12 实测触发）：一次"去 commits 白名单"的 counterfactual 复跑把整条
    DSN 连同真实口令段打进了 stdout。这类输出一旦被抄进证据文件或 CI 日志，就是在
    **新建**一份泄露副本（历史里那份删不掉，新的这份是我们自己加的）。
    gitleaks 二进制侧靠 `--redact`（security.yml 已带），复现器必须等价。
    本函数刻意**不**在本 docstring 里写出可匹配的形状——写出来就会改变被扫描物的计数。
    """
    return re.sub(r"(://[^:/\s]+:)[^@/\s]+(@)", r"\1<已脱敏>\2", seg)


def scan_text(rule, text, path, commit=None):
    """返回 (命中数, 告警列表)——逐 match 判定，非逐行。"""
    hits, flags = 0, []
    rx = rule.setdefault("_rx", compile_rule_regex(rule))
    for ln, line in enumerate(text.splitlines(), 1):
        for m in rx.finditer(line):
            hits += 1
            why = allowed(rule, m.group(0), line, path, commit)
            if why is None:
                flags.append(f"{path}:{ln} <- {_mask(m.group(0))} (放行理由=无)")
    return hits, flags


def do_tree(tracked_only=True):
    total_hits, all_flags = 0, []
    scope = tracked_files() if tracked_only else worktree_files()
    label = "tracked" if tracked_only else "tracked+untracked"
    n = 0
    for rel in scope:
        rel = rel.decode() if isinstance(rel, bytes) else rel
        n += 1
        if any(p.search(rel) for p in GLOBAL_PATHS):
            continue
        f = ROOT / rel
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for rule in RULES:
            h, fl = scan_text(rule, text, rel)
            total_hits += h
            all_flags += fl
    print(f"[{label}] 候选 {n} 个路径：自定义规则命中 {total_hits} 行 → 告警 {len(all_flags)} 行")
    for x in all_flags:
        print("  FLAG " + x)
    return all_flags


def do_history():
    commits = subprocess.run(["git", "rev-list", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.split()
    total_hits, all_flags = 0, []
    for c in commits:
        diff = subprocess.run(["git", "-c", "core.quotepath=false", "show", "--format=",
                               "--unified=0", c], cwd=ROOT, capture_output=True,
                              check=True).stdout.decode("utf-8", "replace")
        cur = None
        for line in diff.splitlines():
            if line.startswith("+++ b/"):
                cur = line[6:]
                if any(p.search(cur) for p in GLOBAL_PATHS):
                    cur = None
                continue
            if cur is None or not line.startswith("+") or line.startswith("+++"):
                continue
            for rule in RULES:
                rx = rule.setdefault("_rx", compile_rule_regex(rule))
                for m in rx.finditer(line[1:]):
                    total_hits += 1
                    if allowed(rule, m.group(0), line[1:], cur, c) is None:
                        all_flags.append(f"{c[:7]} {cur} <- {_mask(m.group(0))}")
    print(f"[history] {len(commits)} 个 commit 增量行：命中 {total_hits} → 告警 {len(all_flags)}")
    for x in all_flags:
        print("  FLAG " + x)
    return all_flags


def do_line(commit, path, lineno):
    full = subprocess.run(["git", "rev-parse", commit], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()
    text = subprocess.run(["git", "show", f"{full}:{path}"], cwd=ROOT,
                          capture_output=True, check=True).stdout.decode("utf-8", "replace")
    line = text.splitlines()[int(lineno) - 1]
    print(f"[control] {full[:7]}:{path}:{lineno} = {line.strip()}")
    print(f"[control] {full[:7]}:{path}:{lineno} = {line.strip()}")
    for rule in RULES:
        rx = rule.setdefault("_rx", compile_rule_regex(rule))
        ms = list(rx.finditer(line))
        for m in ms:
            why = allowed(rule, m.group(0), line, path, full)
            print(f"  rule={rule['id']} match={m.group(0)!r} → "
                  f"{'**可检出**' if why is None else '被 ' + why + ' 放行'}")
        if not ms:
            print("  （该行本规则不命中）")


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    mode = sys.argv[1] if len(sys.argv) > 1 else "tree"
    if mode == "tree":
        sys.exit(1 if do_tree(tracked_only=True) else 0)
    if mode == "worktree":
        sys.exit(1 if do_tree(tracked_only=False) else 0)
    if mode == "history":
        sys.exit(1 if do_history() else 0)
    do_line(*sys.argv[2:5])
