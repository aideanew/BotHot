---
id: STEP-11
title: 采集性能：先测基线，再决定是否优化
baseline: main@4afaedd
tier: sonnect
size: 小（约 0.5–1 人日）
---

# STEP-11：采集性能：先测基线，再决定是否优化

## 归属
- 所属切片：S11 可演示：清单写入 SQL 往返数、Diff 查询计划、单篇入库耗时三项有首测数字
- 来源需求：S-04；REQ-NF-001（文章入库单篇 <30s）；N-03
- 来源方案：V0.2.0 S8（改为“只测不优化”）

## 目标
三项指标首测值入 EVD-V2-11；只有当指标与用户可感耗时相关且超标时才另开优化卡。

## 输入
- STEP-04 PASS

## 输出（新增/修改的文件）
- apps/api/tests/test_perf_collection.py（新；以 `BOTHOT_PERF=1` 门控，未设置时 skip，不新增 pytest marker）
- docs/06_validation/evidence/EVD-V2-11/**

## Execution Steps（三级原子任务 → 四级执行步骤）

标记：🔴 先红（失败测试/反证）｜🛠 实现｜✅ 验证｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决。每个原子任务单独可验收。

### S11.1 测量

#### S11.1.1 ✅

**交付**：SQL 往返：1 页 20 行清单写入的语句数（SQLAlchemy `before_cursor_execute` 计数）

**执行步骤**：
1. [ ] 写 perf 用例，输出数字

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && BOTHOT_PERF=1 uv run pytest tests/test_perf_collection.py -q -k roundtrip -s
```

#### S11.1.2 ✅

**交付**：`EXPLAIN (ANALYZE, BUFFERS)` `_compute_new_manifests`（造 10k 清单 / 1k Job）

**执行步骤**：
1. [ ] 输出计划入 EVD

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && BOTHOT_PERF=1 uv run pytest tests/test_perf_collection.py -q -k explain -s
```

#### S11.1.3 ✅

**交付**：单篇入库耗时（stub resolver + LangBot 桩，p50/p95，n=50）；与 REQ-NF-001 30s 对比

**执行步骤**：
1. [ ] 输出数字

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && BOTHOT_PERF=1 uv run pytest tests/test_perf_collection.py -q -k ingest -s
```

### S11.2 决策

#### S11.2.1 👤

**交付**：依据数字决定是否开优化卡（`ON CONFLICT` 批量 upsert / `status` 索引 / `jobs.subscription_id` 列）

**执行步骤**：
1. [ ] 人判

**验收命令**：
```bash
test -s docs/06_validation/evidence/EVD-V2-11/decision.md
```

## 验收标准（独立验证者逐条判 PASS / FAIL / UNKNOWN）
- [ ] 三项指标首测值与命令入档
- [ ] 未修改任何 app 代码

## 验证命令
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && BOTHOT_PERF=1 uv run pytest tests/test_perf_collection.py -q -s
```

## 证据路径
`docs/06_validation/evidence/EVD-V2-11/`（README 记录：sha、命令、原始输出、PASS/FAIL 结论、验证者）

## 允许修改
- `apps/api/tests/test_perf_collection.py`
- `docs/06_validation/evidence/EVD-V2-11/**`

## 禁止修改
- `apps/api/app/**`（本步不优化）
- `packages/contracts/**`（STEP-01 除外）
- `apps/api/alembic/versions/**`（STEP-04/08/09 各自唯一迁移号除外）
- `.github/**`（需 D-11 授权）
- `docker/**`、`deploy/**`
- 任务书未列出的一切路径

## 依赖与阻塞
- Depends on：STEP-04
- Blocks：（可能的）后续优化卡
- 阻塞条件（遇到即停）：—

## 建议执行档位
`sonnect`　理由：测量脚本

## 升级条件
数字显示用户可感超标 ⇒ 升 opus 出优化 ADR；另：同一原子任务连续 2 次验收失败 ⇒ 停止改代码，重写任务书 / 升档 / 标 blocked（熔断）。

## 预估规模
小（约 0.5–1 人日）

## 完成定义（全项目唯一口径）
所有权内 diff 符合本卡 ∧ 验收逐条有结果 ∧ 自动测试可复现 ∧ EVD 可让一周后的人复现 ∧ `make evidence-check` 通过 ∧ 未改冻结契约（STEP-01 除外）∧ 无新增同类错误。

## 回滚
`git revert <sha>`；无数据影响。
