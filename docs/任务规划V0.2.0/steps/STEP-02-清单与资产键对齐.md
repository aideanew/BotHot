---
id: STEP-02
title: 清单与资产键对齐 + 清单状态机
priority: P0
depends: STEP-01（canonical key 已合入）；裁决 D-V2-02（S2.2 起）、D-V2-06（S2.5）
parallel_with: STEP-03（`manifest.py::_map_row` 串行：S2.3.1 先合入）
estimate: 1.5 人日
---

# STEP-02 清单与资产键对齐

## 目标
已成功入库的文章不再被 Diff 判为新增；Job 终态后下一轮不重复入列；空轮询退避恢复生效（REQ-F-006）。

## 依据（02 §D-02）
- Manifest 键 = `workUuid`（`manifest.py::_map_row`、`entities.py:108`）；Asset 键 = `_article_key(url)`（`kb.py:432`）；Diff 按 `external_id` 直比（`subscription.py:806-822`）。
- 探针 P-2：`已 READY 入库后 Diff 仍判为新增篇数 = 1`。
- `ArticleManifest.status` 无任何推进代码：`grep -rn "MANIFEST_STATUS\|manifest.status\|\.status = \"INGESTED\"" apps/api/app` 仅定义处。
- 夹具掩盖：`tests/test_scheduler.py::_seed_manifests`（`:188-210`）令 `external_id == _article_key(url)`。

## 允许修改
`apps/api/app/models/entities.py`（仅 `ArticleManifest`、`JobItem` 两类）、`apps/api/alembic/versions/<新修订>.py`、`apps/api/app/services/manifest.py`（仅 `_map_row` 与 `_apply_update` 的字段清单）、`apps/api/app/services/subscription.py`（仅 `_compute_new_manifests`、`_populate_job_items`）、`apps/api/app/repositories/job.py`（仅 `JobItemRepository.create` 增参）、`apps/api/app/services/job_worker.py`（仅 `_drain_items` 的结果回写）、`apps/api/scripts/mark_ingested_manifests.py`（新）、`apps/api/tests/test_manifest_asset_alignment.py`（新）、`apps/api/tests/test_manifest_state_machine.py`（新）、`docs/06_validation/evidence/EVD-V2-02/**`
## 禁止修改
`kb.py`、`providers/**`、`scheduler.py`、`tests/test_scheduler.py`（夹具修正属 STEP-09.2，须在本 STEP 合入后）。

## 原子任务

| 编号 | 类型 | 动作 | 验收命令 |
|---|---|---|---|
| S2.1.1 | 🔴 | `test_manifest_asset_alignment.py::test_ready_asset_excluded_from_diff`：manifest `external_id`=32 位 hex、url=真实长链；资产 `external_id=canonical_article_key(url)`、READY ⇒ Diff 为空（探针 P-2 转正） | 改前 FAIL（返回 1） |
| S2.1.2 | 🔴 | 同文件 `test_no_reenqueue_after_job_terminal`：跑一轮 → 置 READY + Job SUCCEEDED → 再跑一轮 ⇒ Job 数不变、`consecutive_empty_syncs` +1 | 改前 FAIL |
| S2.2.1 | 🗄 | 新修订（`down_revision='ab1005w5b'`）：`article_manifests.article_key VARCHAR(128) NOT NULL DEFAULT ''`、`ix_manifest_source_article_key(source_id, article_key)`；`job_items.manifest_id VARCHAR(36) NULL REFERENCES article_manifests(id) ON DELETE SET NULL`、`ix_job_items_manifest_id` | `alembic upgrade head` rc=0 |
| S2.2.2 | 🗄 | 同修订 Python 段：分批 1000 回填 `article_key = canonical_article_key(url)`（url 为空保持 ''） | 隔离库造 3 行后升级，`SELECT count(*) FROM article_manifests WHERE article_key=''` = url 为空的行数 |
| S2.2.3 | ✅ | 迁移往返 + 单头 | `alembic upgrade head && alembic downgrade -1 && alembic upgrade head && test $(alembic heads | wc -l) -eq 1` |
| S2.3.1 | 🛠 | `_map_row` 输出 `article_key`；`_apply_update` 的可变字段加入 `article_key` | `pytest tests/test_manifest_sync.py -q` 绿 |
| S2.3.2 | 🛠 | `_populate_job_items` 传 `manifest_id=m.id`；`JobItemRepository.create(..., manifest_id=None)` | 新增断言：JobItem.manifest_id 非空 |
| S2.4.1 | 🛠 | Diff：`ArticleManifest.article_key != ''` 且 `article_key.not_in(READY 资产 external_id)`；在途子查询改按 `article_key`（经 `JobItem.manifest_id` 关联）；同一 `article_key` 多条清单行（多渠道发现同篇）用 `DISTINCT ON (article_key)` 只取最早一行 | S2.1.1 绿；新增单测：两条同 article_key 清单 ⇒ 只建 1 个 JobItem |
| S2.4.2 | 🛠 | 状态机：入列置 `ENQUEUED`；`_drain_items` 成功 → `INGESTED`、永久失败 → `FAILED`（经 `manifest_id`，空则跳过）；常量集中到 `manifest.py`（`MANIFEST_STATUS_*`） | `test_manifest_state_machine.py` 4 例：入列/成功/永久失败/manifest_id 为空 |
| S2.4.3 | 🛠 | Diff 只取 `status='DISCOVERED'`；另加"自愈"：`ENQUEUED` 且其 JobItem 所属 Job 已终态而自身非 SUCCEEDED 的行回退 `DISCOVERED` | S2.1.2 绿；自愈单测 1 例 |
| S2.5.1 | 👤🗄 | `mark_ingested_manifests.py --dry-run|--apply`：`article_key` 命中 READY 资产的清单行置 `INGESTED` | 隔离库单测 + 生产 dry-run 报告入 EVD |
| S2.6.1 | ✅ | 全量回归 + 探针 | `pytest tests -q`；`evidence/probe_reenqueue_loop.py` 输出 `= 0`（探针需同步改为写 `article_key`，在 EVD 中附改后版本） |

## 完成定义
S2.1.* 绿；迁移往返绿；生产 dry-run 报告入 EVD；`tests/test_scheduler.py` 在本 STEP 合入后仍绿（如因夹具假设变红，属预期，由 STEP-09.2 修正——两者须同一合并窗口）。

## 回滚
`alembic downgrade -1` 删除两列；代码 `git revert`；`mark_ingested_manifests` 输出变更 CSV 用于还原。

## 风险
- `manifest_id` 回写依赖 worker 版本：滚动发布期间旧 worker 不回写 ⇒ 由 S2.4.3 自愈兜底，且 S2.4.1 的键对齐保证即使不回写也不会重复入列。
- `ON DELETE SET NULL` 保证删除订阅/清单不会级联删除 JobItem 历史。
