> 卡片：[TASK-005](../../05_execution/tasks/TASK-005.md) ｜ 采集时间：2026-10-12 ｜ 锚：`HEAD=60e5723`（**本轮改动尚未提交**）
> 状态图例： locally-proven=本机已实测 ｜ ⚪ ci-only=本机物理上不可证（无 docker / 无 .venv / 无二进制 / 禁止起服务）

## 🟡 locally-proven

| 命令 | 实测 |
|---|---|
| `grep -n '^\.project/' .dockerignore` | `20:.project/` ⇒ 命中 |
| `git diff --numstat .dockerignore` | `5 0 .dockerignore`（新增 `.project/` + `.docs/` 等 5 行） |

## ⚪ ci-only

- `docker build` 前后**镜像构建上下文体积对比**（本机无 docker）；
- 需要真实构建产物大小作为验收证据，不能以"规则写了"替代"上下文小了"。
