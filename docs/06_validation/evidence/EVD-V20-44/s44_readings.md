# EVD-V20-44 发布 v1.1.2（执行助手）

平台 @win（Windows 10 x64，Git Bash），开工 head `0fb04ec`（STEP-37 收口批），时间 2026-10-24（Asia/Shanghai）。
本卡不改任何代码（卡面禁止）；改动面 = `EVD-V20-43/s43_review.md`、`CHANGELOG.md`、`AGENTS.md` 版本块、
本目录、执行记录追加。

## 1. S44.1 独立复查 STEP-43（提交 `17c3f13`）

结论 **PASS**。只看 diff 与运行结果；全过程读数在 `../EVD-V20-43/s43_review.md`。要点：
- diff 只动 `logging.py`（json 补 `format_exc_info`、console 钉 `plain_traceback`）与测试 +3 条，
  遮蔽处理器仍在链尾；
- 本机（rich 在场 = P-114 触发条件）现跑 `tests/test_log_redaction.py` ⇒ **18 passed**；
- 反证（卡面命令：临时还原 `logging.py` 到 v1.1.1/`75b212b` 版本）⇒ **4 failed / 14 passed**
  （JSON 无栈 + console locals + 钉子用例），与规划方 s43_readings.md §3 同形；还原后 18 passed、diff 空。

## 2. S44.2 CHANGELOG 与版本块

- 区间现读：`git log --oneline v1.1.1..HEAD`（@`0fb04ec`）= **26 个提交**；引用的短 hash 逐个
  `git log -1` 复核主语：`17c3f13`、`e01327c`、`2578c26`、`03c013d`、`33be5fd`、`6232a95`、
  `53b5197`、`83a2606`、`2db2f99`、`31a3fb4`——全部解析且主语一致。
- `CHANGELOG.md`：`[Unreleased]` 发布前本就是空 ⇒ 保留空段，新写 `## [v1.1.2] - 2026-10-24`
  （Fixed 5 条大白话 + Added 4 条 + Changed 2 条）。
- `AGENTS.md` 版本块改指 **v1.1.2**：不抄发布批自身 sha（自指），权威读数现取
  `git ls-remote --tags origin v1.1.2` / `git rev-parse v1.1.2^{commit}`；
  上一版 v1.1.1 标签对象 `3eace88` → 提交 `75b212b`；区间计数 26，发布批 +1 ⇒ 27。

## 3. S44.3 tag 与 Release

- 顺序：提交推送 ⇒ 等同 head 三绿（attempt 1）⇒ 打注释 tag `v1.1.2` ⇒ 推 tag ⇒ 建 Release 页
  （正文取 tag 注释）。
- 完成判据读数（推送 tag 后回填）：
  - `git ls-remote --tags origin v1.1.2` 指向三绿的提交：见 §5 回填；
  - v1.0.0 / v1.1.0 / v1.1.1 未动：见 §5；
  - REST `releases/tags/v1.1.2` 返回 200：见 §5。

## 5. @ci 与发布读数（推送后回填，2026-10-24 20:0x @win，Asia/Shanghai）

**发布批 `a221f89` 的 @ci**（GitHub REST 现读，轮询至全完成）：

| 工作流 | run id | 轮次 | 结论 |
|---|---|---|---|
| CI | 40038370476 | attempt 1 | success |
| CI-Windows | 40038370474 | attempt 1 | success |
| Security | 40038370536 | attempt 1 | success |

**tag 权威读数**（推送后 `git ls-remote --tags origin` 现取）：

| tag | 标签对象 | `^{}` 指向提交 |
|---|---|---|
| v1.0.0（未动） | `8ecf322` | `c19fe87` |
| v1.1.0（未动） | `db9205d` | `49c3bed` |
| v1.1.1（未动） | `3eace88` | `75b212b` |
| **v1.1.2（本卡新打）** | `4d61f5e` | **`a221f89`（三绿发布批）** |

完成判据逐条：
- ✅ `git ls-remote --tags origin v1.1.2` 的 `^{}` 指向三绿的提交 `a221f89`；v1.0.0/v1.1.0/v1.1.1 未动（上表）。
- ✅ REST `releases/tags/v1.1.2` → HTTP 200（创建 POST 201）。
- ✅ `EVD-V20-43/s43_review.md` 结论 PASS（§1）。
- Release 页（正文 = tag 注释，REST 创建）：
  https://github.com/aideanew/BotHot/releases/tag/v1.1.2
