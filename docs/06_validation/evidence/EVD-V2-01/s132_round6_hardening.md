# S1.3.2 第六轮验证返工：四条新机制全被打穿，七类击败逐条钉成永久反证

批次：`STEP-01` S1.3.2/S1.3.3 返工第二轮。基线 `main@aedba58`（我提交 events 收编那次）。
验证者：`ageneral-purpose-6afcccc1603a3a13`，读法是当前工作树（它自己跑 `git show`/就地 pytest），
预算 30 次工具调用。判据：**T2 FAIL**（四类新机制可击败），T3/T4/T6 基本 PASS，T5 抓到两处数字读数错。
读数机器位：`@win` = 本机 Win10 + `apps/api/.venv`。

---

## 1. 它打穿了什么（七类，逐类附我的复现与修复后读数）

我先在自己这边复现，再改判据。探针是 `.staging/probe_r6.py`（临时目录、不入库；
它 import 比对器的判定函数，只在内存里改文档与登记表，不写任何仓库文件）。

| # | 击败方式 | 修复前 | 修复后 | 关它的判据 |
|---|---|---|---|---|
| G1 | 给带 `maxLength` 的别名发「不是形状」许可证 | compare_defs 绿 + narrow 绿 + absent 绿 | **红** | `_constraint_bearing()`：除 `type`/`$ref` 外任何校验关键词都算真约束；非法标记**不退出比对**，反而多出一条必红差异 |
| G2 | 删掉注释性 def 的标记（QueueMechanism / EventPayloadRules） | compare_defs 绿（只有 ManifestTransition 因为带 `enumStatus` 这种怪关键词才偶然红） | **红**（两处都红） | 缺席的 def 必须有三条正当去处之一：标记 / 被已收编 def 在**形状位**引用 / `ALIAS_WITNESSES` 见证。单靠一条 structural 登记不再放行 |
| G3 | 往 `x-fake` 注释位塞假 `$ref` 冒充"别名已内联" | 绿，且见证测试不再被触发 | **红**（真引用位撤掉的变体读到 3 条差异） | `_referenced_by` 只走形状位（`properties`/`items`/`additionalProperties`/分支/`$ref` 兄弟位） |
| G4 | `field` 写成 def 名（`field="PushRetryState"`）吞掉该 def 五类真漂移 | 五类全绿 | **五类全红** | `_explains` 第 3 道闸：`field` 里出现 def 名一律不解释；且这条登记不能靠"解释过差异"自证消费 |
| D8 | `kind="documentation" + field="types"` 解释属性级类型改动 | 绿 | **红** | 第 4 道闸 `FACT_ALLOWED_KINDS`（kind 首次参与判定）+ 第 5 道 `_direction_ok`；裸事实名只许"完整路径点名" |
| G5 | 现成登记已经在买"删除许可"：丢 `responseData`、丢 `WorkListRow.digest`、清空 `SessionClaims.required`（连必填 `sub` 一起丢） | 三类全绿 | **三类全红** | 第 6 道闸：`fb is MISSING`（产物丢掉稿有的东西）一律不放行；`required` 只接受"产物更严且增量全在被点名字段里" |
| G6 | 文档根整层没比过：产物根 `type` 改 string、稿根删 `type`、稿根加 `additionalProperties:false`；`$id` 两侧本来就不一致却无人记账 | 三类全绿 | **三类全红** | 新增 `_ROOT_VALIDATING_KEYS` 根层比对 + 方向规则（稿声明而产物不声明 ⇒ structural 可解释；反向或值不同 ⇒ 必须 conflict 并引台账）+ `_stale_root_entries`（登记说不等价而两侧现在一致 ⇒ 过期登记必红） |
| G7 | 物化默认值的**值**无人钉：`iss.default` 从 `""` 改成 `"PWNED"` | 绿 | **红** | `_is_empty_value`：只放行"稿没写 ⇒ 模型物化出一个空值"，非空值不是"物化"而是改契约 |

复现读数：修复前 16 条注入里 12 条读绿（`compare_defs=GREEN`）；修复后同一支探针只剩 **1 条绿**，
就是 G3 的**原版**——那条绿是**正确的**：`IdempotencyKey` 本来就有 `ALIAS_WITNESSES` 这条合法去处，
假引用没换来任何新放行。能证伪机制的是变体（撤掉真引用位），它读到 3 条差异。
这条留在文档里而不是"顺手也做成红"，因为我拒绝让反证测试去支持一个我并不能解释的读数。

## 2. 判据本身的变化（写清楚，免得后人以为只是加了几条断言）

- `_explains` 从"两条闸"变成**七条**：缺席只认 structural+点名；`field="*"` 在非空路径不解释；
  `field` 含 def 名不解释；裸事实名（`required`/`types`/`default`…）只许完整路径点名；
  `kind` 必须落在 `FACT_ALLOWED_KINDS[leaf]` 里；`_direction_ok` 要求方向与 kind 一致；
  产物丢东西一律不放行、产物凭空多事实必须完整路径点名。
