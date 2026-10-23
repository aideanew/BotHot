# EVD-V17-12 — STEP-12 文档对账、证据汇总与发布就绪报告

执行机标签：`@win`（除 §5 的 CI 读数外全部本机现跑）。
锚定提交：`main@9983c63`（STEP-00E 交付批）。采集时间：2026-10-23（Asia/Shanghai）。
卡面：`docs/任务规划V0.13.0/steps/STEP-12-文档对账证据汇总与发布.md`（三级任务全文见 V0.7.0 来源卡）。

> **本卡的交付边界（写在最上面，因为它决定这份文件怎么被读）**：
> STEP-12 只做**对账与证据**。**发布动作**（把 `CHANGELOG.md` 的 `[Unreleased]` 落成版本号、
> 打 tag、推 tag）**不在交付范围内，也不由执行方决定**——队列指令原话是"只出对账与证据，发布由用户拍板"。
> 因此本文件 §6 的产物是"就绪判定 + 必须人拍板的三件事"，不是"已发布"。

## 0. 现读锚（每一条都重新量过，不引用上一版）

| 探测 | 读数 |
|---|---|
| `git tag -l` | `local-recovery-42a21f2`、`local-recovery-6751185`、**`v1.0.0`**（无 v1.1.0） |
| `git rev-list --count v1.0.0..HEAD` | **291** |
| tag `v1.0.0` 落点 | `c19fe87`，2026-10-08，`docs(release): v1.0.0 账本终稿` |
| `CHANGELOG.md` 的 v1.0.0 段行号 | `:45`（AGENTS.md 引的正是这一行，本轮复核**仍对**） |
| `[Unreleased]` 段的顶层条目数 | **6**（Added/Changed/Fixed 三个小节）——见 §5.1 的失真判定 |
| `apps/api/.venv` 工具链 | Python 3.12.10 / ruff 0.12.12 / mypy 2.3.1（与 `pyproject` 钉版一致） |
| 前端工具链 | node v24.21.0、pnpm 9.15.9、`packageManager` = pnpm@9.15.9、`next` = ^15.5.28 |
| docker / PG / Redis 本机 | **全无**（`entry.py docker-ps`→3、`migrate`→3）⇒ 连库与容器面一律 `@ci` |
| 迁移单头 | `ab1006c2a`，行数 1（`alembic heads` 真读数，STEP-00E 同批取） |

## 1. S12.1.1 门面文档逐条对账（AGENTS.md「当前项目状态」）

来源卡这句话是"AGENTS.md 的三条不实陈述已证伪 + 测试基线段仍为旧数字"。本轮把**整个状态段**
（12 条 bullet）逐条对了一遍，而不是只对那三条——因为"门面无不实陈述"这条判据管的是全部门面。

