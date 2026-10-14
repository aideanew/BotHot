# STEP-12 文档对账证据汇总与发布

| 项 | 值 |
|---|---|
| 里程碑 | M3 |
| 档位 | haiku |
| 规模 | 小（约 0.5 人日） |
| 依赖 | STEP-06（及已完成的 07–11） |
| 裁决 | — |
| 剩余原子任务 | 5（👤 0） |
| 所有权（写） | W：AGENTS.md、docs/02_requirements（REQ-F-004/006）、docs/04_engineering/conventions.md、CHANGELOG.md、docs/05_execution/task-index |
| 基线 | main@a9b194d |

## 1. 目标与可证伪验收
- 门面文档无不实陈述；需求条目有测试锚；发布 v1.1.0。

## 2. 证据链（现状）
- AGENTS.md:78 三条陈述已证伪（00G 已打标）；测试基线段仍为旧数字。

## 3. 执行逻辑穿透
以 EVD-V2-06 读数为唯一来源改写；`check_docs_consistency` 校验引用。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红（写失败测试）｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### S12.1 对账
- **S12.1.1** 📄 AGENTS.md:78 按 STEP-03/10 实测改写；测试基线改为 EVD-V2-06 的命令+sha+数字；删除 00G 临时标注
- **S12.1.2** 📄 REQ-F-004/006 增验收锚（test_kb_longlink_ingest / test_manifest_asset_alignment / test_e2e_collection）
- **S12.1.3** 📄 conventions 增测试端口、代理隔离、DSN 无口令三条

### S12.2 核验与发布
- **S12.2.1** ✅ 构建运行镜像核验时区库（U-06），结果入 EVD
- **S12.2.2** 📄 EVD 汇总 + CHANGELOG [v1.1.0] + task-index 状态

## 5. 测试设计
- `check_docs_consistency` 通过。

## 6. 停止条件与回滚
- 任一 M1 验收未 PASS：不发布。

## 7. 交付证据
EVD-V2-12。

## 8. 完成定义（本卡）
所有权内 diff 与任务一致 ∧ 每个 ✅ 有读数 ∧ 本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 通过 ∧ 推送后 CI 与 Security 均 success（run id 入 EVD）∧ 复审 ≤2 轮（D-14）。
