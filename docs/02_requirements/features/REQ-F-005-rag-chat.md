---
id: REQ-F-005
type: requirement
title: RAG 知识问答
status: active
owner: product
实现度: 部分：组件层已证（X-6 判词更新，2026-10-25：`ask-sse.spec.ts` + `r061-sse-ask.spec.ts` 实跑 35 passed / 0 failed——前端 SSE 消费与打字机渲染有组件级证据；真后端端到端（`e2e/r19-chat-stream.spec.ts`）仍未测，读数在 EVD-V21-51）
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
最后核验 commit: c687a33（2026-10-22，STEP-19 收口判「部分确认」）
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
| 前端流式（打字机、中断保留已渲染内容） | 同一件判词写明前端 spec 存在但「**未执行过**」；`apps/web/e2e/r19-chat-stream.spec.ts` 属真后端档（`E2E_REAL_BACKEND=1` 环境闸），本机与 mock 档都不跑它 |

## 为什么不能升格成「已实现」

`test_chat_sse.py` 里有 2 条真实冒烟依赖本机/LangBot 可达（CI 上就是那 6 条 skip 的一部分），
而前端那条 `apps/web/e2e/r19-chat-stream.spec.ts` 从未在任何档执行过。**用例存在 ≠ 用例执行过**，
这是本仓 `docs/04_engineering/conventions.md` §4.3 第 1 条（skip ≠ pass）的同一族。
补执行需要真后端环境 ⇒ 见 STEP-00E（验收环境供给）与 `docs/任务规划V0.7.0/05-风险自检与局限.md` §1。
