---
id: PROJECT-STRUCTURE-DESIGN
type: architecture
title: BotHot 项目目录架构设计
status: active
owner: architecture
created: 2026-09-29
updated: 2026-09-29
version: 1.0
---

# BotHot 项目目录架构设计

> 本文档基于 PROJECT-STRUCTURE-SPEC 规范，将 BotHot 从当前 `backend/ + frontend/` 扁平结构重新设计为 `apps/ + packages/ + database/ + infra/` 规范化结构。

---

## 1. 目标根目录结构

```text
BotHot/
│
├── apps/                               # 第一层：可运行应用边界
│   ├── api/                            # 后端 API 服务（Python/FastAPI）
│   └── web/                            # 前端 Web 应用（Next.js）
│
├── packages/                           # 跨应用共享包
│   └── contracts/                      # 前后端共享契约（Request/Response/DTO 类型）
│
├── database/                           # 数据库生命周期资产
│   └── migrations/                     # Alembic 迁移脚本（按版本有序）
│
├── infra/                              # 基础设施即代码
│   └── docker/                         # Docker Compose 配置
│
├── scripts/                            # 长期有效的自动化脚本
│   ├── setup.sh                        # 环境初始化
│   └── preflight.sh                    # 预检脚本
│
├── docs/                               # 项目文档（见 PROJECT-DOCUMENTATION-SPEC）
│
├── .local/                             # 本地临时状态（完整 gitignore）
│   ├── ai/                             # AI Agent 工作产物
│   ├── logs/                           # 本地运行日志
│   └── screenshots/                    # 临时截图
│
├── README.md                           # 项目入口（面向人类）
├── AGENTS.md                           # AI 规范入口（面向 Agent）
├── CHANGELOG.md                        # 版本变更记录
├── Makefile                            # 统一命令入口
├── docker-compose.yml                  # 快捷启动（指向 infra/docker/）
├── .gitignore
├── .editorconfig
└── .env.example
```

---

## 2. 后端（apps/api/）完整目录设计

### 2.1 分层模型

```text
┌─────────────────────────────────────────────────────────┐
│                   interfaces/                            │  外部世界入口
│         http/ (FastAPI routers + schemas)               │
├─────────────────────────────────────────────────────────┤
│                  application/                            │  用例编排
│       commands/ │ queries/ │ services/                   │
├─────────────────────────────────────────────────────────┤
│                    domain/                               │  业务核心（最纯净）
│   entities/ │ value_objects/ │ ports/ │ events/          │
├─────────────────────────────────────────────────────────┤
│                infrastructure/                           │  技术实现（可替换）
│  persistence/ │ cache/ │ external/ │ push_providers/     │
├─────────────────────────────────────────────────────────┤
│              shared/ │ core/ │ bootstrap/                │  横切层
└─────────────────────────────────────────────────────────┘
```

### 2.2 完整目录结构

