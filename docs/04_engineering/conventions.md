---
id: ENGINEERING-CONVENTIONS
type: convention
title: BotHot 工程规范
status: active
owner: engineering
created: 2026-09-29
updated: 2026-09-29
version: 1.0
---

# BotHot 工程规范

## 1. 端口分配（强制）

| 端口 | 用途 | 禁止 |
|------|------|------|
| 3000 | 主平台专用 | ❌ BotHot 任何服务不得占用 |
| 3200 | BotHot 前端宿主端口 | — |
| 3300 | BotHot 后端端口 | — |
| 5300 | LangBot | — |
| 5433 | PostgreSQL | — |
| 6380 | Redis | — |

> 容器内部端口：前端 3000、后端 3300（已统一）。

## 2. 命名规范

### 2.1 项目命名
- 项目名：**BotHot**（PascalCase）
- Docker Compose 项目名：**bothot**（lowercase）
- Session Cookie 名：**bothot_session**

### 2.2 后端命名
- 文件：snake_case（`push_provider.py`）
- 类：PascalCase（`PushProvider`）
- 函数/变量：snake_case（`send_message`）
- 常量：UPPER_SNAKE_CASE（`MAX_RETRY_COUNT`）
- 数据库表：snake_case（`bot_channels`）
- 数据库列：snake_case（`channel_type`）

### 2.3 前端命名
- 文件：PascalCase（`SpaceHeaderPanel.tsx`）
- 组件：PascalCase（`SpaceHeaderPanel`）
- 函数/变量：camelCase（`fetchSpaces`）
- 常量：UPPER_SNAKE_CASE（`API_BASE_URL`）
- CSS 类：kebab-case（`space-header`）
- 路由路径：kebab-case（`/hot/daily`）

## 3. Git 规范

### 3.1 分支策略
```
main          ← 生产分支（受保护）
├── develop   ← 集成分支
├── feature/* ← 功能分支
├── fix/*     ← 修复分支
└── docs/*    ← 文档分支
```

### 3.2 提交信息格式
```
<type>(<scope>): <subject>

<body>

<footer>
```

**type**: feat | fix | docs | refactor | test | chore | ci
**scope**: identity | knowledge | subscription | ingest | chat | engine | bot | hot | system | web | infra | docs
**subject**: 简短描述（祈使句，中文或英文均可，同一 PR 内统一语言）

示例：
```
feat(bot): 实现飞书 Webhook Provider 真实推送
fix(hot): 修复聚簇算法时间衰减计算错误
docs(architecture): 更新系统架构设计文档
```

## 4. 测试规范

### 4.1 后端
- 单元测试：`tests/unit/modules/<domain>/`
- 集成测试：`tests/integration/modules/<domain>/`
- 测试文件命名：`test_<module>.py`
- 覆盖率目标：core/ 和 application/ 层 > 80%

### 4.2 前端
- 单元测试：与组件同目录 `*.spec.tsx`
- e2e 测试：`e2e/*.spec.ts`
- 框架：Vitest（单元） + Playwright（e2e）

## 5. 依赖管理

### 5.1 后端
- 包管理：uv（pyproject.toml + uv.lock）
- Python 版本：3.12
- 依赖锁定：uv.lock 必须提交

### 5.2 前端
- 包管理：pnpm
- Node 版本：22
- 锁文件：pnpm-lock.yaml 必须提交

## 6. 环境变量规范

### 6.1 敏感信息
- AK/SK：**不写入 .tf/.py 文件**，通过环境变量传入
- 渠道密钥：AES-256-GCM 加密后落库
- OIDC Client Secret：通过环境变量传入

### 6.2 环境变量命名
- 前缀：`BOTHOT_`
- 格式：`BOTHOT_<SECTION>_<KEY>`
- 示例：`BOTHOT_DB_URL`, `BOTHOT_REDIS_URL`, `BOTHOT_OIDC_CLIENT_ID`

## 7. 文档规范

详见 [PROJECT-DOCUMENTATION-SPEC](../00_governance/doc-spec.md)。

核心规则：
- 每个文档有 frontmatter（id/type/title/status/owner/created/updated）
- 文档放在 docs/ 对应分类目录
- 新需求先入 `02_requirements/inbox/`
- 架构决策记入 `03_solution/decisions/`

## 8. Docker 规范

- Dockerfile 用多阶段构建
- 后端镜像基于 `python:3.12-slim`
- 前端镜像基于 `node:22-alpine`
- Docker Compose 配置在 `infra/docker/compose.yml`
- `.env.example` 提供所有环境变量模板

## 9. 安全规范

- Cookie：HttpOnly + SameSite=Lax
- CORS：白名单制，不开放 0.0.0.0/0
- SQL 注入：ORM 参数化查询，禁用字符串拼接 SQL
- XSS：前端输出转义，禁用 dangerouslySetInnerHTML
- 权限：路由层 require_roles 门禁
- 密钥：不硬编码，环境变量传入
