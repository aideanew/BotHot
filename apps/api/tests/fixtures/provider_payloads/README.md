# Provider 响应契约夹具（fixtures/provider_payloads）

> 本目录的 `.json` 样本刻意**不含**任何注释性键——上游形状就是它字面的样子，
> 形状说明（来源 `file:line`、活体用例编号、刻意不含项、合成声明）集中写在本文，
> 以免注记混进被 `query_work_list` 消费的响应体里、削弱「样本 == 上游形状」这一断言。
> `.xml` 样本不受此限（XML 有注释语法，注记写在文件内且不参与解析）。
>
> 采集口径与机器证明：docs/06_validation/evidence/EVD-V2-00/README.md §5.2
> （`prove_provider_shapes.py` 用 AST 从各 Provider 源码**导出**读取路径再核对样本）。


## redfox.json

形状来源 RedFox｜请求体与响应包裹：app/providers/redfox/client.py:3-5（R8 活体实测 2026-09-28：POST /story/api/gzh/data/queryWorkList，body {bizInfo,offset,sortType}，响应 {code:2000,data:{list,total}}）；顶层键 code/data/msg 见 .docs/03_solution/solutions/r8-redfox对接活体实测与剩余任务方案大纲-20260928.md:49「total 位于 data.total（非顶层）；顶层只有 code/data/msg」；_CODE_OK=2000 见 client.py:56，PAGE_SIZE=20 见 :51；行字段口径 app/services/manifest.py:13-17（workUuid 32 位小写 hex、workUrl 且**无 url 键**、title、summary、publishTime 为无时区北京时间串、readCount/likeCount）；list[0] 逐字段取自活体行字面量 apps/api/tests/test_manifest_sync.py:218-225；列表不含正文（content 恒 null）见 .docs/06_validation/reports/M0能力实证总报告.md:35；registry.py:142-143 verified_scope=契约层（请求体/响应字段/分页/错误码），端到端未验证。合成声明：list[1] 为同口径合成行（活体仅存档 list[0] 的形状），两行 ⇒ len(rows)=2 < PAGE_SIZE=20 ⇒ 供 manifest.py:217-218 的「末页」判定用例。

## dajiala.json

形状来源 Dajiala｜envelope：app/providers/article_sources/dajiala.py:249-251（读顶层 code 与 msg，_CODE_OK=0 见 :46，非 0 走 :263-270 _business_error）；**data 直接是数组**：:102-104 `data=payload.get("data")` 且 `isinstance(data, list)` 否则报「缺 data 数组」；行键：:112-119 只读 url/title/digest/post_time，:116 注释「post_time 是 Unix 时间戳（如 1790659200）」并以 str() 写入 row.publish_time；端点与请求体：:94-101 POST /fbmain/monitor/v3/post_condition，body {key,verifycode:"",ghid}；活体用例：docs/06_validation/evidence/channeltest-20260929/README.md:49-55（TC-A1-02，post_condition 按 ghid 返回 url/title/digest/post_time=1790659200）+ registry.py:174-176「发现(post_condition ghid/nickname)=活体实测 TC-A1-02/09」。刻意不含：README:53 记录的 cost_money/remain（代码从不读，且其在响应中的层级未确认 ⇒ 写进来就是猜测）；行内**无任何 id 键**（D-03 实证，manifest.py:51 _ID_KEYS 全部落空 ⇒ _map_row 返回 None）。合成声明：两条行的 title/digest/url 为合成占位，键名/层级/时间单位才是本样本的断言对象。

## justoneapi.json

