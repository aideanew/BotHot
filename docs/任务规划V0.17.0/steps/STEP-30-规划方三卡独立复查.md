# STEP-30 规划方三卡独立复查（V0.17.0 新增）

| 字段 | 值 |
|---|---|
| 归属-切片 | SL-GATE（证据与验收分离） |
| 归属-需求 | D-V17-01：规划方自做的卡必须由执行助手独立判 PASS/FAIL；P-48 |
| 里程碑 | M0 |
| 执行者 | 执行 Agent-Guard |
| 档位 | sonnet　理由：按现成判据复跑与比对，不做设计 |
| 规模 | 小（4 项，≈0.6 人日） |
| 依赖 | Depends on：29（敏感形门先修好，否则复查提交被门挡）　Blocks：12 |
| 基线 | main@81205f1 |

## 目标（可验证的一句话）
对 STEP-21、STEP-01、STEP-13 各输出一份 PASS / FAIL / UNKNOWN 判定（逐条对卡面验收标准），并把 P-48 的登记种类改正；判 FAIL 的条目写清复现命令，交回规划方。

## 输入
- 卡面：`V0.13.0/steps/STEP-21-*`、`V0.13.0/steps/STEP-01-*`、`V0.13.0/steps/STEP-13-*`
- 证据：`docs/06_validation/evidence/EVD-V13-21/`、`EVD-V13-01/`、`EVD-V3-13/`
- 提交：c93a6bc、1834c4a、bec5225（21）；25088c4（01）；81205f1（13）

## Execution Steps
1. [ ] **S30.1 复查 21**：本机真库跑 `tests/test_idor_matrix.py`；自己挑 2 个 A 类端点，临时删掉其属主判据，确认对应用例变红后还原；核对 `x-idor-classes` 的 B 类 minRole 与代码里的 `require_roles(...)` 逐条一致（不一致即 FAIL，不许改稿迁就代码）。
2. [ ] **S30.2 复查 01**：跑 `tests/test_contract_jsonschema.py` 与 `test_collection_contract.py`；自己改一处产物（例如某个 `maxLength` 减 1）确认探针等价用例变红后还原；`gen_contracts --check` rc=0。
3. [ ] **S30.3 复查 13**：跑 `tests/test_engines_capability.py`；对调 `_engine_reason` 任意两条判断确认变红后还原；`GET /api/v1/engines` 真请求一次，每项都带 `reason`。
4. [ ] **S30.4 P-48 更正**：`apps/api/app/contracts/identity.py` 里 `SessionClaims` 的 `identity-extra-forbid` 登记由 `strictness` 改为 `tightening`，契约两文件全绿；`gen_contracts --check` rc=0。

## 验收标准
- [ ] 三份判定写入 `docs/06_validation/evidence/EVD-V17-30/`，每条验收标准一行：PASS / FAIL / UNKNOWN + 证据路径或命令输出
- [ ] 每个"临时改坏再还原"的操作都有改坏时的失败输出与还原后的 `git diff` 为空的读数
- [ ] S30.4 后契约测试全绿，全量真库 `failed = 0`

## 验证命令
```bash
cd apps/api && . .venv/bin/activate
export AIDEANBOT_TEST_PG_DSN=postgresql+psycopg://postgres@127.0.0.1:5547/bothot_test DATABASE_URL=$AIDEANBOT_TEST_PG_DSN
python -m pytest tests/test_idor_matrix.py tests/test_contract_jsonschema.py tests/test_collection_contract.py tests/test_engines_capability.py -q -rs
cd ../.. && python scripts/gen_contracts.py --check
```

## 允许修改
- `apps/api/app/contracts/identity.py`（仅 S30.4 那一条登记的 `kind`）
- `docs/06_validation/evidence/EVD-V17-30/**`
- 临时改坏的业务文件必须在同一步还原，提交里不得出现

## 禁止修改
- 被复查卡的测试与实现（发现问题只判 FAIL 并写复现，不自己修）
- 冻结契约稿 `docs/任务规划V0.12.0/contracts/**`

## 阻塞条件
- 本机无 PG ⇒ 判 UNKNOWN 并写明，不得把 skip 当 PASS

## 升级条件
任一卡判 FAIL ⇒ 停在本卡，交回规划方裁决，不开第 2 轮自修
