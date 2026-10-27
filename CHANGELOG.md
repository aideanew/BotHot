# Changelog

本项目所有值得记录的变化都写在此文件。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> **收录口径（重要）**：本文件**只收录已实现的事实**（含明确的"部分实现"限定语），
> 不写入计划中/在途功能。每条目末尾标注来源提交短 hash（`git log` 可对）。

## [Unreleased]

_（空。v1.1.4 于 2026-10-27 发布：`[Unreleased]` 在发布前本就是空的，v1.1.4 段的条目
按 `git log v1.1.3..HEAD` 区间重新对账写入，来源短 hash 逐个 `git log -1` 复核主语——
这条口径是 v1.1.0 那次失真教训留下来的，见 `docs/06_validation/evidence/EVD-V17-12/s12_readings.md` §5.1。
发布说明自己也要吃同一条纪律的两回：v1.1.3 那次是"对外可见变化只有一处"被自己那段推翻，
v1.1.4 这次是被引用的**行号**会漂（`test_shapes_response_contract.py` 里钉 22 条那句从 `:107` 漂到 `:114`）
与被引用的**支撑**会失真（`EVD-V21-47/ERRATA.md` 那句"只有一个提交"现读两个）——
所以本版发布段一律只点名不点行号，失真处当场标注，不装作还能复算。）_


## [v1.1.4] - 2026-10-27

> 补丁+质量版（契约覆盖面补一道守卫 + `/auth/me` 对外形状收紧）。区间 `v1.1.3..HEAD` 共 7 个提交
> （发布批自身 +1 ⇒ tag 指向的提交上是 8），其中主语带 `feat` 的 2 个（`3b462d4`、`685e3f8`），
> 其余五个都是 `docs(...)` 前缀（V0.21.0 规划增量与各步交回/收口文档批）。
> **本版零数据库迁移、零新增对外 HTTP 端点**；对外可见的变化只有一处，且是收紧——
> `GET /auth/me` 的 `data.wallet` 不再把主平台钱包对象里我们没声明的键转出去（下面 Changed 第一条，
> 含它的限定）。这句的范围是按文件核出来的：区间内不属于 `docs/**` 与 `apps/api/tests/**` 的改动
> **只有 `apps/api/app/services/auth/service.py` 一个文件**，没有迁移、没有路由、没有 `packages/contracts/**`、
> 没有 `apps/web/**`。
> S58.1 对 STEP-56、STEP-57 的独立复查两份回报各自独立、结论一致：**STEP-56 PASS-with-nits、
> STEP-57 PASS-with-nits**，无 FAIL 也无 UNKNOWN ⇒ 判据①满足、不触发阻塞条件；逐条依据与留下的 nits 见
> `docs/06_validation/evidence/EVD-V21-58/s58_1_independent_review.md`，发布批三绿 run id 与 tag/Release
> 读数见同目录 `s58_readings.md`。
> 测试基线（三绿 head `685e3f8`；收口批 `260a3a4` 与发布批都是零代码的文档批，计数三处（2496 / 6 skipped / 4 deselected）在收口批自己的 CI run 上也逐字相同，只有覆盖率在摆）：
> CI `2496 passed / 6 skipped / 4 deselected`、`Total coverage: 88.89%`、模块覆盖率门
> `✅ 全部模块与全局达标`、前端 `53 文件 / 425 passed`、演示态 e2e `31 passed`、CI-Windows
> `1810 passed / 692 skipped` 且门禁 `failed=0 total_skipped=692 baseline=692`；本机按 CI 顺序复跑
> 同数、覆盖率读 88.91%。**覆盖率那个数不可当精确判据**：已归档的读数落在
> 88.89（交付头 `685e3f8` 的 CI）/ 88.90（STEP-56 收口批 `52673f2` 的 CI，另见于 STEP-56 本机作废跑）
> / 88.91（STEP-56 交付头 `3b462d4` 的 CI 与本机两次交付跑）/ 88.92（STEP-57 收口批 `260a3a4` 的 CI，
> 另见于本机被取代的第 3 跑）/ 88.94（STEP-56 本机作废跑）；88.94 那一次与 88.92 的第二个出处
> 来自作废或被取代的跑、不是交付读数；AGENTS.md 测试段还记着更早一次同树三跑抖出 88.01/87.95/88.00。
> 所以它能过线、不能被当逐位对齐的判据。

### Added

- **契约 def 覆盖面孤儿守卫（闭合 P-126）**：新 `apps/api/tests/test_contract_def_coverage.py` 从两个反向核
  测试模块**现读**种子——shapes 域取 `_check(<名>, <响应值>)` 的调用点（第二实参是字面量字典/列表/集合/元组
  的不算，那是拿合成对象买"覆盖"），引擎域取带 `db_session` 形参的用例里 `_errors(<常量>, data)` 所用常量的
  模块级绑定，两边都不抄名字表；再沿 `$ref` 求可达闭包，判 `全部 def − 可达集 == ∅`，红时点名孤儿。
  同一条清单还判指向本域不存在 def 的坏边、跨域 `$ref`、以及写错的种子名，坏边扫每一个 def 而不是只扫可达集
  （第一版只扫可达集，一条悬空引用的反证就读成了绿）。`$ref` 不走 `x-*` 与数据键（往注释键里塞一条引用
  买不到"有人核过它"的通行证）。现读：种子 19 + 2 = 21、def 30 + 4 = 34、孤儿 0 ——**孤儿 0 与 P-126
  登记行的现测一致，21/34 这两个数是本卡自己现读的**；这条补的是会漏未来漂移的覆盖面，不是现存缺陷。
  来源 `3b462d4`（STEP-56）
- **`GET /auth/me` 的钱包按白名单五键投影（P-121 的泄露面断掉）**：`apps/api/app/services/auth/service.py`
  新增纯函数 `_project_wallet`，只吐 `balanceYuan`/`currency`/`heldYuan`/`availableYuan`/`available`；
  上游没给的可选键**保持缺席、不补 0**（补 0 等于把"平台没告诉我"写成"余额是 0"，前端对这两件事是两种文案）；
  必填键缺失或为 `null`、或整块不是字典 ⇒ 回既有降级形 `{balanceYuan:0, currency:"CNY", available:false}`
  且**不抛 500**；上游多出的键名以 debug 每次记一次、值一律不落日志。`/me` 的三条分支（正常 / 主平台不可达 /
  QA fixture）的降级形现在同源，且每次返回新副本。常驻 8 条用例钉住（1 条走完整登录链的集成 + 7 条纯函数），
  先红跑了两次：未改代码一次、最终字节上把投影那一次调用摘掉再跑整文件一次（`1 failed, 7 passed`，
  还原后按 sha 核实四件全等、整文件 `8 passed`）。来源 `685e3f8`（STEP-57）

### Changed

- **契约链上两处判据由弱变强**（同一批，来源 `3b462d4`；一处管 TS 产物的导出位、一处管冻结稿与生成 schema
  的名字集，都不直接看 HTTP 响应）：
  ① 引擎产物判据从"契约名两侧各有一个空白就算它在"的子串换成钉导出位本身（`export interface`/`export type`
  加同名）的正则，并配一条常驻反证——把导出行换成一行提到它的散文注释后，旧子串判据对那四个引擎 def 名
  全部放行、新正则红；
  ② `test_contract_jsonschema.py` 原来**只有**"逐对探针比对"，而那一对对列表是按两侧名字集的交构造的
  ⇒ 任一侧独有一个 def 时整条静默跳过；现在补两道：`genOnly`（产物有、稿里没有）出现即红，
  `draftOnly` 每个都必须指得出三条既有去处之一（稿根层声明它不是形状 / 被已收编 def 在形状位引用走 /
  别名见证测试点名），另加一条独立判据"探针列表 == 两侧名字集的交 且 装饰器吃的是同一串"——名字集那道门
  只看两份 JSON，永远不看列表是怎么构造出来的。
