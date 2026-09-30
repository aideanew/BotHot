#!/usr/bin/env bash
# 本地 CI 等价门禁（N12c，2026-09-28；§六十一 增补 parity 门禁）
#
# 存在理由：2026-09-28 连续三次 CI 红灯，三次都是「本地没人跑门禁」——
#   ① t0263 单测微任务竞态（前端只在本机跑过，跑的还是 Windows/UTC+8）
#   ② logout_token.py UP038 + manifest.py mypy arg-type（后端 ruff/mypy 本地零机检）
#   ③ pnpm/action-setup 在仓库根找不到 packageManager（§六十一：CI YAML 逻辑此前
#      从未在本地被等价校验，见 parity_gate 的 ci.yml 回归检测）
# 仓库此前**没有任何 pre-commit / hook / 本地脚本**，所有门禁只在 CI 上跑，
# 于是「提交 → 等 CI → 红了再修」成了唯一的反馈回路。
#
# 用法：
#   bash scripts/preflight.sh           # 全跑（parity + ruff + mypy + 前端）
#   bash scripts/preflight.sh backend   # 只跑后端
#   bash scripts/preflight.sh frontend  # 只跑前端
#   bash scripts/preflight.sh parity    # 只跑版本一致性 + CI 配置回归检测
#
# 铁律（踩过的坑）：
#   1. 取退出码必须 `cmd > log 2>&1; echo $?` —— 禁止 `cmd | tail`
#      （管道会把退出码换成 tail 的，2026-09-28 我因此产出过假绿）。
#   2. 前端必须在 **TZ=UTC** 下跑，否则复现不了 CI（runner 是 UTC）。
#   3. Python 工具优先走项目 venv —— Windows 上 ruff/mypy 常只在
#      backend/.venv/Scripts 且未必进 PATH，依赖 PATH 会误报「工具缺失」。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-all}"
LOG="$(mktemp -d)"
FAIL=0

# 铁律 3：venv 在 Windows 是 .venv/Scripts/python.exe，POSIX 是 .venv/bin/python
if [ -x "$ROOT/backend/.venv/Scripts/python.exe" ]; then
  PY="$ROOT/backend/.venv/Scripts/python.exe"
elif [ -x "$ROOT/backend/.venv/bin/python" ]; then
  PY="$ROOT/backend/.venv/bin/python"
else
  PY=python
fi

hr() { printf '\n=== %s ===\n' "$1"; }