| # | AGENTS.md 的陈述 | 本轮现读证据 | 判定 / 处置 |
|---|---|---|---|
| 1 | 版本 = v1.0.0，main 领先 tag **286** 个提交（现读至 `bf141d5`） | `git rev-list --count v1.0.0..HEAD` = **291**（至 `9983c63`） | **数字过期**（同一句昨天写的，一天涨 5 个提交）。已改为 291 + 补一句"候选发布说明在 CHANGELOG 的 v1.1.0 段，发布归用户" |
| 2 | 后端 FastAPI + SQLAlchemy 2.0 + Alembic，**9 个业务域** | `docs/02_requirements/product-requirements.md` v2.0 的域表 = 9（identity/knowledge/subscription/ingest/chat/engine/bot/hot/system） | ✅ 真 |
| 3 | 前端 **Next.js 15** App Router，10 个功能域 | `apps/web/package.json:27` = `"next": "^15.5.28"`；功能域表 10 行 | ✅ 真（且比"15.5.24"那句更新；STEP-17 的 X-02 更正成立） |
| 4 | 推送 6 渠道真实投递 + 事件触发已实现 + 站内通知全链路 | STEP-19 的落库读数（三条直投路径都写 `notifications`）、STEP-26 补 admin 直投、STEP-13 收口判词「需要谁接着做：无」 | ✅ 真（这一条正是 00G 当年标"待建"被实测否证的那条，已在文中改写） |
| 5 | 观测与硬化：structlog 双模 + `/metrics` + `/live` `/ready` + 限流/体限/安全头 + 运行期告警三类 | `app/core/{logging,metrics,schema_guard,security,alerting}.py` 五件都在；`upstream_semaphore` 属 `security.py` | ✅ 真 |
| 6 | **文章来源：4 平台已接入（providers/article_sources/）** | 该目录现读 = `dajiala / justoneapi / tikhub / wellbyte / **rss**` + `base` | **半边不实**：RSS 自 STEP-09 起是一等信息源，目录里是**五个 provider**。已改写为"4 个付费/第三方平台 + RSS，共五个 provider 文件"，并注明 RedFox 在发现注册表里共存 |
| 7 | 热点：日报 LLM 摘要并行化 **`Semaphore(3)`** + 失败降级 | 全仓 `Semaphore(3)` **0 命中**；实际是 `core/security.py:526 upstream_concurrency()` + `:534 upstream_semaphore()`，默认值 `config.py:212` = **4**，可按 `UPSTREAM_CONCURRENCY_<NAME>` 覆盖；降级语义在 `services/llm_summary.py:6,55` | **不实（机制与数字都错）**。已改写为"上限不是写死的 `Semaphore(3)`"那版措辞，并把失败返回 None → 中心文章首段截断降级一并写清 |
| 8 | 测试：CI postgres service + skip 门禁 + 单头断言 + e2e/冒烟 job；现读 **2258/6/4** @run 39885880010（`3491054`） | 同一形状在 `9983c63` 之前的两次运行都成立（`878876f` run 39894271073：`2258 passed / 6 skipped / 4 deselected`、`pg_unreachable=0`、`Total coverage: 87.95%`） | ✅ 判定成立，**run 号可更新**；本行数字与 §5 的三绿表一起改到最新一次读取（见文末"提交前补录"） |
| 9 | `@win` 侧 skip 基线 **666**（零余量，按原因族记账） | `.github/workflows/ci-windows.yml` 的 `SKIP_BASELINE_WIN: "666"` 在场；`878876f` 那次 Windows 门读数 `failed=0 total_skipped=666 baseline=666` | ✅ 真 |
| 10 | 目录结构已迁移 `apps/api/` + `apps/web/`；六边形重构显式推迟 | `guard-structure` rc=0（四个目录全存在） | ✅ 真 |
| 11 | 关键约束 1–6（不改原项目 / sub 锚点 / String(32) / PG 队列 / 直连 SiliconFlow / Provider 契约） | 六条各自有代码或裁决支撑；STEP-14a/15 的分页与 STEP-31 的审计未触碰这六条 | ✅ 真 |
| 12 | 端口表（3000 禁用 / 3200 / 3300 / 5300 / 5433 / 6380） | `guard-ports` rc=0；宿主发布行只有 `5300:5300`、`3300:3300`、`3200:3000`，`3000:` 作为**宿主**端口零命中 | ✅ 真，但见 §6 的 P-102：`compose.yml` **没有** PG/Redis 服务段，5433/6380 是"部署形态由平台供给"的口径，本仓 compose 起不出来 |

**结论**：12 条里 **2 条不实**（#6 半边、#7 全错）+ **1 条数字过期**（#1）+ **1 条可刷新**（#8），全部已在本批改正；
其余 8 条复核为真。来源卡点名的"三条证伪 + 测试基线旧数字"这一批，到本轮才算逐条给了证据而不是逐条改字。

## 2. S12.1.2 需求条目的验收锚对账（原件 `req_anchor_reconciliation.txt`）

| 判据 | 读数 |
|---|---|
| 语料 | 15 份（`docs/02_requirements/**` 的 12 份条目 + 主文档 + `AGENTS.md`） |
| 仓内文件锚（去重，按 HEAD blob 判存在） | **99**，其中**不存在 = 0** |
| `::` 符号锚 | **4**（= 语料里全部这种写法），**对不上 = 0** |
| 写法不齐（裸 `tests/x.py` 而非 `apps/api/tests/x.py`） | **0** |
| 探针四发极性自测 | ①真实符号在 ②编造符号不在 ③真实文件存在 ④编造文件不存在 —— 全对，`rc=0` |

