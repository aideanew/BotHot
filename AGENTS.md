# AGENTS.md — BotHot AI 协作规范

> 本文件是 AI Agent 在 BotHot 项目中工作的入口规范。人类开发者也建议阅读。

## 深度推理模式（强制）

在给出任何设计结论或架构决策之前，必须执行三轮推理：

### 第一轮（发散）：5W1H 全面拆解
显式回答：
1. **What** — 客观事实/现象是什么？
2. **Why** — 深层原因/动机是什么？
3. **Where/When** — 适用的边界条件、时间节点是什么？
4. **Who** — 涉及的主体、责任方是谁？
5. **How** — 执行的手段、方法是什么？
6. **What if** — 如果前提变了，结论会怎样？

### 第二轮（收敛与拷问）
- 对每个节点做苏格拉底式"致命追问"。
- 对关键节点做双向钢人论证（two-way steelmanning）。

### 第三轮（重构）
- 只有当无法再用新问题推翻自己时，输出终稿。
- 终稿必须带前提条件和局限性说明。

## 开发流程（六步循环）

一切功能性变更（代码、目录结构、公开接口、数据库模型等）遵循：

```
PLAN 规划 → SPEC 规格 → APPROVE 批准 → IMPLEMENT 实施 → VERIFY 核验 → CLOSE 归档
```

代码改动必须同步到对应文档和任务进度中。

## 端口分配准则（强制）

**本栈发布**（`docker/compose.yml` 现读发布行）：

| 端口 | 用途 | 约束 |
|------|------|------|
| 3000 | 主平台专用 | ❌ BotHot 任何服务禁止占用（容器内 3000 是前端内部监听，不向宿主发布，见 compose `:423` 的 `"3200:3000"` 注释） |
| 3200 | BotHot 前端宿主端口 | compose `:423` `"3200:3000"`（容器内部 3000） |
| 3300 | BotHot 后端端口 | compose `:245` `"3300:3300"` |
| 5300 | LangBot | compose `:101` `"5300:5300"` |

**外部提供**（不在本栈 compose 内发布；P-78/P-102 判定前的过渡口径，来源为旧表陈述）：

| 端口 | 用途 | 约束 |
|------|------|------|
| 5433 | PostgreSQL（历史规划值） | 本栈 compose 现读**未发布**该端口（PG 由平台侧/测试环境供给：CI 用 service 容器、本机测试用 5547 隔离库） |
| 6380 | Redis（历史规划值） | 同上；本栈 compose 内无 Redis 服务 |

> 端口变更需先经架构裁决并同步本文档 + docs/04_engineering/conventions.md。

## 文档体系入口

所有项目文档在 `docs/` 目录，入口导航：

- **项目导航地图** → [docs/00_governance/project-map.md](docs/00_governance/project-map.md)
- **功能需求基线** → [docs/02_requirements/product-requirements.md](docs/02_requirements/product-requirements.md)
- **系统架构设计** → [docs/03_solution/architecture.md](docs/03_solution/architecture.md)
- **项目目录架构设计** → [docs/03_solution/project-structure-design.md](docs/03_solution/project-structure-design.md)
- **工程规范** → [docs/04_engineering/conventions.md](docs/04_engineering/conventions.md)
- **路线图** → [docs/04_engineering/roadmap.md](docs/04_engineering/roadmap.md)
- **待办清单** → [docs/04_engineering/backlog.md](docs/04_engineering/backlog.md)
- **多会话协作纪律（AI 会话强制规范，开工前必读）** → [docs/04_engineering/collaboration-discipline.md](docs/04_engineering/collaboration-discipline.md)

## 当前项目状态

