---
id: TASK-009
type: task
title: ADR-0009 访客访问策略定稿（依裁决 D-01）
status: blocked
slice: S2
owner: Agent-Doc（opus 起草）
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-009：ADR-0009 访客访问策略定稿（依裁决 D-01）

**归属**
- 所属切片：S2（WP-2 访客访问策略）
- 执行 Agent：Agent-Doc（opus 起草）
- 来源需求：REQ-F-007（角色门禁）；backlog AUTHGATE-001/002
- 来源方案：ADR-0009（提议，本规划已起草）

**目标**
ADR-0009 状态从 proposed 变 accepted，明确 /hot、/hot/daily、/public 对游客是否可见，以及真实态是 302 还是原地渲染。

**输入**
- docs/03_solution/decisions/adr-0009-guest-access-policy.md（草案）
- apps/web/middleware.ts:14-15（白名单仅 / 与 /auth）
- apps/web/e2e/auth-gate.spec.ts:10（注释称 /hot 豁免）
- commit 2766d17（hot 页接 AuthGate）
- CHANGELOG Unreleased『公共引流位保持可见』

**输出**（新增/修改的文件）
- `docs/03_solution/decisions/adr-0009-guest-access-policy.md`
- `docs/03_solution/decisions/adr-index.md`

**Execution Steps**
1. [ ] 把 D-01 裁决结果写入 ADR『决定』节
2. [ ] 列出受影响路由表与 e2e 断言变化
3. [ ] adr-index 登记

**验收标准**
- [ ] ADR 状态 accepted，含路由 × 游客行为表
- [ ] 表内每条路由都有对应 e2e 断言计划

**验证命令**
```bash
grep -n '^status:' docs/03_solution/decisions/adr-0009-guest-access-policy.md
```

**证据路径**
`docs/06_validation/evidence/EVD-009/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `docs/03_solution/decisions/**`

**禁止修改**
- apps/**
- packages/**

**依赖与阻塞**
- Depends on：D-01
- Blocks：TASK-010、TASK-011
- 阻塞条件：D-01 未裁决 → blocked

**建议执行档位**
opus　理由：安全边界决策

**升级条件**
裁决推翻已冻结的 Identity 契约 → fable；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小
