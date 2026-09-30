---
id: TASK-PLAN-v0.6
type: task-plan
title: BotHot 全局审计与剩余任务方案大纲（v0.6）
status: active
owner: engineering
created: 2026-09-30
updated: 2026-09-30
baseline_commit: 2fa95f0
supersedes: docs/09_archive/superseded/当前任务规划.md（W1–W5 合并前口径，2026-09-30 由 WD 归档）
---

# BotHot 全局审计与剩余任务方案大纲（v0.6）

> ⚠️ **覆盖状态头注（WD，2026-09-30 补）**
>
> 本文件成文于 W1–W5 集成**之后**、**WA–WD 并行任务之前**。因此：
> - **部分条目已被 WA–WB 等并行交付覆盖**。归档时点在工作区可见的未提交改动（**未合并，不作已交付凭据**）
>   已触及若干本文件条目所在的文件，例如 `backend/app/db.py`（对应 R1.4 连接池）、
>   `backend/app/providers/engine_port.py` / `api/v1/engines.py` / `api/v1/admin.py`（对应 R2.4 引擎端口）、
>   `frontend/components/NotificationBell.tsx` / `frontend/lib/api/notifications.ts`（对应站内通知订阅侧）。
> - **逐条状态以代码实证与 `docs/04_engineering/backlog.md` 为准**，本文件**不逐条追改状态**——
>   它的价值在「证据链 + 编号化方案大纲」的结构，而非状态快照（状态快照会随即过期，恰是本仓库病史）。
> - 引用本文件做排期前，**先对 `backlog.md` 与代码复核**该条是否仍成立。

> **取证基线**：`main @ 2fa95f0`（W1–W5 五路并行交付已全部合并）。
> **唯一标准**：与代码实证一致。每条要点均带 `文件:行` 证据链，可复现。
> **编号规则**：`R<域>.<阶段>.<任务>`，其下 a/b/c 为**原子步骤**（每步可独立提交、独立验收）。
> **优先级**：P0（阻塞验收/可靠性）> P1（性能/安全/工程性）> P2（架构/迁移）。

---

## 第一节 证据核验：W1–W5 交付裁定

| 工作流 | 声称 | 实证证据 | 裁定 |
|---|---|---|---|
| **W1** `0879882` | cron 全生命周期修复 + 渠道密钥 AES-256-GCM + 旧分叉收编 | `services/cron_expr.py`（2559B）、`core/secret_crypto.py`（3998B）均存在；`providers/push_port.py` **已删除**；`services/push.py:20` 已改 import `app.providers.push.make_push_provider`；`admin.py:64` import `app.providers.push.registered_channels`；`bots.py:481` 新增 `PUT /tasks/{task_id}`；`pyproject.toml:15 croniter>=0.19` | ✅ 属实 |
| **W2** `25181c1` | 热点域落地（聚簇/评分/Feed 生产者/LLM 日报） | `services/hot_cluster.py`、`hot_scorer.py`、`feed_service.py`、`llm_summary.py` 四文件均存在 | ✅ 属实 |
| **W3** `90618b7` | 调度器并发安全 + 事件触发 outbox | `models/bothot_entities.py:243 class PushEvent` / `:250 __tablename__="push_events"`；`services/push_scheduler.py:85 .with_for_update(skip_locked=True)` | ✅ 属实 |
| **W4** `d2678d7` | 前端推送任务 Tab + 热点中心增强 | `frontend/app/bots/page.tsx:50 activeTab`（channels/tasks）、`:31 import PushTasksTab` | ✅ 属实 |
| **W5** | CI 真实化 + 文档修复 + 契约冻结 | `.github/workflows/ci.yml` 三 job（backend:9 / frontend:125 / compose:218），`:61 alembic upgrade head`；`celery` 已从 `pyproject.toml` 移除 | ✅ 属实 |

**结论**：`当前任务规划.md`（W1–W5 合并前撰写）的 M1–M5 **约 70% 已交付**；该文档口径已过时，须归档（见 R7.4）。

---

## 第二节 辩证裁定：历史文档 vs 最新真实代码

### 2.1 W1–W5 合并**新产生**的文档漂移（backlog 未随合并同步）

