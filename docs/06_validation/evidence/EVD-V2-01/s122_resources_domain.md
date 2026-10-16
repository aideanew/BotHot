# S1.2.2 第四域（resources）收编 + `ArticleKey` 跨域统一（执行 D-V8-02）

批次：`STEP-01` S1.2.2 第四个域。基线 `main@a8f54fe`（熔断登记那次）。
读数机器位：`@win` = 本机 Win10 + `apps/api/.venv`；`@ci` 待本批推送后补。

---

## 1. 这一域为什么比前三域难：它把"跨域同一个键"这件事顶到脸上

`resources` 稿里有五个 def，形状与非形状各半，但真正的问题不在这里：

- **`ArticleKey` 在两稿里同名不同约束**：`collection` 稿 `minLength: 3`，`resources` 稿 `minLength: 8`，
  而唯一源只能有一个别名。这不是"挑一个"的事——挑错方向就是给一域产物改事实。
  我先算清再动（不是"反正冗余"）：三支分支各自**最短可过串**是
  `s:`+8 = 10、`b:…:1:1` 支 14、`h:` 支 34，全部 >8 ⇒ 取更严的 8 对接受集是**恒等变换**。
  这条算式钉在 `test_article_key_min_length_is_the_unified_value` 里，且它同时断言
  两稿的界（3 与 8）与产物的取值（8）——**将来谁把两稿对齐了，这条会红，逼他更新登记**。
- **规范 pattern 在 `collection` 稿里是校验（三条 `oneOf`），在 `resources` 稿里只是注释
  （`x-target-pattern`）**。别名一旦共享，产物就会对 `ContentAsset.externalId` /
  `ShortLinkMap.articleKey` 施加稿没写的校验。这不是等价改写也不是宽严关系 ⇒ 登记成
  `conflict` 类并引台账（新登记 **D-V8-06**，默认值取源侧，理由是 `b:/s:/h:` 形状本身
  已由 D-V2-01/D-V3-01 签署，注释只是它的散文形式）。
  这条的**跨域等值**由 `test_resources_pattern_matches_adr_0011_shape` 验：
  ADR 文本里三支前缀仍在、两域产物 pattern 逐字符相等、稿注释去掉捕获组包装后与产物主体相同。
- **`InAppNotification.sub` 不套 identity 的 `Sub`**（那会给这份合同加它没声明的 1..64）。
  两域形状不同是**事实分歧**，我把它登记成 `sub-not-aliased-to-identity` 并发布 **P-10** 交裁决，
  而不是让吸收步骤顺手统一——顺手统一等于用工具替人做决定。

## 2. 收编了什么、没收编什么

| 稿件条目 | 去处 | 理由 |
|---|---|---|
| `ContentAsset` | `BaseModel`，16 个字段 camelCase alias、`extra="forbid"` | 稿的 `additionalProperties: false` 与模型 `forbid` 同形 ⇒ 零登记 |
| `ShortLinkMap` | `BaseModel` 两字段（`shortKey` / `articleKey`） | DB 行还有 `id`、`biz`——**不收**：稿里没有的形状不是吸收步骤有资格新增的（identity 那次 `SpaceAccessRow` 的错不犯第二次） |
| `InAppNotification` | `BaseModel` 六字段 | `is_broadcast` 等位标志不在稿面 ⇒ 不进视图 |
| `ChannelSecret` | 不收编（`x-not-in-single-source` + `not-a-shape` 登记） | 全是加密实现与运维纪律；更要紧的是 `x-projection-rules` 明令任何响应都不得出现它，做成可实例化模型反而诱导有人去序列化 |
| `x-projection-rules` / `x-resource-lifecycle` | 不收编（根层标记） | 投影纪律与生命周期叙述，不是形状；状态机值集已由 `collection.ManifestStatus` 钉住 |

## 3. 两条新归一，以及它们的边界测试

| 归一 | 内容 | 边界（都有反证） |
|---|---|---|
| `single-value-enum-to-const` | 稿的 `enum: [article]` 与产物的 `const: article` 在事实层合流 | **只在单值时**。`test_single_value_enum_normalization_cannot_hide_a_second_value` 把稿加成两支 ⇒ 必须红 |
| `default-on-required-is-inert` | 稿在**必填**字段上写的 `default` 是惰性事实（`required` 已保证存在），产物不写它不算差异 | 只开「稿有、产物无」一个方向，且只认该 def 的必填字段。`test_inert_default_rule_does_not_cover_optional_fields` 给可选字段 `title` 加默认值 ⇒ 必须红 |

顺带：`_default_restates_domain` 允许"默认值等于唯一取值"这一种非空物化（`contentType` 场景），
判据是**复述**而不是"新事实"；默认值一旦不等于唯一取值就落回硬差异。

## 4. 这一批同时收紧了门禁本身（第六轮遗留项）

- `test_normalizations_used_are_all_backed_by_registry` 从"查 kind"改成**按 rule 名认领**：
  任何一条 `documentation` 登记都能替 `strip-title` 发通行证，是第六轮 T3 点名的。
  改完立刻暴露**七处**缺行（(域, rule) 组合逐一数：identity / events / resources 各缺一条
  `strip-description`＝3，events / resources 各缺一条 `nullable-form`＝2，collection 缺
  `alias-inlining` 与 `oneOf-to-pattern-set`＝2，合计 7）——全部补齐，
  每条都写清"归一发生在哪一层、边界在哪、谁验它"。
  **这条的意义**：登记表不再是"解释差异的自由文本"，而是一份必须与比对器实际行为逐名对齐的账。
- 生成物侧不再带 Pydantic 派生的 `title`（第六轮 T3 的另一半）；
  上一轮修 `_strip_titles` 时把真实字段 `title`（文章标题）误删过，已被门禁抓住并改为
  "`properties` 容器本身不是 schema 节点"。

## 5. 读数

| 命令 | 结果 | 位 |
|---|---|---|
| `pytest tests/test_collection_contract.py -q` | `156 passed`（本批前 141；净增 15 条收集项） | `@win` |
| `gen_contracts.py --only-schemas` + `--check --only-schemas` | 四条写出、四条幂等一致 | `@win` |
| `ruff check app/contracts tests/test_collection_contract.py` | `All checks passed!` | `@win` |
| `mypy app/contracts` | `Success: no issues found in 5 source files` | `@win` |
| 未解释差异（四域逐一） | 0 | `@win` |

## 6. 本批没做 / 已知不足

- `api` 域未起。它是唯一一个**根层就是形状**的域（信封 `{code,message,data,requestId}` + 分页两套壳），
  现有比对器只比 def 容器 ⇒ 收编它要么把信封建成 def、要么给根层加"根即契约"的比路面。
  这个选择会决定 P-10 那条 `sub` 之类跨域形状问题的处置口径，故单独一批做。
- 没跑全量后端套件（本机一次跑到 6% 后我中止过一回；结论以 `@ci` 为准）。
- `_inert_default` 只看稿侧 `required` 列表，不看"该字段是否根本不存在"——已由
  `_default_explainer` 的属性点名兜住，但仍是一条**有边界**的归一，不是普适规则。
- 本批**未经独立验证**。按 D-14，S1.3.2 的"全捕"判据已熔断待 D-V8-05；域面判据
  （每条不等有登记、每条登记有具名消费者、每条归一按名认领）我现在能机械复核，
  但"复核者是我自己"这件事，状态只能记 **部分确认**。
