---
id: TASK-021
type: task
title: 性能基线测量脚本与首测
status: ready
slice: S6
owner: Agent-Guard
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-021：性能基线测量脚本与首测

**归属**
- 所属切片：S6（WP-6 基线指标）
- 执行 Agent：Agent-Guard
- 来源需求：REQ-NF-001（API<500ms、首 Token<3s、单篇入库<30s、Feed<100ms）
- 来源方案：§11 基线指标

**目标**
M-01…M-04 四项各有可复跑脚本与一次首测数值（含环境说明），落入 test-results。

**输入**
- 本规划 §11 指标定义
- 运行中的 compose 栈（共享底座）
- Job 表 created_at/updated_at（入库耗时来源）

**输出**（新增/修改的文件）
- scripts/bench/api_latency.py（新增）
- scripts/bench/chat_ttft.py（新增）
- scripts/bench/ingest_duration.sql（新增）
- `docs/06_validation/test-results/2026-10-perf-baseline.md`

**Execution Steps**
1. [ ] api_latency：对 GET /api/v1/hot/feed?page=1&page_size=20 与 GET /api/v1/bots/tasks 各 50 次，输出 p50/p95
2. [ ] chat_ttft：POST /api/v1/chat/ask 测首个 SSE data 帧时间，10 次
3. [ ] ingest_duration：对近 7 天成功 Job 计算 p50/p95（只读 SQL）
4. [ ] M-04 Feed DB 时间：EXPLAIN ANALYZE 复用 2026-10-08 留证口径
5. [ ] 汇总报告写明机器、数据量、时间

**验收标准**
- [ ] 四项指标均有数值或明确『无法测量 + 原因』
- [ ] 脚本可在同环境复跑，结果偏差记录

**验证命令**
```bash
python scripts/bench/api_latency.py --base http://127.0.0.1:3300 --n 50
python scripts/bench/chat_ttft.py --n 10
```

**证据路径**
`docs/06_validation/evidence/EVD-021/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `scripts/bench/**`
- `docs/06_validation/test-results/**`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- apps/**

**依赖与阻塞**
- Depends on：TASK-002（栈可起）
- Blocks：任何性能优化任务（本规划不排）
- 阻塞条件：无可用会话 cookie / 无测试数据 → 回报，不伪造

**建议执行档位**
sonnect　理由：脚本编写 + 实测

**升级条件**
结果离散度 > 50% → opus 复核方法；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中
