# P-124 探针读数（覆盖面门判不住 satisfies 被摘）

@win，2026-10-26，开工树 b4157a9 + 本卡改动。命令都在 `apps/web` 下跑，代理变量已清。

## 做了什么

把 `lib/api/mock-routes.ts` 里 DELETE `/api/v1/spaces/{id}` 那条 handler 的约束整段摘掉
（`}) satisfies SpaceDeleteResult,` → `}),`），其余一字未动；跑两道门，然后按 sha256 还原源文件。

## 读数

| 命令 | rc | 结论 |
|---|---|---|
| `pnpm exec vitest run tests/s52-mock-contract-coverage.spec.ts` | 0 | `Test Files 1 passed (1)`、`Tests 3 passed (3)` ⇒ **门看不见** |
| `pnpm run typecheck` | 0 | 0 错 ⇒ **编译期也看不见**（该字面量自身合法，只是不再与契约对账） |

原文：`p124_coverage_green_after_removing_satisfies.txt`、`p124_typecheck_green_after_removing_satisfies.txt`；
还原后源文件 sha256 与探针前一致（`True`，脚本输出）。

## 为什么本卡不修

三道用例判的是"路由 ↔ 对照表 ↔ 后端权威名"这三者的一致性，而 handler 里那句 `satisfies`
是第四件事——它与表之间没有机器连接。修法要落到"运行时逐条断言样例键集合与契约逐字相同"，
即 STEP-48 的既有形状（`tests/s48-engine-contract.spec.ts` 写死 10 个键并注明源文件 + 数字段行自检），
但要铺到 22 条 ⇒ 22 份键清单需与 `packages/contracts/src/shapes/dto.ts` 同步维护。
卡面第 6 格只规定覆盖判据，把它塞进这张 ≈0.8 人日的卡会挤掉 P-122 的七处；
因此登记 **P-124** 交规划方排卡，本卡如实记录洞在。

## 今天的手工对账（P-124 修好之前的替代证据）

审查子智能体在第 1 轮逐条对过 22 条路由的 handler 约束与 `MOCK_CONTRACT_MAP` 的类型名，
结论"逐条相同"，读数记在 `review_round1.md` 问题 1。
