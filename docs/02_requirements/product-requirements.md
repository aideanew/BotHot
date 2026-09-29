---
id: REQ-BASELINE
type: requirement
title: BotHot 功能需求基线
status: active
owner: product
created: 2026-09-29
updated: 2026-09-29
version: 1.0
---

# BotHot 功能需求基线

> 本文件描述当前有效的正式需求基线。历史需求通过 features/ 目录保留。

---

## 一、业务域识别

BotHot 后端识别出 **9 个业务域**，前端识别出 **10 个功能域**。

### 后端业务域

| # | 业务域 | 核心职责 | 数据模型 | API 路由 |
|---|---|---|---|---|
| 1 | identity | 用户认证、SSO、会话、角色门禁 | User | auth.py |
| 2 | knowledge | 知识空间、内容资产、公共库 | KnowledgeSpace, ContentAsset, ShortLinkMap | spaces.py |
| 3 | subscription | 信息源订阅、Manifest Diff、同步调度 | Source, SourceSubscription, ArticleManifest | subscriptions.py |
| 4 | ingest | 文章入库流水线、Job 执行、质量评分 | Job, JobItem | extract.py |
| 5 | chat | RAG 问答、SSE 流式、意图检测 | — | chat.py, resolve.py |
| 6 | engine | 可插拔引擎管理、引擎密钥、嵌入/重排 | — | engines.py |
| 7 | bot | 多渠道推送、渠道配置、推送任务、推送日志 | BotChannel, PushTask, PushLog | bots.py |
| 8 | hot | 热点聚簇、热度评分、Feed 流、每日日报 | HotTopic, HotTopicArticle, DailyReport, FeedItem | hot.py |
| 9 | system | 系统管理、健康检查、Onboarding、进程心跳 | ProcessHeartbeat | admin.py, onboarding.py, system.py |

### 前端功能域

| # | 功能域 | 核心页面 | API 模块 |
|---|---|---|---|
| 1 | auth | /auth/aidean/callback | auth.ts |
| 2 | knowledge | /spaces, /spaces/[id], /public | spaces.ts, public-library.ts |
| 3 | subscription | /subscriptions | subscriptions.ts |
| 4 | ingest | /jobs, 添加文章面板 | jobs.ts, ingest.ts, batch.ts |
| 5 | chat | /chat | ask.ts |
| 6 | engine | /engines | engines.ts |
| 7 | bot | /bots | bots.ts |
| 8 | hot | /hot, /hot/daily | hot.ts |
| 9 | admin | /admin | admin.ts |
| 10 | onboarding | /onboarding | — |

---

## 二、功能需求清单

### REQ-F-001：多渠道机器人推送
- **实现状态**：✅ 六种渠道 Provider 已实现真实投递（飞书/钉钉/企微/Webhook/站内通知已通，微信 ClawBot 需部署服务）；PushScheduler 在 backend 进程内 60s 调度；事件触发待实现
- **渠道**：飞书、钉钉、企业微信、微信 ClawBot、通用 Webhook、站内通知
- **触发方式**：定时（Cron）、事件触发（新文章/热点更新/日报）、手动
- **管理**：渠道 CRUD、推送任务 CRUD、推送日志查询、一键测试
- **验收**：各渠道 Webhook 推送可成功送达，定时任务按 Cron 准时触发

### REQ-F-002：热点聚簇与日报
- **聚簇**：多篇文章按主题聚簇为热点事件
- **评分**：48h 独立来源数加权，24h 减半时间衰减
- **Feed**：信息流首页，类型/分类筛选，热度排序
- **日报**：TOP 10 热点 + LLM 生成摘要，Markdown 格式
- **验收**：聚簇结果合理，日报可自动/手动生成

### REQ-F-003：知识库管理
- 多空间隔离（用户级 + 公共库）
- LangBot RAG 1:1 映射
- 可插拔引擎（builtin / langbot / aidean / redfox）
- 公共库共享与发布（allowlist）
- **验收**：空间 CRUD 正常，引擎切换可用

### REQ-F-004：公众号链接入库
- 链接解析（RedFox + Wandao）
- 内容标准化（Markdown + 元数据）
- 质量评分与分类标签
- 短链映射（0 重复请求）
- **验收**：公众号文章可入库为 ContentAsset

### REQ-F-005：RAG 知识问答
- SSE 流式问答
- 多空间会话路由
- 检索重排（Reranker 可选）
- **验收**：问答流式响应正常，命中知识库

### REQ-F-006：整号订阅与增量同步
- 订阅一个公众号的全部文章
- Manifest Diff 水位机制
- 固定时点锚 / 滑动窗口
- 空轮询退避
- **验收**：增量同步只拉新文章，水位正确推进

### REQ-F-007：SSO 统一认证
- OIDC 接入主平台
- 身份锚点 = users.sub
- 会话 Cookie（HttpOnly + SameSite=Lax）
- 角色门禁（admin / operator / user）
- Backchannel Logout
- **验收**：SSO 登录/登出正常，角色门禁生效

### REQ-F-008：管理后台
- 知识空间 / 文档 / 订阅 / 引擎管理
- Bot 渠道 / 推送任务管理
- 热点中心 / 日报管理
- Onboarding 引导
- **验收**：管理端各功能 CRUD 正常

---

## 三、非功能需求

### REQ-NF-001：性能
- API 响应 < 500ms（非 LLM 调用）
- RAG 问答首 Token < 3s
- 文章入库单篇 < 30s
- Feed 分页查询 < 100ms

### REQ-NF-002：安全
- SSO Cookie HttpOnly + SameSite=Lax
- 渠道密钥 AES-256-GCM 加密落库
- 生产环境 OIDC iss/aud 校验
- CORS 白名单
- SQL 注入防护（ORM 参数化）

---

## 四、约束需求

### REQ-C-001：技术栈
- 后端：Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic
- 前端：Next.js 14 + TypeScript + Tailwind CSS + pnpm
- 数据库：PostgreSQL 16
- 缓存：Redis 7
- 知识引擎：LangBot
- 容器：Docker Compose

### REQ-C-002：端口分配
- 3000 = 主平台专用（禁止占用）
- 3200 = BotHot 前端宿主端口
- 3300 = BotHot 后端端口
- 5300 = LangBot
- 5433 = PostgreSQL
- 6380 = Redis
