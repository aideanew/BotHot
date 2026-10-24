# STEP-46 引擎域响应形状契约链（P-82 第一刀）

> 基线 main@9028b89｜状态：✅ 已收口（@ci 三绿：CI 40099919134 / CI-Windows 40099919204 / Security 40099919142）｜版本 V0.21.0

| 字段 | 内容 |
|---|---|
| 1 归属 | **规划方**（D-V21-01：契约语义与生成器属 Contract 列，opus） |
| 2 切片 | SL-SHAPE（前端演示数据与后端线上形状同源） |
| 3 来源 | P-82；S37.4 交回（`EVD-V18-37/s37_readings.md:43-53`）；D-V3-07 |
| 4 目标 | 引擎域两个端点的线上 `data` 形状有唯一源，schema 与 TS 由它派生，真端点被反向核 |
| 5 输入 | `app/contracts/engine.py`、`scripts/gen_contracts.py`、`app/api/v1/engines.py:159-216`、稿 `docs/任务规划V0.12.0/contracts/engine.schema.json` |
| 6 输出 | 改 `app/contracts/engine.py`（+EngineList、SpaceEngineBinding）；改稿 engine.schema.json（加两 def）；改 `scripts/gen_contracts.py`（+契约派生 TS：`CONTRACT_TS_DOMAINS`、`_json_schema_to_ts`、`generate_contract_ts`，不认识的形状立即报错）；新 `packages/contracts/src/engine/dto.ts`（删 `.gitkeep`）；改 `packages/contracts/src/index.ts`；新 `apps/api/tests/test_engine_response_contract.py`；`ci-windows.yml` `SKIP_BASELINE_WIN` 683→685 |
| 7 验收 | ① `gen_contracts.py --check` rc=0 且含 `src/engine/dto.ts` ② 新用例 5 passed（连库）③ 反证：端点 data 多塞一键 ⇒ 连库用例红（"Additional properties are not allowed"）④ 反证：样例缺 `decryptFailed` `satisfies EngineCapability` ⇒ tsc TS1360 ⑤ `test_contract_jsonschema.py` 原样通过 ⑥ 三绿 |
| 8 命令 | `cd apps/api && pytest -q tests/test_engine_response_contract.py tests/test_engines_capability.py tests/test_contract_jsonschema.py tests/test_p4_engines.py`；`python ../../scripts/gen_contracts.py --check`；`apps/web/node_modules/.bin/tsc -p packages/contracts/tsconfig.json --noEmit` |
| 9 证据 | `docs/06_validation/evidence/EVD-V21-46/s46_readings.md` |
| 10 允许修改 | 第 6 格所列 |
| 11 禁止修改 | `app/api/v1/engines.py`（只核不改）；`EngineReason`/`EngineCapability` 既有字段；任何覆盖率阈值 |
| 12 依赖 | 无 ｜ Blocks：STEP-48、STEP-47 复用其生成器 |
| 13 档位 | opus（契约语义 + 生成器，不可逆面） |
| 14 升级条件 | 契约比对测试判出语义差 ⇒ 停，走 fable 级复核 |
| 15 规模 | 中，≈0.5 人日（已完成） |
| 16 熔断 | 同判据 2 次 FAIL ⇒ 停 |

## 三级任务
1. [x] **S46.1 契约模型**
   1. [x] S46.1.1 `EngineList{items: EngineCapability[], defaultEngine}`、`SpaceEngineBinding{engine, engineKbId(str, NOT NULL 语义), spaceId}`，均 `extra="forbid"`
   2. [x] S46.1.2 稿加同名两 def（加法），`test_contract_jsonschema.py` 通过
2. [x] **S46.2 生成器派生 TS**
   1. [x] S46.2.1 `$ref`/`anyOf`/`enum`/`const`/`array`/`object`/标量 → TS；不认识 ⇒ SystemExit
   2. [x] S46.2.2 目录占用冲突检查（实体内省与契约派生不得同目录）
   3. [x] S46.2.3 `--check` 字节幂等覆盖新 TS
3. [x] **S46.3 反向核**
   1. [x] S46.3.1 不连库牙齿 3 条（多键红、缺键红、engineKbId=null 红；TS 产物无 `unknown`）
   2. [x] S46.3.2 连库 2 条（GET /engines、PATCH /spaces/{id}/engine 真端点 data 过 schema）
   3. [x] S46.3.3 Windows skip 基线 +2
4. [x] **S46.4** @ci 三绿（规划方回填 `s46_readings.md` §@ci）
