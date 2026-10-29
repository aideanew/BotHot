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
| REQ-F-004 公众号链接入库 | 解析 / 标准化 / 评分分类 / 短链映射 | **已实现**（X-5，2026-10-25：八个判据锚文件实跑 283 passed / 0 failed，EVD-V21-51） | [features/REQ-F-004-article-ingest.md](features/REQ-F-004-article-ingest.md) |
| REQ-F-005 RAG 知识问答 | SSE 流式 + 多空间会话 + 可选重排 | **已实现（命题范围：`/chat` 契约五态）**（STEP-60，2026-10-29：真后端 e2e 五态全部真跑通过——run `40808385199` 五条 `✓` / `5 passed (2.8s)`，守卫步 `ok=5 skipped=0 failed=0`，原始切片与逐条读数见 `docs/06_validation/evidence/EVD-V24-60/s60_readings.md` §6.2；组件层 X-6 的 35 passed 证据不变。**未覆盖面**：`FIRST_TOKEN_SLOW_MS` 慢提示仍是 UNKNOWN；`initial` / `forbidden` 两态在 `/chat` 无 DOM 出口，见 `docs/06_validation/evidence/EVD-V22-60/s60_0_probe_readings.md`） | [features/REQ-F-005-rag-chat.md](features/REQ-F-005-rag-chat.md) |
| REQ-F-006 整号订阅与增量同步 | 订阅整号 + Manifest Diff 水位 + 锚定/滑动 + 空轮询退避 | 已实现（V0.13.0 那句「行为层未做」已过期） | [features/REQ-F-006-subscription-sync.md](features/REQ-F-006-subscription-sync.md) |
| REQ-F-007 SSO 统一认证 | OIDC + `users.sub` 锚 + HttpOnly/Lax Cookie + 角色门禁 + Backchannel Logout | 已实现（命题范围；与主平台的真实握手需白名单配合） | [features/REQ-F-007-sso.md](features/REQ-F-007-sso.md) |
| REQ-F-008 管理后台 | 空间/文档/订阅/引擎 + 渠道/任务 + 热点/日报 + Onboarding | **已实现（命题范围：四屏）**（2026-10-29 现读：`apps/web/e2e/admin.spec.ts` 在真后端档 `6 passed / 1 skipped`——7 条里 6 条 `✓`（① 游客守卫 350ms / ③ 非 admin 出口 427ms / ④ 375px 无溢出 224ms / ⑤ 五屏切换 577ms / ⑥ 告警条 417ms / ⑦ 375px 密钥表 328ms），唯一 skip 是 ② 键盘可达（real 档按 P-131），run `40808385199` 步 13，读数见 `docs/06_validation/evidence/EVD-V24-60/s60_readings.md` §6.2；P-88 那句「真后端档无读数」由此作废。**未覆盖面**：四屏 e2e 只证渲染与切屏，写路径（CRUD）仍只由 API 层用例 `apps/api/tests/test_admin_contract.py` 与 `apps/web/tests/admin-ops-panels.spec.tsx` 覆盖） | [features/REQ-F-008-admin-console.md](features/REQ-F-008-admin-console.md) |

> 本表**不重复**验收句：验收句在各子文件里，避免同一句话两处版本漂移。

---

## 三、非功能需求（摘要）

| 需求 | 内容 | 实现度 | 详文 |
|---|---|---|---|
| REQ-NF-001 性能 | API<500ms、首 Token<3s、入库<30s、Feed<100ms | **已实现（首测基线，2026-10-24）**：四条 p50/p95 全部达标（API 5–13ms / 首 Token 0.8–1ms 录制回放 / 入库 27–30ms / Feed 6–13ms），读数与局限见 `docs/03_solution/design/PERF-baseline-v1.md` | [non-functional/REQ-NF-001-performance.md](non-functional/REQ-NF-001-performance.md) |
| REQ-NF-002 安全 | Cookie / 密钥加密 / OIDC 校验 / ~~CORS 白名单~~ / SQL 注入防护 | **已实现（命题范围）**：加密与生产守卫有锚；**CORS 一条按实况改写为「经 `next.config.mjs` 同源 rewrites 达成，无 CORS 中间件」**（C-3：不重新立项）；SQL 参数化面与 Cookie `SameSite` 两类机检由 SEC-006 落地（STEP-49 收口，证据 `docs/06_validation/evidence/EVD-V21-49/`，锚 `apps/api/tests/test_sec006_sql_param_surface.py` 与 `apps/api/tests/test_auth.py`） | [non-functional/REQ-NF-002-security.md](non-functional/REQ-NF-002-security.md) |

---

## 四、约束需求（摘要）

