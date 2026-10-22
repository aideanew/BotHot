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
        FAILED test_the_resolver_has_exactly_two_claimed_production_callers
        FAILED test_that_one_call_hands_it_the_page_it_already_fetched
```

⇒ 两条判据分别红在"传什么"与"有没有人叫"，且 `test_the_resolver_has_exactly_two_claimed_production_callers`
把调用面钉成一份**带名字与次数的清单**——多一处同样红（第二个没人认领的写入口正是 ADR-0014 要防的分裂）。
生产里"零额外请求"是结构性的：`_persist_document` 拿到的 `article.html` 就是本次直抓已在手的原文。
（本条在 S8.2.1 交付时清单是 `[("services/kb.py", 1)]`；S8.4 加了调度器那一处，
被这条门当场拦住并迫使改动写进判据——见 §10e。改名一次是为了名字不与内容撒谎。）

## 8. `SKIP_BASELINE_WIN` 的分片算法（本卡内还会动）

| 片 | 新增连库用例 | 累计 |
|---|---|---|
| 起点（STEP-10 交付 `066ceeb`） | — | 621 |
| S8.1.1 | `test_source_identifiers` 3 | 624 |
| S8.2.1 | `test_identifier_resolver` 8 | 632 |
| S8.3 | `test_channel_routing` 2 | 634 |
| S8.4 | `test_channel_routing` 再 3（三条调度器判据） | **637** |

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
**本档在 S8.3 之后是 634**（见 §8 表与 §9a 的单跑读数）；S8.2.1 那两个数（1527/632）
是当时的快照，不复用为终值。

**S8.3 又加了 2 条连库判据 ⇒ 本档最终 634**（`test_channel_routing` 的两条服务层判据要真表
`article_manifest`）：621 + 3（S8.1.1）+ 8（S8.2.1）+ 2（S8.3）= **634**。

这里有一处**自我更正**要留在台账里：S8.2.1 提交时我在 `ci-windows.yml` 的注释里写过一行
"S8.3 那批离线判据（0 条连库）不需要动阈值"——那是按"服务层的翻页判据可以脱库跑"的**假设**写的，
而实测那两条都要 `db_session`。假设错，按读数改数（该注释已就地更正，不是悄悄覆盖）。

## 9. S8.3.1/S8.3.2 协议升级（`WorkListPage` 端口 + 服务层止页）

先红读数（改前形状，静态可复算，比"跑一次报错"更省且不依赖本机依赖）：

```
git grep -c "query_work_list_page" HEAD -- apps/api/app   ⇒ 0 命中（端口在主干上根本不存在）
工作树同一条                                                ⇒ base.py 4 / 五家 provider 各 1 / manifest.py 2
```

⇒ 这一片的"红"是**结构性缺失**，不是形状不符；所以判据的重点放在"接线之后不许退回去"，
用两条变异把每条判据的判定力实测出来（跑完即回滚）：

| 变异 | 改动 | 读数 |
|---|---|---|
| A | `manifest._fetch_page` 里 `paged = getattr(...)` 改成恒 `None`（= 端口升级了但没人用） | `2 failed, 48 passed`：`test_sync_follows_the_cursor_and_stops_when_there_is_none` + `test_the_paged_port_branch_is_actually_taken_by_the_service`；**`test_manifest_sync.py` 全绿** ⇒ 旧端口渠道（RedFox）确实没被波及 |
| B | `justoneapi.query_work_list_page` 的 `next_cursor=None` 改成 `"2"`（= 编一个游标） | `1 failed, 28 passed`：`test_no_channel_hands_out_a_cursor_it_did_not_measure[justoneapi]` |
| 基线 | 回滚后 | `tests/proofs + tests/test_channel_routing` ⇒ `62 passed`；`test_channel_routing + test_provider_contract + test_manifest_sync` ⇒ `221 passed` |

⇒ 变异 A 只红两条而不是全红，正是想要的分布：服务层的行为判据 + 一条直接看分支的 AST 门。
只留前者会漏"分支写死一半"，只留后者会漏"游标没真的传下去"。

### 9a. 判据自己先红过一次：级别键读错就是"永远成立的断言"

`test_an_all_dropped_page_is_error_not_just_a_warning` 第一次跑（本机全量连库面）：

```
1 failed, 2182 passed, 6 skipped
FAILED test_an_all_dropped_page_is_error_not_just_a_warning
  AssertionError: assert 'None' == 'error'
  捕获项原文：{'channel': 'tikhub', 'attempted': 2,
              'event': 'discovery.page_all_dropped', 'log_level': 'error'}
