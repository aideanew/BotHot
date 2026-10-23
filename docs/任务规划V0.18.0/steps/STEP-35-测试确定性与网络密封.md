# STEP-35 测试确定性与网络密封

> 基线 main@f86811e｜状态：⚪ 未开始｜版本 V0.18.0

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
1. [ ] **S35.1** P-104：定位 `manifest.py` 覆盖抖动的那一行（对比两次覆盖报告的 missing 行），改成确定覆盖；判据：同树连跑 3 次，模块门九行读数逐字相同
2. [ ] **S35.2** P-98：`subscription.py` 补用例，CI 余量 ≥ 5 行（记下 covered/total）
3. [ ] **S35.3** P-52/P-71 并发用例改为事件序判据（用 asyncio.Event 记录开始/结束交叠），不用墙钟；P-53/P-63：structlog 全局配置改由 fixture 设置并在 teardown 还原，`capture_logs` 用例在窗内首次取 logger
4. [ ] **S35.4** P-105（D-V18-08）：`vitest.config.ts` 钉 `environmentOptions.happyDOM.url = 'http://localhost:3200/'`；setup 把未桩的 `fetch` 换成直接抛错；跑一遍，原 39 处 `AggregateError` 对应的用例逐条补桩；反证：删一条桩该用例必须红

## 完成判据（全部机器可判）
- 连跑 3 次模块门读数相等（三份原文入证据）
- vitest 输出 `ECONNREFUSED` 计数 0，且 415（或现数）全绿
- 三绿

## 熔断
连续 2 轮验收 FAIL ⇒ 停卡交回规划方（rounds-check 机器执行，口径见 D-V18-16）。前提与现读不符 ⇒ 先登记 P 号再停，不自改卡面。
