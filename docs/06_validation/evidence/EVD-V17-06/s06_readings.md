# EVD-V17-06：STEP-06 采集端到端测试闭环与覆盖率门（V0.17.0 队列⑮）

- 日期：2026-10-22（Asia/Shanghai）
- 基线：`main@8e5b23e`（STEP-14a 记录提交，开工时工作树干净）
- 卡面：`docs/任务规划V0.13.0/steps/STEP-06-采集端到端测试闭环与覆盖率门.md` ← 源卡
  `docs/任务规划V0.7.0/steps/STEP-06-采集端到端测试闭环与覆盖率门.md`（继承卡字段 5/8 明确
  「同来源卡；本版未改动」⇒ 判据全文按源卡读，本文件 §5 逐条判定）
- 环境：Win10 + Git Bash；`apps/api/.venv` Python 3.12；`PYTHONUTF8=1`；隔离 PG16@127.0.0.1:5547；
  Redis/LangBot 未起；**五个付费 provider 一次真实上游调用都没发**（全部 `httpx.MockTransport`
  吃 `tests/fixtures/provider_payloads/` 样本），LangBot 与文章页抓取同为桩。
- 证据件命名：源卡 §7 写的是 `EVD-V2-06`（V0.3.0 年代的目录名，`docs/任务规划V0.3.0/steps/STEP-06-*:30`
  把它列为输出路径）。本队列⑮的同批卡一律用 `EVD-V<规划版本>-<step号>`（已有
  `EVD-V17-04 / -05 / -07 / -08 / -09 / -10`），故本件落在 `EVD-V17-06/`，内容契约不变。

## 0. 现读（写代码之前）

| 事实 | 读数 |
|---|---|
| `apps/api/tests/test_e2e_collection.py` | **不存在**（`ls tests/` 无该文件）⇒ 卡面 S6.1 两条从零建 |
| 已有用例覆盖到第几段 | `test_manifest_sync.py` ①②（+`:543` 一条 ①②③）、`test_scheduler.py:493` ③、`test_job_worker.py` ③④（ingest 为桩）、`test_kb_longlink_ingest.py::test_two_distinct_long_links` ④、`test_manifest_asset_alignment.py::test_ready_article_is_not_re_enqueued` ②→③→⑤ —— **没有任何一条把五段连起来跑过一次** |
| `test_p0_asset_cache.py` 的 `URL_A`（改前第 26 行） | `https://mp.weixin.qq.com/s/p0-cache-001?biz=…&hid=h0`：短链路径挂伪参数（微信长链真实参数名是 `__biz`，`hid` 不是微信参数）⇒ 规范键退成 `h:` 兜底支，实测 `canonical_article_key(URL_A)` = `h:…`；且全文件只有这一条 URL，「同号两篇」那个维度不存在 |
| `test_scheduler.py` 的 `_seed_manifests`（改前第 189 行） | `external_id = "t24-w0"` + `url = https://mp.weixin.qq.com/s/t24-w0`；`article_key` 实测 `h:caedb061244e3bea3e5038abb8681980`（token 只有 6 字符，够不到 `CANONICAL_S_KEY` 的 8），而资产那侧铺的 external_id 是 `t24-w0` ⇒ 两支永不相等 |

行号一律标「改前」：本仓行号每批都漂（`test_kb_longlink_ingest.py` 的 docstring 早就写过这条），
锚给成"当时那一行的内容"才可复核。
| `ci.yml` 的 pytest 步（改前第 166 行）覆盖率门 | 只有 `--cov-fail-under="$COV_BASELINE"`（75），无模块级门；`scripts/` 下无 `check_module_coverage.py`；`make` 无 `coverage-gate` 目标 |
| provider 桩可复用什么 | `test_provider_contract.py` 的 `_BUILDERS`（真客户端类 + 注入 MockTransport 的 http）与 `_client(sample)`；`test_langbot` 的 `_client/_lb_transport/_StubResolver`；`test_p0_asset_cache._CountingStubResolver`；`test_rss_subscription` 的 `_provider/MIXED_FEED/FEED`；`test_manifest_asset_alignment._OneSessionCtx` |
| registry 能不能直接给六个 provider | **不能**：`providers/discovery/registry.py` 的 `tikhub` 位 `implemented=False`，`select_channels` 会把它筛掉 ⇒ 经 registry 参数化会漏渠道或假绿。本卡直接用 `_BUILDERS` 里的客户端类（卡面 §3「provider 桩」与此一致） |

