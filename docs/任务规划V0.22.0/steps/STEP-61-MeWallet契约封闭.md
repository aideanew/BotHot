# STEP-61 MeWallet 契约封闭（D-V21-21 另一半）

> 基线 main@12c87e9（实际开工在 `291d530`，差的是规划方两个文档提交，本卡允许面在其中零改动）｜状态：✅ 已交付（台账 P-121 记闭合、P-130 记交回；读数与越界申报见 `EVD-V22-61/s61_readings.md`）｜裁决 D-V21-21、D-V22-05、D-V22-06

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行助手（opus 档；D-V22-06，原子步与判据见 `08-阶段A执行细则.md` §4，冲突以 08 为准）｜切片 S-CON-1 |
| 2 来源 | D-V21-21；STEP-57 卡面第 5 格 ③ 未执行 |
| 3 目标 | 冻结稿、`shapes.py`、生成产物三处 `MeWallet` 均封闭，多余键契约测试红 |
| 4 输出 | 先红读数；同一提交改冻结稿 `additionalProperties:false` + `shapes.py` `extra="forbid"` + 重生成产物 |
| 5 验收 | ① 改前多余键不红（入证）② 改后多余键红 ③ `gen_contracts.py --check` 幂等 ④ `_WALLET_UNAVAILABLE` 键 ⊆ 五键（新增断言）⑤ 前端 tsc 0 |
| 6 允许修改 | `apps/api/app/contracts/shapes.py`（仅 `MeWallet`）、`packages/contracts/**` 产物、`docs/任务规划V0.12.0/contracts/shapes.schema.json`（仅 `MeWallet`）、`apps/api/tests/test_contract_*.py`、`apps/api/tests/test_me_wallet_projection.py`、`apps/web/**` 类型（仅 tsc 要求时） |
| 7 禁止修改 | 其余 def、service、迁移 |
| 8 规模/档位 | ≈0.3 人日｜opus（契约语义 + 冻结稿落笔权在规划方） |
| 9 熔断 | 同判据 2 次 FAIL ⇒ 停；前端读了五键外字段 ⇒ 停 |
| 10 验证命令 | `cd apps/api && pytest tests/test_contract_jsonschema.py tests/test_contract_def_coverage.py tests/test_shapes_response_contract.py tests/test_me_wallet_projection.py tests/test_auth.py -q && python ../../scripts/gen_contracts.py --check && cd ../web && pnpm exec tsc --noEmit` |
| 11 证据 | `docs/06_validation/evidence/EVD-V22-61/` |
| 12 依赖 | 无｜Blocks：62 |
| 13 阻塞条件 | 降级常量含五键外键 ⇒ 停，交回（需先改 service） |
| 14 升级条件 | 无 |
| 15 档位理由 | 冻结稿仅规划方落笔（D-V21-20） |
| 16 规模 | 小，<2 小时，但因落笔权不可与他卡合并 |
