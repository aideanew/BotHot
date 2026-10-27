# STEP-56 读数与判词（EVD-V21-56）

基线：规划方 `97cc469`（三绿与本机 PG 前置见 `s56_0_preopen_ci_readings.txt`）
卡面：`docs/任务规划V0.21.0/steps/STEP-56-契约覆盖面孤儿判据.md`
交付面：`apps/api/tests/test_contract_def_coverage.py`（新）+ `test_engine_response_contract.py`
+ `test_contract_jsonschema.py` + `docs/任务规划V0.21.0/02-需求复核与辩证分析.md`
+ `docs/06_validation/evidence/EVD-V21-47/ERRATA.md`。禁止面 `apps/api/app/**`、
`packages/contracts/**`、`scripts/gen_contracts.py` 与冻结稿 `docs/任务规划V0.12.0/**`
在交付批里零改动（探针动过、逐字还原，见 §2 末）。

## 1. S56.1 新守卫

现读的种子与 def 面（`s56_readings_raw.txt`，跑在交付字节上）：

| 面 | 读数 |
|---|---|
| shapes 种子（测试里 `_check("<名>", …)` 的调用点） | 19 个 |
| engine 种子（带 `db_session` 的用例所用 validator 常量绑定的 def 名） | 2 个（`EngineList`、`SpaceEngineBinding`） |
| shapes def / engine def | 30 / 4 |
| 活体判据（两域一起） | `[]`（零条） |

种子 21 个，def 34 个 ⇒ 其余 13 个靠 `$ref` 入边活着，逐条现读（同 `s56_readings_raw.txt`）：
`EngineCapability`←`EngineList`、`EngineReason`←`EngineCapability`、`MeUser`/`MeWallet`←`MeView`、
`SpaceStats`←`SpaceDetail`、`SpaceView`←`SpacePage`、`SpaceDocItem`←`SpaceDocPage`、
`SpaceDocStatus`←`SpaceDocItem`、`BatchDocFailure`←`DocsBatchDeleteResult`、
`DocIngestStatus`←`DocIngestState`/`IngestAccepted`、`NotificationItem`←`NotificationHistoryPage`、
`PublicSpaceView`←`PublicSpacePage`、`ExtractedImageView`←`ExtractedArticleView`。

三个设计决定，都不是风格问题：

1. **种子取调用点而不是整篇正则**。整篇正则读得到 `_check` 的定义处与模块常量，删掉一条真端点
   用例它照样取到那个名字——那正是 P-126 说的"覆盖被删了没人红"。engine 侧的 def 名绑在
   `_LIST`/`_BINDING` 上，用例里只出现变量名，所以取"带 `db_session` 的用例里 `_errors(<常量>, data)`
   调用点所用的常量"；两条不连库的"契约有牙齿"用例同样引用这两个变量，但它们打合成字面量、
   不打真端点，**不算覆盖**。认到调用点而不是认引用，是为了堵另一种写法：删掉断言、
   只留一句对常量的引用，按"出现过名字就算"的口径照样读绿（反证
   `test_teeth_keeping_the_reference_is_not_coverage` 打的就是这一刀，并顺手要求另一条用例不受牵连）。
2. **`$ref` 不走注释键与数据键**。可达性跳过 `x-*` 与 `enum`/`const`/`default`/`examples`/`required`，
   其余子树（`properties`/`items`/`additionalProperties`/`anyOf` 分支等）一律下钻。本项目的散文就写在
   `x-*` 里，而 validator 从不求值那些子树：往 `x-note` 里塞一条 `$ref` 就能替一个 def 买到
   "有人核过它"的假象。这是 `test_collection_contract.py` 的 `_referenced_by` 当年被 G3 打穿后收紧的
   同一条刀，新守卫一上来就用收紧后的形制（反证
   `test_teeth_ref_inside_annotation_does_not_grant_reachability` 两边都测：藏在注释里不算、挂在
   `properties` 上才算——只测一边要么放行要么误伤）。**为什么不做"只放形状键"的白名单**：那样将来
   产物换一个容器键（`not`/`contains`/`propertyNames`…）就会漏掉真引用，把一个本来有人核的 def 读成
   孤儿——那种假红比多下钻一层产生的假红更难查；而白名单在第一版里其实根本不参与判定
   （第 2 轮复查点出的装饰性缺陷，已删，见 §7-13）。