- **版本**：**v1.1.5**（STEP-63 于 2026-10-29 发布，质量版：真后端 e2e 从骨架到 `/chat` 五态真跑 + UX 态契约自洽 + 需求判词纠真）。
  证据：`CHANGELOG.md` 有 `## [v1.1.5] - 2026-10-29` 段（条目按 `git log v1.1.4..HEAD` 区间重新对账写入，
  区间 63 个提交 = `feat` 10 / `fix` 12 / `docs(...)` 38（其中 1 个是 `docs+fix(...)` 合批主语）/ `chore` 3，
  10 个 `feat` 主语逐个 `git log -1` 复核；**本行不抄发布批自己的 sha**——写这段时它还不存在，
  权威读数一律现取：`git ls-remote --tags origin v1.1.5`（注释标签给出标签对象与 `^{}` 指向的提交两行）、
  `git rev-parse v1.1.5^{commit}`）；发布批三绿 run id、全量回归读数与 tag/Release 读数见
  `docs/06_validation/evidence/EVD-V22-63/`。
  本版要点：**真后端 e2e 这条链第一次能真跑**——`apps/web/playwright.config.ts` 只在 `E2E_REAL_BACKEND=1` 时生成
  `real` project（没有该开关就**不产生 `projects` 键**：Playwright 一见到非空 `projects` 就只跑列出的项目，
  演示态那 43 条才不会被挤掉）；`e2e/real.setup.ts` 产出三角色 storageState；`scripts/e2e/run_real_backend.sh`
  一条命令摆好迁移 → uvicorn(:3300) → 探活 → 种子会话 → next(:3200)，端口被占即非零退出（D-V4-02），
  退出码 2/3/4/5/6/7/8/9/10/11/12 各指一件事；假 LLM / 假 LangBot 两件 + 可检索种子补上"不烧额度也能真跑"这一环；
  `r19-chat-stream.spec.ts` 按契约现读重写为**五态**，CI 增「跑 r19（带 `E2E_CHAT_LLM=1`）」与「断言该步未被 skip」两步。
  **UX 态契约自洽**：`UX_STATES` 是 8 值词表、`UX_VIEW_STATES` 给六视图投影（spaces 7 / hot 5 / chat 5 /
  admin 6 / notificationbell 5 / onboarding 2），键序由冻结稿 `ux_states.schema.json` 钉住；`offstate` 移出
  `states`、住进 `x-core-views[NotificationBell].x-build-mode-notes` ⇒ 逐键比对不再需要例外分支。
  **`/chat` 的停止**：`useSseAsk` 的 `stop()` abort 流但保留已渲染正文、迟到 delta 不写入、该条标 `stopped`
  且仍可重试；文案收成唯一源 `apps/web/lib/chat/copy.ts`（上一轮同一句散在三处，P-146）。**`MeWallet` 契约封闭**
  （`apps/api/app/contracts/shapes.py` 加 `additionalProperties: false`），v1.1.4 记的 P-121 部分闭合就此闭合。
  **需求判词 12 条纠真**（STEP-62）：五条实现度、四条测试锚、无锚需求数 2→1，`/chat` 的"八态"按契约改成"五态"。
  **`e2e-real` job 仍是非阻塞**：STEP-62 交付时的末三次真执行是 `1eaf2d5` ✓ / `ca9ba70` ✗ / `d6d67fc` ✓ ⇒ 当时落
  「保持」不是漏改；到本版末前件已成立（`d6d67fc` ✓ / `f536398` ✓ / `6e78dff` ✓），摘除动作**不在本版做**
  （本版允许面不含 `ci.yml`），与 `ci.yml` 里那句"摘除归 STEP-62"的过期注释合并成一卡，登台账 **P-168**。
  本版**零数据库迁移、零新增对外 HTTP 端点**；区间内 `apps/api/app/**` 只动了 `apps/api/app/contracts/shapes.py`
  一个文件（无路由、无模型、无 `apps/api/alembic/versions/**` 下的新迁移——本仓没有 `apps/api/migrations` 这个目录）。
  测试基线（三绿 head `6e78dff`；其后的收口批 `3115532` 与发布批都是零代码文档批）：
  CI `2503 passed / 6 skipped / 4 deselected`、`Total coverage: 88.93%`、模块覆盖率门 `✅ 全部模块与全局达标`、
  skip 门 `total_skipped=6 baseline=6 pg_unreachable=0`；前端 `57 文件 / 452 passed`；
  演示态 e2e `43 条中 31 passed / 12 skipped`（第 43 条是 mock 档跳过的 r19）；`e2e-real` job 内 r19 五条
  `5 passed (4.9s)`、守卫步 `ok=5 skipped=0 failed=0`、admin `6 passed / 1 skipped`（② 键盘可达按 P-131 跳）；
  CI-Windows `1817 passed / 692 skipped` 且门禁 `failed=0 total_skipped=692 baseline=692`。
  本机全量（本版唯一一次发版口径，发布批；隔离 PG16@5547 + `PYTHONUTF8=1`；同一棵树跑了两次，差量见下一行）：
  `2503 passed / 6 skipped / 4 deselected`、
  `Total coverage: 88.90%`、模块门 `✅ 全部模块与全局达标`、skip 门 `total_skipped=6 baseline=6 pg_unreachable=0`。
  ⚠ **本机口径必须是 UTF-8 模式**：默认 cp936 码页下同一棵树读 `2500 passed / 3 failed`，三条红同一形状——
  父进程用 gbk 解码子进程的 UTF-8 输出 ⇒ `proc.stdout` 为 `None`（`test_health_probe_bounded.py` 两条、
  `test_security_scan_helper.py` 一条）；Linux CI 与 cp1252 的 CI-Windows 都碰不到，故不在 CI 暴露。修法动的是
  测试文件、不在发版卡允许面，登 **P-169**。
  ⚠ 覆盖率那个数**不可当精确判据**：本区间已归档的两个交付读数落在 88.93（`6e78dff` 的 CI）与 88.94
  （`d6d67fc` 的 CI），本机这次读 88.90——同族旧例是 88.01/87.95/88.00 那次同树三抖（台账 P-104）。
  `@win` 侧 skip 基线仍是 **692**（零余量，本版新增用例全不连库 ⇒ 不动）。
  区间计数：`git rev-list --count v1.1.4..HEAD` 于收口批 `3115532` = **63**，发布批自身 +1 ⇒ tag 指向的提交上是 64
  （自指提交不抄 sha，以现取为准）。上一版 `v1.1.4`（STEP-58，2026-10-27）及更早各版也都是注释标签，
  现取口径不变——注意 `git rev-parse v1.x.0` 给的是**标签对象**的 sha 不是被标提交。
  ⚠ 失真教训仍有效（三条）：`[Unreleased]` 的条数 ≠ 区间提交数，发布段必须按区间重新对账（v1.1.0 的原始登记见
  `docs/06_validation/evidence/EVD-V17-12/s12_readings.md` §5.1）；**被引用的行号与被引用的支撑都会失真**，
  门面文字优先点名（测试名/函数名），不点行号；**"本机复跑同数"要带口径**——本版默认 cp936 码页下差 3 条，
  只报总数就会把环境差异读成交付缺陷（P-169）。
