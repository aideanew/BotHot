# EVD-V20-45 STEP-45 订阅锚点时钟确定性 · 规划方读数

- 平台 @linux（沙箱，Python 3.12.15，PG16@5547，Redis 8.10.2@6379/6380 本轮补装），2026-10-24 00:26–00:41（Asia/Shanghai）
- 基线：main@7e4c10e（+ STEP-43 提交）

## 1. 现象
| 来源 | 读数 |
|---|---|
| CI@7e4c10e backend job 120525653954（00:22 CST 跑） | `未达标 84.95% ≥ 85.0% 350/412 行 app/services/subscription.py`，`❌ 覆盖率门判红`；pytest 本身 2319 passed |
| 本机全量 #1（无 Redis） | 同 84.95%，350/412 |
| 本机全量 #2（无 Redis，复跑） | 同 84.95%，缺失行集合与 #1 完全相同 |
| 本机全量 #3（补齐 Redis，skip 5→2） | 同 84.95% ⇒ 与 Redis 无关 |

## 2. 根因
缺失行含 `subscription.py:628`（`_next_anchored_run` 中「锚点已过 ⇒ candidate += 1 天」）。既有用例用真实时钟、锚 10/12 点（Asia/Shanghai）；上海时间 0～10 点之间运行时 candidate 永远在未来，628 行走不到。75b212b 的 CI 在白天跑 ⇒ 绿；7e4c10e（纯文档提交）在 00:22 跑 ⇒ 红。

## 3. 修复
新增 `apps/api/tests/test_subscription_anchor_clock.py`，冻结 `app.services.subscription.datetime.now`：今日未到、已过顺延、恰在整点顺延、未知时区回落 UTC、无锚即现在，共 5 条。不改业务代码、不改阈值。

## 4. 读数（修后）
| 项 | 读数 |
|---|---|
| 专项 + `test_p2_subscription.py` 带 term-missing | 628 不在缺失列 |
| 本机全量 #4（00:38，同一凌晨时段） | **2331 passed / 2 skipped / 4 deselected / 0 failed**，202.21s |
| `check_module_coverage.py` | `达标 85.68% 353/412 subscription.py`；TOTAL 88.41%；`✅ 全部模块与全局达标` |
| ruff check / format --check（新文件） | 通过 |

## 5. 待回填
@ci 三绿：`s45_ci.md`（规划方）
