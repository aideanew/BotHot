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
#   bash scripts/e2e/run_real_backend.sh [--with-fake-llm] [--with-fake-langbot] [--no-frontend] [--stop]
# 退出码（读 CI 日志时靠它分辨"哪一环不对"，全靠非零码不行的话就会把环境缺失读成用例失败）：
#   2 端口被占（只查这一棒要用的那几个） 3 --with-fake-llm 但 fake_llm.py 还没有
#   4 60s 内 /health 没回 code==0        5 seed 不是 3 条、或 cookie 名/值解析不出来
#   6 S59.0 探针红 ⇒ 按 02 §5 走方案 B    7 60s 内 :3200 没起来
#   8 /ready 返回码不在 {200,503}        9 终态自检：pidfile 里的进程已经不在了
#   10 探针没取到响应（curl 缺失或超时）⇒ 不判 S59.0，别把它读成"要走方案 B"
#   11 --with-fake-langbot 但 fake_langbot.py 还没有
#   12 ⑤b /chat 种子不合格（缺 seed_chat_space.py / 脚本非零 / 取不到 space_id）
#   64 未知参数（连"该起什么"都没说清，不做默认猜测）
# 环境变量（CI 与本机共用，全部给默认值）：
#   DATABASE_URL REDIS_URL AIDEAN_ISSUER E2E_RUN_DIR E2E_SEED_FILE APP_ENV E2E_SKIP_MIGRATE
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_DIR="${E2E_RUN_DIR:-${RUNNER_TEMP:-/tmp}/e2e-real}"
SEED_FILE="${E2E_SEED_FILE:-$RUN_DIR/seed.txt}"
PIDS_FILE="$RUN_DIR/pids"
WITH_FAKE_LLM=0
WITH_FAKE_LANGBOT=0
NO_FRONTEND=0
DO_STOP=0
for arg in "$@"; do
  case "$arg" in
    --with-fake-llm) WITH_FAKE_LLM=1 ;;
    --with-fake-langbot) WITH_FAKE_LANGBOT=1 ;;
    --no-frontend) NO_FRONTEND=1 ;;
    --stop) DO_STOP=1 ;;
    *) echo "❌ 未知参数：$arg（可用：--with-fake-llm --with-fake-langbot --no-frontend --stop）" >&2; exit 64 ;;
  esac
done

mkdir -p "$RUN_DIR"

port_open() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

# 端口终检失败时把占用者打出来。两个工具都没有就如实说"取不到"，不假装读过。
# 末尾必须 return 0：空闲时 `ss | grep` 无命中返回 1，而 `ownp="$(port_owner …)"`
# 这条赋值在 `set -euo pipefail` 下会把 1 变成脚本中止（CI 实证 4160b81：两行
# `stopped …` 之后零输出退出 1，`端口终检` 一行都没打出来）——读数函数的契约是
# "永远成功、如实打印读到了什么"，失败语义交给调用方的端口判定，不归它。
port_owner() {
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null | grep ":$1 " | head -2
  elif command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | tail -2
  else
    echo "(本机没有 ss 也没有 lsof ⇒ 占用者取不到)"
  fi
  return 0
}

# D-V23-16：认领"该不该给这个 PID 发信号"的**主判据**——它是不是该端口的监听者。
# 原来的唯一判据是命令行特征，而 `next start` 会把进程标题改写成 `next-server (v15.x)`，
# `ps -o args=` 就再也看不到 `next/dist/bin/next` ⇒ 白名单不匹配 ⇒ 不发信号 ⇒ 端口一直被占
# （CI 实证：同屏 `跳过 frontend pid=4426：命令行对不上` + `占用者读数：…("next-server (v1"...)`）。
# 端口属主是 OS 给的事实、不受标题改写影响；取不到属主时**不**当作"不是它"，仍退回命令行特征判定。
port_owner_pids() {
  local port="$1" line
  if command -v ss >/dev/null 2>&1; then
    while IFS= read -r line; do
      case "$line" in
        *":$port "*) printf '%s\n' "$line" | grep -o 'pid=[0-9][0-9]*' | sed 's/^pid=//' ;;
      esac
    done < <(ss -ltnp 2>/dev/null)
  elif command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null
  fi
  return 0
}

role_port() {
  case "$1" in
    backend) echo 3300 ;;
    frontend) echo 3200 ;;
    fake_llm) echo 3290 ;;
    fake_langbot) echo 3291 ;;
    *) echo "" ;;
  esac
}

