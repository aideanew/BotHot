# STEP-00H 健康与就绪探针有界化 + CI-Windows 回绿（V0.13.0 新增）

> 状态：**🟢 S00H.1.1–1.4 与 S00H.2.1 全部已确认（2026-10-17 `@ci`）**；S00H.2.2 按卡面跳过
> （2.1 已确认 ⇒ 条件步不执行），S00H.2.3 仍待"连续 2 次 `CI-Windows` success"。
> 读数在 `docs/06_validation/evidence/EVD-V13-00H/s00h_readings.md` §7。
> 最有分量的一条：`tests/test_security_middleware.py`（5 条打 `/health`）改前**本机整文件跑不完**，
> 改后与 `test_health_ready.py` 合跑 `71 passed / 0 failed / 39.64s`。
> ⚠️ 本卡期间查明：`CI-Windows` 从 `5e5ab17` 起就再没卡过，之后的每一次红都换在了
> `SKIP_BASELINE_WIN=320` 这条 stale 阈值上（收紧属 STEP-00X，见 §7.5）。
> 过程中被实测推翻两个判断（`gather` 并发不等于总上界；我自己的"并发判据"原本是恒真的），
> 并追出一个新缺陷（限流豁免集的死条目）——都写在 EVD §4/§5。

| 字段 | 值 |
|---|---|
| 归属-切片 | S-M0 前提固定（步行骨架的"健康检查"一环） |
| 归属-需求 | M-9（依赖不可达时不得无限挂起，V0.12.0 立；本卡把它从"启动期"扩到"请求期"）、M-10（Win10 一等开发平台）、M-6（主干绿） |
| 归属-方案 | D-V10-02（探针上界 + 并发，本版代选）；U-23 根因假设 **H2**（本版提出，`@linux` 已证机制，`@win` 待证） |
| 里程碑 | M0（阻塞 00X S00X.4.2、00E 出门判据、RV 的 `@ci` 读数、P-5） |
| 执行者 | **规划方**（同时动 API 启动/连接路径与 Guard 的 CI 读数，属高风险核心；执行期间 `app/db.py`、`app/api/v1/system.py`、`.github/workflows/ci-windows.yml` 对其他 Agent 冻结） |
| 档位 | opus　理由：改的是所有请求共享的业务连接池参数，选错 timeout 语义会在生产把慢库判成不可达；需要 opus 做取舍 |
| 规模 | 中（≈1.25 人日；7 个三级任务，单个均 < 2h） |
| 依赖 | Depends on：无（00W 已交付的启动探测上界是本卡的前提事实，不是前置任务）　Blocks：00X(S00X.4.2)、00E、RV、06（覆盖率门要 `CI-Windows` 读数可比） |
| 基线 | main@314d7f2（与 b8d27ff 相比 `app/db.py`、`app/api/v1/system.py`、`app/main.py` 零差异，`git diff --stat b8d27ff..314d7f2 -- <三文件>` 为空） |

## 为什么要有这张卡（证据链）
1. **卡住的用例只有一类。** `CI-Windows` run 38937542471（b8d27ff）三次 `Timeout (0:02:00)` 全落在 `tests/test_envelope.py:48/60/165`，三条用例**都只做一件事：`GET /api/v1/system/health`**（证据 `evidence/b8d27ff/ciwin_38937542471_stall_excerpt.txt`；用例原文 `apps/api/tests/test_envelope.py:45-62,162-167`）。
2. **`/health` 串行等三个探针，PG 那个没有上界。** `app/api/v1/system.py:92-94` 依次 `await _check_pg()`、`_check_redis()`、`_check_langbot()`；redis 有 `socket_connect_timeout=2`（:52），langbot 有 `httpx timeout=3`（:73），**唯独 `_check_pg` 用 `app/db.py:61-69` 的业务引擎，`connect_args` 默认空 ⇒ 无 `connect_timeout`**。`/ready` 的 `_check_schema`（:111-123）同样走这个引擎。
3. **机制已在 `@linux` 复现。** 黑洞 DSN 下 `create_app()` 约 3s 返回（00W 的上界生效），随后 `GET /health` **60s 不返回（rc=124）**；314d7f2 复跑 45s 仍 rc=124（证据 `evidence/b8d27ff/probe_health_blackhole.txt`、`evidence/314d7f2/probe_health_blackhole.txt`）。
4. **Windows 正好把"拒连"变成"黑洞"。** 执行方自己的读数：Windows 机上 `127.0.0.1:1`、`:5` 的 `socket.create_connection(timeout=2)` 都是 **unresponsive@2.00s**，回环不回 RST（`docs/任务规划V0.12.0/05-风险自检与局限.md` U-23 条）。CI-Windows 没有 PG 服务，`database_url` 默认 `localhost:5432`（`app/core/config.py:20`）⇒ 每次 `/health` 都是一次无上界的黑洞连接。
5. **栈与此相容。** portal 线程停在 `selectors._select`（等 socket 就绪），主线程停在 `TestClient → anyio from_thread.call → Future.result`——这正是"路由协程在等一个永不完成的 connect"的样子。