## 1. S6.2 纠偏夹具（含变异反证）

### 1.1 `test_scheduler.py`（S6.2.1 / S6.2.1.1）

改后的夹具（`_article_seed` / `_seed_manifests` / `_mark_ingested_and_reshare`）：
`external_id` = 32 位小写 hex（redfox `workUuid` 同形），`url` = 带 `__biz/mid/idx/sn` 的长链并挂
追踪参数与片段，`article_key` 实测落在 `b:T24SCHEDZHhkZg==:2650000000:1` 那一支——两支键空间
**互不相等**，夹具内另带两条 `assert` 盯住这一点（键空间一旦重新重合，夹具自己先红）。

同批补的第二道判据：`test_incremental_sync_creates_job_with_diff_items` 第三条断言原先是空的。
资产铺好后不改清单状态的话，Diff 的首道谓词 `status == DISCOVERED` 就已经把它挡掉了（首轮入列
时 `_populate_job_items` 把行翻成了 ENQUEUED），ready 键减写错也照样绿。现在把 Job 置终态
（否则「在途键减」会替它守住，同样测不到 ready 门）并按状态机合法路径
`validate_transition("manifest", "ENQUEUED", "DISCOVERED")` 回退清单，让 ready 键减成为唯一的门。

反证（真变异，不是推理）：把 `app/services/subscription.py::_compute_new_manifests` 的
`ArticleManifest.article_key.not_in(ready_keys)` 改成 `ArticleManifest.external_id.not_in(ready_keys)`
（= P-2 的原缺陷形），实测 `test_scheduler.py::test_incremental_sync_creates_job_with_diff_items`
**转红**，日志读数 `scheduler 触发订阅 t24-incr：新增=2`（改前该轮为 0）。改回后 22 条全绿。

读数：`pytest tests/test_scheduler.py -q` → `22 passed`（S6.2.1.1 达成）。

### 1.2 `test_p0_asset_cache.py`（S6.2.2）

`URL_A` 改成唯一样本源 `fixtures/wechat_urls.LONG_A`（真实长链），`_biz_anchor()` 改用 `BIZ_A`，
并新增机器门④ `test_p0_same_account_two_long_links_are_isolated`：同号两篇 ⇒ 两个 asset 行、
两支 `b:` 键、`fetch_count == 2`、第二篇不命中缓存，最后钉
`(asset_a.hit_count, asset_b.hit_count) == (1, 0)` 与 `(version, version) == (1, 1)`。

分工（不是重复 `test_kb_longlink_ingest.py::test_two_distinct_long_links`）：那条证 **身份坍缩**
（第二篇不许领第一篇的正文），这条证 **P0 缓存面在同号两篇之间不串号**（计数与版本各归各的行）。
这条分工不是嘴上说的，实测过：把 `app/repositories/asset.py::hit()` 改成「按 source 给该源下所有
READY 资产各 +1」，全量跑该文件与那条 P-3 用例，**只有新增的这条转红**
（`1 failed, 16 passed`）——旧夹具全文件只有一条 URL，这个失效面当时测不到。

读数：`pytest tests/test_p0_asset_cache.py -q` → `5 passed`（原 4 条 + ④）。

## 2. S6.1 六渠道 E2E 闭环（`tests/test_e2e_collection.py`，新建）

