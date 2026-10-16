# S3.4.1（P-14）provider 覆盖率补口：详情兜底 / 关键词搜索 / `_request` 错误映射

批次：`STEP-03` 余项 **S3.4.1**，发布条目 **P-14**（`docs/任务规划V0.12.0/00-README.md` §4 末行）｜
基线 `main@d044d2a`（本会话开工时 `git log -1` 现读）｜读数标机器位：**`@win`** = 本机 Win10 + `apps/api/.venv`。
**生产代码零改动**（`git status --short` 只见 `tests/**` 与本文；工作树与他人共享，未做任何暂存）。

## 1. 判据命令与前后读数

命令（P-14 出门判据原文那条，逐字）：

```
cd apps/api && .venv/Scripts/python.exe -X utf8 -m pytest tests/test_provider_contract.py \
  tests/test_rss_provider.py tests/test_manifest_sync.py -q \
  --cov=app.providers.article_sources --cov-report=term-missing
```

| 模块 | 前（开工现读） | 后 | 仍缺的行 |
|---|---|---|---|
| `dajiala.py` | **50%** | **100%** | 无 |
| `justoneapi.py` | **43%** | **99%** | 115（按构造不可达，见 §6） |
| `tikhub.py` | **52%** | **100%** | 无 |
| `wellbyte.py` | **44%** | **99%** | 134（同上） |
| `rss.py` | 79% | **100%** | 无 |
| `base.py` | 100% | 100% | 无 |
| `__init__.py` | 45% | 100% | 无 |
| TOTAL | 55% | **99%** | — |

- 判据要求的是**四家付费 provider ≥80%**：43–52 ⇒ **99–100**，四家全部过线。
  同报告里的 `rss` 与 `__init__` 一并推过 80（P-14 那句「逐模块 ≥80%」读起来有歧义，这里两条口径都满足）。
- 前读数尾行：`57 passed, 21 skipped in 66.49s`；后读数尾行：见 §8（同一命令、最后一次编辑之后现取）。
- 中途读数（先补 detail/search、后补 rss 与两发越界 epoch）：`206 passed / 21 skipped`、TOTAL 95%，
  当时 `justoneapi 98%（115、197-198）`、`wellbyte 98%（134、230-231）`——
  197-198 / 230-231 是「epoch 越界 ⇒ 时间留空」那两条 `except`，本批末段补了用例，只剩两个不可达返回体。

## 2. 交付面

| 件 | 内容 |
|---|---|
| 新载荷 7 份 | `tests/fixtures/provider_payloads/{dajiala_detail,dajiala_search,justoneapi_detail,justoneapi_search,tikhub_detail,tikhub_search,wellbyte_search}.json`，形状说明集中登记在同目录 `README.md` 的新段落（沿用该文件「样本不含注释、形状说明写本文」的既有约定） |
| `tests/test_provider_contract.py` | +55 条函数（参数化展开 +165 条用例）：detail / search / `_request`·`_handle_response` 错误映射 / 时间 / `aclose` 归属 / page>1 不发请求 / 工厂函数；`test_every_sample_is_claimed_by_a_case` 升级为显式认领表 + 递归扫描 + 双向核对（§5） |
| `tests/test_rss_provider.py` | +14 条：抓取路径（`query_work_list` 的 112-128 此前无人判）、`_get_client`/`aclose` 生命周期、格式容错分支 |
| 生产代码 | **一行未改**（本卡禁止）。发现的三处缺陷只做见证用例 + 登记（§7） |

别名优先序是本批最容易放过的一类：载荷刻意让**主键与次键同时存在且值不同**
（`nickname` vs `author`、`create_time` vs `public_time`、`doc_url` vs `url`、`url` vs `content_url`），
否则「别名兜底链」改成任何一条都能过——单值样本判不住顺序。

## 3. 每条新用例判什么 + 能把它打红的变异

