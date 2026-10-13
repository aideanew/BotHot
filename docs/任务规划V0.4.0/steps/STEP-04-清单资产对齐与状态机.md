---
id: STEP-04
title: 清单↔资产键对齐与清单状态机（P0-2 重复入列）
baseline: main@4afaedd
tier: sonnect
size: 大（约 1.5–2 人日）
---

# STEP-04：清单↔资产键对齐与清单状态机（P0-2 重复入列）

## 归属
- 所属切片：S4 可演示：订阅号已入库文章在下一轮同步不再入列；Job 终态后空轮询退避生效
- 来源需求：M-03、REQ-F-006
- 来源方案：ADR-0012；03 §8.2；探针 P-2

## 目标
P-2 输出 `已 READY 入库后 Diff 仍判为新增篇数 = 0`；第二轮同步不新建 Job 且 `consecutive_empty_syncs` 递增。

## 输入
- ADR-0012
- app/contracts/collection.py（ManifestStatus/ALLOWED_TRANSITIONS）
- STEP-02（canonical_article_key）、STEP-03（_map_row 已改）合入
- subscription.py:753-860、job_worker.py:324-360、entities.py:99-230

## 输出（新增/修改的文件）
- apps/api/alembic/versions/ab1006c1a_manifest_article_key.py（新，唯一迁移号）
- apps/api/app/models/entities.py（ArticleManifest.article_key、JobItem.manifest_id、注释 X-05）
- packages/contracts/src/subscription/dto.ts（gen_contracts 重新生成）
- apps/api/app/services/manifest.py（仅 `_map_row` 写 article_key 一行 + `_upsert` 写列）
- apps/api/app/services/subscription.py
- apps/api/app/services/job_worker.py
- apps/api/tests/test_manifest_asset_alignment.py（新）
- apps/api/tests/test_manifest_state_machine.py（新）

## Execution Steps（三级原子任务 → 四级执行步骤）

标记：🔴 先红（失败测试/反证）｜🛠 实现｜✅ 验证｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决。每个原子任务单独可验收。

### S4.1 先红

#### S4.1.1 🔴

**交付**：`test_manifest_asset_alignment.py`：清单 `external_id=workUuid`、url 为真实形态，资产按 kb 真实写法 READY ⇒ `_compute_new_manifests` 返回 0（P-2 转正）

**执行步骤**：
1. [ ] 复制探针逻辑为常驻用例
2. [ ] 改前红（=1）

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_manifest_asset_alignment.py -q
```

#### S4.1.2 🔴

**交付**：同文件：Job 终态后再跑 `run_incremental_sync` ⇒ 不新建 Job、`consecutive_empty_syncs` +1

**执行步骤**：
1. [ ] 写用例（改前红）

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_manifest_asset_alignment.py -q -k second_round
```

### S4.2 数据模型

#### S4.2.1 🗄

**交付**：迁移 `ab1006c1a`（down_revision=`ab1005w5b`）：`article_manifests.article_key VARCHAR(128) NOT NULL DEFAULT ''` + `ix_manifest_source_article_key`；`job_items.manifest_id VARCHAR(36) NULL` FK SET NULL + `ix_job_items_manifest_id`

**执行步骤**：
1. [ ] 写迁移（纯 DDL）
2. [ ] entities.py 同步字段
3. [ ] `python scripts/gen_contracts.py` 重新生成 dto.ts

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run alembic heads | grep -c head
```

### S4.3 写侧

#### S4.3.1 🛠

**交付**：`_map_row` 计算 `article_key = canonical_article_key(url)`；`_upsert` 写入/更新该列

**执行步骤**：
1. [ ] 实现 + 单测

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_manifest_sync.py -q
```

#### S4.3.2 🛠

**交付**：`_populate_job_items` 写 `JobItem.manifest_id` 并把清单置 `ENQUEUED`

**执行步骤**：
1. [ ] 实现 + 单测

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_manifest_state_machine.py -q -k enqueue
```

### S4.4 Diff 与状态机

#### S4.4.1 🛠

**交付**：`_compute_new_manifests`：只取 `status='DISCOVERED'`，并以 `article_key NOT IN (READY 资产 external_id)` 过滤（同一键空间）；保留在途 Job 排除

**执行步骤**：
1. [ ] 实现
2. [ ] S4.1.1 转绿

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_manifest_asset_alignment.py -q
```

