# STEP-52 其余 mock 样例 satisfies 契约类型（S37.4 第二段，P-82 收口）

> 基线 main@b4157a9｜状态：✅ 收口（2026-10-26，交付头 `0aa2923` 三绿 attempt 1：
> CI 40263352699 / CI-Windows 40263352628 / Security 40263352616；读数在 `EVD-V21-52/`）｜版本 V0.21.0

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行助手（Agent-Web） |
| 2 切片 | SL-SHAPE |
| 3 来源 | S37.4、P-82、P-122（STEP-47 盘出的 7 处漂移）；契约名清单 = `apps/api/app/contracts/shapes.py` 的 `MOCK_ROUTE_CONTRACTS`（只读） |
| 4 目标 | mock 表 22 条路由（引擎 2 条已由 48 做，本卡 20 条）的样例与 handler 返回值全部 `satisfies` 契约类型；未登记即红 |
| 5 输入 | `packages/contracts/src/**/dto.ts`（只读）；`apps/web/lib/api/mock-routes.ts`、`mock-data.ts`、`types.ts` |
| 6 输出 | 新 `apps/web/lib/api/mock-contract-map.ts`（路由 pattern 源串 → 契约类型名，纯数据）；改 `mock-routes.ts` 每条 handler 返回值 `satisfies`；`types.ts` 中与契约同形的手写类型改为契约别名；新 `apps/web/tests/s52-mock-contract-coverage.spec.ts`：`MOCK_ROUTES` 每条的 pattern 都在 map 里（缺一条即红）；改 `mock-routes.ts` 头注释，删掉"P-82 不可满足"段；P 表 P-82、P-122 闭合。**P-122 七处逐条处理**：`/auth/me` mock 改回线上嵌套形 `{user:{…},wallet:{…}}`（归一化函数两种形态都吃，页面零改动——先跑现有 me 归一化用例确认）；logout 返回 `{logged_out:true}`；两条列表补 `total/limit/offset`（回显请求值）；`POST /spaces` 补 `engine/engineKbId/isPublic`；`DELETE /spaces/{id}` 补 `engineResidue`；详情未命中改抛 30004；`Space`/`SpaceDoc` 等手写类型与契约同形的改为契约别名（线上恒有的键不再可选） |
| 7 验收 | ① 先红：覆盖测试在只有引擎域登记时红，列出缺失路由数 ② 改后 typecheck/vitest/lint 绿 ③ 反证：任一域样例删一键 ⇒ tsc 红（至少 3 个域各一次，输出入证）④ 三绿 |
| 8 命令 | 同 STEP-48 第 8 格 |
| 9 证据 | `EVD-V21-52/` |
| 10 允许修改 | 第 6 格所列 + `apps/web/lib/api/mock-data.ts`（样例补键）+ 因类型收紧报错的调用方类型标注与测试夹具补默认值 |
| 11 禁止修改 | `packages/contracts/**`、`apps/api/**` |
| 12 依赖 | STEP-47、STEP-48 ｜ Blocks：STEP-53 |
| 13 档位 | sonnet |
| 14 升级条件 | 契约与前端现有渲染依赖的字段冲突（前端读了契约里没有的键）⇒ 登记 P 号交回规划方，不改契约 |
| 15 规模 | 中，≈0.8 人日 |
| 16 熔断 | 同判据 2 次 FAIL ⇒ 停 |

## 三级任务
1. [x] **S52.1** 覆盖测试先红
2. [x] **S52.2** identity + notifications 样例
3. [x] **S52.3** spaces 样例
4. [x] **S52.4** docs + resolve + extract 样例
5. [x] **S52.5** 反证三次 + 全量 + 三绿 + P-82 闭合 + 07 记录
