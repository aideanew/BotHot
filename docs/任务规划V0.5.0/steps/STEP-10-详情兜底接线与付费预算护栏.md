# STEP-10 详情兜底接线与付费预算护栏

| 项 | 值 |
|---|---|
| 里程碑 | M2（条件） |
| 档位 | sonnet |
| 规模 | 中（约 1.5 人日） |
| 依赖 | STEP-02；S10.2.2 另依赖 S8.3；D-V2-05 |
| 裁决 | D-V2-05 |
| 剩余原子任务 | 3（👤 0） |
| 所有权（写） | W：services/article_detail_fallback.py、services/kb.py（_resolve_with_retry 接线）、services/paid_call_budget.py（新）、core/config.py、providers/article_sources/*（调用前 acquire） |
| 基线 | main@65f508b |

## 1. 目标与可证伪验收
- 协调器在开关打开时被入库链路真实调用（覆盖率 >0），按成本升序；付费调用受渠道日预算约束，超额拒绝并计数。

## 2. 证据链（现状）
- `ArticleDetailFallbackCoordinator` 仅在 article_detail_fallback.py:49/:56 出现；config.py:110 默认 False；`grep budget|quota|cost_limit app` 空。

## 3. 执行逻辑穿透
_resolve_with_retry 失败（可兜底类）且开关开 → coordinator 按 cost_rank 逐个渠道 → 每次付费调用前 budget.acquire(channel) → 超额 ⇒ BudgetExceeded，记指标，停止兜底。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红（写失败测试）｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### S10.1 接线
- **S10.1.1** 🔴🛠 入库主链接线协调器（开关关时零调用、开时按成本顺序调用），测试先红

### S10.2 预算
- **S10.2.1** 🔴🛠 paid_call_budget.py：按渠道日计数（PG 原子自增，Asia/Shanghai 日界），测试先红
- **S10.2.2** 🛠 所有付费 provider 调用前 `budget.acquire(channel)`；超额计 `bothot_paid_budget_rejected_total`

## 5. 测试设计
- 新增约 8 条。

## 6. 停止条件与回滚
- D-V2-05 无数：开关保持关，S10.2 仍实现（默认额度 0 = 全拒）。

## 7. 交付证据
EVD-V2-10。

## 8. 完成定义（本卡）
所有权内 diff 与任务一致 ∧ 每个 ✅ 有读数 ∧ 本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 通过 ∧ 推送后 CI 与 Security 均 success（run id 入 EVD）∧ 复审 ≤2 轮（D-14）。
