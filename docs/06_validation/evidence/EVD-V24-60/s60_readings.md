# EVD-V24-60 · `/chat` 五态真后端验收通道（STEP-60 交付读数）

> 卡面：`docs/任务规划V0.22.0/steps/STEP-60-聊天流式八态.md`（第 1–16 格）
>      + `docs/任务规划V0.24.0/steps/STEP-继承卡增量-V0.24.md` §1（重写与 §1.4 八条验收）
>      + `docs/任务规划V0.25.0/steps/STEP-60-订正增量.md`（三处订正，冲突时以它为准）
> 派工：`docs/任务规划V0.25.0/06-下一批下发指令.md` §2
> 基线：`main@9b0a037`（STEP-68 交付头）
> 采集：2026-10-29 09:2x–10:0x 本机（win32 / git-bash / node 24.18.0 / playwright 1.63.0 / vitest 5.0.0）

## 1. 交付面（只动了允许改的三处）

| 文件 | 改动 |
|---|---|
| `apps/web/e2e/r19-chat-stream.spec.ts` | 重写：删 8 值数组与 ④ 自指用例；头注两句过期判词改写；运行时读冻结稿取 5 键并断言 `=== 5`；5 条用例 |
| `.github/workflows/ci.yml` | `Start real stack` 加 `--with-fake-llm --with-fake-langbot`；新增 r19 步（带 4 个 env）+ 「断言不是 skipped」步，排在 admin 之前 |
| `docs/06_validation/evidence/EVD-V24-60/**` | 本目录 |

零改动：`apps/web/components/**`、`apps/web/lib/**`（只 import `CHAT_COPY`）、`apps/web/middleware.ts`、
`apps/api/**`、`packages/contracts/**`、`scripts/e2e/**`。

## 2. §1.4 八条验收逐条

| # | 判据（原文） | 读数 | 结论 |
|---|---|---|---|
| 1 | `grep -c 'every(.*=== "未测")'` = 0 | 现读 **0**（④ 与 `UX_STATES` 数组整条删除） | PASS |
| 2 | `grep -c 'toHaveLength(8)'` = 0 | 现读 **0** | PASS |
| 3 | `CHAT_STATES.length === 5` 的断言在文件内 | `if (CHAT_STATES.length !== 5) throw …`（模块加载即判，不靠某条用例） | PASS |
| 4 | 5 条用例各有明确 passed/failed/skipped，没有「没跑却算通过」 | 见 §4（本机读不到真栈，5 条以 @ci 为准；守卫步把「整片 skip」变成会红的判据） | PASS（结构面）/ 读数待 §6 |
| 5 | `unauthenticated` 断言 URL，不只断言文案 | `expect.poll(() => new URL(page.url()).pathname).toBe("/")`（D-V23-14） | PASS |
| 6 | `e2e-real` 里 r19 步在 admin 步之前 | PyYAML 现读：r19 idx=**8** < 守卫 idx=**9** < admin idx=**10**（共 14 步） | PASS |
| 7 | `frontend` 的 `E2E (mock UI)` 仍 42 passed | **原字与现读形状不符**：那一跑是 `31 ✓ / 11 -` = 42 **条**，passed 从来不是 42。本卡后 r19 自身 4→5 条 ⇒ 43 条（`s60_playwright_list.txt` 的 mock `--list` 读 43，**实测**）；届时 `31 ✓ / 12 -` 里的 `12 -` 是**推算**（r19 在 mock 档整片 skip，本卡只加了 1 条用例），通过数 31 一条未变 | 按形状 PASS，按原字不可达（见 §5.3） |
| 8 | `backend` 计数不变（2502 passed / 6 skipped） | 本卡零后端字节（`git diff --stat` 无 `apps/api/**`）⇒ 计数不可能变；`2502 / 6` 这个**数**在本包内无存证，出处是包外的 `EVD-V23-64/66/67` 与 `EVD-V24-72/73`，本轮 CI 的实际读数以 §6 回填为准 | 按「零改动面」PASS（数字不在包内，标明出处） |

## 3. 五态与供给（实现取舍）

