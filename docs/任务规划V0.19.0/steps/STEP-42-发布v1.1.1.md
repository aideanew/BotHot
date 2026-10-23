# STEP-42 发布 v1.1.1

> 基线 main@9c66add｜状态：⚪ 队列第一｜版本 V0.19.0

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行 Agent-Doc |
| 2 验收者 | 规划方 |
| 3 难度 / 里程碑 | 低 / M4 |
| 4 来源 | D-V19-04；STEP-40 |
| 5 目标 | 先对 STEP-40 做独立复查；通过后把 v1.1.0 之后的提交发布为 v1.1.1，并为 v1.1.0、v1.1.1 各建一个 GitHub Release 页 |
| 6 输入 | STEP-40 的提交与 `EVD-V19-40/`；`CHANGELOG.md`；`AGENTS.md` 版本块；tag `v1.1.0` 的注释正文 |
| 7 输出路径 | `docs/06_validation/evidence/EVD-V19-40/s40_review.md`、`CHANGELOG.md`、`AGENTS.md`（版本块）、git tag `v1.1.1`、两个 GitHub Release、`docs/06_validation/evidence/EVD-V19-42/` |
| 10 命令 | 复查：`git show <STEP-40 提交>`、`python -m pytest -q tests/test_log_redaction.py tests/test_audit_log.py`、临时去掉 `redact_rendered` 跑同一命令看 8 条红后还原；发布：`git tag -a v1.1.1 -m …`、`git push origin v1.1.1`；Release：`gh release create v1.1.0 --notes-from-tag`、`gh release create v1.1.1 --notes-from-tag`（没有 gh 就用 GitHub 网页，不在命令行写 token） |
| 12 允许修改 | 第 7 格所列 |
| 13 禁止修改 | 任何代码；已有 tag（不得移动或删除 v1.0.0、v1.1.0） |
| 14 依赖 | STEP-40 所在 head 三绿（attempt 1） |
| 15 档位 | sonnet（复查）/ haiku（发布） |
| 16 规模 | ≈0.3 人日 |

## 三级任务
1. [ ] **S42.1** 独立复查 STEP-40：只看 diff 与运行结果，输出 PASS / FAIL / UNKNOWN 与不超过 10 行理由。FAIL ⇒ 停卡交回规划方，不发版
2. [ ] **S42.2** `CHANGELOG.md`：`[Unreleased]` 并入 `## [v1.1.1] — <发布日>`，写一条大白话的"安全修复：推送渠道凭据与采集令牌不再写进日志"；保留空的 `[Unreleased]`；hash 逐个 `git log -1` 复核
3. [ ] **S42.3** `AGENTS.md` 版本块改指 v1.1.1；提交推送 → 等同 head 三绿 → 打注释 tag `v1.1.1` → 推 tag
4. [ ] **S42.4** 建两个 Release 页（正文取各自 tag 注释），证据记两个 Release 的网址与 tag 指向的 sha

## 完成判据
- `git ls-remote --tags origin v1.1.1` 指向三绿的提交；`v1.1.0` 仍指向 `49c3bed`
- REST `releases/tags/v1.1.0` 与 `releases/tags/v1.1.1` 都返回 200
- `EVD-V19-40/s40_review.md` 结论为 PASS

## 熔断
连续 2 轮验收 FAIL ⇒ 停卡交回。tag 推上去后任一工作流红：不删 tag，登记 P 号交回。
