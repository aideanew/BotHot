# EVD-V23-64 STEP-64 读数与判词（方案 A 尝试 → 方案 B 交付）

> 基线 main@480c073（D-V23-07 已生效，64/65 改派执行助手）｜交付头见本批提交
> 权威设计：`docs/任务规划V0.23.0/08-阶段A执行细则.md` §2；卡面 `STEP-64-UX八态契约归位.md` 第 13 格 ①
> 结论口径：**P-80 部分闭合**（理由见 §7）、**P-139 未闭合**（理由见 §7.2——本版只碰 ux 一域，且 B 档的新测试自己又新增了一处硬编码历史目录引用）

---

## 1. 原子步读数

| 原子步 | 判据 | 读数 | 判定 |
|---|---|---|---|
| S64.0 选路探针 | 未改前既有契约测试全绿 | `test_contract_jsonschema.py` 单跑 **81 passed**；与 `test_contract_def_coverage.py` 并跑 **92 passed**；`test_collection_contract.py` **219 passed** | 起点可信 |
| S64.0 判 A/B | `DOMAINS` 能否表达"域键 ux、稿名 ux_states、产物名 ux" | 能（稿名来自元组第一项，产物名是 `f"{域键}.schema.json"`）⇒ 按 08 §2.1 判 **A** | 先按 A 执行 |
| S64.1–S64.4 方案 A | 全绿三段链 | A 的四处字节全部落过地（`app/contracts/ux.py`、生成器两行、`schemas/ux.schema.json`、`src/ux/dto.ts`、`index.ts`、`test_contract_jsonschema.py`），随后 **`test_collection_contract.py` 7 条红**——其中 **3 条是 `note` 硬堵、4 条是我没补的登记缺口**（逐条性质见 §2）⇒ 依卡面 13 ① 转 B，**A 的四处字节全部回退** | 转 B |
| S64.2(B) 活体锚 | `states.ts` 内 `UX_STATES` 与冻结稿逐值同序 | 8/8 同序相等，见 `s64_b_6_enum_crosscheck.txt` | ✅ |
| S64.3(B) 先红 | 少一值必红、乱序必红 | `s64_b_1_red_seven_values.txt`、`s64_b_2_red_reordered.txt` | ✅ |
| S64.4 门禁不动 | `gen_contracts --check` rc 0、生成器零改动 | rc **0**；`git status` 里 `scripts/gen_contracts.py` 无条目 | ✅ |
| S64.5 证据 | 本目录 | `s64_*` 全部原文（目录内文件即判据，不写份数——份数本身就是会漂的数） | ✅ |

---

## 2. 方案 A 为什么堵死（这一段是 B 的合法性来源，不是事后找台阶）

A 落地后 `test_collection_contract.py` 读 **7 failed / 216 passed**，原文在 `s64_a_blocked_7failures.txt`。
**复核者抓到我把这 7 条一律写成"`note` 的下游"——那是虚报。** 逐条重读原文：其中 **3 条是硬堵点**
（`note` 簇），**4 条是本可以在允许面内补登记就消掉的缺口**（登记面就是 `apps/api/app/contracts/ux.py`
里的 `CONTRACT_DIVERGENCES`，那是卡面第 6 格允许新建的文件）。

