# EVD-V17-08 · STEP-08 执行方读数

> 卡面：`docs/任务规划V0.7.0/steps/STEP-08-信息源标识与按源路由.md`（V0.13.0 起的继承卡只改基线，
> 三级任务沿用来源卡）。DDL 的形状与取舍在 **ADR-0014**。
> 卡面字段 11 写的证据目录 `docs/任务规划V0.8.0/evidence/61358c3-08/` 本仓从未建过
> （与 P-58 同一形状：继承卡在七个版本里逐字复制那一格）⇒ 按现行约定落在本目录，偏离已在 P-65 登记。

## 1. S8.1.1 迁移往返 + 回填（真库演练，`bothot_test`@5547 / PG 16.4）

| 步 | 命令 | 读数 |
|---|---|---|
| 单头 | `alembic heads` | `ab1006c2a (head)` —— 只有一个头 |
| 升 | `alembic upgrade head` | rc=0，`Running upgrade ab1006c4a -> ab1006c2a` |
| 高点探针 | `scripts/migration_roundtrip_probe.py --expect=present` | 六列齐全 + 三索引齐全，rc=0：`ix_source_identifiers_kind` / `ix_source_identifiers_source_id` / `uq_source_identifier_kind_value` |
| 降 | `alembic downgrade -1` | rc=0 |
| 低点探针 | `information_schema.tables where table_name='source_identifiers'` | **表不存在**（`0`）——真 `downgrade()`，不是只回退 `alembic_version` |
| 再升 | `alembic upgrade head` | rc=0 |

### 1b. 回填的"读数 = 播种数"

演练刻意在**降级之后**播种，再升级，才能证明回填属于这次迁移而不是历史残留：

```
播种 sources 4 行：external_id 分别 BIZ-AAA / BIZ-BBB / BIZ-CCC / 空串
低点（表不存在）: (0, '表不存在', [])
升级后:            (1, 3, [('biz', 'source', 3)])
清场后:            (1, 0, [])
```

⇒ 回填 3 条 = 非空 `external_id` 的播种数，**空串那条没有生成行**（判据是"非空才回填"，
不是"每源一行"）；`kind/origin` 全是 `('biz','source')`，与 ADR-0014 §3 第三条一致
（`origin` 要能区分"源自己给的"与 S8.2 resolver 推导的）。

## 2. 形状三方对账（实体 ↔ 迁移 ↔ 探针）

`tests/test_source_identifiers.py` 把三份东西钉在一起，全是**读磁盘/读元数据**，不抄表：

| 判据 | 形状 |
|---|---|
| 列集合 | `SourceIdentifier.__table__` == 迁移里 `create_table` 的 `sa.Column` 名（AST 取） == `SHAPES["ab1006c2a"].columns` |
| 唯一约束名 | `uq_source_identifier_kind_value` 必须同时出现在迁移与 `SHAPES.indexes`（只有一边有 = 探一个不存在的东西） |
| 链序 | 迁移的 `down_revision` == `ab1006c4a`（**不是**卡面当年写的 `ab1006c1a`；STEP-28 字段 9 明文"以合入时 heads 为准"） |

## 3. DB 侧不变量（连库）

| 用例 | 判的是什么 |
|---|---|
| `test_same_kind_and_value_belongs_to_one_source_only` | 不变量 1：同 `(kind,value)` 属于第二个源 ⇒ `IntegrityError`（应用层查重挡不住并发写） |
| `test_the_same_value_under_a_different_kind_is_a_different_fact` | 唯一性是"同一种标识内"的：biz 与 ghid 同值必须允许，否则一个号主的两种标识互相挤掉 |
| `test_deleting_the_source_takes_its_identifiers` | `ON DELETE CASCADE` 真的在：源删掉后按 `source_id` 查得空集（留孤儿 = 反查命中不存在的源） |

## 4. 契约面（卡面 S8.1.1"实体与 dto 同提交生成"）

`scripts/gen_contracts.py` 的 `DOMAIN_ENTITIES["subscription"]` 加 `SourceIdentifier` ⇒
`packages/contracts/src/subscription/dto.ts` 多出该 interface，并在 `src/index.ts` 导出。
`gen_contracts --check` 12 项幂等一致。
越界声明：`scripts/gen_contracts.py` 与 `src/index.ts` 不在继承卡的"所有权（写）"清单里
（那份清单是 V0.7.0 的，只列到 `services/manifest.py`），但同一行的"实体与 dto 同提交生成"
只能靠它们落地 ⇒ 记进 §6。

## 5. 静态面

