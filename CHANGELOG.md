# Changelog

本项目所有值得记录的变化都写在此文件。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> **收录口径（重要）**：本文件**只收录已实现的事实**（含明确的"部分实现"限定语），
> 不写入计划中/在途功能。每条目末尾标注来源提交短 hash（`git log` 可对）。
>
> **版本边界口径（WD 补注，2026-09-30）**：本仓库**尚无 tag**，版本段是按
> `docs/04_engineering/roadmap.md` 的**阶段定义 + 提交日期**划出的里程碑节点，而非打过的 tag。
> 划分依据（`git log --date=short`）：
> - `v0.3` = 2026-09-29 的提交（`dca56b0` `3b548b1` `1c89b2e` `90c4e2f` `e786d78`）
> - `v0.4` = 2026-09-30 的推送域提交（`0879882` `90618b7` 及 `d2678d7` 的 /bots 部分）
> - `v0.5` = 2026-09-30 的热点域 + 工程基建提交（`25181c1` `d2678d7` 的 /hot 部分
>   `cac6a22` `e5bf6cb` `a6889b0`）
>
> 两段同日完成，故工程基建类（CI 真实化 / 契约冻结 / 文档修正）归入最后完成的 `v0.5`。
> 发布节点确定后，据此加 tag 即可，无需再挪动条目。

## [Unreleased]

### Added

- **观测与运行时硬化（W6-W10，`main @ 8b1b5f2`）**：structlog 双模日志（`core/logging.py`，
  prod=JSON/dev=Console，启动 `main.py:249`）；Prometheus 指标 8 族 + `/metrics` 独立 router
  `include_in_schema=False`（`core/metrics.py` + `MetricsMiddleware`）；`/live` `/ready` 探针 +
  `core/schema_guard.py`（schema 不一致 503）；运行时安全中间件限流/体限/安全头
  （`core/security.py`，经 `install_security_middlewares`）；两 Dockerfile 多阶段 + uid1000 +
  HEALTHCHECK，compose 全服务 logging/limits，backend/scheduler/worker 三常驻服务
  read_only/tmpfs/cap_drop/no-new-privileges（数据服务不设只读根）；
  运行期告警三类（`core/alerting.py`）
- **站内通知持久化底座（R1.2a，2026-10-08）**：`Notification` 实体 + 迁移 `ab1005w5a`
  （`sub` SSO 锚 + 广播标记 + `(sub, created_at)` 复合索引），作为离线补投存储层；
  写侧落库/读侧 `/history`/前端补投待建 —— `backend/app/models/bothot_entities.py`
- **CI 门禁补全（WD）**：`frontend` job 增 Playwright **mock UI e2e**（`PORT=3456`，**阻塞门禁**，
  产物以 `next build` + `NEXT_PUBLIC_API_MOCK=true` 生成）；新增 **`compose-smoke` job**
  （build backend 镜像 → 起核心服务 → 跑 `scripts/smoke.sh`：`/api/v1/system/health` +
  scheduler/worker 心跳新鲜度）；`backend` job 在迁移后增 **alembic 单头断言**（head 数 == 1，
  防 multi-head 分叉静默不落库）—— `.github/workflows/ci.yml`
- **README「部署指南」小节（WD）**：compose 环境变量清单（含 `PUSH_SECRET_MASTER_KEY` /
  `ENGINE_KEY_MASTER_KEY` 等必填主密钥）+ 端口纪律表 —— `README.md`
- **过时规划文档归档（WD）**：`当前任务规划.md` → `docs/09_archive/superseded/`（附归档标识头，
  说明其成文于 W1–W5 之前、约七成已过期）

### Fixed

- **CI 首跑红灯修复（`08c3935..7bdb964`）**：契约幽灵依赖清零 + 前端镜像 context 升根、
  `security.yml` 解析即拒 + 加载期 env 白名单越界、mock 产物缓存复用 + 排序断言时间戳并列、
  UP017 风格清零
