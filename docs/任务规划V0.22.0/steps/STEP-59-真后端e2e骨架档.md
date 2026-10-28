# STEP-59 真后端 e2e 骨架档（REQ-F-008 四屏）

> 基线 main@12c87e9｜状态：✅ 已交付（real 档首跑读数在 @ci 的 `e2e-real` job；本机侧读数、四处静默失效位的处置与"本机不可证"清单见 `EVD-V22-59/s59_readings.md`；08 §2 59.4 的 ②④ 前提冲突登台账 P-131。**第 2 轮（2026-10-28，@ci 首跑真读数回来后开的）**：`e2e-real` 首跑（run 40643109335）红两条 ⇒ ① `admin.spec.ts:101 ① 游客访问 /admin 与 /admin/ops`（同 describe 的 ②-⑦ `6 did not run`）、② `Stop stack` 端口残留。① 的机制由探针钉死：`test.use({storageState: undefined})` **清不掉** project 默认会话（判据是测试服务器实际收到的 `Cookie` 头，不是配置回显；探针 B 仍收到 `probe_session=admin-token`，换成文档化的`{cookies: [], origins: []}` 才为空），artifact 的 `error-context.md` 快照画的正是带着 admin 会话的后台（`QA管理员` + `退出` + `ADMIN CONSOLE`）⇒ 原卡面头注那句「在 1.63 源码里核对过生效路径」是被否证的旧判断。② 的依据是同秒两行 `stopped backend pid=3890` 之后紧跟端口红 ⇒ `kill` 异步，终检紧跟其后把 SIGTERM 释放延迟读成泄漏，改为有界宽限 + 占用者读数，**门没放松**。两处都在本卡第 6 格原文内（`admin.spec.ts` 仅开关与 storageState、`scripts/e2e/**`），授权口径见 07 行与 P-147。本机证不了 stop 与 ① 的真读数（无 docker/PG/Redis，且 git-bash 的 `kill` 按 MSYS pid 发信号、Windows 监听者不死 ⇒ `stopped … pid=` 在本机会谎报），所以这一轮的终判以 @ci 为准；演示态可本机复算且已复算：mock e2e `31 passed / 0 failed`。凭据 `EVD-V22-59/s59_6_round2_storagestate_probe.txt`｜裁决 D-V22-01/02/04

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行助手（opus 档；D-V22-06，原子步与判据见 `08-阶段A执行细则.md` §2，冲突以 08 为准）｜切片 S-E2E-1 |
| 2 来源 | REQ-F-008（`product-requirements.md:74`）、P-88、D-V21-06 |
| 3 目标 | CI 新 job `e2e-real` 中 `admin.spec.ts` 四屏组（⑤⑥⑦）执行数 3、跳过 0、失败 0 |
| 4 输出 | S59.0 探针读数（代码层答案见 01 F8，@ci 实跑确认）；收编 `apps/api/scripts/qa_seed_sessions.py` 作种子（不另写）；`scripts/e2e/run_real_backend.sh`（uvicorn 显式 `SESSION_STORE_BACKEND=redis`，F7）；`playwright.config.ts` 增 `real` project；`ci.yml` 新 job（非阻塞） |
| 5 验收 | ① S59.0 读数入证并写明走 A 或 B ② 新 job 首跑：⑤⑥⑦ 3 passed / 0 skipped ③ `git diff 12c87e9 -- apps/api/app` 为空 ④ 会话来自 `qa_seed_sessions.py`、job env 含 `SESSION_STORE_BACKEND=redis` 与 redis service（grep 判） ⑤ job 时长入证 |
| 6 允许修改 | `scripts/e2e/**`、`apps/web/playwright.config.ts`、`apps/web/e2e/admin.spec.ts`（仅开关与 storageState）、`apps/web/e2e/real.setup.ts`（新建）、`apps/web/.gitignore`（仅加 `e2e/.auth/`）、`.github/workflows/ci.yml`（新增 job 段）、`docs/06_validation/evidence/EVD-V22-59/**`、本卡与卡表 |
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
