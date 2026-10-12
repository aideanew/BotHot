> 卡片：[TASK-004](../../05_execution/tasks/TASK-004.md) ｜ 采集时间：2026-10-12 ｜ 锚：`HEAD=60e5723`（**本轮改动尚未提交**）
> 状态图例： locally-proven=本机已实测 ｜ ⚪ ci-only=本机物理上不可证（无 docker / 无 .venv / 无二进制 / 禁止起服务）

## 🟡 locally-proven（离线复现器，**近似非等价**：Go RE2 ≠ Python re）

| 档 | 命令 | 实测 |
|---|---|---|
| tracked | `python docs/任务规划V0.1.0/_workspace/gitleaks_replay.py tree` | 命中 **35** → **告警 0** |
| tracked+untracked（权威档，含守卫配置自己） | `… worktree` | 候选 5001 路径 → 命中 **46** → **告警 0** |
| history（93 commit 增量行） | `… history` | 命中 **44** → **告警 0** |
| 配置可解析 | `python -c "import tomllib,pathlib;tomllib.loads(pathlib.Path('.gitleaks.toml').read_text(encoding='utf-8'))"` | TOML ok |
| 口令值不再出现在工作树 | `grep -rnF "$PW" . --exclude-dir=.git`（`$PW` 库外赋值） | **0 命中** |

### 能力证明（反事实，副本在仓库外）

```bash
mkdir -p /tmp/glcf && sed '/^commits = \[/,+2d' .gitleaks.toml > /tmp/glcf/nolock.toml
GITLEAKS_TOML=/tmp/glcf/nolock.toml python docs/任务规划V0.1.0/_workspace/gitleaks_replay.py history
# 实测：命中 44 → 告警 1
#   FLAG 01f6892 docker/compose.yml <- postgresql+psycopg://bothot_rw:<已脱敏>@
```
⇒ **规则确实抓得到历史里那条内嵌口令**；全历史 0 告警**只**是因为 `commits` 登记，不是因为瞎。
告警行自带脱敏（`_mask()`）——否则一次复跑就会把口令抄进新工件。

### 共存证明（入库配置抑制）

`… replay.py history` ⇒ 同一行被 `commits` 放行，**告警 0**。

## ⚪ ci-only

- `gitleaks` **8.21.2 真二进制**四条命令 + 双 fixture（bad/ok），见 `.gitleaks.toml` footer；
- `[[rules.allowlists]]` 复数键是否被识别（v8 走 koanf，**未知键静默忽略** ⇒ 不识别时无报错，必须靠 fixture 区分）；
- Security 工作流绿。

## 判据口径

**只有"告警 0"是判据**；"候选路径数""命中总数"都会随工作区残留物漂移（实测 4998→5001），仅用于定位。
把本配置复制进扫描域会 +6（本文件自命中数）；`_workspace/*.local.toml` 已被 `.gitignore` 排除 ⇒ 复现前先确认无残留副本。
