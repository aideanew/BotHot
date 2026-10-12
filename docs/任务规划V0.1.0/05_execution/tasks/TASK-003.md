---
id: TASK-003
type: task
title: 端口与底座口径落档（依裁决 D-02）
status: blocked
slice: S0
owner: Agent-Doc
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-003：端口与底座口径落档（依裁决 D-02）

**归属**
- 所属切片：S0（WP-0 安全止血）
- 执行 Agent：Agent-Doc
- 来源需求：REQ-C-002（端口分配）
- 来源方案：ADR-0010（提议）

**目标**
AGENTS.md / README / conventions.md 的 PG、Redis 端口与实际编排一致，且只有一种口径。

**输入**
- 裁决 D-02 结果
- AGENTS.md 端口表（5433/6380）
- docker/compose.yml:46-47（共享底座 5435/6379）

**输出**（新增/修改的文件）
- `AGENTS.md`
- `README.md`
- `docs/04_engineering/conventions.md`

**Execution Steps**
1. [ ] 按 D-02 结论更新三处端口表
2. [ ] README『服务与启动顺序』改写为共享底座或栈内二选一的实际形态
3. [ ] make guard-ports 若需新增检查，提交需求给 Agent-Guard（本任务不改 Makefile）

**验收标准**
- [ ] 三份文档端口表逐字一致
- [ ] 与 docker/compose.yml 实际值一致（人工比对表格）

**验证命令**
```bash
grep -nE '5433|5435|6380|6379' AGENTS.md README.md docs/04_engineering/conventions.md docker/compose.yml
```

**证据路径**
`docs/06_validation/evidence/EVD-003/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `AGENTS.md`
- `README.md`
- `docs/04_engineering/conventions.md`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- docker/**
- Makefile

**依赖与阻塞**
- Depends on：TASK-002、D-02
- Blocks：无
- 阻塞条件：D-02 未裁决 → blocked

**建议执行档位**
haiku　理由：纯文档替换

**升级条件**
出现第三种口径 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小（并入 S0）
