# STEP-57 读数（出路③：只发 `/auth/me` 钱包白名单投影；`MeWallet` 契约侧仍开放）

> 卡：`docs/任务规划V0.21.0/steps/STEP-57-me钱包白名单投影.md`（裁决 D-V21-17，取代 D-V21-09）
> 基线：main@52673f2（STEP-56 收口批，同 head 三绿 attempt 1）

## 0. 开工前置（现取）

- `git fetch` 后 `origin/main...HEAD` = `0 0`，head = `52673f2bf8ab9d679ec3df7eb2f6bbea1ab3603f`。
- 上一卡收口批三绿：CI 40443130984 / CI-Windows 40443130849 / Security 40443130907，均 attempt 1；
  逐字行见 `s57_0_preopen_ci_readings.txt`（ubuntu `2488 passed, 6 skipped, 4 deselected`、
  skip 门禁 `total_skipped=6 baseline=6 pg_unreachable=0`、`Total coverage: 88.90%`、
  `✅ 全部模块与全局达标`、vitest 53/425、e2e 31；@win `1802 passed, 692 skipped`、
  `windows 门禁：failed=0 total_skipped=692 baseline=692`）。
- **PG@5547 连通前置**（按规划方 2026-10-27 的口径：先确认连得上再开跑）：双栈在监听之外，
  实跑 `pytest tests/test_shapes_response_contract.py -q -rs` ⇒ **18 passed，0 skipped**（那 18 条含第 1 轮我加进去的两条；退回后该文件是 17 条，两次都是 0 skipped）
  （原始读数归档 `s57_0_preflight_and_void_note.txt`；该文件含 `test_me_degraded_branch_shape(db_session)`，
  正是本卡要动的降级分支的邻居。第一次跑是 17 passed，那在我往这个文件加第 18 条用例之前，两次都 0 skipped）。
  只听 `netstat` 不算连上。同份读数里还记着门链第 1 跑为什么作废。

## 1. 改前的字节（现状核对，不是猜测）

| 位置 | 现读 |
|---|---|
| `apps/api/app/services/auth/service.py:259`（改前；第 2 轮交付后在 :297） | `"wallet": wallet.get("wallet", wallet)` —— 上游给什么就往外发什么 |
| `apps/api/app/contracts/shapes.py:47-56` | `class MeWallet(BaseModel)` + `model_config = ConfigDict(extra="allow")`，五个字段里 `balanceYuan`/`currency` 必填，其余带默认值 |
| `packages/contracts/schemas/shapes.schema.json:388` | `"additionalProperties": true`（全 30 个 def 里唯一一个 `true`） |
| `apps/api/tests/test_shapes_response_contract.py:75-82` | 旧判据叫「`MeWallet` 是唯一开放对象」，`assert open_defs == ["MeWallet"]` |
| `apps/web/tests/s55-mock-runtime-shape.spec.ts:414-415` | 期望 `MeWallet` 多一个契约外键时**放行**（`toEqual([])`）——即运行时形状门对这一层是照着契约的开放形松的手 |

前端读的键（判卡面熔断条件「前端真读了五键之外的钱包字段」）：`lib/api/types.ts` 的
`normalizeMeData` 里字段访问恰好三处——`w.available`、`w.balanceYuan`、`w.currency`；
`heldYuan`/`availableYuan` 在 `apps/web` 只各出现 1 次且都在 `tests/me-normalize.spec.ts` 的夹具里；
`internalNote` 零命中。⇒ **熔断条件不触发**，本卡按卡面走。`MeWalletInfo` 是契约别名
（`types.ts:47`），不是手抄的第二张形状表，所以封闭之后 tsc 不会红——这条不是推测，
改后 `pnpm run typecheck`、`pnpm exec tsc --noEmit -p ../../packages/contracts/tsconfig.json` 都 rc=0。

## 2. S57.1 先红（判据①）

新 `apps/api/tests/test_me_wallet_projection.py`，走完整登录链（内存桩，不连库）：伪主平台的钱包
多吐一个 `internalNote`，断言我们的响应里没有它。键名刻意挑"主平台内部风控"那种不像业务字段的，
免得被读成"这个本来就该给"。

