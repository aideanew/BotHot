# STEP-15 前端契约层与真实后端对齐（mock 纠偏）

| 字段 | 值 |
|---|---|
| 归属-切片 | S-M5 前端契约层 |
| 归属-需求 | REQ-F-002 / F-005 / F-008 的**验证面**；M-7（测试有效性） |
| 归属-方案 | 04 §4.13、`01` F-81/F-82、`coverage §4`；裁决 D-V3-07 |
| 里程碑 | M5 |
| 档位 | sonnet　理由：多为注释更正、fixture 生成与用例补齐，属原子实现。**升级条件**：若需改 `packages/contracts` 结构 ⇒ 转 W-Contract + opus |
| 规模 | 中（≈1.5 人日） |
| 依赖 | Depends on：STEP-01、STEP-14（消费其 DTO）。Blocks：STEP-12 |
| 基线 | main@13acacc |
| 剩余原子任务 | 8（👤 0） |

## 目标
让前端测试「绿」重新等于「与真实后端契约一致」：注释与实现相符、mock 数据由契约生成、至少一条关 mock 的真实后端 e2e 在 CI 跑主干路径。

## 输入（本会话实测）
- `MOCK_ENABLED = (NEXT_PUBLIC_API_MOCK ?? "true") !== "false"`（`lib/api/http.ts:18-19`）⇒ 默认 mock；`apps/web/Dockerfile:33` 构建期钉 false
- 无 mock 分支的模块：`hot.ts` / `bots.ts` / `admin.ts` / `jobs.ts` / `subscriptions.ts`（`grep -c MOCK_ENABLED` = 0）
- **注释不实**：`e2e/hot.spec.ts:4` 与 `e2e/bots-tasks.spec.ts:4` 自称「mock 主干」，而上述模块无 mock 分支 ⇒ 这些套件只在真后端下可跑
- 单测强度：45 文件（22 tsx/23 ts）、约 394 用例块、**36/45 用 `vi.mock`**（含 `vi.mock("@/lib/api")`）
- e2e：5 文件 23 测试；`real-backend.spec.ts:22` 默认 gate 跳过（`E2E_REAL_BACKEND==="1"`）
- CI：`ci.yml:247` typecheck、`:263` vitest、`:296` chromium、`:304-306` mock e2e、`:312` gated 真实 e2e
- 契约：`contracts/api.envelope.schema.json`、`ux_states.schema.json#/x-universal-rules`

## 输出（文件）
`apps/web/e2e/{hot.spec.ts,bots-tasks.spec.ts}`（注释）、`apps/web/lib/api/mock-data.ts`（改为生成）、`scripts/gen-fe-mocks.py`（新，或复用 `gen_contracts`）、`apps/web/tests/api-contract.spec.ts`（新）、`apps/web/components/LoadingErrorShell.tsx` **只读复用**、`.github/workflows/ci.yml`（S15.4.1，限 D-11 范围外 ⇒ 需单独授权，见阻塞条件 ③）

## Execution Steps
1. [ ] ✅ **S15.1.0** 复跑清点命令取当前读数（mock 文件数、无 mock 分支模块清单），入 EVD-V3-15
2. [ ] 🔴 **S15.1.1** 复现注释不实：无后端时起 `hot.spec.ts` ⇒ 记录真实失败/跳过形态
3. [ ] 📄 **S15.1.2** 更正 `hot.spec.ts` / `bots-tasks.spec.ts` 头注释为「需真实后端」，并把 gate 条件写进注释
   - S15.1.2.1 **禁止反向**：不得给 `hot.ts` 加 mock 分支来迁就旧注释（会让演示态假装能跑真实数据）
4. [ ] 🛠 **S15.2.1** `mock-data.ts` 的假对象改由 `packages/contracts` 生成物产出（脚本生成，人不再手写）
   - 变异反证：手改一个 mock 字段名 ⇒ 一致性测试必须红
5. [ ] ✅ **S15.2.2** 记录「`vi.mock('@/lib/api')` 文件数」基线 36；目标不是降到 0，而是**数据源单一**（B-13）
6. [ ] 🔴🛠 **S15.3.1** `tests/api-contract.spec.ts`：对生成 DTO/OpenAPI 做运行时校验（响应必含 `code/message/requestId`；分页壳字段齐；时间 ISO8601 带时区）
7. [ ] 🛠 **S15.3.2** 错误呈现收敛：错误码 `retryable=false` 时不渲染重试按钮（`ux#/x-universal-rules` 第 4 条），统一走 `LoadingErrorShell`
8. [ ] ✅ **S15.4.1** CI：typecheck + vitest 全绿；关 mock 的真实后端 e2e 主干 ≥1 条在 CI 执行（非 skipped），run id 入 EVD

## 验收标准
- [ ] 两个 spec 的注释与 `hot.ts`/`bots.ts` 实况一致（`grep` 判据须先过可满足性检查）
- [ ] mock 数据 100% 由契约生成；手写假对象在 `lib/api/**` 中被守卫拦住
- [ ] `api-contract.spec.ts` 绿且变异可红
- [ ] `retryable` 驱动重试显隐：给一个 `10004` 用例断言**无**重试按钮
- [ ] 至少一条关 mock e2e 在 CI 真实执行（junit 里是 pass 不是 skip）
- [ ] `pnpm typecheck && pnpm vitest run` 读数入 EVD

## 验证命令
```bash
cd apps/web
grep -c MOCK_ENABLED lib/api/*.ts                                   # 记录无 mock 分支的模块
pnpm vitest run --reporter=junit --outputFile=../../docs/06_validation/evidence/EVD-V3-15/vitest.xml
pnpm playwright test --project=chromium 2>&1 | tail -20              # 记录真实后端套件的 skip/pass
NEXT_PUBLIC_API_MOCK=false E2E_REAL_BACKEND=1 pnpm playwright test e2e/real-backend.spec.ts
grep -n 'MOCK_ENABLED' lib/api/notifications.ts                     # 演示态不连 SSE 的行（S15.1 需一并更正注释）
```

## 证据路径
`docs/06_validation/evidence/EVD-V3-15/`

## 允许修改
`apps/web/e2e/**`（注释与 gate）、`apps/web/lib/api/mock-data.ts`、`apps/web/tests/**`、`scripts/gen-fe-mocks.py`、`apps/web/components/admin/**`（S15.3.2 复用点）
## 禁止修改
`apps/api/app/**`、`packages/contracts/**`（需改 ⇒ 转 W-Contract）、`apps/web/components/LoadingErrorShell.tsx`、`.github/workflows/**`（除非单独授权，见阻塞 ③）、`next.config.mjs`

## 依赖与阻塞
- Depends on：STEP-01、STEP-14　Blocks：STEP-12
- 阻塞条件：① 契约生成物与后端实际响应不符 ⇒ 停，判为**契约缺陷**转 ADR，不得在前端侧「适配」掉差异；② 真实后端 e2e 需要 CI 起 PG/Redis ⇒ 属 `ci.yml` 变更，超出 D-11 授权范围 ⇒ 上报待批；③ `hot.ts` 被要求加 mock ⇒ 违反 S15.1.2.1，拒绝并说明
