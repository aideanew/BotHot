---
id: TASK-PLAN-v0.8
type: task-plan
title: BotHot 全量剩余任务大纲体系（v0.8）
status: active
owner: engineering
created: 2026-10-08
updated: 2026-10-08
baseline_commit: 7bdb964（main）+ 工作区未提交改动（R1.2a 通知存储底座）
supersedes: docs/05_execution/tasks/TASK-PLAN-v0.7.md（W6–W10 已全部交付合并，其域 A–E 大部分消化）
---

# BotHot 全量剩余任务大纲体系（v0.8）

> **取证基线**：`main @ 7bdb964`（W6–W10 五路 + 5 个 CI 首跑修复 + 集成审查修复已合并）
> + 工作区未提交改动（6 改 + 1 新：Notification 模型/迁移 ab1005w5a/test 修复/e2e 修复/ci 引号/MOCK 门）。
> **唯一标准**：与代码实证一致，每条带 `文件:行` 证据链。
> **编号规则**：`S<阶段>.<任务>.<原子步骤>`，三级层次，原子步骤可独立提交、独立验收。

---

## 第零节 进度裁定（证据链，2026-10-08 实测）

### 0.1 已交付（main @ 7bdb964，勿重造）

| 交付 | 证据 |
|---|---|
| W6 观测：structlog 143 处 / `/metrics` / `/live` / `/ready` / schema_guard | `core/logging.py:1-13`；`core/metrics.py`；`api/v1/system.py:119-145`；prometheus-client + pytest-cov 已入 `pyproject.toml:20/:33` |
| W7 安全：`install_security_middlewares` / 固定窗口限流 / 4MiB 体上限 / 安全头 / 上游 Semaphore ×5 | `core/security.py:462/:184-195/:402/:502`；dajiala.py:77、justoneapi.py:79、tikhub.py:31、wellbyte.py:97、redfox/client.py:84；`core/errors.py:21-22`；`security.yml` 四扫描器 |
| W8 数据：分页 SQL 下推（路由切片 grep=0）/ `limit_offset_query` / 索引断言 / 读缓存 / 批量 UPDATE / 引擎删除闭环 | `api/deps.py:40-50`；`services/subscription.py:160`、`services/spaces.py:645-754`；`tests/test_indexes.py`；`core/cache.py`（admin.py:463 消费）；`hot_scorer.py:149-160`；`services/spaces.py:236-276` |
| W9 前端：契约消费 7 处 / dynamic×2 + Image×1 / error 12 + loading 11 / Pagination×4 / 通知铃持久化未读数 | `lib/api/{types,bots,hot}.ts`；`components/Pagination.tsx`；`NotificationBell.tsx:24-110` |
| W10 治理：CI 5 job / 覆盖率门禁 75 / SKIP_BASELINE=6 / 单头断言 / `guard-versions` / gen_contracts.py / 6 域 DTO 生成 | `ci.yml:12-364`；`Makefile:143-144`；`scripts/gen_contracts.py`；`packages/contracts/src/{bot,hot,ingest,subscription,knowledge,push_event}/dto.ts` |
| R1.2a 通知存储底座（**未提交**） | `models/bothot_entities.py:264-301`（Notification + `ix_notifications_sub_created`）；`alembic/versions/ab1005w5a_notifications.py`（单头 ✅） |

### 0.2 当前真实缺口（全量清单，后文按阶段展开）

