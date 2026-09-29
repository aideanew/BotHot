针对你提出的“微信公众号RSS为主，结合多领域信息，在自有服务器上每日自动更新并入库”的需求，基于当前可用的开源工具和自动化框架，以下是一套完整可行的技术方案。

---

## 一、微信公众号RSS：自建工具选型

微信公众号没有原生RSS输出，必须通过第三方工具生成。当前主要有四类开源方案，稳定性差异较大：

| 工具 | 技术原理 | 稳定性 | 部署复杂度 | 关键风险 |
|------|---------|--------|-----------|----------|
| **Wechat2RSS** | 公众号后台接口 + 定时抓取 | 较高 | Docker Compose，简单 | 微信风控触发后等待时间倍增，最大等待6小时 |
| **we-mp-rss** | 公众号后台接口 + Web管理面板 | 较高 | Docker一行命令 | 需要已开通公众号的微信扫码授权 |
| **WeWe RSS** | 基于微信读书接口 | 中等 | Docker Compose | 有用户反馈登录数小时即失效 |
| **wechat-download-api** | 公众号接口 + IP代理池 | 中等 | 需自行构建 | 反风控体系复杂，维护成本较高 |

**推荐：Wechat2RSS 或 we-mp-rss。**

Wechat2RSS 的设计目标是“长期稳定可用”，程序只抓取最新20篇文章，不会回溯历史，更新延迟在0-24小时内波动，每个公众号每天检查1-2次。它通过Docker镜像 `ttttmr/wechat2rss` 发布，512M内存即可运行，部署时填写邮箱和许可证配置即可启动。

we-mp-rss 的优势在于提供了完整的Web管理界面，支持通过公众号名称直接搜索订阅，也支持MySQL和SQLite两种数据库。部署命令极简：

```bash
docker run -d --name we-mp-rss -p 8001:8001 -v ./data:/app/data \
  rachelos/we-mp-rss:latest
```

授权方式是用一个开通了公众号的微信扫码登录，系统模拟公众号后台视角抓取数据，**不需要手动抓Cookie或拼Header**。如果你没有已开通的公众号，注册一个个人号即可。

**关键注意**：微信风控是这类工具的共同挑战。Wechat2RSS的风控策略是触发限制后等待时间倍增（15分钟→30分钟→60分钟→…→6小时），解封后自动恢复。建议部署后先用2-3个公众号测试一周，观察稳定性后再批量添加。


## 二、多源信息聚合：n8n作为调度中枢

微信公众号RSS只解决了“公众号怎么变成RSS”的问题。要实现多源聚合、去重、结构化入库和每日自动更新，需要一个自动化调度框架。**n8n 是最合适的选择。**

n8n完全开源、支持自托管，有活跃的中文社区，且其Code节点支持JavaScript/Python，可以灵活处理数据清洗和格式转换。相比Zapier和Make，n8n自托管版本没有任务数量限制。

### 整体架构

```
┌─────────────────────────────────────────────────────┐
│                    n8n 工作流引擎                     │
│                                                     │
│  Schedule Trigger (每日定时)                          │
│       │                                             │
│       ├── RSS Feed Read (并行抓取所有源)              │
│       │   ├── 微信公众号RSS (Wechat2RSS/we-mp-rss)   │
│       │   ├── 国际新闻 RSS (BBC/Reuters/Guardian)    │
│       │   ├── AI资讯 RSS (Ars Technica/OpenAI Blog)  │
│       │   └── 教育 RSS (EdSurge/Education Week)      │
│       │                                             │
│       ├── Code节点 (去重 + 清洗 + 统一字段)           │
│       │                                             │
│       └── 入库节点                                   │
│           ├── PostgreSQL / MySQL                    │
│           └── (可选) 飞书多维表格 / Notion            │
└─────────────────────────────────────────────────────┘
```

### n8n中的关键处理步骤

**1. 并行抓取**：用多个RSS Feed Read节点并行拉取所有订阅源，每个源可独立配置更新频率和超时。

**2. 数据清洗与去重**：用Code节点处理，核心逻辑包括：
- 按文章URL或标题+发布时间做去重
- 过滤24小时内的新内容（避免重复入库）
- 去除HTML标签，提取纯文本摘要
- 统一字段结构：`{source, title, url, published_at, summary, category}`

