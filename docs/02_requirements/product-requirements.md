---
id: REQ-BASELINE
type: requirement
title: BotHot 功能需求基线
status: active
owner: product
created: 2026-09-29
updated: 2026-10-23
version: 2.0
---

# BotHot 功能需求基线

> 本文件描述当前有效的正式需求基线。**自 STEP-17（2026-10-23）起，12 条需求的详文与
> 实现度判据在子目录里逐条一份**，本文件只留摘要、链接与「需求 ↔ STEP ↔ 测试锚」三向表：
>
> - `features/REQ-F-001…008-*.md`、`non-functional/REQ-NF-001…002-*.md`、
>   `constraints/REQ-C-001…002-*.md`
>
> 每条头部三字段：`实现度`（已实现 / 部分 / 骨架 / 未实现 / **证据不足**）、
> `验收锚`（具名测试文件，或「无」）、`最后核验 commit`。
> **单一详源纪律**：详文只写在子文件里；本文件若复制其内容就成了第二份真相
> （`scripts/check_docs_consistency.py` 会红在路径与行号上，人眼不会）。
> 历史需求通过 `inbox/` 与 `docs/任务规划V0.1.0/**` 等历史版本保留，不改写。

---

## 一、业务域识别

BotHot 后端识别出 **9 个业务域**，前端识别出 **10 个功能域**。

### 后端业务域

| # | 业务域 | 核心职责 | 数据模型 | API 路由 |
|---|---|---|---|---|
| 1 | identity | 用户认证、SSO、会话、角色门禁 | User | auth.py |
| 2 | knowledge | 知识空间、内容资产、公共库 | KnowledgeSpace, ContentAsset, ShortLinkMap | spaces.py |
| 3 | subscription | 信息源订阅、Manifest Diff、同步调度 | Source, SourceSubscription, ArticleManifest | subscriptions.py |
| 4 | ingest | 文章入库流水线、Job 执行、质量评分 | Job, JobItem | extract.py |
| 5 | chat | RAG 问答、SSE 流式、意图检测 | — | chat.py, resolve.py |
| 6 | engine | 可插拔引擎管理、引擎密钥、嵌入/重排 | — | engines.py |
| 7 | bot | 多渠道推送、渠道配置、推送任务、推送日志 | BotChannel, PushTask, PushLog | bots.py |
| 8 | hot | 热点聚簇、热度评分、Feed 流、每日日报 | HotTopic, HotTopicArticle, DailyReport, FeedItem | hot.py |
| 9 | system | 系统管理、健康检查、Onboarding、进程心跳 | ProcessHeartbeat | admin.py, onboarding.py, system.py |

### 前端功能域

| # | 功能域 | 核心页面 | API 模块 |
|---|---|---|---|
| 1 | auth | /auth/aidean/callback | auth.ts |
| 2 | knowledge | /spaces, /spaces/[id], /public | spaces.ts, public-library.ts |
| 3 | subscription | /subscriptions | subscriptions.ts |
| 4 | ingest | /jobs, 添加文章面板 | jobs.ts, ingest.ts, batch.ts |
| 5 | chat | /chat | ask.ts |
| 6 | engine | /engines | engines.ts |
| 7 | bot | /bots | bots.ts |
| 8 | hot | /hot, /hot/daily | hot.ts |
| 9 | admin | /admin | admin.ts |
| 10 | onboarding | /onboarding | — |

---

## 二、功能需求清单（摘要；详文与判据见链接）

