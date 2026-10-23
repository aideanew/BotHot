# EVD-V17-11：STEP-11 采集性能基线（V0.17.0 队列⑮）

- 日期：2026-10-22（Asia/Shanghai）
- 基线：`main@0eff7bc`（STEP-06 收口批），开工前工作树干净
- 卡面：`docs/任务规划V0.13.0/steps/STEP-11-采集性能基线.md` ← 源卡
  `docs/任务规划V0.7.0/steps/STEP-11-采集性能基线.md`（继承卡字段 5/8「同来源卡；本版未改动」）
- 证据件命名：源卡 §7 写 `EVD-V2-11`，本队列现行约定是 `EVD-V<规划版本>-<step号>`，同 STEP-06 那条说明。
- 环境：Win10 + Git Bash；`apps/api/.venv` Python 3.12；隔离 PG16@127.0.0.1:5547（迁移单头 ab1006c2a）；
  抓取与 LangBot 全为 MockTransport；**五个付费 provider 一次真实上游调用都没发**。
- 原始读数件：`perf_baseline_readings.txt`（PERF-* 三行 + 生产 Diff 语句原文 + EXPLAIN 计划全文）。

## 0. 现读（写代码之前）

| 事实 | 读数 |
|---|---|
| 有没有性能基线 | 无。`tests/` 下无 perf 目录，`pyproject` 的 markers 只有 `langbot_real` 一条，无 pytest-benchmark 依赖 |
| REQ-NF-001 的入库预算 | `docs/02_requirements/product-requirements.md` 段内「文章入库单篇 < 30s」 |
| `Job` 有没有 subscription_id 列 | **没有**（`app/models/entities.py` 的 `Job`：`user_id/payload/status/progress/error/result/idempotency_key/worker_heartbeat_at`）⇒ 订阅与 Job 的关联只靠 `idempotency_key` 的前缀 LIKE |
| 手写索引 | `app/models/entities.py` 里只有一条 `Index()`：`ix_manifest_source_article_key`；全仓 models 共两条，另一条是 `bothot_entities.py` 的 `ix_notifications_sub_created`（通知域，与采集无关）。其余索引全靠 `index=True` |
| 「1 页 20 行」的 20 从哪来 | `providers/article_sources/base.py` 的 `WORK_LIST_PAGE_SIZE = 20`（桩因此按 20 造，不是随手取的数） |

## 1. 三个基线数字（本机实测，逐字见原始件）

### 1.1 一页清单写入的 SQL 语句数（S11.1.1）

`ManifestSyncService.sync_source(..., max_pages=1)` 吃一个 20 行的清单桩，用
`before_cursor_execute` 数语句：

```
PERF-SQL backlog=0    rows=20 calls=1 total=43 {'SAVEPOINT': 1, 'SELECT': 21, 'INSERT': 20, 'RELEASE': 1}
PERF-SQL backlog=2000 rows=20 calls=1 total=43 {'SAVEPOINT': 1, 'SELECT': 21, 'INSERT': 20, 'RELEASE': 1}
```

两档读数**逐字相等** ⇒ 每页成本是 O(页)，不随本地已有清单规模增长（43 = 1 笔 `_known_count`
SELECT + 每行 1 SELECT + 1 INSERT + 一对 SAVEPOINT/RELEASE）。卡面担心的那类形状——
「每轮增量都在为历史买单」——在发现→清单这一段不成立。

用例里只设形状上界（`total < 4 × 页行数`、`INSERT == 页行数`），精确数字不硬编码：
把 43 写进断言会让换机器/换 SQLAlchemy 小版本都红，而红的原因与性能无关。

### 1.2 `_compute_new_manifests` 在 10k 清单 / 1k Job 下的 EXPLAIN（S11.1.2）

```
PERF-DIFF 清单=10000 jobs=1000 命中=10000 耗时=304.9ms
Planning Time: 0.466 ms
Execution Time: 15.310 ms
```

计划里三处值得规划方直接看到的形状（全文在原始件）：

