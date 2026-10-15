# EVD-V2-01 · STEP-01 采集域契约冻结

本目录随 STEP-01 推进增量填充。当前在位：**S1.2.1**（Pydantic 唯一源 `collection.py`）。

## S1.2.1 读数（@win，2026-10-15，基线 `75abba7`）

命令：`apps/api/.venv/Scripts/python.exe -X utf8`，脚本 `.staging/verify_contracts.py`（scratch，
按纪律不入库；本文件记录其**输出**而非脚本）。

### 1. `ArticleKey` 的 pattern：期望接受与实际校验**逐条一致**（8/8）

| 见证串 | pattern 期望 | 模型校验结果 | 报错类型 |
|---|---|---|---|
| `b:MzI4NjA5NTU4Mg:2650635316:1` | 接受 | 接受 | — |
| `s:abcDEF12` | 接受 | 接受 | — |
| `h:0123456789abcdef0123456789abcdef` | 接受 | 接受 | — |
| `s`（ADR-0011 不变量 1 的退化形状，P0-1 回归锚） | 拒绝 | 拒绝 | `string_too_short` |
| `ssssssss` | 拒绝 | 拒绝 | `string_pattern_mismatch` |
| `b:a:b:c` | 拒绝 | 拒绝 | `string_pattern_mismatch` |
| `h:0123456789ABCDEF0123456789abcdef`（大写 hex） | 拒绝 | 拒绝 | `string_pattern_mismatch` |
| `x:abcdefgh`（未知前缀） | 拒绝 | 拒绝 | `string_pattern_mismatch` |

### 2. 与冻结稿的差异：现在登记在 `CONTRACT_DIVERGENCES`（9 条），不再靠 docstring 叙述

（本小节第一版是散文清单，被第一轮独立验证判 FAIL——它抓到清单漏项，见 §7。
现在改成模型文件末尾的机器可读登记表，S1.3.2 的比对脚本按它放行，**表里没有的差异一律红**。）

| # | 落点 | kind | 内容 |
|---|---|---|---|
| 1 | `ArticleKey` | structural | `oneOf` 三支 → 一条带锚 alternation；换行探针实测 `$` 是 ECMA-strict ⇒ 等价成立 |
| 2 | 所有可空字段 | structural | `type:[string,null]` → `anyOf[...,null]` |
| 3 | `ArticleKey` / `CollectionEvent.event` | structural | 稿里在 `$defs`，Pydantic 对别名/Literal 就地展开 |
| 4 | `ArticleKey` 的 3/128 | structural | 两支都声明了，但对 pattern 是**冗余**（最短可过串 10 字符、最长 ≤ 82） |
| 5 | `WorkListRow.publish_time`、`ArticleManifest.publish_time` | tightening | 无时区串被拒（实测 `timezone_aware`） |
| 6 | `CollectionEvent.at` | tightening | 同上 |
| 7 | `DiscoveryChannelView.lastSuccessAt` | tightening | **第一版清单漏了这处**，验证者补的 |
| 8 | `digest`/`author`/`content_hash`/`all_skipped_pages`/`idempotency_key`/`count` | serialization | 稿无 default，模型 `""`/0 ⇒ 接受集同、dump 会物化 |
| 9 | 除 `WorkListRow` 外全部 | strictness | 稿未声明 `additionalProperties:false`，模型默认 `extra="ignore"` ⇒ **丢弃**而非透传 |

### 3. 其余实测读数

- `WorkListRow`：`additionalProperties: true`、`required: ['id','url','title']`；额外字段 `upstream_fld=7`
  被透传保留；`id=""` → `string_too_short`、缺 `id` → `missing`、`url="http:/"`（7 字符）→ 拒。
  **我第一版见证用 `http://x` 误判成"意外通过"**——那串正好 8 字符，是被 min_length 合法放行的，
  错在我的探针不是模型。
- `ManifestSyncReport.required` = 冻结稿的 8 项，`all_skipped_pages` 不在 required（与稿一致，COULD 字段）。
- `CollectionEvent.required = ['event','source_id','channel','at']`，`event` 内联枚举 7 值（与稿一致）。
- `DiscoveryChannelView` 序列化键实测为
  `name, description, implemented, enabled, available, reason, contractVerifiedAt, verifiedScope, lastSuccessAt, lastError`
  ⇒ camelCase alias 生效，与 `app/providers/discovery/registry.py:333-340` 的真实输出同形
  （`lastSuccessAt`/`lastError` 是 STEP-05 的 COULD 新增，现在只是契约占位）。
- 未知渠道 `channel="weixin"` → `enum` 拒。
- **无反向依赖**（S1.2.1.2）：AST 扫 `collection.py` 的 import，结果只有
  `['__future__','enum','pydantic','typing']`；`app.services` / `app.providers` / `app.models` / `app.api`
  出现次数 0。