```

⇒ 生产代码是对的，错在判据读了 `level` 这个**不存在的键**——`capture_logs()` 用的是 `log_level`。
这类错的可怕之处不在红，而在它**可以绿**：若当初写成 `assert events.get(...) != "warning"`，
读错键得到 `None` 也照样通过，判据就成了永真式。所以修完断言后把键名一起钉在注释里，
并让判取"等于 `error`"而不是"不等于别的"。修后本机读数：
`tests/proofs + tests/test_channel_routing + tests/test_ci_windows_skip_gate` ⇒ `69 passed`；
`test_channel_routing` 无 DSN 单跑 ⇒ `28 passed / 2 skipped`（连库面 2 条，与 634 的算术一致）。
修后复跑受影响的四个族（连库面）：`test_channel_routing + test_provider_contract + test_manifest_sync
+ tests/proofs + test_collection_contract` ⇒ `415 passed / 23 skipped`。

**没有假装跑过全量**：修完这一条之后又起了一次全量连库复跑，跑到一半被中断（exit≠0、无终端行），
所以本片的全量终判**不由本机给**，由 CI 的 ubuntu 全量面（`@ci`）判——
本机能负责的是：修前的全量读数只有那一条红（`1 failed, 2182 passed, 6 skipped`），
红项已修且修复面已被上面那 415 条覆盖。收口批会再跑一次完整全量把终值写回本节。

### 9b. 三家夹具的游标检索，与"端口交付、翻页未交付"的界线

| 渠道 | 响应侧游标 | 请求侧字段名 | 本卡 `next_cursor` |
|---|---|---|---|
| JustOneAPI | ✅ 实测在案（`justoneapi.json` 的 `data.PagingInfo{Offset, IsEnd}`） | ❌ 从未实测（TC-A3 只跑到首页） | `None` |
| TikHub | ❌（夹具里 offset/cursor/next 一键皆无；余额 0，TC-A2-02b 402） | 请求侧 `offset` 在案（首页传空串） | `None` |
| Wellbyte | ❌（夹具只有 `meta.endpoint`） | ❌ | `None` |
| Dajiala | — 上游明说"不支持翻页，仅返回最新批次"（TC-A1-04 备注） | — | `None` |
| RSS | — feed 一次给全 | — | `None` |

⇒ 卡面 S8.3.1 的"provider 交出游标"这一半**在本卡不可满足**，两个具体的拦路石：
① 没有一家同时实测到"响应游标 + 请求侧字段名"（猜的键名会让上层每轮多花一次付费调用买回同一批条目，
表现是"清单不增长"而不是"接线错了"）；② 想在本卡把它做出来必须把行解析从 `query_work_list` 搬进新端口，
而 `tests/proofs/test_provider_shapes.py` 是按**函数名** `query_work_list` 定位"渠道读哪些上游键"的
（实测搬走 ⇒ 4 条形状判据红，读数见下），那个文件属于 STEP-00T，不在本卡所有权内。
⇒ 登记 **P-68**，本卡交付"端口 + 类型 + 服务层翻页机制"，真游标留给有活体读数的那一卡。

搬动行解析的实测代价（我先试过再撤回）：

```
把 dajiala/justoneapi 的解析搬进私有方法后：
tests/proofs ⇒ 4 failed, 282 passed
  test_sample_covers_every_main_path_read_key[dajiala.json / justoneapi.json]
  test_paid_provider_rows_reach_a_manifest_identity_source[dajiala.py / justoneapi.py]
  （报错原文：`query_work_list 一个 .get()/[] 读取点都没导出 ⇒ 提取器失效，证据为空`）
