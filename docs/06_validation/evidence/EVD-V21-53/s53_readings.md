# EVD-V21-53 发布 v1.1.3（执行助手）

平台 @win（Windows 10 x64）。开工 head `c8307f7`（STEP-55 收口批）。时间 2026-10-26（Asia/Shanghai）。

## 0. 开工前置（逐条现取，不沿用记忆里的数）

| 前置 | 读数 |
|---|---|
| 队列 52/54/55 是否都收口 | 卡表第 6/7/8 行均 ✅ 三绿；三张卡的收口批分别是 `92af50a`、`e4a9a67`、`c8307f7` |
| 开工 head 三绿 | `c8307f7`：CI **40325881539** success / CI-Windows **40325881543** success / Security **40325881529** success，均 attempt 1 |
| 上一次发布用的 tag | `v1.1.2`（STEP-44，2026-10-24）；本版按卡面只新增一个注释标签 `v1.1.3`，**不动任何已有 tag** |
| 规划方是否有新提交待合 | `git fetch` 后 `origin/main...HEAD` = `0 0` ⇒ 双端一致，无需 rebase |

`c8307f7` 的判据读数（发版前的最新一次全绿，逐字取自 run 级 logs zip，原文 `s53_0_preopen_ci_readings.txt`）：
CI backend `2471 passed, 6 skipped, 4 deselected`（206.15s）、skip 门禁 `total_skipped=6 baseline=6 pg_unreachable=0`、
`Total coverage: 88.93%`、`✅ 全部模块与全局达标`、前端 `53 文件 / 425 passed`、mock e2e `31 passed`；
CI-Windows `failed=0 total_skipped=692 baseline=692`、前端 `53 文件 / 425 passed`（与 ubuntu 侧、本机侧逐字同数）。

## 1. S53.1 独立复查（判据①）

见 `s53_1_independent_review.md`：**STEP-46 PASS（带 nits）、STEP-47 PASS（带 nits）**，无 FAIL、无 UNKNOWN ⇒
判据①满足，不触发卡面第 16 格阻塞。复查产出新登记 **P-126**（台账 `docs/任务规划V0.12.0/00-README.md`，
契约生成链的反向核覆盖面按 mock 路由表反推、缺一道孤儿 def 判据；现测 30 个 def 全部可达 ⇒ 潜在面而非现存缺陷），
以及两条交回规划方的文档订正（`02-需求复核与辩证分析.md:29` 的"24 条"应为 22；
`EVD-V21-47/s47_red_extra_key.txt:2` 的行号与交付字节不符，按纪律不回改已归档原文）。

复查后到本发版批之间**代码零改动**：`git diff --name-only c8307f7 HEAD` 只含 `CHANGELOG.md`、
`AGENTS.md` 与本证据目录（判据①的 PASS 对被 tag 的 head 仍然成立，这条在 §4 用 diff 复核入证）。

## 2. S53.2 CHANGELOG 与 AGENTS 版本块（本版实际改动面）

`CHANGELOG.md`：新增 `## [v1.1.3] - 2026-10-26` 段（现读在第 18 行），`[Unreleased]` 的占位说明改成本版口径。
条目**按区间重新对账**而不是抄 `[Unreleased]` 的条数（v1.1.0 的失真教训）：`git log --oneline v1.1.2..c8307f7`
共 28 个提交，其中主语带 `feat(`/`fix(` 的 10 个（含 1 个把规划文档混在里面的 `9816f7f`，
和 1 个只是导入排序的 `88d7518`），另有 STEP-51 的文档纠真批；
11 个来源短 hash 逐个 `git log -1` 复核主语（`9816f7f`/`f4f0261`/`0aa2923`/`4a2c62b`/`be23d41`/`a8c3df9`/
`8644bea`/`4dc37ec`/`88d7518`/`4245847`/`eae0356`），全部存在且主语与条目对得上。

### 发版批自己也过了一轮独立复查（结论先是 FAIL，四条改完才对）

这一批的产物就是"给人读的话"，所以复查针对措辞与字节是否相符。**首轮判 FAIL**，四条被逐字核实并订正：