- 工具门：`ruff check app tests` rc=0；`mypy app` **109 files** rc=0（新增 2 个文件）。

### 4. 卡面与冻结稿的一处命名不一致（不改任何一方，记账）

卡 S1.2.1 要求实现 `DiscoveryReport`，冻结稿里**没有**这个名字；实际对应两个 `$defs`：
`ManifestSyncReport`（单源单轮发现报告）与 `DiscoveryChannelView`（后台渠道就绪度视图）。
本模块按冻结稿命名（唯一源是模型，卡片是任务描述），不新造第三个名字。

### 5. 本步没做的

- 尚未接 `gen_contracts.py` 生成 `packages/contracts/schemas/collection.schema.json`（S1.3.1）；
- 尚未有 `tests/test_collection_contract.py`（S1.4.1）——所以上面的见证向量现在是**脚本读数**，
  还不是 CI 门禁；落测试前它不会自己变红；
- 其余四契约（identity/events/resources/api）未收编（S1.2.2）；
- `ChannelName == registry.CHANNELS.keys()` 已实测相等（本次会话内 6 个键顺序也一致），
  但这条**断言**要等 S1.4.1 才进门禁。

## 6. 覆盖率门禁的预计算（避免"加了个没人 import 的模块把 CI 碰红"）

新模块没人 import ⇒ 它的语句全部计入 missed。实测取精确语句数：
`coverage run` 一个只 import 该包的脚本后 `coverage report --include="*collection.py"`
⇒ **`app\contracts\collection.py 78 stmts / 0 miss / 100%`**（被 import 就全执行，没有函数体；
第一版是 70 条，加了差异登记表后 78 条）。

CI 侧分母取自 `@ci` backend job 日志（run 38717913012）：`TOTAL 8799 1811 79%`，
门禁是 `--cov-fail-under=75`（`.github/workflows/ci.yml:123` `COV_BASELINE: "75"`）。

| 场景 | 总语句 | missed | 覆盖率 | 门禁（≥75） |
|---|---|---|---|---|
| 现状（不含本模块） | 8799 | 1811 | 79.42% | 过 |
| 本模块加入且**尚无测试 import** | 8877 | 1889 | 78.72% | 过（余量 3.72pt） |
| S1.4.1 落测试后（78 条转为覆盖） | 8877 | 1811 | 79.60% | 过 |

⇒ S1.2.1 单独进 CI 不会把 backend job 碰红；S1.4.1 之后覆盖率回到原值。
（`--include` 的坑：`*contracts*` 会连 `.staging` 里的 scratch 脚本一起匹配而漏掉目标文件，
第一次读数因此是空的，改用 `*collection.py` 才拿到 78。）

## 7. 第一轮独立验证：判 **FAIL**，抓到一个真 bug 和三处清单漏项

验证者的结论原文是「S1.2.1 narrowly FAILS the 逐字段对照+差异全登记 bar」。
它跑出来的东西分三类，其中第一类是**实现缺陷**，不是我表述不清：

| 类别 | 抓到什么 | 证据 | 处置 |
|---|---|---|---|
| **契约保真 bug** | `WorkListPage.next_cursor`：冻结稿 `required: [rows, next_cursor, page_size]`（`collection.schema.json:41`），我却给了 `default=None` ⇒ `{'rows':[],'page_size':1}` **被模型接受**，生成物 `required` 只有两项 | 它实测 + 我复跑：修复前"缺 next_cursor 被接受"，修复后"被拒"，而 `next_cursor=None` 显式给 null 仍通过 | 改成 `next_cursor: str \| None`（必填可空），并在 docstring 写明为什么不能用"缺字段"表达"末页" |
| **差异清单漏项 ×3** | ① `lastSuccessAt` 也被 `AwareDatetime` 收紧，我只写了 `publish_time`/`at`；② 可选字段的 `""`/`0` default 会在 dump 里物化（稿无 default）；③ 除 `WorkListRow` 外全部模型默认 `extra="ignore"` ⇒ 多余字段**静默丢弃**，与稿的隐式 allow 不对称且与 WorkListRow 内部不一致 | 它的 `zzz` 探针：接受、但不在 `model_dump()` 里 | 全部进 `CONTRACT_DIVERGENCES`（9 条），docstring 不再维护叙述清单——**叙述会漏项，登记表少一项就红** |
| **口径纠正** | 我原来写"`ChannelName` 与 `CHANNELS` 顺序也一致故用有序比较"：把契约钉在**实现文件的 dict 插入序**上是错的耦合 | 判断题不是读数题，我接受 | 改成"与 `CHANNELS` 比**集合**、顺序只与**冻结稿**比" |

