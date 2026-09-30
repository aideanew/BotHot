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

## 05–09 分类

| 分类 | 用途 | 状态 |
|---|---|---|
| `04_planning/` | 发布计划 | 🔲 预留 |
| `05_execution/` | 任务跟踪 | 🔲 预留 |
| [06_validation/](../06_validation/) | 验证与测试 | ✅ **已启用**——已有实测证据：[`evidence/channeltest-20260929/`](../06_validation/evidence/channeltest-20260929/README.md)（4 平台文章来源活体实测，TC 编号逐条可对）+ `acceptance/`、`test-results/` |
| `07_release/` | 发布记录 | 🔲 预留 |
| `08_knowledge/` | 知识库 | 🔲 预留 |
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
