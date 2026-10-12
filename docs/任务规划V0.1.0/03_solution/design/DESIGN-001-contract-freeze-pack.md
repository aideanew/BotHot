---
id: DESIGN-001
type: design
title: 契约冻结包（本轮剩余任务）
status: proposed
owner: architecture
created: 2026-10-12
updated: 2026-10-12
baseline_commit: 60e5723
---

# 契约冻结包

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
