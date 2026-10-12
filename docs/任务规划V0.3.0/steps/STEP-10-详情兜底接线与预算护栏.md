---
id: STEP-10
title: 详情兜底接线与付费预算护栏（条件：D-V2-05）
baseline: main@4afaedd
tier: sonnect
size: 中（约 1.5 人日）
---

# STEP-10：详情兜底接线与付费预算护栏（条件：D-V2-05）

## 归属
- 所属切片：S10 可演示：直抓失败的非图集文章经付费详情兜底入库；超日预算后拒绝付费调用并告警
- 来源需求：C-02
- 来源方案：V0.2.0 S6；F-11

## 目标
`article_detail_fallback.py` 覆盖率 ≥85%，开关关时零付费调用；预算第 N+1 次被拒、跨日重置、Redis 断开 fail-closed。

## 输入
- STEP-02 PASS（规范键）
- D-V2-05 裁决（无 ⇒ 只做 S10.1 且开关默认关）

## 输出（新增/修改的文件）
- apps/api/app/services/kb.py（_resolve_with_retry 失败分支）
- apps/api/app/services/paid_call_budget.py（新）
- apps/api/app/services/article_detail_fallback.py
- apps/api/tests/test_detail_fallback_wiring.py、test_paid_call_budget.py（新）

## Execution Steps（三级原子任务 → 四级执行步骤）

标记：🔴 先红（失败测试/反证）｜🛠 实现｜✅ 验证｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决。每个原子任务单独可验收。

### S10.1 接线

#### S10.1.1 🔴🛠

**交付**：测试：直抓抛 `ExtractFailedError`（非图集）且开关开 ⇒ 协调器被调、结果按规范键入库；开关关 ⇒ 不调；图集 ⇒ 不调；然后实现接线与 `ArticleDetail→ResolvedArticle` 适配

**执行步骤**：
1. [ ] 先红后绿

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_detail_fallback_wiring.py -q --cov=app.services.article_detail_fallback --cov-fail-under=85
```

### S10.2 预算

#### S10.2.1 🔴🛠

**交付**：`paid_call_budget.py`：渠道×自然日（Asia/Shanghai）Redis INCR+TTL；Redis 不可用 fail-closed（抛 50002）

**执行步骤**：
1. [ ] 先红后绿

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_paid_call_budget.py -q
```

#### S10.2.2 🛠

**交付**：所有付费 provider 调用前 `budget.acquire(channel)`

**执行步骤**：
1. [ ] 实现

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_provider_contract.py tests/test_paid_call_budget.py -q
```

## 验收标准（独立验证者逐条判 PASS / FAIL / UNKNOWN）
- [ ] 协调器覆盖率 ≥85%
- [ ] 开关关 ⇒ 0 付费调用（计数断言）
- [ ] 预算三条用例绿
- [ ] 全量 failed=0

## 验证命令
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_detail_fallback_wiring.py tests/test_paid_call_budget.py -q
```

## 证据路径
`docs/06_validation/evidence/EVD-V2-10/`（README 记录：sha、命令、原始输出、PASS/FAIL 结论、验证者）

## 允许修改
- `apps/api/app/services/kb.py（仅 _resolve_with_retry 与 make_default_ingest 生命周期）`
- `apps/api/app/services/article_detail_fallback.py`
- `apps/api/app/services/paid_call_budget.py`
- `apps/api/app/providers/article_sources/**（仅调用前 budget.acquire 一行，且须在 STEP-08 合入后）`
- `apps/api/tests/test_detail_fallback_wiring.py`
- `apps/api/tests/test_paid_call_budget.py`

## 禁止修改
- 默认开启兜底开关
- `packages/contracts/**`（STEP-01 除外）
- `apps/api/alembic/versions/**`（STEP-04/08/09 各自唯一迁移号除外）
- `.github/**`（需 D-11 授权）
- `docker/**`、`deploy/**`
- 任务书未列出的一切路径

## 依赖与阻塞
- Depends on：STEP-02；（S10.2.2 另依赖 STEP-08 合入以免 providers 冲突）；D-V2-05
- Blocks：—
- 阻塞条件（遇到即停）：预算需要新表 ⇒ 停（Redis 计数即可满足契约）

## 建议执行档位
`sonnect`　理由：接线+计数器

## 升级条件
兜底结果与直抓结果键不一致 ⇒ 升 opus；另：同一原子任务连续 2 次验收失败 ⇒ 停止改代码，重写任务书 / 升档 / 标 blocked（熔断）。

## 预估规模
中（约 1.5 人日）

## 完成定义（全项目唯一口径）
所有权内 diff 符合本卡 ∧ 验收逐条有结果 ∧ 自动测试可复现 ∧ EVD 可让一周后的人复现 ∧ `make evidence-check` 通过 ∧ 未改冻结契约（STEP-01 除外）∧ 无新增同类错误。

## 回滚
`git revert <sha>`；无数据影响。
