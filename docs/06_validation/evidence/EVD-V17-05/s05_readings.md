# EVD-V17-05：STEP-05 采集静默告警与可观测（V0.17.0 队列⑦）

- 日期：2026-10-20 → 2026-10-21（Asia/Shanghai）
- 基线：`main@2f1a006`（STEP-10 记录提交）
- 卡面：`docs/任务规划V0.13.0/steps/STEP-05-*` ← 源卡 `docs/任务规划V0.7.0/steps/STEP-05-采集静默告警与可观测.md`；
  排程依据 `docs/任务规划V0.13.0/09-剩余任务原子化大纲与执行序.md` E-13（P-9 与 P-30 同卡）
- 冻结契约真源：`app/contracts/collection.py:176`（`all_skipped_pages`）、`:210-233`（`CollectionEvent`
  的 `discovery.page_all_skipped` 与 page 级幂等键）、`:204-207`（`lastSuccessAt`/`lastError`，COULD）
- 环境：Win10 + Git Bash；`apps/api/.venv` Python 3.12.10；`PYTHONUTF8=1`；隔离 PG16@5547；
  Redis/LangBot 未起；**告警投递全部换桩，未真发一条**（`alerting._deliver` 被 monkeypatch）。

## 0. 现读（写代码之前）

| 事实 | 读数 |
|---|---|
| `alerting.py` 的告警种类 | 只有心跳/积压/推送连败三类（`:122/:132/:138`），无采集维度 |
| `metrics.py` 指标族 | 6 族（`:55-84`），无发现链路维度 |
| `_map_row → None` 的静默面 | 有计数（`report.skipped`）但**没有页级判定**，也没有指标/告警 |
| `ManifestSyncReport`（pydantic 视图） | 冻结稿已声明 `all_skipped_pages`（`collection.py:176`），**dataclass 里没有这个字段** ⇒ 稿与实现漂移，本卡把它接上 |
| `P-30` 的吞异常出口 | `push_scheduler.py` 的 `except Exception:` 只 `logger.warning`，无计数 |
| `P-9` 的置空点 | `push_events.py` `_hydrate_payload` 内 6 处置 `""`（`:41/:45/:46/:47/:52/:53/:65`），无日志无计数、连 `logger` 在本函数都没用过 |
| 跨进程拓扑 | 发现同步只在 **scheduler 进程**（唯一生产调用点 `scheduler.py:139`）；`run_alert_checks` 与 `/metrics` 只在 **backend 进程**（`push_scheduler.py:92` ← `main.py:274`）⇒ Prometheus 注册表进程内私有 |

拓扑这一条决定了设计：静默信号里**只有库里那半**能被 backend 探测到，
所以本卡把「连续 N 轮零新增」读 `source_subscriptions.consecutive_empty_syncs`（既有列，
`entities.py:93`，**零迁移**），把「整页全丢弃」由同步进程当场交 `alerting.notify_discovery_event` 投递。

## 1. 先红

命令：

```bash
cd apps/api
python -X utf8 -m pytest tests/test_discovery_silence_alert.py -q -rs
```

读数：`11 failed, 1 passed in 1.08s`。
唯一绿的那条是极性用例 `test_alerting_disabled_delivers_nothing`（总开关关 ⇒ 不投递，
改前本来就不会投，必然成立）。红因两类：

- 机制不存在：`指标族未注册：bothot_discovery_calls_total`、`AttributeError: module 'app.core.alerting' has no attribute 'check_discovery_silence'`、
  `TypeError: _counter() ...`（P-9/P-30 两族同理）；
- 形状漂移：`test_report_carries_the_two_alert_bearing_counters_of_the_frozen_view`
  红在本地 dataclass 没有 `all_skipped_pages`（冻结稿有 ⇒ 稿在说、代码没做）。

## 2. 实现

### 2.1 `app/core/metrics.py`（S5.2.1）