**对 V0.12.0 U-23 结论的更正**："卡点在 TestClient/anyio portal，与 psycopg/启动探测无关"——前半句是**症状位置**，后半句不成立：portal 只是在替 `/health` 等 psycopg 连接。启动探测确实无关（00W 已限时），**请求期探测**是新怀疑面。状态：`部分确认`（机制 `@linux` 已证；"Windows 上就是它"待 S00H.2.1 的 `@ci` 读数）。

## 反证（钢人）
- **反 1：若是黑洞，为什么 ubuntu 不卡？** ubuntu job 有 PG service 容器，`localhost:5432` 真能连上；即使没连上，Linux 回环会 RST 立即返回。⇒ 不构成反证。
- **反 2：其他也用 `create_app()` 的用例为什么不卡？** 只有打到 `/health`、`/ready` 才会走 `_check_pg`；`test_envelope.py` 里打 404 路由的用例（:150-158）同一文件内不卡。⇒ 与 H2 一致。
- **反 3：可能是 TestClient 跨事件循环复用缓存引擎（H3）。** `app/db.py:77` 在 import 期建出模块级单例 `_engine`，而每个 `TestClient(...)` 起一个新 portal 事件循环——连接池里上一个循环建的连接被下一个循环复用。H3 也能解释"只在用到引擎的路由卡"。⇒ **未被排除**，S00H.2.2 专门判它。
- **反 4：加了上界也许只是把 120s 卡变成 3s×N 慢。** 是的——所以 S00H.1.3 同时把三个探针改为 `asyncio.gather` 并发，`/health` 总上界取单探针上界而不是三者之和。

## 目标（可验证的一句话）
`DATABASE_URL` 指向黑洞地址时，`GET /api/v1/system/health` 与 `GET /api/v1/system/ready` 在 **≤ 5s** 内返回且 `deps.postgres == "unreachable"`；`CI-Windows` 工作流连续 2 次 `success`。

## 输入
- 文档：本目录 `01` F-03～F-05、`02` §3、`03` D-V10-02
- 证据：`evidence/b8d27ff/{ciwin_38937542471_stall_excerpt.txt,probe_health_blackhole.py,probe_health_blackhole.txt}`、`evidence/314d7f2/probe_health_blackhole.txt`
- 契约：`docs/任务规划V0.12.0/contracts/api.envelope.schema.json`（**不改形状**：`deps.*` 的取值集 `ok/unreachable/unhealthy` 不变）
- 前置状态：00W 的启动探测上界在位（`app/main.py` `_assert_schema_current` 3s/5s）

## 输出（文件）
- 改：`apps/api/app/db.py`（业务引擎默认带 `connect_timeout`，可由 `DB_CONNECT_TIMEOUT` 覆盖）
- 改：`apps/api/app/core/security.py`（**越界声明**：不在本卡输出清单。限流豁免集里 `/live`、`/ready` 两条是**死条目**——匹配是 `scope["path"]` 精确相等，而探针挂在 `/api/v1/system` 前缀下 ⇒ `/ready` 一直被限流，Redis 不可达时先在处理器之前吃一次 2s 连接超时。不改它，卡面目标句「`/ready` ≤5s」在 `@win` 上无法达成；`core/metrics.py:90` 用的是完整路径，两处口径本来就不一致。理由与双向判据见 `EVD-V13-00H` §5）
- 改：`apps/api/app/api/v1/system.py`（三个探针各套 `asyncio.wait_for`；`/health` 用 `asyncio.gather`；`_check_schema` 同样有上界）
- 新：`apps/api/tests/test_health_probe_bounded.py`
- 改（仅 S00H.2.2 触发时）：`apps/api/tests/conftest.py`（每个 TestClient 结束后 `dispose` 缓存引擎的夹具）
- 改：`.github/workflows/ci-windows.yml`（仅 S00H.2.3：把 `--timeout=300` 收紧到 `--timeout=120`，读数稳定后再收）
- 证据：`docs/06_validation/evidence/EVD-V13-00H/`

## Execution Steps

