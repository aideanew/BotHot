# EVD-V17-10 · S10.V15.2 付费详情兜底的触发条件/供应商/预算运营可配

> 卡面：`docs/任务规划V0.15.0/steps/STEP-继承卡增量-V15.md` 的 STEP-10 增量表第 2 行；
> 裁决：**D-V12-20**（运营可读、管理员可写；无库值 = 关闭；只配触发条件/供应商/预算，不配 key）。
> 上一轮（S10.V15.1，详情兜底接进入库链路）的读数在同目录 `s10_v15_1_readings.md`。

## 1. 先红原文（改前，main@626e4ad）

scratch 探针（不入库，跑完清场）：

```
[probe] 路由表里 /admin/article-fallback 的条数 = 0 → []
[probe] kb.py 里 fetch_detail 调用点 = 1 处；reason= 出现 = 0 次
[probe] app/** 里 captcha/验证码 的命中数 = 0（0 ⇒ 没有可接的检测面）
[probe] 库里的键 = ['article_fallback']
[probe] ARTICLE_FALLBACK_KEY 属性存在吗 = False
[probe] 协调器有预算/触发面吗 = budget_remaining=False fallback_article_for=False
[probe] 已清场
```

四件事都被这四行钉住：**没有接口**（0 条路由）、**只有一个触发点**（`reason=` 0 次）、
**没有检测面**（`captcha` 全仓 0 命中）、**配置写进去也没人读**（键未登记 ⇒ `refresh()` 会跳过它）。

装载红（本卡 18 条用例在改前）：

```
ERROR tests/test_article_fallback_config.py
E   AttributeError: type object 'ArticleDetailFallbackCoordinator' has no attribute 'reset_budget_for_tests'
1 warning, 16 errors in 1.66s
```

## 2. 改后绿

| 面 | 命令 | 读数 |
|---|---|---|
| 本卡 | `pytest tests/test_article_fallback_config.py -q` | **18 passed** |
| **上一轮交付面 0 修改** | `tests/test_detail_fallback_wiring.py` 同批跑 | 27 passed（含那 10 条），一行未改 |
| 守卫面 | `tests/test_audit_log.py tests/test_idor_matrix.py tests/test_require_roles_single_arg.py` | **138 passed** |
| 静态 | `ruff check app tests` / `mypy app` | rc=0 / `Success: no issues found in 116 source files` |
| 全量两形状 + `SKIP_BASELINE_WIN` | 见 §6 | 待填 |

`fetch_detail(url, reason=...)` 的 `reason` 带默认值，就是为了那 10 条不改还能绿：
默认值只承担**调用形状**，两个调用点都显式传值，语义不靠默认。

## 3. 三条口径与它们各自的代价

1. **「无库值 = 关闭」怎么读**。库里没那一行时，本卡按 env 旗标 `article_detail_fallback_enabled`
   决定（默认 False ⇒ 生产上"无库值 = 关"成立），而不是把 env 旗标判死。
   另一种读法（无库值一律关、env 说了也算）会直接推翻 S10.V15.1 已经三绿的判据
   （`test_flag_on_free_failure_spends_exactly_one_paid_call` 就是靠 env 打开的），
   那属于"新卡推翻旧卡交付面"，该由规划方改卡而不是由执行方选边。取舍留痕于此。
2. **`captcha` 被拒收，不是被忽略**。§1 第 3 行是本条的全部依据：全仓没有验证码形态的判定，
   收下这个值等于做一个人能配、机器不执行的旋钮（本仓的既有病：`BotBinding` 死表、T5.6 计费预留）。
   服务层 `validate()` 直接 10005 并把可用值列在报错里；读接口另有 `wiredTriggers` 字段把
   "现在能配哪些"说清楚。放开的前提登记为 **P-64**。
3. **预算扣在哪一步**。第一版把 `_spend()` 放在 `fetch_detail` 入口（一次调用扣 1），
   而一次调用最多会打三家 ⇒ 预算被放大 3 倍。自己的用例
   `test_budget_is_counted_per_attempt_not_per_success` 抓到：

   ```
   assert coordinator.budget_remaining() == 0, "两家各一次 = 扣两次，预算按尝试计数"
   E   AssertionError: 1 == 0
   ```

   改成扣在**每一次 provider 尝试**上、用尽即 `break`（剩余家不再试）。
   计"尝试"而不是计"成功"：付费接口"扣费但 data=null"是实测在案的形状
   （`registry.py` 里 dajiala 的失败计费口径，¥0.045/次），只扣成功等于预算永远扣不完。

## 4. 读侧为什么必须与协调器同源