# 停：先按 pidfile 逐个 kill，再用命令行特征兜一遍。
# 为什么两层都要：记录到的 PID 未必是真正的监听者——`pnpm exec next start` 里 pnpm 会派生
# node 子进程，只 kill 包装进程会把服务留在端口上，而脚本照样打印"stopped frontend"。
# 前端那一处已改成直接 `exec node ./node_modules/next/dist/bin/next`（PID 就是服务本身），
# 兜底留着是因为端口残留的失败形态最难读（下一次进来只看到 rc=2"端口被占"）。
stop_all() {
  local stopped_any=0 had_pidfile=0 name pid pat port cmdline grace ownp owns have_ps=0 have_ps_out
  # `command -v ps` 只证明"有个叫 ps 的程序"，不证明它支持 `-p … -o args=`：git-bash 的 ps 就是这种
  # （文件头注写的"退化成按 PID 直杀并说明原因"当时并未真的发生——have_ps 被置成 1、cmdline 取空、
  # 于是每个 PID 都走"命令行对不上"分支被跳过）。这里改成**探能力**而不是探存在，并把探测结果打出来。
  have_ps=0
  have_ps_out="$(ps -p 1 -o args= 2>/dev/null || true)"
  if [ -n "${have_ps_out// /}" ]; then
    have_ps=1
  else
    echo "note: 本机 ps 不支持 -o args=（或未取到输出）⇒ 认领只能靠端口属主，命令行特征这一层跳过"
  fi
  # 先把"本脚本起过哪些角色"抄下来：下面要 rm pidfile，终检得在文件还在的时候判。
  local started=""
  if [ -f "$PIDS_FILE" ]; then
    had_pidfile=1
    started="$(cut -d' ' -f1 < "$PIDS_FILE" 2>/dev/null || true)"
    while read -r name pid; do
      [ -n "${pid:-}" ] || continue
      # 只给"确属本脚本那一类"的 PID 发信号：开发机上 PID 会复用，
      # 裸 `kill` 可能打死一个早已占坑的无关进程，而日志照样写 "stopped frontend"。
      # 主判据（D-V23-16）= 它是不是该角色的端口的监听者；端口属主不受进程标题改写影响。
      # 取不到属主（本机没有 ss 也没有 lsof）时**不**把"取不到"当成"不是它"，退回命令行特征判定。
      port="$(role_port "$name")"
      owns=0
      ownp=""
      if [ -n "$port" ]; then
        ownp="$(port_owner_pids "$port")"
      fi
      if [ -n "${ownp// /}" ] && printf '%s\n' "$ownp" | grep -qx "$pid"; then
        owns=1
      fi
      if [ "$owns" != 1 ]; then
        if [ -n "${ownp// /}" ]; then
          # 端口上确有监听者，且不是 PIDfile 里这个 PID ⇒ 它已被复用，一律不发信号。
          # 命令行不参与：命令行特征分不清「同名的另一个会话」，那正是 D-V23-16 要堵的洞（D-V24-06 甲）。
          echo "跳过 $name pid=$pid：端口 :$port 的监听者是 $ownp，不是它（不发信号）"
          continue
        fi
        if [ "$have_ps" = 1 ]; then
          cmdline="$(ps -p "$pid" -o args= 2>/dev/null || true)"
          case "$cmdline" in
            *"uvicorn app.main:app --host 127.0.0.1 --port 3300"* | *"next/dist/bin/next"* | *"next-server"* | *"scripts/e2e/fake_llm.py"* | *"scripts/e2e/fake_langbot.py"*) ;;
            *) echo "跳过 $name pid=$pid：既不是端口 :${port:-?} 的监听者、命令行也对不上（PID 可能已被复用，不发信号）"; continue ;;
          esac
        else
          echo "note: $name pid=$pid 无端口属主证据也无 ps 能力 ⇒ 按 PID 直杀（本机能力受限，非静默）"
        fi
      fi
      if kill "$pid" 2>/dev/null; then echo "stopped $name pid=$pid"; stopped_any=1
      else echo "already gone $name pid=$pid"; fi
    done < "$PIDS_FILE"
    rm -f "$PIDS_FILE"
  fi
  # 特征兜底只用于"本 checkout 绝对路径下"的三条：next、fake_llm、fake_langbot。
  # 为什么不再按 cmdline 杀 uvicorn：那条特征（`--port 3300`）在本机共用工作树里会命中
  # **别人**起的后端（compose 的 backend 也是 3300），一个 rc=2 的早退就把别人的栈杀了；
  # uvicorn 有 exec 换来的真 PID 在 pidfile 里，按 PID 杀就够。
  # 本机 git-bash 没有 pgrep/pkill（实测）⇒ 这一层在 win 上是空转，只按 pidfile 走。
  if ! command -v pgrep >/dev/null 2>&1 || ! command -v pkill >/dev/null 2>&1; then
    echo "note: 本机没有 pgrep/pkill ⇒ 跳过命令行特征兜底（CI 的 ubuntu runner 有）"
  else
    for pat in "$REPO_ROOT/apps/web/node_modules/next/dist/bin/next" \
               "$REPO_ROOT/scripts/e2e/fake_llm.py" \
               "$REPO_ROOT/scripts/e2e/fake_langbot.py"; do
      if pgrep -f "$pat" >/dev/null 2>&1; then
        pkill -f "$pat" && { echo "pkill 兜底清掉：$pat"; stopped_any=1; }
      fi
    done
  fi
  # 端口终检只判"本脚本确实起过的那几个"：把别人的栈读成本脚本没清干净是误判
  # （--stop 或 --no-frontend 时，3200 上很可能是 compose 的前端，与我们无关）。
  # 为什么要有界地等：`kill` 是异步的——SIGTERM 发出去到内核释放监听端口之间有几十到几百毫秒，
  # 原来的终检紧跟在 kill 之后，把这段延迟读成"没清干净"（CI 实证：同一秒内先打
  # `stopped backend pid=3890` 再报端口红，而那进程确实是被本脚本杀的那个）。
  # 宽限期用尽仍占用才算红，并把占用者打出来——**仍然不静默放过**，只是不再把延迟当泄漏。
  for name in backend frontend fake_llm fake_langbot; do
    port=""
    case "$name" in
      backend) port=3300 ;;
      frontend) port=3200 ;;
      fake_llm) port=3290 ;;
      fake_langbot) port=3291 ;;
    esac
    printf '%s\n' "$started" | grep -qx "$name" || continue
    grace=0
    while port_open "$port"; do
      grace=$((grace + 1))
      if [ "$grace" -gt 30 ]; then
        echo "❌ 本脚本起过的 $name 还占着端口 $port（kill 后等满 6s 仍未释放，不静默放过）" >&2
        echo "   占用者读数：$(port_owner "$port")" >&2
        return 1
      fi
      sleep 0.2
    done
    if [ "$grace" -gt 0 ]; then
      echo "端口 $port 在第 ${grace} 次轮询（约 $((grace * 200))ms）后才空闲——SIGTERM 的释放延迟，不是泄漏"
    fi
    # 空闲时也把属主读一遍并落一行：STEP-67 验收 ② 要能事后证明"这段读数没被删"，
    # 只在红路径打印就等于"绿了就没有物证"——那正是本文件一直在反对的那类静默。
    ownp="$(port_owner "$port")"
    echo "端口终检 $name :$port 空闲；占用者读数：${ownp:-(空)}"
  done
  if [ "$stopped_any" != 1 ]; then
    # 这句以前固定写"pidfile 不存在"，可在 `already gone` 那条路径上 pidfile 明明存在 ⇒ 谎报。
    if [ "$had_pidfile" = 1 ]; then
      echo "本脚本记过的进程都不在了（pidfile 已删除）；端口占用与否只对起过的角色判"
    else
      echo "没有本脚本起过的进程（pidfile 不存在）"
    fi
  fi
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
# 把前端 rewrite 的目标钉死成同一个 3300（`next.config.mjs:9-16` 读 BACKEND_ORIGIN，
# 缺省值也是 http://localhost:3300）。显式设它不是改默认行为，是让"端口只有一个来源"：
# 上面那条端口检查用的 3300 与浏览器实际打的 3300 从此是同一个数，不会一处改了两处没改。
export BACKEND_ORIGIN="${BACKEND_ORIGIN:-http://127.0.0.1:3300}"
export AIDEAN_PUBLIC_URL="${AIDEAN_PUBLIC_URL:-$AIDEAN_ISSUER}"
# 注：`AIDEAN_PUBLIC_URL` 只被登录路由拿去拼 authorize 跳转（`app/api/v1/auth.py:63` 的
# `public_base_url=settings.aidean_public_url or None`，字段默认空串见 `config.py:31`），
# 而第⑥步那两个探针（/auth/me 与 /system/ready）都不走登录路由——所以它不在这条探针链上。
# 把它跟着 issuer 设，是为了让"这一档没有可用的外部登录"这件事在配置里也是显式的，
# 而不是靠留空偶然得到。
export APP_ENV="${APP_ENV:-development}"

