# EVD-V18-35 测试确定性与网络密封（执行助手）

平台 @win（Windows 10 x64，Git Bash，`apps/api/.venv` Python 3.12.10，node 24.21.0 / pnpm 9.15.9），
开工 head `0f20da2`（STEP-34 收口批），时间 2026-10-24（Asia/Shanghai）。
卡面 = `docs/任务规划V0.18.0/steps/STEP-35-*.md` + V0.19.0 增量 S35.5 + V0.20.0 增量 S35.6。
本机无 docker、5547 无监听 ⇒ 连库面（S35.2 的 subscription 用例、S35.3 的调度器用例）本机只验收集与静态，
真跑以 @ci 为准。**阈值一个没动**（D-V18-07）。

## S35.1 manifest.py 覆盖抖动定位与确定覆盖（P-104）

- 抖动行定位：取同树（`manifest.py` 最后一次改动 = `211533c`，2026-10-22）的两份 CI 覆盖报告现读——
  run 39891503640 missing = `154,169,180-181,343,409-410,440-444`（12 行）、
  run 39894271073 missing = `154,180-181,343,409-410,440-444`（11 行）⇒ **抖的恰是 `manifest.py:169`**
  （`_parse_rfc822` 的 naive 分支：无时区 RFC 822 日期按规范默认读 GMT）。P-104 的 218/219 ±1 与此吻合。
- 根因：既有三条 RFC822 用例全是**带时区**形态（+0800 / GMT / EST，都走 :170 的 `astimezone`），
  :169 只能等"别的路径恰好喂到无时区串"才被覆盖 ⇒ 随运行时序漂。
- 修法（只加用例）：`test_rss_provider.py::TestPublishTimeRfc822::test_rfc822_without_timezone_reads_as_gmt`
  ——确定输入 `Wed, 02 Oct 2024 07:30:00`（无时区）⇒ 断言 `07:30 UTC`。本地 5 passed（该类全量）。
- 判据"同树连跑 3 次模块门九行读数逐字相同"：交付 head 推送后用 `workflow_dispatch` 派发补跑（见 §@ci）。

## S35.2 subscription.py 余量 ≥5 行（P-98）

- 基线现读（run 40004227226，STEP-45 之后）：`subscription.py` **353/412 = 85.68%**，对 ≥85.0% 的线余量 **2 行**。
- 零覆盖区（CI missing 集合现读）：`:246-252`（list_sources 的 total count 分支与返回形状）、
  `:254-269`（`update_source` 方法体全身——GET/PATCH /sources 管理面此前无任何用例）。
- 补三发（`test_p2_subscription.py`，连库夹具，本机只验收集 24 collected）：
  ① `test_p2_list_sources_returns_rows_and_total`（total ≥1 + 视图五键形状钉死）；
  ② `test_p2_update_source_renames_and_reurls`（改名/改址 + 部分更新语义 + biz 去重锚不许动）；
  ③ `test_p2_update_source_missing_id_is_404_shape`（不存在 id ⇒ ResourceNotFoundError）。
- 预期余量：353 + 22 ≈ 375/412（≥355 即满足 ≥5 行；CI 现读回填于 §@ci）。

## S35.3 并发用例会合点化 + structlog 配置密封（P-52/P-71/P-53/P-63）

- **P-53 先红（本机活体复现）**：`pytest tests/test_observability.py tests/test_discovery.py` ⇒
  **2 failed**（`test_whitelist_unknown_channel_is_warned` / `test_default_runner_skips_when_no_channel_available`，
  两处 `caplog.text` 空串）；反向顺序 33 passed——与 P-53 记载逐字同形。
- 根因与修法：`clean_logging` 夹具的 teardown 只 `structlog.reset_defaults()` ⇒ 把 structlog 留在
  **库默认**（PrintLogger 直打 stdout、不经 stdlib 路由）⇒ 后续 caplog 用例失明。修法：setup 存
  `structlog.get_config()`、teardown `structlog.configure(**saved)` 原样还回（同一 processors 列表对象，
  P-63/P-40 同族教训）。改后正序/反序双 **33 passed**。
