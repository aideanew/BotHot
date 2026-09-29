---
id: BACKLOG
type: backlog
title: BotHot 待办清单
status: active
owner: product
created: 2026-09-29
updated: 2026-09-29
---

# BotHot 待办清单

> 状态标记：✅ 已完成 | 🔧 部分完成 | ⬜ 未开始

## ✅ 已完成（BotHot 新增能力）

### PUSH-001~006：六种渠道 PushProvider ✅
- **状态**：全部实现真实投递（`providers/push/` 包）
- **飞书**：交互式卡片消息 + HMAC-SHA256 加签 ✅
- **钉钉**：Markdown 消息 + HMAC-SHA256 加签 ✅
- **企业微信**：Markdown 消息 ✅
- **通用 Webhook**：POST JSON + HTTP 2xx 校验 ✅
- **微信 ClawBot**：Bearer token 鉴权 + `/api/send` 调用 ✅（需部署 ClawBot 服务）
- **站内通知**：Redis pub/sub → `bothot:notifications:{user_id}` ✅

> **注意**：旧 `providers/push_port.py`（AideanBot 遗留）仍存在，仅含 web/clawbot 两个占位
> Provider（`implemented=False`）。`services/push.py` 仍引用旧端口；`bots.py` 和
> `push_scheduler.py` 已使用新 `providers/push/` 包。迁移 `push.py` 到新包是 TECH-001 的工作。

### ARTSRC-001~004：四平台文章来源 Provider ✅
- **状态**：4 个第三方 API 平台已接入（`providers/article_sources/` 包）
- **Dajiala 极致了**：post_condition 发现 + article_html 详情兜底（¥0.04~0.14/次）✅ 活体实测
- **JustOneAPI**：get-account-history-articles/v2 发现 + get-article-detail/v1 详情兜底（¥0.15~0.40/次）✅ 活体实测
- **TikHub**：fetch_account_articles 发现 + fetch_search 搜索 ✅ 契约级（OpenAPI 读取 + 鉴权实测，付费端点 402 需充值）
- **Wellbyte 数井**：article_v1 搜索 + account_history_v2 发现 ✅ 活体实测（detail_v2 三连 422 禁用）
- **发现注册**：4 平台已注册到 `discovery/registry.py`，与 RedFox 共存，后台 `discovery_channels` 白名单可控
- **详情兜底**：`ArticleDetailFallbackCoordinator` 按成本排序（Dajiala ¥0.04 → JustOneAPI ¥0.15），总开关 `ARTICLE_DETAIL_FALLBACK_ENABLED`
- **item_show_type 检测**：`parse_item_show_type` / `is_gallery_type` 已加入 source_resolver，图集类(=8)不触发付费兜底
- **测试证据**：`docs/06_validation/evidence/channeltest-20260929/`

### PUSH-007：PushScheduler 定时调度 ✅
- **状态**：已实现，在 backend 进程内运行（FastAPI lifespan 启动/停止）
- **调度间隔**：60s
- **Cron 解析**：简版，支持 `HH:MM`（每天定时）和 `*/N`（每 N 小时）
- **完整 croniter 支持**：待 TECH-002

### 渠道管理 API ✅
- `GET/POST/PUT/DELETE /api/v1/bots` — 渠道 CRUD
- `POST /api/v1/bots/{id}/test` — 测试推送
- `GET /api/v1/bots/{id}/logs` — 推送日志
- `POST/GET/DELETE /api/v1/bots/tasks` — 推送任务管理
- `POST /api/v1/bots/tasks/{id}/run` — 手动触发

## 🔴 高优先级

### PUSH-008：事件触发推送 ⬜
- **当前状态**：模型已建（`trigger_type=event`），调度未实现
- **目标**：新文章入库/热点更新/日报生成时自动触发推送
- **验收**：文章 INDEXED → 自动推送到绑定的 event 类型渠道

### TECH-001：迁移 push.py 到新 Provider 包 🔧
- **当前状态**：`services/push.py` 仍 import 旧 `providers/push_port.py`
- **目标**：统一到 `providers/push/` 包，删除旧 `push_port.py`
- **风险**：需确认 `push.py` 的调用方（如有）不受影响

### TECH-002：PushScheduler 完整 Cron 支持 ⬜
- **当前状态**：仅支持 `HH:MM` 和 `*/N`，不支持标准 5 段 cron
- **目标**：引入 croniter 或实现完整 cron 解析
- **验收**：`*/5 * * * *`（每 5 分钟）等标准表达式可正确调度

## 🟡 中优先级

### HOT-001：热点聚簇算法 ⬜
- **当前状态**：模型已建（HotTopic, HotTopicArticle），API 为占位
- **目标**：多篇文章按主题聚簇为热点事件（LLM + 向量相似度）
- **参考**：AIHOT 项目聚簇逻辑
- **当前 API**：`POST /api/v1/hot/topics/cluster` 返回 stub 响应

### HOT-002：热度评分 ⬜
- **当前状态**：模型有 `hot_score` 字段，计算逻辑未实现
- **目标**：48h 独立来源数加权 + 24h 减半时间衰减

### HOT-003：Feed 流 ✅
- **状态**：API 已实现（`GET /api/v1/hot/feed`），支持类型/分类筛选 + 热度排序
- **前端**：`/hot` 页面骨架已建

### HOT-004：每日日报生成 ✅
- **状态**：API 已实现（`POST /api/v1/hot/daily/generate`），TOP 10 热点 → Markdown
- **前端**：`/hot/daily` 页面骨架已建

### FE-001：Bot 渠道管理页面 🔧
- **当前状态**：页面已建（`/bots`），渠道列表 + 创建/编辑 + 测试推送 + 日志
- **待完善**：推送任务管理 UI（Cron 编辑器）

### FE-002：推送任务管理页面 ⬜
- **当前状态**：API 已通，前端 UI 未建
- **目标**：推送任务 CRUD + Cron 编辑 + 日志查看

### FE-003：热点 Feed 页面 🔧
- **当前状态**：页面已建（`/hot`），Feed 流展示 + 筛选
- **待完善**：热度可视化、状态徽章交互

### FE-004：每日日报页面 🔧
- **当前状态**：页面已建（`/hot/daily`）
- **待完善**：Markdown 渲染优化 + 历史翻页

## 🟢 低优先级

### MIG-001：后端 apps/api/ 目录迁移
- **参考**：project-structure-design.md 阶段化迁移策略

### MIG-002：前端 apps/web/ 目录迁移
- **参考**：project-structure-design.md 阶段化迁移策略

### MIG-003：packages/contracts/ 共享契约提取

### TEST-001：后端单元测试补全
- **目标**：各业务域 core/application 层测试覆盖
- **重点**：PushProvider 单测（mock httpx）、PushScheduler 调度逻辑

### TEST-002：Playwright e2e 测试
- **目标**：关键用户流程端到端验证
- **端口**：3200（禁止 3333）

### TEST-003：Docker Compose 冒烟测试
- **目标**：docker compose up 全服务启动验证

### DOC-001：README 更新 ✅
- **状态**：已完成功能说明 + 快速开始 + 部署指南

### DOC-002：CHANGELOG.md 编写