一条链路五段全用真服务：`ManifestSyncService`（真翻页/幂等 upsert）→ `ArticleManifest` →
`SourceSubscriptionService.run_incremental_sync`（真 Diff + 真 Job/JobItem）→ `JobWorker.run_once`
（真认领/真逐篇消费/真清单四态回写）→ `KnowledgeBaseService.ingest_url`（真资产 upsert + 真 doc +
真分类）→ 再发现一次 + 再 Diff 一次。**只有上游 HTTP 是假的**：provider 吃样本、LangBot 与文章页
是 MockTransport。worker 与调度器共用 `db_session` 那条会话（`_OneSessionCtx`），所以整套读数
发生在外层事务回滚里，不留存量。

每渠道读数（下表全部取自 `pytest tests/test_e2e_collection.py -q -s` 的结构化日志，
逐条对应 `Manifest 同步 … calls=… new=… same=…` / `T2.4 增量入列 … 新增=…` /
`job_worker 终态 … counts={…}` 三行，`EVD` 同批捕获于 `D:/tmp/e2e_read.log`）：

| 渠道 | 发现新增 | 上游调用 | filtered_offsite | 入列 | 条目 SUCCEEDED | 资产 | doc | 抓取次数 | 二轮新增 | 二轮 Diff | 资产与清单同源 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| redfox | 2 | 1 | 0 | 2 | 2 | 2 | 2 | 2 | 0 | 0 | 是 |
| dajiala | 2 | 1 | 0 | 2 | 2 | 2 | 2 | 2 | 0 | 0 | 是 |
| justoneapi | 2 | 1 | 0 | 2 | 2 | 2 | 2 | 2 | 0 | 0 | 是 |
| tikhub | 2 | 1 | 0 | 2 | 2 | 2 | 2 | 2 | 0 | 0 | 是 |
| wellbyte | 2 | 1 | 0 | 2 | 2 | 2 | 2 | 2 | 0 | 0 | 是 |
| rss | 2 | 1 | **3** | 2 | 2 | 2 | 2 | 2 | 0 | 0 | **否** |

六条判据逐条都是断言而非日志：`report.discovered == 2`、`len(manifests) == 2` 且
`article_key` 互不相同、Job 恰 1 个 + 条目全 PENDING 且 `manifest_id` 非空、`Job.status ==
SUCCEEDED` + `counts == {total:2, succeeded:2, failed:0, pending:0}`、清单全 `INGESTED`、
资产 2 行 READY + doc 2 行 INDEXED、`fetch_count == 2`、二轮 `discovered == 0` 且
`updated + unchanged == 2` 且 `Diff == 0` 且 Job 数不增且资产数不增。RSS 另钉
`filtered_offsite == 3`（D-V2-03：外链只发现不入库，且"滤掉几条"必须是一个数）。

### 2.1 连跑 3 次一致（S6.1.1.1）

两半都做：
- 进程内：`test_e2e_discovery_is_deterministic_across_three_syncs` 对同一渠道连打三次上游，
  断言三次的 `article_key` 集合逐字相同、第一次 `discovered=2`、第二三次 `(0, 2)`。
- 跨进程：`pytest tests/test_e2e_collection.py -q` 连跑三次，读数
  `7 passed in 2.78s / 7 passed in 2.72s / 7 passed in 2.71s`（同一台机、同一隔离 PG，
  无重试、无 flaky 标记）。

为什么整链不在一个会话里跑三遍：`db_session` 只在用例结束时回滚，同一事务里第二遍
`_seed` 会先撞 `uq_source_type_external`——那是夹具边界不是不稳定，写成"三轮"只会得到一个
假红或一套自造的清场 SQL。

### 2.2 变异反证（二轮 Diff=0 有判定力）

把 `_compute_new_manifests` 的首道谓词 `status == DISCOVERED` 摘掉（P-2/P-3 之前的失效面形），
跑整个 E2E 文件：`1 failed, 6 passed`，红的**只有 `[rss]`**，报错
`app.core.errors.JobStateInvalidError: [30005] manifest 非法流转: INGESTED → ENQUEUED`。
两条结论都是从这次红里读出来的，不是读码推的：
1. 五个微信渠道的二轮**同时**被状态门与 ready 键减两道守着（摘掉状态门它们仍绿，说明 ready
   门真的在减资产）；
