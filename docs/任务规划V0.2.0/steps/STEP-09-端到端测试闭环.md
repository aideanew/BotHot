---
id: STEP-09
title: 端到端测试闭环与夹具纠偏
priority: P0（收口）
depends: S9.2 与 STEP-01/02 同一合并窗口；S9.1 依赖 STEP-02、STEP-03；S9.1.2 依赖 STEP-04
estimate: 1.5 人日
---

# STEP-09 端到端测试闭环

## 目标
用一条不依赖外网的测试，把"发现 → 清单 → Diff → Job → Worker → 入库 → 第二轮不重复"完整走通；把那些按错误假设构造、因而掩盖缺陷的夹具改成真实形态；让覆盖率门禁覆盖采集模块。

## 依据
- 现有测试各测一段、无接缝测试：`manifest.py` 94% 而 4 client ~18%（01 §1.2.3）。
- 夹具掩盖：`tests/test_scheduler.py::_seed_manifests`（`:188-210`）令 `external_id == _article_key(url)`；`:530` 直接用清单 id 造 READY 资产；`tests/test_p0_asset_cache.py:26` 用非真实参数名 `?biz=`。
- CI 覆盖率门：`.github/workflows/ci.yml:127` `--cov-fail-under="$COV_BASELINE"`；本轮实测总覆盖率 79%。

## 允许修改
`apps/api/tests/test_e2e_collection.py`（新）、`apps/api/tests/test_scheduler.py`（仅夹具 `_seed_manifests` 与 `:520-545` 段）、`apps/api/tests/test_p0_asset_cache.py`（仅 `URL_A` 与新增长链用例）、`.github/workflows/ci.yml`（仅覆盖率阈值与新增模块覆盖率检查步骤）、`scripts/check_module_coverage.py`（新）
## 禁止修改
`apps/api/app/**`（本 STEP 只写测试与门禁；测出缺陷回到对应 STEP 修）。

## 原子任务

| 编号 | 类型 | 动作 | 验收命令 |
|---|---|---|---|
| S9.1.1 | 🛠 | `test_e2e_collection.py::test_redfox_end_to_end`：MockTransport 回放 RedFox 两页样本（含长链与短链）→ `IncrementalScheduler.run_once()` → `JobWorker.run_once()`（真实 `KnowledgeBaseService`，LangBot 用 `test_langbot` 桩，直抓用桩 fetcher 按 URL 返回不同 HTML）⇒ 资产数 = 清单数、键全部 canonical、清单全部 `INGESTED`；推进时钟再跑一轮 ⇒ 0 新 Job、`consecutive_empty_syncs==1` | 在 STEP-01/02/03 合入前运行应 FAIL（作为三者的联合反证），合入后 PASS |
| S9.1.2 | 🛠 | 参数化到 dajiala/justoneapi/wellbyte/rss（各自样本 + identity）；tikhub 随 U-04 结论 | 每参数一条 PASS |
| S9.2.1 | 🛠 | `_seed_manifests`：`external_id=uuid4().hex`、`url` 用 `fixtures/wechat_urls` 的真实形态（长链为主）；`:530` 段 READY 资产 `external_id=canonical_article_key(url)` | `pytest tests/test_scheduler.py -q` 绿（STEP-02 合入后） |
| S9.2.2 | 🛠 | `test_p0_asset_cache.py::URL_A` 的 `?biz=` 改 `__biz=`；新增 `test_p0_two_long_links_distinct_assets` | 绿 |
| S9.3.1 | 🛠 | `scripts/check_module_coverage.py --xml coverage.xml --min app/providers/article_sources=80 --min app/services/article_detail_fallback.py=85 --min app/services/manifest.py=90`；CI backend job 追加一步 | 反证：在 61739f0 上运行 rc≠0（4 client <25%） |
| S9.3.2 | 🛠 | `COV_BASELINE` 上调到 M1 完成时实测值（向下取整） | CI 绿 |

## 完成定义
S9.1.1 与 S9.1.2 全绿；S9.3.1 在 CI 中生效。

## 回滚
测试与门禁文件 `git revert`。