新增 6 族 + 6 个记录函数（`record_*`，与既有 `record_push_outcome` 同形态）：

| 指标 | 类型 | 标签 |
|---|---|---|
| `bothot_discovery_calls_total` | Counter | channel, outcome(success/failed) |
| `bothot_manifest_rows_total` | Counter | channel, result(discovered/updated/unchanged/dropped/fallback) |
| `bothot_discovery_page_all_skipped_total` | Counter | channel |
| `bothot_discovery_last_success_timestamp` | Gauge | channel |
| `bothot_event_payload_empty_total`（P-9） | Counter | name, field |
| `web_notification_persist_failed_total`（P-30） | Counter | reason |

模块 docstring 里补了**进程边界**一节：这四族只在跑同步的进程里有值，backend 的 `/metrics`
看不到它们；`bothot_jobs_by_status` 之所以能看到，是因为它在抓取时回读 Postgres。

### 2.2 `app/services/manifest.py`（S5.2.2）

- `WorkListProvider` 协议加 `name`（声明成只读 `@property`：`RSSFeedProvider` 就是属性实现，
  写成可变属性协议会拒收 ⇒ mypy 实测报过）；
- `ManifestSyncReport` 补 `all_skipped_pages`；
- `sync_source` 按页埋点：调用结果（成功/失败各一计数，失败**照抛**）、行结果五类、
  整页全丢弃判定 `page_rows and page_dropped == page_rows`；
- 判定命中后三步都做：`report.all_skipped_pages += 1`、`record_discovery_page_all_skipped`、
  `logger.error("discovery.page_all_skipped", …)` + `await notify_discovery_event(CollectionEvent(…))`；
  事件载荷直接用**契约模型** `CollectionEvent` 构造（不是自造 dict），
  页级键由 `alerting.discovery_idempotency_key` 生成，形状 `{source_id}:{channel}:{yyyymmdd}:{page}`；
- 词表外的渠道名（provider 没登记 `name`）只出声不投递，避免拿假渠道污染标签体系。

### 2.3 `app/core/alerting.py`（S5.1.1/S5.2.3）

- `DISCOVERY_TZ = Asia/Shanghai`（业务日界与全仓一致；否则跨零点会算成两天、同一件事报两遍）；
- `_FIRED_DAYS` + `allow_daily_alert()`：日幂等门；`reset_alert_cooldown_state()` 一并清空，
  既有 `test_alerting_default.py` 的隔离夹具不用改就能罩住新状态；
- `discovery_day_key()`（告警级 `{source_id}:{channel}:{yyyymmdd}`）与
  `discovery_idempotency_key()`（事件级，多一段 `:{page}`）——两级都要，理由写在 docstring；
- `notify_discovery_event(event)`：按告警级键一天一次，正文只含标识（不含上游响应原文、不含凭据）；
- `check_discovery_silence(session, *, threshold)`：读库，SQL 只取「ACTIVE 且计数非零」，
  **阈值比较放 Python**（写进 SQL 也能跑，但那条判据就脱离了可验证面——桩会话不执行 WHERE）；
- `run_alert_checks` 加第 4 块独立 try，阈值 env `ALERT_DISCOVERY_SILENCE_ROUNDS`（默认 3），
  沿用既有纪律：`ALERTING_ENABLED` 非真直接返回空。

### 2.4 P-9 / P-30（卡面所有权外的必要行）

- `push_events.py`：新增 `_count_empty()`，在三条分支末尾对**每个最终为空的模板变量**
  计一次 `bothot_event_payload_empty_total{name,field}` + 一条 `logger.warning("push_event.payload_empty", …)`。
  置空语义一个字没改（仍置空、仍发事件）；日志只报字段名不报值。
- `push_scheduler.py`：`except Exception as exc:` 里加一行 `record_web_notification_persist_failed(type(exc).__name__)`。
  吞异常仍是取舍，补的只是"吞了"的可观测面。
