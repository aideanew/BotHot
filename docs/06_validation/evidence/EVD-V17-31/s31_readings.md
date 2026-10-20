# EVD-V17-31：运营与管理写操作的结构化审计日志

- 日期：2026-10-20
- 改卡依据：**D-V17-02**（STEP-31 卡内冻结设计，照做不改口径）
- 基线：`main@8d1c410`（STEP-26 交付与记录提交，三 CI 绿）
- 环境：Win10 + Git Bash；`apps/api/.venv` Python 3.12.10；`PYTHONUTF8=1`；
  本机隔离 PostgreSQL 16.4（`127.0.0.1:5547/bothot_test`，trust）；Redis/LangBot 未起。
- 本卡零迁移。

## 1. 审计面枚举（由路由表生成，不手写清单）

复用 `tests/test_idor_matrix.py::_enumerate_operations`，取三个前缀下
`POST/PUT/PATCH/DELETE`：

| 前缀 | 数量 | 操作 |
|---|---:|---|
| `/api/v1/admin` | 12 | PATCH `/spaces/{space_id}`；DELETE `/spaces/{space_id}`；DELETE `/spaces/{space_id}/docs/{doc_id}`；POST `/spaces/{space_id}/docs:delete`；POST `/spaces/{space_id}/docs:recategorize`；POST `/engines/keys/{engine}`；DELETE `/engines/keys/{engine}`；POST `/push`；POST `/jobs/{job_id}:cancel`；POST `/jobs/{job_id}:retry`；DELETE `/subscriptions/{subscription_id}`；DELETE `/sources/{source_id}` |
| `/api/v1/bots` | 8 | POST 空路径；POST `/tasks`；PUT `/tasks/{task_id}`；DELETE `/tasks/{task_id}`；POST `/tasks/{task_id}/run`；PUT `/{channel_id}`；DELETE `/{channel_id}`；POST `/{channel_id}/test` |
| `/api/v1/sources` | 3 | POST 空路径；PATCH `/{source_id}`；DELETE `/{source_id}` |
| **合计** | **23** | 计数锚写在 `test_write_operation_enumeration_has_a_measured_anchor` |

## 2. S31.1 改前先红

命令：

```bash
cd apps/api && python -m pytest tests/test_audit_log.py -q
```

读数：`25 failed, 2 passed, 1 warning in 33.38s`。

- 25 红 = 23 个写操作（审计条数为 0）+ 请求体标记负面断言 + 403 负面断言；
- 2 绿 = 枚举计数锚 + 匿名 401 不写（改前本来就没有任何审计记录，负向断言必然成立）。
- 另：实现落地后、摘除中间件做 S31.4 反证时复现同一读数 `25 failed, 2 passed`。

代表红原文（S31.4 摘除中间件后单跑 `[POST /api/v1/bots]`）：

```text
F                                                                        [100%]
================================== FAILURES ===================================
_ test_each_write_operation_emits_exactly_one_audit_record[POST /api/v1/bots] _

        with capture_logs() as logs:
            response = client.request(method, _fill(path))

        entries = _audit_entries(logs)
>       assert len(entries) == 1, (
            f"{method} {path}：审计条数 {len(entries)}（status={response.status_code}，"
            f"body={response.text[:120]!r}）"
        )
E       AssertionError: POST /api/v1/bots：审计条数 0（status=422，body='{"code":10005,"message":"请求参数校验失败: [{\'type\': \'missing\', \'loc\': (\'body\',), \'msg\': \'Field required\', \'input\': None}]","dat'）
E       assert 0 == 1
E        +  where 0 = len([])

tests\test_audit_log.py:146: AssertionError
```

（`body` 原文被用例的 120 字符截断；红的原因是中间件不在 ⇒ 没有任何 `audit` 记录。）

## 3. S31.2 实现

- 新增 `apps/api/app/core/audit.py`：纯 ASGI `AuditMiddleware`，装在
  `RequestIdMiddleware` 内、`ErrorEnvelopeMiddleware` 外；发送包装器只捕获
  响应状态与信封 `code`，请求结束后写一条 `event="audit"`。
- `app/api/deps.py` 新增 `record_audit_actor`：依赖 `get_current_user_id` 取
  `users` 行，把 `sub` 与 `role` 写进 `request.state.audit_actor`。
  选 `get_current_user_id` 而不是直接 `get_current_sub`：既有测试用覆写
  `get_current_user_id` 注入身份（`test_discovery.py`、`test_process_heartbeat.py`），
  挂前者不改变这些用例的语义。
- 三个路由组声明行挂依赖：`bots.py`（与既有 `get_current_sub` 并列）、
  `admin.py`、`subscriptions.py::sources_router`。
- 固定 9 字段：`actor_sub`、`actor_role`、`method`、`route`（路由模板）、
  `path_params`、`status`、`code`、`request_id`、`ts`（UTC ISO 8601 带时区）。