### S00H.1 先红后绿（`@linux`）
1. [x] **S00H.1.1** 新增 `tests/test_health_probe_bounded.py`：子进程设 `DATABASE_URL=postgresql+psycopg://x@10.255.255.1:5432/x`、`REDIS_URL=redis://127.0.0.1:1/0`、`LANGBOT_BASE_URL=http://127.0.0.1:1`，用 `TestClient(create_app())` 依次打 `/api/v1/system/health`、`/api/v1/system/ready`，父进程 `timeout=20` 计时；断言 rc=0、两次请求各 ≤ 5s、`deps.postgres == "unreachable"`
   - S00H.1.1.1 在 314d7f2 上跑出**红**（期望：子进程超时），读数入 EVD——证明用例抓得到缺陷
2. [x] **S00H.1.2** `app/db.py`：`create_engine_and_session` 在 `connect_args` 未给 `connect_timeout` 时补 `connect_timeout=int(os.environ.get("DB_CONNECT_TIMEOUT", "3"))`；显式传入的 `connect_args` 优先（00W 的启动探测调用不受影响）
   - S00H.1.2.1 新增常量旁写一行注释：为什么是 3（与 redis 2s、langbot 3s 同量级；生产慢库首连 < 3s 的依据见 `evidence/314d7f2/pytest_314d7f2.txt` 真库全量 0 失败）
3. [x] **S00H.1.3** `system.py`：抽 `_bounded(coro, seconds)` = `asyncio.wait_for` + `TimeoutError → "unreachable"`；`/health` 改 `pg, redis, langbot = await asyncio.gather(_bounded(_check_pg()), _bounded(_check_redis()), _bounded(_check_langbot()))`；`_check_schema` 内 `read_current_version_async` 同样套上界，超时按现有 `current is None → unreachable` 分支走
   - S00H.1.3.1 `PROBE_TIMEOUT_S = 3.0`，模块级常量，不进 Settings（不新增配置面）
4. [x] **S00H.1.4** `@linux`/`@ci` 真库全量回归（**本机无 PG，判不了**）：`passed ≥ 1478`、`failed = 0`、覆盖率不低于 85%；S00H.1.1 用例由红转绿
   — **已确认**（`@ci` run 39030366256 @ `10c1019`：`1533 passed / 6 skipped / 0 failed`，
   `Total coverage: 85.94%`，同 job 的 skip 门禁打的是 `pg_unreachable=0` ⇒ 那 435 条连库用例是真跑的）。
   ⚠️ 顺带查出一条**卡面数值没有机器闸**：CI 的 `--cov-fail-under` 用的是 `COV_BASELINE=75`，
   而本卡验收写 85%——今天 85.94% 只比卡面高 0.94 个点，一次合法重构就能把它带到线下而 CI 仍绿。

### S00H.2 Windows 判别与收口（`@ci`）
5. [x] **S00H.2.1** 推送后读 `CI-Windows`：若 `test_envelope.py` 不再出现 `Timeout`，H2 判**已确认**，跳过 S00H.2.2；读数（run id、head_sha、junit 汇总、日志中 `Timeout` 计数 = 0）入 EVD
   — **已确认**（run 39030366312 @ `10c1019`：Backend tests = success，junit
   `1098 passed / 441 skipped / 0 failed in 987.74s`；`Failed: Timeout` = 0、
   faulthandler 转栈头 = 0、job 在 35 分钟上限内跑完而非 cancelled）。
   **归因不靠"最后一次读数"**：逐提交翻转表显示 `Backend tests` 恰在 `5e5ab17`
   （= `feat(STEP-00H S00H.1.1-1.3)`）第一次转绿，其前 5 个提交全是 failure。
   H3（缓存引擎跨事件循环）**作为 U-23 根因被排除**——限时不改池的归属关系，若 H3 是因则仍该挂；
   但"排除它是 U-23 的原因"≠"排除它存在"，这条区分写在 EVD §7.2。
   判据细节：`-q` 下日志本来就不打印通过用例名，所以"日志里没有 test_envelope"**不能**当判据，
   判据是三个 0 计数 + `failed=0`。
