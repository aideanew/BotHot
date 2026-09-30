---
id: BACKLOG
type: backlog
title: BotHot 待办清单
status: active
owner: product
created: 2026-09-29
updated: 2026-09-30
---

# BotHot 待办清单

> 状态标记：✅ 已完成 | 🔧 部分完成 | ⬜ 未开始
>
> **回填口径（WD，2026-09-30）**：本清单每一项的状态均以 `main @ 2fa95f0` 的**代码实证**为准，
> 逐条附 `文件:行号`。铁律：**禁止把未实现写成已完成，也禁止把已实现留作未开始**——
> 前者是本仓库的历史病史，后者同样制造假象（把已完成项当待办重复排期）。

## ✅ 已完成（BotHot 新增能力）

### PUSH-001~006：六种渠道 PushProvider ✅
- **状态**：全部实现真实投递（`backend/app/providers/push/`，注册表见 `backend/app/providers/push/__init__.py:24`）
- **飞书**：交互式卡片消息 + HMAC-SHA256 加签 ✅
- **钉钉**：Markdown 消息 + HMAC-SHA256 加签 ✅
- **企业微信**：Markdown 消息 ✅
- **通用 Webhook**：POST JSON + HTTP 2xx 校验 ✅
- **微信 ClawBot**：Bearer token 鉴权 + `/api/send` 调用 ✅（需部署 ClawBot 服务）
- **站内通知**：Redis pub/sub → `bothot:notifications:{user_id}` ✅（**仅投递侧**）
  - 证据：`backend/app/providers/push/web.py:16`（频道前缀）、`:50`（`r.publish`）
  - 缺口：**前端订阅侧未实现** —— `main @ 2fa95f0` 下 `frontend/**` grep
    `WebSocket|bothot:notifications` **零命中**，通知发进无人接收的频道（登记见 FE-005）

### ARTSRC-001~004：四平台文章来源 Provider ✅
- **状态**：4 个第三方 API 平台已接入（`providers/article_sources/` 包）
- **Dajiala 极致了**：post_condition 发现 + article_html 详情兜底（¥0.04~0.14/次）✅ 活体实测
- **JustOneAPI**：get-account-history-articles/v2 发现 + get-article-detail/v1 详情兜底（¥0.15~0.40/次）✅ 活体实测
- **TikHub**：fetch_account_articles 发现 + fetch_search 搜索 ✅ 契约级（OpenAPI 读取 + 鉴权实测，付费端点 402 需充值）
- **Wellbyte 数井**：article_v1 搜索 + account_history_v2 发现 ✅ 活体实测（detail_v2 三连 422 禁用）
- **发现注册**：4 平台已注册到 `discovery/registry.py`，与 RedFox 共存，后台 `discovery_channels` 白名单可控
- **详情兜底**：`ArticleDetailFallbackCoordinator` 按成本排序（Dajiala ¥0.04 → JustOneAPI ¥0.15），总开关 `ARTICLE_DETAIL_FALLBACK_ENABLED`
- **item_show_type 检测**：`parse_item_show_type` / `is_gallery_type` 已加入 source_resolver，图集类(=8)不触发付费兜底
- **测试证据**：`docs/06_validation/evidence/channeltest-20260929/`

### PUSH-007：PushScheduler 定时调度 ✅
- **状态**：已实现，在 backend 进程内运行（FastAPI lifespan 启动/停止，`backend/app/main.py:247`）
- **调度间隔**：60s
- **Cron 解析**：**croniter 完整 5 段式 + 三种简写兼容**（`HH:MM` / `*/N` / 纯数字分钟 ↔ 标准式互译）
  —— `backend/app/services/cron_expr.py`（91 行）；依赖 `croniter>=0.19`（`backend/pyproject.toml:15`）
- **并发安全**：到期任务 `FOR UPDATE SKIP LOCKED` 短锁领取（`backend/app/services/push_scheduler.py:85`）
- **测试**：`backend/tests/test_push_providers.py`（20 例，覆盖 `cron_expr` 全分支）

### PUSH-008：事件触发推送 ✅
- **实现**：PG outbox 表 `push_events` —— `backend/app/models/bothot_entities.py:243`（表名 `:250`）
- **迁移**：`backend/alembic/versions/ab1004w3a_push_events.py`
- **生产侧**（worker 进程）：文章入库 / 聚簇完成 / 日报生成 → 事件落库（`backend/app/services/push_events.py`）
- **消费侧**（backend 进程）：`push_scheduler` 扫描未消费事件，复用 `_execute_task` 投递（at-most-once）
- **模板变量**：`{space_name}/{doc_title}/{hot_topic}/{topic_count}` —— `backend/app/services/push_template.py`
- **测试**：`backend/tests/test_w3_push_scheduler.py`（10 例）
- **注**：跨进程投递**不能**用进程内事件总线（ingest 在 worker 进程、调度器在 backend 进程），
  outbox 表是本约束下的正确拓扑；代价是事件延迟下限 = 扫描间隔 60s。