- 禁止项：不读请求体/响应体/查询串/请求头；`path_params` 只取路由声明参数；
  401 不写。

## 4. S31.3 负面断言

改后读数：

```text
27 passed, 1 warning in 34.56s
```

覆盖：

1. `test_request_body_marker_never_reaches_the_audit_log`：标记串
   `s31-body-marker` 放进请求体，拒绝路径（403）与执行路径（404）各一条，
   审计记录 JSON 里均无该串；
2. `test_plain_user_forbidden_is_audited_as_403_10004`：普通用户被拒写一条，
   `status=403`、`code=10004`、`actor_role=user`；
3. `test_anonymous_401_is_not_audited`：匿名请求 `status=401`，审计条数为 0。

## 5. S31.4 摘除反证

临时把 `app.add_middleware(AuditMiddleware)` 注释掉：

```text
25 failed, 2 passed, 1 warning in 33.90s
```

还原后：

```text
27 passed, 1 warning in 34.28s
```

补录 §2 代表红原文时再次摘除中间件单跑一条（命中同一断言 `len(entries) == 1`），
还原后全文件：`27 passed, 1 warning in 37.65s`。

## 6. 回归面与静态门

- 受影响路由组既有用例第一批：`122 passed in 100.13s`
  （bots 读授权 / discovery / heartbeat / push+hot 矩阵 / task owner /
  渠道 extra_config 加密 / W7 安全中间件）。
- 第二批：`231 passed in 343.30s`
  （r11 admin/batch/engine keys/push、r48 admin jobs、r02 订阅生命周期、IDOR 矩阵）。
- `ruff check app tests`：All checks passed。
- `mypy app`：Success: no issues found in 115 source files。
- 无 DSN 下 `test_audit_log.py`：`1 passed, 26 skipped in 6.33s`
  ⇒ `.github/workflows/ci-windows.yml` 的 `SKIP_BASELINE_WIN` 由 545 抬到 **571**
  （545 + 26，无余量）。
- 无 DSN 全量（CI-Windows 形态）：`1453 passed, 571 skipped, 1 warning in 1045.98s`，
  failed = 0。1453 = 既有 1452 + 本卡不连库的计数锚 1；571 = 545 + 本卡 26。

## 7. 本机真库全量门

命令：`AIDEANBOT_TEST_PG_DSN=… DATABASE_URL=… PYTHONUTF8=1 python -m pytest -q`

- 首跑：`1 failed, 2017 passed, 6 skipped, 1 warning in 939.99s`。唯一红为
  `tests/test_scheduler.py::test_run_once_runs_due_subscriptions_in_parallel`
  （并发重叠时序断言，不经 HTTP/审计链路）：单跑 `1 passed in 1.69s`，
  连跑 20 次 20/20 绿 ⇒ 全量负载下的既有用例抖动，登记 **P-52**，本卡未修。
- 复跑：`2018 passed, 6 skipped, 1 warning in 976.30s`（failed = 0）。
  对照基线 1991 passed / 6 skipped，+27 条即本卡新增用例。

## 8. 三 CI

交付提交 `5a2e4711f5e745cd33a9f504e9c1af86d1c17f98` 的 `push` 三工作流：

| 工作流 | 结论 | 关键读数 |
|---|---|---|
| CI（ubuntu-latest） | success（run 39394482245） | backend `2018 passed, 6 skipped, 1 warning in 179.56s`；覆盖率 86.71%（门 75%）；frontend 385 passed、e2e 27 passed |
| CI-Windows | success（run 39394482305） | backend `1453 passed, 571 skipped, 1 warning in 1011.50s`；门禁 `failed=0 total_skipped=571 baseline=571`；frontend 385 passed |
| Security | success（run 39394482293） | — |

CI-Windows 的 571 与无 DSN 本机全量读数一致；545 + 26，无余量。

## 9. 边界与已知影响

- 审计中间件位于 W7 入站防护（体限/限流）之内：被 413/429 短路的请求走不到
  操作者依赖，没有操作者，按 D-V17-02 不写（与 401 同族）。已在 `audit.py`
  模块头登记。
- 三个路由组的**读**接口也挂 `record_audit_actor`（设计口径为「三个路由组上
  挂一个依赖」）：`/api/v1/bots/channels` 等原本只验 cookie 的读接口，现在
  还要求本地 `users` 行存在；缺行属既有代码定义的异常态（会引导重新登录）。
- 全量首跑暴露既有用例 **P-52**：`test_scheduler.py::test_run_once_runs_due_subscriptions_in_parallel`
  自称「不受测试机负载影响」的重叠断言，在满负载下可能误红（实测两段 sync 不重叠：
  第二段起始比第一段结束晚 12ms）。本卡未触碰 scheduler 与中间件链路，按规定登记不修。
- P-50 / P-51 仍为 STEP-26 的待授权残留，本卡未动。