3. **坏边扫每一个 def**，不只扫可达集里的。第一版只走可达集，于是"既是孤儿又挂坏边"的 def
   只剩"孤儿"这一句，坏边要等它被接上可达链才露出来——`test_teeth_dangling_and_cross_domain_refs_are_reported`
   第一版就是因为这个读绿的（不是判据没问题，是我打探针的地方不对），改成全量扫之后才红。

4. **实参是合成容器的 `_check` 不算覆盖**。`_check("Foo", {...})` 判的是测试自己造的对象，不是
   真端点响应；种子抽取要求第二个实参不是 `dict`/`list`/`set`/`tuple` 字面量（反证
   `test_teeth_synthetic_object_is_not_coverage` 把 `LogoutResult` 的实参换成空字典，要求它立刻
   从种子里消失并进孤儿清单）。现读 19 条 shapes 种子在这条规则下**一个不少**（全都是
   `resp.json()["data"]` / `data` 这类来自响应的形制），所以它不是为了让读数好看才加的。

判据在孤儿之外还判三类相邻的静默面：`$ref` 指向本域不存在的 def、`$ref` 跨域（真端点用
`{**SHAPES, "$ref": …}` 建 validator，跨域引用在 `_check` 当场抛 error 而不是契约层红）、
测试里的种子名在产物里根本没有。常驻 11 条用例 = 2 条正面 + 9 条反证。

## 2. 先红（卡面验收 ①②，原始输出全部归档）

| 探针 | 打法 | 新守卫 | 旧门 | 还原 |
|---|---|---|---|---|
| ①a 字面形 | `shapes.py` 加一个无人引用的 def + 重新生成产物 | **红** `s56_1a_newguard_red.txt`（1 failed / 10 passed，红的正是 `test_no_contract_def_is_an_orphan`） | `test_shapes_response_contract` 17 passed、`test_engine_response_contract` 6 passed、`gen --check` 0 **绿**；但 **旧比对器 `test_collection_contract` 也红**（`s56_1a_oldgate_collection_red.txt`：`生成物多出一个 def（稿里没有 ⇒ 谁加的？）`），本卡 S56.3 的名字集门也红（`s56_1a_nameset_gate_red.txt`） | `RESTORE_DONE sha_all_equal=True`；`git diff --stat` 对 `apps/api/app`、`packages/contracts` 为空 |
| ①b 隔离形 | 同一个 def **同时**写进 `shapes.py` 与冻结稿（节点从产物里逐字抄）⇒ 变成"稿与产物都有，但没人核、没人引用" | **红** `s56_1b_newguard_red.txt`（1 failed / 10 passed） | **全绿**：`test_collection_contract` 220、`test_contract_jsonschema` 82（多出的那条探针正是它）、`test_shapes` 17、`test_engine` 6、`gen --check` 0、contracts `tsc` 0、前端 `s48/s52/s55` 3 文件 7 passed（`s56_1b_frontend_vitest_green.txt`） | 稿与 6 个文件全部还原，`git diff --stat` 对 `docs/任务规划V0.12.0` 为空 |
| ② 引擎覆盖被删 | 删掉两条连库真端点用例（114→93 行） | **红** `s56_2_engine_live_deleted_newguard_red.txt`，3 failed / 8 passed：`test_no_contract_def_is_an_orphan` 四条点名（`EngineList`/`SpaceEngineBinding` 无落点，`EngineCapability`/`EngineReason` 因"引用它的 def 自己也不可达"一起进来），`test_both_domains_contribute_seeds` 同时红 ⇒ "整域失去覆盖"与"某条用例被删"分开报；第三条红是常驻反证 `test_teeth_keeping_the_reference_is_not_coverage`——它的锚点（`_errors(_LIST,`）就在被删的那两条用例里，锚点消失 ⇒ 它自己按设计红（这条不是缺陷，是"反证不许默默空转"那道自锁在起作用） | 全绿：`test_shapes` 17、`test_engine` 4（剩下的）、`test_contract_jsonschema` 81、`test_collection_contract` 219 | `RESTORE_ENGINE_LIVE sha_equal=True sha=b3f61dd375c4` |
| ③ S56.2 判据强度 | 把产物 `engine/dto.ts` 里 `export type EngineReason = …` 换成一行提到该名的注释 | 新正则 **红**（`s56_3_engine_file_red_on_mutated_dto.txt`，2 failed / 4 passed，带 DSN ⇒ 0 skipped） | 同一份字节上旧子串判据把四个 def **全读成"在"**（`s56_3_old_vs_new_criterion.txt`：`rc_like 0`），新正则只报三条 ⇒ 差集就是 `EngineReason` | `sha_all_equal=True` |

