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
# D-V12-02（S27.5）：主题里只写 L3 号时按**第一段**反推卡号（`S1.3.2` → 1，`S27.3` → 27）。
# 这是关掉 EVD-V14-00T §4-3 登记的真实盲区：`…S1.3.2 的第 7 轮熔断…` 改前零归属。
_L3_ID_RE = re.compile(r"(?<![A-Za-z0-9])S([0-9]+)\.[0-9]+(?:\.[0-9]+)*")
# `(?<![A-Za-z0-9])` 是必须的：不加词界时 `background-3`、`reorder around 3 tests`
# 都会被当成"第 3 轮"（实测），而那是**假红**——门一红人就停手，假红的代价是门被关掉。
# 第 2 轮复验又抓到同族两个漏网：`second-round 3`（`round` 前是连字符）、`back-ground-3`，
# 所以 lookbehind 要连 `-`/`_` 一起挡；而 `round_3` 这种下划线写法仍要认 ⇒ 分隔符类加 `_`。
_ROUND_RE = re.compile(r"第\s*(\d+)\s*轮|(?<![A-Za-z0-9_-])round[\s_-]*(\d+)", re.IGNORECASE)
# D-V12-02：中文数字轮号（`第二轮`…`第二十轮`）。P-31 记的 STEP-01 那 10 条主题就是这种写法，
# 改前完全不计数。上界取二十——D-14 只到第 3 轮，超过二十的写法不存在，多认只会引入歧义。
_CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}
_ROUND_CN_RE = re.compile(r"第\s*([一二三四五六七八九十]{1,3})\s*轮")
_REWORK_TOKENS = ("返工", "重做")
_REWORK_THRESHOLD = MAX_ROUNDS + 1  # 出现「第 3 轮」这类显式轮号即红

# 耦合门（D-V4-03）的两个 glob 根（相对仓库根，POSIX 分隔符）
EVIDENCE_ROOT = "docs/06_validation/evidence"
TESTS_ROOT = "apps/api/tests"


def _cn_number(text: str) -> int | None:
    """中文数字 → 整数，只支持 D-14 需要的 1～20（`十` / `十一` / `二十`）。"""
    if not text or any(ch not in _CN_DIGITS and ch != "十" for ch in text):
        return None
    if "十" not in text:
        if len(text) != 1:
            return None
        return _CN_DIGITS[text]
    left, _, right = text.partition("十")
    if "十" in right:
        return None
    tens = _CN_DIGITS[left] if left else 1
    ones = _CN_DIGITS[right] if right else 0
    value = tens * 10 + ones
    return value if 1 <= value <= 20 else None


def _round_numbers(subject: str) -> list[int]:
    """主题里出现的全部轮号（`第3轮` / `round-3` / `第三轮` 三种写法，本仓历史实际都有）。"""
    out: list[int] = []
    for m in _ROUND_RE.finditer(subject):
        out.append(int(m.group(1) or m.group(2)))
    for m in _ROUND_CN_RE.finditer(subject):
        value = _cn_number(m.group(1))
        if value is not None:
            out.append(value)
    return out


def _primary_card(subject: str) -> str:
    """一条主题归属的**唯一**卡号（D-V12-02：跨卡提及只计主卡）。

    优先级：首个 `STEP-<id>` > 首个 L3 号（`S<卡号>.`）。两者都没有 ⇒ 空串（不归属）。
    """
    ids = _STEP_ID_RE.findall(subject)
    if ids:
        return ids[0]
    l3 = _L3_ID_RE.findall(subject)
    return l3[0] if l3 else ""


def _is_round_marker(subject: str) -> bool:
    """轮次标记：含返工/重做，或含任一显式轮号。"""
    return any(tok in subject for tok in _REWORK_TOKENS) or bool(_round_numbers(subject))


