# S1.3.2 第五轮验证返工：三类比对器盲区 + 两处被证成的假话

批次：`STEP-01` S1.3.2/S1.3.3 返工（第五轮独立验证判 **FAIL** 之后的修复）
**+ 同批续做的 events 域收编**（§11 之后）。
基线：`main@983a356`（我提交 S1.1.2 ADR-0012 那一次）。
执行者与验证者都是子智能体，读数一律标机器位（`@win` = 本机 Win10 + `apps/api/.venv`）。

---

## 1. 第五轮验证交了什么（原文条目 → 我的处置）

验证者 `ageneral-purpose-904fd056cc0ba7be`，读法是 `git show 983a356:<path>`（不碰我的工作树），
`80 passed in 0.75s` 基线上又跑了 16 条单侧 + 3 条双侧注入。它的总判据是：
**S1.2.2 首域 + 比对器多域化 = conditional pass；比对器" totality（全捕）"= FAIL**。

| 它的点名 | 我的处置 | 落点 |
|---|---|---|
| 比对器三类盲区（`default`、tuple 形式 `items`、≥2 支非 pattern 的 `anyOf`） | 三类都补，并各钉参数化反证 | `_canon` / `compare_defs` |
| `field="*"` 的整片放行还能吞掉一个 def 的全部差异 | 非根路径上一律不解释；并加具名反证 | `_explains` |
| "解释过一处差异"被算作登记表的消费者 ⇒ 遮差异的登记自己给自己发合格证 | 消费判据收窄成"当归一用到"或"具名断言兑现"两档 | `test_registry_rules_are_all_consumed` |
| `kind` 从来没被校验值域 | 加 `DIVERGENCE_KINDS` + 核对测试 + 反证 | 同上文件 |
| identity 的 `UserId` 在登记表里被写成"约束被内联进使用处"，**实测没有任何使用处** | 文本更正 + 新增 `ALIAS_WITNESSES` 见证测试；并新增一条"消失的 def 必须有三选一的正当去向"总闸 | `identity.py` / `test_absent_draft_defs_are_accounted_for` |
| ADR-0012 §1 把 `subscription.py:130` 列成 `article_manifests.external_id` 的写入点 | 实测该行是 `Source(...)` 的 `external_id=external_id` ⇒ 改为 `manifest.py:144 → :156 → :255`，并把 `sources.external_id` 另立为**第四个键空间**写进注记 | `adr-0012-…md` |
| `test_generated_artifact_matches_current_model` 硬编码 `["collection"]` ⇒ identity 域"模型 ≠ 产物"的窗口本地无门禁 | 改成遍历 `DOMAINS`，并断言生成器覆盖的域集合 == 域表 | 同名测试 |
| 文档里的数字读数腐烂（"6 条"vs 9、"11 类"vs 15、"两处必要改动"vs 3） | 见 §8 更正表；并把"计数不写进文档字符串"立成本文件的规矩 | §8 |

## 2. 三类盲区各自怎么补，以及"补住了没有"的反证

### 2.1 `default`：从人读面挪进校验面

根因不是漏了一个关键词，而是**分类错**：`default` 当时挂在 `STRIPPED_KEYWORDS_TO_RULE` 里
（那张表的语义是"文本不同不构成契约差异"），于是比对器两侧都不看它。第五轮验证的
I10/I10b/X3 三条注入（稿侧加 `default=[]`、生成物侧把 `exp.default` 改 0、两侧写成 A/B）
全部读 0 条差异——等于"默认值这一整类契约事实不在门禁管辖内"。

补法分三层，缺一层都还能绕：
1. **进事实面**：`default` 加进 `SUPPORTED_VALIDATING_KEYWORDS` 与 `_canon` 的取值列表。
2. **哨兵而不是 None**：`_flat_diff` 原来用 `None` 表示"这一侧没这个键"。但
   `"default": null` 是**合法且常见**的 JSON Schema（`AwareDatetime | None = None` 就生成它），
   于是"稿里没写 default"与"稿里写了 null 默认值"读出来一模一样，方向判据直接失效——
   这批改动第一次跑就是把 10 条 `稿=None 生成=None` 的假差异报成硬差异（`@win` 实测），
   我才看见这个坑。现在用 `MISSING` 单例，打印成 `（无此键）`。
