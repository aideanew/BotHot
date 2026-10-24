# EVD-V21-46 引擎域响应形状契约链 —— 读数

> 平台 @linux（规划方沙箱，aarch64，Python 3.12，PG16@5547 自备，Redis@6380）｜基线 9028b89｜时间 2026-10-24 21:30～21:50 CST

## 1. 问题存在（先红）
- `grep -rn response_model apps/api/app/api` → 0 处；`app/core/response.py` 的 `Envelope.data: object | None` ⇒ OpenAPI 无响应形状。
- 旧 `scripts/gen_contracts.py`：TS 只来自 SQLAlchemy 列内省与请求模型；`packages/contracts/src/engine/` 只有 `.gitkeep`。
- tsc 探针（临时文件，不入库）：引擎 mock 样例原样（缺 `activeSource`、`decryptFailed`）`satisfies EngineCapability` ⇒
  `error TS1360 … Property 'decryptFailed' is missing … but required in type 'EngineCapability'.` ⇒ 登记 P-119。

## 2. 改动摘要
见 `docs/任务规划V0.21.0/steps/STEP-46-引擎域响应形状契约链.md` 第 6 格。`app/api/v1/engines.py` 零改动。

## 3. 改后读数
| 项 | 命令 | 结果 |
|---|---|---|
| 生成幂等 | `python scripts/gen_contracts.py --check` | rc=0，7 个 dto 域（新增 engine）+ 6 个 schema 域逐字节一致 |
| 契约包编译 | `tsc -p packages/contracts/tsconfig.json --noEmit` | 0 错 |
| 前端编译 | `apps/web: tsc --noEmit -p .` | 0 错（本卡未改前端） |
| 定向用例 | `pytest -q tests/test_engine_response_contract.py tests/test_p4_engines.py` | 18 passed |
| 契约比对 | `pytest -q tests/test_engines_capability.py tests/test_contract_jsonschema.py`（与新文件同批） | 93 用例中 91 passed + 2 连库在未迁移库上失败 → 迁移后全过（首跑库未 `alembic upgrade`，非代码问题） |
| 反证① 多键 | 临时让 PATCH 端点 data 多一个键 `legacy` | 连库用例红：`Additional properties are not allowed ('legacy' was unexpected)`；已还原（`git diff app/api/v1/engines.py` 为空） |
| 反证② TS | 缺 `decryptFailed` 的样例 `satisfies EngineCapability` | TS1360；补齐的样例通过 |
| 全量 | `pytest tests/ -q -rs --cov=app` | **2382 passed / 3 skipped / 4 deselected / 0 failed**，215.09s；skip 三条：LangBot 两条 + 代理变量对照一条（均非"PG 不可达"） |
| 模块门 | `check_module_coverage.py` | ✅ 全部模块与全局达标；TOTAL 88.91%，subscription 88.44%，manifest 94.78%，kb 88.76% |
| 其余门 | ruff check（改动文件）/ mypy `app/contracts/engine.py` / guard-structure / guard-ports / guard-versions / guard-ci-secret-mask / check_docs_consistency | 全部 rc=0 |

## 4. Windows skip 账
新增 2 条连库用例（`db_session` 夹具）⇒ @win 无 DSN 时 +2 skip ⇒ `ci-windows.yml` `SKIP_BASELINE_WIN` 683→685（锚注释已写）。

## 5. 越界申报
- 改了冻结稿 `docs/任务规划V0.12.0/contracts/engine.schema.json`：规划方权限（D-V21-01），只加两个 def，既有 def 未动；格式化后数组由单行变多行，语义比对用例通过。

## @ci（推送后回填）
- 待回填。