REQ-F-004 的 11 个锚、REQ-F-006 的 12 个锚（含前端 `r024-subscription-lifecycle.spec.tsx`）全部命中真实文件；
来源卡当年要求"增验收锚（test_kb_longlink_ingest / test_manifest_asset_alignment / test_e2e_collection）"
这三条现在都在列表里（分别由 STEP-04/06 补的判据面）。

⚠ **这条对账今天没有常驻门**：`scripts/check_docs_consistency.py` 只扫
`docs/04_engineering/backlog.md` 里 ✅ 条目的 `path:line`，**不看需求条目**。
也就是说"明天有人往 REQ 文档里写一条不存在的用例文件"，任何门都不会红。⇒ 登记台账 §4 **P-108**，
建议把本探针做成 `guard` 的一条（判据：故意把某个锚改成不存在的文件名 ⇒ 门必须红）。

## 3. S12.1.3 `conventions.md` 增三条（本轮落地形态）

三条原散在脚本注释与各卡 EVD，从未进规范正文。本批写成 **§4.5「测试环境的三条隔离纪律」**，
每条都带"实体在哪 + 违反时被什么抓住"：

1. **测试端口只能用隔离段（5547/6390），不许静默换端口**——实体 `scripts/test-env.sh` 的
   `FORBIDDEN_PORTS=(5433 5435 6379 6380)` + 越界端口检查，命中即 `exit 2`；理由 = D-12 事故。
2. **用例出站网络由 `conftest` 密封**——实体 `apps/api/tests/conftest.py:87-96`
   （清 6 个代理变量 + `NO_PROXY=127.0.0.1,localhost,::1`），并写明"故意 skip"的
   `tests/test_env_isolation.py:77`  ⇒ 看到 `@ci` 的 6 条 skip 时要知道其中一条是设计如此。
3. **DSN/口令/主密钥不得进仓内文本**——执行面 = `evidence-check` 读索引判形 + CI gitleaks 读历史，
   并明写"一次性生成的凭据同样是凭据"（这条与 §4 的 P-107 相连）。

## 4. S12.2.1 运行镜像的时区库核验（U-06 那一格）

**卡面要求**：构建运行镜像核验时区库，结果入 EVD。**本机无 docker ⇒ 不能自己 build 并 exec 容器**。
可用的替代证据面是 CI 的 `compose-smoke` job——它做的正是"build backend 镜像 → 起核心服务 → 探活"：

```
run 39891503640 @8e59749 的 compose-smoke 步（原文摘录，凭据值不抄录）：
  [1/2] 轮询 backend 健康端点 → 信封 code==0，data.deps = {postgres: ok, redis: ok, langbot: unreachable}
  [2/2] scheduler / worker 心跳 → rows: scheduler|2 worker|2，两条 age=2s ⇒ PASS
  结果：PASS=3 FAIL=0，冒烟结论 ✅ PASS
  docker compose ps 行显示 backend 容器命令 = "uvicorn app.main:ap…"，postgres 服务镜像 = postgres:16-alpine
```

**判定**：`app.api.v1.hot:38` 与 `app.core.alerting:116` 都在**模块导入期**构造
`ZoneInfo("Asia/Shanghai")`；`uvicorn app.main:app` 起得来（`/system/health` 返回信封 code 0）且
`worker`/`scheduler`（`python -m app.services…`）心跳新鲜 ⇒ **运行镜像里时区库解析得到**，
U-06 的问题**答案是"能用"**。这是间接证据，但它是同一镜像、同一解释器、同一进程入口的间接证据，
比"本机构建不了所以未测"强。

