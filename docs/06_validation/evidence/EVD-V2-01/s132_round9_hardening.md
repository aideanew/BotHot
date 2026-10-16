# S1.3.2 第九轮验证返工：台账引用洗白 + 「写了等于没写」的新增

批次：`STEP-01` S1.2.2/S1.3.2 返工（第九轮独立验证之后的修复）。
基线：`main@6e40a94`（工作树含我未提交的台账修复与本次门禁改动）。
执行者与验证者都是子智能体。读数一律标机器位（`@win` = 本机 Win10 + `apps/api/.venv`）。

---

## 1. 第九轮验证交了什么（原文条目 → 我的处置）

| 验证条目 | 它的读数 | 我的处置 | 状态 |
|---|---|---|---|
| T1 全组测试 | `159 passed` `@win`（干净 HEAD） | 复现一致；本次改动后 `166 passed` `@win` | 已确认 |
| T2 default 方向 | 5 项注入 4 绿，但**点破** `tail=="default"` 那一支不走 `_explains` | 复核后**不改判据**（见 §4），只把它记为已知弱点 | 存在缺陷（已登记，不掩饰） |
| T3a/b/d | structural→红、真号但不相干→红、假号 `D-V8-99`→红 | 与第八轮的三条永久反证一致 | 已确认 |
| **T3c** | **注入 `SessionClaims.properties.sub.pattern="^PROBE$"` + 一条引用 `D-V8-04` 的登记 ⇒ 0 条差异**（`tightening` 与 `strictness` 两种 kind 都能绕过） | 复现成功（见 §2），已堵：引用必须同时说到 **def 名 + 字段 + 事实类**，且按**词边界**、且只认**表格行** | 需要返工→已修 |
| **T3e** | **`additionalProperties: true` 加在 def 根 ⇒ 比对器一条不报**（`minLength` 同） | 部分推翻其成因：实测该差异**有报**，是被 `identity-extra-forbid` 解释掉的（0 vs 1 的差只在有无那条登记）。已堵「恒真新增不许被声称收紧的登记解释」 | 需要返工→已修（成因与我此前认知不同） |
| T4 同名重复行 | 域内重复→红，跨域同名→放行 | 与第八轮实现一致 | 已确认 |
| T5 幽灵属性 / description 两侧 | 3 条差异、三处站点各 1 条、`$ref` 优先解析成立 | 一致 | 已确认 |
| **T6 台账渲染** | **HEAD 的台账第 52 行切成 19 列——`D-V8-06` 与 `D-V8-07` 粘在同一行，`D-V8-07` 渲染上不存在的**；且 HEAD 的测试文件里**没有任何表格卫生守卫** | 拆分修复在工作树里（我上一轮做的），本轮把守卫补进测试：列数须等于表头、表格中间不许夹空行、一行只许一条裁决 | 已修 + 已钉 |
| T7 `$id` 统一 | 4/4 稿与产物 `$id` 同为 `bothot://contracts/<域>/v1`，根层无其他键静默漂移 | 一致；`root-identifier-conflict` 只剩 3 处过去式注释 | 已确认 |
| T8 生成器 | `--check` RC=0，但幂等一致是 **10** 条（6 个 `dto.ts` + 4 个 `schema.json`），不是我在执行段里写的 9 条 | 复核：9 是**四域收编之前**的正确读数（3 schema + 6 dto），不是错数；本轮把当前读数 10 写进本文件与执行段 §26，不回改历史行 | 部分确认（历史读数成立，缺当前读数） |
| 附件：陈旧数字 | `b:` 支被写成 13 的那串三元组仍活在两份文档里（`08-执行过程:802`、`steps/STEP-01:11`），而测试断言的是 `b:` 支 = 14 | 两处改为 14，并新立 `test_plan_docs_restate_the_verified_minima` 让文档重抄的数字必须等于算式；`test_the_wrong_minima_triple_is_not_restated` 保证那个错数不再以任何形式留在 `docs/` 里 | 已修 |