**3. 入库**：n8n原生支持PostgreSQL、MySQL、Supabase等数据库节点。可以直接用PostgreSQL节点写入，也可以用HTTP Request节点调用你已有的数据库API。

n8n官方模板库中有一个“新闻聚合+关键词分析+数据库存储”的完整工作流，每6小时运行一次，从RSS、Google News和直接网页抓取三种来源收集数据，经过相关性过滤后存入双数据库系统。你可以直接导入这个模板作为起点，把默认的保险行业关键词替换为你关注的AI、教育、国际新闻关键词。


## 三、信息源配置：可直接使用的RSS列表

### 国际新闻

| 来源 | RSS地址 |
|------|---------|
| BBC World | `http://feeds.bbci.co.uk/news/world/rss.xml` |
| The Guardian | `https://www.theguardian.com/world/rss` |
| Reuters World | `https://www.reutersagency.com/feed/?best-topics=world` |
| Al Jazeera | `https://www.aljazeera.com/xml/rss/all.xml` |

以上源在国际新闻RSS聚合工具中属于预置的60+新闻源预设之一。

### AI资讯

| 来源 | RSS地址 |
|------|---------|
| OpenAI Blog | `https://openai.com/blog/rss.xml` |
| Anthropic Blog | `https://www.anthropic.com/blog/rss` |
| Ars Technica | `https://feeds.arstechnica.com/arstechnica/index` |
| MIT Tech Review | `https://www.technologyreview.com/feed/` |
| arXiv CS.AI | `http://export.arxiv.org/rss/cs.AI` |

以上均被收录在Apify的多源新闻抓取工具的预设源列表中。

### 教育资源

| 来源 | RSS地址 |
|------|---------|
| EdSurge | `https://www.edsurge.com/articles_rss` |
| Education Week | `https://www.edweek.org/arc/outboundfeeds/rss/` |
| eLearning Industry | `https://elearningindustry.com/feed` |

这些源在Apify的教育与EdTech情报管道中被作为“顶级教育RSS源”使用。

此外，GitHub上有一个持续维护的 **awesome-rss-feeds-list** 项目，聚合了2000个经过HTTP验证的活源，按“语言×分类”双维度组织，支持OPML一键导入，覆盖中文思考随笔、开发者工具、国际新闻等多个分类。你可以直接下载其OPML文件，在n8n中解析后批量导入订阅源。


## 四、每日自动更新的实现方式

n8n的 **Schedule Trigger** 节点支持Cron表达式，可以精确控制运行时间。例如，要每天早上7点自动运行：

```
0 7 * * *
```

也可以配合时区设置，确保按北京时间执行。

对于微信公众号RSS这一层，Wechat2RSS和we-mp-rss本身就内置了定时抓取机制——每个公众号每天自动检查1-2次。n8n只需要定时拉取这些RSS源即可，不需要额外控制抓取频率。


## 五、在你服务器上的完整部署路径

以下是在自有Linux服务器上的推荐部署顺序：

**第一步：部署微信公众号RSS工具（以we-mp-rss为例）**

```bash
# 拉取镜像并启动
docker run -d \
  --name we-mp-rss \
  -p 8001:8001 \
  -v /your/data/path:/app/data \
  --restart unless-stopped \
  rachelos/we-mp-rss:latest
```

启动后访问 `http://你的服务器IP:8001`，用微信扫码授权，然后搜索并订阅你关注的公众号。

**第二步：部署n8n**

```bash
docker run -d \
  --name n8n \
  -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n \
  --restart unless-stopped \
  n8nio/n8n
```

访问 `http://你的服务器IP:5678`，完成初始设置。

**第三步：在n8n中配置工作流**

1. 添加Schedule Trigger节点，设为每日定时（如早上7点）
2. 添加多个RSS Feed Read节点，分别填入：
   - `http://你的服务器IP:8001/feeds/MP_WXS_xxx.rss`（公众号RSS，具体地址在we-mp-rss的订阅管理页面获取）
   - 国际新闻、AI资讯、教育类RSS地址（见上文）
3. 添加Code节点做去重和字段统一
4. 添加PostgreSQL/MySQL节点写入数据库

**第四步：数据库建表参考**

