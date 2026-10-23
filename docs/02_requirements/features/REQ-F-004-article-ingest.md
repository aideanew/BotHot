---
id: REQ-F-004
type: requirement
title: 公众号链接入库
status: active
owner: product
实现度: 证据不足（按 04 §4.3 的判据锚有具名用例满足，但规划文档侧从未给过这条的实现度判词）
验收锚:
  - apps/api/tests/test_e2e_collection.py
  - apps/api/tests/test_collection_contract.py
  - apps/api/tests/test_extractor.py
  - apps/api/tests/test_normalizer_quality.py
  - apps/api/tests/test_categorizer.py
  - apps/api/tests/test_d04_short_link.py
  - apps/api/tests/test_article_identity.py
  - apps/api/tests/test_kb_longlink_ingest.py
  - apps/api/tests/test_p0_asset_cache.py
  - apps/api/tests/test_idempotency_lock.py
  - apps/api/tests/test_r04_jobs.py
  - apps/api/tests/test_job_worker.py
  - apps/web/tests/r063-batch-ingest.spec.ts
  - apps/web/tests/t0263-ingest-status-poll.spec.tsx
最后核验 commit: bf141d5（2026-10-23 现读；判据见正文，非规划文档判词）
---

# REQ-F-004 公众号链接入库

## 需求条目

- 链接解析（RedFox + Wandao）
- 内容标准化（Markdown + 元数据）
- 质量评分与分类标签
- 短链映射（0 重复请求）
- **验收**：公众号文章可入库为 ContentAsset

## 实现度为什么写「证据不足」而不是「已实现」

卡面 S17.1.1.1 要求取值来自 01/coverage 的**实测条目**，不得凭印象。现读结果：
`docs/任务规划V0.6.0/…` 与 `coverage_and_domain_audit_13acacc.txt` 对 F-004 只有
「✅ 有 STEP 覆盖」这一格（那是**规划覆盖度**，不是实现度判词），全仓没有任何一份
规划文档给过 F-004 的实现度判词。⇒ 按卡面阻塞条件 ②，标 `证据不足` 并列入未决，
不填「已实现」——即使下面这些判据锚今天都有通过的用例在守。

## 04 §4.3 判据锚的满足情况（可读，但不构成"判词"）

| 判据锚（一句可验证的话） | 满足它的用例 |
|---|---|
| 短链二次入库 `fetch_count == 1 ∧ hitCache == True` | `test_d04_short_link.py`、`test_p0_asset_cache.py` 机器门①③ |
| 长链同号两篇 0 重复（也不互相顶正文） | `test_kb_longlink_ingest.py::test_two_distinct_long_links`（P-3 转正）、`test_p0_asset_cache.py` 机器门④（STEP-06 S6.2.2 新增） |
| 六渠道「发现→清单→入列→入库→二轮 Diff=0」 | `test_e2e_collection.py`（STEP-06 S6.1，2026-10-22 起常驻） |

## 已登记

「F-004 有测试锚但从未有实现度判词」这一文档侧缺口进
`docs/任务规划V0.7.0/05-风险自检与局限.md` §1 未决，由规划方补判词或改判据口径。