- 第一遍红（在未改的 `service.py` 上，最终用例字节之前的那一版）：
  `AssertionError: 钱包透传未过滤，响应带出契约外键：['availableYuan', 'balanceYuan', 'currency', 'heldYuan', 'internalNote']`
- 第二次红**跑在最终字节上**（`s57_probe_A_service_off.txt`）：只把投影那一次调用摘掉、
  `_project_wallet` 本体留着，再跑**整文件**，读数 `1 failed, 7 passed`——红的就是那一条集成用例，
  7 条纯函数用例照旧绿（换成整份还原 HEAD 会让纯函数那 7 条因 import 失败连坐，那条红就说不清是谁的了）；
  还原后按字节写回、四件 sha 全等（`sha_all_equal=True`），整文件复跑 `8 passed`。
- 顺带一条环境噪声，与本卡判据无关：失败输出里那段 `redis.exceptions.TimeoutError` 是
  `app/core/security.py` 的限流计数器在本机无 Redis 时的既有 fail-open 告警
  （`[warning] 限流计数器 Redis 不可用，本轮 fail-open（不限流）`），pass 的用例不打印所以平时看不见。

## 3. S57.2 投影（判据②）

`service.py` 模块级新增 `_WALLET_KEYS` / `_WALLET_REQUIRED` / `_WALLET_UNAVAILABLE` 与纯函数
`_project_wallet(raw)`。三条口径与卡面一致，各自都有用例钉着：

- 只吐白名单五键；上游没给的可选键**保持缺席，不补 0**（补 0 会把"平台没告诉我"写成"余额是 0"，
  而前端对这两件事是两种文案）——`test_projection_leaves_absent_optional_keys_absent`。
- 必填键缺失、值为 `null`、或整块不是字典 ⇒ 回降级形 `{balanceYuan:0, currency:"CNY", available:false}`，
  不抛 500——`test_projection_degrades_when_a_required_key_is_missing_or_null`（里面还判**降级得报对原因**：
  `missing == ["balanceYuan"]`）与 `test_projection_degrades_on_a_non_dict_payload`（只喂非字典，两条各判一条出口）。
  "`null` 也算缺"是第 1 轮复查逼出来的：只判 `key in raw` 会让 `{"balanceYuan": null}` 过关，而信封层
  `core/response.py` 的 `success(data=...)` 不做形状校验，那个 `null` 会一路走到契约之外。
- 多出的键名以 debug 记一次、**值一律不落日志**——`test_projection_drops_unknown_keys_and_logs_only_their_names`
  用 `structlog.testing.capture_logs` 判四件事：恰好一条、`keys == ["internalNote"]`、
  `log_level == "debug"`，以及**整批事件**里搜不到那个值（复查指出"只搜那一条事件"会放过别处漏值，
  判据因此改成 `str(events)`）。"记一次"取的是**每次投影记一次**，不是进程级去重——卡面那句
  「以 debug 级别记一次」两种读法都成立，本卡选不丢事件的那一种，并把口径写进断言消息里。
- 混合键型不炸：`test_projection_survives_mixed_key_types`。`sorted(raw)` 遇到 `{1: ..., "balanceYuan": ...}`
  是 `TypeError`，而这条函数的承诺正是"不抛 500"；上游 JSON 的键一定是字符串，但它是纯函数、也会被直接喂字典。

两处顺手收紧（都在允许面 `apps/api/app/services/auth/service.py` 内，不是重构邀请）：
`/me` 的两条既有降级分支改为复用 `_WALLET_UNAVAILABLE` 的副本，于是"三条分支同形"变成同源而不是三份
字面量；`_project_wallet` 每次返回新字典（`test_projection_copies_the_degraded_shape_instead_of_sharing_it`
钉的就是"调用方改了返回值不许污染下一个人"）。

## 4. S57.3 契约封闭与产物（判据③）——**第 1 轮读数，整节已按出路③ 退回 HEAD 字节，见 §10**