- **后端**：FastAPI + SQLAlchemy 2.0 + Alembic，9 个业务域
- **前端**：**Next.js 15** App Router（X-02 更正），10 个功能域
  - 证据：`apps/web/package.json:27` `"next": "^15.5.28"`、`:28` `"react": "^19.0.0"`；
    运行时锚 `apps/web/.nvmrc` = `24.21.0`、`package.json:7` `engines.node >= 24.0.0`
    （同一条漂移当年在需求基线与本 conventions §5.2 各自出现过，均已更正。
    `^15.5.24 → ^15.5.28` 这一步是 2026-10-23 的依赖安全补丁批，见台账 P-99；
    刻意只给符号名不给 `product-requirements.md` 的行号——那份文件已按 STEP-17 拆分子文件）。
- **推送**：6 渠道 Provider 真实投递（**站内通知全链路已通**，完整口径见下一行；微信 ClawBot 需部署服务）；PushScheduler 60s 调度（SKIP LOCKED 短锁领取 + **投递重试/指数退避/死信终态**，重试态挂 PushTask）；Cron 完整 5 段式 + 简写兼容；**事件触发已实现且 payload 自足**（emit 时查库补模板变量快照）；渠道密钥 **AES-256-GCM**（fail-closed，双主密钥已纳入生产守卫）；旧 push_port 已删除
- **观测与硬化**：structlog 双模日志（`core/logging.py`）+ Prometheus `/metrics`（`core/metrics.py`）+ `/live` `/ready` 探针（`core/schema_guard.py`，schema 不一致 503）+ 限流/体限/安全头中间件（`core/security.py`）+ 运行期告警三类（`core/alerting.py`，`ALERTING_ENABLED` 门）；Dockerfile 多阶段+uid1000+HEALTHCHECK，compose read_only/tmpfs/cap_drop/no-new-privileges
- **通知持久化（STEP-17 S17.2.1：原第 75/77 两行自相矛盾，此处合并为单一陈述）**：
  站内通知链路四条腿都在——存储层 `Notification` 表（迁移 `ab1005w5a`）、
  **写侧三路径**（调度器投递 / 手动与测试直投 / admin 直投，后两条由 STEP-23 与 STEP-26 补上，
  落库顺序由 `test_push_persist_order.py` 钉住）、读侧 `system.py` 的 `/notifications/history`
  与 `PUT /notifications/read`、订阅侧 SSE `/notifications` + 前端 `NotificationBell`。
  旧第 77 行把写侧与读侧 history 写成待建（R1.2 的 b/c/d 三项）——那是**被实测否证的陈述**：
  `docs/04_engineering/backlog.md` 的 NOTIF-001 早于 2026-10-08 就把 R1.2a/b/c/d 全标 ✅，
  STEP-19 的收口判词（`docs/06_validation/evidence/EVD-V3-19/verdicts.md`）进一步判 F-001
  「需要谁接着做：无」。需求侧的详文与判据见
  `docs/02_requirements/features/REQ-F-001-multi-channel-push.md`。
