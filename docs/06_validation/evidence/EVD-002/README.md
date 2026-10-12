> 卡片：[TASK-002](../../05_execution/tasks/TASK-002.md) ｜ 采集时间：2026-10-12 ｜ 锚：`HEAD=60e5723`（**本轮改动尚未提交**）
> 状态图例： locally-proven=本机已实测 ｜ ⚪ ci-only=本机物理上不可证（无 docker / 无 .venv / 无二进制 / 禁止起服务）

## 🟡 locally-proven

| 命令 | 实测输出 |
|---|---|
| `git grep -nE 'bothot_rw:[^<>@[:space:]]+@' -- docker apps scripts packages .github` | **rc=1（空）** ⇒ 连接串口令外置达成 |
| `grep -n 'DATABASE_URL' docker/compose.yml` | `159: - DATABASE_URL=${DATABASE_URL:?…未设置…}`（`:?` = 缺失即拒绝启动） |
| `git diff --numstat docker/compose.yml docker/.env.example` | `20 4 docker/.env.example` / `4 2 docker/compose.yml` |

⚠ 行号会漂：复算请用上表命令，不要引用本文件的行号。

## ⚪ ci-only

1. `docker compose -f docker/compose.yml config`（未设 `DATABASE_URL` 时**必须非 0**）——本机无 docker。
2. `docker compose -f docker/compose.yml -f docker/compose.ci.yml config --quiet`（叠加后**必须 0**）。
3. CI 的 `compose` / `compose-smoke` 两个 job 绿。

## 已知未完成项

- **口令轮换**属 TASK-001（人工运维），**至今无证据** ⇒ 历史里那条凭据是否已失效仍未知；
  这直接决定"能否推送"，见大纲 R.16.1。