1. `scripts/** 进 lint/type 检查面；治理门的基线由事件给出` —— **删条**。它属于上一版：`53b5197`（STEP-34 S34.8）
   经 `git merge-base --is-ancestor` 确认是 `v1.1.2` 的祖先，且同一条已在 `[v1.1.2]` 段里；我原来引的
   `9816f7f`/`a8c3df9` 根本没动 lint/type 配置（前者只抬 `SKIP_BASELINE_WIN`）。
2. STEP-50 那条写"AGENTS/conventions 里引用的 Node、Next、`requires-python` 等逐条对账" —— **改写**。
   `scripts/check_docs_consistency.py:447-456` 的语料只有 `AGENTS.md` + `docs/02_requirements/**`，
   `:418-421` 明确**跳过** `requires-python`；现文里写清这两点，并把 `conventions.md` 不在覆盖面说成已知未覆盖。
3. "本版对外契约的可见变化只有一处语义纠偏（30101→30004）" —— **改口径**。它被自己那段推翻：
   同一节列的演示态七处形状修正、以及 `useSpaceDetail.ts:169` 并入 30004 让 404 空态**在真实后端下第一次生效**，
   都是用户可见的。现改为"真实端点响应形状零改动；改的是演示态数据面 + 前端一处行为 + 门禁"。
4. AGENTS 里"运行时形状门——摘掉某条 `satisfies` 也能红" —— **改准**。没有任何门去看 `satisfies` 这个词；
   红的是"摘掉之后这条样例与契约不同形"。现写成两句：旧死角是"被摘后走形无人判"（实测 rc=0/rc=0），
   摘掉本身若样例仍同形不红（那是类型层弱化）。

另有五条精度订正一起改了：22 条 satisfies 的归属补上 STEP-48 的引擎 2 条；"engine 4 个 def"注明本版新增其中 2 个
（`git show v1.1.2:...engine.schema.json` 里只有 `EngineCapability`/`EngineReason`）；"真端点反向核 17 条"改成
"该文件 17 条用例，其中响应反向核 9 处＝7 真端点 + 2 桩端点"；覆盖率抖动那句从"±0.03 见 AGENTS 测试段"
改成实测跨度 88.90–88.99 并指明 AGENTS 记的是同族另一组数；证据里 `:43 在 _errors 内` 改成 `:43 是空行、
`_errors` 在 `:44-45``，`mock-routes.ts 的 method:/pattern: 各 22 处` 改成原始计数 27/23 并以常驻判据为准。
**这条记录本身要留着的理由**：四条里三条是"数字对、归属/范围说满了"，正是发布说明最容易带进生产的那类错。

`AGENTS.md`：只改"当前项目状态"的版本块（与 STEP-44 发布批同范围——`git show a221f89 -- AGENTS.md` 的 diff
只有一个 hunk，就是这一段；**测试段的基线读数不由发布批代改**，那是各卡收口时维护的）。
新块写明：本版零迁移、零新增对外端点、唯一对外语义纠偏是演示态未命中码 30101→30004；
tag 的权威读数一律现取（`git ls-remote --tags origin v1.1.3`、`git rev-parse v1.1.3^{commit}`），
本行不抄自己的 sha（自指），区间计数 `28 + 1 = 29` 也标注"以现取为准"。

## 3. 已有 tag 的基线（判据④的前半，动 tag 之前取）

```
$ git show-ref --tags
42a21f2ee463e3636c341909e832523470771dbd refs/tags/local-recovery-42a21f2
67511854ab2582c584f54487f9768cd9496213cc refs/tags/local-recovery-6751185
8ecf3220ff823c405e6e4e61456688e79e5177a1 refs/tags/v1.0.0
db9205df7fc7a55bf5653e33e368b6cb8e128d75 refs/tags/v1.1.0
3eace8804f772bc1ea33951b6ec717de17e65012 refs/tags/v1.1.1
4d61f5e90dc7adb6923793952f5295ff63a9b2e1 refs/tags/v1.1.2
```

发版批与 tag 推完后逐个 `git rev-list -n1 <tag>` 复取，逐字相同才算"一个都没动"（读数在 §5）。

## 4. S53.3 tag + Release + 三绿

（待回填：发版批 head、三绿 run id、tag 对象与指向提交的 `git ls-remote` 两行、
`GET /repos/aideanew/BotHot/releases/tags/v1.1.3` 的状态码与 `html_url`、`git show-ref --tags` 与
`git rev-list -n1` 的前后对比、`git diff --name-only c8307f7 <发版批>` 的代码零改动复核。）
