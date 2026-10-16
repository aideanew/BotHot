# S1.3.2 + S1.4.1 读数（@win，基线 `c1657d6`）

一步做完两件事：`apps/api/tests/test_collection_contract.py`
- **S1.3.2** 生成物 vs 冻结稿的**语义比对**（约束面，不是文本 diff）
- **S1.4.1** 契约锚定测试（键不变量 / `WorkListRow` 必填 / `ChannelName` 与注册表 / 错误码映射）

## 1. 为什么必须有第 2 层门禁

`gen_contracts --check` 只保证「产物 == 模型的 schema」。
「模型 == 冻结稿」是另一件事——没人管的话唯一源就退化成"我以为它是唯一源"。

## 2. 比对器的三条设计纪律

| 纪律 | 做法 | 为什么 |
|---|---|---|
| **归一不免费** | 每条归一化（剥 title / 剥 description / 剥 default / 可空写法 / `$ref` 内联 / `oneOf`→pattern 集 / `required` 顺序）都必须在 `CONTRACT_DIVERGENCES` 里有对应 kind 的登记，`test_normalizations_used_are_all_backed_by_registry` 逐条断言 | 没登记就归一 = 把差异藏起来 |
| **未知关键词直接红** | 稿里出现比对器没实现的关键字 ⇒ 报"比对器不认识 {key}"，不忽略 | 静默少比一项比报错危险（`jsonschema` 库本机没装，也**不装**——按纪律不装依赖，比对器只实现稿实际用到的子集） |
| **pattern 比接受集不比文本** | `oneOf` 三支与单条 alternation 用 11 条见证语料的**布尔向量**比相等 | 文本不等而语义等价正是登记过的 structural；比文本会把合法归一变成噪音 |

## 3. 比对器会不会"只会通过"——注入了四类真实漂移

探针 `.staging/probe_comparator.py`（scratch，不入库；在内存里替换生成物，未动任何仓库文件）：

| 注入 | 结果 |
|---|---|
| A `WorkListRow.title.maxLength` 512→256 | **红 2 条**（`WorkListRow.properties.title.maxLength: 稿=512 生成=256`，还连带 `WorkListPage…rows.items…`） |
| B `WorkListPage.required` 少一项 | **红 1 条**（列出两边的 required） |
| C 删掉 `DiscoveryChannelView.reason` 属性 | **红 2 条**（属性缺失 + required 不等） |
| D `ManifestStatus` 枚举多一个值 | **红 2 条**（两处引用都报） |
| 对照 1：真实生成物 + 完整登记表 | **0 条**（不误报） |
| 对照 2：真实生成物 + 删掉 ArticleKey 那条 structural 登记 | **1 条**：`ArticleKey: 生成物缺这个 def（且无针对该 def 的 structural 登记）` |

⇒ 门确实打得住。对照 2 是 S1.2.2.3 要求的"故意漏登记必须红"的机器化版本。
**这里还翻出一个我自己的假门禁**：第一版 gating 写的是"registry 里存在任意 `structural` 就放行"，
删掉某一条也照样放行 ⇒ 反证测试打不中；改成"必须有**针对该 def 名字**的登记"才有效。

## 4. 测试清单与结果

`pytest tests/test_collection_contract.py -q` ⇒ **44 passed in 0.67s**（`@win`）。
卡面 §5 估"约 12 条"，实际 44 条是因为参数化（键见证 3+7、9 个 def 各一条比对、WorkListRow 接受集 5 条）。

分组：
- 结构：`test_both_contract_files_exist`、`test_neither_side_uses_a_keyword_the_comparator_does_not_implement`（后已扩成两侧、并按域参数化）、
  `test_each_draft_def_is_explained_or_equal[9]`、`test_whole_domain_has_no_unexplained_divergence`
- 登记表：`test_normalizations_used_are_all_backed_by_registry`、
  `test_registry_rules_are_all_consumed`
- 键不变量（ADR-0011 的 1/4 两条）：接受 3 支、拒 `"s"`（P0-1 回归锚）、拒大写 hex、拒未知前缀、
  **拒尾随换行**（`h:<32hex>\n`——Python 的 `$` 会放过它，Pydantic-core 用 ECMA-strict 不放过）
- 渠道：与 `CHANNELS` 比**集合**、顺序只与**冻结稿**比（第一轮验证者指出的错耦合，已改口径）
- 状态机 / 事件枚举：`ManifestStatus` 值集、`CollectionEvent.event` 生成物 vs 稿
- 视图：camelCase 键实测（`contractVerifiedAt`/`verifiedScope`/`lastSuccessAt`/`lastError`）、
  真实后台输出的 8 个键必须是契约属性的子集（新增字段先改契约，不能反过来）