- **本版那处对外可见的收紧就是上面 Added 的钱包投影**：以前上游加什么字段我们就转什么，现在只转五个键。
  **限定必须一起读**：契约里 `MeWallet` 仍是全 30 个 def 中唯一一个开放对象（`additionalProperties: true`），
  所以演示态样例多写一个键、或前端 TS 类型那一层，都不会红——把它改封闭要与冻结稿
  `docs/任务规划V0.12.0/contracts/shapes.schema.json` 那两行声明同步，而冻结稿只有规划方能落笔
  （**裁决 D-V21-20 的正文尚未落档**：`docs/03_solution/decisions/decision-log.md` 现读止于 D-V21-19，
  该裁定的内容目前只以台账 P-127 裁定行的"代录"形式与 04 附录 A 第九节第 9 条存在）。
  规划方因此裁定本卡只发投影那一半（台账 P-129 出路③），封闭那一半转入后续卡。
  另两处已登记的残留：可选键被上游**显式**发成 `null` 时按"给了值"原样带出；主平台把 wallet 信封的 `data`
  发成列表时 `/auth/me` 仍会 500（非本版引入，已登 P-128）。

### Fixed

- **两处文档与已发布事实不符**（来源 `3b462d4`，STEP-56 S56.4）：
  `docs/任务规划V0.21.0/02-需求复核与辩证分析.md:29` 的"前端 24 条 mock 样例"改 22
  （判据是 `apps/api/tests/test_shapes_response_contract.py` 的
  `test_mock_route_table_matches_the_frontend_one_to_one` 里那句条数断言——刻意不写行号，理由见下一条）；
  `EVD-V21-47` 那条先红读数把红钉在 `:43` 而交付字节的 assert 在 `:50`——按纪律**不回改已归档原文**，
  在该目录新增 `ERRATA.md` 注明行号漂移与原因。
  **本段自己也要吃这条纪律**：`ERRATA.md` 里"该文件自 `f4f0261` 之后一字未动 / `git log --all` 只有 1 个提交"
  那两条支撑在 `3b462d4` 时可复算，但本版 `685e3f8` 改了那个测试文件的 docstring ⇒ 现读是 2 个提交；
  行号论证的**结论不受影响**（`f4f0261` 那一版里 `:43` 仍是空行、`:50` 才是 assert）。
  同一文件里"断言在哪一行"也会因 docstring 增删而漂移（`:107` → 现读 `:114`），这就是为什么上面只点名不点行号，
  也是 `ERRATA.md` 里补一条带日期订正的原因。

## [v1.1.3] - 2026-10-26

> 补丁+质量版（契约链收尾）。区间 `v1.1.2..HEAD` 共 28 个提交（发布批自身 +1 ⇒ tag 指向的提交上是 29），
> 用户可感变化如下；其余为 V0.21.0 规划与各步收口/文档批。**本版零数据库迁移、零新增对外 HTTP 端点、
> 真实端点的响应形状零改动**——本版把"形状"这件事从人眼核对变成了机器判据，改的是演示态（mock）数据面
> 与前端一处行为（空间详情 404 空态在真实后端下开始生效，见 Fixed 第一条），以及门禁本身。
> S53.1 对 STEP-46/47 的独立复查结论两项均 PASS（无 FAIL、无 UNKNOWN），逐条依据与留下的 nits 见
> `docs/06_validation/evidence/EVD-V21-53/s53_1_independent_review.md`；发布批三绿 run id 与 tag/Release 读数见
> 同目录 `s53_readings.md`。测试基线：CI `2471 passed / 6 skipped / 4 deselected`、`Total coverage 88.9%`、
> 模块覆盖率门全达标、mock e2e `31 passed`、CI-Windows `failed=0 total_skipped=692=基线`、
> 前端 `53 文件 / 425 passed`（三处逐字同数）。**覆盖率那个数不可当精确判据**：本区间多次读数（不同提交、
> 本机与两侧 CI）落在 88.90–88.99，跨度 0.09 个百分点；同树复算本身也会抖
> （AGENTS.md 测试段记着 88.01/87.95/88.00 那一次），所以它能过线、不能被当逐位对齐的判据。

### Added

- **响应形状进入契约生成链**：`apps/api/app/contracts/{engine,shapes}.py` 成为唯一源，经
  `scripts/gen_contracts.py` 生成 `packages/contracts/schemas/*.schema.json` 与
  `packages/contracts/src/**/dto.ts`——engine 域现在 4 个 def（**本版新增其中 2 个**：
  `EngineList`/`SpaceEngineBinding`，另两个在 v1.1.2 之前就有）、shapes 域 30 个 def；
  产物有字节幂等漂移门钉着。响应侧的反向核共 9 处：**7 处打真实端点**（连库，覆盖 spaces / docs /
  batch / public library / ingest / notifications / me 降级支），**2 处只能打桩端点**
  （`resolve`+`extract` 与 `me`+`logout` 的正常支，因为那两个端点依赖上游客户端替身）；
  该文件合计 17 条用例。来源 `9816f7f`（STEP-46，引擎域 2 条路由）、`f4f0261`（STEP-47，其余 20 条路由）
- **演示态其余 20 条 mock 路由的样例补上 `satisfies` 契约类型**（引擎那 2 条由 STEP-48 先接，合计 22 条全覆盖），
  并新增对照表 `apps/web/lib/api/mock-contract-map.ts`（逐字镜像后端 `MOCK_ROUTE_CONTRACTS`）
  与三道机器红：漏登记即红、表里有死条目即红、与后端权威源逐条不同名即红。
  来源 `0aa2923`（STEP-52，闭合 P-122/P-82）、`be23d41`（STEP-48 的引擎 2 条）
- **运行时形状门**：逐条走真实分发器取实际响应，再用从生成好的 schema JSON 现读的形状递归核对
  （含 `required`/多键/`$ref`/`anyOf`/`enum`/数组元素/空数组记账，以及契约声明的
  取值范围 `minimum`/`maximum`/`minLength`/`maxLength`）；装载期还会对整棵 def 树硬抛七类
  "会让某条判据静默失效"的写法。它补的洞要说准确：**不是"摘掉 `satisfies` 这件事本身会红"**——
  样例若仍与契约同形，摘掉那句静态标注没有任何门会响（那是类型层的弱化，不是形状漂移）；
  红的是"**摘掉之后这条样例再走形**"，而那正是旧局面的死角：`satisfies` 一被摘，
  这条样例此后与契约不同形也不会有任何机器红（覆盖面门与 `tsc` 都看不见，实测 rc=0/rc=0）。
  现在同不同形由运行时判，与那句 `satisfies` 在不在无关。
  来源 `4a2c62b`（STEP-55 S55.1，闭合 P-124；反证 A 行的原文读数在 `EVD-V21-55/s55_probe_readings.md`）
- **引擎域的前端类型与样例接上契约生成类型**（`EngineItem = EngineCapability`、样例逐条 `satisfies`、
  两个 handler `satisfies`、运行时键集合守卫）。来源 `be23d41`（STEP-48，P-119/D-V21-02）
- **技术栈版本声明 ↔ 实值一致性门**：AGENTS.md 与需求基线里带键值引用的行（现测 4 行）与
  `apps/web/package.json`/`apps/api/pyproject.toml` 的实值逐条对账，引用形制不对、值与实值不符、
  或引用了历史版本值都会红；`requires-python` 刻意不比对（它声明的是兼容下界而非当前实值），
  且比对器自己带自测负例。
  **口径说清楚**：语料只有 `AGENTS.md` + `docs/02_requirements/**`，`docs/04_engineering/conventions.md`
  **不在**它读的范围内——那一处对齐仍靠人（这是本条已知未覆盖面，非本版新引入）。
  来源 `a8c3df9`（STEP-50）
