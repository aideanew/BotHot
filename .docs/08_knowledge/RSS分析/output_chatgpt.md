可以，而且按照你的四个要求——**稳定、每天自动更新、结构统一、自托管入库**——我不建议把系统简单做成“一个 RSS 阅读器”，而是做成：

> **微信公众号专用采集层 + 通用 RSS/网站采集层 + 统一标准化层 + PostgreSQL 内容库 + 每日汇总层**

截至 **2026 年 9 月**，微信公众号这一层依然是整个系统里最特殊、也最容易失效的部分：公众号本身并没有像普通网站那样统一、稳定的官方 RSS 出口。现在较成熟的方案主要依赖微信读书或网页采集，因此应该把它隔离出来，不要让整个系统绑定在某一种公众号采集实现上。原始 WeWe RSS 项目已经在 **2026-05-11** 被归档，因此不建议直接把原项目作为长期唯一底座。([github.com][1])

---

# 一、我最建议你的整体架构

```text
                    ┌──────────────────────────┐
                    │       信息源管理中心       │
                    │  公众号 / RSS / 网站 / API │
                    └────────────┬─────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            │                    │                    │
            ▼                    ▼                    ▼
   ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
   │ 微信公众号采集层 │   │ 标准 RSS 采集层 │   │ 特殊网站采集层 │
   │                │   │                │   │                │
   │ WeRSS / WeMP   │   │ Miniflux       │   │ RSSHub         │
   │ RSS / API      │   │ 原生RSS/Atom    │   │ RSS-Bridge     │
   └───────┬────────┘   └───────┬────────┘   └───────┬────────┘
           │                    │                    │
           └────────────────────┼────────────────────┘
                                ▼
                     ┌──────────────────────┐
                     │ 统一标准化 / 去重层    │
                     │                      │
                     │ 标题 / 正文 / 来源     │
                     │ 时间 / 作者 / 分类     │
                     │ URL / hash / 标签      │
                     └──────────┬───────────┘
                                ▼
                     ┌──────────────────────┐
                     │     PostgreSQL       │
                     │                      │
                     │ articles             │
                     │ sources              │
                     │ feeds                │
                     │ fetch_runs           │
                     │ tags                 │
                     │ daily_digest         │
                     └──────────┬───────────┘
                                │
                    ┌───────────┼────────────┐
                    ▼           ▼            ▼
                 阅读器      搜索/RAG      每日简报
                              /AI分析        ↓
                                         微信/飞书/邮件
```

这个架构最大的好处是：

**微信公众号采集挂掉，不影响 AI、教育、国际资讯、科技网站等其他来源。**

以后即使微信公众号采集技术换掉，数据库和下游系统都不用重做。

---

# 二、微信公众号：目前有 4 种路线

## 方案 A：WeRSS 类自托管方案

这是我认为目前最符合你需求的方向之一。

现在比较值得关注的是新的 `letuswerss/werss`，它已经不是单纯“RSS 阅读器”，而是在做完整的微信公众号内容采集与分析系统。

它目前支持：

* 微信公众号订阅
* 定时采集
* RSS 输出
* API
* PostgreSQL / MySQL / SQLite
* 标签
* 热点发现
* AI 标签
* Web 管理
* Webhook
* MinIO 图片存储
* 文章保留策略
* API Key
* Docker Compose

并且当前版本已经有 `v1.1.5`，项目仍在维护。([GitHub][2])

它的一个非常重要的特点是：

```text
微信公众号
     ↓
WeRSS
     ↓
PostgreSQL
     ↓
API / RSS
     ↓
你的统一信息库
```

也就是说，它本身已经具备你要的“服务器运行 + 数据库存储 + 自动更新”。

而且它明确支持：

```text
SQLite
MySQL
PostgreSQL
```

以及：

```text
GET /api/v1/wx/mps
GET /api/v1/wx/articles
GET /api/v1/wx/articles/{id}
GET /rss
GET /rss/{feed_id}
```

等 API。([GitHub][3])

### 但是

我不会把它直接定义成“整个系统的最终数据库”。

原因很简单：