形状来源 JustOneAPI｜envelope：app/providers/article_sources/justoneapi.py:6「响应统一包裹 {code, message, data, recordTime, requestId}」，_CODE_OK=0 见 :47，失败读 message 见 :300-305；行路径：:117-127 data(dict)→MsgList(dict)→Msg(list)，注释 :121「嵌套结构：data.MsgList.Msg = 文章列表」；行键：:133-143 读 AppMsg.ContentUrl/Title/Digest/CreateTime 与 BaseInfo.DateTime（:140 注释「CreateTime 是 Unix 时间戳」，:141 两处共用 isinstance(int|float) 守卫 ⇒ DateTime 的单位口径**继承自该守卫而非活体样本**）；账号/分页键：docstring :10-12 活体口径「data.MsgList.Msg[10 条]，每条 AppMsg{Title,Digest,ContentUrl,CreateTime,UpdateTime}／data.AccountInfo{UserName(gh_),NickName,HeadImgUrl,Signature}／data.PagingInfo{Offset,IsEnd}」；端点与请求：:104-109 POST /api/weixin/get-account-history-articles/v2（form 编码 token+ghid），:101-102 page>1 返回空（游标需上页 Offset，无法预构 ⇒ D-06）；活体用例：registry.py:197-199「发现(history/v2 ghid)=活体实测 TC-A3-01」；gh_b9465228558d 取自 docs/06_validation/evidence/channeltest-20260929/README.md:119。刻意不含：AppMsg.MsgId / ItemIndex——它们只出现在 docs/任务规划V0.2.0/steps/STEP-03-渠道行契约归一.md:36 的**假设**里，代码与活体记录均无（D-03：行内无任何 _ID_KEYS 命中）。合成声明：除 gh_ 与时间戳外均为占位值。

## tikhub.json