```text
apps/api/
│
├── src/
│   │
│   ├── bootstrap/                      # 启动层
│   │   ├── main.py                     # 唯一启动入口（FastAPI app）
│   │   ├── app.py                      # 应用工厂（create_app）
│   │   └── lifespan.py                 # 生命周期（启动/停止 scheduler）
│   │
│   ├── modules/                        # ★★ 核心：按业务域组织
│   │   │
│   │   ├── identity/                   # 身份认证域
│   │   │   ├── domain/
│   │   │   │   ├── entities/
│   │   │   │   │   └── user.py         # User 实体（sub, email, role）
│   │   │   │   ├── value_objects/
│   │   │   │   │   └── session.py      # 会话值对象
│   │   │   │   ├── ports/
│   │   │   │   │   ├── oidc_provider.py    # OIDC 接口（主平台认证）
│   │   │   │   │   ├── session_store.py    # 会话存储接口
│   │   │   │   │   └── user_repo.py        # 用户仓储接口
│   │   │   │   └── exceptions.py       # 认证异常
│   │   │   ├── application/
│   │   │   │   ├── commands/
│   │   │   │   │   ├── login/
│   │   │   │   │   │   ├── command.py  # SSO 登录命令
│   │   │   │   │   │   └── handler.py  # OIDC 交换 + User 快照
│   │   │   │   │   └── logout/
│   │   │   │   │       └── handler.py  # 会话销毁 + logout token
│   │   │   │   ├── queries/
│   │   │   │   │   └── get_current_user/
│   │   │   │   │       └── handler.py  # GET /auth/me
│   │   │   │   └── dtos/
│   │   │   │       └── auth_dto.py
│   │   │   ├── interfaces/
│   │   │   │   └── http/
│   │   │   │       ├── router.py       # /api/v1/auth/*
│   │   │   │       ├── controller.py   # 登录/回调/登出/me
│   │   │   │       └── schemas.py      # 请求/响应 Schema
│   │   │   └── infrastructure/
│   │   │       ├── oidc/
│   │   │       │   └── aidean_client.py    # 主平台 OIDC 实现
│   │   │       ├── persistence/
│   │   │       │   ├── user_model.py       # SQLAlchemy User Model
│   │   │       │   └── user_repo_impl.py   # UserRepo 实现
│   │   │       └── cache/
│   │   │           ├── session_store_redis.py  # Redis 会话存储
│   │   │           └── session_store_memory.py # 内存会话存储（开发）
│   │   │
│   │   ├── knowledge/                  # 知识库管理域
│   │   │   ├── domain/
│   │   │   │   ├── entities/
│   │   │   │   │   ├── knowledge_space.py  # 知识空间
│   │   │   │   │   ├── content_asset.py    # 内容资产
│   │   │   │   │   └── short_link.py       # 短链映射
│   │   │   │   ├── ports/
│   │   │   │   │   ├── space_repo.py
│   │   │   │   │   ├── asset_repo.py
│   │   │   │   │   └── public_library.py   # 公共库接口
│   │   │   │   └── events/
│   │   │   │       └── article_ingested.py # 文章入库事件
│   │   │   ├── application/
│   │   │   │   ├── commands/
│   │   │   │   │   ├── create_space/
│   │   │   │   │   ├── publish_to_public/  # 发布到公共库
│   │   │   │   │   └── update_space/
│   │   │   │   ├── queries/
│   │   │   │   │   ├── get_space/
│   │   │   │   │   ├── list_spaces/
│   │   │   │   │   └── list_public_library/
│   │   │   │   └── dtos/
│   │   │   │       └── space_dto.py
│   │   │   ├── interfaces/
│   │   │   │   └── http/
│   │   │   │       ├── router.py       # /api/v1/spaces/*
│   │   │   │       ├── controller.py
│   │   │   │       └── schemas.py
│   │   │   └── infrastructure/
│   │   │       ├── persistence/
│   │   │       │   ├── models/         # KnowledgeSpace, ContentAsset, ShortLinkMap
│   │   │       │   ├── repositories/   # SpaceRepoImpl, AssetRepoImpl
│   │   │       │   └── mappers/        # ORM ↔ Domain Entity
│   │   │       └── external/
│   │   │           └── langbot_kb.py   # LangBot KB 同步
│   │   │
│   │   ├── subscription/               # 订阅同步域
│   │   │   ├── domain/
│   │   │   │   ├── entities/
│   │   │   │   │   ├── source.py            # 信息源
│   │   │   │   │   ├── subscription.py      # 订阅
│   │   │   │   │   └── article_manifest.py  # 文章清单
│   │   │   │   ├── ports/
│   │   │   │   │   ├── source_repo.py
│   │   │   │   │   ├── subscription_repo.py
│   │   │   │   │   └── manifest_repo.py
│   │   │   │   └── services/
│   │   │   │       └── sync_policy.py       # 同步策略（固定时点/滑动窗口）
│   │   │   ├── application/
│   │   │   │   ├── commands/
│   │   │   │   │   ├── create_subscription/
│   │   │   │   │   └── sync_subscription/   # 触发同步
│   │   │   │   └── queries/
│   │   │   │       └── list_subscriptions/
│   │   │   ├── interfaces/
│   │   │   │   └── http/
│   │   │   │       ├── router.py       # /api/v1/subscriptions/*
│   │   │   │       └── schemas.py
│   │   │   └── infrastructure/
│   │   │       ├── persistence/
│   │   │       │   └── repositories/
│   │   │       └── external/
│   │   │           └── manifest_fetcher.py  # 拉取文章清单
│   │   │
│   │   ├── ingest/                     # 文章入库域
│   │   │   ├── domain/
│   │   │   │   ├── entities/
│   │   │   │   │   ├── job.py               # 入库任务
│   │   │   │   │   └── job_item.py          # 任务条目
│   │   │   │   ├── ports/
│   │   │   │   │   ├── job_repo.py
│   │   │   │   │   └── content_fetcher.py  # 内容采集接口
│   │   │   │   └── services/
│   │   │   │       ├── normalizer.py        # 内容标准化
│   │   │   │       ├── quality_scorer.py    # 质量评分
│   │   │   │       ├── categorizer.py       # 分类标签
│   │   │   │       └── state_machine.py     # 入库状态机
│   │   │   ├── application/
│   │   │   │   ├── commands/
│   │   │   │   │   ├── ingest_url/          # URL → 入库
│   │   │   │   │   └── batch_ingest/        # 批量入库
│   │   │   │   └── queries/
│   │   │   │       └── list_jobs/
│   │   │   ├── interfaces/
│   │   │   │   └── http/
│   │   │   │       ├── router.py       # /api/v1/extract/*
│   │   │   │       └── schemas.py
│   │   │   └── infrastructure/
│   │   │       ├── persistence/
│   │   │       │   └── job_repo_impl.py
│   │   │       └── external/
│   │   │           ├── redfox_client.py     # RedFox 采集
│   │   │           └── wandao_client.py     # Wandao 采集
│   │   │
│   │   ├── chat/                       # RAG 问答域
│   │   │   ├── domain/
│   │   │   │   ├── entities/
│   │   │   │   │   └── conversation.py      # 会话
│   │   │   │   ├── ports/
│   │   │   │   │   ├── rag_engine.py        # RAG 引擎接口
│   │   │   │   │   └── llm_provider.py      # LLM 接口
│   │   │   │   └── services/
│   │   │   │       ├── intent_detector.py   # 意图检测
│   │   │   │       └── space_resolver.py    # 空间解析
│   │   │   ├── application/
│   │   │   │   ├── commands/
│   │   │   │   │   └── ask/                 # 提问 → SSE 流式
│   │   │   │   └── queries/
│   │   │   │       └── resolve_target/      # 解析目标空间
│   │   │   ├── interfaces/
│   │   │   │   └── http/
│   │   │   │       ├── router.py       # /api/v1/chat/*, /api/v1/resolve/*
│   │   │   │       └── schemas.py
│   │   │   └── infrastructure/
│   │   │       └── external/
│   │   │           ├── llm_streaming.py     # LLM 流式直连（SiliconFlow）
│   │   │           └── reranker.py          # 检索重排
│   │   │
│   │   ├── engine/                     # 引擎管理域
│   │   │   ├── domain/
│   │   │   │   ├── entities/
│   │   │   │   │   └── engine_config.py     # 引擎配置
│   │   │   │   ├── ports/
│   │   │   │   │   └── engine_port.py       # EnginePort 抽象
│   │   │   │   └── services/
│   │   │   │       └── engine_registry.py   # 引擎注册表
│   │   │   ├── application/
│   │   │   │   ├── commands/
│   │   │   │   │   ├── register_engine_key/ # 注册引擎密钥
│   │   │   │   │   └── switch_engine/       # 切换空间引擎
│   │   │   │   └── queries/
│   │   │   │       └── list_engines/
│   │   │   ├── interfaces/
│   │   │   │   └── http/
│   │   │   │       ├── router.py       # /api/v1/engines/*
│   │   │   │       └── schemas.py
│   │   │   └── infrastructure/
│   │   │       └── external/
│   │   │           ├── langbot_engine.py    # LangBot 引擎实现
│   │   │           ├── aidean_engine.py     # Aidean 引擎实现
│   │   │           ├── redfox_engine.py     # RedFox 引擎实现
│   │   │           ├── embedding.py         # 嵌入服务
│   │   │           └── reranker_impl.py     # 重排服务
│   │   │
│   │   ├── bot/                        # 多渠道推送域
│   │   │   ├── domain/
│   │   │   │   ├── entities/
│   │   │   │   │   ├── bot_channel.py       # 渠道配置
│   │   │   │   │   ├── push_task.py         # 推送任务
│   │   │   │   │   └── push_log.py          # 推送日志
│   │   │   │   ├── ports/
│   │   │   │   │   ├── channel_repo.py
│   │   │   │   │   ├── task_repo.py
│   │   │   │   │   ├── log_repo.py
│   │   │   │   │   └── push_provider.py     # PushProvider 接口
│   │   │   │   └── services/
│   │   │   │       ├── push_dispatcher.py   # 推送调度逻辑
│   │   │   │       └── content_renderer.py  # 模板渲染
│   │   │   ├── application/
│   │   │   │   ├── commands/
│   │   │   │   │   ├── create_channel/
│   │   │   │   │   ├── create_push_task/
│   │   │   │   │   ├── test_push/           # 测试推送
│   │   │   │   │   └── trigger_push/        # 手动触发
│   │   │   │   └── queries/
│   │   │   │       ├── list_channels/
│   │   │   │       └── list_push_logs/
│   │   │   ├── interfaces/
│   │   │   │   └── http/
│   │   │   │       ├── router.py       # /api/v1/bots/*
│   │   │   │       └── schemas.py
│   │   │   └── infrastructure/
│   │   │       ├── persistence/
│   │   │       │   └── models/         # BotChannel, PushTask, PushLog
│   │   │       └── push_providers/     # ★ 六种渠道 Provider 实现
│   │   │           ├── feishu.py
│   │   │           ├── dingtalk.py
│   │   │           ├── wechat_work.py
│   │   │           ├── wechat_clawbot.py
│   │   │           ├── webhook.py
│   │   │           └── web.py
│   │   │
│   │   ├── hot/                        # 热点聚簇域
│   │   │   ├── domain/
│   │   │   │   ├── entities/
│   │   │   │   │   ├── hot_topic.py         # 热点事件
│   │   │   │   │   ├── hot_topic_article.py # 热点↔文章关联
│   │   │   │   │   ├── daily_report.py      # 每日日报
│   │   │   │   │   └── feed_item.py         # Feed 条目
│   │   │   │   ├── ports/
│   │   │   │   │   ├── topic_repo.py
│   │   │   │   │   ├── report_repo.py
│   │   │   │   │   └── feed_repo.py
│   │   │   │   └── services/
│   │   │   │       ├── clustering.py        # 聚簇算法
│   │   │   │       ├── hot_scorer.py        # 热度评分
│   │   │   │       └── report_generator.py  # 日报生成
│   │   │   ├── application/
│   │   │   │   ├── commands/
│   │   │   │   │   ├── cluster_topics/      # 触发聚簇
│   │   │   │   │   └── generate_daily_report/
│   │   │   │   └── queries/
│   │   │   │       ├── list_topics/
│   │   │   │       ├── list_reports/
│   │   │   │       └── get_feed/
│   │   │   ├── interfaces/
│   │   │   │   └── http/
│   │   │   │       ├── router.py       # /api/v1/hot/*
│   │   │   │       └── schemas.py
│   │   │   └── infrastructure/
│   │   │       ├── persistence/
│   │   │       │   └── models/         # HotTopic, DailyReport, FeedItem
│   │   │       └── external/
│   │   │           └── llm_summarizer.py    # LLM 生成摘要
│   │   │
│   │   └── system/                     # 系统管理域
│   │       ├── domain/
│   │       │   ├── entities/
│   │       │   │   └── process_heartbeat.py # 进程心跳
│   │       │   └── ports/
│   │       │       └── heartbeat_repo.py
│   │       ├── application/
│   │       │   ├── commands/
│   │       │   │   └── complete_onboarding/
│   │       │   └── queries/
│   │       │       ├── health_check/
│   │       │       └── admin_dashboard/
│   │       ├── interfaces/
│   │       │   └── http/
│   │       │       ├── router.py       # /api/v1/system/*, /admin/*, /onboarding/*
│   │       │       └── schemas.py
│   │       └── infrastructure/
│   │           └── persistence/
│   │               └── heartbeat_repo_impl.py
│   │
│   ├── shared/                         # 内部共享层
│   │   ├── domain/
│   │   │   ├── base_entity.py          # 实体基类
│   │   │   └── timestamp_mixin.py      # 时间戳混入
│   │   └── utils/
│   │       ├── pagination.py
│   │       └── crypto.py               # AES-256-GCM 加密工具
│   │
│   └── core/                           # 横切关注点
│       ├── config.py                   # 配置管理（Settings）
│       ├── errors.py                   # 全局异常基类与处理器
│       ├── response.py                 # 统一响应格式
│       ├── middleware/
│       │   ├── auth_middleware.py      # require_roles
│       │   ├── request_context.py     # RequestId 中间件
│       │   └── error_envelope.py      # 异常信封中间件
│       └── security.py                 # OpenAPI 安全方案标注
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   └── modules/
│   │       ├── identity/
│   │       ├── knowledge/
│   │       ├── bot/
│   │       └── hot/
│   ├── integration/
│   │   └── modules/
│   └── e2e/
│
├── scripts/
│   ├── seed.py
│   └── cleanup.sh
│
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── test.txt
│
├── .env.example
├── .project/                        # 第三方参考项目集合（133MB，gitignore，非 BotHot 代码）
│   ├── LangBot/                    # LangBot 框架源码（参考）
│   ├── MediaCrawler/               # 媒体爬虫参考
│   ├── wechat-clawbot/             # 微信 ClawBot 参考
│   └── ...                          # firecrawl, lux, wandao, reclip, SHY-downloader
├── pyproject.toml
├── alembic.ini
├── Dockerfile
└── Makefile
```

