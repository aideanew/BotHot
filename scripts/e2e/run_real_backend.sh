#!/usr/bin/env bash
# STEP-59 真后端 e2e 启动器（原子步与判据见 docs/任务规划V0.22.0/08-阶段A执行细则.md §2 59.1）
#
# 一条命令把"能跑真后端 e2e"的四件事摆好：迁移 → uvicorn(:3300) → 探活 → 种子会话 → 前端(:3200)。
# 端口口径按 D-V4-02：**被占就退出非零，绝不静默换口**（换口会让 playwright 的 baseURL 与
# next start 的端口各说各话，那类失败读起来像"测试红了"，实际是环境错位）。
#
# 会话来源按 D-V22-02：产品代码零改动，只在测试侧往 Redis 写会话 + 本地 users 行，
# 用 `qa-fixture-` 假令牌命中 `app/services/auth/service.py` 的短路（不进主平台）。
# 因此 uvicorn 必须显式 `SESSION_STORE_BACKEND=redis`——该开关默认是 memory（config.py:55），
# 而 memory 是**进程内**存储，另一个进程写不进去，种子会化成"写了但看不见"的静默失效。
#
# 用法：
#   bash scripts/e2e/run_real_backend.sh [--with-fake-llm] [--no-frontend] [--stop]
# 退出码（读 CI 日志时靠它分辨"哪一环不对"，全靠非零码不行的话就会把环境缺失读成用例失败）：
#   2 端口被占（只查这一棒要用的那几个） 3 --with-fake-llm 但 fake_llm.py 还没有
#   4 60s 内 /health 没回 code==0        5 seed 不是 3 条、或 cookie 名/值解析不出来
#   6 S59.0 探针红 ⇒ 按 02 §5 走方案 B    7 60s 内 :3200 没起来
#   8 /ready 返回码不在 {200,503}        9 终态自检：pidfile 里的进程已经不在了
# 环境变量（CI 与本机共用，全部给默认值）：
#   DATABASE_URL REDIS_URL AIDEAN_ISSUER E2E_RUN_DIR E2E_SEED_FILE APP_ENV E2E_SKIP_MIGRATE
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_DIR="${E2E_RUN_DIR:-${RUNNER_TEMP:-/tmp}/e2e-real}"
SEED_FILE="${E2E_SEED_FILE:-$RUN_DIR/seed.txt}"
PIDS_FILE="$RUN_DIR/pids"
WITH_FAKE_LLM=0
NO_FRONTEND=0
DO_STOP=0
for arg in "$@"; do
  case "$arg" in
    --with-fake-llm) WITH_FAKE_LLM=1 ;;
    --no-frontend) NO_FRONTEND=1 ;;
    --stop) DO_STOP=1 ;;
    *) echo "❌ 未知参数：$arg（可用：--with-fake-llm --no-frontend --stop）" >&2; exit 64 ;;
  esac
done

mkdir -p "$RUN_DIR"

port_open() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

# 停：先按 pidfile 逐个 kill，再用命令行特征兜一遍。
# 为什么两层都要：记录到的 PID 未必是真正的监听者——`pnpm exec next start` 里 pnpm 会派生
# node 子进程，只 kill 包装进程会把服务留在端口上，而脚本照样打印"stopped frontend"。
# 前端那一处已改成直接 `exec node ./node_modules/next/dist/bin/next`（PID 就是服务本身），
# 兜底留着是因为端口残留的失败形态最难读（下一次进来只看到 rc=2"端口被占"）。
stop_all() {
  local stopped_any=0 name pid pat port
  if [ -f "$PIDS_FILE" ]; then
    while read -r name pid; do
      [ -n "${pid:-}" ] || continue
      if kill "$pid" 2>/dev/null; then echo "stopped $name pid=$pid"; stopped_any=1
      else echo "already gone $name pid=$pid"; fi
    done < "$PIDS_FILE"
    rm -f "$PIDS_FILE"
  fi
  for pat in "uvicorn app.main:app --host 127.0.0.1 --port 3300" \
             "next/dist/bin/next start -p 3200" \
             "scripts/e2e/fake_llm.py --port 3290"; do
    if pgrep -f "$pat" >/dev/null 2>&1; then
      pkill -f "$pat" && { echo "pkill 兜底清掉：$pat"; stopped_any=1; }
    fi
  done
  for port in 3200 3290 3300; do
    if port_open "$port"; then
      echo "❌ 端口 $port 仍被占用：本脚本起过的进程没清干净（不静默放过）" >&2
      return 1
    fi
  done
  [ "$stopped_any" = 1 ] || echo "没有本脚本起过的进程（pidfile 不存在，三个端口本来就空闲）"
  return 0
}