# 只检查"这一次真的要用"的端口：以前 3200 无条件检查，于是 `--no-frontend`（说明写着
# "复用已有栈时用"）在同一条检查里就撞 rc=2 ——那条旗标永远不可能起到"复用"的作用。
ports_to_check="3300"
[ "$WITH_FAKE_LLM" = 1 ] && ports_to_check="3290 $ports_to_check"
[ "$WITH_FAKE_LANGBOT" = 1 ] && ports_to_check="3291 $ports_to_check"
[ "$NO_FRONTEND" = 1 ] || ports_to_check="3200 $ports_to_check"
for port in $ports_to_check; do
  if port_open "$port"; then
    echo "❌ 端口 $port 已被占用：本脚本不换口（D-V4-02），请先停掉占用者" >&2
    echo "   注意 --no-frontend 只是不起前端，后端(uvicorn)每次都新起一个 ⇒ 3300 仍要空闲；" \
         "要复用已在跑的整套栈就别跑本脚本，直接给 Playwright 备好 E2E_SEED_FILE" >&2
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

if [ "$WITH_FAKE_LANGBOT" = 1 ] && [ ! -f "$REPO_ROOT/scripts/e2e/fake_langbot.py" ]; then
  echo "❌ --with-fake-langbot 需要 scripts/e2e/fake_langbot.py（STEP-72 交付），该文件现在不存在" >&2
  exit 11
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