撤回成"解析仍住在 query_work_list，新端口复用它"后 ⇒ 286 全绿
```

### 9c. 行级策略：为什么"丢且出声"只写一份

`build_work_list_page` 是五家唯一的收页口。约束不过的行（`url` 短于 8、缺 id/url/title）
`warning` 一条 + 整页再计数一条。两条反面形状都在本仓历史上出现过：一条脏项打挂整页（P-17）
与整页静默消失（P0-3），所以"抛"和"默默丢"都不许。

一处刻意的设计：**typed `publish_time` 是加一格，不是换一格**。
`_map_row` 的别名表按 `publishTime` 优先，而 `_parse_time` 不认 datetime 对象
（实测：给它 `datetime` 返回 `None`）⇒ 若 provider 把原键改名，时间整列静默变空，
看起来像"上游没时间"。判据因此取"两条路径解出同一个瞬间"而不是"字段非空"；
RSS 的 RFC 822 那一支**不在 provider 层解析**（那份解析全仓只该有一份，见 P-28 的口径未定），
它的 typed 格就是 `None`，由判据 `test_non_numeric_time_shape_is_left_to_the_consumer` 钉住。

代价如实登记：迁移后的 provider 里"被丢掉几行"只在这两条日志里可见，
`ManifestSyncReport.skipped` 计的是消费端解不出身份的行——两者不是同一件事，
本卡没有指标面（`core/metrics.py` 不在所有权内），也不顺手加一个指标（那是 STEP-05 的地盘）。

更硬的一层：**旧端口路径上这些行原本会走 `_map_row` 返回 None ⇒ `page_dropped == page_rows`
⇒ `_note_all_skipped_page` 打 P0-3 那条告警**；换成新端口后它们在上游就被契约挡下，
服务层收到的是空页，于是按"上游没内容"止页、`skipped=0`、`all_skipped_pages=0`
⇒ 告警面在这一页上是空的。本卡把"整页丢光"升成 `error`（`discovery.page_all_dropped`，
判据 `test_an_all_dropped_page_is_error_not_just_a_warning`），缺口本身登记为 **P-69**——
它是本卡的改动造成的，不是继承来的，所以更要写在台账里而不是只写在代码注释里。

`_parse_time` 对 datetime 对象的行为是实测的（不是读码推测）：

```
_parse_time(datetime(2026,9,28,8,0, tz=UTC))            ⇒ None
_parse_time("1790659200")                                ⇒ 2026-09-29 05:20:00+00:00
_parse_time("2026-09-28T08:00:00+00:00")                 ⇒ 2026-09-28 08:00:00+00:00
```

⇒ 第二行与 typed 格解出的是同一个瞬间（判据 `test_typed_time_and_original_key_are_the_same_instant`）；
第一行就是"把 `publishTime` 改名成 typed datetime"的后果——时间整列静默变空，
看起来像"上游没时间"。所以 `_fetch_page` 用 `model_dump(mode="json")` 而不是 python 模式。



### 9d. S8.3 的终值读数（补跑，同一份工作树 = 提交 `211533c`）

| 面 | 读数 |
|---|---|
| 全量连库（本机 PG@5547） | `2183 passed / 6 skipped / 0 failed`（= 上一档 2153 + 本片 30 条） |
| 全量无 DSN（= CI-Windows 取材面） | `1554 passed / 634 skipped` ⇒ 与阈值 `634` 逐字相等 |
| CI（ubuntu，验收面） | run 39694539066 @211533c = success |
| Security | run 39694539158 @211533c = success |
| CI-Windows | run 39694539088 @211533c（634 的验证在这一条上） |

⇒ 上一段说的"收口批会再跑一次完整全量"已经兑现：2183 与 634 两个数都是**补跑后的实测值**，
不是从 2153/632 推的。CI-Windows 那条如果与 634 不符，红在本节留痕，不改阈值凑数（D-V10-11）。

**S8.4 又加 3 条连库判据 ⇒ 本档 637**（同文件无 DSN 单跑实测 `34 passed / 5 skipped`）；
634 这一档的 CI-Windows 终判已在 `@ci` 落地（三条见下表），不沿用为终值。

| 提交 | CI | CI-Windows | Security |
|---|---|---|---|
| `211533c`（S8.3） | run 39694539066 success | run 39694539088 success（634 的验证在这条上） | run 39694539158 success |

## 10. S8.4.1 按源标识选渠道 + 降级开关

先红读数（改前形状，静态可复算）：

```
git grep -c "required_identifier" HEAD -- apps/api/app  ⇒ 0 命中
git grep -c "select_channels"     HEAD -- apps/api/app  ⇒ 0 命中
工作树同两条                                             ⇒ registry.py 11 处 / select_channels 三处引用
```

四条变异实测（每条单独施加、跑完立即回滚；回滚后 `39 passed`）：

| 变异 | 改动 | 读数 | 这条抓到的是什么 |
|---|---|---|---|
| A | `select_channels` 的标识筛选整条去掉（候选=全部可用） | `4 failed, 35 passed`（四条筛选判据全红） | S8.4.1.1：拿 biz 去打要 ghid 的接口不报错、只回空清单 |
| B | 排序键里把 `cost_rank=None` 当 0（未知=免费） | `4 failed, 35 passed`（含两条调度器判据） | 未实测成本被当成最便宜 ⇒ 最贵那家拿到每一次首发 |
| C | 去掉"只多试一家"的上限（`spent >= 2` 删除） | **1 failed, 38 passed** | 见下方"判据的局限" |
| D | `fallback` 开关恒 True（忽略传入值） | `1 failed, 38 passed`：`test_degradation_off_...` | 开关关着却在试第二家 = 运营以为没花钱而每轮多打一家 |

### 10b. 判据的局限（写在交付里，不藏在脑子里）

变异 C 只红**一条**：`test_degradation_on_calls_the_second_channel_exactly_once` 抓不到它——
那条的第二家（dajiala）是成功的，成功就 `break`，上限在这条路径上根本看不见。
有牙的是 `test_degradation_on_still_raises_when_the_second_channel_fails`：两家都失败时，
没有上限就会去调第三家，`calls` 从 2 变 3 就红。⇒ "1 次"这个判据的判定力**来自失败路径**，
不来自成功路径；只留前者会留下一条没有牙齿的判据。

### 10c. 降级开关今天打不开，是实测结论不是遗漏

```
"discovery_fallback_enabled" in Settings.model_fields   ⇒ False
bool(getattr(Settings(), "discovery_fallback_enabled", False)) ⇒ False
```

⇒ 机制（`make_routed_sync_runner(..., fallback_enabled=...)`）已交付并有判据（§10 表的 C/D 两条），
但**运营侧还打不开它**：那一行配置位在 `app/core/config.py`，不在本卡所有权内。
判据 `test_the_degradation_switch_has_no_config_field_yet` 钉的就是"字段不存在"这个现状——
将来有人补上那一行，这条会**红**，那时该改的是本节与 P-70 的处置，而不是顺手把断言删掉。
登记 **P-70**。

### 10d. 顺带撞到的一个飘（不是本卡造成的，但读数留在本卡）

S8.4 的判据要在 `test_channel_routing + test_scheduler + test_discovery` 合并跑，
其中 `test_scheduler.py::test_run_once_runs_due_subscriptions_in_parallel` **红过一次**：

| 组合 | 次数 | 结果 |
|---|---|---|
| 本卡文件 + scheduler + discovery | 3 | 2 绿 1 红（红的是那条并行判据） |
| scheduler + discovery（不带本卡新文件） | 3 | 2 绿 1 红 |
| 只跑那一条 | 5 | 5 绿 |
| A/B：HEAD 版 scheduler（去掉本卡改动）+ scheduler + discovery | 3 | 3 绿 |
| A/B：本卡版 scheduler 还原后 + 同上 | 6 | 6 绿 |

⇒ 红与本卡改动**无因果**（同一组合在我没改调度器时也红过；A/B 各跑都不稳定复现）。
它的形状是判据自称"不受测试机负载影响"，实际靠 `asyncio.sleep(0.05)` 造出的 50 毫秒墙钟窗判重叠。
⇒ 登记 **P-71**（含"换成 `asyncio.Event` 会合点"的出门判据），本卡不改那个文件。
顺带一条环境读数：本机隔离 PG（`D:/tmp/pg16`）在今晨停过一次，5 条连库判据当时是被 conftest
判成"PG 不可达 ⇒ skip"而不是失败——`2153/2183` 那种"passed"数一旦掉到 `34 passed / 5 skipped`
就是库没了的信号，这个对照关系比看退出码可靠（PG 起来后 39 条全绿）。

### 10e. S8.2.1 那道接线门当场拦下了 S8.4 的第二处调用

S8.4 的调度器要按源标识选渠道，于是加了对 `ensure_identifiers` 的调用。全量无 DSN 复测时：

```
1 failed, 1560 passed, 637 skipped
FAILED tests/test_identifier_resolver.py::test_the_resolver_has_exactly_one_production_caller
  assert hits == [("services/kb.py", 1)]
   +  where hits = [('services/kb.py', 1), ('services/scheduler.py', 1)]