### 2.3 当前文件 → 目标位置映射

| 当前文件 | 目标位置 | 说明 |
|---|---|---|
| `backend/app/main.py` | `apps/api/src/bootstrap/main.py` | 启动入口 |
| `backend/app/core/config.py` | `apps/api/src/core/config.py` | 配置 |
| `backend/app/core/errors.py` | `apps/api/src/core/errors.py` | 异常 |
| `backend/app/core/response.py` | `apps/api/src/core/response.py` | 响应格式 |
| `backend/app/core/middleware.py` | `apps/api/src/core/middleware/` | 中间件拆分 |
| `backend/app/core/request_context.py` | `apps/api/src/core/middleware/request_context.py` | |
| `backend/app/core/engine_keyring.py` | `apps/api/src/modules/engine/infrastructure/keyring.py` | |
| `backend/app/api/deps.py` | `apps/api/src/core/middleware/auth_middleware.py` | 依赖注入 |
| `backend/app/api/v1/auth.py` | `apps/api/src/modules/identity/interfaces/http/` | |
| `backend/app/api/v1/spaces.py` | `apps/api/src/modules/knowledge/interfaces/http/` | |
| `backend/app/api/v1/subscriptions.py` | `apps/api/src/modules/subscription/interfaces/http/` | |
| `backend/app/api/v1/extract.py` | `apps/api/src/modules/ingest/interfaces/http/` | |
| `backend/app/api/v1/chat.py` | `apps/api/src/modules/chat/interfaces/http/` | |
| `backend/app/api/v1/resolve.py` | `apps/api/src/modules/chat/interfaces/http/` | |
| `backend/app/api/v1/engines.py` | `apps/api/src/modules/engine/interfaces/http/` | |
| `backend/app/api/v1/bots.py` | `apps/api/src/modules/bot/interfaces/http/` | |
| `backend/app/api/v1/hot.py` | `apps/api/src/modules/hot/interfaces/http/` | |
| `backend/app/api/v1/admin.py` | `apps/api/src/modules/system/interfaces/http/` | |
| `backend/app/api/v1/onboarding.py` | `apps/api/src/modules/system/interfaces/http/` | |
| `backend/app/api/v1/system.py` | `apps/api/src/modules/system/interfaces/http/` | |
| `backend/app/models/entities.py` | 拆分到各域 `infrastructure/persistence/models/` | User→identity, KnowledgeSpace→knowledge, etc. |
| `backend/app/models/bothot_entities.py` | 拆分到各域 `infrastructure/persistence/models/` | BotChannel→bot, HotTopic→hot, etc. |
| `backend/app/models/base.py` | `apps/api/src/shared/domain/base_entity.py` | |
| `backend/app/repositories/*.py` | 各域 `infrastructure/persistence/repositories/` | |
| `backend/app/services/auth/` | `apps/api/src/modules/identity/application/` | |
| `backend/app/services/spaces.py` | `apps/api/src/modules/knowledge/application/` | |
| `backend/app/services/subscription.py` | `apps/api/src/modules/subscription/application/` | |
| `backend/app/services/batch_ingest.py` | `apps/api/src/modules/ingest/application/commands/` | |
| `backend/app/services/job_worker.py` | `apps/api/src/modules/ingest/application/` | 独立进程入口 |
| `backend/app/services/scheduler.py` | `apps/api/src/modules/subscription/application/` | 独立进程入口 |
| `backend/app/services/push.py` | `apps/api/src/modules/bot/application/` | |
| `backend/app/services/push_scheduler.py` | `apps/api/src/modules/bot/application/` | 独立进程入口 |
| `backend/app/services/intent.py` | `apps/api/src/modules/chat/domain/services/` | |
| `backend/app/services/resolver.py` | `apps/api/src/modules/chat/domain/services/` | |
| `backend/app/services/normalizer.py` | `apps/api/src/modules/ingest/domain/services/` | |
| `backend/app/services/quality.py` | `apps/api/src/modules/ingest/domain/services/` | |
| `backend/app/services/categorizer.py` | `apps/api/src/modules/ingest/domain/services/` | |
| `backend/app/services/state_machine.py` | `apps/api/src/modules/ingest/domain/services/` | |
| `backend/app/services/jobs.py` | `apps/api/src/modules/ingest/application/` | |
| `backend/app/services/kb.py` | `apps/api/src/modules/knowledge/application/` | |
| `backend/app/services/public_library.py` | `apps/api/src/modules/knowledge/application/` | |
| `backend/app/services/roles.py` | `apps/api/src/modules/identity/application/` | |
| `backend/app/services/manifest.py` | `apps/api/src/modules/subscription/domain/services/` | |
| `backend/app/services/process_heartbeat.py` | `apps/api/src/modules/system/domain/services/` | |
| `backend/app/services/engine_keys.py` | `apps/api/src/modules/engine/application/` | |
| `backend/app/services/extractor.py` | `apps/api/src/modules/ingest/domain/services/` | |
| `backend/app/providers/push/*.py` | `apps/api/src/modules/bot/infrastructure/push_providers/` | |
| `backend/app/providers/push_port.py` | `apps/api/src/modules/bot/domain/ports/push_provider.py` | |
| `backend/app/providers/langbot/` | `apps/api/src/modules/engine/infrastructure/external/langbot_engine.py` | |
| `backend/app/providers/aidean/` | `apps/api/src/modules/engine/infrastructure/external/aidean_engine.py` | |
| `backend/app/providers/redfox/` | `apps/api/src/modules/ingest/infrastructure/external/redfox_client.py` | |
| `backend/app/providers/engine_port.py` | `apps/api/src/modules/engine/domain/ports/engine_port.py` | |
| `backend/app/providers/embedding.py` | `apps/api/src/modules/engine/infrastructure/external/embedding.py` | |
| `backend/app/providers/reranker.py` | `apps/api/src/modules/engine/infrastructure/external/reranker_impl.py` | |
| `backend/app/providers/discovery/` | `apps/api/src/modules/engine/domain/services/engine_registry.py` | |
| `backend/app/providers/source_resolver.py` | `apps/api/src/modules/ingest/domain/services/` | |
| `backend/app/providers/raw_store.py` | `apps/api/src/modules/ingest/infrastructure/` | |
| `backend/app/db.py` | `apps/api/src/core/database.py` | |
| `backend/alembic/` | `database/migrations/` | 迁移独立 |

