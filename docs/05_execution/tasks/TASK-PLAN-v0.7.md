---
id: TASK-PLAN-v0.7
type: task-plan
title: BotHot 全量剩余任务大纲与五路并行作业包（v0.7）
status: active
owner: engineering
created: 2026-09-30
updated: 2026-09-30
baseline_commit: 2ca714f
supersedes: docs/05_execution/tasks/TASK-PLAN-v0.6.md（口径已过期，见下）
---

# BotHot 全量剩余任务大纲与五路并行作业包（v0.7）

> **取证基线**：`main @ 2fa95f0`（W1–W5 已合并）+ 工作区未提交改动（WA/WB/WC/WE）
> + 分支 `feat/wd-ci-docs @ 1bbc749`（WD，已提交未合并）。
> **唯一标准**：与代码实证一致，每条带 `文件:行` 证据链。
> **编号规则**：`域.阶段.任务`（如 C.1.2），其下 a/b/c 为**原子步骤**（可独立提交、独立验收）。
> **与 v0.6 的关系**：v0.6 的 R1–R7 编号**不再沿用**（其 R1.1/R1.4/R2.4/R5.4/R6.2/R6.3/R6.4/R7.1/R7.4
> 已被 WA–WE/WD 覆盖或部分覆盖）；本文件按「域 A–E」重编，并给出逐条覆盖裁定。

---

## 第零节 前置条件（**开工前必须完成，否则五路互相污染**）

WA/WB/WC/WE 的全部产出**滞留工作区、零提交**（`git branch -v`：`feat/wa-hot-scoring`/`feat/wc-infra`/
`feat/we-notifications` 均为 `2fa95f0`，`git log` 无新增）。五路并行作业**必须**基于一个干净 HEAD。

```bash
# 0) 备份工作区（沙箱破坏性操作前必备）
cp -r /e/Code/AideanBotHot /e/Code/_AideanBotHot_backup_$(date +%Y%m%d%H%M)

# 1) 落定 WA–WE（当前分支 feat/we-notifications）
git add -A && git commit -m "feat(wa-we): 热点评分接线/推送重试/分页形状/FK索引/站内通知订阅侧"

# 2) 合并 WD（feat/wd-ci-docs，1 提交）
git checkout main && git merge --no-ff feat/wd-ci-docs -m "merge: WD CI 门禁与文档漂移清零"
git merge --no-ff feat/we-notifications -m "merge: WA-WE 语义接通与工程加固"

# 3) 五路各自开分支
for b in w6-observability w7-security w8-data w9-frontend w10-gov; do
  git branch feat/$b main
done
```

**五路分支**：`feat/w6-observability` / `feat/w7-security` / `feat/w8-data` / `feat/w9-frontend` / `feat/w10-gov`
**统一纪律**：只 `git add <自己拥有的路径>`；不 `git rm`；不 `git push`；不 `--force`；不碰 `.workbuddy/`。

---

## 第一节 进度裁定（证据链）

### 1.1 已交付（已合并）

| 交付 | 证据 |
|---|---|
| W1 推送渠道域（cron 全生命周期 / AES-256-GCM 渠道密钥 / 旧 `push_port.py` 删除） | `0879882`；`core/secret_crypto.py` 存在；`providers/push_port.py` 已不存在 |
| W2 热点域落地 | `25181c1`；`services/hot_cluster.py` / `hot_scorer.py` / `feed_service.py` / `llm_summary.py` |
| W3 调度并发安全 + outbox | `90618b7`；`push_scheduler.py:85 .with_for_update(skip_locked=True)`；`models/bothot_entities.py:243 class PushEvent` |
| W4 前端推送任务 Tab + 热点中心 | `d2678d7`；`frontend/app/bots/page.tsx:50 activeTab` |
| W5 CI 真实化 + 文档 | `a6889b0`；`.github/workflows/ci.yml` 三 job（`:9 backend` / `:125 frontend` / `:218 compose`） |

### 1.2 已在工作区完成（**未提交**，本轮视为已实现但未验收）

