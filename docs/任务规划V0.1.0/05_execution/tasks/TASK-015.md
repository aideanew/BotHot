---
id: TASK-015
type: task
title: 前端 bots/hot API 层改用 *Out 契约类型
status: ready
slice: S3
owner: Agent-App
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-015：前端 bots/hot API 层改用 *Out 契约类型

**归属**
- 所属切片：S3（WP-3 响应形状契约）
- 执行 Agent：Agent-App
- 来源需求：REQ-F-001/002
- 来源方案：ADR-0008

**目标**
apps/web/lib/api/bots.ts 与 hot.ts 的返回类型来自 @bothot/contracts 的 *Out，删除本地重复定义。

**输入**
- apps/web/lib/api/{bots,hot,types}.ts
- packages/contracts/src/index.ts（TASK-014 后）

**输出**（新增/修改的文件）
- `apps/web/lib/api/bots.ts`
- `apps/web/lib/api/hot.ts`
- `apps/web/lib/api/types.ts`
- `apps/web/lib/api/mock-data.ts`

**Execution Steps**
1. [ ] import type 替换本地类型
2. [ ] mock-data 以 satisfies 对齐新类型
3. [ ] 删除本地重复 interface（grep 确认零消费）

**验收标准**
- [ ] tsc 零错；vitest 零回归；mock e2e 绿
- [ ] grep 本地重复类型名零命中

**验证命令**
```bash
cd apps/web && pnpm exec tsc --noEmit && pnpm run test:unit -- --run && pnpm run test:e2e
```

**证据路径**
`docs/06_validation/evidence/EVD-015/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/web/lib/api/**`

**禁止修改**
- packages/**
- apps/api/**
- apps/web/components/**（若组件需改，回报）

**依赖与阻塞**
- Depends on：TASK-014
- Blocks：无
- 阻塞条件：组件层类型报错 > 10 处 → 停，回报拆分

**建议执行档位**
sonnect　理由：类型替换

**升级条件**
2 次失败 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中