- 两文件不在 STEP-05 卡面所有权（W：metrics.py、alerting.py、manifest.py、registry.py、新用例、web 面板）内，
  但 E-13 明写「P-9 与 P-30 在这一张卡里一起做」⇒ 按提示词第四节「卡面增量」只加必要行并在此留证。
- `providers/redfox/client.py`：`RedfoxClient` 加类属性 `name = "redfox"`（同为卡面增量，
  没有它 redfox 渠道的指标标签会落成 `unknown`）；`providers/article_sources/rss.py` 只改了 docstring 一行。

### 2.5 零迁移、零契约产物变更

`alembic heads` → `ab1006c1a (head)` 单头；`gen_contracts --check` → 12 项 `幂等一致`，rc=0
（本卡没动任何 pydantic 请求/响应模型；`all_skipped_pages` 是**补齐实现**，不是改稿）。

## 3. 改后读数

```bash
python -X utf8 -m pytest tests/test_discovery_silence_alert.py -q
```

```text
14 passed in 1.96s
```

覆盖面：4 族指标出现在 `/metrics` 文本里；整页丢弃的**计数 + ERROR 事件 + 契约载荷 + 告警**；
同日重复被日幂等挡住；行结果五类分别计；调用失败计数后仍上抛（不吞）；
P0-3 回放（见 §4）；探测阈值判定；`run_alert_checks` 接线；总开关关 ⇒ 零投递；
P-9 两个字段各自计数且有结构化日志；P-30 计数不破坏回执路径；
日界键按业务时区（§3b）。

## 3b. 本卡自己踩的两个红，与其中一个抓出的真缺陷

全量复跑里第一次无 DSN 批红了 **我自己的** 用例，读数
`1 failed, 1475 passed, 571 skipped in 1033.21s`：

```text
>       assert event.idempotency_key == f"{_SOURCE}:redfox:{_page_date()}:1"
E       AssertionError: assert 's05-source-1...ox:20261020:1' == 's05-source-1...ox:20261021:1'
```

1. **测试自己的错**：期望值是在动作之后**第二次**取当天日期算的，而这轮全量从 23:59 跑到
   00:0x，跨了业务日界 ⇒ 断言要求事件携带"一天之后"的日期。修法：期望值改从
   事件自带的 `at` 推出来（`event.at.astimezone(DISCOVERY_TZ)`），不再二次取时。
2. **改法带出的真缺陷**：为了钉住这条判据新增 `test_day_key_uses_the_business_day_boundary_not_utc`
   （UTC 10-20 17:00 = 上海 10-21 01:00），它在**实现**上红了：
   `alerting.discovery_day_key` 原来是 `(at or now(TZ)).strftime("%Y%m%d")`——
   aware datetime 的 `strftime` 打的是它**自带偏移**的字段、不做换算，
   于是拿 UTC 时刻建的键就按 UTC 切日 ⇒ 跨零点的同一件事会被算成两天各投一次，
   「一天一次」在真实部署（`at = datetime.now(UTC)`）下根本不成立。
   修为 `at.astimezone(DISCOVERY_TZ)` 后再 `strftime`（`alerting.py:123-133`）。
   这条红不是事后补的说明：§5 的 M4 把换算摘掉，现在仍稳定复现 `2 failed`。

## 4. P0-3 回放（卡面 §1 的可证伪要求）

`test_p0_3_replay_alert_fires_on_the_pre_step_03_mapping`：输入用**今天会被兜底收下**的形状
（有 URL 无 id），把 `manifest._map_row` 临时退回 STEP-03 之前（缺 id 即丢整行），
断言 `report.all_skipped_pages == 1` 且告警投出 1 条。
⇒ 告警不是只对本卡随手造的脏行有效，它对「上游返回正常而本仓零入库」那一整族有效。

## 5. 反证电池（6 条，各改一行，跑完还原并核字节）

电池脚本每条都先断言锚点命中次数恰为 1、跑完按字节比对还原（防"改完没改回来"）。