`effective_config(settings, stored)` 与 `ready_detail_platforms(settings)` / `allowed_platforms(...)`
是**模块级函数**，协调器和 `GET /admin/article-fallback` 都调它们。
理由与 STEP-28 的 `default_categories()` 同一条：接口自己拼一份"当前生效形状"，
就和入库用的那份成了两个真源，漂移的形状是"配置页显示已开、实际按关跑"（或反过来），
那种问题只能靠人对着两个文件读，读出来也已经晚了。

`platforms[].ready` 只回答"这家配没配凭据"（布尔），**永不回显值**——ADR-0013 不变量 2。

## 5. 越界与追认（逐条）

| 项 | 说明 | 判据 |
|---|---|---|
| 计数锚追认 | `tests/test_audit_log.py`（写操作 25→26、admin 14→15）、`tests/test_idor_matrix.py`（操作 96→98、注册面 92→94） | 两条锚的 docstring 自己写着"真加/删端点时来改这条，不要放宽成 `>= 0`"；先让参数化用例真的长出 `PUT /admin/article-fallback` 并绿，再追认数 |
| 角色矩阵 | `OPERATOR_OK` +1（`GET /article-fallback`）、`ADMIN_ONLY` +1（`PUT /article-fallback`） | `test_operator_write_surface_matches_d_v12_12` / `test_admin_only_surface_matches_d_v12_12` 全绿 ⇒ operator 写这条确实 10004（D-V12-20 的落点） |
| 触发点接进 `kb.py` | 卡面允许面（STEP-10 的写面本就含入库链） | `test_both_trigger_points_are_wired_in_the_ingest_chain`：AST 断言 `_ingest_url_inner` 里有 `reason="empty_body"`、`_resolve_with_retry` 里有 `reason="http_error"`，且 `paid_detail_to_article` 只出现 1 份 |
| 无新增迁移 | 本卡不需要 DDL（预算是进程内计数） | `alembic heads` 仍 `ab1006c4a` 单头 |

## 6. 门禁与基线

| 项 | 读数 |
|---|---|
| 全量连库（`bothot_test`@5547） | **2139 tests / 0 failed / 0 errors / 6 skipped**（终端行 `2133 passed, 6 skipped`） |
| 无 DSN 同形状（`env -u AIDEANBOT_TEST_PG_DSN -u DATABASE_URL`） | **2139 tests / 0 failed / 0 errors / 621 skipped**（终端行 `1518 passed, 621 skipped`） |
| `SKIP_BASELINE_WIN` | **612 → 621**。算式（按模块实测，不是猜）：`test_article_fallback_config` 8（该文件 18 条里另 10 条不连库）+ `test_audit_log` 1（按写操作参数化的那条又随新 admin 写端点变长，25→26）⇒ 612 + 9 = 621，与全量 `total_skipped=621` 一致 |
| `ruff check app tests` / `mypy app` | rc=0 / `Success: no issues found in 116 source files` |
| `alembic heads` | `ab1006c4a (head)` 单头（本卡无迁移） |
| `gen_contracts --check` / `check_docs_consistency` / `evidence-check` / `rounds-check` | 待填（提交前后各跑一次，读数不预判） |
| `@ci` 三条 run id | 待填 |

## 7. 局限（先说，不等被问）

- **预算是进程内、按业务日的**。跨进程不共享、重启即归零。真正"按渠道日计数、跨进程持久"的那张表
  是 S10.2.1/S10.2.2，仍被两件事卡着：需要迁移号（STEP-10 卡面字段 13 禁止动 `alembic/**`）
  且 S10.2.2 依赖 STEP-08（队列⑫）。本卡**没有**把它做成"看起来有预算"的样子，
  读接口的 `dailyBudget` 与告警文案都写的是"当日/本进程"。
- **只有 worker 链路会付费**（承 S10.V15.1 的接线：`make_default_ingest`）。
  HTTP 贴链接路径与 scheduler 的构造点仍传 `detail_fallback=None` ⇒ 运营在页面上打开开关后，
  "用户贴一条链接"不会触发付费。这是上一轮登记过的裁决点（要不要把付费放进用户同步请求路径），
  本卡不替规划方决定。
- 快照不是广播：改完最多 60 秒内其他进程还按旧值跑（ADR-0013 §5 同一条代价）。
- `providers` 名单里写了没配凭据的家 ⇒ 静默不试（`available_platforms` 读得出来），
  不报错也不换别家：付费面宁可少花，不要"配了 A 结果打了 B"。
- 契约 DTO 面与 STEP-28 同一处缺口（P-61）：本卡新增的两个请求模型只在 OpenAPI 可见，
  `packages/contracts` 里没有生成物。
