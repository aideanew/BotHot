#!/usr/bin/env bash
# 前端 CI 等价复现脚本（N12b，2026-09-28）
#
# 目的：把「本地绿、CI 红」的定位成本降到一条命令。
#
# 铁律（每条都踩过坑）：
#   1. 必须与 runner 运行时同构：同 OS 家族 + 同 TZ + 同 Node 补丁号 + 同 pnpm 版本。
#      仅「命令相同」不构成等价 CI（Windows/UTC+8 上跑同样的命令曾得到假绿）。
#   2. 依赖目录必须干净：不得把宿主 node_modules 挂进容器
#      （Windows 平台二进制会污染判断，曾据此误判「锁文件缺 Linux 包」）。
#   3. 退出码必须直接取 $?，**禁止** `cmd | tail` 形式
#      （管道会把退出码换成 tail 的，曾产出 TEST_EXIT=0 的假绿）。
#   4. Docker Desktop 会强制注入 127.0.0.1:10809 代理，容器内无此端口 → 必须显式清空。
#   5. 契约源码在 frontend 之外（tsconfig paths 把 @bothot/contracts 指到 ../packages）：
#      archive 必须带上 packages/，并把容器内 /packages 挂出来（/w 的 ../packages 即 /packages）。
#      漏了它 typecheck / next-build 期类型检查必红——2026-09-30 首版脚本就栽在这里。
#
# 用法：
#   bash scripts/ci-repro-frontend.sh          # 默认 node:24-bookworm-slim
#   NODE_IMAGE=node:20-bookworm-slim bash scripts/ci-repro-frontend.sh
set -uo pipefail

NODE_IMAGE="${NODE_IMAGE:-node:24-bookworm-slim}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROBE_DIR="${PROBE_DIR:-$(mktemp -d)}"

echo "== 准备干净源码（git archive，不含 node_modules）=="
echo "   repo : $REPO_ROOT"
echo "   probe: $PROBE_DIR"
mkdir -p "$PROBE_DIR/src"
git -C "$REPO_ROOT" archive HEAD frontend packages | tar -x -C "$PROBE_DIR/src"

cat > "$PROBE_DIR/run.sh" <<'INNER'
#!/usr/bin/env bash
set -uo pipefail
export TZ=UTC
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
export NO_PROXY="*"
export npm_config_registry="${NPM_REGISTRY:-https://registry.npmmirror.com}"

echo "### 运行时指纹 ###"
echo "node=$(node -v) pnpm=$(pnpm -v) tz=$(date +%Z) os=$(uname -sr) nproc=$(nproc)"

npm i -g "pnpm@9.15.9" --registry="$npm_config_registry" >/dev/null 2>&1

fail=0
step() { # step <名称> <命令...>
  local name="$1"; shift
  "$@" > "/tmp/step.log" 2>&1
  local code=$?
  echo "STEP[$name]_EXIT=$code"
  [ "$code" -ne 0 ] && { echo "--- 失败输出（$name）---"; tail -60 /tmp/step.log; fail=1; }
  return 0
}

step install   pnpm install --frozen-lockfile
step typecheck pnpm run typecheck
step unittest  pnpm run test:unit
NEXT_PUBLIC_API_MOCK=false pnpm run build > /tmp/build.log 2>&1
build_code=$?
echo "STEP[build]_EXIT=$build_code"
if [ "$build_code" -ne 0 ]; then tail -60 /tmp/build.log; fail=1; fi

echo "### 汇总 ###"
echo "PROBE_FAIL=$fail"
exit "$fail"
INNER

# Git Bash/MSYS 会把 /w、/tmp/... 自动改写成 W:/、C:\... 传给 docker.exe，
# 容器报 "working directory 'W:/' is invalid"（2026-09-30 实测）。挂载源在
# 有 cygpath 的平台显式转 Windows 路径，并用 MSYS_NO_PATHCONV=1 保住 -w /w；
# 该变量在 Linux 宿主上是惰性环境变量，无副作用。
if command -v cygpath >/dev/null 2>&1; then
  _SRC_WIN="$(cygpath -w "$PROBE_DIR/src")"
  _RUN_WIN="$(cygpath -w "$PROBE_DIR/run.sh")"
  M_VOL=(-v "$_SRC_WIN\\frontend:/w" -v "$_SRC_WIN\\packages:/packages" -v "$_RUN_WIN:/run.sh:ro")
else
  M_VOL=(-v "$PROBE_DIR/src/frontend:/w" -v "$PROBE_DIR/src/packages:/packages" -v "$PROBE_DIR/run.sh:/run.sh:ro")
fi
MSYS_NO_PATHCONV=1 docker run --rm \
  "${M_VOL[@]}" \
  -w /w \
  -e TZ=UTC -e "NO_PROXY=*" \
  "$NODE_IMAGE" bash /run.sh
code=$?

echo
if [ "$code" -eq 0 ]; then
  echo "✅ 等价 CI 四步全绿（镜像 $NODE_IMAGE）"
else
  echo "❌ 等价 CI 失败（镜像 $NODE_IMAGE，退出码 $code）"
fi
exit "$code"
