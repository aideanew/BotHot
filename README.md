# BotHot

> 公众号链接 → 知识库 → 多渠道机器人推送 闭环

BotHot 是从 AideanBot 全面升级而来的多渠道机器人推送与知识管理平台。在原有"公众号链接入库 → LangBot 知识问答"闭环基础上，新增了多渠道主动推送能力（飞书/钉钉/企业微信/微信 ClawBot/通用 Webhook/站内通知），并融合 AIHOT 的热点聚簇与日报功能。

## 核心能力

### 1. 多渠道机器人推送
- **六种渠道**：飞书、钉钉、企业微信、微信 ClawBot、通用 Webhook、站内通知
- **定时推送**：Cron 表达式驱动，支持每天定时、周期推送
- **事件触发**：新文章入库、热点更新等事件自动触发推送
- **测试推送**：管理端一键测试渠道连通性
- **推送日志**：完整投递记录，成功/失败/响应摘要

> ✅ **当前实现状态**：渠道管理 API、推送任务模型、推送日志模型已建成。六种渠道的 PushProvider 均已实现真实投递（飞书/钉钉/企微/Webhook/站内通知已通，微信 ClawBot 需部署 ClawBot 服务后可用）。PushScheduler 以 60s 间隔在 backend 进程内运行（FastAPI lifespan）。详见 [待办清单](docs/04_engineering/backlog.md)。

### 2. 热点聚簇与日报（融合 AIHOT）
- **热点聚簇**：多篇文章按主题聚簇为事件，按热度排序
- **热度评分**：48h 内独立来源数加权，24h 减半
- **Feed 流**：信息流首页，支持类型/分类筛选
- **每日日报**：自动取 TOP 10 热点生成 Markdown 日报

> ⚠️ **当前实现状态**：数据模型已建（HotTopic, DailyReport, FeedItem），聚簇/评分/日报逻辑待 v0.5 落地。

### 3. 知识库管理（继承 AideanBot）
- 公众号链接解析入库（RedFox + 4 平台文章来源：Dajiala/JustOneAPI/TikHub/Wellbyte）
- LangBot RAG 知识引擎
- 多空间隔离、公共库共享
- 整号订阅与增量同步

## 技术架构

```
PostgreSQL 16  ←  Backend (FastAPI / Python 3.12)
Redis 7            ├─ REST API (port 3300)
                   ├─ Push Scheduler (定时推送调度)
                   ├─ Subscription Scheduler (订阅同步)
                   └─ Job Worker (文章入库)
LangBot 5300  ←  知识引擎 (RAG)
Frontend (Next.js 14 / Node 22)  →  port 3200
```

### 端口规范

| 服务       | 宿主端口 | 容器端口 |
|-----------|---------|---------|
| Frontend  | 3200    | 3000    |
| Backend   | 3300    | 3300    |
| LangBot   | 5300    | 5300    |
| PostgreSQL| 5433    | 5432    |
| Redis     | 6380    | 6379    |

> 端口 3000 归主平台，BotHot 前端统一使用 3200。

## 项目文档

所有文档在 `docs/` 目录，入口导航见 [docs/00_governance/project-map.md](docs/00_governance/project-map.md)。

| 文档 | 说明 |
|---|---|
| [产品愿景](docs/01_product/product-vision.md) | BotHot 要解决什么问题 |
| [功能需求基线](docs/02_requirements/product-requirements.md) | 9 个后端业务域 + 10 个前端功能域 |
| [系统架构设计](docs/03_solution/architecture.md) | 进程拓扑、数据模型、推送架构、SSO 流程 |
| [项目目录架构设计](docs/03_solution/project-structure-design.md) | apps/ monorepo 目标结构 + 迁移策略 |
| [工程规范](docs/04_engineering/conventions.md) | 端口、命名、Git、测试、安全规范 |
| [路线图](docs/04_engineering/roadmap.md) | v0.3 → v1.0 路线图 |
| [待办清单](docs/04_engineering/backlog.md) | 按优先级排列的待办任务 |

## 快速开始

### Docker Compose 部署

```bash
# 1. 配置环境变量
cp docker/.env.example docker/.env
# 编辑 docker/.env，填入 REDFOX_API_KEY、LLM_API_KEY 等

# 2. 启动全栈
docker compose -f docker/compose.yml up -d

# 3. 检查状态
docker compose -f docker/compose.yml ps
```

### 本地开发

```bash
# 后端
cd backend
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 3300

# 前端
cd frontend
pnpm install
pnpm dev  # 自动在 3200 端口启动
```

## API 概览

### 机器人渠道管理
- `GET    /api/v1/bots/channels`         — 可用渠道类型
- `POST   /api/v1/bots`                  — 创建渠道
- `GET    /api/v1/bots`                  — 渠道列表
- `PUT    /api/v1/bots/{id}`             — 更新渠道
- `DELETE /api/v1/bots/{id}`             — 删除渠道
- `POST   /api/v1/bots/{id}/test`        — 测试推送
- `GET    /api/v1/bots/{id}/logs`        — 推送日志

### 推送任务
- `POST   /api/v1/bots/tasks`            — 创建推送任务
- `GET    /api/v1/bots/tasks`            — 任务列表
- `POST   /api/v1/bots/tasks/{id}/run`   — 手动触发
- `DELETE /api/v1/bots/tasks/{id}`       — 删除任务

### 热点与日报
- `GET    /api/v1/hot/topics`            — 热点列表
- `GET    /api/v1/hot/topics/{id}`       — 热点详情
- `POST   /api/v1/hot/topics/cluster`    — 触发聚簇
- `GET    /api/v1/hot/daily/reports`     — 日报列表
- `GET    /api/v1/hot/daily/reports/{date}` — 日报详情
- `POST   /api/v1/hot/daily/generate`    — 生成日报
- `GET    /api/v1/hot/feed`              — Feed 流

## 项目结构（当前）

```
BotHot/
├── backend/
│   ├── app/
│   │   ├── api/v1/                    # API 路由（9 个业务域）
│   │   ├── models/                    # 数据模型
│   │   ├── services/                  # 业务服务
│   │   ├── providers/                 # 外部服务适配器
│   │   └── core/                      # 横切关注点
│   └── alembic/                       # 数据库迁移
├── frontend/
│   ├── app/                           # Next.js App Router 页面
│   ├── components/                    # React 组件
│   └── lib/api/                       # API 调用模块
├── docker/
│   ├── compose.yml                    # Docker Compose 编排
│   └── .env.example                   # 环境变量模板
├── docs/                              # 项目文档（00_governance ~ 09_archive）
├── scripts/                           # 自动化脚本
├── AGENTS.md                          # AI 协作规范
└── README.md                          # 本文件
```

> 目标目录架构（apps/ monorepo）见 [项目目录架构设计](docs/03_solution/project-structure-design.md)。

## 与 AideanBot 的关系

BotHot 是 AideanBot 的全面升级版：
- **保留**：公众号链接入库、LangBot RAG、知识空间管理、SSO 认证、整号订阅
- **新增**：多渠道推送（6 种渠道）、定时推送调度、热点聚簇、每日日报、Feed 流
- **改名**：AideanBot → BotHot（session cookie、项目名、容器名全部更新）
- **端口**：前端 3200、后端 3300

## License

MIT
