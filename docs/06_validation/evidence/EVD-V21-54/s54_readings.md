# EVD-V21-54 测试库连跑确定性（P-120 收口）

平台 @win（Windows 10 x64，便携 PG16.15@5547 的 `bothot_test`，**跨会话持久库**），
开工 head `92af50a`（STEP-52 收口批；其交付头 `0aa2923` 三绿，
CI 40263352699 / CI-Windows 40263352628 / Security 40263352616）。
时间 2026-10-26（Asia/Shanghai）。开工同步：`git fetch` 后 `HEAD...origin/main` = `0 0`，工作树干净。

## 第 0 步读数

规划方与执行侧最近一次三绿是 STEP-52 交付头；本卡开工时收口批 `92af50a` 随后也三条全绿
（CI 40266355969 / CI-Windows 40266355961 / Security 40266355987，均 attempt 1）
——开工那一刻 CI-Windows 还在 in_progress，读数取于其后，如实标注先后。
卡面基线写的是 `main@bfd6d82`（规划时点），开工现读已是 `92af50a`——差的是 47 收口、52 交付与 52 收口三个批，
本卡允许面（`apps/api/tests/test_scheduler.py` 一条用例 + 它的辅助函数）在这三个批里**一行没被动过**：
`git log --oneline v1.1.2..HEAD -- apps/api/tests/test_scheduler.py` 零命中 ⇒ 卡面前提仍然成立。

## S54.1 先红（原文 `s54_1_round1_red.txt`、`s54_1_round2_red.txt`，判读 `s54_1_red_readings.md`）

同一持久库连跑两次 `pytest tests/test_scheduler.py -q`（连跑之间不重建库、不手工删行）：

| 轮 | rc | 读数 |
|---|---|---|
| 1 | 1 | `1 failed, 24 passed in 12.51s` |
| 2 | 1 | 同上逐字同形（⇒ 稳定红，不是时序抖动） |

红因两轮同一条：`psycopg.errors.UniqueViolation: duplicate key value violates unique constraint "users_pkey"`，
明细就是本用例自己写死的夹具主键。**与卡面"第二次红"相比本机更严重**：首跑即红——这张库已被
STEP-49/50/51/52 四个会话的全量跑用过，残留至少跨了 4 次会话（P-120 原文说的是"第二次及以后"）。

## S54.2 修法（只动这一条用例与一个新辅助函数）

| 位置 | 改动 |
|---|---|
| 新 `_purge_daily_namespace()` | 同步裸 SQL（手法同本文件既有的 `_purge_t24`）：先删两类每日 Job 的 `job_items`，再删 `jobs`，最后按 id 与 sub 删用例自己的用户行。**刻意不吞异常**——清场失败意味着残留会害死下一跑，报红比静默好 |
| 用例进门 | `_purge_daily_namespace()` 放在建引擎之前：上一跑留下的用户行/作业先清掉，本跑才有确定起点 |
| 用例出门 | 原来写在"断言之后、`finally` 之外"的那段 async 清场整段移进 `finally`（`engine.dispose()` 之后），断言红、入队中途红都会走到这里；`from sqlalchemy import delete` 随该段删除（本文件再无别处用它，ruff 复核过） |
| 其余用例 | 一字未动（`git diff --stat` 只列本文件；`_t24_guard` 夹具、其他用例、conftest、CI 工作流均零改动） |

## S54.2 验收②：改后同库连跑三次该文件

`pytest tests/test_scheduler.py -q` × 3（同一库，中间不重建）：
**25 passed / rc=0**，三轮逐字同形（10.96s / 10.76s / 10.67s，@win 2026-10-26）。
对照先红：同一库上改前两轮都是 `1 failed, 24 passed` ⇒ 这三轮绿不是"库恰好干净"，是进门那次清理真的执行了。

清理路径的独立证据（临时脚本现读，脚本不入库；读数在 `s54_1_red_readings.md` 第二节）：
改之前库里有 1 条用户行 + 2 条每日类 Job（一条 `daily_report` 已 SUCCEEDED、一条 `hot_cluster` 还 QUEUED），
三轮跑完之后同类读数全是 0 行 ⇒ "进门清 + 出门清"两条路都真的走通了，不是断言被跳过。

## S54.3 同库连跑两次全量（判定 + w2_worker 观察）

命令：`pytest tests/ -q -rs --cov=app --cov-report=json`（两轮完全同一条命令），同库、中间不重建。

