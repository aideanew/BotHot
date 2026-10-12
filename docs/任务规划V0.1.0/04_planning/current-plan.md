---
id: CURRENT-PLAN-20261012
type: plan
title: BotHot 剩余任务分配与执行规划（v1.0.0 之后）
status: proposed
owner: engineering
created: 2026-10-12
updated: 2026-10-12
baseline_commit: 60e57231b1a2fed5ab566290e25f02c16b0e60d3
supersedes_candidate: docs/05_execution/tasks/TASK-PLAN-v0.9.md（批准后由人裁定是否替代）
---

# BotHot 剩余任务分配与执行规划

> 本文件是规划产物，不是实现。所有「✅ 已有」都附证据；没有证据的地方标「未验证」。
> 状态 `proposed`：在 §12 待裁决项被人裁决前，S2 / S7 / S8 不得开工。

---

## 1. 规划快照

```yaml
snapshot:
  规划日期: 2026-10-12（Asia/Shanghai）
  仓库: https://github.com/aideanew/BotHot（public）
  git_branch: main
  git_commit: 60e57231b1a2fed5ab566290e25f02c16b0e60d3   # 2026-10-09 16:45 +0800
  最新 tag: v1.0.0 → c19fe87（HEAD 领先 tag 15 个提交）
  工作区是否干净: true（全新 clone，git status 为空）
  提交总数: 93
  需求文档清单:
    - docs/02_requirements/product-requirements.md   最后修改 2026-09-29
    - docs/01_product/product-scope.md               最后修改 2026-09-29
    - docs/01_product/product-goals.md               最后修改 2026-09-29
    - docs/02_requirements/inbox/                     仅 README，无原始需求
    - docs/04_engineering/backlog.md                 最后修改 2026-10-09
    - docs/04_engineering/roadmap.md                 最后修改 2026-10-08
    - docs/05_execution/tasks/TASK-PLAN-v0.9.md      最后修改 2026-10-08
  代码文件数:
    git_ls_files_总数: 4958
    其中_.project_第三方源码: 4385（125M，7 个外部项目）
    其中_apps: 389
    非_.project_文件: 573（含 apps 389）
  后端测试文件: apps/api/tests 76 个文件，def test_ 共 895 个
  前端测试: apps/web/tests 45 个文件；e2e 5 个 spec
  alembic: 18 个版本，单头 ab1005w5b
  测试命令（来自 .github/workflows/ci.yml 与 Makefile）:
    后端: cd apps/api && ruff check app tests && mypy app && python -m alembic upgrade head && pytest tests/ -q   # 需 PG
    契约: python scripts/gen_contracts.py --check
    前端: cd apps/web && pnpm install --frozen-lockfile && pnpm run typecheck && pnpm exec tsc --noEmit && pnpm run test:unit && pnpm run build
    e2e: cd apps/web && pnpm run test:e2e
    编排: docker compose -f docker/compose.yml -f docker/compose.ci.yml config --quiet && bash scripts/smoke.sh
    文档: python scripts/check_docs_consistency.py
  CI 状态: HEAD 60e5723 的 CI 与 Security 两个工作流结论均为 success（GitHub Actions run 37906907637 等）
  本次规划未在本地执行: 后端 pytest、前端 vitest/e2e、compose 起栈（无 PG 与共享底座）；仅本地执行了 check_docs_consistency.py（20/20 通过）
```

---

## 2. 事实基线

### 2.1 已确认的事实（有证据）

| # | 事实 | 证据 |
|---|---|---|
| F-01 | v1.0.0 已打 tag 并推送 | `git ls-remote --tags origin` → `v1.0.0^{} = c19fe87` |
| F-02 | 后端 FastAPI，14 个路由模块共 74 个 `@router` 装饰端点（另 engines/subscriptions 用具名 router） | `apps/api/app/api/v1/*.py` |
| F-03 | 数据模型 22 张表：BotHot 新增 9 张（`bothot_entities.py`），继承 13 张（`entities.py`） | `grep __tablename__` |
| F-04 | 角色阶梯 user < operator < admin，授权单一入口 `require_role` | `apps/api/app/services/roles.py` |
| F-05 | 错误码登记表 `ERROR_CODES` 含 10007/10008，**不含 50003**；`ConfigurationError.code=50003` | `apps/api/app/core/errors.py:9-37,222-225` |
| F-06 | 契约包 `errors.ts` 是**手写**的，缺 10007/10008；`gen_contracts.py --check` 不覆盖它 | `packages/contracts/src/common/errors.ts`；`scripts/gen_contracts.py:1-60` |
| F-07 | 前端错误文案表缺 10007/10008/20004/20005/30005/30006/50001/50003，另含后端不存在的 10101/10102/30101/30102/50101 | `apps/web/lib/api/http.ts:26-51` |
| F-08 | 契约域 DTO 是**持久层实体镜像**，不是 API 响应形状；identity/chat/engine 仍为骨架 | `packages/contracts/src/index.ts` 头注 |
| F-09 | 分页双口径并存：bot/hot = page/page_size；知识库/订阅/任务 = limit/offset | `packages/contracts/src/common/pagination.ts` |
| F-10 | `docker/compose.yml:157` 含明文连接串 `bothot_rw:<已轮换·见运维工单>@host.docker.internal:5435`，由 `01f6892`（提交说明是 middleware）引入；仓库为 public；当次 gitleaks 未拦截 | `git log -S <已轮换·见运维工单>`；Security run success |
| F-11 | compose 已不含 postgres/redis 服务，改连「共享底座」PG 5435 / Redis 6379 DB1 | `docker/compose.yml:46-47,157-158` |
| F-12 | 前端 middleware 只放行 `/` 与 `/auth*`；`/hot` `/hot/daily` `/public` 均包 AuthGate | `apps/web/middleware.ts:14-15`；`grep -l AuthGate app` |
| F-13 | middleware 在 mock 构建下短路，e2e 只跑 mock 产物 → 真实态 302 行为没有自动化覆盖 | `middleware.ts:26`；`ci.yml:290-299` |
| F-14 | `check_docs_consistency.py` 未接入 CI 与 preflight | 全仓 grep 仅脚本自身 |
| F-15 | `app.providers.embedding` 生产零调用方（仅 `tests/test_embedding.py`） | grep |
| F-16 | `BotBinding` 除模型定义外仅在注释中出现 | `grep BotBinding app` |
| F-17 | RagflowAdapter / SaaS 适配器方法抛 `NotImplementedError`，注册表排除骨架位；空间删除已降级不回滚 | `providers/engine_port.py:112-170`；`engines.py:142-160` |
| F-18 | SSE 通知帧无 id；落库在投递之后 | `api/v1/system.py:227,259`；`services/push_scheduler.py:222` |
| F-19 | `.project/` 不在根 `.dockerignore`，前端镜像构建上下文会带上 125M | `.dockerignore` |
| F-20 | real-backend e2e 为非阻塞 step（continue-on-error） | `ci.yml:302-305` |
| F-21 | 性能：仅有 2026-10-08 两条 EXPLAIN 留证（0.034ms / 0.38ms），**无端到端延迟基线** | `docs/06_validation/test-results/2026-10-08-notifications-history-explain.md` |

### 2.2 仅来自文档、未在代码中验证

| # | 说法 | 来源 | 未验证原因 |
|---|---|---|---|
| U-01 | 全量 1002 passed / 4 skipped | AGENTS.md | 本次未本地跑 pytest；仅有 CI 绿作间接证据 |
| U-02 | 6 渠道真实投递可达 | backlog PUSH-001~006 | 需外部 webhook，未实测 |
| U-03 | 4 平台文章来源活体可用 | channeltest-20260929 证据 | 外部付费 API，未复测 |
| U-04 | compose-smoke 在 CI 中通过 | run 37906907637 整体 success | 未取 job 级明细 |

### 2.3 文档与代码不一致清单

| # | 文档说法 | 代码事实 | 处置任务 |
|---|---|---|---|
| X-01 | AGENTS/README：PG 5433、Redis 6380，compose 起栈内 postgres/redis | 共享底座 5435/6379，compose 无 PG/Redis | TASK-003（待 D-02） |
| X-02 | README/AGENTS/REQ-C-001：Next.js 14 | `next ^15.5.24`，React 19 | TASK-019 |
| X-03 | conventions §5.2：Node 22；§8 前端镜像 node:22 | `.nvmrc=24.21.0`，`engines.node >=24` | TASK-019 |
| X-04 | conventions §6.1：渠道密钥是 base64 过渡态 | AES-256-GCM 已落地（`core/secret_crypto.py`） | TASK-019 |
| X-05 | conventions §6.2：环境变量前缀 `BOTHOT_` | 实际 `DATABASE_URL`、`PUSH_SECRET_MASTER_KEY` 等无前缀 | TASK-019 |
| X-06 | conventions §8：compose 在 `infra/docker/compose.yml` | `docker/compose.yml`（v0.7 裁定不迁） | TASK-019 |
| X-07 | conventions §9：CORS 白名单制 | TASK-PLAN-v0.9 §0.2 裁定不加 CORS（同源代理） | TASK-019 |
| X-08 | conventions §4.1：`tests/unit/modules/<domain>/` | 扁平 `apps/api/tests/test_*.py` | TASK-019 |
| X-09 | README 本地开发 `cd backend` / `cd frontend` | `apps/api` / `apps/web` | TASK-019 |
| X-10 | REQ-F-001：事件触发待实现 | outbox `push_events` 已实现（backlog PUSH-008） | TASK-019 |
| X-11 | roadmap v1.0 四项均未勾 | tag v1.0.0 已存在，CHANGELOG 有 v1.0.0 段 | TASK-019 |
| X-12 | AGENTS「当前项目状态：v0.6.5」 | v1.0.0 已发布 | TASK-019 |
| X-13 | CHANGELOG Unreleased：「middleware 裁定不实施」「公共库/热点保持可见」 | middleware 已实现；/public、/hot 受保护 | TASK-011（待 D-01） |
| X-14 | e2e/auth-gate.spec.ts 注释：/hot 游客可浏览 | hot 页已包 AuthGate | TASK-010（待 D-01） |
| X-15 | project-map：05–07 目录「预留」 | 05/06/07 已有内容 | TASK-019 |
| X-16 | doc-migration-map：6 项「待迁移」 | 未迁移 | TASK-020（待 D-05） |

### 2.4 读取失败或无法访问

- `.docs/09_archive/inception/立项分析/*.docx`：二进制，未读（已归档，不影响规划）。
- `.docs/05_execution/任务进度.md`（572KB）与 `.docs/04_planning/剩余任务原子化执行大纲-20260922.md`（373KB）：仅抽样，未全文通读。二者已被 `docs/` 新体系与 TASK-PLAN-v0.9 取代（见 doc-migration-map）。**风险**：其中若有未迁移的需求条目，本规划会漏掉。
- `.project/**`：第三方源码，未读（不属本项目需求）。
- 外部系统（主平台 OIDC、共享底座、LangBot、6 个推送渠道）：无访问权限，未实测。

---

## 3. 需求基线复核

### 3.1 复述与拆解

BotHot 是主平台下的子平台：把公众号文章链接采集入库成知识，供 RAG 问答；在此之上把新文章、热点聚簇和每日日报通过 6 种渠道主动推送出去。用户通过主平台 SSO 登录。

- **用户**：主平台账号持有者（role=user），在自己的知识空间里入库、订阅、问答。
- **管理端**：role=operator / admin。operator 管推送渠道、推送任务、热点聚簇与日报生成；admin 另管全站空间、信息源、引擎 Key（`bots.py:179` 等、`subscriptions.py:103`、`admin.py`）。
- **系统边界**：内含 Web（Next.js）、API（FastAPI）、scheduler、worker 四个进程；外部依赖主平台 OIDC、共享底座 PG/Redis、LangBot、SiliconFlow、RedFox 与 4 个文章平台、6 个推送渠道。
- **关键词**：入库、订阅水位、空间隔离、RAG、渠道、Cron、outbox、聚簇、评分、日报、SSO、角色门禁。

**判断**：功能需求 REQ-F-001~008 在代码中都有实现（F-02~F-04 与 backlog 逐条证据）。所以「剩余任务」不是新功能，而是：①安全事故止血；②契约与代码的单一来源闭环；③一处需求冲突（访客访问）；④文档漂移；⑤没有基线的非功能需求；⑥一组待人裁决的遗留项。

### 3.2 分级

| ID | 级别 | 需求 | 可验证改写 | 状态 |
|---|---|---|---|---|
| R-M1 | MUST | 仓库与配置中不得有真实凭据 | `gitleaks detect`（含 URL 内嵌口令规则）对 HEAD 零告警 | ❌ 违反（F-10） |
| R-M2 | MUST | 前后端错误码同源 | `gen_contracts --check` 覆盖 errors.ts 且通过；前端码表类型为 `Record<ApiErrorCode,string>` | ❌（F-05~F-07） |
| R-M3 | MUST | 角色门禁与登录守卫行为确定且有测试 | ADR-0009 路由表中每条路由都有自动化断言（含真实态） | ⚠️ 冲突（F-12/F-13，X-13/X-14） |
| R-M4 | MUST | 文档与代码一致（AGENTS 硬规则） | check_docs_consistency 在 CI 中执行且通过；§2.3 清单清零 | ❌（F-14，X-01~X-16） |
| R-M5 | MUST | 端口纪律（REQ-C-002） | 端口表与编排一致 | ❌（X-01） |
| R-S1 | SHOULD | API 响应形状有机器可读契约 | OpenAPI components 含 bot/hot 的 *Out 模型，契约包导出 | ❌（F-08） |
| R-S2 | SHOULD | 站内通知实时与历史不重复显示 | 帧 id == 表 id，前端按 id 去重的单测通过 | ❌（F-18） |
| R-S3 | SHOULD | 非功能指标有基线（REQ-NF-001） | 4 项指标有首测数值 | ❌（F-21） |
| R-S4 | SHOULD | 真实后端 e2e 为阻塞门禁 | real-backend 4 用例连续 3 次绿且 CI 阻塞 | ❌（F-20，外部阻塞） |
| R-C1 | COULD | 清理死代码/死表（BotBinding、embedding.py） | 见 TASK-022/023 | 待裁决 |
| R-C2 | COULD | 仓库瘦身（.project/） | 见 TASK-005/024 | 部分待裁决 |
| R-C3 | COULD | .docs/ 遗留 6 项迁移 | doc-migration-map 无「待迁移」 | 待裁决 |
| R-N1 | MUST NOT | 不加 CORS | TASK-PLAN-v0.9 §0.2 | 维持 |
| R-N2 | MUST NOT | 不修改 AideanBot 原项目 | AGENTS 约束 1 | 维持 |
| R-N3 | MUST NOT | 不引入 Redis 队列（Job 队列在 PG） | AGENTS 约束 4 / ADR-0007 | 维持 |
| R-N4 | MUST NOT | 本轮不做六边形 modules/ 重构 | roadmap v0.7 裁定「推迟立项」 | 维持（D-10） |
| R-N5 | MUST NOT | 本轮不做多租户、插件化、聚簇向量化（HOT-005） | product-scope Out of Scope；backlog HOT-005「显式排除」 | 维持 |
| R-N6 | MUST NOT | 无基线不排优化任务 | 本规划纪律 | 维持 |