- **SQL 参数化面 AST 门 + `SameSite=Lax` 断言**：AST 扫 `app/**` 里进 SQL 的字符串形，逐调用点判拼接
  （登记时 12 处，读数归档 `docs/06_validation/evidence/EVD-V21-49/s49_2_callsites.txt`），
  允许表恰一条且有用例钉住它不许扩大，另有三份额外形状的负例（f-string 带运行期值、拼接/format、
  同一常量形出现在表外文件）；会话 Cookie 的 `SameSite` 由先红 strict 钉住。来源 `8644bea`（STEP-49）
- **全站性能基线首版**：`perf_baseline.py` 测量 harness + 往返计数用例 + `PERF-baseline-v1.md`，
  四条 SLA 首测全达标、可感性四条各自证明（注入 25ms 对照），复跑 p50 偏差 ≤13%。
  来源 `4dc37ec`（STEP-18，P-118 以自备 PG16@5547 解除）、`88d7518`

### Fixed

- **空间详情页的"404 语义空态"在真实后端下从未生效**：入口判断只认 30101/10102，而线上未命中/越权的码是
  30004（后端全仓不产 30101）——演示态 mock 恰好抛 30101 把这个缺陷盖住了。现在条件式并入 30004，
  并把注释与僵尸文案的口径纠真（文案保留，删除另排卡）。来源 `0aa2923`（STEP-52 越界申报一行）、
  `4a2c62b`（STEP-55 S55.3，P-123）
- **演示态与线上形状的七处漂移逐条修**：`/auth/me` 回线上嵌套形、`logout` 回回执对象、
  两条列表补整页三键并**回显请求值**（缺省页宽取后端的 50）、`POST /spaces` 补 `engine`/`engineKbId`/`isPublic`、
  `DELETE /spaces/{id}` 补 `engineResidue`、详情未命中改抛线上码 30004、`types.ts` 15 个手写 interface 改契约别名。
  来源 `0aa2923`（P-122）
- **测试库连跑不再随机红**：调度器每日入队用例改为"进门先清 + 出门必清"（新增同步清场函数，
  先删两类每日 Job 的明细行、再删 Job、最后删用例自己的用户行；清场整段移进 `finally`，
  断言红或入队中途红都会执行）。此前跨会话残留会让下一跑撞唯一约束。
  来源 `4245847`（STEP-54，P-120）
- **模块覆盖率门在 Windows 上可以按附录 A 原样复算**：两个独立因都修在同一脚本里——① 阈值键与
  `coverage.json` 的键形不再逐字比（本机是 `app\services\kb.py` 反斜杠相对形，八条阈值键全部"命中 0 个"），
  现在两侧归一再要求"全等或以 `/`+键结尾"，且多命中会如实返回两个由调用方判 NOT-PASS；
  ② 达标末行的 `✅`（与判红末行的 `❌`）不在 cp936 里，所有模块都达标的那一跑也会在打印末行时抛
  `UnicodeEncodeError` 变成 rc=1——控制台语言不再能决定门的结果。
  来源 `4a2c62b`（STEP-55 S55.2，P-125）

### Changed

- **前端类型面以契约为准**：`Space` 的 `engine`/`engineKbId`/`isPublic` 与 `SpaceDoc.category`
  由可选转必填（契约就是这么声明的），测试夹具按允许面补默认值；`MeData` 作为归一化视图刻意不别名化。
  来源 `0aa2923`
- **门面文档纠真**：路线图的通知行与当前阶段、`REQ-NF-001` 的首测判词、端口表拆成"本栈发布 / 外部提供"、
  `REQ-F-004` 判已实现、`REQ-F-005` 判部分（组件层已证）。来源 `eae0356`（STEP-51，D-V21-05）

## [v1.1.2] - 2026-10-24

> 补丁+质量版。区间 `v1.1.1..HEAD` 共 26 个提交（发布批自身 +1 ⇒ tag 指向的提交上是 27），
> 用户可感变化如下；其余为 V0.20.0 规划与各步收口文档。本版零迁移、对外 HTTP 契约除
> 分页目标壳新键 `hasMore` 消费面外无变化。独立复查读数见 `EVD-V20-43/s43_review.md`
> 与 `EVD-V18-3x/` 各卡证据。

### Fixed

- **线上 JSON 异常日志恢复错误栈**：此前生产 JSON 日志里异常只剩 `"exc_info": true`，
  出错无从排查；现在渲染前先把异常展开成完整纯文本栈。来源 `17c3f13`（STEP-43，P-115）
- **异常栈不再打印栈帧局部变量**：开发机装了 rich 时，console 异常栈会把栈帧局部变量
  （可能含凭据形值）原样打进日志；现在 console 固定纯文本栈，有无 rich 行为一致。
  来源 `17c3f13`（STEP-43，P-114；独立复查 PASS 见 `EVD-V20-43/s43_review.md`）
- **RSS 清单回退重试不再重复排队**：RSS 的清单行与其镜像篇落在不同 source 上，
  ready 键减对它结构性失明——清单被合法回退成 DISCOVERED 后会把已入库的篇重新入列
  （先红实测：重开轮 enqueued=2）。现在 ready 减跨 source 按规范文章键减。
  来源 `2db2f99`（STEP-36 S36.1，P-97/D-V18-06①）
- **凌晨跑 CI 不再因覆盖率门随机红**：订阅锚点与调度器每日入队等墙钟分支改为冻结时钟
  确定覆盖。来源 `e01327c`（STEP-45，P-116）、`83a2606`/`891a897`（STEP-35）
- **404 的 message 固定为"资源不存在或无权限"**：不再把调用方塞进路径的 id 原样回显。
  来源 `31a3fb4`（STEP-37 S37.5，P-111①/D-V19-07）

### Added

- **外链过滤数跨轮可读**：RSS 发现层滤掉的外链数进 metrics（`bothot_discovery_rss_filtered_offsite_total`）。
  来源 `2db2f99`（STEP-36 S36.2，P-75）
- **源清单对 RSS 显示真实 feed 地址**；`GET /sources?type=` 拼错类型从"回空清单"改为
  422 并列出可用值。来源 `2db2f99`（STEP-36 S36.3，P-76）
- **按源降级开关能被运营打开**：`discovery_fallback_enabled` 进 Settings（默认仍关），
  删掉会把"配置项不存在"伪装成"选了关"的 getattr 兜底。来源 `2db2f99`（STEP-36 S36.4，P-70）
- **前端单测拨不出网**：未桩的 fetch 直接抛错、基址钉 3200（原 39 处静默拨 3000 归零）。
  来源 `83a2606`（STEP-35 S35.4，P-105/D-V18-08）

### Changed