def rounds_violations(subjects: list[str], max_rounds: int = MAX_ROUNDS) -> list[dict[str, object]]:
    """按 STEP id 归集轮次标记，返回越限项（纯函数，可喂合成主题）。

    两条红路（缺一会漏）：
      1. 同一卡在范围内被标记 > max_rounds 次 ⇒ 已经第 3 轮；
      2. 任一主题直接写出 ≥ max_rounds+1 的轮号 ⇒ 即便前面的轮发生在范围外，
         "第 3 轮"这个事实本身就够熔断。

    归属口径（D-V12-02 / S27.5）：每条主题只计**主卡**（`_primary_card`），
    跨卡提及不再连坐；只写 L3 号的按第一段反推卡号。
    """
    limit = max_rounds
    marks: dict[str, list[str]] = {}
    for subject in subjects:
        if not _is_round_marker(subject):
            continue
        card = _primary_card(subject)
        if card:
            marks.setdefault(card, []).append(subject)
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
    # `-c core.quotepath=false` 不是美化：默认 git 会把非 ASCII 路径转义成 "\344\273\273…"，
    # 于是 `ROOT / 那个字符串` 不存在 ⇒ 中文命名的文件被当成「本批已删除」跳过。
    # 实测本批第一次跑门时 7 个待检路径只扫了 5 个（EVD-V4-00P §5）。
    proc = subprocess.run(["git", "-c", "core.quotepath=false", *args],
                          cwd=str(ROOT), capture_output=True)
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


# ══════════════════════════════════════════════════════ STEP-00P 敏感形门（S00P.1.1）
#
# 判据实体为什么在这里、而不是子进程直调卡面点名的
# `docs/任务规划V0.5.0/evidence/65f508b/secret_shape_scan.py`：
# 实测把**单个文件**当参数喂给它——它的扫描集是 `root.rglob("*")`，对文件根返回空集 ⇒
# 「文件数 0 / HIGH 命中 0 / rc=0」（同一个 patch 文件按目录扫到 5 条，按文件扫到 0 条；
# 现跑读数在 EVD-V4-00P §2）。照卡面直调就是造一个**永远绿的安全门**，那比没有门更坏。
#
# 下面四条常量逐条从那个脚本搬运、**不改语义**（不新增豁免、不改规则），
# 由 `apps/api/tests/test_secret_shape_gate.py` 与脚本源码里的字面量逐条对账防副本漂移。
# 该卡禁止修改 V0.1…V0.8 规划树，所以不动原脚本；两处并存由对账用例钉住。

SECRET_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("dsn-embedded-password", re.compile(r"(?i)[a-z][a-z0-9+.\-]*://[^:/\s\"']+:[^@/\s\"']+@")),
    ("aws-akia", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b")),
    ("github-fine-grained", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b")),
    ("private-key-block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    ("vendor-key-assign", re.compile(
        r"(?i)(?:tikhub|dajiala|wellbyte|redfox)[_-]?(?:api[_-]?key|token)"
        r"\s*[:=]\s*\S{8,}")),
]

# 占位值不算秘密（变量引用 / 模板 / 本地-CI 固定占位凭据）——与原脚本同源
SECRET_ALLOW: list[re.Pattern[str]] = [
    re.compile(r"[:/](?:\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*|<[^>\s]+>|%[sdv])@"),
    re.compile(r"://(?:[^:/\s\"@]+|<user>):"
               r"(?:bothot|bothot_dev|bothot_ci|aideanbot|nobody|nosuch|not_a_secret)@"),
]

# 口令赋值形（`password = "…"`）：值像占位/脱敏就不算，其余一律 HIGH 交人判
SECRET_ASSIGN = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key|dsn)\b"
    r"\s*[:=]\s*[\"']?([^\"'\s,;)}]{4,})")
SECRET_FAKE = re.compile(r"(?i)^(?:<[^>]*>|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|%[sdv]"
                         r"|change[_-]?me|your[_-]?\S*|REDACTED\S*|x{4,}|\*{4,})$")
# 赋值判据的三条补充豁免：规则定义行自身（否则召回器举报自己）、脱敏串、尖括号/变量模板
_SECRET_ASSIGN_SKIP = re.compile(r"(?i)redact|\*{3,}|x{4,}|<[^>]+>|\$\{")

# 与 EVD-V5-00S/secret_shape_gate.py 的差异（读代码得来，非推测）：那条 key 赋值判据要求
# 值被引号包住且 ≥20 字符，召回面比这里的 SECRET_ASSIGN 窄；本门取 V0.5.0 的宽口径，
# 因为短口令与 YAML 无引号写法都不能放过。分歧已登记待规划方追认。

_SECRET_MAX_BYTES = 4_000_000  # 与 _grep 同一上限：超了当产物/资源，不当文本


