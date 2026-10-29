# STEP-68：逐视图态投影 `UX_VIEW_STATES`

## 1. 归属

- 所属切片：P-B 产品兑现层
- 来源需求：`02` M-6；台账 P-80（部分闭合余项）、P-147
- 来源方案：D-V24-05、D-V23-08
- 执行者：执行助手

## 2. 目标

`packages/contracts/src/ux/states.ts` 除 8 值词表 `UX_STATES` 外，再导出一份**逐视图投影** `UX_VIEW_STATES`（6 个视图 × 各自键集），并由 `apps/api/tests/test_ux_states_contract.py` 新增一条断言钉住「投影 == 冻结稿 `x-core-views[].states` 的键集」，无任何例外分支。

## 3. 输入

- 文档：`01` §2.1（6 个视图各列 5–7 个键的现读）、`03` §2（STEP-70 改后的稿）
- 契约：`docs/任务规划V0.12.0/contracts/ux_states.schema.json#x-core-views`
- 前置任务：STEP-70
- 前置状态：`NotificationBell.offstate` 已移出 `states`（否则投影要带例外）

## 4. 输出

- 修改：`packages/contracts/src/ux/states.ts`（新增 `UX_VIEW_STATES` + 类型）
- 修改：`packages/contracts/src/index.ts`（导出类型）
- 修改：`apps/api/tests/test_ux_states_contract.py`（新增 1 条 + 头注补第 ⑤ 条）
- 新增：`docs/06_validation/evidence/EVD-V24-68/`

## 5. Execution Steps

1. [x] **S68.1** 在 `states.ts` 末尾追加（**保持 `UX_STATES` 那一行的形态不变**，`:36` 的正则锚着它）：

   ```ts
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
   ```

2. [x] **S68.2** `index.ts` 增加 `export type { UxViewStates } from "./ux/states";`（**只导出类型**，不导出值——`emitDeclarationOnly` 下导出值等于给消费侧一个运行时黑洞）
3. [x] **S68.3** `test_ux_states_contract.py` 新增一条：

   ```python
   def test_ux_view_states_projection_equals_frozen_draft() -> None:
       """逐视图键集 == 冻结稿 x-core-views[].states 的键集，同序，无例外。

       为什么不留 `offstate` 例外：例外会腐化，且下一个写卡的人不知道要不要再加一个。
       STEP-70 已把它移到 `x-build-mode-notes`，所以这里可以无条件逐键比。
       """
       # 归一：首段 → 去前导 / → 小写 → 去非字母数字
       ...
   ```

   归一实现必须是纯函数、写在测试文件内，不引第三方。

4. [x] 头注（`states.ts` 与测试文件）补第 ⑤ 条说明：**投影是"本视图要交的态"，词表是"可能的态"**
5. [x] 跑定向测试
6. [x] 本卡单独提交并推送

## 6. 验收标准

- [x] `states.ts` 中 `UX_STATES` 那一行**字节未变**（`grep -n '^export const UX_STATES = \[' ` 仍恰好 1 条）
- [x] `UX_VIEW_STATES` 6 个键，各键的值都是 `UX_STATES` 的子集
- [x] `chat` 的值恰为 `["loading","success","error","unauthenticated","degraded"]`（**不含** `initial`/`empty`/`forbidden`）
- [x] `notificationbell` 的值**不含** `offstate`
- [x] `pytest tests/test_ux_states_contract.py -q` = **5 passed**（原 4 条 + 新增 1 条）
- [x] `grep -c "offstate" apps/api/tests/test_ux_states_contract.py` = **0**（无例外分支）
- [x] `pnpm exec tsc --noEmit`（`packages/contracts` 与 `apps/web`）通过
- [x] 本卡不改 `scripts/gen_contracts.py`（`ux` 仍不进生成器，`test_ux_domain_is_not_half_wired_into_the_generator` 绿）

## 7. 验证命令

```bash
cd /d/Code/AideanBotHot
grep -n '^export const UX_STATES = \[' packages/contracts/src/ux/states.ts
cd apps/api && python -m pytest tests/test_ux_states_contract.py -q
cd /d/Code/AideanBotHot/apps/web && pnpm exec tsc --noEmit
cd /d/Code/AideanBotHot && grep -c "offstate" apps/api/tests/test_ux_states_contract.py || echo "0（期望）"
```

## 8. 证据路径

`docs/06_validation/evidence/EVD-V24-68/`（含 5 passed 原文 + 6 视图键集打印）

## 9. 允许修改

- `packages/contracts/src/ux/states.ts`
- `packages/contracts/src/index.ts`
- `apps/api/tests/test_ux_states_contract.py`
- `docs/06_validation/evidence/EVD-V24-68/**`

## 10. 禁止修改

- `packages/contracts/schemas/**`（不得造 `ux.schema.json`，`test_ux_domain_is_not_half_wired_into_the_generator` 会红）
- `scripts/gen_contracts.py`
- `docs/任务规划V0.12.0/contracts/**`（冻结稿由 STEP-70 独占）
- `apps/web/**`（本卡不碰前端）
- `apps/api/app/**`

## 11. 依赖与阻塞

- Depends on：STEP-70（`offstate` 未移出时，投影必须带例外 ⇒ 与「无例外」的验收冲突）
- Blocks：STEP-60（60 的用例清单以逐视图键集为准）
- 阻塞条件：`test_ux_states_literal_equals_frozen_draft_enum` 变红 ⇒ 停手（说明动到了 `UX_STATES` 那一行的形态）

## 12. 建议执行档位

sonnet。理由：纯字面量 + 一条断言，无架构判断。

## 13. 升级条件

- 归一规则在 6 个视图上出现歧义（如某视图 `view` 首段不是合法标识符）⇒ 升级 opus，交回规划方定归一规则，**不许自己加别名表**

## 14. 预估规模

小，≈0.3 人日，小于 2 小时。

## 15. 熔断

同一判据 2 轮未过 ⇒ 停手，登 P 号。

## 16. 交接物

`EVD-V24-68/` 要能让一周后的人核对「投影 == 稿」而不用读代码。