| # | 失败测试 | 原文首因（逐字摘）| 性质 |
|---|---|---|---|
| 1 | `test_neither_side_uses_a_keyword_the_comparator_does_not_implement[ux-稿-ux_states.schema.json]` | `ux.稿.State: 比对器不认识关键词 'note'（要么实现它，要么改一侧——不能忽略）` | **硬堵**：三条出路分别撞 D-V23-06（改比对器＝动门禁）、D-V21-20（改冻结稿）、以及它自己那句（不许忽略） |
| 2 | `test_every_domain_has_no_unexplained_divergence` | `[ux]` 之下两行与 #1 同字（`compare_defs()` 把 note 当差异返回） | **硬堵**（同一个 `note`） |
| 6 | `test_comparator_does_not_false_positive` | `{'ux': ["…'note'…", …]} != {'ux': []}` | **硬堵**（同上） |
| 3 | `test_normalizations_used_are_all_backed_by_registry` | `ux: 归一 definitions-vs-refs-dialect 被用到，但登记表里没有**同名**条目认领它` | **登记缺口**——而这条正是卡面 13 ① 说的**键形**那一半：键形不致"无法比对"，但它确实要求一条登记 |
| 4 | `test_registry_rules_are_all_consumed` | `ux: 根层 type 不等价（稿=object 生成=（无此键））却没有方向合法的登记` | **登记缺口**（补一条 `structural` 的文档根登记即可） |
| 5 | `test_every_x_keyword_on_an_absorbed_def_is_claimed` | `ux/State: 注释键 x-required-for-every-core-view 在登记表里无人认领` | **登记缺口**（补一条 `documentation` 认领即可） |
| 7 | `test_document_root_divergences_are_named` | 与 #4 同字 | **登记缺口**（与 #4 同一条登记） |

诚实的结论是两句而不是一句：**A 不是"七条都过不去"，而是"四条我还没补、三条补不了"**。
补不了的三条（`note` 簇）决定 A 的死活 ⇒ 转 B 的判断不变；但我当时把七条一起记成 `note` 的下游，
等于把"执行侧没做完的登记"写成"门不让做"——那是同一族病（把未完成记成外部约束），进 §9 第 8 行。

关键的**结构性堵点**不在登记表，而在"要不要给 ux 建这张比对表"：
`test_collection_contract.py::test_generated_artifact_matches_current_model`
（HEAD 字节 `:3465`；我加过 ux 行的那次跑在 `:3474`）的 `assert set(fresh) == set(DOMAINS)`
把"生成器覆盖的域"与"本文件的逐 def 比对域"钉成同一个集合。反证原文 `s64_a_reverse_proof_no_ux_row.txt`：
把 ux 留在生成器里、从比对表里删掉，立刻红
`生成器覆盖的域与域表不一致：[… , 'ux'] vs [… ]`。

⇒ 因果链：**域进生成器 ⇒ 必须为它建逐 def 比对行 ⇒ 比对行一走就读冻结稿 ⇒ 冻结稿带 `note` ⇒ 必红**。
"建比对行"这步在允许面内（加行本来就是被允许的），撞死在下一环上。
卡面 13 ① 预写的出口就是这一类，故转 B **不算阻塞**。

### 2.1 与卡面措辞的偏离（照实记，不圆）

卡面 13 ① 把这一路写成"冻结稿的 `definitions` 与产物的 `$defs` **键形**使逐 def 比对无法成立"。
现读这句**对了一半**：

- **对的那半**：键形差异确实进了比对，并因此要求一条归一登记——`#3` 的
  `归一 definitions-vs-refs-dialect 被用到，但登记表里没有同名条目认领它` 就是它（`_defs_of()`，
  `test_collection_contract.py:162`，把 `$defs`/`definitions` 按同一语义处理，注释写明"两种方言并存是稿子内部的不一致"）。
- **错的那半**：它把"无法成立"写成键形造成，实际**不可满足的是关键词**——`note` 既不在
  `SUPPORTED_VALIDATING_KEYWORDS`、也不在 `STRIPPED_KEYWORDS_TO_RULE`、也不在 `_NON_CONSTRAINT_KEYS`，
  又不以 `x-` 开头 ⇒ `_walk` 直接记一条"不认识关键词"。键形只需登记，关键词需要有人改稿或改门。

⇒ **后果句成立**（"逐 def 比对无法在不改冻结稿的前提下成立"），**原因句指错了主体**。
本批按后果句走 B；两句的订正一起交回规划方（P-142 第二条），措辞已按现读改过来。

---

## 3. 方案 B 的落地物（三个文件，逐文件对允许面）