| 位置 | 文档现状 | 代码实证 | 裁定 |
|---|---|---|---|
| `backlog.md:73` | HOT-001 热点聚簇 ⬜ 未开始 | `services/hot_cluster.py` 已存在 | ❌ 漂移 |
| `backlog.md:79` | HOT-002 热度评分 ⬜ 未开始 | `services/hot_scorer.py` 已存在 | ❌ 漂移 |
| `backlog.md:83-87` | HOT-003「修复中：并行任务 W2 正在补…」 | W2 已合并 | ❌ 措辞过期 |
| `backlog.md:89-93` | HOT-004「修复中」 | W2 已合并 | ❌ 措辞过期 |
| `backlog.md:56` | PUSH-008 事件触发 ⬜ | `push_events` 表 + 消费侧已落 | ❌ 漂移 |
| `backlog.md:66-69` | TECH-002「仅支持 HH:MM 和 */N」 | croniter 已引入、`cron_expr.py` 已建 | ❌ 漂移 |
| `backlog.md:61-64` | TECH-001「仍 import 旧 push_port」 | `push_port.py` 已删 | ❌ 漂移 |
| `backlog.md:99-101` | FE-002 推送任务页 ⬜ | W4 已建 Tab | ❌ 漂移 |
| `roadmap.md:14` | 「当前阶段：v0.3」 | W1–W5 已交付 v0.4/v0.5 能力 | ❌ 阶段标签滞后 |

### 2.2 被"过度诊断"的项（**不是缺陷，不要修**）——辩证要点

| 现象 | 初判 | 辩证裁定 |
|---|---|---|
| 全仓 `CORS` 零命中（9 处注册表零 `CORSMiddleware`） | "缺 CORS 是缺陷" | ❌ **反向成立**：`frontend/next.config.mjs:4-10 rewrites` 把浏览器 `/api/v1/*` 代理到 `BACKEND_ORIGIN`，浏览器**从不跨域直连后端** → 无 CORS 是**正确设计**。若贸然加 CORS 反而扩大攻击面。 |
| 全仓 `relationship()`/`selectinload` 零命中 | "缺 ORM 加载优化" | ⚠️ **自觉选择**：代码库用显式 JOIN 手写 SQL，规避懒加载意外（N+1 的另一种来源）。真问题不是"没有 relationship"，而是**没有 eager-load 纪律**——一旦引入关系就会退化（见 R1.3）。 |
| `engine_port.py` 12 处 `NotImplementedError` | "适配器残缺是缺陷" | ❌ **诚实门禁**：`:210` 注册表显式将骨架位排除出路由（"杜绝伪 available"）。这是**正面实践**。真正待办是 `engines.py:158` 记载的 `delete_space` 走 adapter 分支会整体回滚（见 R2.4）。 |
| `BotBinding` 死表 | "遗漏" | ⚠️ **已登记开放项**：`admin.py:16` 自认"登记为独立开放项"。需**产品拍板**接线或删表（R2.5）。 |

---

## 第三节 真实剩余缺口清单（每条带证据链）

### 3.1 数据层与性能

| # | 缺口 | 证据 | 影响 | 级别 |
|---|---|---|---|---|
| A1 | **19/23 列表端点无分页约束**（仅 4 个 PAGED：`bots.py:210/359/455`、`hot.py:52/194`）；其中 **15 个是真实集合端点**：`admin.py:156/175/208/254/284/436/452/605`、`spaces.py:59/115/191`、`subscriptions.py:72/175/246`、`engines.py:129` | AST 扫描函数签名（见附录 A） | 随数据规模线性膨胀，单请求全表返回、内存放大 | P0 |
| A2 | **4 个外键列无索引** | `models/bothot_entities.py:78`（PushTask.space_id）、`:87`（PushTask.created_by）、`:107`（PushLog.push_task_id）、`:138`（HotTopic.center_asset_id）；对照 `:66/:104/:161/:164` 均有 `index=True` | JOIN / 级联删除 / 按空间过滤全表扫 | P0 |
| A3 | 无 eager-load 纪律（`relationship`/`selectinload`/`joinedload` 全仓 0 命中） | grep 计数 = 0 | 关联取值为逐行往返的隐患面 | P1 |
| A4 | 连接池偏薄且无回收 | `app/db.py:37 pool_size=5, max_overflow=5`（单进程上限 10）；仅有 `pool_pre_ping`，**无 `pool_recycle`** | 三进程（backend/scheduler/worker）+ migrate 突发；长连接受 PG/idle 断连影响 | P1 |
| A5 | 无读缓存层 | Redis 已在栈内，仅用于 station 通知 pub/sub；无 TTL 缓存 | 高频只读端点（枚举/来源/渠道）反复回源 | P2 |

