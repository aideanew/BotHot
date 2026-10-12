---
id: TASK-025
type: task
title: real-backend e2e 解阻并转为阻塞门禁（外部依赖）
status: blocked
slice: S8
owner: Agent-App
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-025：real-backend e2e 解阻并转为阻塞门禁（外部依赖）

**归属**
- 所属切片：S8（WP-8 真实链路验收）
- 执行 Agent：Agent-App
- 来源需求：backlog TEST-002；roadmap v1.0『全量测试通过』
- 来源方案：—

**目标**
e2e/real-backend.spec.ts 在 compose 栈上以真实 OIDC 登录跑通 4 条用例，CI 中去掉 continue-on-error。

**输入**
- apps/web/e2e/real-backend.spec.ts
- .github/workflows/ci.yml:302-305（non-blocking）
- 外部：主平台 oidc_clients.redirect_uris 白名单、测试账号、真实文章 URL

**输出**（新增/修改的文件）
- `apps/web/e2e/real-backend.spec.ts`
- `.github/workflows/ci.yml`

**Execution Steps**
1. [ ] 确认三项外部前置（D-08）
2. [ ] 本地栈跑通 4 用例
3. [ ] CI 侧提供测试凭据（仓库 secret，由人配置）后去掉 continue-on-error

**验收标准**
- [ ] 4 用例绿 3 次连续
- [ ] CI 中该 step 为阻塞

**验证命令**
```bash
cd apps/web && E2E_REAL_BACKEND=1 pnpm run test:e2e -- e2e/real-backend.spec.ts
```

**证据路径**
`docs/06_validation/evidence/EVD-025/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/web/e2e/real-backend.spec.ts`
- `.github/workflows/ci.yml`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- apps/api/**

**依赖与阻塞**
- Depends on：D-08
- Blocks：无
- 阻塞条件：外部前置缺任一 → blocked

**建议执行档位**
sonnect　理由：脚本修复

**升级条件**
链路问题跨前后端 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中
