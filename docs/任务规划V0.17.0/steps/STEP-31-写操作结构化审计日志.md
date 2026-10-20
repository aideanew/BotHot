# STEP-31 运营与管理写操作的结构化审计日志（V0.17.0 新增，D-V17-02）

| 字段 | 值 |
|---|---|
| 归属-切片 | S-M1 安全（"谁在什么时候改了推送渠道 / 删了空间"必须查得到） |
| 归属-需求 | 冻结契约 `docs/任务规划V0.12.0/contracts/identity.schema.json#/x-permission-matrix` 运营端一档"写操作须记录操作者 sub"；P-49；R-V14-03 |
| 归属-方案 | **D-V17-02（规划方已定设计，本卡只实现）** |
| 里程碑 | M2 |
| 执行者 | 执行 Agent-API |
| 档位 | sonnet　理由：设计已冻结，实现是一个中间件 + 一个依赖 + 按路由表生成的测试 |
| 规模 | 小（4 项，≈0.8 人日） |
| 依赖 | Depends on：29（敏感形门）　Blocks：12 |
| 基线 | main@81205f1 |

## 现读
- `grep -ri audit apps/api/app` 0 命中：没有任何审计设施。
- 推送域、管理端、引擎 Key、来源的写操作只有 `require_roles` 门，不留操作者痕迹。
- 已有 structlog 与 `RequestIdMiddleware`（`app/core/logging.py`、`app/core/middleware.py`、`app/core/request_context.py`）。

## 设计（D-V17-02，照做，不改口径）
| 项 | 规定 |
|---|---|
| 覆盖面 | 路径前缀 `/api/v1/bots`、`/api/v1/admin`、`/api/v1/sources` 下所有 `POST/PUT/PATCH/DELETE` |
| 时机 | 请求结束后（拿得到最终状态码）写一条；被拒的 4xx 也写；**401 不写**（没有操作者） |
| 载体 | structlog 一条 `event="audit"` 的 info 日志；**零迁移** |
| 字段（固定 9 个，键名照抄） | `actor_sub`、`actor_role`、`method`、`route`（路由模板，如 `/api/v1/bots/{channel_id}`，不是实际 URL）、`path_params`（字典）、`status`（HTTP）、`code`（信封业务码，取不到为 null）、`request_id`、`ts`（ISO 8601 带时区） |
| 禁止 | 绝不记录请求体、响应体、查询串、请求头；`path_params` 只放路由声明的参数 |
| 操作者从哪来 | 在三个路由组上挂一个依赖，把已认证的 `sub` 与角色写进 `request.state`；中间件只读 `request.state`，不自己解析会话 |

## 目标（可验证的一句话）
上述前缀下每个写操作（由路由表枚举，不手写清单）被一个已登录用户请求后，日志里恰好出现一条字段齐全的 `audit` 记录，且记录里不含请求体中的任何值。

## Execution Steps
1. [ ] **S31.1 先红**：新建 `tests/test_audit_log.py`，从路由表枚举三个前缀下的写操作（复用 `tests/test_idor_matrix.py` 的 `_enumerate_operations`），每个操作用 admin 身份请求一次，断言捕获到恰好 1 条 `event=audit`；改前全红，红的读数入 EVD。
2. [ ] **S31.2 实现**：依赖写 `request.state.audit_actor`；中间件按设计表写日志。
3. [ ] **S31.3 负面断言**：请求体里放一个标记串（如 `s31-body-marker`），断言任何审计记录里都没有它；匿名请求（401）不产生审计记录；普通用户被拒（403）产生一条且 `status=403`、`code=10004`。
4. [ ] **S31.4 反证**：临时把中间件从 app 上摘掉 ⇒ S31.1 全红；还原后全绿。读数入 EVD。

## 验收标准
- [ ] 审计用例数 = 枚举出的写操作数（打印入 EVD），全部通过
- [ ] 负面断言与反证读数入 `docs/06_validation/evidence/EVD-V17-31/`
- [ ] 本机真库全量 `failed = 0`；ruff、mypy 全绿
- [ ] 若新增连库用例，同步抬 `.github/workflows/ci-windows.yml` 的 `SKIP_BASELINE_WIN` 到测量值（不留余量）

## 允许修改
- `apps/api/app/core/middleware.py`（或新建 `app/core/audit.py`）
- `apps/api/app/api/deps.py` 里新增依赖函数（不得改既有函数的行为）
- `apps/api/app/main.py`（挂中间件）
- 三个路由组的 `APIRouter(... dependencies=[...])` 声明行（`bots.py`、`admin.py`、`subscriptions.py` 的 `sources_router`）
- `apps/api/tests/test_audit_log.py`（新）、`.github/workflows/ci-windows.yml`（仅阈值）
- `docs/06_validation/evidence/EVD-V17-31/**`

## 禁止修改
- `apps/api/alembic/**`（本卡零迁移）
- 各端点函数体；`app/services/roles.py`
- 冻结契约稿

## 阻塞条件
- 发现某写操作取不到操作者（例如服务间回调）⇒ 停下登记，交规划方裁决，不自行豁免

## 升级条件
需要改 `get_current_sub` / `require_roles` 本身 ⇒ 停，交规划方