REQ-NF-001 四个数字（API<500ms 等）能写成可验证句，但**没有测量**，所以只能先做测量（TASK-021），不能宣称达标或排优化。

### 3.3 冲突清单

| # | 冲突 | 双方证据 | 处理 |
|---|---|---|---|
| C-01 | 游客能否看 /hot、/public | CHANGELOG「公共引流位保持可见」、e2e 注释「/hot 游客可浏览」 vs `2766d17` 给 hot 加 AuthGate、middleware 拦截 | BLOCKING → D-01 |
| C-02 | 未登录是原地渲染还是 302 | e2e 断言 URL 不变（只在 mock 下成立） vs 真实态 middleware 302 到 `/` | 并入 D-01 |
| C-03 | 端口：5433/6380 vs 5435/6379 | AGENTS 强制表 vs compose 共享底座 | BLOCKING → D-02 |
| C-04 | 「真实密钥禁止入库」 vs compose 明文口令 | README 安全铁律 vs F-10 | 无需裁决，直接修（TASK-001/002/004） |
| C-05 | conventions 要求 CORS 白名单 vs 裁定不加 CORS | conventions §9 vs v0.9 §0.2 | 以后者为准（已裁定），改文档（TASK-019） |
| C-06 | 契约唯一源：SQLAlchemy 内省 vs 需要 API 响应形状 | index.ts 头注 | 提议 ADR-0008 → D-09 |
| C-07 | 非功能目标 vs 无压测环境 | REQ-NF-001 vs TASK-PLAN-v0.9 §3「以留证替代达标」 | 先测基线（TASK-021），不承诺达标 |

### 3.4 未知登记册

| # | 未知 | 级别 | 处理 |
|---|---|---|---|
| D-01 | 游客访问策略（/hot、/hot/daily、/public 可见与否；真实态 302 还是原地渲染） | BLOCKING | 条件方案见 ADR-0009 草案；共同部分：真实态单测必须补 |
| D-02 | 端口与底座口径：以共享底座为准，还是恢复栈内 PG/Redis | BLOCKING | 方案 A：共享底座为准，改 AGENTS 端口表；方案 B：compose 恢复栈内 postgres/redis（5433/6380），共享底座作为 override 文件。共同部分：TASK-002 口令外置两方案都要做 |
| D-03 | BotBinding 表删除还是保留 | BLOCKING（仅对 TASK-022） | A 删（占迁移号 ab1006w6a）/ B 留并注明 |
| D-04 | 前端遗留码 10101/10102/30101/30102/50101 删除还是保留 | NON_BLOCKING | 假设：保留在 LEGACY_MESSAGES，不进主表类型约束；依据：保留无害，删除可能影响主平台透传错误（未验证） |
| D-05 | .docs/ 6 项迁移还是归档 | BLOCKING（仅对 TASK-020） | A 迁移（API 文档以 OpenAPI 生成为准）/ B 全部归档 |
| D-06 | embedding.py 删除还是保留给 HOT-005 | BLOCKING（仅对 TASK-023） | A 删 / B 留 |
| D-07 | .project/ 是否移出版本库 | BLOCKING（仅对 TASK-024） | A 移出 / B 保留并说明；TASK-005（排除出镜像上下文）两方案都做 |
| D-08 | 主平台 OIDC 白名单、测试账号、真实文章 URL | BLOCKING（外部，仅对 TASK-025） | 等外部 |
| D-09 | 批准 ADR-0008（契约唯一源 = 后端 Python 代码：errors.py 登记表 + FastAPI OpenAPI；TS 一律生成） | BLOCKING（对 S1、S3） | 若否决：S1 退化为手工同步 errors.ts + 单测比对；S3 取消 |
| D-10 | 六边形重构是否立项 | 非本轮 | 维持推迟 |
| D-11 | Ragflow / SaaS 引擎实接排期 | 外部 | 不排任务 |
| A-01 | 50003 的登记名用 CONFIGURATION_ERROR | NON_BLOCKING | 依据：类名 `ConfigurationError` |
| A-02 | PushMessage 加可选字段不影响其他 5 个 provider | NON_BLOCKING | 依据：dataclass 默认值；由 TASK-016 回归测试验证 |
| A-03 | 新增 Pydantic 响应模型可做到线上 JSON 零漂移 | NON_BLOCKING | 由快照测试验证，失败即停 |

### 3.5 隐含要求与前置条件

- **凭据轮换先于删除**：只改 compose 不轮换，旧口令仍在 git 历史里可用（public 仓库）。TASK-001 是人工前置。
- **git 历史**：彻底清除需要改写历史（filter-repo + force push），与协作纪律「拒绝 rebase 重写」冲突，本规划**不排**，只轮换。列入风险 K-01。
- **契约变更须先登记**（AGENTS、errors.py 头注）：S1/S3 所有改契约的任务都依赖 D-09。
- **迁移串行**：本轮只有 TASK-022（条件）占用迁移号 `ab1006w6a`，down_revision=`ab1005w5b`。
- **单一提交身份**：执行者按协作纪律用 `CodingHeader`。
- **推送前门禁**：每个任务合并前跑 `bash scripts/preflight.sh`；改 `apps/api/app/**` 的任务另跑后端全量 pytest（协作纪律 §9）。
- **隔离 PG**：本地测试用独立端口（如 5547），不碰 5433。
- **边界条件**：middleware 只判 cookie 存在，过期 cookie 会穿透到 AuthGate（backlog AUTHGATE-002 已述）；TASK-010 的单测需包含「有过期 cookie」用例。


---

## 4. 契约冻结包

> **唯一源（提议，待 D-09 批准 ADR-0008）**：后端 Python 代码是契约唯一源——
> 错误码 = `apps/api/app/core/errors.py`（`ERROR_CODES` + 各 `AppError` 子类）；
> 请求/响应形状 = FastAPI `create_app().openapi()` 的 `components.schemas`（Pydantic）；
> 实体镜像 = SQLAlchemy 模型内省（现状保留）。
> TypeScript 侧 `packages/contracts/**` **一律由 `scripts/gen_contracts.py` 生成**，`--check` 为 CI 门禁。
> 禁止手写第二份。下文中的 TS / JSON 代码块是「生成器目标产物」的冻结样式，由任务验收命令机器校验，不是第二个源。
>
> **冻结范围**：现有 88 个端点的线上形状**按当前代码冻结**（本轮不改任何已有字段）；本轮只允许三类变更：
> ① 错误码登记补 50003（TASK-006）；② 新增响应模型声明，线上 JSON 零漂移（TASK-012/013）；③ SSE 通知帧**新增**可选 `id` 字段（TASK-016）。

### 4.① API 契约

**传输与信封**（`core/response.py:12-24`）

```ts
// 生成目标：packages/contracts/src/common/response.ts（现有，已与后端一致）
interface ApiResponse<T> { code: number; message: string; data: T | null; requestId: string }
// 成功判据唯一为 code === 0（不是 HTTP 2xx）
```

**分页**（冻结双口径，不在本轮统一）

| 口径 | 适用域 | 形状 | 约束 |
|---|---|---|---|
| page | bot、hot | `{items,total,page,page_size}` | page≥1；1≤page_size≤100，默认 20；越界 10005/422 |
| offset | spaces、sources/subscriptions、jobs、admin、notifications/history | `{items,total,limit,offset}`（history 另含 `unread_total`） | 见 `deps.limit_offset_query` |

**鉴权**：Cookie `bothot_session`（HttpOnly、SameSite=Lax、Secure 由 `SESSION_COOKIE_SECURE` 控制、Path=/、Max-Age=`session_ttl_seconds`，`auth.py:92-101`）。浏览器经 Next rewrites 同源访问，**不启用 CORS**。

**幂等语义（已在代码中）**

| 端点 | 语义 | 证据 |
|---|---|---|
| POST /api/v1/hot/topics/cluster | 同日同 days 有在途 Job 时返回 `queued:false` 与既有 job_id，不重复入队 | `hot.py:175-200` |
| POST /api/v1/hot/daily/generate | 同日日报唯一约束 `uq_daily_report_date` | backlog HOT-004 |
| PUT /api/v1/system/notifications/read | 重复标记无副作用；越权 id 影响行数为 0 | backlog NOTIF-001 |
| POST /api/v1/auth/logout | 无会话也返回成功 | `auth.py:146` |
| 其余 POST | **未验证**幂等，执行者不得假设 | — |

**端点全集（88 个，静态解析自 `apps/api/app/api/v1/*.py`，鉴权列按依赖注入判定）**

| # | 方法 | 路径 | 鉴权 | 模块 |
|---|---|---|---|---|
| 1 | PATCH | `/api/v1/admin/spaces/{space_id}` | role≥admin | admin.py |
| 2 | DELETE | `/api/v1/admin/spaces/{space_id}/docs/{doc_id}` | role≥admin | admin.py |
| 3 | DELETE | `/api/v1/admin/spaces/{space_id}` | role≥admin | admin.py |
| 4 | GET | `/api/v1/admin/spaces` | role≥admin | admin.py |
| 5 | GET | `/api/v1/admin/spaces/{space_id}/docs` | role≥admin | admin.py |
| 6 | GET | `/api/v1/admin/jobs` | role≥admin | admin.py |
| 7 | GET | `/api/v1/admin/jobs/{job_id}` | role≥admin | admin.py |
| 8 | GET | `/api/v1/admin/subscriptions` | role≥admin | admin.py |
| 9 | GET | `/api/v1/admin/engines/keys` | role≥operator | admin.py |
| 10 | POST | `/api/v1/admin/engines/keys/{engine}` | role≥operator | admin.py |
| 11 | DELETE | `/api/v1/admin/engines/keys/{engine}` | role≥operator | admin.py |
| 12 | POST | `/api/v1/admin/spaces/{space_id}/docs:delete` | role≥admin | admin.py |
| 13 | POST | `/api/v1/admin/spaces/{space_id}/docs:recategorize` | role≥admin | admin.py |
| 14 | GET | `/api/v1/admin/push/channels` | role≥operator | admin.py |
| 15 | GET | `/api/v1/admin/discovery/channels` | role≥operator | admin.py |
| 16 | GET | `/api/v1/admin/ops/liveness` | role≥operator | admin.py |
| 17 | POST | `/api/v1/admin/push` | role≥operator | admin.py |
| 18 | POST | `/api/v1/admin/jobs/{job_id}:cancel` | role≥admin | admin.py |
| 19 | POST | `/api/v1/admin/jobs/{job_id}:retry` | role≥admin | admin.py |
| 20 | DELETE | `/api/v1/admin/subscriptions/{subscription_id}` | role≥admin | admin.py |
| 21 | GET | `/api/v1/admin/sources` | role≥admin | admin.py |
| 22 | DELETE | `/api/v1/admin/sources/{source_id}` | role≥admin | admin.py |
| 23 | GET | `/api/v1/auth/login` | 匿名 | auth.py |
| 24 | GET | `/api/v1/auth/callback` | 匿名 | auth.py |
| 25 | POST | `/api/v1/auth/logout` | 匿名 | auth.py |
| 26 | POST | `/api/v1/auth/backchannel-logout` | 匿名 | auth.py |
| 27 | GET | `/api/v1/auth/me` | 匿名 | auth.py |
| 28 | GET | `/api/v1/bots/channels` | 登录 | bots.py |
| 29 | POST | `/api/v1/bots` | role≥operator | bots.py |
| 30 | GET | `/api/v1/bots` | 登录 | bots.py |
| 31 | GET | `/api/v1/bots/{channel_id}` | 登录 | bots.py |
| 32 | PUT | `/api/v1/bots/{channel_id}` | role≥operator | bots.py |
| 33 | DELETE | `/api/v1/bots/{channel_id}` | role≥operator | bots.py |
| 34 | POST | `/api/v1/bots/{channel_id}/test` | role≥operator | bots.py |
| 35 | GET | `/api/v1/bots/{channel_id}/logs` | 登录 | bots.py |
| 36 | POST | `/api/v1/bots/tasks` | role≥operator | bots.py |
| 37 | GET | `/api/v1/bots/tasks` | 登录 | bots.py |
| 38 | PUT | `/api/v1/bots/tasks/{task_id}` | role≥operator | bots.py |
| 39 | DELETE | `/api/v1/bots/tasks/{task_id}` | role≥operator | bots.py |
| 40 | POST | `/api/v1/bots/tasks/{task_id}/run` | role≥operator | bots.py |
| 41 | POST | `/api/v1/chat/ask` | 登录 | chat.py |
| 42 | GET | `/api/v1/engines` | 登录 | engines.py |
| 43 | PATCH | `/api/v1/spaces/{space_id}/engine` | 登录 | engines.py |
| 44 | POST | `/api/v1/extract` | 登录 | extract.py |
| 45 | GET | `/api/v1/hot/topics` | 登录 | hot.py |
| 46 | GET | `/api/v1/hot/topics/{topic_id}` | 登录 | hot.py |
| 47 | POST | `/api/v1/hot/topics/cluster` | role≥operator | hot.py |
| 48 | GET | `/api/v1/hot/daily/reports` | 登录 | hot.py |
| 49 | GET | `/api/v1/hot/daily/reports/{report_date}` | 登录 | hot.py |
| 50 | POST | `/api/v1/hot/daily/generate` | role≥operator | hot.py |
| 51 | GET | `/api/v1/hot/feed` | 登录 | hot.py |
| 52 | GET | `/api/v1/onboarding/steps` | 匿名 | onboarding.py |
| 53 | POST | `/api/v1/resolve` | 登录 | resolve.py |
| 54 | GET | `/api/v1/spaces/public` | 登录 | spaces.py |
| 55 | POST | `/api/v1/spaces/{space_id}/links` | 登录 | spaces.py |
| 56 | PATCH | `/api/v1/spaces/{space_id}/public` | 登录 | spaces.py |
| 57 | GET | `/api/v1/spaces` | 登录 | spaces.py |
| 58 | POST | `/api/v1/spaces` | 登录 | spaces.py |
| 59 | GET | `/api/v1/spaces/{space_id}` | 登录 | spaces.py |
| 60 | PATCH | `/api/v1/spaces/{space_id}` | 登录 | spaces.py |
| 61 | DELETE | `/api/v1/spaces/{space_id}` | 登录 | spaces.py |
| 62 | GET | `/api/v1/spaces/{space_id}/docs` | 登录 | spaces.py |
| 63 | GET | `/api/v1/spaces/{space_id}/docs:categories` | 登录 | spaces.py |
| 64 | DELETE | `/api/v1/spaces/{space_id}/docs/{doc_id}` | 登录 | spaces.py |
| 65 | PATCH | `/api/v1/spaces/{space_id}/docs/{doc_id}` | 登录 | spaces.py |
| 66 | POST | `/api/v1/spaces/{space_id}/docs:delete` | 登录 | spaces.py |
| 67 | POST | `/api/v1/spaces/{space_id}/docs:recategorize` | 登录 | spaces.py |
| 68 | POST | `/api/v1/spaces/{space_id}/docs` | 登录 | spaces.py |
| 69 | POST | `/api/v1/spaces/{space_id}/docs:batch` | 登录 | spaces.py |
| 70 | GET | `/api/v1/spaces/{space_id}/docs/{doc_id}/status` | 登录 | spaces.py |
| 71 | POST | `/api/v1/sources` | 登录 | subscriptions.py |
| 72 | GET | `/api/v1/sources` | 登录 | subscriptions.py |
| 73 | PATCH | `/api/v1/sources/{source_id}` | role≥admin | subscriptions.py |
| 74 | DELETE | `/api/v1/sources/{source_id}` | role≥admin | subscriptions.py |
| 75 | POST | `/api/v1/spaces/{space_id}/subscriptions` | 登录 | subscriptions.py |
| 76 | GET | `/api/v1/spaces/{space_id}/subscriptions` | 登录 | subscriptions.py |
| 77 | PATCH | `/api/v1/spaces/{space_id}/subscriptions/{subscription_id}` | 登录 | subscriptions.py |
| 78 | DELETE | `/api/v1/spaces/{space_id}/subscriptions/{subscription_id}` | 登录 | subscriptions.py |
| 79 | GET | `/api/v1/jobs` | 登录 | subscriptions.py |
| 80 | GET | `/api/v1/jobs/{job_id}` | 登录 | subscriptions.py |
| 81 | POST | `/api/v1/jobs/{job_id}/retry` | 登录 | subscriptions.py |
| 82 | POST | `/api/v1/jobs/{job_id}/cancel` | 登录 | subscriptions.py |
| 83 | GET | `/api/v1/system/health` | 匿名 | system.py |
| 84 | GET | `/api/v1/system/live` | 匿名 | system.py |
| 85 | GET | `/api/v1/system/ready` | 匿名 | system.py |
| 86 | GET | `/api/v1/system/notifications` | 登录 | system.py |
| 87 | GET | `/api/v1/system/notifications/history` | 登录 | system.py |
| 88 | PUT | `/api/v1/system/notifications/read` | 登录 | system.py |