| 态 | 判据 | 供给/手段 | 为什么不是卡面原字 |
|---|---|---|---|
| loading | `CHAT_COPY.thinking` 可见（5s）+ 「停止」可点 + 点后 `CHAT_COPY.stopped` 可见 | `page.route` 把本次请求压 2s 后再 `continue()` | 真链路首 delta 几十毫秒，不压窗口抓不稳（§1.5 允许的「拉长窗口」同族做法，且**不是** slow 模式） |
| success | `假 LLM 首段` + `来源文章` + `来源引擎：` | 真后端 + 假 LLM + 假 LangBot + 种子空间 | 同原字 |
| error | `CHAT_COPY.interruptedPartial` 可见 + 首段正文仍在 + 「重试」可见 | `route.fetch()` 读真响应 → 截断在首个 delta 后 → `fulfill` 回放（回放时剥 `content-encoding`/长度头并钉回 `text/event-stream`，见 §5.5） | 原字的 `FAKE_LLM_MODE=abort` 探针实测是**干净 EOF**（§2 探针一），后端会照发 `done`，到不了 error 态 |
| unauthenticated | `page.url()` 落回 `/` + 不出现 `10004/权限不足` | 清 cookie → `goto("/chat")` | 同原字（D-V23-14） |
| degraded | `CHAT_COPY.degraded` 可见 + 「重试」可见 | `context.setOffline(true)` 后提问 ⇒ fetch 当场失败 ⇒ 50002 ∈ `DEGRADED_CODES` | 原字的 `FAKE_LLM_MODE=slow` 是**进程级**开关，与 success 在同一 job 互斥；且 16s 首帧与后端 15s 读超时同点竞争，读数不确定 |

探针读数与三条候选的取舍见 `s60_0_probe_readings.md`。

## 4. 本机能取到 / 取不到的读数

本机**没有** 5547(PG)/6380(Redis)/3200/3300/3290/3291 的任何监听（`netstat -an | grep LISTENING` 零命中）⇒
`run_real_backend.sh` 的两条硬前提（迁移要 PG、会话种子要 Redis）都不成立 ⇒
**五态的行为读数本机取不到**，只能取静态读数：

| 读数 | 原样输出 | 文件 |
|---|---|---|
| `--project=real … --list` = 5 条（用例名逐条） | `Total: 5 tests in 1 file` | `s60_playwright_list.txt` |
| mock 档 `--list` = 43 条（r19 由 4 条变 5 条） | `Total: 43 tests in 7 files` | 同上 |
| `tsc --noEmit` | 退出码 0，无输出 | 见 §5 |
| `next lint` | `✔ No ESLint warnings or errors` | 见 §5 |
| `vitest run` | stdout 只有 `Test Files 57 passed (57)`（**`Tests` 汇总行没落进捕获**）；条数取同一跑的 JUnit：`<testsuites … tests="452" failures="0" …>` | `s60_vitest.txt` |

`E2E_REAL_BACKEND=1` 时 `--list` 能列出 5 条，说明**模块级**的冻结稿读取、`CHAT_COPY` 解析、
`real` project 的 `globalSetup` 接线在本机都成立；行为层留给 CI 的 `e2e-real`。

## 5. 三处订正与一处偏离（都来自读数，不是偏好）

### 5.1 订正一：守卫步的符号不是 `ok`，是 `✓`

本轮最初按「非 TTY 下 list reporter 打 `ok`」写守卫步（`grep -cE '^  ok +[0-9]+ '`）。
取样改到 **CI 实跑日志**（run `40692846396` / head `299b220` 的 `E2E (mock UI)` 段）后才发现：
CI 上打的是 `  ✓  N …` / `  -   N …`，`ok` = 0 行。

⇒ 照 `ok` 写，守卫步对**一次真跑**也会判红。现读样本：`31 ✓ / 11 - / 0 ✘`（`s60_ci_sample_mock_e2e.txt`），
正则改用 `^  ✓ +[0-9]+ ` / `^  - +[0-9]+ ` / `^  ✘ +[0-9]+ `（`+` 覆盖 `✓   1` 与 `✓  10`、
`-   5` 与 `-  26` 两种宽度）。样本文件里的原日志行号（`758:` …）已剥掉——不剥的话三条正则在
**那份转存**上全数命中 0，样本就成了「看起来能数、实际数不出来」的假存证。
原先那条「非 TTY 打 ok」的读数来自 win32/git-bash 的管道，不是 CI 的形状——同族病史见 P-104。

### 5.2 偏离：候选甲的第二句（`skipped` = 0）不采用

