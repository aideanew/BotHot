# EVD-V21-51 需求判词与文档纠真（执行助手）

平台 @win（便携 PG16@5547），开工 head `a8c3df9`（STEP-50 交付批），时间 2026-10-25（Asia/Shanghai）。
本卡只改文档；两份读数（后端锚用例、前端 SSE 用例）取自实际运行。

## X-1 roadmap 站内通知行

`roadmap.md:44` 原文「前端订阅侧未实现」已被后续交付推翻（`roadmap.md:77` 自己就列了
`NotificationBell`）。改写为「**前端订阅侧已实现**」，引现读行号：
`apps/web/lib/api/notifications.ts:4`（EventSource 订阅 `GET /api/v1/system/notifications`）、
`apps/web/components/NotificationBell.tsx:68`（`export default function NotificationBell`）。

## X-2 roadmap 当前阶段

`roadmap.md:14` 「当前阶段：v0.6.5 …」→ 「**当前阶段：v1.1.x 维护期**」，引 tag `v1.1.2` = `a221f89`
（2026-10-24 发布，Release 页在册）与 `CHANGELOG.md` 的 `[v1.1.2]` 段。

## X-3 REQ-NF-001 判词

子文件 `REQ-NF-001-performance.md`：frontmatter 实现度「部分（…三条无测量值）」→「**已实现（首测基线，
2026-10-24，STEP-18）**」；四行条目表全部改为「✅ 有」并引 `PERF-baseline-v1.md` 的实测数字
（API p50 5.41–12.82ms / 首 Token 0.76–0.96ms **录制回放** / 入库 p50 26.67–29.95ms / Feed p50 6.15–12.74ms）；
**局限照抄**：条目 2 标注「桩回放的出帧时延，真实网络 RTT 不在测」。总表 `product-requirements.md:84`
判词同步改「已实现（首测基线，2026-10-24）」。

## X-4 端口表拆分（D-V21-05）

`AGENTS.md` 与 `REQ-C-002-port-allocation.md` 的单表拆为**本栈发布 / 外部提供**两段：
- 本栈发布 = `docker/compose.yml` 现读发布行（`:101` "5300:5300"、`:245` "3300:3300"、`:423` "3200:3000"
  含 3000 归主平台的注释）；
- 外部提供 = 5433/6380 两个**历史规划值**（本栈 compose 现读不发布这两个端口——P-78/P-102 判定前的
  过渡口径，如实写明）。
- `test_r19_ports.py` 复跑 **7 passed**（判据不受文档改动影响）。

## X-5 REQ-F-004 判词（实跑）

八个判据锚文件全量实跑（`@win`，PG16@5547）：
`pytest -q tests/test_e2e_collection.py tests/test_collection_contract.py tests/test_extractor.py
tests/test_normalizer_quality.py tests/test_categorizer.py tests/test_d04_short_link.py
tests/test_article_identity.py tests/test_kb_longlink_ingest.py`
⇒ **283 passed / 0 failed**（42.60s）。全过 ⇒ 判「**已实现**」，子文件 frontmatter 与总表判词同步。

## X-6 REQ-F-005 判词（实跑）

`pnpm exec vitest run tests/ask-sse.spec.ts tests/r061-sse-ask.spec.ts` ⇒ **2 files / 35 passed**。
判词改「**部分：组件层已证**」——组件级 SSE 消费与打字机渲染有证据；真后端端到端
（`e2e/r19-chat-stream.spec.ts`）仍零执行，如实保留在判词里。

## S51.6 门禁

`check_docs_consistency.py`（含 STEP-50 新 stack 门）rc=0；`test_r19_ports.py` 7 passed。

## @ci（推送后回填）

_（占位）_