2. RSS 只有状态门：摘掉之后它真的把已入库的篇重新入列了 ⇒ 新登记 **P-97**。

## 3. S6.3 模块覆盖率门

### 3.1 `scripts/check_module_coverage.py`（S6.3.1）

纯 stdlib，输入 `coverage.json`。阈值表逐字取卡面 §1：article_identity 100、
manifest/kb/subscription 85、dajiala/justoneapi/tikhub/wellbyte 80、全局 79。
退出码三态：`0` 达标 / `1` 判红 / `2` NOT-PASS（缺文件、解析失败、形状不符、阈值键命中 0 个
或命中多个文件）。**`2` 与 `0` 必须可分**：CI 里那步没跑、路径写错、模块改名，三种情况的
共同表现是"一条都没判"，而这种时候最容易写成通过。

接线（S6.3.2）：`ci.yml` 的 `backend` job 在 pytest 命令里加
`--cov-report=json:coverage.json`，随后新增一步 `Module coverage gate (check_module_coverage)`；
`make coverage-gate` 与 `python scripts/entry.py coverage-gate` 同义（`check_entry_parity` 绿），
刻意**不**并入 `make guard` 聚合目标——没有那次 pytest 就没有输入，放进聚合门只会让每次多一个
rc=2，把"缺输入"这件事喊废。

实测（本机，非 CI）：
- `make coverage-gate` 在没有 `coverage.json` 时打印 `NOT-PASS 读不到 apps\api\coverage.json…`
  并以 rc=2 退出（entry.py 的收尾行也复述「3 = 工具缺失，不是通过」）。
- 阈值表与 8 个模块的真实读数见 §3.3。

### 3.2 反证四面（S6.3.1.1，常驻在 `tests/test_module_coverage_gate.py`）

判据跑的是仓库里那份脚本（`importlib` 按路径加载），不是测试文件里抄一份逻辑。

| 输入 | 期望 | 读数 |
|---|---|---|
| 各模块恰好落线 | rc=0 | 绿 |
| `kb.py` 84.99（其余落线） | rc=1 | 绿 |
| 全局 totals 78.9（模块全绿） | rc=1 | 绿 |
| **人为调高阈值**（同一份落线输入 + `--set app/services/kb.py=85.01`） | rc=1 | 绿（先 0 后 1，两条都在同一条用例里断言） |
| **调低 / 置零 / 非数字 / 未知模块** 四种 `--set` 输入 | rc=2 | 绿（这一面是独立验证者指出漏洞后补的，见 §8） |
| coverage.json 不存在 | rc=2 | 绿 |
| 内容不是合法 JSON | rc=2 | 绿 |
| 顶层缺 `totals` | rc=2 | 绿 |
| 阈值表里某个模块在 JSON 中命中 0 个文件 | rc=2 | 绿 |
| 阈值表被悄悄下调（与卡面数字比对） | 红 | 绿 |
| ci.yml / Makefile / entry.py 三处接线文字在场 | 红 | 绿 |

读数：`pytest tests/test_module_coverage_gate.py -q` → `11 passed`（不连库，因此不计入 skip 家族）。

### 3.3 覆盖率读数（本机全量，隔离 PG16@5547）

全量：`2247 passed / 6 skipped / 0 failed`，用时 `1233.92s`（20:33）；skip 6 条与
`ci.yml` 的 `SKIP_BASELINE: "6"` 同形（LangBot/Redis 依赖缺失类），**PG 不可达类 0 条**。
读数取自该次运行的 `.coverage`（`coverage json` 复算），不是 term 输出的四舍五入值。

