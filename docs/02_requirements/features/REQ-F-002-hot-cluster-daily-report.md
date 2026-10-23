---
id: REQ-F-002
type: requirement
title: 热点聚簇与日报
status: active
owner: product
实现度: 已实现
验收锚:
  - apps/api/tests/test_r19_hot_chain.py
  - apps/api/tests/test_w2_cluster.py
  - apps/api/tests/test_w2_scorer.py
  - apps/api/tests/test_w2_report.py
  - apps/api/tests/test_wa_hot_scoring.py
  - apps/api/tests/test_hot_scorer_batch.py
  - apps/web/tests/w4-hot.spec.ts
  - apps/web/e2e/hot.spec.ts
最后核验 commit: c687a33（2026-10-22，STEP-19 收口判「已确认」）
---

# REQ-F-002 热点聚簇与日报

## 需求条目

- **聚簇**：多篇文章按主题聚簇为热点事件（TF-IDF 字 bigram，候选上限护栏 + 倒排剪枝）
- **评分**：48h 独立来源数加权，24h 减半时间衰减
- **Feed**：信息流首页，类型/分类筛选，热度排序
- **日报**：TOP 10 热点 + LLM 生成摘要，Markdown 格式
- **验收**：聚簇结果合理，日报可自动/手动生成

## 实现度判据

| 判据 | 出处与原判词 |
|---|---|
| 评分**已接线**（不是算完不写回） | `AGENTS.md`「热点」段；`test_r19_hot_chain.py` 与 `test_hot_scorer_batch.py` 钉住「worker 聚簇后评分 + 日报前兜底重算 + 每小时 hot_rescore 周期重评 + Feed 分数同步回刷」 |
| Feed 三类生产者 + 业务日界 Asia/Shanghai | 同上段；`test_w2_integration.py` |
| 日报 LLM 失败走降级 | `AGENTS.md`「LLM 摘要并行化 `Semaphore(3)` + 失败降级」；判据锚见 `docs/任务规划V0.7.0/04-剩余可执行大纲体系.md` §4.3 行「REQ-F-002」 |

## 缺口与局限

聚簇算法升级（嵌入向量 + pgvector）是**显式排除项**，见 `docs/04_engineering/backlog.md` 的
HOT-005；`apps/api/app/providers/embedding.py` 目前生产零调用方（仅测试引用），不要把"模块存在"读成"已接入"。
