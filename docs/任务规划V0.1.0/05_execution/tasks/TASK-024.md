---
id: TASK-024
type: task
title: .project/ 第三方源码去留（条件：D-07）
status: blocked
slice: S7
owner: Agent-Guard
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-024：.project/ 第三方源码去留（条件：D-07）

**归属**
- 所属切片：S7（WP-7 待裁决处置）
- 执行 Agent：Agent-Guard
- 来源需求：仓库卫生
- 来源方案：—

**目标**
A：.project/ 移出版本库并 gitignore；B：保留并在 README/AGENTS 说明用途与许可。

**输入**
- .project/（7 个第三方项目，125M，git ls-files 4385 个文件）

**输出**（新增/修改的文件）
- A：.gitignore、.project/**（rm + git add）
- B：AGENTS.md 一节

**Execution Steps**
1. [ ] A：外部备份 → rm -r .project → git add -u .project → .gitignore 加条目
2. [ ] B：写明用途

**验收标准**
- [ ] A：git ls-files .project | wc -l == 0；CI 绿

**验证命令**
```bash
git ls-files .project | wc -l
```

**证据路径**
`docs/06_validation/evidence/EVD-024/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `.gitignore`
- `.project/**`
- `AGENTS.md`

**禁止修改**
- apps/**
- packages/**

**依赖与阻塞**
- Depends on：D-07
- Blocks：无
- 阻塞条件：发现 apps/** 引用 .project 内文件 → 停

**建议执行档位**
haiku　理由：机械操作

**升级条件**
—；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小