**卡面写的"旧门全绿"只在 ①b 成立**，这条如实记着：旧比对器管的是"产物有没有私加稿里没有的 def"，
而 P-126 的病是"稿与产物都有、但没有任何真端点反向核、也没有可达引用"。所以我没有只交 ①b 那个
干净结论，而是把 ①a 的实际读数也一并归档——①a 里旧门红了两处，这不是探针失败，是那条判据的
覆盖面本来就比卡面假设的宽。

另一处如实记：备份文件本身会撒谎。第一次的备份取在 S56.2 增补之前，`restore` 把我后来加的
`test_ts_dto_criterion_is_export_scoped` 一起"还原"掉了，而它照样打印 `sha_all_equal=True`
——它比的是备份自己的 sha，不是我意图中的交付字节。发现后按最终字节重取备份，四条探针全部重跑，
本文件的数字与归档的 `s56_1a_* / s56_1b_* / s56_2_* / s56_3_*` 输出都出自重跑那一次
（`EVD-V21-56/` 里没有 `.py`，探针驱动与读数脚本都留在临时目录）。

守卫里 9 条反证跑的是合成副本（改的是内存里的文档或源码字符串），不是仓库字节——它们判的是
"某类写法会不会让判据静默"，产物现状由正面那条判。

## 3. S56.2 与 S56.3

**S56.2**：`test_engine_response_contract.py` 的子串判据换成与 shapes 域 `:88` 同形的
`export (interface|type) <名>\b`。两侧现在同形，也就同样放行"被注释掉的 export"
（`// export interface X`）——本卡要求同形，我没有在这一侧偷偷加强度，把这个残留记在这里。
换判据的理由不再写在注释里，而是常驻一条反证 `test_ts_dto_criterion_is_export_scoped`：
在同一份产物文本上做"导出行→散文"的替换，要求新判据报不出来、旧子串判据四个名全放行。
现读这份产物，四个 def 名各自唯一"两侧带空白"的出现位就是它自己的导出行（实测各 1 处，
行号 8/21/26/28），所以这个锚点是最小的。

**S56.3**：七域现读（`s56_readings_raw.txt` 末段）——`genOnly` 七域全 0；`draftOnly` 共 10 个，
分布在 collection(1)/identity(3)/events(4)/resources(2)，`api.envelope`/`engine`/`shapes` 三域字面相等。
10 个的落点逐个现读：①稿根层 `x-not-in-single-source` 声明非形状 5 个（`IsAdminEcho`、
`EventPayloadRules`、`ManifestTransition`、`QueueMechanism`、`ChannelSecret`）；②被已收编 def 在
形状位 `$ref` 引走 3 个（`collection/ArticleKey`、`identity/Sub`、`resources/ArticleKey`）；
③`ALIAS_WITNESSES` 点名可执行见证测试 2 个（`identity/UserId`、`events/IdempotencyKey`）。

⇒ **卡面判据③触发**：字面"名字集相等"今天不可能绿。要相等只有两条路——给那三个没有使用处的别名
（`UserId`/`IdempotencyKey`）与两个跨域 `ArticleKey` 在冻结稿里补根层声明，或者给它们真使用处；
前者是改稿的语义声明（规划方的面），后者要动 `app/contracts/**`，两者都在本卡允许面外。
已登记 **P-127 交回**，不放宽、不改判据口径。

交付里落地的是不需要裁定就成立的那部分：交集不再是无人过问的判据——
`test_def_name_sets_are_equal_or_every_drop_is_accounted` 要求 `genOnly` 恒空、`draftOnly` 逐个指得出
上面三条既有去处之一（读 `test_collection_contract` 里同一批判据源，没有第二张名单）；
`test_probe_parametrization_covers_every_pair` 判的是另一件事：探针列表必须等于两侧名字集的交集，
且 `@pytest.mark.parametrize` 吃下去的必须是这一串——将来有人在 `_shape_pairs()` 里加筛选或把装饰器
换成另一张表，名字集门不会红（它只看两份 JSON），只有这条会红。

