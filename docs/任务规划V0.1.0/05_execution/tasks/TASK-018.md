---
id: TASK-018
type: task
title: check_docs_consistency 入 CI 与 preflight
status: ready
slice: S5
owner: Agent-Guard
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-018：check_docs_consistency 入 CI 与 preflight

**归属**
- 所属切片：S5（WP-5 治理门禁）
- 执行 Agent：Agent-Guard
- 来源需求：roadmap v0.6.5 未勾项『治理脚本入 CI 强制步』
- 来源方案：—

**目标**
CI backend job 与 scripts/preflight.sh 都执行 check_docs_consistency.py，失败即红。

**输入**
- .github/workflows/ci.yml:97（契约漂移门禁附近）
- scripts/preflight.sh
- 现状：全仓 grep check_docs_consistency 仅脚本自身

**输出**（新增/修改的文件）
- `.github/workflows/ci.yml`
- `scripts/preflight.sh`

**Execution Steps**
1. [ ] ci.yml backend job 在契约门禁后加一步 python "$GITHUB_WORKSPACE/scripts/check_docs_consistency.py"
2. [ ] preflight.sh 加同名检查
3. [ ] actionlint 通过

**验收标准**
- [ ] actionlint 零告警
- [ ] CI 中该 step 存在且绿
- [ ] 故意在 backlog 写一个不存在路径时 step 红（本地验证）

**验证命令**
```bash
actionlint && bash scripts/preflight.sh && python scripts/check_docs_consistency.py
```

**证据路径**
`docs/06_validation/evidence/EVD-018/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `.github/workflows/ci.yml`
- `scripts/preflight.sh`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- scripts/check_docs_consistency.py

**依赖与阻塞**
- Depends on：无
- Blocks：无
- 阻塞条件：—

**建议执行档位**
haiku　理由：追加一步

**升级条件**
actionlint 红 → sonnect；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小
