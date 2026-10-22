# EVD-V17-09 · STEP-09 执行方读数（RSS 作为一等信息源）

> 卡面：`docs/任务规划V0.13.0/steps/STEP-09-RSS一等信息源.md`（字段 12「允许修改」= 来源卡所有权矩阵，
> 来源卡 `docs/任务规划V0.7.0/steps/STEP-09-RSS一等信息源.md:11`）。
> 卡面字段 11 写的证据目录 `docs/任务规划V0.8.0/evidence/61358c3-09/` 本仓从未建过
> （与 P-58 / P-65 同一形状：继承卡在七个版本里逐字复制那一格）⇒ 按现行约定落在本目录。
> 交付基线 `b26fef5`（STEP-08 收口提交，三绿已核）。

## 0. 现读行号（卡面明令"禁止照抄来源卡读数"）

| 卡面锚（基线 61358c3） | 现读（交付基线 b26fef5） | 漂移 |
|---|---|---|
| `rss.py:99-128` 发现可用 | `_resolve_feed_url` 在 `rss.py:88`、`query_work_list` 在 `:102` | 是 |
| `rss.py:130-132` 详情硬返 None | `fetch_article_detail` 在 `rss.py:148` | 是 |
| `job_worker.py:100-107` `_is_permanent_error` 不含 10006 | 该函数在 `job_worker.py:154` | 是（+54 行） |

三处锚**全部漂移**，但每一处都按符号名重新锚定成功、判据本身未失效；卡面字段 16 的停转条件是
"漂移 >3 处或判据不可满足"，实测漂移 = 3 处（未 >3），且 V0.13.0 卡面「本版变更」第一条就是
"执行前先现读行号" ⇒ 按现读继续，不触发停并上报。所有权矩阵里的 `job_worker.py:100-107`
同理按**函数**理解（本卡只改 `_is_permanent_error` 一个函数体 + 一行 import）。

## 1. 先红（S9.1.1 / S9.2.1 卡面带 🔴，改前捕获）

命令：`pytest tests/test_rss_subscription.py -q`（真库 DSN 已设，未设会 skip 而非 fail，那不算读数）。

```
9 failed, 4 passed
```

| 用例 | 先红原因（改前形状） |
|---|---|
| `test_a_non_url_identifier_fails_instead_of_becoming_a_request` | `_resolve_feed_url` 末行 `return identifier`，biz 串被当成 feed 地址打出去 |
| `test_offsite_links_are_dropped_and_the_count_is_visible` | 无过滤、无计数 |
| `test_the_offsite_filter_shares_one_host_list_with_the_ingest_path` | 同上 |
| `test_malformed_url_counts_as_a_permanent_error` | `_is_permanent_error` 只认 20001/20003 |
| `test_resolve_does_not_retry_a_malformed_url` | 10006 落到 `except Exception` ⇒ 退避重试满预算 |
| `test_rss_registration_stores_the_feed_url_as_an_identifier` | `register_source` 无 `source_type` / `feed_url` 形参（TypeError） |
| `test_rss_registration_is_idempotent_on_the_feed_url` | 同上 |
| `test_an_unknown_source_type_is_rejected_not_treated_as_biz` | 同上——类型参数根本不存在，无从拒绝 |
| `test_the_route_body_accepts_the_card_camel_case_shape` | `RegisterSourceRequest` 没有 `type` / `feedUrl` 两个字段 |

改前就 **绿** 的 4 条是刻意放进去的反向边界，防止"加严"把合法形状一起退回：
`test_the_three_legitimate_identifier_shapes_still_resolve`（别名/直链/空标识取首个）、
`test_no_second_host_allowlist_is_written_in_the_provider`（当时 rss.py 里确实没有域名字面量）、
`test_network_errors_are_still_retried`、`test_a_feed_url_still_cannot_be_registered_as_a_biz`
（R8 L1-3 的 biz 形态校验在改前就拦得住 feed 地址——这条本来就该绿，不是本卡的成果）。

## 2. 交付后读数（判据全部转绿）

| 范围 | 命令 | 读数 |
|---|---|---|
| 本卡新件 | `pytest tests/test_rss_subscription.py` | `15 passed`（4 条连库真跑） |
| 相邻族 | `pytest tests/test_rss_subscription.py tests/test_rss_provider.py tests/test_channel_routing.py tests/test_identifier_resolver.py` | `115 passed / 0 skipped`（真库） |
| 受本卡改动影响的服务/发现/订阅族 | `pytest tests/test_channel_routing.py tests/test_rss_provider.py tests/test_discovery.py tests/test_p2_subscription.py tests/test_r02_subscription_lifecycle.py tests/test_source_identifiers.py` | `161 passed / 0 skipped` |
| 全量（真库 `bothot_test`@5547 / PG 16.4） | `pytest -q` | **2208 passed / 6 skipped / 0 failed**，1054.63s（STEP-08 收口时 2193 + 本卡 15 条 = 2208；6 条 skip 全部是 LangBot/Redis 不可达族，PG 不可达族 0） |
| lint | `ruff check app tests`（0.12.12） | All checks passed |
| 类型 | `mypy app` | Success: no issues found in 117 source files |
| skip 基线门 | `pytest tests/test_ci_windows_skip_gate.py` | `6 passed`；`SKIP_BASELINE_WIN` 637 → **641**（+4，按文件实测） |
| 文档一致性 | `python scripts/check_docs_consistency.py` | 23 个路径引用，0 个不存在 |

