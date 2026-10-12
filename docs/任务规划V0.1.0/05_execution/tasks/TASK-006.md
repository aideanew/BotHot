---
id: TASK-006
type: task
title: 错误码登记表补全 50003 并加注册一致性断言
status: blocked
slice: S1
owner: Agent-Contract
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-006：错误码登记表补全 50003 并加注册一致性断言

**归属**
- 所属切片：S1（WP-1 错误契约单一源）
- 执行 Agent：Agent-Contract
- 来源需求：REQ-F-008 / REQ-NF-002（失败可读）；errors.py 头注『先登记后实现』
- 来源方案：ADR-0008（提议）

**目标**
errors.py 中每个 AppError 子类的 code 都在 ERROR_CODES 中有登记名；50003 登记为 CONFIGURATION_ERROR。

**输入**
- apps/api/app/core/errors.py:9-37（ERROR_CODES，缺 50003）
- errors.py:222-225（ConfigurationError code=50003）
- 契约：DESIGN-001 §② Errors 目标表

**输出**（新增/修改的文件）
- `apps/api/app/core/errors.py`
- apps/api/tests/test_error_registry.py（新增）

**Execution Steps**
1. [ ] ERROR_CODES 增 50003: "CONFIGURATION_ERROR"
2. [ ] 新增测试：遍历 AppError.__subclasses__()（递归），断言 code ∈ ERROR_CODES 且 http_status 为 int
3. [ ] 跑 ruff/mypy/新测试

**验收标准**
- [ ] 新测试通过
- [ ] ruff check、mypy app 通过
- [ ] AppError(50003) 实例 name == CONFIGURATION_ERROR

**验证命令**
```bash
cd apps/api && ruff check app tests && mypy app && pytest tests/test_error_registry.py -q
```

**证据路径**
`docs/06_validation/evidence/EVD-006/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/api/app/core/errors.py`
- `apps/api/tests/test_error_registry.py`

**禁止修改**
- packages/contracts/**
- apps/web/**
- apps/api/alembic/**

**依赖与阻塞**
- Depends on：D-09
- Blocks：TASK-007
- 阻塞条件：发现其他未登记 code → 一并登记前先回报（属契约变更）

**建议执行档位**
opus　理由：改的是全栈契约源，需判断语义命名

**升级条件**
—（已是 opus）；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小
