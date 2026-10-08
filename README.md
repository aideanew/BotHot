# BotHot

> 公众号链接 → 知识库 → 多渠道机器人推送 闭环

BotHot 是从 AideanBot 全面升级而来的多渠道机器人推送与知识管理平台。在原有"公众号链接入库 → LangBot 知识问答"闭环基础上，新增了多渠道主动推送能力（飞书/钉钉/企业微信/微信 ClawBot/通用 Webhook/站内通知），并融合 AIHOT 的热点聚簇与日报功能。

## 核心能力

### 1. 多渠道机器人推送
- **六种渠道**：飞书、钉钉、企业微信、微信 ClawBot、通用 Webhook、站内通知
- **定时推送**：Cron 表达式驱动（croniter 完整 5 段式 + `HH:MM` / `*/N` / 纯数字简写兼容）
- **事件触发**：新文章入库、热点更新、日报生成事件自动触发推送（PG outbox 表 `push_events`：worker 进程 emit → backend 调度器 claim 消费；事件延迟下限 = 60s 扫描间隔）
- **测试推送**：管理端一键测试渠道连通性
- **推送日志**：完整投递记录，成功/失败/响应摘要

> ✅ **当前实现状态**：渠道管理 API、推送任务模型、推送日志模型已建成。六种渠道的 PushProvider 均已实现真实投递（飞书/钉钉/企微/Webhook/站内通知已通，微信 ClawBot 需部署 ClawBot 服务后可用）。渠道密钥以 AES-256-GCM 落库（AAD 绑定渠道 id，`PUSH_SECRET_MASTER_KEY` fail-closed）。PushScheduler 以 60s 间隔在 backend 进程内运行（FastAPI lifespan），到期任务以 `FOR UPDATE SKIP LOCKED` 领取。
>
> ✅ **缺口已闭环（2026-10-08）**：① 站内通知全链路（SSE 订阅 + 持久化落库 + 离线补投 history + 已读回执，FE-005/NOTIF-001）；② 投递重试（指数退避 + 死信终态，PUSH-009）。

### 2. 热点聚簇与日报（融合 AIHOT）
- **热点聚簇**：多篇文章按主题聚簇为事件，按热度排序
- **热度评分**：48h 内独立来源数加权，24h 减半
- **Feed 流**：信息流首页，支持类型/分类筛选
- **每日日报**：自动取 TOP 10 热点生成 Markdown 日报

> ✅ **当前实现状态（v0.5 起）**：**生产管道已打通** —— 聚簇为标题字 bigram TF-IDF 单链接凝聚（`services/hot_cluster.py`，Job type `hot_cluster`）；热度评分为 48h 独立来源加权 + 24h 半衰 + 状态机（`services/hot_scorer.py`）；Feed 三类生产者就位（文章入库落点 / 聚簇副作用 / 日报副作用，`(item_type, ref_id)` 唯一约束 upsert）；日报含 LLM 摘要且失败降级为正文首段截断（`services/llm_summary.py`，每日 06:30 自动生成前一日，业务日界 Asia/Shanghai）。详见 [待办清单](docs/04_engineering/backlog.md) HOT-001~004。

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
Frontend (Next.js 14 / Node 24)  →  port 3200
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

## 部署指南（Docker Compose）

**前置**：Docker Engine + Compose v2（`docker compose` 子命令，非旧版 `docker-compose`）。

```bash
# 1) 准备环境变量（.env 已被 gitignore，禁止入库）
cp docker/.env.example docker/.env
# 2) 按下方清单填写必填项（尤其两个主密钥）
# 3) 启动全栈（compose 项目名固定为 bothot，见 docker/compose.yml 顶层 name:）
docker compose -f docker/compose.yml up -d
# 4) 查看状态 / 日志
docker compose -f docker/compose.yml ps
docker compose -f docker/compose.yml logs -f backend
# 5) 冒烟：健康端点（信封 code==0）+ scheduler/worker 心跳新鲜度
bash scripts/smoke.sh
```

**服务与启动顺序**（定义见 `docker/compose.yml`）：

```
postgres / redis  →  migrate（一次性 alembic upgrade head，restart: "no"）
                  →  backend（3300，带 healthcheck）
                  →  scheduler / worker（常驻进程，不开端口；健康信号是 process_heartbeats 心跳）
                  →  langbot / langbot_plugin_runtime（知识引擎侧，5300）
                  →  frontend（3200，依赖 backend）
```

> `migrate` 失败时 `backend` / `scheduler` / `worker` 三者**都不会启动**
> （`depends_on: service_completed_successfully`）—— 这是刻意的失败可见性，不要绕过。