契约面：本卡改了 `POST /api/v1/sources` 的请求模型（加 `type` / `feedUrl`，两者都有默认值 ⇒ 旧客户端形状不变）。
`test_contract_jsonschema.py` 与 `test_collection_contract.py` 在全量里绿。

## 3. 摘除反证（mutation，逐处摘、逐处看红）

不改仓库里的生产文件：用 scratch 插件（`-p probe_s09`，脚本在本仓之外）在运行时把某一处改动摘掉，
看**恰好是哪几条**变红。每一行都跑 `tests/test_rss_subscription.py`（+ 该族邻居）。

| 摘掉的东西 | 还原成的形状 | 变红的判据 | 计数 |
|---|---|---|---|
| P1 未知标识报错 | `_resolve_feed_url` 末行回到 `return identifier` | `test_a_non_url_identifier_fails_instead_of_becoming_a_request` | 1 |
| P2 外链过滤 | `_split_offsite` ⇒ `(list(items), 0)` | 计数可见 / 共享名单 / 跨 feed 累计 | 3 |
| P3 worker 永久失败 | `_is_permanent_error` 去掉 10006 | `test_malformed_url_counts_as_a_permanent_error` | 1 |
| P4 单篇不重试 | `_resolve_with_retry` 去掉 10006 那一支 | `test_resolve_does_not_retry_a_malformed_url` | 1 |
| P5 标识写入口 | `ensure_identifiers` ⇒ 什么都不写的空调 | 注册落库 + 幂等 | 2 |
| P6 rss 分支 | `ensure_identifiers` 把 rss 当公众号补（写 sample_url 不写 feed_url） | 注册落库 + 幂等 | 2 |
| P7 路由读的那一格 | `CHANNELS["rss"].required_identifier` ⇒ `biz` | `test_the_registered_identifier_is_the_one_the_router_reads` | 1 |
| P8 camelCase | `feedUrl` 别名 ⇒ `feed_url` | `test_the_route_body_accepts_the_card_camel_case_shape` | 1 |

八处摘除**各自只红它该红的那几条**，没有"摘掉 A 却靠 B 绿"的耦合；P5/P6 同红那两条注册判据，
说明"注册时补标识"这一格的承重是**调用点 + rss 分支**两处，任缺一处都读得出来。
全部还原后复跑：`61 passed / 0 failed`（`grep -c MUTATION rss.py` = 0，工作树无残留）。

## 4. S9.1.2 的实现选择：判据复用而不是名单复用

外链过滤**不写**第二份域名名单，而是把每条 item 的链接喂给入库主路径自己的谓词
`source_resolver.normalize_article_url`（它同时管 scheme / 白名单域名 / 512 超长 / 控制字符）：

```
判"能不能入库" = 判"入库主路径能不能吃下这个 URL"
```

- 为什么不用 `urlsplit(...).netloc in ALLOWED_HOSTS`：那仍是"同一个事实两处实现"，
  名单一致但**周边谓词**不一致（超长、控制字符、无 scheme 的条目会被当成"外链之外的东西"漏下去）。
- 代价与如实声明：`rss.py` 现在 import 了 `source_resolver`（带着 httpx）。这个依赖方向是
  provider→provider，不碰 services 层，可接受。
- 无域名名单的门由 AST 判据钉：`test_no_second_host_allowlist_is_written_in_the_provider`
  扫 rss.py 里含 `.qq.com` 的字符串常量 ⇒ 必须为空集。判 AST 而不是判 grep 措辞。

`total` 的语义在本卡被明确成"**上游给了几行**"（截断后、过滤前），与返回行数分开：
MIXED_FEED 5 条里 2 条可入库 ⇒ `page.total == 5`、`len(page.rows) == 2`、`filtered_offsite == 3`。
这条与 STEP-08 的 `build_work_list_page`（"静默丢行必须留下计数"）同族。

## 5. RSS 源的身份落在哪：三格各管一件事

| 位置 | 值 | 实测 |
|---|---|---|
| `sources.type` | `rss` | 注册后 `db_session.get(Source, id).type == "rss"` |
| `sources.url` | feed 地址原文 | `== FEED` |
| `sources.external_id` | `rss:` + sha256(feed) 前 32 位 | 不直接断言，由幂等断言覆盖（同 feed 两次注册 ⇒ 同一 `sourceId`） |
| `source_identifiers(kind='feed_url')` | feed 地址原文 | `{kind: value}` 查询结果 **恰等于** `{"feed_url": FEED}` ⇒ 同时证明没有误写 `sample_url`/`biz` |

