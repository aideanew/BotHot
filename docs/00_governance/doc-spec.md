---
id: DOC-SPEC
type: convention
title: BotHot 文档规范 v1.1
status: active
owner: governance
created: 2026-09-29
updated: 2026-09-29
version: 1.1
---

# BotHot 文档规范 v1.1

## 1. 文档分类

| 分类目录 | 用途 | 当前状态 |
|---|---|---|
| `00_governance/` | 治理：导航、索引、术语、规范 | ✅ 已有内容 |
| `01_product/` | 产品：愿景、目标、范围 | ✅ 已有内容 |
| `02_requirements/` | 需求：功能需求、需求收件箱 | ✅ 已有内容 |
| `03_solution/` | 解决方案：架构、目录设计、决策 | ✅ 已有内容 |
| `04_engineering/` | 工程：路线图、待办、规范 | ✅ 已有内容 |
| `04_planning/` | 规划：发布计划、里程碑 | 🔲 预留（目录已建） |
| `05_execution/` | 执行：任务跟踪 | 🔲 预留（目录已建） |
| `06_validation/` | 验证：验收标准、测试结果 | 🔲 预留（目录已建） |
| `07_release/` | 发布：发布说明、发布记录 | 🔲 预留（目录已建） |
| `08_knowledge/` | 知识：会议纪要、复盘、技术笔记 | 🔲 预留（目录已建） |
| `09_archive/` | 归档：取消/废弃/替代的文档 | 🔲 预留（目录已建） |

> 00–04 为当前活跃分类，05–09 为预留分类（目录骨架已建，按需启用）。

## 2. 文档 Frontmatter（强制）

每个 `.md` 文件**必须**以 YAML frontmatter 开头：

```yaml
---
id: <UNIQUE-ID>          # 唯一标识符，大写 + 连字符
type: <type>              # navigation|convention|requirement|architecture|decision|roadmap|backlog|vision
title: <标题>
status: active|proposed|deprecated|draft
owner: <角色>             # governance|product|architecture|engineering
created: YYYY-MM-DD
updated: YYYY-MM-DD
version: <semver>
---
```

## 3. 新需求进入流程

```text
新需求/想法
    │
    ▼
02_requirements/inbox/<name>.md    ← 草稿阶段，格式宽松
    │
    ▼ (评审通过)
02_requirements/product-requirements.md  ← 合并入正式需求基线
    │
    ▼ (架构设计)
03_solution/architecture.md        ← 更新架构设计
03_solution/decisions/adr-xxxx.md  ← 如有架构决策
    │
    ▼ (实施)
04_engineering/backlog.md          ← 进入待办
04_engineering/roadmap.md          ← 进入路线图
```

## 4. 命名规范

- 文件名：kebab-case（`product-vision.md`）
- ADR 文件：`adr-<4位编号>-<简短描述>.md`（`adr-0005-push-provider-adapter-pattern.md`）
- inbox 文件：`<简短描述>.md`（`inbox/wechat-clawbot-push.md`）

## 5. 文档状态流转

```text
draft → proposed → active → deprecated
                         ↓
                      superseded（被新文档替代，保留但标注）
```

## 6. 旧文档处理

- `.docs/` 目录下的旧文档保留但标记为 `deprecated`
- 迁移到 `docs/` 后，旧文件加注释：`> 本文档已迁移至 docs/xxx/`
- 迁移完成后可删除 `.docs/`