```sql
CREATE TABLE daily_articles (
    id SERIAL PRIMARY KEY,
    source VARCHAR(100) NOT NULL,      -- 来源标识（公众号名/媒体名）
    source_type VARCHAR(20) NOT NULL,   -- wechat / news / ai / education
    title TEXT NOT NULL,
    url TEXT UNIQUE,
    summary TEXT,
    published_at TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT NOW(),
    category VARCHAR(50)                 -- 可选的分类标签
);

CREATE INDEX idx_published_at ON daily_articles(published_at DESC);
CREATE INDEX idx_source_type ON daily_articles(source_type);
```


## 六、稳定性建议

**关于微信风控**：这是最大的不确定因素。Wechat2RSS的风控等待机制会在解封后自动重置，部署在稳定IP的服务器上（避免频繁更换IP）可以降低触发频率。如果订阅量较大（超过20个公众号），建议先用少量号测试2-3周再逐步增加。

**关于RSS源失效**：RSS源的生命周期不可控，建议在n8n工作流中添加“抓取失败告警”——当某个源连续多次返回空结果时，通过企业微信机器人或邮件通知你。n8n原生支持错误处理和通知节点。

**关于数据入库**：如果不想维护数据库，也可以用n8n写入飞书多维表格，n8n有现成的飞书Bitable节点，配置简单且有中文文档。


## 七、备选方案对比

如果觉得n8n的运维成本较高，还有一个轻量级替代方案：**用Python脚本 + cron + GitHub Actions的思路自建**。有一个开源项目用TypeScript + GitHub Actions实现了全自动化AI资讯聚合，每2小时抓取一次，集成14+平台、70+ RSS和52个公众号，输出结构化JSON。但这个方案依赖GitHub Actions作为运行环境，与“在自有服务器上运行”的需求不完全匹配。

另一个纯服务器方案是**Python + feedparser + APScheduler + SQLAlchemy**，代码量不大（核心逻辑约200行），完全可控，但没有n8n的可视化调试和节点生态。如果你对Python更熟悉，这条路也完全可行。

综合来看，**we-mp-rss（或Wechat2RSS）+ n8n + PostgreSQL** 是当前在自有服务器上实现“公众号RSS为主、多源聚合、每日更新、结构化入库”的最成熟路径，部署一次后基本可以无人值守运行。


你遇到的问题核心在于：大多数微信公众号 RSS 工具（如 Wechat2RSS）的设计逻辑是**基于已知的公众号 ID（如 `biz` 或 `fakeid`）来生成 RSS**，而不是提供一个“按名字搜索公众号并返回文章列表”的通用接口。你实现了“获取执行文章”，说明你已经有了目标公众号的 ID，但缺少一个从“公众号名字”到“文章列表”的转换桥梁。

以下是几种可行的技术路径，按推荐程度排序。

---

## 方案一：使用 we-mp-rss 的内置搜索 API（最直接）

你之前部署的 we-mp-rss 本身就提供了按名称搜索公众号的 REST API，这正是你需要的功能。

**核心接口：**

| 接口 | 方法 | 说明 |
|------|------|------|
| `/mps/search/{kw}` | GET | 按关键词搜索公众号，返回匹配的账号列表（含 ID、名称、Logo） |
| `/mps/by_article?url={url}` | POST | 通过任意一篇文章链接反查公众号信息 |

**使用示例：**

假设你的 we-mp-rss 运行在 `http://localhost:8001`，想搜索“机器之心”：

```bash
# 1. 搜索公众号，获取其内部 ID
curl "http://localhost:8001/mps/search/机器之心?limit=5"

# 返回类似：
# [{"mp_id": "MP_WXS_xxxxx", "name": "机器之心", ...}]

# 2. 拿到 mp_id 后，其文章列表会通过 RSS 或 API 暴露
# 具体文章列表接口取决于你的版本，通常在 /feeds/{mp_id} 或类似路径
```

**关键前提**：这个搜索功能依赖 we-mp-rss 中维护的微信会话（通过扫码授权获得）。2026 年 7 月底微信曾收紧第三方接口，如果搜索接口返回空结果，说明你的会话可能已失效，需要重新扫码授权。另外需要注意，we-mp-rss 的搜索是“从微信公众号的超链接中搜索其他公众号”，本质上是利用微信自身的搜索能力，如果微信关闭了这个口子，搜索就会失败。

**如果搜索接口失效的降级方案**：用 `/mps/by_article` 接口。你只需要手动找到目标公众号的**任意一篇文章链接**，粘贴进去就能反查出公众号信息，然后订阅。这是比“按名字搜索”更稳定的方式，因为它不依赖微信的搜索接口。