> **它是微信公众号系统，不应该成为整个互联网信息系统的核心抽象。**

你的数据库最终应该能够同时容纳：

```text
微信公众号
RSS
新闻网站
AI 官方博客
arXiv
教育网站
YouTube
Podcast
未来其他 API
```

所以更好的办法是：

```text
WeRSS
   ↓
统一内容 API
   ↓
你的 PostgreSQL
```

而不是：

```text
所有信息
   ↓
全部塞进 WeRSS
```

---

# 三、We-MP-RSS 也是一个值得关注的路线

`rachelos/we-mp-rss` 目前仍在维护，功能也比较丰富。

它支持：

* 微信公众号采集
* RSS
* 自动定时更新
* SQLite
* MySQL
* API
* Webhook
* Markdown
* DOCX
* PDF
* JSON
* 多种采集模式
* Redis
* 通知
* HTML 清洗

并且后端是：

```text
Python + FastAPI
```

前端是：

```text
Vue 3 + Vite
```

数据库支持 SQLite / MySQL。([GitHub][4])

它还有一个很实际的优点：

> 项目结构比较偏“采集系统”，而不是单纯 RSS 阅读器。

所以也很适合作为微信公众号采集器。

---

# 四、但是有一个必须特别注意的问题

微信公众号采集目前**没有真正意义上的“100%稳定方案”**。

例如旧版 WeWe RSS 的 issue 中就存在：

* 订阅停止更新
* 无法添加公众号
* 429
* 微信读书账号失效
* 部分公众号无法更新
* 数量较大后出现限制

等问题。([GitHub][5])

所以你的设计必须遵循：

> **微信公众号是“不可靠输入源”，不是整个系统的单点依赖。**

这是整个架构里非常重要的一点。

---

# 五、另一个方向：Mp2RSS

还有一个值得关注的商业化/服务化方案：

**Mp2RSS**

它与自托管项目最大的区别是：

```text
不需要自己维护微信公众号采集系统
```

它现在支持：

* 微信公众号文章
* RSS
* JSON Feed
* Open API
* CLI
* AI Agent
* X/Twitter
* 公众号整号订阅
* Markdown 正文

并且可以直接把公众号文章作为结构化数据消费。官方项目称公众号文章平均约 **2–3 小时**从发文到数据可见。([GitHub][6])

它的模型是：

```text
公众号文章 URL
      ↓
Mp2RSS
      ↓
JSON / RSS / API
      ↓
你的服务器
      ↓
PostgreSQL
```

这个方案最大的优势是**减少自己维护微信采集器的成本**。

最大的缺点则正好相反：

> 你要求“在我的服务器上运行”，那么 Mp2RSS 就不完全符合你的自托管要求。

因此我会把它作为：

**微信公众号采集层的备用/容灾渠道**

而不是主系统。

---

# 六、标准 RSS 信息源就简单很多了

国际新闻、AI、教育、科技等信息，不应该再使用微信公众号那套复杂机制。

优先级应该是：

```text
官方网站 RSS / Atom
        ↓
     直接采集
```

例如 MIT News 官方就直接提供：

* Latest News
* Research
* Engineering
* AI
* Education
* Global
* Science

等多个 RSS。([MIT新闻][7])

这样来源就非常干净。

---

# 七、对于普通 RSS，我更建议 Miniflux

如果你准备自己搭这个系统，我反而很推荐：

**Miniflux**

它很适合作为：

> **RSS 抓取与标准化入口**

它支持：

* RSS 1.0 / 2.0
* Atom
* JSON Feed
* OPML
* 全文抓取
* 全文搜索
* PostgreSQL
* API
* Webhook
* 分类
* 标签
* 定时抓取
* RSS-Bridge
* Docker
* 自托管

而且它是单体 Go 服务 + PostgreSQL，架构非常简单。([Miniflux][8])

它还有一个非常适合你需求的设计：

### 新文章 Webhook

Miniflux 可以在发现新文章之后向你的接口：

```http
POST /webhook/miniflux
```

发送 JSON。

([Miniflux][9])

这样可以做到：

