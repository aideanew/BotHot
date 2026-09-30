# AGENTS.md — BotHot AI 协作规范

> 本文件是 AI Agent 在 BotHot 项目中工作的入口规范。人类开发者也建议阅读。

## 深度推理模式（强制）

在给出任何设计结论或架构决策之前，必须执行三轮推理：

### 第一轮（发散）：5W1H 全面拆解
显式回答：
1. **What** — 客观事实/现象是什么？
2. **Why** — 深层原因/动机是什么？
3. **Where/When** — 适用的边界条件、时间节点是什么？
4. **Who** — 涉及的主体、责任方是谁？
5. **How** — 执行的手段、方法是什么？
6. **What if** — 如果前提变了，结论会怎样？

### 第二轮（收敛与拷问）
- 对每个节点做苏格拉底式"致命追问"。
- 对关键节点做双向钢人论证（two-way steelmanning）。

### 第三轮（重构）
- 只有当无法再用新问题推翻自己时，输出终稿。
- 终稿必须带前提条件和局限性说明。

## 开发流程（六步循环）

一切功能性变更（代码、目录结构、公开接口、数据库模型等）遵循：

```
PLAN 规划 → SPEC 规格 → APPROVE 批准 → IMPLEMENT 实施 → VERIFY 核验 → CLOSE 归档
```

代码改动必须同步到对应文档和任务进度中。

## 端口分配准则（强制）

| 端口 | 用途 | 约束 |
|------|------|------|
| 3000 | 主平台专用 | ❌ BotHot 任何服务禁止占用 |
| 3200 | BotHot 前端宿主端口 | 容器内部 3000，宿主映射 3200 |
| 3300 | BotHot 后端端口 | 容器内部 3300 |
| 5300 | LangBot | — |
| 5433 | PostgreSQL | 容器 5432 → 宿主 5433 |
| 6380 | Redis | 容器 6379 → 宿主 6380 |

> 端口变更需先经架构裁决并同步本文档 + docs/04_engineering/conventions.md。

## 文档体系入口

所有项目文档在 `docs/` 目录，入口导航：

- **项目导航地图** → [docs/00_governance/project-map.md](docs/00_governance/project-map.md)
- **功能需求基线** → [docs/02_requirements/product-requirements.md](docs/02_requirements/product-requirements.md)
- **系统架构设计** → [docs/03_solution/architecture.md](docs/03_solution/architecture.md)
- **项目目录架构设计** → [docs/03_solution/project-structure-design.md](docs/03_solution/project-structure-design.md)
- **工程规范** → [docs/04_engineering/conventions.md](docs/04_engineering/conventions.md)
- **路线图** → [docs/04_engineering/roadmap.md](docs/04_engineering/roadmap.md)
- **待办清单** → [docs/04_engineering/backlog.md](docs/04_engineering/backlog.md)

## 当前项目状态

- **版本**：v0.5（v0.4 推送能力落地 + v0.5 热点融合，2026-09-30 五路并行交付集成审查通过）
- **后端**：FastAPI + SQLAlchemy 2.0 + Alembic，9 个业务域
- **前端**：Next.js 14 App Router，10 个功能域
- **推送**：6 渠道 Provider 真实投递（飞书/钉钉/企微/Webhook 已通；**站内通知投递侧**通——Redis pub/sub，**前端订阅侧未实现**；微信 ClawBot 需部署服务）；PushScheduler 60s 调度（SKIP LOCKED 短锁领取，多副本安全）；Cron 完整 5 段式 + 三种简写兼容（`services/cron_expr.py`，croniter）；Cron 任务创建/编辑/暂停恢复/run-now 全生命周期正确；**事件触发已实现**——PG outbox 表 `push_events`（worker 产、backend 调度器消费）+ 模板变量；渠道密钥 **AES-256-GCM 已落库**（`core/secret_crypto.py`，AAD 绑定 channel id，`PUSH_SECRET_MASTER_KEY` fail-closed，存量迁移 `ab1004w1a`）
- **文章来源**：4 平台已接入（providers/article_sources/）—— Dajiala 极致了（发现+HTML详情）、JustOneAPI（发现+正文详情）、TikHub（发现+搜索，需充值）、Wellbyte 数井（搜索+URL驱动发现）；与 RedFox 共存于发现注册表，详情兜底协调器按成本排序
- **热点**：已落地——聚簇（字 bigram TF-IDF 单链接凝聚，Job 队列执行，手动+每日定时）、评分（48h 独立来源加权 + 24h 半衰 + 状态机）、Feed 三类生产者（文章入库/聚簇/日报，`(item_type,ref_id)` upsert）、日报（LLM 摘要失败降级首段截断，每日 06:30 自动生成前一日）；业务日界 = Asia/Shanghai
- **测试**：连库用例真实执行（CI 有 postgres service + skip 门禁）；全量 798 passed / 2 skipped（隔离 PG 实测 2026-09-30）
- **目录结构**：当前 backend/ + frontend/，目标 apps/api/ + apps/web/（见 project-structure-design.md）

## 关键约束

1. **不修改 AideanBot 原项目** — BotHot 是独立副本
2. **SSO 身份锚点 = users.sub** — 余额/等级从不持久化，实时查询主平台
3. **渠道字段存为 String(32) 而非 enum** — 新增渠道零数据库迁移
4. **Job 队列在 PostgreSQL** — FOR UPDATE SKIP LOCKED，不引入 Redis 队列
5. **LLM 流式直连 SiliconFlow** — 不经 LangBot 转发
6. **推送 Provider 契约** — delivered=True/False + reason + response_data，失败时有可读原因（不伪造回执）
