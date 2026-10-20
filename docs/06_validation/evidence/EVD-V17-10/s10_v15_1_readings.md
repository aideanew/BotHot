# EVD-V17-10：STEP-10 S10.V15.1 详情兜底接进入库链路（V0.17.0 队列⑥）

- 日期：2026-10-20（Asia/Shanghai）
- 基线：`main@8367b77`（STEP-04 S4.5.1 记录提交）
- 卡面：`docs/任务规划V0.15.0/steps/STEP-继承卡增量-V15.md` §「STEP-10 +2」S10.V15.1；
  原卡 `docs/任务规划V0.13.0/steps/STEP-10-详情兜底接线与付费预算护栏.md`（S10.1.1 接线，
  §3 执行逻辑「`_resolve_with_retry` 失败（可兜底类）→ coordinator」）
- 裁决：D-V12-13（付费兜底接入但默认关、永远先免费直抓）
- 环境：Win10 + Git Bash；`apps/api/.venv` Python 3.12.10；`PYTHONUTF8=1`；
  隔离 PostgreSQL 16.4（`127.0.0.1:5547/bothot_test`）；Redis/LangBot 未起；付费 API 全部计数桩。

## 1. 先红（改前，业务代码一行未动）

命令：

```bash
cd apps/api
python -X utf8 -m pytest tests/test_detail_fallback_wiring.py -q -rs
```

读数：`8 failed in 1.79s`（当时 8 条；`test_fallback_body_survives_extractor_and_quality_gate`
与 `test_fallback_page_html_is_not_double_wrapped` 是接线落地后补的两条形状用例，见 §3b，
它们在 §4 的变异上同样红）。两类红因：

（a）调用图证明——全仓 `ArticleDetailFallbackCoordinator` 实例化 0 处：

```text
>       assert hits == [("services/job_worker.py", 1)], f"协调器实例化面={hits}"
E       AssertionError: 协调器实例化面=[]
```

```text
>       assert len(_coordinator_calls(func)) == 1, "make_default_ingest 未实例化协调器"
E       AssertionError: make_default_ingest 未实例化协调器
```

（b）其余 6 条红在装配点不存在：

```text
E       TypeError: KnowledgeBaseService.__init__() got an unexpected keyword argument 'detail_fallback'
```

改前现读核对：`article_detail_fallback.py:49` 定义协调器、`:56` 只出现在 docstring 用法示例里；
`config.py:110` 开关默认 `False`；`kb.py`/`job_worker.py`/`api/deps.py` 无任何实例化
⇒ 与卡面「Coordinator 全仓 0 处实例化」一致。

## 2. 实现（两个文件，最小改动，零迁移零契约）

- `apps/api/app/services/kb.py`
  - `:29` 引入 `ExtractFailedError`；`:52` `TYPE_CHECKING` 下引入协调器类型；
  - `:79` `KnowledgeBaseService.__init__` 末位新增可选参数 `detail_fallback`（默认 `None`），
    `:88` 存入 `self._detail_fallback` ⇒ 既有三处构造点（`api/deps.py`、`scheduler.py`、测试）零变更；
  - `:354-372` `_resolve_with_retry` 重试环之后：仅当末次异常是 `ExtractFailedError`
    （`source_resolver.py:242/:244`：网络异常或非 200，即免费直抓的失败形态）且注入了协调器时
    才调 `fetch_detail`；拿到非空正文才合成 `ResolvedArticle` 返回，否则原样上抛。
    域错误（`SourceUrlUnrecognizedError`/`ExtractQualityLowError`）与本仓 bug（`RuntimeError`）不兜底。
- `apps/api/app/services/job_worker.py`
  - `:171` 函数内引入协调器；`:182` 在 `make_default_ingest` 里**装配一次**（不是每篇一次）；
    `:192` 以 `detail_fallback=detail_fallback` 注入 `KnowledgeBaseService`。
  - 协调器 `__init__` 读 `settings.article_detail_fallback_enabled`（默认 `False`）：关时连
    `_init_providers()` 都不执行 ⇒「配了 key」≠「启用兜底」被用例钉住（§3 第一行）。

## 3. 改后读数与三档付费调用计数

```bash
cd apps/api
python -X utf8 -m pytest tests/test_detail_fallback_wiring.py -q        # 无 DSN
```

```text
10 passed in 1.07s
```

provider 用 `_CountingProvider` 计数，全程不发真实请求：

| 场景 | 免费直抓 | 开关 | provider 装配 | 付费调用次数 |
|---|---|---|---|---|
| 关 + 配了 key | 失败（`ExtractFailedError`） | False | 工厂 0 次调用 | **0** |
| 开 + 免费成功 | 成功 | True | 工厂 1 次 | **0** |
| 开 + 免费失败 | 失败 | True | 工厂 1 次 | **恰 1**（dajiala 命中即止，justoneapi/tikhub 各 0） |

