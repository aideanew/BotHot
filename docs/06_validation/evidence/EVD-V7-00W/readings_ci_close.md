# @ci 收口读数（STEP-00W 验收判据逐条对齐）

取证时刻：2026-10-15 18:15–18:30（本地）／10:02–10:27Z（Actions）。原始响应逐字存本目录：
`runs_latest_at_close.json`、`jobs_ci_e7e9f25.json`、`jobs_ciwin_593dc5b_final.json`、
`jobs_ciwin_e7e9f25_final.json`、`ciwin_e7e9f25_timeout_stack.txt`。
读法：`GET /repos/aideanew/BotHot/actions/runs`、`GET /actions/runs/{id}/jobs`、
`GET /actions/jobs/{job_id}/logs`（日志里 Actions 自身已把 token 打成 `***`，无凭据入档）。

## 1. 三个工作流的最终结论（head_sha `e7e9f25`）

| 工作流 | run id | job | conclusion | 起讫 | 关键读数 |
|---|---|---|---|---|---|
| `CI` | 38717913012 | workflow-lint / backend / frontend / compose / compose-smoke | **success**（五 job 全绿） | — | backend：`1058 passed, 6 skipped, 1 warning in 52.43s`；skip 门禁 `total_skipped=6 baseline=6 pg_unreachable=0` |
| `Security` | 38717912870 | — | **success** | — | 00W 未把安全面碰红 |
| `CI-Windows` | 38717912956 | windows-dev（job id 116365008740） | **failure**（不是 cancelled） | 10:06:45Z → 10:27:07Z（20m22s） | `--timeout=300` 命中并带全线程栈；此前 10:14:15 / 10:18:45 / 10:24:03 三次 `Timeout (0:02:00)!` dump；`Successfully installed ... pytest-timeout-2.4.0 ...` |

上一提交 `593dc5b` 的同一形态：`CI` success（run 38717350352）、`CI-Windows` **failure**
（run 38717350410，10:02:12Z → 10:22:28Z，20m16s）。⇒ "failure 而非 cancelled" 在两个提交上各测到一次，
不是单点运气。

## 1.1 补证：00W 前后的同一 ubuntu job，与"cancelled → failure+栈"的对照

第二轮独立验证者指出"passed 数无产物"，为此把**对照分母**也取回落档
（`ci_backend_log_2940a6f_excerpt.txt` / `ci_backend_log_e7e9f25_excerpt.txt`）：

| 提交 | backend job | 汇总行 | SKIPPED 明细 | windows-dev |
|---|---|---|---|---|
| `2940a6f`（新用例尚不存在，`CI` 工作流里还含 windows-dev） | 116350907193 success | `1057 passed, 6 skipped, 1 warning in 80.11s` | 6 条：chat_sse×2 / env_isolation×1 / session_store_redis×2 / we_notifications×1 | **cancelled**（09:32:06Z → 10:07:20Z，撞 35min 上限） |
| `e7e9f25`（含新用例） | 116365009382 success | `1058 passed, 6 skipped, 1 warning in 52.43s` | 与上一行**逐字相同的 6 条** | 不存在于 `CI`（已拆出），在 `CI-Windows` = failure+栈 |

⇒ 三条结论都有产物：
1. **净增 1 个 pass、0 个 skip** ⇒ 新用例 `test_startup_probe_timeout.py` 在 ubuntu-latest 上是
   **真跑且 passed**（不是靠 skip 蒙过门禁）；`-q` 不打印用例名，所以这条只能靠差分推，
   两份明细都存了，谁都能复核。
2. **判据 5** 的 `≥1058 / failed=0` 由 `1058 passed …` + `pytest_status=0 gate_status=0` 直接支持。
3. **D-V7-01/02 的因果**第一次有了同机对照：拆分前同一 run 里 windows-dev 是 `cancelled`
   （35min 到点被杀，结论被遮蔽），拆分并加逐用例超时后是 `failure`（20min 内自己退出、带栈）。
   `pytest-timeout` 字符串在 `2940a6f` 日志里出现 **0** 次、在 `e7e9f25` 里 **3** 次 ⇒ 依赖确实生效。

## 2. 判据映射（卡面"验收标准"六条）