> 注：`/auth/me` 标「匿名」是因为鉴权在函数体内（未登录抛 10001），不是对外开放数据。
> **对 D-01 的影响**：`/api/v1/hot/*` 与 `/api/v1/spaces/public` 当前**后端要求登录**。若裁决游客可看 /hot 或 /public，后端也必须开放匿名读，这是 Identity 契约变更。

**本轮新增的响应模型（TASK-012/013 目标，字段逐字取自现序列化代码）**

```ts
// 生成目标：packages/contracts/src/bot/dto.ts 追加
export interface BotChannelOut {            // bots.py:113-129 _serialize_channel
  id: string; name: string; channel_type: string; webhook_url: string;
  has_secret: boolean;                       // secret_enc 永不出现在响应中
  extra_config: string;                      // 回显为解密后的 JSON 字符串（S2.1 语义）
  status: string; user_id: string;
  total_push_count: number; success_push_count: number;
  created_at: string | null; updated_at: string | null;
}
export interface PushTaskOut {              // bots.py:145-160 _serialize_task
  id: string; name: string; bot_channel_id: string;
  trigger_type: string; cron_expr: string; trigger_event: string;
  content_template: string; space_id: string;
  next_run_at: string | null; last_run_at: string | null;
  status: string; created_by: string; created_at: string | null;
}
export interface PushLogOut {               // bots.py:132-142 _serialize_log（8 字段）
  id: string; bot_channel_id: string; push_task_id: string | null;
  status: string; content_preview: string; error_message: string;
  response_summary: string; created_at: string | null;
}
// 生成目标：packages/contracts/src/hot/dto.ts 追加
export interface HotTopicOut {              // hot.py:84-97
  id: string; title: string; summary: string; hot_score: number;
  source_count: number; article_count: number; status: string;
  topic_date: string; category: string; created_at: string | null;
}
export interface HotTopicDetailOut extends HotTopicOut {   // hot.py:128-146
  articles: { asset_id: string; relevance_score: number }[];
}
export interface DailyReportOut {           // hot.py:230-238（列表项）
  id: string; report_date: string; title: string; topic_count: number;
  status: string; generated_by: string; created_at: string | null;
}
export interface FeedItemOut {              // hot.py:345-357
  id: string; item_type: string; ref_id: string; title: string; summary: string;
  source_name: string; score: number; category: string; url: string;
  is_pinned: boolean; created_at: string | null;
}
```

> 可空性以 SQLAlchemy 列定义为准；上面 `push_task_id`、`user_id` 等可空性在实现时由模型内省核对，若与此不同，以代码为准并在 TASK-012/013 的 PR 中注明（不得改线上值）。

### 4.② Errors 契约

| code | 登记名 | HTTP | 前端文案（TASK-008 目标） | 前端行为 |
|---|---|---|---|---|
| 10001 | UNAUTHENTICATED | 401 | 尚未登录或会话已过期 | 切 AuthGate 访客卡 |
| 10002 | SSO_STATE_INVALID | 400 | 登录状态校验失败，请重新登录 | 回首页 + 登录按钮 |
| 10003 | SSO_TOKEN_EXCHANGE_FAILED | 401 | 授权码兑换失败，请重新登录 | 同上 |
| 10004 | FORBIDDEN | 403 | 权限不足 | 无权限态 |
| 10005 | REQUEST_INVALID | 422 | 请求参数不合法 | 表单内联错误 |
| 10006 | MALFORMED_URL | 400 | 链接格式不正确 | 表单内联错误 |
| 10007 | RATE_LIMITED | 429 | 请求过于频繁，请稍后再试 | toast；**不自动重试** |
| 10008 | PAYLOAD_TOO_LARGE | 413 | 提交内容过大 | toast |
| 20001 | SOURCE_URL_UNRECOGNIZED | 400 | 非公众号文章，请检查链接 | 内联 |
| 20002 | EXTRACT_FAILED | 502 | 网络异常，文章抓取失败 | 可手动重试 |
| 20003 | EXTRACT_QUALITY_LOW | 422 | 内容质量不足，无法入库 | 内联 |
| 20004 | DISCOVERY_FAILED | 502 | 信息源发现失败，请稍后重试 | 可手动重试 |
| 20005 | RATE_LIMITED_UPSTREAM | 429 | 上游接口限频，请稍后重试 | toast |
| 30001 | SPACE_NOT_FOUND | 404 | 知识空间不存在或已删除 | 空态 + 返回 |
| 30002 | LANGBOT_API_ERROR | 502 | 机器人服务异常，请稍后重试 | 错误态 |
| 30003 | INGEST_FAILED | 502 | 入库失败，请稍后重试 | 可手动重试 |
| 30004 | RESOURCE_NOT_FOUND | 404 | 资源不存在或已删除 | 空态 |
| 30005 | JOB_STATE_INVALID | 409 | 任务当前状态不允许该操作 | toast + 刷新 |
| 30006 | SPACE_NAME_CONFLICT | 409 | 空间名称已存在 | 内联 |
| 50001 | INTERNAL_ERROR | 500 | 服务内部错误，请稍后重试 | 错误态（展示 requestId） |
| 50002 | DEPENDENCY_UNAVAILABLE | 503 | 依赖服务暂不可用，请稍后重试 | 错误态 |
| 50003 | CONFIGURATION_ERROR（**新登记**） | 500 | 服务配置异常，请联系管理员 | 错误态（展示 requestId） |

- 错误体 = 信封 `{code≠0, message, data:null, requestId}`；429/413 由中间件短路，同样是信封并带 `X-Request-ID`（`core/security.py:6-29`）。
- 30004 现文案「知识空间不存在或已删除」是继承文案，与 RESOURCE_NOT_FOUND 语义不符，TASK-008 改为上表。
- 遗留码 10101/10102/30101/30102/50101：后端不产出；按 D-04 默认假设保留在 `LEGACY_MESSAGES`，不进主表类型约束。
- **机器校验**：`gen_contracts --check`（errors.ts）+ 前端 `satisfies Record<ApiErrorCode,string>` + `test_error_registry.py`。

### 4.③ Identity 契约

| 项 | 冻结值 | 证据 |
|---|---|---|
| 用户 ID | `users.sub`（主平台 OIDC sub，字符串）为身份锚点；本地 `users.id` 为 UUID 字符串 | AGENTS 约束 2 |
| 角色枚举 | `user` / `operator` / `admin`，秩 0/1/2，取最高达标即放行 | `services/roles.py` ROLE_RANK |
| 默认角色 | `user`；脏值按 user 处理（fail closed） | `roles.py` has_min_rank |
| 升权 | 只能显式写 `users.role`；`PUBLIC_ADMIN_ALLOWLIST` 只管「公共库发布」，**不授予任何角色** | `roles.py` 头注 |
| 会话 | 服务端会话（Redis/memory），cookie 只存 session_id | `auth.py:92-101` |
| 余额/等级 | 不落库，实时查主平台 | AGENTS 约束 2 |
| 登出 | 前端 POST /auth/logout；主平台 POST /auth/backchannel-logout（logout_token iat 偏差 ≤300s） | `config.py:47` |

**权限边界（禁止项）**

1. 用户端（role=user）**不得**调用：`/api/v1/admin/**`、`/api/v1/bots/**` 的写操作与日志、`POST /hot/topics/cluster`、`POST /hot/daily/generate`、`PATCH/DELETE /api/v1/sources/{id}`。
2. operator **不得**调用：admin 级端点（空间/文档/Job/订阅/信息源的全站管理）。
3. 前端 TopBar 显示或隐藏 ≠ 授权；授权只看后端 `require_role`。
4. `/auth/me` 的 `is_admin` 只读回显，不得用于后端授权（`roles.py` sub_has_min_rank）。
5. 用户只能操作自己的空间（`space.user_id != user_id → 30004`，如 `engines.py:155-158`）。
6. 通知历史只返回 `sub == 我 OR is_broadcast`；标记已读越权影响 0 行。

### 4.④ Resources 契约

- 本系统**没有文件/图片上传端点**（`grep UploadFile|File( app` 零命中）。
- 外部资源只以 URL 形式出现：`ContentAsset` 的来源 URL、`FeedItem.url`、通知 `url`；前端只做链接跳转，不代理下载。
- 渠道 webhook URL ≤512 字符（`bots.py MAX_WEBHOOK_CHARS`）；密钥与 `extra_config` 以 AES-256-GCM 落库，响应只回 `has_secret`。
- 配置类资源（本轮新增约束，TASK-002）：数据库与 Redis 连接串只能来自环境变量（`docker/.env`，已 gitignore），compose 文件内不得出现口令。
- 生命周期：知识文档软删除与引擎侧残留规则维持现状（`engines.py:142-160` 注释）。

### 4.⑤ Events 契约

**A. 推送事件 outbox（`push_events` 表，现状冻结）**

| event_type | 生产者（worker 进程） | 载荷（emit 时补齐） |
|---|---|---|
| new_article | 文章入库 INDEXED | `asset_id, space_id, doc_title, space_name` |
| hot_topic_update | 聚簇完成 | `topic_id, hot_topic, topic_count` |
| daily_report | 日报生成 | `report_date, report_title` |

- 消费：backend 进程 push_scheduler 每 `PUSH_SCHEDULER_INTERVAL`（默认 60s，下限 5s）领取，先标 `consumed_at` 再投递 → **at-most-once**；延迟下限 = 扫描间隔。
- 幂等键：事件行 `id`（UUID）；投递失败走 PushTask 重试簿记，不重放事件。

**B. 站内通知（Redis pub/sub → SSE）**

- 频道：`bothot:notifications:{sub}`（定向）与 `bothot:notifications:broadcast`。
- SSE：`GET /api/v1/system/notifications`，`data:` 行为 JSON；`: ping` 心跳；Redis 不可用时发 `{"type":"service_unavailable","message":...}` 后关流。
- 帧 JSON Schema（TASK-016 目标，`id` 为**新增可选**，向后兼容）：

```json
{
  "$id": "bothot.notification.frame.v2",
  "type": "object",
  "required": ["title", "message"],
  "properties": {
    "id":       {"type": "string", "description": "与 notifications.id 相同；旧帧可缺省"},
    "title":    {"type": "string"},
    "message":  {"type": "string"},
    "url":      {"type": "string"},
    "space_id": {"type": "string"},
    "doc_id":   {"type": "string"}
  },
  "additionalProperties": true
}
```

- 前端去重键：`id`（有则用）→ 否则沿用现行内容窗口去重。

### 4.⑥ UX States 契约

| 页面 | 加载态 | 访客态 | 空态 | 错误态 | 无权限态 | 成功态 |
|---|---|---|---|---|---|---|
| /spaces、/spaces/[id] | Skeleton | AuthGate 卡 | 「还没有知识空间」+ 新建入口 | LoadingErrorShell + 重试 | — | 列表/详情 |
| /subscriptions、/jobs | Skeleton | AuthGate 卡 | 空列表提示 | LoadingErrorShell | — | 列表 |
| /chat | Skeleton | AuthGate 卡 | 未选空间提示 | 流中断提示可重发 | — | 流式回答 |
| /bots（渠道/任务） | Skeleton | AuthGate 卡 | 「暂无渠道」 | LoadingErrorShell | 10004 → 「权限不足」卡 | 列表 + 测试推送结果 |
| /hot、/hot/daily | Skeleton | **待 D-01** | 「暂无热点 / 暂无日报」 | LoadingErrorShell | — | Feed / Markdown |
| /public | Skeleton | **待 D-01** | 空列表 | LoadingErrorShell | — | 列表 |
| /admin | Skeleton | AuthGate 卡 | — | LoadingErrorShell | is_admin=false → 「权限不足」卡 | 管理面板 |
| NotificationBell | 不渲染徽标 | 不连接 SSE | 「暂无通知」 | service_unavailable 静默降级 | — | 列表 + 未读数 |
| 任意页收到 10007 | — | — | — | toast「请求过于频繁」，不自动重试 | — | — |

### 4.4 契约自检

- [x] 前端只凭契约写 API 层：端点全集 + 信封 + 分页 + 错误表 + bot/hot 响应形状齐备；其他域响应形状**未生成**，本轮维持各模块现有本地类型（风险 K-05）。
- [x] 后端只凭契约实现：本轮后端改动（TASK-006/012/013/016）字段已逐字给出。
- [x] 数据端只凭契约设计表结构：本轮仅 TASK-022（条件）涉及表。
- [x] 错误码覆盖已知失败路径：后端 23 个码全部列出，含 429/413 中间件路径。
- [x] 管理端越权路径已列为禁止项（4.③ 1–6）。
- 结论：**对本轮任务完备**。对「未来任意前端新功能」不完备（其他域无响应形状契约），已列入风险。

---

## 5. 数据模型基线

**现状（冻结，不在本轮改动）**：22 张表，alembic 18 个版本，单头 `ab1005w5b`。

