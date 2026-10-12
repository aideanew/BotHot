---
id: TASK-023
type: task
title: embedding.py 处置（条件：D-06）
status: blocked
slice: S7
owner: Agent-API
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-023：embedding.py 处置（条件：D-06）

**归属**
- 所属切片：S7（WP-7 待裁决处置）
- 执行 Agent：Agent-API
- 来源需求：TASK-PLAN-v0.9 S2.6；backlog HOT-005
- 来源方案：—

**目标**
A：删除 app/providers/embedding.py 与 tests/test_embedding.py；B：保留并登记为 HOT-005 前置。

**输入**
- grep：app.providers.embedding 仅 tests/test_embedding.py 引用

**输出**（新增/修改的文件）
- A：两文件删除（rm + git add，遵守『禁止 git rm』）
- B：backlog 注记

**Execution Steps**
1. [ ] A：rm 两文件 → 全量 pytest → ruff/mypy
2. [ ] B：仅文档

**验收标准**
- [ ] A：git grep 'providers.embedding' 零命中；pytest 零回归

**验证命令**
```bash
git grep -n 'providers.embedding'; cd apps/api && pytest -q
```

**证据路径**
`docs/06_validation/evidence/EVD-023/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/api/app/providers/embedding.py`
- `apps/api/tests/test_embedding.py`
- `docs/04_engineering/backlog.md`

**禁止修改**
- 其余全部

**依赖与阻塞**
- Depends on：D-06
- Blocks：无
- 阻塞条件：—

**建议执行档位**
haiku　理由：删除或注记

**升级条件**
pytest 红 → sonnect；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小
