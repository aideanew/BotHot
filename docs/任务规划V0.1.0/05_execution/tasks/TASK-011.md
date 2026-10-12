---
id: TASK-011
type: task
title: 访客策略文档对账
status: ready
slice: S2
owner: Agent-Doc
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-011：访客策略文档对账

**归属**
- 所属切片：S2（WP-2 访客访问策略）
- 执行 Agent：Agent-Doc
- 来源需求：协作纪律 §5（文档与代码一致）
- 来源方案：ADR-0009

**目标**
CHANGELOG Unreleased、backlog AUTHGATE-002 与 ADR-0009 一致，无互相矛盾表述。

**输入**
- CHANGELOG.md:11-44
- docs/04_engineering/backlog.md AUTHGATE 节

**输出**（新增/修改的文件）
- `CHANGELOG.md`
- `docs/04_engineering/backlog.md`

**Execution Steps**
1. [ ] 删除/改写『middleware 裁定不实施』与『公共引流位保持可见』等与现状冲突的表述
2. [ ] backlog AUTHGATE-002 指向 ADR-0009 并附 TASK-010 提交哈希

**验收标准**
- [ ] python scripts/check_docs_consistency.py 退出 0
- [ ] 人工：CHANGELOG 与 ADR 无矛盾句

**验证命令**
```bash
python scripts/check_docs_consistency.py
```

**证据路径**
`docs/06_validation/evidence/EVD-011/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `CHANGELOG.md`
- `docs/04_engineering/backlog.md`

**禁止修改**
- apps/**
- packages/**

**依赖与阻塞**
- Depends on：TASK-010
- Blocks：无
- 阻塞条件：—

**建议执行档位**
haiku　理由：文档同步

**升级条件**
出现新冲突需判断 → sonnect；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小
