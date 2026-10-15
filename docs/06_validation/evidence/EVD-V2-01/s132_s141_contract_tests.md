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
| **归一不免费** | 每条归一化（剥 title / 剥 description / 剥 default / 可空写法 / `$ref` 内联 / `oneOf`→pattern 集 / `required` 顺序）都必须在 `CONTRACT_DIVERGENCES` 里有对应 kind 的登记，`test_normalizations_are_all_backed_by_registry` 逐条断言 | 没登记就归一 = 把差异藏起来 |
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
- 结构：`test_both_contract_files_exist`、`test_draft_has_no_keyword_the_comparator_does_not_understand`、
  `test_each_draft_def_is_explained_or_equal[9]`、`test_whole_domain_has_no_unexplained_divergence`
- 登记表：`test_normalizations_are_all_backed_by_registry`、
  `test_comparator_bites_when_a_registry_entry_is_removed`
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
