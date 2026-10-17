# STEP-15b 前端默认真实后端 + e2e 数据面去手写 mock（V0.13.0 新增，承接 STEP-15 S15.2.2）

| 字段 | 值 |
|---|---|
| 归属-切片 | S-M2（"开发者打开页面看到的就是真实后端的行为"——前端主路径可演示的前提） |
| 归属-需求 | D-V3-07（mock 数据必须由 `packages/contracts` 生成物驱动，禁手写假对象）；STEP-15 目标"去掉残留 mock 分支" |
| 归属-方案 | STEP-15 执行记录 S15.2.2"要删就得先给 e2e 换数据面，属独立一张卡"——本卡即那张卡；D-V10-03（本版代选：默认值翻转） |
| 里程碑 | M2 |
| 执行者 | **规划方**（前端/UI 核心；涉及 9 个 API 模块与 e2e 产物链） |
| 档位 | opus（S15b.1）/ sonnect（S15b.2 机械删除）　理由：默认值翻转影响所有开发者与 CI 两条 e2e；删除分支本身是机械活 |
| 规模 | 大（≈1.75 人日；6 个三级任务） |
| 依赖 | Depends on：22（否则翻到真实后端后推送任务页立刻报错——这本身就是翻转的价值，但需先修）、15 余项　Blocks：14b 余项（通用表要在真实数据下验收） |
| 基线 | main@314d7f2 |

## 证据链
1. `apps/web/lib/api/http.ts:18-19`：`MOCK_ENABLED = (process.env.NEXT_PUBLIC_API_MOCK ?? "true") !== "false"` ⇒ **未设环境变量时默认走手写样例数据**；注释自述"M1 后端未就绪阶段"——该前提已不成立（后端真库 1478 用例全绿，`evidence/314d7f2/pytest_314d7f2.txt`）。
2. 生产构建已有两道守卫：`apps/web/package.json` 的 `prebuild` 在 `NEXT_PUBLIC_API_MOCK !== 'false'` 时 exit 1，`apps/web/Dockerfile:33` `ARG NEXT_PUBLIC_API_MOCK=false` ⇒ **生产不受影响，受害的是开发与联调**。
3. 代价已有实例：`GET /api/v1/bots/tasks` 在真实后端下永远 404（STEP-22 证据 3），而默认 mock 让开发者看到的是正常列表 ⇒ 缺陷被遮蔽。
4. 规模（STEP-15 卡已量化）：39 处 `MOCK_ENABLED` 分支 / 9 个 `lib/api/*.ts`；`mock-data.ts` 3 个导出；7 个测试文件引用；`ci.yml:314-338` 的 mock UI e2e 要求 `NEXT_PUBLIC_API_MOCK=true` 烘焙且为**阻塞门禁**。

## 反证（钢人）
- **反 1：翻转后没起后端的前端开发者打不开页面。** 是的，这正是 UX 契约里"错误态"该被看见的场景；且 `make dev`/`scripts/entry.py` 会同时起后端。为纯 UI 开发保留显式 `NEXT_PUBLIC_API_MOCK=true` 的入口（不删开关，只翻默认）。
- **反 2：mock e2e 是阻塞门禁，翻转会让它红。** 不会——`ci.yml:338` 已显式设 `"true"`，不依赖默认值；本卡 S15b.1.2 用读数证明。
- **反 3：直接删光 mock 更彻底。** 删光会同时打掉阻塞门禁的数据面；D-V3-07 要的是"mock 由契约生成"，不是"没有 mock"。⇒ 先翻默认（小、可逆），再把手写样例换成生成物，最后删分支。

## 目标（可验证的一句话）
未设 `NEXT_PUBLIC_API_MOCK` 时前端打真实后端；`lib/api/*.ts` 中 `MOCK_ENABLED` 分支数从 39 降到 ≤ 1（仅 `http.ts` 的统一拦截点）；mock e2e 门禁仍为 success。