- 新增第 6 种 `kind = conflict`：稿与实测**类型不相交**时不再冒充 `tightening`（宽严关系），
  而必须引一条**真实存在的台账裁决号**——`test_conflict_entries_cite_a_live_decision_id`
  拿 `docs/03_solution/decisions/decision-log.md` 反向核验。台账行被删 ⇒ 冲突重新变成待办。
- 生成侧：`_strip_titles` 递归剥掉派生 title（`response_data` → `"Responsedata"` 这类没人读的键）。
  **第一版我把稿件里真存在的字段 `title`（文章标题，`maxLength: 512`）一起删了**，
  门禁立刻报 `ArticleManifest: properties.title 生成=（无此键）`——我自己写的一刀切被自己的守卫当场抓住；
  改成"`properties` 的容器不当 schema 节点、只有它的每个值才是"。
- `MISSING` 哨兵的定义位置：它同时是 `_explains` 两个参数的默认值，而默认值在 import 期求值 ⇒
  必须定义在 `_explains` 之前。第一版放在后面，pytest 直接 collection NameError。

## 3. 我自己两处被证成的说法（不是它误判）

1. `08` §12.1 第一条我写"删标记 ⇒ 红，因为 `enumStatus` 是比对器不认识的关键词"。
   前半对、后半错：真让 QueueMechanism/EventPayloadRules 变红的是**缺席归属**那条测试，
   而 `compare_defs` 本身对删标记是绿的。我把偶然的红当成了机制的红。
2. §12.2 我写"92 → 加 events 域与 **8** 条新测试"。实测 `git show aedba58` 增加 **9** 个 `def test_`、
   收集到 **17** 条用例项（92 + 17 = 109）。数字又一次没复核就写了。
   另外 §12.2 的 `1.52s` 它跑两次都得 `2.14s` ⇒ 计时读数不作证据，之后我只报条数不报秒数。

## 4. 顺手补上的两条真事实（原稿里没人管）

- **`hot.py:192` 今天就违反 events 稿的 `x-rule`**：幂等键里塞 `uuid4().hex[:8]`，
  它自己的注释说动机是"已终结 job 不阻塞重跑"，与"禁止随机 uuid 当幂等键"直接对立。
  我第一版把这条注释的责任人写成"转 STEP-03 评审"——把"现在就冲突"讲成"以后再看"。
  现在钉成闭合清单 `KNOWN_UUID_IDEMPOTENCY_SITES`：新增一处必红，清单里的旧项若被修掉也必须更新
  （`test_random_uuid_idempotency_keys_are_a_closed_list`）。
- **`IdempotencyKey` 的 128 真正的执法者是 DB**：`entities.py:202` 是 `String(128) unique=True`。
  别名没有任何模型引用 ⇒ 128 在线上形状上无人执行，所以加
  `test_idempotency_key_bound_matches_the_column_that_enforces_it` 核对长度与唯一性。
- 三份稿的 `$id` 两套写法（collection 已被另一会话写成标识符式，identity/events 仍是文件位址式）
  ⇒ 登记 `D-V8-03`（默认统一到产物侧写法），并以 `conflict` 类挂住，不由比对器静默择一。

## 5. 读数

| 命令 | 结果 | 位 |
|---|---|---|
| `pytest tests/test_collection_contract.py -q` | `127 passed`（第六轮返工前 109；净增 18 条用例项） | `@win` |
| `pytest tests -q -k "contract or gen_contracts or schema"` | `131 passed, 1 skipped, 1059 deselected` | `@win` |
| 击败复现探针（修复前 / 修复后） | 12 条绿 / **1 条绿**（且那条绿是正确行为，见 §1） | `@win` |
| `ruff check app/contracts tests/test_collection_contract.py` | `All checks passed!` | `@win` |
| `mypy app/contracts` | `Success: no issues found in 4 source files` | `@win` |
| `gen_contracts.py --check` | rc=0，9 条幂等一致（6 dto.ts + 3 schema） | `@win` |
| `ruff check scripts` | 3 条**存量**错误在未收编文件里（`scripts` 不在任何 lint 面 = 已发布的 P-7，本批未动） | `@win` |

## 6. 本批**没有**做

- 没跑全量后端套件（本机一次 45 分钟无输出被我中止）。契约面读数以单文件 + `-k` 近邻子集为准，
  全量结论以推送后的 `@ci` 为准（run id + head_sha + conclusion 附在提交后的补记里）。
- `resources` / `api` 两域仍未起（D-V8-02 的 `ArticleKey` 3-vs-8 裁决行已登记，未执行）。
- S1.4.3 IDOR 生成器未动。
- 未把 `_walk` 的关键词表与 `FACT_ALLOWED_KINDS` 合并成单一真源——目前两处都要维护，
  一致性靠 `test_neither_side_uses_a_keyword_the_comparator_does_not_implement` 兜；这是已知冗余，不是已解决。
- 新机制仍**未经第七轮独立验证**：本文件全部是我自己的复现与判读，状态只能记 `部分确认`。