| 产出 | 证据 | 覆盖 v0.6 条目 | 裁定 |
|---|---|---|---|
| 4 个无索引 FK 补索引 + 迁移 | `models/bothot_entities.py`（space_id/created_by/push_task_id/center_asset_id 均 `index=True`）；`alembic/versions/ab1004w4a_push_retry_and_fk_indexes.py` `op.create_index` ×4 | R1.1 | ✅ 实现，**缺断言测试**（见 C.3.1） |
| 推送投递重试/指数退避/死信 | `providers/push/base.py`（`retryable` 字段）；`push_scheduler.py`（`MAX_PUSH_RETRIES=3`、`60*4^(n-1)`、`log_status="dead"`） | PUSH-009（新） | ✅ 实现 |
| 事件 payload 自足快照 + 模板变量/时区 | `push_events.py:_hydrate_payload`；`push_template.py`（`report_title`、`Asia/Shanghai`） | — | ✅ 实现 |
| 站内通知订阅侧（SSE + 铃铛） | `api/v1/system.py:notifications`（SSE，双锚 `sub`/`users.id` + broadcast）；`frontend/components/NotificationBell.tsx`；`frontend/lib/api/notifications.ts` | FE-005（新） | ✅ 实现，**离线通知无补投**（见 D.5） |
| 热度评分接线 + 周期重评 | `job_worker.py:HOT_JOB_TYPES` 增 `hot_rescore`；`scheduler.py:_maybe_enqueue_rescore`（每小时）；`hot_scorer.py` FeedItem 分数同步 | HOT-002/HOT-004 补完 | ✅ 实现，**FeedItem 逐条 UPDATE**（见 C.5.1） |
| 聚簇剪枝与护栏 + 日报并发 | `hot_cluster.py`（倒排预筛、`MAX_CANDIDATES_DEFAULT=3000`）；`feed_service.py`（`_SUMMARY_CONCURRENCY=3` + `asyncio.gather`） | — | ✅ 实现 |
| 分页响应形状（5 端点） | `admin.py`（`admin_list_spaces`/`admin_list_subscriptions`/`admin_list_sources`）；`spaces.py`（`list_public_spaces`/`list_spaces`）→ `{items,total,limit,offset}` | R1.2 部分 | 🔧 **仅路由层切片，全量仍加载**（见 C.1） |
| 连接池 env 化 + 回收 | `db.py`（`DB_POOL_SIZE`/`DB_MAX_OVERFLOW`/`DB_POOL_RECYCLE=1800`） | R1.4 部分 | 🔧 **无启动断言**（见 C.3.2） |
| 未实接引擎删除降级 | `providers/engine_port.py:delete_kb` 返回 `None` 而非抛错 | R2.4 部分 | 🔧 **service 层清映射/响应注明残留未做**（见 C.6） |
| 版本锚部分对齐 | `frontend/Dockerfile` → `node:24-alpine` + corepack 读 `packageManager`；`frontend/package.json engines.node>=24.0.0` | R6.2 部分 | 🔧 **`.nvmrc` 不存在**（`cat .nvmrc` → not found，三方未齐） |
| 生产守卫纳入双主密钥 | `core/config.py`（`push_secret_master_key`/`engine_key_master_key` 入 `production_guard_violations()`） | R4.5 部分 | 🔧 **未白名单化**（非标准 env 名仍可绕过） |
| roadmap/AGENTS v0.6 | `docs/04_engineering/roadmap.md`（v0.3→v0.6，v0.6 十条勾选）；`AGENTS.md` 状态行 | R7.1.2 | 🔧 待与本轮交付再同步 |

### 1.3 WD 已提交未合并（`1bbc749`，8 文件 +1149/−153）

| 产出 | 证据 | 覆盖 v0.6 |
|---|---|---|
| CI e2e（mock UI + 真后端门控）+ compose-smoke + 单头断言 | `.github/workflows/ci.yml` 四 job；`Assert single alembic head` | R5.4.1 / R6.1.2 / R6.1.3 |
| `guard-ports` fail-closed | `Makefile`（双 grep 各自判 `$?`） | R6.3.1 |
| backlog 逐条回填 + 归档 + CHANGELOG 切段 + README 部署指南 | `docs/04_engineering/backlog.md`、`docs/09_archive/superseded/当前任务规划.md`、`CHANGELOG.md`、`README.md` | R7.1.1 / R7.4.1 / R6.4.1 |

### 1.4 复核发现的**在途缺陷**（需本轮一并修）

| # | 缺陷 | 证据 | 归口 |
|---|---|---|---|
| P1 | 分页只做了**路由层切片**，`svc.list_*()` 仍全量加载 | `admin.py:admin_list_spaces` → `items = await svc.list_space_views_any()` 后 `items[offset:offset+limit]` | C.1.2 |
| P2 | `hot_scorer` 对每话题逐条 `UPDATE feed_items`（N 次往返） | `hot_scorer.py` `for t in topics: await session.execute(update(FeedItem)...)` | C.5.1 |
| P3 | `.nvmrc` 缺失，版本锚三方未齐 | `cat .nvmrc` → not found；`frontend/Dockerfile` 已 `node:24-alpine` | A.4.3 |
| P4 | `_maybe_enqueue_daily_jobs` 内 `if operator_id is None: return` 会提前退出整个方法 | `scheduler.py` hot_cluster 分支 | A.6（顺手） |
| P5 | SSE 离线通知无补投（Redis pub/sub 无持久化，前端仅内存态） | `system.py:_notification_stream`；`NotificationBell.tsx` `setItems` 内存 | D.5.1 |
| P6 | 引擎删除仅"不整体回滚"，未清 `engine_kb_id` 映射、未在响应注明引擎侧残留 | `engines.py:patch_space_engine` docstring 自述"响应注明残留属 service 层职责" | C.6 |

---

## 第二节 全量剩余任务大纲（域 → 阶段 → 原子任务 → 步骤）

### 域 A 可观测性与运行时（OBS）｜归口 **W6**｜P0

#### A.1 结构化日志
| 任务 | 原子步骤 | 证据/依赖 |
|---|---|---|
| **A.1.1** structlog 双模初始化 | a) 新建 `core/logging.py`：prod=JSONRenderer / dev=ConsoleRenderer；b) 桥接 stdlib `logging`（`ProcessorFormatter` 去重复行）；c) `LOG_LEVEL`/`LOG_FORMAT` 走**模块常量+env**（**不动 `core/config.py`**，规避 W7 文件争用，与 `db.py` 池参数同先例） | `pyproject.toml:18 structlog>=24.4.0` 已装；`grep -rn structlog backend/app \| wc -l` = **0** |
| **A.1.2** requestId 全链贯通 | a) 复用既有 `core/request_context.py` + `core/middleware.py:RequestIdMiddleware`（**已存在，勿重造**）；b) 让 structlog `contextvars.merge_contextvars` 注入 `request_id`；c) 日志字段名与 `core/middleware.py:REQUEST_ID_HEADER` 单一来源 | `core/middleware.py:23`、`core/request_context.py` |
| **A.1.3** 分层迁移 | a) `core/` → b) `services/` → c) `api/`；d) 验收 `grep -rn structlog backend/app \| wc -l` ≥ 50 且 `grep -rn "^import logging" backend/app \| wc -l` = 0（`logging.getLogger` 仅允许出现在 `core/logging.py`） | — |