---

## 3. 前端（apps/web/）完整目录设计

### 3.1 分层模型

```text
┌─────────────────────────────────────────────────────────┐
│                    app/ (Next.js App Router)             │  路由页面层
├─────────────────────────────────────────────────────────┤
│                   features/                              │  业务功能域
│  ┌──────────┬────────────┬──────────┬─────────────────┐ │
│  │components│   hooks/   │  store/  │    api/  types/  │ │
│  └──────────┴────────────┴──────────┴─────────────────┘ │
├─────────────────────────────────────────────────────────┤
│           components/ui/      data-access/               │  共享 UI 与数据访问
├─────────────────────────────────────────────────────────┤
│         lib/utils/   hooks/   constants/   types/        │  全局工具
└─────────────────────────────────────────────────────────┘
```

### 3.2 完整目录结构

```text
apps/web/
│
├── src/                                # （如使用 src/ 目录）
│   │
│   ├── app/                            # Next.js App Router（路由页面层）
│   │   ├── layout.tsx                  # 根布局
│   │   ├── page.tsx                    # 首页（Feed 流）
│   │   ├── globals.css                 # 全局样式
│   │   ├── error.tsx                   # 错误页
│   │   ├── not-found.tsx               # 404
│   │   ├── auth/
│   │   │   └── aidean/callback/        # SSO 回调
│   │   │       └── page.tsx
│   │   ├── spaces/
│   │   │   ├── page.tsx                # 空间列表
│   │   │   └── [id]/page.tsx           # 空间详情
│   │   ├── public/page.tsx             # 公共库
│   │   ├── subscriptions/page.tsx      # 订阅管理
│   │   ├── jobs/page.tsx               # 任务列表
│   │   ├── chat/page.tsx               # RAG 问答
│   │   ├── engines/page.tsx            # 引擎管理
│   │   ├── bots/page.tsx               # Bot 渠道管理
│   │   ├── hot/
│   │   │   ├── page.tsx                # 热点中心
│   │   │   └── daily/page.tsx          # 每日日报
│   │   ├── admin/page.tsx              # 管理后台
│   │   └── onboarding/page.tsx         # 引导
│   │
│   ├── features/                       # ★★ 业务功能域
│   │   ├── auth/
│   │   │   ├── components/
│   │   │   │   └── AuthContext.tsx     # 认证上下文
│   │   │   ├── hooks/
│   │   │   ├── api/
│   │   │   │   └── auth.api.ts
│   │   │   └── index.ts
│   │   ├── knowledge/
│   │   │   ├── components/
│   │   │   │   ├── SpaceHeaderPanel.tsx
│   │   │   │   ├── SpaceArticleSection.tsx
│   │   │   │   ├── DocList.tsx
│   │   │   │   ├── DocStatusBadge.tsx
│   │   │   │   ├── DocBatchActions.tsx
│   │   │   │   ├── DocLifecycleActions.tsx
│   │   │   │   ├── AddArticlePanel.tsx
│   │   │   │   ├── PublicLibraryPicker.tsx
│   │   │   │   └── add-article/        # 添加文章子组件
│   │   │   │       ├── BatchProgressList.tsx
│   │   │   │       ├── ParsePreviewCard.tsx
│   │   │   │       ├── QualityBadge.tsx
│   │   │   │       ├── SubmitSuccessCard.tsx
│   │   │   │       └── types.ts
│   │   │   ├── hooks/
│   │   │   │   ├── useSpaceDetail.ts
│   │   │   │   └── useBatchIngest.ts
│   │   │   ├── api/
│   │   │   │   ├── spaces.api.ts
│   │   │   │   ├── public-library.api.ts
│   │   │   │   └── ingest.api.ts
│   │   │   └── index.ts
│   │   ├── subscription/
│   │   │   ├── components/
│   │   │   │   ├── SubscriptionCard.tsx
│   │   │   │   ├── SubscriptionLifecycleActions.tsx
│   │   │   │   └── SubscribeShortcut.tsx
│   │   │   ├── hooks/
│   │   │   │   └── useSubscriptions.ts
│   │   │   ├── api/
│   │   │   │   └── subscriptions.api.ts
│   │   │   └── index.ts
│   │   ├── ingest/
│   │   │   ├── components/
│   │   │   │   ├── JobCard.tsx
│   │   │   │   └── JobFilterBar.tsx
│   │   │   ├── hooks/
│   │   │   │   └── useJobsList.ts
│   │   │   ├── api/
│   │   │   │   ├── jobs.api.ts
│   │   │   │   └── batch.api.ts
│   │   │   └── index.ts
│   │   ├── chat/
│   │   │   ├── components/
│   │   │   │   ├── AskInputBar.tsx
│   │   │   │   ├── ChatMessageList.tsx
│   │   │   │   └── types.ts
│   │   │   ├── hooks/
│   │   │   │   └── useSseAsk.ts
│   │   │   ├── api/
│   │   │   │   └── ask.api.ts
│   │   │   └── index.ts
│   │   ├── engine/
│   │   │   ├── components/
│   │   │   │   └── EngineSwitcher.tsx
│   │   │   ├── api/
│   │   │   │   └── engines.api.ts
│   │   │   └── index.ts
│   │   ├── bot/
│   │   │   ├── components/             # Bot 渠道管理组件
│   │   │   ├── api/
│   │   │   │   └── bots.api.ts
│   │   │   └── index.ts
│   │   ├── hot/
│   │   │   ├── components/             # 热点/日报组件
│   │   │   ├── api/
│   │   │   │   └── hot.api.ts
│   │   │   └── index.ts
│   │   ├── admin/
│   │   │   ├── components/
│   │   │   │   ├── AdminDocSection.tsx
│   │   │   │   ├── AdminOpsSection.tsx
│   │   │   │   └── AdminSpaceCard.tsx
│   │   │   ├── hooks/
│   │   │   │   └── useAdminData.ts
│   │   │   ├── api/
│   │   │   │   └── admin.api.ts
│   │   │   └── index.ts
│   │   └── onboarding/
│   │       ├── components/
│   │       │   ├── StepIndicator.tsx
│   │       │   └── StepPanels.tsx
│   │       └── types.ts
│   │
│   ├── components/                     # 纯 UI 组件层（零业务逻辑）
│   │   ├── ui/                         # 基础 UI 原子组件
│   │   │   ├── LoadingErrorShell.tsx
│   │   │   ├── Skeleton.tsx
│   │   │   └── ConfirmModal.tsx
│   │   └── layout/                     # 布局组件
│   │       ├── TopBar.tsx
│   │       └── index.ts
│   │
│   ├── data-access/                    # 数据访问层
│   │   ├── http.ts                     # HTTP 客户端实例
│   │   ├── types.ts                    # API 通用类型
│   │   └── mock-data.ts               # Mock 数据
│   │
│   ├── lib/                            # 全局通用能力
│   │   ├── hooks/
│   │   │   └── usePageTitle.ts
│   │   └── utils/
│   │       └── format.ts
│   │
│   └── constants/
│       └── routes.ts                   # 路由路径常量
│
├── public/                             # 静态文件
├── tests/
│   └── *.spec.tsx                      # 单元测试
├── e2e/
│   ├── real-backend.spec.ts
│   └── trunk.spec.ts
├── .env.example
├── .project/                        # 第三方参考项目集合（133MB，gitignore，非 BotHot 代码）
│   ├── LangBot/                    # LangBot 框架源码（参考）
│   ├── MediaCrawler/               # 媒体爬虫参考
│   ├── wechat-clawbot/             # 微信 ClawBot 参考
│   └── ...                          # firecrawl, lux, wandao, reclip, SHY-downloader
├── next.config.mjs
├── tailwind.config.ts
├── tsconfig.json
├── package.json
├── Dockerfile
└── Makefile
```