3. **只放行一个方向，且必须点名属性**：`_default_explainer` 只接受
   「稿里 MISSING ⇒ 模型物化出值」，且该属性名必须出现在某条 `serialization` 登记的 `field` 里。
   反向（稿有、产物没有）与"两侧都有但不同"永远是硬差异。
   为什么还要点名到属性：只按 def 放行的话，把 `pages` 的默认从 0 改成 7 也满足
   "稿没写 ⇒ 模型物化"，照样溜过去（验证者的 I10b 就是这个形状）。
   ⇒ 副作用是好的：`dump-materializes-defaults` 那条登记的 `field` 现在是一份
   **必须维护的清单**，新增一个会物化默认值的属性不登记就红。

### 2.2 tuple 形式的 `items`

`_canon(node["items"])` 遇到 list 形式（`items: [{...}, {...}]`，位置元组校验）会走到
`node if isinstance(node, dict) else {}` ⇒ 折成"空事实"，两侧都空 = 没差异。
现在逐位 `_canon` 成列表再比。

### 2.3 两支及以上的 `anyOf`

原条件写的是 `... and "anyOf" not in node`——它的本意是"可空写法已由 nullable-form 归一合并了，
别再当分支比一遍"，但它顺手把所有 anyOf 都排除在分支比对之外。
判据换成 `not merged_single_anyof`：只有**真的被当可空合并掉**的那一支才不再比分支。

### 2.4 反证读数（这是本节的核心证据）

我把三处修复**逐字回退成旧写法**，复制成 `apps/api/tests/_probe_old_comparator.py` 跑一遍，
然后立刻删掉（探针不进仓库）：

```
FAILED …[default：生成物把空串默认值改成别的字符串-生成物]
FAILED …[default：稿声明一个模型没有的默认值-稿]
FAILED …[default：稿把模型物化出来的默认值改掉（两侧都有但不同）-稿]
FAILED …[tuple items：两侧都写数组形式而第 0 位约束不同-both]
FAILED …[多支 anyOf：两支都不是 pattern 包装-both]
5 failed, 87 passed in 1.36s        @win
```

对照：同一批测试在修复后的正式文件里 **92 passed in 0.91s** `@win`。
"两侧都改"的两类需要**同时**改两侧才成立，所以我补了 `_compare_with_both_sides_mutated()`——
第一版结构上就测不到这类，这是它们漏网的真正原因（不是没想到，是注入器只能改一侧）。

## 3. `field="*"` 整片放行关闭

验证者构造的 `Divergence(ref="WorkListRow", field="*", kind="structural")` 能把
`additionalProperties` 翻转、删必填、`format: uri→email`、删属性四类真漂移一次吞掉。
`_explains` 现在在非空路径上对 `field=="*"` 直接返回 False（整片放行只剩 `path==""` 那一档，
即"整个 def 缺席"，那本来就必须由 structural 登记点名 def）。
反证：`test_star_wildcard_entry_no_longer_buys_a_free_pass` 注入同一条恶意登记 + 五处真改动，
要求**每处仍然报**，且这条登记在"必须有消费者"那关也过不去。

## 4. "消费"判据收窄

`compare_defs` 命中某条登记时会 `_note_explainer(hit.rule)`；第一版 `test_registry_rules_are_all_consumed`
把 `_USED_EXPLAINERS` 也算消费 ⇒ 遮差异的登记**自证被消费**。现在只认两档：
归一被比对器用到（`_USED_RULES`），或有 `RULE_CONSUMERS` 点名的具名断言（并且**真的调用**它）。
收窄后立刻有条目变红，补了两个具名消费者：
`generated-provenance-keys → test_artifact_provenance_keys_are_declared`（逐域验产物自证键）。