| 变异 | 读数 | 还原 |
|---|---|---|
| M1 `manifest.py` 整页判定前置 `if False and …` | `3 failed, 11 passed` | 字节一致 |
| M2 `alerting.py` 日幂等门 `if key in _FIRED_DAYS:` → `if False:` | `2 failed, 12 passed` | 字节一致 |
| M3 `alerting.py` 探测去掉 `>= threshold` 过滤 | `1 failed, 13 passed` | 字节一致 |
| M4 日键退回不换算（`at.astimezone(TZ)` → `at`） | `2 failed, 12 passed` | 字节一致 |
| M5 `push_events.py` `_count_empty` 循环源改 `()` | `1 failed, 13 passed` | 字节一致 |
| M6 `push_scheduler.py` P-30 计数改 `pass` | `1 failed, 13 passed` | 字节一致 |
| 对照组（未变异） | `14 passed` | — |

M1/M2/M3 各咬一层（判定 / 幂等 / 阈值），M4 咬住 §3b 的时区换算，M5/M6 咬住两个可观测出口。
电池脚本是临时件，跑完即删（不入库，避免把 scratch 带进证据包）。

## 6. 相关回归

```bash
python -X utf8 -m pytest tests/test_admin_push_persists_notification.py tests/test_alerting_default.py \
  tests/test_alerting_drill.py tests/test_collection_contract.py tests/test_direct_push_persists_notification.py \
  tests/test_discovery.py tests/test_discovery_silence_alert.py tests/test_manifest_asset_alignment.py \
  tests/test_manifest_state_machine.py tests/test_manifest_sync.py tests/test_notification_frame_id.py \
  tests/test_notification_history.py tests/test_observability.py tests/test_push_persist_order.py \
  tests/test_w3_push_scheduler.py tests/test_wb_push_hardening.py -q -rs     # 真库，按字母序
```

```text
354 passed, 1 warning in 37.01s
```

（时区修正后复跑；修前同一集合是 `352 passed`——多出的 2 条是 §3b 的新用例与它替代的那条。）

⚠️ 这批里有一次**我的顺序造成的假红**要留在账上：第一次我用自己给的顺序跑同一集合，
得 `2 failed, 338 passed`——`tests/test_observability.py` 里 5 处
`blog.configure_logging(force=True)` 装完全局 structlog 后没有还原，把排在它**之后**的
`caplog` 用例瞎掉（`test_discovery.py` 两条红在 `caplog.text` 为空串）。
反证：`pytest tests/test_discovery.py tests/test_observability.py -q` ⇒ `35 passed`；
探针也否证了我的第一个假设（`configure_logging(force=True)` 之后 `capture_logs()` 仍然捕得到，
打印 `[{'rows': 1, 'event': 'probe.event', …}]`），真因是 stdlib `logging` 路由被重装、
pytest 的 `caplog` 因此失明。CI 与本机全量都按字母序 ⇒ 今天不红，属**潜伏**，
已登记 **P-53**（归 00R/00T 用例密封面，本卡未授权改那个文件，登记不修）。

## 7. 全量读数与三 CI

### 7.1 真库全量（隔离 PG16@5547，`pytest tests/ -q -rs --junitxml=…`）

第一次（时区修正**之前**）：

```text
1 failed, 2040 passed, 6 skipped, 1 warning in 900.06s (0:15:00)
```

失败用例有名有姓（这轮日志全文留盘，不再犯 STEP-10 那次被 `tail` 截掉名字的错）：

```text
______________ test_run_once_runs_due_subscriptions_in_parallel _______________
>           assert a1 < b0, f"两次同步未重叠（串行）：{spans}"
E           AssertionError: 两次同步未重叠（串行）：[(570112.1953399, 570112.2559764), (570112.3226138, 570112.3788131)]
```

