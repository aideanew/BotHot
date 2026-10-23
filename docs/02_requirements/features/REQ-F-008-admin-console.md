---
id: REQ-F-008
type: requirement
title: 管理后台
status: active
owner: product
实现度: 部分（后端读面齐；coverage 那句「前端无消费者（实测 0 命中）」自 STEP-14b 起已不成立，但 SLA 级判词未重发）
验收锚:
  - apps/api/tests/test_admin_contract.py
  - apps/api/tests/test_r11_admin_routes.py
  - apps/api/tests/test_r48_admin_jobs.py
  - apps/api/tests/test_r11_batch_admin.py
  - apps/api/tests/test_r11_engine_keys.py
  - apps/api/tests/test_system_settings.py
  - apps/api/tests/test_health.py
  - apps/api/tests/test_health_ready.py
  - apps/api/tests/test_process_heartbeat.py
  - apps/web/tests/admin-ops-panels.spec.tsx
  - apps/web/e2e/admin.spec.ts
最后核验 commit: 8e5b23e（2026-10-22，STEP-14b / STEP-14a 收口后现读）
---

# REQ-F-008 管理后台

## 需求条目

- 知识空间 / 文档 / 订阅 / 引擎管理
- Bot 渠道 / 推送任务管理
- 热点中心 / 日报管理
- Onboarding 引导
- **验收**：管理端各功能 CRUD 正常

## 两条互相冲突的读数，本文件按哪条写

| 说法 | 出处 | 现读 |
|---|---|---|
| 「后端有接口、前端无消费者（实测 0 命中）」 | `coverage_and_domain_audit_13acacc.txt`（13acacc 时点） | **已过期**：`apps/web/tests/admin-ops-panels.spec.tsx` 与 `apps/web/e2e/admin.spec.ts` 自 STEP-14b 起在跑，管理五屏 + 采集配置屏有渲染契约与角色门判据 |
| 「admin 分页清单已收敛到目标壳」 | STEP-14a（`test_admin_contract.py`，8 条） | 成立 |

⇒ 实现度写「部分」而不是「已实现」，因为 F-008 的验收句是「各功能 CRUD 正常」，
而**四屏主路径在 mock 档结构上不可达**（演示态会话 `is_admin` 恒 false，见台账 P-88），
真后端档 e2e 仍未取得读数。这不是"没做"，是"做的面与验收句的面差一层"，
该差层由 P-88 挂给规划方裁定。