- 错误码映射：`errors.global.schema.json` 的 `x-table` 21 条与 `app/core/errors.py` 的 `ERROR_CODES`
  **逐条 code→name 对号**（实测 21/21 相等），另比 `definitions.ErrorCode.enum`（去掉 0=成功码）
- 行为收紧：`publish_time` / `CollectionEvent.at` 无时区被 `ValidationError` 拒（不是 `Exception` 盲断言）

## 5. 工具门与邻居

| 命令 | 结果 |
|---|---|
| `ruff check app tests`（apps/api cwd） | rc=0（第一版有 9 条：I001 导入序 ×1、B017 盲断言 ×6、B007 循环变量未用 ×1、E501 ×1，全修） |
| `mypy app` | rc=0，109 files |
| `pytest tests/test_collection_contract.py tests/test_discovery.py tests/test_startup_probe_timeout.py` | **62 passed, 2 skipped in 14.96s**（2 条 skip 属既有 Redis/LangBot 不可达类，不是本文件产生的） |

B007 那条修得值得记：我原来写 `for rule, need in _NORMALIZATION_TO_KIND.items():` 却在循环体里
按 `rule` 名字硬编码判断 kind ⇒ `need` 根本没用上，等于**映射表是装饰**。改成
`assert need in kinds`，映射表才真的在管事。

## 6. 本步没做的

- 覆盖率：新模块被 import 后 78 条语句转为覆盖，但**还没测**（要等一次 @ci 读数才能报新百分比，
  不预估）；`EVD-V2-01/s121_collection_models.md` §6 的算术仍然只是算术。
- S1.2.2 其余四契约（identity / events / resources / api）未收编 ⇒ 比对器目前只服务 collection 一个域。
- S1.4.3 IDOR 参数化生成未做（下一步）。
- 语义比对里 `tightening` 类差异**在 schema 形状上看不见**（稿的 `format: date-time` 与模型的
  `{"format":"date-time"}` 归一后同形），所以那三条登记只由**行为测试**负责，
  比对器不负责——这点在登记表 reason 里写了，别让下一个人以为比对器能抓到它。

## 7. 第三轮独立验证：**S1.4.1 PASS，S1.3.2 作为门禁 FAIL**（抓到 6 类绕过）

它没接受我 §3 的"门确实打得住"，而是自己发明注入方式去打，结果 15 类里 **6 类穿过去了**：

| 它注入的漂移 | 第一版结果 | 根因 |
|---|---|---|
| `s:` 分支字符类去掉连字符 `-` | **0 条，漏** | pattern 只比 11 条语料的接受向量，语料里没有含 `-` 的 token |
| `h:` 的 `{32}`→`{31,32}` | **0 条，漏** | 同上：语料罩不住量词边界 |
| `b:` 的 mid `{1,12}`→`{1,13}`、idx `{1,2}`→`{1,3}` | **0 条，漏 ×2** | 同上 |
| 往生成物塞 `minItems` | **0 条，漏** | 未知关键词检查**只跑稿侧**（`:254` `:312`），生成物侧塞什么都行 |
| 往生成物塞 `const` | **0 条，漏** | 同上；且 `_canon` 只读它认识的键，多余键静默丢弃 |
| 真差异发生时参数化的 `[WorkListPage]` 那条 | **PASSED，误报平安** | 差异路径是 `WorkListPage.required: …`，过滤器找的是 `WorkListPage:` 或 `.WorkListPage.` ⇒ 9 条参数化测试全绿，只有汇总那条红。所谓"每 def 可定位"是假的 |

⇒ 我 §3 写的那句"门确实打得住"**把 4 类的读数当成 15 类的结论**，是外推过度。

## 8. 修完后的形态（本次增量）

| 修法 | 落点 |
|---|---|
| pattern **先比文本推导**：稿的 `oneOf` 三支去掉 `^`/`$` 折成 `^(?:A\|B\|C)$`，与生成物 pattern 逐字符相等；语料向量降为第二层，并补 17 条边界见证（含连字符 token、hex 31/32/33、biz/mid/idx 位数边界） | `canonical_alternation` / `_pattern_fact` / `test_article_key_pattern_text_is_derivable_from_draft` |
| **两侧**都跑未知关键词检查；`_canon` 把没映射的键收进 `unmapped` ⇒ 成为差异，不再静默丢 | `test_neither_side_uses_a_keyword_the_comparator_does_not_implement`（参数化两侧） |
| 差异统一以 `def名:` 前缀 ⇒ 参数化的每-def 测试真的分得清责任 | `test_each_draft_def_is_explained_or_equal[9]` |
| **登记表加 `rule` 字段并要求双向消费**：被比对器用到 或 本文件有个函数替它兑现 reason 里的承诺 | `test_registry_rules_are_all_consumed`、`test_normalizations_used_are_all_backed_by_registry` |
| 三条 dead claim 补上实现者：`x-not` → `test_every_draft_x_keyword_is_registered`；"另设 dump 形状检查" → `test_optional_defaults_materialize_on_dump`；`strictness` → `test_unknown_fields_dropped_except_work_list_row` | 同上 |
| 外部验证者的击败方式**钉成 11 类参数化测试**（下次谁把比对器改坏，CI 替它再问一遍） | `test_comparator_bites_on_each_drift_class` |
| 补上"改了模型没重跑生成器"这段空档：进程内 import 生成器重算，与已提交产物比 | `test_generated_artifact_matches_current_model` |