`ruff check app tests` rc=0；`mypy app`（117 files，S8.2.1 起了 `identifier_resolver.py` 之后）rc=0；
`scripts/` 面另有 7 条**既有**告警（`check_docs_consistency.py` 的 W293/B007、
`check_entry_parity.py` 的 E741×2、`entry.py`/`guards.py` 的 E501×2 等）——
CI 的 lint 面是 `ruff check app tests`，看不到它们；本卡未触碰那些文件，只登记不顺手修。

## 6. 越界声明与后续分片

| 越界 | 为什么必须 |
|---|---|
| `docs/03_solution/decisions/adr-0014-source-identifiers.md`（新）与 `adr-index.md` 一行 | 卡面字段 13"迁移目录需 DDL 停转 ADR"⇒ 不动 ADR 就动不了 `alembic/**`；先例是 ADR-0013（同一队列、同一授权形状） |
| `scripts/migration_roundtrip_probe.py` 的 `SHAPES` 新登记 | P-60 修复后，**新头不登记 CI 往返步直接判红**——这不是可选动作 |
| `scripts/gen_contracts.py` + `packages/contracts/src/index.ts` | §4 |

- S8.2（`identifier_resolver.py`）、S8.3（协议升级 + 翻页）、S8.4（按源路由 + 降级开关）、
  S8.5.1（👤 TikHub openapi 核实）各自成一片，读数续写本文件。
- 本卡未做也不该在本卡做：给"没有走过入库"的存量源补标识行。`ensure_identifiers` 的唯一生产调用点
  是入库落库那一步（§7b），所以写路径覆盖的是"以后每次入库"，存量里既不建源也不入库的那部分
  仍靠迁移里的一次性回填（缺口的表现与后果写在 ADR-0014 §5）。

## 7. S8.2.1 标识补全（`app/services/identifier_resolver.py`）

先红（改前形状，scratch 探针，跑完回滚）：

```
[probe] 红（改前形状）：新建源 + 带 __biz 的样例链接 ⇒ 标识行数 = 0
[probe] 绿（改后）：ensure_identifiers ⇒ ['biz', 'sample_url']
[probe] 与解析层恒等：biz = 'MzA5NzIwNTQ1Mg=='（URL 里是 %3D%3D 书写）
[probe] 幂等：第二次调用不新增行 ⇒ ['biz', 'sample_url']
[probe] 落库明细 = [('biz', 'resolver'), ('sample_url', 'source')]
```

⇒ "红"不是"模块不存在"这一种（那太容易满足）：改前**表已在、列也在**（S8.1 已经落了底座），
缺的是"有人往里写"。所以红形取"新建源之后行数为 0"，绿形取"同样一步之后落库明细连 origin 都对"。

`tests/test_identifier_resolver.py` 的 8 条连库判据（另 6 条不连库）里，值得单独留名的三条：

| 用例 | 抓的是哪一种"看起来对" |
|---|---|
| `test_biz_derivation_is_the_parsing_layer_not_a_second_copy` | 只断"与 `parse_wechat_url` 恒等"不够——两处各抄一份同样代码时它也成立 ⇒ 另取 `%3D%3D` 与 `==` **两种书写**比同值（D-01b 的裂身份形状） |
| `test_a_biz_already_owned_by_another_source_is_not_taken` | A 用列登记 biz、B 的列空但样例链接指向**同一个** `__biz` ⇒ `sources` 的 `(type, external_id)` 唯一约束拦不住，拦得住的是本表 `(kind, value)`；改后行为是"不覆盖 + 告警 + B 只拿到 sample_url" |
| `test_ensure_is_idempotent` | 把幂等写成"每次读都插一行"在功能测试里看不出来（读出来还是那个 biz），只有计数能看出来 ⇒ 断 `count()` 两次相等 |

**ghid 不从 biz 凭空推，是实测结论不是偷懒**：`GHID_MAPPING_CHANNELS` 现读为空——
`dajiala.py:85`、`justoneapi.py:101`、`tikhub.py:16` 都**以 ghid 为入参**，
`wellbyte.py:14` 有映射但形状是「文章 URL → gh_」且按 credits 计费（TC-A4-04 实测 78cr）。
⇒ 留一条用例（`test_no_channel_claims_the_biz_to_ghid_mapping`）在将来有人填上这个常量时
**主动变红**，逼他把渠道兜底分支和用例一起补。卡面 ghid 那格的落地路径在 §7b。

## 7b. S8.2.1 的 ghid 半边：卡面判据与仓内证据的差，以及未测声明

卡面 S8.2.1 的交付原文是「从直抓 HTML 解析 `gh_` 原始 id（**以样本为准**），入库成功时写
`ghid`（零额外请求）」。这一半今天只能这样落，且必须把没证到的部分写清楚：

