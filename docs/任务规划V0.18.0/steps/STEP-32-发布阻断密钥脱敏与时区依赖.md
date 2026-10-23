# STEP-32 发布阻断密钥脱敏与时区依赖

> 基线 main@f86811e｜状态：⚪ 未开始｜版本 V0.18.0

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行 Agent-Guard |
| 2 验收者 | 规划方，只出 PASS/FAIL/UNKNOWN |
| 3 难度 / 里程碑 | 低 / M4 发布阻断 |
| 4 来源 | P-107、P-106；D-V18-03、D-V18-04 |
| 5 目标 | 公开 CI 日志里读不到任何生成的密钥值；后端运行镜像与 Windows 开发机都显式依赖 tzdata，不再靠基础镜像碰巧带 |
| 6 输入 | `.github/workflows/ci.yml:472-473`（f86811e 现读）；`apps/api/pyproject.toml`；`apps/api/uv.lock:1039,1765` |
| 7 输出路径 | `.github/workflows/ci.yml`、`apps/api/pyproject.toml`、`apps/api/uv.lock`、`scripts/guards.py`（仅新增一条守卫函数）、对应测试、`docs/06_validation/evidence/EVD-V18-32/`（D-V18-13） |
| 10 命令 | `python scripts/entry.py guard-structure`；`cd apps/api && uv lock --check`；`pytest tests/test_guards*.py -q`；推送后读 CI `compose-smoke` 步日志原文 |
| 12 允许修改 | 上面第 7 格所列；`docs/04_engineering/conventions.md` §4.5 第 3 条补一句 |
| 13 禁止修改 | 其他工作流的业务步；`apps/api/Dockerfile`；任何 `app/**` |
| 14 依赖 | 无（队列第一项） |
| 15 档位 | sonnet |
| 16 规模 | ≈0.3 人日 |

## 三级任务
1. [ ] **S32.1** `ci.yml` 两行改为：生成值先赋给本步局部变量 → `echo "::add-mask::$变量"` → 再写 `$GITHUB_ENV`。不改密钥长度与生成方式
2. [ ] **S32.2** `scripts/guards.py` 新增守卫：解析 `.github/workflows/*.yml`，凡某步 `run` 里向 `$GITHUB_ENV` 写入命令替换 `$(...)` 的值，同一步内必须先出现对同一变量的 `::add-mask::`；接入 `make guard`/CI Governance 步。反证：把 S32.1 的 mask 行删掉，守卫必须红
3. [ ] **S32.3** `pyproject.toml` 主依赖加 `tzdata`（不带平台标记），`uv lock` 重锁；单测：`zoneinfo.ZoneInfo("Asia/Shanghai")` 在设置 `PYTHONTZPATH` 为空目录时仍可构造（证明来自 tzdata 包而非系统库）
4. [ ] **S32.4** 推送后读 `compose-smoke` 步的日志原文：两把密钥所在位置显示为 `***`；证据只记"显示为 *** 的行号"，不抄任何值

## 完成判据（全部机器可判）
- CI / CI-Windows / Security 在交付提交同一 head 三绿（attempt 1）
- 守卫反证红→还原绿两次读数入证据
- `grep -c 'add-mask' .github/workflows/ci.yml` ≥ 2
- `uv lock --check` rc=0，`uv.lock` 里 tzdata 条目不再只有 win32 标记
- gitleaks 全历史 0 新增

## 熔断
连续 2 轮验收 FAIL ⇒ 停卡交回规划方（rounds-check 机器执行，口径见 D-V18-16）。前提与现读不符 ⇒ 先登记 P 号再停，不自改卡面。

## 卡面增量（2026-10-23 14:15，规划方，回应执行方开工读数）
1. **接线不算越界，允许面补三处（各限一处）**：`scripts/entry.py` 用 `add(...)` 注册新守卫任务并把它加进 `guard` 复合目标的元组；`Makefile` 增同名薄转调目标（否则 `check_entry_parity` 必红）；`.github/workflows/ci.yml` 的 Governance 步 `run` 内加一行调用新守卫。三处都只许"加"，不许改已有行的语义。
2. **uv 怎么办**：允许把 uv 装在仓库外（版本号写进证据）。重锁必须用 uv 生成，**禁止手改 `uv.lock`**；重锁时索引保持与现锁一致（现锁 1483 处地址全是清华镜像、0 处 pypi.org），否则整份锁文件地址会被换掉。判据补一条：`git diff --stat apps/api/uv.lock` 只涉及 tzdata 条目与引用它的那几行，其余包版本零变化（把 diff 摘要入证据）。装不上 uv ⇒ 只改 `pyproject.toml`，`uv.lock` 那半标"未测"交回，不许手改凑数。
3. **如实写清 S32.3 的效力来源**：现读 CI（`ci.yml:64`、`ci-windows.yml:174`）、Security 与 `apps/api/Dockerfile:32` 全部是 `pip install` 读 `pyproject.toml`，**没有任何一处消费 `uv.lock`**。所以本卡真正生效的是 `pyproject.toml` 加依赖；`uv.lock` 只是保持一致。"锁文件不被任何运行面消费"属 P-55，由 STEP-38（D-V18-12）处理，本卡不越界。
4. 队列理解正确：32 → 33 → 同一提交三绿 → 39。