- **P-63**：已知复现面 `tests/test_observability.py tests/test_system_settings.py` 修后 **24 passed**；
  `capture_logs` 各用例的取 logger 时机维持现状（首用发生在窗内的用例今天双序全绿，无脆弱面新增）。
- **P-52/P-71**：`test_run_once_runs_due_subscriptions_in_parallel` 的判据从"两段 50ms sleep 的
  墙钟重叠"换成**会合点**——每个 runner 进场置位自己的 `asyncio.Event`、`wait_for` 对方的
  （超时 30s 显式判红）。真并行 ⇒ 双方都越过；串行/慢 ⇒ 越不过而红。与机器负载无关。
  连库用例本机未跑（无 PG），@ci 复算。
- `time.perf_counter` 死导入随手清（ruff F401）。

## S35.4 前端单测拨网密封（P-105 / D-V18-08）

- 基线（改前本机现跑）：`pnpm test:unit` ⇒ 49 files / **415 passed**，stderr 里 **39 处 AggregateError**
  （`ECONNREFUSED ::1:3000 / 127.0.0.1:3000`，18 个 spec 文件）——与 P-105 记数一致；happy-dom 基址未钉，
  未桩 fetch 真拨主平台端口。
- 修法（三件）：
  ① `vitest.config.ts`：`environmentOptions.happyDOM.url = "http://localhost:3200/"`（前端宿主端口；
     主平台 3000 在单测里结构上不可达）；
  ② 新增 `tests/setup-fetch-guard.ts`（进 `setupFiles`）：未桩的 `fetch` 直接抛
     "S35.4 fetch-guard…"——底线桩，`vi.stubGlobal` 者覆盖之；
  ③ 新增常驻反证 `tests/setup-fetch-guard.spec.ts` 三发：基址断言 = `http://localhost:3200`、
     未桩 fetch rejects `/S35\.4 fetch-guard/`、自桩 `stub-ok` 优先。
- 改后：`pnpm test:unit` ⇒ **415 passed (415)，AggregateError/ECONNREFUSED 计数 0**（grep 计数现读）。
  39 处的调用方本就自带吞错路径（组件级 catch）⇒ 换成撞 guard 抛错后路径不变、静默依旧，
  但**网络包一次都不发**且任何断言想咬它就能咬到（抛错可断言，AggregateError 不可）。
- 反证（卡面"删一条桩该用例必须红"）：临时删 `setup-fetch-guard.spec.ts` 第②③发里自桩那发的
  `vi.stubGlobal` ⇒ 该发红（1 failed / 2 passed）；还原 ⇒ 3 passed。变异前后读数在本节。
- `pnpm typecheck`（tsc --noEmit）与 `pnpm lint`（ESLint）均 0 错。

## S35.5 未认证 + 非法体的常驻判据（P-111② / D-V19-08，V0.19 加项）

- 新增 `test_validation_no_echo.py::test_unauthenticated_invalid_body_is_401_and_never_echoes`：
  `create_app()` **不覆盖任何依赖**（真实依赖链）打三个真端点
  （PUT admin/discovery/config、PUT admin/categories、POST extract），体是**类型错误 + 运行时随机值**
  （随机值藏在 pydantic 会抄进 `input` 的位置——旧 422 文案的泄漏向量）。
- 断言：三发全 401 / `code=10001`，随机值不在响应体与 `capture_logs` 的任何一行。
- 注释写明（卡面要求）：**绿是因为鉴权在校验之前**——哪天体校验被挪到鉴权前，这发就 422 且值泄漏 ⇒ 红。
- 本机：该文件 14 passed。

## S35.6 墙钟分支普查（P-116 遗留，V0.20 加项）

`rg "datetime\.now\(|time\.time\(|date\.today\(" apps/api/app/` = **41 处**（清单原样入证）。逐点判定（分三类）：

