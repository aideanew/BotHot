#!/usr/bin/env bash
# BotHot 冒烟脚本（W5 / TEST-003 的可执行雏形）
#
# 用法：
#   bash scripts/smoke.sh                 # docker compose up -d → 探活 → 心跳 → PASS/FAIL
#   SKIP_UP=1   bash scripts/smoke.sh     # 栈已在跑，只探活（不重复 up）
#   SMOKE_STRICT=1 bash scripts/smoke.sh  # 要求 /health 的 status == "ok"（全部依赖就绪）
#   SMOKE_SKIP_HEARTBEAT=1 bash scripts/smoke.sh   # 跳过心跳检查（无 psql 环境时的人工兜底）
#
# 检查项：
#   1) backend HTTP 存活：轮询 http://localhost:3300/api/v1/system/health
#      （backend/app/api/v1/system.py:62 起，**无鉴权**；任一依赖降级仍返 200，故
#       默认判据是「HTTP 200 且信封 code==0」，严格模式才追加 status=="ok"）
#   2) scheduler / worker 心跳：读 `process_heartbeats` 表（backend/app/services/process_heartbeat.py:57），
#      两个进程键都有行且 `age <= HEARTBEAT_MAX_AGE` 才判存活。
#      —— 为什么用数据库心跳而不是端口：这两个进程**不开任何端口**（compose 里它们的
#      healthcheck 就是跑 `python -m app.services.process_heartbeat <key>`）。
#
# 退出码：0 = 全部 PASS；1 = 有 FAIL。
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

COMPOSE_FILE="${COMPOSE_FILE:-docker/compose.yml}"
COMPOSE="docker compose -f ${COMPOSE_FILE}"
HEALTH_URL="${HEALTH_URL:-http://localhost:3300/api/v1/system/health}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-120}"      # 轮询总超时（秒）
HEARTBEAT_MAX_AGE="${HEARTBEAT_MAX_AGE:-300}" # 与 compose 的 healthcheck --max-age 同口径
PG_SERVICE="${PG_SERVICE:-postgres}"
PG_USER="${POSTGRES_USER:-bothot}"
PG_DB="${POSTGRES_DB:-bothot}"
SKIP_UP="${SKIP_UP:-0}"
SMOKE_STRICT="${SMOKE_STRICT:-0}"
SMOKE_SKIP_HEARTBEAT="${SMOKE_SKIP_HEARTBEAT:-0}"

PASS_COUNT=0
FAIL_COUNT=0

log()  { printf '%s\n' "$*"; }
ok()   { PASS_COUNT=$((PASS_COUNT + 1)); log "  ✅ PASS  $*"; }
bad()  { FAIL_COUNT=$((FAIL_COUNT + 1)); log "  ❌ FAIL  $*"; }

log "== BotHot 冒烟 =="
log "   compose=${COMPOSE_FILE}  health=${HEALTH_URL}  strict=${SMOKE_STRICT}"

# ── 0) 拉起栈 ────────────────────────────────────────────────────────────
if [ "$SKIP_UP" = "1" ]; then
  log "[0/2] 跳过 docker compose up（SKIP_UP=1）"
else
  log "[0/2] docker compose up -d ..."
  if ! $COMPOSE up -d; then
    bad "docker compose up -d 失败"
    log ""
    log "结果：PASS=${PASS_COUNT} FAIL=${FAIL_COUNT}"
    exit 1
  fi
  ok "docker compose up -d 完成"
fi

# ── 1) backend 存活探针 ──────────────────────────────────────────────────
log "[1/2] 轮询 backend 健康端点（最长 ${HEALTH_TIMEOUT}s）"
health_body=""
elapsed=0
while [ "$elapsed" -lt "$HEALTH_TIMEOUT" ]; do
  # 优先 curl；无 curl 时回落 python3（宿主环境差异，二者取其一）
  if command -v curl >/dev/null 2>&1; then
    health_body="$(curl -fsS --max-time 3 "$HEALTH_URL" 2>/dev/null || true)"
  elif command -v python3 >/dev/null 2>&1; then
    health_body="$(python3 - "$HEALTH_URL" <<'PY' 2>/dev/null || true