| # | 缺口 | 证据 | 归口 |
|---|---|---|---|
| G1 | 通知四链路未接线：web.py 零落库、无 history 端点、无已读端点、前端无 fetchHistory | `providers/push/web.py:54` 仅 publish；`system.py` grep history=0；`notifications.ts` 导出仅 5 项 | S1 |
| G2 | `assert_pool_capacity` 定义了但生产启动路径零调用（仅 test_indexes.py:61 调用） | `db.py:85`；grep 全仓 2 处 | S0 |
| G3 | 限流 fail-open 日志无节流，Redis 抖动期每请求 1–2 条 + 全栈 | `security.py:193/:298` | S0 |
| G4 | `tsc --noEmit` 软门禁（continue-on-error: true），"严格门禁"名不副实 | `ci.yml:238-240` | S0 |
| G5 | 测试数文档漂移：AGENTS:71「848/2」vs ci.yml:99「796/4」互相矛盾 | 两文件实测 | S0 |
| G6 | backlog 缺 W8 两项交付记载（分页下沉/读缓存 grep=0）；CHANGELOG compose 措辞过宽（read_only 仅 3 服务/cap_drop 2 处，非"全服务"） | `backlog.md`、`CHANGELOG.md` [Unreleased] | S0 |
| G7 | auth 路由域无 error.tsx/loading.tsx（SSO 回调失败无边界兜底）；not-found 仅 3 域 | `app/auth/` 实测 | S0 |
| G8 | docker/.env.example 缺 `PUSH_SECRET_MASTER_KEY`/`ENGINE_KEY_MASTER_KEY`/`ALERT_*`（W5 协调请求遗留） | docker/.env.example | S0 |
| G9 | `.workbuddy/` 未跟踪噪音未入 .gitignore | git status | S0 |
| G10 | `bot_channels.extra_config` 明文 JSON（飞书 app_secret/钉钉 token），主密钥不覆盖 | `bothot_entities.py:36`；`push_scheduler.py:191` 透传 | S2 |
| G11 | 告警功能就绪但生产恒短路（compose 无 ALERT_ 变量） | backlog:137-138 自述 | S2 |
| G12 | BotBinding 死表 / Ragflow+Saas 未实接 / 真后端 e2e 三前置 / pgvector | `entities.py:223`；`engine_port.py:114-180`；`real-backend.spec.ts:21` | S2 |
| G13 | v0.7 目录迁移零动工：apps/ 183 个 .gitkeep，backend/frontend 原样 | `apps/` 实测 | S3 |
| G14 | 域 DTO 死代码：6 域已生成但 index.ts 不导出、前端零消费 | `packages/contracts/src/index.ts` | S3 |
| G15 | v1.0 发布链未启动（全量门禁复跑/文档复核/推送 GitHub） | roadmap:112-118 | S4 |

---

## 〇.5 S0 执行收口（2026-10-08 实测，全部完成 ✅）

> 提交链（main @ `01a08a6`，ahead 8 未推送）：`87ad712` → `7dfed5a` → `c56b642` → `5fe5a4f` → `8c9026c` → `5476807` → `cf0022a` → `01a08a6`。

| 任务 | 状态 | 提交 | 实测证据 |
|---|---|---|---|
| S0.1 R1.2a 落定 | ✅ | `87ad712`/`7dfed5a`/`c56b642` | 隔离 PG 5547：单头 `ab1005w5a`、建表+复合索引；后端全量 **943 passed / 7 skipped**（PG 类 skip=0；7 条=LangBot/Redis 死口 5 + Windows bash 探针 2） |
| S0.2 池断言接线（G2） | ✅ | `5fe5a4f` | `db.py` engine 参数化 + main/scheduler/worker 三入口 fail-fast；mock engine 三分支用例（junitxml 5 passed） |
| S0.3 限流日志节流（G3） | ✅ | `8c9026c` | 60s 窗口节流，3 用例（窗口内 1 条/越窗复燃/端到端 6 请求 ≤1 条） |
| S0.4 tsc 转硬门禁（G4） | ✅ | `5476807` | 本地 tsc 零错误实跑后摘 `continue-on-error`（ci.yml ±3） |
| S0.5 文档卫生（G5/G6/G8/G9） | ✅ | `cf0022a` + `c56b642` | 测试数统一 943/7、CHANGELOG 措辞收窄、.env.example 补双主密钥+ALERT、.gitignore 补 .workbuddy/ |
| S0.6 auth 域边界（G7） | ✅ | `cf0022a` | `frontend/app/auth/error.tsx`+`loading.tsx`；SSO 失败 mock e2e 断言**登记待办**（mock 态登录不经过 callback 路由，无现成链路） |
| vitest MOCK 门回归 | ✅ | `01a08a6` | `notifications.ts:103` 门加 `NODE_ENV!=="test"` 豁免；**独立复跑 vitest 全量 359/359 绿（exit 0，2026-10-08 11:35）** |

