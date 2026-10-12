---
id: TASK-013
type: task
title: hot 域响应模型（Pydantic）声明并接入序列化
status: blocked
slice: S3
owner: Agent-API
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-013：hot 域响应模型（Pydantic）声明并接入序列化

**归属**
- 所属切片：S3（WP-3 响应形状契约）
- 执行 Agent：Agent-API
- 来源需求：REQ-F-002
- 来源方案：ADR-0008（提议）

**目标**
hot.py 的 topics/daily/feed 响应由 Pydantic 模型定义并进入 OpenAPI，线上 JSON 形状不变。

**输入**
- apps/api/app/api/v1/hot.py:89/193/344（分页返回点）
- DESIGN-001 §① hot 响应 Schema

**输出**（新增/修改的文件）
- apps/api/app/api/v1/schemas/hot.py（新增）
- `apps/api/app/api/v1/hot.py`
- apps/api/tests/test_hot_response_shape.py（新增）

**Execution Steps**
1. [ ] 新建 HotTopicOut/HotTopicDetailOut/DailyReportOut/FeedItemOut
2. [ ] 序列化改造 + 路由声明
3. [ ] 快照测试

**验收标准**
- [ ] 快照测试通过
- [ ] OpenAPI components 含四模型
- [ ] 全量 pytest 零回归；ruff/mypy 绿

**验证命令**
```bash
cd apps/api && pytest tests/test_hot_response_shape.py -q && ruff check app tests && mypy app
```

**证据路径**
`docs/06_validation/evidence/EVD-013/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/api/app/api/v1/schemas/hot.py`
- `apps/api/app/api/v1/hot.py`
- `apps/api/tests/test_hot_response_shape.py`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- apps/api/app/api/v1/bots.py
- apps/api/app/api/v1/schemas/__init__.py（归 TASK-012；本任务直接 import app.api.v1.schemas.hot，Python 3 命名空间包在 __init__ 尚未合并时同样可导入）
- apps/web/**

**依赖与阻塞**
- Depends on：D-09
- Blocks：TASK-014
- 阻塞条件：同 TASK-012

**建议执行档位**
sonnect　理由：同上

**升级条件**
同上；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中