⚠ **一条必须交给发布的隐式依赖（台账 §4 P-106）**：能解析 ≠ 被声明。
`apps/api/pyproject.toml` **没有** `tzdata`，`apps/api/Dockerfile` **不装** 系统 tzdata，
基础镜像是 `python:3.12-slim`。⇒ 时区可用性现在靠"基镜像恰好带 tz db"这一**未被声明的事实**；
上游 slim 哪天剥掉它，后端会在 **import 期整体起不来**（不是某个功能降级，是进程起不来），
而 CI 只有 `compose-smoke` 那一条路会红。修法很小（`pyproject` 加 `tzdata` 或 Dockerfile `apt-get install -y --no-install-recommends tzdata`），
但**不在本卡所有权内**（W 只到 AGENTS/02_requirements/conventions/CHANGELOG/task-index）。

## 5. S12.2.2 汇总件：CHANGELOG、task-index、门禁与三绿

### 5.1 CHANGELOG（本轮产物）
`## [v1.1.0] — 未发布（STEP-12 对账产物；发布与否由用户拍板）` 段已插在 `[v1.0.0]` 之前，
含 **11 条 Added + 7 条 Changed + 6 条 Fixed**（共 24 条顶层条目，计数方式是 `^- ` 严格匹配，
子行缩进的补充句不计），每条末尾给来源提交短 hash，且**每个 hash 都 `git log -1` 复核过主语**——
复核过程中改掉了一次错配：`b79c8e9`/`859c0df` 我起初当成 STEP-02/03 的交付提交，
实际它们是 STEP-01 的返工批，`契约生成面` 那条已按现读改挂 `25088c4`/`a6f54e1`/`d044d2a`，
provider 那三条缺陷改挂 `2a7195d`/`f7a3a6b`（STEP-20）。

- **如实登记一条失真**：`[Unreleased]` 段今天只有 **6 个顶层条目**，而 `v1.0.0..HEAD` 之间有 **291 个提交**——
  即"Unreleased 从没被按时填过"。所以 v1.1.0 那段不是"把 Unreleased 换个标题"，是**重新对账出来的**。
  这一句必须写在这里，否则发布的人以为搬空 Unreleased 就等于发布完了。
- `[Unreleased]` **保持不动**（搬空它就是发布动作）。

### 5.2 task-index
`docs/05_execution/task-index.md` 只在 **V0.1.0 的历史树**里存在（`docs/任务规划V0.1.0/05_execution/task-index.md`），
当前 `docs/05_execution/` 下只有 `tasks/TASK-PLAN-v0.{6,7,8,9}.md`，**没有** 现役 task-index。
⇒ 本卡不改一个不存在的路径；"任务进度"的现役载体是各版 `docs/任务规划V0.1x.0/07-执行过程记录.md`
（V0.17.0 已到第 **38** 行，STEP-12 收口写第 **39** 行）。这一条差异写给规划方，别让它继续当"要改的文件"。

### 5.3 门禁读数（本批 push 前全部实跑）

| 门 | 读数 |
|---|---|
| `ruff check app tests` | All checks passed，rc=0 |
| `mypy app` | Success: no issues found in 119 source files |
| `check_entry_parity` | rc=0（Makefile 37 目标 / entry.py 41 任务） |
| `check_docs_consistency` | rc=0（23 个路径引用，0 个不存在） |
| `evidence-check`（读索引） | rc=0；内含 gitleaks：**364 commits scanned，no leaks found** |
| `guard-ports` / `guard-versions` / `guard-structure` | 全 rc=0 |
| `rounds-check` | 见提交后复跑（D-14 阈值 ≤2 轮） |
| 需求锚对账探针 | rc=0（§2） |

### 5.4 三绿与队列闭合
- 队列 **①–⑯ 已全部走完**：①–⑭ 在前几批，⑮ = 14a→06→11→18→17→RV→00X→00E，⑯ = 本卡。
- **STEP-00E 批（`9983c63`）三条 attempt 1 全绿**（本卡开工前实测，取数面 = GitHub Actions 日志 + REST）：