- `shapes.py` 的 `MeWallet` 改继承 `_Closed`，删掉 `extra="allow"` 与那行 `model_config`；文档字符串
  写明投影在哪、为什么可选键不补。
- `python scripts/gen_contracts.py` 重新生成，`--check` 幂等 rc=0。**产物面只有一处变化**：
  `packages/contracts/schemas/shapes.schema.json` 的 `MeWallet.additionalProperties` 由 `true` 变 `false`
  （加 `description` 文案）；`packages/contracts/src/shapes/dto.ts` **字节不变**——TS 接口本来就不编码
  `additionalProperties`，所以这次改动不会、也没有必要动前端类型。
- 契约测试两条收紧：`test_no_shape_def_is_an_open_object`（旧名"MeWallet 是唯一开放对象"实际上是给
  透传背书）现读 `open_defs == []`，并新增"object 必须显式写 `additionalProperties`"这一半——缺省在
  JSON Schema 里不是封闭，那会让多键判据静默；`test_me_wallet_now_rejects_an_unknown_key` 判合法两键
  过、契约外键必须报。
- 反证 `s57_probe_B_def_open.txt`：把 `shapes.py` 整份换成 HEAD 版（开放形）再重新生成，两条用例同报
  ——`契约里又出现开放对象（上游加字段就直通对外）：['MeWallet']` 与 `MeWallet 仍放行契约外键 ⇒ 开放没拆干净`
  （`2 failed, 16 deselected`）；还原后再生成 + `--check` rc=0，四件 sha 全等，两条用例复跑绿。

## 5. 越界申报（第 1 轮的两处；第 2 轮随 S57.3 退回而都不成立）

> 本节保留为第 1 轮的读数。**规划方 2026-10-27 选定 P-129 的出路③（本卡只发投影那一半）之后，
> 下面两处涉及的文件都已原样退回 HEAD 字节**，第 2 轮的交付面见 §10。

**第一处**：`apps/web/tests/s55-mock-runtime-shape.spec.ts:414-418` 从"期望放行"翻成"期望报错"。卡面对
`apps/web` 写的是「的类型与样例（仅当 tsc 要求）」，而这里既不是类型也不是样例、tsc 也没红——**改它的是卡面
验收④自己**：那半句要求「s55 运行时形状门仍绿」，而这条断言钉的是"`MeWallet` 开放时门该放行"，
`MeWallet` 一旦封闭它就必然红。要么翻这条断言，要么让 `MeWallet` 保持开放（＝本卡不做）。
改动是 3 行注释 + 2 行断言，没有动样例数据、没有动 `checkShape`/`auditDefs` 本体。

**第二处**（第 1 轮复查指出，我改前没看见）：`apps/api/app/contracts/shapes.py:13-16` 的**模块文档字符串**
原写「本模块里唯一 `extra="allow"` 的是 `MeWallet`……这一处如实写成开放对象」——类改成封闭之后这句话
就是假话。复查给的机制是"它会被生成进 `shapes.schema.json` 的顶层描述"，**这一半我实测否证了**：
生成物的根 `description` 恒为固定文案「由 scripts/gen_contracts.py 从 …生成，请勿手动修改」，
docstring 里的「写法纪律」等字样在 schema 里 grep 零命中，`git diff -- packages/contracts/schemas/shapes.schema.json`
也只有 MeWallet 那两行。所以改它的理由是"源码里不许留假话"，不是"产物会被污染"。卡面字段 6 只写
「`shapes.py` 中 `MeWallet` 一个类」，这段在类外 ⇒ 按越界申报处理：改 4 行文字（说清 STEP-57 之后
不再有开放对象、以及改前它为什么确实是开放的），不动任何 def。