### 3.2 后端健壮性与资源治理

| # | 缺口 | 证据 | 影响 | 级别 |
|---|---|---|---|---|
| B1 | **无入站限流** | `slowapi`/`RateLimit` 零命中；仅有 `RateLimitedUpstreamError`（`core/errors.py:116`）处理**上游** 4004 限频 | 自身 API 无防护，登录/抓取/聚簇触发端点可被打爆 | P0 |
| B2 | 无请求体大小上限 | 全仓无 body-size / Content-Length 校验 | 大 payload 内存放大 | P1 |
| B3 | 上游调用无进程内并发上限 | `asyncio.Semaphore` 零命中 | RedFox/JustOneAPI/TikHub/Wellbyte/LLM 并发不可控 | P1 |
| B4 | 引擎适配器缺口 | `providers/engine_port.py:65/114/118/122/126/130/134/161/165/169/173/177/181`（Ragflow P2 + SaaS P3）；`engines.py:158` 记载 `delete_space` 走 adapter 分支抛 NotImplementedError 整体回滚 | Ragflow 引擎下空间无法删除 | P1 |
| B5 | 死表待决策 | `models/entities.py:223 class BotBinding`，`admin.py:16` 自认开放项 | 认知负担 / 潜在误用 | P2 |

### 3.3 前端

| # | 缺口 | 证据 | 影响 | 级别 |
|---|---|---|---|---|
| C1 | **契约未被消费** | `@bothot/contracts` 在 `frontend/**` 引用数 = **0** | W5 冻结的契约形同虚设，前后端类型漂移面仍在 | P1 |
| C2 | 无图片优化 / 无代码分割 | `next/image` = 0、`next/dynamic` = 0（15 业务页 + 3 fallback 全静态引入） | 首屏体积与 LCP 未优化 | P1 |
| C3 | e2e 未入 CI | `ci.yml` 三 job 无 e2e；`e2e/real-backend.spec.ts` 5 处 test/skip、`trunk.spec.ts` 9 处 | 真后端链路无自动回归 | P1 |
| C4 | 无语义错误边界 | 缺 `error.tsx`/`loading.tsx`/`not-found.tsx` 全套 | 运行期错误直落白屏 | P2 |

### 3.4 基础设施 / 运维 / 安全

