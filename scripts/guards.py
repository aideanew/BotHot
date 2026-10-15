#!/usr/bin/env python3
"""架构守卫的跨平台实体（STEP-00X S00X.1.2/S00X.3.1）。

为什么从 Makefile 搬进 Python：GNU make 4.4.1 for Windows 跑不了那些
"多行 `; \\` 续行 + shell 变量"的 recipe（实测 `make guard-ports` 报
`printf: -c: line 4: unexpected EOF while looking for matching '"'`，
即使命令行走 LF 也一样）。这类目标此前只有 Linux 侧能跑，
Windows 上"跑不了"和"跑了没问题"在读数上长得一模一样——正是要消灭的东西。

唯一源纪律：Makefile 的对应目标与 scripts/entry.py 都只转调本文件，不各留一份实现。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps" / "api"
WEB = ROOT / "apps" / "web"
DOCKER_DIR = ROOT / "docker"

# 端口表（AGENTS.md）：3333 是 AideanBot 旧端口，BotHot 一律禁用
FORBIDDEN_PORT = "3333"
SESSION_COOKIE = "bothot_session"

STRUCTURE_DIRS = [
    API / "app",
    WEB / "app",
    ROOT / "packages" / "contracts" / "src",
    ROOT / "docs" / "00_governance",
]


def _grep(needle: str, roots: list[Path], globs: list[str]) -> list[str]:
    """跨平台的 grep -rn：返回 "相对路径:行号: 内容"，只找文本文件、跳过大文件。

    两个实测过的坑：
    - 必须 `fullmatch`。用 `search` 时 `*.py` 会命中 `llm_summary.cpython-312.pyc`
      （文件名里含子串 ".py"），把字节流里的巧合当成源码命中 ⇒ 守卫永久假红。
    - 跳过 `__pycache__/node_modules/.venv/.git`：既快，也避免二进制误报。
    """
    hits: list[str] = []
    def to_rx(glob: str) -> re.Pattern[str]:
        # 按 `*` 切段再逐段 re.escape：先 replace(".") 后 replace("*") 的写法会把
        # 自己刚生成的 `.*` 里的点又转义掉，模式含义就错了（实测踩过）
        return re.compile(".*".join(re.escape(p) for p in glob.split("*")) + "$")

    pats = [to_rx(glob) for glob in globs]
    skip = {"__pycache__", "node_modules", ".venv", ".git", ".pnpm-store", "dist", "build", ".next"}
    for base in roots:
        if not base.exists():
            continue
        files = [base] if base.is_file() else [
            p for p in base.rglob("*")
            if p.is_file() and not any(part in skip for part in p.parts)]
        for f in files:
            if not any(p.fullmatch(f.name) for p in pats):
                continue
            try:
                if f.stat().st_size > 4_000_000:
                    continue
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for no, line in enumerate(text.splitlines(), 1):
                if needle in line:
                    hits.append(f"{f.relative_to(ROOT)}:{no}: {line.strip()[:120]}")
    return hits


def guard_ports() -> int:
    print("检查端口分配...")
    backend_hits = _grep(FORBIDDEN_PORT, [API / "app", DOCKER_DIR],
                         ["*.py", "*.yml", "*.yaml", "*.sh", "*.env*", "*.example"])
    frontend_hits = _grep(FORBIDDEN_PORT, [WEB / "app", WEB / "lib", WEB / "e2e"],
                          ["*.ts", "*.tsx", "*.json", "*.mjs"])
    rc = 0
    if backend_hits:
        print("❌ 后端/编排侧发现旧端口 3333：")
        print("\n".join(f"  {h}" for h in backend_hits))
        rc = 1
    if frontend_hits:
        print("❌ 前端侧发现旧端口 3333：")
        print("\n".join(f"  {h}" for h in frontend_hits))
        rc = 1
    if rc:
        print("❌ 发现旧端口 3333，需清理")
        return rc
    print(f"✅ 无旧端口 {FORBIDDEN_PORT}")
    cookie_ok = any(SESSION_COOKIE in (p.read_text(encoding="utf-8", errors="replace"))
                    for p in (API / "app").rglob("*.py"))
    print(f"✅ session cookie = {SESSION_COOKIE}" if cookie_ok
          else f"❌ session cookie 名称不正确（未在任何 .py 中找到 {SESSION_COOKIE}）")
    return 0 if cookie_ok else 1


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def guard_versions() -> int:
    print("检查版本锚点一致性...")
    nvmrc = _read(WEB / ".nvmrc").strip()
    dockerfile = ""
    for line in _read(WEB / "Dockerfile").splitlines():
        m = re.search(r"node:([0-9]+)", line)
        if m:
            dockerfile = m.group(1)
            break
    pkg = _read(WEB / "package.json")
    engines = ""
    m = re.search(r'"engines"\s*:\s*{[^}]*?"node"\s*:\s*">=\s*(\d+)', pkg, re.S)
    if m:
        engines = m.group(1)
    pm = re.search(r"pnpm@(\d+)", pkg)
    pm_version = pm.group(1) if pm else ""
    compose = ""
    tail = _read(DOCKER_DIR / "compose.yml")
    fe = tail[tail.find("\n  frontend:"):] if "\n  frontend:" in tail else ""
    m = re.search(r"BASE_IMAGE:-node:(\d+)", fe) or re.search(r"BASE_IMAGE:\$\{BASE_IMAGE:-node:(\d+)\}", fe)
    if m:
        compose = m.group(1)
    print(f"  .nvmrc node: {nvmrc}")
    print(f"  Dockerfile node: {dockerfile}")
    print(f"  engines.node: {engines}")
    print(f"  packageManager pnpm major: {pm_version}")
    print(f"  compose BASE_IMAGE node: {compose}")
    rc = 0
    for label, value in ((".nvmrc 为空或不存在", nvmrc), ("Dockerfile 未找到 node 版本", dockerfile),
                         ("package.json engines.node 未找到", engines),
                         ("packageManager 未找到 pnpm 版本", pm_version),
                         ("compose 前端 BASE_IMAGE 未找到 node 锚（compose 可覆盖 Dockerfile FROM，必须同锚盯防）", compose)):
        if not value:
            print(f"❌ {label}")
            rc = 1
    if rc == 0 and nvmrc:
        major = nvmrc.split(".")[0]
        for label, value in (("Dockerfile", dockerfile), ("engines.node", engines),
                             ("compose BASE_IMAGE", compose)):
            if major != value:
                print(f"❌ .nvmrc 主版本 ({major}，全值 {nvmrc}) != {label} ({value})")
                rc = 1
    print("❌ 版本锚点不一致" if rc else "✅ 版本锚点一致")
    return rc


def guard_structure() -> int:
    print("检查目录结构...")
    rc = 0
    for d in STRUCTURE_DIRS:
        rel = d.relative_to(ROOT)
        if d.exists():
            print(f"✅ {rel} 存在")
        else:
            print(f"⚠️  {rel} 不存在")
            rc = 1
    return rc


EVIDENCE_PROOFS = [
    "docs/06_validation/evidence/EVD-V2-00/prove_dsn_policy.py",
    "docs/06_validation/evidence/EVD-V2-00/prove_dsn_policy.py --self-test",
    "docs/06_validation/evidence/EVD-V2-00/prove_provider_shapes.py",
    "docs/06_validation/evidence/EVD-V2-00/g24_static_check.py",
    "docs/06_validation/evidence/EVD-V2-00/g24_static_check.py --self-test",
    "docs/06_validation/evidence/EVD-V2-00R/prove_net_isolation.py",
    "docs/06_validation/evidence/EVD-V2-00R/prove_net_isolation.py --self-test",
]


def evidence_check() -> int:
    """stdlib 证据逐条复跑；真实工具步缺任一个就 rc=3（不是 PASS 也不是 FAIL）。"""
    rc = 0
    for spec in EVIDENCE_PROOFS:
        parts = spec.split()
        target = ROOT / parts[0]
        print(f"── {spec} ──")
        if not target.exists():
            print(f"❌ 证据脚本不存在：{parts[0]}")
            return 1
        code = subprocess.run([sys.executable, "-X", "utf8", str(target), *parts[1:]], cwd=str(ROOT)).returncode
        if code:
            print(f"❌ 证据复跑失败：{spec}（rc={code}）")
            return 1
    tool_steps = []
    ruff = shutil_which("ruff") or _venv_script("ruff")
    if ruff:
        tool_steps.append(("ruff", [ruff, "check", "app", "tests"], API))
    else:
        print("SKIP(tool missing) ruff——stdlib 近似表(g24)判不了的成员序/段序之外，终判在这一步")
        tool_steps = None
    gitleaks = shutil_which("gitleaks")
    if not gitleaks and os.environ.get("LOCALAPPDATA"):
        cand = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "tools" / "gitleaks" / "gitleaks.exe"
        gitleaks = str(cand) if cand.exists() else None
    if gitleaks and tool_steps is not None:
        tool_steps.append(("gitleaks", [gitleaks, "detect", "--source", ".", "--config", ".gitleaks.toml",
                                     "--no-banner"], ROOT))
    else:
        print("SKIP(tool missing) gitleaks——Security 门禁的终判在这一步，本机只跑 secret_shape_scan 做召回")
        tool_steps = None
    if tool_steps is None:
        print("⚠ evidence-check：stdlib 证据全过，但真实工具步没跑 ⇒ 退出码 3（这不是 PASS，也不是 FAIL）")
        return 3
    for name, cmd, cwd in tool_steps:
        print(f"── 真实工具步：{name} ──")
        code = subprocess.run(cmd, cwd=str(cwd)).returncode
        if code:
            print(f"❌ {name} 失败（rc={code}）")
            return code
    print("✅ evidence-check 全部通过（stdlib 证据 + 真实工具两步）")
    return 0


def shutil_which(name: str) -> str | None:
    import shutil

    return shutil.which(name)


def _venv_script(name: str) -> str | None:
    base = API / ".venv" / ("Scripts" if os.name == "nt" else "bin") / (name + (".exe" if os.name == "nt" else ""))
    return str(base) if base.exists() else None


GUARDS = {"guard-ports": guard_ports, "guard-versions": guard_versions,
          "guard-structure": guard_structure, "evidence-check": evidence_check}


def main(argv: list[str]) -> int:
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    if len(argv) != 1 or argv[0] not in GUARDS:
        print(f"用法：python scripts/guards.py <{'|'.join(GUARDS)}>")
        return 1
    return GUARDS[argv[0]]()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
