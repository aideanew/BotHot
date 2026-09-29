# BotHot

> 公众号链接 → 知识库 → 多渠道机器人推送 闭环

BotHot 是从 AideanBot 全面升级而来的多渠道机器人推送与知识管理平台。在原有"公众号链接入库 → LangBot 知识问答"闭环基础上，新增了多渠道主动推送能力（飞书/钉钉/企业微信/微信 ClawBot/通用 Webhook/站内通知），并融合 AIHOT 的热点聚簇与日报功能。

## 核心能力

### 1. 多渠道机器人推送（新增）
- **六种渠道**：飞书、钉钉、企业微信、微信 ClawBot、通用 Webhook、站内通知
- **定时推送**：Cron 表达式驱动，支持每天定时、周期推送
- **事件触发**：新文章入库、热点更新等事件自动触发推送
- **测试推送**：管理端一键测试渠道连通性
- **推送日志**：完整投递记录，成功/失败/响应摘要

### 2. 热点聚簇与日报（融合 AIHOT）
- **热点聚簇**：多篇文章按主题聚簇为事件，按热度排序
- **热度评分**：48h 内独立来源数加权，24h 减半
- **Feed 流**：信息流首页，支持类型/分类筛选
- **每日日报**：自动取 TOP 10 热点生成 Markdown 日报

### 3. 知识库管理（继承 AideanBot）
- 公众号链接解析入库（RedFox + Wandao）
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

## 渠道配置指南

### 飞书机器人
1. 在飞书群中添加自定义机器人
2. 复制 Webhook URL（`https://open.feishu.cn/open-apis/bot/v2/hook/xxx`）
3. （可选）启用加签模式，复制密钥
4. 在 BotHot 管理端创建渠道，填入 Webhook URL 和密钥

### 钉钉机器人
1. 在钉钉群中添加自定义机器人
2. 复制 Webhook URL（`https://oapi.dingtalk.com/robot/send?access_token=xxx`）
3. （可选）启用加签模式
4. 在 BotHot 管理端创建渠道

### 企业微信群机器人
1. 在企业微信群中添加群机器人
2. 复制 Webhook URL
3. 在 BotHot 管理端创建渠道

## 项目结构

```
BotHot/
├── backend/
│   ├── app/
│   │   ├── api/v1/
│   │   │   ├── bots.py          # 机器人渠道管理 API
│   │   │   ├── hot.py           # 热点聚簇与日报 API
│   │   │   └── ...
│   │   ├── models/
│   │   │   ├── bothot_entities.py  # BotHot 扩展模型
│   │   │   └── ...
│   │   ├── providers/push/
│   │   │   ├── feishu.py        # 飞书推送 Provider
│   │   │   ├── dingtalk.py      # 钉钉推送 Provider
│   │   │   ├── wechat_work.py   # 企业微信推送 Provider
│   │   │   ├── webhook.py       # 通用 Webhook Provider
│   │   │   ├── wechat_clawbot.py # 微信 ClawBot Provider
│   │   │   └── web.py           # 站内通知 Provider
│   │   ├── services/
│   │   │   ├── push_scheduler.py # 推送任务调度器
│   │   │   └── ...
│   │   └── ...
│   └── alembic/versions/
│       └── ab1004bh01_bothot_extensions.py  # BotHot 扩展表迁移
├── frontend/
│   ├── app/
│   │   ├── bots/                # 机器人渠道管理页
│   │   ├── hot/                 # 热点中心
│   │   ├── hot/daily/           # 每日日报
│   │   └── ...
│   └── lib/api/
│       ├── bots.ts              # 机器人 API 模块
│       └── hot.ts               # 热点 API 模块
└── docker/
    ├── compose.yml              # Docker Compose 编排
    └── .env.example             # 环境变量模板
```

## 与 AideanBot 的关系

BotHot 是 AideanBot 的全面升级版：
- **保留**：公众号链接入库、LangBot RAG、知识空间管理、SSO 认证、整号订阅
- **新增**：多渠道推送（6 种渠道）、定时推送调度、热点聚簇、每日日报、Feed 流
- **改名**：AideanBot → BotHot（session cookie、项目名、容器名全部更新）
- **端口**：前端 3200（原 3333）、后端 3300（原 8000 容器内同步改为 3300）

## License

MIT