# ②b 假 LangBot：只在 uvicorn 之前 export LANGBOT_BASE_URL 才有意义——settings 在进程启动时读 env，
# 起完再 export 等于没设（`/system/health` 的 langbot 会继续指着缺省 :5300 报 unreachable）。
# 用户名口令用产品缺省即可：假服务不校验凭据（真实口径见 providers/langbot/client.py:52-68）。
if [ "$WITH_FAKE_LANGBOT" = 1 ]; then
  echo "== ②b 假 LangBot 上游 :3291 =="
  nohup sh -c "cd '$REPO_ROOT' && exec python scripts/e2e/fake_langbot.py --port 3291" \
    > "$RUN_DIR/fake_langbot.out" 2>&1 &
  FAKE_LANGBOT_PID=$!
  record_pid fake_langbot "$FAKE_LANGBOT_PID"
  export LANGBOT_BASE_URL="http://127.0.0.1:3291"
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
# `|| true` 是必须的：python 非零退出时它打的行照样有诊断价值，而直接跑在 `set -e` 下
# 会先让脚本死在 1（旧写法就是这样，rc=5 那条"seed 不是 3 条"的分支根本走不到，
# 日志里只剩一条 traceback）。真正的判定在下面按行数做。
(cd "$REPO_ROOT/apps/api" && python scripts/qa_seed_sessions.py) > "$SEED_FILE" 2>&1 || SEED_RC=$?
SEED_RC=${SEED_RC:-0}
# 统一去掉 CR：win 上跑这一步时 python 可能写 CRLF，而 `$(...)` 只剥尾换行不剥尾 CR，
# 于是第 ⑥ 步从行尾取到的 COOKIE_VALUE 会带一个 \r，curl 的请求头随之畸形——
# 那种红会被读成"S59.0 不成立 ⇒ 走方案 B"，实际是行尾。real.setup.ts 侧本来就按 /\r?\n/ 解析。
SEED_LF="$RUN_DIR/seed.lf.txt"
tr -d '\r' < "$SEED_FILE" > "$SEED_LF"
n_session=$(grep -c '^session ' "$SEED_LF" || true)
echo "seed 写入 $SEED_FILE：session 行 $n_session 条（应为 3），种子脚本 rc=$SEED_RC"
if [ "$n_session" != "3" ] || [ "$SEED_RC" != "0" ]; then
  echo "❌ 种子不合格（session 行 $n_session 条 / 脚本 rc=$SEED_RC）；seed 内容：" >&2
  cat "$SEED_LF" >&2
  exit 5
fi

echo "== ⑤b /chat 可检索种子（STEP-73：直写表是测试夹具，不是产品路径，D-V24-12）=="
# 为什么单独一棒：`chat.py:83-96` 的候选集合取自本空间的 `langbot_file_id`，集合为空时
# 假 LangBot 返回的那条会被整体过滤掉，`ask` 表现为"检索到了但上下文为空"。
SPACE_OUT="$RUN_DIR/seed_chat_space.out"
if [ ! -f "$REPO_ROOT/scripts/e2e/seed_chat_space.py" ]; then
  echo "❌ ⑤b 需要 scripts/e2e/seed_chat_space.py（STEP-73 交付），该文件现在不存在" >&2
  exit 12