def _mask_shape(rule: str, frag: str) -> str:
    """命中只报形状，不报正文。

    原脚本打印匹配串前 90 个字符——对连接串形状而言那已经是**凭据正文本身**，
    会落进终端与 CI 日志。安全铁律第 1 条禁止这件事，所以这里刻意与原脚本的
    **输出格式**不同（判据相同）。规则名已经说明是哪一族，片段只用来定位，不用来复原值。

    连接串的**账号位也打码**（只留 4 字符）：复核实测出「把 token 直接放在 userinfo 的用户名位、
    口令位填一个占位字符」这类用法——只隐口令段等于把凭据整条留在输出里。
    匹配串本身止于 at 符号，所以主机段从来不在片段里；定位靠「文件:行号 + 规则名」，不靠片段复原。
    """
    if rule == "dsn-embedded-password":
        head, sep, rest = frag.partition("://")
        userinfo, _, host = rest.partition("@")
        user, _, _pw = userinfo.partition(":")
        return f"{head}://{user[:4]}***:***@{host}"
    return frag[:4] + "***"


def secret_scan(text: str, code: bool = False,
                lang: str = "hash") -> tuple[list[tuple[str, int, str]], int]:
    """纯函数：文本 → ([(规则, 行号, 打码形状)], 被 ALLOW 放行处数)。

    `code=True` 走源码模式（S27.V15.1）：源码里的表达式不再误报，字面量照报。
    默认 `False` 是**刻意**的——文档面读数必须与改前逐字节一致（④）。
    `lang` 只影响注释符（`hash` = Python 的 `#`，`slash` = JS/TS 的 `//`）。

    合成字符串即可证伪，不必造 git 状态——"这判据会不会永远绿"必须可测。

    两处与那条脚本的实现差异都是**收紧**（方向：少漏检），且各有反证用例：
    - ALLOW 对**匹配段**判，不对整行判。行级判会被同一行里一处无关的占位形（`%s@tenant`）
      带着真凭据一起放行（复核实测 ⇒ 漏检）。gitleaks 的 allowlist regex 本来也是作用在匹配上。
    - `re.compile` 豁免只认「值本身以 re.compile 开头」的规则定义行。
      行级豁免让 `password = "…"  # 注释里提到 re.compile` 也一并放行（复核实测 ⇒ 漏检）。
    """
    hits: list[tuple[str, int, str]] = []
    allowed = 0
    if code:
        return secret_scan_source(text, lang)
    for no, line in enumerate(text.splitlines(), 1):
        for name, rx in SECRET_RULES:
            for m in rx.finditer(line):
                frag = m.group(0)
                if any(a.search(frag) for a in SECRET_ALLOW):
                    allowed += 1
                    continue
                hits.append((name, no, _mask_shape(name, frag)))
        for m in SECRET_ASSIGN.finditer(line):
            val = m.group(2)
            if (val.startswith("re.compile") or SECRET_FAKE.match(val)
                    or _SECRET_ASSIGN_SKIP.search(val)):
                continue
            hits.append(("assign", no, f"{m.group(1)}=<已打码，值长 {len(val)} 字符>"))
    return hits, allowed


# ══════════════════════════════════════════ 源码模式（S27.V15.1 / D-V12-21）
#
# 为什么需要第二种口径：P-40 的 14 个自有源码文件里，命中全是**表达式**——
# 键名紧接赋值号、右值是解密函数调用；对象键名后接冒号、右值是表单对象属性；
# 键名等于配置对象属性。门没有豁免通道，所以任何触碰这些文件的提交都被永久挡住。
# （本段刻意不写出那三种形状的完整文本：写了就会被本门自己判红，S00P.2.1 的规矩
#   先约束写规矩的人，EVD-V4-00P §10 记过同一次自伤。）
#
# 但"放宽"必须是一条有语义的线，不是"源码文件跳过"：
#   · 键名落在**字符串/注释**里 ⇒ 那段文本本身就是字面量 ⇒ 照报（含跨行三引号与反引号，
#     这正是两轮复查里漏掉的第一类：行内判断看不见跨行串）；
#   · 键名在代码位 ⇒ 看**赋值号到行尾**的整段右值，而不是正则截断出来的片段。
#     正则的字符类在第一个引号处就停，于是「取环境变量 + 逗号 + 写死兜底值」会被截成
#     「取环境变量 + 左括号」，看上去就是表达式——这是复查第 2 轮漏掉的第二类。
#   · 右值里没有引号（含反引号）且不是纯数字 ⇒ 表达式 ⇒ 不报；
#   · 右值里出现**值类**字面量（≥8 字符、非占位、非全大写环境变量名）⇒ 报；
#   · 整体就是一个字面量 ⇒ 直接赋值 ⇒ 报（不看长度，短口令也算）。
#
# 为什么不用 AST：TS/TSX 没有 stdlib 解析器；且文件可能正在编辑（语法不完整）时
# 门仍必须给出判定。字符级状态机对两类语言都成立，且失败方向是"多报"。

