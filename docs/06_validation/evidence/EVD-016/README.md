> 卡片：[TASK-016](../../05_execution/tasks/TASK-016.md) ｜ 采集时间：2026-10-12 ｜ 锚：`HEAD=60e5723`（**本轮改动尚未提交**）
> 状态图例： locally-proven=本机已实测 ｜ ⚪ ci-only=本机物理上不可证（无 docker / 无 .venv / 无二进制 / 禁止起服务）

## 🟡 locally-proven

| 命令 | 实测 |
|---|---|
| `git diff --numstat apps/api` | `base.py 3/0`、`web.py 5/0`、`push_scheduler.py 10/0` |
| `git status --porcelain apps/api/tests/test_notification_frame_id.py` | `??`（新增文件） |
| `python -m py_compile` × 4 文件 | 通过（语法级） |
| 静态反证 | 删 `push_scheduler.py:184` 的 `notification_id=notification_id` ⇒ 管道层 `assert frame_id` 必红（第一版没有这条，被复核指出"3 例无鉴别力"后重做） |

## ⚪ ci-only

```bash
cd apps/api && pytest tests/test_notification_frame_id.py tests/test_notification_history.py tests/test_push_providers.py -q
```
本机无 `apps/api/.venv`（用户明令不装依赖），且连库用例需 PG（隔离实例 **5547**，绝不碰 5433）。

## 交付后新暴露（已进大纲，不属本卡）

1. **孤儿帧窗口**：`:194` 发布 → `:247` 提交，savepoint 在 `:286` ⇒ 提交失败则"有帧无行"，下一轮换 id（G-22）。
2. **重复帧去重**：重试每轮自铸新 id；TASK-017 若把 5s 内容窗口**替换**成 id 去重（而非叠加），
   上述窗口的重复帧会从"合并"变"两条都显示" ⇒ 真实退化。
3. **既有数据可见性缺陷**：调度侧从不设 `external_user_id` ⇒ 定时 web 通知**全部落为广播**、
   任何登录用户可见（G-21，优先级高于本卡收口）。