```text
RSS新文章
       ↓
Miniflux
       ↓
Webhook
       ↓
你的 Content Ingestor
       ↓
PostgreSQL
       ↓
AI分类 / 摘要 / 标签
```

这比每天跑一个脚本扫所有网站要专业得多。

---

# 八、FreshRSS 也可以，但定位稍有不同

FreshRSS 同样是非常成熟的自托管 RSS 聚合器。

它支持：

* RSS
* Atom
* Web Scraping
* OPML
* 搜索
* Feed 生成
* WebSub
* 自托管
* 大量 Feed

官方目前仍把它定位为轻量、自托管 RSS/Atom 聚合器。([FreshRSS][10])

所以：

```text
Miniflux
```

我更倾向于把它作为：

> **机器采集 / API / 数据管道**

而：

```text
FreshRSS
```

更适合作为：

> **个人阅读 / Web 阅读界面**

如果你的最终目标主要是“内容数据库 + AI”，Miniflux 会更契合。

---

# 九、RSSHub 和 RSS-Bridge 非常适合作为“适配器”

这是另一个核心组件。

大量网站：

```text
没有 RSS
```

这时候不要自己写几十个爬虫。

可以用：

```text
RSSHub
RSS-Bridge
```

作为中间适配层。

RSS-Bridge 本身就是把：

> 没有 RSS 的网站转换成 RSS / Atom

的工具，并且可以自托管。([RSS Bridge][11])

Miniflux 甚至原生支持 RSS-Bridge 集成，当网站本身不存在 Feed 时，可以尝试通过 RSS-Bridge 生成 Feed。([Miniflux][12])

RSSHub 同样拥有大量第三方网站适配规则，目前仍在持续维护。它甚至存在微信公众号相关路由，不过其公众号路线同样存在第三方依赖和反爬问题，所以我不建议把它作为你的主要微信公众号方案。([GitHub][13])

---

# 十、这样你的信息源就可以分成 5 类

我会把你的整个信息系统设计成：

| source_type  | 采集方式            | 典型来源            |
| ------------ | --------------- | --------------- |
| `wechat`     | WeRSS / WeMP    | 微信公众号           |
| `rss`        | Miniflux        | 官方 RSS / Atom   |
| `rss_bridge` | RSS-Bridge      | 无 RSS 网站        |
| `rsshub`     | RSSHub          | 社交网站/特殊网站       |
| `api`        | 自己的 API Adapter | 新闻 API / 数据 API |

最终全部转换成统一结构。

---

# 十一、你的统一文章结构非常重要

无论来源是什么，最终都变成：

```json
{
  "id": "uuid",
  "source_type": "wechat",
  "source_id": "xxx",
  "source_name": "机器之心",
  "author": "xxx",
  "title": "xxx",
  "url": "https://...",
  "published_at": "2026-09-28T08:30:00+08:00",
  "fetched_at": "2026-09-28T09:00:00+08:00",

  "content_html": "...",
  "content_markdown": "...",
  "summary": null,

  "language": "zh",
  "category": "ai",

  "tags": [],
  "cover_image": "...",

  "content_hash": "...",
  "url_hash": "...",

  "raw_source": {},
  "status": "active"
}
```

这样以后：

```text
微信公众号
MIT
BBC
arXiv
OpenAI
Anthropic
Hugging Face
教育网站
```

在数据库里全部长得一样。

这会给你未来做：

```text
全文搜索
AI 摘要
Embedding
RAG
热点检测
主题聚类
每日简报
周报
信息评分
知识库
```

留下很大的空间。

---

# 十二、数据库我建议这样设计

不要只有一张 `articles` 表。

最少：

```text
sources
   ↓
feeds
   ↓
articles
   ↓
article_contents
   ↓
article_tags
   ↓
tags
```

另外再有：

```text
fetch_runs
daily_digests
notifications
```

例如：

```text
sources
├── 微信公众号
├── MIT News
├── BBC
├── OpenAI
├── arXiv
└── Hugging Face

feeds
├── 机器之心
├── 36氪
├── MIT AI
├── MIT Education
├── OpenAI News
└── arXiv AI

articles
├── article A
├── article B
├── article C
└── ...

daily_digests
├── 2026-09-27
├── 2026-09-28
└── ...
```

