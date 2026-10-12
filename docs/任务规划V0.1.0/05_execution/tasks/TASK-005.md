---
id: TASK-005
type: task
title: .project/ 排除出前端镜像构建上下文
status: ready
slice: S0
owner: Agent-Guard
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-005：.project/ 排除出前端镜像构建上下文

**归属**
- 所属切片：S0（WP-0 安全止血）
- 执行 Agent：Agent-Guard
- 来源需求：REQ-C-001（Docker Compose 部署）
- 来源方案：—（卫生项，无需 ADR）

**目标**
根 .dockerignore 排除 .project/（125M 第三方源码），frontend 镜像构建上下文不再携带它。

**输入**
- .dockerignore（当前无 .project 条目）
- du -sh .project = 125M

**输出**（新增/修改的文件）
- `.dockerignore`

**Execution Steps**
1. [ ] 在 .dockerignore『其余目录一律不入上下文』段加 .project/ 一行（附注释）
2. [ ] 本地 docker build 前端镜像，对比构建上下文体积

**验收标准**
- [ ] grep -n '^.project/' .dockerignore 命中
- [ ] frontend 镜像 build 成功，上下文体积下降（记录前后数值）

**验证命令**
```bash
grep -n '^\.project/' .dockerignore
docker compose -f docker/compose.yml build frontend 2>&1 | grep -i 'transferring context'
```

**证据路径**
`docs/06_validation/evidence/EVD-005/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `.dockerignore`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- .project/**（不删除，删除属 D-07）

**依赖与阻塞**
- Depends on：无
- Blocks：无
- 阻塞条件：build 失败且与本改动相关 → 回退并回报

**建议执行档位**
haiku　理由：一行配置

**升级条件**
build 失败 → sonnect；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小（并入 S0 演示）
