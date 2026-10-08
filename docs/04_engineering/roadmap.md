---
id: ROADMAP
type: roadmap
title: BotHot 路线图
status: active
owner: product
created: 2026-09-29
updated: 2026-10-08
version: 1.0
---

# BotHot 路线图

## 当前阶段：v0.6.5 — 观测与安全运行时硬化（W6-W10）+ 通知持久化底座

> v0.4/v0.5 已于 2026-09-30 交付；v0.6 由五路并行（WA-WB-WC-WD-WE）+ 集成审查完成；
> v0.6.5（W6-W10 观测/安全/硬化）已于 `main @ 8b1b5f2` 合并，CI 首跑修复至 `main @ 7bdb964`（2026-10-08 回填）

**目标**：基于项目文档规范与工程结构规范，完成 BotHot 文档架构和目录架构的重新设计。

**交付物**：
- [x] docs/ 文档体系（00_governance ~ 04_engineering）
- [x] 功能需求基线（9 后端业务域 + 10 前端功能域）
- [x] 系统架构设计文档
- [x] 项目目录架构设计文档（apps/ monorepo 结构）
- [x] ADR 决策索引
- [x] AGENTS.md 更新

---

## v0.4 — 推送能力落地 ✅（2026-09-30 集成审查通过）

> 预计开始：2026-09-30
> 勾选状态同步：2026-09-30（W5 依代码实证回填；W1-W5 五路并行交付 + 集成审查缝合后本阶段完成）

**目标**：多渠道推送真实投递 + Cron 全生命周期 + 事件触发 + 密钥安全落库。

**任务**：
- [x] 实现飞书 Webhook Provider（真实推送）— `providers/push/feishu.py`（交互式卡片 + HMAC-SHA256 加签）
- [x] 实现钉钉 Webhook Provider — `providers/push/dingtalk.py`（Markdown + HMAC-SHA256 加签）
- [x] 实现企业微信 Webhook Provider — `providers/push/wechat_work.py`（Markdown）
- [x] 实现 微信 ClawBot Provider — `providers/push/wechat_clawbot.py`（Bearer token + `/api/send`；需部署 ClawBot 服务）
- [x] 实现通用 Webhook Provider — `providers/push/webhook.py`（POST JSON + HTTP 2xx 校验）
- [x] 实现站内通知 Provider — `providers/push/web.py`（Redis pub/sub → `bothot:notifications:*`；**投递侧**已完成，前端订阅侧未实现）
- [x] PushScheduler 定时调度落地 — 60s 扫描（`main.py:247` lifespan 启动）；Cron 解析升级 **croniter 完整 5 段式 + 三种简写兼容**（`services/cron_expr.py`，TECH-002 完成）
- [x] Cron 任务全生命周期正确性 — 创建即写 `next_run_at`（修复"创建即永不触发"）、新增 `PUT /tasks/{id}`（编辑/暂停恢复）、run-now 补算下次执行、软删除（`api/v1/bots.py`）
- [x] 渠道密钥 AES-256-GCM 落库 — `core/secret_crypto.py`（AAD 绑定 channel id，`PUSH_SECRET_MASTER_KEY` fail-closed）+ 存量迁移 `ab1004w1a`
- [x] 调度器并发安全 — FOR UPDATE SKIP LOCKED 短锁领取 + 单任务异常隔离（`push_scheduler.py`）
- [x] 事件触发推送（新文章/热点更新/日报生成）— PG outbox 表 `push_events`（`ab1004w3a`）：worker 进程 emit、backend 调度器 claim 消费；模板变量 `{space_name}/{doc_title}/{hot_topic}/{topic_count}`（`services/push_events.py` / `push_template.py`）
- [x] 推送日志查询与**重试**机制 — 日志查询（`api/v1/bots.py`）+ 指数退避重试/死信（`services/push_scheduler.py` MAX_PUSH_RETRIES，PUSH-009，详见 v0.6）；重试簿记字段 `retry_count`/`next_retry_at` 由迁移 `ab1004w4a` 落库补齐

## v0.5 — AIHOT 热点功能融合 ✅（2026-09-30 集成审查通过）

> 预计开始：2026-10-01（提前完成）

**目标**：深度融合 AIHOT 的热点聚簇/评分/Feed 流/日报能力。

**任务**：
- [x] 深度分析 AIHOT 核心模块（聚簇算法、评分逻辑）— 口径已融进 `services/hot_cluster.py` / `hot_scorer.py` 实现（需求原文"48h 来源加权、24h 减半"）
- [x] 实现热点聚簇（多文章按主题聚合）— 标题字 bigram TF-IDF + 单链接凝聚聚类（τ 可调），Job type=`hot_cluster` 走 PG Job 队列，手动 API + 每日定时入队
- [x] 实现热度评分（48h 独立来源加权 + 24h 时间衰减）— `services/hot_scorer.py`，状态机 rising→hot→cooling→archived
- [x] 实现 Feed 流（类型/分类筛选 + 热度排序）— 三类生产者就位：文章入库（kb INDEXED 落点）、聚簇副作用、日报副作用；`(item_type,ref_id)` 唯一约束 upsert（`ab1004w2a`）
- [x] 实现每日日报（TOP 10 + LLM 摘要 + Markdown）— 非流式直连 SiliconFlow，失败降级中心文章首段截断；每日 06:30 自动生成前一日日报
- [x] 前端热点中心与日报页面 — 聚簇触发按钮、热度条形、状态过滤、react-markdown 真渲染、翻页

## v0.6 — 前端管理页增强

> 预计开始：2026-10-02