「变异」列就是该用例 docstring 里写的那句；带 ● 的是 §4 电池里**实际跑过**的那发。

### Dajiala

| 用例 | 判据一句话 | 会把它打红的变异 |
|---|---|---|
| `test_owned_http_client_is_closed_and_injected_one_is_not`（×4 家） | 自建客户端必须关，注入的必须**不**关 | ● M17 去掉 `_owns_http` 判断 |
| `test_list_page_beyond_the_first_makes_no_upstream_call`（×4 家） | page>1 不发请求（发了就是白烧额度） | 删掉 `if page > 1` 那行 |
| `test_dajiala_detail_maps_every_field_from_payload` | 每个字段来自载荷具体键 + 端点/请求体逐字 | ● M3 `data.get("html")`→`content`；M5 类参数改名；改端点路径 |
| `test_dajiala_detail_content_text_is_stripped_and_capped` | 纯文本无残留标签且不超 200 字 | ● M4 丢掉 `[:200]`；`_strip_html` 改原样返回 |
| `test_dajiala_detail_without_key_never_calls_the_paid_endpoint` | 缺 key ⇒ None 且**没发请求** | 删掉缺 key 早退 |
| `test_dajiala_detail_swallows_domain_errors_for_the_coordinator`（×6） | 5xx/4xx/非JSON/传输层/业务码 全降 None，不抛给协调器 | 收窄 `except AppError`；删掉 try |
| `test_dajiala_detail_returns_none_on_unusable_payload`（×4） | data 为 null/数组/无 html/html 空 ⇒ None，且确实问过上游 | 删 `isinstance(data, dict)`；删 `if not html` |
| `test_dajiala_detail_keeps_the_paid_body_when_the_epoch_is_out_of_range` | 毫秒当秒 ⇒ 时间留空、正文留下 | ● M6 摘掉 `except (ValueError, OSError)` |
| `test_dajiala_search_maps_rows_and_sends_only_the_keyword` | 行字段来自载荷；body 只有 key/verifycode/keyword | ● M5 `keyword`→`q`；把 sort/time_range 塞进 body |
| `test_dajiala_search_degrades_to_empty_list`（×6） | 同样六种失败 ⇒ `[]` | 删 try；删 `isinstance(data, list)` |
| `test_dajiala_search_drops_non_dict_rows_and_bails_on_object_data` | 字符串行只跳那一行；data 是对象 ⇒ 整次空 | 删行级 isinstance |
| `test_dajiala_detail_without_key_and_search_without_key_stay_silent` | 同一 key：清单显式失败、详情/搜索静默降级（分界本身） | 给详情/搜索的缺 key 分支加 raise |
| `test_dajiala_status_code_error_class_split`（×6） | 5xx⇒`DependencyUnavailableError`，4xx⇒`DiscoveryFailedError` | ● M1 两支异常类对调 |
| `test_dajiala_body_and_shape_error_mapping` | 非 JSON / 顶层非对象 ⇒ 发现失败；响应截 160 | 去掉 `[:160]`；把 json 解析失败兜成 `{}` |
| `test_dajiala_transport_error_becomes_dependency_unavailable` | 传输层 ⇒ 依赖不可用且保留 `from exc` | 收窄成只捕 `ConnectError`；去掉 `from exc` |
| `test_dajiala_business_code_routing`（×5） | -1 参数错／余额·money⇒依赖不可用／其余⇒发现失败 | ● M2 删掉余额分支 |
| `test_dajiala_list_payload_defence` | 清单 data 非数组 ⇒ 显式抛；混入字符串 ⇒ 只跳行 | 把 raise 换成 `return [], 0` |

### JustOneAPI

