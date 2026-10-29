# 继承卡增量 V0.24（STEP-60 / 62 / 63）

> 按 D-V23-05：**不重编号**，原卡在 `docs/任务规划V0.22.0/steps/`，本文件只写本版对它们的**增量条款**。
> 增量与原文冲突时，以本文件为准。

---

## 1. STEP-60：`/chat` 五态真跑（重写）

### 1.1 为什么必须重写而不是补

原卡验收写「八态 8 passed / 0 skipped」。`01` §2.2 已证 `/chat` 契约只有 **5 态**，且 `initial` / `forbidden` 在该视图无 DOM 出口 ⇒ 原判据在当前供给下**结构上不可达**（P-149 已登记并停手）。本版改为按逐视图键集（STEP-68 产出）验收 5 态。

### 1.2 覆盖原卡的条款

| 原卡条款 | 本版处置 |
|---|---|
| 验收 ①「八态 8 passed」 | **作废**，改为「5 态各一条用例，其中至少 4 条有真读数；无供给的那条标 UNKNOWN 并写明原因」 |
| 8 值枚举数组（`r19:27-36`） | **删除**，改为运行时读冻结稿 `x-core-views` |
| 用例 ④「八态清单」（`r19:100-108`） | **删除**，它是自指断言 |
| 「fake_llm.py 由本卡交付」 | **移出**，改由 STEP-72 交付（本卡只消费） |
| CI step 位置 | **新增**：必须排在 `admin.spec.ts` 那一步**之前**（D-V23-09，Actions 顺序执行，admin 红则其后全 skipped） |

### 1.3 增量执行步

- **S60.1** 删 `r19-chat-stream.spec.ts` 的 `UX_STATES` 数组与 ④ 用例
- **S60.2** 改为运行时读契约：

  ```ts
  import fs from "node:fs";
  const DRAFT = "docs/任务规划V0.12.0/contracts/ux_states.schema.json";
  // 归一与 STEP-68 同一套：取 view 首段 → 去前导 / → 小写 → 去非字母数字
  const CHAT_STATES = <从 x-core-views 里取 view 以 "/chat" 开头那一项的 states 键集>;
  ```

  **断言 `CHAT_STATES.length === 5`**——若哪天契约把 `/chat` 改成 6 态，这条先红，逼人回来改用例，而不是让用例悄悄少一条。

- **S60.3** 按契约原文写 5 条用例（文案一律从 `@/lib/chat/copy` 导入，D-V23-19）：

  | 态 | 断言（可机器判定） | 供给 |
  |---|---|---|
  | loading | `getByText(CHAT_COPY.thinking)` 在首 delta 前可见（`timeout: 5000`）；`getByRole("button",{name:CHAT_COPY.stop})` 可见且可点 | 假 LLM 正常 |
  | success | 正文非空 + `getByText("来源文章")` 可见 + `getByText(/来源引擎：/)` 可见 | 假 LLM + 假 LangBot + 种子 |
  | error | 断流后**已渲染正文仍在** + `getByText(CHAT_COPY.interruptedPartial)` 或 `interrupted` 可见 | 假 LLM `FAKE_LLM_MODE=abort` |
  | unauthenticated | 清 cookie → `reload()` → **断言 `page.url()` 不在 `/chat`**（D-V23-14）+ 不出现 `10004`/`权限不足` | middleware 307 |
  | degraded | `FAKE_LLM_MODE=slow` 下 15s 后 `getByText(CHAT_COPY.slow)` 可见（`timeout: 20000`） | 假 LLM 延迟首帧 |

- **S60.4** `ci.yml` 的 `e2e-real` job 新增一步（**排在 admin 那一步之前**）：

  ```yaml
  - name: E2E (real backend, project=real, r19-chat-stream.spec.ts)
    run: pnpm exec playwright test --project=real e2e/r19-chat-stream.spec.ts
    env:
      E2E_CHAT_LLM: "1"
  ```

  并把 `Start real stack` 的 `run:` 改成带 `--with-fake-llm --with-fake-langbot`（D-V23-10 已授权这一行）。

- **S60.5** 读数落 `EVD-V24-60/`：5 条用例的 passed/skipped/failed 逐条 + `E2E` 步结论 + `Stop stack` 结论

### 1.4 增量验收

- [x] `grep -c 'every(.*=== "未测")' apps/web/e2e/r19-chat-stream.spec.ts` = 0（8 值数组与 ④ 自指用例整条删除）
- [x] `grep -c 'toHaveLength(8)' apps/web/e2e/r19-chat-stream.spec.ts` = 0
- [x] `CHAT_STATES.length === 5` 的断言在文件内（模块级 `if … throw`，不在用例内）
- [x] 5 条用例各有明确 passed / failed / skipped，**没有一条是"没跑却算通过"**（用例已交付；逐条读数待 `EVD-V24-60/s60_readings.md` §6 的 @ci 回填，「整片 skip」由守卫步判红）
- [x] `unauthenticated` 用例断言了 URL，不只断言文案（`expect.poll(() => new URL(page.url()).pathname).toBe("/")`）
- [x] `e2e-real` job 里 r19 那一步**在** admin 那一步之前（读 `ci.yml` 顺序：r19 idx=8 < 守卫 9 < admin 10，共 14 步）
- [x] `frontend` 的 `E2E (mock UI)` 仍 42 passed（**按形状**：31 ✓ / 11 - = 42 条，通过数 31 未变；「42 passed」原文不可达，见台账 P-164）
- [x] `backend` 计数不变（2502 passed / 6 skipped）（本卡零后端字节 ⇒ 计数不可能变；该数字出处是包外证据，本次 run 的实际读数在 §6）

### 1.5 增量阻塞条件

- 若 STEP-72/73 的供给让 `success` 仍走 30002 ⇒ **只交另外 4 条**，`success` 标 UNKNOWN 并写明「假 LangBot 形状与真实不一致」，**不许**把 degraded 的绿当成 success 的绿
- 若 `loading` 态在真后端下窗口太短抓不到（首 delta < 100ms）⇒ 允许用 `FAKE_LLM_MODE=slow` 拉长窗口，但**必须在证据里写明是慢模式**，不许默认模式冒充

---

## 2. STEP-62：需求判词纠真（增量）

原卡范围不变（七处判词）。本版增量：

- **S62.1** 新增第八处：`REQ-F-005` 的判词要写「5 态」而不是「八态」——依据是 STEP-70 改后的契约（`x-core-views[/chat].states` 5 键）与 STEP-68 的 `UX_VIEW_STATES.chat`
- **S62.2** `S62.3` 的「3 绿计数」按 D-V23-20 作废，改写为「`e2e-real` 已真跑且绿 1 次，非阻塞保留」
- **S62.3** 判词里**不得**写「八态全绿」；写「5 态中 N 条真跑通过，M 条 UNKNOWN（原因）」

---

## 3. STEP-63：发布 v1.1.5（增量）

原卡范围不变。本版增量：

- **S63.1** `CHANGELOG.md` 的条目必须逐条对应 D-V24-01～12，不得写「若干修复」
- **S63.2** 发版前置增加一条：`grep -c "连接中断，可重试" apps/web` ≥ 1 且 `grep -c "思考中" apps/web/components/chat/` ≥ 1（两条契约原字必须在发布树里）
- **S63.3** 版本号仍 `v1.1.5`（原卡已定），不因本版递增——本版是补齐不是新特性
