# S1.2.2 第一域：identity 收编（@win，基线 `9976e97`）

冻结稿 `docs/任务规划V0.12.0/contracts/identity.schema.json` → 唯一源
`apps/api/app/contracts/identity.py` → 产物 `packages/contracts/schemas/identity.schema.json`。

## 1. 这一步真正的产出不是模型，而是"比对器不能再只服务一个域"

`compare_defs()` 从"读两个固定文件 + 一份登记表"改成 **`DOMAINS` 表驱动**：
每域一行（稿、生成物、该域登记表）。加域=加一行，比对器与门禁都不用再改。
同时补了一个方言归一：collection 的稿用 2020-12 的 `$defs`，**其余四域用 draft-07 的
`definitions`**（同一仓库里两种方言并存，本身就是稿内不一致），
不做这层归一，新域会整域报「生成物缺 def」。这条差异本身也是一条登记（`definitions-vs-refs-dialect`）。

## 2. 泛化过程中抓到的两个"自我缴械"缺陷（都比原缺陷更严重）

| 缺陷 | 怎么发现 | 危害 |
|---|---|---|
| **橡皮章组合**：`_explains()` 里 `ref.startswith("*（")` 判"域级条目"，而登记表里恰好有 `*（所有可空字段）` / `*（除 WorkListRow 外所有模型）` 这种 `field="*"` 的条目 ⇒ 两者一撞，**该域任何差异都算"已被登记解释"** | 我为了写 identity 的 strictness 条目去读匹配逻辑时意识到：identity 的 `*（本域全部 def）` + `field "*"` 会解释一切 | 门禁常亮绿灯，而且红过一次都不会有——比"没做门禁"更糟，因为它提供虚假安全感 |
| **两种记账混一锅**：`_USED_RULES` 既装"比对器用了哪条归一"，又装"哪条登记解释了某个具体差异" ⇒ 正向核对 `used → _NORMALIZATION_TO_KIND[rule]` 对 `identity-extra-forbid` 直接 KeyError | 第一次跑多域测试就红了（KeyError），不是猜的 | 混起来只有两种下场：加一堆"其实不是归一"的键进映射表（把表变成垃圾桶），或者放宽断言（把核对变成形式） |

修法：
- `_explains()` 收紧——`field == "*"` **只允许 `ref` 恰好等于该 def 名且 kind 为 `structural`**；
  tightening / serialization / strictness / documentation 四类**必须点名到具体 field**。
  注释里写明了为什么：否则一条"好心"注册的 `*`+`strictness` 就能吞掉该 def 里任何数值改动。
- 拆成 `_USED_RULES`（归一，须有 kind 归属）与 `_USED_EXPLAINERS`（解释器，须在登记表里且计入消费核对）。
- 消费测试取两者并集；正向测试只查归一，并加一条**"一个归一都没用到 ⇒ 红"**，
  防止"域太薄"被误当成"域很干净"。

## 3. identity 域做了什么、登记了什么

收编：`Sub`（1..64）、`UserId`（UUID 形）、`Role`（user/operator/admin）、`SessionClaims`。
未收编但在稿里的：`IsAdminEcho`（无使用处的裸 boolean——**不硬造 def 去过门禁**，见登记条目）。

`identity.CONTRACT_DIVERGENCES` 6 条（`rule` 全部有消费者）：

| rule | kind | 内容 |
|---|---|---|
| `alias-inlining` | structural | `Sub`/`UserId`/`IsAdminEcho` 是类型别名 ⇒ 不出现在 `$defs`（前两者内联进使用处，第三个无处出现） |
| `definitions-vs-refs-dialect` | structural | 稿用 `definitions`，产物用 `$defs` |
| `exp-required` | tightening | 稿里 `exp` 可选、模型必填：JWT 缺 exp 无法判有效期，"可选"没有可用场景 |
| `identity-dump-defaults` | serialization | `iss`/`aud` 默认 "" ⇒ dump 物化空串 |
| `identity-extra-forbid` | strictness | `SessionClaims` 用 `extra="forbid"`（比 collection 的 ignore 更严），与 `x-never-persisted` 合力：有人塞 `balance` 进来会被**拒**而不是被吞 |
| `identity-x-annotations` | documentation | `Sub.x-rule` 与 `SessionClaims.x-transport/x-never-persisted*` 不进形状，登记"谁负责" |

刻意**没做**的一件事：我最初想在 identity 里建一个 `SpaceAccessRow` 模型承载 `x-idor-checklist`
（越权端点的行形状）。那是**吸收步骤没有资格新增契约面**——稿里没有这个 def，
硬造只会让生成物"多出一个形状"。已删，改由 S1.4.3 与它的模型一起落地（代码里留了注释说明为什么不在这里）。

## 4. 生成器侧的两处必要改动

1. `CONTRACT_SCHEMA_MODULES` 加 `identity`；产物 `identity.schema.json` 落盘。
2. **枚举即使没被任何模型引用也要出 `$defs`**：`identity.Role` 就是这种情况（稿里是独立 def，
   带 `x-rank` 注释；但没有任何模型引用它）。第一版只收 `BaseModel`，于是 Role 从产物里消失，
   我只能靠"登记一条它不该消失"来蒙过门禁——那是拿登记表遮生成器的缺口，
   所以改成枚举也作为顶层符号渲染（`TypeAdapter(cls).json_schema()`）。
