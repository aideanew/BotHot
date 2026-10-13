# STEP-07 存量审计与回填

| 项 | 值 |
|---|---|
| 里程碑 | M2 |
| 档位 | opus + 人 |
| 规模 | 中（脚本 1 人日；生产窗口另计） |
| 依赖 | STEP-06；TASK-001（口令轮换）；D-V2-06 |
| 裁决 | D-V2-06（必须人签） |
| 剩余原子任务 | 5（👤 3） |
| 所有权（写） | W：scripts/audit_article_keys.sql、scripts/backfill_article_keys.py、scripts/missing_articles_report.py（新）；tests/test_backfill_article_keys.py（新） |
| 基线 | main@65f508b |

## 1. 目标与可证伪验收
- 只读审计给出：裸 `s` 键资产数、同号多源数（R-9）、清单 article_key 空值数、短链映射目标为 `s` 的数量。
- 回填脚本幂等（重复执行无变化）、冲突不合并只报告、默认 dry-run。
- 生产执行有人签 dry-run 报告，执行后复跑审计对比。

## 2. 证据链（现状）
- R-2/R-9：S2.1.3 已在 main，部署后长链按 biz 建源，旧 `s` 源成孤儿；改键后历史缓存失效。
- 生产规模未知（U-02/03）。

## 3. 执行逻辑穿透
审计 SQL（只读副本）→ dry-run 计算新键与冲突 → 人签 → 实跑（单事务分批）→ 复跑审计。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红（写失败测试）｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### S7.1 只读审计
- **S7.1.1** 👤🗄 只读副本执行 audit_article_keys.sql，结果入 EVD（不含个人数据）
- **S7.1.2** 👤 抽样 20 条 article_manifests.url 判定 RedFox workUrl 形态，关闭 U-01

### S7.2 回填脚本
- **S7.2.1** 🔴🛠 backfill_article_keys.py：先写测试（冲突不合并、重复执行无变化、dry-run 不写库）再实现
- **S7.2.2** 🛠 missing_articles_report.py：按源列出“清单有、资产无”的篇（隔离库造数验证）

### S7.3 生产执行
- **S7.3.1** 👤🗄 dry-run 报告 → 人签（签名+日期）→ 实跑 → 复跑审计对比

## 5. 测试设计
- test_backfill_article_keys.py（约 6 条，隔离库）。

## 6. 停止条件与回滚
- TASK-001 未完成：禁止任何生产操作。
- 冲突数超过 dry-run 预估：停止，人工裁决。

## 7. 交付证据
EVD-V2-07：审计前后、dry-run 报告、签字记录。

## 8. 完成定义（本卡）
所有权内 diff 与任务一致 ∧ 每个 ✅ 有读数 ∧ 本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 通过 ∧ 推送后 CI 与 Security 均 success（run id 入 EVD）∧ 复审 ≤2 轮（D-14）。