| 文件 | 内容 | 卡面第 6 格依据 |
|---|---|---|
| `packages/contracts/src/ux/states.ts`（新增） | `UX_STATES` 8 值字面量 + `UxState` 类型；头注写清"手写常量、不是生成物、为什么不是 A" | 「`packages/contracts/src/ux/**`（新增）」——08 §2.3 的第 1 项就落在这条允许面里 |
| `packages/contracts/src/index.ts`（仅导出） | 加 `export type { UxState } from "./ux/states";` 与四行说明 | 「`packages/contracts/src/index.ts`（仅导出）」 |
| `apps/api/tests/test_ux_states_contract.py`（新增） | 四条判据（逐值同序 / 不许半接 / index 真导出 / 冻结稿只读） | 卡面 6 未列这一文件；依据是 08 §2.3 第 2 项明文要求"新增 `apps/api/tests/test_ux_states_contract.py`"，且 08 文件头写"卡面与之冲突时以本文件为准" |

`apps/api/app/contracts/ux.py`、`scripts/gen_contracts.py`、`packages/contracts/schemas/ux.schema.json`、
`packages/contracts/src/ux/dto.ts`、`apps/api/tests/test_contract_jsonschema.py`、
`apps/api/tests/test_collection_contract.py` **全部回到 HEAD 字节**（`git status --short` 现读见 §9）。

---

## 4. 先红与召回（B 档）

| 序号 | 输入 | 期望 | 读数 |
|---|---|---|---|
| 先红 1 | `UX_STATES` 写成 7 值（删 `degraded`） | 判据 ① 红，且**两侧枚举都打出来** | `s64_b_1_red_seven_values.txt`：1 failed / 3 passed，报错里 `活体 [...]` 与 `稿 [...]` 并排 |
| 先红 2 | 8 值同集合但**乱序**（`degraded` 挪到第 7 位） | 判据 ① 红（证明"同序"真的在判） | `s64_b_2_red_reordered.txt`：`At index 6 diff: 'degraded' != 'unauthenticated'` |
| 还原 | 改回 8 值同序 | 全绿 | `s64_b_3_green_restored.txt`：4 passed |
| 召回（构造式） | 9 条：把模块里的路径常量/域表对象指到别处，逐条断言"该响的响" | 每条都红且原因正确 | `s64_b_4_recall_proofs.txt`：9 条全过，且还原后四条判据重新为绿 |
| 召回（真实工件） | 在生成物目录里**真的造一份**手写 `packages/contracts/schemas/ux.schema.json`，同一条命令里删掉 | 判据 ② 在真实路径上红 | `s64_b_7_recall_on_real_artifact.txt`：`test_ux_states_contract.py:92` 打 `assert not True`＋`where True = exists()`，删除后复跑 4 passed |

召回清单（脚本在 Temp，不进仓库）：八值下限（两侧同步削成 7 时等式仍成立，靠 `len` 判据兜住）／
活体锚文件缺失／字面量条目换单引号／同文件两条 `UX_STATES`／ux 进 schema 域表／ux 进 TS 域表／
生成物目录出现手写 `ux.schema.json`／`index.ts` 未导出 `UxState`／冻结稿 `note` 消失。

**复核者对召回的一条抓到点上**：构造式召回（把常量指到别处）证的是"这条 assert 会响"，
不是"我描述的那个前提会响"——`s64_b_4` 里"生成物目录出现手写 ux.schema.json"那条，实际打出来的是
`手写的 engine.schema.json`。已按这条补了真实工件版召回（`s64_b_7`，见上表），
剩下两条前提也各有**真实发生过**的跑背书：
"ux 进域表"⇒ `s64_a_reverse_proof_no_ux_row.txt`（ux 真在生成器里、比对行被删掉时读到的红）；
"活体锚文件缺失"⇒ §9 第 1 行那次路径事故（`states.ts` 真读不到，打的就是"八态活体锚缺失"）。

