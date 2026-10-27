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

- **版本**：**v1.1.4**（STEP-58 于 2026-10-27 发布，补丁+质量版：契约覆盖面孤儿守卫 + `/auth/me` 钱包白名单投影）。
  证据：`CHANGELOG.md` 有 `## [v1.1.4] - 2026-10-27` 段（条目按 `git log v1.1.3..HEAD` 区间重新对账写入，
  区间内 2 个 `feat` 主语逐个 `git log -1` 复核；**本行不抄发布批自己的 sha**——写这段时它还不存在，
  权威读数一律现取：`git ls-remote --tags origin v1.1.4`（注释标签给出标签对象与 `^{}` 指向的提交两行）、
  `git rev-parse v1.1.4^{commit}`）；发布批三绿 run id、S58.1 对 STEP-56/57 的独立复查
  （两项均 **PASS-with-nits**，无 FAIL 也无 UNKNOWN ⇒ 判据①满足）与 Release 页读数见
  `docs/06_validation/evidence/EVD-V21-58/`。
  本版要点：**契约 def 覆盖面孤儿守卫**（新 `apps/api/tests/test_contract_def_coverage.py`：种子从两个反向核
  模块**现读**（shapes 取 `_check(<名>, <响应值>)` 调用点、引擎取带 `db_session` 用例里 `_errors(<常量>, data)`
  的常量绑定），沿 `$ref` 求可达闭包判 `全部 def − 可达集 == ∅`，两域同一张表，闭合 P-126；现读
  21 种子 / 34 def / 孤儿 0 ⇒ 补的是覆盖面不是现存缺陷）；**`/auth/me` 钱包白名单五键投影**
  （`app/services/auth/service.py` 的 `_project_wallet`，只吐 `balanceYuan`/`currency`/`heldYuan`/
  `availableYuan`/`available`，可选键缺席不补 0、缺必填或 `null` 或非字典回降级形且不抛 500、
  多余键名以 debug 每次记一次且值不落日志，`/me` 三条分支的降级形同源）；**契约链两处判据由弱变强**
  （引擎 TS 产物从"名字两侧各一空白"的子串换成钉 `export interface`/`export type` 导出位本身的正则；
  冻结稿↔生成 schema 从"只有逐对探针、列表按名字集的交构造"升级为 `genOnly` 出现即红 +
  `draftOnly` 逐个必须指得出三条既有去处 + 探针列表与装饰器同串，STEP-56）；两处文档纠真
  （`02-需求复核与辩证分析.md` 的 24→22；`EVD-V21-47` 以新增 `ERRATA.md` 登记行号漂移而不回改已归档原文）。
  **本版一处对外可见变化是收紧**：`/auth/me` 不再外溢未声明的钱包键。限定一起读：契约里 `MeWallet` 仍是
  全 30 个 def 中唯一一个开放对象（`additionalProperties: true`）⇒ 演示态样例多写一键、前端 TS 类型那一层
  都不红；把它改封闭要与冻结稿 `docs/任务规划V0.12.0/contracts/shapes.schema.json` 那两行声明同步，而冻结稿
  只有规划方能落笔（D-V21-20 与 D-V21-21 两条已由规划方裁定、执行助手在 STEP-58 收口批代录入档，
  `decision-log.md` 现读止于 D-V21-21），故 STEP-57 按台账 P-129 出路③ 只交付投影，
  **P-121 记为部分闭合**；另两处残留分别登在 P-128（`data` 发成列表时 `/auth/me` 仍 500，非本版引入）
  与 P-129 裁定行（可选键被显式发成 `null` 时按"给了值"原样带出）。
  本版**零数据库迁移、零新增对外 HTTP 端点**；区间内不属于 `docs/**` 与 `apps/api/tests/**` 的改动
  **只有 `apps/api/app/services/auth/service.py` 一个文件**（无路由、无 `packages/contracts/**`、无 `apps/web/**`）。
  测试基线（三绿 head `685e3f8`；收口批与发布批都是零代码文档批，计数三处（2496 / 6 skipped / 4 deselected）在收口批 `260a3a4` 自己的 CI run 上也逐字相同）：
  CI `2496 passed / 6 skipped / 4 deselected`、`Total coverage: 88.89%`（本机按 CI 顺序复跑读 88.91%、
  收口批 `260a3a4` 的 CI 读 88.92%）、
  模块覆盖率门 `✅ 全部模块与全局达标`、前端 `53 文件 / 425 passed`、演示态 e2e `31 passed`、
  CI-Windows `1810 passed / 692 skipped` 且 `failed=0 total_skipped=692 baseline=692`。
  ⚠ 覆盖率那个数**不可当精确判据**：本版区间内已归档的读数落在 88.89（交付头 `685e3f8` 的 CI）/
  88.90（STEP-56 收口批 CI）/ 88.91（STEP-56 交付头 `3b462d4` 的 CI、本机交付字节跑，以及 STEP-58 订正批
  `c8d92c4` 的 CI）/ 88.92（STEP-57 收口批 `260a3a4` 的 CI、本机被取代的那跑，以及 STEP-58 收口链的
  `835ffd1` 的 CI）/ 88.93（发布批 `c682acd` 与收口批 `25953e3` 的 CI——**这两个出处是 STEP-58 收口时补进来的，
  原先这份清单没有 88.93，等于把两个真实交付读数漏在清单外**）/ 88.94（STEP-56 本机作废跑），
  其中 88.94 与 88.92 的第二个出处来自作废或被取代的跑、不是交付读数；同族旧例是 88.01/87.95/88.00 那次同树三抖（台账 P-104）。
  `@win` 侧 skip 基线仍是 **692**（零余量，本版新增 8 条用例全不连库 ⇒ 不动）。
  区间计数：`git rev-list --count v1.1.3..HEAD` 于收口批 `260a3a4` = **7**，发布批自身 +1 ⇒
  tag 指向的提交上是 8（自指提交不抄 sha，以现取为准）。
  上一版 `v1.1.3`（STEP-53，2026-10-26）及更早各版也都是注释标签，现取口径不变——注意
  `git rev-parse v1.x.0` 给的是**标签对象**的 sha 不是被标提交（历史读数：`v1.1.3` 标签对象 `f98740b`
  指向提交 `88cb20f`；`v1.1.2` 标签对象见 `EVD-V20-44/`）。
  ⚠ 失真教训仍有效（两条）：`[Unreleased]` 的条数 ≠ 区间提交数，发布段必须按区间重新对账
  （v1.1.0 的原始登记见 `docs/06_validation/evidence/EVD-V17-12/s12_readings.md` §5.1）；
  **被引用的行号与被引用的支撑都会失真**——钉 22 条那句断言的位置因 docstring 增删从 `:107` 漂到 `:114`，
  `EVD-V21-47/ERRATA.md` 里"该测试文件只有一个提交"的支撑因本版 `685e3f8` 也变成两个，
  两处都已在 `EVD-V21-58` 与该 ERRATA 的订正段里标注 ⇒ 门面文字优先点名（测试名/函数名），不点行号。
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
