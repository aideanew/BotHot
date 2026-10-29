# STEP-60 聊天流式八态（REQ-F-005，假 LLM 上游）

> 基线 STEP-59 交付后｜状态：✅ 已交付（2026-10-29。按 V0.24.0 增量 §1 重写为 `/chat` **五态**、按 V0.25.0 订正增量补齐 `env` 与非-skip 守卫步；原「八态」判据作废）｜裁决 D-V22-01/03
> 交付读数与判据逐条：`docs/06_validation/evidence/EVD-V24-60/s60_readings.md`（五态供给、增量 §1.4 八条、@ci 回填；三处供给订正见台账 P-163、两条判据字面不可达见 P-164）
> （历史）开工前判词（2026-10-28，原状态 ⬜ 未开，逐字保留）：**判据「无交付提交」成立：本卡一行代码都没写**。S60.0 探针 2026-10-28 判**卡面第 5 格验收 ①「八态 8 passed / 0 skipped」在当前供给下不可达**——`/ask` 的检索委派 LangBot（`chat.py:344` → `client.py:198-211`），而启动器不提 LangBot、CI 的 `e2e-real` services 只有 postgres+redis、`/system/health` 实测 `"langbot":"unreachable"` ⇒ 检索恒空 ⇒ `chat.py:233-235` 抛 30002，流到不了 LLM；种子还需「公开可抓取的文章 URL + 运行中的 LangBot」两前提（入库口只有 `url: str`）；`initial` 与 `forbidden` 在 /chat 上**没有任何 DOM 出口**（越权 chat 返 404+30004），正命中本卡第 14 格「某态需后端新错误码才能触发 ⇒ 停，交回」，而 V0.23.0 增量又禁止改 `apps/web/components/**`、`app/**`。读数与四条探针见 `docs/06_validation/evidence/EVD-V22-60/s60_0_probe_readings.md`，三条出路登台账 **P-149**。状态不写 `⏸`：词表要求 `⏸` 写明 BLOCKING 的 Q 号，我没有 Q 号可指

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行助手（opus 档；D-V22-06，原子步与判据见 `08-阶段A执行细则.md` §3，冲突以 08 为准）｜切片 S-E2E-2 |
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