#### A.2 指标暴露
| 任务 | 原子步骤 | 证据/依赖 |
|---|---|---|
| **A.2.1** `/metrics` 端点 | a) 新建 `core/metrics.py` + `prometheus_client`（入 `backend/pyproject.toml`，本作业包唯一 owner）；b) `MetricsMiddleware`（**加在既有 `core/middleware.py`**）：`http_request_duration_seconds`（histogram，label: method/path_template/status）、`http_requests_in_flight`（gauge）；c) `db_pool_in_use`/`db_pool_checkedout` gauge（读 `engine.pool`）；d) `jobs_by_status` gauge（定时 `SELECT status,count(*)`）；e) 业务计数：`push_deliveries_total{channel,outcome}`、`hot_cluster_duration_seconds`、`daily_report_total{result}` | `grep -rniE "prometheus\|opentelemetry\|sentry" backend/app` = **0** |
| **A.2.2** 暴露隔离 | a) `/metrics` 走**独立 router**，仅 `expose` 不 `ports`；b) 与 `/api/v1/system/health` 同级的匿名探活分离，不被登录门禁捕获；c) 断言 OpenAPI `security` 标注不含 `/metrics`（对照 `main.py:_annotate_session_security`） | `main.py:64 _annotate_session_security` |

#### A.3 健康/就绪分离
| 任务 | 原子步骤 | 证据/依赖 |
|---|---|---|
| **A.3.1** `/live` + `/ready` | a) 抽 `core/schema_guard.py:check_schema_current() -> tuple[bool,str]`，**复用** `main.py:_assert_schema_current:186` 的 `ScriptDirectory` + `alembic_version` 探测逻辑（勿复制粘贴）；b) `/live`：纯进程存活，**不触依赖**；c) `/ready`：PG ping + Redis ping + `check_schema_current()`；任一失败 → 503 + 明细；d) 保留 `admin.py:486 /ops/liveness` 不回归 | `main.py:186-241`（已实现启动期版本守卫）；`system.py:81 /health` |
| **A.3.2** 编排接线 | a) `docker/compose.yml` backend healthcheck 指向 `/live`；b) `depends_on: {postgres: {condition: service_healthy}, redis: ...}`；c) `Dockerfile HEALTHCHECK`（与 A.4.2 合流） | `docker/compose.yml`（`healthcheck` 命中数 = 0） |

#### A.4 容器与运行时硬化
| 任务 | 原子步骤 | 证据/依赖 |
|---|---|---|
| **A.4.1** compose 治理 | a) 9 服务统一 `logging.options: {max-size: "10m", max-file: "3"}`；b) `deploy.resources.limits`（mem/cpu，**先量测基线再设值**）；c) backend/scheduler/worker `read_only: true` + `tmpfs: /tmp`、`cap_drop: [ALL]`、`security_opt: ["no-new-privileges:true"]`；d) `restart` 策略复核 | `docker/compose.yml`：`limits:`/`logging:`/`read_only:`/`cap_drop:` 命中数均 = **0**（9 服务：`:26 postgres` `:45 redis` `:54 langbot_plugin_runtime` `:82 langbot` `:108 backend` `:230 migrate` `:255 scheduler` `:299 worker` `:333 frontend`） |
| **A.4.2** Dockerfile 硬化 | a) `backend/Dockerfile` 改多阶段（builder 装编译链 → runtime 仅 wheel）；b) 建 uid=1000 非 root 用户 + `USER`；c) 两镜像加 `HEALTHCHECK`；d) `frontend/Dockerfile` 评估 `output:'standalone'`（**须保持 `BACKEND_ORIGIN` 仍为 build-arg**，见 `frontend/Dockerfile:19-25`） | `backend/Dockerfile:5 FROM ${BASE_IMAGE}`（无 USER/HEALTHCHECK） |
| **A.4.3** 版本锚三方齐 | a) **新建 `.nvmrc`** = `24.21.0`（对齐 `frontend/Dockerfile ARG BASE_IMAGE=node:24-alpine`）；b) 三方断言：`.nvmrc` 主版本 == Dockerfile node 主版本 == `package.json engines.node` 主版本；c) `pnpm` 单一源 = `packageManager`（Dockerfile 已去硬编，仅需断言） | `cat .nvmrc` → **not found**；`frontend/package.json engines.node>=24.0.0`；`frontend/Dockerfile` `corepack enable`（已删 `prepare pnpm@10.34.5`） |

#### A.5 告警（依赖 A.2）
| 任务 | 原子步骤 |
|---|---|
| **A.5.1** 三类告警 + 单通道 | a) 进程心跳缺失（复用 `services/process_heartbeat.py:EXPECTED_PROCESSES`）；b) Job 队列积压超阈；c) 推送连续失败（读 A.2.1 指标）；d) 经既有 push provider（飞书/钉钉）投递，落 `core/alerting.py` |