#### S4.4.2 🛠

**交付**：`job_worker._drain_items`：成功 ⇒ 经 `manifest_id` 置 `INGESTED`；永久失败 ⇒ `FAILED`；迁移前用 `ALLOWED_TRANSITIONS` 校验，非法 ⇒ `JobStateInvalidError`

**执行步骤**：
1. [ ] 实现
2. [ ] 状态机单测覆盖每条合法/非法边

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_manifest_state_machine.py -q
```

#### S4.4.3 🛠

**交付**：stale 回退：`ENQUEUED` 且所属 Job 已终态的行在每轮 Diff 前回退 `DISCOVERED`（防 worker 崩溃漏推进）

**执行步骤**：
1. [ ] 实现 + 单测（模拟 worker 崩溃）

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_manifest_state_machine.py -q -k stale
```

### S4.5 验收

#### S4.5.1 ✅

**交付**：P-2 复跑 = 0；`gen_contracts --check` rc=0；迁移往返 + 单头；全量双环境 failed=0

**执行步骤**：
1. [ ] 输出入 EVD-V2-04

**验收命令**：
```bash
python scripts/gen_contracts.py --check && eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests -q | tail -1
```

## 验收标准（独立验证者逐条判 PASS / FAIL / UNKNOWN）
- [ ] P-2 输出 `= 0`
- [ ] 第二轮同步 0 新 Job、`consecutive_empty_syncs` 递增
- [ ] 迁移 upgrade→downgrade→upgrade 成功且 `alembic heads` 仅 1 个
- [ ] `gen_contracts.py --check` rc=0
- [ ] 状态机每条边有测试；非法迁移抛 30005
- [ ] 全量 failed=0

## 验证命令
```bash
python scripts/gen_contracts.py --check && eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run alembic upgrade head && uv run pytest tests/test_manifest_asset_alignment.py tests/test_manifest_state_machine.py -q && uv run pytest tests -q | tail -1
```

## 证据路径
`docs/06_validation/evidence/EVD-V2-04/`（README 记录：sha、命令、原始输出、PASS/FAIL 结论、验证者）

## 允许修改
- `apps/api/alembic/versions/ab1006c1a_manifest_article_key.py`
- `apps/api/app/models/entities.py（仅 ArticleManifest、JobItem）`
- `packages/contracts/src/subscription/dto.ts（仅生成）`
- `apps/api/app/services/manifest.py（仅 _map_row 的 article_key 与 _upsert）`
- `apps/api/app/services/subscription.py`
- `apps/api/app/services/job_worker.py`
- `apps/api/tests/test_manifest_asset_alignment.py`
- `apps/api/tests/test_manifest_state_machine.py`

## 禁止修改
- `apps/api/app/services/kb.py`
- `apps/api/app/providers/**`
- `manifest.py::sync_source` 循环体（STEP-05）
- `apps/api/tests/test_scheduler.py`（STEP-06）
- 迁移内运行应用层 Python（回填属 STEP-07）
- `packages/contracts/**`（STEP-01 除外）
- `.github/**`（需 D-11 授权）
- `docker/**`、`deploy/**`
- 任务书未列出的一切路径

## 依赖与阻塞
- Depends on：STEP-02、STEP-03（均已合入）；D-V2-02
- Blocks：STEP-05、STEP-06、STEP-07、STEP-11
- 阻塞条件（遇到即停）：迁移需要 `ab1006c1a` 以外的版本号或需改 `content_assets` 结构 ⇒ 停

## 建议执行档位
`sonnect`　理由：ADR 已定，迁移+状态机为常规实现；但含迁移，验收由独立验证者判

## 升级条件
状态机出现未在 ALLOWED_TRANSITIONS 中的必要迁移 ⇒ 升 opus（改契约）；另：同一原子任务连续 2 次验收失败 ⇒ 停止改代码，重写任务书 / 升档 / 标 blocked（熔断）。

## 预估规模
大（约 1.5–2 人日）

## 完成定义（全项目唯一口径）
所有权内 diff 符合本卡 ∧ 验收逐条有结果 ∧ 自动测试可复现 ∧ EVD 可让一周后的人复现 ∧ `make evidence-check` 通过 ∧ 未改冻结契约（STEP-01 除外）∧ 无新增同类错误。

## 回滚
代码改动 `git revert <sha>`；迁移 `alembic downgrade -1`（仅本卡迁移号）。