| # | 缺口 | 证据 | 影响 | 级别 |
|---|---|---|---|---|
| D1 | **compose 无资源与日志治理** | `docker/compose.yml` 中 `limits:`/`logging:`/`read_only:`/`cap_drop:` 计数 = **0**（9 服务：postgres/redis/langbot_plugin_runtime/langbot/backend/migrate/scheduler/worker/frontend） | 无资源隔离（OOM 连带）、无日志轮转（磁盘可撑爆）、容器以 root 运行 | P0 |
| D2 | Dockerfile 单阶段 / root / 无 HEALTHCHECK | `backend/Dockerfile:5 FROM ${BASE_IMAGE}`、`frontend/Dockerfile:7 FROM ${BASE_IMAGE}`，两者均无 `USER`/`HEALTHCHECK` | 镜像臃肿、权限过大、编排无法判活 | P1 |
| D3 | **版本锚 5 方漂移** | `.nvmrc`=24.21.0 vs `frontend/Dockerfile:6 node:20-alpine` vs `frontend/package.json:7 engines node>=22.12.0` vs `:5 packageManager pnpm@9.15.9` vs `Dockerfile:31 prepare pnpm@10.34.5` | 构建不可复现，本地/CI/容器行为分歧 | P1 |
| D4 | CI 门禁缺 4 类 | `ci.yml` 无 e2e job、无 docker build、无覆盖率门禁、无依赖/镜像漏洞扫描 | 回归与供应链风险无闸 | P1 |
| D5 | `guard-ports` 守卫失效（fail-open） | `Makefile:126-128`：跨行 `\` 续行后 `if [ $$? -eq 0 ]` 取的是**第二条** grep（frontend）退出码 → 后端独有 `3333` 命中时不报错 | 端口纪律守卫形同虚设 | P1 |
| D6 | **可观测性近乎空白** | `pyproject.toml:18 structlog>=24.4.0` 已装，但 `backend/app` 使用数 = **0**；`prometheus`/`opentelemetry`/`sentry` 全 = 0 | 生产问题不可定位、无时延/错误率基线 | P0 |
| D7 | 无安全响应头 | 全仓无 HSTS/CSP/X-Frame-Options/Referrer-Policy | 浏览器侧攻击面 | P2 |
| D8 | production guard 覆盖窄 | `production_guard_violations()` 仅在 `app_env == "production"` 精确匹配时触发 | 非标准 env 名可绕过危险配置断言 | P1 |

### 3.5 架构与文档

| # | 缺口 | 证据 | 影响 | 级别 |
|---|---|---|---|---|
| E1 | backlog/roadmap 二次漂移 | 见第二节 2.1 表（9 处） | 文档失去可信度，重演"虚标完成" | P1 |
| E2 | 契约仅三个通用类型 | `packages/contracts/src/common/*`；业务域 DTO 未提取（`backlog.md:122` 亦确认） | 前后端域级类型仍各写各的 | P2 |
| E3 | `apps/` 183 个 `.gitkeep` 空壳 | `find apps -name .gitkeep | wc -l` = 183；MIG-001/002/003 未动 | 目录迁移未启动 | P2 |
| E4 | 根目录 `当前任务规划.md` 未跟踪且已过时 | `git status` 显示 `?? 当前任务规划.md` | 将成为下一次漂移源 | P1 |

---

## 第四节 剩余任务方案大纲（三层以上 · 最小原子化 · 带序号）

### R1 数据层性能与正确性（P0）

#### R1.1 外键索引补齐

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R1.1.1** 四列加索引并迁移 | a) `bothot_entities.py:78/87/107/138` 对应列加 `index=True`；b) 新迁移 `ab1004r1a_fk_indexes.py`（`down_revision="ab1004w3a"`），`op.create_index` ×4；c) 新测试 `test_indexes.py` 断言 `pg_indexes` 含四索引；d) `EXPLAIN` 抽验「按 space_id 过滤」走索引 | — |

#### R1.2 列表端点分页收口

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R1.2.1** 统一分页依赖 | a) `api/deps.py` 增 `page_query` 依赖（`page`/`page_size`，默认 20、上限 100）；b) 返回体统一为 `PageResult{items,total,page,page_size}`（对齐 `packages/contracts/src/common/pagination.ts`）；c) 枚举类端点（`bots.py:162 list_channel_types`、`spaces.py:216 list_doc_categories`）白名单豁免 | — |
| **R1.2.2** admin 域接入 | a) `admin.py:156/175/208/254/284/436/452/605` 八个 list 端点接入 `page_query` 并返回 total；b) 新增 `?page_size=` 覆盖测试；c) 保持未传参时默认分页（不回退全量） | R1.2.1 |
| **R1.2.3** 用户侧域接入 | a) `spaces.py:59/115/191`、`subscriptions.py:72/175/246`、`engines.py:129` 接入；b) 前端 `lib/api/*` 相应对接（与 R5.1 合流） | R1.2.1 |
| **R1.2.4** 大表计数优化 | a) `total` 用窗口函数或 `count() over()` 单查，避免二次全表 count；b) 千行级 `EXPLAIN ANALYZE` 基线记录 | R1.2.2 |

#### R1.3 加载策略纪律

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R1.3.1** N+1 审计与固化 | a) 审计 23 个列表查询的关联取值路径，标注「显式 JOIN」或「关系加载」；b) 若引入 `relationship()`，同处强制 `selectinload`/`joinedload`；c) 将「显式 JOIN 纪律」写入 `conventions.md`，防止未来退化 | — |

#### R1.4 连接池与超时治理

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R1.4.1** 池参数化 | a) `db.py:37` 增 `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`/`DB_POOL_RECYCLE`（默认 1800s）；b) 启动断言：`进程数 × (pool+overflow) ≤ PG max_connections`；c) 测试连接回收 | — |

#### R1.5 读缓存

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R1.5.1** TTL 缓存 | a) `core/cache.py`：`get_or_set(key, ttl, loader)`（Redis）；b) 接入低频变更端点（`bots.py:162`、admin 来源/发现渠道）；c) 写路径显式失效 | R1.1.1 |

---

### R2 后端健壮性与资源治理（P0/P1）

#### R2.1 入站限流

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R2.1.1** 引入限流中间件 | a) 依赖（`slowapi` 或自研 ASGI）+ 按 `IP` 与 `user.sub` 双维度；b) 敏感端点独立配额（`auth` 登录、`extract`、`hot` 聚簇触发、`tasks/{id}/run`）；c) `ApiErrorCode` 增 `RATE_LIMITED` 并统一 429 契约；d) 限流命中测试 | — |

#### R2.2 请求体上限

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R2.2.1** body-size 守卫 | a) 中间件校验 `Content-Length` + 流式截断；b) 超限 413（错误码统一）；c) 测试 | — |

#### R2.3 上游并发与时限统一

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R2.3.1** provider 级并发配额 | a) 每 provider 一个 `asyncio.Semaphore(N)`（RedFox/JustOneAPI/TikHub/Wellbyte/LLM 各自可配）；b) 统一 connect/read 超时 + 指数退避（复用 `job_worker` 既有重试）；c) 命中 `RateLimitedUpstreamError`（4004）时开启全局退避窗口；d) 退避与并发测试 | — |

#### R2.4 引擎适配器缺口

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R2.4.1** 空间删除兜底 | a) `engines.py:158`：adapter 未实接时 `delete_space` 返回可读 409（而非 500 + 整体回滚）；b) 新增「引擎能力矩阵」端点暴露 `implemented` 状态；c) 测试 | — |
| **R2.4.2** RagflowAdapter 实接 | a) 按 ADR-0004 P2 排期（需产品拍板优先级）；b) 六方法逐个实现 + 契约测试 | R2.4.1 |

#### R2.5 死表处置

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R2.5.1** BotBinding 决策 | a) **产品拍板**：接线（用途？）或删表；b) 若删 → Alembic `drop_table` + 清 `models/__init__.py` 导出 + 更新 `admin.py:16` 注释；c) 若留 → 写清用途与不接线原因 | 产品决策 |

---

### R3 可观测性与运维（P0）

#### R3.1 结构化日志落地

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R3.1.1** structlog 配置 | a) `core/logging.py`：prod JSON / dev console 双模式；b) `request_id` 注入中间件（与 `ApiResponse.requestId` 同源）；c) `main.py` lifespan 初始化 | — |
| **R3.1.2** 分层替换 | a) 批次一 `core/`；b) 批次二 `services/`；c) 批次三 `api/`；d) 验收：`grep -rn structlog backend/app | wc -l` 达 ≥50 且无残留裸 `logging` | R3.1.1 |

#### R3.2 指标暴露

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R3.2.1** Prometheus `/metrics` | a) HTTP 时延/状态码/在途请求；b) DB 连接池用量；c) 队列深度（`jobs` 按 status 计数）；d) 业务指标：推送成功率（按渠道）、聚簇耗时、日报结果；e) `prometheus.yml` + 最小看板 | R3.1.1 |

#### R3.3 健康与就绪分离

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R3.3.1** `/live` + `/ready` | a) `/live` 纯存活；b) `/ready` 检查 PG + Redis + **alembic head == DB 版本**；c) 版本不一致返回 503；d) Dockerfile `HEALTHCHECK` 指向它（合流 R4.2） | R1.4.1 |

#### R3.4 告警

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R3.4.1** 三类告警 | a) 进程心跳缺失（复用 `process_heartbeats`）；b) 队列积压超阈；c) 推送连续失败；d) 至少落地一条通道（飞书/钉钉，已具备 provider） | R3.2.1 |

---

### R4 安全加固与供应链（P1）

#### R4.1 响应安全头

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R4.1.1** 安全头中间件 | a) `X-Content-Type-Options`/`X-Frame-Options`/`Referrer-Policy`/HSTS；b) CSP 按 Next 实际资源清单收窄（先 report-only）；c) 测试 | — |

> **注意**：**不新增 CORS**（见 2.2 辩证裁定——同源代理下加 CORS 是负收益）。

#### R4.2 容器加固

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R4.2.1** 双 Dockerfile 改造 | a) 构建期建非 root 用户 + `USER`；b) 增 `HEALTHCHECK`；c) backend 改多阶段（build/runtime 分离，去编译工具链）；d) frontend 评估 `output:'standalone'` 后改多阶段（需评估 rewrites 影响）；e) compose 增 `read_only`/`cap_drop: [ALL]`/`security_opt: no-new-privileges` | R3.3.1 |

#### R4.3 密钥治理

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R4.3.1** 轮换流程 | a) `PUSH_SECRET_MASTER_KEY`/`ENGINE_KEY_MASTER_KEY` 轮换 SOP（双密钥窗口）；b) 轮换演练脚本；c) 写入 `conventions.md` | — |

#### R4.4 供应链扫描

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R4.4.1** CI 增四扫 | a) `pip-audit`（后端依赖）；b) `pnpm audit`（前端依赖）；c) `trivy`（镜像）；d) `gitleaks`（提交历史）；e) 失败策略：高危阻断、中危告警 | R6.1.2 |

#### R4.5 production guard 收窄

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R4.5.1** guard 白名单化 | a) `production_guard_violations()` 改为「显式 dev/test 白名单放行，其余一律守卫」；b) 测试覆盖非标准 env 名绕过场景 | — |

---

### R5 前端性能与工程质量（P1）

#### R5.1 契约消费

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R5.1.1** 接入 `@bothot/contracts` | a) `frontend/package.json` 增 workspace 依赖 + `tsconfig` paths；b) `lib/api/*` 返回类型改引契约 `ApiResponse`/`PageResult`；c) 删除本地重复类型定义；d) CI 增契约类型门禁（`tsc --noEmit`） | R7.2.1 |

#### R5.2 渲染优化与分割

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R5.2.1** 图片优化 | a) `<img>` → `next/image`；b) `next.config.mjs` 配 `images.remotePatterns`；c) 验收：`next/image` 引用数 > 0 | — |
| **R5.2.2** 路由级拆包 | a) 重组件（Tab、图表、Markdown 渲染）改 `next/dynamic`；b) 分析 `next build` 首屏 JS 体积前后对比；c) 验收：`next/dynamic` 引用数 > 0 | — |

#### R5.3 运行时韧性

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R5.3.1** 错误边界补齐 | a) 每功能域 `error.tsx` + `loading.tsx`；b) `not-found.tsx`；c) 关键数据用 Suspense 边界 + 骨架屏 | — |

#### R5.4 e2e 入 CI

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R5.4.1** e2e job | a) CI 增 e2e job：起 compose 栈 → 等 `/ready` → `pnpm test:e2e`；b) 解阻 `real-backend.spec.ts` 的 4 处 `test.skip`（OIDC 身份替身）；c) 补 `/bots` 任务流与 `/hot` 路径 e2e；d) 端口 3200（禁 3333） | R6.1.2 |

---

### R6 CI/CD 与发布工程（P0/P1）

#### R6.1 门禁补全

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R6.1.1** 覆盖率门禁 | a) pytest 增 `--cov` + `--cov-fail-under`（先取当前基线为下限防回退）；b) 覆盖率产物上传 | — |
| **R6.1.2** docker build 冒烟 | a) buildx 构建 backend/frontend 镜像（不 push）；b) 失败即红 | R4.2.1 |
| **R6.1.3** 迁移单头守卫 | a) `alembic heads | wc -l == 1` 断言（`upgrade head` 已于 `ci.yml:61` 保留）；b) 分支合并前本地钩子同断言 | — |

#### R6.2 版本锚统一

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R6.2.1** Node 版本决策与对齐 | a) **决策**：Node 22 LTS 还是 24（`.nvmrc` 现为 24.21.0）——二选一；b) `.nvmrc` / `engines` / Dockerfile `BASE_IMAGE` 三方同步为同一版本；c) CI 增锚一致性断言 | — |
| **R6.2.2** pnpm 单一事实源 | a) 版本以 `packageManager` 为唯一源；b) `frontend/Dockerfile:31` 去掉硬编 `pnpm@10.34.5`，改由 corepack 读 `packageManager`；c) 断言 `packageManager` 版本 == CI 解析版本 | — |

#### R6.3 Makefile 修复

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R6.3.1** `guard-ports` 改 fail-closed | a) 拆分为独立判定（后端/前端各一次 `grep` 各自判 `$?`），前置 `set -e`；b) 新增负例测试（真埋一个 3333 断言退出码非 0）；c) 新增 `guard-versions`（对齐 R6.2） | — |

#### R6.4 发布物

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R6.4.1** CHANGELOG 切版本段 | a) 从 `git log` 切分 v0.3/v0.4/v0.5/v0.6 段 + 日期；b) `[Unreleased]` 保留增量；c) tag 流程写入 `conventions.md` | — |

---

### R7 文档一致性与架构迁移（P1/P2）

#### R7.1 文档二次漂移修复（最高性价比，立即做）

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R7.1.1** backlog 状态校正 | a) HOT-001/HOT-002 ⬜→✅；b) HOT-003/HOT-004 去「修复中」措辞并标 ✅（或按实现精度标 🔧 并列明残余）；c) PUSH-008 ⬜→✅（outbox 已落）；d) TECH-001/TECH-002 ✅；e) FE-002 ✅；f) TEST-003 保持 ⬜；g) DOC-002 保留 🔧 | — |
| **R7.1.2** roadmap/AGENTS 同步 | a) `roadmap.md:14` 阶段标签 v0.3 → 与实际交付对齐；b) `AGENTS.md` 状态行核对（推送/热点口径） | R7.1.1 |
| **R7.1.3** 新增 DOC-003 一致性 CI 检查 | a) 轻量脚本：对 backlog 的关键状态图标做 `grep` 实证断言（如标 ✅ 的项其声称文件必须存在）；b) 接入 CI，防漂移复发 | R7.1.1 |

#### R7.2 契约业务域提取

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R7.2.1** 各域 DTO 提取 | a) bot/push 域 DTO；b) hot 域 DTO；c) spaces/subscriptions 域 DTO；d) 由后端 OpenAPI 生成 `.d.ts` 与手写契约双向校验 | R6.1.1 |

#### R7.3 `apps/` 目录迁移（v0.7）

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R7.3.1** hot 域试点 | a) 按 `project-structure-design.md` 迁移 hot 域到 `apps/api/src/modules/hot`；b) pytest 全绿再进下一域 | R7.2.1 |
| **R7.3.2** bot 域迁移 | a) 含 push providers 与 `secret_crypto`；b) 全绿门禁 | R7.3.1 |
| **R7.3.3** 其余域 + 前端 | a) 逐域迁移后端；b) 前端拆 `apps/web`；c) 清理 183 个 `.gitkeep` | R7.3.2 |

#### R7.4 归档

| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **R7.4.1** 过时文档归档 | a) 根目录 `当前任务规划.md` → `docs/09_archive/superseded/`；b) 本文档（TASK-PLAN-v0.6.md）取代其口径 | — |

---

## 第五节 执行顺序与依赖图

```
立即做（成本最低/收益最大）: R6.3 Makefile → R6.2 版本锚 → R7.1 文档校正 → R7.4 归档
P0 性能链:   R1.1 索引 → R1.2 分页 → R1.4 池  ‖ R3.1 日志 → R3.2 指标 → R3.3 live/ready
P0 健壮链:   R2.1 限流 → R2.2 body 上限 ‖ R2.3 上游并发
P0 运维链:   D1 compose 治理（limits/logging/hardening）+ R4.2 容器改造
P1 安全链:   R4.1 安全头 ‖ R4.3 密钥轮换 → R4.4 供应链扫描 → R4.5 guard 收窄
P1 前端链:   R7.2 契约 → R5.1 契约消费 ‖ R5.2 渲染 → R5.3 边界 → R5.4 e2e
P1 CI 链:    R6.1 门禁（覆盖率/docker build/单头）
P2 迁移链:   R7.3 apps/ 迁移（须在功能冻结后；否则双倍返工）
```

两条 P0 链（性能 R1/R3、健壮 R2）文件域不重叠，可并行；R7.3 必须最后。

---

## 第六节 验收标准（量化）

1. 23 个列表端点 **100% 具备 `page_size` + `total`**（仅 `list_channel_types`、`list_doc_categories` 两个枚举端点白名单豁免）。
2. PG `pg_indexes` 覆盖 4 个新增 FK 索引；`EXPLAIN` 证明按 `space_id` 过滤走索引（非 Seq Scan）。
3. 性能基线：`admin_list_space_docs`（1k 行）p95 < 200ms（改造前后各测一次留证）。
4. `/metrics` 暴露 ≥8 项指标；`grep -rn structlog backend/app | wc -l` ≥ 50 且无裸 `logging` 残留。
5. `/ready` 在迁移版本不一致时返回 503（构造不一致场景实测）。
6. CI 门禁 **6 类全绿**：单测+覆盖率、ruff/mypy、alembic 单头、docker build、e2e、漏洞扫描。
7. 容器：非 root、有 `HEALTHCHECK`、compose 有 `limits` 与日志轮转（`max-size`）。
8. `backlog`/`roadmap`/`AGENTS` 状态与 grep 实证一致（DOC-003 脚本零告警）。
9. `grep -rn "@bothot/contracts" frontend | wc -l` > 0 且 `tsc --noEmit` 通过。
10. e2e 在 CI 中真跑：`real-backend.spec.ts` 的 `test.skip` 数从 4 → 0。

---

## 第七节 关键风险与缓解

| 风险 | 概率 | 缓解 |
|---|---|---|
| 分页改造破坏现有前端调用（返回体由数组变 `PageResult`） | 高 | R1.2.1 先定契约 → R1.2.3 与 R5.1 合流，前端同批改；过渡期可双返回（`items` + 兼容数组视图） |
| compose 限资源压垮 worker | 中 | 先量测基线（R3.2 指标）再设 `limits`；先进 shadow 观察 |
| 前端多阶段构建改坏 `rewrites`（构建期烘焙 env） | 中 | `frontend/Dockerfile:19-25` 已注明 build-arg 烘焙；改造时保持 `BACKEND_ORIGIN` 仍为 build-arg |
| 版本锚对齐引入 Node 主版本跳变 | 中 | R6.2.1 需产品/工程拍板 22 vs 24；对齐后跑全量 CI + e2e 验证 |
| `apps/` 迁移造成大规模冲突 | 高 | 仅在功能冻结后启动；每域迁移全绿门禁；契约先行（R7.2） |
| 契约类型与后端实际响应不一致 | 中 | OpenAPI 生成 + 双向校验（R7.2.1d）而非纯手写 |

---

## 第八节 前提条件与局限性

**前提**：
- 本地/CI PG 可达（5433），`PUSH_SECRET_MASTER_KEY`/`ENGINE_KEY_MASTER_KEY` 的密钥管理流程已建立。
- R4.2 frontend 多阶段改造的可行性受 `next.config.mjs` 是否引入 `output:'standalone'` 制约（属代码变更，需评估）。

**显式排除项（非遗漏，各自单独立项）**：
- **CORS**：同源代理下**不应添加**（见 2.2）。
- **`relationship()` 全面引入**：当前显式 JOIN 是自觉选择；仅在有必要时按纪律引入（R1.3）。
- **RagflowAdapter 实接**：依赖主平台排期（ADR-0004 P2）。
- **向量聚簇 / pgvector**：TF-IDF 已满足当前量级；升级路径预留为独立后续任务。
- **站内通知前端订阅侧**：投递侧已通，订阅侧缺失（`AGENTS.md` 须保留该口径）。

**局限性**：
- 本文所有缺口计数基于 `main @ 2fa95f0` 的静态扫描（grep/AST），未做运行期压测；性能类缺口（A1/A4）的**真实影响需压测确认**后方可定优先级。
- 优先级 P0/P1 为工程判断，最终需产品按业务节奏拍板（尤其 R2.4.2 / R2.5.1 / R6.2.1 / R7.3）。

**一句话总览**：W1–W5 已把 `当前任务规划.md` 的 M1–M5 交付约七成（cron/AES/分叉收编/热点域/outbox/前端 Tab/CI 全属实）；本轮真实剩余缺口集中在**四条线**——数据层（19 端点无分页 + 4 个 FK 无索引）、可观测性（structlog 装了零用、无指标）、容器与运维（零 limits/日志轮转、root 单阶段）、契约与文档（前端零消费契约、backlog 二次漂移 9 处）。建议动工序：**R6.3/R6.2/R7.1 低成本项立即做 → R1 + R3 两条 P0 链并行 → R2/R4 安全链 → R5/R6 工程链 → R7.3 迁移压轴**。