```

⇒ 这条门是 S8.2.1 那批写的，它的存在理由就是"不许出现第二个没人认领的写入口"，
这次它抓到的是**本卡自己的**新增调用点。处置方式是把第二处的角色写进判据
（`kb` = 入库时写、`scheduler` = 按源路由前的读侧补行，两处各一次，第三处仍红），
而不是把断言放松成"≥1 处"或删掉——放松的措辞会让下一次真正的分裂静默通过。
判据的名字也一并改掉（原名"exactly_one"已与内容不符，名字不该对内容撒谎）。



```
"discovery_fallback_enabled" in Settings.model_fields   ⇒ False
bool(getattr(Settings(), "discovery_fallback_enabled", False)) ⇒ False
```

⇒ 机制（`make_routed_sync_runner(..., fallback_enabled=...)`）已交付并有判据（§10 表 C/D 两条），
但**运营侧还打不开它**：那一行配置位在 `app/core/config.py`，不在本卡所有权内。
判据 `test_the_degradation_switch_has_no_config_field_yet` 钉的就是"字段不存在"这个现状——
将来有人补上那一行，这条会**红**，红的时候该做的是更新 EVD 本节与 P-70 的处置，
而不是把断言删掉。登记 **P-70**。





## 11. S8.5.1 TikHub 端点核实（👤 位，本批用"零成本可复算的官方契约"完成）

卡面写"人核 `api.tikhub.io/openapi.json`（U-04），结论写 registry `verified_scope`；不符则
`implemented=False` + reason"。本批的核实**不需要凭据也不产生费用**，所以由机器拉取官方契约完成，
读数逐条可复算（GET 一个公开 JSON，无 key、无计费）：

```
curl --noproxy "*" https://api.tikhub.io/openapi.json   ⇒ HTTP 200，3,091,262 字节
paths 总数            ⇒ 1050（与 2026-09-29 那次读数逐字相同 ⇒ 契约未漂移）
含 wechat 的 paths      ⇒ 26 条；其中 /api/v1/wechat_mp/ 共 11 条、全部 v2、web/ 一条都没有
代码在打的那条          ⇒ /api/v1/wechat_mp/web/fetch_account_articles  → 不在 paths 里（False）
现行那条                ⇒ /api/v1/wechat_mp/v2/fetch_account_articles   → 在（POST）
请求 schema FetchAccountArticlesRequest ⇒ username 必填；page_size 默认 20；offset；item_show_type；raw 默认 true
offset 的官方描述       ⇒ "翻页游标（base64），首页留空；翻页传上一页响应的 next_offset"
响应 schema             ⇒ ResponseModel.data = anyOf[{}, null]（**没有字段表**）
```

三条结论，各自管一件不同的事：

1. **发现格与契约不符 ⇒ `implemented=False` + `reason`**（卡面给的处理）。同族 `web/*` 的 404 是
   活体实测（TC-A2-04），而本条路径本身没打活体（余额 0，TC-A2-02b 402）——
   `reason` 里把这两件事分开写，不让"没打活体"混进"实测过"。
2. **`select_channels` 从此排除 `implemented=False` 的渠道**（判据
   `test_an_unwired_channel_is_reported_but_never_dispatched`，变异读数见 §11b）。
   而 `available_channels()` 那一轴**不动**：它答"配了 key 吗"（STEP-28 的三轴分离口径），
   合并成一个布尔就回到本仓反对过的那个形状。
3. **P-68 的响应侧游标对 tikhub 仍未闭合**：官方文字指向 `next_offset`（在**请求参数的描述里**），
   而 `ResponseModel.data` 在契约里没有字段表 ⇒ 仍然只能写"契约说有这么个字段，形状不在案"。
   这就是为什么本卡没有顺手把 tikhub 接成真游标翻页。

### 11b. 摘掉"未实接不派发"这道过滤的变异读数

```
把 `pool = [n for n in available_channels(s) if CHANNELS[n].implemented]` 改回不筛 implemented
⇒ 5 failed, 35 passed
  test_an_unwired_channel_is_reported_but_never_dispatched / test_preferred_channel_leads_only_when_it_is_eligible
  / test_eligible_channels_come_back_in_cost_order
  / test_degradation_on_calls_the_second_channel_exactly_once
  / test_degradation_on_still_raises_when_the_second_channel_fails
还原 ⇒ 35 passed / 5 skipped
```

⇒ 后两条是**降级判据**：一个未实接的渠道混进候选，被派到的是"必然拿不回东西"的第一家，
降级机制看起来在工作、实际每一次都在多打一家 ⇒ 核实结论不落到派发面上，就只是一句注释。

### 11c. 这一格仍然欠一个人类决定

核实做完了，但"要不要为此切端点"不是执行方能定的：切到 v2 需要一次**有余额的活体调用**才能确认
响应形状与 `next_offset` 的位置，而那要花钱（$0.001~0.01/请求）。⇒ 端点切换与真游标接线一起
登记为 **P-72**，归 STEP-03/20 的证据面；本卡只把不匹配固定在事实面上（registry + 判据 + 本节）。

## 12. 本卡终值读数与一条流程教训

| 面 | 终值（本机，提交 `df488f7` + 本收口批的工作树） |
|---|---|
| 全量连库（独立 PG@5547，复刻 ubuntu CI 的连库面） | `2193 passed / 6 skipped / 0 failed`（1036.50s） |
| 全量无 DSN（复刻 CI-Windows 的取材面） | `1562 passed / 637 skipped`（1094.93s）——与阈值 `637` 逐字相等 |
| `ruff check app tests` / `mypy app` | 均 rc=0（mypy 面 117 files） |
| 已交付 | S8.1.1（迁移 `ab1006c2a` + 回填 + ADR-0014）、S8.2.1（标识补全接进入库链）、S8.3.1+S8.3.2（`WorkListPage` 端口、两端口归一、服务层止页）、S8.4.1（按源标识选渠道 + 降级只多试一家）、S8.5.1（TikHub 端点核实并落到派发面） |
| 交回规划方 | P-66（同一编号两个判据版本）、P-67（ghid 无样本可证）、P-68（响应游标未实测 + 解析被函数名锚钉住）、P-69（整页丢光的告警面变薄）、P-70（降级开关没有配置位）、P-71（并发判据会飘）、P-72（TikHub 端点切换要活体）、P-73（卡面验证命令点名的 `apps/api/tests/test_e2e_collection.py` 在本仓不存在） |

### 12b. 一条我自己撞上的流程错：全量跑期间不许动工作树

第一次全量连库复跑读数 `1 failed, 2192 passed, 6 skipped`，红的是
`test_provider_defects_p15_p17.py::test_p16_the_degrade_is_narrower_than_a_blanket_except[fetch_article_detail]`。
它用 `inspect.getsource(TikhubClient.fetch_article_detail)` 读**源码**判"降级只兜领域异常"，
而我在那一轮跑到一半时正在改 `tikhub.py` 的模块文档串——`getsource` 读到的是一份被截断/半写的内容。
单跑该条 2 passed、与相邻两个文件组合跑 243 passed、干净全量重跑 2193 passed 0 failed。

⇒ 结论不是"判据脆弱"，而是**我的测量动作污染了被测面**：只要判据里有"读源码"这一类
（本仓的 AST 门与 `inspect.getsource` 门不少），跑套件期间就不能再改工作树。
这条与 P-63（`capture_logs` 对窗外 logger 失明）是同一族：判据看起来在测代码，实际测的是"那一刻文件系统的状态"。
