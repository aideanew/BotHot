#!/usr/bin/env bash
# 隔离测试环境（STEP-00 / S0.1.1，任务规划 V0.2.0）
#
# 存在理由（D-12）：apps/api/tests/conftest.py 曾把 `:5433/bothot`（部署形态库）当
# 连库目标的第三级回退且只告警不拒绝——未设 AIDEANBOT_TEST_PG_DSN 的机器上「跑测试」
# 等于写生产形态库，而部署中的 scheduler/worker 会把测试订阅当到期任务真实消费（D23）。
# S0.1.2 删掉该回退后，连库用例在「未配置」时一律 skip；本脚本负责让配置变成一条命令。
#
# 用法：
#   bash scripts/test-env.sh up     起隔离 PG 16（宿主 5547）+ Redis（宿主 6390），幂等
#   bash scripts/test-env.sh down   停止并删除容器与数据卷
#   bash scripts/test-env.sh env    只打印 export 行，供 eval "$(bash scripts/test-env.sh env)"
#
# 端口铁律（AGENTS.md「端口分配准则」）：5433/5435=部署 PG、6379/6380=部署 Redis、
# 3000=主平台。测试端口命中前四者即 exit 2——**含**通过 AIDEANBOT_TEST_PG_PORT /
# AIDEANBOT_TEST_REDIS_PORT 覆盖的场景；端口 <1024 同样 exit 2（非 root 无法监听，
# 且 conftest 用保留端口 1 表达「必然拒连」，不复用低端口以免语义混淆）。
#
# 环境来源口径：docker/podman 由本脚本自动化；以本地二进制（initdb/pg_ctl/redis-server）
# 自备实例时，设 AIDEANBOT_TEST_PG_PORT/AIDEANBOT_TEST_REDIS_PORT 后 `env` 子命令照常可用。
#
# ⚠ 本仓库 AI 会话约定「不实际启动服务」：本脚本由执行者自行运行；提交前仅以 `bash -n`
#   做语法验证，未在含 docker 的机器上实跑过 up/down（未验证声明，勿当已验收）。
# ⚠ PG_PASSWORD 取 `bothot_ci`：一次性容器凭据，且落在 .gitleaks.toml 占位口令白名单内，
#   换任何其他值会触发明文口令告警。
set -uo pipefail

TEST_PG_HOST_PORT="${AIDEANBOT_TEST_PG_PORT:-5547}"
TEST_REDIS_HOST_PORT="${AIDEANBOT_TEST_REDIS_PORT:-6390}"
PG_USER="bothot"
PG_PASSWORD="bothot_ci"
PG_DB="bothot_test"
PG_CONTAINER="bothot-test-pg"
REDIS_CONTAINER="bothot-test-redis"
PG_IMAGE="postgres:16-alpine"
REDIS_IMAGE="redis:7-alpine"
FORBIDDEN_PORTS=("5433" "5435" "6379" "6380")

fail() {
  printf '%s\n' "$2" >&2
  exit "$1"
}

guard_ports() {
  local port forbidden
  for port in "$TEST_PG_HOST_PORT" "$TEST_REDIS_HOST_PORT"; do
    case "$port" in
      '' | *[!0-9]*) fail 2 "测试端口必须为纯数字，实际='$port'" ;;
    esac
    if [ "$port" -lt 1024 ] || [ "$port" -gt 65535 ]; then
      fail 2 "测试端口 $port 越界（需 1024–65535）"
    fi
    for forbidden in "${FORBIDDEN_PORTS[@]}"; do
      if [ "$port" = "$forbidden" ]; then
        fail 2 "测试端口 $port 命中部署端口（AGENTS.md 端口分配准则），拒绝启动"
      fi
    done
  done
}