## 5. `kind` 值域与"消失的 def"三条正当去向

- `DIVERGENCE_KINDS` = structural/tightening/serialization/strictness/documentation；
  写错一种 = 凭空第六种放行能力，`test_registry_kinds_are_the_documented_five` 盯。
- `test_absent_draft_defs_are_accounted_for`：稿里有而产物没有的 def 只有三种正当下场——
  ①稿自己声明 `x-not-in-single-source`（由 `test_not_a_shape_claims_are_narrow` 反向验它确实
  不含形状关键词、确实不在产物里、确实有 structural 登记接手）；
  ②被某个**已收编** def 用 `$ref` 真引用（=别名内联的证据，`_referenced_by` 实扫）；
  ③在 `ALIAS_WITNESSES` 里点名一个可执行见证测试。
  这一条是 `UserId` 那类假话的总闸：**"别名会被内联"不再是一句可以随便写的话**。

## 6. identity 域的实质更正

`UserId`（UUID pattern）在本域**没有任何模型引用** ⇒ 约束既不在产物也不在任何使用处。
原登记文本写"Sub/UserId 的约束被内联进使用处"，对 UserId 是假的。处置：
- 文本按实测改写，逐个说清 Sub（真内联）/ UserId（靠见证）/ IsAdminEcho（稿里新加
  `x-not-in-single-source`，它是行为约束不是形状）三条**不同**的原因；
- 新增 `test_user_id_pattern_witnesses`（TypeAdapter 直跑，含大写/少位/无连字符/尾部多字符四种拒）；
- `identity.USER_ID_PATTERN` 提出来做常量，让"稿里的 pattern == 源里的 pattern"可被断言。

## 7. ADR-0012 的锚点更正（我自己写的假锚）

`subscription.py:130` 实测是 `register_source` 里 `Source(...)` 的 `external_id=external_id`，
属**账号级**键空间；`article_manifests.external_id` 的唯一构造点是 `manifest.py:255`，
值来自 `:144`（`_first_str(row, _ID_KEYS)`）经 `:156` 入 dict。已改为实测链路，
并把 `sources.external_id`（`entities.py:62` 注释 `# 公众号 biz`，唯一键 `uq_source_type_external`）
单列成"第四个键空间"注记——**上一轮我自己刚因为凭印象串键被记过一次**（§18 记录），
这次是同一毛病的第二个实例：把相邻的两个 `external_id` 当成同一个。

## 8. 更正表（不覆盖历史，只追加）

| 位置 | 原文 | 实测 | 处置 |
|---|---|---|---|
| `s122_identity_absorption.md:34` | "`identity.CONTRACT_DIVERGENCES` 6 条" | 9 条（表格只列了 6 条，漏 `required-order`/`generated-provenance-keys`/`role-rank-anchor`） | 本表记录，原 §3 不改 |
| `s122:49` | "生成器侧的两处必要改动" | 下面列了 3 条 | 同上 |
| `s122:68` | "11 类漂移注入测试" | 该提交上 15 条参数化 | 同上 |
| `test_collection_contract.py:16` | "11 条语料会被…绕过" | `_PATTERN_CORPUS` 实测 19 条（我第一遍数成 18，正则漏掉一处带行尾注释的项） | 已改成不带数字的表述（"样本再多也罩不住"） |
| `test_comparator_bites_on_each_drift_class` 文档字符串 | "十一类真实漂移" | 参数化条数会变 | 已删数字，写明"条数由 pytest 报" |
| `s122:64` | "`--check` 八条幂等一致（6 个 dto.ts + 2 个 schema）" | **这条验证者说错了**：`find packages/contracts/src -name dto.ts \| wc -l` = 6 | 保留原文，见 §9 |

## 9. 验证者的一条读数我没采纳（附复核）

