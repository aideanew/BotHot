# EVD-V24-60 · S60.0 探针读数（供给与判据的可达性）

> 卡面：`docs/任务规划V0.22.0/steps/STEP-60-聊天流式八态.md` + `docs/任务规划V0.24.0/steps/STEP-继承卡增量-V0.24.md` §1
>      + `docs/任务规划V0.25.0/steps/STEP-60-订正增量.md`（三处订正）
> 采集：2026-10-29 09:2x–09:5x 本机（win32 / git-bash / node 24.18.0 / playwright 1.63.0）
> 探针本体在仓外（`%TEMP%\s60\`），本目录只留原始输出，不留可执行脚本（沿用 EVD-V24-68 的收纳口径）。

## 1. 为什么要先做探针

卡面 five-state 的**供给**与**判据**两条都可能落空：
- 供给：卡面 error 行写 `FAKE_LLM_MODE=abort`、degraded 行写 `FAKE_LLM_MODE=slow`——两个都是**进程级**开关，
  而 CI 一个 job 只起一个 `:3290`。
- 判据：订正增量候选甲给的读法（`grep -c "✓"`）与增量 §1.4④「skipped 也算合格读数」互相打架。

探针要回答的是「这三处到底能不能照字面实现」，而不是「我觉得行」。

## 2. 探针一：`FAKE_LLM_MODE=abort` 是干净 EOF，不是断流

原始输出：`s60_0_fake_llm_probe.txt`

```
normal: 8 lines, exception=None
abort : 2 lines, exception=None
```

- `abort` 模式在客户端（httpx `iter_lines()`）眼里就是**流自然结束**：没有 `ReadError`、没有 `RemoteProtocolError`。
- 后端 `apps/api/app/api/v1/chat.py` 的生成器 `_llm_stream_delta` 只在**超时/4xx**时抛 `DependencyUnavailableError`/
  `LangbotApiError`；上游干净 EOF 只是 `async for` 结束 ⇒ `_event_stream` 照发 `done` 帧
  ⇒ 前端拿到的是一条「内容较短的成功」，**证明不了 error 态**。
- 结论：卡面 error 行的供给照字面实现**不成立**，本卡改用传输层截断（见 §4）。

## 3. 探针二：CDP 限速 + 断网拉不出「读到一半」的窗口

原始输出：`s60_0_cdp_probe.txt`（两次独立执行，读数一致）

```
① 限速 150B/s：总时长 ~10000ms，1 个 chunk（服务端 10 段）
   chunk[1] @10003ms  "data: {\"n\":1,…"
② 断网前：state=running chunks=0
② 断网后：state=done chunks=1 end=clean-done
② 已收正文长度 586（断网后未清空 ⇒ 前端能决定是否保留）
```

- 服务端每 50ms 写一段、共 10 段（586 字节），在 `downloadThroughput=150`（B/s）下**并没有逐段滴出来**：
  渲染进程侧只读到 **1 个 chunk**，整段一起到达。
- 在「已收到 0 段」时切 offline，4 秒后读到的仍是 `end=clean-done`：**已缓冲的响应体不会被 offline 掐断**。
  ⇒ 「首段可见 → 再断网 → 读到一半失败」这条路在本仓不可复现；照着写只会得到一个与断网无关的超时红。
- 结论：手段改成「读走真后端完整响应 → 在首个 delta 之后截断 → 回放」，故障点从"链路"下移到"响应体长度"，
  仍然只丢 done 及其后的帧，字节全部来自真后端。

## 4. 三个候选手段的取舍

| 候选 | 读到的 error 态 | 代价/风险 | 采否 |
|---|---|---|---|
| A `FAKE_LLM_MODE=abort` | **没有**：干净 EOF ⇒ 后端发 done | 需换进程级模式，与 success 互斥 | ✗（探针一） |
| B CDP 限速 + 断网 | **没有**：整段一次性到达，offline 掐不断已缓冲响应 | 时序敏感、不可复现 | ✗（探针二） |
| C `page.route` + `route.fetch()` + 截断在首个 delta 后 | **有**：干净 EOF、无 done ⇒ `ask.ts` 的 `interruptedPartial` | 需要一次真实请求（`route.fetch()` 就是真请求） | ✓ |
| D `context.setOffline(true)` 先断网再问 | **没有** error 态；拿到的是 degraded（50002 ∈ DEGRADED_CODES） | 无 | ✓ 用于 degraded 态 |

## 5. 探针三：list reporter 在 CI 里打的是 `✓`，不是 `ok`

原始输出：`s60_ci_sample_mock_e2e.txt`（取样：CI run `40692846396` / head `299b220` 的 `E2E (mock UI)` 段）

```
ok_n(^  ✓ +[0-9]+ ) = 31
skip_n(^  - +[0-9]+ ) = 11
fail_n(^  ✘ +[0-9]+ ) = 0
```

样本里的原样行（序号宽度不固定）：

```
  ✓   1 e2e/admin.spec.ts:147:7 › … (2.4s)
  ✓  10 e2e/auth-gate.spec.ts:39:9 › … (987ms)
  -   5 e2e/admin.spec.ts:236:9 › …
  -  26 e2e/r19-chat-stream.spec.ts:48:5 › …
```

- **订正**：本轮先前把「非 TTY 下打 `ok`」当成 CI 事实，那是在 win32/git-bash 里把输出接进管道后看到的形状
  （`✓` 没落进管道），不是 GitHub Actions 的形状。照 `ok` 写守卫步 ⇒ CI 上恒为 `ok=0` ⇒ **对一次真跑也判红**。
  取值改成上面这 42 行样本，两条正则才作数。
- `grep -c "skipped"` 不可用：那是**汇总行**（`N skipped`），只在有跳过时出现，无法区分「5 条全跑」与「只跑了 4 条」。

## 6. 订正增量候选甲的一处修改

候选甲 = `grep -c "✓"` ≥ 1 **且** `grep -c "skipped"` = 0。第二句与增量 §1.4④ 打架：那一条把
「明确 passed / failed / **skipped**」并列为合格读数，§1.2 也允许取不到读数的那条标 UNKNOWN
（Playwright 里 UNKNOWN 的唯一机械载体就是 `test.skip`；§1.5 只写「只交另外 4 条、success 标 UNKNOWN」，
没写「拿什么记」）。故本卡落成：

| 判据 | 表达 |
|---|---|
| ① 有真读数 | `✓` 行 ≥ 1 |
| ② 有红就不算过 | `✘` 行 = 0 |
| ③ 用例没有凭空消失 | `✓ + -` == 5（契约 `/chat` 5 态） |

②③ 都比甲强，且不禁止 §1.4④ 明确列为合格读数的 skip。
