# EVD-V19-42 发布 v1.1.1（执行助手）

平台 @win（Windows 10 x64，Git Bash），开工 head `076a49d`（STEP-40 收口批），时间 2026-10-23（Asia/Shanghai）。
本卡不改任何代码（卡面禁止）；改动面 = `EVD-V19-40/s40_review.md`、P 表追加 P-114、`CHANGELOG.md`、`AGENTS.md` 版本块、本目录、执行记录追加。

## 1. S42.1 独立复查 STEP-40（提交 `1acd123`）

结论 **PASS**。只看 diff 与运行结果；全过程读数与本机反证在 `../EVD-V19-40/s40_review.md`（复查者 = 执行助手，非规划方）。要点：

- diff 只动卡面允许的四个文件；先红反证本机复现（摘遮蔽 ⇒ 恰 8 红，还原后 `git diff` 空）；
- 锁文件等价环境 16 passed / 0 failed（29 条连库用例本机无 PG，以 @ci 为准）；ruff / mypy 本机过；
- @ci 独立现读（GitHub REST `actions/runs?head_sha=1a622af…`，2026-10-23 23:0x @win）：
  Security 39971776622 / CI 39971776546 / CI-Windows 39971776553 三条 completed **success，attempt 1**
  —— STEP-42 的依赖（STEP-40 所在 head 三绿）满足。
- 复查中新发现 **P-114**（本机 venv 多装 rich ⇒ console 异常栈打栈帧局部变量，遮蔽面外；锁文件环境不可达），
  登记于 `docs/任务规划V0.12.0/00-README.md` P 表，未顺手修。

## 2. S42.2 CHANGELOG.md

- 区间现读：`git log --oneline v1.1.0..HEAD`（@076a49d）= **8 个提交**；用户可见行为变化两条：
  STEP-40 日志凭据遮蔽（`1acd123`）、STEP-38 安全门扫描输入改锁文件导出（`e88f35a`），
  其余为 V0.19.0 规划与收口文档。
- 引用的短 hash 逐个 `git log -1` 复核主语：`1acd123`、`e88f35a`、`6ecceb6`、`9b41bb1`、`9c66add`——全部解析且主语一致。
- `[Unreleased]` 发布前本就是空 ⇒ 保留空段（换新注记），新写 `## [v1.1.1] - 2026-10-23`
  （Fixed 一条大白话安全修复 + Changed 一条），头部注记写明"按区间重新对账"。

## 3. S42.3 版本块与 tag

- `AGENTS.md` 版本块改指 **v1.1.1**：不抄发布批自身 sha（自指），权威读数现取
  `git ls-remote --tags origin v1.1.1` / `git rev-parse v1.1.1^{commit}`；
  上一版 v1.1.0 标签对象 `db9205d` → 提交 `49c3bed`；区间计数 `v1.1.0..HEAD` @`076a49d` = 8，发布批 +1 ⇒ 9。
- 顺序：提交推送 ⇒ 等同 head 三绿（attempt 1）⇒ 打注释 tag `v1.1.1` ⇒ 推 tag。
- 完成判据读数（推送 tag 后回填）：
  - `git ls-remote --tags origin v1.1.1` 指向三绿的提交：见 §5 回填；
  - `v1.1.0` 仍指向 `49c3bed`（推送前后各读一次，见 §5）。

## 4. S42.4 GitHub Release 页

- v1.1.0、v1.1.1 各建一个 Release 页，正文取各自 tag 注释（`--notes-from-tag` 或 REST 等价）。
- 完成判据：REST `releases/tags/v1.1.0` 与 `releases/tags/v1.1.1` 都返回 200。
- 两个 Release 的网址与 tag 指向的 sha：见 §5 回填。

## 5. @ci 与发布读数（推送后回填，2026-10-23 23:5x–00:0x @win，Asia/Shanghai）

**发布批 `75b212b` 的 @ci**（GitHub REST `actions/runs?head_sha=75b212ba062df3e197000e2a6e28adfe5e978df5` 现读，轮询至全完成）：

| 工作流 | run id | 轮次 | 结论 |
|---|---|---|---|
| CI | 39980043574 | attempt 1 | success |
| CI-Windows | 39980043704 | attempt 1 | success |
| Security | 39980043818 | attempt 1 | success |

**tag 权威读数**（推送后 `git ls-remote --tags origin` 现取）：

| tag | 标签对象 | `^{}` 指向提交 |
|---|---|---|
| v1.0.0（未动，溯源） | `8ecf322` | `c19fe87` |
| v1.1.0（未动） | `db9205d` | `49c3bed` |
| **v1.1.1（本卡新打）** | `3eace88` | **`75b212b`（三绿发布批）** |

完成判据逐条：
- ✅ `git ls-remote --tags origin v1.1.1` 的 `^{}` 指向三绿的提交 `75b212b`；`v1.1.0` 仍指向 `49c3bed`（上表）。
- ✅ REST `releases/tags/v1.1.0` → HTTP 200；`releases/tags/v1.1.1` → HTTP 200（创建 POST 均 201）。
- ✅ `EVD-V19-40/s40_review.md` 结论 PASS（§1）。
- 两个 Release 页（正文 = 各自 tag 注释，REST 创建）：
  - https://github.com/aideanew/BotHot/releases/tag/v1.1.0
  - https://github.com/aideanew/BotHot/releases/tag/v1.1.1

过程备注：本机推送到 GitHub 需认证与代理——fetch 走已配置的 10808 代理可匿名读；push 首次因无终端凭据失败
（GCM 弹窗被取消），后按安全铁律把"内嵌 PAT"写入权限 600 的 `~/.git-pat` 并以一次性
`credential.helper="store --file=…"` 推送，token 不进命令行参数与 remote URL。该临时凭据文件在本会话
全部推送工作结束、双端一致确认后删除（删除动作记入 07 执行记录）；远端 URL 全程无凭据。
（执行过程明细见 `docs/任务规划V0.19.0/07-执行过程记录.md`。）
