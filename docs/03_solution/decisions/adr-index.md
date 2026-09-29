---
id: ADR-INDEX
type: decision-index
title: 架构决策记录索引
status: active
owner: architecture
created: 2026-09-29
updated: 2026-09-29
---

# 架构决策记录（ADR）索引

| ADR | 标题 | 状态 | 日期 |
|---|---|---|---|
| [ADR-0001](adr-0001-rag-engine-selection.md) | RAG 引擎选型：LangBot | accepted | 2026-09-29 |
| [ADR-0002](adr-0002-message-topology-and-llm-billing.md) | 消息拓扑与 LLM 计费路径 | accepted | 2026-09-29 |
| [ADR-0003](adr-0003-session-and-space-resolution.md) | 会话与知识空间解析规则 | accepted | 2026-09-29 |
| [ADR-0004](adr-0004-pluggable-engine-architecture.md) | 知识库引擎可插拔架构 | accepted | 2026-09-29 |
| [ADR-0005](adr-0005-push-provider-adapter-pattern.md) | 多渠道推送 Provider 适配器模式 | accepted | 2026-09-29 |
| [ADR-0006](adr-0006-monorepo-apps-structure.md) | Monorepo apps/ 目录架构 | proposed | 2026-09-29 |
| [ADR-0007](adr-0007-job-queue-postgres-skip-locked.md) | Job 队列用 PostgreSQL FOR UPDATE SKIP LOCKED | accepted | 2026-09-29 |

---

## ADR-0001：RAG 引擎选型

**决策**：LangBot 作为知识引擎，知识空间 1:1 映射。
**理由**：LangBot 已有成熟的 RAG 能力，避免重复造轮子；1:1 映射降低同步复杂度。

## ADR-0002：消息拓扑与 LLM 计费路径

**决策**：LLM 流式响应直连 SiliconFlow，不经 LangBot 转发。
**理由**：LangBot 转发会增加延迟和计费复杂度；直连降低延迟，计费透明。

## ADR-0003：会话与知识空间解析规则

**决策**：通过 intent + resolver 解析目标空间。
**理由**：用户提问可能涉及多空间，需要意图检测和空间解析。

## ADR-0004：知识库引擎可插拔架构

**决策**：EnginePort 抽象 + 注册表，支持 builtin/langbot/aidean/redfox 四种后端。
**理由**：避免锁定单一引擎，新引擎接入只需实现 EnginePort 接口。

## ADR-0005：多渠道推送 Provider 适配器模式

**决策**：PushProvider 接口 + 注册表，每种渠道一个 Provider 实现。
**理由**：channel 字段存为 String(32) 而非 enum，新增渠道零数据库迁移。

## ADR-0006：Monorepo apps/ 目录架构

**决策**：从 `backend/ + frontend/` 迁移到 `apps/api/ + apps/web/` 规范化结构。
**状态**：proposed — 设计文档已完成，实施分阶段推进。
**理由**：业务域边界清晰，依赖方向可控，共享契约可提取。

## ADR-0007：Job 队列用 PostgreSQL FOR UPDATE SKIP LOCKED

**决策**：不引入 Redis 队列，Job 队列在 PostgreSQL 中用 FOR UPDATE SKIP LOCKED 实现。
**理由**：减少组件依赖；PostgreSQL 已有事务保障，SKIP LOCKED 适合多 Worker 并发拉取。