⇒ 已登记的 **P-52** 第二次复现（第二段起点比第一段终点晚 67ms），与本卡改动无关
（`test_scheduler.py` 不碰 metrics/alerting/manifest）。读数已补进 P-52 的证据栏。

修正后复跑：

```text
2042 passed, 6 skipped, 1 warning in 897.97s (0:14:57)
REALDB_RC=0
```

总数核对：STEP-10 基线 2034（2028+6）+ 本卡 14 条 = 2048；`2042+6=2048` ✅，
skip 构成与基线同族（LangBot/Redis 不可达 5 + 代理对照 1），无 "PG 不可达" 类。

### 7.2 CI-Windows 同形状（无 DSN，`--no-header -o faulthandler_timeout=120 --timeout=300 --timeout-method=thread`）

第一次（红在自己用例，见 §3b）：`1 failed, 1475 passed, 571 skipped in 1033.21s`。

修正后复跑：

```text
1477 passed, 571 skipped, 1 warning in 1033.91s (0:17:13)
WIN_RC=0
```

junit 汇总：`tests=2048 skipped=571 failures=0 errors=0`。
skipped 与基线**逐字相同（571）** ⇒ 本卡 14 条用例全部不连库，
`SKIP_BASELINE_WIN` 维持 **571**，不抬阈值。

### 7.3 三 CI

交付提交 `d19b9ab`（`feat(STEP-05 S5.1.1-S5.2.3 第 1 轮): 采集静默告警与可观测上线（四族指标 + 日幂等告警）`）：

| 工作流 | run id | 结论 | 关键读数 |
|---|---:|---|---|
| CI | 39465006493 | ✅ success | backend `2042 passed, 6 skipped, 1 warning in 170.45s`；覆盖率 **87.37%**（门槛 75%）；skip 门禁 `total_skipped=6 baseline=6 pg_unreachable=0` |
| CI-Windows | 39465006658 | ✅ success | backend `1477 passed, 571 skipped, 1 warning in 1012.29s (0:16:52)`；门禁 `windows 门禁：failed=0 total_skipped=571 baseline=571` |
| Security | 39465006563 | ✅ success | 全 job success |

ubuntu `2042/6` = 本机真库 `2042/6`；CI-Windows `1477/571` = 本机无 DSN 同形状 `1477/571`；
门禁基线 571 未抬（本卡 0 连库用例）。

## 8. 未做的事与如实未测

1. **S5.3.1 / S5.3.2（卡面标 COULD）未做**，且判定为"现在做必然做成假可用"：
   `describe_channels` 由 backend 进程服务（`admin.py:493`），而 `bothot_discovery_last_success_timestamp`
   只在 scheduler 进程被写 ⇒ 面板上 `lastSuccessAt` 恒为空；库里只有
   `source_subscriptions.last_success_at`（**按订阅**，不带渠道维度），聚合成"按渠道"是假归属。
   要真做需要 ① 发现侧写一张 per-channel 成功/错误表（DDL ⇒ 需 ADR + 迁移号），或
   ② 让 scheduler 也暴露 `/metrics` 并由 backend 联邦抓取（基础设施改动，不在任何卡的允许面）。
   ⇒ 两个 L4 交回规划方裁定；本卡不为了"7 项齐"而先把字段填成永远为空。
2. **告警未接外部 IM 渠道**：沿用既有 `ALERT_CHANNEL`（默认 `web` 站内通知），
   卡面 §6 本就写明"本卡不接外部 IM 渠道以外的投递"。真实投递未测（本卡零真发）。
3. **`/metrics` 的跨进程可见性未测**：见 §0 拓扑与 §8.1；本卡只判"名称出现在同一进程的
   `/metrics` 文本里"，没有声称 backend 能看到 scheduler 的计数。
4. 未新增连库用例 ⇒ `SKIP_BASELINE_WIN` 维持 **571**（14 条新用例全部不连库，无 DSN 也跑，见 §7.2）。
5. P-50 / P-51 / P-52 未动；本卡新增 **P-53**（§6）。