## 输入
- `apps/web/lib/api/{http,index,ask,auth,engines,ingest,notifications,public-library,spaces}.ts`、`mock-data.ts`；`ci.yml:300-345`；`docs/任务规划V0.12.0/contracts/ux_states.schema.json`
## 输出（文件）
- 改：`apps/web/lib/api/http.ts`（默认值翻转 + 统一 mock 拦截点）
- 改：上列 8 个 `lib/api/*.ts`（删分支）
- 改：`apps/web/lib/api/mock-data.ts` → 由 `packages/contracts` 生成物的样例驱动（只读引用，不改 contracts）
- 改：引用 mock 的 7 个单测文件（仅改 import 来源）
- 证据：`docs/06_validation/evidence/EVD-V13-15b/`

## Execution Steps
1. [ ] **S15b.1.1** `http.ts:19` 改为 `process.env.NEXT_PUBLIC_API_MOCK === "true"`；更新注释（删除"M1 后端未就绪"）；单测：未设/`"false"` ⇒ false，`"true"` ⇒ true
2. [ ] **S15b.1.2** `@ci` 读 `CI` 的 frontend 与 mock-e2e 两个 job：均 success（证明 e2e 不依赖默认值）；run id 入 EVD
3. [ ] **S15b.2.1** 在 `http.ts` 的 `request()` 内建统一 mock 拦截：按 `method + path` 查表返回样例；样例表从 `packages/contracts` 的生成类型构造（`satisfies` 生成类型，类型不符即 tsc 红）
4. [ ] **S15b.2.2** 逐模块删分支（9 个文件，每文件一个提交）：删除后 `pnpm exec tsc --noEmit` 与 `pnpm run test:unit` 绿
5. [ ] **S15b.2.3** 7 个单测改从统一样例表取数；`grep -rn "MOCK_ENABLED" apps/web/lib/api | wc -l` ≤ 1
6. [ ] **S15b.3.1** 真实后端冒烟：起后端（3300）+ 前端（3200），手动/Playwright 打开 `/bots`、`/spaces`、`/admin/ops` 三页，截图入 EVD；任一页出现非契约错误态 ⇒ 登记为新缺陷（不在本卡修）

## 验收标准
- [ ] 单测覆盖默认值三态
- [ ] `grep -rn "MOCK_ENABLED" apps/web/lib/api | wc -l` ≤ 1
- [ ] `pnpm exec tsc --noEmit`、`pnpm run lint`、`pnpm run test:unit` 0 错
- [ ] `NEXT_PUBLIC_API_MOCK=false pnpm run build` 成功
- [ ] `@ci` `CI` 的 frontend 与 mock e2e job success
- [ ] 三页真实后端截图入 EVD（人工判据：页面呈现契约内的成功/空/错误态之一，不出现白屏或未捕获异常）

## 验证命令
```bash
cd apps/web
pnpm exec tsc --noEmit && pnpm run lint && pnpm run test:unit
NEXT_PUBLIC_API_MOCK=false pnpm run build
grep -rn "MOCK_ENABLED" lib/api | wc -l
```

## 证据路径
`docs/06_validation/evidence/EVD-V13-15b/`

## 允许修改
- `apps/web/lib/api/**`、`apps/web/**/__tests__/**` 与 `apps/web/**/*.test.ts(x)` 中引用 mock 的 7 个文件
- `docs/06_validation/evidence/EVD-V13-15b/**`

## 禁止修改
- `packages/contracts/**`（只读引用）
- `apps/web/package.json` 的 `prebuild` 守卫、`apps/web/Dockerfile`
- `.github/workflows/**`（e2e 门禁不改）
- `apps/api/**`

## 依赖与阻塞
- Depends on：22、15 余项
- Blocks：14b 余项
- 阻塞条件：S15b.1.2 mock e2e 红 ⇒ 说明 e2e 依赖默认值，回退 S15b.1.1 并在 EVD 记录原因

## 建议执行档位
opus（S15b.1、S15b.3）/ sonnect（S15b.2）

## 升级条件
统一拦截表无法用生成类型表达某个模块的响应（契约缺口）⇒ 停下，交 Contract 列补契约，不手写类型

## 预估规模
大　6 个三级任务，单个 < 2h；≈1.75 人日