**为什么判据 ① 里"逐值等式"排在"恰为 8 值"前面**：08 §2.4 要求接红原文里"两侧 enum 都打出来"；
先判 `len` 只会打出被削的那一侧。顺序换过来之后，`len` 两条仍不是摆设——第 4 行的召回证明
"两侧同步削成 7"这种等式成立的形，照样被 `len` 判据红掉。

---

## 5. 判据清单（新文件实际判了什么）

| 判据 | 判的内容 | 反证 |
|---|---|---|
| `test_ux_states_literal_equals_frozen_draft_enum` | 逐值 + 同序 + 两侧各恰 8 值 | 先红 1、先红 2、召回"八值下限" |
| `test_ux_domain_is_not_half_wired_into_the_generator` | `ux` 不在 `CONTRACT_SCHEMA_MODULES` / `CONTRACT_TS_DOMAINS`，且 `schemas/ux.schema.json` 不存在 | 域表两条＝构造式召回 + A 的真实跑（`s64_a_reverse_proof_no_ux_row.txt`）；假产物一条＝**真实工件召回** `s64_b_7` |
| `test_index_ts_reexports_the_ux_state_type` | `index.ts` 里那一行导出逐字存在 | 召回一条 |
| `test_frozen_draft_is_read_only_for_this_card` | 冻结稿 State 仍带 `note` 与 `x-required-for-every-core-view` | 召回一条（A 的门一旦打开，这条先红，提醒重跑 S64.0） |

第 2 条是本卡里唯一"防将来"的判据：它的价值不是证明现在对，而是让"有人半路接 A 但不先解决 `note`"
这一步在 `pytest tests/` 里就红，而不是让 CI 的逐 def 比对器红成一团没人看得懂的形。

---

## 6. 卡面第 5 格七条验收的逐条判定（B 档）

| 条 | 原判据 | 判定 | 说明 |
|---|---|---|---|
| ① | 未改前既有 7 域契约测试全绿（基线读数入证） | ✅ | §1 第一行；基线是在**回退后的 HEAD 字节**上复测的，所以它同时是"未改态"与"A 已清干净"两个读数 |
| ② | 故意把 `State` 写成 7 值 ⇒ 新断言必红，原文入证，随后还原 | ✅（对象换形） | B 档下"写成 7 值"的落点是 `UX_STATES` 字面量，不是 Pydantic Enum；先红 1 |
| ③ | 还原后该断言绿 | ✅ | 4 passed |
| ④ | `gen_contracts.py --check` rc 0 | ✅ | rc 0；且生成器本卡零改动 |
| ⑤ | schemas 下除新增 `ux.schema.json` 外其余 7 份字节零变化（`git diff --stat` 只 1 个 `+` 行） | ⚠ **含义降级达成** | 现读：该目录 **7 份、无新增、`git diff --quiet` rc 0**。B 不产 schema 产物，所以"零变化"是靠"什么都没产"满足的，不是靠"只动一个文件"满足的——这是部分闭合的第一处 |
| ⑥ | `apps/web` 的 `tsc --noEmit` rc 0 | ✅（并加跑一条） | rc 0；另跑 `ci.yml:381-382` 的契约包整包 strict 也 rc 0——那条是判这份新 `.ts` 的真门，卡面没列 |
| ⑦ | 冻结稿字节零变化（`git diff --quiet` rc 0） | ✅ | rc 0 |

**但"验收七格过了"不等于"这张卡的目标达到了"**：第 3 格的目标句写的是
「`packages/contracts/schemas/` 下存在一份 ux 形状产物，其 `$defs.State.enum` 与冻结稿逐值同序」，
B 档**根本不产那份产物**——这一句是明确未达成，不是"降级达成"（区别在于：降级达成的是判据 ⑤，
未达成的是目标本身）。第 4 格七项输出里 ①②③④⑥ 五项没做、⑤⑦ 做了。
所以卡面状态行写的是「✅ 已交付（转 B）」而**不是**「✅ 已达成目标」，且 P-80 只记部分闭合。

---

## 7. P-80 记"部分闭合"的口径