#### A.6 顺手修正（P4）
| 任务 | 原子步骤 |
|---|---|
| **A.6.1** `scheduler.py` 早退语义 | a) `_maybe_enqueue_daily_jobs` 内 hot_cluster 分支的 `if operator_id is None: return` 改为 `continue` 语义（抽独立私有方法）；b) 删冗余 `or now_local.hour > hour`；c）补单测断言「daily 成功 + cluster 无 operator」时 daily 不被回滚 |

---

### 域 B 安全与入站防护（SEC）｜归口 **W7**｜P0/P1

#### B.1 入站限流
| 任务 | 原子步骤 | 证据 |
|---|---|---|
| **B.1.1** Redis 令牌桶中间件 | a) 新建 `core/security.py`（**不得改 `core/middleware.py`／`main.py`，二者归 W6**）；b) 固定窗口 + Redis `INCR`+`EXPIRE`（多副本一致），Redis 不可达 → **fail-open + warn**（可用性优先）；c) 双维度 `client_ip` + `user.sub`（sub 由 cookie 解出，与 `api/deps.py:get_current_sub` 同口径） | `slowapi`/`RateLimit` 命中 **11 处全为 `RateLimitedUpstreamError`**（上游 4004），**无入站限流** |
| **B.1.2** 敏感路径配额 + 429 契约 | a) 独立配额表：`/api/v1/auth/*`、`/api/v1/chat`、`/api/v1/extract`、`/api/v1/hot/topics/cluster`、`/api/v1/bots/tasks/{id}/run`；b) `core/errors.py` 增 `RATE_LIMITED` 码（**`errors.py` 归 W7**）；c) 429 响应体走 `core/response.failure` 信封（携带 requestId） | `core/errors.py:116 RateLimitedUpstreamError` |

#### B.2 请求体上限
| 任务 | 原子步骤 |
|---|---|
| **B.2.1** BodyLimit 中间件 | a) `core/security.py`：`Content-Length` 预检 + 流式截断双保险；b) 超限 → 413 + 统一错误码；c) 白名单豁免路径（如 SSE `/notifications` 为 GET 无 body，天然不涉） |

#### B.3 上游调用治理
| 任务 | 原子步骤 | 证据 |
|---|---|---|
| **B.3.1** provider 级信号量 + 统一超时/退避 | a) `providers/article_sources/*.py`（dajiala/justoneapi/tikhub/wellbyte）与 `providers/redfox/client.py` 各加模块级 `asyncio.Semaphore(N)`（N 走 env，**只加并发闸与超时，不改解析逻辑**）；b) `httpx.Timeout(connect=..., read=...)` 统一；c) 命中 `RateLimitedUpstreamError`（4004）触发全局退避窗口，复用 `job_worker.py:92` 既有分支 | `grep -rn asyncio.Semaphore backend/app` = 1（仅 `feed_service.py` LLM，in-flight） |

#### B.4 响应安全头
| 任务 | 原子步骤 |
|---|---|
| **B.4.1** SecurityHeaders 中间件 | a) `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: strict-origin-when-cross-origin`、HSTS（仅 https）；b) CSP 先 `Content-Security-Policy-Report-Only`（按 Next 实际资源收窄）；c) **须为最外层**（保证 429/413 也带安全头） |
| **B.4.2** 明确不加 CORS | a) 写入 `docs/04_engineering/conventions.md` 防后人误加 | `grep -rn CORSMiddleware backend/app \| wc -l` = **0**（正确设计：`frontend/next.config.mjs` rewrites 同源代理） |

#### B.5 配置守卫收窄
| 任务 | 原子步骤 | 证据 |
|---|---|---|
| **B.5.1** guard 白名单化 | a) `core/config.py:production_guard_violations()` 改为「显式 `dev`/`test`/`local` 白名单放行，其余一律守卫」；b) 保留双主密钥断言（in-flight 已加）；c) 补非标准 env 名（如 `prod-eu`）绕过场景的守卫测试 | `core/config.py:192-201`（in-flight） |

#### B.6 密钥治理
| 任务 | 原子步骤 |
|---|---|
| **B.6.1** 轮换 SOP + 演练脚本 | a) `docs/07_release/key-rotation-sop.md`（**该新文件路径归 W7**，docs 其余归 W10）：双主密钥窗口、`ab1004w1a` 存量再加密流程；b) `scripts/rotate_keys.sh` 演练（dry-run 默认） |

#### B.7 供应链扫描
| 任务 | 原子步骤 |
|---|---|
| **B.7.1** 独立 workflow `security.yml` | a) **新建** `.github/workflows/security.yml`（**不碰 `ci.yml`，其归 W10**）；b) `pip-audit`（backend）/ `pnpm audit --prod`（frontend）/ `trivy fs`（依赖与镜像）/ `gitleaks`（历史）；c) 策略：高危阻断、中危告警；d) 排除 `langbot_plugins` 第三方目录 |

---

### 域 C 数据层与性能（DATA）｜归口 **W8**｜P0/P1

