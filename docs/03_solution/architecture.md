---
id: ARCHITECTURE
type: architecture
title: BotHot 系统架构设计
status: active
owner: architecture
created: 2026-09-29
updated: 2026-09-29
version: 1.0
---

# BotHot 系统架构设计

## 1. 系统全景

```text
┌─────────────────────────────────────────────────────────────────┐
│                        用户浏览器                                 │
│                   BotHot Frontend (Next.js)                      │
│                      localhost:3200                              │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP / SSE
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     BotHot Backend                               │
│                   FastAPI / Python 3.12                          │
│                      localhost:3300                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ Web 层    │ │Scheduler │ │ Worker   │ │ Push Scheduler   │  │
│  │ (uvicorn)│ │ (常驻进程)│ │(常驻进程) │ │ (in-process)     │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └───────┬──────────┘  │
│       │            │            │               │              │
│       └────────────┴────────────┴───────────────┘              │
│                        │                                         │
│              ┌─────────┴──────────┐                             │
│              │   PostgreSQL 16     │                            │
│              │   (Job 队列 + 状态)  │                            │
│              └────────────────────┘                             │
│              ┌────────────────────┐                             │
│              │   Redis 7          │                             │
│              │  (Session/Cache)   │                            │
│              └────────────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌──────────┐    ┌──────────┐    ┌──────────────┐
    │ LangBot  │    │ RedFox   │    │ 主平台(OIDC)  │
    │  :5300   │    │ (外部API) │    │   :3000      │
    │ RAG 引擎 │    │ 文章采集  │    │  SSO 认证    │
    └──────────┘    └──────────┘    └──────────────┘
                         ▲
                         │ 文章来源平台（providers/article_sources/）
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ Dajiala  │  │JustOneAPI│  │ TikHub   │  │ Wellbyte │
    │ 极致了   │  │          │  │          │  │  数井    │
    │发现+详情 │  │发现+详情 │  │发现+搜索 │  │搜索+发现 │
    └──────────┘  └──────────┘  └──────────┘  └──────────┘
```

## 2. 进程拓扑

BotHot 后端有 **3 个独立进程 + 1 个进程内调度器**，共享同一份代码镜像：

| 进程 | 入口 | 职责 | 端口 |
|---|---|---|---|
| Web 层 | `app.main:app` (uvicorn) | REST API + SSE + OpenAPI | 3300 |
| Scheduler | `app.services.scheduler` | 订阅调度 + 文档状态推进 | 无（心跳） |
| Worker | `app.services.job_worker` | 文章入库流水线（FOR UPDATE SKIP LOCKED） | 无（心跳） |
| Push Scheduler | `app.services.push_scheduler` | 定时推送任务调度（**进程内**，FastAPI lifespan 启动） | 3300（共享） |

> Job 队列在 PostgreSQL（`FOR UPDATE SKIP LOCKED`），不经 Redis。
> 进程心跳写入 `process_heartbeats` 表，供 healthcheck 探测。

## 3. 业务域架构

```text
┌──────────────────────────────────────────────────────┐
│                    interfaces/ (HTTP)                 │
│   auth │ spaces │ subscriptions │ extract │ chat     │
│   engines │ bots │ hot │ admin │ system │ onboarding │
├──────────────────────────────────────────────────────┤
│                  application/ (用例编排)               │
│   commands │ queries │ services                       │
├──────────────────────────────────────────────────────┤
│                    domain/ (业务核心)                  │
│                                                        │
│  ┌─────────┐ ┌──────────┐ ┌────────────┐            │
│  │identity │ │knowledge │ │subscription│            │
│  └─────────┘ └──────────┘ └────────────┘            │
│  ┌─────────┐ ┌──────────┐ ┌────────────┐            │
│  │ ingest  │ │  chat    │ │  engine    │            │
│  └─────────┘ └──────────┘ └────────────┘            │
│  ┌─────────┐ ┌──────────┐ ┌────────────┐            │
│  │  bot    │ │   hot    │ │  system    │            │
│  └─────────┘ └──────────┘ └────────────┘            │
├──────────────────────────────────────────────────────┤
│                infrastructure/ (技术实现)             │
│  persistence(SQLAlchemy) │ cache(Redis) │ external   │
│  LangBot client │ RedFox client │ OIDC client        │
│  Push providers (feishu/dingtalk/wechat_work/...)    │
└──────────────────────────────────────────────────────┘
```

## 4. 数据模型全景

