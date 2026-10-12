---
id: STEP-10
title: V0.1.0 遗留收口（安全与数据可见性优先）
priority: S10.1/S10.2 = P0；S10.3 = P1；S10.4 = P2
depends: 无（与 STEP-00 并行起步）
estimate: 1 人日（不含人工）
---

# STEP-10 V0.1.0 遗留收口

## 目标
关闭上一步遗留中**会造成真实伤害**的两项（凭据仍可用、他人通知可见），把 G-19/TASK-017 这条已做一半的通知去重链收尾，其余阻塞卡明确移交，不再以"未完成"状态悬挂。

## 依据
- TASK-001：`docs/任务规划V0.1.0/_workspace/progress.md` T44 "TASK-001 轮换无证据"；口令仍存在于 public 仓库历史提交 `01f6892`。
- G-21：`services/push_scheduler.py` 构造 `PushMessage` 不设 `external_user_id`（对照 `api/v1/bots.py:332` 传 `ch.user_id`）；`persist_web_notification` 由此恒 `is_broadcast=True`（`push_scheduler.py:277-291`）。采集链 `on_article_indexed → new_article` 事件触发的定时 web 通知会被所有登录用户看到。
- G-19：`persist_web_notification` 生产调用点仅调度器一处；`bots.py` 两处直发绕过落库。
- TASK-017 / G-20：`apps/web/lib/api/notifications.ts:61-71` 逐字段重建载荷、丢弃 `id`，卡片授权未覆盖该文件。

## 允许修改
`apps/api/app/services/push_scheduler.py`、`apps/api/app/api/v1/bots.py`、`apps/web/lib/api/notifications.ts`、`apps/web/components/**/NotificationBell*`、对应测试、`docs/任务规划V0.1.0/05_execution/task-index.md`（仅状态列）、`docs/06_validation/evidence/EVD-001/**`
## 禁止修改
采集域全部文件（与 STEP-01…09 零交集，保证可并行）。

## 原子任务

| 编号 | 类型 | 动作 | 验收命令 |
|---|---|---|---|
| S10.1.1 | 👤 | 运维 `ALTER ROLE … PASSWORD …` 轮换共享底座账号；用旧口令连接应认证失败；更新部署 secret；EVD-001 记录时间与验证结果（**不写任何口令值**） | 人工；EVD-001 存在 |
| S10.1.2 | 👤 | （可选）评估是否用 `git filter-repo` 清除历史；public 仓库已被 fork/clone 的可能性使"清史"不能替代轮换 | 人工决定记录 |
| S10.2.1 | 👤 | D-V2-07：定时 web 通知是否本意广播 | 人工 |
| S10.2.2 | 🔴🛠 | 若"否"：调度侧按 `PushTask.created_by` 解析目标用户 `sub` 填 `external_user_id`；测试：定时任务投递后 `notifications.is_broadcast=False` 且 `sub` 为创建者 | 改前 FAIL |
| S10.3.1 | 👤 | G-19：直发（测试推送 / 立即推送）是否进站内通知历史 | 人工 |
| S10.3.2 | 🛠 | 按裁决：①两处直发也调用 `persist_web_notification`；或②在 REQ-F-001 写明边界 | ①：`grep -c persist_web_notification app/api/v1/bots.py` = 2；②：文档 grep 命中 |
| S10.3.3 | 🔴🛠 | TASK-017 授权扩到 `notifications.ts`：保留帧 `id`；`NotificationBell` 以 `id` 去重（无 id 回退旧逻辑） | vitest：同 id 两帧只显示 1 条；无 id 帧不受影响 |
| S10.4.1 | 📄 | V0.1.0 `task-index.md` 中 17 张阻塞卡状态改为"移交 V0.3.0（待 D-xx）"，保留原卡不删 | `grep -c "移交 V0.3.0" task-index.md` = 17 |

## 回滚
S10.2.2/S10.3.* 代码 `git revert`；S10.1 不可回滚（也不应回滚）。
