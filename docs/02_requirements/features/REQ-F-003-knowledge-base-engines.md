---
id: REQ-F-003
type: requirement
title: 知识库管理与可插拔引擎
status: active
owner: product
实现度: 部分（builtin 已实现；main/coze/dify/fastgpt 四个引擎位是骨架，属裁决 D-V3-03 的显式不做）
验收锚:
  - apps/api/tests/test_engines_capability.py
  - apps/api/tests/test_p4_engines.py
  - apps/api/tests/test_be02_engine_routing.py
  - apps/api/tests/test_engine_delete.py
  - apps/api/tests/test_wc_engine_delete.py
  - apps/api/tests/test_spaces_api.py
  - apps/api/tests/test_r02_docs_lifecycle.py
  - apps/api/tests/test_r02_batch_docs.py
  - apps/web/tests/engine-switcher-states.spec.tsx
  - apps/web/tests/engines.spec.ts
  - apps/web/tests/r054-space-detail-honesty.spec.tsx
最后核验 commit: 482769a（2026-10-21，S30.3 复核；首轮 81205f1）
---

# REQ-F-003 知识库管理与可插拔引擎

## 需求条目

- 多空间隔离（用户级 + 公共库）
- LangBot RAG 1:1 映射
- 可插拔引擎：5 个引擎位 `builtin` / `main`（RAGFlow 拓展系）/ `coze` / `dify` / `fastgpt`
- 公共库共享与发布（allowlist）
- **验收**：空间 CRUD 正常，引擎切换可用

## 实现度判据（这一条是本基线里唯一"实现度必须写部分"的功能需求）

| 判据 | 出处与原判词 |
|---|---|
| 空间/文档/公共库面已实现 | 上述 `test_spaces_api.py`、`test_r02_*` 等具名用例；`coverage_and_domain_audit_13acacc.txt` 未把该域列为缺口 |
| 引擎位只有 `builtin` 为真 | `docs/任务规划V0.7.0/evidence/13acacc/coverage_and_domain_audit_13acacc.txt`：「**已诚实标注但未实现**…唯一成片的骨架区」；`docs/06_validation/evidence/EVD-V17-30/s30_3_step13_verdict.md`：`grep -c NotImplementedError = 16` PASS |
| 骨架不实接是**裁决**不是遗漏 | D-V3-03（签 A）：本轮缺凭据与预算，不实接；实接排期在 `docs/04_engineering/backlog.md` TECH-003b |
| 界面诚实性（三态文案可区分） | `apps/api/tests/test_engines_capability.py` + `apps/web/tests/engine-switcher-states.spec.tsx`；契约字段 `reason ∈ {ok, not_allowlisted, key_missing, not_implemented}` |

## 为什么"骨架"不算已实现也不算未实现

`GET /api/v1/engines` 的 `reason` 把「未开放 / 未登记 Key / 未实接」三态分开回给消费面，
`PATCH .../engine` 对不可用引擎一律 403（10004）且文案与 `reason` 一一对应，
删除空间走的是真回滚路径而非 `NotImplementedError` 冒泡（`test_engine_delete.py` /
`test_wc_engine_delete.py`）。⇒ 用户可感知的行为是**已完成且诚实标注的**，
而"引擎真能检索"这件事确实没做。把这一条写成"已实现"或"未实现"都是错的，
所以实现度字段按判据写成"部分"并逐处注明是哪一半。
