# STEP-06 采集端到端测试闭环与覆盖率门

| 项 | 值 |
|---|---|
| 里程碑 | M1（收口） |
| 档位 | sonnet |
| 规模 | 中（约 1.5 人日） |
| 依赖 | STEP-04、STEP-05 |
| 裁决 | — |
| 剩余原子任务 | 7（👤 0） |
| 所有权（写） | W：apps/api/tests/test_e2e_collection.py（新）、test_scheduler.py（夹具）、test_p0_asset_cache.py（常量）；scripts/check_module_coverage.py（新）；Makefile；ci.yml（coverage-gate 步，D-11 范围） |
| 基线 | main@65f508b |

## 1. 目标与可证伪验收
- 6 个渠道（redfox/dajiala/justoneapi/tikhub/wellbyte/rss）各一条“发现 → 清单 → 入列 → 入库 → 二轮 Diff=0”的 E2E 用例，连跑 3 次结果一致。
- 纠偏掩盖缺陷的夹具（真实形态 URL 与 32 位 hex id）。
- 模块覆盖率门：article_identity 100%、manifest/kb/subscription ≥85%、4 家 provider ≥80%；全局保持 ≥79%。
- M1 收口：四探针全部达“修复后期望”，独立验证者判 PASS。

## 2. 证据链（现状）
- 夹具：test_p0_asset_cache.py `URL_A` 用 `?biz=`；test_scheduler.py `_seed_manifests` 非真实 id/URL（02 §3）。
- ci.yml 覆盖率门仅全局 75%；无模块级门。

## 3. 执行逻辑穿透
E2E 用 provider 桩（样本驱动）+ resolver 桩 + LangBot 桩，走真实 ManifestSyncService/SubscriptionService/JobWorker/KnowledgeBaseService 与真实 PG；断言资产数、清单状态、二轮 Diff。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红（写失败测试）｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### S6.1 E2E
- **S6.1.1** 🛠 test_e2e_collection.py::test_redfox_round_trip
  - S6.1.1.1 连跑 3 次（`pytest --count` 或循环）结果一致
- **S6.1.2** 🛠 参数化到其余 5 渠道；rss 仅 mp.weixin 链接入库，外链按 D-V2-03 计 filtered_offsite

### S6.2 纠偏夹具
- **S6.2.1** 🛠 test_scheduler.py `_seed_manifests` 改 32 位 hex id + 真实长链；READY 资产改用规范键
  - S6.2.1.1 test_scheduler 全绿
- **S6.2.2** 🛠 test_p0_asset_cache.py `URL_A` 改 `__biz` 并增“同号两篇长链”用例

### S6.3 模块覆盖率门
- **S6.3.1** 🛠 scripts/check_module_coverage.py（读 coverage.json，按模块阈值判定）+ Makefile `coverage-gate`
  - S6.3.1.1 人为调高阈值 ⇒ rc≠0（反证）
- **S6.3.2** 🛠 ci.yml pytest 步后接 coverage-gate（D-11 范围）

### S6.4 M1 收口验收
- **S6.4.1** ✅ 双环境全量 + 四探针 + coverage-gate + evidence-check + CI 双绿，汇总 EVD-V2-06；独立验证者只看 diff 与读数判 PASS/FAIL/UNKNOWN

## 5. 测试设计
- E2E 6 条（参数化）；夹具纠偏后既有用例保持绿。

## 6. 停止条件与回滚
- E2E 不稳定（3 次不一致）：先定位时序/时间依赖，禁止加重试掩盖。

## 7. 交付证据
EVD-V2-06：E2E 三连读数、覆盖率表、四探针终值、CI run id、验证者结论。

## 8. 完成定义（本卡）
所有权内 diff 与任务一致 ∧ 每个 ✅ 有读数 ∧ 本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 通过 ∧ 推送后 CI 与 Security 均 success（run id 入 EVD）∧ 复审 ≤2 轮（D-14）。
