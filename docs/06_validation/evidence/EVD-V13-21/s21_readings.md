# STEP-21 IDOR 连库矩阵——读数与结论（规划方自做，第 1 轮）

- 基线：main@fb31ea8；环境 `@linux` PG16@5547 `bothot_test`（`DATABASE_URL` 与 `AIDEANBOT_TEST_PG_DSN` 同设），`alembic upgrade head` rc=0
- 契约：冻结稿 `docs/任务规划V0.12.0/contracts/identity.schema.json` 追加 `x-idor-checklist` 第 3 条、新增 `x-idor-classes`（A/B/C 机读三类，B 逐操作写死 minRole），并校正 `x-permission-matrix` 管理端一档的 operator 可读项；`gen_contracts --check` rc=0，`test_collection_contract.py` 全绿

## 用例数（验收第 1 条）
| 项 | 数 |
|---|---|
| 带路径参数的操作 | 47 = A 21 + A 例外 1 + B 23 + C 2 |
| A 类连库用例（A 用户 × B 的 id） | 22 |
| B 类用例（低于 minRole 每级判拒 + 恰在门槛判放行） | 59 |
| C 类用例 | 2 |
| 归类/反证/读数等无库用例 | 新增 6 |

## 先红 → 修 → 绿
1. `01_red_before_fix.txt`：只加测试、代码不动 ⇒ **2 failed / 104 passed**。operator 能登记、撤销引擎 Key（`POST/DELETE /admin/engines/keys/{engine}` 得 422/404，不是 403）。冻结稿管理端一档本来写 admin，代码自 T5.4 起是 operator；登记 Key = 写第三方凭据且会花钱，与 D-V12-12「改凭据只给管理员」同族 ⇒ **D-V16-06 改为 admin**，GET 登记状态仍 operator。
2. 修：`apps/api/app/api/v1/admin.py` 两处 `require_roles("operator")` → `("admin")`；`tests/test_r11_engine_keys.py` 写操作改用 admin 账号，并新增 `test_engine_key_writes_are_admin_only`（operator 不带请求体也先撞 403/10004）。
3. `02_green_after_fix.txt`：矩阵 + r11 共 136 passed；本机真库全量 **1859 passed / 5 skipped / 0 failed**，ruff、mypy 全绿。

## 反证
- 归类守卫：`test_classification_guard_rejects_a_synthetic_probe_route` 把临时 `GET /api/v1/_probe/{foo_id}` 塞进清单 ⇒ 被认出未归类。
- 动态反证 `03_dynamic_counterproof.txt`：临时删掉 `services/spaces.py:440` 的属主判据 ⇒ `PATCH /spaces/{space_id}/docs/{doc_id}` 的用例红（A 越权实得 200/0），还原后 diff 0 行。
- 正控：B 用户读自己的空间、作业、订阅均 200/0（排除"整片 404 只是播种坏了"）。

## 观察（不在本卡修）
- 三个写接口（改文档分类、批量改分类、改订阅策略）在属主判据之前先校验取值，非法值对任何 id 都回 422/10005——对存在与否同码，不构成存在性探测。
- `/admin/ops` 页对 operator 仍显示登记/撤销按钮，点了会得"登记失败：权限不足"。按秩隐藏归 STEP-15b S15b.V15.2。
- R-V14-03（推送域写操作是否进审计日志）本卡未判，仍在风险表。