| 轮 | rc | 计数 | w2_worker 观察 |
|---|---|---|---|
| 1 | 0 | **2466 passed / 6 skipped / 4 deselected，0 failed**（1799.20s） | 该用例名在整份日志里出现 **0 次**（`-q` 只打印失败用例名）⇒ 本轮绿 |
| 2 | 0 | **2466 passed / 6 skipped / 4 deselected，0 failed**（1806.88s） | 同上，出现 **0 次** ⇒ 本轮也绿 |

两轮同一条命令（`pytest tests/ -q -rs --cov=app --cov-report=json`），中间**不重建库、不手工删行**
（卡面第 8 格）；原文 `s54_3_full_round1.txt`、`s54_3_full_round2.txt`。

最有用的对照：**本机持久库两轮的 2466/6/0 与 CI 新库的 2466/6/0 逐字相同**
（CI 40263352699 @`0aa2923`），而本卡改动前同一张库连跑两次是 2464 passed / 2 failed
⇒ "本机读数可重复、不必每次重建库"这条目标达成；第二轮的作用正是证明它不靠"第一跑恰好把库洗干净"
（第一轮跑完库就应当是干净的，所以第二轮同样 0 failed 才是"出门必清"真的生效的证据）。

覆盖率：`--cov-report=json` 两轮都写同一个 `apps/api/coverage.json`，后写覆盖前写 ⇒ 只剩第二轮的数
**88.94%**（第一轮的数没有被留档，这条如实记为"未单独存档"，不是"两轮同数"的推论）。
本机模块覆盖率门仍判 rc=2（8 条阈值 key 在 @win 的键形下命中 0 个）——那是 **P-125**，
与本卡无关：改本卡之前的那次复跑（`EVD-V21-52/backend_local.md`）已经是同一个 rc=2、同样 8 条失配，
规划方已裁给 S55.2（D-V21-13）。这道门在 CI 的 ubuntu job 上是绿的（`0aa2923` 的 CI 读数里有
`✅ 全部模块与全局达标`）。本机复跑七步的逐条 rc 原文在 `s54_local_gates.txt`：
ruff 0、mypy 0（134 文件）、`alembic upgrade head` 0（这次按 CI 同形把 `DATABASE_URL` 也指到测试库）、
`alembic heads` 单一头 `ab1006c2a`、`gen_contracts --check` 0、`check_docs_consistency` 0、覆盖率门 2（P-125）。

w2_worker 的判定按规划方 2026-10-26 的指令如实记录、不当推论：本轮它绿的机制是
`scheduler` 在收集序里排在 `test_w2_*` 之前，其"进门先清"把 w2 自己上一跑留下的那条
`hot_cluster`（读数见 `s54_1_red_readings.md` 第二节，当天日期、QUEUED 态）删掉了——
这是**顺带治了别人的残留**，不是 w2 自身的清场变好了。两轮都绿只说明这条链在本机
这个顺序下成立；w2 自己的"红一次就留残留"仍在它自己的文件里（本卡允许面之外）。
第二轮也绿 ⇒ 按指令**不登记 P-126**（那条只在"第二轮仍红"时成立）；
w2 自身清场的同族写法问题作为建议随 55 一并交回，不写成本卡的结论。

同步状态：本卡改动期间规划方推了 `faed03a`（只改文档：裁 P-123～125 与 D-V21-12～15、新开 STEP-55、
队列改 54→55→53、附录 A 第五节覆盖率门改在仓库根带 `--json apps/api/coverage.json`、
新 P 号从 P-126 起）。本卡允许面（`apps/api/tests/test_scheduler.py`）与该批**零文件交集**，
`git merge --ff-only origin/main` 直接快进到 `faed03a` 后继续跑，不需要 rebase、没有冲突；
P 表与 07 记录两边的行都保留、只追加不删（这两处本卡只在收口批动）。

同步状态：本卡改动期间规划方推了 `faed03a`（只改文档：裁 P-123～125 与 D-V21-12～15、新开 STEP-55、
队列改 54→55→53、附录 A 第五节覆盖率门改在仓库根带 `--json apps/api/coverage.json`、
新 P 号从 P-126 起）。本卡允许面（`apps/api/tests/test_scheduler.py`）与该批**零文件交集**，
`git merge --ff-only origin/main` 直接快进到 `faed03a` 后继续跑，不需要 rebase、没有冲突；
P 表与 07 记录两边的行都保留、只追加不删（这两处本卡只在收口批动）。

skip 构成与基线：两轮各 6 条 skip，与 STEP-52 后端基线那一跑的六条逐条同因
（LangBot :5300 不可达 2、测试 Redis 不可达 2、通知域 Redis 超时 1、代理变量对照在无该宿主环境时无判定力 1），
**没有一条是"PG 不可达"** ⇒ 连库面真跑。`SKIP_BASELINE_WIN` 仍是 692、`ci.yml` 的 `SKIP_BASELINE` 不动：
本卡不新增也不删除任何连库用例，只是把一条既有用例的清场改成确定，
所以 Windows 侧那条零余量基线不该被这张卡推动（若两轮里 skip 数有变，按纪律先重测再谈抬或降）。

