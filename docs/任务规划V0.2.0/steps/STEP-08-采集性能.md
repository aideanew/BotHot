---
id: STEP-08
title: 采集性能
priority: P2
depends: STEP-02（manifest/job_items 结构定型）
parallel_with: STEP-07（除 manifest.py）
serial_constraints: S8.1.2 先于 S7.1.1/S7.1.2 对 manifest.py 的改动
estimate: 1 人日
---

# STEP-08 采集性能

## 目标
清单写入从"每行 2 次往返"降到"每页 1 条语句"；Diff 查询在万级清单、千级 Job 下走索引；给 REQ-NF-001 留下采集侧第一组可复测数字。

## 依据
- D-10：`ManifestSyncService._upsert` 每行 `SELECT` + `SAVEPOINT flush`（`manifest.py:251-266`）。
- D-11：`Job.idempotency_key.like(f"sync_account:{subscription_id}%")`（`subscription.py:812`）；`jobs.idempotency_key` 普通唯一索引（`entities.py:202`），默认 collation 下 btree 不服务前缀 LIKE（待 EXPLAIN 证实）。
- V0.1.0 仅有通知查询 EXPLAIN 留证，无采集侧基线。

## 允许修改
`apps/api/app/services/manifest.py`（`_upsert`/`sync_source` 写入段）、`apps/api/app/services/subscription.py`（`_compute_new_manifests`、`_create_sync_job`）、`apps/api/app/models/entities.py`（`Job` 增列）、`apps/api/alembic/versions/<新修订>.py`、`apps/api/scripts/bench_collection.py`（新）、新测试、`docs/06_validation/evidence/EVD-V2-08/**`
## 禁止修改
provider、kb、scheduler。

## 原子任务

| 编号 | 类型 | 动作 | 验收命令 |
|---|---|---|---|
| S8.1.1 | 🔴 | 测试：用 SQLAlchemy `before_cursor_execute` 计数，`sync_source` 写 1 页 20 行的语句数 ≤ 3 | 改前 FAIL（≥40） |
| S8.1.2 | 🛠 | `pg_insert(ArticleManifest).values(rows).on_conflict_do_update(index_elements=[source_id, external_id], set_=…, where=<字段有变化>).returning(ArticleManifest.external_id, literal_column("xmax = 0"))`；按返回区分 discovered/updated，未返回者计 unchanged | S8.1.1 绿；`test_manifest_sync.py` 全绿（计数语义不变） |
| S8.2.1 | ✅ | `bench_collection.py`：隔离库造 10k 清单/1k Job/5k 资产，`EXPLAIN (ANALYZE, BUFFERS)` Diff 查询，输出入 EVD-V2-08 | 文件存在且含 Planning/Execution Time |
| S8.2.2 | 🗄 | 若 S8.2.1 显示 `jobs` 顺扫：`jobs.subscription_id VARCHAR(36) NULL` + 索引，`_create_sync_job` 写入，Diff 改等值过滤；回填自 payload JSON | EXPLAIN 显示 Index Scan；迁移往返绿 |
| S8.3.1 | ✅ | 前后对比（语句数、Diff 执行时间）写入 EVD-V2-08，并在 `docs/02_requirements/product-requirements.md` REQ-NF-001 下引用（文档改动属 STEP-11） | EVD 含两组数字 |

## 回滚
`git revert`；S8.2.2 迁移可 downgrade。