**环境变量清单**（模板 `docker/.env.example`；`*.env` 已 gitignore）：

| 变量 | 必填 | 说明 |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | 是 | 默认 `bothot`（仅开发可直接用默认值） |
| `APP_SECRET_KEY` | 是 | 应用密钥 |
| `PUSH_SECRET_MASTER_KEY` | **是** | **渠道密钥 AES-256-GCM 主密钥**。须为 **32 字节密钥的 base64**；缺失/畸形时渠道加解密 **fail-closed 全部拒绝**（`apps/api/app/core/secret_crypto.py`） |
| `ENGINE_KEY_MASTER_KEY` | **是** | **引擎 Key AES-256-GCM 主密钥**，同为 32 字节 base64 口径。与上者**分属不同泄露域、不同轮换周期，禁止复用同一值**（`apps/api/app/core/engine_keyring.py`） |
| `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` / `OIDC_REDIRECT_URI` | 是 | 主平台 SSO OIDC；`OIDC_REDIRECT_URI` 须命中主平台 `oidc_clients.redirect_uris` 白名单 |
| `AIDEAN_ISSUER` / `AIDEAN_PUBLIC_URL` | 是 | 前者容器侧可达基址、后者浏览器侧 authorize 基址 —— **语义不同，不可混填** |
| `OIDC_ISSUER_EXPECTED` / `OIDC_AUDIENCE_EXPECTED` | 生产必填 | userinfo 的 iss/aud 期望值（`APP_ENV=production` 时为空则拒启） |
| `REDFOX_API_KEY` | 是 | RedFox 公众号发现 Provider |
| `DAJIALA_API_KEY` / `JUSTONEAPI_API_KEY` / `TIKHUB_API_KEY` / `WELLBYTE_API_KEY` | 否 | 4 平台文章来源 Provider，缺省则该平台不可用 |
| `EMBEDDING_API_BASE` / `EMBEDDING_API_KEY` / `EMBEDDING_MODEL` | 是 | 嵌入服务（默认硅基流动 `BAAI/bge-m3`） |
| `LLM_API_BASE` / `LLM_API_KEY` / `LLM_MODEL` | 是 | 生成 LLM（日报摘要与问答） |
| `LANGBOT_BASE_URL` / `LANGBOT_API_KEY` | 是 | LangBot 知识引擎；`LANGBOT_ADMIN_USERNAME` / `LANGBOT_ADMIN_PASSWORD` 用于防腐层登录 |
| `SESSION_STORE_BACKEND` | 否 | `redis`（容器部署默认）/ `memory`（宿主裸跑） |
| `SESSION_COOKIE_SECURE` | 生产必填 | HTTPS 环境须置 `true` |
| `BASE_IMAGE` | 否 | 基础镜像源开关（docker.io 不可达时改镜像源） |
| `PIP_MIRROR` / `PROXY_HTTP` | 否 | 依赖安装镜像与出站代理（分层网络规范见 compose 注释） |

> **安全铁律**：真实密钥禁止入库、入文档、入前端。生成 32 字节主密钥：
> `python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"`

**端口纪律**（强制，见 `AGENTS.md`）：

| 端口 | 用途 | 约束 |
|---|---|---|
| 3000 | 主平台专用 | ❌ BotHot 任何服务禁止占用 |
| 3200 | BotHot 前端宿主端口 | 容器内部 3000，宿主映射 3200 |
| 3300 | BotHot 后端端口 | 容器内部 3300 |
| 5300 | LangBot | — |
| 5433 | PostgreSQL | 容器 5432 → 宿主 5433 |
| 6380 | Redis | 容器 6379 → 宿主 6380 |

> 旧端口 `3333` 已废弃：`make guard-ports` 会 fail-closed 拦截（任一命中所属检查即退出码非 0）。

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
- `PUT    /api/v1/bots/tasks/{id}`       — 编辑 / 暂停恢复（含 cron_expr 重算 next_run_at）
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
├── apps/api/
│   │   ├── app/                    # API 路由（9 个业务域）
│   │   ├── models/                    # 数据模型
│   │   ├── services/                  # 业务服务
│   │   ├── providers/                 # 外部服务适配器
│   │   └── core/                      # 横切关注点
│   └── alembic/                       # 数据库迁移
├── apps/web/
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
- **新增**：多渠道推送（6 种渠道，含事件触发 outbox）、定时推送调度、热点聚簇/评分/Feed/日报（生产管道已打通）
- **改名**：AideanBot → BotHot（session cookie、项目名、容器名全部更新）
- **端口**：前端 3200、后端 3300

## License

MIT