runtime() {
  local candidate
  for candidate in ${CONTAINER_RUNTIME:-docker podman}; do
    if command -v "$candidate" >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

dsn() {
  printf 'postgresql+psycopg://%s:%s@localhost:%s/%s\n' \
    "$PG_USER" "$PG_PASSWORD" "$TEST_PG_HOST_PORT" "$PG_DB"
}

print_env() {
  guard_ports
  printf 'export AIDEANBOT_TEST_PG_DSN=%q\n' "$(dsn)"
  printf 'export DATABASE_URL=%q\n' "$(dsn)"
  printf 'export REDIS_URL=%q\n' "redis://localhost:${TEST_REDIS_HOST_PORT}/0"
  printf '# 连库自检（去 +psycopg 驱动前缀后即为 libpq 连接串）：\n'
  printf '#   psql "${AIDEANBOT_TEST_PG_DSN/+psycopg/}" -c "select 1"\n'
}

ensure_container() {
  local rt="$1" name="$2" image="$3"
  shift 3
  if [ "$("$rt" inspect -f '{{.State.Running}}' "$name" 2>/dev/null || echo missing)" = "true" ]; then
    printf '%s 已在运行\n' "$name"
    return 0
  fi
  if "$rt" inspect "$name" >/dev/null 2>&1; then
    "$rt" start "$name" >/dev/null
    printf '%s 已启动（既有容器）\n' "$name"
    return 0
  fi
  "$rt" run -d --name "$name" "$@" "$image" >/dev/null
  printf '%s 已创建\n' "$name"
}

wait_ready() {
  local rt="$1" name="$2" probe="$3" tries="${4:-60}" i
  for ((i = 0; i < tries; i++)); do
    if "$rt" exec "$name" bash -lc "$probe" >/dev/null 2>&1; then
      printf '%s 就绪\n' "$name"
      return 0
    fi
    sleep 1
  done
  fail 1 "$name 在 ${tries}s 内未就绪，查日志：$rt logs $name"
}

cmd_up() {
  guard_ports
  local rt
  if ! rt="$(runtime)"; then
    fail 3 "未找到 docker/podman；自备实例请设 AIDEANBOT_TEST_PG_PORT/AIDEANBOT_TEST_REDIS_PORT 后用 env 子命令"
  fi
  ensure_container "$rt" "$PG_CONTAINER" "$PG_IMAGE" \
    -p "${TEST_PG_HOST_PORT}:5432" \
    -e "POSTGRES_USER=${PG_USER}" \
    -e "POSTGRES_PASSWORD=${PG_PASSWORD}" \
    -e "POSTGRES_DB=${PG_DB}" \
    -v "${PG_CONTAINER}-data:/var/lib/postgresql/data"
  ensure_container "$rt" "$REDIS_CONTAINER" "$REDIS_IMAGE" \
    -p "${TEST_REDIS_HOST_PORT}:6379" --appendonly no
  wait_ready "$rt" "$PG_CONTAINER" "pg_isready -U ${PG_USER} -d ${PG_DB}" 60
  wait_ready "$rt" "$REDIS_CONTAINER" "redis-cli -p 6379 ping" 30
  printf '迁移：cd apps/api && DATABASE_URL=%s alembic upgrade head\n' "$(dsn)"
  printf '注入：eval \"$(bash scripts/test-env.sh env)\"\n'
}

cmd_down() {
  local rt
  rt="$(runtime)" || fail 3 "未找到 docker/podman，无需停止"
  "$rt" rm -f -v "$PG_CONTAINER" "$REDIS_CONTAINER" >/dev/null 2>&1 || true
  printf '已停止并删除 %s / %s（数据卷 %s-data 保留，如需清理：%s volume rm %s-data）\n' \
    "$PG_CONTAINER" "$REDIS_CONTAINER" "$PG_CONTAINER" "$rt" "$PG_CONTAINER"
}

usage() {
  printf '用法: bash scripts/test-env.sh up|down|env\n'
  printf '  up    起隔离 PG16（宿主 %s）+ Redis（宿主 %s），幂等\n' \
    "$TEST_PG_HOST_PORT" "$TEST_REDIS_HOST_PORT"
  printf '  down  停止并删除容器\n'
  printf '  env   只打印 export 行，供 eval "$(bash scripts/test-env.sh env)"\n'
  printf '拒绝端口: %s（AGENTS.md 部署端口表）——命中即 exit 2\n' "${FORBIDDEN_PORTS[*]}"
}

main() {
  case "${1:-up}" in
    up) cmd_up ;;
    down) cmd_down ;;
    env) print_env ;;
    -h | --help | help) usage ;;
    *)
      usage >&2
      exit 64
      ;;
  esac
}

main "$@"