#### C.1 分页收口（**核心：把切片从路由层下沉到查询层**）
| 任务 | 原子步骤 | 证据 |
|---|---|---|
| **C.1.1** 双口径冻结 + 依赖 | a) `api/deps.py` 增 `limit_offset_query`（默认 `limit=50, le=100`, `offset=0`）；b) **冻结**：`{items,total,limit,offset}`（knowledge/订阅/任务/admin 域，存量口径）与 `{items,total,page,page_size}`（bot/hot 域）**双口径并存**，仅补注释不迁移（迁移属契约变更，须先报备）；c) 与 `packages/contracts/src/common/pagination.ts` 注释互引 | `packages/contracts/src/common/pagination.ts`（已自述双口径） |
| **C.1.2** service 层下推 | a) `SpaceService.list_space_views*`、`PublicLibraryService.list_public_views`、`SourceSubscriptionService.list_sources_with_counts`/`list_subscriptions_any`/`list_space_views_any` 增 `limit/offset` 形参 → SQL `LIMIT/OFFSET`；b) `total` 独立 `SELECT COUNT(*)`（同谓词）或 `count() over()`；c) 路由层切片**删除** | P1 缺陷：`admin.py` 现为 `items = await svc.list_space_views_any()` 后 `items[offset:offset+limit]` |
| **C.1.3** 全端点覆盖 | a) `subscriptions.py:72 list_sources` / `:175 list_subscriptions` / `:246 list_jobs`；b) `engines.py:129`；c) `spaces.py:191`（知识库 docs）；d) admin 域剩余 list | 端点行号已核（`grep -n "^async def" subscriptions.py`） |
| **C.1.4** 枚举白名单 | a) `bots.py list_channel_types`、`spaces.py list_doc_categories` 标注豁免并写注释 | — |
| **C.1.5** 计数与基线 | a) 千行级 `EXPLAIN ANALYZE` 前后各一次留证；b) p95 < 200ms 断言（`admin_list_space_docs` 1k 行） | — |

#### C.2 加载策略纪律
| 任务 | 原子步骤 |
|---|---|
| **C.2.1** N+1 审计 + 固化 | a) 审计全部 list 查询的关联取值路径，标注「显式 JOIN」（现状）或「关系加载」；b) 若引入 `relationship()` 必须同处 `selectinload`/`joinedload`；c) 写入 `conventions.md`（**该章节归 W10，W8 只提交内容片段给 W10**） |

#### C.3 索引与查询计划
| 任务 | 原子步骤 | 证据 |
|---|---|---|
| **C.3.1** 索引断言测试 | a) `tests/test_indexes.py`：断言 `pg_indexes` 含 `ix_push_tasks_space_id`/`ix_push_tasks_created_by`/`ix_push_logs_push_task_id`/`ix_hot_topics_center_asset_id`；b) `EXPLAIN` 断言按 `space_id` 过滤非 Seq Scan；c) **PG 不可达 → `pytest.skip`（对齐 `conftest.py` 既有门禁口径）** | in-flight 迁移已建索引但**无测试** |
| **C.3.2** 连接池启动断言 | a) `db.py` 增启动期断言 `进程数 × (pool+overflow) ≤ PG max_connections`（含 migrate 突发）；b) `DB_POOL_RECYCLE` 回收单测 | in-flight `db.py` 有池参数但**无断言** |

#### C.4 读缓存
| 任务 | 原子步骤 |
|---|---|
| **C.4.1** TTL 缓存 | a) 新建 `core/cache.py`：`get_or_set(key, ttl, loader)`（Redis，序列化 JSON）；b) 接入低频变更端点（`list_channel_types`、admin 来源清单、发现渠道白名单）；c) 写路径显式失效；d) Redis 不可达 → 直穿 loader（fail-open） |

#### C.5 批量写
| 任务 | 原子步骤 | 证据 |
|---|---|---|
| **C.5.1** `hot_scorer` FeedItem 分数批量同步 | a) 把 `for t in topics: UPDATE feed_items WHERE ref_id=t.id` 改为单条 `UPDATE ... WHERE item_type='hot_topic' AND ref_id IN (SELECT id FROM hot_topics ...)` 或 `CASE` 批量；b) 断言 `UPDATE` 语句数从 N 降为 1（SQL 计数测试） | P2 缺陷：`hot_scorer.py` 逐条 UPDATE |

#### C.6 引擎删除闭环（P6）
| 任务 | 原子步骤 |
|---|---|
| **C.6.1** 空间删除完整降级 | a) `services/` 空间删除路径：未实接引擎时清 `engine_kb_id`/langbot 映射并删 PG 行；b) 响应体注明「引擎侧残留」字段；c) `engines.py` docstring 与实现对齐；d) 测试覆盖 builtin / 未实接 / 已实接三分支 |

---

### 域 D 前端工程化（FE）｜归口 **W9**｜P1

#### D.1 契约消费
| 任务 | 原子步骤 | 证据 |
|---|---|---|
| **D.1.1** 接入 `@bothot/contracts` | a) `frontend/package.json` 增 workspace 依赖 + `tsconfig` paths；b) `lib/api/*` 返回类型改引契约 `ApiResponse`/`PageResult`；c) 删本地重复类型定义 | `grep -rn "@bothot/contracts" frontend \| wc -l` = **0** |
| **D.1.2** 契约门禁（提需求给 W10） | a) `tsc --noEmit` 入 CI（ci.yml 归 W10，W9 只提出接口需求） | — |

#### D.2 渲染与分割
| 任务 | 原子步骤 | 证据 |
|---|---|---|
| **D.2.1** 图片优化 | a) `<img>` → `next/image`；b) `next.config.mjs` 配 `images.remotePatterns` | `grep -rn "next/image" frontend` = 0 |
| **D.2.2** 路由级拆包 | a) 重组件（Tab、图表、`react-markdown`）改 `next/dynamic`；b) `next build` 首屏 JS 前后对比留证 | `grep -rn "next/dynamic" frontend` = 0 |

