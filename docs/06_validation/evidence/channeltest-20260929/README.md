# API 测试用例与正文获取流程记录（2026-09-29）

> **归档来源**：2026-09-29 活体实测，原始记录在会话上下文中（backend/.tmp_channeltest/ 为临时工作区，未入库）。
> **归档目的**：T37 约定——测试证据从 untracked 临时区归档到 docs/06_validation/evidence/，供后续 ADR 和接入实现引用。
> **状态**：4 个平台已活体实测，结果直接驱动 `providers/article_sources/` 实现。

## 测试平台概览

| 平台 | Base URL | 鉴权方式 | 计费单位 | 实测状态 |
|------|----------|----------|----------|----------|
| 极致了 Dajiala | https://www.dajiala.com/fbmain/monitor/v3 | body {key, verifycode} | ¥/次 | ✅ 全活体 |
| TikHub | https://api.tikhub.io | Header Bearer | credits | ⚠️ 鉴权通过，余额 0 |
| JustOneAPI | https://api.justoneapi.com | URL ?token= | ¥/次 | ✅ 全活体 |
| Wellbyte 数井 | https://api.wellbyte.net | Header Bearer | credits | ✅ 全活体（CF 指纹坑） |

## TC-A1：Dajiala 极致了

### TC-A1-01：post_condition（发现）
- **端点**：POST /monitor/v3/post_condition
- **Body**：`{key, verifycode: "", ghid: "gh_xxx"}`
- **计费**：¥0.14/次
- **结果**：✅ 返回最新 4 篇文章（url/title/digest/post_time Unix 时间戳）
- **注意**：不支持翻页，仅返回最新批次

### TC-A1-02：post_history（历史清单）
- **端点**：POST /monitor/v3/post_history
- **Body**：`{key, verifycode, url, page}`
- **计费**：¥0.14/次
- **结果**：✅ 19 items/页

### TC-A1-07：article_html（详情兜底）⭐
- **端点**：POST /monitor/v3/article_html
- **Body**：`{key, verifycode, url}`
- **计费**：¥0.04/次
- **结果**：✅ 返回完整 HTML（DOCTYPE）+ title/biz/gh_id/nickname/post_time
- **接入决策**：选为详情兜底首选（成本最低 ¥0.04）

### TC-A1-08：article_detail（详情 v2）
- **结果**：❌ data 恒 null（实测缺陷），禁用

## TC-A2：TikHub

### TC-A2-01：鉴权验证
- **端点**：GET /openapi.json
- **结果**：✅ 1050 paths，wechat_mp v2 仅 13 端点
- **鉴权**：Header `Authorization: Bearer <key>` 通过

### TC-A2-02：fetch_account_articles（发现）
- **端点**：POST /api/v1/wechat_mp/web/fetch_account_articles
- **Body**：`{username: gh_xxx, offset: base64游标, item_show_type: 0, raw: true}`
- **结果**：⚠️ 402 余额不足（付费端点，free credit 不接受）
- **接入决策**：契约级实现 + 禁用态注册，充值后按 TC-A2-02b 补活体用例

### TC-A2-03：fetch_search（关键词搜索）
- **端点**：POST /api/v1/wechat_search/v2/fetch_search
- **结果**：⚠️ 402 余额不足

## TC-A3：JustOneAPI

### TC-A3-01：get-account-history-articles/v2（发现）⭐
- **端点**：POST /api/weixin/get-account-history-articles/v2
- **Form**：`token=<key>&ghid=gh_xxx`
- **计费**：¥0.40/次
- **结果**：✅ data.MsgList.Msg[10 条]，每条 AppMsg{Title, Digest, ContentUrl, CreateTime}
- **附带**：data.AccountInfo{UserName(gh_), NickName, HeadImgUrl, Signature}
- **附带**：data.PagingInfo{Offset, IsEnd}

### TC-A3-07：get-article-detail/v1（详情兜底）⭐
- **端点**：GET /api/weixin/get-article-detail/v1?token=<key>&articleUrl=<url>
- **计费**：¥0.15/次
- **结果**：✅ data.data[0].content (HTML 正文) + content_multi_text (富文本) + 60+ 字段

### TC-A3-08：get-article-detail/v5（详情 v5）
- **计费**：¥0.15/次
- **结果**：仅元数据 + 阅读指标，无正文 content 字段

### TC-A3-09：convert-article-link/v1
- **结果**：❌ 不可用（405/参数名不符），禁用

