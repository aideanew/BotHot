# EVD-V24-68 读数：逐视图态投影 `UX_VIEW_STATES`

- 卡面：`docs/任务规划V0.24.0/steps/STEP-68-UX逐视图投影.md`
- 派工：`docs/任务规划V0.25.0/06-下一批下发指令.md` §1
- 基线：`main@408aae2`（= 推送后的 `origin/main`，工作区干净）
- 档位：sonnet
- 执行日：2026-10-29

## 1. 先红（未改 `states.ts` 时）

`pytest_before.txt` 全文见同目录，关键读数：

```
E       AssertionError: UX_VIEW_STATES 块应恰好一条，实读 0 条 ⇒ 谁是唯一源说不清了
1 failed, 4 passed in 0.21s
```

红了的是**新加的那一条**（`test_ux_view_states_projection_equals_frozen_draft`），
原有四条仍绿——说明红的原因确实是"投影尚未存在"，不是解析器写错或锚漂。

## 2. 实现（三处，均在本卡允许面内）

| 文件 | 改动 | 判据锚 |
|---|---|---|
| `packages/contracts/src/ux/states.ts` | 末尾追加 `UX_VIEW_STATES` 对象 + `UxViewStates` 类型，并把「投影 vs 词表」口径写进头注 | `UX_STATES` 那一行**字节未动**（`git diff` 该文件只有 `+` 行，无 `-` 行） |
| `packages/contracts/src/index.ts` | 在原行之后**新增** `export type { UxViewStates } from "./ux/states";` | 原行 `export type { UxState } from "./ux/states";` 整行仍在（`test_index_ts_reexports_the_ux_state_type` 按整行匹配，合并成一行会让它红——已实测一次） |
| `apps/api/tests/test_ux_states_contract.py` | 头注补第 ⑤ 条 + 新增纯函数归一器 `_view_key` 与一条断言 | 见 §4 |

归一实现（测试文件内纯函数，不引第三方）：

```
首段（空白切分）→ 去前导 `/` → 转小写 → 去非 [a-z0-9]
⇒ `/spaces 列表 + /spaces/[id] 详情` → spaces
⇒ `NotificationBell（站内通知）`      → notificationbell
```

无别名表——别名表会变成第二个真源（D-V24-05）。

## 3. 绿读数

`pytest_after.txt`：

```
tests\test_ux_states_contract.py .....                                   [100%]
============================== 5 passed in 0.11s ==============================
```

`view_keys.txt`（六视图：冻结稿 vs 活体投影，逐键同序）：

```
spaces              7  loading, empty, success, error, forbidden, unauthenticated, degraded
hot                 5  loading, empty, success, error, degraded
chat                5  loading, success, error, unauthenticated, degraded
admin               6  unauthenticated, forbidden, empty, success, error, degraded
notificationbell    5  loading, empty, success, error, degraded
onboarding          2  success, degraded

视图键集（同序）: True
逐视图逐键同序: {'spaces': True, 'hot': True, 'chat': True, 'admin': True, 'notificationbell': True, 'onboarding': True}
视图数: 6 (期望 6)
投影 ⊆ 词表: {'spaces': True, 'hot': True, 'chat': True, 'admin': True, 'notificationbell': True, 'onboarding': True}
chat 恰为 5 键: ['loading', 'success', 'error', 'unauthenticated', 'degraded']
```

类型检查（`packages/contracts` 无本地 `node_modules`，按其 `package.json` 的
`typecheck` 语义等价执行，编译器借 `apps/web/node_modules/.bin/tsc`）：

```
tsc -p packages/contracts/tsconfig.json --noEmit   → rc=0
cd apps/web && pnpm exec tsc --noEmit              → rc=0
```

> `apps/web/tsconfig.json` 的 `paths` 把 `@bothot/contracts` 解析到
> `../../packages/contracts/src/index`（源文件，不是 `dist`）⇒ 上面第二条
> 已经把本卡的 `states.ts` / `index.ts` 改动一并类型检查过，不是只检前端。

## 4. 判据逐条（卡面 §6）