| 组 | 表（模型） | 文件 |
|---|---|---|
| identity | users（User，含 role） | `models/entities.py` |
| knowledge | knowledge_spaces、content_assets、short_link_map、knowledge_documents、engine_key_registrations | `models/entities.py` |
| subscription | sources、source_subscriptions、article_manifests | `models/entities.py` |
| ingest | jobs、job_items | `models/entities.py` |
| system | process_heartbeats | `models/entities.py` |
| bot | bot_channels、push_tasks、push_logs、push_events、notifications | `models/bothot_entities.py` |
| hot | hot_topics、hot_topic_articles、daily_reports、feed_items | `models/bothot_entities.py` |
| 疑似死表 | bot_bindings（BotBinding） | `models/entities.py`（F-16） |

- 字段级定义以 SQLAlchemy 模型为准，契约镜像见 `packages/contracts/src/*/dto.ts`（生成物，`--check` 守护）。本规划**不另写一份字段表**，避免第二来源。
- 已有关键索引：`hot_topics.hot_score`、`notifications(sub, created_at)`、`push_events.event_type/consumed_at`、`feed_items(item_type, ref_id)` 唯一、`daily_reports.report_date` 唯一、FK 索引（`ab1004w4a`）。
- 软删除：知识文档与推送任务为软删除（`bots.py` 任务软删除，roadmap v0.4）。
- 渠道字段为 `String(32)` 而非 enum（AGENTS 约束 3）。

**迁移版本号编排（本轮）**

| 序 | 版本号 | down_revision | 任务 | 条件 |
|---|---|---|---|---|
| 1 | ab1006w6a | ab1005w5b | TASK-022 删除 bot_bindings | 仅 D-03=A 时 |

本轮其他任务**禁止**新增迁移。若后续任务需要迁移，必须先在本表登记版本号，串行合并。

**不写 `database/migrations/001_init.sql`**：项目以 alembic 为唯一迁移源，v0.7 裁定 `database/migrations/` 不启用（roadmap v0.7「裁定不迁移」）。另写 SQL 会形成第二来源，违反 §4.2。

---

## 6. 垂直切片清单

**步行骨架已存在**：健康检查（`/system/health`、`/live`、`/ready`）、鉴权写接口（如 `POST /bots`）、表与迁移、前端打真实 API、统一错误信封，均在代码中，CI 编排冒烟通过。所以本轮不重建骨架，S0 的职责是让骨架在**不泄露凭据**的前提下可复现。

| 切片 | 可演示行为（比上一刀多出的） | 任务 | 规模 | 可否与他刀并行 |
|---|---|---|---|---|
| **S0 安全止血** | 用只在 `.env` 里的连接串起栈，smoke 通过；旧口令失效；gitleaks 能拦住同类提交 | 001 002 003 004 005 | 0.5–1 天 | 与 S1、S4、S5 并行 |
| **S1 错误码同源** | 触发限流时界面显示「请求过于频繁」；后端新增错误码不改前端即编译失败 | 006 007 008 | 1 天 | 与 S0、S4、S5 并行（需 D-09） |
| **S2 访客策略** | 未登录访问各页面的行为与 ADR 一致，且真实构建有单测锁定 | 009 010 011 | 0.5–1 天 | 需 D-01；与 S3 并行 |
| **S3 响应形状契约** | 改后端字段名，CI 的契约门禁会红；前端 bots/hot 用生成类型 | 012 013 014 015 | 1.5–2 天 | 需 D-09；在 S1 之后（同用 gen_contracts.py） |
| **S4 通知去重** | 在线收到一条站内通知后刷新页面，铃铛里只有一条 | 016 017 | 0.5 天 | 与 S0、S1、S5 并行 |
| **S5 治理门禁** | 在 backlog 写错一个文件路径，CI 变红；文档与代码一致 | 018 019 020 | 1 天 | 与 S0、S1、S4 并行 |
| **S6 性能基线** | 一份带数字的基线报告，脚本可复跑 | 021 | 0.5–1 天 | 在 S0 之后（需能起栈） |
| **S7 遗留处置** | 按裁决删除或注明死表、死代码、第三方源码 | 022 023 024 | 0.5 天 | 需 D-03/D-06/D-07 |
| **S8 真实链路** | 真实 OIDC 登录下 4 条 e2e 连续 3 次绿，CI 阻塞 | 025 | 1 天 | 需 D-08（外部） |

**排序理由**：S0 是正在发生的安全事件（public 仓库里有可用口令），优先级最高；S1 解锁 S3（共用生成器）且不确定性低；S2 不确定性最高（需求冲突），但依赖人裁决，所以尽早把选项交出去；S6 必须先于任何优化；S7/S8 被外部条件卡住，放后。

小于 2 小时的任务（001、003、005、011、017、018、023、024）已并入所属切片一起演示，不单独成刀。

---

## 7. 原子任务卡全集

工作包（Work Package）→ 原子任务（Atomic Task）→ 执行步骤（Execution Step）：

| 工作包 | 交付什么 | 原子任务 |
|---|---|---|
| WP-0 安全止血 | 凭据不在仓库、栈可复现、同类泄露可被拦截 | TASK-001…005 |
| WP-1 错误契约单一源 | 错误码一处登记，前后端同源 | TASK-006…008 |
| WP-2 访客访问策略 | 登录守卫行为确定且有测试 | TASK-009…011 |
| WP-3 响应形状契约 | bot/hot 响应形状机器可读并被前端消费 | TASK-012…015 |
| WP-4 通知去重 | 实时与历史通知按 id 合并 | TASK-016…017 |
| WP-5 治理门禁 | 文档一致性进 CI，漂移清零 | TASK-018…020 |
| WP-6 基线指标 | 四项非功能指标有首测 | TASK-021 |
| WP-7 待裁决处置 | 死表/死代码/第三方源码按裁决处理 | TASK-022…024 |
| WP-8 真实链路验收 | 真实后端 e2e 成为门禁 | TASK-025 |

每张卡的完整内容见下文（同时落盘为 `docs/05_execution/tasks/TASK-xxx.md`）。

### TASK-001：轮换已入库的共享底座 PG 账号口令（人工）

**归属**
- 所属切片：S0（WP-0 安全止血）
- 执行 Agent：人工（运维）
- 来源需求：REQ-NF-002（真实密钥禁止入库，README 安全铁律）
- 来源方案：ADR-0010（提议）

**目标**
共享底座 PG 账号 bothot_rw 的口令已更换，旧口令 <已轮换·见运维工单> 无法再连接。

**输入**
- 证据：docker/compose.yml:157（commit 01f6892 引入，仓库为 public）
- 前置任务：无
- 前置状态：无

**输出**（新增/修改的文件）
- 无仓库文件变更（运维操作）
- docs/06_validation/evidence/EVD-001/rotation.md（记录时间、执行人，不记新口令）

**Execution Steps**
1. [ ] 在共享底座 PG（宿主 5435）执行 ALTER ROLE bothot_rw WITH PASSWORD '<新值>'
2. [ ] 把新连接串只写入本机 docker/.env（已 gitignore）
3. [ ] 用旧口令尝试连接，确认被拒绝
4. [ ] 在 EVD-001 写入时间与结论（不含口令）

**验收标准**
- [ ] 旧口令连接返回 password authentication failed
- [ ] 仓库内无新口令（gitleaks 与 grep 均 0 命中）

**验证命令**
```bash
PGPASSWORD=<已轮换·见运维工单> psql -h 127.0.0.1 -p 5435 -U bothot_rw -d bothot -c 'select 1'   # 期望：认证失败
git grep -n "<新口令片段>" || echo OK
```

