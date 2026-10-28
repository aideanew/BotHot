# STEP-74：`admin.spec.ts` ⑥ 定位器收窄（P-158 收口）

## 1. 归属

- 所属切片：**P-A′**（`e2e-real` 全绿的最后一块）
- 来源需求：`04` §1 M-3；台账 **P-158**（STEP-67 第 2 轮的 ⑥ strict-mode violation）
- 来源方案：**D-V25-01**（归属从 STEP-68 改判）、`03` §2.1 第二行（禁 `.first()`）
- 执行者：执行助手

## 2. 目标

`apps/web/e2e/admin.spec.ts` 的 ⑥ 用例第二条读取点（`:271`）不再触发 Playwright strict mode：
`getByRole("status").getByText(/告警|依赖未就绪|未知/)` 由 **2 命中**降为 **1 命中**，
且**不掩盖**产品侧「章 + 说明段同信息双渲染」这一事实。

## 3. 输入

- 现场（`EVD-V23-67/s67_7_test6_error.txt`，`3c4138d` 第 2 轮）：
  ```
  strict mode violation: getByRole('status').getByText(/告警|依赖未就绪|未知/) resolved to 2 elements:
    1) <span data-tone="degraded">告警未启用</span> aka getByText('告警未启用')
    2) <p>依赖就绪，但告警探测器未启用（ALERTING_ENABLED=false）…</p> aka getByText('依赖就绪，但…')
  ```
  红在 `admin.spec.ts:271:50`。
- 现读（`df210b3`）：
  ```
  264:    test("⑥ 告警状态条：/ready 的 alerting 读数必须被画出来", …)
  268:      await expect(bar.getByText(/告警未启用|告警已启用|依赖未就绪|未知/)).toBeVisible();
  271:      await expect(bar.getByText(/告警|依赖未就绪|未知/)).toBeVisible();
  ```
- 形态模板：**同一用例的 `:268`**——它用窄式四选一，`:264-272` 全跑过且不报 strict mode。
- 契约/裁决：D-V25-01（归属）、`03` §2.1（禁 `.first()`）
- 前置任务：无（不依赖 V0.24.0 任何一张卡）

## 4. 输出

- 修改：`apps/web/e2e/admin.spec.ts`（**仅 `:271` 一行**）
- 新增：`docs/06_validation/evidence/EVD-V25-74/`
  - `s74_readings.md`（读数 + 反向验证）
  - `s74_before_after.txt`（`:264-272` 的 `sed` 原文，改动前后各一份）
  - `s74_ci.txt`（`@ci` 的 `E2E (real backend…)` 步原文）

## 5. Execution Steps

> 执行记录（V0.25.0 批 1，2026-10-28）：S74.1～S74.4 已做；S74.5 的「本机跑该用例」按本卡 §11 的
> 阻塞条件不成立（本机无 Redis/无 docker，`real` project 起不来），改用 Playwright 引擎 + 逐字 DOM 复算
> 四种状态的命中数做反证（宽 2 / 窄 1，见 `EVD-V25-74/s74_readings.md` §3）；S74.7～S74.8 等提交后的 @ci。
>
1. [x] **S74.1** 取先红：读 `EVD-V23-67/s67_7_test6_error.txt` 原文，确认失败点是 `:271` 的 strict mode（不是 `:268`）。若现场已漂移 ⇒ 停手，先补一条新读数。
2. [x] **S74.2** 记 before：`sed -n '264,272p' apps/web/e2e/admin.spec.ts` 原样落 `s74_before_after.txt`。
3. [x] **S74.3** 把 `:271` 的 `/告警|依赖未就绪|未知/` 换成与 `:268` **逐字相同**的窄式：
   ```ts
   await expect(bar.getByText(/告警未启用|告警已启用|依赖未就绪|未知/)).toBeVisible();
   ```
   **禁止** `.first()`、禁止 `{ exact: true }`、禁止改正则去匹配 `<p>` 里的整句（那是乙案，需产品裁定）。
4. [x] **S74.4** 记 after：同一条 `sed` 落 `s74_before_after.txt`。
5. [x] **S74.5** **反向验证**（本卡的核心判据）：把 `:271` **临时改回宽式**，本机跑一次该用例，
   确认**仍然红**（`resolved to 2 elements`），然后改回窄式并核对 `git diff` 只有一行。
   > 为什么必须做：如果反过来（改完就绿、改回也绿），说明变绿的原因不是这次修改，而是环境变了。
   > 反向验证是「这条断言还活着」的唯一凭证。