| 模块 | 线 | 实测 | 行 | 余量（行） |
|---|---|---|---|---|
| `app/services/article_identity.py` | 100 | **100.00%** | 63/63 | 0（满分即零余量） |
| `app/services/manifest.py` | 85 | 94.35% | 217/230 | 21 |
| `app/services/kb.py` | 85 | 89.05% | 309/347 | 14 |
| `app/services/subscription.py` | 85 | **85.44%** | 352/412 | **2** |
| `app/providers/article_sources/dajiala.py` | 80 | 100.00% | 122/122 | 24 |
| `app/providers/article_sources/justoneapi.py` | 80 | 99.39% | 163/164 | 32 |
| `app/providers/article_sources/tikhub.py` | 80 | 100.00% | 140/140 | 28 |
| `app/providers/article_sources/wellbyte.py` | 80 | 99.42% | 171/172 | 34 |
| 全局 TOTAL | 79 | 88.04% | 8918/10129 | 916 |

门对本机这份 JSON 的读数：`…/scripts/check_module_coverage.py --json D:/tmp/cov.json`
→ 九行全「达标」+ `✅ 全部模块与全局达标`，rc=0。

⚠ 两条零/薄余量必须让规划方知道（登记 **P-98**）：`article_identity` 的线就是满分，任何一条
新增语句没有用例覆盖就直接红；`subscription.py` 实测 85.44%，只差 2 行就会跌破 85。这不是
本卡能改的（改阈值=违卡面，补覆盖=别人的测试文件在本卡允许面之外），但它是下一张碰到这两个
文件的卡的必然红点。

### 3.4 CI 面读数（`@ci` ubuntu-latest，验收权威面 D-V4-01）

同一次运行（run 39803393349，attempt 1）：`2257 passed / 6 skipped / 0 failed in 170.66s`，
skip 门禁 `total_skipped=6 baseline=6 pg_unreachable=0`。新接的那一步在 pytest 之后执行，
它对 CI 自己那份 `coverage.json` 的判定：

| 模块 | 线 | CI 实测 | 行 | 与本机差 |
|---|---|---|---|---|
| `app/services/article_identity.py` | 100 | 100.00% | 63/63 | 0 |
| `app/services/manifest.py` | 85 | 95.22% | 219/230 | +2 行 |
| `app/services/kb.py` | 85 | 87.61% | 304/347 | −5 行 |
| `app/services/subscription.py` | 85 | **85.19%** | **351/412** | **−1 行** |
| 四家 provider | 80 | 100 / 99.39 / 100 / 99.42% | 122/163/140/171 | 同本机 |
| TOTAL | 79 | 88.00% | 8914/10129 | −4 行 |

`✅ 全部模块与全局达标`，rc=0。**CI 面比本机更薄**：`subscription.py` 只剩 1 行余量
（351/412；再有一行没被覆盖就 84.95% 跌破 85）——P-98 因此是按 CI 读数登记的，不是按本机。
`test_module_coverage_gate.py` 的 10 条也在这次全量里（本机那轮跑在它落地之前，故 §3.3 是 2247）。

## 4. 四探针复跑终值（M1 收口，逐条本机重跑，不抄 `61739f0` 旧读数）
探针原件在 `docs/任务规划V0.2.0/evidence/`，本卡只读不改。

| 探针 | 原件 2026-10-12 读数 | 修复后期望 | 本轮实测（2026-10-22） | 判定 |
|---|---|---|---|---|
| P-1 `probe_row_mapping.py` | dajiala/justoneapi → `None`（整行被 skip）、RSS `publish_time=None` | 四行都能解出 | `dajiala -> {...}`、`justoneapi -> {...}`、`redfox -> {...}`、`rss -> {...}`、`atom -> {...}`，五个全部带 `article_key` + tz-aware `publish_time` | 达期望 |
| P-2 `probe_reenqueue_loop.py` | 已 READY 入库后 Diff 仍判新增 = 1 | 0 | `已 READY 入库后 Diff 仍判为新增篇数 = 0` | 达期望，**但达成原因变了**（见下） |
| P-3 `probe_longlink_collision.py` | `fetch_count= 1 B.hitCache= True same_doc= True` | `fetch_count= 2 B.hitCache= False same_doc= False` | `PROBE fetch_count= 2 A.hitCache= False B.hitCache= False same_doc= False` | 达期望（逐字命中） |
| P-4 `probe_multisource_crash.py` | `EXC MultipleResultsFound` | `PROBE2 ok False` | `PROBE2 ok False`（2 passed） | 达期望 |