同文件第 107 行的注释仍写「2026-10-26 现测：31 个对象节点全带 additionalProperties（30 false +
1 true=MeWallet）」——那是带日期的历史读数，按纪律不回改。当时（第 1 轮把 `MeWallet` 关掉之后）
同一口径的现读是 **31 个对象节点、31 false + 0 true**（`type:"object"`：shapes 28 + engine 3）。
**第 2 轮按出路③ 退回之后，本卡交付字节上的现读回到 30 false + 1 true**（shapes 27 false + 1 true
=MeWallet，engine 3 false），def 数仍是 30 ⇒ 除了那一个翻转，没有别的对象节点被动过。这句记在这里而不是抄进那份旧审计的 docstring。

## 6. 本机门链（**第 1 轮字节**的那一跑；第 2 轮读数在 §11）

第 2 跑 `s57_local_gates_run2.txt`，15 步按 `ci.yml` 顺序，链首/链尾指纹相同
（`fp_start == fp_end == 823083c46acf571c` ⇒ 全程一份字节，中途没人（包括我）动过工作树）：

| 步 | rc | 读数 |
|---|---|---|
| pgpreflight / ruff / mypy / alembic upgrade / alembic heads / gen --check / docs | 全 0 | 单头、幂等、版本锚一致 |
| pytest 全量 | **1** | `5 failed, 2492 passed, 6 skipped, 4 deselected in 1214.34s` |
| 覆盖率门（仓库根、不设编码变量） | 0 | `达标 88.91% ≥ 79.0% TOTAL`、`✅ 全部模块与全局达标` |
| 前端 typecheck / contracts tsc / vitest / lint / 演示态 build / mock e2e | 全 0 | vitest `53 passed (53)` 与 `425 passed (425)`；e2e `31 passed (1.6m)` |

skip 侧：`6 skipped` 与基线同数（新用例全不连库），`SKIP_BASELINE` 与 `SKIP_BASELINE_WIN` 都不动。
第 1 跑作废（`s57_local_gates_void_run1.txt`，`7 步 rc 全 0 + pytest 到 43%`），理由与停法记在
`s57_0_preflight_and_void_note.txt` 末段——复查逼我改字节，按「链在跑就不碰工作树」先停链再改。

那 5 条红**不是本卡新增用例红**，全部集中在「冻结稿 ↔ 产物」比对器这一族，见 §9。

## 7. 独立复查（子智能体，只读）与逐条处置

第 1 轮判 **PASS-with-nits**：卡面范围、三条分支同形、前端读键面、未过滤路径四项 PASS，
`_project_wallet`、用例质量、读数准确性三项带 nit；没有 FAIL，卡面两条熔断条件（同判据 2 次 FAIL、
前端读五键之外）都没触发。逐条我自己复核后的处置：

| 复查说的 | 复核与处置 |
|---|---|
| `sorted(k for k in raw …)` 遇混合键型是 `TypeError`，与"不抛 500"的承诺矛盾 | 成立（上游 JSON 键一定是字符串，但它是纯函数、也会被直接喂字典）。改 `sorted(str(key) …)`，配常驻用例 `test_projection_survives_mixed_key_types` |
| `{"balanceYuan": null}` 键在值空会放行 | 成立——先核了信封层：`apps/api/app/core/response.py:19` 的 `success(data=...)` 确实不做形状校验，那种值会一路走到契约之外。判缺改成 `raw.get(key) is None`，用例覆盖并要求报对 `missing` |
| `shapes.py` 模块 docstring 现在是假话，而且"会生成进 schema 顶层描述" | **前半成立、后半我实测否证**（根 description 是固定文案、docstring 字样在 schema 里零命中）。按"源码里不许留假话"改那 4 行，并按卡面字段 6 登**第二处越界申报**（见 §5） |
| 只在那一条事件里搜值，别处漏值会放过 | 成立，判据改成搜**整批** `events` |
| `{"wallet": None}` 被归到"非字典"那条，实际走的是缺必填键 | 成立，两条出口分开判：非字典那条只喂非字典 |
| census 第三判据违规时打印的是整个 objects 名单，不给违规名单 | 成立，改成 `not_false` |
| 「记一次」没说是每次还是进程级 | 卡面两种读法都成立；本卡取"每次投影记一次"（不丢事件），并把口径写进断言消息与 §3 |
| 残余：`wallet.get(...)` 在 `data` 是列表时 `AttributeError` ⇒ 500 | 成立且**非本卡引入**（改前同一表达式在 `:259`）。用 MockTransport 复现出 `client.wallet 返回类型: list` → `'list' object has no attribute 'get'`，登 **P-128** 交回规划方，本卡不动 `providers/**` |
| 读数里两处数字没有支撑字节 | 成立：probe A 改成跑整文件，于是拿到 `1 failed, 7 passed`（原来只跑一条 id，"其余照旧绿"是我推的）；§0 的连通读数也补了原始输出 |