---

# 十三、每日自动更新不要理解成“每天只抓一次”

我建议：

### 采集频率

```text
微信公众号
    2~4 次/天

普通 RSS
    15~60 分钟一次

高优先级新闻
    5~15 分钟一次
```

### 然后每天固定时间生成：

```text
07:30
↓
当天信息汇总
↓
去重
↓
分类
↓
热点聚类
↓
AI摘要
↓
生成 Daily Digest
```

最终：

```text
2026-09-28 每日信息简报

01 国际
02 国内
03 AI
04 科技
05 教育
06 商业
07 科学
08 值得关注
```

数据库同时保留：

```text
原始文章
+
结构化数据
+
AI标签
+
AI摘要
+
每日汇总
```

这就不只是 RSS 阅读器了，而是真正的**个人信息基础设施**。

---

# 十四、你尤其适合增加“来源等级”

因为你以后可能会接几十甚至几百个源。

可以设置：

```text
source_priority

P0 = 官方机构
P1 = 一线媒体
P2 = 专业媒体
P3 = 专业个人
P4 = 聚合/二手来源
```

例如 AI：

```text
OpenAI
Anthropic
Google DeepMind
Meta AI
Microsoft Research
Hugging Face
arXiv
MIT
Stanford
```

和：

```text
AI 自媒体
```

在系统里不能完全等价。

数据库因此可以保留：

```text
source_trust_level
source_type
source_country
source_language
source_category
```

以后 AI 做摘要时也可以知道：

> 这是官方原始信息，还是第三方解读。

---

# 十五、我比较推荐的最终技术栈

如果是你自己的服务器，我会这样搭：

```text
Docker Compose
│
├── PostgreSQL
│
├── Miniflux
│
├── WeRSS
│
├── RSSHub
│
├── RSS-Bridge
│
├── Content Ingestor
│
├── AI Processor
│
└── Daily Digest
```

其中：

### 1. WeRSS

专门负责：

```text
微信公众号
```

### 2. Miniflux

负责：

```text
标准 RSS / Atom
```

### 3. RSSHub

负责：

```text
特殊网站 / 社交平台
```

### 4. RSS-Bridge

负责：

```text
没有 RSS 的普通网站
```

### 5. Content Ingestor

这是你自己写的核心：

```text
所有来源
    ↓
统一格式
    ↓
去重
    ↓
入 PostgreSQL
```

### 6. AI Processor

负责：

```text
分类
摘要
标签
关键词
主题
热点
embedding
```

### 7. Daily Digest

负责：

```text
每天 1 次
生成自己的“今日信息报”
```

---

# 十六、还有一个特别重要的设计

**不要让 Miniflux / WeRSS 成为你的“永久数据库”。**

它们应该是：

```text
采集系统
```

你的真正核心应该是：

```text
PostgreSQL
```

即：

```text
                 ┌── WeRSS
                 │
                 ├── Miniflux
信息源 ──────────┼── RSSHub
                 │
                 ├── RSS-Bridge
                 │
                 └── API
                       ↓
                Content Ingestor
                       ↓
                  PostgreSQL
                       ↓
             ┌─────────┼─────────┐
             ↓         ↓         ↓
            搜索      RAG       每日简报
```

这样未来：

```text
今天用 WeRSS
明天换成其他公众号采集器
后天自己写公众号 Adapter
```

你的数据库和整个下游系统都不用动。

---

# 十七、关于“自动发现新的微信公众号”

这里还可以进一步做一层。

你现在说的是：

> “微信公众号为主的信息，结合其他渠道”

我理解成主要是：

> **你已经有一批公众号，希望每天自动获取这些公众号的新文章。**

如果你真正想要的是：

> **系统每天自动发现新的优质微信公众号，然后自动判断是否订阅**

那就完全是另一个层次了。

可以增加：

```text
Source Discovery
       ↓
关键词 / 行业
       ↓
发现候选公众号
       ↓
来源质量判断
       ↓
重复检查
       ↓
人工确认 / 自动加入
       ↓
进入 WeRSS
```

