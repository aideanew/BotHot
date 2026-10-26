# 本机后端复跑读数（@win，附录 A 第五节同序）

树：`b4157a9` + 本卡改动（本卡 `apps/api/**` 零改动，见 `s52_readings.md` §所有权）。
库：自备便携 PG16.15@5547 的 `bothot_test`（**持久库，非重建**；跨会话复用）。
时间：2026-10-26 10:34–11:1x（Asia/Shanghai），清 6 个代理变量、`PYTHONUTF8=1`。

| 步 | 命令 | rc | 读数 |
|---|---|---|---|
| ruff | `.venv/…python -m ruff check app tests` | 0 | All checks passed! |
| mypy | `-m mypy app` | 0 | Success: no issues found in 122 source files |
| alembic upgrade head | `-m alembic upgrade head` | **1** | 连 `localhost:5433` 超时（`psycopg.errors.ConnectionTimeout`）——**这是我这条复跑链的环境缺项，不是代码红**：CI 的 backend job 在 job 级 env 段同时设迁移库与测试库两个变量、指向同一个库（`ci.yml:47-51`），我这次只给了测试 DSN，alembic 便回落到 `alembic.ini` 的默认串。本机 5433 无监听（`netstat` 对该端口零命中）⇒ 连接从未建立，没有任何库被动过迁移 |
| alembic heads | `-m alembic heads` | 0 | 单一头 `ab1006c2a (head)` |
| gen_contracts --check | `python ../../scripts/gen_contracts.py --check` | 0 | 通过 ⇒ 契约生成物与本卡零漂移（本卡不改契约） |
| check_docs_consistency | 仓库根 `python scripts/check_docs_consistency.py` | 0 | 23 个路径引用全存在；需求侧锚 133 处按 HEAD 判存在；技术栈引用与实值一致（本卡新写的 P 表行与证据文也在这道门里被判过） |
| pytest 全量 | `-m pytest tests/ -q -rs --cov=app --cov-report=json` | **1** | **2 failed, 2464 passed, 6 skipped, 4 deselected**，1809.26s；覆盖率 `TOTAL 88.99%`（coverage.json 已产出） |
| 模块覆盖率门 | `-m … ../../scripts/check_module_coverage.py`（`--json coverage.json`） | **2** | 8 条阈值 key 全判"命中 0 个" ⇒ 门判 NOT-PASS。与本卡无关，属 @win 侧这道门自身不可复算，已登记 **P-125**（含实测表） |

skip 构成 6 条，逐条与 `ci.yml` 的 `SKIP_BASELINE` 口径一致：LangBot :5300 不可达 2 条
（`test_chat_sse.py:1130`/`:1208`）、Redis 不可达 3 条（`test_session_store_redis.py:47`/`:71`、
`test_we_notifications.py:247`）、代理变量对照在无该宿主环境时无判定力 1 条
（`test_env_isolation.py:77`）。**没有一条是"PG 不可达"**——连库面真的跑了。

## 两条红的归因（这是 P-120 的复现，不是本卡引入）

| 用例 | 红形 | 归因 |
|---|---|---|
| `tests/test_scheduler.py::test_daily_jobs_enqueue_after_0630_with_frozen_clock` | INSERT users 参数 `id='u-s35-daily'`、`sub='sub-s35-daily'` 撞固定行 | **P-120 原文**：该用例用固定 id/sub 直插用户且测后不清，持久测试库上第二次及以后的全量必红；CI 每次新库所以从不暴露。本卡没有动过 `apps/api/**`，这一跑是该库上的又一次连跑 |
| `tests/test_w2_worker.py::test_hot_cluster_job_consumed_by_worker` | `AssertionError: actual=QUEUED`（断言 SUCCEEDED），`err=` 空 | **P-120 裁定行预告的同族**（规划方 2026-10-25 补根因："下一跑的 w2_worker 会吃走残留 daily_report"）。本卡零后端改动 ⇒ 只能是残留 Job 与 worker 取件的先后问题；判"部分确认"：同族身份由规划方根因给出，本次读数与之相容，但要等 STEP-54 修完清场后再看这条是否跟着绿，才算证死 |

两条都在 STEP-54 的判据面上（S54.1 先红、S54.3 要求记录 w2_worker 两次是否都绿），
本卡不越面去修 `test_scheduler.py`（STEP-54 的唯一允许面）。

## STEP-52 的判据不依赖这两条红

本卡交付面是 `apps/web/**`；CI 的 backend job 用**新容器新库**，P-120 家族在 CI 不触发
（`f4f0261` 的 @ci 读数：2466 passed / 6 skipped / 0 failed，见 `EVD-V21-47` 与 07 记录最后两行）。
本机这两条红按上面的归因如实记录，不解释成"应该没问题"。