## 8. @ci（交付头 685e3f8）

三条均 completed success、attempt 1：CI 40458690795 / CI-Windows 40458690759 / Security 40458690827。逐字读数由 run 级 logs zip 现取并归档在 `s57_ci_green_readings.txt`：ubuntu 侧 pytest `2496 passed, 6 skipped, 4 deselected`、skip 门禁 `total_skipped=6 baseline=6` 且`pg_unreachable=0`、`Total coverage` 88.89%、`✅ 全部模块与全局达标`、vitest `53 passed (53)` 与`425 passed (425)`、演示态 e2e `31 passed`；@win 侧 `1810 passed, 692 skipped, 4 deselected`、门禁 `failed=0` 且 `total_skipped=692` = 基线、vitest 同 53/425。与本机第 4 跑对账：ubuntu 2496/6/4 逐字同数，@win 侧 1810 passed 也正好是上一卡的 1802 加本卡 8 条（新用例两侧都不连库）；覆盖率两侧分别是 CI 88.89% 与本机 88.91%（上一卡同期读数：CI 88.91% 见 `EVD-V21-56/s56_ci_green_readings.txt`，本机作废跑里出现过 88.90 与 88.94）——这点来回摆就是台账 P-104 记过的 ±1 行抖，可以拿它过线，不当精确判据。

## 9. 阻塞：关闭 `MeWallet` 需要一条当前门词汇表里不存在的登记（已登 P-129 交回）

五条红的测试 id 与逐字消息（全在 `s57_local_gates_run2.txt` 里）：

```
test_each_draft_def_is_explained_or_equal[shapes-MeView]
  shapes/MeView 与冻结稿不等且无登记：MeView: properties.wallet.additionalProperties 稿=True 生成=False
test_each_draft_def_is_explained_or_equal[shapes-MeWallet]
  shapes/MeWallet 与冻结稿不等且无登记：MeWallet: additionalProperties 稿=True 生成=False
test_every_domain_has_no_unexplained_divergence / test_comparator_does_not_false_positive
  [shapes] 同上两条（后者是"什么都没改 ⇒ 每域 0 条"的对照，被同一处差异带红）
test_draft_and_generated_agree_on_every_probe[shapes:MeWallet]
  shapes:MeWallet 稿与产物接受集不同（1 条探针），而登记种类=['documentation', 'structural']
  （只有 tightening / conflict 才允许接受集不同）
```

原因是真实的、也不是我藏得住的口径差：S57.3 把产物侧的 `MeWallet` 关闭，而冻结稿
`docs/任务规划V0.12.0/contracts/shapes.schema.json:385` 仍写 `"additionalProperties": true`，
同文件 `x-invariants` 第 7–8 行仍写着「除 MeWallet 外所有对象 additionalProperties=false」
「MeWallet 正常分支是主平台钱包对象原样透传，本仓不控键集合，故开放（P-121）」。
比对器要一条登记来解释这个差异，但两张表给出的答案互斥：

- `apps/api/tests/test_collection_contract.py:488`：`FACT_ALLOWED_KINDS["additionalProperties"] = {structural, strictness}`
  ⇒ `tightening` 与 `conflict` 都不能在这道门上解释这个事实；
- `apps/api/tests/test_contract_jsonschema.py:61` 把 `structural/serialization/strictness/documentation` 定义为
  「接受集不变」四类，同文件 `:409-413` 的 `assert changing` ⇒ 接受集真的变了（validator 实测 1 条探针两侧结论不同）
  就**只允许** `tightening`/`conflict`。

