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

## 执行记录（V0.11.0 第二增量 · 2026-10-15 · @win 实现 + 自验）

| 三级任务 | 状态 | 事实（都是现读的，不是抄卡面） |
|---|---|---|
| S15.1.1 单一 fetch 封装 | ✅ **早已存在，本卡不再重造** | `lib/api/http.ts:83-122` 就是那个封装：信封解包、`code!==0` 抛 `ApiError`、401→10001、429→20005、错误码→中文文案（`ERROR_MESSAGES` 21 项）。卡面把它写成待做项，是**文档落后于代码**，不是缺件 |
| S15.1.2 OpenAPI→TS 生成脚本（`pnpm gen:api`） | ❌ **显式不做** | 类型唯一源已经在位：`scripts/gen_contracts.py` 从 Pydantic 内省生成 `packages/contracts`，前端 `lib/api/types.ts:8` `import type { Envelope } from "@bothot/contracts"`，CI 有 `gen_contracts --check` 漂移门禁。**再造一条 OpenAPI→TS 管线就是第二份真相**，直接违反 D-09；要做的是把还没进 DTO 的端点补进唯一源（归 STEP-01），不是加生成器 |
| S15.1.3 分页 hook `usePaged<T>` | ✅ **已在位** | `lib/hooks/usePagedList.ts`，并由 `tests/w9-paged-list.spec.ts`（3 条）与 `w9-pagination.spec.ts`（5 条）覆盖 |
| S15.2.1 四个 hook 改用客户端 | ✅ **已在位** | `useAdminData.ts:13`、`useJobsList.ts:10`、`useSubscriptions.ts:15`、`useSpaceDetail.ts:11` 全部 `from "@/lib/api"` |
| S15.2.2 删 mock 分支与死代码 | ⚠ **未做，已量化** | 现存 **39 处 `MOCK_ENABLED` 分支，分布在 9 个 `lib/api/*.ts`**（spaces 11、ingest 5、notifications 5、auth 4、public-library 4、ask 3、engines 3、http 3、index 1）；`lib/api/mock-data.ts` 有 3 个导出条目；**7 个测试文件**引用 `NEXT_PUBLIC_API_MOCK`/`mock-data`。⇒ 这不是"顺手删一下"：删 mock 会同时改掉这 7 份测试与 e2e 的 mock 产物链（`ci.yml` 的 mock e2e 明确要 `NEXT_PUBLIC_API_MOCK=true` 烘焙）。**要删就得先给 e2e 换数据面**，属独立一张卡，本卡不夹带 |
| S15.2.3 admin 6 组端点各一个 typed 函数 | ✅ **本卡完成** | 新建 `lib/api/admin-ops.ts`：`listEngineKeys`/`registerEngineKey`/`revokeEngineKey`/`listPushChannels`/`listDiscoveryChannels`/`getOpsLiveness`/`adminPush` 七个函数 + 类型，从 barrel 转出；本域无 mock 分支 |
| S15.3.1 单测覆盖解包/错误映射/分页 | ✅ 部分（新增 11 条） | `tests/admin-ops-api.spec.ts`：path/method/query/camelCase→snake_case/`10004→权限不足`/`defaultChannel=null` 保留/`delivered=false` 不抛异常。解包与错误映射此前由既有测试覆盖，分页由 w9 两份覆盖 |
| S15.3.2 typecheck + lint 0 错 | ✅ | @win：`tsc --noEmit` 0 错；`pnpm run lint` → `No ESLint warnings or errors`；`pnpm run test:unit` → **47 files / 383 tests** 全过；`NEXT_PUBLIC_API_MOCK=false pnpm run build` 编译成功 |
| S15.3.3 e2e 冒烟（对真后端） | 🛑 本机不可做 | 需要 compose 全栈 + 主平台 OIDC 白名单 + 真公众号 URL，`e2e/real-backend.spec.ts` 头部已写这三条前置，CI 也不具备（该步 `continue-on-error`）。本机无 Docker/WSL ⇒ 归 `@ci`/容器就绪后 |

**这一卡真正的产出**：S15.2.3 的七个 typed 函数（14b 四屏的直接依赖）+ 把卡面四处"待做"与代码现状对齐——
S15.1.1/S15.1.3/S15.2.1 三条**本来就已实现**，继续把它们挂在"未开始"上会让下一位重复造第二份 fetch 封装和第二套分页 hook。

## V0.9.0 → V0.10.0 本卡变更（基线 main@81cb997）

- **阻塞变更**：去掉 00E 前置（前端环境本机已验证）；D-V3-00 按用户 2026-10-14/15 的明确指令记为『已授权』，签字落 decision-log 由 00G S0G.1.1 登记。
- 起点：S15.1.1 单一客户端可立即开工；S15.1.2 类型生成仍等 14a 的 S14a.3.3 OpenAPI 导出。

## 裁决已签（V0.11.0 第四节第 2 步 · 2026-10-15 12:04）
| 项 | 变化 |
|---|---|
| D-V3-07 | 分层保留 `vi.mock`，但 mock 数据必须由 `packages/contracts` 生成物驱动，禁手写假对象；补 API 层契约测试 |
| D-V3-00 | 同上：前置是依赖机 + STEP-00X 的跨平台入口，不是授权 |
| 验收面 | 本卡 Done 只能由 `@ci` **ubuntu-latest** 判定；`@win` 读数只算开发烟测，`@linux` 为依赖机本地验证 |
| 标签 | 依 D-V6-01，本卡 `@dep` 已全部改写为 `@linux`/`@ci` |
