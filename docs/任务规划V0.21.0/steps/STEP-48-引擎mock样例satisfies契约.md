# STEP-48 引擎域 mock 样例 satisfies 契约类型（S37.4 第一段 + P-119）

> 基线 main@9028b89（+规划提交）｜状态：✅ 收口（2026-10-24，交付 head be23d41 三绿 attempt 1：CI 40106721804 / CI-Windows 40106721828 / Security 40106721807；读数在 EVD-V21-48/）｜版本 V0.21.0

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行助手（Agent-Web） |
| 2 切片 | SL-SHAPE |
| 3 来源 | S37.4（V0.18.0 STEP-37）、P-82、**P-119**、D-V21-01/02 |
| 4 目标 | 引擎域 mock 样例与前端引擎类型由契约生成类型约束；写错一个字段 tsc 红 |
| 5 输入 | `packages/contracts/src/engine/dto.ts`（STEP-46 生成，**只读**）；`apps/web/lib/api/engines.ts:43-83`；`apps/web/lib/api/mock-routes.ts` engines 段（`MOCK_ENGINES` 与 GET /engines、PATCH /spaces/{id}/engine 两条路由） |
| 6 输出 | 改 `apps/web/lib/api/engines.ts`（`EngineItem` → `export type EngineItem = EngineCapability`，列表返回类型用 `EngineList`，PATCH 返回用 `SpaceEngineBinding`）；改 `mock-routes.ts` engines 段（5 条样例补 `activeSource: null`、`decryptFailed: false`；每条样例与两条 handler 返回值 `satisfies` 契约类型）；新 `apps/web/tests/s48-engine-contract.spec.ts`（运行时断言 mock 列表每条恰好 10 个键）；改 `mock-routes.ts` 头注释"形状来源"段为"引擎域已由契约约束，其余域待 STEP-52" |
| 7 验收 | ① 先红：在未改代码上把一条样例 `satisfies EngineCapability`，tsc 报 TS1360 缺 `decryptFailed`（原文进证据）② 改后 `pnpm run typecheck` 0 错 ③ 反证：故意删一条样例的 `description` ⇒ tsc 红，还原后绿（两次输出进证据）④ vitest 全绿（含 `mock-routes.spec.ts`、`engines.spec.ts`、`engine-switcher-states.spec.tsx`）⑤ lint 绿 ⑥ 三绿 |
| 8 命令 | `cd apps/web && pnpm run typecheck && pnpm exec tsc --noEmit -p ../../packages/contracts/tsconfig.json && pnpm run test:unit && pnpm run lint` |
| 9 证据 | `docs/06_validation/evidence/EVD-V21-48/s48_readings.md` |
| 10 允许修改 | 第 6 格所列；以及因 `EngineItem` 收紧而 tsc 报错的**调用方**（只改类型标注或补默认值，不改渲染逻辑），逐个列入证据 |
| 11 禁止修改 | `packages/contracts/**`、`scripts/gen_contracts.py`、`apps/api/**`、mock 表其它域 |
| 12 依赖 | STEP-46 @ci 三绿 ｜ Blocks：STEP-52 |
| 13 档位 | sonnet（类型对齐，影响面小、可逆） |
| 14 升级条件 | 调用方 tsc 报错 >10 处，或需改渲染逻辑 ⇒ 停，交回 |
| 15 规模 | 小～中，≈0.4 人日 |
| 16 熔断 | 同判据 2 次 FAIL ⇒ 停卡交回 |

## 三级任务
1. [x] **S48.1 先红**
   1. [ ] S48.1.1 现读 `engines.ts`、`mock-routes.ts` 行号入证
   2. [ ] S48.1.2 临时加 `satisfies` 跑 tsc，TS1360 原文入证，然后撤掉临时改动
2. [x] **S48.2 类型对齐**
   1. [ ] S48.2.1 `EngineItem` 别名到契约类型；`listEngines`/`patchSpaceEngine` 返回类型改契约类型
   2. [ ] S48.2.2 修因收紧产生的调用方 tsc 报错（只改类型）
3. [x] **S48.3 样例约束**
   1. [ ] S48.3.1 5 条样例补两键并逐条 `satisfies EngineCapability`
   2. [ ] S48.3.2 两条 handler 返回值分别 `satisfies EngineList` / `SpaceEngineBinding`
   3. [ ] S48.3.3 反证：删字段 ⇒ tsc 红，还原
4. [x] **S48.4 运行时守卫** `s48-engine-contract.spec.ts`：mock GET /engines 每条 `Object.keys().length === 10` 且键集合等于契约键集合（键集合在测试里写死并注明"源 = packages/contracts/src/engine/dto.ts"）
5. [x] **S48.5** 全量 + 三绿 + 07 记录