| 工作流 | run id | 结论 | 关键读数 |
|---|---|---|---|
| `CI` | **39896802610** | `completed/success` | `2258 passed, 6 skipped, 4 deselected in 194.68s`；`Required test coverage of 75% reached. Total coverage: 88.00%`；`skip 门禁：total_skipped=6 baseline=6 pg_unreachable=0`；`✅ 全部模块与全局达标` |
| `CI-Windows` | **39896802631** | `completed/success` | `1598 passed, 666 skipped, 4 deselected in 1058.67s`；`windows 门禁：failed=0 total_skipped=666 baseline=666`；`Test Files 49 passed (49)` |
| `Security` | **39896802667** | `completed/success` | 四道扫描无 BLOCK |

- ⚠ **这里出现了一条对本卡 §6 有直接影响的复算**：`Total coverage` 在三个**连续的都是文档/入口面**的
  提交上读出 **88.01%（`8e59749`）→ 87.95%（`878876f`）→ 88.00%（`9983c63`）**，
  而三次测试数完全相同（`2258/6/4`）。⇒ 台账 §4 **P-104** 不是单点观察，是**第三次复现**；
  它意味着"覆盖率"这个数**不能当发布门禁的精确判据**（全局线 79 有余量，所以本批不阻塞；
  贴线的模块见 P-98）。

### 5.5 提交前补录
本批（STEP-12，纯文档）自己的三条运行在 push 后读取；如果那一格里出现红，第一顺位怀疑对象是
P-99 那一类**上游公告**（本批没动任何代码/依赖，其余面不可能变）。

## 6. 发布就绪判定（这是本卡真正要交付的东西）

**就绪的技术面**：

| 判据 | 状态 | 读数在哪 |
|---|---|---|
| 主干三绿（CI / CI-Windows / Security） | ✅ 连续成立（本批 push 后复算） | §5.4、各收口行 |
| 全量连库回归真实执行（skip≠pass） | ✅ `2258 passed / 6 skipped / 4 deselected`、`pg_unreachable=0`，6 条 skip 已逐条点名 | `EVD-V4-00E/verify_targets_readings.md` §5 验收② |
| 迁移单头 + 头版本可逆 | ✅ `ab1006c2a` 单头；CI 常驻 upgrade→downgrade→upgrade 三步判 | `cross-platform.md` §7 |
| 覆盖率 | ✅ 全局 **88.00%**（run 39896802610；线 79），九条模块线全达标。⚠ 但**同树三次复算是 88.01 / 87.95 / 88.00** ⇒ 这个数有 ±1 行抖（P-104），可以过线、不可以当精确判据 | CI backend 日志 + §5.4 |
| 门面文档无不实陈述 | ✅ 本批改正 3 条后达成 | §1 |
| 需求条目有测试锚 | ✅ 99 文件锚 + 4 符号锚全命中 | §2 |
| 契约面 | ✅ `test_contract_jsonschema.py` / `test_collection_contract.py` 在 CI 全量内通过 | 各卡收口行 |
| 敏感信息门 | ✅ gitleaks 364 commits no leaks；`evidence-check` 读索引 rc=0 | §5.3 |

**发布前必须先决定的三件事（都不是"技术上不通过"，是"该由人拍板"）**：

1. **版本号与范围**：`v1.0.0` 之后 291 个提交、跨 5 个规划版本、含 3 次 DDL 迁移与 1 次
   `next 14→15` 大版本迁移。按 semver 这至少是 minor，可能有人主张 major。
   执行方不代选：§5.1 的候选段用的是 `v1.1.0`，**这只是占位**。
2. **仓库可见性**：REST 现读 `GET /repos/aideanew/BotHot` = `private=false, visibility=public`。
   这条本身不是缺陷，但它决定了下面第 3 条的严重性评级。
3. **CI 日志回显一次性主密钥**（台账 §4 P-107）：`compose-smoke` 前一步把
   `os.urandom(32)` 生成的两把临时主密钥经 `$GITHUB_ENV` 传给下一步，GitHub 会把下一步的
   `env:` 块原文写进日志 ⇒ 公开仓库里任何读者都能看到**那一次运行**的密钥值。
   技术评级**低**（那两把钥匙只加解密当次 job 里那份一次性数据库，job 结束即废），
   但它是"日志暴露密钥"这个模式，且修法是一行 `::add-mask::`（属 CI 面，不在本卡所有权内）。
   ⚠ 若将来有人把同样的生成方式挪到持久栈，就从"低危"变成"事故"。