这里有一条我自己要先说出来的败笔：本卡第一版把这条写成 `test_every_generated_def_is_actually_probed`
（"产物里每个 def 都要在 `SHAPE_PAIRS` 里"）。独立复查指出它在名字集门成立的前提下**永不可能红**——
`_shape_pairs()` 按构造就是把交集全放进去，那句话与"genOnly 为空"是同一个谓词，它不判任何东西，
而它的 docstring 还写着"名字在两侧都出现但参数化列表没带上"那种情形，那情形在它身上不可达。
我复核后确认成立（①b 里它跟着名字集一起读绿就是佐证），删掉换成现在这条。

## 4. S56.4 两处文档纠真

- `docs/任务规划V0.21.0/02-需求复核与辩证分析.md:29`：`24 条` → `22 条`。现读依据是
  `test_shapes_response_contract.py:107` 钉死的 `len(routes) == 22`（前端 mock 表 22 条 pattern）。
  该文件里其它"24 条"是对历史时点的引文，没动。
- `docs/06_validation/evidence/EVD-V21-47/ERRATA.md` 新增，`EVD-V21-47` 的归档原文一字未回改
  （`git status` 里该目录只有一个 `??` 新增项，`git diff --stat` 为空）。行号结论写成能复算的三条：
  `git log --all --format=%h -- apps/api/tests/test_shapes_response_contract.py` = **1 个提交**（`f4f0261`
  即 STEP-47 交付批本身）；`git log --format=%h f4f0261..HEAD -- 同一路径` = **空**；
  `git show f4f0261:…` 的第 43 行是空行、第 50 行才是那条 `assert`
  ⇒ 该文件从头到尾只有一个已提交版本，而那个版本里 `:43` 就不是断言行，归档的 `:43` 从未对应过已提交字节。
  **这里有一条我自己的写错又改掉的**：本段前一个版本写着"`git log -L` 在这台机器上返回空、不成立"——
  复跑 `git log -L 44,50:apps/api/tests/test_shapes_response_contract.py` 实际返回 `f4f0261` 加一段 diff，
  命令是能用的，那句是我的错。同时前一个版本只写"`git diff --stat f4f0261 HEAD` 为空 ⇒ 一字未动"，
  那证的是"后来没改过"，证不到"那个行号从来没对过"；现在换成上面那三条读数。
  另外那一版还说"把产物字节上的空格邻接实测补进 ERRATA"——实测确实做了（四个 def 名各 1 处，
  行号 8/21/26/28），但它落在本文件 §3 而不是 ERRATA 里，所以不把那份工作写成这一条的功劳。

## 5. 卡面判据逐条

| 判据 | 结论 | 依据 |
|---|---|---|
| ① 先红：加孤儿 def ⇒ 新守卫红、旧门全绿 | **部分成立并已如实记**：字面形（①a）旧比对器也红；隔离形（①b）才做到"只有新守卫红"，且我把 ①a 的读数一并归档 | §2 表前两行 |
| ② 删两条引擎反向核 ⇒ 新守卫红 | 成立 | `s56_2_engine_live_deleted_newguard_red.txt` |
| ③ 名字集真不等 ⇒ 不放宽、登记 P 号交回 | 成立，登记 **P-127**；已交回，待规划方裁定走哪条路 | §3 |
| ④ 全量 + 三绿 | 本机门链与 `@ci` 读数见 §6 | §6 |
| 字段 6 允许面 | 三个测试文件 + 一个新文件 + S56.4 两处文档。**两处超出字段 6 的文字、都按卡面其它要求做的**：证据包 `EVD-V21-56/`（字段 5① 要求"原文入证"），以及账本 `docs/任务规划V0.12.0/00-README.md` 追加一行 P-127（判据③要求"登记 P 号交回"，而登记的地方就是那张表）⇒ 这两处请规划方在裁定时一并确认口径 | `git status` |
| 字段 7 禁止面 | `apps/api/app/**`、`packages/contracts/**`、`scripts/gen_contracts.py` 零改动；冻结稿 `docs/任务规划V0.12.0/**` 也被①b 动过并已逐字还原 | §2 还原列 |
| 字段 10 `SKIP_BASELINE_WIN` | 新守卫与新增的 jsonschema 用例都不连库 ⇒ 基线不动 | §6 skip 读数 |