订正增量推荐甲 = `grep -c "✓"` ≥ 1 且 `grep -c "skipped"` = 0。第二句与增量 **§1.4④** 打架：
那一条把「明确 passed / failed / **skipped**」并列为合格读数；§1.2 也允许取不到读数的那条标 UNKNOWN
（Playwright 里 UNKNOWN 的唯一机械载体就是 `test.skip`）。守卫步落成三条：`✓ ≥ 1`、`✘ = 0`、`✓ + - == 5`。
后两条都比甲严（甲既不查红、也不查「用例凭空消失」），且不禁止 §1.4④ 明确列为合格读数的 skip。

### 5.3 订正二：`E2E (mock UI)` 的「42 passed」原字不可达

见 §2 第 7 行。通过数 31 未变；总条数 42→43 是本卡自己的 5 条用例（全部 `test.skip`）。

### 5.4 订正三：`r19` 头注两句话

| 原句 | 现读 | 处置 |
|---|---|---|
| 「八态取自 `State` 枚举（8 值）」 | 冻结稿 `/chat` 只列 5 键 | 改为「五态取自 `x-core-views[/chat 流式问答].states` 键集；8 值是全局词表」 |
| 「该契约文件在 V0.13.0 及以后没有再出现」 | 文件存在，且 `apps/api/tests/test_ux_states_contract.py` 正在引用 | 整句删除 |

### 5.5 手段②的头部处理（提交前复核抓到的第五处，不是卡的订正）

截断回放原先写的是 `route.fulfill({ response, body })`，靠 `response` 复用原响应头。复核指出一条
**会让 ③ 恒红**的链路：`/api/v1/*` 是 next 的 rewrite 代理（`apps/web/next.config.mjs:14-15`），
next 对 SSE 也套压缩 ⇒ 头里有 `content-encoding: gzip`；而 `route.fetch()` 交出的是**已解压**正文、
`fulfill` 又原样复用那份头 ⇒ 明文配 gzip 头，Chromium 解码失败、`fetch` 当场拒绝 ⇒ 界面走
`useSseAsk` 的 catch（`content: ""` + degraded），`interruptedPartial` 永远等不到。

现改为：删掉 `content-encoding` / `content-length` / `transfer-encoding` 三头，`content-type` 显式钉回
`text/event-stream`，`status` 显式取 `response.status()`。这条**不是**在修复真实产品链路——产品链路里
浏览器自己解 gzip，没有问题；它只修「回放一份已被解压的正文」这个测试侧动作的头部一致性。
本机无法验证这一点（起不了真栈）⇒ 由 §6 的读数裁决。**裁决结果：成立** —— 第 1 跑里 ③ 是 `✓`，
说明摘掉那三个头之后浏览器确实把回放正文当成 SSE 读完了。

## 6. @ci 读数

### 6.1 第 1 跑：head `ca9ba70`，run `40806609514`（2026-10-29T02:29Z 起）

原始切片在 `s60_ci_run_40806609514_log.txt`（zip 内 `e2e-real/` 三段原样，未改写）。

| 项 | 读数 |
|---|---|
| head | `ca9ba70`（推送后 `git ls-remote origin refs/heads/main` 独立复核一致） |
| `CI` run 结论 | **success** —— 但 `e2e-real` 自己是 **failure**，被 `continue-on-error: true` 掩成绿（这正是 STEP-62 要摘它的理由，见 §6.3） |
| `Security` / `CI-Windows` | `Security` success；`CI-Windows` 见 §6.2 |
| `Start real stack` | 成功：`端口检查通过（本次要用：3200 3291 3290 3300）`；`② 假 LLM 上游 :3290` / `②b 假 LangBot 上游 :3291` 两行齐；health 载荷 `deps` 三项 `postgres/redis/langbot = ok`；`⑤b` 两轮 counts `spaces=1 sources=1 assets=1 documents=1` |
| `① loading` | **✘ 647ms** —— 见下方根因 |
| `② success` | **✓ 749ms** |
| `③ error` | **✓ 617ms** —— 手段②（截断 + 摘 `content-encoding`）在真链路上成立，§5.5 的怀疑解除 |
| `④ unauthenticated` | **✓ 425ms** |
| `⑤ degraded` | **✓ 404ms** |
| 合计 | `1 failed / 4 passed (8.2s)` |
| 守卫步输出 | **无读数**：该步被 skipped（上一步已失败）。step 结论表：11 `E2E … r19` failure → 12 `断言 r19 不是 skipped` skipped → 13 admin skipped → 14 Reporter 自检 skipped → 15 Upload success |
| `Stop stack` | 成功：`stopped fake_llm / fake_langbot / backend / frontend` 四行齐，四个端口 `端口终检 … 空闲；占用者读数：(空)` |

