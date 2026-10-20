# EVD-V14-26：STEP-26 管理端直投补写站内历史与三路径顺序统一

- 日期：2026-10-20
- 改卡依据：**D-V17-03**（选项 A：先记 PushLog 与计数，后落通知，最后 commit）
- 基线：`main@c5c0160`（D-V17-03 裁决提交）
- 交付提交：`f383f0de4e1cffa9507ef9f306387645bdbaa063`（`f383f0d`）
- 环境：Win10 + Git Bash；`apps/api/.venv` Python 3.12.10；`PYTHONUTF8=1`；本机隔离 PostgreSQL 16.4（`127.0.0.1:5547/bothot_test`，trust）；本卡不依赖 Redis 可达性。

## 1. S26.1.1 改前红原文

命令：

```bash
cd apps/api && python -m pytest \
  tests/test_admin_push_persists_notification.py \
  tests/test_push_persist_order.py -q
```

读数：`1 failed, 4 passed in 2.73s`。红原文（管理端 web 直投没有落历史）：

```text
_________________ test_admin_web_push_is_visible_to_the_recipient _________________

    assert provider.sent, "provider 未被调用，后面的历史断言就无从谈起"
    row = (await db_session.scalars(select(Notification).where(Notification.message == body))).one_or_none()
>   assert row is not None, "管理端 web 直投没有写站内通知历史"
E   AssertionError: 管理端 web 直投没有写站内通知历史
E   assert None is not None

tests\test_admin_push_persists_notification.py:95: AssertionError
```

同时 3 条 S26.2.4 失败路径用例改前为绿（如实记录：调度器那条改前也可能绿，因为改前
`persist` 先于 `db.add(log)`，但通知落库失败本身不阻止后续 PushLog 落库）。

## 2. 改后绿

```text
tests/test_admin_push_persists_notification.py
tests/test_push_persist_order.py
tests/test_direct_push_persists_notification.py
tests/test_notification_frame_id.py

22 passed in 3.39s
```

推送域（含 `test_r11_push.py`）：

```text
33 passed, 1 warning in 34.64s
```

全量真库（`python -m pytest -q`，本机隔离 PG）：

```text
1991 passed, 6 skipped, 1 warning in 925.50s (0:15:25)
```

对照 STEP-30 基线 1986 passed / 6 skipped：增量精确等于本卡新增 5 条连库用例
（`test_admin_push_persists_notification.py` 2 + `test_push_persist_order.py` 3），0 failed。

## 3. S26.2.1 管理端直投（`services/push.py`）

`PushService.push` 与另外三条 web 路径同形：

1. `channel == "web"` 时投递前 `gen_uuid()` 预铸 `notification_id`；
2. 投递成功且 `result.delivered` 时调用 `persist_web_notification(self._session, push_msg)`；
3. 随后 `await self._session.commit()`（`get_db` 不自动提交，管理端路径没有自己的
   `db.add(log)`/commit）。

反向：非 web 渠道不预铸、不落库、不提交；投递失败也不落库。判据见
`test_admin_push_persists_notification.py::test_admin_non_web_push_does_not_write_in_app_history`。

## 4. S26.2.2 顺序统一（只移动调度器这一处调用）

改前/改后（`push_scheduler.py::_execute_task`）：

| 项 | 改前 | 改后 |
|---|---|---|
| `db.add(log)` | `:242` | `:237` |
| `total/success_push_count += 1` | `:243-245` | `:238-240` |
| `persist_web_notification(...)` | `:229` | `:245` |
| `await db.commit()` | `:247` | `:247` |

两处直投未动代码：`bots.py` run-now `db.add(log) :502` → persist `:521`；test-push
`db.add(log) :667` → persist `:681`，本来就满足「先回执、后通知、再 commit」。

唯一约定写进 `persist_web_notification` docstring：有投递回执的调用方（调度器、
run-now、test-push）先 `db.add(PushLog)` 与计数，再调用本函数，最后 commit；管理端
直投没有 PushLog，投递成功后调用本函数并 commit；本函数不提交事务。

## 5. S26.2.3 文本纠真与计数口径

- `providers/push/web.py:40-42`：删掉「直投路径不落库、无 id 可读」的旧断言，改为
  「四条 web 路径都会预铸；provider 仍保留无 id 不写 null 的防御契约」。