## 6. 本机门链

**最终跑 `s56_local_gates_final.txt`（10:01:20–10:24:27，15 步 rc 全 0）**

```
rc_pgpreflight=0 rc_ruff=0 rc_mypy=0 rc_alembic=0 rc_heads=0 rc_gen=0 rc_docs=0
rc_pytest=0 rc_cov=0 rc_fe_tsc=0 rc_pkg_tsc=0 rc_vitest=0 rc_lint=0 rc_build=0 rc_e2e=0
```

| 读数 | 值 |
|---|---|
| pytest 全量 | **2488 passed / 6 skipped / 4 deselected**（1171.60s） |
| 增量对账 | 基线 2471 + 17 = 2488；17 = 新守卫 11 + `test_contract_jsonschema` 5（名字集门 1 + 探针列表门 1 + 反证 3）+ 引擎侧反证 1 ⇒ 逐条数得回来，不是"多了些用例" |
| skip | 6 = `SKIP_BASELINE` 6；新增 17 条全不连库 ⇒ CI 侧 6 与 `SKIP_BASELINE_WIN`(692) 都不动 |
| 模块覆盖率门 | 按附录 A 原样、仓库根、不设 `PYTHONIOENCODING`：8 个模块逐个达标（`kb.py` 88.18% ≥85%、`article_identity.py` 100% ≥100% 等），**TOTAL 88.91% ≥ 79.0%**，✅ 全部模块与全局达标 |
| 前端 | `pnpm typecheck` 0、contracts tsc（CI 形制 `ci.yml:382`）0、vitest **53 文件 425 passed**、`pnpm lint` 0 |
| 演示态 | `next build` 0、mock e2e **31 passed**（1.6m） |
| 契约与库面 | `gen_contracts --check` 0、`alembic upgrade head` 0、alembic 单头 0、`check_docs_consistency` 0 |
| 起链前置 | PG@5547 应用层核实：`alembic_version=ab1006c2a tables=25 jobs=0 first_connect=0.162s steady=0.001s` |

**作废的五次都记着（run1–run5），日志的 rc 行与停止位置抄在 `s56_local_gates_void_runs.txt`**（整份 30KB×4 的日志不入库，
但每一次作废的理由都是要留的，因为它们各暴露一种我本来会重复犯的错）：

- **run1 `gates1.txt`**：pytest 46% 时我增补了 S56.2 的反证用例 ⇒ 读数不再对应交付字节。停它的过程里
  暴露链自己的两个缺陷：单实例锁按命令行里的脚本名计数，把"启动它的那个 bash 包装"当成第二个实例，
  于是包装自己走 ABORT，而 ABORT 分支用 `> "$OUT"` **把正在跑的那条链的日志截掉了**（自锁反过来破坏
  证据文件）；以及日志里印的 `pid=` 是 MSYS 号，Windows 侧要按命令行找进程。改用 PID 锁。
  这一次它剩下的步骤同样跑完并打出 rc=0 与 DONE 行（覆盖率门读的是被截断的 `coverage.json`），
  和 run2 是同一种看起来全绿。
- **run2 `gates_final.txt`**：pytest 75% 时我又改了 `test_contract_jsonschema.py` 的模块 docstring。
  它的 `rc_pytest=1` 是被我停的痕迹而**不是测试红**，而其余步骤反而跑完并打出 rc=0——一份"看起来全绿"
  的日志里混着一个被杀的步骤，正是要把作废的跑也归档的理由。
- **run3 `gates_final3.txt`**：这次是我的流程错了——它还在跑的时候我去跑了先红探针，而探针会改
  `shapes.py`、`packages/contracts/**` 与冻结稿 ⇒ 它的 `gen --check` 与 pytest 跑在被临时改过的字节上。
- **run4 / run5 `gates_final4.txt`、`gates_final5.txt`**：run3 停不干净之后我误以为只剩一条，实际起了
  第二条 ⇒ **两条链在同一棵树上并发**，都写 `apps/api/coverage.json`、各自 `rm -rf .next` 后重跑
  build 与 e2e。它们报出的数字彼此一致（2488/6/4、TOTAL 88.89% 与 88.91%），但"两条并发的链数字一样"
  不是证据，只是同一份污染被看了两遍。