例如：

```text
AI
├── 大模型
├── Agent
├── Coding Agent
├── AIGC
└── AI产业

教育
├── 教育政策
├── 国际教育
├── 学校
├── 心理教育
└── 教育科技
```

这个“发现系统”不建议一开始就自动放权，否则很容易造成信息源污染。

---

# 十八、如果以你的需求为目标，我会这样落地

### 第一阶段：建立采集底座

```text
PostgreSQL
+
WeRSS
+
Miniflux
+
Content Ingestor
```

先做到：

```text
微信公众号
↓
RSS
↓
每天自动入库
```

---

### 第二阶段：扩展信息来源

加入：

```text
RSSHub
RSS-Bridge
官方 RSS
官方 API
```

开始覆盖：

```text
国际
时事
AI
科技
教育
科学
商业
```

---

### 第三阶段：AI 信息处理

增加：

```text
自动分类
自动摘要
自动标签
实体识别
主题聚类
热点发现
```

---

### 第四阶段：每日信息日报

每天例如：

```text
08:00

《今日信息中心》

★★★★★ 必看
AI
国际
教育

★★★★ 值得关注
科技
商业

★★★ 一般资讯

────────────

今日 137 篇新增
↓
去重后 93 篇
↓
聚类 28 个主题
↓
重点主题 11 个
```

---

# 十九、我目前比较建议的组合

综合你提出的四个条件，我会优先考虑：

```text
                 你的服务器
                     │
        ┌────────────┴────────────┐
        │                         │
  微信公众号                    其他信息源
        │                         │
      WeRSS                    Miniflux
        │                         │
        │                  ┌──────┴──────┐
        │                  │             │
        │               RSSHub      RSS-Bridge
        │                  │             │
        └──────────────────┴─────────────┘
                          │
                          ▼
                  Content Ingestor
                          │
                          ▼
                    PostgreSQL
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
             API         RAG      Daily Digest
```

**这比“直接找一个万能 RSS 工具”更适合你的需求。**

尤其是微信公众号这块，旧的 WeWe RSS 已经归档，而现在又出现了继续维护的 WeRSS 分支/新项目，因此从工程角度最好采用**可替换 Adapter**，而不是把整个系统锁死在某一个项目上。([GitHub][1])

### 一个值得注意的现实边界

“稳定”可以做到的是：

> **整个系统稳定运行。**

而不能承诺：

> **微信公众号本身永远稳定可抓。**

因此真正专业的设计目标应该是：

**“单一信息源失效不会导致整个信息库失效，并且能够检测、告警、重试和替换采集器。”**

这才是你这套系统长期运行的关键。

如果按你的实际需求继续往下设计，我建议下一步直接把它具体化成一套 **“个人信息采集中心”技术方案**：包括 Docker Compose、服务目录结构、PostgreSQL 表结构、公众号/RSS/AI/教育/国际信息源分类、每天 08:00 自动更新与日报、失败重试、去重、全文保存以及后续接 RAG 的完整架构。

