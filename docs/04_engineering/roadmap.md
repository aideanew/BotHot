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

## 当前阶段：v0.3 — 文档架构与目录结构规范化

> 完成时间：2026-09-29

**目标**：基于项目文档规范与工程结构规范，完成 BotHot 文档架构和目录架构的重新设计。

**交付物**：
- [x] docs/ 文档体系（00_governance ~ 04_engineering）
- [x] 功能需求基线（9 后端业务域 + 10 前端功能域）
- [x] 系统架构设计文档
- [x] 项目目录架构设计文档（apps/ monorepo 结构）
- [x] ADR 决策索引
- [x] AGENTS.md 更新

---

## 下一阶段：v0.4 — 推送能力落地

> 预计开始：2026-09-30
> 勾选状态同步：2026-09-30（W5 依代码实证回填；此前目标句称"已实现"，下方任务却全未勾选，自相矛盾）

**目标**：多渠道推送已实现真实投递（6 渠道 Provider + PushScheduler），待完善事件触发和完整 Cron 支持。

**任务**：
- [x] 实现飞书 Webhook Provider（真实推送）— `providers/push/feishu.py`（交互式卡片 + HMAC-SHA256 加签）
- [x] 实现钉钉 Webhook Provider — `providers/push/dingtalk.py`（Markdown + HMAC-SHA256 加签）
- [x] 实现企业微信 Webhook Provider — `providers/push/wechat_work.py`（Markdown）
- [x] 实现 微信 ClawBot Provider — `providers/push/wechat_clawbot.py`（Bearer token + `/api/send`；需部署 ClawBot 服务）
- [x] 实现通用 Webhook Provider — `providers/push/webhook.py`（POST JSON + HTTP 2xx 校验）
- [x] 实现站内通知 Provider — `providers/push/web.py`（Redis pub/sub → `bothot:notifications:*`；**投递侧**已完成，前端订阅侧未实现）
- [x] PushScheduler 定时调度落地 — `services/push_scheduler.py:27`（60s 扫描）在 `main.py:247` lifespan 内启动；Cron 解析为**简版**（`HH:MM` / `*/N` / 纯数字分钟，`push_scheduler.py:30-68`），完整 croniter 支持见 TECH-002
- [ ] 事件触发推送（新文章/热点更新/日报生成）— `_tick` 仅筛选 `trigger_type == "cron"`（`push_scheduler.py:112-119`），无 event 分支
- [ ] 推送日志查询与重试机制 — 日志已落 `PushLog`（`push_scheduler.py:166-174`）与查询 API（`api/v1/bots.py:301,320`），**重试未实现**（无重试计数/退避）

## v0.5 — AIHOT 热点功能融合

> 预计开始：2026-10-01

**目标**：深度融合 AIHOT 的热点聚簇/评分/Feed 流/日报能力。

**任务**：
- [ ] 深度分析 AIHOT 核心模块（聚簇算法、评分逻辑）
- [ ] 实现热点聚簇（多文章按主题聚合）
- [ ] 实现热度评分（48h 独立来源加权 + 24h 时间衰减）
- [ ] 实现 Feed 流（类型/分类筛选 + 热度排序）
- [ ] 实现每日日报（TOP 10 + LLM 摘要 + Markdown）
- [ ] 前端热点中心与日报页面

## v0.6 — 前端管理页增强

> 预计开始：2026-10-02

**任务**：
- [ ] Bot 渠道管理页面（CRUD + 测试推送）
- [ ] 推送任务管理页面（创建/编辑/删除/日志）
- [ ] 推送历史与投递状态展示
- [ ] 热点 Feed 流页面
- [ ] 每日日报页面
- [ ] 前端构建与 Playwright e2e

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
