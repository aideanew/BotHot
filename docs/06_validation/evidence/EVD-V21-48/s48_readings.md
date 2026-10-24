# EVD-V21-48 引擎域 mock 样例 satisfies 契约（执行助手）

平台 @win（Windows 10 x64，`apps/api/.venv` PG16.15@5547 自备便携库），开工 head `9816f7f`（规划批，
三绿 CI 40099919134 / CI-Windows 40099919204 / Security 40099919142），时间 2026-10-24（Asia/Shanghai）。

## S48.1 先红

- 现读行号（开工时）：`engines.ts:43` `EngineItem`（`activeSource?` :52、`decryptFailed?` :56），
  `:61` `PatchEngineResult`，`:79` `listEngines`，`:90` `patchSpaceEngine`；`mock-routes.ts:164`
  `MOCK_ENGINES`，`:222` GET handler，`:231` PATCH handler。
- 临时在第一条样例挂 `satisfies EngineCapability` 跑 `pnpm run typecheck` ⇒ **TS1360**
  （对象缺 `decryptFailed` 不满足 `EngineCapability`）+ TS2322（activeSource 收窄），原文存
  `s48_red_tsc.txt`，随后撤掉临时改动（git diff 核对还原）。

## 改动摘要（S48.2 / S48.3）

- `engines.ts`：`EngineItem` 别名契约生成类型（`import type { EngineCapability, EngineList,
  SpaceEngineBinding } from "@bothot/contracts"`）；`listEngines(): Promise<EngineList>`；
  `patchSpaceEngine(): Promise<SpaceEngineBinding>`（`PatchEngineResult` 接口删除，无外部消费方）。
- `mock-routes.ts`：5 条样例各补 `activeSource`（builtin 保持 `"env"`，其余 `null`）与
  `decryptFailed: false`，逐条 `satisfies EngineCapability`；GET handler 返回 `satisfies
  EngineList`、PATCH handler 返回 `satisfies SpaceEngineBinding`；头注释"形状来源"段改两档口径
  （引擎域已契约约束 / 其余域待 STEP-52）。import 从本地 `EngineItem` 换成契约类型。
- 新增 `tests/s48-engine-contract.spec.ts`（S48.4 运行时守卫，2 用例）：
  ① mock GET /engines 每条恰好 10 键且键集合与契约逐字相同（键集合写死、注明源=dto.ts）；
  ② 判据自检——dto.ts 的 `EngineCapability` 恰 10 字段行、成员名与写死清单一致。

## 调用方修正（卡面允许面：类型标注/补默认值，不改渲染逻辑）

| 文件:行 | 修法 |
|---|---|
| `tests/engine-switcher-states.spec.tsx:121` | 夹具补 `activeSource: null, decryptFailed: false, implemented: false` |
| `tests/engines.spec.ts:51`（registered） | 补 `implemented: false` |
| `tests/engines.spec.ts:68`（legacy） | 补三键默认值；断言 `toBeUndefined()`×2 改 `toBeNull()` / `toBe(false)`（契约语义：未配置来源由 null 表达） |
| `tests/r062-onboarding-steps.spec.tsx:68/77` | 两夹具各补三键默认值 |

渲染组件（EngineSwitcher 等）零改动。

## 反证（S48.3.3）

删 coze 样例的 `description` ⇒ tsc **TS1360**（该样例不满足）+ TS2322（数组不再 assignable），
原文存 `s48_delete_field_red.txt`；还原后 0 错。

## 本机复跑（@win）

- 前端全套：`typecheck` 0 错；`tsc -p packages/contracts` 0 错；`test:unit` **51 files / 420 passed**
  （含新增 s48 spec 2 条、mock-routes.spec、engines.spec、engine-switcher-states.spec）；
  `lint` 0 警告 0 错误。
- 后端全量基线：首跑 **33 failed**——系本机 `bothot_test` 残留 STEP-18 性能种子数据（自种自污，
  如实记录），与代码无关（同树 @ci 三绿佐证）；`DROP DATABASE bothot_test` 重建 + 迁移后复跑
  **2379 passed / 6 skipped / 4 deselected / 0 failed**（1632s）。

## @ci（推送后回填，2026-10-25 0:1x @win，Asia/Shanghai）

交付 head `be23d41`（开发期间远端进了规划方的 STEP-46 收口批 `fa276c6`，本卡 rebase 其上后推送）：

| 工作流 | run id | 轮次 | 结论 |
|---|---|---|---|
| CI | 40106721804 | attempt 1 | success |
| CI-Windows | 40106721828 | attempt 1 | success |
| Security | 40106721807 | attempt 1 | success |

完成判据对照：先红（TS1360 原文）✅；typecheck 0 错 ✅；反证（删 description ⇒ TS1360+TS2322 红、还原绿）✅；
vitest 全绿（51 文件 420 用例含 s48 守卫 2 条）✅；lint 绿 ✅；三绿 ✅；契约面零改动（rebase 后
`git diff fa276c6 be23d41 --name-only` 对 packages/contracts / gen_contracts / apps/api 零命中）✅。