形状来源 TikHub｜⚠ 全部为契约级推断，非活体：registry.py:223-226「发现(fetch_account_articles v2)=契约级（OpenAPI 在案，TC-A2-02b 402 未实测）」，客户端注释 :192「v2 端点响应形状未实测，按 TikHub 统一结构推断」⇒ 消费本样本的用例必须带 xfail(strict=True)（STEP-03 S3.2.3），端点定谳属 U-04（STEP-04 S4.5.1，读 api.tikhub.io/openapi.json）。envelope：:256-280 _handle_response **从不读业务 code**（只按 HTTP 状态判定：402 余额不足 :260-264、404 记 warn 后返回 None :267-269、>=400 抛错 :270-271）⇒ 本样本刻意不含 code/message，含了就是猜测。行路径：:125-131 注释「data.data = 文章列表（微信原始结构）」，取 `data.get("data") or data.get("articles")`——`data.articles` 回退分支无任何外部佐证，故本样本只给 data.data。行键：:138-148 读 app_msg_ext_info.{content_url,title,digest} 与 comm_msg_info.create_time（:145 注释 Unix 时间戳），空 url 行被丢弃（:149-150）。端点漂移（D-15）：代码 :114 实际 POST /api/v1/wechat_mp/web/fetch_account_articles，而 :10 docstring 与 README.md:110 记的活体端点是 /api/v1/wechat_mp/v2/fetch_account_articles，且 web/* 旧端点 registry.py:227 自述「活体实测已下线 TC-A2-04 404」⇒ 本样本对应**请求形状**而非已确认的存在端点。刻意不含：comm_msg_info.id（仅 STEP-03:36 假设）。合成声明：所有值为占位。

## wellbyte.json

形状来源 Wellbyte｜envelope：app/providers/article_sources/wellbyte.py:6「响应统一 {code, message, data, meta:{endpoint, cache_hit, elapsed_ms, request_id, credits_charged}}」，_CODE_OK=0 见 :52，失败读 message 见 :320-325；meta 五个子键**代码一处都不读**（全文件无 meta 访问）⇒ 保留仅为形状忠实，值属推断；行路径：:136-147 data(dict)→MsgList(dict)→Msg(list)，:140-141 注释是 TC-A4-04 的层级教训「**不是** data.data.MsgList（首轮看错层级）」，与 docs/06_validation/evidence/channeltest-20260929/README.md:169 一致；行键：:153-162 读 AppMsg.ContentUrl/Title/Digest/CreateTime 与 BaseInfo.DateTime（:160-162 与 justoneapi 同法，epoch 秒）；docstring :13「ContentUrl(带 sessionid)」⇒ 本样本的 ContentUrl 刻意携带 sessionid，供 STEP-01 S1.3.1 的追踪参数剥离用例；标识：:270-278 data.AccountInfo.UserName（startswith("gh_") 守卫），docstring :13-14「传文章 URL 即返回 ghid——biz→gh_ 映射零成本路径」，活体 TC-A4-04 见 :248-251 与 README.md:167-168（gh_b9465228558d）；端点与请求：:121-127 POST /v1/wechat_mp/user/account_history_articles_v2，body {url: <文章 URL>}（**入参是文章 URL 而非 ghid** ⇒ D-05 标识错位）；:118-119 page>1 返回空（D-06）；:170-176 详情端点禁用（422 三连拒 TC-A4-05/06/07）⇒ 无详情样本；registry.py:245-250 verified_scope=发现活体实测 78cr。刻意不含：AppMsg.MsgId/ItemIndex（仅 STEP-03:36 假设，代码与活体记录均无）。合成声明：除 gh_ 与时间戳外均为占位值。

---

## S3.4.1（P-14）新增的详情 / 搜索载荷

下面七份是 STEP-03 卡面 S3.4.1 补的**详情兜底与关键词搜索**形状（清单那一族只有
`{provider}.json` 一种形状，P-14 记的正是这个缺口）。认领它们的用例全在
`apps/api/tests/test_provider_contract.py`（`_SAMPLE_CLAIMS` 逐份点名，目录里有未认领文件
或认领表里有已消失的文件，`test_every_sample_is_claimed_by_a_case` 都会红）。
本节的锚一律写**函数名/分支名而不写行号**——上面那批条目的 `:123-145` 已经漂过一轮，
而行号漂了没人核对（`check_docs_consistency` 只校验 backlog.md 的锚）。
值全是合成占位；只有活体用例号（TC-A*）与 `gh_b9465228558d` 这类实测记录里的常量是真引用。

## dajiala_detail.json

形状来源 Dajiala｜证据级别：**活体实测**（TC-A1-07，¥0.04/次，`dajiala.py::fetch_article_detail`
自述「返回 data.html（完整 DOCTYPE）+ 元数据」）。envelope 与清单同包裹 `{code,msg,data}`，
但 **data 是对象不是数组**（清单端点 post_condition 的 data 才是数组）⇒
`fetch_article_detail` 读 `data.get("html")` 并在 `not isinstance(data, dict)` / `not html` 时判 None。
键名按代码逐字：html/title/nickname/author/biz/gh_id/post_time；`author` 与 `nickname` **刻意同时给且不同值**，
因为代码是 `nickname or author`——只给一个就把别名优先序变成了无人看守的默认值。
`post_time` 是 epoch 秒（1790659200，与清单样本同口径）。刻意不含：cost_money/remain（代码从不读）。
消费用例：`test_dajiala_detail_maps_every_field_from_payload`、`test_dajiala_detail_content_text_is_stripped_and_capped`。

## dajiala_search.json

形状来源 Dajiala kw_search｜证据级别：**文档级（端点存在但未实测）**——`dajiala.py::search_articles`
的 docstring 自己写着「单价、参数名、响应形状全部未知，本实现按 Dajiala 统一包裹 {code, data} 推断」。
所以本样本只声明「推断形状」：data 直接是数组，行键 url/title/digest/nickname（与清单同源的那套键名），
**不含** sort/publishTimeType 之类代码根本不读的键。
消费用例：`test_dajiala_search_maps_rows_and_sends_only_the_keyword`（其中一条断言钉的正是
「代码只发 keyword，`sort`/`time_range` 两个形参在 dajiala 上不生效」这一现状）。

## justoneapi_detail.json

形状来源 JustOneAPI｜证据级别：**活体实测**（TC-A3-07，¥0.15/次，get-article-detail/v1）。
层级按代码逐字：`data.data` 是数组、取 **items[0]** ⇒ 样本刻意放**两行**且第二行标题不同，
否则「取首行」这条判据与「取任意一行」不可区分。
键名：content（HTML 正文）/content_multi_text（富文本纯版）/title/author/nick_name/biz/ghid/user_name/
create_time/public_time——`author`+`nick_name`、`ghid`+`user_name` 都是**空值与非空值配对**（代码是 `a or b` 兜底链），
`create_time` 与 `public_time` **给不同值**（代码 create_time 优先）。
刻意不含：v5 端点独有的阅读指标 60+ 字段（v1/v5 形状差异未逐项核实，写了就是猜测）。
消费用例：`test_justoneapi_detail_maps_first_row_and_field_aliases`。

## justoneapi_search.json

形状来源 JustOneAPI search-article/v1｜证据级别：**契约级（价目表在册、参数名与响应形状未活体验证）**，
`justoneapi.py` 的搜索段注释逐字记着这一点。样本因此只按代码的读取面给形状：
顶层 `data` 直接是数组（与详情不同！代码 `isinstance(data, list)`），
行键 url/content_url 与 author/nick_name 各配一对**取值优先级判据**（第一行两者都有、值不同，
第二行只有次选键）——这是「别名兜底链」唯一能被样本判住的写法。
消费用例：`test_justoneapi_search_maps_rows_and_url_alias_priority`。

## tikhub_detail.json

形状来源 TikHub v2 fetch_article_detail_h5｜证据级别：**契约级（OpenAPI 在案、余额 0 从未实测）**。
顶层**刻意不含 code/message**（沿用 tikhub.json 的既定判断：`TikhubClient::_handle_response`
只按 HTTP 状态判、从不读业务码，含了就是猜测）。层级 `data` 是对象，
键 content/html 与 author/nick_name 与 gh_id/user_name 按代码的三条兜底链配对——
`content_text` 只在代码里存在而本样本不给，因为「只有纯文本没有 HTML」那一支由用例内联载荷判
（形状未实测，不值得为它多落一份文件）。
**没有 create_time 这类时间键**：`fetch_article_detail` 根本不解析时间，样本给键就是替实现编需求。
消费用例：`test_tikhub_detail_maps_fields_and_request_shape`。

## tikhub_search.json

形状来源 TikHub fetch_search｜证据级别：**契约级（TC-A2-02b 实测 402，从未拿到过 200 响应体）**。
顶层 `data` 直接是数组，行键 doc_url/url/title/digest——doc_url 压 url 是代码的读取序，
第一行两个都给、第二行只给 url。样本**不给** source/author 之类键：
`search_articles` 只填 url/title/digest，作者字段在 TikHub 上是空的（用例
`test_tikhub_search_maps_rows_with_doc_url_priority` 把「作者恒空串」钉成现状，
免得后来人按别家形状"顺手补齐"）。
消费用例：同上。

## wellbyte_search.json

形状来源 Wellbyte article_v1｜证据级别：**活体实测**（TC-A4-02，155cr/次，返回 15 items）。
层级 `data.data` 是数组（与清单的 `data.MsgList.Msg` **不同层级**——这正是 TC-A4-04 记过的层级教训的另一半）。
行键 doc_url/url/title/digest/source{title, dateTime}：`source.title` 是号名（Wellbyte 的形状里作者不在线上），
`source.dateTime` **两种口径都给出**——第一行 epoch 数字（代码只解这个数字），
第二行「4分钟前」（docstring 自述分钟级时效，代码按非数字留空）。
这一对就是「宁缺勿编」判据的载荷：相对串不许被硬解成绝对时刻。
meta 子键照 §wellbyte.json 的口径保留（代码不读，仅形状忠实）。
消费用例：`test_wellbyte_search_maps_rows_and_request_shape`、
`test_wellbyte_search_publish_time_accepts_epoch_only`。
另：**Wellbyte 没有详情样本**，因为 `fetch_article_detail` 是刻意禁用的（422 三连拒 TC-A4-05/06/07），
它的判据是「一个字都不发」，见 `test_wellbyte_detail_is_disabled_and_must_not_call_upstream`。