| 用例 | 判据一句话 | 会把它打红的变异 |
|---|---|---|
| `test_justoneapi_detail_maps_first_row_and_field_aliases` | 取 `data.data[0]`；`create_time` 压 `public_time`；GET 参数名 `articleUrl` | ● M7 `items[0]`→`items[-1]`；● M8 参数名改 `url`；端点改 v5 |
| `test_justoneapi_detail_derives_text_when_rich_text_is_absent` | 无 rich text 时由 HTML 去标签兜 200 字 | 删兜底支；或改成永远 re.sub（上一条会红） |
| `test_justoneapi_detail_without_key_never_calls_the_paid_endpoint` | 缺 key ⇒ None 且不发请求 | 删早退 |
| `test_justoneapi_detail_suppresses_every_upstream_failure`（×7） | suppress 支七种失败全降 None | 把 `suppress_errors` 默认改 False |
| `test_justoneapi_detail_returns_none_on_unusable_payload`（×5） | 嵌套三层任一坏 + 两正文键全空 ⇒ None | 删 `isinstance(items, list) or not items` |
| `test_justoneapi_detail_keeps_the_paid_body_when_the_epoch_is_out_of_range` | 毫秒 epoch ⇒ 时间留空正文留下，且不退回次选键 | 摘掉 `except (ValueError, OSError)` |
| `test_justoneapi_search_maps_rows_and_url_alias_priority` | `url` 压 `content_url`、`author` 压 `nick_name`；GET token+keyword | 别名顺序对调；端点改 v2 |
| `test_justoneapi_search_degrades_to_empty_list`（×7） | 同上七发 ⇒ `[]` | 删 try |
| `test_justoneapi_search_skips_non_dict_rows_and_object_data` | 字符串行只跳；data 对象⇒空；缺 key⇒不发请求 | 删行级 isinstance |
| `test_justoneapi_discovery_error_mapping_is_the_raising_branch`（×10） | 发现路径（suppress=False 另一整支）逐类**抛** | ● M9 删限频支；5xx 异常类换成发现失败 |
| `test_justoneapi_discovery_nested_shape_defence` | data/MsgList/Msg 三层坏都不抛；空 URL 行不建；时间回落 `BaseInfo.DateTime` | 删 `or base_info.get("DateTime")` |

### TikHub