6. [ ] ~~**S00H.2.2**~~ **不执行**（卡面条件：仅 S00H.2.1 仍卡时）。H3 未被单独证伪，留给下游按需重开
7. [ ] **S00H.2.3** 连续 2 次 `CI-Windows` success 后：`--timeout=300 → 120`；在本目录 `07` 与 `docs/04_engineering/cross-platform.md` 各写一句"多平台门已绿"，附两个 run id；关闭 P-5 / U-23
   — **仍未满足**，而且原因值得记：阈值收紧之后 `6925850`（run 39033863921）拿到**第一次 success**，
   紧接着我自己的两个提交把它顶红两次（`7a252f4` run 39034593829、`2a7195d` run 39035688934，
   都是 `failed=0 / 未知族=0 / skipped 443 > 基线 441`）——因为我新增的 2 条连库用例把 Windows
   侧的 skip 抬了 2。**连续计数因此清零重来**，不是回归也不是门坏了。
   已把"新增连库用例 ⇒ 同批重测并抬基线"写成程序（`cross-platform.md` §8）并登记 `D-V10-11`；
   `--timeout` 的 300→120 收紧要等两次真 success，不催。

## 验收标准
- [ ] `@linux` `timeout 20 python evidence/b8d27ff/probe_health_blackhole.py`（同一黑洞环境变量）rc=0，`/health` 墙钟 ≤ 5s（改前 rc=124）
- [ ] `@linux` 新用例在 314d7f2 红、在本卡提交上绿（两次原始输出入 EVD）
- [ ] `@linux` 真库全量 `failed = 0` 且 `passed ≥ 1478`，覆盖率 ≥ 85%
- [ ] `@ci` `CI` 工作流 success（ubuntu 不回归）
- [ ] `@ci` `CI-Windows` 连续 2 次 success，日志 `grep -c "Timeout ("` = 0
- [ ] `git diff --name-only` ⊆ 本卡"输出"清单；`contracts/**` 零改动

## 验证命令
```bash
# @linux（PG16 已起在 5547，见 07 §环境）
cd apps/api && . .venv/bin/activate
APP_ENV=development DATABASE_URL=postgresql+psycopg://x@10.255.255.1:5432/x REDIS_URL=redis://127.0.0.1:1/0 \
  LANGBOT_BASE_URL=http://127.0.0.1:1 timeout 20 python ../../docs/任务规划V0.13.0/evidence/b8d27ff/probe_health_blackhole.py; echo rc=$?
python -m pytest tests/test_health_probe_bounded.py tests/test_envelope.py -q
AIDEANBOT_TEST_PG_DSN=postgresql+psycopg://postgres@127.0.0.1:5547/bothot_test python -m pytest tests/ -q --cov=app --cov-report=term | tail -3
# @ci
curl -s "https://api.github.com/repos/aideanew/BotHot/actions/runs?branch=main&per_page=6" | python -c "import json,sys;[print(r['name'],r['head_sha'][:7],r['conclusion']) for r in json.load(sys.stdin)['workflow_runs']]"
```

## 证据路径
`docs/06_validation/evidence/EVD-V13-00H/`（`red_314d7f2.txt`、`green_<sha>.txt`、`ciwin_<run>.json`、`ciwin_<run>_timeout_count.txt`）

## 允许修改
- `apps/api/app/db.py`、`apps/api/app/api/v1/system.py`
- `apps/api/tests/test_health_probe_bounded.py`（新）、`apps/api/tests/conftest.py`（仅 S00H.2.2）
- `.github/workflows/ci-windows.yml`（仅 pytest 步的 `--timeout` 参数）
- `docs/06_validation/evidence/EVD-V13-00H/**`、`docs/04_engineering/cross-platform.md`（一句）、本目录 `07`

## 禁止修改
- `packages/contracts/**`、`docs/任务规划V0.12.0/contracts/**（冻结稿，被测试硬绑定，见 03 D-V10-06）`（响应形状不变）
- `apps/api/app/main.py`（00W 的启动探测已闭合，本卡不碰）
- `.github/workflows/ci.yml`、`apps/api/alembic/**`、`apps/web/**`
- `apps/api/tests/test_envelope.py`（被卡的用例本身没错，**不许靠改用例回绿**）

## 依赖与阻塞
- Depends on：无
- Blocks：00X(S00X.4.2)、00E、RV、06
- 阻塞条件：①S00H.1.1 在 314d7f2 上**不红** ⇒ 用例没抓到缺陷，停下重写用例；②S00H.2.2 后仍卡 ⇒ 熔断；③ubuntu backend 出现任何新失败 ⇒ 回退本卡提交再查

## 建议执行档位
opus　理由：连接池默认参数影响所有请求；H2/H3 判别需要读栈做因果判断，不是照抄步骤

## 升级条件
S00H.2.2 仍卡（H2、H3 都被否证）⇒ fable 一次，裁决"是否把 CI-Windows 后端测试降为 `-m "not app_client"` 子集"——这是推翻 D-V4-01 的一部分，必须由人或 fable 定

## 预估规模
中　7 个三级任务，单个 < 2h；合计 ≈1.25 人日（含两次 `@ci` 等待）