另三条极性用例：兜底未命中 ⇒ 原样上抛 `ExtractFailedError`（不许伪装成功，付费仍只 1 次）；
非直抓异常（`RuntimeError`）⇒ 付费 0 次（不拿花钱掩盖本仓 bug）；
注入点存在性 ⇒ `svc._detail_fallback` 就是传进来的那个对象。

## 3b. 接线过程中抓到的形状洞（改前不存在、改后必须判）

`ExtractorService.extract()`（`app/services/extractor.py:298`）只喂
`re.search(r'<[^>]*id="js_content"[^>]*>(.*)')` 命中的区段，未命中即 `body=""` ⇒
`extractor.py:305` 直接抛 `ExtractQualityLowError("正文为空…")`。
而付费详情的 `ArticleDetail.content_html` 是**正文片段**（`dajiala.py:128` 取 `data.html`），
不带页面容器 ⇒ 第一版接线（只做 `html=detail.content_html`）虽然 `_resolve_with_retry` 返回了正文，
下游仍会在评分前 20003 终止：**接线等于白接，用户侧症状从 20002 换成 20003**。
补的这层容器（`kb.py:361-362`）只在缺失 `js_content` 时套一次，provider 给整页形态时不重复套
（`test_fallback_page_html_is_not_double_wrapped`）。
这条洞是由 §3 的 `test_fallback_body_survives_extractor_and_quality_gate`
（真过一遍清洗 + 评分，断言 `verdict.passed`）先红出来的，不是事后补的说明。

## 4. 反证（三个变异，各改一行、跑完立即还原）

| # | 变异 | 读数 | 还原后 |
|---|---|---|---|
| M1 | `kb.py:355` 兜底条件前置 `if False and …`（摘掉触发点） | `4 failed, 6 passed`：`test_flag_on_free_failure_spends_exactly_one_paid_call`（`assert 0 == 1`）、`test_flag_on_fallback_miss_re_raises_the_free_error`、`test_fallback_body_survives_extractor_and_quality_gate`、`test_fallback_page_html_is_not_double_wrapped`（三条都红在 `ExtractFailedError` 未被兜住） | `10 passed in 1.07s` |
| M2 | `job_worker.py:192` 删 `detail_fallback=detail_fallback,`（摘掉装配点） | `1 failed, 9 passed`：`test_default_ingest_hands_the_coordinator_to_the_kb_service` ⇒ `协调器没有以 detail_fallback= 注入 KnowledgeBaseService` | 同上 |
| M3 | `kb.py:361` 容器补齐条件改 `if False and …`（摘掉 js_content 包装） | `2 failed, 8 passed`：`test_fallback_body_survives_extractor_and_quality_gate` 红在 `ExtractQualityLowError: [20003] 正文为空`；`test_flag_on_free_failure_spends_exactly_one_paid_call` 红在 html 形状 | 同上 |

M1 与 M2 各只咬一层（触发 / 装配），M3 咬住 §3b 的容器层 ⇒ 用例集不是只测一面。
`git diff HEAD` 已确认三处变异全部还原。

## 5. 相关回归（真库，一条命令跑完）

```bash
cd apps/api
AIDEANBOT_TEST_PG_DSN=... python -X utf8 -m pytest tests/test_kb_resolve_retry.py tests/test_langbot.py \
  tests/test_d04_short_link.py tests/test_kb_longlink_ingest.py tests/test_kb_multisource_anchor.py \
  tests/test_kb_orphan_purge.py tests/test_job_worker.py tests/test_w2_worker.py \
  tests/test_be02_engine_routing.py tests/test_provider_defects_p15_p17.py -q -rs
```

```text
106 passed, 1 warning in 26.90s
```

`test_kb_resolve_retry.py`（重试语义 3 条）与 `test_provider_defects_p15_p17.py`（P-15/16/17 极性）
都在列且全绿 ⇒ 兜底没有改变重试口径，也没有碰 provider 的降级/抛穿分界（本卡不改 provider 一行）。

## 6. lint / 类型 / 迁移 / 契约门

- `ruff check app tests` → `All checks passed!`（rc=0）
- `mypy app` → `Success: no issues found in 115 source files`（rc=0）
- `alembic heads` → `ab1006c1a (head)` 单头（本卡 0 迁移）
- `python scripts/gen_contracts.py --check` → 12 项产物全部 `幂等一致`，rc=0（本卡 0 契约变更；
  输出里的 `alembic head 探测失败` 警告是 `schema_guard` 在仓库根按相对路径探测所致，不参与判定）

