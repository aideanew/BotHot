# STEP-66 身份与问答形状契约化（P-82 余项）

> 基线 main@04d50f8｜状态：⬜ 未开｜裁决 D-V23-01、D-V23-06、D-V21-01｜切片 S-CON-2｜归属：执行助手

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行助手（sonnet 档）｜切片 S-CON-2｜设计裁决见 `03` §2.2/§2.3 与 `08` §4 |
| 2 来源 | `packages/contracts/src/index.ts:17`「保持骨架：identity / chat」；P-82 余项；`01` §3 U6 |
| 3 目标 | `apps/web/lib/api/types.ts` 里**不再有**手写的 Me / Chat 形状字段清单——`MeData`、`ChatCitation`、`ChatAnswer` 全部改为契约派生别名 |
| 4 输出 | ① `scripts/gen_contracts.py` 的 `DOMAIN_ENTITIES` 加 `"identity": ("entities", ["User"])`；② `packages/contracts/src/identity/dto.ts`（生成产物）；③ `apps/api/app/contracts/shapes.py` 新增 `ChatCitation` / `ChatAnswer` 两个 def；④ `packages/contracts/src/shapes/dto.ts` 重生成；⑤ `apps/web/lib/api/types.ts` 三处改别名；⑥ `packages/contracts/src/index.ts` 注释补 identity↔shapes 的分工说明 |
| 5 验收 | ① `python scripts/gen_contracts.py --check` rc 0 ② `grep -c "is_admin: boolean" apps/web/lib/api/types.ts` = 0（手写 Me 字段清单已消失）③ `pnpm exec tsc --noEmit` rc 0 ④ `vitest run tests/me-normalize.spec.ts tests/mock-default.spec.ts tests/s52-mock-contract-coverage.spec.ts` 全绿 ⑤ `pytest tests/test_contract_jsonschema.py tests/test_shapes_response_contract.py tests/test_contract_def_coverage.py -q` 全绿 ⑥ `git diff --stat` 在 `apps/api/app/models/**` 上为空（**不改库模型**，只内省） |
| 6 允许修改 | `scripts/gen_contracts.py`（仅 `DOMAIN_ENTITIES` 一行 + 必要注释）、`apps/api/app/contracts/shapes.py`（仅新增两个 def）、`packages/contracts/**` 产物、`apps/web/lib/api/types.ts`、`apps/api/tests/test_contract_jsonschema.py`（仅 `DOMAINS` 如必要） |
| 7 禁止修改 | `apps/api/app/models/**`（不改列）；`apps/api/app/api/**`、`apps/api/app/services/**`；`apps/web/lib/api/ask.ts`；`.github/workflows/**`（D-V23-06）；`docs/任务规划V0.12.0/contracts/**`（只读）；`apps/web/e2e/**` |
| 8 规模/档位 | ≈0.4 人日｜sonnet（机制已在，照 64 的形制复制） |
| 9 熔断 | 同判据 2 次 FAIL ⇒ 停手写 P 号（从 P-140）交回；若 `User` 与既有 `$defs` **同名不同体** ⇒ 按生成器守卫报错处理（改名），**不得**改守卫或改既有 def 去迁就；若 `MeData` 改别名后 tsc 报字段缺失 ⇒ 按 `get_me` 三条分支字典（`service.py:239-250/273-278/286-293`）为准改前端，**不反向改后端** |
| 10 验证命令 | `@win`：`python scripts/gen_contracts.py --check` → `cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_contract_jsonschema.py tests/test_shapes_response_contract.py tests/test_contract_def_coverage.py -q` → `cd ../web && pnpm exec tsc --noEmit` → `pnpm exec vitest run tests/me-normalize.spec.ts tests/mock-default.spec.ts tests/s52-mock-contract-coverage.spec.ts`；`@ci`：`Contract drift gate` 步绿 |
| 11 证据 | `docs/06_validation/evidence/EVD-V23-66/`（`--check` rc、`grep -c` 读数、tsc rc、三份 vitest 读数、`User` 列清单与产物逐列对照） |
| 12 依赖 | 64（同改 `gen_contracts.py` 与 `index.ts`，必须串行在其后）｜Blocks：无（60/62 不依赖它） |
| 13 阻塞条件 | ① `User` 内省出的列与 `shapes.MeView` 存在**语义冲突**（同名列不同类型）⇒ 停，交回规划方裁决（不得靠改名掩盖）；② 需要新建 `packages/contracts/src/chat/dto.ts` 才能通过验收 ⇒ **卡面判据本就不要它**，说明理解偏了，停手重读 `03` §2.3 |
| 14 升级条件 | 需改 `shapes.py` 既有 def 的语义 ⇒ 升 opus |
| 15 档位理由 | 机制已定、形制可照抄，属原子任务实现面；不涉架构决策 |
| 16 规模 | 小（≈0.4 人日）；3 个原子步各自 <2 小时 |

## 附：为什么 chat 不新建 `chat/dto.ts`

`DOMAIN_ENTITIES` 的机制是**SQLAlchemy 列内省**（`gen_contracts.py:40-48`），而 chat 域没有实体——
`docs/02_requirements/product-requirements.md:40` 的数据模型列写的就是「—」。
给它建 `dto.ts` 只有一条路：手写一个 Pydantic 模型再生成回 TS，等于把"手写真源"从
`types.ts` 搬到 `app/contracts/chat.py`，**真源数量不变、链路还多一跳**。

而 `ChatCitation` / `ChatAnswer` 本来就是**线上响应形状**，按 STEP-47 定的分工
（`shapes` 域 = 线上 `data` 形状），它们该去 `shapes`，不该去 `chat`。
这就是本卡只做两件事的原因：identity 补"库形状"，chat 的"线上形状"归位 `shapes`。