[1]: https://github.com/cooderl/wewe-rss?utm_source=chatgpt.com "GitHub - cooderl/wewe-rss: 🤗更优雅的微信公众号订阅方式，支持私有化部署、微信公众号RSS生成（基于微信读书） · GitHub"
[2]: https://github.com/letuswerss/werss?utm_source=chatgpt.com "GitHub - letuswerss/werss: WeRSS - 面向个人自托管场景的微信公众号热度分析系统，AI Powered 订阅内容整理与分析工具，支持订阅管理、摘要 RSS、标签整理、主题归纳、可视化与本地化后台管理, API/MCP调用。 · GitHub"
[3]: https://github.com/letuswerss/werss "GitHub - letuswerss/werss: WeRSS - 面向个人自托管场景的微信公众号热度分析系统，AI Powered 订阅内容整理与分析工具，支持订阅管理、摘要 RSS、标签整理、主题归纳、可视化与本地化后台管理, API/MCP调用。 · GitHub"
[4]: https://github.com/rachelos/we-mp-rss/wiki/WeRSS-%E2%80%90-%E5%BE%AE%E4%BF%A1%E5%85%AC%E4%BC%97%E5%8F%B7%E8%AE%A2%E9%98%85%E5%8A%A9%E6%89%8B?utm_source=chatgpt.com "WeRSS ‐ 微信公众号订阅助手 · rachelos/we-mp-rss Wiki · GitHub"
[5]: https://github.com/cooderl/wewe-rss/issues/251?utm_source=chatgpt.com "无法添加新的公众号 · Issue #251 · cooderl/wewe-rss · GitHub"
[6]: https://github.com/areyoubugcoder/Mp2RSS "GitHub - areyoubugcoder/Mp2RSS: 持续抓取公众号最新文章，沉淀为含 Markdown 正文的结构化数据，通过 RSS / JSON Feed / Open API / CLI / AI Agent 多种形态交付 —— 支撑舆情分析、投研报告、内容监测、高质量信息收集与个人内容阅读。 · GitHub"
[7]: https://news.mit.edu/rss?utm_source=chatgpt.com "RSS | MIT News | Massachusetts Institute of Technology"
[8]: https://miniflux.app/features.html?utm_source=chatgpt.com "Features"
[9]: https://miniflux.app/docs/webhooks.html?utm_source=chatgpt.com "Webhooks"
[10]: https://www.freshrss.org/?utm_source=chatgpt.com "FreshRSS, a free, self-hostable feeds aggregator"
[11]: https://rss-bridge.org/?utm_source=chatgpt.com "rss-bridge.org"
[12]: https://miniflux.app/docs/rss_bridge.html?utm_source=chatgpt.com "RSS-Bridge"
[13]: https://github.com/DIYgod/RSSHub/blob/master/lib/routes/rsshub/routes.ts?utm_source=chatgpt.com "RSSHub/lib/routes/rsshub/routes.ts at master · DIYgod/RSSHub · GitHub"



你现在遇到的其实是微信公众号采集里最关键的一道坎：

> **“已知一篇文章，可以拿到文章正文” ≠ “只知道公众号名称，就能拿到该公众号的历史文章列表”。**

这两个能力走的是不同的数据链路。

### 你现在缺的其实是这一步

```text
公众号名称
   ↓
公众号唯一身份标识
   ↓
公众号 BookId / fakeid
   ↓
公众号文章列表
   ↓
reviewId / article token
   ↓
文章正文
```

目前比较清楚的一条可行链路，是**通过微信读书的公众号接口拿列表**。2026 年 7 月，`we-mp-rss` 项目的新方案文档明确记录了这条路径：公众号在微信读书侧对应一个 `BookId`，格式通常是 `MP_WXS_<fakid>`；获取文章列表使用 `GET https://weread.qq.com/web/mp/articles?bookId=<BOOK_ID>&offset=...`，再从列表响应中取得每篇文章的 `reviewId`，最后调用 `/web/mp/content?reviewId=...` 获取正文。这个链路依赖微信读书 Web 登录 Cookie。([GitHub][1])

所以你应该把问题拆成 **两个不同接口**：

```text
A. 公众号搜索
公众号名称
    ↓
fakeid / mp_id / BookId

B. 文章采集
BookId
    ↓
文章列表
    ↓
reviewId
    ↓
文章正文
```

---

# 1. 公众号名称如何换成唯一 ID？

现在 `we-mp-rss` 本身就提供了公众号搜索接口：

```http
GET /api/mps/search/{kw}
```

代码里实际调用的是：

```python
search_Biz(kw, limit, offset)
```

它返回公众号搜索结果。项目随后把公众号的 `mp_id` / `faker_id` 保存起来。([GitHub][2])

也就是说，你不要直接：

```text
公众号名字
↓
猜文章 URL
```

而应该：

```text
"机器之心"
↓
search_Biz("机器之心")
↓
{
   mp_name: "机器之心",
   mp_id: "...",
   avatar: "...",
   ...
}
```

然后把这个 `mp_id/faker_id` 转换成微信读书侧的 BookId。