#### D.3 运行时韧性
| 任务 | 原子步骤 |
|---|---|
| **D.3.1** 错误边界补齐 | a) 每功能域 `error.tsx` + `loading.tsx`；b) `not-found.tsx`；c) 关键数据 Suspense + 骨架屏 |

#### D.4 分页 UI 接入
| 任务 | 原子步骤 |
|---|---|
| **D.4.1** 消费新分页形状 | a) `lib/api/*` 对接 `{items,total,limit,offset}`（**兼容渲染两种形状**，防 C.1 未落地时炸）；b) 列表页加分页器组件 `components/Pagination.tsx`；c) e2e 断言翻页 |

#### D.5 通知增强
| 任务 | 原子步骤 | 证据 |
|---|---|---|
| **D.5.1** 离线通知补投（P5） | a) 后端补 `notifications` 持久化表 + `GET /api/v1/system/notifications/history`（**后端部分需协调，W9 先做前端读取与合并去重**）；b) 前端首连拉历史 + SSE 增量合并；c) 未读数落 `localStorage` | `NotificationBell.tsx` 仅内存态；`system.py` 无历史端点 |
| **D.5.2** 429 统一提示 | a) `lib/api` 拦截 429 → 统一 toast | B.1.2 |

#### D.6 e2e 补路径
| 任务 | 原子步骤 | 证据 |
|---|---|---|
| **D.6.1** 补 `/bots` 任务流与 `/hot` 路径 | a) mock e2e 补两条路径；b) 真后端 `real-backend.spec.ts` 的 `test.skip`（4 处）解阻依赖 OIDC 身份替身（**本轮仅记录，不强行解阻**） | `frontend/e2e/real-backend.spec.ts` 已被 WD 改为 env 门控 |

---

### 域 E 契约、CI 门禁与文档治理（GOV）｜归口 **W10**｜P1/P2

#### E.1 契约业务域 DTO 提取
| 任务 | 原子步骤 | 证据 |
|---|---|---|
| **E.1.1** bot/push 域 DTO | a) 由 `bots.py` OpenAPI 生成 `.d.ts`；b) 与手写契约双向校验 | `packages/contracts/src/common/*` 仅 3 通用类型 |
| **E.1.2** hot 域 DTO | a) `hot.py` 的 `HotTopic`/`DailyReport`/`FeedItem` DTO | — |
| **E.1.3** spaces/subscriptions DTO | a) `PageResult`(limit/offset 口径) + 空间/订阅/任务 DTO | — |
| **E.1.4** OpenAPI 双向校验脚本 | a) `scripts/gen_contracts.py`：`openapi.json` → `.d.ts` + diff 校验入 CI | — |

#### E.2 CI 门禁补全
| 任务 | 原子步骤 | 依赖 |
|---|---|---|
| **E.2.1** 覆盖率门禁 | a) `ci.yml` backend job 增 `--cov=app --cov-report=xml --cov-fail-under=<当前基线>`（**先测基线为下限防回退**）；b) 产物上传 | `pytest-cov` **当前不在 `pyproject.toml`** → 需 W6 在 A.2.1 一并加入（已写入 W6 提示词） |
| **E.2.2** `make guard-versions` | a) `Makefile` 新增：断言 `.nvmrc` == Dockerfile node == `engines.node` == `packageManager`；b) fail-closed | A.4.3 |
| **E.2.3** 契约类型门禁 | a) `ci.yml` frontend job 增 `tsc --noEmit`（在 D.1.1 落地后） | D.1 |

#### E.3 文档一致性 CI（DOC-003）
| 任务 | 原子步骤 |
|---|---|
| **E.3.1** `scripts/check_docs_consistency.py` | a) 解析 `backlog.md` 中标 ✅ 的条目，断言其声称的 `文件` 存在（正则提取路径）；b) 接入 CI 独立 step；c) 防「虚标完成」复发 |

#### E.4 文档同步与规范增补
| 任务 | 原子步骤 |
|---|---|
| **E.4.1** 二次同步 | a) `backlog.md` 补 PUSH-009/FE-005 与 WA–WE 落地项；b) `roadmap.md` v0.6→v0.7；c) `AGENTS.md` 状态行；d) `CHANGELOG.md` 增 v0.7（Unreleased） |
| **E.4.2** `conventions.md` 增补 | a) 分页双口径冻结；b) 加载策略纪律（C.2.1 内容）；c) **不加 CORS**；d) 版本锚单一源；e) 索引必需清单 |

#### E.5 目录迁移（**v0.7 压轴，本轮单独立项不动**）
| 任务 | 说明 |
|---|---|
| **E.5.1–E.5.3** | `backend/`→`apps/api/`、`frontend/`→`apps/web/`、`packages/contracts` 提取固化、清 183 个 `.gitkeep`。**必须功能冻结后单独一轮**，与五路并行互斥（会造成全域冲突）。证据：`apps/` 下 183 个 `.gitkeep` 空壳 |

---

## 第三节 五路并行作业包（文件所有权矩阵）