_SOURCE_EXTS = frozenset({".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"})
_HASH_COMMENT_EXTS = frozenset({".py"})

# S27.3 / D-V12-05：`\b` 边界抓不到 `APP_TOKEN` 这类前缀常量名（P-41 的登记项）。
# 只补 `_TOKEN` 后缀这一族；不扩到别的后缀——扩面要配全仓误报对照，属另一条裁决。
SECRET_ASSIGN_SUFFIX = re.compile(
    r"(?i)\b([A-Za-z0-9_]*_token)\b\s*[:=]\s*[\"']?([^\"'\s,;)}]{4,})")

_SRC_LITERAL = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`")
_SRC_ONLY_LITERAL = re.compile(
    r"^(?:[rRbBuUfF]{0,2})?(?:\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)$")
_SRC_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")
# 键位取值：`x["k"]` 的下标、`.get(`/`.pop(`/`.setdefault(` 的第一个实参。
# 这些位置上的字面量是**字段名**，不是值——首版把「键名=对象["同名键"]」这种取值
# 判成"写死凭据"，把改前能过门的 `providers/aidean/client.py`、`api/v1/auth.py` 关回门里。
_KEYED_ACCESS = re.compile(r"\.(?:get|pop|setdefault|getlist|getall)\s*\(\s*$")


def _source_language(suffix: str) -> str | None:
    suffix = suffix.lower()
    if suffix not in _SOURCE_EXTS:
        return None
    return "hash" if suffix in _HASH_COMMENT_EXTS else "slash"


def _source_kinds(lines: list[str], lang: str) -> list[list[str]]:
    """逐行给出每个字符的归属：`c` 代码位 / `s` 字符串位 / `m` 注释位。

    跨行字符串（Python 三引号、JS 反引号）的状态在行间传递——这是复查第 2 轮
    「多行字符串内赋值漏检」的正面修法：行内判断永远看不见上一行打开的定界符。
    """
    out: list[list[str]] = []
    state = ""
    for line in lines:
        kinds = ["c"] * len(line)
        i, n = 0, len(line)
        while i < n:
            if state:
                end = line.find(state, i)
                if end < 0:
                    for j in range(i, n):
                        kinds[j] = "s"
                    i = n
                    break
                for j in range(i, end + len(state)):
                    kinds[j] = "s"
                i = end + len(state)
                state = ""
                continue
            ch = line[i]
            if (lang == "hash" and ch == "#") or (
                    lang != "hash" and ch == "/" and i + 1 < n and line[i + 1] == "/"):
                for j in range(i, n):
                    kinds[j] = "m"
                i = n
                break
            if ch in "\"'":
                triple = ch * 3
                if line.startswith(triple, i):
                    for j in range(i, min(i + 3, n)):
                        kinds[j] = "s"
                    i += 3
                    state = triple
                    continue
                j = i + 1
                while j < n:
                    if line[j] == "\\":
                        j += 2
                        continue
                    if line[j] == ch:
                        break
                    j += 1
                for k in range(i, min(j + 1, n)):
                    kinds[k] = "s"
                i = j + 1
                continue
            if ch == "`":
                j = i + 1
                closed = False
                while j < n:
                    if line[j] == "\\":
                        j += 2
                        continue
                    if line[j] == "`":
                        closed = True
                        break
                    j += 1
                if closed:
                    for k in range(i, j + 1):
                        kinds[k] = "s"
                    i = j + 1
                    continue
                for k in range(i, n):
                    kinds[k] = "s"
                state = "`"
                i = n
                break
            i += 1
        out.append(kinds)
    return out


def _src_literals(text: str) -> list[str]:
    """抽出文本里的字面量内容（去掉定界符）。跨行串按行给出，调用方只需"有没有值类字面量"。"""
    return [m.group(0)[1:-1] for m in _SRC_LITERAL.finditer(text)]


def _src_value_like(literal: str) -> bool:
    """这个字面量像不像"值"：≥8 字符、非占位、非全大写环境变量名。"""
    if len(literal) < 8 or SECRET_FAKE.match(literal):
        return False
    return not _SRC_ENV_NAME.match(literal)


def _literal_is_key(rhs: str, start: int) -> bool:
    """这个字面量是不是处在**键位**（下标或键值访问的第一个实参）。

    为什么键位不能算值：「键名=对象["同名键"]」这种取值的右值来自对象本身，
    引号里那串只是字段名；`.get("k", "v")` 里第一个实参同理。若把键位当值，
    "放宽表达式"就变成"把两处表达式换成另一种误报"，`providers/aidean/client.py`
    与 `api/v1/auth.py` 会重新被门挡住——S27.3 首版就是这么自伤的。
    第二个实参（兜底值）不在键位，照旧按值判定。
    """
    i = start - 1
    while i >= 0 and rhs[i] in " \t":
        i -= 1
    if i < 0:
        return False
    if rhs[i] == "[":
        return True
    if rhs[i] == "(":
        return bool(_KEYED_ACCESS.search(rhs[:i + 1]))
    return False


def _operator_index(line: str, key_end: int) -> int:
    """键名之后的**赋值算子**位置；注解式赋值取后面的 `=`，不是类型注解的 `:`。

    为什么不能只取 `rfind(":")`/`rfind("=")`：注解式赋值的右值会从冒号后开始，
    于是类型名被当成"值里有写死字面量"的表达式——而真正的右值是 `=` 之后那段。
    反过来，对象字面量里的键名后接冒号、右值是属性访问，那一行没有 `=`，冒号就是算子。
    """
    i = key_end
    while i < len(line) and line[i] in " \t":
        i += 1
    if i >= len(line):
        return -1
    if line[i] == "=":
        return i
    if line[i] != ":":
        return -1
    depth = 0
    j = i + 1
    while j < len(line):
        ch = line[j]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "=" and depth == 0 and line[j:j + 2] != "==" and line[j - 1] not in "=!<>":
            return j
        elif ch in ",;" and depth == 0:
            break
        j += 1
    return i


def _source_hit(line: str, kinds: list[str], key_start: int, op: int) -> bool:
    """源码面的一条候选：报还是放行。判据见本节开头的四条。"""
    if kinds[key_start] != "c":
        # 键名在字符串或注释里：那一段文本就是字面量本身（跨行串也走这一支）
        return True
    end = len(line)
    for i in range(op + 1, len(line)):
        if kinds[i] == "m":
            end = i
            break
    rhs = line[op + 1:end].strip().rstrip(",;").strip()
    if not rhs:
        return False
    if "`" in rhs:
        return True
    if _SRC_ONLY_LITERAL.match(rhs):
        return True
    literals = [(m.start(), m.group(0)[1:-1]) for m in _SRC_LITERAL.finditer(rhs)]
    if literals:
        # 键位（下标 / 键值访问首实参）里的字面量是字段名，不参与"值类"判定
        return any(_src_value_like(lit) and not _literal_is_key(rhs, pos)
                   for pos, lit in literals)
    return rhs.isdigit()


def secret_scan_source(text: str, lang: str) -> tuple[list[tuple[str, int, str]], int]:
    """源码面扫描：具名规则照旧，赋值形走 `_source_hit` 的表达式判据。

    返回形状与 `secret_scan` 相同，调用方不必分支。
    """
    lines = text.splitlines()
    kinds_per_line = _source_kinds(lines, lang)
    hits: list[tuple[str, int, str]] = []
    allowed = 0
    for no, line in enumerate(lines, 1):
        kinds = kinds_per_line[no - 1]
        for name, rx in SECRET_RULES:
            for m in rx.finditer(line):
                frag = m.group(0)
                if any(a.search(frag) for a in SECRET_ALLOW):
                    allowed += 1
                    continue
                hits.append((name, no, _mask_shape(name, frag)))
        for rx in (SECRET_ASSIGN, SECRET_ASSIGN_SUFFIX):
            for m in rx.finditer(line):
                val = m.group(2)
                if (val.startswith("re.compile") or SECRET_FAKE.match(val)
                        or _SECRET_ASSIGN_SKIP.search(val)):
                    continue
                op = _operator_index(line, m.end(1))
                if op < 0 or not _source_hit(line, kinds, m.start(1), op):
                    continue
                hits.append(("assign", no, f"{m.group(1)}=<已打码，值长 {len(val)} 字符>"))
    hits.sort(key=lambda item: (item[1], item[0]))
    return hits, allowed


def secret_scan_for_path(text: str, rel: str) -> tuple[list[tuple[str, int, str]], int]:
    """按路径挑口径：源码后缀走源码模式，其余（文档/配置/未知）走原严格口径。"""
    lang = _source_language(Path(rel).suffix)
    if lang is None:
        return secret_scan(text)
    return secret_scan_source(text, lang)


def secret_scope(base: str) -> tuple[list[str], str, str]:
    """待检路径 → (路径, 取材处 index|head, 错误说明)。错误非空即 fail-closed。

    先取索引（卡面 S00P.1.1.1「不扫全仓」），索引为空再退到 base..HEAD。
    为什么要有第二档：`make evidence-check` 目前没有工作流调用（现读 `.github/workflows/`
    下的 yml 对 guard/evidence-check 零命中），但若将来接进 CI，那一步
    **没有 staged 内容**——只按卡面取 `--cached` 就成了"每次必空、每次都绿"的门。两档都空 ⇒
    交回空集，调用方给第三态。

    「取材处」必须一路带到读内容那一步：门要看的是**将要入库的那份字节**，不是工作树上恰好
    打开的那份。复核实测——先 `git add` 一个带形状的文件、再把工作树洗成占位值，
    索引里的 blob 仍带凭据，而只读工作树的门报 rc=0 ⇒ 凭据照样入库（偏绿的 fail-open）。
    """
    rc, out = _git("diff", "--cached", "--name-only")
    if rc:
        return [], "", f"git diff --cached 失败（rc={rc}）"
    paths = [line for line in out.splitlines() if line.strip()]
    if paths:
        return paths, "index", ""
    rc, _ = _git("rev-parse", "--verify", "--quiet", base)
    if rc:
        return [], "", f"索引为空且基线 {base!r} 不可解析 ⇒ 门什么都没看"
    rc, out = _git("diff", "--name-only", base, "HEAD")
    if rc:
        return [], "", f"git diff --name-only {base} HEAD 失败（rc={rc}）"
    return [line for line in out.splitlines() if line.strip()], "head", ""


def _git_bytes(*args: str) -> tuple[int, bytes]:
    proc = subprocess.run(["git", "-c", "core.quotepath=false", *args],
                          cwd=str(ROOT), capture_output=True)
    return proc.returncode, proc.stdout


def secret_blob(rel: str, whence: str) -> bytes | None:
    """取出待检内容的**那一份字节**：索引面取 `:路径`，提交面取 `HEAD:路径`。"""
    ref = f":{rel}" if whence == "index" else f"HEAD:{rel}"
    rc, data = _git_bytes("show", ref)
    return data if rc == 0 else None


def secret_shape_check(base: str = "origin/main") -> int:
    """敏感形阻断步：待检面上 HIGH>0 ⇒ 红；没有可检面或一份都没看成 ⇒ 第三态 rc=3。"""
    paths, whence, err = secret_scope(base)
    if err:
        print(f"❌ 敏感形门：{err}（fail-closed，不许静默放行）", flush=True)
        return 1
    if not paths:
        print(f"⚠️  敏感形门：索引为空且 {base}..HEAD 为空 ⇒ 无可检文件，**这不是通过**（rc=3）",
              flush=True)
        return 3

    scanned = skipped = high = allowed = 0
    reported: list[str] = []
    for rel in paths:
        data = secret_blob(rel, whence)
        if data is None:
            skipped += 1  # 暂存的删除/重命名左侧：索引与 HEAD 里都没有这份内容
            continue
        if len(data) > _SECRET_MAX_BYTES or b"\x00" in data[:4096]:
            skipped += 1
            continue
        scanned += 1
        hits, ok = secret_scan_for_path(data.decode("utf-8", "replace"), rel)
        allowed += ok
        for name, no, shape in hits:
            high += 1
            reported.append(f"   HIGH {name}  {rel}:{no}  {shape}")

    print(f"敏感形门（STEP-00P S00P.1.1）：待检 {len(paths)} 个路径（取材面={whence}），"
          f"实扫 {scanned}，跳过 {skipped}（本批删除/二进制/超限），"
          f"HIGH {high}，ALLOWED 放行 {allowed}", flush=True)
    if high:
        print("\n".join(reported), flush=True)
        print("❌ 敏感形门：命中 >0 ⇒ 本批不得入库。整改口径（S00P.2.1/2.2）："
              "文档里不内联敏感形字面量，也不内联扫描正则本身——只描述形状并指向判据实体；"
              "权威终判仍以 `gitleaks` 的 git 模式为准。"
              "要豁免只能按 D-12 逐指纹登记进 `.gitleaksignore`（STEP-00S 的归属面），"
              "**本门不自建 allowlist**。", flush=True)
        return 1
    if scanned == 0:
        # 一条都没看成 ≠ 看过了。整批都是删除/二进制时，这一维没有终判。
        print("⚠️  敏感形门：待检路径全被跳过（本批删除/二进制/超限）⇒ 退出码 3，**这不是通过**",
              flush=True)
        return 3
    print("✅ 敏感形门：待检面无 HIGH 命中", flush=True)
    return 0


EVIDENCE_PROOFS = [
    "docs/06_validation/evidence/EVD-V2-00/prove_dsn_policy.py",
    "docs/06_validation/evidence/EVD-V2-00/prove_dsn_policy.py --self-test",
    # S00T.V14.3（F-14）：`prove_provider_shapes.py` 已迁成
    # `apps/api/tests/proofs/test_provider_shapes.py`（真 import 真执行，随 pytest tests/ 进 CI），
    # 脚本本体随之删除。留在这里的注释是**指针**，不是待办：
    # "pytest 化 ⇒ 从本表移除"是这一卡出门判据（evidence-check rc=0）的一部分。
    "docs/06_validation/evidence/EVD-V2-00/g24_static_check.py",
    "docs/06_validation/evidence/EVD-V2-00/g24_static_check.py --self-test",
    "docs/06_validation/evidence/EVD-V2-00R/prove_net_isolation.py",
    "docs/06_validation/evidence/EVD-V2-00R/prove_net_isolation.py --self-test",
]


def evidence_check(base: str = "origin/main") -> int:
    """stdlib 证据逐条复跑；真实工具步缺任一个就 rc=3（不是 PASS 也不是 FAIL）。

    S00T.V14.2：先跑 D-V4-03 耦合门——判据必须在复跑脚本**之前**，否则脚本一红就
    `return 1` 短路，耦合这一维永远不会被报出来。
    S00P.1.1：敏感形门同在前置位。**两道前置门各自跑完再汇总**——
    前置门之间一旦短路，第二道门就永远没有读数，那正是 S00T.V14.2 刚修掉的毛病。
    """
    gate_rc = coupling_check(base)
    secret_rc = secret_shape_check(base)
    if gate_rc == 1 or secret_rc == 1:
        return 1
    # 前置门的 3 = 「这一维没有可检面」。它必须一路带到最终退出码，但不能就地短路——
    # 否则干净工作树上 `make evidence-check` 会连证据复跑都不做，把本目标的主用途打掉。
    third = 3 if (gate_rc == 3 or secret_rc == 3) else 0
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
    missing: list[str] = []
    ruff = shutil_which("ruff") or _venv_script("ruff")
    if ruff:
        tool_steps.append(("ruff", [ruff, "check", "app", "tests"], API))
    else:
        missing.append("ruff")
    gitleaks = shutil_which("gitleaks")
    if not gitleaks and os.environ.get("LOCALAPPDATA"):
        cand = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "tools" / "gitleaks" / "gitleaks.exe"
        gitleaks = str(cand) if cand.exists() else None
    # S27.2：CI 的 backend job 不装 gitleaks（权威步在 Security 工作流）。
    # 没有这个开关时，本门会把「工具缺席」判成第三态 ⇒ CI 恒红；而把 gitleaks 装进
    # 每个 job 是重复劳动。开关只允许**显式声明覆盖**，默认仍是缺席即第三态。
    gitleaks_covered = bool(os.environ.get("GUARD_GITLEAKS_COVERED"))
    if gitleaks:
        tool_steps.append(("gitleaks", [gitleaks, "detect", "--source", ".", "--config", ".gitleaks.toml",
                                     "--no-banner"], ROOT))
    elif gitleaks_covered:
        print("SKIP(covered by Security) gitleaks——权威步在 .github/workflows/security.yml", flush=True)
    else:
        missing.append("gitleaks")
    # 缺席告警只报真缺席的那个：改前是 `if gitleaks and tool_steps is not None … else: print(gitleaks SKIP)`，
    # ruff 缺席而 gitleaks 在场时也会打印「SKIP(tool missing) gitleaks」——一条假的缺席读数。
    for name in missing:
        print(f"SKIP(tool missing) {name}——{TOOL_ABSENT_WHY[name]}")
    if missing:
        print("⚠ evidence-check：stdlib 证据全过，但真实工具步没跑 ⇒ 退出码 3（这不是 PASS，也不是 FAIL）")
        return 3
    for name, cmd, cwd in tool_steps:
        print(f"── 真实工具步：{name} ──")
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        print(proc.stdout, end="")
        print(proc.stderr, end="")
        if proc.returncode:
            print(f"❌ {name} 失败（rc={proc.returncode}）", flush=True)
            return proc.returncode
        # gitleaks 8.21.2 @win 实测：Git for Windows 的 system 级 /etc/gitattributes 给 *.docx
        # 注册了 `diff=astextplain`，而 astextplain 要调没装的 docx2txt.exe ⇒ gitleaks 自己打印
        # `ERR failed to scan Git repository error="stderr is not empty"`，**却 rc=0**。
        # 安全门不能把"工具自报没扫成"读成"扫过且干净"（P-37）。
        # 这里给第三态而非判红：这一维此刻没有终判，把它和「扫出了凭据」混成同一个红，
        # 等于用狼来了消耗门禁的信用——本批文件自身的判定已由前置的敏感形门给出。
        if "failed to scan" in f"{proc.stdout}\n{proc.stderr}":
            print(f"⚠️  {name} 自报扫描未完成（rc=0 但输出含 failed to scan）"
                  " ⇒ 退出码 3：这一维没有终判，**不是通过**", flush=True)
            return 3
    if third:
        print("⚠ evidence-check：前置门之一在本批没有可检面 ⇒ 退出码 3（这不是 PASS）", flush=True)
        return 3
    print("✅ evidence-check 全部通过（前置两道门 + stdlib 证据 + 真实工具两步）", flush=True)
    return 0


TOOL_ABSENT_WHY = {
    "ruff": "stdlib 近似表(g24)判不了的成员序/段序之外，终判在这一步",
    "gitleaks": "Security 门禁的终判在这一步；本门前置位已实跑敏感形门（secret_shape_check）做召回",
}


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
# S27.1 / D-V12-03：范围门的默认基线统一读它。CI 里 `origin/main` 在 push 事件上等于
# "刚推完的 HEAD"，范围恒空 ⇒ 门永远第三态；基线只能由事件给出（`github.event.before`）。
BASE_ENV = "GUARD_BASE"


def default_base() -> str:
    """范围门的默认基线：`GUARD_BASE` 非空则用它，否则退回 `origin/main`。"""
    return os.environ.get(BASE_ENV, "").strip() or DEFAULT_BASE


def main(argv: list[str]) -> int:
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    name = argv[0] if argv else ""
    base = default_base()
    explicit = False
    rest = argv[1:]
    if rest[:1] == ["--base"]:
        if len(rest) != 2 or not rest[1].strip():
            print("用法：--base 后面必须且只能跟一个可解析的 ref")
            return 1
        base = rest[1]
        explicit = True
        rest = []
    if rest or not name or name not in GUARDS:
        print(f"用法：python scripts/guards.py <{'|'.join(GUARDS)}> [--base <ref>]")
        return 1
    if explicit and name not in BASE_AWARE:
        # 不接受 --base 的门被传了 --base：静默忽略会制造"我指定了基线所以判了历史"的错觉
        print(f"❌ {name} 不接受 --base（它不比较范围，只看仓库现状）", flush=True)
        return 1
    fn = GUARDS[name]
    return fn(base) if name in BASE_AWARE else fn()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
