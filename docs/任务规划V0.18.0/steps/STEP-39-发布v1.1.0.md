# STEP-39 发布v1.1.0

> 基线 main@f86811e｜状态：⚪ 未开始｜版本 V0.18.0

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行 Agent-Doc |
| 2 验收者 | 规划方 |
| 3 难度 / 里程碑 | 低 / M4 |
| 4 来源 | D-V18-01、D-V18-02；STEP-12 的 `docs/06_validation/evidence/EVD-V17-12/s12_readings.md` §6 |
| 5 目标 | 把 v1.0.0 之后的工作发布为 v1.1.0：CHANGELOG 定稿、打 tag、推 tag、tag 上的 CI 三绿 |
| 6 输入 | `CHANGELOG.md` 的 `[v1.1.0] — 未发布` 候选段与 `[Unreleased]` 段；`AGENTS.md`「当前项目状态」 |
| 7 输出路径 | `CHANGELOG.md`、`AGENTS.md`（版本行）、git tag `v1.1.0`、`docs/06_validation/evidence/EVD-V18-39/`（D-V18-13） |
| 10 命令 | `git tag -a v1.1.0 -m ...`；`git push origin v1.1.0`；读 tag 触发或同 head 的 CI / CI-Windows / Security |
| 12 允许修改 | 第 7 格所列 |
| 13 禁止修改 | 任何代码；已有 tag（不得移动或删除 v1.0.0） |
| 14 依赖 | 32、33 合入，且其最后一个提交同一 head 三绿（attempt 1） |
| 15 档位 | haiku |
| 16 规模 | ≈0.3 人日 |

## 三级任务
1. [ ] **S39.1** 合并 `[Unreleased]` 现有条目进候选段（去重），补上 32、33 两条；候选段标题改为 `## [v1.1.0] — 2026-10-xx`（填实际发布日）；新建空的 `[Unreleased]`；每个 hash 仍需 `git log -1` 复核主语
2. [ ] **S39.2** `AGENTS.md` 版本行改为 v1.1.0，"领先 tag N 个提交"改为 0 并带锚 sha
3. [ ] **S39.3** 提交并推送 → 等该 head 三绿 → 打注释 tag `v1.1.0` 指向该提交 → 推 tag；证据记 tag 指向的 sha 与三条 run id
4. [ ] **S39.4** 发布后冒烟：读该 head 的 `compose-smoke` 步 PASS 行；若任一红 ⇒ 不删 tag，登记 P 号并交回规划方

## 完成判据（全部机器可判）
- `git ls-remote --tags origin v1.1.0` 有且指向三绿的提交
- CHANGELOG 里 `[Unreleased]` 为空段、v1.1.0 段有日期
- 不得出现强推或移动 tag

## 熔断
连续 2 轮验收 FAIL ⇒ 停卡交回规划方（rounds-check 机器执行，口径见 D-V18-16）。前提与现读不符 ⇒ 先登记 P 号再停，不自改卡面。