if [ "$DO_STOP" = 1 ]; then
  stop_all
  exit $?
fi

: "${DATABASE_URL:=postgresql+psycopg://bothot:bothot@localhost:5433/bothot}"
: "${REDIS_URL:=redis://localhost:6380/0}"
: "${AIDEAN_ISSUER:=http://127.0.0.1:9}"   # 关闭端口：主平台不可达，逼出降级/短路分支，也保证不外呼
export DATABASE_URL REDIS_URL AIDEAN_ISSUER
export SESSION_STORE_BACKEND=redis
export QA_FIXTURE_TOKEN_PREFIX="qa-fixture-"
export AIDEAN_PUBLIC_URL="$AIDEAN_ISSUER"
# 守卫口径：`app_env` 默认 development 已在 NON_PRODUCTION_ENVS 白名单里（config.py:10,16），
# 而 QA fixture 前缀与 memory 会话后端都是"生产拒启"项——这条链只在非生产环境跑，写死而非继承，
# 免得有人拿 APP_ENV=production 触发这道 e2e 时得到一个"守卫拒启"的假红。
export APP_ENV="${APP_ENV:-development}"

# 只检查"这一次真的要用"的端口：以前 3200 无条件检查，于是 `--no-frontend`（说明写着
# "复用已有栈时用"）在同一条检查里就撞 rc=2 ——那条旗标永远不可能起到"复用"的作用。
ports_to_check="3300"
[ "$WITH_FAKE_LLM" = 1 ] && ports_to_check="3290 $ports_to_check"
[ "$NO_FRONTEND" = 1 ] || ports_to_check="3200 $ports_to_check"
for port in $ports_to_check; do
  if port_open "$port"; then
    echo "❌ 端口 $port 已被占用：本脚本不换口（D-V4-02），请先停掉占用者" >&2
    echo "   只跑后端与种子可以加 --no-frontend（就不检查 3200 了）" >&2
    exit 2
  fi
done
echo "端口检查通过（本次要用：$ports_to_check）"

# pidfile 一开头就建：早期退出（探活超时 rc=4、seed 不是 3 条 rc=5、探针 rc=6、
# ready 形不对 rc=8、前端没起来 rc=7）都发生在"已经起了 uvicorn"之后，
# 而旧写法只在成功路径落盘 ⇒ 失败后进程留在端口上、下一次进来只看到 rc=2"端口被占"。
: > "$PIDS_FILE"
record_pid() { printf '%s %s\n' "$1" "$2" >> "$PIDS_FILE"; }
# 失败即拆；成功不拆（e2e 还要用这些进程）。
trap 'rc=$?; if [ "$rc" -ne 0 ]; then
        echo "== 失败退出 rc=$rc：拆除本脚本起过的进程 ==" >&2
        stop_all || true
      fi' EXIT

if [ "$WITH_FAKE_LLM" = 1 ] && [ ! -f "$REPO_ROOT/scripts/e2e/fake_llm.py" ]; then
  echo "❌ --with-fake-llm 需要 scripts/e2e/fake_llm.py（STEP-60 交付），该文件现在不存在" >&2
  exit 3
fi

if [ "${E2E_SKIP_MIGRATE:-0}" != "1" ]; then
  echo "== ① 迁移：alembic upgrade head（$DATABASE_URL）=="
  (cd "$REPO_ROOT/apps/api" && python -m alembic upgrade head)
fi

if [ "$WITH_FAKE_LLM" = 1 ]; then
  echo "== ② 假 LLM 上游 :3290 =="
  nohup sh -c "cd '$REPO_ROOT' && exec python scripts/e2e/fake_llm.py --port 3290" \
    > "$RUN_DIR/fake_llm.out" 2>&1 &
  FAKE_LLM_PID=$!
  record_pid fake_llm "$FAKE_LLM_PID"
  export LLM_API_BASE="http://127.0.0.1:3290/v1"
  export EMBEDDING_API_BASE="http://127.0.0.1:3290/v1"
  export LLM_API_KEY="fake" EMBEDDING_API_KEY="fake"
