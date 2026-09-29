# API 测试用例与正文获取流程记录（2026-09-29）

> **归档来源**：AideanBot `.docs/采集渠道/API测试用例与正文获取流程_20260929.md`（2026-09-29 活体实测原始日志，TC 编号逐条可对）。
> **归档目的**：T37 约定——测试证据从 untracked 临时区归档到 docs/06_validation/evidence/，供后续 ADR 和接入实现引用。
> **状态**：4 个平台已活体实测，结果直接驱动 `providers/article_sources/` 实现。

## 修正后的平台能力总表（格级证据级别）

> ⚠️ 每个 ✅/⚠️/❌ 格自带证据级别（活体实测/契约级/文档级/未测），不用行级标签覆盖格级差异。
> 这是 `registry.py` ChannelSpec 的 implemented/available/contract_verified_at/verified_scope 四正交字段纪律在文档层的延伸。

| 平台 | 发现（列表） | 详情兜底 | 搜索 | 实时性 | 计价 | 证据级别 |
|---|---|---|---|---|---|---|
| **Dajiala** | ✅ post_condition（**ghid✅实测 / nickname✅实测¥0.16 / url 文档级**）；post_history(url)✅实测 | ✅ article_html ¥0.04 实测稳定；❌ article_detail 缺陷（计费但 data=null），禁用 | ⚠️ kw_search 端点存在（chunk 反解），**未实测** | ✅ 实时（13:20 发布→13:32 可见） | CNY/次，实测 0.04~0.16 | 列表/详情活体，搜索文档级 |
| **JustOneAPI** | ✅ history/v2（ghid 实测；url 形态文档级） | ✅ detail/v1（GET+articleUrl，实测含正文）；v5 仅指标无正文 | ⚠️ **有**：search-article/v1·v2 ¥0.80、search-account/v1 ¥0.40（价目表在册，未实测）；convert-article-link 实测 405 不可用 | ✅ 实时（sessionid≈调用时刻） | CNY/次，实测 0.15~0.40 | 列表/详情活体，搜索未测 |
| **TikHub** | ✅ fetch_account_articles（v2 契约在案，需 gh_ 形态） | ⚠️ Excel 的 web/* 已下线；**v2 详情端点契约在案未实测** | ✅ wechat_search/v2/fetch_search $0.01（402 证实路由在） | ❓ 未实测 | **USD/请求** $0.001~0.01（非 credits） | 契约级（402 需充值） |
| **Wellbyte** | ✅ account_history_v2（URL 实测，**免费顺带返回 gh_**） | ❌ detail_v2 422 三连拒（0 扣费），禁用待厂商 | ✅ search/article_v1 155cr（**必须 JSON 体**） | ✅ 实时（4.7 分钟前文章可见） | credits（$0.001/cr），实测 78~155 | 列表/搜索活体 |
| **（主路径）项目免费直抓** | — | ✅ **6/6 全文**（含人民日报 13:05 新文 2593 字）；图集类（item_show_type=8）无文字正文属产品事实 | — | ✅ 分钟级 | **¥0** | 活体实测（TC-F 系列） |

### 架构前提（表格不体现但决策必需）

**详情主路径 = 免费直抓（WechatArticleFetcher），实测 6/6 成功率（TC-F-01~08）。**
所有付费详情 API 仅作兜底，默认关闭（`ARTICLE_DETAIL_FALLBACK_ENABLED=false`），
仅在直抓失败且非图集类（item_show_type ≠ 8）时触发。
表格把"详情兜底"列得像主路径会让人高估成本。

### 漏维补齐（决策必需，原表缺）

1. **实时性**：三家实测 5~13 分钟可见（Dajiala 13min / Wellbyte 4.7min / JustOneAPI sessionid≈now）；TikHub 未实测
2. **标识体系**：gh_ / biz / nickname——决定要不要做映射层。TikHub 强依赖 gh_；Wellbyte 传文章 URL 免费换 gh_（TC-A4-04）；Dajiala article_html 同时返回 biz+gh_id
3. **请求形态坑**：Wellbyte 必须 JSON body（form→40001）；JustOneAPI POST/GET 和参数名不统一（history=ghid，detail=articleUrl）；Dajiala 全 POST JSON
4. **失败计费口径**：Wellbyte 失败扣 0（422 三连拒实测）；Dajiala article_detail 失败也扣（¥0.045/次 × 3）——真实 TCO 差异
5. **价格漂移**：Dajiala nickname 实测 ¥0.16 vs 资费页 ¥0.14（疑附加费）

## 测试平台概览

| 平台 | Base URL | 鉴权方式 | 计费单位 | 实测状态 |
|------|----------|----------|----------|----------|
| 极致了 Dajiala | https://www.dajiala.com/fbmain/monitor/v3 | body {key, verifycode} | CNY/次 | ✅ 全活体（搜索除外） |
| TikHub | https://api.tikhub.io | Header Bearer | **USD/请求** | ⚠️ 鉴权通过，余额 0（402） |
| JustOneAPI | https://api.justoneapi.com | URL ?token= | CNY/次 | ✅ 全活体（搜索除外） |
| Wellbyte 数井 | https://api.wellbyte.net | Header Bearer | credits（$0.001/cr） | ✅ 全活体（detail 禁用） |

## TC-A1：Dajiala 极致了

### TC-A1-01：get_remain_money（余额查询）
- **结果**：✅ key 有效，初始余额 ¥1.00

### TC-A1-02：post_condition（发现，ghid 形态）
- **端点**：POST /monitor/v3/post_condition
- **Body**：`{key, verifycode: "", ghid: "gh_b9465228558d"}`
- **计费**：¥0.14/次（cost_money=0.14, remain=0.86）
- **结果**：✅ 返回最新 4 篇文章（url/title/digest/post_time=1790659200 即 13:20:00）
- **实时性**：文章 13:20 发布，13:32 调用即返回，滞后≈12.8 分钟
- **注意**：不支持翻页，仅返回最新批次

### TC-A1-04：post_history（历史清单）
- **端点**：POST /monitor/v3/post_history
- **Body**：`{key, verifycode, url, page}`
- **计费**：¥0.14/次
- **结果**：✅ 19 items/页

### TC-A1-07：article_html（详情兜底）⭐
- **端点**：POST /monitor/v3/article_html
- **Body**：`{key, verifycode, url}`
- **计费**：¥0.04/次
- **结果**：✅ 返回完整 HTML（DOCTYPE）+ title/biz/gh_id/nickname/post_time/author/desc/copyright
- **接入决策**：选为详情兜底首选（成本最低 ¥0.04，biz 与 gh_id 同时返回→免费侧产标识映射原料）

### TC-A1-03/05/08：article_detail（详情 v2）❌
- **计费**：¥0.045/次 × 3 次（扣费但 data=null）
- **结果**：❌ 接口缺陷——排除"图集类无正文"后（TC-A1-08 换图文帖仍 data=null），定谳为端点缺陷
- **失败计费口径**：⚠️ 此端点失败也扣费（与 Wellbyte 422 扣 0 不同）

### TC-A1-09：post_condition（发现，nickname 形态）⭐
- **端点**：POST /monitor/v3/post_condition
- **Body**：`{key, verifycode, nickname: "人民日报"}`
- **计费**：¥0.16/次（⚠️ 高于资费页 ¥0.14，疑 nickname 解析附加费）
- **结果**：✅ 返回 10 条当天文章（05:47 新闻早班车 → 13:05:41 村级短剧）
- **实时性**：最新 post_time 距调用 91 分钟
- **意义**：按名订阅路径的实测前提补齐

### kw_search（搜索）⚠️ 未实测
- **端点 URL**：从前端 SPA JS chunk 反解所得（static1.dajiala.com/static/js/*.js）
- **实测状态**：⚠️ 仅证明端点存在，单价/参数/响应形状全部未知（资费页口径约 ¥0.5/次起）
- **接入决策**：实现按统一包裹推断，降级返回空列表；充值后需补 TC-A1-10 活体用例

## TC-A2：TikHub

### TC-A2-01：OpenAPI 契约获取
- **端点**：GET /openapi.json
- **结果**：✅ 1050 paths；wechat_mp 仅剩 v2 13 个端点（fetch_account_articles 等）
- **关键发现**：**Excel 报价表里 9 个 `/api/v1/wechat_mp/web/*` 端点已不在现行 OpenAPI（下线/隐藏）**
- **契约真源**：`api.tikhub.io/openapi.json`，不是 Excel

### TC-A2-02b：fetch_search（搜索）⚠️ 402
- **端点**：POST /api/v1/wechat_search/v2/fetch_search
- **结果**：⚠️ 402 余额不足（key 有效但付费余额为 0，且不接受免费额度）
- **计费**：$0.01/请求（402 证实路由在，不扣费）
- **接入决策**：契约级实现 + 禁用态注册，充值后按 TC-A2-02b 形态补活体用例

### TC-A2-04：web/* 旧端点 ❌ 已下线
- **端点**：POST /api/v1/wechat_mp/web/fetch_mp_article_detail_json（Excel 标注 Free Credit）
- **结果**：❌ 404 Not Found（现行 OpenAPI 已无该路径）
- **范围澄清**：仅 web/* 旧端点下线；**v2 组详情端点仍在现行 OpenAPI**：
  /api/v1/wechat_mp/v2/fetch_article_detail、fetch_article_detail_h5（官方标"推荐"）、
  fetch_article_full 等 13 个

### fetch_account_articles（发现）⚠️ 契约级
- **端点**：POST /api/v1/wechat_mp/v2/fetch_account_articles
- **Body**：`{username(gh_…), offset(base64游标,首页空), item_show_type(0/5/7/8), raw}`
- **实测状态**：⚠️ 契约在案，402 未实测
- **标识依赖**：username 必须为 gh_ 形态，需 biz→gh_ 映射层（T16）

## TC-A3：JustOneAPI

### TC-A3-01：get-account-history-articles/v2（发现）⭐
- **端点**：POST /api/weixin/get-account-history-articles/v2
- **Form**：`token=<key>&ghid=gh_b9465228558d`
- **计费**：¥0.40/次
- **结果**：✅ data.MsgList.Msg[10 条]，每条 AppMsg{Title, Digest, ContentUrl, CreateTime, UpdateTime}
- **附带**：data.AccountInfo{UserName(gh_), NickName, HeadImgUrl, Signature}
- **附带**：data.PagingInfo{Offset, IsEnd}
- **实时性**：sessionid≈调用时刻（推翻文档"疑快照"推断）
- **POST/GET 坑**：history=POST form；detail=GET query——同平台方法不统一

### TC-A3-07：get-article-detail/v1（详情兜底）⭐
- **端点**：GET /api/weixin/get-article-detail/v1?token=<key>&articleUrl=<url>
- **计费**：¥0.15/次
- **结果**：✅ data.data[0].content (HTML 正文) + content_multi_text (富文本) + 60+ 字段（biz/ghid/author/item_show_type=0 等）
- **参数名坑**：detail 接口参数名为 articleUrl（列表接口为 ghid/url——同平台参数名不统一）

### TC-A3-06：get-article-detail/v5（详情 v5）
- **计费**：¥0.15/次
- **结果**：⚠️ 仅元数据 + 阅读指标，无正文 content 字段

### TC-A3-02/03/04：convert-article-link/v1 ❌
- **结果**：❌ 405/参数名不符（实测方法/参数文档与实现不符），禁用

### 搜索接口 ⚠️ 有，未实测
- **价目表在册**（justoneapi-pricing-20260929-110843.xlsx，293 接口）：
  - search-article/v1 ¥0.80
  - search-article/v2 ¥0.80（支持 latest 类目）
  - search-account/v1 ¥0.40
  - search-account/v2 ¥1.50
- **实测状态**：⚠️ 价目表在册但本轮未调用，参数名/响应形状未知
- **接入决策**：实现按统一包裹推断，降级返回空列表

## TC-A4：Wellbyte 数井

### TC-A4-02：search/article_v1（关键词搜索）⭐
- **端点**：POST /v1/wechat_mp/search/article_v1
- **JSON**：`{keyword, sortType: "LATEST", publishTimeType: "ONE_DAY"}`
- **计费**：155cr/次
- **结果**：✅ 15 items，doc_url 全量长链（含 __biz），source.dateTime 分钟级时效（"4分钟前"）
- **请求形态坑**：⚠️ 必须 JSON body（form→40001，文档自相矛盾）

### TC-A4-03：Cloudflare 指纹拦截 ⚠️
- **现象**：Python urllib 被 CF 1010 拦截（HTTP 403）
- **解决**：必须用 httpx（非 urllib），容器环境复验通过
- **教训**：防腐层客户端强制用 httpx

### TC-A4-04：account_history_articles_v2（发现）⭐
- **端点**：POST /v1/wechat_mp/user/account_history_articles_v2
- **JSON**：`{url: "mp.weixin.qq.com文章长链"}`
- **计费**：78cr/次
- **结果**：✅ data.AccountInfo{UserName:"gh_b9465228558d"} + data.MsgList.Msg[...] + ContentUrl
- **免费侧产**：传文章 URL 即返回 gh_——biz↔gh_ 映射零成本路径
- **层级教训**：首轮误判 data.data.MsgList，实为 data.MsgList

### TC-A4-05/06/07：article_detail_v2（详情）❌
- **端点**：GET /v1/wechat_mp/detail/article_detail_v2?url=
- **结果**：❌ 三连 422 质量门槛拒绝（不同 URL 均被拒，含 Wellbyte 自家返回的 URL）
- **计费**：失败扣 0（承诺实测为真）
- **接入决策**：禁用，不注册详情能力

## TC-F：免费直抓实验组（¥0 成本，主路径验证）

| 用例 | 结果 | 判定 |
|------|------|------|
| TC-F-02 | 3 条短链直抓 + 解析：科技美学 2714 字/35 行、短剧内行人/程序员拾梦同构成功 | ✅ 直抓+解析链路完好 |
| TC-F-04 | 同文章控制变量翻转：scene/chksm 不改变模板归属 | ✅ 模板选择与请求参数无关 |
| TC-F-05 | 壳页 vs SSR 页 item_show_type：壳页=8（图集），SSR 页无此变量 | ✅ 8=图集无文字正文，0/9=图文SSR全文 |
| TC-F-06 | Wellbyte 搜索返回 3 篇分钟级新文直抓：3625/1723/12193 字 | ✅ 免费直抓对分钟级新文章成立 |
| TC-F-08 | 人民日报最新一篇直抓（13:05:41 发布，92 分钟后）：2593 字，biz/author/ct 全解析 | ✅ 当天性双路对账成立 |

**结论**：详情主路径 = 免费直抓，实测 6/6 成功率。所有付费详情 API 仅作兜底。

## 接入实现映射

| 测试用例 | 实现代码 | 文件 | 证据级别 |
|----------|----------|------|----------|
| TC-A1-02 post_condition(ghid) | `DajialaClient.query_work_list` | providers/article_sources/dajiala.py | 活体实测 |
| TC-A1-09 post_condition(nickname) | `DajialaClient.query_work_list`（identifier=nickname） | providers/article_sources/dajiala.py | 活体实测 |
| TC-A1-07 article_html | `DajialaClient.fetch_article_detail` | providers/article_sources/dajiala.py | 活体实测 |
| kw_search | `DajialaClient.search_articles` | providers/article_sources/dajiala.py | ⚠️ 文档级（未实测） |
| TC-A2-02b fetch_search | `TikhubClient.search_articles` | providers/article_sources/tikhub.py | 契约级（402 未实测） |
| TC-A2-01 fetch_account_articles | `TikhubClient.query_work_list` | providers/article_sources/tikhub.py | 契约级（402 未实测） |
| v2 fetch_article_detail_h5 | `TikhubClient.fetch_article_detail` | providers/article_sources/tikhub.py | 契约级（OpenAPI 在案，未实测） |
| TC-A3-01 history/v2 | `JustOneApiClient.query_work_list` | providers/article_sources/justoneapi.py | 活体实测 |
| TC-A3-07 detail/v1 | `JustOneApiClient.fetch_article_detail` | providers/article_sources/justoneapi.py | 活体实测 |
| search-article/v1 | `JustOneApiClient.search_articles` | providers/article_sources/justoneapi.py | ⚠️ 契约级（价目表在册，未实测） |
| TC-A4-02 article_v1 | `WellbyteClient.search_articles` | providers/article_sources/wellbyte.py | 活体实测 |
| TC-A4-04 account_history_v2 | `WellbyteClient.query_work_list` | providers/article_sources/wellbyte.py | 活体实测 |
| TC-A4-04 免费侧产 gh_ | `WellbyteClient.resolve_ghid_from_url` | providers/article_sources/wellbyte.py | 活体实测 |
| TC-A4-05/06/07 detail_v2 禁用 | `WellbyteClient.fetch_article_detail`（返回 None） | providers/article_sources/wellbyte.py | 活体实测（422 禁用） |
| §8.1 item_show_type 检测 | `parse_item_show_type` / `is_gallery_type` | providers/source_resolver.py | 活体实测（TC-F-05） |

## 经验教训（可直接转发）

> 1. **每个 ✅ 必须绑定证据级别**（活体实测/契约级/文档级/未测），不许用行级标签覆盖格级差异。项目 `registry.py` 的 ChannelSpec 已把 implemented/available/contract_verified_at/verified_scope 设计成正交字段，表格遵守同一纪律。
> 2. **"无此能力"下结论前先查端点目录和价目表。** JustOneAPI 的搜索接口在自家导出的价目表里明明白白（¥0.40~0.80），"我没测过"≠"它没有"。
> 3. **"端点已下线"必须限定批次和基准。** TikHub 下线的是 Excel 里 web/* 旧端点，v2 组详情端点仍在现行 OpenAPI；契约真源是 `api.tikhub.io/openapi.json`，不是 Excel。
> 4. **没调用过的接口不许打✅**（Dajiala kw_search 是 chunk 反解所得，仅证明存在）。
> 5. **计价单位别串门**：TikHub=USD/请求，Wellbyte=credits，另两家=CNY；表格混写会直接算错预算。
> 6. **补齐决策维度**：实时性、标识体系（gh_/biz/nickname）、请求形态坑（Wellbyte 必须 JSON、JustOneAPI 方法与参数名不统一）、失败计费口径（Wellbyte 失败扣 0 vs 极致了 article_detail 失败也扣）、以及"详情主路径=免费直抓，付费全是兜底"这个架构前提。
> 7. **价格写实测值并标注漂移**（如 nickname 实测 ¥0.16 vs 资费页 ¥0.14）。
> 8. 原始证据：AideanBot `.docs/采集渠道/API测试用例与正文获取流程_20260929.md`（TC 编号逐条对得上，引用时带 TC 号）。

## API Key 脱敏说明

实测使用的 API key 不归档于此文档。生产环境通过环境变量注入：
- `DAJIALA_API_KEY` / `JUSTONEAPI_API_KEY` / `TIKHUB_API_KEY` / `WELLBYTE_API_KEY`
- docker-compose.yml `&backend_env` 锚点已配置对应环境变量映射
- Settings 类（core/config.py）已添加对应字段，默认空串（未配置 = 跳过注册）
