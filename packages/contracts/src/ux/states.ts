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
 *
 * ⑤ 逐视图投影（STEP-68）：`UX_VIEW_STATES` 是「**本视图要交的态**」，`UX_STATES` 是
 * 「**可能的态**」——两者不是同一条判据。把词表当要求，就会为只有 5 个键的视图造出
 * 契约里没有的态（这一步已发生过，见下方 `UX_VIEW_STATES` 的块注）。
 */
export const UX_STATES = ["initial", "loading", "empty", "success", "error", "forbidden", "unauthenticated", "degraded"] as const;

export type UxState = (typeof UX_STATES)[number];

/**
 * 逐视图态投影（D-V24-05 / 台账 P-147）。
 *
 * 为什么需要它：`UX_STATES` 是**全局词表**（8 值），而契约给每个视图只列 5–7 个键
 * （`x-core-views[].states`）。把词表当要求，就会为 `/chat` 造出 `initial` / `forbidden`
 * 两个契约里没有的态——这正是 `r19-chat-stream.spec.ts` ④ 退化成「断言全部未测」的原因。
 *
 * 键的归一规则（测试侧同一套）：取 `x-core-views[].view` 的**首段**，去掉前导 `/`，
 * 转小写并去掉非字母数字 ⇒ `/spaces 列表…`→`spaces`、`NotificationBell（站内通知）`→
 * `notificationbell`。**不使用别名表**：别名表会变成第二个真源。
 *
 * 顺序与 `x-core-views` 同序；值与该视图 `states` 的键**同序**（消费侧按序生成用例标题）。
 *
 * ⚠ 口径：投影是「本视图要交的态」，词表是「可能的态」。相等性由
 * `apps/api/tests/test_ux_states_contract.py` 的 `test_ux_view_states_projection_equals_frozen_draft` 钉住。
 */
export const UX_VIEW_STATES = {
  spaces: ["loading", "empty", "success", "error", "forbidden", "unauthenticated", "degraded"],
  hot: ["loading", "empty", "success", "error", "degraded"],
  chat: ["loading", "success", "error", "unauthenticated", "degraded"],
  admin: ["unauthenticated", "forbidden", "empty", "success", "error", "degraded"],
  notificationbell: ["loading", "empty", "success", "error", "degraded"],
  onboarding: ["success", "degraded"],
} as const;

export type UxViewStates = typeof UX_VIEW_STATES;