fi

echo "== ③ uvicorn :3300 =="
nohup sh -c "cd '$REPO_ROOT/apps/api' && exec python -m uvicorn app.main:app --host 127.0.0.1 --port 3300" \
  > "$RUN_DIR/uvicorn.log" 2>&1 &
UVICORN_PID=$!
record_pid backend "$UVICORN_PID"

echo "== ④ 探活：GET /api/v1/system/health 直到 code==0（上限 60s）=="
deadline=$((SECONDS + 60))
ok=0
while [ "$SECONDS" -lt "$deadline" ]; do
  body="$(curl -fsS --max-time 3 http://127.0.0.1:3300/api/v1/system/health 2>/dev/null || true)"
  if printf '%s' "$body" | grep -q '"code"[[:space:]]*:[[:space:]]*0'; then
    ok=1
    echo "health 就绪（${SECONDS}s）：$body"
    break
  fi
  sleep 2
done
if [ "$ok" != 1 ]; then
  echo "❌ 60s 内 /health 没有回到 code==0；uvicorn 日志尾部：" >&2
  tail -30 "$RUN_DIR/uvicorn.log" >&2 || true
  exit 4
fi

echo "== ⑤ 种子会话（qa_seed_sessions.py 收编，不另写一份）=="
echo "   给 Playwright 的接法：那一步要显式带 E2E_SEED_FILE=$SEED_FILE"
echo "   （本脚本自己 export 不了调用方的 shell，real.setup.ts 的默认路径与本行同源：\${RUNNER_TEMP:-/tmp}/e2e-real/seed.txt）"
(cd "$REPO_ROOT/apps/api" && python scripts/qa_seed_sessions.py) > "$SEED_FILE" 2>&1
# 统一去掉 CR：win 上跑这一步时 python 可能写 CRLF，而 `$(...)` 只剥尾换行不剥尾 CR，
# 于是第 ⑥ 步从行尾取到的 COOKIE_VALUE 会带一个 \r，curl 的请求头随之畸形——
# 那种红会被读成"S59.0 不成立 ⇒ 走方案 B"，实际是行尾。real.setup.ts 侧本来就按 /\r?\n/ 解析。
SEED_LF="$RUN_DIR/seed.lf.txt"
tr -d '\r' < "$SEED_FILE" > "$SEED_LF"
n_session=$(grep -c '^session ' "$SEED_LF" || true)
echo "seed 写入 $SEED_FILE：session 行 $n_session 条（应为 3）"
if [ "$n_session" != "3" ]; then
  echo "❌ 种子会话不是 3 条；seed 内容：" >&2
  cat "$SEED_LF" >&2
  exit 5
fi

echo "== ⑥ S59.0 先验探针：主平台不可达时，admin 会话能不能进后台 =="
ADMIN_COOKIE_LINE="$(grep '^session qa-admin-001' "$SEED_LF" | tail -n 1)"
COOKIE_NAME="$(printf '%s' "$ADMIN_COOKIE_LINE" | sed -n 's/.*cookie=\([^ ]*\) value=.*/\1/p')"
COOKIE_VALUE="$(printf '%s' "$ADMIN_COOKIE_LINE" | sed -n 's/.* value=\(.*\)/\1/p')"
if [ -z "$COOKIE_NAME" ] || [ -z "$COOKIE_VALUE" ]; then
  echo "❌ 没能从 seed 行里解析出 cookie 名与值（不猜，停下）：$ADMIN_COOKIE_LINE" >&2
  exit 5
fi
ME_JSON="$(curl -fsS --max-time 10 -H "Cookie: $COOKIE_NAME=$COOKIE_VALUE" http://127.0.0.1:3300/api/v1/auth/me || true)"
READY_CODE="$(curl -s -o "$RUN_DIR/ready.json" -w '%{http_code}' --max-time 10 http://127.0.0.1:3300/api/v1/system/ready || true)"
echo "probe: cookie=$COOKIE_NAME value_len=${#COOKIE_VALUE}"
echo "probe: GET /auth/me → $ME_JSON"
echo "probe: GET /system/ready → HTTP $READY_CODE body=$(cat "$RUN_DIR/ready.json" 2>/dev/null || echo '<无>')"