| 需求 | 一句话范围 | 实现度（判据出处见子文件） | 详文 |
|---|---|---|---|
| REQ-F-001 多渠道机器人推送 | 6 渠道 × 3 触发方式 + 渠道/任务/日志管理 | 已实现（外部前置：微信 ClawBot 需部署服务） | [features/REQ-F-001-multi-channel-push.md](features/REQ-F-001-multi-channel-push.md) |
| REQ-F-002 热点聚簇与日报 | 聚簇 / 48h 加权评分 / Feed / LLM 日报 | 已实现（聚簇升级嵌入向量属显式排除项 HOT-005） | [features/REQ-F-002-hot-cluster-daily-report.md](features/REQ-F-002-hot-cluster-daily-report.md) |
| REQ-F-003 知识库与可插拔引擎 | 多空间隔离 + 公共库 + 5 引擎位 | **部分**：builtin 已实现，main/coze/dify/fastgpt 为骨架（D-V3-03 显式不做） | [features/REQ-F-003-knowledge-base-engines.md](features/REQ-F-003-knowledge-base-engines.md) |
| REQ-F-004 公众号链接入库 | 解析 / 标准化 / 评分分类 / 短链映射 | **证据不足**：判据锚有具名用例满足，但规划侧从未给过实现度判词 | [features/REQ-F-004-article-ingest.md](features/REQ-F-004-article-ingest.md) |
| REQ-F-005 RAG 知识问答 | SSE 流式 + 多空间会话 + 可选重排 | 部分：后端在案，前端流式证据未执行过 | [features/REQ-F-005-rag-chat.md](features/REQ-F-005-rag-chat.md) |
| REQ-F-006 整号订阅与增量同步 | 订阅整号 + Manifest Diff 水位 + 锚定/滑动 + 空轮询退避 | 已实现（V0.13.0 那句「行为层未做」已过期） | [features/REQ-F-006-subscription-sync.md](features/REQ-F-006-subscription-sync.md) |
| REQ-F-007 SSO 统一认证 | OIDC + `users.sub` 锚 + HttpOnly/Lax Cookie + 角色门禁 + Backchannel Logout | 已实现（命题范围；与主平台的真实握手需白名单配合） | [features/REQ-F-007-sso.md](features/REQ-F-007-sso.md) |
| REQ-F-008 管理后台 | 空间/文档/订阅/引擎 + 渠道/任务 + 热点/日报 + Onboarding | 部分：四屏在 mock 档结构上不可达（P-88），真后端档无读数 | [features/REQ-F-008-admin-console.md](features/REQ-F-008-admin-console.md) |

> 本表**不重复**验收句：验收句在各子文件里，避免同一句话两处版本漂移。

---

## 三、非功能需求（摘要）

| 需求 | 内容 | 实现度 | 详文 |
|---|---|---|---|
| REQ-NF-001 性能 | API<500ms、首 Token<3s、入库<30s、Feed<100ms | **部分**：四条里只有「单篇入库」拿到服务层读数，其余三条无测量值（承接卡 STEP-18） | [non-functional/REQ-NF-001-performance.md](non-functional/REQ-NF-001-performance.md) |
| REQ-NF-002 安全 | Cookie / 密钥加密 / OIDC 校验 / ~~CORS 白名单~~ / SQL 注入防护 | 部分：加密与生产守卫有锚；**CORS 一条按实况改写为「经 `next.config.mjs` 同源 rewrites 达成，无 CORS 中间件」**（C-3：不重新立项）；SQL 注入与 SameSite 无机检用例 → backlog SEC-006 | [non-functional/REQ-NF-002-security.md](non-functional/REQ-NF-002-security.md) |

---

## 四、约束需求（摘要）

| 需求 | 内容 | 实现度 | 详文 |
|---|---|---|---|
| REQ-C-001 技术栈 | Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic / Next.js 15 + React 19 / PG16 / Redis 7 / LangBot / Docker Compose | 部分：实值与门面今天一致，但一致性本身无机检（backlog STACK-001）。**本次改掉两处失效引用**：`next` 的 spec 已由 `^15.5.24` 升到 `^15.5.28`（依赖安全补丁批，见台账 P-99） | [constraints/REQ-C-001-tech-stack.md](constraints/REQ-C-001-tech-stack.md) |
| REQ-C-002 端口分配 | 3000 禁占 / 3200 前端 / 3300 后端 / 5300 LangBot / 5433 PG / 6380 Redis | 部分：常驻用例 `test_r19_ports.py` 七条双向；端口表两行与实际不符待裁（P-78） | [constraints/REQ-C-002-port-allocation.md](constraints/REQ-C-002-port-allocation.md) |

---

## 五、需求 ↔ STEP ↔ 测试锚 三向表

内容与 `docs/任务规划V0.7.0/04-剩余可执行大纲体系.md` §4.3「需求覆盖矩阵」**同源**。
两处必须同改（改一处就是下一次漂移的种子），一致性目前靠人核对——这张表本身就是
判据 ② 「每条需求能回答有没有测试锚」的落点。

