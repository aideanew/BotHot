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

## CI 实测（2026-10-12 07:19Z 起，本卡首次获得机器判定）

采集方式：未认证 REST（public 仓库可读 run/job 层；日志层 403 需 token，故**拿不到 pytest 计数**）。
重算：`curl -s -x http://127.0.0.1:10808 https://api.github.com/repos/aideanew/BotHot/actions/runs?per_page=6`

| run | head_sha | 结论 | 意义 |
|---|---|---|---|
| `38216549514`（CI） | `ab8a8a73` | **failure** | 反证：修复前的树确实判红 |
| `38217078901`（CI） | `30d98235` | backend **success** | 步骤级：`Lint (ruff)` → `Type check (mypy)` → `Tests (pytest) + coverage + skip gate` 三步全 success |
| 同 run 其余 job | 同上 | `compose` success、`frontend`（含 `Unit tests (vitest)`）success、`workflow-lint` success；`compose-smoke` 采集时仍 in_progress | |
| `38217079332`（Security） | `30d98235` | success，27 步无 skip/cancel | gitleaks 真二进制在本配置上跑通（EVD-004 的 ⚪ 项就此闭合） |

**由红转绿的因果链**（不是"顺手推了一次"）：首红 run 的唯一失败点是 backend step 7 `Lint (ruff)`，
根因 `apps/api/tests/test_notification_frame_id.py:19` 导入了未使用的 `AsyncMock` ⇒ **F401**；
删该导入后同一条 job 走完 ruff/mypy/pytest ⇒ **本卡新增的三层 6 例首次被真实执行并通过**。

**观测边界（重要）**：上表全部结论来自**未认证 REST 的一次成功解析窗口**（2026-10-12 07:19–07:25Z）。
其后 GitHub 返回 403 `API rate limit exceeded` ⇒ **无法确认 `compose-smoke` 的最终结论，
也无法确认随后两个纯文档 sha 的 run 结果**，本卡不把这些写成绿。
重算前提：先看 `curl -o /dev/null -w "%{http_code}"` 为 200 且响应含 `workflow_runs` 键，再读结论
（否则解析失败会被误读成"没有正在跑的 run"——见 `findings.md §D-14`）。

**仍未闭合**：① pytest 的 passed/skipped 具体数字（日志层需鉴权）；② `compose-smoke` 及后续两个纯文档
sha 的 run 最终结论（限流后不可知，见上"观测边界"）；
③ 连库用例的**逐条**执行状态——但方向性证据已有：`.github/workflows/ci.yml:33-41` 给 backend job
挂了真 `postgres:16` service（runner 内映射宿主 5433，与本机的隔离 PG 实例无关，不触犯"绝不碰 5433"），
且 CI 有专门的 "skip gate" 步骤断言 skip 构成 ⇒ 本卡的落库层 2 例**属真执行而非 skip** 的可能性高，
但"高"不等于"实测"，具体数字仍待鉴权取日志。