**任务**：
- [x] Bot 渠道管理页面（CRUD + 测试推送）— `frontend/app/bots/page.tsx`（W4，`d2678d7`）
- [x] 推送任务管理页面（创建/编辑/删除/日志）— `frontend/components/PushTasksTab.tsx`（W4）
- [x] 推送历史与投递状态展示 — 任务 Tab 日志弹窗复用 `listPushLogs`
- [x] 热点 Feed 流页面 — `frontend/app/hot/page.tsx`（含热度条/状态过滤/聚簇触发）
- [x] 每日日报页面 — `frontend/app/hot/daily/page.tsx`（react-markdown + 翻页）
- [x] 前端构建与 Playwright e2e — vitest 39 文件/335 用例 + mock e2e 入 CI（WD `1bbc749`）
- [x] 站内通知订阅侧（新增，FE-005）— 后端 SSE `system.py /notifications` + `NotificationBell`（WE）
- [x] 事件模板变量自足 + 投递重试/退避/死信（新增，PUSH-009 主体）— WB（集成者补完）
- [x] 热度评分接线与周期重评分（G1/G1b）— WA + 审查缝合

## v0.6.5 — 观测与安全运行时硬化（W6-W10）✅（2026-10-08 回填）

> 合并于 `main @ 8b1b5f2`；CI 首跑修复 `08c3935..7bdb964`。目标：结构化日志、指标暴露、
> 存活/就绪探针、运行时安全中间件、容器与编排硬化、运行期告警。

**任务**：
- [x] 结构化日志双模（structlog）— `core/logging.py` `configure_logging()`（prod=JSON/dev=Console，ProcessorFormatter 单出口桥接防重复行，全仓唯一 stdlib `getLogger`）；启动安装 `main.py:249`
- [x] Prometheus 指标 + `/metrics` — `core/metrics.py`（8 指标族）+ 纯 ASGI `MetricsMiddleware`（`main.py:259`）+ 独立 `metrics_router`（`main.py:264`，`include_in_schema=False` 不污染 OpenAPI 契约）
- [x] 存活/就绪探针 + schema 守卫 — `core/schema_guard.py`（复用启动 alembic head 探测）；`/live`（`system.py:119`）/`/ready`（PG+Redis+schema，不一致返 503，`system.py:128`）
- [x] 运行时安全中间件 — `core/security.py`：`RateLimitMiddleware`/`BodyLimitMiddleware`/`SecurityHeadersMiddleware`；经冻结接口 `install_security_middlewares(app)` 装配（`main.py:272-274`）
- [x] 容器与编排硬化 — `backend/Dockerfile`+`frontend/Dockerfile` 多阶段 + 非 root uid1000（`USER app`）+ `HEALTHCHECK`；`docker/compose.yml` 全服务 `logging.options`+`resources.limits`+read_only/tmpfs/cap_drop/no-new-privileges
- [x] 运行期告警（三类）— `core/alerting.py` `run_alert_checks`（心跳缺失/Job 积压/推送连败），复用既有 push provider；接线 `push_scheduler.py:86-88`（`ALERTING_ENABLED` 未置真即短路，开发零副作用）
- [x] 连接池容量守卫 — `db.py:85 assert_pool_capacity()`（进程数×池容量 ≤ PG max_connections，测试强制；启动 lifespan 自动调用待接）
- [x] 告警生产装配 — `compose.yml` 已注入 `ALERTING_ENABLED`/`ALERT_CHANNEL`/`ALERT_TARGET`/`ALERT_PUSH_FAIL_WINDOW`/`ALERT_JOB_BACKLOG` 五变量（默认关闭，`1eaa9b7`，S2.2 闭环；`docker/compose.yml:227-231`）
- [ ] 治理脚本入 CI 强制步 — `check_docs_consistency.py`/`gen_contracts.py` 就绪，CI 尚未编排为门禁 step（剩余项 R1.4）

## v0.7 — 目录结构迁移

> 预计开始：2026-10-03

**目标**：按 project-structure-design.md 执行 apps/ monorepo 迁移。

> **裁定回填（2026-10-08，`ff6e9da`）**：采用**轻量迁移**——整体 `git mv` 保 import 与
> 历史（backend→apps/api、frontend→apps/web），拒绝域级新旧并存（双源漂移）；
> 六边形 `src/modules/<域>` 深度重构**显式推迟立项**（等管理者拍板），下列未勾选项
> 即为推迟部分。ADR-0006 的 monorepo 目标结构已达成，仅未做域内分层。

**任务**：
- [x] apps/ monorepo 骨架落地（轻量迁移：apps/api + apps/web + packages/contracts，375 rename）
- [ ] 创建 apps/api/src/modules/ 目录骨架（**推迟立项**）
- [ ] 创建 apps/web/src/features/ 目录骨架（**推迟立项**）
- [ ] 后端逐域迁移（hot → bot → identity → knowledge → ...）（**推迟立项**，随六边形重构）
- [ ] 前端 features 拆分（**推迟立项**，随六边形重构）
- [x] packages/contracts/ 共享契约提取（common 三组 + 6 域 dto.ts 生成并 index.ts 导出，`4d8ecd9`；identity/chat/engine 骨架待接）
- [ ] database/migrations/ 和 infra/docker/ 迁移（**裁定不迁移**：alembic 留 apps/api/alembic、compose 留 docker/，移动只破坏 CI/alembic.ini 无收益）
- [x] 迁移后全量测试（隔离 PG 968 passed/4 skipped + vitest 359 绿 + tsc 零错，`ff6e9da`）

## v1.0 — 正式发布

> 预计开始：2026-10-04

**任务**：
- [ ] 全量测试通过（后端单元 + 前端构建 + e2e + docker compose 冒烟）
- [ ] README 更新（功能说明 + 部署指南）
- [ ] CHANGELOG.md 编写
- [ ] 推送到 GitHub aideanew/BotHot
