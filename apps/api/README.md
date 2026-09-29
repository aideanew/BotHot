# apps/api — BotHot 后端 API 服务

> **状态**：目录骨架已建，代码尚未迁入。当前后端代码仍在 `backend/` 目录运行。
>
> 迁移计划详见 [docs/03_solution/project-structure-design.md](../../docs/03_solution/project-structure-design.md)

## 目录结构

```
apps/api/
├── src/
│   ├── bootstrap/          # 启动层（main.py, app.py, lifespan.py）
│   ├── modules/            # 按业务域组织（9 个域）
│   │   ├── identity/       # 身份认证
│   │   ├── knowledge/      # 知识库管理
│   │   ├── subscription/   # 订阅同步
│   │   ├── ingest/         # 文章入库
│   │   ├── chat/           # RAG 问答
│   │   ├── engine/         # 引擎管理
│   │   ├── bot/            # 多渠道推送
│   │   ├── hot/            # 热点聚簇
│   │   └── system/         # 系统管理
│   ├── shared/             # 内部共享层
│   └── core/               # 横切关注点（config, errors, middleware）
├── tests/
├── scripts/
├── requirements/
├── pyproject.toml
├── alembic.ini
└── Dockerfile
```

## 分层架构

每个业务域模块内部遵循四层架构：

```
interfaces/    → 外部世界入口（HTTP routers + schemas）
application/   → 用例编排（commands + queries + services）
domain/        → 业务核心（entities + ports + services，零外部依赖）
infrastructure/→ 技术实现（persistence + cache + external + push_providers）
```

## 依赖方向

```
✅ interfaces → application → domain ← infrastructure
❌ domain → database / HTTP framework / Redis / 第三方 SDK
❌ 跨模块直接访问另一个模块的 internal 文件
```
