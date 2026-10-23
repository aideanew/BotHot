# STEP-35 测试确定性与网络密封

> 基线 main@f86811e｜状态：🔶 第 1 轮已交付（2026-10-24，含 S35.5/S35.6 加项，读数在 `EVD-V18-35/`）｜版本 V0.18.0

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行 Agent-Guard（S35.4 前端部分可同人） |
| 2 验收者 | 规划方 |
| 3 难度 / 里程碑 | 中 / M0 |
| 4 来源 | P-52、P-53、P-63、P-71、P-98、P-104、P-105；D-V18-07、D-V18-08 |
| 5 目标 | 同一棵树连跑结果逐行相同：覆盖率不抖、日志捕获不瞎、并发用例不靠运气；前端单测拨不出网 |
| 6 输入 | `apps/api/tests/test_scheduler.py`（并发用例）；`tests/test_observability.py`；`scripts/check_module_coverage.py:36-48`；`app/services/manifest.py`；`apps/web/vitest.config.ts` 与 setup |
| 7 输出路径 | 上述测试与配置、`app/services/manifest.py`（只为消除非确定分支，不改行为）、`apps/web/tests/**` 的 setup、`docs/06_validation/evidence/EVD-V18-35/`（D-V18-13） |
| 10 命令 | `pytest -q -m "not perf" --cov=app` 连跑 3 次后 `python scripts/check_module_coverage.py`；`pnpm -C apps/web test:unit` |
| 12 允许修改 | 第 7 格所列；`subscription.py` 只许加用例不许改源码（源码归 36） |
| 13 禁止修改 | 任何阈值（D-V18-07 一个都不降）；业务行为 |
| 14 依赖 | 34 |
| 15 档位 | sonnet |
| 16 规模 | ≈1.2 人日 |

## 三级任务
1. [x] **S35.1** P-104：抖动行 = `manifest.py:169`（同树两份 CI missing 集合现读差集）；已用确定输入的 RFC822 无时区用例钉死；三连跑对照见证据 §@ci
2. [x] **S35.2** P-98：补 list_sources/update_source 三发（此前 :246-269 零覆盖）；基线 353/412 余量 2 行，预期 375/412（@ci 回填）
3. [x] **S35.3** P-52/P-71：并行判据改 asyncio.Event 会合点（wait_for 显式超时判红）；P-53/P-63：`clean_logging` teardown 改还回应用配置（先红 2 failed 复现 → 修后双序 33 passed）
4. [x] **S35.4** P-105（D-V18-08）：基址钉 3200 + 未桩 fetch 抛错 setup + 三发常驻反证；415 passed、AggregateError 39→0；删桩变异 1 红/还原 3 绿

## 完成判据（全部机器可判）
- 连跑 3 次模块门读数相等（三份原文入证据）
- vitest 输出 `ECONNREFUSED` 计数 0，且 415（或现数）全绿
- 三绿

## 熔断
连续 2 轮验收 FAIL ⇒ 停卡交回规划方（rounds-check 机器执行，口径见 D-V18-16）。前提与现读不符 ⇒ 先登记 P 号再停，不自改卡面。