它 §6 判"`6 个 dto.ts` 与 `packages/contracts/src` 目录不符（2 个 dto.ts + 3 个其它 .ts）"。
我复核：`find packages/contracts/src -name "dto.ts"` → 6，且 `gen_contracts.py --check` 打印
6 条 dto.ts + 2 条 schema = 8 条幂等一致。它的计数来自**只列了部分目录**的读取，
所以这条不改。**别人的更正也要验**——这一批里我自己的两条（`UserId`、`subscription.py:130`）
都是"看起来合理的叙述"造成的，照单全收只会再长一条假话。

## 10. 本批读数

| 命令 | 结果 | 位 |
|---|---|---|
| `pytest tests/test_collection_contract.py -q` | `92 passed in 0.91s`（返工前基线 80） | `@win` |
| 回退三处修复的探针 | `5 failed, 87 passed in 1.36s`，失败的正是 5 条新反证 | `@win` |
| `ruff check tests/test_collection_contract.py app/contracts/` | `All checks passed!`（从 `apps/api` 与仓库根两种 cwd 各跑一次，同一结果） | `@win` |
| `mypy app/contracts/` | `Success: no issues found in 3 source files` | `@win` |
| `gen_contracts.py --check` | rc=0，8 条幂等一致 | `@win` |
| `gen_contracts.py --check --only-schemas` | rc=0，2 条 schema 幂等一致 | `@win` |

## 11. 本批**没有**做的事

- `resources` / `api` 两域未起。`resources` 有一颗已知地雷：它的 `ArticleKey` 与 `collection` 的
  **同名不同约束**（稿侧 `minLength` 8 vs 3，`test_article_key_bounds_are_redundant` 钉着 3/128）
  ⇒ 收编时必须正面裁决，不许静默挑一个。
  `api.envelope` 更麻烦：它的**根层就是信封形状**，`definitions` 里只有若干条，
  而现有比对器只比 `$defs` 目录 ⇒ 要么给它建 def，要么给比对器加根层比路面，两条都得先想清楚。
- S1.4.3 的 IDOR 参数化生成器未动（端点清单要从路由表来，不能手写）。
- `default` 进校验面后**没给 identity/collection 的枚举补 default**——那是模型的事，不是比对器的事。
- `@ci` 读数（本批推送后的 run id + head_sha + conclusion）尚未取；取到之前本批状态记
  **部分确认**，不记"已验证"。

## 12. 同批续做：events 域收编（S1.2.2 第三个域）

返工之后接着把 events 落了，因为它正好是这套机制的第一个真实检验场——稿里六个 def，
**三个是注释、一个是无使用处的别名、两个是能收编的形状**。

| 收编 | 形状 | 备注 |
|---|---|---|
| `EventName` | `str, Enum` 三值 | 与 `push_events.py:26 VALID_EVENT_TYPES` **同序**钉；"新增事件名须三处同改"从注释变成断言 |
| `PushRetryState` | `BaseModel`：`delivered` / `reason(≤512)` / `responseData` / `retryable` | 三个必填来自稿的 `required`；`responseData` 用 alias，Python 侧仍 snake_case |
| `IdempotencyKey` | `Annotated[str, max_length=128]` | 本域**没有使用处** ⇒ 走 `ALIAS_WITNESSES`，由 `test_idempotency_key_alias_witness` 见证 |
| `EventPayloadRules` / `QueueMechanism` / `ManifestTransition` | 不收编 | 稿根层 `x-not-in-single-source` 声明 + `not-a-shape` structural 登记，两处缺一处都红 |

**没有静默解决的一条冲突**：稿 `responseData: ["object","null"]` vs
实测 `providers/push/base.py:50` 的 `response_data: str = ""`（六个 Provider 无一例外按字符串塞
上游回执原文）。两者类型**不相交**，不是宽严关系。契约取实测——产物是消费端读的形状，
写 `object|null` 会让按稿实现的前端解析器在第一条真实回执上就炸——但取实测不等于把冲突抹掉：
登记 `response-data-type-conflict`（tightening）+ 消费者
`test_push_retry_state_tracks_runtime_push_result` 把三方（稿 / 实现 / 产物）钉在同一条测试里，
**谁去裁决、改哪一边，都会先撞到这条红**。裁决请求写在登记文本里，等 owner 判。

