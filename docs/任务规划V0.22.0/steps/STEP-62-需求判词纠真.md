# STEP-62 需求判词纠真 + e2e-real 阻塞化

> 基线 59/60/61 交付后｜状态：✅ 已交付（2026-10-29。判据② 落「保持」：`e2e-real` 末三次**真执行**为 `1eaf2d5` ✓ / `ca9ba70` ✗（run `40806609514`）/ `d6d67fc` ✓（run `40808385199`），「连续三次绿」不成立 ⇒ `continue-on-error` 原样保留、`ci.yml` 零改动）｜裁决 D-V22-01/04、D-V21-05
> 交付读数与判据逐条：`docs/06_validation/evidence/EVD-V22-62/s62_readings.md`（12 条判词改动的旧值与依据、判据③ 文档门 rc 0 原文、字节级改动清单；判据② 的两支结论见该文件 §2.2）

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行助手（sonnet）｜切片 S-DOC |
| 2 来源 | 01 §3 U1～U5、01 §5 X-1～X-3 |
| 3 目标 | 五条判词与证据一致；`e2e-real` 满足条件即阻塞化 |
| 4 输出 | `product-requirements.md` 第 71/74/85/93/94/115/116 行；对应 5 个子文件头部 `实现度`；`ci.yml` 中 `e2e-real` 的 `continue-on-error` |
| 5 验收 | ① 每条新判词带证据路径（EVD-V22-59/60/61、EVD-V21-49/50、D-V21-05）② `e2e-real` 最近 3 次 run 全绿则删 `continue-on-error`，否则保持并在卡面写明 run 号 ③ 文档一致性门 rc 0 |
| 6 允许修改 | `docs/02_requirements/**`、`.github/workflows/ci.yml`（仅该一行）、本卡、卡表、07、`EVD-V22-62/` |
| 7 禁止修改 | 一切代码与测试 |
| 8 规模/档位 | 小｜sonnet |
| 9 熔断 | 同判据 2 次 FAIL ⇒ 停 |
| 10 验证命令 | `python scripts/check_docs_consistency.py` |
| 11 证据 | `docs/06_validation/evidence/EVD-V22-62/` |
| 12 依赖 | 59、60、61｜Blocks：63 |
| 13 阻塞条件 | 59/60 未达标 ⇒ 005/008 判词保持"部分"，只改 NF-002/C-001/C-002 |
| 14 升级条件 | 无 |
| 15 档位理由 | 纯文档 |
| 16 规模 | 小，<2 小时 |