1. 主表走 `Bitmap Index Scan on ix_article_manifests_source_id` ⇒ 按 source 取 10k 行是索引的，
   但随后是 `Sort`（quicksort 3058kB）+ 全部列取回 ⇒ 304.9ms 的大头在**把 1 万个 ORM 对象搬进
   Python**，不在服务端（服务端 15.3ms）。这条对"要不要给 Diff 加游标/分页"比"要不要加索引"更相关。
2. `SubPlan 2`（减在途）里 jobs 那一支：
   ```
   ->  Bitmap Heap Scan on jobs  (actual time=0.029..0.433 rows=1 loops=1)
         Recheck Cond: ((type)::text = 'sync_account'::text)
         Filter: (((idempotency_key)::text ~~ 'sync_account:perf-7f1f30b07d%'::text)
                  AND ((status)::text = ANY ('{QUEUED,RUNNING}'::text[])))
         Rows Removed by Filter: 999
         ->  Bitmap Index Scan on ix_jobs_type  (actual time=0.020..0.022 rows=1000 loops=1)
   ```
   即：**前缀 LIKE 没走 `idempotency_key` 的唯一索引**（默认 collation 下 `LIKE 'x%'` 用不了
   普通 btree），优化器退而按 `type` 取回全部 sync_account 类 Job 再逐行过滤，
   1000 行里扔掉 999 行。卡面列的三个候选优化项里「`jobs.subscription_id` 列」针对的就是这一处，
   而这一处现在是**实测到的**，不是推测。
3. `SubPlan 1`（减已入库）是 `hashed SubPlan` 对 `content_assets` 的 Seq Scan，本次造数里
   资产表是空的 ⇒ **这一支的成本没进这份基线**（局限性见 §3）。

### 1.3 单篇入库 p50 / p95（S11.1.3）

```
PERF-INGEST n=50 p50=17.7ms p95=21.1ms max=85.5ms fetches=50 预算=30000ms
```

p95 占 REQ-NF-001 预算的 **0.07%**，max 占 0.29%。⚠ 但这三者量的是**服务层自身**
（解析→规范化→质量评分→资产 upsert→doc→LangBot 提交），抓取与 LangBot 都是桩 ⇒
这份读数只能说"服务层不是那 30 秒的瓶颈"，**不能用来说 REQ-NF-001 达标**——
真后端/真抓取下的单篇耗时本卡没有凭据面，未测就是未测。

## 2. 「默认不进全量」怎么做到的，以及它为什么不能靠 skip

卡面 §5 要求 perf 用例 CI 不默认跑。做法是 `pyproject` 的
`addopts = ["-m", "not perf"]` + 注册 `perf` marker：

```
$ pytest tests/perf/ -q                      → 4 deselected in 0.76s
$ pytest -m perf tests/perf/ -q -s           → 4 passed in 4.93s
```

（命令行 `-m` 在 addopts 之后解析，故显式请求能覆盖默认摘除——上面两行就是实测。）

**为什么不用 `pytest.skip` 做默认关**：CI-Windows 的 skip 门禁是按原因族零余量记账的
（`SKIP_BASELINE_WIN=666`，未知族即红），把 4 条用例做成 skip 会直接多挂 4 条不进任何族的
红。**为什么不能不摘**：这四条里有 10k 行造数与 n=50 的入库循环，默认进全量会让每次 push
多跑几十秒并改变 skip 账面。

### 2.1 所有权越界声明

卡面 W 只给 `apps/api/tests/perf/test_collection_perf.py`（新）+ EVD，但「默认不进全量」这条
卡面自身要求在 W 面之内做不到：`testpaths=["tests"]` 会递归采集 `tests/perf/`，而唯一的
声明式摘除点是 `pyproject.toml` 的 `addopts`/`markers`。本批因此改了它一次，逐处列举：
`addopts = ["-m", "not perf"]` 一行 + `markers` 里追加一条 `perf` 说明，
既有 `langbot_real` 一字未动。这是 P-87/P-95 已登记的「卡面判据与卡面允许面互斥」同一族，
不另开 P 项，只在此声明。其余 diff 全在 W 面内。

## 3. 局限（这份基线不能用来主张的事）

