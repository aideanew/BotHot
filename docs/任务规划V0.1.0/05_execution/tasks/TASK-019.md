---
id: TASK-019
type: task
title: 文档漂移修正批（不含端口）
status: ready
slice: S5
owner: Agent-Doc
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-019：文档漂移修正批（不含端口）

**归属**
- 所属切片：S5（WP-5 治理门禁）
- 执行 Agent：Agent-Doc
- 来源需求：协作纪律 §5、§8
- 来源方案：—

**目标**
以下已证实的漂移全部改为与代码一致：conventions.md（Node 版本、密钥现状、环境变量前缀、compose 路径、CORS 裁定、测试目录）、README（Next 版本、本地开发路径）、AGENTS『当前项目状态』（版本/Next）、product-requirements REQ-F-001（事件触发已实现）、roadmap v1.0 勾选、project-map 05–07 状态、backlog TEST-003。

**输入**
- 本规划 §2.3 不一致清单 X-01…X-12
- 代码证据：apps/web/package.json（next ^15.5.24、node >=24）、apps/web/.nvmrc=24.21.0、core/secret_crypto.py、tag v1.0.0、CI run 37906907637 success

**输出**（新增/修改的文件）
- `docs/04_engineering/conventions.md`
- `README.md`
- `AGENTS.md`
- `docs/02_requirements/product-requirements.md`
- `docs/04_engineering/roadmap.md`
- `docs/00_governance/project-map.md`
- `docs/04_engineering/backlog.md`

**Execution Steps**
1. [ ] 逐条按 §2.3 清单修改，每处附 文件:行 证据
2. [ ] 端口相关条目跳过（属 TASK-003）
3. [ ] 跑 check_docs_consistency

**验收标准**
- [ ] §2.3 中 X-01…X-12（端口项除外）逐条有对应 diff
- [ ] check_docs_consistency 退出 0

**验证命令**
```bash
python scripts/check_docs_consistency.py && grep -n 'Next.js 14\|cd backend\|Node 版本：22' README.md AGENTS.md docs/04_engineering/conventions.md; test $? -eq 1
```

**证据路径**
`docs/06_validation/evidence/EVD-019/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `docs/**`
- `README.md`
- `AGENTS.md`

**禁止修改**
- apps/**
- packages/**
- docker/**
- AGENTS.md 端口表段落

**依赖与阻塞**
- Depends on：无
- Blocks：无
- 阻塞条件：发现条目需代码改动才能一致 → 回报，不改代码

**建议执行档位**
sonnect　理由：需逐条核证据，haiku 易误改

**升级条件**
—；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中
