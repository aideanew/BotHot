#!/usr/bin/env python3
"""BotHot 跨平台任务入口（STEP-00X）。

`make <task>` 与 `python scripts/entry.py <task>` 同义：Makefile 只做薄转调，
真正的命令表住在这里，Windows 与 Linux 走同一份代码。

三条硬约定（写在代码里，不靠人记）：
- 平台差异只出现在 dispatch() 一处（S00X.1.2.1）。
- 缺工具 ⇒ 打印 `SKIP(<tool> missing)` 并以 rc=3 退出（S00X.1.2.2）。3 沿用 Makefile
  `evidence-check` 既有口径："这不是 PASS，也不是 FAIL"——"没装"绝不能长得像"通过"。
- 一律显式 UTF-8（PYTHONUTF8=1 + encoding="utf-8"），Windows 的 cp936 默认编码会把
  中文输出与 heredoc 源码打碎（本仓库实测）。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps" / "api"
WEB = ROOT / "apps" / "web"
COMPOSE_FILE = ROOT / "docker" / "compose.yml"

RC_OK, RC_FAIL, RC_TOOL_MISSING = 0, 1, 3
IS_WIN = os.name == "nt"


def dispatch() -> dict[str, str]:
    """平台差异的唯一出处：venv 内部布局与批处理壳。"""
    if IS_WIN:
        return {"venv_python": str(API / ".venv" / "Scripts" / "python.exe"), "shell": "cmd"}
    return {"venv_python": str(API / ".venv" / "bin" / "python"), "shell": ""}


def find_tool(name: str) -> str | None:
    """BOTHOT_<TOOL> 指定 → PATH → Windows 兜底安装位。都找不到就返回 None（SKIP）。"""
    override = os.environ.get(f"BOTHOT_{name.upper().replace('-', '_')}")
    if override and Path(override).exists():
        return override
    found = shutil.which(name)
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA", "")
    if IS_WIN and local:
        links = Path(local) / "Microsoft" / "WinGet" / "Links"
        table = {
            "gitleaks": Path(local) / "Programs" / "tools" / "gitleaks" / "gitleaks.exe",
            # winget 装的 GNU make 落在 Links 目录，且它写注册表 PATH——**已运行的进程读不到**，
            # 所以新开 Git Bash 里 `make` 仍然 command-not-found。兜底这条路径，否则
            # entry.py 会把四个守卫目标永远判成 SKIP（实测：本会话 PATH 里没有 Links）。
            "make": links / "make.exe",
            "gh": links / "gh.exe",
            "docker": Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe"),
        }
        cand = table.get(name)
        if cand and cand.exists():
            return str(cand)
    return None


def venv_python() -> str:
    env = os.environ.get("BOTHOT_VENV_PYTHON")
    if env and Path(env).exists():
        return env
    cand = dispatch()["venv_python"]
    if Path(cand).exists():
        return cand
    print(f"⚠️  没有 {cand}，退回当前解释器 {sys.executable}"
          f"（CI 钉 Python 3.12；版本差异由 preflight 判红，不静默）")
    return sys.executable


def spawn(cmd: list[str], cwd: Path, env: dict[str, str] | None) -> int:
    real_env = dict(os.environ)
    real_env["PYTHONUTF8"] = "1"
    if env:
        real_env.update(env)
    full = list(cmd)
    # npm 全局包在 Windows 上是 .CMD shim，CreateProcess 不认裸路径 ⇒ 交给 cmd /c
    if IS_WIN and full[0].lower().endswith((".cmd", ".bat")):
        full = [dispatch()["shell"], "/c", *full]
    try:
        shown = f"[{cwd.relative_to(ROOT)}]"
    except ValueError:
        shown = f"[{cwd}]"
    print(f"$ {shown} {' '.join(full)}", flush=True)
    return subprocess.run(full, cwd=str(cwd), env=real_env).returncode


def tool_missing(name: str, hint: str = "") -> int:
    print(f"SKIP(tool missing) {name} —— 这一步**未执行**。"
          f"按 D-V4-01，正式终判在 @ci（ubuntu-latest）；本机不得据此报 PASS。{hint}")
    return RC_TOOL_MISSING


def venv_script(name: str) -> str | None:
    """venv 里的 console script（Windows 是 Scripts/<name>.exe，POSIX 是 bin/<name>）。"""
    py = Path(venv_python())
    cand = py.parent / (name + ".exe" if IS_WIN else name)
    return str(cand) if cand.exists() else None


def tool_run(script: str, module: str, args: list[str], cwd: Path,
             env: dict[str, str] | None = None):
    """先走 venv console script，再退 `python -m`，都没有就 SKIP（rc=3）。

    alembic 就是只有 console script 的那一类：`python -m alembic` 实测报
    "alembic is a package and cannot be directly executed"。
    """
    def run() -> int:
        exe_path = venv_script(script)
        if exe_path:
            return spawn([exe_path, *args], cwd, env)
        py = venv_python()
        probe = subprocess.run(
            [py, "-c", f"import importlib.util, sys;"
                       f"sys.exit(0 if importlib.util.find_spec('{module}') else 1)"],
            cwd=str(cwd))
        if probe.returncode != 0:
            return tool_missing(module, f"（解释器 {py} 里没有该模块；先跑 entry.py install-backend）")
        return spawn([py, "-m", module, *args], cwd, env)

    return run


def exe(name: str, args: list[str], cwd: Path, env: dict[str, str] | None = None):
    def run() -> int:
        path = find_tool(name)
        if path is None:
            return tool_missing(name)
        return spawn([path, *args], cwd, env)

    return run


def install_backend() -> int:
    return spawn([venv_python(), "-m", "pip", "install", "-e", ".[dev]", "pytest-cov"], API, None)


def find_python312() -> str | None:
    """CI 钉 3.12（ci.yml:56 / security.yml:103）。找不到就 None，由调用方 SKIP——
    拿系统里的 3.11 建 venv 交读数，等于把"版本对齐"这件事悄悄取消。"""
    for cand in (
        os.environ.get("BOTHOT_PYTHON312"),
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python312" / "python.exe"),
        "/usr/bin/python3.12",
        "python3.12",
    ):
        if not cand:
            continue
        resolved = shutil.which(cand) or (cand if Path(cand).exists() else None)
        if resolved and Path(resolved).exists():
            out = subprocess.run([resolved, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
            if out.returncode == 0 and out.stdout.strip() == "3.12":
                return resolved
    return None


def create_venv() -> int:
    base = find_python312()
    if base is None:
        return tool_missing("python3.12", "（正式面 CI 用 3.12；装它之前不要用 3.11 建 venv 交读数）")
    target = API / ".venv"
    if target.exists():
        print(f"已存在 {target}，跳过创建（要重建请先删该目录）")
        return RC_OK
    return spawn([base, "-m", "venv", str(target)], ROOT, None)


def guard(target: str):
    """守卫类目标的实体在 scripts/guards.py（Makefile 也转调它，唯一源）。

    为什么不再是 `make <target>`：GNU make 4.4.1 for Windows 跑不了原来那些
    多行 `; \\` 续行的 shell recipe（实测报 unexpected EOF while looking for
    matching `"'）。留在 Makefile 里就等于"Windows 上永远跑不了"，
    而跑不了与跑过去在读数上长得一样——这正是本卡要消灭的形态。
    """
    def run() -> int:
        py = sys.executable
        script = ROOT / "scripts" / "guards.py"
        if not script.exists():
            print(f"❌ 缺少 {script}")
            return RC_FAIL
        return spawn([py, str(script), target], ROOT, None)

    return run


def coverage_gate():
    """模块覆盖率门（STEP-06 S6.3.1）：实体在 scripts/check_module_coverage.py，纯 stdlib。

    用 `sys.executable` 而不是 `venv_python()`：这份脚本只吃 json/argparse，
    绑 venv 解释器会让"没建 venv"表现为 rc=3 的 SKIP，而门没跑与门过了必须一眼可分。
    """
    def run() -> int:
        script = ROOT / "scripts" / "check_module_coverage.py"
        if not script.exists():
            print(f"❌ 缺少 {script}")
            return RC_FAIL
        return spawn([sys.executable, str(script)], ROOT, None)

    return run


def bash_script(rel: str):
    def run() -> int:
        b = find_tool("bash")
        if b is None:
            return tool_missing("bash", f"（该任务走 {rel}，Windows 需要 Git for Windows）")
        return spawn([b, rel], ROOT, None)

    return run


# (name, 说明, 步骤列表 | 复合子任务)
TASKS: list[tuple[str, str, list, tuple]] = []


def add(name: str, desc: str, steps: list | None = None, composite: tuple = ()):
    TASKS.append((name, desc, steps or [], composite))


def print_dev_hint() -> int:
    print("请在两个终端分别运行：`entry.py dev-backend` 与 `entry.py dev-frontend`"
          "（宿主端口 3300 / 3200，AGENTS.md 端口表；3000 禁用）")
    return RC_OK


def service_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def dependency_endpoints() -> list[tuple[str, str, int]]:
    """从 alembic.ini / compose.yml 的默认锚读依赖服务地址；不做静默换端口（S00X.3.2.1）。"""
    out = []
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        ini = API / "alembic.ini"
        dsn = ""
        if ini.exists():
            for line in ini.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("sqlalchemy.url"):
                    dsn = line.split("=", 1)[1].strip()
                    break
    if dsn:
        # 形如 方案://用户:口令@主机:端口/库名（此处刻意不写出真实形状，避免规划面自己制造凭据形）
        try:
            netloc = dsn.split("//", 1)[1].split("/", 1)[0]
            hostport = netloc.rsplit("@", 1)[-1]
            host, _, port = hostport.partition(":")
            out.append(("PostgreSQL", host or "localhost", int(port or 5432)))
        except ValueError:
            pass
    redis = os.environ.get("REDIS_URL") or "redis://localhost:6380/0"
    try:
        netloc = redis.split("//", 1)[1].split("/", 1)[0]
        host, _, port = netloc.rpartition(":")
        out.append(("Redis", host or "localhost", int(port or 6379)))
    except ValueError:
        pass
    return out


def check_services():
    """迁移/连库前先探 PG 端口：不可达就 SKIP(rc=3) 并点名端口，**不得**让它挂住。

    实测动机：@win 无 PG 时 `alembic upgrade head` 不是快速失败，而是一直挂到被外部 kill
    （psycopg 无 connect_timeout + Windows 对未监听端口不立即 RST），150s timeout 才打断。
    挂住比失败更危险——执行者会以为"在跑"。

    修复指引（STEP-00E 更正过一次）：原文只说"起 `compose.yml`"，但现读该文件的 services 段
    **没有 PG/Redis 服务**（只有 langbot*/backend/migrate/scheduler/worker/frontend），
    照那句做仍然连不上库。真正能给隔离库的是 `entry.py testenv-up`（5547/6390，需要 docker）。
    """
    for name, host, port in dependency_endpoints():
        if name != "PostgreSQL":
            continue        # 迁移只需要 PG；Redis 不可达不该挡 alembic
        if not service_reachable(host, port):
            print(f"SKIP(service unavailable) {name} {host}:{port} 不可达 —— 先起依赖服务："
                  f"`entry.py testenv-up`（隔离测试栈 PG16@5547 / Redis7@6390，需要 docker；"
                  f"注意 docker/compose.yml 里没有 PG/Redis 服务段，起它得不到库），"
                  f"端口按 AGENTS.md 固定、不得静默改端口；本步**未执行**，不是通过")
            return RC_TOOL_MISSING
    return RC_OK


def with_service_check(inner):
    def run() -> int:
        gate = check_services()
        if gate != RC_OK:
            return gate
        return inner()

    return run


def alembic_cli() -> str | None:
    return venv_script("alembic")


def assert_single_head() -> int:
    """S00E.1.3 要求「alembic 单头断言保留」：`heads` 里带 `(head)` 的行必须恰好一行。

    放在 pytest 之前是有理由的：多头时 `upgrade head` 直接报错，但那条错的形状像"环境问题"，
    而多头是治理事故（CI 的 workflow-lint/backend 也各判一次，这里保证 `verify-backend`
    单独跑也不放过）。
    """
    cli = alembic_cli()
    if cli is None:
        return tool_missing("alembic", "（先跑 entry.py install-backend）")
    out = subprocess.run([cli, "heads"], cwd=str(API), capture_output=True, text=True,
                         encoding="utf-8", errors="replace",
                         env={**os.environ, "PYTHONUTF8": "1"})
    if out.returncode != 0:
        print(f"❌ `alembic heads` 本身失败（rc={out.returncode}）⇒ 单头断言**没跑成**，不能当通过")
        print((out.stdout + out.stderr).strip())
        return RC_FAIL
    heads = [line for line in out.stdout.splitlines() if "(head)" in line]
    print(f"单头断言：`alembic heads` 里带 (head) 的行数 = {len(heads)}（应为 1）")
    for line in heads:
        print(f"  {line.strip()}")
    if len(heads) != 1:
        print("❌ 迁移多头或零头 ⇒ verify-backend 停在这里，不放行 pytest")
        return RC_FAIL
    return RC_OK


def report_node_modules(face: str):
    """F-10 的口径：`node_modules` 的**存在性**必须作为读数打出来，不能假设。

    存在理由是 V0.9.0 与 V0.10.0 两台机器各报了一个相反的事实（一台说没有、一台说有），
    而两边都对——差别只在机器。所以这里连同顶层条目数一起打，装前装后各一次。
    """
    def run() -> int:
        nm = WEB / "node_modules"
        if nm.is_dir():
            top = sum(1 for p in nm.iterdir() if not p.name.startswith("."))
            print(f"F-10 读数[{face}] apps/web/node_modules 存在=True，顶层条目={top}")
        else:
            print(f"F-10 读数[{face}] apps/web/node_modules 存在=False")
        return RC_OK

    return run


def run_test_env(role: str):
    """`test-env.sh` 的入口（D-12：测试端口命中部署端口即拒绝启动）。"""
    def run() -> int:
        if find_tool("docker") is None and find_tool("podman") is None:
            return tool_missing("docker", "（testenv-up/down 转调 scripts/test-env.sh，"
                                          "它需要 docker 或 podman；本机两者都无 ⇒ 本步未执行）")
        b = find_tool("bash")
        if b is None:
            return tool_missing("bash", "（testenv-* 走 scripts/test-env.sh，Windows 需要 Git for Windows）")
        return spawn([b, "scripts/test-env.sh", role], ROOT, None)

    return run


def clean_tree() -> int:
    """只删构建缓存，不碰源码、不碰 node_modules/.venv 本体（Makefile 原口径）。"""
    import shutil as _sh

    targets = [WEB / ".next", WEB / "node_modules" / ".cache", API / ".pytest_cache"]
    removed = 0
    for t in targets:
        if t.exists():
            _sh.rmtree(t, ignore_errors=True)
            removed += 1
            print(f"已删 {t.relative_to(ROOT)}")
    skipped = ("node_modules", ".venv", ".git", ".project", ".pnpm-store")
    found = []
    for root, dirs, _files in os.walk(ROOT):
        keep = []
        for d in dirs:
            if d == "__pycache__":
                found.append(Path(root) / d)   # 收集被剪掉的分支，walk 不会再进入
            elif d not in skipped:
                keep.append(d)
        dirs[:] = keep
    for d in found:
        _sh.rmtree(d, ignore_errors=True)
    print(f"清理完成：{removed} 个构建目录 + {len(found)} 个 __pycache__")
    return RC_OK


def migrate_new() -> int:
    msg = os.environ.get("BOTHOT_MSG", "").strip()
    if not msg:
        print("❌ migrate-new 需要消息：make migrate-new MSG=\"描述\" 或 BOTHOT_MSG=\"描述\" "
              "entry.py migrate-new")
        return RC_FAIL
    gate = check_services()
    if gate != RC_OK:
        return gate
    return tool_run("alembic", "alembic", ["revision", "--autogenerate", "-m", msg], API)()


add("venv-backend", "用 CI 同版 Python 建 apps/api/.venv", [create_venv])
add("migrate-new", "alembic revision --autogenerate（消息走 MSG/BOTHOT_MSG）", [migrate_new])
add("install-backend", "安装后端依赖（.[dev] + pytest-cov，与 CI 同口径）", [install_backend])
add("install-frontend", "安装前端依赖（--frozen-lockfile）", [exe("pnpm", ["install", "--frozen-lockfile"], WEB)])
add("install", "前后端依赖一起装", composite=("install-backend", "install-frontend"))
add("migrate", "alembic upgrade head（先探 PG 端口，不可达即 SKIP）",
    [with_service_check(tool_run("alembic", "alembic", ["upgrade", "head"], API))])
add("migrate-down", "alembic downgrade -1",
    [with_service_check(tool_run("alembic", "alembic", ["downgrade", "-1"], API))])
add("lint-backend", "ruff check app tests", [tool_run("ruff", "ruff", ["check", "app", "tests"], API)])
add("typecheck-backend", "mypy app", [tool_run("mypy", "mypy", ["app"], API)])
add("fmt-check-backend", "ruff format --check（非阻断，CI 不跑）",
    [tool_run("ruff", "ruff", ["format", "--check", "app", "tests"], API)])
add("typecheck-frontend", "tsc --noEmit", [exe("pnpm", ["exec", "tsc", "--noEmit"], WEB)])
add("lint-frontend", "next lint（CI 口径 eslint）", [exe("pnpm", ["run", "lint"], WEB)])
add("lint", "后端 ruff + 前端 lint/typecheck", composite=("lint-backend", "lint-frontend", "typecheck-frontend"))
add("test-backend", "pytest tests/ -v", [tool_run("pytest", "pytest", ["tests/", "-v"], API)])
add("test-frontend-unit", "vitest 单测", [exe("pnpm", ["run", "test:unit"], WEB)])
add("test-frontend-e2e", "playwright e2e（需 `pnpm exec playwright install chromium`）",
    [exe("pnpm", ["run", "test:e2e"], WEB)])
add("test", "后端 + 前端单测", composite=("test-backend", "test-frontend-unit"))
add("build-frontend", "next build（NEXT_PUBLIC_API_MOCK=false，生产守卫要求）",
    [exe("pnpm", ["run", "build"], WEB, {"NEXT_PUBLIC_API_MOCK": "false"})])
add("dev-backend", "uvicorn --reload --port 3300",
    [tool_run("uvicorn", "uvicorn", ["app.main:app", "--reload", "--port", "3300"], API)])
add("dev-frontend", "next dev（宿主 3200）", [exe("pnpm", ["run", "dev", "--port", "3200"], WEB)])
add("preflight", "bash scripts/preflight.sh（本地↔CI 版本对齐 + 门禁子集）", [bash_script("scripts/preflight.sh")])
add("scan-secrets", "gitleaks 扫描（00S；须与 CI 同版 8.21.2）",
    [exe("gitleaks", ["detect", "--source", ".", "--config", ".gitleaks.toml", "--no-banner"], ROOT)])
add("docker-up", "docker compose up -d", [exe("docker", ["compose", "-f", str(COMPOSE_FILE), "up", "-d"], ROOT)])
add("docker-down", "docker compose down", [exe("docker", ["compose", "-f", str(COMPOSE_FILE), "down"], ROOT)])
add("docker-logs", "docker compose logs", [exe("docker", ["compose", "-f", str(COMPOSE_FILE), "logs", "--tail", "80"], ROOT)])
add("docker-ps", "docker compose ps", [exe("docker", ["compose", "-f", str(COMPOSE_FILE), "ps"], ROOT)])
add("docker-build", "docker compose build", [exe("docker", ["compose", "-f", str(COMPOSE_FILE), "build"], ROOT)])
add("test-all", "后端 + 前端单测 + e2e", composite=("test-backend", "test-frontend-unit", "test-frontend-e2e"))
add("dev", "前后端一起起的说明（两个终端各起一个）", [print_dev_hint])
add("clean", "清理构建产物（跨平台，不用 rm -rf）", [clean_tree])
for _t, _d in (("guard-ports", "端口守卫"), ("guard-versions", "版本锚守卫"),
               ("guard-structure", "目录结构守卫"), ("evidence-check", "stdlib 证据复跑"),
               ("rounds-check", "D-14 轮次熔断")):
    add(_t, f"{_d}（实体在 guards.py）", [guard(_t)])
# 聚合门（04 §8 完成定义引用的 `make guard`）。必须是复合目标：
# check_entry_parity 要求 Makefile 每个目标名都在 BY_NAME 里，漏注册就是红。
add("guard", "全部架构/证据/治理门", composite=("guard-ports", "guard-structure",
                                              "guard-versions", "rounds-check", "evidence-check"))
# 刻意不进 `guard` 复合目标：它吃的是 pytest 刚产出的 coverage.json，
# 没有那次运行就没有输入——放进聚合门只会让每次都多一个 rc=2，反而把"缺输入"这件事喊废。
add("coverage-gate", "模块覆盖率门（先跑 `--cov=app --cov-report=json`；实体在 check_module_coverage.py）",
    [coverage_gate()])
# ─── STEP-00E：验收环境供给与固定（一条命令出全量读数）───────────────────────────
# 这四条原本是 S00X.1.2 任务表里列过、却从未落地的两个名字（verify-backend/verify-frontend），
# 加上 testenv 两条。归属 00E（S00E.1.2/1.3/2.1），落地时把 00X 那句「34 个任务含 verify-*」的
# 误记更正为 6/8 落地 + 2 移交——见 docs/任务规划V0.13.0/steps/STEP-00X-*.md 的执行记录。
add("testenv-up", "起隔离测试 PG16/Redis7（转调 scripts/test-env.sh，端口 5547/6390）",
    [run_test_env("up")])
add("testenv-down", "停并删除隔离测试容器与卷（同上，down）", [run_test_env("down")])
add("verify-backend", "验收面一条命令：探 PG → 单头断言 → upgrade head → pytest 全量（含 -rs 与覆盖率）",
    [check_services, assert_single_head,
     tool_run("alembic", "alembic", ["upgrade", "head"], API),
     tool_run("pytest", "pytest",
              ["tests/", "-q", "-rs", "--junitxml=pytest-report.xml",
               "--cov=app", "--cov-report=term-missing"], API)])
add("verify-frontend", "验收面一条命令：node_modules 读数 → frozen install → typecheck → vitest → 生产口径 build",
    [report_node_modules("装前"),
     exe("pnpm", ["install", "--frozen-lockfile"], WEB),
     report_node_modules("装后"),
     exe("pnpm", ["exec", "tsc", "--noEmit"], WEB),
     exe("pnpm", ["run", "test:unit"], WEB),
     exe("pnpm", ["run", "build"], WEB, {"NEXT_PUBLIC_API_MOCK": "false"})])

BY_NAME = {name: (desc, steps, composite) for name, desc, steps, composite in TASKS}


def run_task(name: str, depth: int = 0) -> int:
    if name not in BY_NAME:
        print(f"❌ 未知任务：{name}（entry.py help 看全部）")
        return RC_FAIL
    desc, steps, composite = BY_NAME[name]
    if depth > 4:
        print(f"❌ 复合任务递归过深（{name}）——任务表有环")
        return RC_FAIL
    print(f"\n=== {name} · {desc} ===")
    if composite:
        codes = [run_task(sub, depth + 1) for sub in composite]
        if RC_FAIL in codes:
            return RC_FAIL
        return RC_TOOL_MISSING if RC_TOOL_MISSING in codes else RC_OK
    for step in steps:
        rc = step()
        if rc != RC_OK:
            print(f"→ {name} 未通过（rc={rc}；3 = 工具缺失，不是通过）")
            return rc
    return RC_OK


def main(argv: list[str]) -> int:
    if sys.platform == "win32":
        # 让中文输出在 cp936 控制台上不被打成问号
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    if not argv or argv[0] in ("help", "-h", "--help"):
        print("用法：python scripts/entry.py <task>     （与 make <task> 同义）")
        print("退出码：0 通过 / 1 失败 / 3 工具缺失（SKIP，不是通过）\n")
        width = max(len(n) for n, _, _, _ in TASKS)
        for n, d, _, comp in TASKS:
            tail = f"  = {' + '.join(comp)}" if comp else ""
            print(f"  {n:<{width}}  {d}{tail}")
        return RC_OK
    return run_task(argv[0])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