parity_gate() {
  hr "PARITY: 本地 ↔ CI 版本声明一致性 + CI 配置回归检测"
  command -v node >/dev/null 2>&1 || { echo "❌ 缺少 node — 无法校验前端版本声明"; FAIL=1; return; }

  # node：与 .nvmrc 比对。补丁级差异只告警（本机不必装 CI 那个精确补丁号），
  # 主版本不符才阻断（vitest@5 只认 ^22.12.0 || ^24.0.0 || >=26.0.0）
  local exp_node act_node
  exp_node=$(tr -d '[:space:]' < "$ROOT/frontend/.nvmrc")
  act_node=$(node -v 2>/dev/null | sed 's/^v//' || true)
  if [ -z "$act_node" ]; then
    echo "❌ node 不可用"
    FAIL=1
  elif [ "$act_node" = "$exp_node" ]; then
    echo "node=$act_node == .nvmrc ✅"
  elif [ "${act_node%%.*}" = "${exp_node%%.*}" ]; then
    echo "⚠️  node 补丁号漂移：.nvmrc=$exp_node 本机=$act_node（CI 跑 $exp_node，不阻断）"
  else
    echo "❌ node 主版本不符：.nvmrc=$exp_node 本机=$act_node"
    FAIL=1
  fi

  # pnpm：与 frontend/package.json 的 packageManager 严格比对
  local exp_pnpm act_pnpm
  exp_pnpm=$(cd "$ROOT" && node -p "require('./frontend/package.json').packageManager.split('@')[1]" 2>/dev/null || echo "<解析失败>")
  act_pnpm=$(pnpm -v 2>/dev/null || echo "<pnpm 缺失>")
  if [ "$act_pnpm" = "$exp_pnpm" ]; then
    echo "pnpm=$act_pnpm == packageManager ✅"
  else
    echo "❌ pnpm 不符：packageManager=$exp_pnpm 本机=$act_pnpm"
    FAIL=1
  fi

  # CI 配置回归检测（§六十一）：pnpm/action-setup 必须带显式 version。
  # 不带时该 action 在 $GITHUB_WORKSPACE（仓库根）执行，而根目录**没有**
  # package.json（monorepo）→ "No pnpm version is specified" 在 12s 内中止。
  # 只锚定真正的 step 行（^[[:space:]]*- uses:），避免命中注释里的同名文字。
  local wf="$ROOT/.github/workflows/ci.yml" block
  block=$(grep -A3 -E '^[[:space:]]*- uses: pnpm/action-setup' "$wf" 2>/dev/null || true)
  if [ -z "$block" ]; then
    echo "⚠️  未在 ci.yml 找到 pnpm/action-setup（检查是否改名）"
  elif printf '%s\n' "$block" | grep -q 'version: \${{'; then
    echo "ci.yml pnpm/action-setup 带显式 version ✅"
  else
    echo "❌ ci.yml 的 pnpm/action-setup 缺少显式 version —— §六十一 回归，CI 必红"
    FAIL=1
  fi

  # 步骤顺序回归检测（§六十一 更正二）：pnpm/action-setup 必须排在 setup-node 之前。
  # setup-node 的 cache: pnpm 会 shell out 找 pnpm，pnpm 未装时直接报
  # "Unable to locate executable file: pnpm" —— 顺序颠倒就是这个失败形态。
  local ln_pnpm ln_node
  ln_pnpm=$(grep -n -m1 -E '^[[:space:]]*- uses: pnpm/action-setup' "$wf" 2>/dev/null | cut -d: -f1 || true)
  ln_node=$(grep -n -m1 -E '^[[:space:]]*- uses: actions/setup-node' "$wf" 2>/dev/null | cut -d: -f1 || true)
  if [ -n "$ln_pnpm" ] && [ -n "$ln_node" ] && [ "$ln_node" -gt "$ln_pnpm" ]; then
    echo "ci.yml 步骤顺序：pnpm/action-setup(L$ln_pnpm) → setup-node(L$ln_node) ✅"
  else
    echo "❌ ci.yml 步骤顺序错：pnpm/action-setup 必须在 setup-node 之前（L${ln_pnpm:-?} vs L${ln_node:-?}）"
    echo "   setup-node 的 cache: pnpm 会 shell out 找 pnpm，顺序颠倒会报"
    echo "   \"Unable to locate executable file: pnpm\" —— §六十一 更正二"
    FAIL=1
  fi

  # Python 工具链：pyproject.toml 的 dev extras 把 ruff/mypy/pytest 钉死精确版本，
  # 而 ruff 0.12.12 与 0.16.x 的 I001 规则**互斥**（pyproject.toml:25-26 实测记录：
  # 「一方的自动修复即为另一方的违规」）。本机版本不符时 ruff 的结论**对 CI 无意义**，
  # 会产出假绿或假红（§61.2 就是本机 ruff 0.16.5 把 CI 不报的 app/main.py:198 报成红）。
  # 故版本不对齐时直接判红，先修工具再谈门禁结论。
  local exp_ruff act_ruff exp_mypy act_mypy
  exp_ruff=$(sed -n 's/.*"ruff==\(.*\)".*/\1/p' "$ROOT/backend/pyproject.toml" | head -1)
  act_ruff=$("$PY" -m ruff --version 2>/dev/null | cut -d' ' -f2 || echo "<缺失>")
  if [ "$act_ruff" = "$exp_ruff" ]; then
    echo "ruff=$act_ruff == pyproject 钉版 ✅"
  else
    echo "❌ ruff 版本不符：pyproject 钉 $exp_ruff，本机 ${act_ruff:-<缺失>}"
    echo "   （0.12.x 与 0.16.x 的 I001 规则互斥，本机的 ruff 结论对 CI 无意义）"
    echo "   修复：cd backend && ./.venv/Scripts/python.exe -m pip install -e \".[dev]\""
    FAIL=1
  fi

  exp_mypy=$(sed -n 's/.*"mypy==\(.*\)".*/\1/p' "$ROOT/backend/pyproject.toml" | head -1)
  act_mypy=$("$PY" -m mypy --version 2>/dev/null | awk '{print $2}' || echo "<缺失>")
  if [ "$act_mypy" = "$exp_mypy" ]; then
    echo "mypy=$act_mypy == pyproject 钉版 ✅"
  else
    echo "❌ mypy 版本不符：pyproject 钉 $exp_mypy，本机 ${act_mypy:-<缺失>}"
    echo "   修复：cd backend && ./.venv/Scripts/python.exe -m pip install -e \".[dev]\""
    FAIL=1
  fi

  # python：CI 写 python-version "3.12"（浮动补丁号）。本机小版本不同只告警——
  # 工具链按 target-version="py311" 对齐，跨 3.12/3.13 的静态结论基本一致
  local act_py
  act_py=$("$PY" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "<不可用>")
  if [ "$act_py" = "3.12" ]; then
    echo "python=$act_py == CI ✅"
  else
    echo "⚠️  python 版本差异：CI=3.12 本机=$act_py（ruff/mypy 已按钉版对齐，不阻断）"
  fi
}

