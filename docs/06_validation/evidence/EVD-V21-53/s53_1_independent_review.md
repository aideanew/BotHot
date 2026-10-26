# EVD-V21-53 S53.1 独立复查：STEP-46 与 STEP-47（卡面第 6 格判据①）

> 结论：**STEP-46 = PASS（带 nits）**、**STEP-47 = PASS（带 nits）**，无 FAIL、无 UNKNOWN ⇒ 判据①满足，允许发版。
> 复查时间 2026-10-26 19:31–19:46（Asia/Shanghai），提前于发版批执行；被复查的两项交付分别是
> `9816f7f`（STEP-46，混装本版规划文档批）与 `f4f0261`（STEP-47），收口批 `fa276c6`/`b4157a9` 都是纯文档。

## 一、方法与局限（先说清楚"凭什么"）

- **只读复查**：两份子智能体回报（提示词各自独立，第二份把约束收紧后重跑）+ 我自己的锚点复核。
  两次回报的结论一致，且都明确"没有规定的产物在当前字节里缺失"。
- **不跑套件**：复查期间本机门链在跑（CPU 独占），所以判据②"运行结果"取的是**已归档的 @ci 读数**，
  不是我重新测的数。这一点是这次复查的真实局限：凡靠运行才成立的判断，都由三绿的 CI 步骤承担。
- **只看 diff + 当前字节**：`git show`/`git diff` + 现读文件，不采信任何"报告里说做过"。
- 我逐条自己复核过的锚点列在每节末尾（`file:line` 现读，不是抄回报）。

## 二、STEP-46 引擎域响应形状契约链

判据（卡面第 6 格）逐条：

| 判据 | 判定 | 依据（当前字节） |
|---|---|---|
| ① `gen_contracts.py --check` 覆盖到新生成的 TS | **成立** | `scripts/gen_contracts.py:298` `CONTRACT_TS_DOMAINS`（含 engine 域）→ `:351` 逐域派生 → `:436` 目录冲突即报错；`check()` 对契约派生的 `dto.ts` 做字节比对，且 `main()` 用位或避免短路（第一个红不会被第二个盖掉）。产物 `packages/contracts/src/engine/dto.ts` 存在、`.gitkeep` 已删、无 `unknown` |
| ② 契约用例（3 不连库 + 2 连库） | **成立** | `apps/api/tests/test_engine_response_contract.py:43/:50/:56` + 后两条连库；`EVD-V21-46/s46_readings.md:20` 的"18 passed"可分解为 5 + `test_p4_engines.py` 的 13（该文件 testdef 恰 13 条） |
| ③ 真端点反向核 | **机制仍在**，但**当时的探针没有留裸读数** | 判据实体在（连库用例校验端点 `data`），且 `apps/api/app/api/v1/engines.py` 自 `9028b89` 起未被任何提交改过（`git log` 空）⇒ 反向核可复现。EVD-V21-46 目录只有 `s46_readings.md` 一份，反证 ③④ 是**文字陈述**，没有 `.txt` 原文（对照 STEP-47 留了两份） |
| ④ TS1360 探针 | **探针文件按当时的口径"不入库"** | 但牙齿现在长在常驻面上且更强：`apps/web/lib/api/mock-routes.ts:196/:208/:220/:232/:244/:251` 六处 `satisfies`（EngineCapability/EngineList/SpaceEngineBinding），由 `ci.yml` 的前端 tsc 步骤判（STEP-48 落地的） |
| ⑤ 不动 `test_contract_jsonschema.py` | **成立** | `9816f7f` 的文件清单里没有它；引擎草稿与产物的 def 名集都是 `{EngineCapability, EngineList, EngineReason, SpaceEngineBinding}` ⇒ 交集不掩任何一条 |
| ⑥ 三绿可归因 | **成立** | 卡面与证据里的 run id 逐字相同；`fa276c6` 纯文档 ⇒ 读数挂在 `9816f7f` |
| 禁止修改（不动端点/服务层） | **可证** | `git diff 9028b89 HEAD -- apps/api/app/api/v1/engines.py` 为空 |

我自己复核过的锚点：`gen_contracts.py:298/:351/:436`、`test_engine_response_contract.py:43/:50/:56/:60`、
`ci.yml:138-139`（Contract drift gate 在 backend job 内 ⇒ 那条 job 的成功覆盖了判据①）。

判 **PASS** 的最强理由：卡面规定的产物与门全在当前字节上，且数字与三绿可对账。
留下的 nits（都改不了"做完"这件事，但会漏未来的漂移）：

1. `test_engine_response_contract.py:60` 只断言子串 `f" {name} "` ⇒ 名字出现在生成物头注释里也算过；
   同族 STEP-47 的兄弟用例（`test_shapes_response_contract.py:88`）用的是正则。
2. **引擎域没有覆盖面守卫**：STEP-47 的静态守卫显式减掉 `ENGINE["$defs"]`（`:374`），
   而 STEP-46 自己没建同类守卫 ⇒ 把那两条连库用例删掉，链仍绿。
3. `test_contract_jsonschema.py:274` 取 `set(草稿) ∩ set(产物)` 而非名字集相等 ⇒ 模型多出一个草稿里没有的
   def 会整片不进比对（现读该函数确认：`for name in sorted(set(_defs(draft)) & set(_defs(gen)))`）。
4. 反证 ③④ 缺裸读数原文（判据方向正确，但按 D-V4-03 那套"证据的效力只在有人复跑时存在"的标准，
   文字陈述弱于产物）。

## 三、STEP-47 其余域响应形状契约