## TC-A4：Wellbyte 数井

### TC-A4-01：接口口径验证
- **结果**：全部接口用 JSON body（form 不收）
- **端点目录**：GET /zh/endpoints?platform=wechat_mp（12 个，credits 明码）

### TC-A4-02：search/article_v1（关键词搜索）⭐
- **端点**：POST /v1/wechat_mp/search/article_v1
- **JSON**：`{keyword, sortType: "LATEST", publishTimeType: ""}`
- **计费**：155cr/次
- **结果**：✅ 15 items，doc_url 全量长链（含 __biz），source.dateTime 分钟级时效

### TC-A4-03：Cloudflare 指纹拦截 ⚠️
- **现象**：Python urllib 被 CF 1010 拦截
- **解决**：必须用 httpx（非 urllib），容器环境复验通过
- **教训**：防腐层客户端强制用 httpx

### TC-A4-04：account_history_articles_v2（发现）⭐
- **端点**：POST /v1/wechat_mp/user/account_history_articles_v2
- **JSON**：`{url: "mp.weixin.qq.com文章长链"}`
- **计费**：78cr/次
- **结果**：✅ data.AccountInfo{UserName(gh_)} + data.MsgList.Msg[...] + ContentUrl
- **免费侧产**：传文章 URL 即返回 ghid——biz↔gh_ 映射零成本路径
- **层级教训**：首轮看错层级（data.data.MsgList vs data.MsgList），修正后 data.MsgList.Msg

### TC-A4-05/06/07：article_detail_v2（详情）❌
- **端点**：GET /v1/wechat_mp/detail/article_detail_v2?url=
- **结果**：三连 422 质量门槛拒绝（不同 URL 均被拒）
- **计费**：失败扣 0（承诺实测为真）
- **接入决策**：禁用，不注册详情能力

## 接入实现映射

| 测试用例 | 实现代码 | 文件 |
|----------|----------|------|
| TC-A1-01 post_condition | `DajialaClient.query_work_list` | providers/article_sources/dajiala.py |
| TC-A1-07 article_html | `DajialaClient.fetch_article_detail` | providers/article_sources/dajiala.py |
| TC-A2-02 fetch_account_articles | `TikhubClient.query_work_list` | providers/article_sources/tikhub.py |
| TC-A3-01 get-account-history-articles/v2 | `JustOneApiClient.query_work_list` | providers/article_sources/justoneapi.py |
| TC-A3-07 get-article-detail/v1 | `JustOneApiClient.fetch_article_detail` | providers/article_sources/justoneapi.py |
| TC-A4-02 search/article_v1 | `WellbyteClient.search_articles` | providers/article_sources/wellbyte.py |
| TC-A4-04 account_history_articles_v2 | `WellbyteClient.query_work_list` | providers/article_sources/wellbyte.py |
| TC-A4-04 免费侧产 gh_ 映射 | `WellbyteClient.resolve_ghid_from_url` | providers/article_sources/wellbyte.py |
| TC-A4-05/06/07 detail_v2 禁用 | `WellbyteClient.fetch_article_detail` (返回 None) | providers/article_sources/wellbyte.py |
| §8.1 item_show_type 检测 | `parse_item_show_type` / `is_gallery_type` | providers/source_resolver.py |

## 测试报告 §8.1 核心建议（已实现）

1. **item_show_type 检测**：直抓成功后检查 item_show_type，= 8（图集类）时不触发付费详情兜底 → ✅ 已实现 `parse_item_show_type` + `is_gallery_type`
2. **详情兜底按成本排序**：Dajiala ¥0.04 → JustOneAPI ¥0.15 →（TikHub/Wellbyte 不可用跳过）→ ✅ 已实现 `ArticleDetailFallbackCoordinator._DETAIL_FALLBACK_ORDER`
3. **失败不扣费验证**：Wellbyte 422 扣 0（实测确认），Dajiala/JustOneAPI 参数错误不扣费 → ✅ 各 client 的 suppress_errors 路径

## API Key 脱敏说明

实测使用的 API key 不归档于此文档。生产环境通过环境变量注入：
- `DAJIALA_API_KEY` / `JUSTONEAPI_API_KEY` / `TIKHUB_API_KEY` / `WELLBYTE_API_KEY`
- docker-compose.yml `&backend_env` 锚点已配置对应环境变量映射
- Settings 类（core/config.py）已添加对应字段，默认空串（未配置 = 跳过注册）
