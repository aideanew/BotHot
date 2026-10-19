# 任务规划 V0.14.0（AideanBotHot · main@fdad6dd · 2026-10-19）

## 0. 一句话
上一轮执行段（`79de1ca..fdad6dd`，24 个提交，57 个文件 +5749/−409）把 V0.13.0 的两张 P0 卡（00H、22）和 20/23/02-S2.4 交付了，三条工作流全绿。
但本版现跑又发现：**推送任务创建对任何角色都返回 500**（STEP-24），而且**运营角色被锁在全部推送写接口之外**（STEP-25）。这两项是新的 P0，并且都在规划方自做的关键路径上。

## 1. 规划快照
```yaml
snapshot:
  规划日期: 2026-10-19（Asia/Shanghai）
  仓库: https://github.com/aideanew/BotHot
  git_branch: main
  git_commit: fdad6dd8a3df98884ea911f659caa2703b51fa2a   # 规划基线；本目录的提交在其后
  上一规划提交: 79de1ca28cfcfce3b8abb2d1660ea1be02f3fb66（V0.13.0）
  工作区是否干净: true（拉取前后 git status --short 均为空）
  双端: 拉取前 HEAD...origin/main = 0 24 → ff-only → 0 0
  端口: 前端 3200 / 后端 3300（主平台 3000 禁占）；guard-ports 见 06
  需求文档: docs/02_requirements/{product-requirements.md, features/, non-functional/, constraints/, inbox/}（目录最后改动 2026-10-12 14:56 +0800）
  代码文件数: git ls-files 5652；apps/api/app 112；apps/web 191；apps/api/tests 下 test_*.py 94
  测试命令: cd apps/api && alembic upgrade head && python -m pytest tests/ -q --cov=app
  CI@fdad6dd: CI 39184824704 success / CI-Windows 39184824751 success / Security 39184824740 success
  本机全量@fdad6dd: 1570 passed / 5 skipped / 1 failed（失败项由宿主环境变量导致，清空环境后 1 passed，见 01 §3）/ 覆盖率 86% / 147.27s
```

## 2. 目录
| 文件 | 内容 | 对应用户 §10 节号 |
|---|---|---|
| `00-README.md` | 快照、目录、启动顺序 | 1、16 |
| `01-事实基线与进度.md` | 已确认事实、执行段核验、文档与代码不一致清单 | 2 |
| `02-需求复核与辩证分析.md` | 复述、MoSCoW、冲突、未知登记册、隐含要求、5W1H/追问/钢人/终判 | 3.1–3.5 |
| `03-裁决与契约增量.md` | D-V11-01～08；六份契约的增量与唯一源；数据模型与迁移顺序 | 4、5 |
| `04-剩余可执行大纲体系.md` | 切片、L1→L4 大纲、40 卡表、DAG、所有权、档位与成本、指标 | 6–11 |
| `05-风险自检与局限.md` | 风险、未决、待裁决、§12 自检、局限 | 12、14、15 |
| `06-入库与双端一致.md` | 落盘清单、守卫读数、推送校验 | 13 |
| `gen_table.py` | 40 卡剩余量与 DAG 复算脚本（04 的表由它生成） | 8、10 |
| `steps/STEP-24/25/26-*.md` | 新卡（24、25 由规划方自做，26 交执行方） | 7 |
| `steps/STEP-继承卡增量-*.md` | 追加到 00T/00R/15b/10/05/08/17/14a 的 12 项原子任务 | 7 |
| `evidence/fdad6dd/` | 本版全部原始读数 | — |

## 3. 启动顺序（建议的第一刀）
1. **规划方（我）**：STEP-24 → STEP-25（同一切片 SL-PUSH-1，串行；24 修好之后 25 的矩阵才能区分 10004 和 50001）。
2. **执行 Agent-Guard（同时开工，文件不相交）**：S00H.2.3（CI-Windows 已经在三个不同提交上 success）→ 00R 增量 → 00T 增量（两道闸 + F-14）。
3. **执行 Agent-API（同时开工）**：STEP-04 S4.5.1 复跑 → STEP-10（含 P-20）→ STEP-05（含 P-30 计数器）。
4. 25 合入后：STEP-26 交执行 Agent-API；规划方转 15b（含按秩导航）→ 21。
同时写入的 Agent 不超过 3 个（规划方、Guard、API）；Data 线（07→08→09）等 Guard 线空出来再开。

## 4. 与 V0.13.0 的关系
- V0.13.0 目录保持原样，那 37 张卡仍是权威卡面（D-V11-07）。V0.13.0/09（执行侧再清点）的执行序在本版大纲里整体采纳，计数以本版 `gen_table.py` 为准。
- 冻结契约仍只在 `docs/任务规划V0.12.0/contracts/`（被 `test_collection_contract.py:63-65` 等硬绑定），不复制。