6. [x] **S74.6** 本机跑一次（若本机已具备真档前提）：见 §7 第 1 条。若本机起不了全栈 ⇒ 跳过，只写 `@ci` 读数（§7 第 2 条）。
7. [ ] **S74.7** 提交（卡面勾选 + 证据 + 代码同一个提交），推送，读 `@ci` 的 `E2E (real backend, project=real, admin.spec.ts)` 步。
8. [ ] **S74.8** 把该步的 `⑥ … ✓` 行与 `⑦ 不再 did not run` 落 `s74_ci.txt`。

## 6. 验收标准

- [ ] `grep -c "告警未启用|告警已启用|依赖未就绪|未知" apps/web/e2e/admin.spec.ts` = **2**（`:268` 与 `:271` 各一处，逐字同串）
- [ ] `grep -c "\.first()" apps/web/e2e/admin.spec.ts` 的变化中**本卡贡献 0**
- [ ] 反向验证：宽式状态下该用例**红**，附原文与退出码
- [ ] `@ci` 的 `E2E (real backend…)` 步中 ⑥ **通过**（不再 `strict mode violation`）
- [ ] ⑦ **出现在**该步输出里（不再 `did not run`）
- [ ] `git diff --stat` 只含 `admin.spec.ts` 一行 + 证据目录
- [ ] 证据里必须写明「⑥ 的双渲染是否仍是产品事实」——若两处命中都是真渲染，`04` §8 要补一条观察项给规划方（本卡只收窄断言，不改产品）

## 7. 验证命令

```bash
cd /d/Code/AideanBotHot
# 1) 本机真档（需要:3200 前端 + :3300 后端 + seed 文件；起不来就走 2)）
cd apps/web && PORT=3200 E2E_REAL_BACKEND=1 \
  E2E_SEED_FILE="${E2E_RUN_DIR:-${RUNNER_TEMP:-/tmp}/e2e-real}/seed.txt" \
  pnpm exec playwright test --project real e2e/admin.spec.ts -g "⑥" ; cd ../..

# 2) @ci 读数（无 gh，用 REST 取 run 的 jobs/结论）
cd /d/Code/AideanBotHot && python -X utf8 "$TEMP/s59/read_ci_5002410.py" <full-40-char-sha>

# 3) 静态核对
grep -n "告警未启用|告警已启用|依赖未就绪|未知" apps/web/e2e/admin.spec.ts
grep -n "first()" apps/web/e2e/admin.spec.ts
```

## 8. 证据路径

`docs/06_validation/evidence/EVD-V25-74/`

## 9. 允许修改

- `apps/web/e2e/admin.spec.ts`（**仅 `:271` 一条断言的实参**）
- `docs/06_validation/evidence/EVD-V25-74/**`

## 10. 禁止修改

- `apps/web/e2e/admin.spec.ts` 的其它任何行（包括 `:268`；它是形态模板，不是本卡的修改对象）
- **禁止 `.first()`**（D-V25-01 / `03` §2.1）——它会让「产品侧双渲染」永远看不见
- `apps/web/components/**`、`apps/web/app/**`（产品侧改渲染属乙案，需产品裁定）
- `apps/api/**`、`packages/contracts/**`、`.github/workflows/ci.yml`
- 不得为了「让本机跑得动」而改 `playwright.config.ts` 的 `testMatch` 或 `retries`

## 11. 依赖与阻塞

- Depends on：无
- Blocks：**STEP-60**（`e2e-real` 的 `E2E` 步里 ⑥ 不绿，60 的读数面就带着一条已知红）
- 阻塞条件：⑥ 在 mock 档仍 `skipped` 且本机无真档前提 ⇒ **停下，只贴读数**，不新造「本机能跑」的说法
- 阻塞条件：收窄后仍 `resolved to 2 elements` ⇒ 说明窄式也命中两处 ⇒ 停手，升级（见 §13）

## 12. 建议执行档位

**sonnet**（D-V25-06）。理由：≤3 行改动 + 一次反向验证，无设计决策。

## 13. 升级条件

- 窄式仍双命中 ⇒ 说明 `<span>` 与 `<p>` 都可能落进窄式词表 ⇒ 升级 **opus** 并走乙案（产品侧是否刻意双渲染，需规划方裁定）
- 反向验证出现「宽式也绿」⇒ 升级：说明该断言的失败条件已被别的改动抹掉，本卡的前提不成立

## 14. 预估规模

小，**< 1 小时**（不含等 CI）。

## 15. 熔断

同一判据 2 轮未过 ⇒ 停手，登 P 号交回（D-14 / D-V24-07 口径）。

## 16. 交接物

`EVD-V25-74/` 要能让一周后的人只看三件事就判断本卡是否真交付：
① `:268` 与 `:271` 两行**逐字相同**；② 宽式状态下该用例**红**的原文；③ `@ci` 里 ⑥ 通过、⑦ 出现的原文。