## 第 1 轮审查（子智能体只读审查 → 逐条处置）

结论 PASS-with-nits，没有正确性破坏项。审查者独立证到的正面项（带它自己取的锚）：

| 项 | 审查者的证据 |
|---|---|
| SQL 里的表名/列名是真的 | `users`/`jobs`/`job_items` 见 `app/models/entities.py:20`、`:236`、`:256`；`users.id` 主键 `:22`、`users.sub` 唯一非空 `:23`；`jobs.id :238`、`jobs.type :239`（String(32) 带索引）、`job_items.job_id :259-261` ⇒ 清理不会因标识符错而抛 |
| 删除顺序与级联 | `job_items.job_id → jobs.id` 在真 DDL 里就是 `ON DELETE CASCADE`（`alembic/versions/05a5a856c37b_v1_initial_schema.py:143`）⇒ 本函数显式先删明细属**防御性**而非必需；`jobs.user_id → users.id` 也是 CASCADE（同文件 `:125`、`entities.py:240-242`） |
| SKIP→ERROR 风险（本机 692 零余量基线） | `_t24_guard` 是模块级 autouse 夹具（`tests/test_scheduler.py:122-137`），PG 不可达时在**任何用例体之前** `pytest.skip`；第一次清理在 `:846` 的用例体内 ⇒ skip 分支根本走不到清理，skip 构成不会变 |
| 所有权 | `git diff --stat` 一个文件（+47/−12）；`apps/api/app/**`、其它测试、conftest、工作流零命中；`delete` 在本文件已归零（可安全摘除），`Job`/`JobItem`/`select`/`func` 仍在 `:345`/`:353`/`:756` 等处被用 ⇒ 无孤儿导入、无被删用的符号 |
| 第二跑与第一跑不会分叉 | 收集序按字母：`test_scheduler.py` 在 `test_w2_*` 之前，而 w2 那几族的作业在清理之后才建（`test_w2_worker.py:154-158` 用 `_W2_KEY_PREFIX`）；排在 scheduler 之前的文件不产这两类 `jobs` 行；同文件邻居 `test_daily_jobs_skip_before_0630` 断言的是**增量**而非"表为空"（`:904-905`）⇒ 全局 `type IN (...)` 删不到别人的必需品 |

处置（含不修的理由，逐条落到文字而不是"已知问题"）：

1. **`finally` 里 `engine.dispose()` 在清理之前**——审查者指出若 dispose 抛，则随行的清理会被跳过。
   **本卡不改**：两轮全量判据读数必须对应交付树，改这一行位置会让 S54.3 的"两次都 0 failed"
   读的不是被推送的那棵树；而这条暴露已被"进门先清"完全补偿（下一次跑先自我修复）。
   残留面如实写在这：dispose 抛 ⇒ 该跑留下残留 ⇒ 下一跑的进门清理接住，不产生新红。
2. **潜在外键项**：`system_settings.updated_by → users.id` 是 NO ACTION
   （`alembic/versions/ab1006c4a_system_settings.py:49`，模型 `app/models/bothot_entities.py:322`）。
   今天没有任何用例把那个字段写成这对主键（全 tests 树 grep 两个写死值只命中本用例 `:852-853`
   与新常量 `:84`），所以**当前不会触发**；若将来有用例这么写，本清理函数会按设计抛出来
   （它刻意不吞异常）——这是"红得清楚"而不是"静默留残留"，符合本卡取向。登记为观察项，不开 P 号。
3. **"清场写在 finally 之外"这一族在别处是否仍有**：审查者从构造上说"存在"。我自己按形状点了一遍名，
   **没有找到可以判成残留的实例**：含写死主键样子的候选文件里，`test_r04_jobs.py`、
   `test_repositories.py`、`test_metadata_filter.py` 对 PG DSN / `session.commit` / `session.add`
   的引用数都是 **0**——它们的 `id="f-1"`、`id="art-1"`、`id="a-new"` 是内存桩对象，不落共享库。
   ⇒ 按纪律**不登记 P 号**（无实证就不算缺陷，只能算待确认），改为把建议交回规划方：
   做一道 AST 门"连库用例若以写死主键/唯一键 INSERT，则清场必须在 `finally` 或前置幂等清理里"
   （手法与 STEP-49 的 SQL 参数化 AST 门同族），归属 Agent-Guard。这条建议记在 07 记录的交回栏。

## @ci（推送后回填）

待填。
