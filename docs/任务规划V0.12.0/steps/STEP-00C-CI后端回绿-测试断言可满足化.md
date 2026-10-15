# STEP-00C CI后端回绿-测试断言可满足化

> 基线 main@61358c3｜状态：🔴 门禁失败、待修

| 字段 | 内容 |
|---|---|
| 1 归属（执行者） | 执行Agent |
| 2 验收者（与执行者分离） | 规划方(Hark)，只输出 PASS/FAIL/UNKNOWN |
| 3 难度 / 里程碑 | 中低 / M0 |
| 4 来源 | F-02/F-03/F-04；V0.7.0 docs/任务规划V0.7.0/steps/STEP-00C-CI与Security回绿及门禁对齐.md |
| 5 目标 | CI backend job 回绿：唯一失败用例改为可满足且仍能抓住『删源过滤/改 LIMIT/丢通配』三类回归。 |
| 6 输入 | tests/test_asset_fragment_guard.py:27-40,:131-145；app/repositories/asset.py:50-68 |
| 7 输出路径 | apps/api/tests/test_asset_fragment_guard.py（仅此文件） |
| 8 三级任务 | 见下 |
| 9 验收 | CI run 的 backend job = success；本用例在三次变异下均红 |
| 10 命令 | `cd apps/api && uv run pytest tests/test_asset_fragment_guard.py -q && uv run pytest -q --cov=app --cov-fail-under=75` |
| 11 证据 | docs/任务规划V0.8.0/evidence/61358c3-00c/ |
| 12 允许修改 | apps/api/tests/test_asset_fragment_guard.py |
| 13 禁止修改 | apps/api/app/**（D-V4-01：不得改产品代码迎合测试）、ci.yml 阈值 |
| 14 依赖 / 阻塞 | 无 / 无 |
| 15 档位 | T1 |
| 16 升级条件 / 规模 | 若 literal_binds 在当前 SQLAlchemy 渲染 LIKE 参数失败 ⇒ 改为断言 `stmt.compile().params` 字典（仍断言值），并上报规划方 / ≈0.25 人日 |

## 三级任务

### S00C.1 记录器修正
- **S0C.1.1** 先复现：`pytest tests/test_asset_fragment_guard.py -q` 记录 1 failed（禁止照抄本版读数）
- **S0C.1.2** `:38` 改为 `str(stmt.compile(compile_kwargs={"literal_binds": True}))`
- **S0C.1.3** 确认其余用例只依赖条数，不受渲染方式影响（同文件全绿）

### S00C.2 判据射程反证
- **S0C.2.1** 临时删 `source_id ==` 谓词 ⇒ 该用例必须红（本地验证，不提交）
- **S0C.2.2** 临时改 `.limit(5)` ⇒ 红；临时去掉 `%` ⇒ 红
- **S0C.2.3** 三次反证输出存 evidence/61358c3-fix/s0c_mutation.txt

### S00C.3 全量回归
- **S0C.3.1** `ruff check . && ruff format --check .` rc=0
- **S0C.3.2** 全量 pytest（有 PG）`0 failed`、skip≤6、覆盖率≥75%
- **S0C.3.3** 提交信息 `test(step-00c): ...`，推送后 CI backend job 绿

## V0.9.0 → V0.10.0 本卡变更（基线 main@81cb997）

- **状态：✅ 已完成**。CI run `38570541936`（81cb997）success；53ebc4a、2315cda、f710ce9 连续 CI 绿（E-ci）。剩余 0 任务，不再下发。
- 验收者复核点：本卡 S0C.2 的变异反证已由 53ebc4a 的 `sql_render_defects` 静态判据机器化，按 PASS 记。
