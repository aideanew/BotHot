---
id: PROJECT-MAP
type: navigation
title: BotHot 项目导航地图
status: active
owner: governance
created: 2026-09-29
updated: 2026-09-30
version: 1.2
---

# BotHot 项目导航地图

> 本文件是整个文档体系的入口。按分类目录组织，每个文档标注状态和负责角色。

## 00_governance/ — 治理

| 文档 | 说明 | 状态 |
|---|---|---|
| [project-map.md](project-map.md) | 本文件——全文档导航 | active |
| [document-index.md](document-index.md) | 文档索引（ID → 路径映射） | active |
| [glossary.md](glossary.md) | 术语表 | active |
| [doc-spec.md](doc-spec.md) | 文档规范 v1.1 | active |
| [doc-migration-map.md](doc-migration-map.md) | .docs/ → docs/ 迁移映射表 | active |

## 01_product/ — 产品

| 文档 | 说明 | 状态 |
|---|---|---|
| [product-vision.md](../01_product/product-vision.md) | 产品愿景 | active |
| [product-goals.md](../01_product/product-goals.md) | 产品目标 | active |
| [product-scope.md](../01_product/product-scope.md) | 产品范围 | active |

## 02_requirements/ — 需求

| 文档 | 说明 | 状态 |
|---|---|---|
| [product-requirements.md](../02_requirements/product-requirements.md) | 功能需求基线（9 域 + 10 前端域） | active |
| [inbox/](../02_requirements/inbox/) | 新需求收件箱 | — |

## 03_solution/ — 解决方案

| 文档 | 说明 | 状态 |
|---|---|---|
| [architecture.md](../03_solution/architecture.md) | 系统架构设计 | active |
| [project-structure-design.md](../03_solution/project-structure-design.md) | 项目目录架构设计 | active |
| [decisions/adr-index.md](../03_solution/decisions/adr-index.md) | ADR 决策索引（7 条决策） | active |

## 04_engineering/ — 工程

| 文档 | 说明 | 状态 |
|---|---|---|
| [roadmap.md](../04_engineering/roadmap.md) | 路线图（v0.3 → v1.0） | active |
| [backlog.md](../04_engineering/backlog.md) | 待办清单 | active |
| [conventions.md](../04_engineering/conventions.md) | 工程规范 | active |
| [cross-platform.md](../04_engineering/cross-platform.md) | 跨平台分工：CI ubuntu=正式验收面、CI windows=开发平台门、@win=烟测（STEP-00X / D-V4-01） | active |

## 05–09 分类

| 分类 | 用途 | 状态 |
|---|---|---|
| `04_planning/` | 发布计划 | ⚠ **目录存在但为空壳**——`ls docs/04_planning` 只有空目录 `releases/`，
**没有 `current-plan.md`**。而 25 张任务卡的 frontmatter 一律写
`plan: docs/04_planning/current-plan.md`（`grep -h '^plan:' …/tasks/*.md | sort | uniq -c`
→ 25 次同一路径）⇒ **全部为悬空引用**。当前计划实体的真实位置是
`docs/任务规划V0.1.0/04_planning/current-plan.md`。收口需二选一并留证据：
把计划发布到卡片所指路径，或改 25 张卡的 `plan:` 字段。此项需人工裁决（见 TASK-019 回报段） |
| `05_execution/` | 任务跟踪 | ✅ **已启用**——`docs/05_execution/tasks/` 有 4 份历史任务计划
（TASK-PLAN-v0.6 / v0.7 / v0.8 / v0.9）。原标"🔲 预留"与目录实况不符；
注意本目录放的是**历史**任务计划，当前计划在 `04_planning/current-plan.md`（该文件缺失，见上一行） |
| [06_validation/](../06_validation/) | 验证与测试 | ✅ **已启用**——顶层有 `acceptance/`、`evidence/`、
`test-results/`；活体证据 [`evidence/channeltest-20260929/`](../06_validation/evidence/channeltest-20260929/README.md)
（4 平台文章来源活体实测，TC 编号逐条可对） |
| `07_release/` | 发布记录 | 🟡 **部分启用**——实际文件只有 `key-rotation-sop.md`（密钥轮换 SOP，
即 TASK-001 的落点文档）；`release-notes/` 与 `release-records/` 为仅含 `.gitkeep` 的空目录。
原标"🔲 预留"与目录实况不符，但发布记录本身尚未产出 |
| `08_knowledge/` | 知识库 | ✅ **已启用**——有 `meetings/`、`retrospectives/`、`technical-notes/` 三个子目录 |
| `09_archive/` | 归档 | 🔲 预留 |

---

## 快速入口

**我是新人，想了解项目** → 01_product/product-vision.md → 02_requirements/product-requirements.md → 03_solution/architecture.md

**我想看目录结构** → 03_solution/project-structure-design.md

**我想看待办** → 04_engineering/backlog.md

**我想看路线图** → 04_engineering/roadmap.md

**我想查术语** → 00_governance/glossary.md

**我想提需求** → 02_requirements/inbox/（创建新文件，等待评审）

**我想看旧文档迁移** → 00_governance/doc-migration-map.md