P-2 的诚实说明：该探针铺的清单行**没有 `article_key`**（NULL），所以今天那个 0 是
`D-V9-04` 的 NULL 守卫给的（同一轮日志另打出 `manifest.diff.null_key_backlog rows=1`），
不再是「两支键空间对齐」给的。判据本身因此变弱了——真正测那件事的是常驻用例
`test_scheduler.py::test_incremental_sync_creates_job_with_diff_items`（§1.1，带变异红点）
与 `test_e2e_collection.py`（§2.2，摘掉状态门后五渠道仍绿）。探针"绿"不等于判据还在，这句
就是这条记录存在的理由。

本机跑法与平台差异：P-1 直接跑（纯函数）；P-3/P-4 按探针自带用法复制到
`apps/api/tests/test_zz_probe_*.py` 跑完即删（跑后 `ls tests/ | grep -c zz_probe` = 0，
工作树未留痕）；P-2 是独立脚本，原件写死 `asyncio.run(main())`，Windows 默认
ProactorEventLoop 下 psycopg 直接拒（`InterfaceError: Psycopg cannot use the
'ProactorEventLoop'`）⇒ 本机跑不了。为拿到读数，把它整份复制成 `D:/tmp/probe_p2_win.py`
并**只替换最后一行**（换成 `SelectorEventLoop` 显式建环），仓库内原件一字未动。

## 5. 收口判定（源卡三级任务逐条 + 卡面 §1 四句）

| 编号 | 判定 | 依据 |
|---|---|---|
| S6.1.1 `test_e2e_collection.py::test_redfox_round_trip` | 已交付（改名 `test_e2e_round_trip[redfox]`，六渠道参数化后 redfox 是其中一个 id） | §2 读数 + `7 passed` |
| S6.1.1.1 连跑 3 次一致 | 已交付 | §2.1（进程内三次同键集 + 跨进程三次 `7 passed`） |
| S6.1.2 参数化到其余 5 渠道；rss 外链计 `filtered_offsite` | 已交付 | §2 表：五渠道各 2 篇入库；rss `filtered_offsite=3` 且只有 2 条入库 |
| S6.2.1 `_seed_manifests` 真实 id/长链 + READY 资产用规范键 | 已交付（并补了 Job 终态 + 合法回退，见 §1.1） | `22 passed` + 变异红点 |
| S6.2.1.1 test_scheduler 全绿 | 已交付 | 同上 |
| S6.2.2 `URL_A` 改 `__biz` + 同号两篇用例 | 已交付 | `5 passed` + §1.2 的「只有新用例红」变异读数 |
| S6.3.1 `check_module_coverage.py` + `Makefile coverage-gate` | 已交付（另需 `scripts/entry.py` 注册，否则 `check_entry_parity` 红） | §3.1、`make coverage-gate` rc=2 的 NOT-PASS 读数、parity 门绿 |
| S6.3.1.1 人为调高阈值 ⇒ rc≠0 | 已交付（常驻反证，不是一次性手工） | §3.2 表第 4 行 |
| S6.3.2 ci.yml pytest 步后接 coverage-gate | 已交付 | `ci.yml` 新增步 + `tests/test_module_coverage_gate.py::test_ci_wires_the_gate_after_the_pytest_step` |
| S6.4.1 双环境全量 + 四探针 + coverage-gate + evidence-check + CI 双绿 | 已交付 | §3.3 / §3.4（本机与 CI 两面同为 `2257 / 6 / 0`）、§4、§7（三绿 run id）、§8（独立验证者） |
| 卡面 §1「6 渠道 E2E，连跑 3 次一致」 | 达成 | §2 / §2.1 |
| 卡面 §1「纠偏掩盖缺陷的夹具」 | 达成（两处，各带一条只有它才红的变异） | §1 |
| 卡面 §1「模块覆盖率门 …；全局保持 ≥79%」 | 达成（CI 面 88.00%，本机 88.04%） | §3.3 / §3.4 |
| 卡面 §1「M1 收口：四探针全部达修复后期望，独立验证者判 PASS」 | 探针四条达期望（P-2 的达成原因变化已如实写出）；独立验证者五项判定 4 PASS + 1 FAIL（所有权申报漏三处），FAIL 已在 §6 补齐并另触发 §8 的一处加固 | §4 / §6 / §8 |

