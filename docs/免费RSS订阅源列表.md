# 免费 RSS 订阅源完整列表

> 调研日期：2026-10-02
> 覆盖：微信公众号、中文内容源、通用 RSS 工具

---

## 一、RSSHub（开源/自托管/免费）

- **URL**: https://rsshub.app (官方) | https://github.com/DIYgod/RSSHub
- **免费**: ✅ 开源 AGPL-3.0，自托管免费，公共实例免费
- **状态**: 全球最大 RSS 网络，5000+ 实例

### 微信公众号路由（10条）

| 路由 | 后端 | 用法 | 示例 |
|------|------|------|------|
| `/wechat/ce/:id` | CarrierEngine | 传入作者ID | `/wechat/ce/595a5b14d7164e53908f1606` |
| `/wechat/sogou/:id` | 搜狗微信搜索 | 传入公众号名称 | `/wechat/sogou/人民日报` |
| `/wechat/feeddd/:id` | feed.hamibot.com | 传入feeddd ID（**已关闭**） | — |
| `/wechat/mp/homepage/:biz/:hid/:cid?` | 微信MP主页 | biz=base64编码的公众号ID | `/wechat/mp/homepage/MzA3MDM3NjE5NQ==/16` |
| `/wechat/data258/:id?` | mp.data258.com | 传入分类ID | `/wechat/data258/gh_cbbad4c1d33c` |
| `/wechat/tgchannel/:id/:mpName?` | Telegram频道镜像 | 传入TG频道名 | `/wechat/tgchannel/lifeweek` |
| `/wechat/uread/:userid` | uread.ai | 传入uread用户ID | `/wechat/uread/shensining` |
| `/wechat/ershcimi/:id` | cimidata.com（二十次幂） | 传入作者ID | `/wechat/ershcimi/813oxJOl` |
| `/wechat/announce` | 微信官方公告 | 无参数 | `/wechat/announce` |
| `/wechat/msgalbum/:id` | 微信消息合辑 | 传入合辑ID | — |

### 可用公共实例

| 实例 | URL | 状态 |
|------|-----|------|
| 官方 | https://rsshub.app/ | ⚠️ 当前不可达 |
| 社区 | https://rss.injahow.cn/ | ✅ 可用 |

### 其他中文内容源（通过 RSSHub）

| 平台 | 路由示例 |
|------|----------|
| 微博 | `/weibo/user/:uid` |
| 知乎 | `/zhihu/hotlist`, `/zhihu/daily` |
| 哔哩哔哩 | `/bilibili/user/video/:uid` |
| 36氪 | `/36kr/newsflashes` |
| 财新 | `/caixin/latest` |
| 第一财经 | `/yicai/brief`, `/yicai/news` |
| 华尔街见闻 | `/wallstreetcn/news`, `/wallstreetcn/live` |
| 澎湃新闻 | `/thepaper/featured` |
| 小宇宙播客 | `/xiaoyuzhou/podcast/:id` |

> **注意**: 搜狗/data258 等路由需要访问国内服务，海外实例可能 DNS 失败。建议使用国内实例或自托管。

---

## 二、Wechat2RSS（免费公共 + 付费私有）

- **URL**: https://wechat2rss.xlab.app
- **免费**: 部分免费（公共预索引列表），私有部署 15元/月 或 150元/年

### 免费公共源
- 访问 https://wechat2rss.xlab.app/list/all 获取完整列表
- **安全类**: 300+ 账号（看雪学院、腾讯安全应急响应中心、奇安信威胁情报中心等）
- **开发类**: 腾讯技术工程、爱奇艺技术、小米技术、B站技术、机器之心等
- **其他**: 老高的互联网杂谈、小众软件、42章经等
- **延迟**: 平均6小时
- **输出**: 全文，含图片/视频代理
- **OPML**: 支持批量导入

### 付费私有部署
- 基于微信读书采集
- 支持文章链接订阅和公众号ID订阅
- 可配置告警（Telegram、Server酱、Webhook、Bark）
- **价格**: 150元/年（2024-10-01前注册 100元/年）

---

## 三、WeRSS（付费，有试用）

- **URL**: https://werss.app
- **免费**: ❌ 付费，3天免费试用
- **状态**: ⚠️ 暂不开放新订阅
- **输出**: 全文，8-10篇近9天文章
- **延迟**: 1分钟~28小时，平均半天
- **限制**: 最多2个RSS阅读器，不可分享feed URL

---

## 四、feeddd / Hamibot Feed（已关闭）

- **URL**: https://feeddd.org | https://github.com/feeddd/feeds
- **状态**: ❌ 2023-07-05 关闭
- **替代**: Hamibot 专用版脚本仍可用 https://hamibot.com/marketplace/Bh55i

---

## 五、通过 RSSHub 可用的微信公众号源

| 服务 | URL | 路由 | 状态 |
|------|-----|------|------|
| CarrierEngine | search.carrierengine.us | `/wechat/ce/:id` | ✅ 可用 |
| 搜狗微信 | weixin.sogou.com | `/wechat/sogou/:id` | ⚠️ 反爬 |
| 二十次幂 | cimidata.com | `/wechat/ershcimi/:id` | ✅ 可用 |
| data258 | mp.data258.com | `/wechat/data258/:id` | ⚠️ 反爬 |
| uread | uread.ai | `/wechat/uread/:userid` | ✅ 可用 |

---

## 六、通用 RSS 工具

| 工具 | URL | 免费 | 说明 |
|------|-----|------|------|
| ALL-about-RSS | https://rss.tips | ✅ | RSS资源目录（5916⭐） |
| RSS-Bridge | https://github.com/RSS-Bridge/rss-bridge | ✅ | PHP RSS生成器，自托管 |
| Feed43 | https://www.feed43.com | 基础免费 | 网页→RSS转换 |

---

## 七、推荐方案

| 场景 | 推荐方案 | 理由 |
|------|----------|------|
| **最佳免费** | 自托管 RSSHub | 10条微信路由 + 数百中文源，Docker一键部署 |
| **最简单免费** | Wechat2RSS 公共列表 | 零配置，复制feed URL即可，400+预索引账号 |
| **未收录账号** | 国内 RSSHub 实例 + sogou/ce 路由 | 可搜索任意公众号，注意反爬 |
| **最稳定** | Wechat2RSS 私有部署 (150元/年) | 6小时延迟，全文，图片代理 |
