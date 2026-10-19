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

import ast
import os
import re
import subprocess
import sys
from collections.abc import Callable
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


# ══════════════════════════════════════════════════════ STEP-00T V14 两道闸
#
# 存在的理由（F-V14-06）：D-14 与 D-V4-03 都是**已签**裁决，但 `git grep -n "D-14" scripts/`
# 与 `git grep -n "D-V4-03" scripts/` 均 0 命中——签了却没有执行代码，等于没签。
# 两条判据都做成**纯函数**（输入合成数据即可证伪），git 侧只留一层薄壳，
# 这样"门会不会永远绿"这件事本身是可测的。

MAX_ROUNDS = 2  # D-14：≤2 轮，第 3 轮熔断（不是 S0G.2.1 旧卡面的 >3；以 D-V11-04 为准）
_STEP_ID_RE = re.compile(r"STEP-([0-9A-Za-z]+)")
# `(?<![A-Za-z0-9])` 是必须的：不加词界时 `background-3`、`reorder around 3 tests`
# 都会被当成"第 3 轮"（实测），而那是**假红**——门一红人就停手，假红的代价是门被关掉。
_ROUND_RE = re.compile(r"第\s*(\d+)\s*轮|(?<![A-Za-z0-9])round[\s-]*(\d+)", re.IGNORECASE)
_REWORK_TOKENS = ("返工", "重做")
_REWORK_THRESHOLD = MAX_ROUNDS + 1  # 出现「第 3 轮」这类显式轮号即红

# 耦合门（D-V4-03）的两个 glob 根（相对仓库根，POSIX 分隔符）
EVIDENCE_ROOT = "docs/06_validation/evidence"
TESTS_ROOT = "apps/api/tests"


def _round_numbers(subject: str) -> list[int]:
    """主题里出现的全部轮号（`第3轮` / `round-3` 两种写法，本仓历史实际都有）。"""
    out: list[int] = []
    for m in _ROUND_RE.finditer(subject):
        out.append(int(m.group(1) or m.group(2)))
    return out


def _is_round_marker(subject: str) -> bool:
    """轮次标记：含返工/重做，或含任一显式轮号。"""
    return any(tok in subject for tok in _REWORK_TOKENS) or bool(_round_numbers(subject))


def rounds_violations(subjects: list[str], max_rounds: int = MAX_ROUNDS) -> list[dict[str, object]]:
    """按 STEP id 归集轮次标记，返回越限项（纯函数，可喂合成主题）。

    两条红路（缺一会漏）：
      1. 同一卡在范围内被标记 > max_rounds 次 ⇒ 已经第 3 轮；
      2. 任一主题直接写出 ≥ max_rounds+1 的轮号 ⇒ 即便前面的轮发生在范围外，
         "第 3 轮"这个事实本身就够熔断。
    """
    limit = max_rounds
    marks: dict[str, list[str]] = {}
    for subject in subjects:
        if not _is_round_marker(subject):
            continue
        for step_id in _STEP_ID_RE.findall(subject):
            marks.setdefault(step_id, []).append(subject)
    out: list[dict[str, object]] = []
    for step_id, hits in sorted(marks.items()):
        explicit = [n for s in hits for n in _round_numbers(s) if n >= _REWORK_THRESHOLD]
        if len(hits) > limit or explicit:
            out.append({
                "step": step_id,
                "count": len(hits),
                "explicit_rounds": sorted(set(explicit)),
                "subjects": hits,
            })
    return out


