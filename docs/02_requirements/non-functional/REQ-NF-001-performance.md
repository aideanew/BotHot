---
id: REQ-NF-001
type: requirement
title: 性能 SLA
status: active
owner: product
实现度: 部分（四条里只有「单篇入库」拿到服务层读数；API / 首 Token / Feed 三条无测量值）
验收锚:
  - apps/api/tests/perf/test_collection_perf.py
最后核验 commit: 3491054（2026-10-23，STEP-11 交付提交）
---

# REQ-NF-001 性能 SLA

## 需求条目（四条）

| # | 条目 | 有无测量值 | 读数与出处 |
|---|---|---|---|
| 1 | API 响应 < 500ms（非 LLM 调用） | **无** | 待 STEP-18（全站性能基线）；本卡明确不代替它填数 |
| 2 | RAG 问答首 Token < 3s | **无** | 需真实 LLM 凭据或录制回放；STEP-18 阻塞条件 ① 要求这种情况下标 `NOT_MEASURED`，不得用超时值冒充延迟 |
| 3 | 文章入库单篇 < 30s | 服务层有值 | `test_collection_perf.py::test_single_ingest_percentiles`：n=50，**p50 17.7ms / p95 21.1ms / max 85.5ms**（抓取与 LangBot 均为桩） |
| 4 | Feed 分页查询 < 100ms | **无** | 同条目 1 |

## 采集切片另有两条基线（不是 SLA，是形状）

- 一页 20 行的清单写入 = **43 条 SQL**，且本地 backlog 0 / 2000 两档逐字相等 ⇒ O(页)，
  不随存量增长（`test_sql_statements_per_page`）。
- `_compute_new_manifests` 在 10k 清单 / 1k Job 下服务端 **Execution Time 15.310ms**，
  计划里 `Bitmap Heap Scan on jobs` 的 `Rows Removed by Filter: 999` 是唯一实测到的坏形状
  （前缀 LIKE 用不了 `idempotency_key` 唯一索引）。

## 三条必须写在前面的局限

1. 条目 3 的数字**不能**用来宣布 REQ-NF-001 达标：它量的是服务层自身，真实网络抓取、
   微信限流等待、LangBot 索引耗时都不在内。
2. `perf` 用例默认被 `apps/api/pyproject.toml` 的 `addopts = ["-m", "not perf"]` 摘除，
   CI 里是 `4 deselected`（不是 skip）⇒ 这四条数字只在有 PG 的机器上手动取，
   属**手工读数**而非门禁读数，换机器需复跑。
3. 「无基线不得立优化卡」（D-V3-08）现在对**采集切片**成立，对 API/Feed/首 Token 仍不成立
   ——那三条既无基线也无卡在做，唯一承接卡是 STEP-18。
