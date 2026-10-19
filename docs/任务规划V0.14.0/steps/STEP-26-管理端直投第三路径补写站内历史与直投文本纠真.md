# STEP-26 管理端直投第三路径补写站内历史 + 直投文本纠真

| 字段 | 值 |
|---|---|
| 1 执行者 | **执行 Agent-API**（中等，模式已由 STEP-23 建立） |
| 2 验收者 | 独立验证 Agent（PASS / FAIL / UNKNOWN） |
| 3 难度 / 里程碑 | 中 / M2 |
| 4 所属切片 | SL-NOTIFY-1「任何渠道=web 的推送都能在收件人的站内通知历史里读回」 |
| 5 来源 | REQ-F-001、D-V10-05、STEP-23 遗留 P-24/P-25/P-29/P-30、**D-V11-03** |
| 6 证据 | `git grep -n "persist_web_notification(" apps/api/app` 只有 3 处调用（`bots.py:516`、`bots.py:666`、`push_scheduler.py:229`）；`services/push.py:41-62` 的 `PushService.push` 用 `make_push_provider(channel)` 直接投递，而 `providers/push/__init__.py:9` 登记了 `web` ⇒ `POST /admin/push channel=web` 不写历史 |
| 7 档位 | sonnet；升级条件：需要改 `persist_web_notification` 签名或通知表结构 ⇒ opus |
| 8 规模 | 中，5 项，约 0.75 人日 |

## 0. 目标
`POST /admin/push`（`channel=web`）成功投递后，收件人通过站内通知历史 API 能读回同一条消息，且落库行 id 等于投递载荷里的预铸 id；三处直投路径写历史的顺序一致。

## 1. 原子任务
### S26.1 先红
- [ ] **S26.1.1** 新建 `apps/api/tests/test_admin_push_persists_notification.py`（连库）：operator 调 `POST /admin/push`（`channel=web`，收件人为播种用户 sub）⇒ 以收件人身份调历史接口能读到该条消息；改前必须红
  - S26.1.1.a 反向用例：`channel=webhook` 不写站内历史（防止过度落库）

### S26.2 实现
- [ ] **S26.2.1** `apps/api/app/services/push.py`：`channel == "web"` 时与 STEP-23 同形——预铸 id → 投递 → `persist_web_notification`（复用，不复制判据）
- [ ] **S26.2.2** 顺序统一（P-30 的顺序半边）：调度器与两处直投都是 `db.add(log)` 在 persist 之前 ⇒ 写进 `persist_web_notification` docstring，作为唯一约定；有一处不同就改成一致，并在 EVD 写出 before/after
- [ ] **S26.2.3** 文本纠真（P-24/P-25）：`apps/api/app/providers/push/web.py:41-42` 与 `persist_web_notification` docstring 里"直投不落库/未预铸"两句改成事实；`apps/api/tests/test_notification_frame_id.py` 的误导性注释/用例名改窄（只改名与注释，不改断言）

### S26.3 证据
- [ ] **S26.3.1** `docs/06_validation/evidence/EVD-V14-26/s26_readings.md`：先红原文、改后绿、`git grep -n "persist_web_notification(" apps/api/app` = 4 处、`@ci` run id

## 2. 验收标准
- [ ] 新文件真库全绿，改前红有原文
- [ ] `git grep -n "直投不落库\|未预铸" apps/api` = 0
- [ ] 全量 0 failed；三工作流绿

## 3. 验证命令
```bash
cd apps/api && python -m pytest tests/test_admin_push_persists_notification.py tests/test_direct_push_persists_notification.py tests/test_notification_frame_id.py -q
git grep -n "persist_web_notification(" apps/api/app
```

## 4. 允许修改
- `apps/api/app/services/push.py`、`apps/api/app/providers/push/web.py`（仅 docstring/注释）、`persist_web_notification` 所在文件（仅 docstring）
- `apps/api/tests/test_admin_push_persists_notification.py`（新建）、`apps/api/tests/test_notification_frame_id.py`（仅名称与注释）
- `docs/06_validation/evidence/EVD-V14-26/**`

## 5. 禁止修改
- `apps/api/app/api/v1/bots.py`（STEP-24/25 所有）、`apps/api/app/services/roles.py`
- 通知表结构、`database/**`、`alembic/**`
- `persist_web_notification` 的异常吞没行为与计数器（P-30 计数器半边属 STEP-05）

## 6. 依赖与阻塞
- Depends on：STEP-23 ✅、STEP-25（`/admin/push` 的 operator 门要先确定）
- 阻塞条件：`/admin/push` 的收件人锚不是 sub（与 STEP-23 返工轮 7a252f4 同类）⇒ 停，按 STEP-23 的收件人锚规则处理并登记