验证者还报了一个环境事实，我采信并写进这里：**它跑测中途工作树变了**——同一文件先 `159 passed`、几分钟后
`SyntaxError: unterminated string literal`（我当时正用脚本插守卫，shell 把 `\n` 与 `\\` 吃了）。
它因此改用 `git show HEAD:` 的副本继续测量。这条正是我 memory 里那条「win32 上不许用 heredoc 喂 Python 源」的第 N 次应验。

---

## 2. T3c 的复现（先证明它成立，再动手）

探针 `.staging/probe_r10.py`（gitignored，不入库）在内存里替换生成物 + 追加登记行：

```
=== T3c：注入 pattern + 引用不相干的 D-V8-04 ===
无登记行时的差异数 : 1
带登记行时的差异数 : 0        ← 洗白成功
kind=strictness 时 : 0
```

读出现场才看清它为什么能过：`D-V8-04` 那一行裁的是 `exp` 必填，但它的**问题描述**里
顺口写了「identity 冻结稿的 `required` 只有 `sub`」。旧 `citation_covers` 的判据是
`all(name in text)`——`sub` 是 `SessionClaims.properties.sub` 的字段名，于是这条毫不相干的
裁决号变成了 `sub` 的**万能通行证**。两个独立缺陷叠在一起：

1. **substring 匹配**：`sub` 出现在 `SessionClaims.exp` 之外的语境里也算"提到了这个字段"；
2. **不比事实类**：一条裁「必填」的号可以顺带裁掉「格式（pattern）」——登记买到的授权比裁决本身大。

`.staging/probe_r10b.py` 顺带枚举了现网**真正走到**「产物单方面新增」这一道闸的位置，只有 3 处：

```
[identity] SessionClaims @ additionalProperties  rule=identity-extra-forbid  产物实值=False
[resources] ContentAsset @ properties.externalId.pattern  …   引用=['D-V2-01','D-V3-01','D-V8-06']
[resources] ShortLinkMap @ properties.articleKey.pattern    …
```
这三处在"def 名 + 事实关键词（词边界）"的新判据下**全部仍然通过**——
`D-V8-07` 行里同时有 `SessionClaims` 与 `additionalProperties`，`D-V8-06` 行里同时有
`ContentAsset.externalId` / `ShortLinkMap.articleKey` 与 `pattern`。所以这道新闸不豁免任何一条现网登记。

**我自己也算错过一次**：`probe_r10.py` 末段那列 `NEW-RED`（说 `article-key-min-length-unified`、
`response-data-type-conflict` 等 5 行"会变红"）是**探针写错**——它把 `entry.ref` 整串当 def 名去匹配、
又把 `path` 传成占位符 `"x"` 塞进 names。真实判据用的是逐处的 `def_name` 与真实 path。
权威读数以永久测试为准（`166 passed` `@win`），不以我的探针为准。

## 3. T3e 的复现与更正

`.staging/probe_r10c.py` 把"报不报"和"洗不洗"分开测：

```
ap=true  保留登记 : []                                   ← 被登记解释掉
ap=true  删掉登记 : ['SessionClaims: additionalProperties 稿=（无此键） 生成=True']
ap=删除  删掉登记 : []
len=0    删掉登记 : ['SessionClaims: properties.sub.minLength 稿=1 生成=0']
```

所以验证者说的"比对器根本没看"**不成立**——它看了、报了，是登记把 `true` 放行成了 `false` 的授权。
真正的洞在第八轮我新加的 `fa is MISSING` 分支：它检查路径点名、kind、引用，**唯独不检查新增的值**。
`additionalProperties: true` 语义上等于"没写"，却被一条**声称**「契约拒绝多余键」的登记解释——
产物那时其实允许任意未知 claim。修法：新增的值必须真的在收窄（`_is_noop_invention`），
`additionalProperties` 只许 `False`、`minLength/minItems` 必须 ≥1、`pattern` 不许是 `.*` 这类恒真式、
`enum` 不许空。`minLength: 0`、`additionalProperties: true` 现在读红；
产物现状 `additionalProperties: false` 仍读 0 条（正确，它是登记声称的那件事）。