3. `title` 在生成侧统一剥掉。副产物是必要的：同一个枚举既作为顶层 def、又被模型的 `$defs`
   嵌套引用，两处唯一的不同就是 title，不剥会让"同名同体"被冲突守卫误判成两种契约形状。

## 5. 读数

| 命令 | 结果 |
|---|---|
| `pytest tests/test_collection_contract.py -q` | **80 passed in 0.87s**（多域参数化 + 第四轮补的 5 条绕过面） |
| `gen_contracts.py --check`（apps/api cwd） | rc=0，**八条**幂等一致（6 个 dto.ts + 2 个 schema） |
| `ruff check app tests` | `All checks passed!` |
| `mypy app` | `Success: no issues found in 110 source files`（identity.py 进来后由 109 变 110） |
| `secret_shape_gate.py`（62 文件） | HIGH 0 命中 |
| 11 类漂移注入测试（`test_comparator_bites_on_each_drift_class`） | 在收紧**之后**仍然全部为红 ⇒ 收紧没把门禁收松 |

identity 稿只加了 5 行（`x-not-in-single-source` 三条），刻意用纯文本插入而不是
`json.dumps` 重写——后者会把行内对象全部展开，6 行的标记换来整份文件的重排。

## 6. 还没做的

- `events` / `resources` / `api.envelope` 三域未收编（S1.2.2 剩余部分）；
  `resources` 与 `collection` 各有一个 `ArticleKey` 定义（`minLength` 3 vs 8），
  收编时必须正面处理"两稿同键不同约束"，不能默默挑一个。
- S1.4.3 的 IDOR 生成器未做（`x-idor-checklist` 目前只有注释，无可执行面）。
- S1.1.2 的 ADR-0012 未写。
- identity 新域的 @ci 读数未取。


## 7. 同一步里第四轮验证又抓到 5 类绕过（已全关，且都钉成了测试）

它没有接受我"收紧后应当无洞"的说法，自己再造注入，约 27 例里 5 类穿过去：

| 绕过面 | 根因 | 修法 | 钉成的测试 |
|---|---|---|---|
| 稿/产物塞**非 pattern 的 `oneOf` 分支**（如 `oneOf:[{const:…}]`） | `SUPPORTED_VALIDATING_KEYWORDS` 里有 `oneOf` ⇒ 不算 unmapped；而 `_pattern_fact` 只吃带 pattern 的分支 ⇒ 其余**静默丢弃** | `_canon` 改为对 SUPPORTED **全覆盖**：非纯 pattern 分支折成 `facts["branches"]` | `test_comparator_bites_on_patternless_oneof_branch` |
| 稿的某条 pattern 分支**丢掉 `^`/`$`** | `canonical_alternation()` 去锚再补锚 ⇒ 对锚**天生不敏感**，文本相等 | `_pattern_fact` 额外记 `anchored` 布尔（"是否全部带锚"，不是逐支串，否则"三支折一条"自己就成假差异） | `test_comparator_bites_on_draft_side_anchor_loss` |
| 生成物私带 `x-*` 键 | 只查过稿侧未知键 | `_extra_x_keys()` 逐 def/属性比对 | `test_comparator_bites_on_each_drift_class[生成物私带…]` |
| 生成物根层多出键 | 根层根本不比 | 根层比对，放过 def 容器方言，溯源键必须有 `generated-provenance-keys` 登记在位 | `[…生成物根层多出一个键]` |
| **注入器方向单一**：我所有反证都只改生成物 | 稿侧漂移（改稿不改产物）从没被验过 | 加 `_compare_with_mutated_draft()`，锚/patternless/description 三类都从稿侧打 | 上面三条稿侧测试 |

另外三处**我自己写错**的东西（与"洞"不同，属于说错话）：

1. `strip-description` 那条登记的 reason 承诺"保留一条断言：稿里有 ⇒ 生成物也得有"，
   但当时**根本没有这条代码** ⇒ 已实现（`_description_losses`）。
   而我第一版写的反证测试方向是"删稿侧 description 应当红"——那等于给门禁加了登记里没写的要求，
   已改成"生成物侧丢说明应当红"，并在测试 docstring 里写清为什么反方向不该红。
2. `test_registry_rules_are_all_consumed` 第一版对"已被比对器用到"的条目 `continue`，
   于是那条的行为承诺从不在元测试里被跑；现在**所有有消费者的条目都跑**（`used` 只免掉
   "无人认领"这一项投诉）。顺带：`generated-provenance-keys` 记错了桶（归一 vs 解释器）导致
   `KeyError`，说明两套记账混用的代价是真实的。
3. 我引用 `ci_backend_log_e7e9f25_excerpt.txt` 时写成了 `EVD-V2-01/`，实际在
   `EVD-V7-00W/`（跨证据目录引用必须核对路径，已改）。
