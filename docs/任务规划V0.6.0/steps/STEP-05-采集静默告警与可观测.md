# STEP-05 采集静默告警与可观测

| 项 | 值 |
|---|---|
| 里程碑 | M1 |
| 档位 | sonnet |
| 规模 | 小（约 1 人日，面板另 0.5） |
| 依赖 | STEP-03（id_fallback）、STEP-04（manifest.py 写权） |
| 裁决 | — |
| 剩余原子任务 | 6（👤 0） |
| 所有权（写） | W：app/core/metrics.py、alerting.py；app/services/manifest.py（计数埋点）；app/providers/discovery/registry.py（describe_channels 字段）；tests/test_discovery_silence_alert.py（新）；apps/web 只读面板（COULD） |
| 基线 | main@a9b194d |

## 1. 目标与可证伪验收
- 发现链路 4 个指标族上线：调用结果、清单行结果（含 dropped/fallback）、页全跳过、最近成功时间。
- 新告警：某源连续 N 轮“调用成功但 0 行入清单”或“整页全丢弃” ⇒ 一天内告警一次（幂等）。
- 对 P0-3 的回放：在 STEP-03 修复前的代码上该告警必触发（可证伪）。

## 2. 证据链（现状）
- alerting.py:71/:81/:87 只有心跳/积压/推送连败；metrics.py:55-80 六族无采集维度。
- `_map_row → None` 无计数无日志（manifest.py:144-146）。

## 3. 执行逻辑穿透
sync_source 每页结束：统计 rows_in / mapped / dropped / fallback → 指标 + 若 mapped=0 且 rows_in>0 ⇒ `discovery.page_all_skipped` 事件 → alerting 新探测按 `{source_id}:{channel}:{yyyymmdd}` 幂等投递。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红（写失败测试）｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### S5.1 先红
- **S5.1.1** 🔴 test_discovery_silence_alert.py：喂“全缺 id”页 ⇒ 期望告警 1 次、同日重复不再发

### S5.2 实现
- **S5.2.1** 🛠 metrics.py 增 `bothot_discovery_calls_total{channel,outcome}`、`bothot_manifest_rows_total{channel,result}`、`bothot_discovery_last_success_timestamp{channel}`
  - S5.2.1.1 /metrics 输出含新名
- **S5.2.2** 🛠 sync_source 每页埋点 + all-skipped 事件
  - S5.2.2.1 S5.1.1 转绿
- **S5.2.3** 🛠 alerting 新探测 `check_discovery_silence`，接入 `run_alert_checks`，阈值走 settings
  - S5.2.3.1 单测：阈值内不告警、越阈告警、同日幂等

### S5.3 （COULD）管理端可见
- **S5.3.1** 🛠 `describe_channels`（registry.py:310）增 `lastSuccessAt/lastError`（读指标/心跳，不建表）
- **S5.3.2** 🛠 前端只读面板，覆盖五态（加载/空/正常/降级/错误），vitest

## 5. 测试设计
- 新增约 8 条；指标断言用 prometheus_client registry 读值。

## 6. 停止条件与回滚
- 告警噪声：默认阈值 N=3 轮，可配置；本卡不接外部 IM 渠道以外的投递。

## 7. 交付证据
EVD-V2-05：告警触发/幂等读数、/metrics 片段。

## 8. 完成定义（本卡）
所有权内 diff 与任务一致 ∧ 每个 ✅ 有读数 ∧ 本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 通过 ∧ 推送后 CI 与 Security 均 success（run id 入 EVD）∧ 复审 ≤2 轮（D-14）。