诚实边界：`maxLength: 10**9` 这种"数值上几乎不约束"的写法**没拦**——它需要与稿侧比较才有方向，
而稿侧此刻是"没写"。这一类仍只能靠登记文本与人读。

## 4. T2 那条我复核后**不改判据**的

验证者说 `default` 那一支不调 `_explains`，删掉 resources 的登记行后 `compare_defs` 仍是 0 条未解释。
我复现了读数并同意它对"牙齿从哪来"的描述：`default` 差异由 `_default_explainer` 独立处理
（方向唯一 + 必须点名到具体属性 + `_inert_default` 只覆盖必填字段），而行使登记的牙齿来自
`test_registry_rules_are_all_consumed`（登记了却没被任何位置用到 ⇒ 红），不是来自 `_explains`。
不合并这两条路径的理由：`default` 不是校验事实（它不改接受集，只改 dump 物化），
把它塞进 `FACT_ALLOWED_KINDS` 反而会把"序列化差异"与"接受集差异"混进同一套 kind 判据。
**这条弱点保留并写在这里，不假装它已被 `_explains` 七道闸覆盖。**

## 5. 本轮新增的 7 条永久反证

```
test_borrowed_citation_does_not_license_an_invented_constraint      # T3c，三种 kind 全注入
test_invented_noop_constraint_is_not_licensable                     # T3e，ap=true
test_inert_citation_blob_ignores_prose_outside_the_table            # 引用只认表格行
test_decision_log_tables_are_well_formed                            # 列数 = 表头；不许空行打断表格
test_decision_log_has_no_glued_rows                                 # 一行只许一条裁决（按 ID 单元格计数）
test_plan_docs_restate_the_verified_minima                          # 文档重抄的数字必须等于算式
test_the_wrong_minima_triple_is_not_restated                        # 旧错数不许再以任意间距复现
```

它立起来的第一分钟就抓到了东西：`test_plan_docs_restate_the_verified_minima` 首跑报
`08-执行过程-独立执行段.md:805` 被报与算式不符 ——**那一行是我自己刚写的更正注**，
它在正文里复述了旧错数。我把复述改成不带三元组的写法，**没有**加豁免关键词
（豁免词又是一条自我放行的后门）；随后发现"按措辞触发"的守卫本身也拦不住复述，
于是补了按**内容**拦的最后一条。

**已知残留，不改写**：旧错数还活在已推送的提交 message 正文里（`4427fd1`）。
历史消息不改写（那是把别人已经取走的分支锯断），所以这条只以"守卫 + 本句说明"落地。

## 6. 读数（本轮，全部 `@win`）

- `pytest tests/test_collection_contract.py -q` → **166 passed in 3.2s**
- `ruff check app/contracts tests/test_collection_contract.py` → `All checks passed!`
- `mypy app/contracts` → `Success: no issues found in 5 source files`
- `python scripts/gen_contracts.py --check` → `RC=0`，**10 条** `[ok] … 幂等一致`（6 `dto.ts` + 4 `schema.json`）

## 7. 我**没有**做什么（避免读数被当成结论）

- 没有改判据去满足"注入必红"这个我给不出来的保证。**D-V8-05（BLOCKING，未签）仍然悬着**：
  它提议把校验语义换成 `jsonschema`、自研比对器退役成"登记 + 覆盖率守卫"。
  按台账规则 BLOCKING 不自动生效 ⇒ 我继续自研，但这条卡的"比对器全捕"判据**不成立**这一点
  已经是九轮的机器读数，不是我一句话能宣布解决的。
- 没有跑全量后端套件复验本次改动（后台那次 `-rs` 跑的是改动前的树，且仍在进行中）。
- 没有 `@ci` 读数：本提交推送后才去取 run id + head_sha + conclusion。
- 没有动 `api` 域收编：它仍 blocked 在 **D-V8-08（BLOCKING，未签）** 上。
- 没有把探针脚本入库（`.staging/` 已被 gitignore），只留这份证据文件里的读数。