- **文章来源**：**4 个付费/第三方平台 + RSS 共五个 provider 文件**（`apps/api/app/providers/article_sources/`：
  `dajiala.py`、`justoneapi.py`、`tikhub.py`、`wellbyte.py`、`rss.py`，另有 `base.py`；2026-10-23 现读，
  STEP-12 对账时把"4 平台"这句补全——RSS 自 STEP-09 起是一等信息源，不再是外链兜底）。
  Dajiala 极致了（发现+HTML详情）、JustOneAPI（发现+正文详情）、TikHub（发现+搜索，需充值）、
  Wellbyte 数井（搜索+URL驱动发现）；与 RedFox 共存于发现注册表，详情兜底协调器按成本排序
  （协调器默认关，触发条件/供应商/预算由 STEP-10 做成运营可配）
- **热点**：全链路贯通——聚簇（TF-IDF，候选上限护栏 + 倒排剪枝）、**评分已接线**（worker 聚簇后评分 + 日报前兜底重算 + 每小时 hot_rescore 周期重评，Feed 分数同步回刷）、Feed 三类生产者、日报（LLM 摘要并行化 + 失败降级；**上限不是写死的 `Semaphore(3)`**——STEP-12 现读更正：由 `apps/api/app/core/security.py` 的 `upstream_semaphore(name)` 限界，默认值 `config.py:212` = **4**，可用 `UPSTREAM_CONCURRENCY_<NAME>` 逐 provider 覆盖；失败语义在 `services/llm_summary.py`：任何失败返回 None，调用方走"中心文章正文首段截断"降级）；业务日界 = Asia/Shanghai
- **测试**：连库用例真实执行（CI 有 postgres service + skip 门禁 + alembic 单头断言 + e2e/冒烟 job）。
  现读（2026-10-23，`@ci` run **39896802610** @`9983c63`）：**2258 passed / 6 skipped / 4 deselected**、
  `Total coverage: 88.00%`，`skip 门禁：total_skipped=6 baseline=6 pg_unreachable=0`。本机（隔离 PG16@5547）最近一次全量是
  10-22 的 `2257 passed / 6 skipped`（在覆盖率门第 11 条判据落地之前）；10-23 本机
  无 docker CLI、5547 无监听 ⇒ 连库面未在本地复算，连库结论以 `@ci` 为准。
  ⚠ STEP-12 对账补一句：这个全局覆盖率数**同树三次复算是 88.01 / 87.95 / 88.00**（测试数完全相同），
  有 ±1 行抖 ⇒ 可以拿它过线，不可以把它当精确判据（台账 §4 P-104）。
  那 4 条 deselected 是 STEP-11 的 perf 用例
  （`apps/api/pyproject.toml` 的 `addopts = ["-m", "not perf"]` 默认摘除，手动 `-m perf` 才跑）。
  `@win` 侧 skip 基线 **666**（零余量，按原因族记账；新增连库用例必须同步抬到测量值）。
  历史基线 1002/4 为 R2 发布门禁时点（2026-10-08），更早的 974/4、968/4、943/7、848/2、796/4
  分别是门禁修复、S3 收口、S0.1、v0.6 集成、WD 复核时点——只作溯源，不作当前值。
- **目录结构**：已迁移 `apps/api/` + `apps/web/`（2026-10-08 轻量迁移：路径级 git mv，import 未动；六边形 modules/ 重构显式推迟立项，见 TASK-PLAN-v0.9 S3 裁定）

## 阶段体检口径（强制，D-V22-01，用户 2026-10-27）

1. **单卡**只跑卡面列出的、它改到的测试；卡面勾选、卡表、执行记录与交付放**同一个提交**，不另开收口批，卡收口不等 CI。
2. **阶段末**对本阶段动过的模块体检一次，并读一次阶段末提交的 CI 结论。
3. **本机全量回归**只在发版卡跑一次（或开发全部完成时）；CI 每次 push 自动跑，不占执行者时间。
4. 同判据 2 次 FAIL 即停，登 P 号交回。

## 关键约束

1. **不修改 AideanBot 原项目** — BotHot 是独立副本
2. **SSO 身份锚点 = users.sub** — 余额/等级从不持久化，实时查询主平台
3. **渠道字段存为 String(32) 而非 enum** — 新增渠道零数据库迁移
4. **Job 队列在 PostgreSQL** — FOR UPDATE SKIP LOCKED，不引入 Redis 队列
5. **LLM 流式直连 SiliconFlow** — 不经 LangBot 转发
6. **推送 Provider 契约** — delivered=True/False + reason + response_data，失败时有可读原因（不伪造回执）
