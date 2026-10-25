# EVD-V21-47 其余 mock 域响应形状契约 —— 读数

> 平台 @linux（规划方沙箱，aarch64，Python 3.12，自备 PG16@5547 新建库 + Redis）｜基线 bfd6d82｜时间 2026-10-25 22:20～23:30 CST

## 1. 问题存在（先红）
- 改前：`packages/contracts/schemas/` 只有 engine 一个响应形状域；mock 表 22 条路由里 20 条没有任何契约（`grep -c "pattern: /" apps/web/lib/api/mock-routes.ts` → 22）。
- 前端手写类型对契约的 tsc 探针（临时文件，不入库）：`s47_frontend_probe.txt`——`MeData`→`MeView` TS2741；`Space`/`SpaceDetail`/`SpaceDoc`/`SpaceDocsPage` → 契约类型 TS2322。登记 P-122 交 STEP-52。

## 2. 改动摘要
见卡面"交付摘要"。后端路由与 service **零改动**（`git diff --stat apps/api/app/api apps/api/app/services` 为空）。

## 3. 改后读数
| 项 | 命令 | 结果 |
|---|---|---|
| 生成幂等 | `python scripts/gen_contracts.py --check` | rc=0，8 个 dto 域（新增 shapes）+ 7 个 schema 域逐字节一致 |
| 契约包编译 | `tsc -p packages/contracts/tsconfig.json --noEmit` | 0 错 |
| 前端编译 | `apps/web: tsc --noEmit -p .` | 0 错（本卡未改前端） |
| 定向用例 | `pytest -q tests/test_shapes_response_contract.py` | 17 passed（连库）；无库时 10 passed / 7 skipped |
| 稿↔产物 | `pytest -q tests/test_contract_jsonschema.py tests/test_collection_contract.py` | 295 passed |
| 反证 多键 | 临时让空间视图多一个键 | 连库用例红：`Additional properties are not allowed ('probeExtra' was unexpected)`（`s47_red_extra_key.txt`）；已还原，service diff 为空 |
| lint/类型 | `ruff check app tests ../../scripts`；`mypy app ../../scripts` | 全过；mypy 134 文件 0 错 |
| 文档门 | `python scripts/check_docs_consistency.py` | ok |
| 全量 | `pytest tests/ -q -rs --cov=app`（新建库，首跑） | **2470 passed / 2 skipped / 4 deselected / 0 failed**，210.95s；skip 两条均为 LangBot :5300 冒烟 |
| 模块门 | `check_module_coverage.py` | ✅ 全部达标；TOTAL 89.13%，kb 88.76%，manifest 94.78%，subscription 88.44% |

## 4. Windows skip 账
新增 7 条连库用例 ⇒ @win 无 DSN 时 +7 skip ⇒ `SKIP_BASELINE_WIN` 685→692（锚注释已写）。

## 5. 越界申报
- `apps/api/tests/test_collection_contract.py` 的域表加 `shapes`：卡面第 10 格只列了 `test_contract_jsonschema.py`，但该文件有同构的域登记且断言"产物目录 == 登记域"，不加必红。只加 6 行登记，未改判据。
- `packages/contracts/src/index.ts` 导出 shapes 30 个类型（第 10 格 `packages/contracts/**` 内）。

## @ci（推送后回填）
