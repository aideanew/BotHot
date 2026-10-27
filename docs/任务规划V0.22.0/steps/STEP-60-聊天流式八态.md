# STEP-60 聊天流式八态（REQ-F-005，假 LLM 上游）

> 基线 STEP-59 交付后｜状态：⬜｜裁决 D-V22-01/03

| 字段 | 内容 |
|---|---|
| 1 归属 | 规划方（opus）｜切片 S-E2E-2 |
| 2 来源 | REQ-F-005（`product-requirements.md:71`）、`r19-chat-stream.spec.ts` 零执行 |
| 3 目标 | `e2e-real` job 中 `r19-chat-stream.spec.ts` 八态全部执行且通过 |
| 4 输出 | `scripts/e2e/fake_llm.py`（chat SSE + embeddings，三种异常模式）；job 起假上游 :3290；种子空间与文档；spec 开关与八态枚举改读 `ux_states.schema.json` |
| 5 验收 | ① 八态 8 passed / 0 skipped ② 枚举来源为文件读取（grep 判无手抄数组） ③ CI 中无任何到 `siliconflow.cn` 的请求（假上游访问日志 + 环境变量读数） ④ `apps/api/app` 零改动 |
| 6 允许修改 | 同 STEP-59 第 6 格 + `apps/web/e2e/r19-chat-stream.spec.ts` |
| 7 禁止修改 | 同 STEP-59 第 7 格 |
| 8 规模/档位 | ≈1 人日｜opus |
| 9 熔断 | 同判据 2 次 FAIL ⇒ 停 |
| 10 验证命令 | `bash scripts/e2e/run_real_backend.sh --with-fake-llm && cd apps/web && E2E_REAL_BACKEND=1 E2E_CHAT_LLM=fake pnpm exec playwright test --project=real e2e/r19-chat-stream.spec.ts` |
| 11 证据 | `docs/06_validation/evidence/EVD-V22-60/` |
| 12 依赖 | 59｜Blocks：62 |
| 13 阻塞条件 | 后端 SSE 解析对假上游格式不认 ⇒ 以 `apps/api/tests` 现有 SSE 样例为准修假上游，不改后端 |
| 14 升级条件 | 八态中某态需后端新错误码才能触发 ⇒ 停，交回 |
| 15 档位理由 | SSE 通路与降级态组合多 |
| 16 规模 | 中，>2 小时 |