### TECH-001：迁移 push.py 到新 Provider 包 ✅
- 旧 `providers/push_port.py` **已删除**（`git cat-file -e HEAD:backend/app/providers/push_port.py` → not exist）
- `backend/app/services/push.py:20` 与 `backend/app/api/v1/admin.py:64` 均已切到 `app.providers.push`
- 双头语义收敛：不再存在「占位 `delivered=False`」与真实投递并存

### TECH-002：PushScheduler 完整 Cron 支持 ✅
- 见 PUSH-007：`croniter` 已引入，统一收口于 `services/cron_expr.py`，存量三种简写格式行为不回归

### HOT-001：热点聚簇算法 ✅
- **实现**：`backend/app/services/hot_cluster.py`（270 行）—— 标题字 bigram TF-IDF + 单链接凝聚聚类（τ 可调）
- **执行**：Job type=`hot_cluster` 走既有 PG Job 队列（白拿 SKIP LOCKED / 重试 / 心跳）
- **触发**：手动 API + 每日定时入队（`backend/app/services/scheduler.py:298-334`）
- **测试**：`backend/tests/test_w2_cluster.py`（3 例）

### HOT-002：热度评分 ✅
- **实现**：`backend/app/services/hot_scorer.py`（139 行）—— 48h 独立来源加权 + 24h 半衰时间衰减 + 状态机
- **字段**：`backend/app/models/bothot_entities.py:141 hot_score`（已建索引）
- **测试**：`backend/tests/test_w2_scorer.py`（7 例）

### HOT-003：Feed 流 ✅
- **读侧**：`backend/app/api/v1/hot.py`（热点列表/详情、Feed 流，支持类型/分类筛选 + 排序）
- **生产侧**：`backend/app/services/feed_service.py`（276 行）—— 三类生产者：
  ① 文章入库 INDEXED 落点 ② 聚簇副作用 ③ 日报副作用
- **唯一性**：`(item_type, ref_id)` 唯一约束 —— 迁移 `ab1004w2a_feed_unique.py`（upsert 语义基础）
- **模型**：`backend/app/models/bothot_entities.py:206 FeedItem`

### HOT-004：每日日报生成 ✅
- **实现**：`backend/app/services/llm_summary.py`（74 行）—— LLM 中文摘要，**失败降级**为中心文章首段截断
  （日报不因 LLM 故障而缺失）
- **自动定时**：每日 06:30（本地时区）入队 `daily_report`（生成**前一日**日报）
  —— `backend/app/services/scheduler.py:62-63`、`:298-334`
- **幂等**：`uq_daily_report_date` 唯一约束
- **模型**：`backend/app/models/bothot_entities.py:176 DailyReport`

### 渠道管理 API ✅
- `GET/POST/PUT/DELETE /api/v1/bots` — 渠道 CRUD
- `POST /api/v1/bots/{id}/test` — 测试推送
- `GET /api/v1/bots/{id}/logs` — 推送日志
- `POST/GET/PUT/DELETE /api/v1/bots/tasks` — 推送任务管理（**PUT 为 W1 新增**，支持编辑/暂停恢复，`backend/app/api/v1/bots.py:482`）
- `POST /api/v1/bots/tasks/{id}/run` — 手动触发

### FE-001：Bot 渠道管理页面 ✅
- `frontend/app/bots/page.tsx`：渠道列表 + 创建/编辑 + 测试推送 + 日志
- 「待完善：推送任务管理 UI（Cron 编辑器）」已在 FE-002 落地

### FE-002：推送任务管理页面 ✅
- `frontend/app/bots/page.tsx:50`：双 Tab（channels / tasks）；`:31` 引入 `PushTasksTab`
- 组件：`frontend/components/PushTasksTab.tsx`、`frontend/components/CronEditor.tsx`
- 能力：列表/创建/编辑/暂停恢复/删除/立即执行/日志

### FE-003：热点 Feed 页面 ✅
- `frontend/app/hot/page.tsx`：类型 + 状态过滤（`:42`、`:109`）、聚簇触发按钮（`:124 triggerCluster`）、
  热度可视化、状态徽章点击过滤

### FE-004：每日日报页面 ✅
- `frontend/app/hot/daily/page.tsx`：`react-markdown` 真渲染（`:13`）、翻页（`:28`、`:155-161`）

## 🔴 高优先级

### FE-005：站内通知前端订阅侧 ✅
- **状态**：已实现 SSE 订阅 + 未读数徽标
- **后端**：`backend/app/api/v1/system.py:262` — SSE 端点 `/notifications`
- **前端**：`frontend/components/NotificationBell.tsx:12` — 订阅 + 徽标组件
- **验收**：站内通知在浏览器中实际可见、可标记已读

### PUSH-009：推送失败重试机制 ✅
- **状态**：已实现指数退避 + 最大重试次数 + 死信终态
- **实现**：`backend/app/services/push_scheduler.py:41` — MAX_PUSH_RETRIES + 指数退避（重试簿记在 _execute_task）
- **数据模型**：`backend/app/models/bothot_entities.py:91` — `retry_count` + `next_retry_at` 字段
- **验收**：失败任务自动重试，超过最大次数后进入死信

## 🟡 中优先级