两边没有交集。走 `strictness` 能让第一道门闭嘴，但那是一条**声称接受集不变的登记**，而接受集确实变了——
这正是这些门在第六/八/九轮验证里专门要抓的「只有承诺、没有实现者」的装饰条目，属于判据自洗，本卡不做。
改冻结稿也不行：D-V21-20 明确「`docs/任务规划V0.12.0/contracts/**` 只有规划方能落笔」，而卡面字段 6 只给了
`shapes.py` 的 `MeWallet` 一个类。所以这不是「越界申报 + 改必要几行」能过关的情形，是卡面前提与裁决冲突，
按附录 A 第九节第 1 条（要改冻结契约含稿目录 ⇒ 停下交回）停在这里。熔断面：这是该判据的第 1 次 FAIL，
不到 2 次，停的理由是交回条款而不是熔断。

三条出路请规划方择一（本卡不猜）：

1. **改稿**：规划方把 `docs/任务规划V0.12.0/contracts/shapes.schema.json` 的 `MeWallet.additionalProperties`
   改 false 并订正 `x-invariants` 那两行——一步到位，不动任何门的词汇表，也让稿重新等于"我们想要的形状"。
2. **加一档 kind**：裁"模型侧关闭一个稿曾声明为开放的对象"该用哪种登记（要同时改
   `FACT_ALLOWED_KINDS["additionalProperties"]` 与 `SAME_ACCEPTANCE_KINDS` 的口径，那是门的语义，归规划方）。
3. **只发一半**：本卡只发 `_project_wallet` 投影（S57.1/S57.2 已完成且绿），`MeWallet` 暂留开放，
   等稿更新之后再补封闭那一半——但这与 D-V21-17「契约改为封闭对象」的裁决文字不一致，需要明确改判。

**现在的落点**：代码一行没提交，main 仍停在 `52673f2`（三绿）。交付字节的整份快照存在
`s57_pending_code.diff`（含新用例文件 `test_me_wallet_projection.py` 的全文，用 `--no-index` 取，没动索引），
裁定到手就原样接上再跑门链。本卡新增的 8 条用例、契约收紧本身、以及演示态那条翻过来的断言都在里面。

## 10. 出路③ 之后的重新交付（第 2 轮）

规划方 2026-10-27 在 P-129 的三条出路里选定**第三条：本卡只发 `_project_wallet` 投影那一半，`MeWallet` 暂留开放**。按这条裁定做的事：

- **退回 HEAD 字节的是三个文件**：`apps/api/app/contracts/shapes.py`（`MeWallet` 仍是 `BaseModel` + `extra="allow"`，模块 docstring 也回到原样）、`packages/contracts/schemas/shapes.schema.json`（`MeWallet` 仍是那唯一一个 `additionalProperties: true`）、`apps/web/tests/s55-mock-runtime-shape.spec.ts`（那条断言重新期望「开放对象多一个键放行」）。退回后用 `gen_contracts.py --check` 复验：15 个产物全部幂等一致，退出码 0 ⇒ 产物与源两侧一致，不是我手改的 JSON。
- **交付面因此只剩四处**：`app/services/auth/service.py`（`_project_wallet` + 白名单常量 + 三条分支同源于 `_WALLET_UNAVAILABLE`）、`tests/test_auth.py`（伪主平台的 `wallet_extra` 旋钮，默认空 ⇒ 既有用例字节不变）、新 `tests/test_me_wallet_projection.py`（8 条：1 条集成先红 + 7 条纯函数）、`tests/test_shapes_response_contract.py` 里那条普查用例的 **docstring**（正文一字未动，`open_defs == ["MeWallet"]` 仍是判据）。
- **§5 那两处越界申报随之不成立**（涉及的都回到了 HEAD 字节），本节上方保留原读数不删。
- **留开放的实际代价要写清，不能说这条已闭合**：后端不会再把契约外键带出去（这条由 8 条用例钉住），但契约侧仍是开放对象 ⇒ 演示态样例多写一个键、或前端 TS 类型这一层，都不会红。P-121 的"契约无法判形"那一半没闭合，只是从"会泄露"降级成"不会泄露但判不了形"；补那一半的前置是冻结稿那两行声明的更新（另开一张卡，P-129 裁定行里记着）。
- `s57_pending_code.diff` 是**第 1 轮**交付字节的快照（含被退回的 S57.3 那一半），不再是本卡的交付字节；第 2 轮的字节以本轮提交面为准。
- 熔断面：出路③ 之后本卡判据没有再 FAIL 过——第 1 轮那次 FAIL 是形状声明的落笔权冲突，已由裁定解除，不计作第二次同判据失败。
- **投影自身也留了一处没做的面，写清不藏**：可选键被上游显式发成 `null` 时（例如 `heldYuan: null`）本函数按「上游给了值」原样带出，只有必填两键做 `is None` 判缺。卡面 S57.2 的口径是「只取五键、没给的不补」，没规定给了 `null` 怎么办，本卡不自己扩大规则；契约侧仍开放 ⇒ 这道门现在也判不到它。补的那一步应和契约封闭同一张卡一起做（改成「值是 `null` 的可选键当缺席」，配一条用例），记在 P-129 裁定行的残留里。