**闭合的那一半**（可判、有活体源、有门禁盯着）：八态**取值集合与顺序**从此在仓里有了一份被
`pytest tests/` 核对的活体锚；冻结稿从"唯一源"降级为"被核对方"；消费侧可以通过
`import type { UxState } from "@bothot/contracts"` 拿到它，不必再去 `docs/任务规划V0.12.0/` 里抄路径。

**没闭合的那一半**，三条都写清楚：
1. **没有机器可校验的形状产物**：`packages/contracts/schemas/` 下不存在 `ux.schema.json`，
   `packages/contracts/src/ux/` 下不存在 `dto.ts`。卡面第 3 格的目标句（"其 `$defs.State.enum` 与
   冻结稿 `definitions.State.enum` 逐值且同序相等"）在 B 档下**无法满足**，因为那一半的前提就是 A 成立。
2. **`StateRendering` 五字段形状仍在冻结稿单点**：本卡没有为它建活体源。给它手写一份 TS interface
   只是再造一份没人消费的散文副本（本包纯类型、无消费方），故刻意不做。它的归宿要规划方定（P-142）。
3. **`x-core-views` 六视图的叙述那一半**照 08 §1 留在冻结稿，不算缺口，但也不算闭合。

⇒ 卡面、`04` 卡表、`07` 记录与本文件一律写 **部分闭合**，不写"闭合"（08 §2.3 的诚实标注要求）。

### 7.2 P-139 判「未闭合」，且本卡新造了一处它的实例

P-139 说的是**契约的"稿"住在已归档的版本目录里、测试按硬路径读它**这件事；台账给本版划的范围是
「STEP-64 只做 ux 一域，目录级搬迁不属本版」。现读判定：

- ux 这一域的 `DRAFT_DIR` 问题**原样保留**——`test_contract_jsonschema.py:45` 回退到 HEAD 字节，仍指历史目录；
- 更难看的是：**B 档的新测试自己又多写了一处**。`apps/api/tests/test_ux_states_contract.py:30` 的
  `FROZEN_DRAFT = REPO_ROOT / "docs" / "任务规划V0.12.0" / "contracts" / "ux_states.schema.json"`
  就是 P-139 那个病因的**第二个实例**：历史目录一旦改名，这条判据会红在"冻结稿缺失"上——
  报出来的是"文件不存在"，而排障的人仍要从这个路径反推出"某次历史版本归档动了目录"这个成因。
  比静默变绿好，但没好到能自称"已把契约锚归位"。
  为什么不绕开它：B 的判据本质是"活体锚 ↔ 冻结稿逐值同序"，不读稿就没有被核对方；
  而把路径抽成常量再指去别处，需要的是**目录级搬迁**那支笔（规划方）。
- ⇒ P-139 记 **未闭合**，并把"本卡新增了一处引用点"作为自曝写进 P-142 第五条，而不是等复核时发现。

---

## 8. 交回规划方（P-142 的五条，这里给指针不重抄）

| P-142 条 | 内容一句话 | 本文件位置 |
|---|---|---|
| 一 | A 走不通的机械闭包（`:3474` 强制比对行 → 冻结稿 `note` → 三条出路各撞一条纪律） | §2 |
| 二 | 卡面 13 ① 的**原因句指错主体**：键形那一半只需登记（`#3` 的归一认领），不可满足的是关键词 `note`；后果句成立 | §2、§2.1 |
| 三 | 08 §5 第 2 行的 B 档 import 路径 `@bothot/contracts/ux/states` 在本仓不可解析 | 本节下方展开的第 2 条 |
| 四 | B 不产 `ux.schema.json` ⇒ STEP-60 增量的新增验收 ① 照原文执行必红 | 本节下方展开的第 3 条 |
| 五 | 本卡的新测试自己新增了一处 P-139 实例（硬编码历史目录） | §7.2 |

下面三条是 P-142 第 二／三／四 条的展开（写给 65／60 的执行者，别去找不存在的解析路径）：

