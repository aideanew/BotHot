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

## 3. 返工轮 S23.4：收件人锚（独立复核抓出来的，不是我自己看代码看出来的）

### 3.1 触发点

`@ci` 转绿（run 39030366256 @ `10c1019`，`1533 passed / 6 skipped / 0 failed`）之后做了独立复核，
其中一句判词是：**"卡目标第二句『对收件人可见』没有任何用例覆盖，因为夹具 `user_id` 恒为 None"**。
复算夹具：`_seed_channel(...)` 写死 `user_id=None`，四条连库用例全部走它 ⇒
本卡实际只判过**广播**一支。

### 3.2 缺陷形态（现读锚，逐条对过）

| 位置 | 现读 | 后果 |
|---|---|---|
| `app/api/v1/bots.py:617` | `external_user_id=ch.user_id or ""` | `ch.user_id` 是 `users.id`（`bothot_entities.py:41-43` 外键指向 `users.id`） |
| `app/services/push_scheduler.py:290` | `sub=msg.external_user_id or ""` | 于是历史行的 `sub` 收到的是 **users.id** |
| `app/models/bothot_entities.py:274,286` | "收件人锚 = sub（SSO 身份锚点）"、`sub: String(128)` | 契约写的是 **users.sub** |
| `app/api/v1/system.py:394-396` | `or_(Notification.sub == sub, Notification.is_broadcast)` | 读侧按 SSO sub 过滤 ⇒ 那条行**谁都查不到**（死行） |
| `app/api/v1/system.py:316-319` | 订阅侧同时挂 `{sub}` 与 `{user_id}` | **实时帧能到**，所以页面看起来"推送成功了" |

最后两行是这条缺陷能活下来的原因：可见性只在一侧坏，而那一侧恰好是"离线补投"这个次要路径。

### 3.3 修法与为什么不选另一种

只改生产锚（`test_push` 解析 `User.sub`），不放宽读侧谓词。
备选 B 是把 `_notification_scope` 改成 `sub IN (me.sub, me.id)`——那等于把"两套收件人锚"
制度化：`AGENTS.md` 关键约束 2 明写 SSO 身份锚点 = `users.sub`，读侧一旦接受两种锚，
以后每条新通知路径都要决定"写哪一种"，而决定权在调用方手里。
另外只动 web 一支：`wechat_clawbot.py:30-34` 把 `external_user_id` 解释成它自己的收件人语义，
一并改会把别的渠道改坏。

**`run_push_task_now` 不在这次的改动范围**，而且是有意的：它从来不设 `external_user_id`
⇒ 恒广播 ⇒ 行 `sub=""`、`is_broadcast=True` ⇒ 读侧覆盖得到。它与调度器对同一条任务的
行为一致（调度器 `push_scheduler.py:181-191` 建的 `PushMessage` 同样不带收件人）。

### 3.4 读数

| 项 | 读数 |
|---|---|
| 改前形态存在性 | `git show 6925850:apps/api/app/api/v1/bots.py \| grep -c "external_user_id=ch.user_id"` = **1** |
| 本机（无 PG） | `4 passed / 6 skipped`（新增 1 条源码早期线可判，2 条连库用例 skip；**skip ≠ 通过**） |
| 夹具约束面预核（本会话第三次犯同族错之后立的规矩） | `User` 必填无默认 = `email`、`sub`（两者都给了）；`BotChannel` = `channel_type`、`name`；`Notification` = 空集 |
| 静态回归（调用面按 grep 符号导出，不是挑看起来相关的文件） | 清单来自 `grep -rln "test_push" apps/api/tests --include=*.py` ⇒ `test_collection_contract` / 本卡 / `test_r11_push` / `test_security_middleware` / `test_w1_push_domain` 五个文件合跑 **`273 passed / 15 skipped / 0 failed`（38.87s）**；`15` 条 skip 是本机无 PG 的连库面，**skip ≠ 通过** |
| ruff / mypy | `All checks passed!` / mypy `Success: no issues found in 112 source files` |
| 待 `@ci` | 两条新连库用例真库转绿 + 全量 `failed = 0`（本卡 Done 面，D-V4-01） |

### 3.5 我自己在这轮里差点犯的错（必须留在记录里）

- 空 sub 的第一反应该写 `recipient = bound_sub or ""`（"兜个默认值"）。在这条链上 `""` 不是"没有收件人"，
  而是 `is_broadcast=True` ⇒ 定向测试推送变成全站可见通知，**把身份缺陷换成越权缺陷**。
  现在退回原锚 `ch.user_id`，并由 `test_unresolvable_sub_never_upgrades_a_directed_push_to_broadcast` 钉住。
- 复核还判了我另外两件：①`grep 计数 = 3` 那种验收门是文本产物（行为回归不会使它红）；
  ②卡面那条 `git diff --name-only ⊆ 输出清单` 我照字面打了勾而不成立。两条都已在卡面按实改写。
- 复核指出的 stale 注释（`web.py:41-42`、`persist_web_notification` 自己 docstring 的"如直投"）
  与 `created_by` 的锚点/伪造面（P-26）都**不在本卡允许面**，只登记不顺手改。