- 此后的规则很朴素：**链在跑就不碰工作树，探针与链严格串行，一次只起一条**；另外
  `taskkill //T //F` 报成功之后 venv 里那条 pytest 可能仍然活着（父进程已换），必须按命令行复查
  `python.exe` 计数归零才算停干净。
- 还有一条与链无关但同一类：**备份文件会撒谎**。第一次探针备份取在 S56.2 增补之前，`restore` 于是把
  我后来加的反证用例一起"还原"掉，而它照样打印 `sha_all_equal=True`——它比的是备份自己的 sha，
  不是我意图中的交付字节。按最终字节重取备份后四条探针全部重跑，§2 的数字与 `s56_1a_* / s56_1b_* /
  s56_2_* / s56_3_*` 都出自重跑那一次。

## 7. 独立复查（子智能体，只读）与逐条处置

第一轮复查给出：S56.1 PASS-with-nits、S56.2 PASS-with-nits、S56.3 **FAIL of the card's letter**、
S56.4 PASS、范围纪律 PASS-with-nits。它独立复算了我的正面读数（19/2 种子、30/4 def、判据空），
所以绿不是空转。逐条我自己复核后的处置：

| # | nit | 复核结论 | 处置 |
|---|---|---|---|
| 1 | `_ref_names` 递归进 `x-*`，注释里塞一条 `$ref` 就能买到"可达"；同仓 `_referenced_by` 早已为 G3 收紧 | 成立。现读两份产物里 `x-*` 子树内 `$ref` 为 0 处 ⇒ 是未来静默面而非现存缺陷 | 第一版处置：加 `_SHAPE_KEYS` 白名单 + 跳过 `x-*`/散文键，并补一条两边都测的反证。**这个处置本身又被第 2 轮第 13 条打掉**（白名单是装饰性的），现在的规则只剩"注释键与数据键不下钻" |
| 2 | shapes 侧不要求所在用例真打到端点，合成 `_check("Foo", {...})` 可买到覆盖 | 成立。但 19 条种子里有 2 条来自**不连库**的真端点用例（`test_shapes_response_contract.py:307`、`:326`），所以"必须有 `db_session`"这条在 shapes 侧不可用 | 收掉一半：种子抽取要求第二个实参不是容器字面量（§1-4），合成对象从此记不上覆盖面；"这条核真跑过"仍然不判——那是静态判据的定义，见 nit 5 |
| 3 | 引擎规则只看 `fn.args.args`；将来换 keyword-only 夹具就看不见；另外带 `db_session` 却只用 validator 判拒绝的用例也算覆盖 | 前半成立、后果是 fail-closed（种子变空 ⇒ 整域红）；后半是个真宽放行 | 参数扫描扩到 `posonlyargs`/`kwonlyargs`；并把"引用常量"收紧成"把常量交给 `_errors(…, data)` 判一份 data"——反证 `test_teeth_keeping_the_reference_is_not_coverage` 打这一刀（换掉实参名 ⇒ 种子立刻掉，且另一条真端点用例不受牵连）。残留：仍然不判"这条核跑过没有"（静态判据的定义，见 nit 5） |
| 4 | 两套取名口径并存：`_REF_TARGET` 只认 `#/$defs/` 且被 `\w` 截断，`_ref_names` 用 `rsplit` | 成立，正是"第二个真源迟早漂"的形状 | 引擎侧改成走 AST 找 Dict 的 `"$ref"` 键、与 `_ref_names` 共用 `_ref_target`；正则与 `import re` 删掉。连带把②那条反证的变异形制换成 `"$ref"`→`"$rot"`（原来那种换法在新口径下不再打断绑定） |
| 5 | 静态判据在 `@win` 上连库用例全 skip 时仍读绿 | 成立，且是卡面字段 10"新守卫不连库则不动 skip 基线"要求的直接后果——连库版本必然要在 `@win` 抬基线 | 留在 §1 明写，不伪装成运行期判据 |
| 6 | `test_every_generated_def_is_actually_probed` 永不可能红 | **成立，这是我这条卡里最该怕的一种错**：它把"名字集门"的谓词抄了一遍换了个名字。①b 里它跟着名字集读绿就是佐证 | 删掉，换成判"探针列表 = 交集"且"装饰器吃的是同一串"的 `test_probe_parametrization_covers_every_pair`（名字集门只看两份 JSON，永远不看列表怎么构造出来，所以这条不重复）；§3 里把这次败笔写进证据而不是抹掉 |
| 7 | S56.2 的 docstring 里"作为别的 def 的字段类型出现也能凑出空格"不成立（产物里那些形制是 `EngineReason;`、`Array<EngineCapability>`） | 成立，实测每个名两侧带空白的出现位各只有 1 处，就是它自己的导出行 | 删掉那句，理由改成常驻反证 `test_ts_dto_criterion_is_export_scoped` 机器判；顺带把"新判据仍放行被注释掉的 export"这个残留也写明（shapes 侧同形判据一样） |
| 8 | S56.3 交付的是卡面判据③不允许的容纳；且 P-127 还没登记、登记它的账本不在字段 6 里 | 成立 | 按判据③登记 P-127 并交回（收口批），字段 6 与字段 5 的冲突在 §5 与卡面上明写；不修改判据口径 |
| 9 | ①b 探针写过冻结稿，而冻结稿不在禁止面里 ⇒ 出口①可以被执行侧自己盖章 | 成立，这是个真口子：`docs/任务规划V0.12.0/contracts/**` 没在字段 7 的禁止清单上 | 本卡只做探针并已逐字还原；把"①这条出路应当由谁盖章"作为 P-127 裁定的一部分交回规划方 |
| 10 | `git status --porcelain` 不含 `-u` 时没列出 `EVD-V21-56/`，路径式提交可能静默漏掉证据 | **不成立**：`git status --porcelain -- <该目录>` 输出 `?? …/EVD-V21-56/`，`git check-ignore` rc=1（没被忽略）——我前面几次是把输出 `head -10` 截了才没看见。提交时按显式路径列出该目录 22 个文件核实 | 记这条为"复查的读数也要复算"，不照单接受 |
| 11 | 从仓库根跑 `ruff check --config apps/api/pyproject.toml` 会对 `test_contract_jsonschema.py:33` 报 I001 | 成立但只在"改从根目录调用"时成立；CI 与本仓门链都按 `scripts/entry.py` 从 `apps/api` 调 | 不动 |

