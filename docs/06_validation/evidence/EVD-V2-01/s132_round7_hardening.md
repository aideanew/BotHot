# S1.3.2 第七轮验证返工：四条机制又被击穿，这次连"引用必须说对事"都成了判据

批次：`STEP-01` S1.3.2/S1.3.3 返工第三轮。基线 `main@c966a34`（第六轮返工那次提交）。
验证者：`ageneral-purpose-7f5f86de67859529`（就地读工作树 + `git show`），判据 **T2/T4 FAIL**，
T1/T7/T8 PASS，T3 mixed，T5 扫描可绕过，T6 抓到一处我写下的读数无法复核。
读数机器位：`@win` = 本机 Win10 + `apps/api/.venv`。

---

## 1. 它说"能绕过"，我先在自己这边复现——结果两条复现方式我一开始都是错的

| 洞 | 验证者的说法 | 我第一次复现 | 错在哪 | 正确复现 |
|---|---|---|---|---|
| T4 | 约束写成"比对器没实现的关键词"再标「不是形状」⇒ 无声退场 | 我把标记打在 `IdempotencyKey` 上，读到 RED | 那条 def **本来就带 `maxLength`**，被上一轮 G1 的判据拦下 ⇒ 我测的不是它说的洞 | 换成正纯注释的 `EventPayloadRules`（只有 `type` 与 `x-*`）：**9 种写法全部 GREEN** |
| T2b | 稿侧删必填 + 一条点名该字段的登记 ⇒ 洗白 | 读到 RED(2) | 那 2 条差异来自 `WorkListPage` 里 `rows.items` 的**嵌套副本**，`WorkListRow` 本体已被解释掉 | 只看 `WorkListRow:` 前缀：**GREEN(0)** |
| H1 | `format: date-time → date` 被 tightening 登记洗白 | 一次到位 GREEN | — | GREEN（两种 kind 都洗得动） |
| T3a | 产物丢掉 `$schema` 被 structural 登记解释 | 一次到位 GREEN | — | GREEN |

**这已经是我第二次差点把"偶然的红"当成机制的红**（上一次见 §12.1 的更正）。
差别是这次我在写文档之前先做了隔离测量，并把隔离测量本身钉成了测试
（`test_citation_must_be_about_the_licensed_fields` 只看 `WorkListRow:` 前缀）。

## 2. 四个洞各自怎么关

### 2.1 T4：判据不能绑在"我实现了哪几个关键词"上
`_constraint_bearing` 原来是「顶层键 ∩ (`SUPPORTED_VALIDATING_KEYWORDS` − type/$ref)」。
两处都错：只看顶层、且只看我实现的子集。现在：
- 词汇表按 **draft 2020-12 标准**全列（`_VALIDATION_VOCABULARY`，含我没实现的
  `allOf/anyOf/oneOf/if/then/else/not/contains/patternProperties/propertyNames/
  dependentRequired/dependentSchemas/prefixItems/additionalItems/maxItems/uniqueItems/
  additionalProperties/unevaluated*/content*/deprecated` 等）；
- **递归**看每一层（`allOf: [{maxLength: 9}]` 就是把约束藏下一层）；
- `x-*` 子树不判——本项目往里写散文，`x-retry-policy` 里就有 `maxRetries` 这种键名，
  一律当约束会把三个合法注释 def 也判成形状，那是另一种误伤。

写完第一版仍漏一个 `not`（我的复现里唯一还读绿的一条）——词汇表要按标准列全，
漏一个就还是"未实现的关键词既是盲区又是许可证"。已补，并有 9 条参数化反证盯着词汇表被缩回实现子集。

### 2.2 H1 / 语义值叶子：宽松默认改成默认拒绝
两处病根同一个：`FACT_ALLOWED_KINDS.get(leaf, {structural})` 的**默认档**与
`_direction_ok` 结尾的 `return True`。现在：
- 未登记的叶子事实 → `DEFAULT_ALLOWED_KINDS = frozenset()`，**不接受任何解释**（宁可吵一次）；
- 凡是"值本身代表接受集"的事实（`types/nullable/enum/const/pattern/format/items/branches/minItems/unmapped`）
  → 只认 `conflict`，而 `conflict` 必须引**存在**的台账号。
  于是"顺手放宽一条约束"从改一行 Python 变成一次有登记时间、有默认值与备选、受 24h 生效规则约束的动作。