**① 样本面——本仓拿不到"真实直抓页面"**（逐条可复算的检索）：

| 检索 | 结果 |
|---|---|
| `grep -rl "profile_weixin" docs .docs apps/api` | 0 命中（仓内没有任何一份带帐号信息框的页面原文） |
| `apps/api/tests/fixtures/provider_payloads/dajiala_detail.json` 的 `data.html` | **142 字符**的桩（`walk` 实测），不是真页面 |
| 全仓 `mp.weixin.qq.com/s?__biz=` 形态的 URL | 只有合成夹具（`sn=aaaa1111`、`mid=2650000001`，见 `tests/fixtures/wechat_urls.py` 的形状声明） |
| `gh_b9465228558d` 的出处 | 四家 provider 的 **JSON 字段**（TC-A1-07/A3-07/A4-04），不是 HTML |

⇒ 「以样本为准」这一句在本卡**不可满足**：既不猜现网把 gh_ 挂在哪个变量名下，
也不为此发一次真实抓取（卡面零额外请求 + 本卡没有可抓的真实 URL）⇒ 登记 **P-67**，交回规划方。

**② 实现侧怎么做到"有则收、无则空"**：`ghid_from_html()` 的键名家族**镜像** `source_resolver._BIZ_RE`
的两支实证形态（`var X = "…"` = 2026-09 真实页面、`var X = "" || "…"` = M0 样本），只把 biz 换成
user_name；再加一支帐号信息框。token 形状 `gh_ + 6~40 位`取自四家实测值。
窄化的代价与理由：只断"解析得到 gh_"不够——把裸 `gh_[0-9A-Za-z]{6,}` 拿去搜整页，
正文里一句"加我微信号 gh_xxx"就会被写进 `(kind,value)` 全局唯一的约束里，
从此**真号主**入库时只能撞约束告警、不能覆盖。⇒ 两条负面判据：
`test_body_text_mentioning_a_gh_id_is_not_read_as_an_identifier`（正文里的 gh_ 不认、单引号写法不认、
短于下限不认）与 `test_without_page_html_the_ghid_slot_stays_empty`（没页面就留空，不报错也不猜）。

**③ 接线证明（变异测试，跑完回滚）**——"解析函数写成了死代码"这一族只有 AST 门看得见：

```
基线绿：14 passed
变异 1（kb.py 的调用删掉 html= 实参）⇒ 1 failed, 13 passed
        FAILED test_that_one_call_hands_it_the_page_it_already_fetched
变异 2（kb.py 的那一处调用整段删除）  ⇒ 2 failed, 12 passed
        FAILED test_the_resolver_has_exactly_one_production_caller
        FAILED test_that_one_call_hands_it_the_page_it_already_fetched
```

⇒ 两条判据分别红在"传什么"与"有没有人叫"，且 `test_the_resolver_has_exactly_one_production_caller`
把调用面钉死成 `[("services/kb.py", 1)]`——多一处调用同样红（第二个写入口正是 ADR-0014 要防的分裂）。
生产里"零额外请求"是结构性的：`_persist_document` 拿到的 `article.html` 就是本次直抓已在手的原文。

## 8. `SKIP_BASELINE_WIN` 的分片算法（本卡内还会动）

| 片 | 新增连库用例 | 累计 |
|---|---|---|
| 起点（STEP-10 交付 `066ceeb`） | — | 621 |
| S8.1.1 | `test_source_identifiers` 3 | 624 |
| S8.2.1 | `test_identifier_resolver` 8 | **632** |

每片的增量都是**该文件在无 DSN 下单跑**实测的 skipped 数（不是按"写了几个用例"推算），
收口前再做一次全量无 DSN 复测验总数并把 `@ci` 三条 run id 回填本节。

S8.2.1 这一片的四个读数（本机同一份工作树，两跑之间有且只有本片的改动）：

```
test_source_identifiers.py   单跑无 DSN ⇒ 3 passed, 3 skipped
test_identifier_resolver.py  单跑无 DSN ⇒ 6 passed, 8 skipped
全量无 DSN（= CI-Windows 的取材面）⇒ 1527 passed / 632 skipped   ← 与阈值逐字相等
全量有 DSN（独立 PG@5547，= ubuntu CI 的连库面）⇒ 2153 passed / 6 skipped / 0 failed
```

⇒ 632 不是推出来的：全量实测就是它。连库面 0 failed 证明新增的落库判据不是"跳过就算过"
（skip≠pass 这条在本卡是**两面各跑一次**来兑现的，不是只跑能过的那一面）。