**证据路径**
`docs/06_validation/evidence/EVD-001/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `docs/06_validation/evidence/EVD-001/**`

**禁止修改**
- 仓库内任何代码与配置

**依赖与阻塞**
- Depends on：无
- Blocks：TASK-002 的上线（不阻塞其开发）
- 阻塞条件：无共享底座 DBA 权限 → 标 blocked 交人

**建议执行档位**
人工　理由：涉及生产凭据，CLI 不得接触口令

**升级条件**
不适用；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小（<2h，按规则并入 S0 演示）

---

### TASK-002：compose 连接串外置为必填环境变量

**归属**
- 所属切片：S0（WP-0 安全止血）
- 执行 Agent：Agent-Guard
- 来源需求：REQ-NF-002；README『真实密钥禁止入库』
- 来源方案：ADR-0010（提议）

**目标**
docker/compose.yml 不再含任何明文口令；DATABASE_URL/REDIS_URL 缺失时 compose config 直接报错。

**输入**
- docker/compose.yml:150-160（backend_env 锚）
- docker/.env.example
- docker/compose.ci.yml（CI 叠加覆盖，不得被破坏）
- 契约：DESIGN-001 §Resources/配置

**输出**（新增/修改的文件）
- `docker/compose.yml`
- `docker/.env.example`

**Execution Steps**
1. [ ] 把 compose.yml:157-158 改为 ${DATABASE_URL:?DATABASE_URL 未设置} 与 ${REDIS_URL:?REDIS_URL 未设置}
2. [ ] grep 全仓 host.docker.internal:5435 与 bothot_rw 的消费方，逐个改为引用变量（含注释文案）
3. [ ] .env.example 增两条带占位符的条目与注释（共享底座/栈内两种写法）
4. [ ] 确认 compose.ci.yml 覆盖值仍生效

**验收标准**
- [ ] `git grep -nE 'bothot_rw:[^<>@[:space:]]+@' -- docker apps scripts packages .github` 返回空
- [ ] 注：原口径『grep 旧口令字面量』已作废——口令本身已从本规划文档中移除（不该出现在任何入库文件里），改为断言「不存在带 userinfo 口令的 bothot_rw 连接串」这一更强的形状判据
- [ ] 未设置 DATABASE_URL 时 docker compose config 非 0 退出
- [ ] compose.ci.yml 叠加 config --quiet 通过
- [ ] CI compose / compose-smoke 两 job 绿

**验证命令**
```bash
git grep -nE 'bothot_rw:[^<>@[:space:]]+@' -- docker apps scripts packages .github && exit 1 || true
env -u DATABASE_URL docker compose -f docker/compose.yml config --quiet; test $? -ne 0
DATABASE_URL=x REDIS_URL=y docker compose -f docker/compose.yml -f docker/compose.ci.yml config --quiet
```

**证据路径**
`docs/06_validation/evidence/EVD-002/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `docker/compose.yml`
- `docker/.env.example`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- docker/compose.ci.yml

**依赖与阻塞**
- Depends on：无
- Blocks：TASK-003
- 阻塞条件：compose.ci.yml 必须同步修改才能绿 → 停，提交给 Agent-Guard 协调

**建议执行档位**
sonnect　理由：单文件配置改动，规则明确

**升级条件**
CI compose-smoke 连续 2 次红 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小（约 2h）

---

### TASK-003：端口与底座口径落档（依裁决 D-02）

**归属**
- 所属切片：S0（WP-0 安全止血）
- 执行 Agent：Agent-Doc
- 来源需求：REQ-C-002（端口分配）
- 来源方案：ADR-0010（提议）

**目标**
AGENTS.md / README / conventions.md 的 PG、Redis 端口与实际编排一致，且只有一种口径。

**输入**
- 裁决 D-02 结果
- AGENTS.md 端口表（5433/6380）
- docker/compose.yml:46-47（共享底座 5435/6379）

**输出**（新增/修改的文件）
- `AGENTS.md`
- `README.md`
- `docs/04_engineering/conventions.md`

**Execution Steps**
1. [ ] 按 D-02 结论更新三处端口表
2. [ ] README『服务与启动顺序』改写为共享底座或栈内二选一的实际形态
3. [ ] make guard-ports 若需新增检查，提交需求给 Agent-Guard（本任务不改 Makefile）

**验收标准**
- [ ] 三份文档端口表逐字一致
- [ ] 与 docker/compose.yml 实际值一致（人工比对表格）

**验证命令**
```bash
grep -nE '5433|5435|6380|6379' AGENTS.md README.md docs/04_engineering/conventions.md docker/compose.yml
```

**证据路径**
`docs/06_validation/evidence/EVD-003/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `AGENTS.md`
- `README.md`
- `docs/04_engineering/conventions.md`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- docker/**
- Makefile

**依赖与阻塞**
- Depends on：TASK-002、D-02
- Blocks：无
- 阻塞条件：D-02 未裁决 → blocked

**建议执行档位**
haiku　理由：纯文档替换

**升级条件**
出现第三种口径 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小（并入 S0）

---

### TASK-004：gitleaks 规则补『URL 内嵌口令』检测

**归属**
- 所属切片：S0（WP-0 安全止血）
- 执行 Agent：Agent-Guard
- 来源需求：REQ-NF-002
- 来源方案：DESIGN-001 §9 自动化守卫

**目标**
向 security.yml 的 gitleaks 增加规则，使形如 scheme://<user>:<pass>@host 的连接串被识别；对 commit 01f6892 复跑能报出。

**输入**
- .github/workflows/security.yml:421-515（gitleaks step）
- 证据：01f6892 的口令未被现有 gitleaks 拦截（该 run 结论 success）

**输出**（新增/修改的文件）
- .gitleaks.toml（仓库根）
- `.github/workflows/security.yml`

**Execution Steps**
1. [ ] 新建 .gitleaks.toml：extend 默认规则 + 自定义 regex `[a-z+]+://[^:/\s]+:[^@/\s]+@`
2. [ ] allowlist 仅放行 docker/compose.ci.yml 的一次性 bothot:bothot（CI 临时库）
3. [ ] security.yml 的 gitleaks 调用加 --config .gitleaks.toml
4. [ ] 本地对 01f6892 复跑验证能报出

**验收标准**
- [ ] gitleaks detect --log-opts 01f6892^..01f6892 报出 compose.yml:157
- [ ] HEAD 全量扫描在 TASK-002 合并后 0 告警
- [ ] Security 工作流绿

**验证命令**
```bash
gitleaks detect --config .gitleaks.toml --log-opts '01f6892^..01f6892' -v; test $? -eq 1
gitleaks detect --config .gitleaks.toml --no-git -s docker/
```

**证据路径**
`docs/06_validation/evidence/EVD-004/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `.gitleaks.toml`
- `.github/workflows/security.yml`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- docker/**

**依赖与阻塞**
- Depends on：无
- Blocks：无
- 阻塞条件：规则误报 compose.ci.yml 以外的测试夹具 ≥3 处 → 停，回报清单

**建议执行档位**
sonnect　理由：规则编写 + 工作流参数

**升级条件**
Security 工作流连续 2 次红 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小

---

### TASK-005：.project/ 排除出前端镜像构建上下文

**归属**
- 所属切片：S0（WP-0 安全止血）
- 执行 Agent：Agent-Guard
- 来源需求：REQ-C-001（Docker Compose 部署）
- 来源方案：—（卫生项，无需 ADR）

**目标**
根 .dockerignore 排除 .project/（125M 第三方源码），frontend 镜像构建上下文不再携带它。

**输入**
- .dockerignore（当前无 .project 条目）
- du -sh .project = 125M

**输出**（新增/修改的文件）
- `.dockerignore`

**Execution Steps**
1. [ ] 在 .dockerignore『其余目录一律不入上下文』段加 .project/ 一行（附注释）
2. [ ] 本地 docker build 前端镜像，对比构建上下文体积

**验收标准**
- [ ] grep -n '^.project/' .dockerignore 命中
- [ ] frontend 镜像 build 成功，上下文体积下降（记录前后数值）

**验证命令**
```bash
grep -n '^\.project/' .dockerignore
docker compose -f docker/compose.yml build frontend 2>&1 | grep -i 'transferring context'
```

**证据路径**
`docs/06_validation/evidence/EVD-005/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `.dockerignore`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- .project/**（不删除，删除属 D-07）

**依赖与阻塞**
- Depends on：无
- Blocks：无
- 阻塞条件：build 失败且与本改动相关 → 回退并回报

**建议执行档位**
haiku　理由：一行配置

**升级条件**
build 失败 → sonnect；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小（并入 S0 演示）

---

### TASK-006：错误码登记表补全 50003 并加注册一致性断言

**归属**
- 所属切片：S1（WP-1 错误契约单一源）
- 执行 Agent：Agent-Contract
- 来源需求：REQ-F-008 / REQ-NF-002（失败可读）；errors.py 头注『先登记后实现』
- 来源方案：ADR-0008（提议）

**目标**
errors.py 中每个 AppError 子类的 code 都在 ERROR_CODES 中有登记名；50003 登记为 CONFIGURATION_ERROR。

**输入**
- apps/api/app/core/errors.py:9-37（ERROR_CODES，缺 50003）
- errors.py:222-225（ConfigurationError code=50003）
- 契约：DESIGN-001 §② Errors 目标表

**输出**（新增/修改的文件）
- `apps/api/app/core/errors.py`
- apps/api/tests/test_error_registry.py（新增）

**Execution Steps**
1. [ ] ERROR_CODES 增 50003: "CONFIGURATION_ERROR"
2. [ ] 新增测试：遍历 AppError.__subclasses__()（递归），断言 code ∈ ERROR_CODES 且 http_status 为 int
3. [ ] 跑 ruff/mypy/新测试

**验收标准**
- [ ] 新测试通过
- [ ] ruff check、mypy app 通过
- [ ] AppError(50003) 实例 name == CONFIGURATION_ERROR

**验证命令**
```bash
cd apps/api && ruff check app tests && mypy app && pytest tests/test_error_registry.py -q
```

**证据路径**
`docs/06_validation/evidence/EVD-006/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/api/app/core/errors.py`
- `apps/api/tests/test_error_registry.py`

**禁止修改**
- packages/contracts/**
- apps/web/**
- apps/api/alembic/**

**依赖与阻塞**
- Depends on：D-09
- Blocks：TASK-007
- 阻塞条件：发现其他未登记 code → 一并登记前先回报（属契约变更）

**建议执行档位**
opus　理由：改的是全栈契约源，需判断语义命名

**升级条件**
—（已是 opus）；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小

---

### TASK-007：gen_contracts 生成 errors.ts 并纳入 --check

**归属**
- 所属切片：S1（WP-1 错误契约单一源）
- 执行 Agent：Agent-Contract
- 来源需求：REQ-F-008；契约唯一源纪律（packages/contracts/src/index.ts 头注）
- 来源方案：ADR-0008（提议）

**目标**
packages/contracts/src/common/errors.ts 由 scripts/gen_contracts.py 从 errors.py 生成；手改即被 --check 拦截。

**输入**
- scripts/gen_contracts.py:112-172（generate/check）
- apps/api/app/core/errors.py（TASK-006 后）
- 现手写 packages/contracts/src/common/errors.ts（缺 10007/10008）

**输出**（新增/修改的文件）
- `scripts/gen_contracts.py`
- packages/contracts/src/common/errors.ts（生成物）

**Execution Steps**
1. [ ] generate() 增加 errors 产物：读取 ERROR_CODES 与各子类 http_status，渲染 ApiErrorCode/ApiErrorName/ApiErrorHttpStatus/AuthErrorCode
2. [ ] AuthErrorCode 取 http_status==401 的 code 集合（10001/10003），保持与现导出名一致
3. [ ] 生成物加『请勿手动修改』头
4. [ ] 运行生成 → --check 幂等
5. [ ] 契约包 tsc --noEmit 通过

**验收标准**
- [ ] errors.ts 含 10007、10008、50003=CONFIGURATION_ERROR
- [ ] python scripts/gen_contracts.py --check 退出 0
- [ ] 手改 errors.ts 任意一行后 --check 退出 1
- [ ] packages/contracts tsc 零错；apps/web tsc 零错

**验证命令**
```bash
cd apps/api && python ../../scripts/gen_contracts.py && python ../../scripts/gen_contracts.py --check
cd ../web && pnpm exec tsc --noEmit -p ../../packages/contracts/tsconfig.json && pnpm exec tsc --noEmit
```

**证据路径**
`docs/06_validation/evidence/EVD-007/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `scripts/gen_contracts.py`
- `packages/contracts/src/common/errors.ts`

**禁止修改**
- apps/**
- apps/api/alembic/**

**依赖与阻塞**
- Depends on：TASK-006
- Blocks：TASK-008
- 阻塞条件：index.ts 导出名需改 → 停，属契约变更需 opus 审

**建议执行档位**
sonnect　理由：生成器扩展，规则已在 DESIGN-001 写死

**升级条件**
--check 不幂等连续 2 次 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中

---

### TASK-008：前端错误表对齐契约 + 429/413 展示态

**归属**
- 所属切片：S1（WP-1 错误契约单一源）
- 执行 Agent：Agent-App
- 来源需求：REQ-F-008；UX States 契约
- 来源方案：ADR-0008（提议）、DESIGN-001 §⑥

**目标**
前端 ERROR_MESSAGES 以 Record<ApiErrorCode,string> 类型约束覆盖全部后端码；10007/10008 有专属文案，10007 不触发自动重试。

**输入**
- apps/web/lib/api/http.ts:26-51（ERROR_MESSAGES、isAuthError）
- packages/contracts/src/common/errors.ts（TASK-007 生成物）
- DESIGN-001 §② 前端文案表

**输出**（新增/修改的文件）
- `apps/web/lib/api/http.ts`
- apps/web/tests/error-messages.spec.ts（新增）

**Execution Steps**
1. [ ] ERROR_MESSAGES 拆为：satisfies Record<ApiErrorCode,string> 的主表 + LEGACY_MESSAGES（10101/10102/30101/30102/50101，按 D-04 结论保留或删除）
2. [ ] 补 10007『请求过于频繁，请稍后再试』、10008『提交内容过大』、20004/20005/30005/30006/50001/50003 文案（取 DESIGN-001）
3. [ ] isAuthError 改为基于契约 AuthErrorCode（+ D-04 决定是否保留 10101）
4. [ ] 新增 vitest：遍历契约码表断言每码有文案；10007 不在重试判定内

**验收标准**
- [ ] pnpm exec tsc --noEmit 零错（缺码即编译失败）
- [ ] 新 vitest 用例全绿，既有 vitest 零回归
- [ ] mock e2e 绿

**验证命令**
```bash
cd apps/web && pnpm exec tsc --noEmit && pnpm run test:unit -- --run && pnpm run test:e2e
```

**证据路径**
`docs/06_validation/evidence/EVD-008/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/web/lib/api/http.ts`
- `apps/web/tests/error-messages.spec.ts`

**禁止修改**
- packages/contracts/**
- apps/api/**

**依赖与阻塞**
- Depends on：TASK-007、D-04
- Blocks：无
- 阻塞条件：需要新增错误码 → 停，回报给 Agent-Contract

**建议执行档位**
sonnect　理由：前端实现 + 单测

**升级条件**
连续 2 次验收失败 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中

---

### TASK-009：ADR-0009 访客访问策略定稿（依裁决 D-01）

**归属**
- 所属切片：S2（WP-2 访客访问策略）
- 执行 Agent：Agent-Doc（opus 起草）
- 来源需求：REQ-F-007（角色门禁）；backlog AUTHGATE-001/002
- 来源方案：ADR-0009（提议，本规划已起草）

**目标**
ADR-0009 状态从 proposed 变 accepted，明确 /hot、/hot/daily、/public 对游客是否可见，以及真实态是 302 还是原地渲染。

**输入**
- docs/03_solution/decisions/adr-0009-guest-access-policy.md（草案）
- apps/web/middleware.ts:14-15（白名单仅 / 与 /auth）
- apps/web/e2e/auth-gate.spec.ts:10（注释称 /hot 豁免）
- commit 2766d17（hot 页接 AuthGate）
- CHANGELOG Unreleased『公共引流位保持可见』

**输出**（新增/修改的文件）
- `docs/03_solution/decisions/adr-0009-guest-access-policy.md`
- `docs/03_solution/decisions/adr-index.md`

**Execution Steps**
1. [ ] 把 D-01 裁决结果写入 ADR『决定』节
2. [ ] 列出受影响路由表与 e2e 断言变化
3. [ ] adr-index 登记

**验收标准**
- [ ] ADR 状态 accepted，含路由 × 游客行为表
- [ ] 表内每条路由都有对应 e2e 断言计划

**验证命令**
```bash
grep -n '^status:' docs/03_solution/decisions/adr-0009-guest-access-policy.md
```

**证据路径**
`docs/06_validation/evidence/EVD-009/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `docs/03_solution/decisions/**`

**禁止修改**
- apps/**
- packages/**

**依赖与阻塞**
- Depends on：D-01
- Blocks：TASK-010、TASK-011
- 阻塞条件：D-01 未裁决 → blocked

**建议执行档位**
opus　理由：安全边界决策

**升级条件**
裁决推翻已冻结的 Identity 契约 → fable；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小

---

### TASK-010：middleware 白名单与 AuthGate 按 ADR-0009 对齐 + 真实态单测

**归属**
- 所属切片：S2（WP-2 访客访问策略）
- 执行 Agent：Agent-App
- 来源需求：REQ-F-007
- 来源方案：ADR-0009

**目标**
真实构建下 middleware 的放行集合 = ADR-0009 的游客可见路由；有不依赖 mock 的单测锁定该行为。

**输入**
- apps/web/middleware.ts
- apps/web/app/{hot,hot/daily,public}/page.tsx（AuthGate 包裹）
- apps/web/e2e/auth-gate.spec.ts
- ADR-0009 路由表

**输出**（新增/修改的文件）
- `apps/web/middleware.ts`
- `apps/web/app/hot/page.tsx`
- `apps/web/app/hot/daily/page.tsx`
- `apps/web/app/public/page.tsx`
- `apps/web/e2e/auth-gate.spec.ts`
- apps/web/tests/middleware.spec.ts（新增）

**Execution Steps**
1. [ ] PUBLIC_PATHS/PUBLIC_PREFIXES 按 ADR 表修改
2. [ ] 游客可见页移除 AuthGate 包裹或改为可选登录态（按 ADR）
3. [ ] 新增 vitest：以 NextRequest 构造无 cookie 请求，逐路由断言 next() 或 redirect
4. [ ] e2e 矩阵 PROTECTED_PAGES 与注释同步 ADR

**验收标准**
- [ ] middleware 单测覆盖 ADR 表中每条路由
- [ ] vitest 全绿零回归；mock e2e 绿
- [ ] e2e 注释与 PROTECTED_PAGES 不再矛盾

**验证命令**
```bash
cd apps/web && pnpm run test:unit -- --run tests/middleware.spec.ts && pnpm run test:unit -- --run && pnpm run test:e2e
```

**证据路径**
`docs/06_validation/evidence/EVD-010/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/web/middleware.ts`
- `apps/web/app/hot/**`
- `apps/web/app/public/**`
- `apps/web/e2e/auth-gate.spec.ts`
- `apps/web/tests/middleware.spec.ts`

**禁止修改**
- apps/api/**
- packages/**
- apps/web/components/AuthGate.tsx（行为契约不变）

**依赖与阻塞**
- Depends on：TASK-009
- Blocks：TASK-011
- 阻塞条件：需要后端放开匿名接口（如 /hot/feed 无登录） → 停，属 Identity 契约变更

**建议执行档位**
sonnect　理由：规则已由 ADR 写死

**升级条件**
连续 2 次 e2e 红 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中

---

### TASK-011：访客策略文档对账

**归属**
- 所属切片：S2（WP-2 访客访问策略）
- 执行 Agent：Agent-Doc
- 来源需求：协作纪律 §5（文档与代码一致）
- 来源方案：ADR-0009

**目标**
CHANGELOG Unreleased、backlog AUTHGATE-002 与 ADR-0009 一致，无互相矛盾表述。

**输入**
- CHANGELOG.md:11-44
- docs/04_engineering/backlog.md AUTHGATE 节

**输出**（新增/修改的文件）
- `CHANGELOG.md`
- `docs/04_engineering/backlog.md`

**Execution Steps**
1. [ ] 删除/改写『middleware 裁定不实施』与『公共引流位保持可见』等与现状冲突的表述
2. [ ] backlog AUTHGATE-002 指向 ADR-0009 并附 TASK-010 提交哈希

**验收标准**
- [ ] python scripts/check_docs_consistency.py 退出 0
- [ ] 人工：CHANGELOG 与 ADR 无矛盾句

**验证命令**
```bash
python scripts/check_docs_consistency.py
```

**证据路径**
`docs/06_validation/evidence/EVD-011/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `CHANGELOG.md`
- `docs/04_engineering/backlog.md`

**禁止修改**
- apps/**
- packages/**

**依赖与阻塞**
- Depends on：TASK-010
- Blocks：无
- 阻塞条件：—

**建议执行档位**
haiku　理由：文档同步

**升级条件**
出现新冲突需判断 → sonnect；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小

---

### TASK-012：bot 域响应模型（Pydantic）声明并接入序列化

**归属**
- 所属切片：S3（WP-3 响应形状契约）
- 执行 Agent：Agent-API
- 来源需求：REQ-F-001；packages/contracts index.ts『响应形状生成器扩展已登记 backlog』
- 来源方案：ADR-0008（提议）

**目标**
bots.py 的渠道、任务、日志三类响应由 Pydantic 模型定义，出现在 /openapi.json components 中，线上 JSON 形状不变。

**输入**
- apps/api/app/api/v1/bots.py:134（_serialize_log 8 字段）、_serialize_channel（secret_enc→has_secret）
- DESIGN-001 §① bot 响应 Schema

**输出**（新增/修改的文件）
- apps/api/app/api/v1/schemas/bot.py（新增）
- `apps/api/app/api/v1/bots.py`
- apps/api/tests/test_bot_response_shape.py（新增）

**Execution Steps**
1. [ ] 新建 BotChannelOut/PushTaskOut/PushLogOut 与 PageOf[T] 泛型（page/page_size 口径）
2. [ ] 序列化函数改为构造模型后 model_dump(mode='json')，字段与现输出逐字一致
3. [ ] 路由声明 responses/response_model 使其进入 OpenAPI（信封保持 Envelope）
4. [ ] 新增快照测试：同一夹具改造前后 JSON 相等

**验收标准**
- [ ] 快照测试通过（形状零漂移）
- [ ] app.openapi()['components']['schemas'] 含三模型
- [ ] 后端全量 pytest 零回归；ruff/mypy 绿

**验证命令**
```bash
cd apps/api && pytest tests/test_bot_response_shape.py -q && python -c "from app.main import create_app;s=create_app().openapi()['components']['schemas'];assert {'BotChannelOut','PushTaskOut','PushLogOut'}<=set(s)" && ruff check app tests && mypy app
```

**证据路径**
`docs/06_validation/evidence/EVD-012/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/api/app/api/v1/schemas/bot.py`
- `apps/api/app/api/v1/schemas/__init__.py`
- `apps/api/app/api/v1/bots.py`
- `apps/api/tests/test_bot_response_shape.py`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- apps/api/app/api/v1/hot.py
- apps/web/**

**依赖与阻塞**
- Depends on：D-09（ADR-0008 批准）
- Blocks：TASK-014
- 阻塞条件：形状必须变化才能建模 → 停，属 API 契约变更

**建议执行档位**
sonnect　理由：模式化改造 + 快照测试

**升级条件**
快照不一致无法消除 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中

---

### TASK-013：hot 域响应模型（Pydantic）声明并接入序列化

**归属**
- 所属切片：S3（WP-3 响应形状契约）
- 执行 Agent：Agent-API
- 来源需求：REQ-F-002
- 来源方案：ADR-0008（提议）

**目标**
hot.py 的 topics/daily/feed 响应由 Pydantic 模型定义并进入 OpenAPI，线上 JSON 形状不变。

**输入**
- apps/api/app/api/v1/hot.py:89/193/344（分页返回点）
- DESIGN-001 §① hot 响应 Schema

**输出**（新增/修改的文件）
- apps/api/app/api/v1/schemas/hot.py（新增）
- `apps/api/app/api/v1/hot.py`
- apps/api/tests/test_hot_response_shape.py（新增）

**Execution Steps**
1. [ ] 新建 HotTopicOut/HotTopicDetailOut/DailyReportOut/FeedItemOut
2. [ ] 序列化改造 + 路由声明
3. [ ] 快照测试

**验收标准**
- [ ] 快照测试通过
- [ ] OpenAPI components 含四模型
- [ ] 全量 pytest 零回归；ruff/mypy 绿

**验证命令**
```bash
cd apps/api && pytest tests/test_hot_response_shape.py -q && ruff check app tests && mypy app
```

**证据路径**
`docs/06_validation/evidence/EVD-013/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/api/app/api/v1/schemas/hot.py`
- `apps/api/app/api/v1/hot.py`
- `apps/api/tests/test_hot_response_shape.py`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- apps/api/app/api/v1/bots.py
- apps/api/app/api/v1/schemas/__init__.py（归 TASK-012；本任务直接 import app.api.v1.schemas.hot，Python 3 命名空间包在 __init__ 尚未合并时同样可导入）
- apps/web/**

**依赖与阻塞**
- Depends on：D-09
- Blocks：TASK-014
- 阻塞条件：同 TASK-012

**建议执行档位**
sonnect　理由：同上

**升级条件**
同上；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中

---

### TASK-014：gen_contracts 生成响应形状 DTO（*Out）

**归属**
- 所属切片：S3（WP-3 响应形状契约）
- 执行 Agent：Agent-Contract
- 来源需求：契约唯一源
- 来源方案：ADR-0008

**目标**
packages/contracts 新增 bot/hot 的 *Out 响应类型，由 OpenAPI components 生成，并由 index.ts 导出；--check 覆盖。

**输入**
- scripts/gen_contracts.py:38-60（DOMAIN_REQUEST_SCHEMAS）
- TASK-012/013 的 OpenAPI 组件

**输出**（新增/修改的文件）
- `scripts/gen_contracts.py`
- `packages/contracts/src/bot/dto.ts`
- `packages/contracts/src/hot/dto.ts`
- `packages/contracts/src/index.ts`

**Execution Steps**
1. [ ] 新增 DOMAIN_RESPONSE_SCHEMAS 映射
2. [ ] _schema_to_ts 复用，产出 *Out 接口
3. [ ] index.ts 导出新类型（保留原实体导出，不破坏消费方）
4. [ ] --check 幂等 + 契约包 tsc

**验收标准**
- [ ] --check 退出 0
- [ ] 契约包与 apps/web tsc 零错
- [ ] index.ts 导出 7 个 *Out 类型

**验证命令**
```bash
cd apps/api && python ../../scripts/gen_contracts.py --check && cd ../web && pnpm exec tsc --noEmit -p ../../packages/contracts/tsconfig.json
```

**证据路径**
`docs/06_validation/evidence/EVD-014/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `scripts/gen_contracts.py`
- `packages/contracts/**`

**禁止修改**
- apps/**

**依赖与阻塞**
- Depends on：TASK-012、TASK-013
- Blocks：TASK-015
- 阻塞条件：生成器需要改实体导出名 → 停

**建议执行档位**
sonnect　理由：生成器扩展

**升级条件**
不幂等 2 次 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中

---

### TASK-015：前端 bots/hot API 层改用 *Out 契约类型

**归属**
- 所属切片：S3（WP-3 响应形状契约）
- 执行 Agent：Agent-App
- 来源需求：REQ-F-001/002
- 来源方案：ADR-0008

**目标**
apps/web/lib/api/bots.ts 与 hot.ts 的返回类型来自 @bothot/contracts 的 *Out，删除本地重复定义。

**输入**
- apps/web/lib/api/{bots,hot,types}.ts
- packages/contracts/src/index.ts（TASK-014 后）

**输出**（新增/修改的文件）
- `apps/web/lib/api/bots.ts`
- `apps/web/lib/api/hot.ts`
- `apps/web/lib/api/types.ts`
- `apps/web/lib/api/mock-data.ts`

**Execution Steps**
1. [ ] import type 替换本地类型
2. [ ] mock-data 以 satisfies 对齐新类型
3. [ ] 删除本地重复 interface（grep 确认零消费）

**验收标准**
- [ ] tsc 零错；vitest 零回归；mock e2e 绿
- [ ] grep 本地重复类型名零命中

**验证命令**
```bash
cd apps/web && pnpm exec tsc --noEmit && pnpm run test:unit -- --run && pnpm run test:e2e
```

**证据路径**
`docs/06_validation/evidence/EVD-015/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/web/lib/api/**`

**禁止修改**
- packages/**
- apps/api/**
- apps/web/components/**（若组件需改，回报）

**依赖与阻塞**
- Depends on：TASK-014
- Blocks：无
- 阻塞条件：组件层类型报错 > 10 处 → 停，回报拆分

**建议执行档位**
sonnect　理由：类型替换

**升级条件**
2 次失败 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中

---

### TASK-016：SSE 通知帧携带落库 id（后端）

**归属**
- 所属切片：S4（WP-4 通知去重）
- 执行 Agent：Agent-API
- 来源需求：REQ-F-001（站内通知）；backlog NOTIF-001 遗留待办
- 来源方案：DESIGN-001 §⑤ Events

**目标**
web 渠道每条实时帧带 id，且与 notifications 表行 id 相同。

**输入**
- apps/api/app/services/push_scheduler.py:222、267（persist_web_notification 在投递后）
- apps/api/app/providers/push/web.py（publish payload）
- apps/api/app/models/bothot_entities.py:265（Notification）

**输出**（新增/修改的文件）
- `apps/api/app/services/push_scheduler.py`
- `apps/api/app/providers/push/web.py`
- apps/api/app/providers/push/base.py（若 PushMessage 定义于此）
- apps/api/tests/test_notification_frame_id.py（新增）

**Execution Steps**
1. [ ] PushMessage 增可选 notification_id 字段（默认 None，其他渠道忽略）
2. [ ] _execute_task 在 web 渠道投递前 gen_uuid() 赋值
3. [ ] web.py 发布 JSON 增 id 字段
4. [ ] persist_web_notification 使用同一 id 落库
5. [ ] 连库测试：投递后 Redis 帧 id == 表行 id

**验收标准**
- [ ] 新连库测试通过
- [ ] test_notification_history.py 等既有用例零回归
- [ ] 其他 5 渠道 provider 测试零回归

**验证命令**
```bash
cd apps/api && pytest tests/test_notification_frame_id.py tests/test_notification_history.py tests/test_push_providers.py -q
```

**证据路径**
`docs/06_validation/evidence/EVD-016/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/api/app/services/push_scheduler.py`
- `apps/api/app/providers/push/**`
- `apps/api/tests/test_notification_frame_id.py`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- apps/web/**

**依赖与阻塞**
- Depends on：无
- Blocks：无
- 阻塞条件：需要改 Notification 表结构 → 停（会占迁移版本号）

**建议执行档位**
sonnect　理由：小范围后端改动，契约已冻结

**升级条件**
跨进程顺序问题导致测试不稳 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中

---

### TASK-017：NotificationBell 用帧 id 去重（前端）

**归属**
- 所属切片：S4（WP-4 通知去重）
- 执行 Agent：Agent-App
- 来源需求：同 TASK-016
- 来源方案：DESIGN-001 §⑤ Events

**目标**
实时帧的 id 写入 serverId；同一通知经 SSE 与历史各到一次时只显示一条。帧无 id 时保持现行内容窗口去重。

**输入**
- apps/web/components/NotificationBell.tsx:36、105-128
- DESIGN-001 §⑤ 帧 Schema（id 可选）

**输出**（新增/修改的文件）
- `apps/web/components/NotificationBell.tsx`
- apps/web/tests/notification-bell-dedupe.spec.tsx（新增）

**Execution Steps**
1. [ ] SSE onmessage 解析 id → serverId
2. [ ] 合并逻辑统一按 serverId 去重，缺失时回落现规则
3. [ ] vitest：先 SSE 后 history、先 history 后 SSE、帧无 id 三用例

**验收标准**
- [ ] 三用例全绿；既有 vitest 零回归

**验证命令**
```bash
cd apps/web && pnpm run test:unit -- --run
```

**证据路径**
`docs/06_validation/evidence/EVD-017/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/web/components/NotificationBell.tsx`
- `apps/web/tests/notification-bell-dedupe.spec.tsx`

**禁止修改**
- apps/api/**
- packages/**

**依赖与阻塞**
- Depends on：无
- Blocks：无
- 阻塞条件：—

**建议执行档位**
sonnect　理由：组件 + 单测

**升级条件**
2 次失败 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小（与 TASK-016 同刀演示）

---

### TASK-018：check_docs_consistency 入 CI 与 preflight

**归属**
- 所属切片：S5（WP-5 治理门禁）
- 执行 Agent：Agent-Guard
- 来源需求：roadmap v0.6.5 未勾项『治理脚本入 CI 强制步』
- 来源方案：—

**目标**
CI backend job 与 scripts/preflight.sh 都执行 check_docs_consistency.py，失败即红。

**输入**
- .github/workflows/ci.yml:97（契约漂移门禁附近）
- scripts/preflight.sh
- 现状：全仓 grep check_docs_consistency 仅脚本自身

**输出**（新增/修改的文件）
- `.github/workflows/ci.yml`
- `scripts/preflight.sh`

**Execution Steps**
1. [ ] ci.yml backend job 在契约门禁后加一步 python "$GITHUB_WORKSPACE/scripts/check_docs_consistency.py"
2. [ ] preflight.sh 加同名检查
3. [ ] actionlint 通过

**验收标准**
- [ ] actionlint 零告警
- [ ] CI 中该 step 存在且绿
- [ ] 故意在 backlog 写一个不存在路径时 step 红（本地验证）

**验证命令**
```bash
actionlint && bash scripts/preflight.sh && python scripts/check_docs_consistency.py
```

**证据路径**
`docs/06_validation/evidence/EVD-018/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `.github/workflows/ci.yml`
- `scripts/preflight.sh`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- scripts/check_docs_consistency.py

**依赖与阻塞**
- Depends on：无
- Blocks：无
- 阻塞条件：—

**建议执行档位**
haiku　理由：追加一步

**升级条件**
actionlint 红 → sonnect；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小

---

### TASK-019：文档漂移修正批（不含端口）

**归属**
- 所属切片：S5（WP-5 治理门禁）
- 执行 Agent：Agent-Doc
- 来源需求：协作纪律 §5、§8
- 来源方案：—

**目标**
以下已证实的漂移全部改为与代码一致：conventions.md（Node 版本、密钥现状、环境变量前缀、compose 路径、CORS 裁定、测试目录）、README（Next 版本、本地开发路径）、AGENTS『当前项目状态』（版本/Next）、product-requirements REQ-F-001（事件触发已实现）、roadmap v1.0 勾选、project-map 05–07 状态、backlog TEST-003。

**输入**
- 本规划 §2.3 不一致清单 X-01…X-12
- 代码证据：apps/web/package.json（next ^15.5.24、node >=24）、apps/web/.nvmrc=24.21.0、core/secret_crypto.py、tag v1.0.0、CI run 37906907637 success

**输出**（新增/修改的文件）
- `docs/04_engineering/conventions.md`
- `README.md`
- `AGENTS.md`
- `docs/02_requirements/product-requirements.md`
- `docs/04_engineering/roadmap.md`
- `docs/00_governance/project-map.md`
- `docs/04_engineering/backlog.md`

**Execution Steps**
1. [ ] 逐条按 §2.3 清单修改，每处附 文件:行 证据
2. [ ] 端口相关条目跳过（属 TASK-003）
3. [ ] 跑 check_docs_consistency

**验收标准**
- [ ] §2.3 中 X-01…X-12（端口项除外）逐条有对应 diff
- [ ] check_docs_consistency 退出 0

**验证命令**
```bash
python scripts/check_docs_consistency.py && grep -n 'Next.js 14\|cd backend\|Node 版本：22' README.md AGENTS.md docs/04_engineering/conventions.md; test $? -eq 1
```

**证据路径**
`docs/06_validation/evidence/EVD-019/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `docs/**`
- `README.md`
- `AGENTS.md`

**禁止修改**
- apps/**
- packages/**
- docker/**
- AGENTS.md 端口表段落

**依赖与阻塞**
- Depends on：无
- Blocks：无
- 阻塞条件：发现条目需代码改动才能一致 → 回报，不改代码

**建议执行档位**
sonnect　理由：需逐条核证据，haiku 易误改

**升级条件**
—；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中

---

### TASK-020：.docs/ 遗留『待迁移』6 项：迁移或归档

**归属**
- 所属切片：S5（WP-5 治理门禁）
- 执行 Agent：Agent-Doc
- 来源需求：docs/00_governance/doc-migration-map.md 中 6 条『待迁移』
- 来源方案：—

**目标**
doc-migration-map 中不再有『待迁移』状态；每项要么已迁移并与代码核对，要么归档并注明原因。

**输入**
- docs/00_governance/doc-migration-map.md
- .docs/03_solution/interfaces/API接口文档.md（162KB，AideanBot 时代）
- .docs/03_solution/interfaces/数据库文档.md
- SSO 3 文件、test-plans 2 文件

**输出**（新增/修改的文件）
- `docs/00_governance/doc-migration-map.md`
- `docs/09_archive/superseded/**`
- docs/03_solution/**（若选迁移）

**Execution Steps**
1. [ ] 按 D-05 结论执行
2. [ ] 若迁移 API 文档：以 FastAPI /openapi.json 为准，不手抄旧文档

**验收标准**
- [ ] grep -c '待迁移' doc-migration-map.md == 0

**验证命令**
```bash
grep -c '待迁移' docs/00_governance/doc-migration-map.md
```

**证据路径**
`docs/06_validation/evidence/EVD-020/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `docs/**`

**禁止修改**
- apps/**
- .docs/**（只读，不删）

**依赖与阻塞**
- Depends on：D-05
- Blocks：无
- 阻塞条件：D-05 未裁决 → blocked

**建议执行档位**
haiku（归档）/ sonnect（迁移）　理由：视裁决

**升级条件**
—；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中

---

### TASK-021：性能基线测量脚本与首测

**归属**
- 所属切片：S6（WP-6 基线指标）
- 执行 Agent：Agent-Guard
- 来源需求：REQ-NF-001（API<500ms、首 Token<3s、单篇入库<30s、Feed<100ms）
- 来源方案：§11 基线指标

**目标**
M-01…M-04 四项各有可复跑脚本与一次首测数值（含环境说明），落入 test-results。

**输入**
- 本规划 §11 指标定义
- 运行中的 compose 栈（共享底座）
- Job 表 created_at/updated_at（入库耗时来源）

**输出**（新增/修改的文件）
- scripts/bench/api_latency.py（新增）
- scripts/bench/chat_ttft.py（新增）
- scripts/bench/ingest_duration.sql（新增）
- `docs/06_validation/test-results/2026-10-perf-baseline.md`

**Execution Steps**
1. [ ] api_latency：对 GET /api/v1/hot/feed?page=1&page_size=20 与 GET /api/v1/bots/tasks 各 50 次，输出 p50/p95
2. [ ] chat_ttft：POST /api/v1/chat/ask 测首个 SSE data 帧时间，10 次
3. [ ] ingest_duration：对近 7 天成功 Job 计算 p50/p95（只读 SQL）
4. [ ] M-04 Feed DB 时间：EXPLAIN ANALYZE 复用 2026-10-08 留证口径
5. [ ] 汇总报告写明机器、数据量、时间

**验收标准**
- [ ] 四项指标均有数值或明确『无法测量 + 原因』
- [ ] 脚本可在同环境复跑，结果偏差记录

**验证命令**
```bash
python scripts/bench/api_latency.py --base http://127.0.0.1:3300 --n 50
python scripts/bench/chat_ttft.py --n 10
```

**证据路径**
`docs/06_validation/evidence/EVD-021/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `scripts/bench/**`
- `docs/06_validation/test-results/**`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- apps/**

**依赖与阻塞**
- Depends on：TASK-002（栈可起）
- Blocks：任何性能优化任务（本规划不排）
- 阻塞条件：无可用会话 cookie / 无测试数据 → 回报，不伪造

**建议执行档位**
sonnect　理由：脚本编写 + 实测

**升级条件**
结果离散度 > 50% → opus 复核方法；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中

---

### TASK-022：BotBinding 死表处置（条件：D-03）

**归属**
- 所属切片：S7（WP-7 待裁决处置）
- 执行 Agent：Agent-Data
- 来源需求：TASK-PLAN-v0.9 S2.3
- 来源方案：—

**目标**
A：删除 BotBinding 模型与表（迁移 ab1006w6a）；B：保留并在 entities.py 注明保留理由。二选一完成。

**输入**
- apps/api/app/models/entities.py（class BotBinding）
- grep：除模型外仅注释提及（admin.py:16、process_heartbeat.py:27）
- 迁移链当前单头 ab1005w5b

**输出**（新增/修改的文件）
- A：apps/api/app/models/entities.py、apps/api/alembic/versions/ab1006w6a_drop_bot_binding.py、scripts/gen_contracts（无需）
- B：apps/api/app/models/entities.py（注释）

**Execution Steps**
1. [ ] A：模型删除 → 新迁移 down_revision='ab1005w5b'，upgrade drop_table、downgrade 重建 → 单头断言
2. [ ] B：只加注释

**验收标准**
- [ ] A：alembic heads 单头 = ab1006w6a；upgrade/downgrade 往返在隔离 PG 通过；全量 pytest 零回归
- [ ] B：文档登记

**验证命令**
```bash
cd apps/api && python -m alembic heads && python -m alembic upgrade head && python -m alembic downgrade -1 && python -m alembic upgrade head
```

**证据路径**
`docs/06_validation/evidence/EVD-022/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/api/app/models/entities.py`
- `apps/api/alembic/versions/ab1006w6a_drop_bot_binding.py`

**禁止修改**
- packages/**
- apps/web/**

**依赖与阻塞**
- Depends on：D-03
- Blocks：无
- 阻塞条件：发现生产库该表有数据 → 停

**建议执行档位**
sonnect（执行）+ opus（迁移审）　理由：迁移不可逆风险

**升级条件**
—；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小

---

### TASK-023：embedding.py 处置（条件：D-06）

**归属**
- 所属切片：S7（WP-7 待裁决处置）
- 执行 Agent：Agent-API
- 来源需求：TASK-PLAN-v0.9 S2.6；backlog HOT-005
- 来源方案：—

**目标**
A：删除 app/providers/embedding.py 与 tests/test_embedding.py；B：保留并登记为 HOT-005 前置。

**输入**
- grep：app.providers.embedding 仅 tests/test_embedding.py 引用

**输出**（新增/修改的文件）
- A：两文件删除（rm + git add，遵守『禁止 git rm』）
- B：backlog 注记

**Execution Steps**
1. [ ] A：rm 两文件 → 全量 pytest → ruff/mypy
2. [ ] B：仅文档

**验收标准**
- [ ] A：git grep 'providers.embedding' 零命中；pytest 零回归

**验证命令**
```bash
git grep -n 'providers.embedding'; cd apps/api && pytest -q
```

**证据路径**
`docs/06_validation/evidence/EVD-023/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/api/app/providers/embedding.py`
- `apps/api/tests/test_embedding.py`
- `docs/04_engineering/backlog.md`

**禁止修改**
- 其余全部

**依赖与阻塞**
- Depends on：D-06
- Blocks：无
- 阻塞条件：—

**建议执行档位**
haiku　理由：删除或注记

**升级条件**
pytest 红 → sonnect；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小

---

### TASK-024：.project/ 第三方源码去留（条件：D-07）

**归属**
- 所属切片：S7（WP-7 待裁决处置）
- 执行 Agent：Agent-Guard
- 来源需求：仓库卫生
- 来源方案：—

**目标**
A：.project/ 移出版本库并 gitignore；B：保留并在 README/AGENTS 说明用途与许可。

**输入**
- .project/（7 个第三方项目，125M，git ls-files 4385 个文件）

**输出**（新增/修改的文件）
- A：.gitignore、.project/**（rm + git add）
- B：AGENTS.md 一节

**Execution Steps**
1. [ ] A：外部备份 → rm -r .project → git add -u .project → .gitignore 加条目
2. [ ] B：写明用途

**验收标准**
- [ ] A：git ls-files .project | wc -l == 0；CI 绿

**验证命令**
```bash
git ls-files .project | wc -l
```

**证据路径**
`docs/06_validation/evidence/EVD-024/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `.gitignore`
- `.project/**`
- `AGENTS.md`

**禁止修改**
- apps/**
- packages/**

**依赖与阻塞**
- Depends on：D-07
- Blocks：无
- 阻塞条件：发现 apps/** 引用 .project 内文件 → 停

**建议执行档位**
haiku　理由：机械操作

**升级条件**
—；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小

---

### TASK-025：real-backend e2e 解阻并转为阻塞门禁（外部依赖）

**归属**
- 所属切片：S8（WP-8 真实链路验收）
- 执行 Agent：Agent-App
- 来源需求：backlog TEST-002；roadmap v1.0『全量测试通过』
- 来源方案：—

**目标**
e2e/real-backend.spec.ts 在 compose 栈上以真实 OIDC 登录跑通 4 条用例，CI 中去掉 continue-on-error。

**输入**
- apps/web/e2e/real-backend.spec.ts
- .github/workflows/ci.yml:302-305（non-blocking）
- 外部：主平台 oidc_clients.redirect_uris 白名单、测试账号、真实文章 URL

**输出**（新增/修改的文件）
- `apps/web/e2e/real-backend.spec.ts`
- `.github/workflows/ci.yml`

**Execution Steps**
1. [ ] 确认三项外部前置（D-08）
2. [ ] 本地栈跑通 4 用例
3. [ ] CI 侧提供测试凭据（仓库 secret，由人配置）后去掉 continue-on-error

**验收标准**
- [ ] 4 用例绿 3 次连续
- [ ] CI 中该 step 为阻塞

**验证命令**
```bash
cd apps/web && E2E_REAL_BACKEND=1 pnpm run test:e2e -- e2e/real-backend.spec.ts
```

**证据路径**
`docs/06_validation/evidence/EVD-025/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/web/e2e/real-backend.spec.ts`
- `.github/workflows/ci.yml`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- apps/api/**

**依赖与阻塞**
- Depends on：D-08
- Blocks：无
- 阻塞条件：外部前置缺任一 → blocked

**建议执行档位**
sonnect　理由：脚本修复

**升级条件**
链路问题跨前后端 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中


---

## 8. 依赖 DAG

```text
图例：A → B 表示 B 依赖 A；[D-xx] 为人工裁决；( ) 内为执行 Agent

[无前置]
  TASK-001 (人工)            TASK-002 (Guard) ──→ TASK-003 (Doc) ←── [D-02]
  TASK-004 (Guard)           TASK-005 (Guard)
  TASK-016 (API)             TASK-017 (App)
  TASK-018 (Guard)           TASK-019 (Doc)

[D-09] ──→ TASK-006 (Contract) ──→ TASK-007 (Contract) ──→ TASK-008 (App)
[D-09] ──→ TASK-012 (API) ──┐
[D-09] ──→ TASK-013 (API) ──┴──→ TASK-014 (Contract) ──→ TASK-015 (App)
        TASK-007 ─────────────────→ TASK-014   （同改 gen_contracts.py，必须串行）

[D-01] ──→ TASK-009 (Doc/opus) ──→ TASK-010 (App) ──→ TASK-011 (Doc)
TASK-002 ──→ TASK-021 (Guard)
[D-05] ──→ TASK-020    [D-03] ──→ TASK-022    [D-06] ──→ TASK-023
[D-07] ──→ TASK-024    [D-08] ──→ TASK-025
```

**可并行组（按机械规则判定，§7.1 四条：无共享可变状态 ∧ 契约已冻结可校验 ∧ 文件所有权不相交 ∧ 不共用迁移号；另叠加 §8.1「Contract 与 Guard 不与实现并行改」「同时最多 3 个写入 Agent」）**

| 阶段 | 并行组 | 满足依据 |
|---|---|---|
| P1 守卫期 | 002 → 004 → 005 → 018（同一 Agent-Guard 会话串行）∥ 019（Doc）∥ 001（人工） | Guard 期间无实现任务在跑；Guard 与 Doc 文件集不相交（§9）；无迁移；无共享运行时状态 |
| P2 实现期 A | 016（API）∥ 017（App）∥ 021（Guard 脚本，需 002 已合并） | 016 改 push_scheduler/providers，017 改 NotificationBell，021 只新增 scripts/bench 与 test-results → 不相交；016/017 共同依赖的帧 Schema 已在 §4.⑤ 冻结且 `id` 可选、向后兼容；无迁移。注：021 只新增独立脚本、不改任何门禁，不属于「改守卫」，故可与实现并行 |
| P3 契约期 1（D-09 后） | 006 → 007（同一 Agent-Contract 会话串行） | 契约期无实现任务在跑 |
| P4 实现期 B | 008（App）∥ 012（API）∥ 013（API） | 008 改 http.ts；012 改 bots.py + schemas/bot.py + schemas/__init__.py；013 改 hot.py + schemas/hot.py → 不相交；依赖的错误契约（P3 产物）与响应 Schema（§4.①）已冻结；无迁移；共 3 个写入者 |
| P5 契约期 2 | 014 | 单任务 |
| P6 实现期 C | 015 ∥ 009（Doc，若 D-01 已裁决） | 015 改 apps/web/lib/api/**，009 改 decisions/** → 不相交 |
| P7 | 010 → 011；条件任务 020/022/023/024/025 随裁决插入实现期 | 022 占迁移号 ab1006w6a，期间不得有其他迁移 |

**必须串行的链**

1. 006 → 007 → 008（契约源 → 生成物 → 消费方）
2. 007 → 014（同一文件 `scripts/gen_contracts.py`，所有权相交）
3. 012/013 → 014 → 015
4. 009 → 010 → 011
5. 002 → 003；002 → 021（需能起栈）
6. 018 → 025（同改 ci.yml）

**关键路径**：`P1 守卫期 → [D-09] → 006 → 007 → {008 ∥ 012 ∥ 013} → 014 → 015`（不含裁决等待约 4 个工作日）。若 D-09 延迟，可先完成 `P1 → P2`（约 1.5 天），关键路径随裁决到达时间顺延。

**环检测**：对上图做拓扑排序（001,002,004,005,016,017,018,019 → 003,006,012,013,021 → 007 → 008,014 → 015；009 → 010 → 011；条件任务 020/022/023/024/025 无出边），**无环**。

---

## 9. 所有权矩阵

| 路径 | Contract | App | API | Data | Guard | Doc | 人工 |
|---|---|---|---|---|---|---|---|
| packages/contracts/** | ✍ 007 014 | | | | | | |
| scripts/gen_contracts.py | ✍ 007 014 | | | | | | |
| apps/api/app/core/errors.py | ✍ 006 | | | | | | |
| apps/api/tests/test_error_registry.py | ✍ 006 | | | | | | |
| apps/api/app/api/v1/bots.py、schemas/bot.py、schemas/__init__.py | | | ✍ 012 | | | | |
| apps/api/app/api/v1/hot.py、schemas/hot.py | | | ✍ 013 | | | | |
| apps/api/app/services/push_scheduler.py、providers/push/** | | | ✍ 016 | | | | |
| apps/api/app/providers/embedding.py、tests/test_embedding.py | | | ✍ 023 | | | | |
| apps/api/app/models/entities.py、alembic/versions/ab1006w6a_* | | | | ✍ 022 | | | |
| apps/web/lib/api/http.ts | | ✍ 008 | | | | | |
| apps/web/lib/api/{bots,hot,types,mock-data}.ts | | ✍ 015 | | | | | |
| apps/web/middleware.ts、app/hot/**、app/public/**、e2e/auth-gate.spec.ts | | ✍ 010 | | | | | |
| apps/web/components/NotificationBell.tsx | | ✍ 017 | | | | | |
| apps/web/e2e/real-backend.spec.ts | | ✍ 025 | | | | | |
| docker/compose.yml、docker/.env.example | | | | | ✍ 002 | | |
| .gitleaks.toml、.github/workflows/security.yml | | | | | ✍ 004 | | |
| .github/workflows/ci.yml | | 025（仅 302-305 行） | | | ✍ 018 | | |
| .dockerignore | | | | | ✍ 005 | | |
| scripts/preflight.sh | | | | | ✍ 018 | | |
| scripts/bench/**、docs/06_validation/test-results/** | | | | | ✍ 021 | | |
| .gitignore、.project/** | | | | | ✍ 024 | | |
| AGENTS.md、README.md、docs/04_engineering/conventions.md | | | | | | ✍ 003（端口段）019（其余） | |
| docs/03_solution/decisions/** | | | | | | ✍ 009 | |
| CHANGELOG.md、docs/04_engineering/backlog.md | | | | | | ✍ 011 019 023(B) | |
| docs/**（其余） | | | | | | ✍ 019 020 | |
| docs/06_validation/evidence/EVD-001/** | | | | | | | ✍ 001 |

**重叠检查与消除**

- `ci.yml`：018（Guard）与 025（App）同文件 → **按行段拆分不够安全**，规定 025 在 018 合并后才开工（025 本就被 D-08 阻塞），时间上不重叠。
- `AGENTS.md / README / conventions.md`：003 与 019 同文件 → 规定由同一 Agent-Doc 会话串行执行，003 在 019 之后（019 跳过端口段）。
- `backlog.md`：011、019、023(B) → 同一 Agent-Doc 串行。
- 其余路径无重叠。

**新增 Agent 说明**：在 §8.1 五个 Agent 之外增加 **Agent-Doc**（只写 docs/、README、AGENTS、CHANGELOG），理由：本轮文档任务 7 个，放进 Guard 会使 Guard 与实现并行时违反「Guard 不与实现并行改」。

---

## 10. 档位分配与成本预算

| 档位 | 用途（本轮） |
|---|---|
| fable | 不预分配；仅在 D-01 或 D-09 的裁决要推翻已冻结的 Identity / 契约语义时启用 |
| opus | TASK-006（契约源）、TASK-009（安全边界 ADR）、TASK-022 迁移审查、每切片开工前契约审、熔断升级 |
| sonnect | 实现、测试、生成器、配置、需核证据的文档 |
| haiku | 纯文档替换、一行配置、机械删除 |

> 规则要求「默认档 = opus」：凡任务卡未写明档位或执行中出现卡外情况，一律按 opus 处理。卡上写 sonnect/haiku 的，都附了理由与升级条件。

| 切片 | 任务数 | haiku | sonnect | opus | fable | 人工 |
|---|---|---|---|---|---|---|
| S0 | 5 | 2（003、005） | 2（002、004） | 0 | 0 | 1（001） |
| S1 | 3 | 0 | 2（007、008） | 1（006） | 0 | 0 |
| S2 | 3 | 1（011） | 1（010） | 1（009） | 0 | 0 |
| S3 | 4 | 0 | 4 | 0 | 0 | 0 |
| S4 | 2 | 0 | 2 | 0 | 0 | 0 |
| S5 | 3 | 1–2（018、020 归档） | 1–2（019、020 迁移） | 0 | 0 | 0 |
| S6 | 1 | 0 | 1 | 0 | 0 | 0 |
| S7 | 3 | 2（023、024） | 1（022） | 1（022 迁移审） | 0 | 0 |
| S8 | 1 | 0 | 1 | 0 | 0 | 0 |
| **合计** | **25** | **6–7** | **15–16** | **4** | **0** | **1** |

**券制度**：opus 每切片 ≤3 次（契约审 / 卡住升级 / 高风险 review）；fable 每切片 ≤1 次且须人批准；超出需人批准。

**熔断**：同一任务连续 2 次验收失败 → 停止改代码，改为重写任务书 / 升级档位 / 标 blocked，禁止换提示词硬撞第 3 次。

---

## 11. 基线指标

| # | 用户可感操作 | 指标 | 目标（REQ-NF-001） | 与用户耗时的关系 | 首次测量值 |
|---|---|---|---|---|---|
| M-01 | 打开热点 Feed 首页 | `GET /api/v1/hot/feed?page=1&page_size=20` 服务端 p95 | <100ms | 首屏数据等待的主要部分；DB 时间之外还含序列化与网络 | **尚无基线**（只有 DB 层 EXPLAIN，见 M-01b） |
| M-01b | 同上（DB 层） | 对应 SQL 的 EXPLAIN ANALYZE 执行时间 | — | 仅是 M-01 的组成部分，**不得**单独作为优化目标 | 通知历史同类查询 0.034ms（定向）/ 约 0.38ms（5000 行广播分支），2026-10-08 留证；Feed 查询本身**未测** |
| M-02 | 打开推送任务列表 | `GET /api/v1/bots/tasks` 服务端 p95 | <500ms | 管理页首屏等待 | **尚无基线** |
| M-03 | 提问到看见第一个字 | `POST /api/v1/chat/ask` 首个 SSE data 帧时间 | <3s | 直接等于用户等待 | **尚无基线** |
| M-04 | 提交一篇文章到可检索 | 单篇入库 Job（created_at→成功终态）p50/p95 | <30s | 直接等于用户等待 | **尚无基线**（可从 jobs 表只读计算） |

- 首测由 TASK-021 完成。**在 TASK-021 交付前，本规划不排任何性能优化任务**；交付后，只有离目标最远且与用户耗时有直接关系的指标才可立项优化。
- 已下线的候选指标：前端包体积（无证据表明它是当前用户耗时瓶颈）、聚簇耗时（后台任务，用户不直接等待）。

---

## 12. 风险清单 / 未决问题 / 待裁决清单

### 12.1 风险

| # | 风险 | 可能性 | 影响 | 应对 |
|---|---|---|---|---|
| K-01 | 泄露口令在 git 历史中永久存在（public 仓库） | 已发生 | 高 | TASK-001 轮换是唯一有效手段；改写历史与协作纪律冲突，不做 |
| K-02 | 共享底座 PG 是否对公网可达**未知** | 未知 | 若可达则高 | 请人确认 5435 的监听地址与防火墙 |
| K-03 | 响应模型改造引入线上形状漂移 | 中 | 中 | 快照测试为硬门禁，不一致即停 |
| K-04 | D-01 若选「游客可看 /hot」，需开放后端匿名读，扩大攻击面 | 视裁决 | 中 | ADR-0009 列出限流与字段裁剪要求 |
| K-05 | 其他域（spaces/jobs/subscriptions/chat）仍无响应形状契约 | 确定 | 中 | 本轮只做 bot/hot；后续按同模式扩展 |
| K-06 | 多 AI 会话并行导致工作树交错（协作纪律已记录） | 中 | 中 | 执行者遵守 §1 开工取证、只 add 自己路径 |
| K-07 | `.docs/` 两个超大文件未通读，可能漏掉未迁移需求 | 低-中 | 中 | D-05 处理时顺带检索「未实现」「待办」关键词 |
| K-08 | 本规划未本地跑测试，「1002 passed」依赖文档与 CI 绿 | 低 | 低 | 第一刀开工前执行者先跑一次全量作为基线 |

### 12.2 未决问题（需信息，不需拍板）

- Q-01 共享底座 PG（5435）是否只监听本机？（影响 K-02 严重度）
- Q-02 主平台 OIDC 是否已把 BotHot 的 redirect_uri 加入白名单？（D-08）
- Q-03 生产环境 bot_bindings 表是否有数据？（D-03 的前提）
- Q-04 `.project/` 中的第三方项目许可证是否允许随仓库公开分发？（D-07 的前提）

### 12.3 待裁决清单（需人拍板）

| # | 问题 | 选项 | 规划默认推荐（仅供参考，不代替裁决） |
|---|---|---|---|
| D-01 | 游客访问 /hot、/hot/daily、/public | A：全部需登录（现状代码）＋把真实态 302 写进契约；B：/hot、/hot/daily 游客可看（后端开放匿名只读 + 限流），/public 需登录；C：三者都游客可看 | 无推荐：这是产品决定。A 改动最小 |
| D-02 | 端口与底座口径 | A：以共享底座为准（改 AGENTS 端口表为 5435/6379）；B：compose 恢复栈内 PG/Redis（5433/6380），共享底座改为 override 文件 | B 与 AGENTS 强制约束一致，且 CI 已有 compose.ci.yml 同类做法 |
| D-03 | bot_bindings | A 删除 / B 保留 | 先回答 Q-03 |
| D-04 | 前端遗留错误码 | A 删除 / B 保留在 LEGACY 表（默认假设） | B |
| D-05 | .docs/ 6 项 | A 迁移 / B 归档 | B（旧文档属 AideanBot 时代，API 文档应以 OpenAPI 为准） |
| D-06 | embedding.py | A 删除 / B 保留给 HOT-005 | 视 HOT-005 是否立项 |
| D-07 | .project/ | A 移出版本库 / B 保留并说明 | 先回答 Q-04 |
| D-08 | real-backend e2e 外部前置 | 外部提供 / 继续非阻塞 | — |
| D-09 | ADR-0008 契约唯一源 | 批准 / 否决 | 批准（与现有 gen_contracts 方向一致，只是扩大覆盖） |

---

## 13. 落盘清单

见下表（路径均相对仓库根，写在本地分支 `plan/2026-10-12-remaining-tasks`，**未推送**）。

| 路径 | 用途 |
|---|---|
| `docs/04_planning/current-plan.md` | 本规划全文（16 节） |
| `docs/03_solution/design/DESIGN-001-contract-freeze-pack.md` | 六份契约冻结包（与 §4 同文） |
| `docs/03_solution/decisions/adr-0008-contract-single-source.md` | ADR-0008 契约唯一源（proposed） |
| `docs/03_solution/decisions/adr-0009-guest-access-policy.md` | ADR-0009 访客访问策略（proposed，待 D-01） |
| `docs/03_solution/decisions/adr-0010-externalize-connection-strings.md` | ADR-0010 连接串外置（proposed） |
| `docs/05_execution/task-template.md` | 任务卡模板（16 字段） |
| `docs/05_execution/task-index.md` | 任务索引（25 张卡，状态/依赖/档位） |
| `docs/05_execution/tasks/TASK-001.md … TASK-025.md` | 25 张原子任务卡 |
| `docs/00_governance/glossary.md` | 末尾追加「规划期新增术语」一节 |
| `docs/03_solution/decisions/adr-index.md` | 登记 ADR-0008/0009/0010（proposed） |

**未写入（及原因）**

| 路径 | 原因 |
|---|---|
| docs/03_solution/architecture.md | 已存在且 active；本规划不改架构，只在 ADR 中提议 |
| docs/04_planning/roadmap.md | 已有 `docs/04_engineering/roadmap.md`，再建一份会成为第二来源；切片路线已在本文件 §6 |
| packages/contracts/** | 契约变更须先批准 ADR-0008（AGENTS「先登记后实现」）；目标产物样式已冻结在 §4，由 TASK-007/014 生成 |
| database/migrations/001_init.sql | alembic 是唯一迁移源，v0.7 裁定不启用该目录（§5） |

---

## 14. 自检结果

| 项 | 结果 | 说明 |
|---|---|---|
| 每条 MUST 可写成可验证句 | ✅ | §3.2 R-M1…R-M5 |
| 冲突全部列出，未替用户决定 | ✅ | C-01…C-07；D-01/D-02 未擅定 |
| BLOCKING 已列并给条件方案 | ✅ | §3.4、§12.3 |
| 未伪造需求或方案 | ✅ | 无新功能；每项附证据 |
| 六份契约齐全、机器可校验 | ⚠️ 部分 | 错误码、bot/hot 响应、通知帧可机器校验；其余域响应形状未覆盖（K-05），本轮不需要 |
| 唯一源已指定 | ✅（待 D-09） | ADR-0008 |
| 三方能凭契约独立开工 | ✅（对本轮任务） | §4.4 |
| 错误码覆盖已知失败路径 | ✅ | 23 码 |
| 管理端越权路径已禁止 | ✅ | §4.③ |
| 按垂直切片划分 | ✅ | §6 |
| 每刀可独立演示验收 | ✅ | §6 演示列 |
| 第一刀是步行骨架 | ⚠️ 已存在 | 骨架已在代码中（§6 首段证据）；S0 负责让它安全可复现 |
| 任务卡 16 项字段齐全 | ✅ | 25 张卡，生成器统一渲染 |
| 每张卡有验证命令 | ✅ | TASK-001 为人工命令 |
| 每张卡有允许/禁止路径 | ✅ | |
| 每个任务可追溯到需求 | ✅ | 「来源需求」字段 |
| DAG 无环 | ✅ | §8 |
| 并行结论附机械依据 | ✅ | §8 可并行组表 |
| 关键路径已标 | ✅ | §8 |
| 所有权矩阵无重叠 | ✅（经时序消除） | §9 三处同文件按串行消除 |
| 每任务有档位与理由 | ✅ | |
| 成本预算表 | ✅ | §10 |
| 基线指标有首测或标「尚无基线」 | ✅ | §11 |
| 风险/未决/待裁决分开 | ✅ | §12 |
| 未修改业务代码 | ✅ | 只写 docs/ |
| 无无证据绝对结论 | ✅ | |
| 未用「最佳实践」替代证据 | ✅ | |
| 未验证项已标注 | ✅ | §2.2 |

两项 ⚠️ 已说明理由，不属于「带着未过项输出」：一项是本轮范围外的契约覆盖，一项是骨架已存在无需重建。

---

## 15. 本次规划的前提与局限

- 基线钉在 `main@60e5723`。并行会话若之后推进了 main，执行者开工前须按协作纪律 §1 重新取证，冲突时以新 HEAD 为准并更新本文件。
- 未本地运行后端 pytest、前端 vitest/e2e、compose 起栈；测试数与可运行性依赖 AGENTS.md 记载与 GitHub Actions 结论。
- 外部系统（主平台、共享底座、LangBot、推送渠道、文章平台）全部未实测。
- `.docs/` 两个超大历史文件只抽样，见 K-07。
- 工期估算基于任务规模经验，没有本项目的历史速度数据，只能作排序参考。
- 档位名沿用指令中的 `fable / opus / sonnect / haiku`。

---

## 16. 建议的第一刀与启动顺序

**第一刀 = S0 安全止血**，原因：public 仓库中有可用口令（F-10），这是唯一在持续造成风险的问题，而且不依赖任何裁决。

启动顺序：

1. **今天，人工**：TASK-001 轮换 `bothot_rw` 口令；回答 Q-01（5435 是否对外）。
2. **P1 守卫期**：Agent-Guard 一个会话串行做 002 → 004 → 005 → 018；同时 Agent-Doc 做 019（跳过端口段）。
3. **P2 实现期 A**：016（API）、017（App）、021（Guard 新增测量脚本）三个并行。
4. **把 D-01、D-02、D-09 三个裁决交给人**。D-09 批准后进入 P3（006 → 007）与 P4（008 ∥ 012 ∥ 013）。
5. D-02 裁决后，Agent-Doc 在 019 之后做 003。
6. D-01 裁决后做 009 → 010 → 011；D-03/D-05/D-06/D-07/D-08 随到随插。
