# BotHot 剩余任务规划 V0.12.0（基线 main@3a67e96）

> 项目：AideanBotHot｜仓库 `https://github.com/aideanew/BotHot` 分支 main｜端口段 3200-3300（前端 3200 / 后端 3300）
> 规划日期：2026-10-15｜上一版 V0.11.0（第二增量基线 17c5d28）｜本版是它的增量：30 张卡随件继承（编号不复用、不重排），新增 1 张。
> 开工前 `git fetch` + `git merge --ff-only`；先验入站文件与在途脏文件 0 交集再快进。

## 0. 一句话结论

**主干看上去已经"双绿"，其实不是：Security 最近两次 success，但 CI 工作流最近 10 次结论全部是 `cancelled`。** ubuntu 五个 job 每次都绿，唯独 `windows-dev` 的全量 pytest 每次跑满 35 分钟被超时取消，整个工作流的结论就跟着变成 cancelled。任何只看工作流结论的人都会读成"CI 没跑完"，而不是"Ubuntu 绿、Windows 断"。（证据 `evidence/3a67e96/workflow_runs_main.json`、`ci_run_38707720244_jobs.json`）

**卡死的根因已基本定位，而且它同时是一个生产缺陷。** `app/main.py:281` 在 import 期执行 `app = create_app()`，后者在 `_assert_schema_current` 里同步 `asyncio.run()` 连库探测，而探测引擎（`app/db.py:53-59`）没有 `connect_timeout`。Linux 上本地拒连会立即返回，所以 CI ubuntu 不受影响；Windows 对拒连要约 2 秒，再加上 psycopg 只在 Selector 事件循环下才真正发起连接（conftest.py:26 正好设了它），于是 pytest 一 import 到 `app.main` 就变得极慢甚至挂住。我在 Linux 上把 `DATABASE_URL` 指向一个黑洞地址，`import app.main` 直接挂满 25 秒（rc=124）：**生产机只要启动时数据库所在网络丢包而不是拒连，uvicorn 就会在 import 期无限挂起。**（证据 `evidence/3a67e96/win_stall_rootcause_probe.txt`）

**因此本版只新增一张 P0 卡 STEP-00W**：给启动探测加超时、把 windows-dev 拆成独立工作流（让 CI 结论只反映正式验收面）、在 Windows job 加逐用例超时与 faulthandler 取栈，用 @win 栈闭合根因。其余 30 张卡继承，状态按 3a67e96 的真实代码与读数刷新。

**本版核实后的进度**：@linux 连库全量 **1058 passed / 5 skipped / 0 failed，覆盖率 79%，77.36 秒**；Security 回绿（00S 完成）；管理端运维四屏已上线（14b 大部分完成）；Win10 工具链与入口跨平台化完成一半（00X）。**采集域主线（01→02→04→07，P-1/P-2/P-3）仍一行没动**，这是剩余工作中真正的核心。

## 1. 本版相对 V0.11.0 的变化

| # | 变化 | 证据 |
|---|---|---|
| 1 | 基线 17c5d28 → **3a67e96**，其间 13 个提交：00X（entry.py/guards.py/windows-dev job）、00S（Security 回绿）、15 S15.2.3（admin-ops typed 客户端）、14b（`/admin/ops` 四屏） | `git log 17c5d28..3a67e96` |
| 2 | **CI 工作流最近 10 次全部 `cancelled`**；同一批 run 中 ubuntu 五个 job（backend / frontend / compose / compose-smoke / workflow-lint）全部 success，windows-dev 在「Backend tests」步被取消 | evidence/3a67e96/*.json |
| 3 | **U-20 根因定位**：import 期同步连库探测无超时；@linux 黑洞地址复现挂死；与 @win 读数（拒连 2.05s、alembic 挂 150s、裸 import 快、pytest 采集慢）逐条吻合 | win_stall_rootcause_probe.txt |
| 4 | 新增 **STEP-00W**（8 个三级任务 / 1.0 人日 / opus / 规划方执行） | steps/STEP-00W-*.md |
| 5 | 新增裁决 **D-V7-01～D-V7-03**（按用户授权代选，见 03 §1） | 03 |
| 6 | 纠正历史口径「管理端 6 组接口无前端消费」：push、ops/liveness、discovery/channels、engines/keys **4 组已被 `lib/api/admin-ops.ts` 消费**；backchannel-logout 是 IdP→本服务的服务间回调，**按设计不需要前端**；`admin/alerts` **后端并无此路由**（告警状态只在 `/system` 就绪聚合里以 `alerting: enabled/disabled` 出现） | 01 F-07 |
| 7 | @linux 读数首次与 CI ubuntu 对齐：1058/5/0、79%、收集 1063 条 1.23s（@win 同一收集 262.65s） | pytest_linux_3a67e96.txt |
| 8 | 规模：**31 卡 / 200 三级任务 / 30.75 人日**（继承 30 卡 192/29.75 + 00W 8/1.0）；剩余数逐卡见 04 §2 | 04 §2.1 复算脚本 |

## 2. 阅读顺序
1. `01-事实基线与进度.md`：快照 + 已确认事实 + 文档与代码不一致清单
2. `02-需求拆解与辩证分析.md`：需求复核、5W1H、钢人论证
3. `03-裁决与契约.md`：新裁决 + 六份契约（`contracts/`，唯一源规则不变）
4. `04-剩余可执行大纲体系.md`：31 卡总表、DAG、所有权矩阵、档位与预算
5. `steps/STEP-00W-*.md`：本版唯一新卡；其余卡为 V0.11.0 随件继承，**卡内"执行记录"截至 17c5d28 之后的 13 个提交**，状态以 04 §2 为准
6. `05-风险自检与局限.md`、`06-入库与双端一致.md`、`07-执行过程记录.md`

## 3. 规划方（本 Agent）与执行 Agent 分工
- **规划方自执行（核心 + 高难度 + UI）**：00W（P0 根因）、01（采集域契约冻结）、13（引擎能力面）、14a（管理端后端聚合）、14b 余项（通用表 S14b.2.1、告警横幅 S14b.2.3）、15 余项。
- **执行 Agent（中等/简单）**：00X 余项、00E、RV、00T、00R、17、02、03、04、05、06、07、08、09、10、11、12、18、19、00G/00P 余项。
- 判定一律由独立验证者看 diff + 运行结果，只出 PASS / FAIL / UNKNOWN（继承 V0.11.0 07 §4 的规则）。