def rounds_check(base: str = "origin/main") -> int:
    """D-14 轮次熔断门：统计 `base..HEAD` 内每张卡的返工轮次，越限即红并点名。"""
    subjects, warn = _commit_subjects(base)
    if warn:
        print(f"❌ rounds-check：{warn}", flush=True)
        return 1
    if not subjects:
        # 范围空 ⇒ 门什么都没看。这里必须返回"不是通过"的第三态（rc=3，
        # 与 evidence-check 的"工具缺席"同一口径），否则空范围会伪装成 PASS。
        print(f"⚠️  rounds-check：{base}..HEAD 为空 ⇒ 无可检提交，**这不是通过**（rc=3）", flush=True)
        return 3
    violations = rounds_violations(subjects)
    print(f"rounds-check：范围 {base}..HEAD 共 {len(subjects)} 个提交，"
          f"阈值 ≤{MAX_ROUNDS} 轮（D-14，第 {MAX_ROUNDS + 1} 轮熔断）", flush=True)
    for item in violations:
        print(f"❌ STEP-{item['step']}：返工标记 {item['count']} 次"
              + (f"，且出现显式第 {item['explicit_rounds']} 轮" if item["explicit_rounds"] else ""), flush=True)
        for subject in item["subjects"]:  # type: ignore[union-attr]
            print(f"     · {subject}")
    if violations:
        print(f"结论：{len(violations)} 张卡越过 D-14 ⇒ 停手并升级裁决"
              f"（不得自行开第 {MAX_ROUNDS + 2} 轮）", flush=True)
        return 1
    print("✅ rounds-check：范围内无卡越过轮次上限", flush=True)
    return 0


def _git(*args: str) -> tuple[int, str]:
    proc = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def _commit_subjects(base: str) -> tuple[list[str], str]:
    """`base..HEAD` 的主题列表；base 不可解析时返回错误说明（调用方判红，不静默放行）。"""
    rc, _ = _git("rev-parse", "--verify", "--quiet", base)
    if rc:
        return [], f"基线 {base!r} 不可解析（先 fetch，或显式传 --base）"
    rc, out = _git("log", "--format=%s", f"{base}..HEAD")
    if rc:
        return [], f"git log {base}..HEAD 失败（rc={rc}）"
    return [line for line in out.splitlines() if line.strip()], ""


