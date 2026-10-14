# BotHot 剩余任务规划 V0.7.0（基线 main@13acacc）

> 规划日期：2026-10-14｜仓库：https://github.com/aideanew/BotHot（main）｜**规划方未修改任何业务代码**，仅写 `docs/任务规划V0.7.0/**`。
> 上一版：V0.6.0（基线 a9b194d，产出后未入库，长期停留在工作区未跟踪状态；本版将其纳入仓库并以本版为准）。

## 0. 一句话结论

**V0.6.0 的 M0 判断依然成立且更硬了：短链二次入库的缓存回归在 `13acacc` 上仍在——`apps/api/app` 自引入回归的 078dc30 起一行未改。但本版查到 V0.6.0 自己有两条会直接坑死执行者的缺陷：它的 R0 验收判据 `grep "like(" kb.py 为空` 命中一句解释「为什么删」的 docstring，因此永远验不过；它要修的 E501 行号已从 `:104` 漂到 `:116`。**
**更大的问题是宽度：12 条需求里 V0.6.0 只有 2 条有实质 STEP，9 条一个卡都没有——引擎域 16 处 `NotImplementedError`、6 组管理端点「有 API 零前端消费」、四条性能 SLA 全无度量锚、告警默认关（`ALERTING_ENABLED=false`）导致 V0.6.0 STEP-05「缺陷一天内被发现」的前提根本不成立。V0.7.0 把这三件事一起补上：修 M0 卡的自伤缺陷 + 新增 STEP-13…19 覆盖 9 条需求 + 冻结 6 份机器可校验契约（此前只有 2 份且缺 Identity/Resources/Events/UX）。**

## 1. 本版相对 V0.6.0 的变化（每条附证据）

| # | 变化 | 证据 |
|---|---|---|
| 1 | 基线 a9b194d → **13acacc**；确认 `apps/api/app` 未变 ⇒ 回归判断仍成立 | `evidence/13acacc/static_readings_13acacc.txt` S-02（F-65） |
| 2 | **作废恒红判据**：R0.2.3 的 `grep "like(" kb.py 为空` → 改复用 AST 判据 AF-S6 | S-06（F-75）、`prove_anchor_fallback.py:820`（F-76） |
| 3 | **更正过期行号**：E501 `test_asset_fragment_guard.py:104` → **:116**；并新增 S0C.1.0「先实跑 ruff 再动手，禁止照抄 5 这个数」 | `e501_lint_scan_13acacc.txt`（F-68/F-69） |
| 4 | **新增两句假 docstring 的修正任务**（R0 S-R0.2.2/S-R0.2.4）——它们是回归进主干的直接原因 | `kb.py:339-340`、`kb.py:468-469`（F-74） |
| 5 | 证明脚本冻结基线 6,801 → **7,322**（同口径）/ 全量口径 **8,383**；新增「只降不升」与 docs:app 比出门指标 | S-09（F-67） |
| 6 | 复审熔断加**机械执行**（反证：S2.1.3 已 13 轮必须判红） | `git show a576bc2`（F-66） |
| 7 | **新增 STEP-13…19（7 张卡、47 个三级任务）**覆盖此前无 STEP 的 9 条需求 | `coverage_and_domain_audit_13acacc.txt` §2-§4（F-77…F-87） |
| 8 | **契约从 2 份补到 6 份**（API/Errors/Identity/Resources/Events/UX），全部 JSON Schema draft 2020-12 且逐条带本仓 `file:line` 来源 | `contracts/*.json`（任务书 §4.1 六份齐全） |
| 9 | 冻结「分页目标壳」并登记**分页两壳并存**为真实缺陷（9 处 offset vs 6 处 page） | F-80 |
| 10 | STEP-00T 由 M1 **提进 M0**；STEP-05 新增前置 STEP-16（否则告警验收是纸面绿） | F-83、05 §1 R-7 |
| 11 | 规模 17 STEP/116 任务/19.25 人日 → **24 STEP/173 任务（👤 17）/≈27.75 人日**（合计经程序化求和更正，见 07 §3-2） | 04 §4.2/§4.8 |
| 12 | 完成定义新增两条排除项：**skip≠pass**、**判据先验可满足性**；并禁止抄上一时点读数当本时点值 | F-88、F-75、04 §4.14 |

## 2. 阅读顺序

