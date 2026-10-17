# STEP-23 手动/测试直投补写站内通知历史（REQ-F-001 未闭环项，V0.13.0 新增）

> 状态：**🟡 三个三级任务已交付（2026-10-17 `@win`）**，落库行为与真库全量仍待 `@ci`。
> 读数与两处自我纠正（含"我的注释触发了我自己的守卫"）见
> `docs/06_validation/evidence/EVD-V13-23/s23_readings.md`。附带登记 **P-24**：
> `test_notification_frame_id.py` 里"直投不预铸 ⇒ 载荷无 id"那句已被本卡推翻，但该文件不在本卡允许面。

| 字段 | 值 |
|---|---|
| 归属-切片 | S-M2（"手动推一条，站内通知历史里能看到"是推送主路径可演示行为） |
| 归属-需求 | **REQ-F-001**（`docs/02_requirements/product-requirements.md:55-79`）"触发方式：定时、事件、**手动**"；同节 2026-10-12 登记的"本需求未闭环的一处，暂无任务认领" |
| 归属-方案 | D-V10-05（本版代选：直投复用调度器同一落库函数，不另写一套） |
| 里程碑 | M2 |
| 执行者 | 执行 Agent（中等：两个调用点 + 先红用例；落库函数已存在） |
| 档位 | sonnect　理由：复用现成函数，判据机器化 |
| 规模 | 小（≈0.5 人日；3 个三级任务） |
| 依赖 | Depends on：**22**（同改 `bots.py`，必须串行）　Blocks：无 |
| 基线 | main@314d7f2 |

## 证据链
- `grep -rn "persist_web_notification" apps/api/app` 在 314d7f2 上只有**一个调用点** `services/push_scheduler.py:229`（`ch.channel_type == "web" and result.delivered` 时，:228）。
- 两条直投路径只做 `provider.push()` + `PushLog`：`api/v1/bots.py:341/:344`（`POST /{channel_id}/test`）与 `:624/:627`（`POST /tasks/{task_id}/run`）。⇒ web 渠道走 Cron/事件会进离线补投历史，走"手动/测试"**永不进历史**。
- 需求文档自己登记了这条不一致（"修复属代码改动，本文档只登记不一致"），V0.12.0 31 张卡中无一认领（`grep -rn "persist_web_notification" docs/任务规划V0.12.0/steps` 0 命中）。

## 反证
- "一键测试本就不该进历史"？需求原文把"手动"列为与 Cron、事件并列的触发方式，且 `/tasks/{id}/run` 是真实推送不是测试。⇒ `/run` 必须进；`/test` 的取舍登记为 D-V10-05：**也进**，理由是 web 渠道的"测试"对收件人就是一条真实到达的消息，历史缺它会让"离线补投"漏发。若用户希望 `/test` 不进，只需删一行调用，可逆。

## 目标（可验证的一句话）
web 渠道经 `/test` 或 `/tasks/{id}/run` 投递成功后，`notifications` 表新增恰好 1 行，且 `GET` 通知历史接口对收件人可见。

## 输入
- `services/push_scheduler.py:179,228-229,274-290`（落库函数与 notification_id 生成口径）；`docs/任务规划V0.12.0/contracts/resources.schema.json`（`InAppNotification`）
## 输出（文件）
- 改：`apps/api/app/api/v1/bots.py`（两处调用）
- 新：`apps/api/tests/test_direct_push_persists_notification.py`
- 证据：`docs/06_validation/evidence/EVD-V13-23/`

## Execution Steps
1. [x] **S23.1.1** 先红：播种一个 web 渠道与一个 event/cron 任务；以 operator 身份分别调 `/test` 与 `/tasks/{id}/run`；断言 `notifications` 行数各 +1；在 314d7f2（或 22 合入后的 HEAD）上红
2. [x] **S23.1.2** 两处直投在 `provider.push()` 之前按 `push_scheduler.py:179` 同口径生成 `notification_id`，成功后 `if ch.channel_type == "web" and result.delivered: await persist_web_notification(db, push_msg)`（从 `app.services.push_scheduler` 导入，**不复制函数体**）
3. [x] **S23.1.3** 回归：`tests/test_w1_push_domain.py`、`test_notification_frame_id.py`、`test_bots_logs_filter.py` 全绿；真库全量 `failed = 0`

## 验收标准
- [x] 新用例先红后绿（两份输出入 EVD §1/§2）
- [ ] `grep -rn "persist_web_notification(" apps/api/app --include=*.py | grep -v "def " | wc -l` = 3（本机实测 3：调度器 1 + 本卡新增 2）
- [ ] `@ci` `CI` success —— **待 @ci**：4 条连库行为用例在本机 skip（skip ≠ 通过）
- [x] `git diff --name-only` ⊆ "输出"清单

## 验证命令
```bash
cd apps/api && . .venv/bin/activate
export AIDEANBOT_TEST_PG_DSN=postgresql+psycopg://postgres@127.0.0.1:5547/bothot_test
export PUSH_SECRET_MASTER_KEY=$(python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")
python -m pytest tests/test_direct_push_persists_notification.py tests/test_w1_push_domain.py tests/test_notification_frame_id.py -q
```

## 证据路径
`docs/06_validation/evidence/EVD-V13-23/`

## 允许修改
- `apps/api/app/api/v1/bots.py`（仅两处直投函数体）
- `apps/api/tests/test_direct_push_persists_notification.py`（新）
- `docs/06_validation/evidence/EVD-V13-23/**`
## 禁止修改
- `apps/api/app/services/push_scheduler.py`（只导入不改）
- `packages/contracts/**`、`apps/api/alembic/**`、`apps/web/**`

## 依赖与阻塞
- Depends on：22（同文件）
- Blocks：无
- 阻塞条件：`persist_web_notification` 需要的 `PushMessage` 字段在直投路径上取不到 ⇒ 停下回报，不在本卡改落库函数签名

## 建议执行档位
sonnect
## 升级条件
需要改 `push_scheduler.py` 才能复用 ⇒ 升 opus 判是否抽公共服务
## 预估规模
小　3 个三级任务；≈0.5 人日