def count_test_cases(source: str) -> int:
    """AST 数 `def test_` / `async def test_`（含类内方法），不用 grep 行数。

    为什么不用 grep：一行 `def test_x():` 与被注释掉的 `# def test_x():` 在行数上等价，
    而在收集上不等价；本门要判的是"有没有新增可跑用例"。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test_")
    )


def _is_evidence_py(rel: str) -> bool:
    return rel.startswith(EVIDENCE_ROOT + "/") and rel.endswith(".py")


def _is_tests_py(rel: str) -> bool:
    return (
        rel.startswith(TESTS_ROOT + "/")
        and rel.endswith(".py")
        and rel.rsplit("/", 1)[-1].startswith("test_")
    )


def parse_name_status(out: str) -> list[tuple[str, str, str | None]]:
    """`git diff --name-status` 输出 → [(状态, 新路径, 旧路径或 None)]（纯函数，可喂合成 diff）。"""
    rows: list[tuple[str, str, str | None]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, paths = parts[0], parts[1:]
        if len(paths) == 2:  # R100\t旧\t新 / C100\t源\t目标
            rows.append((status[0], paths[1], paths[0]))
        else:
            rows.append((status[0], paths[0], None))
    return rows


def coupling_counts(
    rows: list[tuple[str, str, str | None]],
    read_head: Callable[[str], str],
    read_base: Callable[[str], str],
) -> dict[str, int]:
    """证据脚本净增数（A/U 加、D 减）与用例净增（每个改动文件 新−旧 的 AST 用例数之差）。

    读文件走注入的 `read_head` / `read_base` 两个回调：判据本身保持纯函数，
    反证用例可以喂合成 diff + 合成文件表，不必造 git 状态。
    未跟踪的新证据脚本（状态 U）与 A 同权——它同样需要配对用例。
    """
    evidence_added = 0
    tests_delta = 0
    for status, new_path, old_path in rows:
        if _is_evidence_py(new_path) and status in ("A", "U"):
            evidence_added += 1
        elif _is_evidence_py(new_path) and status == "D":
            evidence_added -= 1
        # 用例侧要**两侧各自算**：只看 new_path 时，把 `test_gone.py` 改名成
        # `helper_x.py`（R 状态，新路径不再是 test_）会一整条被跳过 ⇒ 两条用例消失
        # 而 tests_delta 记 0（实测），门在"删用例最彻底"的形态上反而放行。
        if _is_tests_py(new_path) and status != "D":
            tests_delta += count_test_cases(read_head(new_path))
        old_rel = old_path if old_path is not None else (new_path if status in ("M", "D", "R") else None)
        if old_rel and status not in ("A", "U") and _is_tests_py(old_rel):
            tests_delta -= count_test_cases(read_base(old_rel))
    return {"evidence_added": evidence_added, "tests_delta": tests_delta}


def coupling_violated(evidence_added: int, tests_delta: int) -> bool:
    """D-V4-03 判据：证据脚本净增 > 0 且 用例净增 < 1 ⇒ 红。

    卡面写的是"用例净增 = 0"；这里取 `< 1`（即 ≤0）——加证据脚本同时**删**用例是更坏的
    情形，按 =0 判会放行。这是执行方对判据的唯一一处收紧，已写进 EVD-V14-00T §3 待规划方追认。
    """
    return evidence_added > 0 and tests_delta < 1


def missing_base_blobs(rows: list[tuple[str, str, str | None]], blob_exists: Callable[[str], bool]) -> list[str]:
    """需要读基线、基线里却没有的测试文件（纯函数，可喂合成判定）。

    为什么单独抽出来：`read_base` 读不到时交回空串 ⇒ 旧用例数被当成 0 ⇒ tests_delta 被**抬高**
    （实测：M 行读不到基线时报「净增 1」）。那是往绿的方向偏，所以必须先证伪再算。
    """
    out: list[str] = []
    for status, new_path, old_path in rows:
        if status in ("A", "U"):
            continue  # 新增侧本来就没有基线版本
        old_rel = old_path if old_path is not None else new_path
        if _is_tests_py(old_rel) and not blob_exists(old_rel):
            out.append(old_rel)
    return out


def coupling_check(base: str = "origin/main") -> int:
    """在 base 与工作树之间做耦合判定（覆盖未提交的改动，门在提交前才有用）。"""

    def read_head(rel: str) -> str:
        path = ROOT / rel
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""

    def read_base(rel: str) -> str:
        rc, out = _git("show", f"{base}:{rel}")
        return out if rc == 0 else ""

    rc, _ = _git("rev-parse", "--verify", "--quiet", base)
    if rc:
        print(f"❌ evidence 耦合门：基线 {base!r} 不可解析 ⇒ 红（fail-closed，不许静默放行）", flush=True)
        return 1
    _rc, tracked = _git("diff", "--name-status", base, "--", EVIDENCE_ROOT, TESTS_ROOT)
    _rc2, untracked = _git("ls-files", "--others", "--exclude-standard", "--", EVIDENCE_ROOT, TESTS_ROOT)
    rows = parse_name_status(tracked) + [("U", line, None) for line in untracked.splitlines() if line.strip()]

    # 基线里取不到的旧测试文件必须先证伪，否则 `read_base` 的空串会被当成"原来没有用例"
    # ⇒ tests_delta 被抬高（往绿的方向偏）。详见 missing_base_blobs 的 docstring。
    def blob_exists(rel: str) -> bool:
        return _git("cat-file", "-e", f"{base}:{rel}")[0] == 0

    for rel in missing_base_blobs(rows, blob_exists):
        print(f"❌ evidence 耦合门：基线 {base} 里取不到 {rel}"
              " ⇒ 红（不许把「读不到」当成「原来没有用例」）", flush=True)
        return 1

    counts = coupling_counts(rows, read_head, read_base)
    print(f"evidence 耦合门（D-V4-03）：范围 {base}..工作树 ⇒ 证据脚本净增 {counts['evidence_added']}，"
          f"用例净增 {counts['tests_delta']}", flush=True)
    if coupling_violated(counts["evidence_added"], counts["tests_delta"]):
        print("❌ 加了证据脚本却没加可跑用例：证据的效力只在有人复跑时存在，而 CI 不跑这些脚本"
              "（F-V14-05 的静默腐坏就是这么来的）", flush=True)
        return 1
    return 0


EVIDENCE_PROOFS = [
    "docs/06_validation/evidence/EVD-V2-00/prove_dsn_policy.py",
    "docs/06_validation/evidence/EVD-V2-00/prove_dsn_policy.py --self-test",
    "docs/06_validation/evidence/EVD-V2-00/prove_provider_shapes.py",
    "docs/06_validation/evidence/EVD-V2-00/g24_static_check.py",
    "docs/06_validation/evidence/EVD-V2-00/g24_static_check.py --self-test",
    "docs/06_validation/evidence/EVD-V2-00R/prove_net_isolation.py",
    "docs/06_validation/evidence/EVD-V2-00R/prove_net_isolation.py --self-test",
]


def evidence_check(base: str = "origin/main") -> int:
    """stdlib 证据逐条复跑；真实工具步缺任一个就 rc=3（不是 PASS 也不是 FAIL）。

    S00T.V14.2：先跑 D-V4-03 耦合门——判据必须在复跑脚本**之前**，否则脚本一红就
    `return 1` 短路，耦合这一维永远不会被报出来。
    """
    if coupling_check(base):
        return 1
    for spec in EVIDENCE_PROOFS:
        parts = spec.split()
        target = ROOT / parts[0]
        print(f"── {spec} ──")
        if not target.exists():
            print(f"❌ 证据脚本不存在：{parts[0]}", flush=True)
            return 1
        code = subprocess.run([sys.executable, "-X", "utf8", str(target), *parts[1:]], cwd=str(ROOT)).returncode
        if code:
            print(f"❌ 证据复跑失败：{spec}（rc={code}）", flush=True)
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
            print(f"❌ {name} 失败（rc={code}）", flush=True)
            return code
    print("✅ evidence-check 全部通过（stdlib 证据 + 真实工具两步）", flush=True)
    return 0


def shutil_which(name: str) -> str | None:
    import shutil

    return shutil.which(name)


def _venv_script(name: str) -> str | None:
    base = API / ".venv" / ("Scripts" if os.name == "nt" else "bin") / (name + (".exe" if os.name == "nt" else ""))
    return str(base) if base.exists() else None


GUARDS = {"guard-ports": guard_ports, "guard-versions": guard_versions,
          "guard-structure": guard_structure, "evidence-check": evidence_check,
          "rounds-check": rounds_check}
# 只有这两道门需要基线（其余门看的是仓库现状，与"这一批改了什么"无关）
BASE_AWARE = ("evidence-check", "rounds-check")
DEFAULT_BASE = "origin/main"


def main(argv: list[str]) -> int:
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    name = argv[0] if argv else ""
    base = DEFAULT_BASE
    rest = argv[1:]
    if rest[:1] == ["--base"]:
        if len(rest) != 2:
            print("用法：--base 后面必须且只能跟一个可解析的 ref")
            return 1
        base = rest[1]
        rest = []
    if rest or not name or name not in GUARDS:
        print(f"用法：python scripts/guards.py <{'|'.join(GUARDS)}> [--base <ref>]")
        return 1
    if base != DEFAULT_BASE and name not in BASE_AWARE:
        # 不接受 --base 的门被传了 --base：静默忽略会制造"我指定了基线所以判了历史"的错觉
        print(f"❌ {name} 不接受 --base（它不比较范围，只看仓库现状）", flush=True)
        return 1
    fn = GUARDS[name]
    return fn(base) if name in BASE_AWARE else fn()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