1. **A 的堵点是关键词不是键形**：要么由规划方处置冻结稿 `definitions.State` 的 `note`
   （改名 `x-note` 即可与 `x-required-for-every-core-view` 同走"注释键认领"那条既有出路，那是不动比对器的最小改动），
   要么在 `08` §2.1 的判据表里把"稿侧带比对器未实现关键词"明列为 B 的触发条件之一。
2. **08 §5 交叉影响第 2 行的 B 档 import 路径在本仓不可解析**：写的是
   `import { UX_STATES } from "@bothot/contracts/ux/states"`，但 `packages/contracts/package.json`
   的 `exports` 只有 `"."`，`apps/web/tsconfig.json:27-33` 的 `paths` 只映射裸标识符
   `@bothot/contracts`，且本包纪律是纯类型消费（`src/index.ts` 头注第 1 条）。⇒ STEP-65 请用
   `import type { UxState } from "@bothot/contracts"`；需要在运行时枚举八态的地方，按
   `test_ux_states_contract.py` 的做法读字面量，**不要**值导入。
3. **STEP-60 的枚举来源在 B 档下没有产物**：`steps/STEP-继承卡增量-V0.23.md` 给 60 的 5 格新增第 ① 条
   "若 `ux.schema.json` 不存在或读不到 `$defs.State.enum` ⇒ 红（不得回退成硬编码数组）"。
   B 档不产该文件 ⇒ 60 照增量执行必红。建议改为读 `packages/contracts/src/ux/states.ts` 的
   `UX_STATES`（那不是硬编码，是同一份活体锚）；这条改判需要规划方落笔或授权执行侧落笔。

---

## 9. 交付面自查（`git status --short`，本批全部非文档条目）

裸跑 `git status --short` 会把新建目录收成一行 `?? packages/contracts/src/ux/`；
点名到文件更准（`git status --short packages/contracts/src/ux/states.ts apps/api/tests/test_ux_states_contract.py packages/contracts/src/index.ts`）：

```
 M packages/contracts/src/index.ts
?? apps/api/tests/test_ux_states_contract.py
?? packages/contracts/src/ux/states.ts
```

`scripts/gen_contracts.py`、`apps/api/tests/test_contract_jsonschema.py`、
`apps/api/tests/test_collection_contract.py`、`packages/contracts/schemas/**`、
`apps/api/app/contracts/**` 均无条目 ⇒ A 的四处字节回退干净。
执行过程中我自己出过的错（都已修，不圆场）：

