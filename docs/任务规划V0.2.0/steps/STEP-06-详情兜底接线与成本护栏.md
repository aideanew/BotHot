---
id: STEP-06
title: 详情兜底接线与付费调用预算护栏
priority: P1
depends: STEP-01；S6.2 需裁决 D-V2-05
parallel_with: STEP-04 的 S4.1/S4.3/S4.4（文件不相交）
serial_constraints: S6.1 先于 S4.2.1（二者都写 kb.py）；S6.2.2 晚于 S4.3.2（二者都写 providers/article_sources/*）
estimate: 1.5 人日
---

# STEP-06 详情兜底接线与成本护栏

## 目标
直抓失败（非图集）时，在开关开启且预算允许的情况下，按成本顺序调用付费详情，结果走同一入库链；任何付费调用都受日预算约束，Redis 不可用时 fail-closed。

## 依据（02 §D-08、§D-09）
- `services/article_detail_fallback.py` 覆盖率 0%；唯一引用是 `core/config.py:110` 开关。
- `grep -rln "budget\|quota\|cost_limit" apps/api/app` 为空。
- 文档陈述不符：AGENTS.md "详情兜底协调器按成本排序"。

## 允许修改
`apps/api/app/services/kb.py`（仅 `_resolve_with_retry` 与新增适配函数）、`apps/api/app/services/article_detail_fallback.py`、`apps/api/app/services/paid_call_budget.py`（新）、`apps/api/app/services/job_worker.py`（仅 `make_default_ingest` 生命周期）、`apps/api/app/providers/article_sources/{dajiala,justoneapi,tikhub,wellbyte}.py`（仅在请求前插入 `budget.acquire`）、`apps/api/app/core/config.py`（新增 `paid_call_daily_limit_<channel>`）、新测试
## 禁止修改
`manifest.py`、`registry.py`、`scheduler.py`。

## 原子任务

| 编号 | 类型 | 动作 | 验收命令 |
|---|---|---|---|
| S6.1.1 | 🔴 | `test_detail_fallback_wiring.py`：①直抓 `ExtractFailedError` + 开关开 ⇒ 协调器调用 1 次、资产键为 canonical；②开关关 ⇒ 0 次；③图集（`is_gallery_type`）⇒ 0 次；④协调器返回 None ⇒ 原异常上抛 | 改前 FAIL |
| S6.1.2 | 🛠 | `_resolve_with_retry` 失败分支 / `ExtractQualityLowError` 分支调用协调器；`ArticleDetail → ResolvedArticle` 适配（`content_html` 优先） | S6.1.1 绿 |
| S6.1.3 | 🛠 | 协调器随 `make_default_ingest` 创建，worker `run_forever` 退出时 `aclose()` | 单测：stop 后 `aclose` 被调用 |
| S6.2.1 | 🛠 | `PaidCallBudget(redis, limits, tz="Asia/Shanghai")`：键 `paid:{channel}:{YYYYMMDD}`，`INCR` + `EXPIREAT` 次日 00:05；超限/Redis 异常 ⇒ `False` | 单测 3 例（超限、跨日、Redis 断开） |
| S6.2.2 | 🛠 | 4 个付费 client 每次上游请求前 `acquire`；拒绝时抛 `DependencyUnavailableError("预算耗尽")` 并 `alerting` | 单测：拒绝时 MockTransport 0 次请求 |
| S6.2.3 | 👤 | D-V2-05：运营给出每渠道日上限；未给出 ⇒ 保持 `article_detail_fallback_enabled=False` 且上限默认 0 | 人工 |
| S6.3.1 | ✅ | 覆盖率 | `pytest --cov=app.services.article_detail_fallback --cov=app.services.paid_call_budget` 各 ≥ 85% |

## 回滚
开关 `ARTICLE_DETAIL_FALLBACK_ENABLED=false`（默认）即完全旁路；预算默认 0 ⇒ 付费调用全部拒绝（安全默认）。

## 风险
- 预算默认 0 会让**发现**侧付费渠道（STEP-04）也被拒——这是有意的安全默认，启用渠道时必须同时配置预算（写入 STEP-11 运维说明）。