| 类 | 点 | 判定 |
|---|---|---|
| **值型**（时间作为数据写入，不选分支） | `api/v1/chat.py:446`、`bots.py:304/438/508`、`system.py:485`、`core/audit.py:105`、`core/alerting.py:133`、`core/security.py:314`、`push/dingtalk.py:50`、`push/feishu.py:40`、`repositories/job.py:137/146/177`、`services/article_detail_fallback.py:197`、`job_worker.py:323/441`、`push_events.py:110`、`push_scheduler.py:80`、`kb.py:741`、`push_template.py:27`、`process_heartbeat.py:148`、`scheduler.py:339`、`auth/logout_token.py:126/134/216`、`auth/service.py:136/162`、`system_settings.py:362/381`、`hot.py:71/72/165/282`、`hot_cluster.py:217`、`hot_scorer.py:101` | 不构成"随墙钟取不同分支"；其中 `bots.py` 三处的 `parse_cron_next(cron, now)` 下游值随 now 变，但其所在模块不在模块门九行跟踪面内 |
| **已冻结覆盖** | `subscription.py:618/625`（`_next_anchored_run` 两分支） | STEP-45 的 `test_subscription_anchor_clock.py` 已用固定时钟钉 00:22 / 10:00 / 15:00 三态 ⇒ **S35.6 的"03:00 与 15:00 两侧"判据已满足** |
| **值型（参数可注入）** | `subscription.py:505/509/513`、`scheduler.py:409/470`、`manifest.py:396` | `now` 只参与 `next_run_at`/idempotency-key/日志字段的**取值**；分支选择由入参（`sync_anchor_hour`/`clear_anchor`/`now_fn`）决定，与时刻无关。`scheduler.py:409/470` 的分支随 now 落哪一天可变，但该模块不在九行跟踪面内，登记为观察项 |

结论：跟踪面（九行）内的墙钟分支在 STEP-45 之后仅剩取值型；`manifest.py:169` 的抖动与墙钟无关
（是覆盖路径缺口，S35.1 已钉死）。

## 本机全量与连库面声明

连库面（S35.2 三发、S35.3 调度器一发）本机未跑（无 PG）——以 @ci 为准。本机不连库全量 + 上述各文件单项读数见各节。

## 第 2 轮（@ci 抓出的两件事）

1. **CI-Windows 40010753538 = failure**：`windows-dev` 的 Windows skip 门禁
   `failed=0 total_skipped=669 baseline=666`——本卡新增的 3 条 subscription 连库用例
   在 @win 以「PG-DSN-未设置」族 skip（族内 557→560），我漏抬 `SKIP_BASELINE_WIN`
   （提示词 §5 的既有纪律）。修法：抬到**测量值 669**（零余量），构成注释重算入注
   （调度器并行用例是改写非新增，不进账）。
2. **S35.1 三连跑对照的剩余抖动**：同 run 40010753485 三次 attempt（同一棵树）
   TOTAL 88.26% / 88.34% / 88.37%——八行跟踪模块已逐字相同（manifest 稳在 219/230、
   subscription 稳在 363/412），逐模块差分（attempt1 vs 2 的全量 term-missing 表）
   唯一漂移模块 = **`app/services/scheduler.py`**（missing 75↔67）：
   `_maybe_enqueue_daily_jobs` 用不可注入的 `datetime.now(self._tz)`（:409），
   06:30/06:35 两个门随 CI 跑的时刻开合；reconcile 默认实现体随同批遗留 DB 状态漂。
   修法（测试侧，源码零改动）：冻结模块级 datetime 三发 + reconcile 两态一发
   （`test_scheduler.py` 新增 4 条连库用例，会随第 2 轮推送在 @ci 复算）。
   三连跑九行对照原文：`s35_1_threerun.txt`（attempt 2/3 九行已逐字相同——
   这两 attempt 恰好都落在门关侧；attempt 1 在另一时刻 ⇒ 暴露出 scheduler 漂移）。

## @ci（推送后回填）

_（占位：交付 head 三绿 run id；subscription.py 模块门行（余量行数）；S35.1 的三次派发跑九行对照；S35.3 调度器用例与 S35.2 三发 @ci 实跑读数。）_
