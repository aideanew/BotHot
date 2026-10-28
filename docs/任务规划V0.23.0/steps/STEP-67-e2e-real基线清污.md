# STEP-67 e2e-real 基线清污（P-147 / P-148 余项）

> 基线 main@2f4b115｜状态：**❌ 作废（有裁决行 D-V24-07）**——第 2 轮 @ci `3c4138d`（run `40668413325`）：判据② **通过**（`Stop stack`=success 且 `端口终检 … 空闲；占用者读数：(空)` 逐字在日志，`port_owner()` 契约修复被证实）；判据① 第 2 次红——⑤ 修复成立（✓ 711ms）但 ⑥ 告警状态条 `:271` strict mode violation（P-145→P-152 后第三层被 serial 揭出；⑥ 是旧用例、mock 档 skipped ⇒ 本机结构性不可证）⇒ 按卡面第 9 格与 D-V24-07（仍红 ⇒ 登 P 号、标 ❌ 并交回）**熔断**，登记 **P-158**、交回规划方；第 3 轮预审建议随 P-158 交付｜裁决 D-V23-15、D-V23-16、D-V23-21、D-V24-07｜切片 S-E2E-3｜归属：执行助手（sonnet 档）
> 卡面内容由规划方 2026-10-28 指令原文给出，执行侧代录成文件并逐条核字节——**核出两条按字面不可满足的判据**，处置与本卡实测全在 `EVD-V23-67/s67_readings.md` §2/§3

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行助手｜sonnet 档｜切片 S-E2E-3（新建）｜裁决 D-V23-15/16/21 |
| 2 来源 | P-147、P-148（第二半）、D-V23-15、D-V23-16 |
| 3 目标 | `e2e-real` 的 `E2E` 步与 `Stop stack` 步**双 success**，整 job 绿 |
| 4 输出 | ① `scripts/e2e/run_real_backend.sh`：`stop_all` 的认领判据换成"该 PID 是不是角色端口的监听者"（新 `port_owner_pids()` / `role_port()`），命令行特征降为辅助并加 `*"next-server"*`；`have_ps` 改成探能力；端口终检无条件落一行属主读数 ② `apps/web/e2e/admin.spec.ts`：**只改 ①**，按 `REAL_BACKEND_ENABLED` 分支，real 分支附 `guest-landing-*.txt` 物证 ③ `EVD-V23-67/**` ④ 台账 P-150 + 卡面状态 + `04` §2 卡表新增行 |
| 5 验收 | ① `E2E (real backend, project=real, admin.spec.ts)` = success ② `Stop stack` = success 且日志仍能看到 `占用者读数` 那一行（证明读数没被删）③ mock e2e 无误伤——**按实测口径写**：`31 passed / 11 skipped`（42 条被收集）且 `e2e_rc=0`，与基线同数 ④ `backend` 仍 `2502/6`、`@win` 仍 `1816 + 692` ⑤ `git diff 2f4b115 -- apps/web/middleware.ts apps/web/components apps/web/lib apps/api/app packages/contracts` **为空** ⑥（本机不可证的两条明列为 @ci 项，不以本机通过冒充） |
| 6 允许修改 | `scripts/e2e/run_real_backend.sh`、`apps/web/e2e/admin.spec.ts`（**仅 ①**）、`docs/06_validation/evidence/EVD-V23-67/**`、台账与卡面、`04` §2 卡表 |
| 7 禁止修改 | `apps/web/middleware.ts`、`apps/web/components/**`、`apps/web/lib/**`、`apps/api/app/**`、`packages/contracts/**`、`apps/web/e2e/trunk.spec.ts`、`apps/web/e2e/auth-gate.spec.ts`、迁移 |
| 8 规模/档位 | 小（两处、合计 <30 行）｜sonnet |
| 9 熔断 | 同一判据 2 轮未过 ⇒ 停，登 P 号，不动第 3 轮。升级条件：mock 档 `trunk.spec.ts:53` 或 `auth-gate.spec.ts` 任一红 ⇒ 立刻停手升级（说明 ① 的改动误伤了演示态契约） |
| 10 验证命令 | `@win`：`bash -n scripts/e2e/run_real_backend.sh` → `cd apps/web && pnpm exec tsc --noEmit` → `NEXT_PUBLIC_API_MOCK=true` 产物 + `PORT=3456 pnpm run test:e2e`（mock 档）；`@ci`：`e2e-real` job 的 `E2E (real backend…)` 与 `Stop stack` 两步结论 |
| 11 证据 | `docs/06_validation/evidence/EVD-V23-67/`（`s67_readings.md` + `s67_1_local_stop_shots.txt` + `s67_2_mock_e2e_rerun.txt`） |
| 12 依赖 | 无（P-147/P-148 的余项）｜Blocks：60（读数面归因干净）、62（S62.3 的实测口径） |
| 13 阻塞条件 | 若 CI 上 ① 仍红而落点既不是 `/` 也不是 `/admin` ⇒ 停手交回（说明还有第三种落点，四条不变量之外） |
| 14 升级条件 | 需要动 `middleware.ts` 或任何 `apps/web/components/**` 才能过 ⇒ 停（那是产品裁定，D-V23-15 明令不改） |
| 15 档位理由 | 判据已由裁决定死，剩实现与读数；不涉新设计选择 |
| 16 规模 | 小 |