| 需求 | 承接 STEP | 判据锚（可验证的一句话） | 测试锚（具名文件；「无」者已进 backlog） |
|---|---|---|---|
| REQ-F-001 多渠道推送 | 19 + 05（+ 23/26 补直投） | 手动/事件/定时三路径均有 `notifications` 行；6 渠道投递回执可查 | `apps/api/tests/test_r19_notification_paths.py`、`apps/api/tests/test_direct_push_persists_notification.py`、`apps/api/tests/test_admin_push_persists_notification.py`、`apps/api/tests/test_push_providers.py` |
| REQ-F-002 热点与日报 | 19 + 15 | 评分回填后 Feed 分数与 `HotTopic.hot_score` 一致；日报 LLM 失败走降级 | `apps/api/tests/test_r19_hot_chain.py`、`apps/api/tests/test_hot_scorer_batch.py`、`apps/api/tests/test_w2_report.py` |
| REQ-F-003 知识库/引擎 | 13 + 19 | 未实接引擎显示的原因与「未配置 Key」可区分；builtin 端到端可用 | `apps/api/tests/test_engines_capability.py`、`apps/api/tests/test_engine_delete.py`、`apps/web/tests/engine-switcher-states.spec.tsx` |
| REQ-F-004 链接入库 | R0、02、06 | 短链二次入库 `fetch_count == 1 ∧ hitCache == True`；长链同号两篇 0 重复 | `apps/api/tests/test_d04_short_link.py`、`apps/api/tests/test_p0_asset_cache.py`、`apps/api/tests/test_kb_longlink_ingest.py`、`apps/api/tests/test_e2e_collection.py` |
| REQ-F-005 RAG 问答 | 19 + 15 | `/chat` 流式中断保留已渲染内容；SSE 断连可重连；无「假成功」 | `apps/api/tests/test_chat_sse.py`、`apps/web/tests/ask-sse.spec.ts`；`apps/web/e2e/r19-chat-stream.spec.ts` **零执行** |
| REQ-F-006 整号订阅 | 03、04、06 | READY 资产存在时 Diff=0；清单四态可回写且非法边被拒 | `apps/api/tests/test_manifest_asset_alignment.py`、`apps/api/tests/test_manifest_state_machine.py`、`apps/api/tests/test_scheduler.py` |
| REQ-F-007 SSO | 19 + 17 | backchannel-logout 有消费面或被显式 MUST NOT；登出后服务端会话失效可测 | `apps/api/tests/test_backchannel_logout.py`、`apps/api/tests/test_r19_sso_session.py`、`apps/api/tests/test_auth.py` |
| REQ-F-008 管理后台 | 14（+ 14a/14b/15） | 6 组「有 API 无 UI」端点各自有界面或显式豁免记录 | `apps/api/tests/test_admin_contract.py`、`apps/web/tests/admin-ops-panels.spec.tsx`、`apps/web/e2e/admin.spec.ts` |
| REQ-NF-001 性能 SLA | 18 + 11 | 四条 SLA 均有首次测量值；无基线不得立优化卡 | 采集切片：`apps/api/tests/perf/test_collection_perf.py`（默认 deselect，手动跑）；API / 首 Token / Feed：**无** → 待 STEP-18 |
| REQ-NF-002 安全 | 17 + 16 + 00C | CORS 条目达成方式回写需求文本；告警默认姿态明确；密钥扫描零新增命中 | `apps/api/tests/test_extra_config_crypto.py`、`apps/api/tests/test_secret_shape_gate.py`；SQL 注入面与 SameSite 断言：**无** → backlog SEC-006 |
| REQ-C-001 技术栈 | 17 | 门面文本版本与 `package.json`/`pyproject` 实值一致 | **无**（本次已把两处失效引用改回）→ backlog STACK-001 |
| REQ-C-002 端口 | 17 + 19 | 全仓无 BotHot 服务占 3000；宿主端口与 AGENTS 表一致 | `apps/api/tests/test_r19_ports.py` |

**无锚需求数 = 2**（REQ-C-001 整条、REQ-NF-001 的三条 SLA 子项），均已在
`docs/04_engineering/backlog.md` 立项，不留静默空白（卡面验收标准第 2 条）。
