---
id: TASK-008
type: task
title: 前端错误表对齐契约 + 429/413 展示态
status: blocked
slice: S1
owner: Agent-App
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-008：前端错误表对齐契约 + 429/413 展示态

**归属**
- 所属切片：S1（WP-1 错误契约单一源）
- 执行 Agent：Agent-App
- 来源需求：REQ-F-008；UX States 契约
- 来源方案：ADR-0008（提议）、DESIGN-001 §⑥

**目标**
前端 ERROR_MESSAGES 以 Record<ApiErrorCode,string> 类型约束覆盖全部后端码；10007/10008 有专属文案，10007 不触发自动重试。

**输入**
- apps/web/lib/api/http.ts:26-51（ERROR_MESSAGES、isAuthError）
- packages/contracts/src/common/errors.ts（TASK-007 生成物）
- DESIGN-001 §② 前端文案表

**输出**（新增/修改的文件）
- `apps/web/lib/api/http.ts`
- apps/web/tests/error-messages.spec.ts（新增）

**Execution Steps**
1. [ ] ERROR_MESSAGES 拆为：satisfies Record<ApiErrorCode,string> 的主表 + LEGACY_MESSAGES（10101/10102/30101/30102/50101，按 D-04 结论保留或删除）
2. [ ] 补 10007『请求过于频繁，请稍后再试』、10008『提交内容过大』、20004/20005/30005/30006/50001/50003 文案（取 DESIGN-001）
3. [ ] isAuthError 改为基于契约 AuthErrorCode（+ D-04 决定是否保留 10101）
4. [ ] 新增 vitest：遍历契约码表断言每码有文案；10007 不在重试判定内

**验收标准**
- [ ] pnpm exec tsc --noEmit 零错（缺码即编译失败）
- [ ] 新 vitest 用例全绿，既有 vitest 零回归
- [ ] mock e2e 绿

**验证命令**
```bash
cd apps/web && pnpm exec tsc --noEmit && pnpm run test:unit -- --run && pnpm run test:e2e
```

**证据路径**
`docs/06_validation/evidence/EVD-008/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/web/lib/api/http.ts`
- `apps/web/tests/error-messages.spec.ts`

**禁止修改**
- packages/contracts/**
- apps/api/**

**依赖与阻塞**
- Depends on：TASK-007、D-04
- Blocks：无
- 阻塞条件：需要新增错误码 → 停，回报给 Agent-Contract

**建议执行档位**
sonnect　理由：前端实现 + 单测

**升级条件**
连续 2 次验收失败 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中