## 6. 所有权越界声明与新登记

卡面所有权（源卡字段 W）：`tests/test_e2e_collection.py`(新)、`test_scheduler.py`、
`test_p0_asset_cache.py`、`scripts/check_module_coverage.py`(新)、`Makefile`、`ci.yml`。
**本批 diff 共 14 个文件，其中 8 个在允许面之外**，逐条声明——
这张表第一版只写了四条，独立验证者按 diff 逐文件核对后判 §6 为 FAIL（漏了三条），
下面的版本是补齐后的：

| 路径 | 为什么必须动 | 动了什么 |
|---|---|---|
| `scripts/entry.py` | Makefile 只做薄转调，新目标名必须在 `BY_NAME` 里，否则 `check_entry_parity`（常驻门）红 | 新增 `coverage_gate()` 步骤 + `add("coverage-gate", …)` |
| `apps/api/tests/test_module_coverage_gate.py`（新） | S6.3.1.1 的反证必须常驻才能防复发；判据文件不在允许面内是 P-87/P-95 已登记的同一族冲突 | 新文件，11 条不连库用例 |
| `.gitignore` | `.coverage` 与 `coverage.json` 是本卡新门的输入产物，未忽略会在共享工作树里长期挂着未跟踪文件，一次宽 add 就被扫进提交 | 加两条规则 |
| `docs/04_engineering/conventions.md` | AGENTS.md 开发流程要求「代码改动同步到文档」；新增的 CI 门不写进规范就等于没有 | §4.1 追加一段（门的位置、跑法、为什么不许被全局分抵掉） |
| `.github/workflows/ci-windows.yml` | 执行助手指令的硬规：新增连库用例必须把 `SKIP_BASELINE_WIN` 抬到测量值、零余量（D-V10-11）。卡面 W 只写了 `ci.yml`，但那条规则来自指令层且优先级更高 | `658 → 666` + 锚注释 |
| `docs/任务规划V0.12.0/00-README.md` | 执行助手指令：新缺陷一律从台账续号登记，不许在卡内顺手修 | 追加 P-97 / P-98 两行 |
| `docs/任务规划V0.17.0/07-执行过程记录.md` | 同上：每张交付卡在该表追加一行 | 追加第 31 行 |
| `docs/06_validation/evidence/EVD-V17-06/**` | 卡面 §7 要求的交付证据（卡面命名 `EVD-V2-06` 与本队列现行 `EVD-V17-<step>` 同义，见文件头） | 读数件 + 四份原始日志件 |

新登记（写入 `docs/任务规划V0.12.0/00-README.md` 台账）：
- **P-97**：RSS 的 Diff 少一道守卫（ready 键减跨不到 source），实测于 §2.2 的变异；本卡不修。
- **P-98**：卡面阈值表里 `article_identity=100` 与 `subscription≥85` 两条是零/薄余量
（本机 85.44% 差 2 行，CI 面只有 85.19% 差 1 行），下一张碰这两个文件的卡会必然红，
请规划方裁定是棘轮还是留余量。

## 7. CI 三绿（交付提交 `88381e2`，父提交 `8e5b23e`）

三条检查全部 **attempt 1 即 success**（原文摘录入库：`ci_backend_gate_logs.txt`、
`ci_windows_skip_gate_logs.txt`）：