### 第 2 轮（针对第 1 轮改动之后）

第 2 轮复查复核了六处增量，判 5 处 PASS、1 处 PASS-with-nits，并给出一条真缺口：

| # | 读数 | 处置 |
|---|---|---|
| 12 | **P-127 还没登记**，而我写的 `s56_readings.md` §3/§5 已经写"已登记"——那是对不存在的事实做陈述 | 当场把 P-127 行追加进账本 `docs/任务规划V0.12.0/00-README.md`（追加前查末行锚点、管道数 6、行内无换行、全文件无同号行；写完复算行数 214→215 且新行 6 管道）。账本不在卡面字段 6 的允许面里，这处冲突在 §5 与卡面上明写 |
| 13 | `_SHAPE_KEYS` 是**装饰性**的：`isinstance(value, dict \| list)` 兜底会下钻任何 dict/list，那个键集从不参与判定 | 删掉键集，只留"注释键 + 数据键不下钻"这一条真实规则（`_DATA_KEYS`），并把"为什么不用只放形状键的白名单"写进注释：将来产物换容器键时白名单会漏真引用、把有人核的 def 读成孤儿，那种假红比多下钻一层更难查。第 1 轮的 §1-2 措辞跟着改 |
| 14 | `_engine_seeds` 只认模块级 `Assign`，写成 `AnnAssign` 或 f-string 就静默取不到引擎种子 | 后果是 `test_both_domains_contribute_seeds` 当场红（fail-loud），不是假绿 ⇒ 记 §7 不改 |
| 15 | `test_probe_parametrization_covers_every_pair` 里的 `<root>` 断言与 `_shape_pairs()` 的判断式逐字同形 ⇒ 两处一起改就看不出 | 删掉那半条，留下确实不重复的两半（列表==交集、装饰器吃的是同一串）。"今天按构造成立"这句留在 docstring 里 |
| 16 | 增量本身正面读数复算通过：19/2 种子、34 个 def、`_live_report()==[]`、22 处 `_check` 无一被新规则误丢、`LogoutResult` 锚点全文件唯一、产物里 `"$ref"` 恰 2 处、ruff 与行长合规 | 作为独立复算记录归档，`s56_readings_raw.txt` 就是这轮的读数 |

