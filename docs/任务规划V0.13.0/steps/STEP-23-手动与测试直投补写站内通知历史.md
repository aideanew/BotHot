# STEP-23 手动/测试直投补写站内通知历史（REQ-F-001 未闭环项，V0.13.0 新增）

> 状态：**🟡 三个三级任务已交付并经 `@ci` 转绿（`10c1019`，run 39030366256），但独立复核判完成度 ≈70% ⇒ 已开返工轮 S23.4**。
> 返工的缘由不是行为回归，而是**用例覆盖面**：第一版四条连库用例的夹具全都 `user_id=None`，
> 于是它们判的只有广播那一支；定向渠道会把 `bot_channels.user_id`（= `users.id`）原样写进
> `Notification.sub`，而历史查询按 SSO sub 过滤 ⇒ 那是一条谁都查不到的**死行**，
> 而卡面"对收件人可见"这半句从来没有用例判过。
> 读数与两处自我纠正（含"我的注释触发了我自己的守卫"）见
> `docs/06_validation/evidence/EVD-V13-23/s23_readings.md` §1–§3。
> 登记三件不在本卡允许面、因此只登记不顺手做的：**P-24**（`test_notification_frame_id.py` 的旧口径）、
> **P-25**（`web.py:41-42` 与 `persist_web_notification` 自己 docstring 里的"直投不落库/未预铸"两句在
> 本卡之后为假）、**P-26**（`created_by` 列是 `users.id` 外键，后端兜 `"system"` 字面量、
> 前端填 SSO sub ⇒ 建任务路径可达 500，且归属可被 operator 伪造）。

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
- [x] `git diff --name-only` ⊆ "输出"清单 —— **这条在第一版被照字面打了勾，而实际不成立**：
  台账同步要求我同时改 `docs/00_governance/decisions/decision-log.md` 的 D-V10-05 行、
  `V0.12.0/00-README.md` 的 P-24、`V0.13.0/04` 的合计与 `V0.13.0/08` 的执行记录（`831d6e9` 共 4 处清单外文档）。
  现按实改写：**代码面 ⊆ 清单，文档面按 AGENTS"改动须同步文档与进度"另计**，两者不要混着勾。
- [ ] **S23.4（返工轮，独立复核开出）** 定向 web 渠道的收件人锚
  - [x] S23.4.1 先红：`test_directed_web_channel_history_row_is_keyed_by_the_recipient_sub`（本机 skip、`@ci` 判）
  - [x] S23.4.2 修：`bots.py` 的 `test_push` 解析 `User.sub` 后才填 `external_user_id`（只改 web 一支）
  - [x] S23.4.3 反证两条：①`test_unresolvable_sub_never_upgrades_a_directed_push_to_broadcast`
    ——解析不到 sub 时**不许**退化成空串（空串在这条链上 = `is_broadcast=True` ⇒ 定向测试推送
    升级成全站通知）；②`test_direct_push_does_not_feed_channel_user_id_straight_into_the_recipient_anchor`
    ——本机可判的源码早期线（判不到行为，只防回退）
  - [ ] S23.4.4 `@ci`：新增两条连库用例在真库上绿，且全量 `failed = 0`
- [ ] **S23.5（第二轮复核追进）** 写侧判据不等于"可见"
  - [x] S23.5.1 端到端判据：`test_recipient_actually_reads_the_directed_row_back_through_the_history_api`
    ——写入后用收件人自己的 sub 调 `system.notifications_history` 读回来，并加一条"换个人读不到"的反证
    （否则"可见"可能是靠把它变成广播换来的）。不走 HTTP 栈 ⇒ 不需要路由依赖覆盖，也不碰别人的文件
  - [x] S23.5.2 注释按实现改窄：两处直投原写"savepoint 保证落库失败**只回滚通知行**"比实现强——
    `db.add(log)` 在 persist 之前，回滚会把尚未 flush 的 PushLog 一并撤销再由 commit 重插
    （最终行都在，但那是"整体延后重插"）。调度器 `persist → add(log)` 与直投 `add(log) → persist`
    的顺序不一致 + `persist` 吞掉所有异常且无计数器，一并登记 **P-30**
  - [x] S23.5.3 复核的一条 claim 复算后**否掉**：「全仓调用计数实际是 4」——按卡面命令原样跑只有 3 行，
    第 4 条是把 `bots.py:45` 的 import 行算进去（我的模式带左括号，import 行不含括号）。
    记这条是为了说明：**不现跑就直接改卡，卡上那条就会变成迁就某次读数的判据**
  - [ ] S23.5.4 `@ci`：S23.4 + S23.5 的新增连库用例在真库上绿
- [ ] **卡目标句的诚实降格**：上一轮提交标题写"REQ-F-001 那条不一致闭环"**超售**——
  REQ-F-001 的"手动"其实有**第三条**路径（`services/push.py:40-61`，`POST /admin/push` 的服务面
  自铸 `PushMessage` 直接投递、不写历史），它不在本卡允许面（只允许 `bots.py` 两处直投函数体）。
  已登记 **P-29**，默认值 A=补落库 + 一条按收件人 sub 读回的连库用例；B=有意不进历史，
  则必须把 `push.py` 与可见性口径各写一句"此路径不进历史"

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