**协作记录**：S0 由两个并行会话交错完成（含 S0.2 测试文件的 mock engine 方案、`01a08a6` vitest 修复），全部经 git 对象库 + 独立实测交叉验证；无编辑战，磁盘终态自洽。

**0.2 节缺口对账**：G2–G9 全部闭合 ✅；G1（通知四链路）→ S1；G10–G15 → S2–S4 维持原排期。

---

## 第一节 全量剩余任务大纲体系

### 阶段 S0：在途落定与 P0 缺陷修复（最先执行，阻塞 S1）

#### S0.1 工作区 R1.2a 落定
- **S0.1.a** 提交 6 改 + 1 新（Notification 模型/__init__ 导出/迁移 ab1005w5a/test_security_middleware bash 探针/e2e 断言锚/ci.yml 引号/MOCK 门），只 `git add` 名下 7 路径，禁 `git add -A`
- **S0.1.b** 隔离 PG（5544+ 端口，勿碰 5433 原项目）`alembic upgrade head` 验证 ab1005w5a 建表 + 单头；全量 pytest 复跑，实测数回填文档

#### S0.2 连接池断言生产接线（G2）
- **S0.2.a** `main.py` lifespan 内 create_engine 后调用 `assert_pool_capacity(expected_processes=N)`
- **S0.2.b** `scheduler.py` / `job_worker.py` 启动入口各自调用（进程数口径=1）
- **S0.2.c** 断言失败 fail-fast：structlog error + 拒绝启动；补启动失败分支单测

#### S0.3 限流 fail-open 日志节流（G3）
- **S0.3.a** `security.py:193/:298` 加 per-key 时间窗去重（60s 内同 key 仅 1 条，`exc_info` 仅首条带全栈）
- **S0.3.b** 单测：模拟 Redis 连续异常 N 次，断言日志条数 ≤ 窗口去重上界

#### S0.4 tsc 软门禁转硬（G4）
- **S0.4.a** 本地实跑 `tsc --noEmit` 取当前错误全清单
- **S0.4.b** 修至零错误（含 6 域 DTO 若接线则一并过）
- **S0.4.c** `ci.yml:239` 移除 `continue-on-error: true`，注释与行为对齐

#### S0.5 文档与仓库卫生（G5/G6/G8/G9）
- **S0.5.a** `.gitignore` 追加 `.workbuddy/`
- **S0.5.b** AGENTS.md:71 测试数统一为 S0.1.b 实测值（并注明口径日期）
- **S0.5.c** backlog 补记 W8 分页下沉 + 读缓存两条交付（带文件:行）
- **S0.5.d** CHANGELOG compose 措辞收窄：read_only 3 服务（:178/:328/:375）、cap_drop 2 处，删"全服务"表述
- **S0.5.e** docker/.env.example 补 `PUSH_SECRET_MASTER_KEY` / `ENGINE_KEY_MASTER_KEY` / `ALERT_*`（注释默认关闭）

#### S0.6 auth 域边界补齐（G7）
- **S0.6.a** 新建 `frontend/app/auth/error.tsx` + `loading.tsx`（对齐既有 11 域样板）
- **S0.6.b** SSO 回调失败路径断言进 mock e2e（trunk.spec 登录失败分支）

### 阶段 S1：通知持久化全链路 R1.2（P0，存储层已建、四链路全空）

> 纪律前提：ab1005w5a 已随 upgrade head 进所有环境建表，但**零写入方 = 死表**（与 BotBinding 同类病史）。本轮必须闭环，否则回滚迁移。

#### S1.1 写侧落库
- **S1.1.a** `providers/push/web.py`：publish 同时 INSERT `Notification`（broadcast 载荷 → `sub=""`、`is_broadcast=True`；定向 → sub 锚）
- **S1.1.b** 降级策略：落库失败不阻断 publish（structlog error，投递优先）；复用 `get_or_set` 同款 Redis 异常处理风格
- **S1.1.c** 连库单测：投递一次 → 断言 notifications 行存在、字段与载荷一致