1. `content_assets` 在本次造数里为空 ⇒ 减已入库那一支的成本没有读数；把 10k 行换成"半数已入库"
   才是生产稳态，本卡按卡面字面（10k 清单/1k Job）交付，未擅自加档。
2. EXPLAIN 的一次性读数受本机缓存影响（`shared hit` 全命中，无 disk read）⇒ 冷缓存下的
   服务端耗时会更高，这里没有那个数。
3. p50/p95 是**单进程内**的服务层时间；真实部署里同一条链还要经 HTTP 抓取、微信限流、
   LangBot 索引等待。REQ-NF-001 的达标主张必须有那些数，本卡明确不主张。
4. 三条用例都跑在 `db_session` 外层事务里（回滚清场），与真库稳态的区别是索引统计量是现造的
   （10k 行刚 INSERT，autovacuum 还没跑）⇒ `rows=1` 这类估算在真库里可能不同。

## 4. 收口判定（卡面三级任务逐条）

| 编号 | 判定 | 读数位置 |
|---|---|---|
| S11.1.1 1 页 20 行的 SQL 语句数 | 已交付（数字 43，两档 backlog 相同） | §1.1 + 原始件 |
| S11.1.2 10k/1k 的 EXPLAIN 入 EVD | 已交付（计划全文 + 三处形状读解） | §1.2 + 原始件 |
| S11.1.3 单篇入库 p50/p95 与 30s 对比 | 已交付（p50 17.7ms / p95 21.1ms），并显式声明它不构成 REQ-NF-001 达标 | §1.3 / §3.3 |
| S11.2.1 依据数字决定是否开优化卡（👤） | **待规划方裁定**；执行方建议见 §5，不代签 | §5 |
| 卡面 §1「三个基线数字入档」 | 达成 | §1 |
| 卡面 §6「禁止无基线优化」 | 本卡只量不改：`app/**` 零 diff | §0/§1 |

## 5. 给规划方的裁定材料（S11.2.1 是 👤 项，执行方不代签）

按实测把三个候选排一遍，**不是按"看起来该优化"**：

- 「批量 upsert」：不建议现在做。每页 43 条语句、且两档 backlog 相同 ⇒ 发现段是 O(页)；
  一页 20 行的绝对成本已经是毫秒级，批量化省的是每轮几十毫秒，代价是 `_upsert` 的
  并发唯一键兜底（SAVEPOINT 重试）要重写。收益/风险比不划算。
- 「status 索引」：无读数支持。计划里 `status` 只是主表 bitmap 扫描之后的 Filter，
  而主表已经先按 `source_id` 收到 10k 行；再加 status 索引改不了这一步。
- 「`jobs.subscription_id` 列」：**唯一有实测依据的一项**（`Rows Removed by Filter: 999`，
  前缀 LIKE 用不了唯一索引）。但按 1k→100k Job 外推，这一支从 0.43ms 变成约 40ms，
  在 Diff 总耗时（15.3ms 服务端）里占比会反超——是否值得动 DDL（需要 ADR + 迁移 +
  CI 往返门）取决于线上 Job 表真实规模。建议：列为 SHOULD 而非 P0，
  并给一条「当 `jobs` 中 `type=sync_account` 行数超过 5 万时启动」的门槛，
  而不是现在就建列。另可先做零 DDL 的一步：给 `idempotency_key` 建 `text_pattern_ops`
  btree，让 `LIKE 'x%'` 可用索引——这条是本卡的读数顺带提示的，未在卡面候选里，
  请规划方决定是否另开卡。

## 6. 环境变更与本轮不可复核项（STEP-00E S00E.2.2 第 3 条：每轮重取，不引用上一版工具链状态）

上面的三个数字是 **10-22 深夜**在隔离 PG16@5547 可达时实测的，原始输出已入库
（`perf_baseline_readings.txt`）。今早续跑时本机环境变了：

```
$ docker ps            → command not found
$ "<Docker 兜底路径>/docker.exe" ps -a → rc=2（该路径不存在）
$ netstat -ano | findstr ":5547 :5433 :6390" → 无监听
$ tasklist /FI "IMAGENAME eq postgres.exe" → 无进程
```