顺带一条我自己撞出来的：第 13 条改动把"认 `_errors(<validator>, data)` 调用点"写进引擎种子抽取时，
第一版判据写成 `expr.func != ast.Name(id="_errors")`——ast 节点比较是身份比较，永真 ⇒ 引擎种子恒空，
正面用例当场红（红得对，但原因不是判据发现问题而是我的调用形错了）。这条与 §2 探针②的第三条红
同源：那一红是反证自己的锚点随用例被删而消失，属于设计内的自锁生效，不是判据另有问题。

## 8. @ci 三绿读数与判据③的裁定到手（收口批补记）

- 交付头 `3b462d4` 三条 attempt 1 全 success：CI 40439001496 / CI-Windows 40439001492 / Security 40439001387。
  逐字行归档在 `s56_ci_green_readings.txt`（run 级 logs zip 现取）。关键读数：ubuntu 侧
  `2488 passed, 6 skipped, 4 deselected`、skip 门禁 `total_skipped=6 baseline=6 pg_unreachable=0`、
  `Total coverage: 88.91%`、`✅ 全部模块与全局达标`、vitest `53 passed (53)` 与 `425 passed (425)`、
  演示态 e2e `31 passed`；@win 侧 `1802 passed, 692 skipped, 4 deselected`、门禁
  `failed=0 total_skipped=692 baseline=692`、vitest 同 53/425。本机 §6 最终跑的 2488/6/4 与 88.91%
  和 @ci 逐字同数 ⇒ 两个 skip 基线都不动（新守卫 11 条用例全不连库）。
- **判据③的裁定（D-V21-20）2026-10-27 到手**：按「等价满足」通过——不改冻结稿、不给别名补使用处；
  有效口径就是交付批已经落地的三条（`genOnly` 恒空即红 + `draftOnly` 逐个指得出三条既有去处 +
  探针列表与装饰器吃同一串），规划方明确「不需要再加强度」⇒ **收口批没有再动任何测试文件**。
  盖章权归规划方：`docs/任务规划V0.12.0/contracts/**` 只有规划方能落笔，先红探针可临时改但必须在
  同一条命令内还原并核实 sha——本卡交付批的 ①b 探针正是这个形状（还原 sha 见 `s56_1b_*`），
  这条口径同时写进 04 附录 A 第九节第 9 条。
- 收口批范围（零代码改动）：卡面两处——状态行 ⬜→✅ 与第 5 格判据③末尾代录一句；卡表第 10 行；
  04 附录 A 第九节第 9 条；P 表两行（P-126 闭合、P-127 裁定代录）；07 第 11 行；证据侧三件
  （本段、`s56_ci_green_readings.txt`、`s56_closeout_verdict.md`）加交付批漏跟踪的
  `s56_push_credential_note.txt`。`apps/api/**`、`packages/contracts/**`、`scripts/**`、`apps/web/**`
  与四个测试文件在收口批里一字未动。
- **判词原本写在卡面末尾，被第 3 轮复查判为越出规划方本轮对卡面的授权**（STEP-19/53/54/55 的卡面
  都只有状态行与勾选，判词的先例落点是证据与 07），所以整段移到 `s56_closeout_verdict.md`，
  卡面回到 16 行、`git diff --numstat` 对该文件现读 **2/2**（只有状态行与第 5 格两行）。
  复查另有三条 nit 已就地改掉：本段旧版的 readings 自计件数（写完即变，改为本段自身不计）、
  07 第 11 行证据列把收口批新增写成 1 件（实为 3 件）、P-126 闭合行「四组探针」漏写 `s56_3_*`。
- 还原列（收口批提交前现核，本段自身不计件数——它随下一次编辑变）：`git diff --numstat` 命中
  五处文档（readings、P 表 +2、04 +2/−1、07 +1、卡面 2/2）；`git status --porcelain -- apps packages scripts`
  **零命中**，未跟踪只有本目录三件。⇒ 收口批确为零代码改动。
- 仍交回规划方两件（D-V21-20 未覆盖）：① `docs/03_solution/decisions/decision-log.md` 里 D-V21-20
  那一行**尚未落档**（该文件不在本卡允许面内，P 表只是代录内容）；② 「证据包目录与 P 表这两处写在
  卡面字段 6 之外的动作」的口径确认。
