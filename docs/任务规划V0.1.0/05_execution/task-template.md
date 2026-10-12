---
id: TASK-TEMPLATE
type: template
title: 原子任务卡模板
status: active
created: 2026-10-12
---

# TASK-XXX：<任务名称>

**归属**
- 所属切片：S-N（WP-N）
- 执行 Agent：
- 来源需求：REQ-F-xxx / REQ-NF-xxx
- 来源方案：ADR-xxxx / DESIGN-xxx

**目标**
<一句话，可验证>

**输入**
- 文档 / 契约 / 前置任务 / 前置状态

**输出**（精确到文件）
- `<path>`

**Execution Steps**
1. [ ] <可执行动作>

**验收标准**
- [ ] <可自动化检查优先；不可自动化写清人工判断标准>

**验证命令**
```bash
<可直接复制执行>
```

**证据路径**
`docs/06_validation/evidence/EVD-xxx/`

**允许修改**
- `<path pattern>`

**禁止修改**
- `packages/contracts/**`（非 Contract 任务）
- `apps/api/alembic/versions/**`（未登记迁移号的任务）

**依赖与阻塞**
- Depends on / Blocks / 阻塞条件

**建议执行档位**
<haiku / sonnect / opus / fable>　理由：

**升级条件**
<何时升档>；连续 2 次验收失败即熔断。

**预估规模**
<小 / 中 / 大>，是否 <2h
