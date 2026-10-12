---
id: TASK-022
type: task
title: BotBinding 死表处置（条件：D-03）
status: blocked
slice: S7
owner: Agent-Data
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-022：BotBinding 死表处置（条件：D-03）

**归属**
- 所属切片：S7（WP-7 待裁决处置）
- 执行 Agent：Agent-Data
- 来源需求：TASK-PLAN-v0.9 S2.3
- 来源方案：—

**目标**
A：删除 BotBinding 模型与表（迁移 ab1006w6a）；B：保留并在 entities.py 注明保留理由。二选一完成。

**输入**
- apps/api/app/models/entities.py（class BotBinding）
- grep：除模型外仅注释提及（admin.py:16、process_heartbeat.py:27）
- 迁移链当前单头 ab1005w5b

**输出**（新增/修改的文件）
- A：apps/api/app/models/entities.py、apps/api/alembic/versions/ab1006w6a_drop_bot_binding.py、scripts/gen_contracts（无需）
- B：apps/api/app/models/entities.py（注释）

**Execution Steps**
1. [ ] A：模型删除 → 新迁移 down_revision='ab1005w5b'，upgrade drop_table、downgrade 重建 → 单头断言
2. [ ] B：只加注释

**验收标准**
- [ ] A：alembic heads 单头 = ab1006w6a；upgrade/downgrade 往返在隔离 PG 通过；全量 pytest 零回归
- [ ] B：文档登记

**验证命令**
```bash
cd apps/api && python -m alembic heads && python -m alembic upgrade head && python -m alembic downgrade -1 && python -m alembic upgrade head
```

**证据路径**
`docs/06_validation/evidence/EVD-022/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/api/app/models/entities.py`
- `apps/api/alembic/versions/ab1006w6a_drop_bot_binding.py`

**禁止修改**
- packages/**
- apps/web/**

**依赖与阻塞**
- Depends on：D-03
- Blocks：无
- 阻塞条件：发现生产库该表有数据 → 停

**建议执行档位**
sonnect（执行）+ opus（迁移审）　理由：迁移不可逆风险

**升级条件**
—；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小