**未闭合但不阻塞发布的清单**（都登记在台账 §4，逐条给归属）：
P-98（模块阈值零/薄余量，需裁定棘轮 vs 地板）、P-99（上游公告型红灯的处置政策，本批已按①自行处置过）、
P-100（`open(` 判据抓函数名）、P-101（make↔entry 的 Linux 半边无执行者）、
P-102（`compose.yml` 无 PG/Redis 服务段）、P-103（compose.test.yml 要不要建）、
P-104（同树 CI 覆盖率 ±1 行漂）、P-105（vitest 真拨 `localhost:3000` 且被吞）、
P-106（时区库是未声明的隐式依赖）、P-107（一次性主密钥进公开日志）、P-108（需求锚对账无常驻门）、
STEP-05 的 S5.3.1/S5.3.2（COULD 两项，交回规划方）、S00E.3.1（👤 验收面归属裁决）、
P-78/P-86…P-97 里仍标"规划方裁定"的若干条。

## 7. 未测清单（本卡判不了，换到对应环境可原地复跑）

| 项 | 为什么未测 | 复跑面 |
|---|---|---|
| `S12.2.1` 的**直接**核验（容器里打印 tz db 路径 / `ZoneInfo` 构造成功） | 本机无 docker，起不了容器 | 任一有 docker 的机器：`docker compose -f docker/compose.yml -f docker/compose.ci.yml build backend`，再 `docker run --rm --entrypoint python <镜像> -c "import os,zoneinfo; print(zoneinfo.ZoneInfo('Asia/Shanghai')); print(os.path.exists('/usr/share/zoneinfo/Asia/Shanghai'))"`——第二行 False 而第一行仍成功 ⇒ 靠的是 pip 的 `tzdata` 包，那也要在 `pyproject` 里写明（P-106 的两种情形） |
| 干净机按 README 从零（00X 的 Done 判据 2） | 本机非干净机且无 docker | 同上 |
| `make X` ↔ `entry.py X` 的 Linux 半边 | ubuntu job 从不调用 make（P-101） | 任一 Linux 机跑 6 个任务 |
| 生产环境读数（STEP-07 的审计/重加密演练） | 生产只读 DSN 从未提供 | 运维提供只读 DSN 的机器 |
| 发布后冒烟（`v1.1.0` tag 推上去之后的 CI + compose-smoke） | 发布动作归用户 | 打 tag 后读 run |

## 8. 所有权申报

卡面允许（W）：`AGENTS.md`、`docs/02_requirements/**`、`docs/04_engineering/conventions.md`、
`CHANGELOG.md`、`docs/05_execution/task-index`。

本批实际动了：`AGENTS.md`（§1 的三条改正）、`conventions.md`（§4.5 新增）、`CHANGELOG.md`（v1.1.0 候选段）、
`EVD-V17-12/`（本文件 + 对账原件）、台账 `docs/任务规划V0.12.0/00-README.md`（P-106/107/108 + P-102 补正）、
卡面 `docs/任务规划V0.13.0/steps/STEP-12-*.md`（执行记录）、`docs/任务规划V0.17.0/07-执行过程记录.md`（行 39）。

**未动且故意不动**：
- `docs/02_requirements/**` —— §2 的对账**没有发现需要改的锚**（99/4 全命中）；无实陈述就不改字。
- `docs/05_execution/task-index` —— 该路径不存在（§5.2）。
- `apps/api/Dockerfile` / `pyproject.toml` —— P-106 的修法在那两侧，本卡无所有权。
- `.github/workflows/*` —— P-107 的 `::add-mask::` 修法在 CI 面，属 D-11 授权范围外。
- `[Unreleased]` 段 —— 搬空它 = 执行发布，越权。
