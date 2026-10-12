---
id: TASK-016
type: task
title: SSE 通知帧携带落库 id（后端）
status: ready
slice: S4
owner: Agent-API
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-016：SSE 通知帧携带落库 id（后端）

**归属**
- 所属切片：S4（WP-4 通知去重）
- 执行 Agent：Agent-API
- 来源需求：REQ-F-001（站内通知）；backlog NOTIF-001 遗留待办
- 来源方案：DESIGN-001 §⑤ Events

**目标**
web 渠道每条实时帧带 id，且与 notifications 表行 id 相同。

**输入**
- apps/api/app/services/push_scheduler.py:222、267（persist_web_notification 在投递后）
- apps/api/app/providers/push/web.py（publish payload）
- apps/api/app/models/bothot_entities.py:265（Notification）

**输出**（新增/修改的文件）
- `apps/api/app/services/push_scheduler.py`
- `apps/api/app/providers/push/web.py`
- apps/api/app/providers/push/base.py（若 PushMessage 定义于此）
- apps/api/tests/test_notification_frame_id.py（新增）

**Execution Steps**
1. [x] PushMessage 增可选 notification_id 字段 ⇒ 实做 `notification_id: str = ""`（**非 None**，
   与本数据类既有全 `""` 默认的风格一致；`base.py:35`，置末位避免位置参数破坏，全部调用点用关键字）
2. [x] `_execute_task` 在 web 渠道投递前 `gen_uuid()` 赋值 ⇒ `push_scheduler.py:179`
3. [x] web.py 发布 JSON 增 id 字段 ⇒ `web.py:43-45`，**仅在非空时写键**（直投路径不落库，
   无 id 可读；写 `id: null` 会让前端"字段存在但无值"与"未预铸"两种语义糊在一起）
4. [x] persist_web_notification 使用同一 id 落库 ⇒ `:289` `id=msg.notification_id or gen_uuid()`
5. [x] 三层测试落地（载荷 / **管道** / 落库），本机无 `.venv` ⇒ 仅 `py_compile` 通过，**pytest 交 CI**
   ⚠ 外部复核指出我第一版 5 例里 3 例**无鉴别力**（删掉步骤 2 的注入仍然全绿）——
   已补管道层两例（`_execute_task` 真跑 + fake session/fake provider），并静态反证：
   删 `push_scheduler.py:184` 的 `notification_id=notification_id` ⇒ `assert frame_id` 必红。

**验收标准**
> 判据更新（2026-10-12 07:19Z）：CI run `38217078901`（sha `30d98235`）backend job 三步
> `Lint (ruff)` → `Type check (mypy)` → `Tests (pytest) + coverage + skip gate` **全部 success**。
> 此前该树判红的原因是我引入的 **F401**（`tests/test_notification_frame_id.py` 导入未用的 `AsyncMock`），
> 见 EVD-016 的"CI 实测"节。下面三条由"本机不可证"升为"**CI 已判、本机仍不可证**"；
> 未闭合的是 pytest 逐条计数（日志层需鉴权）与 `compose-smoke` 结论。
- [x] 新连库测试通过（`test_frame_id_equals_row_id` + 管道层 2 例）——**CI 判绿**（backend job pytest 步 success；本机无 `.venv`/PG 仍不可证）
- [x] `test_notification_history.py` 等既有用例零回归——**CI 判绿**（同一步全量跑，无回归即通过）
- [x] 其他 5 渠道 provider 测试零回归——**CI 判绿**；静态理由保留：`notification_id` 只在
  `web.py` 被读，各 provider 自建载荷 dict，无 `asdict(msg)` 外泄路径

**本卡交付后新暴露的两项（不属本卡范围，须单独裁决）**
1. **孤儿帧窗口**：发布发生在 `:194`、提交在 `:247`，`persist` 用 savepoint（`:286`）。
   若 `:247` 提交失败 ⇒ 帧已带 id X 外发、行被回滚；下一轮自铸 id Y ⇒ 同一逻辑通知出现
   "帧 X 无行 + 帧 Y 有行"。**id 永不与"已提交的行"不一致**，只与"没有行"不一致。
2. **at-most-once 重试的重复帧**：每次重试自铸新 id；一旦前端改成"按 id 去重"（TASK-017），
   现有 5s 内容窗口若被**替换**而非**叠加**，此窗口的重复帧会从"合并"变"两条都显示"（退化）。
3. **既有缺陷（非本卡引入，实测）**：`_execute_task` 构造 `PushMessage` 时**从不设 `external_user_id`**
   （`:181-191`；对照 `bots.py:332` 传 `ch.user_id`）⇒ 所有**调度产生**的 web 通知都走
   `bothot:notifications:broadcast` 且落库 `is_broadcast=True, sub=""`（`:290-291`）
   ⇒ **任何登录用户都看得到别人的定时通知**。要么本意即广播（则写进 REQ-F-001），
   要么定向任务的收件人锚必须在调度侧建立。**这是数据可见性问题，优先级高于本卡收口。**

**验证命令**
```bash
cd apps/api && pytest tests/test_notification_frame_id.py tests/test_notification_history.py tests/test_push_providers.py -q
```

**证据路径**
`docs/06_validation/evidence/EVD-016/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `apps/api/app/services/push_scheduler.py`
- `apps/api/app/providers/push/**`
- `apps/api/tests/test_notification_frame_id.py`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- apps/web/**

**依赖与阻塞**
- Depends on：无
- Blocks：无
- 阻塞条件：需要改 Notification 表结构 → 停（会占迁移版本号）

**建议执行档位**
sonnect　理由：小范围后端改动，契约已冻结

**升级条件**
跨进程顺序问题导致测试不稳 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
中