fi
# 同 ⑤ 的写法：`|| SPACE_RC=$?` 让失败时的输出照样落进 SPACE_OUT，判定放在下面按字段做
# （直接跑在 `set -e` 下会先死在赋值那一行，日志里只剩 rc，没有脚本自己的诊断）。
(cd "$REPO_ROOT/apps/api" && python ../scripts/e2e/seed_chat_space.py) > "$SPACE_OUT" 2>&1 || SPACE_RC=$?
SPACE_RC=${SPACE_RC:-0}
sed 's/^/    /' "$SPACE_OUT"
# 尾 `\r` 一并剥掉：win 上 python 可能写 CRLF（理由同 ⑤ 的 SEED_LF 那段）。
SPACE_ID="$(sed -n 's/^space_id=\([0-9a-fA-F-]*\)\r\{0,1\}$/\1/p' "$SPACE_OUT" | tail -n 1)"
if [ "$SPACE_RC" != "0" ] || [ -z "$SPACE_ID" ]; then
  echo "❌ /chat 种子不合格（脚本 rc=$SPACE_RC、space_id 取到 '${SPACE_ID}'）；输出见上，不猜" >&2
  exit 12
fi
printf 'space %s\n' "$SPACE_ID" >> "$SEED_FILE"
echo "seed 追加：space $SPACE_ID → $SEED_FILE（real.setup.ts 只解析 ^session 行，多这一行不影响它）"

echo "== ⑥ S59.0 先验探针：主平台不可达时，admin 会话能不能进后台 =="
ADMIN_COOKIE_LINE="$(grep '^session qa-admin-001' "$SEED_LF" | tail -n 1)"
COOKIE_NAME="$(printf '%s' "$ADMIN_COOKIE_LINE" | sed -n 's/.*cookie=\([^ ]*\) value=.*/\1/p')"
COOKIE_VALUE="$(printf '%s' "$ADMIN_COOKIE_LINE" | sed -n 's/.* value=\(.*\)/\1/p')"
if [ -z "$COOKIE_NAME" ] || [ -z "$COOKIE_VALUE" ]; then
  echo "❌ 没能从 seed 行里解析出 cookie 名与值（不猜，停下）：$ADMIN_COOKIE_LINE" >&2
  exit 5
fi
ME_CURL_RC=0
ME_JSON="$(curl -fsS --max-time 10 -H "Cookie: $COOKIE_NAME=$COOKIE_VALUE" http://127.0.0.1:3300/api/v1/auth/me 2>/dev/null)" || ME_CURL_RC=$?
READY_CODE="$(curl -s -o "$RUN_DIR/ready.json" -w '%{http_code}' --max-time 10 http://127.0.0.1:3300/api/v1/system/ready || true)"
echo "probe: cookie=$COOKIE_NAME value_len=${#COOKIE_VALUE}"
echo "probe: GET /auth/me → curl_rc=$ME_CURL_RC body=$ME_JSON"
echo "probe: GET /system/ready → HTTP $READY_CODE body=$(cat "$RUN_DIR/ready.json" 2>/dev/null || echo '<无>')"

# rc=6 只该说"S59.0 这条前提不成立"，不该顺带把"curl 根本没跑成"也算进去——
# 否则一次 curl 缺失/超时会把结论指到方案 B，而真问题是这一棒的工具或端口。
if [ "$ME_CURL_RC" != 0 ]; then
  echo "❌ 探针没能取到 /auth/me 的响应（curl rc=$ME_CURL_RC）：这是工具或连通性问题，不判 S59.0 的结论" >&2
  exit 10
fi
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
# 直接 exec node 打 next 的 bin（绝对路径），而不是 `pnpm exec next start`：后者 PID 是 pnpm，
# 真监听者（node）是它的子进程 ⇒ pidfile 记的是包装进程，`--stop` 只 kill 得到包装进程，
# 服务还占在 3200 上而日志照样打印 "stopped frontend"。绝对路径同时给 stop_all 的
# 特征兜底当一个"只属于本 checkout"的匹配锚。
nohup sh -c "cd '$REPO_ROOT/apps/web' && exec node '$REPO_ROOT/apps/web/node_modules/next/dist/bin/next' start -p 3200" \
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
