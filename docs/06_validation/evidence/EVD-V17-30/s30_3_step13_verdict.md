# STEP-30 S30.3 复查 STEP-13 — 判定：PASS

- 复查对象：`docs/任务规划V0.13.0/steps/STEP-13-可插拔引擎能力面收敛.md`（交付 81205f1；证据 `EVD-V3-13/`）
- 复查基线：main@482769a
- 环境：本机 PG16 @ `127.0.0.1:5547/bothot_test`

## 逐条验收

| # | 卡面验收标准 | 判定 | 证据 |
|---|---|---|---|
| 1 | `test_engines_capability.py` 两种失败态的 `reason` 断言绿，且改错任一处能红（变异反证） | PASS | 还原后 `43 passed in 1.49s`；对调 `_engine_reason` 的"未开放/未配置"两条判断 ⇒ `4 failed, 39 passed`，失败输出见下；已还原（blob MATCH） |
| 2 | `grep -c NotImplementedError app/providers/engine_port.py` = 16 | PASS | 现读 `16`；`test_skeleton_surface_only_shrinks` 钉 `<= 16`（tests:128-131） |
| 3 | REQ-F-003 文本与代码实况逐句一致 | PASS | `ENGINE_ORDER = ["builtin","main","coze","dify","fastgpt"]`（engine_port.py:197）；`ENGINE_IMPLEMENTED` 仅 `builtin=True`（:222-228）；真请求 5 items 全带 `reason`；`test_switch_refusal_says_the_same_reason_as_the_listing` 钉 403/10004 与文案一一对应（tests:92-104） |
| 4 | `gen_contracts --check` rc=0；`ruff`/`mypy` 无新增错 | PASS | RC=0（五份 schema 幂等一致）；`ruff check app tests` → `All checks passed!` RC=0；`mypy app` → `Success: no issues found in 114 source files` RC=0 |
| 5 | 全量连库 0 failed（依赖机） | PASS | `s30_full_readings.txt` |
| 6 | 无任何新迁移号被占用 | PASS | `git status --porcelain apps/api/alembic/versions` 输出 0 行；head 仍为 `ab1006c1a` |

## 变异反证（S30.3）

改坏：在 `apps/api/app/api/v1/engines.py::_engine_reason` 里对调"未开放名单"与"Key 未配置"两条判断的顺序。

```text
E   assert 'key_missing' == 'not_allowlisted'
E   assert 'key_missing' == 'not_allowlisted'
E   assert 'key_missing' == 'not_allowlisted'
E   assert 'key_missing' == 'not_allowlisted'
FAILED tests/test_engines_capability.py::test_reason_follows_the_fixed_precedence[main-False-False]
FAILED tests/test_engines_capability.py::test_reason_follows_the_fixed_precedence[coze-False-False]
FAILED tests/test_engines_capability.py::test_reason_follows_the_fixed_precedence[dify-False-False]
FAILED tests/test_engines_capability.py::test_reason_follows_the_fixed_precedence[fastgpt-False-False]
4 failed, 39 passed in 1.47s
```

还原后 `43 passed in 1.49s`；`git hash-object` = `git rev-parse HEAD:...` ⇒ MATCH。

## 真请求读数

`GET /api/v1/engines`（TestClient + 覆盖 `get_current_user_id`；Windows 下用 `WindowsSelectorEventLoopPolicy` 避开 psycopg 的 Proactor 限制）：

```text
HTTP 200
items 5
  builtin: reason=ok available=True implemented=True
  main: reason=not_allowlisted available=False implemented=False
  coze: reason=not_allowlisted available=False implemented=False
  dify: reason=not_allowlisted available=False implemented=False
  fastgpt: reason=not_allowlisted available=False implemented=False
VERDICT=PASS
```

## 计数口径

文件级判据 `apps/api/app/providers/engine_port.py` = 16（PASS）。全 `apps/api/app` 目录 grep 为 17，
多出的一条是 `apps/api/app/api/v1/engines.py:186` 注释里的 `NotImplementedError` 字样，不是骨架位实现；
不在本卡"骨架位只降不升"的判据面内。