if ! printf '%s' "$ME_JSON" | grep -q '"is_admin"[[:space:]]*:[[:space:]]*true'; then
  echo "❌ S59.0 红：主平台不可达时 admin 会话没有拿到 is_admin=true ⇒ 按 02 §5 走方案 B" \
       "（e2e 档起本地假主平台），不改产品代码、不需用户裁决" >&2
  exit 6
fi
echo "S59.0 绿：方案 A 成立（qa-fixture 短路 + 本地 users 行就够，不进主平台）"

# /ready 也判，不只是打印：以前 READY_CODE 取了、echo 了，却没有任何一条退出码依赖它——
# 那正是"看着检查了其实没检查"。503 是合法读数（依赖未就绪时后端回 503 + 标准信封，
# ⑥ 那条告警状态条本来就要画这个态）；其余码（000/4xx/5xx）说明这一棒的底座不对，
# 单独用 rc=8，好让它不会被误读成"S59.0 不成立 ⇒ 走方案 B"（那是 rc=6）。
case "$READY_CODE" in
  200|503) echo "probe /ready 判定通过：HTTP $READY_CODE（503 属合法降级读数）" ;;
  *) echo "❌ /ready 读到 HTTP $READY_CODE（只接受 200 或 503），body=$(cat "$RUN_DIR/ready.json" 2>/dev/null || echo '<无>')" >&2
     exit 8 ;;
esac

if [ "$NO_FRONTEND" = 1 ]; then
  echo "== ⑦ 跳过前端（--no-frontend）：只留后端与种子，pidfile 已按增量记好 =="
  exit 0
fi

echo "== ⑦ 前端 :3200（MOCK=false 构建一次后 next start）=="
BUILD_T0=$SECONDS
(cd "$REPO_ROOT/apps/web" && rm -rf .next && NEXT_PUBLIC_API_MOCK=false pnpm exec next build \
  > "$RUN_DIR/next_build.log" 2>&1)
echo "next build（MOCK=false）用时 $((SECONDS - BUILD_T0))s"
# 直接 exec node 打 next 的 bin，而不是 `pnpm exec next start`：后者 PID 是 pnpm，
# 真监听者（node）是它的子进程 ⇒ pidfile 记的是包装进程，`--stop` 只 kill 得到包装进程，
# 服务还占在 3200 上而日志照样打印 "stopped frontend"。
nohup sh -c "cd '$REPO_ROOT/apps/web' && exec node ./node_modules/next/dist/bin/next start -p 3200" \
  > "$RUN_DIR/next_start.log" 2>&1 &
NEXT_PID=$!
record_pid frontend "$NEXT_PID"
ok=0
deadline=$((SECONDS + 60))
while [ "$SECONDS" -lt "$deadline" ]; do
  if port_open 3200 && curl -fsS --max-time 3 http://127.0.0.1:3200/ -o /dev/null 2>/dev/null; then
    ok=1
    echo "前端就绪（${SECONDS}s）"
    break
  fi
  sleep 2
done
if [ "$ok" != 1 ]; then
  echo "❌ 60s 内 :3200 没有起来；next start 日志尾部：" >&2
  tail -30 "$RUN_DIR/next_start.log" >&2 || true
  exit 7
fi

# pidfile 已在 ②③⑦ 各步增量写好，这里不再整份覆盖。
# 终态自检：每条记到的 PID 必须还活着——不然"全部就绪"这句话没有依据
# （服务在 exec 之后立刻崩掉，端口检查那一轮可能正好赶上它还活着的那 2 秒）。
missing=""
while read -r name pid; do
  [ -n "${pid:-}" ] || continue
  kill -0 "$pid" 2>/dev/null || missing="$missing $name"
done < "$PIDS_FILE"
if [ -n "$missing" ]; then
  echo "❌ pidfile 里这些进程已不在：$missing ⇒ 就绪判定不成立（内容：$(tr '\n' ';' < "$PIDS_FILE")）" >&2
  exit 9
fi
echo "== 全部就绪：后端 :3300、前端 :3200、seed=$SEED_FILE、pidfile=$PIDS_FILE（$(wc -l < "$PIDS_FILE") 条）=="