| 文件 | 内容 |
|---|---|
| `01-事实基线与上一步复核.md` | 快照、F-64…F-88 新读数、NOT_MEASURED 清单、上一步做了什么/没做、对 V0.6.0 的逐条复核、读取失败部分 |
| `02-需求拆解与根因穿透.md` | 本次需求 R-1…R-9、MUST/SHOULD/COULD/MUST NOT、7 条冲突、**四条根因链**、双向钢人论证 B-1…B-3、隐含前置 |
| `03-裁决默认值与契约.md` | 20 项裁决（11 继承 + 9 新增，含 4 个 BLOCKING）、6 契约索引、数据模型基线、索引策略、**迁移号串行编排** |
| `04-剩余可执行大纲体系.md` | 24 STEP 总表、**需求覆盖矩阵**、DAG 与两条关键路径、并行机械判定、所有权矩阵与 3 处重叠消除、档位成本、基线指标 B-1…B-15、里程碑、**继承卡 16 字段补遗**、日历、13–19 完整大纲、完成定义 |
| `05-风险自检与局限.md` | 10 条风险、13 项未决、5 项待裁决、§4 自检逐条、6 条前提与局限 |
| `06-入库与双端一致.md` | 落盘清单、第 1/2 批切分与理由、推送与双端一致自证命令 |
| `steps/STEP-*.md` | 24 张任务书（17 继承并标注变更 + 7 新增） |
| `contracts/` | 6 份冻结契约 + 2 份继承（collection 域） |
| `evidence/13acacc/` | 本会话全部机器读数（8 份，均为静态；无一条来自运行） |

## 3. 立即可做的三件事

1. **第一刀（不需要任何新裁决）**：在依赖执行机上对 `13acacc` 走 STEP-R0 + STEP-00C 同一 PR——但**先跑 R0 的 S-R0.1.2 与 00C 的 S0C.1.0**（判据可满足性 + ruff 实跑），再动手改；V0.6.0 那份合并补丁可套用（`git apply --check` rc=0，一处 +12 offset），**能套用不等于还对**。
2. **零依赖并行**：STEP-17（纯文档）任何机器今天就能做；它同时是「下一轮不再只覆盖采集域」的结构保障。
3. **裁决供给**：`docs/03_solution/decisions/decision-log.md` 仍不存在，20 项 **0 已签**。先签 4 个 BLOCKING（D-V3-00/01/03/06），其中 D-V3-00 决定 UI 三张卡（14b/15/16）由谁执行。

## 4. 本版刻意不做的事（MUST NOT，防范围蔓延）
- 不排任何「性能优化」任务——四条 SLA **尚无基线**（B-15），按模板 §9.1 无基线不准优化；只排 STEP-18 测量。
- 不复活 `Source.url.like` 兜底（会让 P-4 回来），也不顺手删 `asset.py:66` 的 LIKE（与回归无关，属越界）。
- 不新增迁移号给 13–19；需 DDL 即停转 ADR。
- 不把 `apps/web` 的 mock 分支补回去迁就旧注释（`e2e/hot.spec.ts:4` 的错在注释，不在实现）。
- 不给引擎域「先建通用适配器框架」——未实接前那是为假想需求设计。
- 不改写 V0.4.0/V0.5.0/V0.6.0 的历史结论；勘误只在本版就地标注。

## 5. 与 V0.6.0 / V0.5.0 的关系
- 本版 `steps/` **自包含**：17 张继承卡已复制进来并逐张在卡尾标「V0.6.0 → V0.7.0 本卡变更」；执行者只需读 V0.7.0。
- V0.6.0 与 V0.5.0 保留在仓内作历史与证据溯源（其 `evidence/a9b194d/*` 是本版 NOT_MEASURED 项的上一时点唯一记录）。
- 冲突时**以 V0.7.0 为准**：行号（:116）、冻结基线（HEAD 口径 7,322 / 全 evidence 8,383；⚠ 本会话结束时工作树已达 **7,995**，系并发会话第十四轮未提交改动，见 07 §2）、R0 判据（AST 而非 grep）、规模（24 STEP/173 任务）四处 V0.6.0 已过时或需带口径。

## 6. 复现本版读数的命令（win32 即可，无需依赖）

```bash
cd <repo> && git rev-parse HEAD                    # 期望 13acacc…
git diff --stat 078dc30 HEAD -- apps/api/app       # 期望空（F-65，回归仍在的根据）
git apply --check -v docs/任务规划V0.6.0/evidence/a9b194d/STEP-R0+00C_combined_simulated_a9b194d.patch; echo rc=$?
grep -n '\.like(' apps/api/app/services/kb.py      # 期望命中 :342 docstring ⇒ R0 旧判据恒红
wc -l docs/06_validation/evidence/EVD-V2-00R/*.py docs/06_validation/evidence/EVD-V2-02/*.py | tail -1   # 7,322
find docs/06_validation/evidence -name '*.py' | xargs wc -l | tail -1                                     # 8,383
grep -rhoE 'REQ-(F|NF|C)-[0-9]{3}' docs/任务规划V0.6.0 | sort | uniq -c    # 仅 F-004 / NF-001 ⇒ 2/12
grep -c NotImplementedError apps/api/app/providers/engine_port.py          # 16
for p in admin/push admin/ops/liveness admin/discovery/channels admin/engines/keys backchannel-logout; do printf '%s=' $p; grep -rl "$p" apps/web/app apps/web/components apps/web/lib 2>/dev/null | wc -l; done   # 全 0
```
> E501 的显示宽度扫描（CJK 记 2 列）判据已完整写在 `evidence/13acacc/e501_lint_scan_13acacc.txt` §1-§2；规划方的一次性脚本未入包（避免污染证据件）。