### 2.3 T3a：根层的形状键与标识键分档
`type/required/additionalProperties` 允许"稿声明而容器不声明"这种结构性不等（`structural`）；
`$id/$schema` 是文档身份本身，只能 `conflict` 并引台账。
`$id` 那一套已经登记 **D-V8-03**；`$schema` 丢失现在必红。

### 2.4 T2b：引用必须"说的就是这件事"
先做的是"required 类 tightening 必须引台账"（identity 的 `exp-required` 因此登记 **D-V8-04**）。
隔离测量证明这还不够：引一条**存在但不相干**的号（我拿讲 `exp` 的 D-V8-04 去解释删掉 `url`）
照样洗白。于是加第二道：`citation_covers(entry, licensed)` —— 被点名的字段必须出现在
所引台账行的原文里。现在三种引用（不存在的号 / 相干号 / 不相干号）全部读红。

**诚实边界**：比对器只看当下两侧，看不见"稿侧被改弱"这段历史。
我做的是**把代价搬到登记侧**（必须引、且必须引对），不是"检测出稿侧改弱"。
这条边界写在测试与登记文本里，不写成已经解决。

### 2.5 T5：行扫描换成 AST 数据流
原判定是"同一行里同时出现 `idempotency_key=` 与 `uuid`"——被三种写法绕过：
随机源挪上一行、`secrets.token_hex`、`random.getrandbits`。
现在 `_random_idempotency_sites()` 走 AST：认 Call 的函数名（含 `uuid.uuid4` 属性形式）、
把"被赋成随机值的局部变量"标脏并顺着 f-string/拼接/下标传播，再看 `idempotency_key=` 关键字实参。
`tempfile` 自检四种全抓、合法那条不误报（`test_ast_scan_catches_random_keys_that_move_lines`）。
锚点也修过一次：`Call.lineno` 指向 `foo(` 那行（实测指到 `:189` 的 `repo, db`），
现在记**值那一行**（`:192`）与登记文本一致。

**边界也写清**：只认关键字实参、只扫 `apps/api/app`、污染只追一跳赋值。
位置参数传法、跨函数深数据流、`scripts/` 里的作业创建都在射程之外。

## 3. 验证者的一条说法我没采纳

它 T6 说我的"修复前 12 绿 / 修复后 1 绿"无法复核（探针 `.staging/probe_r6.py` 未入库）。
这点它说得对——所以我不再引用未入库探针的历史读数，改成**可重跑**的两条：
`.staging/probe_r7c.py`（本轮四类）与本轮新写进仓库的 12 条永久反证。
它另一条"only 1 correct green remains 是乐观的"我也接受：G1 家族的 `allOf` 变体当时确实仍绿。

## 4. 读数

| 命令 | 结果 | 位 |
|---|---|---|
| `pytest tests/test_collection_contract.py -q`（本轮开始时） | `127 passed` | `@win` |
| 同上（第七轮返工后） | **`141 passed`** | `@win` |
| 四类击败复现（返工前 / 返工后） | T4 9 绿 + H1 2 绿 + T3a 1 绿 + T2b(隔离) 1 绿 / **0 绿** | `@win` |
| AST 扫描自检 | 四种绕过全抓，合法样例不误报 | `@win` |
| `ruff check app/contracts tests/test_collection_contract.py` | `All checks passed!` | `@win` |
| `mypy app/contracts` | `Success: no issues found in 4 source files` | `@win` |
| `gen_contracts.py --check --only-schemas` | rc=0，三条幂等一致 | `@win` |

新增的永久反证：`test_constraint_hidden_in_an_unimplemented_keyword_cannot_be_declared_prose`（9 条参数化）、
`test_format_change_is_not_explainable_by_structural_or_tightening`、
`test_generated_losing_schema_identity_is_a_hard_diff`、
`test_required_tightening_cites_a_live_decision_id`、
`test_citation_must_be_about_the_licensed_fields`、
`test_ast_scan_catches_random_keys_that_move_lines`。

## 5. 本批**没有**做

- 没把 `_VALIDATION_VOCABULARY` 与 `SUPPORTED_VALIDATING_KEYWORDS` 合并成一份真源——
  两份清单仍需同步维护；已知的冗余，不是已解决。
- 资源域（`resources`）与 `api` 域仍未起（D-V8-02 的 `ArticleKey` 3-vs-8 已登记未执行）。
- S1.4.3 IDOR 生成器未动。
- 全量后端套件：本机一次跑到约 6% 仍在进行，结论以 `@ci` 为准（见 `ci_readings_batch7.md`）。
- 第七轮返工**尚未经第八轮验证**——本文件的判读全部出自我自己，状态只能记 `部分确认`。
