# STEP-11 采集性能基线

| 项 | 值 |
|---|---|
| 里程碑 | M2（与 05 并行） |
| 档位 | sonnet |
| 规模 | 小（约 0.5–1 人日） |
| 依赖 | STEP-04 |
| 裁决 | — |
| 剩余原子任务 | 4（👤 1） |
| 所有权（写） | W：apps/api/tests/perf/test_collection_perf.py（新，默认不进全量，标记 perf）；EVD |
| 基线 | main@a9b194d |

## 1. 目标与可证伪验收
- 三个基线数字入档：1 页 20 行清单写入的 SQL 语句数；`_compute_new_manifests` 在 10k 清单/1k Job 下的 EXPLAIN；单篇入库 p50/p95（桩）。据此决定是否开优化卡。

## 2. 证据链（现状）
- 无 pytest-benchmark、无性能基线；REQ-NF-001 单篇 30s。

## 3. 执行逻辑穿透
SQLAlchemy `before_cursor_execute` 计数；`EXPLAIN (ANALYZE, BUFFERS)`；n=50 计时。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红（写失败测试）｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### S11.1 测量
- **S11.1.1** ✅ SQL 往返计数用例，输出数字
- **S11.1.2** ✅ EXPLAIN 造数 10k/1k，计划入 EVD
- **S11.1.3** ✅ 单篇入库 p50/p95（n=50），与 30s 对比

### S11.2 决策
- **S11.2.1** 👤 依据数字决定是否开优化卡（批量 upsert / status 索引 / jobs.subscription_id 列）

## 5. 测试设计
- perf 标记用例，CI 不默认跑。

## 6. 停止条件与回滚
- 禁止无基线优化。

## 7. 交付证据
EVD-V2-11。

## 8. 完成定义（本卡）
所有权内 diff 与任务一致 ∧ 每个 ✅ 有读数 ∧ 本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 通过 ∧ 推送后 CI 与 Security 均 success（run id 入 EVD）∧ 复审 ≤2 轮（D-14）。