⇒ 本机连库面本轮不可用，因此：

1. 三条 perf 读数**未在今早复算**（不复算不等于失效：读数件与命令都在，换到有 PG 的机器
   可原地重跑）。
2. 全量连库回归不在本机做，改由 `@ci`（ubuntu + postgres service）承担——这正是 D-V4-01 的分工。
3. 非连库面本轮全部实跑并通过：`ruff check app tests` rc=0、`mypy app` 119 files 无问题、
   `check_entry_parity` 绿、`check_docs_consistency` 通过、
   `pytest tests/test_module_coverage_gate.py -q` → `11 passed`、
   `pytest tests/ --co -m "not perf"` → `2264/2268 tests collected (4 deselected)`。
   最后一条是这次改动最关键的反证：**4 条 perf 用例被摘掉而不是一起跑**，
   且默认面的用例数与昨日 CI 的 `2257 passed + 6 skipped = 2263` 加上当日新增的 1 条判据对齐。
4. `SKIP_BASELINE_WIN` 不动（仍 666）：deselect 不进 skip 账，这一点由本卡的 CI-Windows
   运行结果反证——若它把 4 条 perf 当成 skip，`total_skipped` 会超阈值并直接红。
5. 卡面 §8 要求的 `gitleaks detect` 与 `evidence-check`：今早第一次跑 `evidence-check` 得 rc=3，
   原因写在自己的输出里（「索引为空且 origin/main..HEAD 为空 ⇒ 无可检文件，这不是通过」）——
   即本批文件还没 `git add` 时，敏感形门没有可检面。暂存后复跑才算读数，见 §7。

## 7. 交付读数

- 敏感形门（取材面=index）：`待检 6 个路径，实扫 6，跳过 0，HIGH 0，ALLOWED 放行 0` ⇒ 通过。
- `entry.py evidence-check` → rc=0（含 gitleaks 全历史 `no leaks found`）。
- 上一小节第 5 条那个 rc=3 是**同一命令在未暂存状态下的读数**，两条都留在这里：
  它们一起说明"索引为空 ⇒ 无可检面 ⇒ 不是通过"这条判据真的在起作用。
- 三条 run id（CI / CI-Windows / Security）只能在推送后取得 ⇒ 本批交付提交内本节到此为止。
  这与 STEP-06 被独立验证者点名的那条偏差同形，因此在这里显式标注：
  **卡面 §8 的「run id 入 EVD」在交付提交的时刻尚未成立**，由紧随的记录批补齐并写明提交号。

### 7.1 CI 面读数（run 39885880010，`@ci` ubuntu-latest，attempt 1 success）

```
2258 passed, 6 skipped, 4 deselected, 2 warnings in 213.92s (0:03:33)
skip 门禁：total_skipped=6 baseline=6 pg_unreachable=0
✅ skip 门禁通过：连库用例真实执行，skip 数在基线内
```

这一行同时是三件事的实测证据：① perf 四条在 CI 里是 **deselected**（不是 skip，也不是一起跑），
`4 deselected` 就写在 pytest 的汇总行里；② 默认面的数 `2258 + 6 = 2264` 与本机
`--co -m "not perf"` 的 `2264/2268 collected` 逐字对齐；③ skip 账没被本卡动过（仍 6，PG 不可达类 0）。
既然 deselect 不进 skip 账，`SKIP_BASELINE_WIN` 预期仍是 666，等 @win 那一步的读数落地后在
本节末追一条实测行确认（不拿"预期"当读数）。覆盖率门那一步（`backend/15_Module coverage gate`）照常执行。

Security 在这一批判红，但红得与本卡无关：findings 全部命中 `next`，而该公告出现在
上一条 Security（`0eff7bc`，10-22 23:49 success）与本条（10-23 09:50）之间；
诊断与处置记在 `docs/任务规划V0.17.0/07-执行过程记录.md` 第 33 行与台账 **P-99**。
本卡的三绿锚点因此落到紧随其后的补丁提交上——这一条不粉饰。