| 用例 | 判据一句话 | 会把它打红的变异 |
|---|---|---|
| `test_tikhub_detail_maps_fields_and_request_shape` | v2 h5 端点 + `url` 参数 + Bearer 头 + 三条兜底链 | 端点写成已下线的 web/*；鉴权挪进 query |
| `test_tikhub_detail_falls_back_to_html_and_text_only_payloads` | `content or html`；只有纯文本也算有效 | ● M11 丢掉 html 别名；条件写成 `and` |
| `test_tikhub_detail_without_key_never_calls_the_paid_endpoint` | 缺 key ⇒ None 且不发请求 | 删早退 |
| `test_tikhub_degrades_to_none_on_402_and_404`（×4，detail+search 双判） | 402（余额 0 的日常态）与 404（旧端点）⇒ 空 | ● M10 详情不再 `suppress_402` |
| `test_tikhub_detail_and_search_raise_instead_of_degrading_defect_witness` | ⚠️ 缺陷见证：4xx/5xx **抛穿**，与 `base.py` 协议矛盾 | 给 detail/search 补 `except AppError`（修复即红，逼记录更新） |
| `test_tikhub_search_maps_rows_with_doc_url_priority` | `doc_url` 压 `url`；作者恒空串是现状；body 两键 | 别名对调；按别家"顺手补齐" author |
| `test_tikhub_search_payload_shape_defence`（×2） | data 非数组⇒空；字符串行只跳 | 删守卫 |
| `test_tikhub_search_without_key_returns_empty_without_calling` | 缺 key ⇒ `[]` 且不发请求 | 删早退 |
| `test_tikhub_discovery_never_silently_returns_empty_on_failure`（×6） | 发现路径 402 ⇒ 显式抛且文案含「充值」 | 给发现调用点补 `suppress_402=True` |
| `test_tikhub_404_on_discovery_degrades_to_empty_page` | 404 ⇒ 空页不抛（端点漂移不等于我方请求错） | 404 并入 4xx 抛错 |
| `test_tikhub_discovery_row_mapping_and_alias_branches` | `data.articles` 别名 + 顶层 content_url/title/create_time 兜底 + 空 URL 行不建 | 删 `or data.get("articles")`；删顶层兜底 |

### Wellbyte

| 用例 | 判据一句话 | 会把它打红的变异 |
|---|---|---|
| `test_wellbyte_detail_is_disabled_and_must_not_call_upstream` | 禁用 = **零请求**（每次 30cr） | 把详情接回真实调用 |
| `test_wellbyte_search_maps_rows_and_request_shape` | `doc_url` 压 `url`；作者取 `source.title`；body 三键 | 作者改读 `item["author"]`；body 少键 |
| `test_wellbyte_search_publish_time_accepts_epoch_only` | 数字 epoch 解析；「4分钟前」留空 | 加 `now()-timedelta` 兜底（编时间） |
| `test_wellbyte_search_keeps_rows_when_an_epoch_is_out_of_range` | 毫秒 epoch ⇒ 行留下、时间留空 | 摘掉 `except (ValueError, OSError)`；坏时间改丢行 |
| `test_wellbyte_search_translates_sort_and_time_range`（×6） | 口语口径→上游枚举，未知值兜默认 | ● M13 `sortType` 兜底改空串；删 `_TIME_MAP["all"]` |
| `test_wellbyte_search_degrades_to_empty_list`（×8） | 403/422/5xx/4xx/非JSON/非对象/业务码/传输层 ⇒ `[]` | 漏传 `suppress_errors=True` |
| `test_wellbyte_search_payload_shape_defence`（×3） | 三层坏形状各自收口 | 删行级守卫 |
| `test_wellbyte_search_crashes_on_null_source_defect_witness` | ⚠️ 缺陷见证：`source: null` ⇒ 整次 AttributeError | ● M14 改成 `item.get("source") or {}`（修复即红） |
| `test_wellbyte_search_without_key_returns_empty_without_calling` | 缺 key ⇒ `[]` 且不发请求 | 删早退 |
| `test_wellbyte_resolve_ghid_takes_username_from_account_info` | `data.AccountInfo.UserName` + 端点/body/Bearer | 层级写成 `data.data.AccountInfo` |
| `test_wellbyte_resolve_ghid_returns_none_for_every_unusable_answer`（×8） | 七种坏答案 + 缺 key 全 ⇒ None（不发请求） | 删 `startswith("gh_")` 守卫 |
| `test_wellbyte_discovery_error_mapping_is_the_raising_branch`（×12） | 403⇒依赖不可用（CF 指纹）、422⇒发现失败（不扣费）、限频⇒上游限频 | ● M12 403 换异常类 |
| `test_wellbyte_discovery_nested_shape_defence` | 三层坏形状 + 空 URL 行不建 + DateTime 回落 | 层级写成 `data.data.MsgList`（TC-A4-04 的原错） |

### 跨家（契约绊线 + 工厂）

| 用例 | 判据一句话 | 会把它打红的变异 |
|---|---|---|
| `test_provider_timestamps_are_naive_local_while_the_frozen_contract_demands_aware`（×3） | ⚠️ 缺陷见证三段：naive 现状 / 喂进 `WorkListRow` 被 `timezone_aware` 拒 / 与消费端同一瞬间不同形状 | ● M15、M16 把 `tz=None` 改 `tz=UTC` |
| `test_article_source_factory_fails_loudly_on_unknown_and_unconfigured_names` | 未知平台名与没配 key 都抛 `ConfigurationError` | 删 `cls is None` 守卫（变 KeyError） |
| `test_article_source_factory_builds_only_the_configured_channels` | 只造配了 key 的两家；注册表与 S3.2 名单不分叉 | `key_map` 字段名写错（KeyError） |
| `test_every_sample_is_claimed_by_a_case`（改造） | 四向核对，见 §5 | §5 的两发实测 |

### RSS（`test_rss_provider.py`）

| 用例 | 判据一句话 | 会把它打红的变异 |
|---|---|---|
| `TestFetchPath::test_query_work_list_fetches_alias_resolved_feed_and_parses` | 抓取 + 解析 + 行能被 `_map_row` 接住 + 请求 URL 就是 identifier | 抓完不做 `_map_row` 可用的键归一 |
| `TestFetchPath::test_second_page_never_fetches` | page>1 零请求 | 删 page 判断 |
| `TestFetchPath::test_http_status_error_degrades_to_empty_page` | 500 ⇒ 空页不抛 | 删 try |
| `TestFetchPath::test_transport_error_degrades_to_empty_page` | 拒连 ⇒ 空页不抛 | 把 `except httpx.HTTPError` 换成 `except Exception: raise` |
| `TestFetchPath::test_unparsable_body_degrades_to_empty_page` | 200 但不是 XML ⇒ 空页 | `_parse_feed` 改成抛 ParseError |
| `TestFetchPath::test_item_cap_bounds_one_feed` | 单 feed 截到 `_MAX_ITEMS_PER_FEED`，total 报截断后的数 | ● M18 丢掉截断 |
| `TestFetchPath::test_get_client_is_lazy_reused_and_fully_closed` | 懒建、复用、关闭后清引用 | `_client` 不复用；`aclose` 不清 None |
| `TestFormatFallbacks::`（7 条） | 无 channel／非命名空间 feed／陌生 root／`<link href>` 变体／Atom 无 id 回落 link＋updated／Atom 无 id 无 link 丢行 | 逐个删对应容错分支（丢行或抛异常） |

## 4. 实际跑过的反证电池（不是"想想会红"）

方法：**变异在内存里做**——读生产源码文本 → 替换 → `compile`+`exec` 成 ModuleType →
先把父包 `import` 就位、再把 `sys.modules["app.providers.article_sources.<家>"]` 与父包属性一起换成变异体 →
同进程 `pytest.main(指定 node id)`。工作树里的生产文件从未被写入（共享工作区，禁令第 1 条）。
脚本：`docs/06_validation/evidence/EVD-V2-02/mutate_s341.py`（入库，别人能重跑；仓库根
`cd apps/api && .venv/Scripts/python.exe -X utf8 ../../docs/06_validation/evidence/EVD-V2-02/mutate_s341.py`）。

- 基线（16 条被点名 node id、未变异）：**rc=0**——基线不绿就把整批判 INCONCLUSIVE，这条纪律沿用
  `EVD-V2-02/mutate_replay_r9.py` 的 N-00。
- 18 发变异读数：**RED 命中 18 / 未抓到 0 / 可疑 0**（全部打在点名的那条用例上）。
  本批最后一次文字编辑（两条 docstring 的锚位更正）之后**整批重跑过一次**，读数不变
  ——「变异会红」这句话因此晚于一切改动，不是改动中途的旧数。
- 判据不是 `rc≠0`，而是「红在我点名的那条用例上」——`-rf` 抓 FAILED 行逐条比对 node id。
  实际打印出的红了名字与点名一致（例如 M7 只红 `test_justoneapi_detail_maps_first_row_and_field_aliases`，
  M1 红 `test_dajiala_status_code_error_class_split` 的 500/502/503 三发）。
- 两发特别有意义：**M14/M15/M16** 打的是"缺陷见证"那三条——把缺陷修掉，见证用例立刻红，
  所以这三条不是给现状上锁，而是**给改动上绊线**（修的人必须回来处理这段记录）。

## 5. 认领守卫自己的咬合力（实测）

改造点（`test_every_sample_is_claimed_by_a_case`）：
1. 名单从「`_BUILDERS` 的补集 + `rss_only` 白名单」换成显式登记表 `_SAMPLE_CLAIMS`，
   **每个** payload 都写明「哪个用例在吃它」——`rss2`/`atom` 的原有注释写着
   「由 `tests/test_rss_provider.py` 判」，现读该文件用的是内联字符串、真正逐字吃这两份 XML 的是
   `EVD-V2-00/prove_provider_shapes.py`，登记按实改写（不是新增豁免关键字）。
2. 扫描 `glob` → `rglob`：把样本藏进子目录过去能绕过这道门，现在不能。
3. 新增两个方向：认领表里不许有已消失的样本（改名即红）、`_BUILDERS` 里每家必须有认领行。

实测（本批跑过，不是推演）：
- 往顶层丢 `_counterproof_unclaimed.json` ⇒ 红，点名 `_counterproof_unclaimed`；
- 再往 `_subdir/nested_unclaimed.json` 丢一份 ⇒ 同一发把两个都点名（证明递归扫描生效）；
- 把 `dajiala_detail.json` 改名 ⇒ 红（`dajiala_detail_renamed` 未认领）；
- 删除/还原之后 ⇒ 1 passed。测试后目录清点无残留（`git status` 只见 7 份新载荷）。

## 6. 仍未覆盖的行，以及为什么直说

- `justoneapi.py:115`、`wellbyte.py:134`：都是 `if payload is None: return [], None` 的返回体。
  两家的 `_handle_response` 里**每一个** `return None` 都在 `if suppress_errors:` 之内，而唯一的调用点
  `query_work_list` 不传该参数（默认 False）⇒ 该分支按构造不可达，补任何载荷都到不了。
  这条不是嘴上说的：`docs/06_validation/evidence/EVD-V2-02/prove_unreachable_branches.py` 用 AST 同时核对
  「`return None` 全在 suppress 支里」+「调用点没传 True」，rc=0（`@win` 实测）。
  要覆盖它只能改生产代码（删掉这个防御分支或让调用点传 True），本卡禁止，故留白并登记。
- 其余四个模块（dajiala/tikhub/rss/base/`__init__`）为 100%，无留白。
- **实现缺口被钉成现状、而不是被补齐**：TikHub 详情路径完全不解析时间、
  Dajiala/JustOneAPI 的 `search_articles` 不填 `publish_time`、TikHub 搜索不填 `author`、
  Dajiala 搜索忽略 `sort`/`time_range`。用例断言的就是「为空」，并写明为什么不算实现正确——
  这几条是 P-14 之外的实现欠账（多数源于「端点未实测」），补它们要活体样本，归 STEP-08 S8.5.1。

## 7. 本批查出的生产缺陷（一律**不改**，只登记 + 见证）

| # | 缺陷 | 锚 | 见证用例 | 后果 |
|---|---|---|---|---|
| B-1 | 详情/搜索的 `publish_time` 是**无时区的本机墙上时间**（`fromtimestamp(ts, tz=None)`），而清单消费路径 `_parse_time` 对同一数字解出的是 aware UTC；`app/contracts/collection.py` 的 `WorkListRow.publish_time` 是 `AwareDatetime`，稿面字段说明自己写着「provider 内即转为带时区时间」 | `dajiala.py:162`、`justoneapi.py:196`、`wellbyte.py:229`（对照 `app/services/manifest.py::_from_epoch`、`app/contracts/collection.py:112` 与 §362-368 的 `timezone-required:publish_time` 登记） | `test_provider_timestamps_are_naive_local_while_the_frozen_contract_demands_aware`（×3；M15/M16 已证会红） | 今天不炸：`ArticleDetailFallbackCoordinator` 与 `search_articles` 都还没有生产调用点。**STEP-10 详情接线一落，这条就当场红**（AwareDatetime 拒 naive），且换主机时区会让墙上钟差 8 小时——同一键空间的两套时间口径，STEP-02 同族 |
| B-2 | TikHub 的 `fetch_article_detail` / `search_articles` 在 4xx/5xx 时**抛** `AppError`，违反 `base.py` 协议「返回 None …（不抛异常，由 coordinator 降级）」，也与它自己 docstring 的「失败时降级返回 None（suppress_errors），不抛异常」矛盾（`_handle_response` 只对 402/404 降级） | `tikhub.py:170-254`（调用点无 `except AppError`）对照 `tikhub.py:168` 与 `app/providers/article_sources/base.py:91-97`；对照 `dajiala.py:145` 与 `justoneapi.py:171` 两条**确实**降级 | `test_tikhub_detail_and_search_raise_instead_of_degrading_defect_witness` | 现由 `article_detail_fallback.py:99` 那个宽 `except Exception` 吞成「兜底未命中」而不可见；上层若按协议只判 None 就会被单次上游抖动打断整条链 |
| B-3 | `item.get("source", {})` 兜不住 JSON 的 `null`（默认值只在**键缺失**时生效）⇒ `source: null` 让整次搜索抛 `AttributeError`，**已映射好的行一起丢**，155cr 白烧。同一函数体的另两处（`data.get("MsgList") or {}`、`msg_list.get("Msg") or []`）用的是能兜 null 的写法 | `wellbyte.py:223`（对照 `wellbyte.py:142`、`:145`） | `test_wellbyte_search_crashes_on_null_source_defect_witness`（M14 已证修掉就红） | 上游返回 null 属可预期形状；一行坏 = 整页丢，正是 P-1 那族"静默换入口再来一次" |
| O-1 | 观察项（**不判缺陷**）：Wellbyte 的限频识别只认 `rate`/`限频` 两个子串，HTTP 标准文案 `Too Many Requests` 落不进那一支、会被当普通发现失败；上游真实文案未活体核实，故只钉现状不下判断 | `wellbyte.py:331-337` | `test_wellbyte_discovery_error_mapping_is_the_raising_branch[注意：标准429文案落不进限频支路]` | 若 STEP-08 活体拿到限频文案，这条要重新定性 |
| O-2 | 观察项：`RSSFeedProvider.__init__` 没有 `http` 注入参数（其余四家都有）⇒ 抓取路径只能靠私有属性 `_client` 注入才可测。这是**可测性**缺口而非行为缺陷，改签名不在本卡授权 | `rss.py:58-66` | `test_rss_provider.py::_fed_provider` 的注释里写明 | 后续若加注入参数，本批的私有属性注入点应随之简化 |

## 8. 静态门与全量回归（`@win`，最后一次编辑之后）

- `cd apps/api && .venv/Scripts/python.exe -X utf8 -m ruff check app tests` → `All checks passed!`
- `.venv/Scripts/python.exe -X utf8 -m mypy app` → `Success: no issues found in 112 source files`（mypy 不检查 tests）
- 判据命令（§1）尾行：**`222 passed, 21 skipped in 70.28s (0:01:10)`**（`@win`，**最后一次编辑之后**复跑；
  覆盖率表与前两次读数逐字一致：`dajiala 117/0`、`justoneapi 157/1`、`tikhub 125/0`、
  `wellbyte 165/1`、`rss 145/0`、`base 34/0`、`__init__ 31/0`、TOTAL 99%）
- 全量 `cd apps/api && .venv/Scripts/python.exe -X utf8 -m pytest tests/ -q` 尾行：**本机拿不到**。
  原因不是本批：单次全量在本机要 25 分钟以上（`@win` 实测 ~1.3s/条），而中途必然撞在
  `TestClient(create_app())` + health/ready 探针那一族用例上**永久卡死**——
  本批用 `--timeout=200` 单独复现过一条：`tests/test_envelope.py::test_health_envelope_and_request_id_header`
  跑 200 秒不出结果，栈与 U-23 记录的形状逐帧相同（`starlette/testclient.py:351 handle_request`
  → `anyio/from_thread.py:340 portal.call(...).result()` → `threading.wait`）。
  **处置**：改成**逐文件分进程**跑全量（每个 `tests/test_*.py` 一个 pytest 进程，`--timeout=25`），
  一条卡死不带走别人，读数落到 `docs/06_validation/evidence/EVD-V2-02/s341_per_file_sweep.txt`（87 个测试模块 = `ls tests/*.py` 去掉
  非用例文件 `wechat_urls.py`）：

  | 面 | 读数 |
  |---|---|
  | 出结果的 81 个文件 | **929 passed / 426 skipped / 0 failed** |
  | 本机结构性卡死的 6 个文件 | `test_envelope`(17) `test_health`(6) `test_health_ready`(6) `test_observability`(16) `test_security_middleware`(65) `test_we_notifications`(11) = **121 条未判定** |

  这 6 个文件**不是本批改的**：`git diff --stat` 对它们空输出（与 HEAD 逐字节相同），
  本批只动了 `tests/test_provider_contract.py`、`tests/test_rss_provider.py`、
  `tests/fixtures/provider_payloads/**` 与本证据件。合计 929+426+121 ≈ 1476，
  与「CI 在 HEAD 收 1309 条 + 本批新增 165 条 = 1474」对得上（差 2 属四舍五入级别的口径差，不遮）。
  顺手交给 P-5/U-23 的一条线索：从前那句「先 `-v` 拿用例名」现在有了具体名字——
  上面那条 node id 就是本机最早、最稳定的一发。
- 本机**无 PostgreSQL、无 docker**，连库用例一律 skip ⇒ 以上读数只主张「非连库面全绿 + 用例条数」，
  **不据以主张任何库行为**（U-20 的口径）。判定面在 `@ci`。
- skip 数：判据命令前后都是 **21 skipped**（全部来自 `test_manifest_sync.py` 的无 PG skip），
  本批**没有新增 skip，也没有新增 xfail/skip 类装饰** ⇒ CI 的 `SKIP_BASELINE=6` 门禁不受影响
  （本机 21 与 CI 6 的差是平台可达性差异，非本批引入）。
  刻意不用 `xfail(strict=True)` 表达 B-1/B-2/B-3：junit 会把 xfailed 记成 `<skipped>`，
  等于把三条缺陷推给 CI 的 skip 门禁去红——那会红在共享主干上而不是红在缺陷上，
  所以改成「钉现状 + 修复即红」的绊线写法。

## 9. 前提条件与局限

1. 载荷是**合成占位值**：本批判的是形状与链路，不判上游真值（活体核实仍归 STEP-08 S8.5.1，卡面 R-1）。
   其中 Dajiala 详情/JustOneAPI 详情/Wellbyte 搜索三条有活体用例号背书（TC-A1-07 / TC-A3-07 / TC-A4-02），
   其余四份是契约级推断——这份区别逐条写在 `provider_payloads/README.md` 的新段落里。
2. 时区断言一律走 `.timestamp()` 而不是墙上钟字面量，因此主机时区变了也不会假红；
   B-1 那条的三段判据在任何主机时区下同真同假。
3. 变异电池点名的是「函数级 node id」，参数化里除 M1/M2/M9/M10/M12/M13/M15/M16 之外
   都只要求「指定函数红」，不逐参归因——逐参归因需要 CJK 参数 id 的 pytest 转义形式，实测会把
   node id 匹配搞坏（本批第一版就是这么栽过一次再改的）。
4. `@win` 单平台读数。epoch 越界那两条（B 族时间解析）在 Windows 抛 `OSError`、Linux 一般抛 `ValueError`，
   两者都在生产代码捕获的 `(ValueError, OSError)` 元组里，所以用例跨平台同判；
   但「Linux 侧具体抛哪一个」本批未在真机上复现（CI ubuntu 回读才能定）。
