---
id: REQ-F-005
type: requirement
title: RAG 知识问答
status: active
owner: product
实现度: 已实现（命题范围：`/chat` 契约五态，STEP-62 现读 2026-10-29）：真后端端到端 `apps/web/e2e/r19-chat-stream.spec.ts` 五态已在 CI 真跑通过——run `40808385199` 步 11 五条 `✓` / `5 passed (2.8s)`，步 12 守卫 `ok=5 skipped=0 failed=0`（读数见 `docs/06_validation/evidence/EVD-V24-60/s60_readings.md` §6.2）；组件层 X-6 的 35 passed（EVD-V21-51）不变。未覆盖面见下节，原「真后端端到端仍未测」一句作废
验收锚:
  - apps/api/tests/test_chat_sse.py
  - apps/api/tests/test_intent.py
  - apps/api/tests/test_reranker.py
  - apps/api/tests/test_resolver.py
  - apps/api/tests/test_langbot.py
  - apps/api/tests/test_kb_resolve_retry.py
  - apps/web/tests/ask-sse.spec.ts
  - apps/web/tests/r061-sse-ask.spec.ts
  - apps/web/e2e/r19-chat-stream.spec.ts
最后核验 commit: c687a33（2026-10-22，STEP-19 收口）；实现度于 2026-10-29 STEP-62 按 run `40808385199` 重判
---

# REQ-F-005 RAG 知识问答

## 需求条目

- SSE 流式问答
- 多空间会话路由
- 检索重排（Reranker 可选）
- **验收**：问答流式响应正常，命中知识库

## 实现度判据

| 判据 | 出处与原判词 |
|---|---|
| 后端 SSE / 会话路由 / 重排在案 | `docs/06_validation/evidence/EVD-V3-19/verdicts.md` 对 F-005 判「**部分确认**（后端在案 / 前端证据不足）」 |
| 前端流式（打字机、中断保留已渲染内容） | `apps/web/tests/ask-sse.spec.ts` + `r061-sse-ask.spec.ts` 组件级 35 passed（EVD-V21-51） |
| 真后端端到端五态 | STEP-60 交付、run `40808385199` 真跑：五条 `✓`，守卫步 `ok=5 skipped=0 failed=0`（`docs/06_validation/evidence/EVD-V24-60/s60_readings.md` §6.2）。原判词「`r19-chat-stream.spec.ts` 属真后端档，本机与 mock 档都不跑它」仍是事实，但 CI 的 `e2e-real` job 就是那个档——它跑了 |

## 命题范围与未覆盖面（STEP-62 重写，原节名「为什么不能升格成「已实现」」已作废）

升格的前提是被 STEP-19 记为「未执行过」的那条用例真的执行了。它在 `2026-10-29` 的五次 `e2e-real`
实跑中跑过（`8b695ce` / `de65373` / `1eaf2d5` / `ca9ba70` / `d6d67fc` 各一次，其中 `ca9ba70` 那次红在
① 用例自身——提问正文复述了占位文案触发严格模式，逐次读数见 `s60_readings.md` §6.3），所以判词按契约五态写成「已实现」。

**未覆盖面两条，均未写成用例、不得由本条判词外溢**：

1. `FIRST_TOKEN_SLOW_MS`（15s）的慢提示仍是 UNKNOWN——它与 success 态互斥，spec 未覆盖。
2. 「真网络错误」下的 UX：既有用例用**截断响应体**证明「无 done 帧 ⇒ `interruptedPartial` + 正文保留」，
   不能代表断网；后者走 `useSseAsk` 的 catch 分支会清空 `content`（读数位置见 `s60_readings.md` §8 第 2 条）。

另：`initial` / `forbidden` 两态在 `/chat` 无 DOM 出口（探针读数 `docs/06_validation/evidence/EVD-V22-60/s60_0_probe_readings.md`），
契约五态指的是 `/chat` 视图实际有的五态，不是八态全集。

后端侧不便：`test_chat_sse.py` 里有 2 条真实冒烟依赖本机/LangBot 可达，在 CI 上属那 6 条 skip 的一部分
（skip 门 `total_skipped=6 baseline=6` 之上不再增长）；这不是本条的「已实现」判据面。