### 3.3 当前前端文件 → 目标位置映射

| 当前文件 | 目标位置 | 说明 |
|---|---|---|
| `frontend/app/layout.tsx` | `apps/web/src/app/layout.tsx` | |
| `frontend/app/page.tsx` | `apps/web/src/app/page.tsx` | |
| `frontend/app/bots/page.tsx` | `apps/web/src/app/bots/page.tsx` | |
| `frontend/app/hot/page.tsx` | `apps/web/src/app/hot/page.tsx` | |
| `frontend/app/hot/daily/page.tsx` | `apps/web/src/app/hot/daily/page.tsx` | |
| `frontend/components/AuthContext.tsx` | `apps/web/src/features/auth/components/` | |
| `frontend/components/TopBar.tsx` | `apps/web/src/components/layout/` | |
| `frontend/components/AddArticlePanel.tsx` | `apps/web/src/features/knowledge/components/` | |
| `frontend/components/DocList.tsx` | `apps/web/src/features/knowledge/components/` | |
| `frontend/components/Space*.tsx` | `apps/web/src/features/knowledge/components/` | |
| `frontend/components/PublicLibraryPicker.tsx` | `apps/web/src/features/knowledge/components/` | |
| `frontend/components/add-article/` | `apps/web/src/features/knowledge/components/add-article/` | |
| `frontend/components/Subscription*.tsx` | `apps/web/src/features/subscription/components/` | |
| `frontend/components/SubscribeShortcut.tsx` | `apps/web/src/features/subscription/components/` | |
| `frontend/components/Job*.tsx` | `apps/web/src/features/ingest/components/` | |
| `frontend/components/chat/` | `apps/web/src/features/chat/components/` | |
| `frontend/components/EngineSwitcher.tsx` | `apps/web/src/features/engine/components/` | |
| `frontend/components/Admin*.tsx` | `apps/web/src/features/admin/components/` | |
| `frontend/components/onboarding/` | `apps/web/src/features/onboarding/components/` | |
| `frontend/components/LoadingErrorShell.tsx` | `apps/web/src/components/ui/` | |
| `frontend/components/Skeleton.tsx` | `apps/web/src/components/ui/` | |
| `frontend/components/ConfirmModal.tsx` | `apps/web/src/components/ui/` | |
| `frontend/components/use*.ts` | 各 feature 的 `hooks/` 目录 | 按归属域拆分 |
| `frontend/lib/api/http.ts` | `apps/web/src/data-access/http.ts` | |
| `frontend/lib/api/types.ts` | `apps/web/src/data-access/types.ts` | |
| `frontend/lib/api/auth.ts` | `apps/web/src/features/auth/api/` | |
| `frontend/lib/api/spaces.ts` | `apps/web/src/features/knowledge/api/` | |
| `frontend/lib/api/bots.ts` | `apps/web/src/features/bot/api/` | |
| `frontend/lib/api/hot.ts` | `apps/web/src/features/hot/api/` | |
| `frontend/lib/api/admin.ts` | `apps/web/src/features/admin/api/` | |
| `frontend/lib/api/engines.ts` | `apps/web/src/features/engine/api/` | |
| `frontend/lib/api/jobs.ts` | `apps/web/src/features/ingest/api/` | |
| `frontend/lib/api/ask.ts` | `apps/web/src/features/chat/api/` | |
| `frontend/lib/api/subscriptions.ts` | `apps/web/src/features/subscription/api/` | |
| `frontend/lib/api/batch.ts` | `apps/web/src/features/knowledge/api/` | |
| `frontend/lib/api/ingest.ts` | `apps/web/src/features/knowledge/api/` | |
| `frontend/lib/api/public-library.ts` | `apps/web/src/features/knowledge/api/` | |
| `frontend/lib/api/mock-data.ts` | `apps/web/src/data-access/mock-data.ts` | |