为什么 `external_id` 不放 feed 原文：该列 `String(128)` + `uq_source_type_external`，而 feed 地址可到 512。
截断会让两条不同 feed 撞成同一个源（数据合并级错误），留空会被唯一约束挡住第二个 RSS 源。
副作用如实登记：**GET/PATCH /sources 的视图把 `external_id` 放在 `biz` 这一格**，
所以 RSS 源在清单里那一格是一个 sha 摘要（见 P-76）。

`kind='feed_url'` 这一格是 `IDENTIFIER_KINDS` 里第一次有"第二种源真正用到第二种标识"——
STEP-08 建表时它就列在集合里，但没有任何写入方。P7 反证（把渠道读的格改成 `biz` ⇒ 链断）
证明这一格不是装饰。

## 6. 越界与所有权（本卡动过的、卡面上没写的路径）

卡面「允许修改」= `app/api（订阅接口）`、`providers/article_sources/rss.py`、`services/kb.py（错误分类）`、
`job_worker.py`、`docs/RSS订阅渠道.md`。本卡实际还改了四处，**逐条登记**（P-74）：

| 路径 | 为什么非改不可 | 有没有更小的替代 |
|---|---|---|
| `services/subscription.py` | 卡面 S9.1.1 要"订阅支持 `{type:'rss', feedUrl}`"，而注册逻辑在 service（`app/api` 只有请求模型 + 一行委托）。在路由里直查 `Source` 表 = 开第二个源写入口，比越界更糟 | 无 |
| `services/identifier_resolver.py` | 不加 rss 分支，`ensure_identifiers` 会把 feed 地址登记成 `sample_url`（占掉全局唯一约束的一格并给个假名字），且 `feed_url` 永远空 ⇒ 卡面 3 的穿透链在中间断 | 在 subscription.py 直插 `SourceIdentifier` = 第二个标识写入口，正是 ADR-0014 要防的分裂 |
| `tests/test_identifier_resolver.py` | STEP-08 的 AST 门钉"标识补全只许有两处调用"，本卡合法地加了第三处 ⇒ 门**改为点名三处**（`kb` / `scheduler` / `subscription`），一条没删 | 不放宽：仍是"每处恰一次 + 逐处认领" |
| `tests/test_rss_provider.py` | 两条既有判据的样本链接用 `example.com`，与 D-V2-03 的外链过滤正面冲突 | 只换**喂进去的 feed 内容**（改成白名单域名），断言一条没动；P2 反证显示过滤被摘掉时它们仍绿 ⇒ 它们不再依赖过滤是否存在 |

条件迁移 `ab1006c3a`（04 表"条件"）**未开**：`sources.type` 是 `String(32)`（加一类源零迁移，
AGENTS.md 关键约束 3）、`source_identifiers.kind` 是 `String(16)` 且无 CHECK、
`IDENTIFIER_KINDS` 已含 `feed_url` ⇒ 本卡没有任何 DDL。单头仍是 `ab1006c2a`。

## 7. 未测（不编造读数）

- **没有任何活体 RSS 抓取**：全部走 `httpx.MockTransport`。预置 `FREE_RSS_FEEDS` 那 20 条地址
  今天是否还活着、回链落在哪个域，本仓无样本 ⇒ 文档里写"未测"，不写成"能入库"。
- **RSS 端到端入库未测**：注册 → 订阅 → 调度 → 清单 → Job 的完整链路只在判据层接上
  （注册写 `feed_url` + 路由读 `feed_url` 两条各自绿），没有跑过一次真的 `run_incremental_sync`。
- **`normalize_article_url` 当过滤谓词的误杀率未测**：白名单当前只有 `mp.weixin.qq.com`，
  所以除微信镜像 feed 之外**整批**会被滤——这是裁决 D-V2-03 的直接后果，不是本卡新增的策略。
- 五家供应商的 API Key 一律未用于真实付费调用（本卡也不需要：rss 侧全 mock）。

## 8. 登记项

| P 项 | 内容（摘要，全文在 `docs/任务规划V0.12.0/00-README.md` 台账） |
|---|---|
| P-74 | 本卡四处越界（含 STEP-08 的 AST 门改点名三处调用）——所有权矩阵没覆盖 RSS 身份写入链 |
| P-75 | `filtered_offsite` 只到 provider 实例，`WorkListPage` 契约里没有这一格（形状的归属在 STEP-08）⇒ 跨轮/跨进程汇总读不到 |
| P-76 | `GET/PATCH /sources` 的视图把 `external_id` 放在 `biz` 格：RSS 源在清单里显示为 sha 摘要，且 `list_sources` 的 `type` 参数与注册类型无联动校验 |

## 9. 三绿（验收面 = `@ci` ubuntu-latest；skip≠pass）

| 工作流 | run id | 结论 |
|---|---|---|
| CI | 待回填 | — |
| Security | 待回填 | — |
| CI-Windows | 待回填 | —（本平台对连库结论零主张，只读 skip 计数 = 641 与未知族） |

交付提交 sha：待回填（本文件先写"待回填"，不预测读数）。
