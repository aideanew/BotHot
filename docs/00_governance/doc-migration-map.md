---
id: DOC-MIGRATION-MAP
type: reference
title: .docs/ → docs/ 迁移映射表
status: active
owner: governance
created: 2026-09-29
updated: 2026-09-29
---

# .docs/ → docs/ 迁移映射表

> 本表列出旧 `.docs/` 目录下每个文档的目标位置。

## 00_governance/

| 旧路径 | 新路径 | 处理方式 |
|---|---|---|
| `DOC-REORG-PLAN-SPEC-20260929.md` | `09_archive/superseded/` | 归档（已被 doc-spec.md 替代） |
| `project-map.md` | `00_governance/project-map.md` | 已替代（新版本） |
| `开发流程.md` | `00_governance/doc-spec.md` | 已替代（并入文档规范） |
| `文档索引.md` | `00_governance/document-index.md` | 已替代（新版本） |
| `文档规范-v1.1.md` | `00_governance/doc-spec.md` | 已替代（新版本） |
| `编号互转表.md` | `09_archive/superseded/` | 归档（旧编号体系不再使用） |
| `阻塞项登记表.md` | `04_engineering/backlog.md` | 已替代（并入待办清单） |

## 02_requirements/

| 旧路径 | 新路径 | 处理方式 |
|---|---|---|
| `backlog.md` | `04_engineering/backlog.md` | 已替代（新版本） |
| `inbox/README.md` | `02_requirements/inbox/README.md` | 已替代（新版本） |
| `需求文档.md` | `02_requirements/product-requirements.md` | 已替代（新版本） |

## 03_solution/

| 旧路径 | 新路径 | 处理方式 |
|---|---|---|
| `decisions/ADR-0001-RAG引擎选型.md` | `03_solution/decisions/adr-0001-rag-engine-selection.md` | 已替代（新版本） |
| `decisions/ADR-0002-消息拓扑与LLM计费路径.md` | `03_solution/decisions/adr-0002-message-topology-and-llm-billing.md` | 已替代 |
| `decisions/ADR-0003-会话与知识空间解析规则.md` | `03_solution/decisions/adr-0003-session-and-space-resolution.md` | 已替代 |
| `decisions/ADR-0004-知识库引擎可插拔.md` | `03_solution/decisions/adr-0004-pluggable-engine-architecture.md` | 已替代 |
| `interfaces/API接口文档.md` | `03_solution/api-reference.md` | 待迁移 |
| `interfaces/主平台统一账号接入说明/` | `03_solution/sso-integration/` | 待迁移（3 个文件） |
| `interfaces/数据库文档.md` | `03_solution/database-schema.md` | 待迁移 |
| `solutions/SPEC-知识库平台化总设计.md` | `03_solution/architecture.md` | 已替代（新架构文档） |
| `solutions/SPEC-素材资产化与公共知识库.md` | `03_solution/design/public-library-design.md` | 待迁移 |
| `solutions/R9-SSO-backchannel-logoutUri补齐*.md` | `09_archive/superseded/` | 归档（已实施完成） |
| `solutions/SPEC-M3后台管理*.md` | `09_archive/superseded/` | 归档（已实施完成） |
| `solutions/SPEC-T4.3飞书知识库扩槽*.md` | `09_archive/superseded/` | 归档 |
| `solutions/SPEC-T6.1微信通道与Bot接线*.md` | `09_archive/superseded/` | 归档 |
| `solutions/r8-redfox对接活体实测*.md` | `09_archive/superseded/` | 归档 |
| `test-plans/SSO测试方案.md` | `06_validation/test-plans/sso-test-plan.md` | 待迁移 |
| `test-plans/SSO联调测试方案.md` | `06_validation/test-plans/sso-integration-test.md` | 待迁移 |

## 04_planning/

| 旧路径 | 新路径 | 处理方式 |
|---|---|---|
| `R6-剩余任务原子化执行大纲*.md` | `09_archive/superseded/` | 归档（已被 backlog.md 替代） |
| `R7-需求全景穿透*.md` | `09_archive/superseded/` | 归档 |
| `剩余任务原子化执行大纲*.md` | `09_archive/superseded/` | 归档 |
| `当前态快照.md` | `04_engineering/roadmap.md` | 已替代（新版本） |

## 05_execution/

| 旧路径 | 新路径 | 处理方式 |
|---|---|---|
| `任务进度.md` | `04_engineering/backlog.md` | 已替代（新版本） |

## 06_validation/

| 旧路径 | 新路径 | 处理方式 |
|---|---|---|
| `reports/F项锚点覆盖率报告.md` | `06_validation/evidence/anchor-coverage-report.md` | 待迁移 |
| `reports/M0能力实证总报告.md` | `06_validation/evidence/m0-capability-report.md` | 待迁移 |
| `reports/R6.1.1-镜像漂移取证报告*.md` | `06_validation/evidence/image-drift-report.md` | 待迁移 |
| `reports/修复报告*.md` | `09_archive/superseded/` | 归档 |
| `reports/活体单篇验证报告*.md` | `06_validation/evidence/live-validation-report.md` | 待迁移 |

## 08_knowledge/

| 旧路径 | 新路径 | 处理方式 |
|---|---|---|
| `RSS分析/output_*.md` (6 个) | `08_knowledge/technical-notes/rss-analysis/` | 待迁移（6 个 LLM 分析结果） |
| `交接提示词/*.md` (2 个) | `09_archive/superseded/` | 归档（交接已完成） |

## 09_archive/

| 旧路径 | 新路径 | 处理方式 |
|---|---|---|
| `inception/立项分析/*.md` (6 个) | `09_archive/inception/` | 原样迁移 |
| `superseded/*.md` (11 个) | `09_archive/superseded/` | 原样迁移 |

## 10_operations/

| 旧路径 | 新路径 | 处理方式 |
|---|---|---|
| `部署运维手册.md` | `04_engineering/deployment-guide.md` | 待迁移 |

## 采集渠道/

| 旧路径 | 新路径 | 处理方式 |
|---|---|---|
| `数据时效性对比*.md` | `08_knowledge/technical-notes/data-timeliness-comparison.md` | 待迁移 |
| `采集成本对比*.md` | `08_knowledge/technical-notes/collection-cost-comparison.md` | 待迁移 |

---

## 迁移状态汇总

| 状态 | 数量 | 说明 |
|---|---|---|
| ✅ 已替代 | 15 | 旧文档内容已被新 docs/ 文档覆盖 |
| 🔲 待迁移 | 14 | 需要手动迁移到新位置 |
| 📦 归档 | 24 | 移入 09_archive/，不再活跃 |

> 迁移完成后，`.docs/` 目录可删除。归档文档在 `docs/09_archive/` 保留历史记录。