- **门禁判据精度**：open( 判据锚到调用形、rounds 按最大轮号+持签逃生口、台账号左右边界、
  需求侧验收锚常驻门、掩码守卫 job 级+OUTPUT 通道；scripts/** 进 lint/type 门；
  ubuntu 加 make/entry 六任务对等步；faulthandler 转栈 100<杀值 120。
  来源 `2578c26`/`03c013d`/`33be5fd`/`6232a95`/`53b5197`（STEP-34，P-100/56/57/85/100/101/108/109/110）
- **分页壳收敛**：前端 `PagedResponse` 只剩 D-V3-02 目标壳（消费 `hasMore`）；
  引擎切换拒绝词与列表文案统一。来源 `31a3fb4`（STEP-37 S37.2/S37.3，P-90/P-96）


## [v1.1.1] - 2026-10-23

> 补丁版。区间 `v1.1.0..HEAD` 共 8 个提交，用户可见的行为变化两条（下 Fixed / Changed 各一），
> 其余为规划（V0.19.0）与各步收口文档。独立复查读数见 `docs/06_validation/evidence/EVD-V19-40/`
> （s40_review.md）与 `EVD-V19-42/`。本版零迁移、对外 HTTP 契约无变化。

### Fixed

- **安全修复：推送渠道凭据与采集令牌不再写进日志**。此前每推送一次（钉钉 / 企业微信 / 飞书）
  或用 JustOneAPI 采集一次，出站 URL 里的凭据就原样进一次应用日志；`HTTPStatusError` 的
  文本也自带完整 URL。现在在日志唯一出口（渲染完成后、落盘前）对整行文本遮蔽：
  出站 URL 的 query 与片段整段省略、绝对 URL 里令牌形的路径段遮蔽、主机名保留（排障要它）；
  审计日志的路径参数只保留 UUID 与不超过 15 位的短标识符，其余一律遮蔽。
  新增 15 条遮蔽用例；反证读数：摘掉遮蔽后恰好 8 条红（三家真推送 provider 与异常栈，
  console / json 各一遍）。来源 `1acd123`（STEP-40，P-113；证据 `EVD-V19-40/`）

### Changed

- **安全门（Security 工作流）的扫描输入改为锁文件导出**：pip-audit 的扫描对象从环境快照
  改为锁文件导出结果，扫描器步骤统一一次重试，并把"扫描器未运行"与"扫出漏洞"两种红
  区分开（红的原因写清楚）。来源 `e88f35a`（STEP-38；反证批 `6ecceb6`、还原批 `9b41bb1`、
  收口读数 `9c66add`）


## [v1.1.0] - 2026-10-23

> 发布时现读：`v1.0.0` 是**注释标签**，标签对象 `8ecf322` 指向提交 `c19fe87`（2026-10-08，
> "docs(release): v1.0.0 账本终稿"）；`git rev-list --count v1.0.0..HEAD` 于 `9544ef3`（STEP-33 收口批）
> 现读 = **304 个提交**，本发布批自身再 +1 ⇒ tag 指向的提交上是 305。
> 本节**不是**"把 `[Unreleased]` 换个标题"：发布前 `[Unreleased]` 只有 6 条而区间内有 304 个提交，
> 所以这一版是重新对账的产物（该失真由 STEP-12 登记，见 `docs/06_validation/evidence/EVD-V17-12/s12_readings.md` §5.1）。
> 读法：每条末尾的来源短 hash 都可 `git log -1` 对主语（STEP-39 发布时逐个复核，本段共 42 个短 hash，
> 全部解析成功；其中一条此前挂在错提交上，已更正，见下条探针条目的来源注）；能力级的判据与读数在各卡 EVD 目录
> （`docs/06_validation/evidence/`）。发布阻断两项 STEP-32 / STEP-33 由 STEP-39 并入。

### Added（用户可见的新能力）

- **采集渠道与文章分类改为运营可配**：后端读写面 + 管理端配置页；此前 registry/categorizer 只读 env 常量，
  全仓无写接口。来源 `05ff3ff`、`7c4bda8`（后端）、`848afb2`（前端配置页，STEP-14b）
- **RSS 成为一等信息源**：独立 provider、订阅生命周期与清单四态，不再只当"外链兜底"。来源 `22b9ede`（STEP-09）
- **信息源标识与按源路由**：外部标识解析、协议升级、按源选渠道 + 降级开关。来源 `bb4e3ac`、`211533c`、
  `df488f7`、`7ed167b`（STEP-08）
- **详情兜底协调器接进入库链路**（默认关、免费源先跑）与触发条件/供应商/预算运营可配。
  来源 `1e5c462`（S10.V15.1）、`b60e1e9`（S10.V15.2）（STEP-10）
- **采集静默的可观测出口**：发现链指标族、同步埋点、静默丢行/吞异常的告警出口。来源 `d19b9ab`（STEP-05）
- **写操作结构化审计日志**：23 个写操作全量归类，操作者身份取自服务端会话而非请求体。来源 `5a2e471`（STEP-31）
- **管理端直投补写站内通知历史**（第三条直投路径补齐，三路径落库顺序被用例钉住）。来源 `f383f0d`（STEP-26）
- **模块覆盖率门进 CI**：按模块设线（provider ≥80 / services ≥85 / article_identity=100 / 全局 ≥79），
  阈值只许调高，反证常驻。来源 `88381e2`（STEP-06）
- **引擎不可用原因可视化**：`GET /api/v1/engines` 每位带 `reason`（`ok`/`not_allowlisted`/`key_missing`/
  `not_implemented`），切换拒绝的文案与之一一对应。来源 `81205f1`（STEP-13）、`d839eb7`（STEP-15 消费面）
- **分页目标壳**（`hasMore` 等目标形状）+ 前端消费。来源 `fbb0409`（STEP-14a）、`d839eb7`
- **验收环境四入口**：`entry.py` / `make` 的 `testenv-up`、`testenv-down`、`verify-backend`、`verify-frontend`
  （一条命令出"真库全量 + skip 构成 + 覆盖率"与"前端 install→typecheck→vitest→build"）。来源 `9983c63`（STEP-00E）

- **AuthGate 统一未登录守卫（G1-G4）**：`components/AuthGate.tsx` 三态渲染
  （loading=骨架 / guest=统一提示卡"尚未登录或会话已过期"+登录按钮 / authed=children）；
  `tests/auth-gate.spec.tsx` 4 用例（含 authed→guest 掉落自动切卡锁定）；
  `e2e/auth-gate.spec.ts` 9 受保护页矩阵（原地渲染断言 + 404 不混淆用例）；
  `trunk.spec` ① 的断言随散装跳首页的废除同步改为断言 AuthGate 锚点。来源 `793288e`

### Changed（行为口径变了，读旧文档的人要注意）

- **正式验收面 = CI `ubuntu-latest`；Windows 侧独立成 `CI-Windows` 工作流作开发平台门**
  （D-V4-01 / D-V7-01）：两 job 曾同居一个工作流，导致"验收面绿、徽章显示灰"。
  来源 `593dc5b`（拆分与超时根因）、`0c1815c`（多平台门收口）
- **CI-Windows 的 skip 门改为"按原因族记账 + 未知族即红 + 阈值零余量"**：新增一条连库用例必然把门顶红，
  这是设计要求（重测构成后才抬阈值）。来源 `593dc5b`、`0c1815c`、`88381e2`（抬到测量值那一档）；
  阈值史 320→441→443→444→…写在 `cross-platform.md` §8
- **健康/就绪探针有界化**：依赖不可达时 `degraded` 快速返回而不是挂住，`/ready` 与 schema 守卫分层。
  来源 `5e5ab17`（S00H.1.1-1.3 探针两层上界 + 端点预算——**发布时更正**：原候选段把这条挂在
  `a3ad07a`/`0c1815c` 上，那两个提交的主语是 skip 基线与 `--timeout` 收紧，不是探针本体）
- **角色门禁单参数化 + 推送任务归属服务端化**：`require_roles` 是"取最高档"的语义（写两个参数＝admin-only），
  运营写权按意图恢复；任务创建者归属只信服务端会话。来源 `7504ef8`（STEP-24 S24.1-3 + STEP-25 S25.1-3），
  第 2 轮更正 `392a635`
- **`next` / `eslint-config-next` 升到 15.5.28**（上游安全公告 GHSA-2464-fhr4-w9xw + CVE-2026-94482 的修复线）；
  同批把 pnpm-audit 与 trivy 的 BLOCK 清空。来源 `bf141d5`
- **需求基线拆成 12 份可机检条目**（REQ-F-001…008 + NF×2 + C×2），主文档只留摘要与三向表。来源 `8de3a1a`（STEP-17）

- **九页未登录形态收敛为一（G2）**：废除六形态散装（subscriptions/jobs 白屏 null、
  engines/public/bots 无守卫裸调 API（guest 态发 401 请求）、spaces/chat/onboarding/spaces/[id]
  散装 `router.replace("/")`、admin loading-guest 不分致游客误见"权限不足"卡）——
  全部统一为 AuthGate 原地卡片，保留 URL 上下文；guest 态数据请求门补齐
  （engines/public/bots/onboarding 的 load effect 加 authed 门）。来源 `793288e`
- **TopBar 游客态两处口径**（G3.1 + G3.4）：新增"登录"按钮（与首页引导卡同源 `login()`），
  未登录隐藏私有导航入口（订阅/任务/引擎/机器人；admin 既有 `is_admin` 门不变），公共引流位保持可见；
  四私有项后改为 🔒 徽标按钮（`title="登录后可见：X"`，点击触发登录），authed 恢复正常链接、loading 不渲染。
  middleware cookie 预拦截经双向论证**裁定不实施**（语义冲突/能力上限/双源漂移/收益边际，见 backlog AUTHGATE-002）。
  `tests/topbar-guest-nav.spec.tsx` 3 用例锁定三形态。来源 `793288e`、`7cf145b`

### Fixed

- **推送域 4 个读接口缺角色门 + `/tasks` 路由被遮蔽**（后者使运营永远看不到自己的任务）。
  来源 `1236d50`、`31a6667`、`15470ee`（STEP-22）
- **两处夹具在掩盖缺陷**：`test_scheduler` 用假 id/假长链播种（于是"入库后 Diff=0"这条恒真）、
  `test_p0_asset_cache` 的 `URL_A` 不是真 `__biz` 锚（同号两篇互顶正文看不出来）。改后各带一条变异红点。
  来源 `88381e2`（STEP-06）
- **三家 provider 的时间锚、TikHub 的降级语义、"一行坏数据打挂整页"**（P-15/P-16/P-17）。
  来源 `2a7195d`、返工轮 `f7a3a6b`（STEP-20）
- **契约生成面**：jsonschema 成语义真源、`api.envelope` 收编、`collection.schema.json` 由生成器产出、
  mid/idx 前导零规范化（同文两键的第三种形态）。来源 `25088c4`（STEP-01）、`a6f54e1`（STEP-02 S2.4）、
  `d044d2a`（STEP-03 收口）
- **四条历史探针全部达"修复后期望"**（短链二次入库命中缓存、同号两篇互顶正文、多源同键
  `MultipleResultsFound`、已 READY 篇二轮 Diff 仍判新增）——**注意 P-2 那条的达成原因变了**（由 NULL 守卫给出，
  不再是"两支键空间对齐"），这条限定语必须一起读，读数在 `EVD-V17-06` §4。来源 `88381e2`（STEP-06 复跑）
- **端到端采集链此前从未被整体跑过**（发现→清单→入列→入库→二轮 Diff 五段，历史用例最多覆盖三段）。
  来源 `88381e2`（STEP-06 六渠道 E2E，连跑三次同键集）

- **Security 工作流双红灯**（CI run 37749240003 / 37749239965 实证，三条各有根因）：
  trivy 钉的是**不存在的版本** `0.57.1`（release 下载 404 → SCANNER_ERROR）改 `0.75.0`；
  `next` 14.2.35 → 15.5.27 消 pnpm-audit 13 条 critical/high（next×11 + 传递依赖 postcss 8.4.31、
  source-map-js 1.2.1 用 pnpm overrides 强提），配套 React 18→19、`spaces/[id]` params Promise 化
  （`use()` 解包 + Suspense 边界）、6 个测试文件按 React 19 的 act 语义改、11 处内部导航 `<a>` → `<Link>`；
  mock e2e ⑦ 空间详情红的根因是 engines 域**没有 mock 分支**、请求穿透 MOCK 网关打到 :3300 变 500——
  推翻原裁定补 mock 分支，而 hot 域的穿透**刻意保留**（hot.spec 无 console 门禁，它构成后端不可达降级路径的真实覆盖）。
  来源 `d0b5760`；15.5.27 → 15.5.28 的后续补丁见上面 Changed 的 `bf141d5`
- **公开 CI 日志里的密钥脱敏 + 时区库改为显式依赖**（P-107 / P-106，STEP-32）：
  `compose-smoke` 现场生成的两把一次性主密钥此前**未掩码**就写进 `$GITHUB_ENV`，
  而仓库是 public、后续步骤的 `env:` 块把值原文打进日志——改成"赋值给本步局部变量 → `::add-mask::` →
  再写入"，并新增守卫 `guard-ci-secret-mask`（写入 `$GITHUB_ENV` 的本步生成值必须先掩码，
  三处接线：`make guard`、`entry.py guard`、CI Governance 步；无可检面则 rc=3 不算通过）。
  `Asia/Shanghai` 此前只靠 psycopg 的 win32 传递依赖拿到 tzdata，而它在**导入期**被构造——上游一剥就是进程起不来，
  现改为 `pyproject.toml` 的无条件主依赖。判据与前后对照在 `EVD-V18-32`。来源 `da09dd1`
- **422（10005）不再回显调用方提交的值**（P-62，STEP-33）：校验处理器此前把 pydantic 的错误字典
  整片格式化进 message，而其中同时带着 `input`（原值）、`msg`（自定义校验器把原值内插进句子）与 `ctx`；
  现在只报「字段路径 + 错误类型 + 固定原因」，`input`/`ctx` 一次都不读，未知错误类型走泛化句、
  **不退回 msg**，连 `extra="forbid"` 那种"把凭据串当字段名"的绕过也被路径形状约束挡住。
  判据打在三条真端点上（不连库，见 `EVD-V18-33` §1.2）。来源 `c9287a6`

## [v1.0.0] - 2026-10-08

> 主题：v1.0 正式发布——S0–S3 执行批次（通知四链路/加密/告警/轻量迁移）+
> R0/R1 发布收口（死脚本复活/契约接线/outbox e2e）+ R3 功能增强。
> 版本段由 Unreleased 切出（`16d07ea` 结构定稿，`572dcde` 门禁修复后打 tag）。

> 收录 2026-10-08 的 S0–S3 执行批次与 R0/R1 收口批次（TASK-PLAN-v0.8/v0.9 驱动，基线 `main` 推进至 R1.2）。

### Added

- **RSS 订阅发现渠道（远端 2026-10-02 批并入，`5ed5886`）**：article_sources 新增
  RSS provider + 28 连库/单测；Redis 4 兼容性修复；usePagedList ESLint 修复
  —— `apps/api/app/providers/article_sources/rss.py`（前端依赖降级裁定不并入，见 `731558b`）

- **站内通知持久化四链路（S0-S1，`87ad712` `1e7202c` `9385991`）**：`Notification` 实体 +
  迁移 `ab1005w5a`（`sub` SSO 锚 + 广播标记 + `(sub, created_at)` 复合索引）；
  调度器 savepoint 落库（失败不阻断投递）+ `/notifications/history` 分页端点
  （定向+广播可见性）+ 已读回执（单条/批量/越权归零，连库 8 用例）+ 前端
  `fetchHistory`/`markRead` 离线补投 + 首连历史合并去重（serverId 锚点）
  —— `apps/api/app/services/push_scheduler.py` `apps/api/app/api/v1/system.py` `apps/web/components/NotificationBell.tsx`
- **extra_config 整字段加密（S2.1，`de4e825`）**：AES-256-GCM 域分隔 AAD
  （`{channel_id}:extra_config`，与 `secret_enc` 不可互搬）+ 存量明文兼容读
  （`{` 前缀判定）+ 迁移 `ab1005w5b`（fail-closed）+ 6 处接线（写2/回显1/投递3）+ 7 单测
- **告警生产装配启用（S2.2，`1eaa9b7`）**：compose backend_env 注入五变量（默认关闭）
  + 三类告警演练留证（隔离 PG savepoint 同会话探测，载荷语义断言）
- **轻量目录迁移（S3，`ff6e9da`）**：`backend/→apps/api/`、`frontend/→apps/web/`
  （git mv 保历史，375 rename；183 骨架 `.gitkeep` 清理）+ CI×2/compose/Makefile/
  Dockerfile/tsconfig 路径同步 + parents 层级修复；六边形 modules/ 重构显式推迟立项
- **契约接线（R1.1，`4d8ecd9`）**：`@bothot/contracts` index.ts 导出 6 域 DTO
  （bot/hot/ingest/knowledge/push_event/subscription）；CI 双门禁（backend 契约漂移
  `--check` + frontend 契约包整包 tsc——paths 只解析 dist 的源码盲区堵死）

### Fixed

- **S0 执行收口批（`5fe5a4f` `8c9026c` `5476807` `7dfed5a` `01a08a6`）**：连接池容量守卫
  生产接线（web/scheduler/worker 三进程 fail-fast）；限流 fail-open 告警 60s 窗口节流；
  tsc --noEmit 摘软闸转硬门禁；Windows 无 WSL 的 bash 功能探针防假阳性 + MOCK 态 SSE
  不建连；MOCK 门 `NODE_ENV=test` 豁免（vitest 全量 359 用例全绿）
- **`test_security_middleware` 跨平台假阳性（S0-R0.1，`7dfed5a`）**：`_BASH` 由
  `shutil.which` 升级为功能探针（`bash -c 'exit 0'` 非 0 视同不可用→skip），并给子进程
  补 UTF-8 解码——修复 Windows 无 WSL 下 2 例假阳性失败
  —— `apps/api/tests/test_security_middleware.py`
- **S3 迁移漏网脚本复活（R0，`e019bb0` `1526a6b`）**：`gen_contracts.py` BACKEND_DIR
  `backend→apps/api`（sys.path 插死目录致 import 必炸）与 `preflight.sh` 12 处旧路径修复；
  连带修复 gen_contracts 游离 `*/` 语法错误（split hack 切出头残留，`bot/dto.ts:54`
  TS1109 实证，契约包整包 tsc 首次全绿）
- **outbox 消费失败分支端到端（R1.2，`9a6e5ab`）**：emit→claim（consumed_at 先标记）→
  派发→webhook 不可达注入失败→failed PushLog + 重试簿记→重投领取为空
  （at-most-once 锚定）；隔离 PG 11/11 绿 —— `apps/api/tests/test_w3_push_scheduler.py`

### Changed

- **多会话协作纪律固化（`566633c` `8ba2512`）**：开工取证/可信通道序/单一提交身份/
  路径所有权/断点报告 + §7 实战教训（后台管道假死/pnpm 交互确认/git mv 嵌套/
  parents 层级/无尾斜杠盲区）—— `docs/04_engineering/collaboration-discipline.md`
- **文档一致性修复（R0.3，`7a0be0f`）**：backlog 20 处旧路径引用改 `apps/*`
  （check_docs_consistency 实测 20/20 通过，此前该门禁因迁移假红）；
  roadmap 告警装配置 ✅ —— `docs/04_engineering/backlog.md`
- **任务计划 v0.8/v0.9 入库（`fbaaeaa` `be6077d`）**：S0 执行收口节 + 外部 81 项大纲
  逐条裁定（剔除已完成 9/修正 3/补遗 P0 4）
  —— `docs/05_execution/tasks/`

## [v0.6.5] - 2026-09-30

> 主题：W6-W10 六路并行交付（观测硬化/入站防护/数据层/契约消费/前端/文档治理）+
  集成审查修复 + CI 首跑红灯五连修（`c56b642` 状态回填收口，提交日 2026-10-08）。

### Added

- **观测与运行时硬化（W6-W10，`main @ 8b1b5f2`）**：structlog 双模日志（`core/logging.py`，
  prod=JSON/dev=Console，启动 `main.py:249`）；Prometheus 指标 8 族 + `/metrics` 独立 router
  `include_in_schema=False`（`core/metrics.py` + `MetricsMiddleware`）；`/live` `/ready` 探针 +
  `core/schema_guard.py`（schema 不一致 503）；运行时安全中间件限流/体限/安全头
  （`core/security.py`，经 `install_security_middlewares`）；两 Dockerfile 多阶段 + uid1000 +
  HEALTHCHECK，compose 全服务 logging/limits，backend/scheduler/worker 三常驻服务
  read_only/tmpfs/cap_drop/no-new-privileges（数据服务不设只读根）；
  运行期告警三类（`core/alerting.py`）

### Fixed

- **CI 首跑红灯修复（`08c3935..7bdb964`）**：契约幽灵依赖清零 + 前端镜像 context 升根、
  `security.yml` 解析即拒 + 加载期 env 白名单越界、mock 产物缓存复用 + 排序断言时间戳并列、
  UP017 风格清零
- **security.yml 加载期 0-job 秒红（三轮首跑实证）**：job 级 `env:` 使用了
  `runner.temp` 与 `coalesce()`——该层表达式白名单均不含二者，GitHub 表现为
  工作流加载被拒（0 job、created==updated、API 无错误详情，REST 排查通道全部
  静默）。真凶由 actionlint 定位（本地官方 workflow-parser 只查 schema，查不出
  上下文可用性）。修复：`VERDICT_DIR` 改静态 `/tmp/security-verdicts`；
  `SECURITY_GATE_ENFORCE` 改 `${{ vars.X }}` 直引（消费侧 `${X:-1}` 兜底已存在）。
  防再犯：ci.yml 新增 **`workflow-lint` job**（actionlint v1.7.12 钉版，全部
  workflow 静态检查）—— `.github/workflows/security.yml` `.github/workflows/ci.yml`
- **CI frontend 13 秒红：`@bothot/contracts` 幽灵依赖（2026-09-30 首跑实证）**：W9 曾把
  `workspace:*` 写入 `frontend/package.json`，但仓库**无 pnpm workspace 根**且 lockfile
  从未收入该条目——本地 tsc/vitest 因「tsconfig paths + 纯 `import type` 擦除」假绿，
  CI 第一步 `pnpm install --frozen-lockfile` 因 package.json ↔ lockfile 声明漂移必红。
  修复 = 删除该从未生效的依赖声明，契约消费机制明确为 **纯 tsconfig paths 类型解析**
  （机制本身不变，仅删幽灵声明；运行时导入若未来出现，next build 期即报错，非静默漏过）
  —— `frontend/package.json` `frontend/tsconfig.json`

## [v0.6] - 2026-09-30

> 主题：WA/WB/WC/WE 四路交付集成（评分接线/推送加固/基建/通知闭环）+
  WD CI 编排补全（e2e/compose-smoke/单头断言/guard-ports fail-closed）+ 集成终态同步。

### Added

- **CI 门禁补全（WD）**：`frontend` job 增 Playwright **mock UI e2e**（`PORT=3456`，**阻塞门禁**，
  产物以 `next build` + `NEXT_PUBLIC_API_MOCK=true` 生成）；新增 **`compose-smoke` job**
  （build backend 镜像 → 起核心服务 → 跑 `scripts/smoke.sh`：`/api/v1/system/health` +
  scheduler/worker 心跳新鲜度）；`backend` job 在迁移后增 **alembic 单头断言**（head 数 == 1，
  防 multi-head 分叉静默不落库）—— `.github/workflows/ci.yml`
- **README「部署指南」小节（WD）**：compose 环境变量清单（含 `PUSH_SECRET_MASTER_KEY` /
  `ENGINE_KEY_MASTER_KEY` 等必填主密钥）+ 端口纪律表 —— `README.md`
- **过时规划文档归档（WD）**：`当前任务规划.md` → `docs/09_archive/superseded/`（附归档标识头，
  说明其成文于 W1–W5 之前、约七成已过期）

### Changed

- **backlog 全量回填代码实证状态（WD）**：`PUSH-007/008`、`TECH-001/002`、`HOT-001~004`、
  `FE-001~004`、`TEST-001~003`、`MIG-003`、`DOC-001/002` 逐条对照 `main @ 2fa95f0` 代码更新，
  每处附 `文件:行号`；并新增 `FE-005`（站内通知**前端订阅侧**缺失）与 `PUSH-009`（推送失败重试）
  —— `docs/04_engineering/backlog.md`
- **CHANGELOG 切分版本段（WD）**：由「全部挤在 Unreleased」改为 `v0.3 / v0.4 / v0.5` 三段
  + 空的 `Unreleased` 承接增量 —— 本文件
- **`SKIP_BASELINE` 复核（WD）**：合并后连库用例由 742 → **796** 条（+54），
  但 skip 数**未随之增长**（实测 `796 passed, 4 skipped`，PG 不可达类 skip = 0）→ 阈值维持 `6`；
  并在 CI 注释中固化该复核结论 —— `.github/workflows/ci.yml`
- **真实后端 e2e 由「死断言」改为环境闸（WD）**：原 `test.skip(true, …)` 为**无条件恒跳过**，
  套件永不可执行；现改为 `E2E_REAL_BACKEND=1` 时真实执行，文章 URL 可由 `E2E_ARTICLE_URL` 覆盖，
  并配 CI `continue-on-error` + 仓库变量闸 —— `frontend/e2e/real-backend.spec.ts`
- **前端镜像构建上下文升为仓库根**：前端经 tsconfig paths 引用 `packages/contracts`，
  `next build` 期类型检查需要其可见，旧 `context: ../frontend` 在镜像内取不到 → build 必炸。
  现为 `context: ..` + `dockerfile: frontend/Dockerfile`，builder 将契约源放 `/packages`；
  新增根 `.dockerignore` 控制上下文体积（仅 frontend/ + packages/ 入镜像构建）
  —— `frontend/Dockerfile` `docker/compose.yml` `.dockerignore`
- **compose `BASE_IMAGE` 默认值回归 node:24 锚**：原 `${BASE_IMAGE:-node:20-alpine}` 会
  **静默覆盖** Dockerfile 的 node:24 锚（3.4 版本锚统一）；`guard-versions` 扩围新增
  compose 侧锚比对，漂移即红 —— `docker/compose.yml` `Makefile`
- **本地门禁补漂移拦截**：`preflight.sh` 前端段增 `pnpm install --frozen-lockfile
  --lockfile-only`（只解析校验不装包；漂移副本实测 exit 1，报错与 CI 逐字一致）；
  `ci-repro-frontend.sh` 的 `git archive` 补上 `packages/` 并挂载容器 `/packages`
  （原只带 frontend，容器内契约路径缺失，复现口径本身失真）
  —— `scripts/preflight.sh` `frontend/scripts/ci-repro-frontend.sh`

### Fixed

- **`Makefile` `guard-ports` fail-open（WD）**：原实现两段 `grep` 用 `\` 续行后，
  `if [ $? -eq 0 ]` 取到的是**第二条（前端）grep** 的退出码——后端/编排侧独有 `3333`
  命中时被静默放过，守卫形同虚设。改为两段各自捕获输出、各自判据，任一命中即 `exit 1`
  —— `Makefile`（本地三场景实测：干净 exit 0；仅后端注入 exit 1；仅前端注入 exit 1）

## [v0.5] - 2026-09-30

> 主题：AIHOT 热点能力融合落地 + 工程基建（CI 真实化 / 契约冻结 / 文档修正）。

### Added

- 热点域落地（v0.5）：聚簇（标题字 bigram TF-IDF 单链接凝聚，Job type=`hot_cluster`）、
  热度评分（48h 独立来源加权 + 24h 半衰 + 状态机）、Feed 三类生产者
  （`(item_type,ref_id)` upsert，迁移 `ab1004w2a`）、日报（LLM 摘要失败降级为正文首段截断，
  每日 06:30 自动生成前一日日报；业务日界 Asia/Shanghai）—— `25181c1`
- 前端热点中心增强：/hot 聚簇触发按钮 + 热度条形 + 状态过滤；/hot/daily react-markdown
  真渲染 + 翻页（与 v0.4 的 /bots Tab 同属提交 `d2678d7`）—— `d2678d7`
- **共享契约冻结（W5）**：`packages/contracts/` 落地 `PageResult<T>` / `ApiResponse<T>` /
  `ApiErrorCode` 三类，均标注后端单一来源 `文件:行号`，配 `package.json` + `tsconfig.json`
  （`emitDeclarationOnly` → 仅产 `.d.ts`）—— `cac6a22`
- **冒烟脚本（W5）**：`scripts/smoke.sh`——`docker compose up -d` 后轮询
  `/api/v1/system/health` 并校验 `process_heartbeats` 中 scheduler/worker 心跳新鲜度，
  输出 PASS/FAIL —— `cac6a22`

### Changed

- **CI 后端测试门禁真实化（W5）**：`backend` job 增加 `postgres:16` service
  （凭据/端口与 `backend/tests/conftest.py:36` 默认 DSN 对齐）与 `alembic upgrade head`
  迁移步骤；新增 skip 门禁（PG 不可达类 skip 直接失败 + skip 总数超基线失败）—— `cac6a22`
- **文档漂移修复（W5）**：`docs/04_engineering/roadmap.md` 回填 v0.4 勾选状态；
  `backlog.md` 将 HOT-003/HOT-004 由 ✅ 更正为 🔧 并注明缺口；`AGENTS.md` 修正站内通知/
  热点/密钥加密三处表述；`conventions.md` §6.1 补渠道密钥 base64 过渡态说明；
  `project-map.md` 将 `06_validation/` 由"预留"更正为"已启用" —— `cac6a22`
- 热点域时区口径统一：`hot.py` 4 处 `datetime.utcnow()`（naive、已弃用）→
  `datetime.now(Asia/Shanghai)` 业务日界 —— `25181c1`
- `docker/compose.yml` 注入 `PUSH_SECRET_MASTER_KEY`；旧调度测试迁移 —— `e5bf6cb`
- 集成终态同步：roadmap v0.4/v0.5 完成勾选 + `AGENTS.md` 状态 + CHANGELOG 收录 +
  新增 `.gitattributes` —— `a6889b0`

### Fixed

- 集成审查发现并修复的两处 W1 缺陷：渠道 secret **AAD 绑定空串**（创建时 id 未生成即加密，
  读取侧必解密失败 → 改为显式预生成 id 后加密）；`bots` 域**写端点收参与前端契约错位**
  （后端标量查询参数收不到 JSON body → 改为 Pydantic body 模型）—— `0879882`
- 旧 `test_push_providers.py` 引用已删除的 `_parse_cron_next`（ImportError ×5）→
  迁移到 `app.services.cron_expr` —— `e5bf6cb`

## [v0.4] - 2026-09-30

> 主题：多渠道推送真实投递 + Cron 全生命周期 + 事件触发 + 密钥安全落库。

### Added

- 六渠道推送 Provider 真实投递：飞书、钉钉、企业微信、通用 Webhook、微信 ClawBot、站内通知
  （`backend/app/providers/push/`；站内通知为 Redis pub/sub **投递侧**，前端订阅侧未实现）—— `dca56b0`
- Bot 渠道管理能力：渠道 CRUD、测试推送、推送日志、推送任务 CRUD 与手动触发
  （`backend/app/api/v1/bots.py`）—— `dca56b0`
- PushScheduler 定时调度器：60s 扫描，在 backend 进程内由 FastAPI lifespan 启动
  （`backend/app/main.py:247`）—— `dca56b0` `1c89b2e`
- Cron 解析统一收口 `services/cron_expr.py`：croniter 完整 5 段式 + 三种简写兼容
  （`HH:MM` / `*/N` / 纯数字分钟）；Cron 任务创建即写 `next_run_at`、新增
  `PUT /api/v1/bots/tasks/{id}`（编辑/暂停恢复）、run-now 补算下次执行 —— `0879882`
- 渠道密钥 AES-256-GCM 落库：`core/secret_crypto.py`（AAD 绑定 bot_channel.id，
  `PUSH_SECRET_MASTER_KEY` fail-closed）+ 存量 base64 重加密迁移 `ab1004w1a` —— `0879882`
- 推送调度器并发安全：FOR UPDATE SKIP LOCKED 短锁领取 + 单任务异常隔离
  （多副本部署不再重复投递）—— `90618b7`
- 事件触发推送（PUSH-008）：PG outbox 表 `push_events`（迁移 `ab1004w3a`）——
  worker 进程 emit（文章入库/聚簇/日报）、backend 调度器 claim 消费；
  模板变量 `{space_name}/{doc_title}/{hot_topic}/{topic_count}` —— `90618b7`
- 前端推送任务管理：/bots 双 Tab（渠道 / 任务）+ `PushTasksTab` + `CronEditor`
  （列表/创建/编辑/暂停恢复/删除/立即执行/日志；与 v0.5 的 /hot 增强同属提交 `d2678d7`）—— `d2678d7`

### Changed

- 依赖清理：移除 `celery[redis]`（全仓零接线，且与"不引入 Redis 队列"约束冲突）；
  新增 `croniter` —— `0879882`
- 文档状态口径修正：推送 Provider 由"占位"更正为"已实现真实投递"，
  PushScheduler 归属更正为 backend 进程内 —— `1c89b2e`

### Fixed

- **Cron 任务创建即永不触发**（调度器过滤 `next_run_at IS NOT NULL`，创建端点不写该列）—— `0879882`
- **渠道 secret AAD 绑定空串**：创建时 id 未生成即加密（AAD=""），读取侧以 channel id
  解密必失败——改为显式预生成 id 后加密 —— `0879882`（集成审查发现）
- **bots 域写端点收参与前端契约错位**：后端标量查询参数收不到前端 JSON body（创建恒 400、
  更新静默 no-op）——改为 Pydantic body 模型（对齐 spaces 域惯例），前端零改动 —— `0879882`
  （集成审查发现）
- `push_port.py` 双头推送语义（占位 delivered=False 与真实投递并存）收敛删除（TECH-001）—— `0879882`

## [v0.3] - 2026-09-29

> 主题：BotHot 从 AideanBot 升级基线 + 文档架构与目录结构规范化。
> （两类工作同日落地，无 tag 分隔，故并列于本段。）

### Added

- BotHot 从 AideanBot 升级：多渠道推送骨架 + AIHOT 热点数据模型与读侧 API +
  前端统一 3200 端口（`dca56b0`）
- BotHot 扩展数据模型 7 张表（bot_channels / push_tasks / push_logs / hot_topics /
  hot_topic_articles / daily_reports / feed_items）+ Alembic 迁移 `ab1004bh01` —— `dca56b0`
- 前端页面：机器人管理（`/bots`）、热点中心（`/hot`）、日报（`/hot/daily`）—— `dca56b0`
- 四平台文章来源 Provider：Dajiala 极致了、JustOneAPI、TikHub、Wellbyte 数井
  （`backend/app/providers/article_sources/`，含发现注册与按成本排序的付费详情兜底协调器）—— `3b548b1`
- `ConfigurationError`（code `50003`）异常类 —— `3b548b1`
- 文章采集测试证据归档：`docs/06_validation/evidence/channeltest-20260929/`
  （4 平台活体实测，TC 编号逐条可对）—— `3b548b1`
- 文档体系 `docs/`（00_governance ~ 04_engineering，23 个文件）；
  `apps/` monorepo 目录骨架；`packages/contracts/` 契约包骨架 —— `1c89b2e`
- `Makefile` 27 个 target（含 `guard-ports` / `guard-structure` 架构守卫）—— `1c89b2e`

### Changed

- 项目由 AideanBot 升级更名为 BotHot（session cookie / 容器名 / 项目名 / 前端端口 3200）—— `dca56b0`
- 后端容器内部端口由 8000 漂移修正为 3300（与 compose、前端 rewrites 对齐）—— `1c89b2e`
- 文章来源证据口径由"行级标签"改为**格级证据**（每个 ✅/⚠️/❌ 自带 TC 编号与级别）；
  补齐实时性/标识体系/请求形态/失败计费/价格漂移五个决策维度 —— `90c4e2f`
- 计价单位纠正：TikHub 为 **USD/请求**（非 credits），Wellbyte 为 credits，
  Dajiala / JustOneAPI 为 CNY —— `90c4e2f`

### Fixed

- 双端 CI 门禁清零：backend（ruff 0.12.12 / mypy / pytest 本地全绿）；
  frontend（typecheck / vitest / build 全绿）—— `e786d78`
- `providers/article_sources/registry.py`：4 个来源工厂函数前移到 `CHANNELS` 之前，
  消除模块导入期 `NameError`（ruff F821）—— `e786d78`
- `push_scheduler.stop()`：`with` 更正为 `async with`（`_suppress_cancel` 仅实现
  `__aenter__`；原实现调用 stop() 必抛 `AttributeError`，调度器停不下来）—— `e786d78`
- 安全：`bots` / `hot` 两个 router 补 `get_current_sub` 登录门禁
  （此前两域全部端点可匿名读写）—— `e786d78`
- 前端 `bots` / `hot` / `hot/daily` 三页补 `usePageTitle`，修复页签标题覆盖守卫 —— `e786d78`
- JustOneAPI 搜索由"返回空列表"更正为真实契约级实现；
  TikHub 详情由返回 `None` 更正为调用 v2 端点（402 时降级）—— `90c4e2f`

---

## 记录约定

- 新增条目请归入 `Unreleased` 对应小节（Added / Changed / Fixed / Removed / Security）。
- **禁止把未实现或仅计划中的功能写进来**——本仓库的历史问题是文档虚报状态，
  条目须能被 `git log` 或代码实证核对。
- 发布时把 `Unreleased` 段落改名成 `## [x.y.z] - YYYY-MM-DD`，并新增空的 `Unreleased`。

### Fixed

- **middleware mock 构建短路（2026-10-09，修 CI frontend job e2e 全红）**：全局认证守卫
  middleware（01f6892 引入）硬查 `bothot_session` cookie，而 mock 态登录存 localStorage
  无 cookie——mock 已登录用户也被 307 弹回首页。加 `NEXT_PUBLIC_API_MOCK` 构建期内联
  判定，mock 产物整体跳过 middleware；真实态路由层守卫不变。
- **compose-smoke 共享底座适配（2026-10-09，修 CI compose-smoke job）**：底座迁移后主
  compose 无 postgres/redis、backend env 指向 runner 上不存在的 host.docker.internal；
  新增 `docker/compose.ci.yml` CI 专用叠加（回补栈内 PG/Redis + 覆盖 backend/migrate/
  scheduler/worker 连接 env），smoke.sh 支持 `COMPOSE_FILE` 多文件叠加。
- **backend healthcheck 探针超时 2s→4s（2026-10-09）**：/health 的 LangBot 探测固定
  等满 3s，探针 2s 客户端侧先超时致容器恒 unhealthy；4s 覆盖探测上限且低于 compose
  层 5s。
- **frontend 容器 CMD 摘除 runtime corepack 依赖（2026-10-09）**：`pnpm start` 触发
  corepack 现场下载 pnpm，运行时坏代理 env 下 fetch 失败崩溃循环；改直用
  `node_modules/.bin/next start`，runner 零外网依赖。