**① 红的根因是这一条用例自己**，不是产品、不是供给：提问正文写的是
`"R19 loading：先别急着回答，我要看「思考中…」这一态"`，把占位文案原样复述进了用户气泡，于是
`getByText(CHAT_COPY.thinking)` 在严格模式下同时命中两条：

```
Error: strict mode violation: getByText('思考中…') resolved to 2 elements:
    1) <div class="…bg-brand-500…">R19 loading：先别急着回答，我要看「思考中…」这一态</div>
    2) <p class="text-base text-neutral-400">思考中…</p> aka getByText('思考中…', { exact: true })
```

改法（最小）：提问正文换成不复述文案的 `"R19 loading：先别急着回答，我要看等待这一态"`，
并给占位符断言加 `exact: true` —— 两处都只动这一条用例，不动产品、不动其余四条。

### 6.2 第 2 跑（待回填）

| 项 | 读数 |
|---|---|
| head | 待填 |
| `e2e-real` 结论 / 五条逐条 | 待填 |
| 守卫步输出（`ok=? skipped=? failed=?`） | 待填 |
| `backend` / `frontend` / `CI-Windows` | 待填 |

### 6.3 顺带取到的两个事实（给 STEP-62 用）

1. `e2e-real` 最近三次**真执行**（`8b695ce` / `de65373` / `1eaf2d5`）全 success；`408aae2` 与 `9b0a037`
   两次是 skipped（上游 job 红），不算执行读数。本卡这一跑是第四次执行、且是第一次 failure ⇒
   「连续三次绿」的窗口在本次被打破，`continue-on-error` 的摘除判据要按 STEP-62 卡面②重算。
2. `CI` 的 run 结论在 `continue-on-error: true` 下**掩盖了 e2e-real 的 failure**（本跑即例），
   这是「绿着不算绿」的又一实例。

## 7. 同批附带：主干红的来源与修法（不属于本卡允许面）

`9b0a037` 的 CI 红在 `frontend` 的 `Unit tests (vitest)`。下面这段是**重建**（取自那次 CI 日志的
`Unit tests (vitest)` 段；本机无法重放该 CI 输出，故不声称是本包内的原始存证）：

```
FAIL tests/ask-sse.spec.ts > … > meta 后断流（无内容无 done）→ 标记 50002 请重试
AssertionError: expected '连接中断，可重试' to contain '重新提问'
Tests  1 failed | 451 passed (452)
```

可机械复核的那一半在 git 里，不依赖这段转述：`git show HEAD:apps/web/tests/ask-sse.spec.ts`
的该断言原文是 `toContain("重新提问")`，现值是 `toContain(CHAT_COPY.interrupted)`（`s60_vitest.txt`
记本机复跑）。

根因：STEP-69（`8614365`）把 `lib/api/ask.ts` 的两串文案换成 `CHAT_COPY.interrupted` /
`interruptedPartial`，但 `tests/ask-sse.spec.ts` 那条仍钉旧字面量「重新提问」。
修法：该断言改读 `CHAT_COPY.interrupted`（与 P-146「同一句散在多处」同族的**唯一真源**做法）。
本机复跑：`Test Files 57 passed (57)` / JUnit `tests="452" failures="0"`（`s60_vitest.txt`），修后连跑 6 次全绿；
本轮更早有一次 `1 failed | 56 passed (57)` 的读数**未能复现**（失败用例名被输出过滤掉了），
按「修后 6 连绿 + CI 只红这一条」判为同一条红，不另开 P 号。
`apps/web/tests/**` 不在 STEP-60 的允许面内 ⇒ 这一处**单独成提交**，并在台账登记为「修主干红」，不算本卡交付物。

## 8. 局限

- 五态的行为读数只能在 CI 取（本机无 PG/Redis）。§6.1 已回填第 1 跑（②③④⑤ 绿、① 红在用例自身），
  §6.2 的第 2 跑未回填前，本卡对外主张「四条已真跑通过 + ① 已改用例待复跑」。
- 截断手段（手段②）改的是**响应体长度**，不是链路：它能证明「无 done 帧 ⇒ interruptedPartial + 正文保留」，
  不能证明「真网络错误下的 UX」——后者走 `useSseAsk` 的 catch，会把 `content` 清空（读数在
  `useSseAsk.ts:135-140`），本卡未把它写成用例。
- `FIRST_TOKEN_SLOW_MS=15s` 的 slow 提示本卡未覆盖（同上：与 success 互斥），仍是 UNKNOWN。