## 11. 第 2 轮门链读数（交付字节 = 第 4 跑 `s57_local_gates_run4.txt`）

- **第 3 跑标成 superseded，不是回抄数字**：那一跑（`s57_local_gates_run3_superseded.txt`，链首尾字节指纹 f99f022a1f05daf2，15 步退出码全 0，pytest 2496 passed / 6 skipped / 4 deselected、TOTAL 88.92%、vitest 53 文件 425 passed、e2e 31 passed）跑完之后，第 2 轮复查又判出五处会被读成假话的文字（证据包标题、§4/§6 缺轮次标记、§5 的普查数句、`service.py` 的行号、新用例 docstring 里那句「契约当时」）⇒ 改动虽然是注释与文档行，字节确实变了，所以那一跑的读数不能当交付字节的读数用。这与第 1 轮那条「链在跑就不碰工作树」是同一条规矩的另一半：**改过字节就重跑，不改数字去迁就旧读数**。

- **第 4 跑（本轮交付字节）**：链首尾字节指纹同为 1343902a7ee8ccad（`fp_stable=YES`）⇒ 全程一份字节，中途没人（包括我）动过工作树。15 步退出码全 0：

- `pgpreflight` 0（先按夹具路径连上 PG@5547）、`ruff`（app tests ../../scripts）0、`mypy` 0
- `alembic upgrade head` 0、`alembic heads` 单头 0、`gen_contracts.py --check` 0（退回后产物与源两侧一致）
- `check_docs_consistency` 0
- `pytest tests/ -q -rs --cov`：**2496 passed / 6 skipped / 4 deselected，0 failed**（上一卡收口时的 2488 + 本卡 8 条）
- 覆盖率门按附录 A 原样在仓库根跑、不设编码变量：`达标 88.91% ≥ 79.0% TOTAL` 与 `✅ 全部模块与全局达标`
- 前端 `typecheck` 0、`contracts typecheck`（CI 的调用形）0、`vitest` `53 passed (53)` 与 `425 passed (425)`、
  `lint` 无告警、演示态 `next build` 编译通过、`playwright` mock e2e `31 passed (1.6m)`

skip 面：`6 skipped` 与 `SKIP_BASELINE` 同数；`SKIP_BASELINE_WIN`（692）不动——本卡 8 条新用例全不连库。
计数对账：第 1 轮那 5 条红随契约封闭退回而消失，总数正好是上一卡收口时的 2488 + 本卡 8 = 2496 ⇒ 没有用例被顺带改弱或删掉。覆盖率在 88.91 与 88.92 之间来回摆是台账 P-104 记过的 ±1 行抖（可以拿它过线，不当精确判据）。