import sys, urllib.request
try:
    with urllib.request.urlopen(sys.argv[1], timeout=3) as r:
        sys.stdout.write(r.read().decode("utf-8", "replace"))
except Exception:
    pass
PY
)"
  else
    bad "既无 curl 也无 python3，无法探活"
    health_body=""
    break
  fi
  [ -n "$health_body" ] && break
  sleep 3
  elapsed=$((elapsed + 3))
done

if [ -z "$health_body" ]; then
  bad "backend /health 在 ${HEALTH_TIMEOUT}s 内无响应（${HEALTH_URL}）"
else
  log "   body: ${health_body}"
  # 判据：HTTP 200 + 信封 code==0（成功）。用 grep 判 json 关键字段，避免依赖 jq。
  if printf '%s' "$health_body" | grep -q '"code"[[:space:]]*:[[:space:]]*0'; then
    ok "backend 存活（信封 code==0）"
  else
    bad "backend 返回非 0 code 或非信封结构"
  fi
  if [ "$SMOKE_STRICT" = "1" ]; then
    if printf '%s' "$health_body" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"'; then
      ok "严格模式：全部依赖 status=ok"
    else
      bad "严格模式：存在依赖降级（status != ok）"
    fi
  else
    if printf '%s' "$health_body" | grep -q '"status"[[:space:]]*:[[:space:]]*"degraded"'; then
      log "  ⚠️  WARN  依赖降级（status=degraded）；如需据此判失败请用 SMOKE_STRICT=1"
    fi
  fi
fi

# ── 2) scheduler / worker 心跳 ───────────────────────────────────────────
log "[2/2] 检查 scheduler / worker 心跳（process_heartbeats，max-age=${HEARTBEAT_MAX_AGE}s）"
if [ "$SMOKE_SKIP_HEARTBEAT" = "1" ]; then
  log "  ⏭️  已按 SMOKE_SKIP_HEARTBEAT=1 跳过（**人工步骤**：在栈内执行"
  log "      \`docker compose -f ${COMPOSE_FILE} exec -T ${PG_SERVICE} psql -U ${PG_USER} -d ${PG_DB}\`"
  log "      然后 \`SELECT process_key, now()-last_heartbeat_at AS age FROM process_heartbeats;\`，"
  log "      两行 age 均应 < ${HEARTBEAT_MAX_AGE}s）"
else
  hb_rows=""
  if hb_rows="$($COMPOSE exec -T "$PG_SERVICE" psql -U "$PG_USER" -d "$PG_DB" -tAc \
      "SELECT process_key || '|' || EXTRACT(EPOCH FROM (now() - last_heartbeat_at))::int FROM process_heartbeats" 2>/dev/null)"; then
    if [ -z "$hb_rows" ]; then
      bad "process_heartbeats 无任何行——scheduler/worker 从未报到（或迁移未执行）"
    else
      log "   rows: $(printf '%s' "$hb_rows" | tr '\n' ' ')"
      for key in scheduler worker; do
        row="$(printf '%s\n' "$hb_rows" | grep "^${key}|" || true)"
        if [ -z "$row" ]; then
          bad "${key} 无心跳行（进程从未启动）"
          continue
        fi
        age="${row#*|}"
        if [ "$age" -le "$HEARTBEAT_MAX_AGE" ] 2>/dev/null; then
          ok "${key} 心跳新鲜（age=${age}s）"
        else
          bad "${key} 心跳过期（age=${age}s > ${HEARTBEAT_MAX_AGE}s）——进程卡死或已退出"
        fi
      done
    fi
  else
    bad "无法查询 ${PG_SERVICE}.process_heartbeats（psql 不可用 / 容器未起 / 表未建）"
  fi
fi

log ""
log "结果：PASS=${PASS_COUNT} FAIL=${FAIL_COUNT}"
if [ "$FAIL_COUNT" -gt 0 ]; then
  log "冒烟结论：❌ FAIL"
  exit 1
fi
log "冒烟结论：✅ PASS"
exit 0