项目当前的实现实际上就是这样做的：添加公众号时，保存 `faker_id`，然后调用 `WxGather().Model().get_Articles(...)` 抓取该公众号的文章。([GitHub][2])

---

# 2. 微信读书这一层才是真正的“文章列表”

目前公开记录得比较清楚：

```http
GET https://weread.qq.com/web/mp/articles
```

参数：

```text
bookId
offset
```

例如：

```http
GET https://weread.qq.com/web/mp/articles?bookId=MP_WXS_xxx&offset=0
```

继续：

```text
offset=20
offset=40
offset=60
...
```

就可以翻页。

当前公开的 2026 年方案文档明确记录了这一点，而且指出 `reviewId` 就是在这个列表接口的响应中获得的。([GitHub][1])

所以你的采集器应该长这样：

```python
def sync_public_account(mp_name):

    # 1. 搜公众号
    mp = search_public_account(mp_name)

    # 2. 获得 BookId
    book_id = mp.book_id

    # 3. 分页获取文章
    offset = 0

    while True:
        articles = get_mp_articles(
            book_id=book_id,
            offset=offset
        )

        if not articles:
            break

        for article in articles:
            save_article_metadata(article)

        offset += 20
```

然后第二层：

```python
for article in articles:
    content = get_mp_content(
        review_id=article["reviewId"]
    )

    save_article_content(content)
```

---

# 3. 你的“文章 URL 采集器”很可能已经有第二半了

你现在说：

> “我实现了获取指定文章，但有公众号名字，拿不到文章列表。”

这非常像是你已经实现了：

```text
文章URL
    ↓
mp.weixin.qq.com/s/xxxx
    ↓
文章正文
```

但缺：

```text
公众号名字
    ↓
公众号 ID
    ↓
文章列表
```

所以**不需要推倒重来**。

你应该直接增加一个：

```text
PublicAccountResolver
```

再增加：

```text
PublicAccountArticleLister
```

架构：

```text
wechat/
├── account/
│   ├── search.py
│   ├── resolver.py
│   └── model.py
│
├── article/
│   ├── list.py        ← 你现在缺的
│   ├── content.py     ← 你已经有的
│   └── parser.py
│
└── sync/
    └── scheduler.py
```

---

# 4. 最关键的一点：不要把“公众号名称”当主键

例如：

```text
机器之心
```

只是展示名称，不应该作为真正身份。

应该保存：

```text
mp_name
mp_id
faker_id
book_id
avatar
intro
```

数据库：

```sql
CREATE TABLE wechat_accounts (
    id              UUID PRIMARY KEY,
    mp_name         TEXT NOT NULL,
    mp_id           TEXT,
    faker_id        TEXT,
    book_id         TEXT,
    avatar_url      TEXT,
    intro           TEXT,

    source_provider TEXT,
    status          TEXT,

    last_sync_at    TIMESTAMP,
    created_at      TIMESTAMP,
    updated_at      TIMESTAMP
);
```

因为以后可能出现：

```text
同名公众号
名称修改
账号迁移
采集器更换
```

所以：

```text
mp_name = 可变属性
mp_id   = 身份
book_id = 某个采集渠道的身份映射
```

这会安全很多。

---

# 5. 你现在最应该做的是“公众号解析器”

整个流程建议变成：

```text
用户输入：

"机器之心"
       │
       ▼
┌───────────────────┐
│ PublicAccountSearch│
└─────────┬─────────┘
          ▼
      搜索结果
          │
          ▼
┌───────────────────┐
│ Account Resolver   │
└─────────┬─────────┘
          ▼
 mp_id / faker_id
          │
          ▼
      BookId
          │
          ▼
┌───────────────────┐
│ Article List API   │
│ offset=0           │
│ offset=20          │
│ offset=40          │
└─────────┬─────────┘
          ▼
      reviewId
          │
          ▼
┌───────────────────┐
│ Article Content    │
└───────────────────┘
```

这样以后用户只输入：

```text
添加公众号：机器之心
```

系统就可以自动完成：

```text
搜索
→ 确认公众号
→ 获取 ID
→ 获取历史列表
→ 获取文章
→ 入库
→ 后续定时增量更新
```

