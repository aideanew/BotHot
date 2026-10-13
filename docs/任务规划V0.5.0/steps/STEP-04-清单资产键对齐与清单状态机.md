# STEP-04 清单资产键对齐与清单状态机

| 项 | 值 |
|---|---|
| 里程碑 | M1 |
| 档位 | sonnet |
| 规模 | 大（约 2 人日） |
| 依赖 | STEP-02（S2.2.3 合入）、STEP-03（S3.3.2 合入）；D-V2-02 |
| 裁决 | D-V2-02 |
| 剩余原子任务 | 10（👤 0） |
| 所有权（写） | W：apps/api/alembic/versions/ab1006c1a_*.py（新）；app/models/entities.py（ArticleManifest/JobItem）；app/services/manifest.py（_map_row/_upsert）、subscription.py（_compute_new_manifests/_populate_job_items）、job_worker.py（_drain_items/_finalize/recover_stale）；packages/contracts/src/subscription/dto.ts（生成）；tests/test_manifest_asset_alignment.py（新）、test_manifest_state_machine.py（新） |
| 基线 | main@65f508b |

## 1. 目标与可证伪验收
- P-2：已 READY 入库的篇，下一轮 Diff 新增数 = 0（空轮询退避恢复有效）。
- 清单四态状态机可观测：DISCOVERED → ENQUEUED → INGESTED / FAILED；worker 崩溃后 stale ENQUEUED 自动回退。
- 迁移往返（upgrade/downgrade/upgrade）+ 单头；`gen_contracts --check` 绿。

## 2. 证据链（现状）
- subscription.py:806-822：`ArticleManifest.external_id.not_in(ready_ext)`，manifest 键=渠道 id，asset 键=`_article_key(url)` ⇒ 永不相交（P-2 读数 =1）。
- subscription.py:828 `_populate_job_items` 不写清单关联；job_worker.py:324 `_drain_items` 终态不回写清单。
- 迁移头 `ab1005w5b`（gates_65f508b.txt）。

## 3. 执行逻辑穿透
sync_source 写清单时同时算 `article_key` → Diff 以 `article_key` 对资产、以 `manifest_id` 对在途 Job → 入列写 `job_items.manifest_id` 并置 ENQUEUED → worker 终态回写 INGESTED/FAILED → `recover_stale`（job_worker.py:204）同时回退超时 ENQUEUED。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红（写失败测试）｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### S4.1 先红
- **S4.1.1** 🔴 test_manifest_asset_alignment.py：P-2 探针转常驻（READY 后 Diff 期望 0，改前 1）
- **S4.1.2** 🔴 同文件：同篇短链/长链两形态各一条清单 ⇒ 只入列一次

### S4.2 数据模型
- **S4.2.1** 🗄 迁移 ab1006c1a（down=ab1005w5b）：`article_manifests.article_key` + 索引 `ix_manifest_source_article_key`；`job_items.manifest_id` FK + 索引
  - S4.2.1.1 纯 DDL，不跑应用代码
  - S4.2.1.2 upgrade → downgrade → upgrade 往返
- **S4.2.2** 🛠 entities.py 同步字段；`python scripts/gen_contracts.py` 重新生成 dto.ts（同一提交）
  - S4.2.2.1 `--check` rc=0

### S4.3 写侧
- **S4.3.1** 🛠 `_map_row` 计算 `article_key=canonical_article_key(url)`；`_upsert` 写入/更新
  - S4.3.1.1 单测：url 变化时 article_key 跟随更新
- **S4.3.2** 🛠 `_populate_job_items` 写 `manifest_id` 并把清单置 ENQUEUED（与入列同事务）

### S4.4 Diff 与状态机
- **S4.4.1** 🛠 `_compute_new_manifests` 改为 status=DISCOVERED ∧ article_key∉READY 资产 ∧ id∉活动 Job 的 manifest_id
  - S4.4.1.1 S4.1.1/S4.1.2 转绿
- **S4.4.2** 🛠 `_drain_items` 终态回写：SUCCEEDED ⇒ INGESTED；FAILED（永久）⇒ FAILED；限流/可重试保持 ENQUEUED
  - S4.4.2.1 test_manifest_state_machine.py 覆盖每条合法边与 2 条非法边
- **S4.4.3** 🛠 `recover_stale` 扩展：ENQUEUED 超过 `manifest_enqueued_ttl` 且无活动 Job ⇒ 回 DISCOVERED
  - S4.4.3.1 单测模拟 worker 崩溃

### S4.5 验收
- **S4.5.1** ✅ P-2 复跑 = 0；迁移往返 + 单头；`gen_contracts --check` rc=0；全量双环境 0 failed；CI 双绿

## 5. 测试设计
- 新增约 15 条连库用例；状态机用例纯 SQL 事务内完成。

## 6. 停止条件与回滚
- 迁移在 CI PG 上失败：停止，不手工改库；修迁移后重跑往返。
- 回滚：downgrade 到 ab1005w5b（列/索引/外键全部可逆）。

## 7. 交付证据
EVD-V2-04：P-2 前后读数、迁移往返输出、EXPLAIN 草读（正式基线在 STEP-11）。

## 8. 完成定义（本卡）
所有权内 diff 与任务一致 ∧ 每个 ✅ 有读数 ∧ 本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 通过 ∧ 推送后 CI 与 Security 均 success（run id 入 EVD）∧ 复审 ≤2 轮（D-14）。