| # | 错 | 后果 | 怎么被抓到的 |
|---|---|---|---|
| 1 | 新测试里 `REPO_ROOT` 写成 `parents[2]` | 4 条判据全读 `apps/docs/…` 不存在 | 第一次跑就红；红的原因是 FileNotFoundError 而不是"值对不上"，一眼可辨 |
| 2 | `git status --short -- ../packages/contracts/schemas` 在 `apps/api` 下跑 | 打印了"空即零变化"，但那是 `no such directory` 的空 | 写证据时发现 warning 与"零变化"并存 ⇒ 空输出不是证据，回仓库根重测（`s64_b_5_gate_readings.txt` 里有订正段） |
| 3 | 判据 ① 起初先判 `len` | 先红原文只打得出被削的一侧，不满足 08 §2.4"两侧都打出来" | 跑第一次先红时看原文自己对不上要求 ⇒ 调顺序并补一条召回 |
| 4 | 480c073 提交信息把 `92 passed` 记成"既有 7 域契约测试"的读数，而 08 §2.1 写的命令是单文件 | 读者按单文件复算会读成 81，误以为基线漂了 | 本轮复测两个命令 ⇒ 已在 `s64_b_5` 里按现读订正，不回改已提交原文 |
| 5 | 误删 `_gen_contracts()` 函数体（编辑事故） | 文件一瞬间语法不完整 | 立即补回并全文复读 + `py_compile` + 4 passed |
| 6 | 写收口文档的脚本把 `docs/任务规划-索引.md` 那张表按 **5 列**假设 | 脚本在改索引前非零退出（前三处已写、第四处未写） | 脚本里的 `assert len(cells)` 挡住了 ⇒ 先看表头再改假设（实读 6 列），没造成错改；这条记下来是因为**它是一次"假设布局"的错**，与 `feedback-evidence-probe-self-lies` 同一族 |
| 7 | 测试文件头注写「本文件判三件事」而实有 4 条判据 | 门面文字与判据数不符（本仓的旧病） | 提交前自查改为「四件事」并补 ④ 那条的判据说明 |
| 8 | **§2 把七条红一律归因成 `note` 的下游**，实际其中 4 条（`#3/#4/#5/#7`）是本可以在允许面内补登记的缺口 | 把"执行侧没做完"写成"门不让做"——这是本卡最重的一处虚报，因为它正是 B 的合法性来源那段 | 只读复核者抓到；逐条回读 `s64_a_blocked_7failures.txt:61/134/153/188` 后重写 §2 ⇒ 转 B 的判断不变（`note` 簇三条仍无解），但措辞改为"四条我没补、三条补不了" |
| 9 | 三处行号引错：`test_collection_contract.py:3474`（HEAD 字节实为 `:3465`，`:3474` 是我加过 ux 行那次的号）、`_defs_of()` 写成 `:171-178`（实为 `:162`）、`test_ux_states_contract.py:28`（改头注后漂到 `:30`） | 一行号错就会被读成"这份证据是抄的"；本卡的 P-140 抱怨的正是这件事 | 复核者抓到 + 本轮逐条 `grep -n` 现读订正；同时把判据改为**优先点测试名**（`::test_generated_artifact_matches_current_model`），行号只作辅证 |
| 10 | 召回里有两条把模块常量指向别处（`does_not_exist.ts`、`engine.schema.json`），却写成"生成物目录出现手写 ux.schema.json"这类前提 | 证的是"assert 会响"，不是"描述的那个前提会响" | 复核者抓到 ⇒ 补 `s64_b_7`（真造一份 `ux.schema.json`、跑、删、复跑 4 passed），另两条前提改由真实发生过的跑背书 |
| 11 | 证据里写了"6 份原文"这类可数数（实际当时已 8 份，还会随补证增加） | 可数的数最容易漂——本仓已为此记过 P-104/§9 第 4 行 | 改为不写份数，只写"`s64_*` 全部原文" |
| 12 | `07` 行里的三个 run id 只在聊天与 Temp 里，仓内没有任何文件背书 | 读 `07` 的人无法复核"基线三绿"这句 | 把 REST 读数落进 `s64_0_base_ci_readings.txt`（含 6 个 job 结论与 `e2e-real` 的 failure 行），`07` 行的句子改为指向该文件 |

**复核者意见的处置**（接与驳都要留痕）：第 8/9/10/11/12 条全部**接**并已改；
另有一条**驳**——复核者说 `test_contract_jsonschema.py` 的 `DRAFT_DIR` 应在 `:44`（引 P-140 口径），
现测该常量的赋值行在 **`:45`**，且台账 P-139 与 `docs/任务规划-索引.md:43` 引用的也都是 `:45`
（`grep -n "DRAFT_DIR =" apps/api/tests/test_contract_jsonschema.py` ⇒ `45:`）⇒ 这条不改。

---

## 10. 本机未证明、须由 @ci 取的事

| 事 | 为什么本机不取 | 出处 |
|---|---|---|
| `Contract drift gate (gen_contracts --check)` 步绿 | 本机已跑同命令 rc 0，但卡面 10 格的 `@ci` 面是 CI 的步序 | `ci.yml:138-139` |
| 后端全量 `pytest tests/` 的新总数 | 卡面 6 格只要求单卡面测；全量按 D-V22-01 留到阶段体检/发版 | `04` §6 |
| CI-Windows skip 基线 | 本卡新增 4 条**全不连库** ⇒ 692 不该动；若动了说明有别的东西进来了 | 台账纪律 |
