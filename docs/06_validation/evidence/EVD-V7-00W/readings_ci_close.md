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

## 2. 判据映射（卡面"验收标准"六条）

| # | 判据 | 状态 | 依据 |
|---|---|---|---|
| 1 | `@linux` 黑洞 `import app.main` rc=0 且 < 5s | **部分确认**（无手跑 @linux） | 本机无 docker（`docker: command not found`），拿不到 @linux 手跑面。同族读数：`@ci` ubuntu runner 的 backend job 里本用例算进 1058 passed（不在 6 条 SKIPPED 名单内）⇒ 黑洞地址在真 Linux runner 上确实是黑洞、探测确实在上界内返回；`@win` 侧子进程自报 4.50–4.58s |
| 2 | 新用例在 3a67e96 上红、本卡提交上绿 | **已确认** | 红：`red_prefix_blackhole_selector.txt`（在 `2940a6f` 的分离 worktree 里跑，`git diff --stat 3a67e96 2940a6f -- apps/api/app/main.py apps/api/app/db.py` 为空 ⇒ 这份代码就是 3a67e96 的代码）；绿：`1 passed in 7.00s`（@win）+ ubuntu backend 1058 passed |
| 3 | `CI` 结论 = success 且原始响应存证 | **已确认** | 上表第一行 + `jobs_ci_e7e9f25.json` |
| 4 | `CI-Windows` = success；若失败必须是 failure + faulthandler 栈、不得 cancelled | **按卡面"若仍失败"分支达成**（failure + 栈，两个提交各一次） | `ciwin_e7e9f25_timeout_stack.txt`。卡面"目标"句还要求"并最终 success" ⇒ **未达成**，转 U-23 |
| 5 | ubuntu backend passed ≥ 1058、failed = 0 | **已确认** | `1058 passed, 6 skipped`，日志 10:08:37Z |
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
