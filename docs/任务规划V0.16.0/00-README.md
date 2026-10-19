# 任务规划 V0.16.0（AideanBotHot · 基线 main@28c0d2e · 2026-10-19 23:45）

## 0. 一句话
**STEP-27 交付并收口**：执行助手两轮完成 8 项（d32edfc + 9e1532d），14 个被挡的自有源码文件全部归零，@ci 三绿；规划方补读收口提交 28c0d2e 也三绿，本机真库全量 **1765 passed / 6 skipped / 0 failed、覆盖率 86.14%**、迁移单头往返通过。独立复查（opus）判 **A 项 FAIL**：短变量名左值后跟写死兜底值整类漏报——但旧门同样漏、且卡面 ④ 要求 `SECRET_ASSIGN` 字节不变，是**卡面自相矛盾的存量缺口，不是倒退**。按 D-V16-01：27 收口不开第 3 轮，缺口登记 P-44 转新卡 **STEP-29**。
全仓普查还剩 11 个自有文件有命中（1 个业务文件误报 + 10 个测试夹具），后续卡一碰就被挡 ⇒ **执行队列第一项改为 STEP-29**，之后按 V0.15.0 的队列继续。

## 1. 规划快照
```yaml
snapshot:
  规划日期: 2026-10-19 23:45（Asia/Shanghai）
  仓库: https://github.com/aideanew/BotHot
  git_branch: main
  git_commit: 28c0d2e      # 本版基线；上一版基线 6b3a58f/8135f1a
  工作区是否干净: true（未跟踪仅 apps/api/.coverage，被忽略的测试产物）
  双端: git pull --ff-only 后 HEAD...origin/main = 0 0
  CI@9e1532d: CI 39271291938 ✅ / CI-Windows 39271292029 ✅ / Security 39271292556 ✅
  CI@28c0d2e: CI 39274782243 ✅ / CI-Windows 39274782211 ✅ / Security 39274782247 ✅（规划方补读，执行方焚毁凭据后未读到）
  CI@8135f1a: CI ✅ / Security ✅ / CI-Windows ✅（18:48 回填）
  本机@28c0d2e（@linux，PG16@5547 独占）: alembic upgrade head rc=0、downgrade -1 再 upgrade rc=0、单头 ab1006c1a；pytest 1765 passed / 6 skipped / 0 failed，覆盖率 86.14%（门 75），墙钟 163s
  skip 构成: Redis 不可达 3、LangBot :5300 不可达 2、代理变量对照 1；PG 不可达 0
  前端: 8135f1a..28c0d2e 未改 apps/web/**、apps/api/app/**、packages/**（git diff 现读）⇒ 沿用 typecheck/lint/vitest 385 读数
  测试命令: cd apps/api && pytest tests/ -q -rs --cov=app --cov-fail-under=75（ci.yml 同款）
```

## 2. 阅读顺序与目录（按 `docs/任务规划-命名规则.md` 固定 8 文件）
| 文件 | 内容 |
|---|---|
| `00-README.md` | 本文件：结论、快照、第一刀 |
| `01-事实基线与进度.md` | 27 交付核验、普查、文档与代码不一致清单、各卡进度 |
| `02-需求复核与辩证分析.md` | 复查 A 项 FAIL、P-41～P-46 的复算与终判（支持/反对论证） |
| `03-裁决与契约增量.md` | D-V16-01～05（已同步 decision-log）；契约无变化 |
| `04-剩余可执行大纲体系.md` | 43 卡表（`gen_table.py` 输出）、DAG、关键路径、并行组、所有权、**附录：执行助手提示词** |
| `05-风险自检与局限.md` | 风险、待用户输入、§12 自检、局限 |
| `06-入库与双端一致.md` | 落盘清单、门禁读数、推送后双端 |
| `07-执行过程记录.md` | 本版规划过程与更正 |
| `gen_table.py` | 剩余量、DAG、关键路径复算 |
| `steps/STEP-29-夹具占位形与证据脚本隔离.md` | **新卡，队列第一项** |
| `steps/STEP-继承卡增量-V0.16.md` | 27 收口、依赖改向 29、S27.3 数字更正 |
| `evidence/28c0d2e/` | 全量测试、迁移往返、敏感形普查、独立复查读数 |

## 3. 第一刀与启动顺序（执行助手一个，串行）
1. **STEP-29**（6 项：召回补缺 → 误报 → 夹具 → 证据脚本隔离 → 读数口径）。
2. STEP-26 → STEP-04 S4.5.1 → STEP-10 S10.V15.1 → STEP-05。
3. STEP-07（S07.V15.1～3 测试库演练）。
4. 00H S00H.2.3 → 00R → 00T。
5. STEP-28 → STEP-10 S10.V15.2 → 08 → 09（迁移串行）。
6. **规划方（核心/高难度，含 UI）**：STEP-21（IDOR 连库矩阵）→ STEP-15b（含 V15.1 网络桩、V15.2 按秩隐藏）→ 19 → 14b（含采集配置页）→ 13 → 15 → 12。
7. 提醒用户：STEP-26 交付且真实渠道发送成功后，重置飞书/钉钉 webhook 与 app_secret（D-V12-15）。

## 4. 与旧版本的关系
- V0.13.0/V0.14.0/V0.15.0 卡面仍权威；本版只写增量（D-V11-07）。冻结契约仍只在 `docs/任务规划V0.12.0/contracts/`（未改）。P 表仍在 `docs/任务规划V0.12.0/00-README.md`，本版追加 P-42～P-46。