#### S1.2 读侧 history 端点
- **S1.2.a** `api/v1/system.py` 新增 `GET /notifications/history`：`Depends(limit_offset_query)`（复用 C.1 口径，limit≤100）
- **S1.2.b** 过滤 `(sub == 当前用户 OR is_broadcast)`，按 `created_at` 倒序——热路走 `ix_notifications_sub_created`（EXPLAIN 留证非 Seq Scan）
- **S1.2.c** 响应形状 `{items,total,limit,offset}`（冻结口径），载荷字段与 SSE 帧一一对应
- **S1.2.d** 匿名探活隔离：不入 session security 标注（对照 `_annotate_session_security` 白名单处理）

#### S1.3 已读回执
- **S1.3.a** `PUT /notifications/read`：body 支持 `{id}` 单条与 `{before: ts}` 批量两模式，写 `read_at`
- **S1.3.b** 未读数来源：history 增 `unread_total` 字段（`read_at IS NULL` 计数），避免前端二次拉取
- **S1.3.c** 单测：单条/批量/越权（sub 不匹配 → 404 语义）

#### S1.4 前端补投接线
- **S1.4.a** `lib/api/notifications.ts` 增 `fetchHistory(limit,offset)` / `markRead(...)`（走 http.ts MOCK 网关，mock 态返回演示数据）
- **S1.4.b** `NotificationBell` 首连拉 history + `mergeFromHistory`（接线既有 ：56 预留桩）；去重复用 ：99-110 的 5s 窗口 key（id 或 content hash）
- **S1.4.c** 展开下拉时调 markRead 同步服务端；localStorage 未读数与服务端 unread_total 对账（取大者，防丢）
- **S1.4.d** mock e2e：补通知历史渲染路径断言

#### S1.5 验收
- **S1.5.a** 连库端到端：emit→落库→history→read→unread 归零
- **S1.5.b** SKIP_BASELINE / COV_BASELINE 复核；backlog NOTIF-001 回填 ✅

### 阶段 S2：遗留项处置（可拍板后并行排期）

#### S2.1 extra_config 明文加密（G10，P1 安全）
- **S2.1.a** 迁移：读全量 `bot_channels.extra_config` → AES-256-GCM 再密（复用 `core/secret_crypto.py`，AAD 绑定 channel id + 字段名）
- **S2.1.b** 读侧改造：`push_scheduler.py:191` / 相关 provider 取用前解密
- **S2.1.c** `docs/07_release/key-rotation-sop.md` 增补该字段的轮换语义；守卫测试覆盖

#### S2.2 告警启用（G11）
- **S2.2.a** compose 注入 `ALERT_*` 变量（默认接飞书/钉钉既有 provider）
- **S2.2.b** 演练三类告警：进程心跳缺失 / Job 队列积压 / 推送连败，留演练证据入 docs/06_validation

#### S2.3 BotBinding 死表处置（需产品拍板：接线或删表迁移）
#### S2.4 真后端 e2e 解阻（前置：Compose 栈常驻 + 主平台 OIDC redirect_uri 白名单 + 真实文章 URL）
#### S2.5 RagflowAdapter/SaasAdapter 实接（ADR-0004 P2/P3，依赖主平台排期）
#### S2.6 HOT-005 向量聚簇（pgvector，量级触发后单独立项）
#### S2.7 `engines.py list_engines` 有界豁免注释固化（5 引擎位清单，非分页遗漏）

### 阶段 S3：v0.7 目录迁移 apps/ monorepo（功能冻结后压轴，与 S0–S2 互斥）

#### S3.1 迁移前置
- **S3.1.a** 宣告功能冻结，main 基线全绿
- **S3.1.b** 外部备份 `cp -r` 至 `/e/Code/_AideanBotHot_backup_*`
- **S3.1.c** 迁移方案定稿（git mv 保历史；CI/Makefile/Dockerfile 路径映射表）