| 需求 | 内容 | 实现度 | 详文 |
|---|---|---|---|
| REQ-C-001 技术栈 | Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic / Next.js 15 + React 19 / PG16 / Redis 7 / LangBot / Docker Compose | **已实现**：实值与门面一致性由常驻门维持——`scripts/check_docs_consistency.py` 的 STACK-001 段（STEP-50 收口，证据 `docs/06_validation/evidence/EVD-V21-50/`）把门面里的 `"key": "^x.y.z"` 声明与 `apps/web/package.json` / `apps/api/pyproject.toml` 实值比对，不一致即红。**本次改掉两处失效引用**：`next` 的 spec 已由 `^15.5.24` 升到 `^15.5.28`（依赖安全补丁批，见台账 P-99） | [constraints/REQ-C-001-tech-stack.md](constraints/REQ-C-001-tech-stack.md) |
| REQ-C-002 端口分配 | 3000 禁占 / 3200 前端 / 3300 后端 / 5300 LangBot / 5433 PG / 6380 Redis | **已实现（按 D-V21-05「文档跟实况」口径）**：端口表拆「本栈发布」（3200/3300/5300，`docker/compose.yml` 现读）与「外部提供」（PG/Redis，本栈 compose 不发布）两段，`AGENTS.md` 与子文件同源；常驻用例 `apps/api/tests/test_r19_ports.py` 七条双向（含反证：把谓词改成能吃 3000 时必红），STEP-51 S51.3 落地。原「P-78 待裁」那条前提已由 D-V21-05（`docs/03_solution/decisions/decision-log.md:146`）关闭——裁的是文档跟实况，不是改端口 | [constraints/REQ-C-002-port-allocation.md](constraints/REQ-C-002-port-allocation.md) |

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
| REQ-F-005 RAG 问答 | 19 + 15 | `/chat` 流式中断保留已渲染内容；SSE 断连可重连；无「假成功」 | `apps/api/tests/test_chat_sse.py`、`apps/web/tests/ask-sse.spec.ts`；`apps/web/e2e/r19-chat-stream.spec.ts`（真后端档五态，run `40808385199` 步 11 `5 passed` + 步 12 守卫 `ok=5 skipped=0 failed=0`，读数见 `docs/06_validation/evidence/EVD-V24-60/s60_readings.md` §6.2——原「零执行」已作废） |
| REQ-F-006 整号订阅 | 03、04、06 | READY 资产存在时 Diff=0；清单四态可回写且非法边被拒 | `apps/api/tests/test_manifest_asset_alignment.py`、`apps/api/tests/test_manifest_state_machine.py`、`apps/api/tests/test_scheduler.py` |
| REQ-F-007 SSO | 19 + 17 | backchannel-logout 有消费面或被显式 MUST NOT；登出后服务端会话失效可测 | `apps/api/tests/test_backchannel_logout.py`、`apps/api/tests/test_r19_sso_session.py`、`apps/api/tests/test_auth.py` |
| REQ-F-008 管理后台 | 14（+ 14a/14b/15） | 6 组「有 API 无 UI」端点各自有界面或显式豁免记录 | `apps/api/tests/test_admin_contract.py`、`apps/web/tests/admin-ops-panels.spec.tsx`、`apps/web/e2e/admin.spec.ts`（真后端档 `6 passed / 1 skipped`，② 键盘可达按 P-131 跳过；run `40808385199` 步 13） |
| REQ-NF-001 性能 SLA | 18 + 11 | 四条 SLA 均有首次测量值；无基线不得立优化卡 | 采集切片：`apps/api/tests/perf/test_collection_perf.py`（默认 deselect，手动跑）；API / 首 Token / Feed：**无** → 待 STEP-18 |
| REQ-NF-002 安全 | 17 + 16 + 00C | CORS 条目达成方式回写需求文本；告警默认姿态明确；密钥扫描零新增命中 | `apps/api/tests/test_extra_config_crypto.py`、`apps/api/tests/test_secret_shape_gate.py`；SQL 参数化面 `apps/api/tests/test_sec006_sql_param_surface.py`、SameSite `apps/api/tests/test_auth.py`（SEC-006，STEP-49 收口，`docs/06_validation/evidence/EVD-V21-49/`） |
| REQ-C-001 技术栈 | 17 | 门面文本版本与 `package.json`/`pyproject` 实值一致 | `scripts/check_docs_consistency.py` 的 STACK-001 段（常驻门：门面 `"key": "^x.y.z"` 与实值比对，不一致即红；STEP-50 收口，`docs/06_validation/evidence/EVD-V21-50/`——原「无 → backlog STACK-001」已作废） |
| REQ-C-002 端口 | 17 + 19 | 全仓无 BotHot 服务占 3000；宿主端口与 AGENTS 表一致 | `apps/api/tests/test_r19_ports.py` |

**无锚需求数 = 1**（只剩 REQ-NF-001 的三条 SLA 子项；REQ-C-001 已由 STACK-001 门托住，2026-10-29 STEP-62 现读改数）。它已在
`docs/04_engineering/backlog.md` 立项，不留静默空白（卡面验收标准第 2 条）。
