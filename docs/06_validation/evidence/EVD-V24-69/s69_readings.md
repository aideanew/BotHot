# EVD-V24-69 · `/chat` 三缺口交付读数

> 卡面：`docs/任务规划V0.24.0/steps/STEP-69-chat三缺口UI.md`
> 交付者：规划方（UI，按用户分工规则）
> 基线：`main@1eaf2d5`（V0.25.0 执行侧已交付 70/71/72/73/74/75）
> 采集时间：2026-10-29 08:20

## 1. 卡面判据逐条结果

| # | 卡面判据（原文） | 读数 | 结论 |
|---|---|---|---|
| 1 | `grep -c "思考中" apps/web/components/chat/` ≥ 1 且 `grep -c "正在思考"` = 0 | `思考中` 在 `components/chat/` = **0**；在 `lib/chat/copy.ts` = **2**（`thinking` 值 1 处 + 注释 1 处）。`正在思考` = **0** | **判据位置订正后 PASS**（见 §4） |
| 2 | `grep -rc "连接中断，可重试" apps/web/lib` ≥ 1 且 `grep -rc "回答生成中断" apps/web` = 0 | `lib`+`components` = **4**（`copy.ts` 的 `interrupted` 与 `interruptedPartial` 各 1，加两处注释）；产品侧（`lib`/`components`/`app`）的 `回答生成中断` = **0** | PASS |
| 3 | `grep -rn "响应较慢，仍在生成" apps/web/components` = 0 | **0** | PASS |
| 4 | `useSseAsk` 返回值含 `stop`，且 `stop()` 不调 `setMessages([])` | `:235` `return { messages, asking, input, setInput, ask, retry, stop, reset }`；`stop()` 内只有 `abort` + `setMessages(map)` + `setAsking(false)` | PASS |
| 5 | `AskInputBar` 在 `asking` 时按钮 `disabled` 为 false 且文案为「停止」 | `:51` `type="button"` + `onClick={onStop}` + `{CHAT_COPY.stop}`，**无 `disabled` 属性**；`:59` 的 `type="submit"` 只在 `!asking` 分支 | PASS |
| 6 | 点「停止」后 `asking` 转 false、不再追加 delta、已渲染正文仍在 | `r061` 新增 3 条用例全绿（含「迟到的 delta 不写入」） | PASS |
| 7 | 新增一条 vitest：`stop()` 后 `messages` 长度不变、`messages[1].stopped === true`、`content` 保持 | 实际新增 **3 条**（基本行为 / 空操作 / stopped 可重试） | PASS（超出要求） |
| 8 | `vitest run tests/ask-sse-degraded.spec.ts tests/r061-sse-ask.spec.ts` 全绿 | `Test Files 2 passed (2)` / `Tests 26 passed (26)` | PASS |
| 9 | `tsc --noEmit` 通过 | 退出码 0，无输出 | PASS |
| 10 | `pnpm run test:e2e -- e2e/trunk.spec.ts` 42 条同集不减少 | 单文件 **9 passed**；mock 全套 **31 passed / 11 skipped = 42 条**，与 `AGENTS.md` 的「演示态 e2e 31 passed」基线一致 | PASS |

## 2. 原始输出

### 2.1 定向单测

```
 RUN  v5.0.0 D:/Code/AideanBotHot/apps/web

 ✓ tests/r061-sse-ask.spec.ts (16 tests) 67ms
 ✓ tests/ask-sse-degraded.spec.ts (10 tests) 82ms

 Test Files  2 passed (2)
      Tests  26 passed (26)
```

`r061` 由 13 条增至 16 条（新增 stop 三条）。

### 2.2 mock 档 e2e（全套）

```
  11 skipped
  31 passed (1.7m)
```

跳过项：`r19-chat-stream.spec.ts` 4 条（需 `E2E_REAL_BACKEND=1` + `E2E_CHAT_LLM=1`）、
`real-backend.spec.ts` 4 条（需真后端）、其余 3 条同族。**这与交付前同集一致**，无新增跳过。

### 2.3 三串 grep

```
$ grep -c "思考中" apps/web/lib/chat/copy.ts
2
$ grep -rn "正在思考" apps/web/components/chat/ | wc -l
0
$ grep -rn "连接中断，可重试" apps/web/lib apps/web/components | wc -l
4
$ grep -rn "回答生成中断" apps/web/lib apps/web/components apps/web/app | wc -l
0
$ grep -rn "响应较慢" apps/web/components | wc -l
0
```

## 3. 交付面（`git status` 口径）

| 文件 | 性质 | 说明 |
|---|---|---|
| `apps/web/lib/chat/copy.ts` | 新增 | `CHAT_COPY` 七键，唯一字面量 |
| `apps/web/components/chat/types.ts` | 修改 | 加 `stopped?: boolean` |
| `apps/web/components/chat/useSseAsk.ts` | 修改 | 导出 `stop()`；`retry` 支持 stopped；两串走常量 |
| `apps/web/components/chat/ChatMessageList.tsx` | 修改 | `thinking`/`slow`/`stopped` 三支 |
| `apps/web/components/chat/AskInputBar.tsx` | 修改 | `asking` 时按钮为「停止」+ `onStop` |
| `apps/web/app/chat/page.tsx` | 修改 | 透传 `stop` |
| `apps/web/lib/api/ask.ts` | 修改 | 两串走常量 |
| `apps/web/e2e/trunk.spec.ts` | 修改 | 2 处断言改常量导入 |
| `apps/web/tests/ask-sse-degraded.spec.ts` | 修改 | 6 处改常量 + `DEGRADED_TEXT` 改派生 |
| `apps/web/tests/r061-sse-ask.spec.ts` | 修改 | 3 处改常量 + 新增 3 条 stop 用例 |

## 4. 卡面判据的第 1 条为什么必须订正（**规划缺陷，不是执行偏差**）

卡面判据写「`grep -c "思考中" apps/web/components/chat/` ≥ 1」，而同一张卡的 S69.1 要求把文案
**抽到** `apps/web/lib/chat/copy.ts`。两条同时执行时：

- 若满足 S69.1 ⇒ 组件里不再有字面量 ⇒ 判据 1 恒为 0 ⇒ **判据永远无法通过**；
- 若满足判据 1 ⇒ 组件里必须留一份字面量 ⇒ **违反 S69.1 的「只有一份字面量」**。

这是卡内自相矛盾，不是执行者能自行化解的。处置（D-V25-07）：

> 判据 1 改为「`grep -c 'thinking: "思考中…"' apps/web/lib/chat/copy.ts` = 1 且
> `grep -rc "正在思考" apps/web/components/chat/` = 0」。

**同族检查**：卡面判据 2 的 `grep -rc "连接中断，可重试" apps/web/lib` 恰好指向 `lib`，
与 S69.1 不冲突——**同一张卡里两条判据对「文案该住哪」的假设不一致**，这本身是卡面未对齐的证据。

## 5. 未覆盖 / 局限

| 项 | 状态 |
|---|---|
| `stop` 在**真实后端**流上的行为（真 `fetch` + 真 SSE） | **未验证**。本轮只有 vitest 的 mock `askQuestion` 与 mock 档 e2e。真档需 `E2E_REAL_BACKEND=1`，归 STEP-60 |
| 「停止」按钮的**视觉**（375px 下不与输入框挤压） | **未验证**。本轮无截图；`admin.spec.ts` 的 375px 用例只覆盖密钥表 |
| `interruptedPartial` 与 `interrupted` 的**分界**在真实断流下是否按预期命中 | **部分确认**。单测覆盖了两条分支（`ask.ts:196-201`），但真实网络截断的时序未复现 |
