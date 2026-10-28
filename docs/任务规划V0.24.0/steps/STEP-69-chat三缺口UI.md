# STEP-69：`/chat` 三缺口（loading 原字 / 可中断 / error 原字）

## 1. 归属

- 所属切片：P-B 产品兑现层
- 来源需求：`02` M-1、M-2、M-3、M-4；台账 P-143
- 来源方案：D-V24-04、D-V24-09
- 执行者：**规划方（UI）**——按用户分工规则，UI 与高难度任务归规划方

## 2. 目标

`/chat` 的 `loading` 态渲染契约原字「思考中…」且带可点的「停止」按钮；`error` 态渲染含契约原字「连接中断，可重试」；这三串与既有 `degraded`/`slow` 两串**只有一份字面量**（`CHAT_COPY`），产品组件与 spec 都从它导入。

## 3. 输入

- 文档：`03` §4（双向召回清单，**强制输入**）
- 契约：`ux_states.schema.json#x-core-views[/chat 流式问答]`（STEP-70 改后版本）
- 前置任务：STEP-70
- 前置状态：契约四处矛盾已消失（`x-required-for-every-core-view=false`）

## 4. 输出

- 新增：`apps/web/lib/chat/copy.ts`（`CHAT_COPY`）
- 修改：`apps/web/components/chat/ChatMessageList.tsx`（`thinking` / `slow` / `stopped` 三支）
- 修改：`apps/web/components/chat/useSseAsk.ts`（导出 `stop()`；`degraded`/`interrupted` 走常量）
- 修改：`apps/web/components/chat/AskInputBar.tsx`（`asking` 时按钮为「停止」+ `onStop`）
- 修改：`apps/web/components/chat/types.ts`（`ChatMessage.stopped?: boolean`）
- 修改：`apps/web/app/chat/page.tsx`（把 `stop` 透传给 `AskInputBar`）
- 修改：`apps/web/lib/api/ask.ts`（`:198`/`:200` 两串走常量）
- 修改：`apps/web/tests/ask-sse-degraded.spec.ts`、`apps/web/tests/r061-sse-ask.spec.ts`、`apps/web/e2e/trunk.spec.ts`（改常量导入）
- 新增：`docs/06_validation/evidence/EVD-V24-69/`

## 5. Execution Steps

1. [ ] **S69.1** 新建 `apps/web/lib/chat/copy.ts`：

   ```ts
   /**
    * `/chat` 的产品文案唯一字面量（D-V24-09 / D-V23-19）。
    * 来源：`docs/任务规划V0.12.0/contracts/ux_states.schema.json#x-core-views[/chat 流式问答]`。
    * 产品组件与 spec 一律从本文件导入，不得再写字面量——上一轮（P-146）同一句文案散在
    * `useSseAsk.ts` / `ask-sse-degraded.spec.ts` / `trunk.spec.ts` 三处，改一处漏两处。
    * ⚠ 不能放 `@bothot/contracts`：该包 `emitDeclarationOnly`，spec 无法运行时 import。
    */
   export const CHAT_COPY = {
     /** loading：契约原字「思考中…」 */
     thinking: "思考中…",
     /** loading 的可中断入口 */
     stop: "停止",
     /** error：契约原字「连接中断，可重试」 */
     interrupted: "连接中断，可重试",
     /** error：已渲染部分内容时，保留「可能不完整」这条信息（D-V24-04） */
     interruptedPartial: "连接中断，可重试（已生成内容可能不完整）",
     /** degraded：30002 / 50002 */
     degraded: "引擎暂不可用，请稍后重试或换个空间",
     /** degraded：首 token 慢锚 */
     slow: "响应较慢，仍在生成…",
     /** 用户主动停止（不是错误态，见 S69.3） */
     stopped: "已停止",
   } as const;
   ```

2. [ ] **S69.2** `ChatMessageList.tsx:74` 的「正在思考…」改为 `{CHAT_COPY.thinking}`；`:71` 的「响应较慢，仍在生成…」改为 `{CHAT_COPY.slow}`
3. [ ] **S69.3** `useSseAsk.ts` 新增并导出 `stop()`：

   - `streamAbortRef.current?.abort()`
   - 找到当前正在流式的助手消息（`streaming === true` 的最后一条），`patch(id, { streaming: false, slow: false, stopped: true })`
   - **不得** `setMessages([])`、**不得** `setInput("")`（那是 `reset()` 的语义，`:179-184`）
   - 在 `UseSseAskResult` 里加 `stop: () => void`
   - `ChatMessageList` 增一支：`m.stopped && !m.content` ⇒ 渲染 `CHAT_COPY.stopped`（中性灰，不是 `text-danger`）；`m.stopped && m.content` ⇒ 正文 + 一行 `CHAT_COPY.stopped` + 「重试」按钮（复用 `onRetry`）

4. [ ] **S69.4** `AskInputBar.tsx`：`asking` 时按钮文案 `CHAT_COPY.stop`、`type="button"`、`onClick={onStop}`、**不再 `disabled`**；输入框仍 `disabled={asking}`（禁的是重复发送，不是禁止中止）
5. [ ] **S69.5** `ask.ts:198` → `CHAT_COPY.interruptedPartial`；`:200` → `CHAT_COPY.interrupted`；`useSseAsk.ts:128` → `CHAT_COPY.interrupted`；`:125` → `CHAT_COPY.degraded`
6. [ ] **S69.6** 按 `03` §4 改 6 处断言为常量导入：

   | 文件:行 | 旧 | 新 |
   |---|---|---|
   | `trunk.spec.ts:85` | `getByText("正在思考…")` | `getByText(CHAT_COPY.thinking)` |
   | `trunk.spec.ts:86` | `getByText("回答中…")` | `getByText(CHAT_COPY.stop)` |
   | `ask-sse-degraded.spec.ts:155` | `queryByText("正在思考…")` | `queryByText(CHAT_COPY.thinking)` |
   | `ask-sse-degraded.spec.ts:232` | 同上 | 同上 |
   | `ask-sse-degraded.spec.ts:242` | `getByText("正在思考…")` | `getByText(CHAT_COPY.thinking)` |
   | `ask-sse-degraded.spec.ts:116` | `toBe("回答生成失败，请稍后重试")` | `toBe(CHAT_COPY.interrupted)` |
   | `r061-sse-ask.spec.ts:154` | `message: "回答生成中断，内容可能不完整，请重试"` | `message: CHAT_COPY.interruptedPartial` |
   | `r061-sse-ask.spec.ts:165` | 同上 | 同上 |
   | `r061-sse-ask.spec.ts:209` | `toBe("回答生成失败，请稍后重试")` | `toBe(CHAT_COPY.interrupted)` |

   **`r061-sse-ask.spec.ts:199` 的 `"回答生成失败"` 不动**——那是 mock 的 `ApiError` 消息透传，不是兜底文案。

7. [ ] 跑定向测试（见第 7 节），全绿
8. [ ] 本卡单独提交并推送

## 6. 验收标准

- [ ] `grep -c "思考中" apps/web/components/chat/` ≥ 1，且 `grep -c "正在思考"` = **0**
- [ ] `grep -rc "连接中断，可重试" apps/web/lib` ≥ 1，且 `grep -rc "回答生成中断" apps/web` = **0**（产品侧归零）
- [ ] `grep -rn "响应较慢，仍在生成" apps/web/components` = **0**（已走常量）
- [ ] `useSseAsk` 返回值含 `stop`，且 `stop()` 不调用 `setMessages([])`（人工读 diff 确认）
- [ ] `AskInputBar` 在 `asking` 时按钮 `disabled` 为 false 且文案为「停止」
- [ ] 点「停止」后：`asking` 转 false、不再追加 delta、已渲染正文仍在
- [ ] 新增一条 vitest：`stop()` 后 `messages` 长度不变、`messages[1].stopped === true`、`content` 保持
- [ ] `pnpm exec vitest run tests/ask-sse-degraded.spec.ts tests/r061-sse-ask.spec.ts` 全绿
- [ ] `pnpm exec tsc --noEmit` 通过
- [ ] `pnpm run test:e2e -- e2e/trunk.spec.ts` 42 条同集不减少（mock 档不回归）

## 7. 验证命令

```bash
cd /d/Code/AideanBotHot/apps/web
pnpm exec tsc --noEmit
pnpm exec vitest run tests/ask-sse-degraded.spec.ts tests/r061-sse-ask.spec.ts tests/r061-sse-ask.spec.ts
pnpm run test:e2e -- e2e/trunk.spec.ts

