# STEP-59 真后端 e2e 骨架档（REQ-F-008 四屏）

> 基线 main@12c87e9｜状态：⬜｜裁决 D-V22-01/02/04

| 字段 | 内容 |
|---|---|
| 1 归属 | 规划方（opus）｜切片 S-E2E-1 |
| 2 来源 | REQ-F-008（`product-requirements.md:74`）、P-88、D-V21-06 |
| 3 目标 | CI 新 job `e2e-real` 中 `admin.spec.ts` 四屏组（⑤⑥⑦）执行数 3、跳过 0、失败 0 |
| 4 输出 | S59.0 探针读数（代码层答案见 01 F8，@ci 实跑确认）；收编 `apps/api/scripts/qa_seed_sessions.py` 作种子（不另写）；`scripts/e2e/run_real_backend.sh`（uvicorn 显式 `SESSION_STORE_BACKEND=redis`，F7）；`playwright.config.ts` 增 `real` project；`ci.yml` 新 job（非阻塞） |
| 5 验收 | ① S59.0 读数入证并写明走 A 或 B ② 新 job 首跑：⑤⑥⑦ 3 passed / 0 skipped ③ `git diff 12c87e9 -- apps/api/app` 为空 ④ 会话来自 `qa_seed_sessions.py`、job env 含 `SESSION_STORE_BACKEND=redis` 与 redis service（grep 判） ⑤ job 时长入证 |
| 6 允许修改 | `scripts/e2e/**`、`apps/web/playwright.config.ts`、`apps/web/e2e/admin.spec.ts`（仅开关与 storageState）、`.github/workflows/ci.yml`（新增 job 段）、`docs/06_validation/evidence/EVD-V22-59/**`、本卡与卡表 |
| 7 禁止修改 | `apps/api/app/**`、`apps/web/lib/**`、`packages/contracts/**`、迁移、`mock-routes.ts` |
| 8 规模/档位 | ≈1 人日｜opus（新增 CI 环境属跨模块集成） |
| 9 熔断 | 同判据 2 次 FAIL ⇒ 停；方案 A、B 均不通 ⇒ 登 P-130 |
| 10 验证命令 | `bash scripts/e2e/run_real_backend.sh && cd apps/web && E2E_REAL_BACKEND=1 pnpm exec playwright test --project=real e2e/admin.spec.ts` |
| 11 证据 | `docs/06_validation/evidence/EVD-V22-59/` |
| 12 依赖 | 无｜Blocks：60、62 |
| 13 阻塞条件 | CI runner 无法同时起 PG + Redis service |
| 14 升级条件 | 需要改产品代码才能放行 ⇒ 停，交回裁决（违反 D-V22-02） |
| 15 档位理由 | 首次引入真后端 CI 环境，失败形态多 |
| 16 规模 | 中，>2 小时 |