---

# 6. 还有一个非常重要的细节：不要每次都全量抓

你最终是做“每日自动更新”，所以第一次：

```text
抓过去 N 页
```

以后应该：

```text
每次只抓最新 1~2 页
```

例如：

```text
第一次
offset=0
offset=20
offset=40
...
直到初始化完成

以后每天
offset=0
offset=20
```

然后根据：

```text
reviewId
文章 URL
publish_time
content_hash
```

去重。

这样可以显著降低请求量。

`we-mp-rss` 当前实现本身就存在 `mp_max_pages`、分页间隔等配置，并且其 issue 也特别提到了批量订阅后立即多页抓取会增加风险暴露，因此“添加订阅”和“大规模初始历史抓取”最好解耦。([GitHub][3])

---

# 7. 如果你已经在使用 WeRSS，其实不用自己重新实现底层

目前 `WeRSS` 已经把这一层封装起来了。

它有：

```text
GET /api/v1/wx/mps
GET /api/v1/wx/mps/{mp_id}

GET /api/v1/wx/articles
POST /api/v1/wx/articles
```

其中文章查询可以按：

```text
mp_id
发布时间
标题
标签
```

进行过滤。([GitHub][4])

因此你完全可以把它作为：

```text
微信公众号采集 Adapter
```

然后你的程序只需要：

```text
公众号名称
   ↓
WeRSS Search
   ↓
mp_id
   ↓
WeRSS Article Query
   ↓
你的 PostgreSQL
```

这比你自己重新维护微信读书接口要省事很多。

---

# 8. 如果你现在是自己写代码，我更建议你这样做

不要把：

```text
微信文章抓取
```

写成一个巨大的爬虫。

抽象成：

```text
interface WechatSourceAdapter {

    searchAccounts(name): Account[]

    resolveAccount(account): AccountIdentity

    listArticles(account, cursor): ArticlePage

    getArticle(article): ArticleContent
}
```

然后现在：

```text
WeReadAdapter
```

以后可以再接：

```text
WeRSSAdapter
WeMpRssAdapter
Mp2RssAdapter
```

最终你的业务层完全不知道底层究竟是：

```text
微信读书
WeRSS
其他服务
```

这和你之前做项目时喜欢的“业务层不要知道底座实现”其实是同一个工程思路。

---

## 你现在这个问题，可以直接定位成一句话

**你已经解决了 `ArticleContent`，现在缺的是 `Account → ArticleList`。**

最现实的当前链路是：

```text
公众号名称
 ↓
公众号搜索 / search_Biz
 ↓
faker_id / mp_id
 ↓
BookId = MP_WXS_xxx
 ↓
weread.qq.com/web/mp/articles
 ↓
reviewId
 ↓
weread.qq.com/web/mp/content
 ↓
正文
```

这条链路在目前公开的 2026 年资料中仍有明确实现记录。([GitHub][1])

**如果你把你现在“已经能获取指定文章”的代码或项目目录贴出来，我可以直接按你现有实现帮你补上“公众号名称 → 公众号 ID → 文章列表 → 全量/增量同步”的这一段，而不是让你重写整个采集器。**

[1]: https://github.com/rachelos/we-mp-rss/issues/442 "新方案路径 · Issue #442 · rachelos/we-mp-rss · GitHub"
[2]: https://github.com/rachelos/we-mp-rss/blob/main/apis/mps.py?utm_source=chatgpt.com "we-mp-rss/apis/mps.py at main · rachelos/we-mp-rss · GitHub"
[3]: https://github.com/rachelos/we-mp-rss/blob/main/config.example.yaml?utm_source=chatgpt.com "we-mp-rss/config.example.yaml at main · rachelos/we-mp-rss · GitHub"
[4]: https://github.com/letuswerss/werss?utm_source=chatgpt.com "GitHub - letuswerss/werss: WeRSS - 面向个人自托管场景的微信公众号热度分析系统，AI Powered 订阅内容整理与分析工具，支持订阅管理、摘要 RSS、标签整理、主题归纳、可视化与本地化后台管理, API/MCP调用。 · GitHub"