```text
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   User      │1───*│ KnowledgeSpace   │1───*│  ContentAsset   │
│ (sub,email, │     │ (name,engine,    │     │ (markdown,hash, │
│  role)      │     │  is_public)      │     │  quality,category)│
└──────┬──────┘     └────────┬─────────┘     └────────┬────────┘
       │                     │                         │
       │1───*          1───*│                    1───*│
       │                     │                         │
┌──────┴──────┐     ┌────────┴─────────┐     ┌────────┴────────┐
│SourceSubsc- │     │SourceSubscription│     │  ArticleManifest │
│ ription     │     │ (sync_policy,    │     │ (external_id,    │
│(anchor_hour,│     │  water_level)    │     │  content_hash)   │
│ next_run_at)│     └──────────────────┘     └──────────────────┘
└─────────────┘

┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ BotChannel  │1───*│   PushTask       │1───*│    PushLog      │
│(channel_    │     │(trigger_type,    │     │(status, content,│
│ type,webhook│     │ cron_expr,       │     │ response)       │
│ secret_enc) │     │ content_template)│     │                  │
└─────────────┘     └──────────────────┘     └─────────────────┘

┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  HotTopic   │1───*│HotTopicArticle   │     │  DailyReport    │
│(title,summ- │     │(relevance_score) │     │(date, markdown, │
│ ary,score,  │     └──────────────────┘     │ topic_count)    │
│ status)     │                               └─────────────────┘
└─────────────┘
│
│     ┌───────────┐
│1───*│ FeedItem  │
│     │(type,ref, │
│     │ score)    │
│     └───────────┘
```

## 5. 推送架构

```text
PushTask 到期/事件触发
        │
        ▼
PushScheduler (backend 进程内, FastAPI lifespan, 60s 间隔)
        │
        ├──→ BotChannel(飞书)    → FeishuProvider    → 飞书 Webhook API
        ├──→ BotChannel(钉钉)    → DingTalkProvider  → 钉钉 Webhook API
        ├──→ BotChannel(企微)    → WechatWorkProvider→ 企微 Webhook API
        ├──→ BotChannel(ClawBot)→ ClawBotProvider   → 微信 ClawBot API
        ├──→ BotChannel(Webhook)→ WebhookProvider   → 自定义 URL
        └──→ BotChannel(站内)   → WebProvider       → Redis pub/sub
                │
                ▼
            PushLog (投递记录)

> **实现说明**：BotHot 有两套推送代码路径——
> - **新** `providers/push/` 包：6 个渠道，全部 `implemented=True`，真实 HTTP 投递。`bots.py` 和 `push_scheduler.py` 使用此包。
> - **旧** `providers/push_port.py`（AideanBot 遗留）：2 个渠道（web/clawbot），`implemented=False` 占位。`services/push.py` 仍引用此端口。
> - 迁移 `push.py` 到新包是 TECH-001 的工作（见 backlog）。
```

## 6. SSO 认证流程

```text
用户访问 BotHot
    │
    ▼ (未登录)
GET /api/v1/auth/login
    │
    ▼ (302 重定向)
主平台 OIDC Authorize
    │
    ▼ (用户授权)
BotHot /auth/aidean/callback
    │
    ▼ (OIDC token 交换)
后端获取 userinfo → 创建/更新 User 快照
    │
    ▼ (Set-Cookie)
bothot_session (HttpOnly, SameSite=Lax)
    │
    ▼
已登录状态
```

## 7. 关键设计决策

| ADR | 决策 | 核心结论 |
|---|---|---|
| ADR-0001 | RAG 引擎选型 | LangBot 作为知识引擎，1:1 映射知识空间 |
| ADR-0002 | 消息拓扑与 LLM 计费路径 | LLM 流式直连 SiliconFlow，不经 LangBot 转发 |
| ADR-0003 | 会话与知识空间解析规则 | 会话路由通过 intent + resolver 解析目标空间 |
| ADR-0004 | 知识库引擎可插拔 | EnginePort 抽象 + 注册表，多后端切换零迁移 |

## 8. 部署架构

```text
docker compose -f docker/compose.yml
│
├── postgres:16-alpine        (5433:5432)
├── redis:7-alpine            (6380:6379)
├── langbot:latest            (5300:5300)
├── langbot_plugin_runtime    (内部网络)
├── backend (bothot-backend)  (3300:3300)
│   ├── migrate (一次性)
│   ├── scheduler (常驻)
│   └── worker (常驻)
└── frontend (bothot-frontend)(3200:3000)
```

## 9. 目标目录架构（详见 project-structure-design.md）

当前项目使用 `backend/` + `frontend/` 扁平结构。目标是迁移到规范化的 `apps/` 结构：

```text
BotHot/
├── apps/
│   ├── api/          # 后端（按 9 个业务域组织）
│   └── web/          # 前端（按 10 个功能域组织）
├── packages/
│   └── contracts/    # 前后端共享契约（纯类型；前端经 tsconfig paths + import type 消费，
│                     #   非 npm 依赖——仓库无 pnpm workspace 根，见 frontend/tsconfig.json）
├── database/
│   └── migrations/   # Alembic 迁移
├── infra/
│   └── docker/       # Docker Compose
├── docs/             # 项目文档
└── scripts/          # 自动化脚本
```

详细设计见 [project-structure-design.md](project-structure-design.md)。
