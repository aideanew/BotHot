"""S27.1 读数：`GUARD_BASE` 在一次性仓库里的三种形态（非空批 / 追平 / 坏基线）。

为什么不用主仓跑：主仓的批面随提交变化，读数不可复现；卡面要求的是"一次性仓库"。
本脚本只做三件事——建仓、提交、调用 `scripts/guards.py`，不改任何业务文件。

用法（仓库根）：python docs/06_validation/evidence/EVD-V15-27/s27_1_probe.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
GUARDS = ROOT / "scripts" / "guards.py"


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.name=Probe", "-c", "user.email=probe@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} 失败：{proc.stderr}")
    return proc.stdout.strip()


def run(repo: Path, env_extra: dict[str, str]) -> tuple[int, str]:
    env = dict(os.environ)
    env.pop("GUARD_BASE", None)
    env.update(env_extra)
    proc = subprocess.run([sys.executable, "-X", "utf8", "scripts/guards.py", "rounds-check"],
                          cwd=str(repo), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="guard-base-"))
    repo = tmp / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy2(GUARDS, repo / "scripts" / "guards.py")
    (repo / "notes.txt").write_text("base\n", encoding="utf-8")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "chore: 基线")
    first = git(repo, "rev-parse", "HEAD")
    for i in (1, 2):
        (repo / "notes.txt").write_text(f"base {i}\n", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", f"docs: 第 {i} 次改动（无轮次标记）")

    cases = [
        ("GUARD_BASE=两提交前", {"GUARD_BASE": first}, 0),
        ("未设 GUARD_BASE 且已追平", {"GUARD_BASE": "HEAD"}, 3),
        ("GUARD_BASE 不可解析", {"GUARD_BASE": "no-such-ref-27"}, 1),
    ]
    bad = 0
    for label, env_extra, expect in cases:
        rc, out = run(repo, env_extra)
        head = out.splitlines()[0] if out else ""
        print(f"[{label}] rc={rc}（期望 {expect}）  {head}")
        if rc != expect:
            bad += 1
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"结论：{len(cases) - bad}/{len(cases)} 与期望一致")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
