# EVD-V14-24 · STEP-24 推送任务创建恒 500 与创建者归属服务端化

执行者：规划方（Hark），2026-10-19，基于 main@8cd0e68。环境 @linux：Debian aarch64 / Py3.12 / PG16@5547 `bothot_test`（迁移单头 `ab1006c1a`）/ Redis 未起（限流 fail-open 日志，与判读无关）。

## 先红（`s24_red.txt`）
- `test_admin_creates_task_and_owner_is_local_user_id`：**500/50001 `IntegrityError`**（后端兜字面量 `"system"` 违反 `push_tasks.created_by → users.id` 外键）。
- `test_forged_created_by_is_ignored`：请求体 `created_by=<另一个真实 users.id>` **落库成功且归属被改写**——这比卡面预计的更严重：原代码不只是 500，还允许任何能建任务的人伪造归属（写侧越权，D-V11-02 的反方案在旧代码里已经是事实）。
- 结果：2 failed。

## 修复（交付提交见 `@ci` 小节）
- `apps/api/app/api/v1/bots.py`：`PushTaskCreateRequest` 删除 `created_by`；`create_push_task` 依赖改为 `actor: User = Depends(require_roles("operator"))`（角色实参按 STEP-25 同提交收口）；`created_by=actor.id`；`git grep -n '"system"' apps/api/app/api/v1/bots.py` = 0。
- 前端：`PushTasksTab.tsx` 删 `userSub` 属性与 `created_by` 透传；`app/bots/page.tsx` 调用点同步（卡面允许清单外 1 行，因为属性删除必须改调用方，登记为卡面增量）；`lib/api/bots.ts` 删请求侧可选 `created_by`。
- S24.2.2.b：UI 当前**没有**"创建者"列（`grep -n 创建者 apps/web/components/PushTasksTab.tsx` = 0），本项无需改动。

## 改后
- 目标用例 2 passed（`s24_green.txt`）。
- 复跑原探针（`probe_after.txt`）：② 两行 **200 0**（改前 500 50001）。
- `git grep -n created_by apps/web`：只剩响应类型 `lib/api/bots.ts:61` 与测试夹具数据 `tests/w4-bots-tasks.spec.ts:94`（响应形状）。
- 前端：typecheck rc=0、lint 无告警、vitest 全量 383 passed（STEP-25 前端用例加入后该文件 10 passed）。
- 后端全量与 `@ci` 读数见 `docs/06_validation/evidence/EVD-V14-25/s25_readings.md`（两卡同一交付提交）。

## S24.3.1 存量审计
生产只读 DSN 未提供（D-V12-14：先在测试库演练，生产以后跑）⇒ **未测**，不写 0。审计 SQL 已并入 STEP-07 的脚本清单。
