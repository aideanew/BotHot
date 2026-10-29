---
id: REQ-F-008
type: requirement
title: 管理后台
status: active
owner: product
实现度: 已实现（命题范围：四屏，STEP-62 现读 2026-10-29）：真后端档 e2e `apps/web/e2e/admin.spec.ts` 取到读数——run `40808385199` 步 13 `6 passed / 1 skipped`（7 条里 6 条 `✓`：① 游客守卫 350ms / ③ 非 admin 出口 427ms / ④ 375px 无溢出 224ms / ⑤ 五屏切换 577ms / ⑥ 告警条 417ms / ⑦ 375px 密钥表 328ms），唯一的 skip 是 ② 键盘可达（real 档按 P-131）；读数见 `docs/06_validation/evidence/EVD-V24-60/s60_readings.md` §6.2。写路径（CRUD）不在本条命题范围，证据见下节
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
最后核验 commit: 8e5b23e（2026-10-22，STEP-14b / STEP-14a 收口后现读）；实现度于 2026-10-29 STEP-62 按 run `40808385199` 重判
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

## 命题范围与未覆盖面（STEP-62 重写，原「实现度写「部分」」那段已作废）

升格的依据是**原判据缺口被填上**：P-88 记的是「四屏主路径在 mock 档结构上不可达、真后端档无读数」，
而 STEP-60 让真后端档有了读数（`admin.spec.ts` `6 passed / 1 skipped`，run `40808385199`），
卡面第 13 条阻塞条件「59/60 未达标 ⇒ 005/008 保持部分」的前提已反转。

**与 D-V21-06 的关系说清**：那条裁决是「**不为 mock 档造 admin 会话**，后台四屏判词维持部分」——
前半句至今有效（mock 档仍不造 admin 会话，本条判词不借 mock 档成立）；后半句的前提是
「除了 mock 档没有别的档能跑到四屏」，该前提被真后端档读数推翻，故判词随证据走。

**未覆盖面**：本条验收句是「管理端各功能 CRUD 正常」，而四屏 e2e 只证**渲染与切屏**，
写路径仍只由 API 层与组件层覆盖——`apps/api/tests/test_admin_contract.py`（契约面 8 条）
与 `apps/web/tests/admin-ops-panels.spec.tsx`（组件层渲染 + 提交载荷）。四屏 e2e 里没有一条
真发出写请求，所以「CRUD 正常」的断言面落在那两处，不落在这里。