| 判据 | 判定 | 依据（当前字节） |
|---|---|---|
| ① 22 条 mock 路由 ↔ 契约名机器表 + 逐条对名 | **成立** | 权威表 `apps/api/app/contracts/shapes.py:340-363` 恰 22 条；`test_shapes_response_contract.py:105-118` 断言条数、首个命中、单射与索引集相等（数量或形制一变就响亮地红），`:121-124` 要求每个登记名都是真 def。前端侧的对齐不靠我数原文（`mock-routes.ts` 里 `method:` 字面出现 27 次、`pattern:` 23 次，含接口字段声明与其它代码），而是由常驻判据钉住：`s52-mock-contract-coverage` 三条用例断言"归一键数＝注册路由数＝表条目数≥22"，注册路由数现值 22 ⇒ 两侧逐条一一对应 |
| ② 真端点反向核 | **成立，但"17 条"是文件级用例数不是反向核处数** | 该文件共 **17 条用例**：5 条静态牙齿（`:56/:63/:72/:77/:85`）+ 2 条表判据（`:105/:121`）+ **7 条连库真端点**（`:158/:185/:214/:228/:261/:284/:343`）+ **2 条桩端点**（`:307` 的 resolve/extract、`:326` 的 me 正常支与 logout，依赖上游客户端替身）+ 1 条覆盖面守卫（`:368`）⇒ **响应反向核是 9 处**，其中 2 处打的不是真端点；静态守卫 `:368-377` 会红（删掉任一 `_check("X"…)` 即红，不恒绿）；元素层/可选键非空判据在 `:172/:196/:225/:253/:297/:323` |
| ③ 契约漂移门 + skip 基线 | **成立** | `test_contract_jsonschema.py:51` 与 `test_collection_contract.py:103-110` 登记 shapes；草稿与产物 def 名集都是 30；`SKIP_BASELINE_WIN=692` 的 +7 锚注记逐字列出那 7 条连库用例 |
| 数字可归因 | **成立** | 17 = 5 牙齿 + 2 表 + 7 连库 + 2 桩 + 1 守卫（与"无库时 10 passed / 7 skipped"对得上）；卡面 run id 与证据一致；`b4157a9` 纯文档；`git diff f4f0261^ f4f0261 -- app/api app/services app/core` 为空 ⇒ 零路由/服务改动 |

我自己复核过的锚点：`test_shapes_response_contract.py:374` 的守卫表达式
（`expected = set(MOCK_ROUTE_CONTRACTS.values()) - set(ENGINE["$defs"])`）、
`$ref` 闭包可达性：**22 条登记去重后是 21 个类型名**（`POST /spaces` 与 `GET /spaces/{id}` 共用
`SpaceDetail`），其中 19 个在 shapes、2 个（`EngineList`/`SpaceEngineBinding`）在 engine 域；
从这 21 个名字沿 `$ref` 下钻，**shapes 的 30 个 def 全部可达、孤儿 0**（脚本实测）。
另核 `EVD-V21-47/s47_red_extra_key.txt:2` 的行号（见下面 nit 2），
以及 `docs/任务规划V0.21.0/02-需求复核与辩证分析.md:29` 仍写"前端 24 条 mock 样例"（现值 22）。

判 **PASS** 的最强理由：三条判据全在当前字节上被机器判着，且与三绿读数一致。
留下的 nits：

1. **新覆盖面缺口（已登记 P-126）**：反向核的覆盖面是按 mock 路由表反推的 ⇒ 一个既没被 mock 路由映射、
   也没被别的 def `$ref` 引用的 def，会照样进 `packages/contracts/src/shapes/dto.ts` 与 `index.ts`，
   没有任何一处真端点判它，且哪里都不红。今天 30 个 def 全可达 ⇒ **潜在面，不是现存缺陷**。
2. `s47_red_extra_key.txt:2` 把红钉在 `tests/test_shapes_response_contract.py:43`，
   而交付文件里 `_check` 的 assert 在 `:50`（`:43` 是空行，`_errors` 在 `:44-45`）⇒ 那份先红出自更早一版本；
   按纪律**不回改已归档原文**，只在这里注明。该文件也没记命令与用例名（"16 deselected"说明跑过 `-k`）。
3. 卡面 §34 的分组数标错（"6 牙齿/机器表 + 3 桩端点"，实际 5+2 与 2）；总数 17 不受影响。
4. `SpaceStats.chunks` 的非空位与 `MeView.qaFixture` 没有任何 live 判据（只有手造 dict 覆盖）⇒
   这两处契约位未被证明，也未被否证。
5. `docs/任务规划V0.21.0/02-需求复核与辩证分析.md:29` 仍写"前端 24 条 mock 样例"（现值 22）——
   文档纠真族（STEP-51 家族），交回规划方，本发版批不动（卡面第 9 格只允许 CHANGELOG 与 AGENTS 版本块）。

## 四、判据①的终判

`PASS / PASS` ⇒ 无 FAIL、无 UNKNOWN，**不触发卡面第 16 格的阻塞条件**，v1.1.3 可以发。
本次复查产出：新登记 **P-126**（台账，STEP-46/47 守卫家族的覆盖面缺口），
两条交回规划方的文档订正（`02-需求复核与辩证分析.md:29` 的 24→22；`EVD-V21-47` 那份先红的行号归属）。
复查之后到发版批之间，代码没再动过：`c8307f7`（STEP-55 收口批）到发版批之间只改 CHANGELOG/AGENTS 与本目录，
所以这份 PASS 对被 tag 的 head 仍然成立——这条在 S53.3 用 diff 复核入证。
