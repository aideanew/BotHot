---
id: STEP-07
title: 存量审计与回填（生产，人工把关）
baseline: main@4afaedd
tier: opus
size: 中（脚本 1 人日；生产窗口另计）
---

# STEP-07：存量审计与回填（生产，人工把关）

## 归属
- 所属切片：S7 可演示：生产中历史 `'s'` 键资产被识别并（经批准后）改写；缺失文章清单可导出
- 来源需求：S-03；I-06；N-05
- 来源方案：D-V2-06；ADR-0011 存量策略

## 目标
只读审计数字入档；回填脚本 dry-run 报告经人批后实跑，冲突行零自动合并。

## 输入
- STEP-06 PASS
- TASK-001 口令轮换证据（EVD-001）
- 生产只读副本连接（由人提供，不入库）

## 输出（新增/修改的文件）
- scripts/audit_article_keys.sql（新，只读）
- scripts/backfill_article_keys.py（新，默认 --dry-run）
- scripts/missing_articles_report.py（新）
- apps/api/tests/test_backfill_article_keys.py（新）
- docs/06_validation/evidence/EVD-V2-07/**

## Execution Steps（三级原子任务 → 四级执行步骤）

标记：🔴 先红（失败测试/反证）｜🛠 实现｜✅ 验证｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决。每个原子任务单独可验收。

### S7.1 只读审计

#### S7.1.1 👤🗄

**交付**：在只读副本执行 `audit_article_keys.sql`：`content_assets.external_id='s'` 行数、`short_link_maps.article_key='s'` 行数、`article_manifests` 中 article_key 为空的行数、sources 数；关闭 U-02/U-03

**执行步骤**：
1. [ ] 人执行
2. [ ] 结果入 EVD

**验收命令**：
```bash
psql "$RO_DSN" -f scripts/audit_article_keys.sql > docs/06_validation/evidence/EVD-V2-07/audit.txt
```

#### S7.1.2 👤

**交付**：抽样 20 条 `article_manifests.url` 判定 RedFox workUrl 形态，关闭 U-01

**执行步骤**：
1. [ ] 人判

**验收命令**：
```bash
test -s docs/06_validation/evidence/EVD-V2-07/u01_sample.md
```

### S7.2 回填脚本

#### S7.2.1 🔴🛠

**交付**：`backfill_article_keys.py`：分批 500、幂等、默认 dry-run；同源两行算出同键 ⇒ 不合并、写冲突 CSV、跳过；回填 `article_manifests.article_key` 与可判定的 `content_assets.external_id`

**执行步骤**：
1. [ ] 先写测试（冲突不合并、重复执行无变化）
2. [ ] 实现

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_backfill_article_keys.py -q
```

#### S7.2.2 🛠

**交付**：`missing_articles_report.py`：`job_items.url ∪ article_manifests.url` 按规范键减 `content_assets` ⇒ CSV

**执行步骤**：
1. [ ] 实现 + 隔离库造数验证

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run python ../../scripts/missing_articles_report.py --dsn "$AIDEANBOT_TEST_PG_DSN" --out /tmp/missing.csv && test -f /tmp/missing.csv
```

### S7.3 生产执行（人）

#### S7.3.1 👤🗄

**交付**：dry-run 报告入 EVD → 人批（签名+日期）→ 实跑 → 复跑审计 SQL 对比

**执行步骤**：
1. [ ] 人执行

**验收命令**：
```bash
diff docs/06_validation/evidence/EVD-V2-07/audit.txt docs/06_validation/evidence/EVD-V2-07/audit_after.txt
```

## 验收标准（独立验证者逐条判 PASS / FAIL / UNKNOWN）
- [ ] 审计数字入档（U-01/02/03 关闭）
- [ ] 回填脚本测试绿：冲突不合并、二次执行零变化
- [ ] 生产实跑前有人签批的 dry-run 报告
- [ ] 实跑后 `external_id='s'` 行数 = 0 或等于冲突清单行数

## 验证命令
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_backfill_article_keys.py -q
```

## 证据路径
`docs/06_validation/evidence/EVD-V2-07/`（README 记录：sha、命令、原始输出、PASS/FAIL 结论、验证者）

## 允许修改
- `scripts/audit_article_keys.sql`
- `scripts/backfill_article_keys.py`
- `scripts/missing_articles_report.py`
- `apps/api/tests/test_backfill_article_keys.py`
- `docs/06_validation/evidence/EVD-V2-07/**`

## 禁止修改
- `apps/api/app/**`
- 任何对生产库的写操作（S7.3 人工执行除外）
- 把连接串/口令写入任何文件
- `packages/contracts/**`（STEP-01 除外）
- `apps/api/alembic/versions/**`（STEP-04/08/09 各自唯一迁移号除外）
- `.github/**`（需 D-11 授权）
- `docker/**`、`deploy/**`
- 任务书未列出的一切路径

## 依赖与阻塞
- Depends on：STEP-06；TASK-001；D-V2-06
- Blocks：STEP-12（发布说明）
- 阻塞条件（遇到即停）：TASK-001 未完成或 dry-run 冲突数 >0 未经人逐条处理 ⇒ 停

## 建议执行档位
`opus`　理由：生产数据不可逆操作，需高风险 review

## 升级条件
出现需合并两条资产的情形 ⇒ 升 fable + 人裁；另：同一原子任务连续 2 次验收失败 ⇒ 停止改代码，重写任务书 / 升档 / 标 blocked（熔断）。

## 预估规模
中（脚本 1 人日；生产窗口另计）

## 完成定义（全项目唯一口径）
所有权内 diff 符合本卡 ∧ 验收逐条有结果 ∧ 自动测试可复现 ∧ EVD 可让一周后的人复现 ∧ `make evidence-check` 通过 ∧ 未改冻结契约（STEP-01 除外）∧ 无新增同类错误。

## 回滚
`git revert <sha>`；无数据影响。
