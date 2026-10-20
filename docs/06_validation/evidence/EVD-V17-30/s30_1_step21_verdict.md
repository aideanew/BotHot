# STEP-30 S30.1 复查 STEP-21 — 判定：PASS

- 复查对象：`docs/任务规划V0.13.0/steps/STEP-21-IDOR连库矩阵与属主规则扩面-P11-P12.md`（交付 c93a6bc / 1834c4a / bec5225）
- 复查基线：main@482769a
- 环境：本机 PostgreSQL 16 @ `127.0.0.1:5547/bothot_test`（`AIDEANBOT_TEST_PG_DSN` 与 `DATABASE_URL` 同值）
- 判定人：执行助手（与规划方分离）；只判 PASS / FAIL / UNKNOWN，不改被复查卡的测试与实现

## 逐条验收

| # | 卡面验收标准 | 判定 | 证据 |
|---|---|---|---|
| 1 | 第 3/4 节用例数 = 枚举出的 A 类端点×方法数 + B 类端点×方法数（两数打印），全部通过 | PASS | `apps/api/tests/test_idor_matrix.py:735` 打印 `S21 A=22 B_ops=23 B_cases=62 C=2`；逐条参数化全部通过，原始输出见 `s30_idor_counts.txt` |
| 2 | 枚举守卫反证：新增临时 `GET /api/v1/_probe/{foo_id}` 路由 ⇒ 守卫红 | PASS | 失败输出见下；已还原（`apps/api/app/main.py` 工作树 blob = HEAD blob） |
| 3 | 动态反证输出入 EVD | PASS | 两处 A 类端点改坏输出见下；均已还原（blob MATCH） |
| 4 | `gen_contracts --check` 通过；真库全量 `failed = 0` | PASS | `python scripts/gen_contracts.py --check` RC=0（五份 schema 幂等一致）；全量读数见 `s30_full_readings.txt` |
| 5 | （STEP-30 S30.1 追加）B 类 minRole 与代码 `require_roles(...)` 逐条一致，不一致即 FAIL | PASS | 独立探针 23/23 OK：`VERDICT=PASS（23 条 B 类 minRole 与代码 require_roles 逐条一致）`；探针按路由表递归 `original_router`/`include_context`，对端点源码提取 `require_roles(...)` 并取最大秩（`require_roles` 语义 = max，D-V10-09），输出见下 |

## 枚举守卫反证

临时在 `apps/api/app/main.py` 增加：

```python
_probe = APIRouter(prefix="/api/v1")

@_probe.get("/_probe/{foo_id}")
async def _probe_route(foo_id: str) -> dict:
    return {"ok": foo_id}

app.include_router(_probe)
```

失败输出：

```text
E   AssertionError: 这些带路径参数的端点没有归入 x-idor-classes：GET /api/v1/_probe/{foo_id}
E   assert not ['GET /api/v1/_probe/{foo_id}']
FAILED tests/test_idor_matrix.py::test_every_operation_with_a_path_param_is_classified
1 failed in 1.82s
```

## 动态反证（两处 A 类端点）

### 1) `GET /api/v1/spaces/{space_id}`

改坏：`apps/api/app/services/spaces.py` 的 `get_space_view` 把
`if space is None or space.user_id != user_id:` 改成 `if space is None:`。

```text
FAILED tests/test_idor_matrix.py::test_a_user_cannot_reach_b_users_resource[GET-api_v1_spaces_space_id]
E   AssertionError: GET /api/v1/spaces/{space_id}：A 越权实得 200/0
E   assert (200, 0) == (404, 30004)
1 failed, 1 warning in 5.52s
```

### 2) `GET /api/v1/jobs/{job_id}`

改坏：`apps/api/app/services/subscription.py` 的 `_job_view` 把
`if job is None or (owner is not None and job.user_id != owner):` 改成 `if job is None:`。

```text
FAILED tests/test_idor_matrix.py::test_a_user_cannot_reach_b_users_resource[GET-api_v1_jobs_job_id]
E   AssertionError: GET /api/v1/jobs/{job_id}：A 越权实得 200/0
E   assert (200, 0) == (404, 30004)
1 failed, 1 warning in 5.00s
```

> 说明（不是 FAIL）：第一次把判据删在 `apps/api/app/services/jobs.py::JobService.get_job` 上，
> 读数是 `21 passed`——该函数不在 `GET /jobs/{job_id}` 的路由调用链上，真实判据在
> `SourceSubscriptionService._job_view`。复查必须按实得状态定位，不能按文件名猜。

## B 类 minRole 逐条核对

独立探针输出（节选）：

```text
OK  PUT /api/v1/bots/tasks/{task_id} -> operator
OK  PUT /api/v1/bots/{channel_id} -> operator
B 条目 23；代码带角色门但不在 B 表的操作 15（供参考，不判）
...
VERDICT=PASS（23 条 B 类 minRole 与代码 require_roles 逐条一致）
```

## 还原读数

```text
$ for f in spaces.py subscription.py jobs.py main.py api.envelope.schema.json collection.schema.json engines.py; do
    [ "$(git hash-object "$f")" = "$(git rev-parse "HEAD:$f")" ] && echo "MATCH $f" || echo "DIFF $f"; done
MATCH apps/api/app/services/spaces.py
MATCH apps/api/app/services/subscription.py
MATCH apps/api/app/services/jobs.py
MATCH apps/api/app/main.py
MATCH packages/contracts/schemas/api.envelope.schema.json
MATCH packages/contracts/schemas/collection.schema.json
MATCH apps/api/app/api/v1/engines.py

$ git status --porcelain | grep -v '^??'
 M apps/api/app/contracts/identity.py
```

（唯一未还原项是 S30.4 允许修改的 `identity.py` `kind` 一行。）

## 全量真库

`python -m pytest tests/ -q -rs`（PG16@5547）的原始末行与 skip 清单见 `s30_full_readings.txt`：`failed = 0`。