## 7. 全量读数与三 CI

### 7.1 真库全量（@linux 口径的本机等效，隔离 PG16@5547）

```bash
cd apps/api
AIDEANBOT_TEST_PG_DSN=... DATABASE_URL=... python -X utf8 -m pytest tests/ -q -rs \
  --junitxml=/d/tmp/s10_pytest_report_realdb.xml
```

```text
2028 passed, 6 skipped, 1 warning in 895.32s (0:14:55)
REALDB_RC=0
```

skip 构成与基线同族（LangBot/Redis 不可达 5 条 + 代理对照 1 条），`pg_unreachable=0`。

⚠️ **本卡有一次量错要留在账上**：这条读数之前先跑过一次，输出是
`1 failed, 2027 passed, 6 skipped in 900.76s`，但当时我把命令写成
`… | tee file | tail -12`，**失败用例名被自己的 `tail` 截掉了**，事后无法归因。
定向复现尝试（真库）：`test_run_once_runs_due_subscriptions_in_parallel` 单跑 1 passed，
`tests/test_scheduler.py` 连跑 3 次 `22 passed`（这是本套件唯一在案的负载敏感项 P-52），
其余无候选 ⇒ 那 1 条失败**未判定到具体用例**。随后带 junit、日志全文留盘的复跑为
`2028 passed / 6 skipped / 0 failed`（上方），无 DSN 形状也是 `0 failed`。
纪律更正：全量复跑一律 `> 文件` 留全量日志 + junit，不再挂 `tail` 管道。

### 7.2 CI-Windows 同形状全量（无 DSN，`--no-header -o faulthandler_timeout=120 --timeout=300 --timeout-method=thread`）

```text
1463 passed, 571 skipped, 1 warning in 1033.99s (0:17:13)
WIN_RC=0
```

junit 汇总：`tests=2034 errors="0" failures="0" skipped="571"`。
与基线（STEP-31 交付时 `1453/571`）逐项对齐：passed `+10`（本卡新增 10 条，全部不连库）、
skipped 不变 **571** ⇒ `SKIP_BASELINE_WIN` 保持 571，不动阈值。

### 7.3 三 CI

（待回填）

## 8. 边界与如实未测

1. **预算护栏未接线**：卡面判据「恰 1 次且受预算护栏约束」只满足前半。后半属原卡
   S10.2.1/S10.2.2（`paid_call_budget.py` 按渠道日计数 + 每次付费前 `acquire`），有两个硬前置未满足：
   ① S10.2.2 依赖 S8.3（STEP-08 未做，排在队列⑫）；② S10.2.1 要 PG 计数表，而 STEP-10 卡面字段 13
   「禁止修改：迁移目录（需 DDL 停转 ADR）」⇒ 无迁移号可用（V0.17 序列表里 08 持 `ab1006c2a`、
   28 持 `ab1006c4a`，都不归本卡）。
   ⇒ 本卡只把 `kb.py:356` 留成**唯一付费调用点**（未来 `acquire` 的前置位置），
   **预算读数记「未测」，不写 0**；请规划方裁定 S10.2 的落地次序或给出迁移号。
2. **触发面只覆盖「直抓 HTTP 失败」**：协调器 docstring 另列的「正文为空（`ExtractQualityLowError`）」
   发生在 `_ingest_url_inner` 抽取评分之后、验证码类属上游形态判定，本次未接
   （原卡 §3 也只写 `_resolve_with_retry` 失败）；触发条件可配置属 S10.V15.2（依赖 STEP-28）。
3. **只接 worker 链路**：注入点写在 `make_default_ingest`（V15.1 原文「`job_worker` → `kb.ingest_url`」）。
   HTTP 贴链接路径（`api/deps.py:169`）与 `scheduler.py:195` 的构造点仍传 `detail_fallback=None`
   ⇒ 开关打开也不会付费。若规划方要 API 侧也兜底，是「把付费调用放进用户同步请求路径」的裁决点，
   不在本卡偷做。
4. **付费接口零真实调用**：provider 全为计数桩，未使用任何真实 key、未产生费用；
   四家平台 key 的可用性不在本卡判定范围（活体读数归 STEP-03/20 在案证据）。
5. **未新增连库用例** ⇒ `SKIP_BASELINE_WIN` 维持 **571**：新用例 10 条全部不连库，
   无 DSN 也执行（§3 读数即无 DSN，0 skip）。
6. P-50 / P-51 / P-52 未动；本卡未新增 P 项（§3b 的洞是**本卡自己接线时**引入即修的形状问题，
   改前不存在付费兜底路径，故不构成存量缺陷登记）。