| # | 判据 | 状态 | 依据 |
|---|---|---|---|
| 1 | `@linux` 黑洞 `import app.main` rc=0 且 < 5s | **部分确认**（无手跑 @linux；推断现在有产物） | 本机 `docker` 不在 PATH，拿不到手跑面。同族读数已入库：`ci_backend_log_2940a6f_excerpt.txt` = **1057 passed, 6 skipped**（新用例尚不存在）vs `ci_backend_log_e7e9f25_excerpt.txt` = **1058 passed, 6 skipped**，且**两份的 6 条 SKIPPED 明细逐字相同**（chat_sse×2 / env_isolation×1 / session_store_redis×2 / we_notifications×1，无一条是本用例）⇒ 净增 1 pass、0 skip ⇒ 新用例在 ubuntu-latest 上是 **passed 而非 skip**。`@win` 侧子进程自报 4.50–4.58s |
| 2 | 新用例在 3a67e96 上红、本卡提交上绿 | **已确认** | 红：`red_prefix_blackhole_selector.txt`（在 `2940a6f` 的分离 worktree 里跑，`git diff --stat 3a67e96 2940a6f -- apps/api/app/main.py apps/api/app/db.py` 为空 ⇒ 这份代码就是 3a67e96 的代码）；绿：`1 passed in 7.00s`（@win）+ ubuntu backend 1058 passed |
| 3 | `CI` 结论 = success 且原始响应存证 | **已确认** | 上表第一行 + `jobs_ci_e7e9f25.json` |
| 4 | `CI-Windows` = success；若失败必须是 failure + faulthandler 栈、不得 cancelled | **按卡面"若仍失败"分支达成**（failure + 栈，两个提交各一次） | `ciwin_e7e9f25_timeout_stack.txt`。**取证面分级**：`runs_latest_at_close.json` 抓取时 CI-Windows 仍是 run 级 `in_progress/conclusion=null`（该文件表头是我手写的说明行，不是 API 字段），"failure 而非 cancelled"的证据在 **job 级** JSON（`jobs_ciwin_593dc5b_final.json` / `jobs_ciwin_e7e9f25_final.json`，两者 conclusion 均为 `failure`、completed_at 相隔 5 分钟、非同一份）。卡面"目标"句还要求"并最终 success" ⇒ **未达成**，转 U-23 |
| 5 | ubuntu backend passed ≥ 1058、failed = 0 | **已确认（有产物）** | `ci_backend_log_e7e9f25_excerpt.txt` 汇总行 `1058 passed, 6 skipped, 1 warning in 52.43s` + `skip 门禁：total_skipped=6 baseline=6 pg_unreachable=0` + `pytest_status=0 gate_status=0`。第一版我把这些数字写在文档里、日志只留在未入库的 `.staging/` ⇒ 被第二轮验证者判为 overclaim，现补件并把对照分母（1057 passed）也存了 |
| 6 | `git diff --stat` 只含"输出"一节列出的文件 | **593dc5b 达成 / e7e9f25 越界** | e7e9f25 另改 `docs/任务规划V0.12.0/08-…`、`05-…`（用户指令要求的执行过程记录，不在卡面允许清单）；详见 `handoff_next_card.md` |

## 3. 卡死点已经不是启动探测（U-23 的硬线索）

300s 命中块的栈形如：

```
Stack of asyncio-portal-… : anyio/from_thread.py:538 run_blocking_portal → … →
    selectors.py:315 _select
主线程：starlette/testclient.py:351 handle_request → anyio/from_thread.py:340 call
    → concurrent/futures/_base.py:451 result → self._condition.wait(timeout)
Captured stdout: HTTP Request: GET http://testserver/api/v1/system/health "HTTP/1.1 200 OK"
```

⇒ 卡在 **同步 `TestClient` 发一次请求、等 anyio blocking portal 的 Future**，
portal 所在 loop 停在 `selectors._select`；与被修的 import 期连库探测**不同源**
（那条已由 `--timeout` 之外单独证明：本用例在 windows 侧也进了 20% 之后的进度）。
所以 00W 修的是"import 期无界挂起"，Windows 全量慢是**另一个**缺陷，落在 U-23：
下一步用 `-v`/`--timeout=60 -k` 二分定位到具体用例或 fixture，怀疑面 = TestClient 的
portal 与 Windows Selector 循环的交互，而不是 psycopg。