- **`test_security_middleware` 跨平台假阳性（R0.1，2026-10-08）**：`_BASH` 由 `shutil.which`
  升级为功能探针（`bash -c 'exit 0'` 非 0 视同不可用→skip），并给子进程补 UTF-8 解码——
  修复 Windows 无 WSL 下 2 例假阳性失败 —— `backend/tests/test_security_middleware.py`

### Changed

- **backlog 全量回填代码实证状态（WD）**：`PUSH-007/008`、`TECH-001/002`、`HOT-001~004`、
  `FE-001~004`、`TEST-001~003`、`MIG-003`、`DOC-001/002` 逐条对照 `main @ 2fa95f0` 代码更新，
  每处附 `文件:行号`；并新增 `FE-005`（站内通知**前端订阅侧**缺失）与 `PUSH-009`（推送失败重试）
  —— `docs/04_engineering/backlog.md`
- **CHANGELOG 切分版本段（WD）**：由「全部挤在 Unreleased」改为 `v0.3 / v0.4 / v0.5` 三段
  + 空的 `Unreleased` 承接增量 —— 本文件
- **`SKIP_BASELINE` 复核（WD）**：合并后连库用例由 742 → **796** 条（+54），
  但 skip 数**未随之增长**（实测 `796 passed, 4 skipped`，PG 不可达类 skip = 0）→ 阈值维持 `6`；
  并在 CI 注释中固化该复核结论 —— `.github/workflows/ci.yml`
- **真实后端 e2e 由「死断言」改为环境闸（WD）**：原 `test.skip(true, …)` 为**无条件恒跳过**，
  套件永不可执行；现改为 `E2E_REAL_BACKEND=1` 时真实执行，文章 URL 可由 `E2E_ARTICLE_URL` 覆盖，
  并配 CI `continue-on-error` + 仓库变量闸 —— `frontend/e2e/real-backend.spec.ts`
- **前端镜像构建上下文升为仓库根**：前端经 tsconfig paths 引用 `packages/contracts`，
  `next build` 期类型检查需要其可见，旧 `context: ../frontend` 在镜像内取不到 → build 必炸。
  现为 `context: ..` + `dockerfile: frontend/Dockerfile`，builder 将契约源放 `/packages`；
  新增根 `.dockerignore` 控制上下文体积（仅 frontend/ + packages/ 入镜像构建）
  —— `frontend/Dockerfile` `docker/compose.yml` `.dockerignore`
- **compose `BASE_IMAGE` 默认值回归 node:24 锚**：原 `${BASE_IMAGE:-node:20-alpine}` 会
  **静默覆盖** Dockerfile 的 node:24 锚（3.4 版本锚统一）；`guard-versions` 扩围新增
  compose 侧锚比对，漂移即红 —— `docker/compose.yml` `Makefile`
- **本地门禁补漂移拦截**：`preflight.sh` 前端段增 `pnpm install --frozen-lockfile
  --lockfile-only`（只解析校验不装包；漂移副本实测 exit 1，报错与 CI 逐字一致）；
  `ci-repro-frontend.sh` 的 `git archive` 补上 `packages/` 并挂载容器 `/packages`
  （原只带 frontend，容器内契约路径缺失，复现口径本身失真）
  —— `scripts/preflight.sh` `frontend/scripts/ci-repro-frontend.sh`

### Fixed

- **security.yml 加载期 0-job 秒红（三轮首跑实证）**：job 级 `env:` 使用了
  `runner.temp` 与 `coalesce()`——该层表达式白名单均不含二者，GitHub 表现为
  工作流加载被拒（0 job、created==updated、API 无错误详情，REST 排查通道全部
  静默）。真凶由 actionlint 定位（本地官方 workflow-parser 只查 schema，查不出
  上下文可用性）。修复：`VERDICT_DIR` 改静态 `/tmp/security-verdicts`；
  `SECURITY_GATE_ENFORCE` 改 `${{ vars.X }}` 直引（消费侧 `${X:-1}` 兜底已存在）。
  防再犯：ci.yml 新增 **`workflow-lint` job**（actionlint v1.7.12 钉版，全部
  workflow 静态检查）—— `.github/workflows/security.yml` `.github/workflows/ci.yml`
