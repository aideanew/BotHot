---
id: ROADMAP
type: roadmap
title: BotHot 路线图
status: active
owner: product
created: 2026-09-29
updated: 2026-09-30
version: 1.0
---

# BotHot 路线图

## 当前阶段：v0.6 — 前端管理页增强与工程加固

> v0.4/v0.5 已于 2026-09-30 交付；v0.6 由五路并行（WA-WB-WC-WD-WE）+ 集成审查完成

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
- [ ] 推送日志查询与**重试**机制 — 日志查询已完成（`api/v1/bots.py`），**重试未实现**（无重试计数/退避；当前失败仅落 `PushLog(status=failed)`）

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

## v0.7 — 目录结构迁移

> 预计开始：2026-10-03

**目标**：按 project-structure-design.md 执行 apps/ monorepo 迁移。

**任务**：
- [ ] 创建 apps/api/src/modules/ 目录骨架
- [ ] 创建 apps/web/src/features/ 目录骨架
- [ ] 后端逐域迁移（hot → bot → identity → knowledge → ...）
- [ ] 前端 features 拆分
- [ ] packages/contracts/ 共享契约提取
- [ ] database/migrations/ 和 infra/docker/ 迁移
- [ ] 迁移后全量测试

## v1.0 — 正式发布

> 预计开始：2026-10-04

**任务**：
- [ ] 全量测试通过（后端单元 + 前端构建 + e2e + docker compose 冒烟）
- [ ] README 更新（功能说明 + 部署指南）
- [ ] CHANGELOG.md 编写
- [ ] 推送到 GitHub aideanew/BotHot