---

## 4. packages/contracts/ 设计

```text
packages/contracts/
├── src/
│   ├── identity/
│   │   ├── auth.contract.ts        # 登录/回调/登出 契约
│   │   └── index.ts
│   ├── knowledge/
│   │   ├── space.contract.ts       # 空间 CRUD 契约
│   │   ├── asset.contract.ts       # 内容资产契约
│   │   └── index.ts
│   ├── subscription/
│   │   ├── subscription.contract.ts
│   │   └── index.ts
│   ├── ingest/
│   │   ├── job.contract.ts
│   │   └── index.ts
│   ├── chat/
│   │   ├── ask.contract.ts         # SSE 问答契约
│   │   └── index.ts
│   ├── engine/
│   │   ├── engine.contract.ts
│   │   └── index.ts
│   ├── bot/
│   │   ├── channel.contract.ts     # 渠道管理契约
│   │   ├── push-task.contract.ts   # 推送任务契约
│   │   └── index.ts
│   ├── hot/
│   │   ├── topic.contract.ts       # 热点契约
│   │   ├── daily-report.contract.ts
│   │   ├── feed.contract.ts
│   │   └── index.ts
│   ├── common/
│   │   ├── pagination.types.ts     # 通用分页
│   │   ├── response.types.ts       # 通用响应格式
│   │   └── error.types.ts          # 错误契约
│   └── index.ts
└── package.json
```

