# STEP-63 发布 v1.1.5

> 基线 STEP-62 交付后｜状态：✅ 已交付（2026-10-29。本机全量一次 `2503 passed / 6 skipped / 4 deselected`、`Total coverage: 88.90%`；CHANGELOG `## [v1.1.5]` 按 `git log v1.1.4..HEAD` 的 63 个提交对账；AGENTS 版本块换 v1.1.5）｜裁决 D-V22-01（本版唯一一次全量回归）
> 逐门读数与两条残留（P-168 `continue-on-error` 摘除、P-169 本机码页）：`docs/06_validation/evidence/EVD-V22-63/s63_readings.md`

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行助手（sonnet）｜发版 |
| 2 来源 | 本版 59～62 |
| 3 目标 | v1.1.5 注释 tag + Release，GET 200 |
| 4 输出 | 本机全量一次（04 附录 B）；CHANGELOG `## [v1.1.5]`（按 `git log v1.1.4..HEAD` 对账）；AGENTS 版本块；tag/Release/对账 |
| 5 验收 | ① 本机全量 0 failed，skip 数等于基线 ② 发版提交三绿 attempt 1 ③ `git push origin v1.1.5` 逐字点名，既有 tag 不变 ④ GET `/releases/tags/v1.1.5` 200 |
| 6 允许修改 | `CHANGELOG.md`、`AGENTS.md` 版本块、本卡、卡表、07、`EVD-V22-63/` |
| 7 禁止修改 | 代码、测试、其他文档 |
| 8 规模/档位 | 小｜sonnet |
| 9 熔断 | 全量红 ⇒ 不发版，登 P 号交回 |
| 10 验证命令 | 04 附录 B |
| 11 证据 | `docs/06_validation/evidence/EVD-V22-63/` |
| 12 依赖 | 62 |
| 13 阻塞条件 | 任一绿灯缺失 |
| 14 升级条件 | 全量红且归属不明 ⇒ 交回规划方 |
| 15 档位理由 | 流程化 |
| 16 规模 | 小（全量链 ≈21 分钟） |