| 路径 | W6 OBS | W7 SEC | W8 DATA | W9 FE | W10 GOV |
|---|---|---|---|---|---|
| `backend/app/main.py` | **✍ owner** | ✗ | ✗ | ✗ | ✗ |
| `backend/app/core/middleware.py` | **✍ owner** | ✗ | ✗ | ✗ | ✗ |
| `backend/app/core/{logging,metrics,schema_guard}.py` | **✍ 新建** | ✗ | ✗ | ✗ | ✗ |
| `backend/app/core/security.py` | ✗ | **✍ 新建** | ✗ | ✗ | ✗ |
| `backend/app/core/config.py` | ✗ | **✍ owner** | ✗ | ✗ | ✗ |
| `backend/app/core/errors.py` | ✗ | **✍ owner** | ✗ | ✗ | ✗ |
| `backend/app/api/v1/system.py` | **✍ owner** | ✗ | ✗ | ✗ | ✗ |
| `backend/app/db.py` | **✍ owner** | ✗ | ✗ | ✗ | ✗ |
| `backend/app/services/process_heartbeat.py` | **✍ owner** | ✗ | ✗ | ✗ | ✗ |
| `backend/app/providers/article_sources/*`、`redfox/client.py` | ✗ | **✍ owner** | ✗ | ✗ | ✗ |
| `backend/app/api/deps.py`、`api/v1/{admin,spaces,subscriptions,engines}.py` | ✗ | ✗ | **✍ owner** | ✗ | ✗ |
| `backend/app/services/*_service.py`、`repositories/*.py` | ✗ | ✗ | **✍ owner** | ✗ | ✗ |
| `backend/app/models/bothot_entities.py`、`alembic/versions/*` | ✗ | ✗ | **✍ owner** | ✗ | ✗ |
| `backend/app/core/cache.py`、`services/hot_scorer.py` | ✗ | ✗ | **✍ 新建/owner** | ✗ | ✗ |
| `frontend/**`（除 `Dockerfile`） | ✗ | ✗ | ✗ | **✍ owner** | ✗ |
| `frontend/Dockerfile`、`backend/Dockerfile`、`docker/compose.yml`、`.nvmrc` | **✍ owner** | ✗ | ✗ | ✗ | ✗ |
| `backend/pyproject.toml` | **✍ owner** | ✗ | ✗ | ✗ | ✗ |
| `packages/contracts/**`、`.github/workflows/ci.yml`、`Makefile`、`scripts/check_docs_consistency.py` | ✗ | ✗ | ✗ | ✗ | **✍ owner** |
| `.github/workflows/security.yml`、`scripts/rotate_keys.sh`、`docs/07_release/key-rotation-sop.md` | ✗ | **✍ 新建** | ✗ | ✗ | ✗ |
| `docs/**`（除上述） | ✗ | ✗ | ✗ | ✗ | **✍ owner** |

### 冻结接口（跨路唯一耦合点，两侧都按此写，先后落地均可）

1. `backend/app/core/security.py` **必须**导出
   `def install_security_middlewares(app: FastAPI) -> None`
   —— 内部按「内→外」顺序 `add_middleware`：`BodyLimitMiddleware` → `RateLimitMiddleware` → `SecurityHeadersMiddleware`；**import 无副作用**（不在 import 期读 Redis）。
2. `backend/app/main.py`（W6）在既有两行之后追加
   ```python
   try:
       from app.core.security import install_security_middlewares
       install_security_middlewares(app)
   except ImportError:
       pass  # W7 未落地时 W6 仍可独立通过
   ```
3. `backend/app/core/errors.py`（W7）新增 `RATE_LIMITED` 码与 `PAYLOAD_TOO_LARGE` 码；W8/W9 仅**消费**，不改该文件。
4. `backend/pyproject.toml`（W6）须同时加入 `prometheus-client` 与 `pytest-cov`（后者为 W10 覆盖率门禁前置）。

---

## 第四节 验收标准（量化 · 五路共用）

1. **门禁全绿**：`ruff check` + `mypy` + `pytest`（PG 可达时连库真跑）+ `alembic heads | grep -c '(head)'` == 1 + `pnpm typecheck` + `pnpm test` + `pnpm run test:e2e`。
2. **无回归**：后端全量用例数 ≥ 796 passed（WD 基线），新增用例覆盖各自新增分支。
3. **文件所有权零越界**：`git diff --name-only` 输出 ⊆ 本路 owner 集合。
4. **证据留痕**：每条任务在报告里给出 `文件:行` 或命令 + 原始输出。
5. **禁改项**：不得新增 CORS；不得删除 `.workbuddy/`；不得 `git rm`；不得改 `AideanBot` 原项目。
6. **未完成必标 ⬜**：禁止把未实现写成已完成（本仓病史）。

### 各域专项量化