## 方案二：使用 wechat-article-spider（专门的 CLI 工具）

`wechat-article-spider` 是一个专门为解决“按公众号名称爬取文章”而设计的命令行工具，功能覆盖非常完整。

**它支持的操作：**

```bash
# 1. 扫码登录（首次使用）
wechat-spider login

# 2. 按公众号名称搜索
wechat-spider search "极客公园"

# 3. 爬取指定公众号的文章（标题 + 链接）
wechat-spider scrape "极客公园" --pages 5 --days 30

# 4. 爬取文章并包含正文（Markdown 格式）
wechat-spider scrape "极客公园" --pages 5 --days 30 --content

# 5. 批量爬取多个公众号
wechat-spider batch "极客公园,爱范儿,机器之心" --pages 3 --days 7 --content

# 6. 输出到 CSV
wechat-spider scrape "极客公园" --pages 5 --days 30 --content --output result.csv
```

安装方式：`pip install git+https://github.com/qbu11/wechat-article-spider.git`。

它的登录凭证缓存约 4 天有效，支持通过 `export-login` 导出凭证字符串，方便在无头服务器上部署。这个工具通过微信公众平台 API 工作，需要 Chrome 浏览器环境用于扫码登录。


## 方案三：通过微信读书间接获取

微信读书收录了大量公众号，且提供了搜索入口。`wechat-search-weread` 这个 Agent Skill 可以通过微信读书的“搜一搜”功能搜索公众号文章，返回标题、公众号名、发布时间和 `mp.weixin.qq.com` 直链。

**但有两个重要局限：**

1. **搜索的是文章，不是公众号列表**。你可以在微信读书搜索框输入公众号名字，选择“公众号”分类找到目标账号，但这更多是手动操作。程序化地“按公众号名获取其全部文章列表”并不是微信读书 API 的原生能力。
2. **收录不全**。部分公众号在微信读书侧收录滞后，实测遇到过滞后半个多月的情况。微信读书的公众号搜索还有特殊前提：如果某个公众号从未有人在手机端点击“在微信读书中打开”，它可能根本不会出现在搜索结果中。

`weread-mp-fetcher` 这个工具的设计说明也明确写道：“**不搜公众号名字**。微信读书网页端搜不到公众号（实测无解），所以用文章链接代替”。这说明微信读书这条路在“按名称搜索公众号”这个环节上存在硬伤。


## 方案四：搜狗微信搜索

搜狗微信搜索（`weixin.sogou.com`）是另一个入口。基于它的爬虫接口 `WechatSogou` 可以搜索公众号和文章。Apify 上也提供了基于搜狗微信搜索的 Scraper，支持按关键词返回文章标题、公众号名、发布时间和链接。

**核心问题**：搜狗微信搜索的**反爬策略比较激进**，且搜索结果的质量和覆盖范围不如微信自身的搜索。另外，搜狗搜索的“公众号”分类结果和“文章”分类结果是分开的，你可能需要先搜到公众号，再进入其主页才能看到文章列表，这增加了程序化实现的复杂度。


## 综合建议

**如果你的 we-mp-rss 部署仍然可用**，优先使用它的 `/mps/search/{kw}` 接口。这是最贴合你现有架构的方案，不需要引入新工具。如果该接口因微信风控失效，退回到 `/mps/by_article`，用手动找一篇文章链接的方式反查公众号信息。

**如果你需要一个独立于 we-mp-rss 的专用爬取工具**，`wechat-article-spider` 是当前功能最完整的 CLI 选择。它原生支持“搜索公众号 → 获取文章列表 → 提取正文 → 导出 CSV”的完整链路，可以直接集成到你的 n8n 工作流中作为执行节点。

**不建议把微信读书作为主要方案**。它的定位是“阅读器”而非“爬虫工具”，在“按名称搜索公众号”这个具体需求上存在明确的技术限制，官方 API 也已废弃了文章列表接口。

**最终落地时，建议在你的 n8n 工作流中增加一个“公众号 ID 映射表”** ：首次通过搜索获取到目标公众号的 `mp_id` 后，将其名称和 ID 的对应关系存入数据库。后续每日更新时，n8n 直接读取映射表中的 ID 来拉取 RSS，不再依赖搜索接口。这样即使微信的搜索接口临时失效，你的日常更新流程也不会中断。