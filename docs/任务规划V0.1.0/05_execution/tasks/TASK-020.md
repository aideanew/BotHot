---
id: TASK-020
type: task
title: .docs/ 遗留『待迁移』6 项：迁移或归档
status: blocked
slice: S5
owner: Agent-Doc
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-020：.docs/ 遗留『待迁移』6 项：迁移或归档

**归属**
- 所属切片：S5（WP-5 治理门禁）
- 执行 Agent：Agent-Doc
- 来源需求：docs/00_governance/doc-migration-map.md 中 6 条『待迁移』
- 来源方案：—

**目标**
doc-migration-map 中不再有『待迁移』状态；每项要么已迁移并与代码核对，要么归档并注明原因。

**输入**
- docs/00_governance/doc-migration-map.md
- .docs/03_solution/interfaces/API接口文档.md（162KB，AideanBot 时代）
- .docs/03_solution/interfaces/数据库文档.md
- SSO 3 文件、test-plans 2 文件

**输出**（新增/修改的文件）
- `docs/00_governance/doc-migration-map.md`
- `docs/09_archive/superseded/**`
- docs/03_solution/**（若选迁移）

**Execution Steps**
1. [ ] 按 D-05 结论执行
2. [ ] 若迁移 API 文档：以 FastAPI /openapi.json 为准，不手抄旧文档

**验收标准**
- [ ] grep -c '待迁移' doc-migration-map.md == 0

**验证命令**
```bash
grep -c '待迁移' docs/00_governance/doc-migration-map.md
```

**证据路径**
`docs/06_validation/evidence/EVD-020/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `docs/**`

**禁止修改**
- apps/**
- .docs/**（只读，不删）

**依赖与阻塞**
- Depends on：D-05
- Blocks：无
- 阻塞条件：D-05 未裁决 → blocked

**建议执行档位**
haiku（归档）/ sonnect（迁移）　理由：视裁决

**升级条件**
—；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中