- `tests/test_notification_frame_id.py`：模块 docstring 改为「载荷层锁 provider 防御契约」；
  用例 `test_frame_omits_id_key_when_absent` 更名为
  `test_frame_omits_id_key_when_message_has_no_id`，只改名称/注释，断言未动。
- `persist_web_notification` docstring：删掉「未预铸（如直投）」的旧口径，改为四条路径
  均预铸；保留「没有预铸的调用方退回 ORM 自铸」作为防御。

计数：

```text
$ git grep -n "persist_web_notification(" apps/api/app
push_scheduler.py:274:async def persist_web_notification(...)   # 定义
bots.py:521 / bots.py:681 / push.py:73 / push_scheduler.py:245  # 4 个调用点
```

即：**调用点 4 处**（卡面口径），原始 grep 5 行（含 1 行定义）。

`git grep -n "直投不落库\|未预铸" apps/api`：**1 处残留**，位于
`apps/api/tests/test_direct_push_persists_notification.py:177` 的断言失败文案
（STEP-23 文件，不在 D-V17-03 授权范围）。本卡未越权修改；生产代码与文档中该短语为 0。
详见 §7 残留登记。

## 6. S26.2.4 失败路径（三条路径各一条）

`tests/test_push_persist_order.py` 让 `persist_web_notification` 内的 `Notification`
在 flush 时违反 `VARCHAR(256)`（title 置 300 字符），而不是构造时抛错，以此证明
savepoint 失败后同事务回执仍在。三条用例分别覆盖调度器、run-now、test-push。

断言：`push_logs` 有 1 行 success、`total_push_count`/`success_push_count` 均为 1、
`notifications` 无该条消息、调用本身不抛错。

改前读数：三条均绿（4 passed 中的 3 条）。改后：三条均绿。

savepoint 实测（直接路径，SQL 事件监听；最终 `logs=1 notes=0 total=1 success=1`）：

```text
SAVEPOINT sa_savepoint_2
INSERT INTO push_logs (...)
SAVEPOINT sa_savepoint_3
INSERT INTO notifications (...)
ROLLBACK TO SAVEPOINT sa_savepoint_3
RELEASE SAVEPOINT sa_savepoint_2
```

结论：`begin_nested()` 先 flush 待写对象再开自己的 savepoint ⇒ 上面的 PushLog 在
persist savepoint 之外，通知行回滚不会撤销它，不存在「撤销后由 commit 重插」。
据此把 `bots.py:514-518` 那段旧注释改成实测结论（代码未动，D-V17-03 授权）。

## 7. 残留登记（需规划方裁决，不由本卡修）

已按执行助手指令「新缺陷从 P-50 起登记」写入 `docs/任务规划V0.12.0/00-README.md`：

1. **P-50（验收 grep 残留）**：`test_direct_push_persists_notification.py:177` 的断言失败文案
   仍含「未预铸」。该文件是 STEP-23 交付物，不在 STEP-26 允许修改清单内；改成「没有预铸」
   只需一个词，但本卡不越权。原始验收 `git grep ... apps/api = 0` 因此为 1（生产面为 0）。
2. **P-51（同句注释第二处）**：`bots.py:674-679`（test-push 路径）仍有「savepoint 回滚会
   连带撤销未 flush 的 PushLog」的旧结论。D-V17-03 只授权修改 `513-518` 那一段，故未改；
   实测结论（§6）同样适用于该处，建议下一张触碰 `bots.py` 的卡同步。

## 8. CI 读数

head_sha = `f383f0de4e1cffa9507ef9f306387645bdbaa063`：

| 工作流 | 结论 | run id / 备注 |
|---|---|---|
| CI | success | run `39383488851` |
| CI-Windows | success | run `39383488791`；门禁读数 `failed=0 total_skipped=545 baseline=545`（零余量）。构成：PG-DSN-未设置 436（431 + 本卡新增 5）、PG-不可达 104、Redis-不可达 3、LangBot-不可达 1、代理变量未设 1；backend `1452 passed, 545 skipped, 0 failed in 1010.03s`；frontend `Test Files 47 passed (47)` |
| Security | success | run `39383488768` |
