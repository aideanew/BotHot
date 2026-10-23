# STEP-45 订阅锚点时钟确定性（main 红灯修复）

> 基线 main@7e4c10e｜状态：🟡 规划方已交付，待 @ci 三绿｜版本 V0.20.0

| 字段 | 内容 |
|---|---|
| 1 归属 | **规划方**（D-V20-06：main 当前红，阻塞所有后续卡的"三绿"判据） |
| 2 验收者 | 执行助手在 STEP-44 S44.1 一并复查 |
| 3 难度 / 里程碑 | 中 / M4 |
| 4 来源 | P-116（规划方 V0.20.0 在 CI@7e4c10e backend job 日志与本机两次复跑同读到 `subscription.py 84.95% < 85%`） |
| 5 目标 | 模块覆盖率门的读数与 CI 几点跑无关 |
| 6 输入 | `app/services/subscription.py::_next_anchored_run`（第 610–629 行） |
| 7 输出路径 | 新增 `apps/api/tests/test_subscription_anchor_clock.py`（5 条，冻结 `datetime.now`）；证据 `docs/06_validation/evidence/EVD-V20-45/` |
| 10 命令 | `cd apps/api && python -m pytest -q tests/test_subscription_anchor_clock.py tests/test_p2_subscription.py --cov=app.services.subscription --cov-report=term-missing`（第 628 行不得出现在缺失列） |
| 12 允许修改 | 第 7 格所列 |
| 13 禁止修改 | 业务代码（本卡不改 `subscription.py`）；覆盖率阈值（D-V18-07） |
| 14 依赖 | 无 |
| 15 档位 | opus |
| 16 规模 | ≈0.2 人日（已完成） |

## 根因
既有用例用真实时钟、锚 10/12 点（Asia/Shanghai）。上海时间 0～10 点间运行时，"锚点已过 ⇒ 顺延一天"的第 628 行走不到，`subscription.py` 恰少 1 行（350/412 = 84.95%）。7e4c10e 的 CI 在 00:22 CST 跑 ⇒ backend 判红；75b212b 在白天跑 ⇒ 绿。与 7e4c10e 的改动（纯文档）无关。

## 三级任务
1. [x] **S45.1** 定位：CI 日志 + 本机两次复跑（含补齐 Redis 后）同为 84.95%；缺失行含 628
2. [x] **S45.2** 新增 5 条冻结时钟用例：今日未到、已过顺延、恰在整点顺延、未知时区回落 UTC、无锚即现在
3. [x] **S45.3** 本机全量 + 模块覆盖率门
4. [ ] **S45.4** @ci 三绿（规划方回填）

## 遗留（交 STEP-35，见下）
全仓其它"读墙钟"的覆盖面未普查。STEP-35（测试确定性）加项 **S35.6**：用 `rg "datetime.now\(|time.time\(" app/` 列出业务代码读墙钟的点，逐个确认有冻结时钟用例覆盖两侧分支；缺的补用例，不改业务代码。
