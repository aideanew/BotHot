---
id: STEP-12
title: 文档对账、证据汇总与发布
baseline: main@4afaedd
tier: haiku
size: 小（约 0.5 人日）
---

# STEP-12：文档对账、证据汇总与发布

## 归属
- 所属切片：S12 可演示：AGENTS/需求/CHANGELOG 的每条采集陈述都能指到一个 EVD
- 来源需求：X-01…X-07；U-06
- 来源方案：01 §2.3

## 目标
文档中无与代码相反的采集陈述；EVD-V2-00R…11 汇总；CHANGELOG 有 v1.1.0 段（打 tag 由人执行）。

## 输入
- STEP-06 PASS（必要）、STEP-07…11（已完成部分）

## 输出（新增/修改的文件）
- AGENTS.md（:78/:80 两段）
- docs/02_requirements/product-requirements.md（REQ-F-004/006 验收锚）
- docs/04_engineering/conventions.md（测试端口 5547/6390 与代理隔离说明）
- CHANGELOG.md
- docs/06_validation/evidence/README 汇总表
- docs/05_execution/task-index.md

## Execution Steps（三级原子任务 → 四级执行步骤）

标记：🔴 先红（失败测试/反证）｜🛠 实现｜✅ 验证｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决。每个原子任务单独可验收。

### S12.1 对账

#### S12.1.1 📄

**交付**：AGENTS.md:78 按 STEP-03/10 实际结果改写；:80 测试基线改为 STEP-06 实测（命令+sha+数字）

**执行步骤**：
1. [ ] 改写

**验收命令**：
```bash
grep -n 'EVD-V2-06' AGENTS.md
```

#### S12.1.2 📄

**交付**：REQ-F-004/006 增验收锚（指向 test_kb_longlink_ingest / test_manifest_asset_alignment / test_e2e_collection）

**执行步骤**：
1. [ ] 改写

**验收命令**：
```bash
grep -n 'test_e2e_collection' docs/02_requirements/product-requirements.md
```

#### S12.1.3 📄

**交付**：conventions.md 增测试端口与代理隔离说明

**执行步骤**：
1. [ ] 改写

**验收命令**：
```bash
grep -n '5547' docs/04_engineering/conventions.md
```

### S12.2 核验与发布

#### S12.2.1 ✅

**交付**：构建运行镜像后核验时区库（U-06）：`docker run --rm <img> python -c "from zoneinfo import ZoneInfo;ZoneInfo('Asia/Shanghai')"`

**执行步骤**：
1. [ ] 有 docker 的执行者执行，结果入 EVD

**验收命令**：
```bash
docker compose -f docker/compose.yml build api
```

#### S12.2.2 📄

**交付**：EVD 汇总 + CHANGELOG `[v1.1.0]`；task-index 标注各 STEP 状态

**执行步骤**：
1. [ ] 汇总

**验收命令**：
```bash
grep -n 'v1.1.0' CHANGELOG.md
```

## 验收标准（独立验证者逐条判 PASS / FAIL / UNKNOWN）
- [ ] AGENTS/REQ 中每条采集陈述带 EVD 或测试锚
- [ ] `python scripts/check_docs_consistency.py` rc=0
- [ ] CHANGELOG 有 v1.1.0 段

## 验证命令
```bash
python scripts/check_docs_consistency.py && grep -n 'v1.1.0' CHANGELOG.md
```

## 证据路径
`docs/06_validation/evidence/EVD-V2-12/`（README 记录：sha、命令、原始输出、PASS/FAIL 结论、验证者）

## 允许修改
- `AGENTS.md（仅能力声明与测试基线两段）`
- `docs/02_requirements/product-requirements.md`
- `docs/04_engineering/conventions.md`
- `CHANGELOG.md`
- `docs/06_validation/evidence/README.md`
- `docs/05_execution/task-index.md`

## 禁止修改
- `apps/**`
- AGENTS.md 端口表语义（只增注测试端口说明）
- `packages/contracts/**`（STEP-01 除外）
- `apps/api/alembic/versions/**`（STEP-04/08/09 各自唯一迁移号除外）
- `.github/**`（需 D-11 授权）
- `docker/**`、`deploy/**`
- 任务书未列出的一切路径

## 依赖与阻塞
- Depends on：STEP-06（及已完成的 07–11）
- Blocks：—
- 阻塞条件（遇到即停）：发现文档陈述无对应 EVD ⇒ 删除或改为“待验证”，不得编数字

## 建议执行档位
`haiku`　理由：文档同步为主；数字全部来自 EVD

## 升级条件
陈述涉及需求范围改动 ⇒ 升 opus；另：同一原子任务连续 2 次验收失败 ⇒ 停止改代码，重写任务书 / 升档 / 标 blocked（熔断）。

## 预估规模
小（约 0.5 人日）

## 完成定义（全项目唯一口径）
所有权内 diff 符合本卡 ∧ 验收逐条有结果 ∧ 自动测试可复现 ∧ EVD 可让一周后的人复现 ∧ `make evidence-check` 通过 ∧ 未改冻结契约（STEP-01 除外）∧ 无新增同类错误。

## 回滚
`git revert <sha>`；无数据影响。
