---
id: TASK-007
type: task
title: gen_contracts 生成 errors.ts 并纳入 --check
status: ready
slice: S1
owner: Agent-Contract
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-007：gen_contracts 生成 errors.ts 并纳入 --check

**归属**
- 所属切片：S1（WP-1 错误契约单一源）
- 执行 Agent：Agent-Contract
- 来源需求：REQ-F-008；契约唯一源纪律（packages/contracts/src/index.ts 头注）
- 来源方案：ADR-0008（提议）

**目标**
packages/contracts/src/common/errors.ts 由 scripts/gen_contracts.py 从 errors.py 生成；手改即被 --check 拦截。

**输入**
- scripts/gen_contracts.py:112-172（generate/check）
- apps/api/app/core/errors.py（TASK-006 后）
- 现手写 packages/contracts/src/common/errors.ts（缺 10007/10008）

**输出**（新增/修改的文件）
- `scripts/gen_contracts.py`
- packages/contracts/src/common/errors.ts（生成物）

**Execution Steps**
1. [ ] generate() 增加 errors 产物：读取 ERROR_CODES 与各子类 http_status，渲染 ApiErrorCode/ApiErrorName/ApiErrorHttpStatus/AuthErrorCode
2. [ ] AuthErrorCode 取 http_status==401 的 code 集合（10001/10003），保持与现导出名一致
3. [ ] 生成物加『请勿手动修改』头
4. [ ] 运行生成 → --check 幂等
5. [ ] 契约包 tsc --noEmit 通过

**验收标准**
- [ ] errors.ts 含 10007、10008、50003=CONFIGURATION_ERROR
- [ ] python scripts/gen_contracts.py --check 退出 0
- [ ] 手改 errors.ts 任意一行后 --check 退出 1
- [ ] packages/contracts tsc 零错；apps/web tsc 零错

**验证命令**
```bash
cd apps/api && python ../../scripts/gen_contracts.py && python ../../scripts/gen_contracts.py --check
cd ../web && pnpm exec tsc --noEmit -p ../../packages/contracts/tsconfig.json && pnpm exec tsc --noEmit
```

**证据路径**
`docs/06_validation/evidence/EVD-007/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `scripts/gen_contracts.py`
- `packages/contracts/src/common/errors.ts`

**禁止修改**
- apps/**
- apps/api/alembic/**

**依赖与阻塞**
- Depends on：TASK-006
- Blocks：TASK-008
- 阻塞条件：index.ts 导出名需改 → 停，属契约变更需 opus 审

**建议执行档位**
sonnect　理由：生成器扩展，规则已在 DESIGN-001 写死

**升级条件**
--check 不幂等连续 2 次 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中