| 检查 | run id | 结论 | 关键读数 |
|---|---|---|---|
| CI（ubuntu-latest，验收面） | 39803393349 | success | `2257 passed / 6 skipped / 0 failed in 170.66s`；skip 门禁 `total_skipped=6 baseline=6 pg_unreachable=0`；新步 `Module coverage gate` 打印 `✅ 全部模块与全局达标`，TOTAL 88.00% |
| Security | 39803393049 | success | gitleaks 无新增泄漏 |
| CI-Windows | 39803393352 | success | `1597 passed / 666 skipped`；门禁 `failed=0 total_skipped=666 baseline=666`，未知族 0 ⇒ 交付前算的预测值与实测逐字相符 |

本机第二轮全量（含覆盖率门文件落地后）：`2257 passed / 6 skipped / 0 failed in 1102.54s`
——与 CI 面的用例数完全一致（本机 6 条 skip 同族：LangBot 2 / Redis 3 / 代理变量 1）。
门禁：`ruff check app tests` 0、`mypy app` 119 files 无问题、`check_docs_consistency.py`
23 个路径引用 0 个不存在、`entry.py evidence-check` rc=0（含 gitleaks 356 commits no leaks
+ `protect --staged` no leaks）。

如实记一条流程偏差：**交付提交 `88381e2` 里本节的标题是空的**（当时三绿未回）。
这是本队列既有的"先交付、后回填"做法，但它在 `88381e2` 这个时刻确实让卡面 §8 的
「run id 入 EVD」不成立，独立验证者据此点了名；回填批（本提交）之后才成立。

回填批自己的三绿（`0eff7bc`，含 `--set` 只许调高的加固与第 11 条判据）：
CI 39808521965 / CI-Windows 39808522030 / Security 39808522490，三条 attempt 1 全部 success，
@win 读数 `1598 passed / 666 skipped`、`failed=0 total_skipped=666 baseline=666`
⇒ 新增的那条判据不连库（passed +1、skipped 不变），基线仍然是零余量的等号。

## 8. 独立验证者结论与它触发的两处改动

验证者与执行者分离（卡面字段 2），只给 diff 与读数、不给意图。五项判定：
**1 S6.1 PASS、2 S6.1.2 PASS、3 S6.2 PASS、4 S6.3 PASS、5 所有权 FAIL**。
它另外给的三条不支持声明是：§7 当时为空、CI 数字无入库件可复算、`D:/tmp` 里的日志与
P-2 副本不在仓库——三条都由本批的 `ci_*.txt` / `e2e_channel_readings.txt` /
`four_probe_readings.txt` 与 §7 补齐。

它点出的一个**真实漏洞**已被修：`--set KEY=PCT` 原先也接受**调低**，
于是 `--set app/services/article_identity.py=0` 会打印「达标」并 rc=0 ——
一个永不红的降级出口，比没有门更糟。现在写小一律 rc=2 拒收，判据常驻
`test_lowering_a_threshold_via_the_counterproof_channel_is_refused`
（四个输入：调低、置零、非数字、未知模块）。

它给的两条局限如实收下、不粉饰：
1. 参数化里"同一 scenario 的前五条断言"与 `test_kb_longlink_ingest::test_two_distinct_long_links`
   重叠，真正独有的是 per-row 的 `(hit_count, version)` 隔离那一维（§1.2 已这样写）。
2. 夹具用 `canonical_article_key` 自己算期望键，所以"整套键方案被换掉"这一类改动不在这里被抓住
   ——算法判定力在 `test_article_identity.py`，本卡不动它。
3. 它自己的环境连不上 PG（默认 DSN 指向 `bothot/bothot@5433`，本机未监听），报
   `7 skipped 测试 PG 不可达（OperationalError）`；因此它对 E2E 的判定是基于 diff 与
   committed bytes 的静态复核，"7 passed ×3" 那两条对它而言是转录。这条限制同样如实记在这里，
   读数的可复算性由 §3.4/§7 的 CI 面与两份入库日志件承担。

