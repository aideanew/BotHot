---
id: TASK-014
type: task
title: gen_contracts 生成响应形状 DTO（*Out）
status: ready
slice: S3
owner: Agent-Contract
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-014：gen_contracts 生成响应形状 DTO（*Out）

**归属**
- 所属切片：S3（WP-3 响应形状契约）
- 执行 Agent：Agent-Contract
- 来源需求：契约唯一源
- 来源方案：ADR-0008

**目标**
packages/contracts 新增 bot/hot 的 *Out 响应类型，由 OpenAPI components 生成，并由 index.ts 导出；--check 覆盖。

**输入**
- scripts/gen_contracts.py:38-60（DOMAIN_REQUEST_SCHEMAS）
- TASK-012/013 的 OpenAPI 组件

**输出**（新增/修改的文件）
- `scripts/gen_contracts.py`
- `packages/contracts/src/bot/dto.ts`
- `packages/contracts/src/hot/dto.ts`
- `packages/contracts/src/index.ts`

**Execution Steps**
1. [ ] 新增 DOMAIN_RESPONSE_SCHEMAS 映射
2. [ ] _schema_to_ts 复用，产出 *Out 接口
3. [ ] index.ts 导出新类型（保留原实体导出，不破坏消费方）
4. [ ] --check 幂等 + 契约包 tsc

**验收标准**
- [ ] --check 退出 0
- [ ] 契约包与 apps/web tsc 零错
- [ ] index.ts 导出 7 个 *Out 类型

**验证命令**
```bash
cd apps/api && python ../../scripts/gen_contracts.py --check && cd ../web && pnpm exec tsc --noEmit -p ../../packages/contracts/tsconfig.json
```

**证据路径**
`docs/06_validation/evidence/EVD-014/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `scripts/gen_contracts.py`
- `packages/contracts/**`

**禁止修改**
- apps/**

**依赖与阻塞**
- Depends on：TASK-012、TASK-013
- Blocks：TASK-015
- 阻塞条件：生成器需要改实体导出名 → 停

**建议执行档位**
sonnect　理由：生成器扩展

**升级条件**
不幂等 2 次 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中
