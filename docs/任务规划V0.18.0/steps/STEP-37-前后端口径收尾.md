# STEP-37 前后端口径收尾

> 基线 main@f86811e｜状态：🔶 第 1 轮已交付（2026-10-24，读数在 EVD-V18-37/；S37.4 停在 P-82 交回）｜版本 V0.18.0

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行 Agent-Web（S37.1 由同人顺手） |
| 2 验收者 | 规划方 |
| 3 难度 / 里程碑 | 低～中 / M3 |
| 4 来源 | P-50、P-51、P-82、P-90、P-96 |
| 5 目标 | 同一件事前后端只有一套词、一套分页壳；mock 样例错了 tsc 会红；历史残留的错误注释清掉 |
| 6 输入 | `apps/api/app/api/v1/bots.py:674-679`；`apps/api/app/api/v1/engines.py:61-65` `REFUSAL_MARKERS`；`packages/contracts`（engine.schema `EngineReason`、分页壳）；`apps/web/lib/hooks/usePagedList.ts`；`apps/web/lib/api` 的 mock 拦截表 |
| 7 输出路径 | 上述文件、对应测试、`docs/06_validation/evidence/EVD-V18-37/`（D-V18-13） |
| 10 命令 | `pnpm -C apps/web typecheck && pnpm -C apps/web test:unit`；`pytest tests/test_engine*.py -q`；`gen_contracts --check` |
| 12 允许修改 | 第 7 格所列 |
| 13 禁止修改 | `packages/contracts/**` 的契约内容（只读生成类型） |
| 14 依赖 | 36 |
| 15 档位 | sonnet |
| 16 规模 | ≈1.0 人日 |

## 三级任务
1. [x] **S37.1** P-50/P-51：两处残留文本按台账行原文改正，零行为变化
2. [x] **S37.2** P-90：前端只按 `EngineReason` 枚举值查一张文案表（唯一一处）；后端 `REFUSAL_MARKERS` 的措辞改为由同一枚举派生或在测试里与前端文案表逐值比对；反证：改一侧措辞 ⇒ 比对用例红
3. [x] **S37.3** P-96：`PagedResponse` 收敛为 `PageTargetUnified` 一种（含 `hasMore`），旧两壳分支删除；所有调用方 tsc 通过
4. [ ] **S37.4** P-82：mock 拦截表里每条样例加 `satisfies <生成类型>`；反证：故意写错一个字段 ⇒ tsc 红

## 完成判据（全部机器可判）
- 每项反证读数
- tsc、vitest、后端相关用例全绿
- 三绿

## 熔断
连续 2 轮验收 FAIL ⇒ 停卡交回规划方（rounds-check 机器执行，口径见 D-V18-16）。前提与现读不符 ⇒ 先登记 P 号再停，不自改卡面。
