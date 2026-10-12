---
id: TASK-010
type: task
title: middleware 白名单与 AuthGate 按 ADR-0009 对齐 + 真实态单测
status: ready
slice: S2
owner: Agent-App
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-010：middleware 白名单与 AuthGate 按 ADR-0009 对齐 + 真实态单测

**归属**
- 所属切片：S2（WP-2 访客访问策略）
- 执行 Agent：Agent-App
- 来源需求：REQ-F-007
- 来源方案：ADR-0009

**目标**
真实构建下 middleware 的放行集合 = ADR-0009 的游客可见路由；有不依赖 mock 的单测锁定该行为。

**输入**
- apps/web/middleware.ts
- apps/web/app/{hot,hot/daily,public}/page.tsx（AuthGate 包裹）
- apps/web/e2e/auth-gate.spec.ts
- ADR-0009 路由表

**输出**（新增/修改的文件）
- `apps/web/middleware.ts`
- `apps/web/app/hot/page.tsx`
- `apps/web/app/hot/daily/page.tsx`
- `apps/web/app/public/page.tsx`
- `apps/web/e2e/auth-gate.spec.ts`
- apps/web/tests/middleware.spec.ts（新增）

**Execution Steps**
1. [ ] PUBLIC_PATHS/PUBLIC_PREFIXES 按 ADR 表修改
2. [ ] 游客可见页移除 AuthGate 包裹或改为可选登录态（按 ADR）
3. [ ] 新增 vitest：以 NextRequest 构造无 cookie 请求，逐路由断言 next() 或 redirect
4. [ ] e2e 矩阵 PROTECTED_PAGES 与注释同步 ADR

**验收标准**
- [ ] middleware 单测覆盖 ADR 表中每条路由
- [ ] vitest 全绿零回归；mock e2e 绿
- [ ] e2e 注释与 PROTECTED_PAGES 不再矛盾

**验证命令**
```bash
cd apps/web && pnpm run test:unit -- --run tests/middleware.spec.ts && pnpm run test:unit -- --run && pnpm run test:e2e
```

**证据路径**
`docs/06_validation/evidence/EVD-010/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/web/middleware.ts`
- `apps/web/app/hot/**`
- `apps/web/app/public/**`
- `apps/web/e2e/auth-gate.spec.ts`
- `apps/web/tests/middleware.spec.ts`

**禁止修改**
- apps/api/**
- packages/**
- apps/web/components/AuthGate.tsx（行为契约不变）

**依赖与阻塞**
- Depends on：TASK-009
- Blocks：TASK-011
- 阻塞条件：需要后端放开匿名接口（如 /hot/feed 无登录） → 停，属 Identity 契约变更

**建议执行档位**
sonnect　理由：规则已由 ADR 写死

**升级条件**
连续 2 次 e2e 红 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中
