---
id: TASK-017
type: task
title: NotificationBell 用帧 id 去重（前端）
status: ready
slice: S4
owner: Agent-App
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-017：NotificationBell 用帧 id 去重（前端）

**归属**
- 所属切片：S4（WP-4 通知去重）
- 执行 Agent：Agent-App
- 来源需求：同 TASK-016
- 来源方案：DESIGN-001 §⑤ Events

**目标**
实时帧的 id 写入 serverId；同一通知经 SSE 与历史各到一次时只显示一条。帧无 id 时保持现行内容窗口去重。

**输入**
- apps/web/components/NotificationBell.tsx:36、105-128
- DESIGN-001 §⑤ 帧 Schema（id 可选）

**输出**（新增/修改的文件）
- `apps/web/components/NotificationBell.tsx`
- apps/web/tests/notification-bell-dedupe.spec.tsx（新增）

**Execution Steps**
1. [ ] SSE onmessage 解析 id → serverId
2. [ ] 合并逻辑统一按 serverId 去重，缺失时回落现规则
3. [ ] vitest：先 SSE 后 history、先 history 后 SSE、帧无 id 三用例

**验收标准**
- [ ] 三用例全绿；既有 vitest 零回归

**验证命令**
```bash
cd apps/web && pnpm run test:unit -- --run
```

**证据路径**
`docs/06_validation/evidence/EVD-017/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/web/components/NotificationBell.tsx`
- `apps/web/tests/notification-bell-dedupe.spec.tsx`

**禁止修改**
- apps/api/**
- packages/**

**依赖与阻塞**
- Depends on：无
- Blocks：无
- 阻塞条件：—

**建议执行档位**
sonnect　理由：组件 + 单测

**升级条件**
2 次失败 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小（与 TASK-016 同刀演示）
