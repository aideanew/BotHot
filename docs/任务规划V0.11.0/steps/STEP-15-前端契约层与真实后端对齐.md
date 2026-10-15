# STEP-15 前端契约层与真实后端对齐

> 基线 main@61358c3｜状态：⚪ 未开始

| 字段 | 内容 |
|---|---|
| 1 归属（执行者） | 规划方(Hark) |
| 2 验收者（与执行者分离） | 执行Agent，只输出 PASS/FAIL/UNKNOWN |
| 3 难度 / 里程碑 | 核心 / M2 |
| 4 来源 | F-08/F-15/F-16；V0.7.0 docs/任务规划V0.7.0/steps/STEP-15-前端契约层与真实后端对齐.md |
| 5 目标 | apps/web 所有 API 调用经同一契约客户端；类型由 OpenAPI 生成；去掉残留 mock 分支。 |
| 6 输入 | apps/web/lib/api/**、components/use*.ts |
| 7 输出路径 | apps/web/lib/api/client.ts；apps/web/lib/api/generated/**；apps/web/lib/api/admin/*.ts |
| 8 三级任务 | 见下 |
| 9 验收 | pnpm typecheck/lint/test:unit/build 全绿；grep 页面内裸 fetch = 0 |
| 10 命令 | `cd apps/web && pnpm typecheck && pnpm lint && pnpm test:unit && pnpm build` |
| 11 证据 | docs/任务规划V0.8.0/evidence/61358c3-15/ |
| 12 允许修改 | apps/web/lib/**、apps/web/components/use*.ts |
| 13 禁止修改 | apps/web/app/**页面布局（归 14b）、apps/api/** |
| 14 依赖 / 阻塞 | 14a(S14a.3.3) / D-V3-00 BLOCKING |
| 15 档位 | T3 |
| 16 升级条件 / 规模 | OpenAPI 与契约不一致 ⇒ 以契约为准回 14a 修 / ≈1.5 人日 |

## 三级任务

### S15.1 客户端
- **S15.1.1** 单一 fetch 封装：envelope 解包、错误码映射、401 跳转
- **S15.1.2** OpenAPI→TS 类型生成脚本（pnpm script `gen:api`）
- **S15.1.3** 分页 hook `usePaged<T>`

### S15.2 迁移
- **S15.2.1** 现有 useAdminData/useJobsList/useSubscriptions/useSpaceDetail 改用客户端
- **S15.2.2** 删除 mock 分支与死代码
- **S15.2.3** admin 6 组端点各一个 typed 函数

### S15.3 测试
- **S15.3.1** test:unit 覆盖解包/错误映射/分页
- **S15.3.2** typecheck + lint 0 错
- **S15.3.3** e2e 冒烟（对真后端）

## V0.9.0 → V0.10.0 本卡变更（基线 main@81cb997）

- **阻塞变更**：去掉 00E 前置（前端环境本机已验证）；D-V3-00 按用户 2026-10-14/15 的明确指令记为『已授权』，签字落 decision-log 由 00G S0G.1.1 登记。
- 起点：S15.1.1 单一客户端可立即开工；S15.1.2 类型生成仍等 14a 的 S14a.3.3 OpenAPI 导出。