`x-retry-policy` 那条注释也做成可执行事实：测试读 `push_scheduler.MAX_PUSH_RETRIES` 与
`RETRY_BACKOFF_BASE_SECONDS` 算出 `[60, 240, 960]` 再与稿比——那组数字第一次有了责任人。

### 12.1 新机制自己也被反证钉住（四条）

> **更正（第六轮验证后追加，不覆盖原文）**：下面第 1 条我写的因果是错的。
> "删掉 `x-not-in-single-source` 里的 `ManifestTransition` ⇒ 红"成立，但
> `QueueMechanism` / `EventPayloadRules` 删标记后 `compare_defs` 仍然**绿**——
> 让它们变红的是另一条测试（缺席归属 `test_absent_draft_defs_are_accounted_for`），
> 不是我以为的"关键词不认识所以吵"。机制本身可被击败，修复与读数见
> `s132_round6_hardening.md` §1 的 G1/G2。同样被推翻的还有 §12.2 的"8 条新测试"
> （实测 9 个 `def test_` / 17 条收集项）与 `1.52s` 计时（复跑 `2.14s`，计时不作证据）。

- 删掉 `x-not-in-single-source` 里的 `ManifestTransition` ⇒ 红：它的 `enumStatus`/`legalEdges`
  是比对器不认识的关键词，退出比对必须有**稿侧**声明，不能只靠登记表。
- 把**真形状** `PushRetryState` 标成"不是形状" ⇒ 红两处（`compare_defs` 见它仍在生成物里、
  narrow 判据见它含 `properties`/`required`）。
- 稿侧把 `reason.maxLength` 从 512 改 511 ⇒ 仍然红。这条钉的是 `response-data-type-conflict`
  **不越界**：它只解释 `responseData` 的类型那一处，不是给整个 def 买免检票。
- 给没被登记点名的属性（`EventName`）物化一个 `default` ⇒ 红，钉 `default` 方向判据的"点名"那一半。

### 12.2 events 批读数

| 命令 | 结果 | 位 |
|---|---|---|
| `pytest tests/test_collection_contract.py -q` | `109 passed in 1.52s`（返工批 92 → 加 events 域与 8 条新测试） | `@win` |
| `gen_contracts.py --check --only-schemas` | rc=0，**三条**幂等一致（collection / identity / events） | `@win` |
| `ruff check app/contracts/events.py tests/test_collection_contract.py scripts` | `All checks passed!` | `@win` |
| `mypy app/contracts/` | `Success: no issues found in 4 source files` | `@win` |

### 12.3 这一批我自己又踩的两处（写清楚，因为"探针报错"不等于"被测对象有问题"）

1. `events.py` 第一版有**九处**在 CJK 字符串里嵌 ASCII 双引号 ⇒ `SyntaxError`，`py_compile` 当场抓住。
   这条规矩上一轮才写进记忆，还是复发——教训是"写完必须 compile 再声称绿"，不是"我记得住了"。
2. `assert runtime["response_data"] is str` 恒假，因为 `providers/push/base.py` 带
   `from __future__ import annotations` ⇒ `dataclasses.fields(...).type` 是**字符串** `'str'`。
   第一遍读出来是红，我差点把它写成"实现与契约不符"的证据；实际是我的断言写法不成立，
   改用 `typing.get_type_hints` 才对。

## 13. 本批仍**未**取得的外部读数

全量后端套件（`apps/api` 下 `pytest -q`）与推送后的 CI 结论（run id + head_sha + conclusion）
在写这一段时**还没回来**。所以：
- 契约面读数以 `@win` 单文件为准（§10 与 §12.2），**没有**本批的全量 pass/skip 总数；
- 不引用任何历史批次的总数来充当本批总数；
- 状态记 **部分确认**，待第六轮验证 + `@ci` 读数再判收尾。
