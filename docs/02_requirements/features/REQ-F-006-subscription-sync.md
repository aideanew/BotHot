---
id: REQ-F-006
type: requirement
title: 整号订阅与增量同步
status: active
owner: product
实现度: 已实现（V0.13.0 基线里「STEP-04 行为层未做」那句已过期，判据见正文）
验收锚:
  - apps/api/tests/test_manifest_sync.py
  - apps/api/tests/test_manifest_state_machine.py
  - apps/api/tests/test_manifest_asset_alignment.py
  - apps/api/tests/test_p2_subscription.py
  - apps/api/tests/test_r02_subscription_lifecycle.py
  - apps/api/tests/test_rss_subscription.py
  - apps/api/tests/test_rss_provider.py
  - apps/api/tests/test_channel_routing.py
  - apps/api/tests/test_identifier_resolver.py
  - apps/api/tests/test_source_identifiers.py
  - apps/api/tests/test_scheduler.py
  - apps/web/tests/r024-subscription-lifecycle.spec.tsx
最后核验 commit: 8367b77（2026-10-21，STEP-04 S4.5.1 复跑；后续由 STEP-06 的 E2E 续判）
---

# REQ-F-006 整号订阅与增量同步

## 需求条目

- 订阅一个公众号的全部文章
- Manifest Diff 水位机制
- 固定时点锚 / 滑动窗口
- 空轮询退避
- **验收**：增量同步只拉新文章，水位正确推进

## 实现度判据

| 判据 | 出处与原判词 |
|---|---|
| Diff 按规范键减（不是按渠道内 id 减） | `test_manifest_asset_alignment.py::test_ready_article_is_not_re_enqueued`（P-2 探针转正）；`test_scheduler.py::test_incremental_sync_creates_job_with_diff_items` 于 2026-10-22 补上反向变异读数（改回按 `external_id` 减 ⇒ 该用例红） |
| 清单四态可回写且非法边被拒 | `test_manifest_state_machine.py`；`docs/任务规划V0.7.0/04-剩余可执行大纲体系.md` §4.3 的 F-006 判据锚逐字对应 |
| 退避与水位算术 | `test_scheduler.py`（22 条：触发窗口 / 退避序列 / 锚定整点 / SKIP LOCKED 并发认领） |
| RSS 一等信息源 | `test_rss_provider.py`、`test_rss_subscription.py`（含 D-V2-03 外链只发现不入库） |

## 一条过期读数的处理（卡面明令不得照抄）

`docs/任务规划V0.13.0/01-事实基线与进度.md` 的 X-8 写「STEP-04 行为层（Diff 与四态）**未做**」——
那是 61358c3 时点的状态。现读：STEP-04 S4.5.1 已复跑并留读数（见执行记录与
`docs/06_validation/evidence/EVD-V17-04/s04_5_1_readings.md`），STEP-06 又把整条链路
端到端跑通。本文件按现读写，历史那份不改（历史规划结论属禁止修改面）。
