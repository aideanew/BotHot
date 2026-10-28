/**
 * 八态枚举（与冻结稿 `docs/任务规划V0.12.0/contracts/ux_states.schema.json` 的
 * `definitions.State.enum` **逐值同序**）。
 *
 * ⚠ 本文件是**手写常量，不是生成物**。STEP-64 原计划走方案 A（`app/contracts/ux.py` →
 * `schemas/ux.schema.json` → `src/ux/dto.ts` 三段链），但域一旦进生成器，
 * `apps/api/tests/test_collection_contract.py` 的 `set(fresh) == set(DOMAINS)` 会强制为 `ux`
 * 建一张「稿 ↔ 产物」逐 def 比对行；而冻结稿的 `definitions.State` 带非标准关键词 `note`，
 * 比对器对未知关键词判红（它的三条出路是「实现它 / 改一侧 / 忽略」，前两条分别撞
 * D-V23-06 不动门禁与 D-V21-20 冻结稿只读，第三条被它自己明令禁止）⇒ 依卡面第 13 格 ①
 * 转方案 B。读数与反证见 `docs/06_validation/evidence/EVD-V23-64/`，台账记 P-142。
 *
 * 相等性由 `apps/api/tests/test_ux_states_contract.py` 钉住（`pytest tests/` 已经会跑到它，
 * 不新建 CI 步骤）。
 *
 * ⚠ 消费口径：本包只导出类型（`tsconfig.json` 是 `emitDeclarationOnly`，`src/index.ts` 头注
 * 第 1 条写的就是「因此消费侧必须用 `import type`」）⇒ **不要把 `UX_STATES` 当运行时值导入**。
 * 需要在运行时枚举八态的地方（vitest / e2e），按那条测试的做法读这个数组字面量，
 * 类型侧则用 `import type { UxState } from "@bothot/contracts"`。
 */
export const UX_STATES = ["initial", "loading", "empty", "success", "error", "forbidden", "unauthenticated", "degraded"] as const;

export type UxState = (typeof UX_STATES)[number];