backend_gate() {
  hr "BACKEND: ruff check app tests"
  ( cd "$ROOT/backend" && "$PY" -m ruff check app tests > "$LOG/ruff.log" 2>&1 )
  local rc=$?
  echo "ruff exit=$rc"; [ $rc -ne 0 ] && { cat "$LOG/ruff.log"; FAIL=1; }

  hr "BACKEND: mypy app"
  ( cd "$ROOT/backend" && "$PY" -m mypy app > "$LOG/mypy.log" 2>&1 )
  rc=$?
  echo "mypy exit=$rc"; [ $rc -ne 0 ] && { cat "$LOG/mypy.log"; FAIL=1; }
}

frontend_gate() {
  hr "FRONTEND: lockfile drift (package.json ↔ pnpm-lock.yaml，frozen 口径)"
  # CI 以 `pnpm install --frozen-lockfile` 安装，声明漂移秒红；但 tsc/vitest 不读 lockfile，
  # 本地全绿也拦不住（8b1b5f2 首次推送即 CI 13s 红的教训）。--lockfile-only 只做解析校验，
  # 不下载包、不动 node_modules，漂移时以 ERR_PNPM_OUTDATED_LOCKFILE 非零退出。
  ( cd "$ROOT/frontend" && pnpm install --frozen-lockfile --lockfile-only > "$LOG/pnpm-drift.log" 2>&1 )
  local rc=$?
  echo "frozen-lockfile exit=$rc"; [ $rc -ne 0 ] && { cat "$LOG/pnpm-drift.log"; FAIL=1; }

  hr "FRONTEND: typecheck (tsc --noEmit)"
  ( cd "$ROOT/frontend" && node node_modules/typescript/bin/tsc --noEmit > "$LOG/tsc.log" 2>&1 )
  rc=$?
  echo "tsc exit=$rc"; [ $rc -ne 0 ] && { cat "$LOG/tsc.log"; FAIL=1; }

  hr "FRONTEND: test:unit (TZ=UTC，与 CI runner 同构)"
  # CI runner 是 UTC；本机是 UTC+8。只在 UTC+8 跑会漏掉时区耦合缺陷（§51 的教训）。
  ( cd "$ROOT/frontend" && TZ=UTC node node_modules/vitest/vitest.mjs run > "$LOG/vitest.log" 2>&1 )
  rc=$?
  echo "vitest exit=$rc"
  if [ $rc -ne 0 ]; then
    sed -e 's/\x1b\[[0-9;]*m//g' "$LOG/vitest.log" | grep -E "FAIL|AssertionError|Tests |Test Files" | head -30
    FAIL=1
  else
    sed -e 's/\x1b\[[0-9;]*m//g' "$LOG/vitest.log" | grep -E "Tests |Test Files"
  fi
}

case "$MODE" in
  backend)  backend_gate ;;
  frontend) frontend_gate ;;
  parity)   parity_gate ;;
  all)
    parity_gate
    backend_gate
    frontend_gate
    ;;
  *) echo "用法: bash scripts/preflight.sh [backend|frontend|parity|all]"; exit 2 ;;
esac

echo
if [ "$FAIL" -eq 0 ]; then
  echo "✅ preflight 全绿 —— 与 CI 门禁口径一致"
else
  echo "❌ preflight 有红 —— 先修再提交，别等 CI"
fi
echo "（日志目录：$LOG）"
exit "$FAIL"