### TEST-003：Docker Compose 冒烟测试 🔧
- **已有**：`scripts/smoke.sh`（W5）—— 轮询 `/api/v1/system/health`（信封 code==0）
  + 校验 `process_heartbeats` 中 scheduler/worker 心跳新鲜度
- **WD 变更**：新增 CI `compose-smoke` job（`.github/workflows/ci.yml`）—— build backend 镜像 →
  起核心服务 → 跑 smoke.sh；此前该脚本**从未被任何 CI 消费**
- **待完善**：**首次 Actions 运行验证**（langbot 镜像拉取耗时、runner 端口占用、心跳首次落库时延）

### MIG-003：packages/contracts/ 共享契约提取 🔧
- **已有**（W5）：骨架 + 三类通用类型冻结 —— `PageResult<T>` / `ApiResponse<T>` / `ApiErrorCode`
- **缺口**：① 业务域 DTO 未提取；② **前端尚未消费** —— `@bothot/contracts` 在 `frontend/**` 引用数 = 0
  （契约冻结了却无人使用，漂移面仍在）

### TEST-001：后端单元测试补全 🔧
- **现状（提交态实证，`main @ 2fa95f0`，全仓 707 个 `def test_`）**：
  - 推送域：`test_push_providers.py`(20) / `test_r11_push.py`(11) / `test_w1_push_domain.py`(28) / `test_w3_push_scheduler.py`(10)
  - 调度与心跳：`test_scheduler.py`(22) / `test_process_heartbeat.py`(17)
  - 热点域：`test_w2_cluster.py`(3) / `test_w2_scorer.py`(7)
- **缺口**：① 聚簇/评分用例偏薄（3 + 7 例），无「千篇量级」性能用例；
  ② outbox 消费侧无端到端用例（入队→扫描→投递→消费标记）
- **CI 侧**：连库用例此前被**静默 skip**（`ci.yml` 无 postgres service），W5 已修复并加 skip 门禁；
  WD 复核实测 `796 passed, 4 skipped`，其中 PG 不可达类 skip = 0

### TEST-002：Playwright e2e 测试 🔧
- **现状**：`frontend/e2e/trunk.spec.ts`（mock 主干 9 条路径）+ `frontend/e2e/real-backend.spec.ts`（4 条）
- **WD 变更**：
  - mock 套件**已入 CI**（`frontend` job，PORT=3456，**阻塞门禁**）
  - real-backend 由无条件 `test.skip(true, …)`（**死断言**，套件永不可执行）改为**环境闸**
    `E2E_REAL_BACKEND=1`，并配 `continue-on-error: true` + 仓库变量闸
- **缺口**：real-backend 三项前置未落地 —— ① Compose 栈运行 ② 主平台 OIDC 白名单 ③ 真实文章 URL
- **端口**：3200（禁止 3333）

### HOT-005：聚簇算法升级（嵌入向量）⬜
- **现状**：TF-IDF 字 bigram（日增百~千篇量级下够用）
- **升级路径**：`ContentAsset` 加 embedding 列 + pgvector；`embedding.py` 目前**生产零调用方**（仅测试引用）
- **定位**：**显式排除项**（非遗漏），单独立项，不阻塞当前阶段

### TECH-003：RagflowAdapter 实接 ⬜
- **现状**：`backend/app/providers/engine_port.py` 中 RagflowAdapter 六方法抛 `NotImplementedError`
  （`:114-134`，ADR-0004 P2）；SaaS 适配器同类（`:161-181`，P3）
- **说明**：`:210` 的注册表**已显式排除骨架位**，不可路由 → 不产生伪 `available`
  —— 这是**诚实门禁，不是缺陷**
- **已知副作用**：`backend/app/api/v1/engines.py:158` 记载 `delete_space` 走 adapter 分支会
  抛 `NotImplementedError` 并整体回滚（空间删不掉）；修法与排期见协调请求

## 🟢 低优先级

### MIG-001：后端 apps/api/ 目录迁移 ⬜
- **参考**：`project-structure-design.md` 阶段化迁移策略
- **状态**：未开始（当前仍为 `backend/`；`apps/api/` 为 183 个 `.gitkeep` 空壳）

### MIG-002：前端 apps/web/ 目录迁移 ⬜
- **参考**：`project-structure-design.md` 阶段化迁移策略
- **状态**：未开始（当前仍为 `frontend/`）

### DOC-001：README 更新 🔧
- **已有**：功能说明 + 快速开始 + 部署指南
- **WD 变更**：补「部署指南」小节（compose 环境变量清单，含 `PUSH_SECRET_MASTER_KEY` /
  `ENGINE_KEY_MASTER_KEY`；端口纪律表）；并修正 W1-W5 合并后的状态漂移
  （原文「事件触发未实现」「热点生产管道缺失」「聚簇为占位响应」均已过期）
- **待完善**：v1.0 发布前全量复核

### DOC-002：CHANGELOG.md 编写 ✅
- **W5**：建初版（Keep-a-Changelog 格式，全部条目归入 `Unreleased`）
- **WD 变更**：切分 `v0.4` / `v0.5` 版本段（均标注 2026-09-30），保留空的 `Unreleased` 承接增量
