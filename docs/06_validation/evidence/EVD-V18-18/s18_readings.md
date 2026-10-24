# EVD-V18-18 全站性能基线（STEP-18，执行助手）

平台 @win（Windows 10 x64），时间 2026-10-24（Asia/Shanghai）。
**S18.0 环境自备**：zonky 便携 PostgreSQL 16.15（`%USERPROFILE%\pg16-5547`，非系统服务）于 5547，
库 `bothot`/`bothot_test` 迁移至 `ab1006c2a` 单头；Redis/LangBot/真实 LLM 不在测（指纹详见
`docs/03_solution/design/PERF-baseline-v1.md`）。P-118 的环境阻塞以"自备 PG16@5547"口径解除
（V0.18 增量明写的路径），本卡据此开工。

## 交付物

- `scripts/perf_baseline.py`（新增测量 harness；`git diff` 对 `apps/api/app/**` **零命中**——本卡只测不改）
- `apps/api/tests/test_perf_probe.py`（新增往返计数用例，连库；本机对自备 5547 实跑 **1 passed**）
- `docs/03_solution/design/PERF-baseline-v1.md`（指纹、读数、可感性证明、前提与局限）
- 本目录 6 组原始读数（base/rerun/warm1/warm2/inject25/smoke 的 JSON+MD）

## 读数（n=50/探测）

| 指标 | p50 | p95 | SLA 目标 | 结论 |
|---|---|---|---|---|
| API /spaces | 8.08–12.82ms | 10.60–15.59ms | <500ms | ✅ |
| API /hot/topics | 5.41–9.80ms | 8.27–11.82ms | <500ms | ✅ |
| API /jobs | 5.69–8.74ms | 8.37–17.31ms | <500ms | ✅ |
| 单篇入库（服务层） | 26.67–29.95ms | 32.36–42.21ms | <30s | ✅ |
| Feed /hot/feed | 6.15–12.74ms | 8.62–21.13ms | <100ms | ✅ |
| 首 Token（录制回放） | 0.76–0.96ms | 1.58–3.96ms | <3s | 桩回放时延，真实 RTT 不在测（逐数标注） |

## S18.2.1 可感性证明（注入 25ms 对照，tag=inject25）

| 指标 | 基线 p50 | 注入后 p50 | 位移 | 判定 |
|---|---|---|---|---|
| API /spaces | 11.31 | 48.65 | +37.3 | ✅ 同向 |
| API /hot/topics | 8.42 | 37.59 | +29.2 | ✅ |
| API /jobs | 8.60 | 34.50 | +25.9 | ✅ |
| 单篇入库（short） | 29.15 | 50.07 | +20.9 | ✅ 同向（注入 25 在桩 resolve 内，含重叠方差） |
| Feed | 9.40 | 35.86 | +26.5 | ✅ |
| 首 Token | 0.94 | 33.06 | +32.1 | ✅（注入在首帧前） |

**四条全部可感 ⇒ 无下线指标。**

## 复跑偏差（判据 ≤15%，同命令同环境）

- p50：warm1 vs warm2 全指标 ≤12.9% ✅（spaces 12.82→11.17 最大）。
- p95：绝对抖动 ±2ms 级（n=50 的 p95 取第 48 位，单点离群即移动——feed 一组 11.46→21.13）。
  **抖动来源 = 单点离群 + 冷启动**（冷首跑 API 读比热态高 40–55%，预热两轮后稳定）。
  如实记录：p50 作精确判据；p95 带 ±2ms 级说明（与 P-104 的"覆盖率不能当精确判据"同族纪律）。

## S18.3.1 / S18.3.2

- **S18.3.1**：D-V18-14 已裁定**不开优化卡**——基线全面高于目标线（余量 4.7×–700×），
  无候选优化立项；裁定与理由留在 decision-log（D-V18-14 原文）与本文件。
- **S18.3.2**：基线已写入 `docs/04_engineering/roadmap.md` 的"性能基线"节（S18.3.2 的 V0.18 改口径落点）。

## 前提与局限（摘要，全文见 PERF-baseline-v1.md）

同进程测量（无网络栈）、Redis/LangBot/真实 LLM 不在测、数据集规模小（空间 30/热点 60/Feed 100）、
未引入任何优化（app/** 零命中）。p95 的单点离群敏感如实记录。


## @ci（推送后回填，2026-10-24 22:4x @win，Asia/Shanghai）

交付 head `88d7518` 三绿，attempt 1：

| 工作流 | run id | 结论 |
|---|---|---|
| CI | 40053307363 | success（**2370 passed** / 6 skipped / 4 deselected——比 STEP-37 交付头 +1 = 本卡 `test_perf_probe` 在连库环境真实执行通过） |
| CI-Windows | 40053307366 | success（1693 passed / **683 skipped** / 4 deselected；skip 门禁 **683/683 过**） |
| Security | 40053307379 | success |

Windows skip 账目（现读日志）：本卡 +1 连库用例落在「PG-DSN-未设置」族（前两交付头稳定 570 → 本 run 571），
总量 682→683 **恰等于基线 683** ⇒ 按 D-V10-11（抬到测量值、不留余量）基线无需再动。
顺带更正一处旧证据：`EVD-V18-36` 把 52e8e0a 的 Windows 门禁写成"683/683"，实读为 **682**/683
（+4 预测实落 +3），该文件已随本批更正。

完成判据对照：四条 SLA 各有 p50/p95 + 指纹 + 可复跑命令 ✅；可感性四条全证明、无下线指标 ✅；
复跑偏差 p50 ≤13%（p95 单点离群敏感已说明抖动来源）✅；PERF 文档写明前提与局限 ✅；
本卡零优化改动（`git diff` 对 `apps/api/app/**` 零命中；新增为 scripts/ 与 tests/ 与 docs/）✅；三绿 ✅。
