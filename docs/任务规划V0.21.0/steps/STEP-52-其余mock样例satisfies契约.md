# STEP-52 其余 mock 样例 satisfies 契约类型（S37.4 第二段，P-82 收口）

> 状态：⬜ 待执行助手（STEP-47 @ci 三绿后）｜版本 V0.21.0

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行助手（Agent-Web） |
| 2 切片 | SL-SHAPE |
| 3 来源 | S37.4、P-82、STEP-47 产出的契约名清单（`EVD-V21-47/`） |
| 4 目标 | mock 表 24 条路由的样例与 handler 返回值全部 `satisfies` 契约类型；未登记即红 |
| 5 输入 | `packages/contracts/src/**/dto.ts`（只读）；`apps/web/lib/api/mock-routes.ts`、`mock-data.ts`、`types.ts` |
| 6 输出 | 新 `apps/web/lib/api/mock-contract-map.ts`（路由 pattern 源串 → 契约类型名，纯数据）；改 `mock-routes.ts` 每条 handler 返回值 `satisfies`；`types.ts` 中与契约同形的手写类型改为契约别名；新 `apps/web/tests/s52-mock-contract-coverage.spec.ts`：`MOCK_ROUTES` 每条的 pattern 都在 map 里（缺一条即红）；改 `mock-routes.ts` 头注释，删掉"P-82 不可满足"段；P 表 P-82 闭合 |
| 7 验收 | ① 先红：覆盖测试在只有引擎域登记时红，列出缺失路由数 ② 改后 typecheck/vitest/lint 绿 ③ 反证：任一域样例删一键 ⇒ tsc 红（至少 3 个域各一次，输出入证）④ 三绿 |
| 8 命令 | 同 STEP-48 第 8 格 |
| 9 证据 | `EVD-V21-52/` |
| 10 允许修改 | 第 6 格所列 + 因类型收紧报错的调用方类型标注 |
| 11 禁止修改 | `packages/contracts/**`、`apps/api/**` |
| 12 依赖 | STEP-47、STEP-48 ｜ Blocks：STEP-53 |
| 13 档位 | sonnet |
| 14 升级条件 | 契约与前端现有渲染依赖的字段冲突（前端读了契约里没有的键）⇒ 登记 P 号交回规划方，不改契约 |
| 15 规模 | 中，≈0.8 人日 |
| 16 熔断 | 同判据 2 次 FAIL ⇒ 停 |

## 三级任务
1. [ ] **S52.1** 覆盖测试先红
2. [ ] **S52.2** identity + notifications 样例
3. [ ] **S52.3** spaces 样例
4. [ ] **S52.4** docs + resolve + extract 样例
5. [ ] **S52.5** 反证三次 + 全量 + 三绿 + P-82 闭合 + 07 记录