#### S3.2 后端迁移 backend/ → apps/api/
- **S3.2.a** `app/` + `alembic/` + `pyproject.toml` + `tests/` 整体迁移
- **S3.2.b** compose/Dockerfile/CI build context 路径同步
- **S3.2.c** 迁移后隔离 PG 全量 pytest 复跑对齐基线

#### S3.3 前端迁移 frontend/ → apps/web/
- **S3.3.a** `app/` + `components/` + `lib/` + `e2e/` 迁移；pnpm-workspace 路径更新
- **S3.3.b** e2e 端口纪律复核（3200，禁 3333）

#### S3.4 契约接线（G14，与迁移合并做）
- **S3.4.a** `packages/contracts/src/index.ts` 导出 6 域 DTO（chat/engine/identity 三空骨架补齐或显式标注延后）
- **S3.4.b** 前端 `lib/api/*` 逐域消费域 DTO，删本地重复定义
- **S3.4.c** `gen_contracts.py --check` 从"仅生成门禁"升级为双向 diff 硬门禁（后端 OpenAPI 漂移即红）

#### S3.5 收尾
- **S3.5.a** database/infra 目录迁移；183 个 `.gitkeep` 清理
- **S3.5.b** 全量门禁复跑：pytest + e2e + compose-smoke + security.yml + guard-ports/guard-versions
- **S3.5.c** project-structure-design.md 与 roadmap v0.7 段回填

### 阶段 S4：v1.0 正式发布

#### S4.1 发布门禁
- **S4.1.a** 全量测试：后端（PG 真跑、skip 门禁）+ 前端 vitest + mock e2e + compose-smoke 全绿
- **S4.1.b** 覆盖率基线自 75 上调至实测值；SKIP_BASELINE 复核
- **S4.1.c** security.yml 四扫描器零高危

#### S4.2 文档定稿
- **S4.2.a** README（部署指南/端口纪律/env 清单）与 AGENTS「当前项目状态」全量复核，以实测为准
- **S4.2.b** CHANGELOG 切 v0.6.5/v0.7/v1.0 段（历史交付归段，不留 Unreleased 悬置）

#### S4.3 发布动作
- **S4.3.a** 推送 GitHub `aideanew/BotHot`（走 `github-aideanew` SSH 别名 + 10808 代理；push 后 `git ls-remote` 核验远端 commit）
- **S4.3.b** 打 tag `v1.0.0`；CHANGELOG 附 tag 链接

---

## 第二节 执行顺序与依赖

```
S0（落定+P0 修复）─→ S1（通知四链路，依赖 S0.1 的表基线）
S2 与 S0/S1 并行可排（S2.1 加密建议在 S3 前完成，避免迁移放大改动面）
S3（目录迁移）─→ 依赖 S0–S1 完成后的功能冻结
S4（发布）─→ 依赖 S3 全绿
```

**关键路径**：S0.1 → S1 → S3 → S4；S2 全程旁路。

## 第三节 验收标准

1. 门禁全绿：ruff + mypy + pytest（连库）+ 单头断言 + tsc（**硬门禁**）+ vitest + mock e2e + compose-smoke。
2. 通知链路：emit→落库→history→read→前端补投，全链实测证据（文件:行 + 命令输出）。
3. 无死表：notifications 表有读写双方；BotBinding 处置有结论（接线或删）。
4. 文档零漂移：AGENTS/backlog/CHANGELOG/roadmap 数字与描述以本轮实测为准。
5. 禁改项：不加 CORS；不碰 AideanBot 原项目；不 `git rm`；`.workbuddy/` 只入 .gitignore 不删除。

## 第四节 前提与局限

- **前提**：隔离 PG 可建（勿用 5433——那是 AideanBot 原项目）；双主密钥 env 已配；Node 24 + pnpm 9.15.9。
- **局限**：静态取证（grep/AST/git），S1 性能与 S3 迁移风险需运行期验证；S2.3/S2.4/S2.5 依赖外部拍板，排期弹性。
- **显式排除**：CORS（同源代理下负收益）；pgvector（S2.6 单独立项）。