- **CI frontend 13 秒红：`@bothot/contracts` 幽灵依赖（2026-09-30 首跑实证）**：W9 曾把
  `workspace:*` 写入 `frontend/package.json`，但仓库**无 pnpm workspace 根**且 lockfile
  从未收入该条目——本地 tsc/vitest 因「tsconfig paths + 纯 `import type` 擦除」假绿，
  CI 第一步 `pnpm install --frozen-lockfile` 因 package.json ↔ lockfile 声明漂移必红。
  修复 = 删除该从未生效的依赖声明，契约消费机制明确为 **纯 tsconfig paths 类型解析**
  （机制本身不变，仅删幽灵声明；运行时导入若未来出现，next build 期即报错，非静默漏过）
  —— `frontend/package.json` `frontend/tsconfig.json`
- **`Makefile` `guard-ports` fail-open（WD）**：原实现两段 `grep` 用 `\` 续行后，
  `if [ $? -eq 0 ]` 取到的是**第二条（前端）grep** 的退出码——后端/编排侧独有 `3333`
  命中时被静默放过，守卫形同虚设。改为两段各自捕获输出、各自判据，任一命中即 `exit 1`
  —— `Makefile`（本地三场景实测：干净 exit 0；仅后端注入 exit 1；仅前端注入 exit 1）

## [v0.5] - 2026-09-30

> 主题：AIHOT 热点能力融合落地 + 工程基建（CI 真实化 / 契约冻结 / 文档修正）。

### Added

- 热点域落地（v0.5）：聚簇（标题字 bigram TF-IDF 单链接凝聚，Job type=`hot_cluster`）、
  热度评分（48h 独立来源加权 + 24h 半衰 + 状态机）、Feed 三类生产者
  （`(item_type,ref_id)` upsert，迁移 `ab1004w2a`）、日报（LLM 摘要失败降级为正文首段截断，
  每日 06:30 自动生成前一日日报；业务日界 Asia/Shanghai）—— `25181c1`
- 前端热点中心增强：/hot 聚簇触发按钮 + 热度条形 + 状态过滤；/hot/daily react-markdown
  真渲染 + 翻页（与 v0.4 的 /bots Tab 同属提交 `d2678d7`）—— `d2678d7`
- **共享契约冻结（W5）**：`packages/contracts/` 落地 `PageResult<T>` / `ApiResponse<T>` /
  `ApiErrorCode` 三类，均标注后端单一来源 `文件:行号`，配 `package.json` + `tsconfig.json`
  （`emitDeclarationOnly` → 仅产 `.d.ts`）—— `cac6a22`
- **冒烟脚本（W5）**：`scripts/smoke.sh`——`docker compose up -d` 后轮询
  `/api/v1/system/health` 并校验 `process_heartbeats` 中 scheduler/worker 心跳新鲜度，
  输出 PASS/FAIL —— `cac6a22`

### Changed

- **CI 后端测试门禁真实化（W5）**：`backend` job 增加 `postgres:16` service
  （凭据/端口与 `backend/tests/conftest.py:36` 默认 DSN 对齐）与 `alembic upgrade head`
  迁移步骤；新增 skip 门禁（PG 不可达类 skip 直接失败 + skip 总数超基线失败）—— `cac6a22`
- **文档漂移修复（W5）**：`docs/04_engineering/roadmap.md` 回填 v0.4 勾选状态；
  `backlog.md` 将 HOT-003/HOT-004 由 ✅ 更正为 🔧 并注明缺口；`AGENTS.md` 修正站内通知/
  热点/密钥加密三处表述；`conventions.md` §6.1 补渠道密钥 base64 过渡态说明；
  `project-map.md` 将 `06_validation/` 由"预留"更正为"已启用" —— `cac6a22`
- 热点域时区口径统一：`hot.py` 4 处 `datetime.utcnow()`（naive、已弃用）→
  `datetime.now(Asia/Shanghai)` 业务日界 —— `25181c1`
- `docker/compose.yml` 注入 `PUSH_SECRET_MASTER_KEY`；旧调度测试迁移 —— `e5bf6cb`
- 集成终态同步：roadmap v0.4/v0.5 完成勾选 + `AGENTS.md` 状态 + CHANGELOG 收录 +
  新增 `.gitattributes` —— `a6889b0`

### Fixed

- 集成审查发现并修复的两处 W1 缺陷：渠道 secret **AAD 绑定空串**（创建时 id 未生成即加密，
  读取侧必解密失败 → 改为显式预生成 id 后加密）；`bots` 域**写端点收参与前端契约错位**
  （后端标量查询参数收不到 JSON body → 改为 Pydantic body 模型）—— `0879882`
- 旧 `test_push_providers.py` 引用已删除的 `_parse_cron_next`（ImportError ×5）→
  迁移到 `app.services.cron_expr` —— `e5bf6cb`

## [v0.4] - 2026-09-30

> 主题：多渠道推送真实投递 + Cron 全生命周期 + 事件触发 + 密钥安全落库。

### Added

- 六渠道推送 Provider 真实投递：飞书、钉钉、企业微信、通用 Webhook、微信 ClawBot、站内通知
  （`backend/app/providers/push/`；站内通知为 Redis pub/sub **投递侧**，前端订阅侧未实现）—— `dca56b0`
- Bot 渠道管理能力：渠道 CRUD、测试推送、推送日志、推送任务 CRUD 与手动触发
  （`backend/app/api/v1/bots.py`）—— `dca56b0`
- PushScheduler 定时调度器：60s 扫描，在 backend 进程内由 FastAPI lifespan 启动
  （`backend/app/main.py:247`）—— `dca56b0` `1c89b2e`
- Cron 解析统一收口 `services/cron_expr.py`：croniter 完整 5 段式 + 三种简写兼容
  （`HH:MM` / `*/N` / 纯数字分钟）；Cron 任务创建即写 `next_run_at`、新增
  `PUT /api/v1/bots/tasks/{id}`（编辑/暂停恢复）、run-now 补算下次执行 —— `0879882`
- 渠道密钥 AES-256-GCM 落库：`core/secret_crypto.py`（AAD 绑定 bot_channel.id，
  `PUSH_SECRET_MASTER_KEY` fail-closed）+ 存量 base64 重加密迁移 `ab1004w1a` —— `0879882`
- 推送调度器并发安全：FOR UPDATE SKIP LOCKED 短锁领取 + 单任务异常隔离
  （多副本部署不再重复投递）—— `90618b7`
- 事件触发推送（PUSH-008）：PG outbox 表 `push_events`（迁移 `ab1004w3a`）——
  worker 进程 emit（文章入库/聚簇/日报）、backend 调度器 claim 消费；
  模板变量 `{space_name}/{doc_title}/{hot_topic}/{topic_count}` —— `90618b7`
- 前端推送任务管理：/bots 双 Tab（渠道 / 任务）+ `PushTasksTab` + `CronEditor`
  （列表/创建/编辑/暂停恢复/删除/立即执行/日志；与 v0.5 的 /hot 增强同属提交 `d2678d7`）—— `d2678d7`

### Changed

- 依赖清理：移除 `celery[redis]`（全仓零接线，且与"不引入 Redis 队列"约束冲突）；
  新增 `croniter` —— `0879882`
- 文档状态口径修正：推送 Provider 由"占位"更正为"已实现真实投递"，
  PushScheduler 归属更正为 backend 进程内 —— `1c89b2e`

### Fixed

- **Cron 任务创建即永不触发**（调度器过滤 `next_run_at IS NOT NULL`，创建端点不写该列）—— `0879882`
- **渠道 secret AAD 绑定空串**：创建时 id 未生成即加密（AAD=""），读取侧以 channel id
  解密必失败——改为显式预生成 id 后加密 —— `0879882`（集成审查发现）
- **bots 域写端点收参与前端契约错位**：后端标量查询参数收不到前端 JSON body（创建恒 400、
  更新静默 no-op）——改为 Pydantic body 模型（对齐 spaces 域惯例），前端零改动 —— `0879882`
  （集成审查发现）
- `push_port.py` 双头推送语义（占位 delivered=False 与真实投递并存）收敛删除（TECH-001）—— `0879882`

## [v0.3] - 2026-09-29

> 主题：BotHot 从 AideanBot 升级基线 + 文档架构与目录结构规范化。
> （两类工作同日落地，无 tag 分隔，故并列于本段。）

### Added

- BotHot 从 AideanBot 升级：多渠道推送骨架 + AIHOT 热点数据模型与读侧 API +
  前端统一 3200 端口（`dca56b0`）
- BotHot 扩展数据模型 7 张表（bot_channels / push_tasks / push_logs / hot_topics /
  hot_topic_articles / daily_reports / feed_items）+ Alembic 迁移 `ab1004bh01` —— `dca56b0`
- 前端页面：机器人管理（`/bots`）、热点中心（`/hot`）、日报（`/hot/daily`）—— `dca56b0`
- 四平台文章来源 Provider：Dajiala 极致了、JustOneAPI、TikHub、Wellbyte 数井
  （`backend/app/providers/article_sources/`，含发现注册与按成本排序的付费详情兜底协调器）—— `3b548b1`
- `ConfigurationError`（code `50003`）异常类 —— `3b548b1`
- 文章采集测试证据归档：`docs/06_validation/evidence/channeltest-20260929/`
  （4 平台活体实测，TC 编号逐条可对）—— `3b548b1`
- 文档体系 `docs/`（00_governance ~ 04_engineering，23 个文件）；
  `apps/` monorepo 目录骨架；`packages/contracts/` 契约包骨架 —— `1c89b2e`
- `Makefile` 27 个 target（含 `guard-ports` / `guard-structure` 架构守卫）—— `1c89b2e`

### Changed

- 项目由 AideanBot 升级更名为 BotHot（session cookie / 容器名 / 项目名 / 前端端口 3200）—— `dca56b0`
- 后端容器内部端口由 8000 漂移修正为 3300（与 compose、前端 rewrites 对齐）—— `1c89b2e`
- 文章来源证据口径由"行级标签"改为**格级证据**（每个 ✅/⚠️/❌ 自带 TC 编号与级别）；
  补齐实时性/标识体系/请求形态/失败计费/价格漂移五个决策维度 —— `90c4e2f`
- 计价单位纠正：TikHub 为 **USD/请求**（非 credits），Wellbyte 为 credits，
  Dajiala / JustOneAPI 为 CNY —— `90c4e2f`

### Fixed

- 双端 CI 门禁清零：backend（ruff 0.12.12 / mypy / pytest 本地全绿）；
  frontend（typecheck / vitest / build 全绿）—— `e786d78`
- `providers/article_sources/registry.py`：4 个来源工厂函数前移到 `CHANNELS` 之前，
  消除模块导入期 `NameError`（ruff F821）—— `e786d78`
- `push_scheduler.stop()`：`with` 更正为 `async with`（`_suppress_cancel` 仅实现
  `__aenter__`；原实现调用 stop() 必抛 `AttributeError`，调度器停不下来）—— `e786d78`
- 安全：`bots` / `hot` 两个 router 补 `get_current_sub` 登录门禁
  （此前两域全部端点可匿名读写）—— `e786d78`
- 前端 `bots` / `hot` / `hot/daily` 三页补 `usePageTitle`，修复页签标题覆盖守卫 —— `e786d78`
- JustOneAPI 搜索由"返回空列表"更正为真实契约级实现；
  TikHub 详情由返回 `None` 更正为调用 v2 端点（402 时降级）—— `90c4e2f`

---

## 记录约定

- 新增条目请归入 `Unreleased` 对应小节（Added / Changed / Fixed / Removed / Security）。
- **禁止把未实现或仅计划中的功能写进来**——本仓库的历史问题是文档虚报状态，
  条目须能被 `git log` 或代码实证核对。
- 发布时把 `Unreleased` 段落改名成 `## [x.y.z] - YYYY-MM-DD`，并新增空的 `Unreleased`。