---

## 5. database/ 设计

```text
database/
├── migrations/                         # Alembic 迁移（从 backend/alembic/ 迁入）
│   ├── env.py
│   └── versions/
│       ├── 05a5a856c37b_v1_initial_schema.py
│       ├── ab1004bh01_bothot_extensions.py
│       └── ... (全部迁移脚本)
├── seeds/                              # 种子数据
└── alembic.ini                         # Alembic 配置
```

---

## 6. infra/ 设计

```text
infra/
└── docker/
    ├── compose.yml                     # Docker Compose（从 docker/compose.yml 迁入）
    ├── compose.prod.yml                # 生产配置（未来）
    └── .env.example                    # 环境变量模板
```

---

## 7. 迁移策略

### 7.1 阶段化迁移（不一次性重构）

```text
阶段 1（当前）：创建目录骨架 + 设计文档
    ├── 创建 apps/api/src/modules/ 目录结构（.gitkeep）
    ├── 创建 apps/web/src/features/ 目录结构（.gitkeep）
    ├── 创建 packages/contracts/ 骨架
    ├── 创建 database/ 和 infra/ 目录
    └── 更新 AGENTS.md 指向新结构

阶段 2（后续）：逐域迁移后端
    ├── 先迁移独立域（hot, bot）—— 与现有代码耦合最低
    ├── 再迁移核心域（identity, knowledge）
    ├── 最后迁移复杂域（ingest, chat, engine）
    └── 每域迁移后跑测试验证

阶段 3（后续）：前端 features 拆分
    ├── 按功能域拆分 components/ → features/
    └── 每域迁移后跑构建验证

阶段 4（后续）：共享契约
    ├── 提取前后端共享类型到 packages/contracts/
    └── 前后端共同引用
```

### 7.2 迁移期间的双轨策略

```text
迁移期间，旧结构（backend/ + frontend/）和新结构（apps/）可以并存：
- 旧代码继续在 backend/ 和 frontend/ 运行
- 新代码逐步在 apps/ 中创建
- 通过 Makefile 的不同 target 管理两套路径
- 完全迁移后删除旧目录
```

---

## 8. 依赖方向约束（强制）

### 后端

```text
✅ 允许：interfaces → application → domain ← infrastructure
❌ 禁止：domain → database / HTTP framework / Redis / 第三方 SDK
❌ 禁止：interfaces → repository（跳过 application 层）
❌ 禁止：跨业务模块直接访问另一个模块的 internal 文件
```

### 前端

```text
✅ 允许：pages → features → components/ui → lib/utils（单向）
❌ 禁止：features/order → features/payment/internal/
❌ 禁止：components/ui → features/（UI 组件依赖业务逻辑）
❌ 禁止：utils/ → features/（工具函数依赖业务域）
```

### 模块间通信

```text
✅ 允许：模块 A → 模块 B 的公开 API（index.ts）
✅ 允许：模块 A → Domain Event → 模块 B
❌ 禁止：任何模块 → 另一个模块的 internal 路径
```
