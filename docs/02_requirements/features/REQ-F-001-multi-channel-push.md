---
id: REQ-F-001
type: requirement
title: 多渠道机器人推送
status: active
owner: product
实现度: 已实现
验收锚:
  - apps/api/tests/test_r19_notification_paths.py
  - apps/api/tests/test_direct_push_persists_notification.py
  - apps/api/tests/test_admin_push_persists_notification.py
  - apps/api/tests/test_push_persist_order.py
  - apps/api/tests/test_notification_history.py
  - apps/api/tests/test_push_providers.py
  - apps/api/tests/test_w3_push_scheduler.py
  - apps/web/e2e/bots-tasks.spec.ts
最后核验 commit: c687a33（2026-10-22，STEP-19 收口判「已确认」）
---

# REQ-F-001 多渠道机器人推送

> 母文件 `../product-requirements.md` 只留摘要与链接；本文件是这一条的**单一详源**。
> 实现度取值来自规划文档的实测判词，不来自印象（卡面 S17.1.1.1）。

## 需求条目

- **渠道**：飞书、钉钉、企业微信、微信 ClawBot、通用 Webhook、站内通知
- **触发方式**：定时（Cron）、事件触发（新文章 / 热点更新 / 日报）、手动
- **管理**：渠道 CRUD、推送任务 CRUD、推送日志查询、一键测试
- **验收**：各渠道 Webhook 推送可成功送达，定时任务按 Cron 准时触发

## 实现度判据（逐条给出处）

| 判据 | 出处与原判词 |
|---|---|
| 三路径（定时 / 事件 / 手动）都落 `notifications` | `docs/06_validation/evidence/EVD-V3-19/verdicts.md` 对 S19.1.1 判「**已确认**」；缺口由 STEP-23（手动/测试直投）与 STEP-26（admin 直投）补齐，同一件里写明「需要谁接着做：**无**」 |
| Provider 契约 `delivered=True/False + reason + response_data` | `AGENTS.md` 关键约束第 6 条 + `apps/api/app/services/push.py` 模块 docstring「投递使用真实 Provider…6 渠道均可实际投递」 |
| 调度器领取与重试 | `apps/api/app/services/push_scheduler.py`（SKIP LOCKED 短锁 + 指数退避 + 死信终态），`test_w3_push_scheduler.py` |

## 曾经写错、现已闭合的两处（留痕用，别当待办）

1. `product-requirements.md` 在 2026-10-12 写过「**本需求未闭环的一处（暂无任务认领）**：
   `persist_web_notification` 只有调度器一个调用点，两条直投 API 不写历史」——
   该陈述已被 STEP-23 / STEP-26 否证，本次拆分时从母文件删除，历史原文见
   `git log -p docs/02_requirements/product-requirements.md`。
2. `AGENTS.md` 的「站内通知全链路已通」与「写侧/读侧 history 待建 R1.2b/c/d」自相矛盾，
   实况是读侧已在（`apps/api/app/api/v1/system.py` 的 `/notifications`、`/notifications/history`、
   `/notifications/read`），已按 STEP-17 S17.2.1 合并成单一陈述。

## 尚未闭合的真实缺口

**微信 ClawBot 需要部署服务**（不在本仓可验证面内）。这是一条外部前置，不是"未实现"：
本地与 CI 都无法证明其投递，故 EVD 侧一律标未测，不得冒充读数。
