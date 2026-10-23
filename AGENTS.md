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

| 端口 | 用途 | 约束 |
|------|------|------|
| 3000 | 主平台专用 | ❌ BotHot 任何服务禁止占用 |
| 3200 | BotHot 前端宿主端口 | 容器内部 3000，宿主映射 3200 |
| 3300 | BotHot 后端端口 | 容器内部 3300 |
| 5300 | LangBot | — |
| 5433 | PostgreSQL | 容器 5432 → 宿主 5433 |
| 6380 | Redis | 容器 6379 → 宿主 6380 |

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

- **版本**：**v1.0.0**（X-12：原写 v0.6.5，落后一个大版本）。
  证据：`git tag -l` → `v1.0.0`；tag 落在 `c19fe87`（2026-10-08，
  "docs(release): v1.0.0 账本终稿"）；`CHANGELOG.md:45` 有 `## [v1.0.0] - 2026-10-08` 段。
  当前 `main` 已领先 tag **286 个提交**（`git rev-list --count v1.0.0..HEAD`，2026-10-23 现读至 `bf141d5`），
  故"已发布 v1.0.0 + 主干继续前进"两者不矛盾；写版本号时以 tag 为准，不以 v0.x 叙事为准。
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
- **文章来源**：4 平台已接入（providers/article_sources/）—— Dajiala 极致了（发现+HTML详情）、JustOneAPI（发现+正文详情）、TikHub（发现+搜索，需充值）、Wellbyte 数井（搜索+URL驱动发现）；与 RedFox 共存于发现注册表，详情兜底协调器按成本排序
- **热点**：全链路贯通——聚簇（TF-IDF，候选上限护栏 + 倒排剪枝）、**评分已接线**（worker 聚簇后评分 + 日报前兜底重算 + 每小时 hot_rescore 周期重评，Feed 分数同步回刷）、Feed 三类生产者、日报（LLM 摘要并行化 Semaphore(3) + 失败降级）；业务日界 = Asia/Shanghai
- **测试**：连库用例真实执行（CI 有 postgres service + skip 门禁 + alembic 单头断言 + e2e/冒烟 job）。
  现读（2026-10-23，`@ci` run 39885880010 @3491054）：**2258 passed / 6 skipped / 4 deselected**，
  `skip 门禁：total_skipped=6 baseline=6 pg_unreachable=0`。本机（隔离 PG16@5547）最近一次全量是
  10-22 的 `2257 passed / 6 skipped`（在覆盖率门第 11 条判据落地之前）；10-23 本机
  无 docker CLI、5547 无监听 ⇒ 连库面未在本地复算，连库结论以 `@ci` 为准。
  那 4 条 deselected 是 STEP-11 的 perf 用例
  （`apps/api/pyproject.toml` 的 `addopts = ["-m", "not perf"]` 默认摘除，手动 `-m perf` 才跑）。
  `@win` 侧 skip 基线 **666**（零余量，按原因族记账；新增连库用例必须同步抬到测量值）。
  历史基线 1002/4 为 R2 发布门禁时点（2026-10-08），更早的 974/4、968/4、943/7、848/2、796/4
  分别是门禁修复、S3 收口、S0.1、v0.6 集成、WD 复核时点——只作溯源，不作当前值。
- **目录结构**：已迁移 `apps/api/` + `apps/web/`（2026-10-08 轻量迁移：路径级 git mv，import 未动；六边形 modules/ 重构显式推迟立项，见 TASK-PLAN-v0.9 S3 裁定）

## 关键约束

1. **不修改 AideanBot 原项目** — BotHot 是独立副本
2. **SSO 身份锚点 = users.sub** — 余额/等级从不持久化，实时查询主平台
3. **渠道字段存为 String(32) 而非 enum** — 新增渠道零数据库迁移
4. **Job 队列在 PostgreSQL** — FOR UPDATE SKIP LOCKED，不引入 Redis 队列
5. **LLM 流式直连 SiliconFlow** — 不经 LangBot 转发
6. **推送 Provider 契约** — delivered=True/False + reason + response_data，失败时有可读原因（不伪造回执）