| # | 判据 | 读数 |
|---|---|---|
| 1 | `states.ts` 中 `UX_STATES` 那一行字节未变 | `grep -c '^export const UX_STATES = \['` = 1；该文件 `git diff` 无 `-` 行 |
| 2 | `UX_VIEW_STATES` 6 键，各值 ⊆ `UX_STATES` | 6/6 `True`（`view_keys.txt`）；测试内断言 |
| 3 | `chat` 恰为 5 值、不含 `initial`/`empty`/`forbidden` | 测试内等值断言 + `view_keys.txt` 打印 |
| 4 | `notificationbell` 不含被移出的那一态 | 逐键同序比对覆盖（多一个键即红），**不写该字面量**，见 §5 |
| 5 | `pytest tests/test_ux_states_contract.py -q` = 5 passed | `5 passed in 0.11s` |
| 6 | 测试文件内 `grep -c "offstate"` = 0 | `0`（grep rc=1 即零命中） |
| 7 | `tsc --noEmit`（contracts + web） | 两条均 rc=0 |
| 8 | 不改生成器、`ux` 仍不进生成器 | `test_ux_domain_is_not_half_wired_into_the_generator` 绿；本卡未碰 `scripts/gen_contracts.py` |

未跑 backend 全量——D-V22-01 单卡只跑它改到的测试，卡面 §7 也只列了定向命令。

## 5. 卡面内部矛盾与处置（登 P-161）

**矛盾**：S68.3 给的示例 docstring 里出现了两次被 STEP-70 移出的那个态名
（原句是「为什么不留 `<该态名>` 例外：例外会腐化……」），而 §6 与派工单 §1.2 的
判据 6 要求「测试文件内 `grep -c "offstate"` = **0**」。两条不可能同时成立。

**处置**：取 §6/派工单的机械判据（可复核、无解释空间），把该字面量从测试文件里全部去掉：

- 头注第 ⑤ 条只描述口径（投影 vs 词表），不点名那个态；
- 新测试的 docstring 改为「STEP-70 已把唯一那一态移到 `x-build-mode-notes`（view 对象的兄弟键，
  不在 `states` 里）」，同样不写该字面量；
- 判据 4 的语义靠**逐键同序等值**保证：冻结稿 `states` 里没有它，投影多写一个键即红。

这不是放宽判据——是两条判据冲突时取机械的那一条；语义覆盖没有减少。
规划方若要保留示例 docstring 的原字面量，需同步把判据 6 改掉（这两条都在规划方落笔权内）。

附属观察两处，一并交回（不阻塞本卡）：

1. 卡面 S68.1 只给了 `UxViewStates` 类型；本卡另在头注里说明**值** `UX_VIEW_STATES` 不得被运行时导入
   （`emitDeclarationOnly` 下导出值等于给消费侧一个运行时黑洞）。`index.ts` 只导出类型，未导出值。
2. `packages/contracts` 没有本地 `node_modules`、仓库也没有 workspace 根 ⇒ 卡面 §7 的
   `pnpm exec tsc --noEmit` 在该目录下会报 `Command "tsc" not found`（实测）。本卡用
   `apps/web/node_modules/.bin/tsc -p packages/contracts/tsconfig.json` 等价执行并记录 rc。

## 6. 完成度分析

| 维度 | 判断 | 依据 |
|---|---|---|
| 目标达成 | 100% | 6 视图投影全部落地，逐键同序相等；`chat` 5 键、`onboarding` 2 键与契约一致 |
| 判据覆盖 | 8/8 | §4 表逐条有读数，无「未测」项 |
| 先红有效性 | 是 | 红在同一条新用例、且报错文本指向"块不存在"，不是解析/锚失败 |
| 允许面 | 未越界 | 改动 3 个文件全在卡面 §9 名单内（另加卡面自身勾选，与 STEP-70 同例） |
| 证据可复核 | 是 | 三份原始读数（before/after/六视图打印）+ 本篇；一周后无需读代码即可核对「投影 == 稿」 |
| 残留 | 2 项 | §5 的两处附属观察；无阻塞项 |
| 风险 | 低 | 纯字面量 + 一条断言，无运行时代码路径；`UX_STATES` 行字节未动 |

**未覆盖项（如实记）**：本卡不验证前端是否**消费**这份投影——那是 STEP-60 的事
（`r19-chat-stream.spec.ts` 的五条用例以本卡投影为准）。本卡也不改 `UX_STATES`，
全局八态词表保持原样。