验证者也确认了这些是**真的**（不是它客气）：8 条键见证向量逐条复现、错误类型一致；
`ruff` / `mypy 109 files` 复跑绿；`setuptools.find_packages(include=["app*"])` 能收到 `app.contracts`；
范围干净（无 alembic / apps/web / packages-contracts，后者是 S1.3.1 的活）；
`oneOf → alternation` 的等价性它拿换行注入去打破也没打破（Pydantic-core 的 `$` 是 ECMA-strict）。

我的两处 overstatement（它点名，我认）：
1. 提交信息说"9 个形状**逐字段**落地"——`next_cursor` 那条就是反例，"逐字段"当时不成立；
2. 说"差异**都**写在 docstring 里"——漏了三处。**"都"字是我没验证过的全称量词**，
   这是本会话里第三次被同一个字绊倒（前两次是"已排除 gitleaks"和"秒拒地址"）。

## 8. 修复后的复跑读数（@win）

- `WorkListPage.model_json_schema()["required"]` = `['rows', 'next_cursor', 'page_size']`（与稿一致）；
  `{'rows':[],'page_size':1}` 被拒；`next_cursor=None` 显式给通过。
- `CONTRACT_DIVERGENCES` = 9 条，kind 分布 `{structural: 4, tightening: 3, serialization: 1, strictness: 1}`。
- 模块语句数 70 → **78**（登记表本身是语句），覆盖率影响见 §6（78.72%，门禁 75）。
- `ruff check app tests` rc=0；`mypy app` 109 files rc=0；AST 复查 import 仍只有
  `__future__ / enum / pydantic / typing`。
- 三次语法自伤（写登记表时把中文引号写成嵌套直引号、忘 import `NamedTuple`），
  都是 `py_compile` 先报出来的 ⇒ 生成/改 Python 源后**先编译再声称绿**。

## 9. 第二轮复核：四条修复确认，又抓到第五、第六条

复核者对 §7/§8 的四条给 **CONFIRMED**（`next_cursor` required、登记表 9 条分布一致、
`ChannelName` 口径改成集合比较、`ruff` / `mypy 109 files` / AST 无反向依赖），
但它在"逐字段再查一遍"时抓到两条我仍然没登记的差异：

| 抓到什么 | 我的处置 | 为什么这么处置 |
|---|---|---|
| `WorkListRow.url` 稿里声明 `format: uri`，模型只给 min/max ⇒ 生成物没这个键，**形状差异且未登记** | **消除它而不是登记它**：字段加 `Field(json_schema_extra={"format": "uri"})` | 登记一条差异 = 让比对脚本永远记住一个例外；而这条根本没有语义代价（稿里 format 默认不 assert，加上去只让形状对齐）。实测生成物变为 `{"format":"uri","maxLength":512,"minLength":8,"type":"string"}`，且 `http:/`、`x` 仍被 min_length 拒 ⇒ 校验强度没变 |
| Pydantic 给**每个属性与模型**加 `title`（`Url`、`Publish Time`、类名），稿里只有 def 级中文 title | 登记为第 10 条 `structural`，规定"比对脚本剥离 `title` 后再比形状，人读描述走 `description`" | 我先试的是**关掉它**：`ConfigDict(field_title_generator=lambda …: None)` 实测抛 `TypeError: field_title_generator … must return str, not NoneType` ⇒ 关不掉，只能归一化。这条是试出来的，不是查文档猜的 |

顺带把 §7 那条 serialization 记录的字段面补全（`DiscoveryChannelView` 的四个 `None` 默认也会在
dump 里物化成 `null`，复核者说这条"arguable"——我同意它有争议，但既然稿允许 null、模型也接受 null，
差异只在 dump 形状，那就写全，不靠"arguable"跳过）。

**修复后读数（@win）**：`CONTRACT_DIVERGENCES` = **10 条**
（`structural 5 / tightening 3 / serialization 1 / strictness 1`）；
8 条键见证向量重跑仍逐条一致；`ruff check app tests` rc=0；`mypy app` 109 files rc=0。

**这条流程值得记一句**：第一轮验证判 FAIL 之后我改了四条，第二轮又抓到两条——
不是修得不干净，而是"差异清单是否完备"这件事**没法靠自审收敛**，只能靠"逐字段再查一遍"的外部视角。
所以 S1.3.2 的比对脚本必须把"表里没有的差异 = 红"做成机械的：
从第三轮起，完备性就该由门禁负责，而不是由谁又想起来一条负责。

> **后续状态（勿据此文）**：`CONTRACT_DIVERGENCES` 现已扩到 **11 条并新增 `rule` 字段**（每条必须有消费者），本文的 9/10 条是历史读数。现行清单与三次验证的攻防见 `s132_s141_contract_tests.md` §7–§9。
