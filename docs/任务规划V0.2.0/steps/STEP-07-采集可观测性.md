---
id: STEP-07
title: 采集可观测性
priority: P2
depends: STEP-03（计数字段）、STEP-04（registry 结构）
parallel_with: STEP-08（除 manifest.py）
serial_constraints: S7.1.1/S7.1.2 中对 manifest.py 的改动晚于 S8.1.2
estimate: 1 人日
---

# STEP-07 采集可观测性

## 目标
"为什么没采到"可以在指标、告警与后台页面三处被直接回答；D-03 这类"整页全 skip"不再静默。

## 依据
- D-03 发生时日志只有一行 `new=0 … skip=N`（`manifest.py:223-237`），无告警。
- `GET /api/v1/admin/discovery/channels`（`api/v1/admin.py:467`）前端零消费（`grep -rln discovery apps/web --include=*.ts*` 为空）。
- 指标模块 `core/metrics.py` 已存在（Prometheus `/metrics`）。

## 允许修改
`apps/api/app/core/metrics.py`、`apps/api/app/services/manifest.py`（仅日志/指标/告警调用）、`apps/api/app/providers/discovery/registry.py`（仅 `describe_channels`）、`apps/api/app/core/alerting.py`（仅新增告警类型）、`apps/web/app/admin/**`（新增面板）、`apps/web/lib/api/admin.ts`、对应测试
## 禁止修改
采集业务逻辑（Diff、入列、入库）。

## 原子任务

| 编号 | 类型 | 动作 | 验收命令 |
|---|---|---|---|
| S7.1.1 | 🛠 | 指标：`bothot_discovery_calls_total{channel,outcome}`、`bothot_manifest_rows_total{channel,result}`（new/updated/unchanged/skipped/filtered/id_fallback）、`bothot_paid_calls_total{channel,decision=allowed|denied}` | 单测：一次 `sync_source` 后 `/metrics` 文本含对应样本 |
| S7.1.2 | 🔴🛠 | 一页 `skipped == len(rows) > 0` ⇒ `logger.error` + `alerting.emit("discovery_rows_unusable", channel=…)`（按渠道 1 小时节流） | 单测：全 skip 页触发 1 次；第二次同小时不重复 |
| S7.1.3 | 🛠 | `describe_channels` 每渠道增 `lastSuccessAt`、`lastError`（来自进程内滑动记录；多进程下标注"本进程视角"） | 单测 |
| S7.2.1 | 🛠 | 前端 `/admin` "发现渠道"只读表：名称/启用/可用/原因/最近成功/最近错误/默认渠道 | vitest 3 例（加载/空/错误态） |

## 回滚
纯增量；`git revert`。
