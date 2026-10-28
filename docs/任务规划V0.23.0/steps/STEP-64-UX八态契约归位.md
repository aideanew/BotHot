# STEP-64 UX 八态契约归位（P-80 / P-139）

> 基线 main@04d50f8｜状态：⬜ 未开｜裁决 D-V23-02、D-V23-06｜切片 S-UX-CON｜归属：**规划方亲做**（核心/高难）

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行助手（opus 档；依 D-V23-07 自规划方改派）｜切片 S-UX-CON｜原子步与判据见 `08-阶段A执行细则.md` §2，冲突以 08 为准 |
| 2 来源 | P-80（`docs/任务规划V0.12.0/00-README.md:147`，自 V0.12.0 未认领）；P-139（本版新登记，契约锚被硬编码在历史版本目录）；`01` §3 U7 |
| 3 目标 | 八态枚举有**活体契约源**：`packages/contracts/schemas/` 下存在一份 ux 形状产物，其 `$defs.State.enum` 与冻结稿 `definitions.State.enum` **逐值且同序**相等（8 值） |
| 4 输出 | ① `apps/api/app/contracts/ux.py`（新增，`State` 8 值 Enum + `StateRendering`，`extra="forbid"`）；② `scripts/gen_contracts.py` 两处域表各加一行；③ `packages/contracts/schemas/ux.schema.json`（新增产物）；④ `packages/contracts/src/ux/dto.ts`（新增产物）；⑤ `packages/contracts/src/index.ts` 导出；⑥ `apps/api/tests/test_contract_jsonschema.py` 的 `DOMAINS` 加一行 + 一条枚举相等断言；⑦ 先红原文入证 |
| 5 验收 | ① 未改前既有 7 域契约测试全绿（基线读数入证）② 故意把 `State` 写成 7 值（少 `degraded`）⇒ 新断言必红，原文入证，随后还原 ③ 还原后该断言绿 ④ `python scripts/gen_contracts.py --check` rc 0 ⑤ `packages/contracts/schemas/` 下除新增 `ux.schema.json` 外其余 7 份字节零变化（`git diff --stat` 只 1 个 `+` 行）⑥ `cd apps/web && pnpm exec tsc --noEmit` rc 0 ⑦ 冻结稿 `docs/任务规划V0.12.0/contracts/ux_states.schema.json` 字节零变化（`git diff --quiet -- <该路径>` rc 0） |
| 6 允许修改 | `apps/api/app/contracts/ux.py`（新增）、`scripts/gen_contracts.py`（**仅**两处域表各加一行，不改任何判定逻辑）、`packages/contracts/schemas/ux.schema.json`（新增）、`packages/contracts/src/ux/**`（新增）、`packages/contracts/src/index.ts`（仅导出）、`apps/api/tests/test_contract_jsonschema.py`（仅 `DOMAINS` 一行 + 一条断言） |
| 7 禁止修改 | `docs/任务规划V0.12.0/contracts/**`（只读，D-V21-20）；`apps/api/app/api/**`、`apps/api/app/services/**`、`apps/api/app/models/**`；`apps/web/**` 除 tsc 必需的类型引用外；`.github/workflows/**`（D-V23-06）；既有 7 域的任何 def |
| 8 规模/档位 | ≈0.5 人日｜opus（契约链三段 + 既有判据登记面，写错会让 7 域产物一起漂） |
| 9 熔断 | 同判据 2 次 FAIL ⇒ 停手写 P 号（从 P-140）交回；若 S64.0 判 B 而执行者仍按 A 硬做 ⇒ 停；若需改冻结稿才能让 A 成立 ⇒ 停（落笔权不在本卡） |
| 10 验证命令 | `@win`：`cd apps/api && .venv/Scripts/python.exe -m pytest tests/test_contract_jsonschema.py tests/test_contract_def_coverage.py -q` → `python ../../scripts/gen_contracts.py --check` → `cd ../web && pnpm exec tsc --noEmit`；`@ci`：`Contract drift gate (gen_contracts --check)` 步绿 |
| 11 证据 | `docs/06_validation/evidence/EVD-V23-64/`（先红原文、枚举逐值对照表 8 行、`--check` rc、`git diff --stat`、冻结稿零变化证明） |
| 12 依赖 | 无｜Blocks：65（65 的用例要 import 该枚举）、66（同改 `gen_contracts.py` 与 `index.ts`）、60（八态枚举来源） |
| 13 阻塞条件 | ① 冻结稿的 `definitions` 与产物的 `$defs` 键形使逐 def 比对无法在不改冻结稿的前提下成立 ⇒ 转方案 B（见 08 §2.3），**不算阻塞**；② 若 B 也无法让 `test_every_domain_has_a_generated_counterpart` 成立 ⇒ 停，交回规划方重定（此时才叫阻塞） |
| 14 升级条件 | 需新增/修改生成器的判定逻辑 ⇒ 升 fable 并先开裁决（本卡明令不改判定逻辑） |
| 15 档位理由 | 契约语义 + 跨模块集成仲裁，属 opus 适用面；不涉需求终裁故不用 fable |
| 16 规模 | 小-中（≈0.5 人日）；**>2 小时**，因含先红/还原/重生成三段，不与相邻卡合并 |

## 附：为什么这张卡必须排在 STEP-60 之前

STEP-60 的判据原文（V0.22.0 `08` §2 59.4）要求「八态枚举改为读 `ux_states.schema.json`」。
若照字面执行，`r19-chat-stream.spec.ts` 会去读 `docs/任务规划V0.12.0/contracts/ux_states.schema.json`——
一个**历史版本目录**。后果有三层：
① 任何一次文档整理（历史版本归档、目录改名）都会静默打断 e2e；
② 该文件不受 `gen_contracts --check` 保护，改了没人知道；
③ 它使"契约唯一源"这条纪律在 e2e 这一侧破例，而破例不会写在任何门里。

本卡把**机器可校验的那一半**（8 值枚举 + `StateRendering` 形状）搬进活体链，
叙述性的一半（`x-core-views` 六视图的文案要求）留在冻结稿当设计说明——
这是刻意的取舍：叙述无法由 Pydantic 生成，硬搬只会造出第二份手写真相。
