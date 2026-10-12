---
id: TASK-012
type: task
title: bot 域响应模型（Pydantic）声明并接入序列化
status: blocked
slice: S3
owner: Agent-API
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-012：bot 域响应模型（Pydantic）声明并接入序列化

**归属**
- 所属切片：S3（WP-3 响应形状契约）
- 执行 Agent：Agent-API
- 来源需求：REQ-F-001；packages/contracts index.ts『响应形状生成器扩展已登记 backlog』
- 来源方案：ADR-0008（提议）

**目标**
bots.py 的渠道、任务、日志三类响应由 Pydantic 模型定义，出现在 /openapi.json components 中，线上 JSON 形状不变。

**输入**
- apps/api/app/api/v1/bots.py:134（_serialize_log 8 字段）、_serialize_channel（secret_enc→has_secret）
- DESIGN-001 §① bot 响应 Schema

**输出**（新增/修改的文件）
- apps/api/app/api/v1/schemas/bot.py（新增）
- `apps/api/app/api/v1/bots.py`
- apps/api/tests/test_bot_response_shape.py（新增）

**Execution Steps**
1. [ ] 新建 BotChannelOut/PushTaskOut/PushLogOut 与 PageOf[T] 泛型（page/page_size 口径）
2. [ ] 序列化函数改为构造模型后 model_dump(mode='json')，字段与现输出逐字一致
3. [ ] 路由声明 responses/response_model 使其进入 OpenAPI（信封保持 Envelope）
4. [ ] 新增快照测试：同一夹具改造前后 JSON 相等

**验收标准**
- [ ] 快照测试通过（形状零漂移）
- [ ] app.openapi()['components']['schemas'] 含三模型
- [ ] 后端全量 pytest 零回归；ruff/mypy 绿

**验证命令**
```bash
cd apps/api && pytest tests/test_bot_response_shape.py -q && python -c "from app.main import create_app;s=create_app().openapi()['components']['schemas'];assert {'BotChannelOut','PushTaskOut','PushLogOut'}<=set(s)" && ruff check app tests && mypy app
```

**证据路径**
`docs/06_validation/evidence/EVD-012/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/api/app/api/v1/schemas/bot.py`
- `apps/api/app/api/v1/schemas/__init__.py`
- `apps/api/app/api/v1/bots.py`
- `apps/api/tests/test_bot_response_shape.py`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- apps/api/app/api/v1/hot.py
- apps/web/**

**依赖与阻塞**
- Depends on：D-09（ADR-0008 批准）
- Blocks：TASK-014
- 阻塞条件：形状必须变化才能建模 → 停，属 API 契约变更

**建议执行档位**
sonnect　理由：模式化改造 + 快照测试

**升级条件**
快照不一致无法消除 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中
