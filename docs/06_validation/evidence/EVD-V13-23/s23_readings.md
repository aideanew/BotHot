# EVD-V13-23 · 手动/测试直投补写站内通知历史（执行方读数）

基线 `main@a6f54e1`；卡 `docs/任务规划V0.13.0/steps/STEP-23-*.md`；裁决 D-V10-05。机器 `@win`（无 PG / 无 Redis）。

## 1. 先红（S23.1.1）
```
2 failed, 1 passed, 4 skipped in 1.04s
FAILED ...::test_direct_push_paths_delegate_to_the_shared_persist_fn[test_push]
FAILED ...::test_direct_push_paths_delegate_to_the_shared_persist_fn[run_push_task_now]
E  AssertionError: run_push_task_now 没有调用 persist_web_notification ⇒ 手动/测试推送永不进历史
```
红落在**结构守卫**上（本机无 PG 也能判）；4 条连库用例 skip，其判定权在 `@ci`。
`passed` 的那条是判据自检（对 `list_channels`/`list_push_logs` 必须为 False）——
没有它，守卫恒真也能让本卡看起来"已交付"。

## 2. 改后绿
```
3 passed, 4 skipped in 1.61s                                   # 本卡新文件
48 passed, 13 skipped / 0 failed in 39.07s                     # + w1_push_domain + notification_frame_id
                                                               #   + bots_logs_filter + bots_read_authz + idor_matrix
```
卡面验收 `grep -rn "persist_web_notification(" apps/api/app --include=*.py | grep -v "def " | wc -l` = **3**
（调度器 1 + 本卡新增 2）。

## 3. 两处返工过程里的自我纠正

1. **我自己的注释触发了我自己的守卫**：结构守卫判"`Notification(` 不许出现在直投函数里"
   （防第二个落库真源），而我插入的注释原文含 `复制一份 \`Notification(...)\`` ⇒ 改后仍红。
   改的是**措辞**，不是放宽判据——这条判据正是本卡要留下来的东西。
2. **`test_notification_frame_id.py::test_frame_omits_id_key_when_absent` 的 docstring 被本卡推翻**：
   它写"直投路径不预铸 ⇒ 载荷里没有 id 键"，而本卡之后 web 渠道直投**会**预铸。
   该用例本身仍绿，因为它手工构造 `PushMessage`、**根本没调** `test_push`/`run_push_task_now`——
   它实际测的是 provider 的"无 id 分支"，不是直投路径。这个区别必须写下来，否则下一会话会
   把这句注释当成"直投不落库"的现读证据。已在 `tests/test_direct_push_persists_notification.py`
   里加一条正向断言（直投载荷必须带预铸 id + 落库行 id == 载荷 id），并登记 **P-24** 让该文件的
   owner 改注释/改名。本卡允许修改面不含那个文件。

## 4. 为什么 CI 侧用桩 provider
`providers/push/web.py:30-31`：web provider 第一件事是问 Redis，拿不到就 `delivered=False`。
`backend` job 没有 Redis 服务 ⇒ 走真 provider 的连库用例在 CI 上会因环境而非因代码失败。
桩只回答"投递成没成"，把被测面（成功后落库）与依赖面解耦，并各留一条反向用例
（失败不落库、非 web 渠道不落库）防止"无条件落库"混过绿。

## 5. 状态
| 项 | 状态 |
|---|---|
| S23.1.1 先红 | **已确认**（本机结构面） |
| S23.1.2 两处复用同一落库函数 | **已确认**（本机 + 验收计数 = 3） |
| S23.1.3 回归 | **已确认**（本机 48 passed / 0 failed）；真库全量 **待 @ci** |
| 落库行为（4 条连库用例） | **待 @ci**（本机 skip ≠ 通过） |