- **W6**：`grep -rn structlog backend/app | wc -l` ≥ 50 且 `grep -rn "^import logging" backend/app | wc -l` == 0；`/metrics` 暴露 ≥ 8 指标；`/ready` 在版本不一致时返回 503（**构造不一致场景实测**）；`compose.yml` 的 `logging`/`limits`/`cap_drop` 命中数 ≥ 9/≥1/≥3；两 Dockerfile 均有 `USER` 与 `HEALTHCHECK`；`.nvmrc` 存在且三方主版本一致。
- **W7**：`install_security_middlewares` 可被独立 import；限流命中返回 429 且携带 requestId；`Content-Length` 超限返回 413；响应含 4 个安全头；`security.yml` 四扫步骤存在；`grep -rn CORSMiddleware backend/app | wc -l` 仍 == 0。
- **W8**：**全部列表端点**（`subscriptions.py:72/175/246`、`engines.py:129`、`spaces.py:59/115/191`、`admin.py` 各 list）在 SQL 层带 `LIMIT/OFFSET`（**断言不出现路由层切片**，grep `items[offset` == 0）；`tests/test_indexes.py` 4 索引断言通过；`hot_scorer` FeedItem 同步 UPDATE 语句数 == 1；`EXPLAIN` 前后基线与 p95 留证。
- **W9**：`grep -rn "@bothot/contracts" frontend | wc -l` > 0；`grep -rn "next/image\|next/dynamic" frontend | wc -l` > 0；`error.tsx`/`loading.tsx` 覆盖各功能域；e2e 新增 ≥ 2 条路径通过。
- **W10**：`ci.yml` 含覆盖率门禁与 `tsc --noEmit`；`make guard-versions` 在注入错版本时 fail-closed（**负例实测**）；`check_docs_consistency.py` 对伪造 ✅ 报警；`backlog.md` 新增项与代码一致。

---

## 第五节 依赖与执行顺序

```
前置：落定 WA–WE + 合并 WD（第零节）

W6 ─┬─ A.1 日志 ─→ A.2 指标 ─→ A.5 告警
    ├─ A.3 live/ready（抽 schema_guard，复用 main.py 既有逻辑）
    └─ A.4 容器/版本锚 ─→（W10 E.2.2 guard-versions 依赖 A.4.3）

W7 ─┬─ B.1 限流 ┐
    ├─ B.2 body ┤→ 统一在 core/security.py，由 W6 main.py 一行装配
    ├─ B.4 安全头┘
    └─ B.3 上游并发 / B.5 守卫 / B.6 密钥 SOP / B.7 扫描（互相独立）

W8 ─┬─ C.1 分页下沉（核心）─→ C.1.5 基线 ┐
    ├─ C.3 索引/池断言                  ├→ W9 D.4 分页 UI 消费（后置，兼容双形状）
    ├─ C.4 缓存 / C.5 批量写 / C.6 闭环 ┘

W9 ─┬─ D.1 契约消费 ─→（W10 E.2.3 tsc 门禁）
    ├─ D.2 渲染 / D.3 边界 / D.5 通知 / D.6 e2e（独立）

W10 ─┬─ E.1 契约 DTO（依赖 W8 C.1 定稿形状）
     ├─ E.2 门禁（E.2.1 依赖 W6 加 pytest-cov；E.2.2 依赖 W6 A.4.3）
     ├─ E.3/Е.4 文档（依赖全路落地）
     └─ E.5 迁移：本轮不做
```

**关键路径**：WA–WE 落定 → W6/W7/W8 并行 → W9（消费 C.1）→ W10 收口。

---

## 第六节 风险与缓解

| 风险 | 概率 | 缓解 |
|---|---|---|
| 五路共用工作区互相覆盖 | 高 | 第零节先落定基线；严格文件所有权（第三节矩阵）；只 `git add` 自己路径 |
| W6/W7 争 `main.py`／`core/middleware.py` | 高 | 冻结接口（第三节）：W7 只建 `core/security.py`，W6 一行装配 + `try/except ImportError` |
| 分页形状变更打爆前端 | 高 | W9 D.4 兼容渲染两种形状；W8 不改 bot/hot 域 `page/page_size` 口径 |
| compose 限资源压垮 worker | 中 | A.4.1 先量测基线再设 limits；`read_only` 需配 `tmpfs` 否则 PG/tmp 写失败 |
| `.nvmrc` 引入 Node 主版本跳变 | 中 | A.4.3 对齐到既有 `node:24-alpine`；跑全量 CI + e2e 验证 |
| 限流 Redis 不可达导致全站 429 | 中 | B.1.1 明确 **fail-open**（可用性优先） |
| 覆盖率门禁首次即红 | 中 | E.2.1 以**当前实测基线**为下限（防回退，不设高目标） |
| 契约 DTO 与后端响应漂移 | 中 | E.1.4 OpenAPI 生成 + 双向 diff，不纯手写 |

---

## 第七节 前提与局限

**前提**：PG（5433）与 Redis（6380）可达；`PUSH_SECRET_MASTER_KEY`/`ENGINE_KEY_MASTER_KEY` 已配；Node 24 + pnpm 9.15.9 可用。

**显式排除（非遗漏，单独立项）**：
- **目录迁移 `apps/`**（E.5）：与五路互斥，须功能冻结后单独一轮。
- **RagflowAdapter / SaaS 引擎实接**：依赖主平台排期（ADR-0004 P2/P3）。
- **`BotBinding` 死表处置**：需产品拍板接线或删表（`admin.py:16` 已自认开放项）。
- **真后端 e2e 解阻（OIDC 身份替身）**：需主平台白名单，本轮仅记录。
- **CORS**：**明确不加**（同源代理下负收益，见 B.4.2）。
- **向量聚簇 / pgvector**：TF-IDF 满足当前量级，升级路径独立立项。

**局限**：本大纲缺口计数基于 `main @ 2fa95f0` + 工作区未提交改动的静态扫描（grep/AST/`git diff`），未做运行期压测；性能类（C.1.5/C.3.2）真实影响需压测确认。优先级为工程判断，`C.6`/`A.4.1`/`B.7.1` 最终需产品按节奏拍板。