登记表从 12 条收敛到 **11 条**（第一版把 ArticleKey 的"oneOf 折一条"与"别名内联无 $defs"写成两条，其实是同一件事）；
每条多一个 `rule`。`used` 不再是无人接的返回值——`_USED_RULES` 由比对过程记录、由双向核对消费。

## 9. 本次读数（@win，修复后）

- `pytest tests/test_collection_contract.py -q` ⇒ **61 passed in 0.90s**（第一版 44 条）
- `ruff check app tests`（apps/api cwd）rc=0；`mypy app` rc=0，109 files
- 两条新断言**自己也被打过**（不是声称，是跑过）：
  - 把产物指向一份只改过一个字符（`title.maxLength` 512→511）的副本 ⇒
    `test_generated_artifact_matches_current_model` 报"模型与已提交产物不一致"；
  - 合成一条没有消费者的登记（`rule=bogus-rule-with-no-consumer`）⇒
    `test_registry_rules_are_all_consumed` 报 `dead claim：bogus-rule-with-no-consumer（SomeDef / someField）`。
  两次都在内存里做，未改任何仓库文件（副本写在 `.staging/` 且用完删除）。
- 邻居回归：`pytest tests/test_collection_contract.py tests/test_discovery.py tests/test_startup_probe_timeout.py`
  （第一轮读数 62 passed / 2 skipped；本轮未重跑那两条邻居，改动只在契约文件内）

## 10. `@ci` 侧对 9b70bc2（修复前那版）的读数

- `CI` run **38737622962** = **success**（backend 含这 44 条新测试 + 覆盖率门禁 75 未破）
- `CI-Windows` run **38737622022** = **failure**（13:10:16Z，第七个同形态读数，仍非 cancelled）
## 11. 修复版（61 条）的 @ci 读数 —— 承诺补的那一条，现在补上

- 提交 `d4cb236`；run **38743100273**；job=backend **116449607972** = **success**（13:29:19Z → 13:32:00Z）
  （原始响应 `jobs_ci_d4cb236.json`）
- 步 **Contract drift gate (gen_contracts --check) = success**、**Tests (pytest) + coverage + skip gate = success**
- 汇总行：`1119 passed, 6 skipped, 1 warning in 78.46s`
  ⇒ 相对无契约测试时的基线 `1058 passed, 6 skipped`（`ci_backend_log_e7e9f25_excerpt.txt`）
  **净增 61 个 pass、0 个新 skip**——与 `test_collection_contract.py` 的 61 条逐一对上，
  没有一条靠 skip 蒙过门禁。skip 门禁：`total_skipped=6 baseline=6 pg_unreachable=0`。
- 覆盖率实测：`TOTAL 8878 1812 80%`（此前 §6 只能给的算术预测是 8877/1811/79.60%）
  ⇒ **语句数差 1**（登记表合并两条后又改动一处），所以那条预测偏低但同向；
  现在这一行是读数不是算术。门禁 `--cov-fail-under=75` 余量扩大到 5pt。
- `CI-Windows` run 38743100542 = **failure**（第八个同形态读数，仍非 cancelled；U-23 未变）
- `Security` run 38743100163 = **success**


## 12. 引用勘误（第四轮验证点名，2026-10-16）

- 本文 §2/§3/§8 曾引用三个**不存在的测试名**（`test_normalizations_are_all_backed_by_registry`、
  `test_draft_has_no_keyword_the_comparator_does_not_understand`、
  `test_comparator_bites_when_a_registry_entry_is_removed`）。已全文替换为真实函数名。
  错因是我按"意图"记名字而不是按代码记名字——这类错误只有 grep 能治，已经并进 P-3 那条守卫需求里。
- 文中 `mypy 109 files` 是**当时**的读数（identity 域收编前）。现为 110；不改写旧读数，只在此加一句。
- 跨证据目录引用：`ci_backend_log_e7e9f25_excerpt.txt` 在 `EVD-V7-00W/`（不是 `EVD-V2-01/`）。
- "净增 61 pass、0 新 skip ⇒ 没有一条靠 skip 蒙过"——这句只在**聚合与 test_collection_contract.py
  这一文件**两个粒度上成立；该 run 的 6 条 SKIPPED 明细未逐条重新核对（核对过的是 e7e9f25 那一份）。
  把聚合读数说成文件级结论，是我这一轮又犯的一次"外推"。