cd /d/Code/AideanBotHot
grep -rc "正在思考" apps/web/components/chat/ || echo "0（期望）"
grep -rc "思考中" apps/web/components/chat/
grep -rn "回答生成中断" apps/web --include=*.ts --include=*.tsx | grep -v node_modules || echo "0（期望）"
```

## 8. 证据路径

`docs/06_validation/evidence/EVD-V24-69/`（含：三串的 grep 前后读数、stop 的 vitest 输出、trunk 42 条读数）

## 9. 允许修改

- `apps/web/lib/chat/copy.ts`（新增）
- `apps/web/components/chat/**`
- `apps/web/app/chat/page.tsx`
- `apps/web/lib/api/ask.ts`
- `apps/web/tests/ask-sse-degraded.spec.ts`、`apps/web/tests/r061-sse-ask.spec.ts`
- `apps/web/e2e/trunk.spec.ts`
- `docs/06_validation/evidence/EVD-V24-69/**`

## 10. 禁止修改

- `apps/web/middleware.ts`（D-V23-15：落点不改）
- `apps/web/components/AuthGate.tsx`、`apps/web/e2e/auth-gate.spec.ts`（mock 档 AuthGate 契约）
- `apps/web/lib/api/errors.ts` 的文案映射表（既有映射不动，本卡只改 `/chat` 兜底与流中断两处）
- `packages/contracts/**`、`apps/api/**`、`scripts/e2e/**`
- `docs/任务规划V0.12.0/contracts/**`

## 11. 依赖与阻塞

- Depends on：STEP-70（契约原字是断言依据；70 未落地时本卡引用的是旧文字）
- Blocks：STEP-60（60 的用例断言这三串）
- 阻塞条件：`trunk.spec.ts` 或 `auth-gate.spec.ts` 任一条红且原因不是常量导入 ⇒ 停手（说明改动误伤了 mock 档契约）

## 12. 建议执行档位

opus。理由：改的是状态机边界（`stop` 与 `reset` 的语义分界），且跨组件契约；`stop` 写错会把「停止」变成「清空」。

## 13. 升级条件

- 出现「`stop` 之后该不该给重试入口」的判断分歧 ⇒ 升级 fable（这是产品交互取舍）
- 42 条 mock e2e 中有任一条因本卡变红且不是常量导入问题 ⇒ 升级 opus review

## 14. 预估规模

中，≈0.8 人日，大于 2 小时。

## 15. 熔断

同一判据 2 轮未过 ⇒ 停手，登 P 号。

## 16. 交接物

`EVD-V24-69/` 必须能证明三件事：三串的 grep 前后读数、`stop` 的行为（vitest 输出）、mock e2e 42 条未减。
