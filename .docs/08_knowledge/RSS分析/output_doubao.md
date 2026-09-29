# 一、核心痛点解决：已知公众号名称，如何获取文章列表
微信公众号没有公开的官方API，**所有获取方式的核心逻辑都是：先通过公众号名称拿到唯一标识 `__biz`（也叫 fakeid），再用 biz 调用接口拉取文章列表**。你当前只能获取单篇文章、拿不到列表，本质是缺少「名称 → biz → 列表」的完整链路。以下是4种可落地的方案，按稳定性排序：

## 方法1：微信公众平台后台接口（最稳定，推荐）
### 原理
利用微信公众号后台「插入超链接」的官方搜索能力，通过公众号名称搜索得到对应 biz，再调用官方文章列表接口批量获取数据。**需要你有一个正常的个人/企业公众号（免费即可）**。

### 操作步骤
1. 登录 [微信公众平台](https://mp.weixin.qq.com/)，进入「新建群发」→「图文消息」编辑页，点击工具栏的「超链接」按钮。
2. 在弹窗中输入目标公众号名称，按 F12 打开开发者工具抓包，可得到两个核心接口：
   - **公众号搜索接口**：`[https://mp.weixin.qq.com/cgi-bin/searchbiz](https://mp.weixin.qq.com/cgi-bin/searchbiz)`，传入公众号名称，返回包含 `fakeid`（即 __biz）的公众号信息。
   - **文章列表接口**：`[https://mp.weixin.qq.com/cgi-bin/appmsg](https://mp.weixin.qq.com/cgi-bin/appmsg)`，传入 biz 即可返回该公众号的文章列表（标题、原文链接、发布时间、封面图等字段）。
3. 用代码模拟请求，携带登录后的 Cookie 和 Token 即可持续调用。

### Python 示例代码
```python
import requests

# 替换为你自己的公众号后台Cookie和Token
COOKIE = "你的登录Cookie"
TOKEN = "你的接口Token"
headers = {"Cookie": COOKIE}

# 1. 通过公众号名称获取biz
def get_biz_by_name(official_name):
    url = "[https://mp.weixin.qq.com/cgi-bin/searchbiz](https://mp.weixin.qq.com/cgi-bin/searchbiz)"
    params = {
        "action": "search_biz",
        "begin": 0,
        "count": 5,
        "query": official_name,
        "token": TOKEN,
        "lang": "zh_CN",
        "f": "json",
        "ajax": 1
    }
    resp = requests.get(url, params=params, headers=headers).json()
    return resp["list"][0]["fakeid"]

# 2. 通过biz获取文章列表
def get_article_list(biz, count=10):
    url = "[https://mp.weixin.qq.com/cgi-bin/appmsg](https://mp.weixin.qq.com/cgi-bin/appmsg)"
    params = {
        "action": "list_ex",
        "begin": 0,
        "count": count,
        "fakeid": biz,
        "type": 9,
        "token": TOKEN,
        "lang": "zh_CN",
        "f": "json",
        "ajax": 1
    }
    resp = requests.get(url, params=params, headers=headers).json()
    return resp["app_msg_list"]

# 调用示例
biz = get_biz_by_name("目标公众号名称")
articles = get_article_list(biz, count=10)
for item in articles:
    print(item["title"], item["link"], item["create_time"])
```

> 注意：Cookie 和 Token 有效期约 1~3 天，需定时更新；接口有官方频率限制，建议单公众号请求间隔 ≥ 10 秒。

## 方法2：开源工具库 wechatarticles（快速实现）
### 特点
封装了上述公众号后台接口，无需自己抓包分析，直接通过「公众号昵称」就能批量获取 biz 和文章列表，开箱即用。

### 使用方式
```bash
pip install wechatarticles
```

```python
from wechatarticles import AccountBiz, ArticlesUrls

COOKIE = "你的公众号后台Cookie"

# 1. 批量通过名称获取biz
ab = AccountBiz(COOKIE)
biz_result = ab.office(["公众号1", "公众号2"])
biz = biz_result[0]["biz"]

# 2. 获取最新文章列表
articles = ArticlesUrls(COOKIE)
article_list = articles.latest_articles(biz=biz, count=10)
print(article_list)
```

> 项目地址：[wechat_articles_spider](https://github.com/wnma3mz/wechat_articles_spider)

## 方法3：第三方付费API（省心免维护）
如果不想维护登录态、处理反爬策略，可以直接使用商业聚合接口，传入公众号名称即可返回结构化文章列表，例如：
- **Just One API**：支持公众号名称/文章URL查询，返回全文、阅读量等结构化数据
- 天行数据、天聚数行等平台均有封装好的微信公众号文章接口

优势：无需维护 Cookie 和反爬，稳定性高；劣势：有使用成本，数据经过第三方。

## 方法4：历史消息页解析（备用，无需公众号）
如果没有自己的公众号，可先通过手机微信获取目标公众号的历史消息链接：
1. 手机微信打开公众号主页 → 「全部消息」→ 右上角「...」→「复制链接」
2. 链接中 `__biz=` 后的字符串即为该公众号的 biz 值
3. 拿到 biz 后，可模拟微信客户端 UA 访问历史消息页，解析提取文章列表

> 该方式稳定性较差，容易被微信风控，仅作为备用方案。

---

# 二、完整自托管RSS聚合+入库方案
针对你「公众号为主+多渠道信息、每日更新、结构统一、服务器运行、本地入库」的需求，以下3套方案按落地难度从低到高排序：

## 方案一：开箱即用组合方案（推荐，稳定性最高）
### 整体架构
`微信公众号转RSS服务 + 通用RSS聚合器 + 结构化数据库`

### 1. 微信公众号转RSS层
二选一，均支持 Docker 部署在你的服务器上，自动把公众号转为标准 RSS 源：
- **Wechat2RSS**：成熟稳定的商业级私有部署方案，平均6小时更新延迟，支持全文输出、图片代理、公众号自动跟随迁移，Docker 一键部署。
- **WeRSS (we-mp-rss)**：完全开源免费，支持公众号转RSS、转Markdown，内置 SQLite/MySQL 存储，资源占用低。
  一键部署命令：
  ```bash
  docker run -d --name we-mp-rss -p 8001:8001 -v ./data:/app/data ghcr.io/rachelos/we-mp-rss:latest
  ```

### 2. 多渠道RSS聚合层（统一结构）
选用自托管 RSS 聚合器，统一管理公众号 + 国际/实事/AI/教育等所有外部 RSS 源，输出标准化结构：
- **Miniflux**：Go 语言开发，轻量高性能，占用资源极低，原生支持 PostgreSQL，可配置每日定时更新，内置全文搜索和API。
- **FreshRSS**：功能更丰富，支持多用户、插件扩展，兼容 SQLite/MySQL/PostgreSQL，自定义更新粒度更灵活。

### 3. 数据入库
- **轻量方式**：直接复用聚合器自带的 PostgreSQL/MySQL 数据库，表结构已经标准化（标题、链接、发布时间、来源、内容、分类），直接对接你的业务查询即可。
- **自定义入库**：编写 Python 定时脚本，通过聚合器 API 或直接解析 RSS XML，按你的业务字段清洗后写入自有数据库，支持去重、分类打标。

### 4. 定时更新机制
- 公众号转RSS服务默认 6 小时内检测更新，满足每日更新要求。
- 聚合器可配置为**每日固定时间全量刷新**（如每天凌晨 6 点），白天可设置每 6 小时增量检查。

## 方案二：全自研可控方案（100%自定义）
### 整体架构
`定时采集任务 + 数据清洗统一层 + 业务数据库 + RSS输出层`

### 实现逻辑
1. **采集层**：
   - 公众号：基于上述 `wechatarticles` 库，每日定时抓取指定公众号的文章列表 + 正文内容。
   - 其他渠道：用 `feedparser` 库抓取国际新闻、AI、教育等官方 RSS 源。
2. **清洗统一层**：将所有来源的内容归一化为统一字段结构，示例：

| 字段 | 类型 | 说明 |
|---|---|---|
| article_id | string | 唯一标识（原文URL哈希） |
| title | string | 文章标题 |
| summary | string | 内容摘要 |
| content | text | 正文内容 |
| publish_time | datetime | 发布时间 |
| source | string | 来源名称（公众号/媒体名） |
| category | string | 分类（实事/AI/教育等） |
| url | string | 原文链接 |

3. **存储层**：写入 PostgreSQL/MySQL，建立 URL 唯一索引实现自动去重。
4. **调度层**：通过 Linux Crontab 或 Celery 定时执行，每日凌晨全量更新，白天每 6 小时增量检查。
5. **输出层**：可按需生成统一格式的 RSS Feed，或提供 REST API 供业务调用。

### 优势
字段、更新频率、存储结构完全可控；劣势：需要自行处理反爬、Cookie 维护、异常重试等问题。

## 方案三：RSSHub 中间件方案（扩展能力强）
### 整体架构
`自建RSSHub + RSS聚合器 + 入库脚本`

### 说明
- RSSHub 是开源的通用 RSS 生成器，支持上千个网站生成 RSS，其中包含微信公众号路由（依赖搜狗微信数据源）。
- 你可以在服务器上自建 RSSHub，配置公众号名称生成对应 RSS 源，再叠加其他官方 RSS 源，统一导入 FreshRSS/Miniflux 聚合，最后同步入库。

> 注意：RSSHub 的微信公众号路由依赖搜狗搜索接口，稳定性不如专用转RSS服务，适合作为补充渠道。

---

# 三、落地建议
1. **先解决文章列表问题**：如果你有公众号，直接用**方法1 + wechatarticles 库**，1 小时内就能实现「名称 → 文章列表」的批量获取；如果没有公众号，可先注册一个免费的个人订阅号，或短期使用第三方API过渡。
2. **整体架构优先选方案一**：`WeRSS + Miniflux` 组合，Docker Compose 半天就能部署完成，自带数据库，天然满足稳定、每日更新、结构统一的要求，无需重复造轮子。
3. **入库策略**：优先直接复用 Miniflux 的 PostgreSQL 数据库，表结构已经标准化；如果需要对接自有业务系统，再写一个轻量同步脚本即可。

需要我给你一份 WeRSS + Miniflux 的 Docker Compose 一键部署模板吗？



# 一、核心痛点解决：已知公众号名称，如何获取文章列表
微信公众号没有公开的官方API，**所有获取方式的核心逻辑都是：先通过公众号名称拿到唯一标识 `__biz`（也叫 fakeid），再用 biz 调用接口拉取文章列表**。你当前只能获取单篇文章、拿不到列表，本质是缺少「名称 → biz → 列表」的完整链路。以下是4种可落地的方案，按稳定性排序：

## 方法1：微信公众平台后台接口（最稳定，推荐）
### 原理
利用微信公众号后台「插入超链接」的官方搜索能力，通过公众号名称搜索得到对应 biz，再调用官方文章列表接口批量获取数据。**需要你有一个正常的个人/企业公众号（免费即可）**。

### 操作步骤
1. 登录 [微信公众平台](https://mp.weixin.qq.com/)，进入「新建群发」→「图文消息」编辑页，点击工具栏的「超链接」按钮。
2. 在弹窗中输入目标公众号名称，按 F12 打开开发者工具抓包，可得到两个核心接口：
   - **公众号搜索接口**：`[https://mp.weixin.qq.com/cgi-bin/searchbiz](https://mp.weixin.qq.com/cgi-bin/searchbiz)`，传入公众号名称，返回包含 `fakeid`（即 __biz）的公众号信息。
   - **文章列表接口**：`[https://mp.weixin.qq.com/cgi-bin/appmsg](https://mp.weixin.qq.com/cgi-bin/appmsg)`，传入 biz 即可返回该公众号的文章列表（标题、原文链接、发布时间、封面图等字段）。
3. 用代码模拟请求，携带登录后的 Cookie 和 Token 即可持续调用。

### Python 示例代码
```python
import requests

# 替换为你自己的公众号后台Cookie和Token
COOKIE = "你的登录Cookie"
TOKEN = "你的接口Token"
headers = {"Cookie": COOKIE}

# 1. 通过公众号名称获取biz
def get_biz_by_name(official_name):
    url = "[https://mp.weixin.qq.com/cgi-bin/searchbiz](https://mp.weixin.qq.com/cgi-bin/searchbiz)"
    params = {
        "action": "search_biz",
        "begin": 0,
        "count": 5,
        "query": official_name,
        "token": TOKEN,
        "lang": "zh_CN",
        "f": "json",
        "ajax": 1
    }
    resp = requests.get(url, params=params, headers=headers).json()
    return resp["list"][0]["fakeid"]

# 2. 通过biz获取文章列表
def get_article_list(biz, count=10):
    url = "[https://mp.weixin.qq.com/cgi-bin/appmsg](https://mp.weixin.qq.com/cgi-bin/appmsg)"
    params = {
        "action": "list_ex",
        "begin": 0,
        "count": count,
        "fakeid": biz,
        "type": 9,
        "token": TOKEN,
        "lang": "zh_CN",
        "f": "json",
        "ajax": 1
    }
    resp = requests.get(url, params=params, headers=headers).json()
    return resp["app_msg_list"]

# 调用示例
biz = get_biz_by_name("目标公众号名称")
articles = get_article_list(biz, count=10)
for item in articles:
    print(item["title"], item["link"], item["create_time"])
```

> 注意：Cookie 和 Token 有效期约 1~3 天，需定时更新；接口有官方频率限制，建议单公众号请求间隔 ≥ 10 秒。

## 方法2：开源工具库 wechatarticles（快速实现）
### 特点
封装了上述公众号后台接口，无需自己抓包分析，直接通过「公众号昵称」就能批量获取 biz 和文章列表，开箱即用。

### 使用方式
```bash
pip install wechatarticles
```

```python
from wechatarticles import AccountBiz, ArticlesUrls

COOKIE = "你的公众号后台Cookie"

# 1. 批量通过名称获取biz
ab = AccountBiz(COOKIE)
biz_result = ab.office(["公众号1", "公众号2"])
biz = biz_result[0]["biz"]

# 2. 获取最新文章列表
articles = ArticlesUrls(COOKIE)
article_list = articles.latest_articles(biz=biz, count=10)
print(article_list)
```

> 项目地址：[wechat_articles_spider](https://github.com/wnma3mz/wechat_articles_spider)

## 方法3：第三方付费API（省心免维护）
如果不想维护登录态、处理反爬策略，可以直接使用商业聚合接口，传入公众号名称即可返回结构化文章列表，例如：
- **Just One API**：支持公众号名称/文章URL查询，返回全文、阅读量等结构化数据
- 天行数据、天聚数行等平台均有封装好的微信公众号文章接口

优势：无需维护 Cookie 和反爬，稳定性高；劣势：有使用成本，数据经过第三方。

## 方法4：历史消息页解析（备用，无需公众号）
如果没有自己的公众号，可先通过手机微信获取目标公众号的历史消息链接：
1. 手机微信打开公众号主页 → 「全部消息」→ 右上角「...」→「复制链接」
2. 链接中 `__biz=` 后的字符串即为该公众号的 biz 值
3. 拿到 biz 后，可模拟微信客户端 UA 访问历史消息页，解析提取文章列表

> 该方式稳定性较差，容易被微信风控，仅作为备用方案。

---

# 二、完整自托管RSS聚合+入库方案
针对你「公众号为主+多渠道信息、每日更新、结构统一、服务器运行、本地入库」的需求，以下3套方案按落地难度从低到高排序：

## 方案一：开箱即用组合方案（推荐，稳定性最高）
### 整体架构
`微信公众号转RSS服务 + 通用RSS聚合器 + 结构化数据库`

### 1. 微信公众号转RSS层
二选一，均支持 Docker 部署在你的服务器上，自动把公众号转为标准 RSS 源：
- **Wechat2RSS**：成熟稳定的商业级私有部署方案，平均6小时更新延迟，支持全文输出、图片代理、公众号自动跟随迁移，Docker 一键部署。
- **WeRSS (we-mp-rss)**：完全开源免费，支持公众号转RSS、转Markdown，内置 SQLite/MySQL 存储，资源占用低。
  一键部署命令：
  ```bash
  docker run -d --name we-mp-rss -p 8001:8001 -v ./data:/app/data ghcr.io/rachelos/we-mp-rss:latest
  ```

### 2. 多渠道RSS聚合层（统一结构）
选用自托管 RSS 聚合器，统一管理公众号 + 国际/实事/AI/教育等所有外部 RSS 源，输出标准化结构：
- **Miniflux**：Go 语言开发，轻量高性能，占用资源极低，原生支持 PostgreSQL，可配置每日定时更新，内置全文搜索和API。
- **FreshRSS**：功能更丰富，支持多用户、插件扩展，兼容 SQLite/MySQL/PostgreSQL，自定义更新粒度更灵活。

### 3. 数据入库
- **轻量方式**：直接复用聚合器自带的 PostgreSQL/MySQL 数据库，表结构已经标准化（标题、链接、发布时间、来源、内容、分类），直接对接你的业务查询即可。
- **自定义入库**：编写 Python 定时脚本，通过聚合器 API 或直接解析 RSS XML，按你的业务字段清洗后写入自有数据库，支持去重、分类打标。

### 4. 定时更新机制
- 公众号转RSS服务默认 6 小时内检测更新，满足每日更新要求。
- 聚合器可配置为**每日固定时间全量刷新**（如每天凌晨 6 点），白天可设置每 6 小时增量检查。

## 方案二：全自研可控方案（100%自定义）
### 整体架构
`定时采集任务 + 数据清洗统一层 + 业务数据库 + RSS输出层`

### 实现逻辑
1. **采集层**：
   - 公众号：基于上述 `wechatarticles` 库，每日定时抓取指定公众号的文章列表 + 正文内容。
   - 其他渠道：用 `feedparser` 库抓取国际新闻、AI、教育等官方 RSS 源。
2. **清洗统一层**：将所有来源的内容归一化为统一字段结构，示例：

| 字段 | 类型 | 说明 |
|---|---|---|
| article_id | string | 唯一标识（原文URL哈希） |
| title | string | 文章标题 |
| summary | string | 内容摘要 |
| content | text | 正文内容 |
| publish_time | datetime | 发布时间 |
| source | string | 来源名称（公众号/媒体名） |
| category | string | 分类（实事/AI/教育等） |
| url | string | 原文链接 |

3. **存储层**：写入 PostgreSQL/MySQL，建立 URL 唯一索引实现自动去重。
4. **调度层**：通过 Linux Crontab 或 Celery 定时执行，每日凌晨全量更新，白天每 6 小时增量检查。
5. **输出层**：可按需生成统一格式的 RSS Feed，或提供 REST API 供业务调用。

### 优势
字段、更新频率、存储结构完全可控；劣势：需要自行处理反爬、Cookie 维护、异常重试等问题。

## 方案三：RSSHub 中间件方案（扩展能力强）
### 整体架构
`自建RSSHub + RSS聚合器 + 入库脚本`

### 说明
- RSSHub 是开源的通用 RSS 生成器，支持上千个网站生成 RSS，其中包含微信公众号路由（依赖搜狗微信数据源）。
- 你可以在服务器上自建 RSSHub，配置公众号名称生成对应 RSS 源，再叠加其他官方 RSS 源，统一导入 FreshRSS/Miniflux 聚合，最后同步入库。

> 注意：RSSHub 的微信公众号路由依赖搜狗搜索接口，稳定性不如专用转RSS服务，适合作为补充渠道。

---

# 三、落地建议
1. **先解决文章列表问题**：如果你有公众号，直接用**方法1 + wechatarticles 库**，1 小时内就能实现「名称 → 文章列表」的批量获取；如果没有公众号，可先注册一个免费的个人订阅号，或短期使用第三方API过渡。
2. **整体架构优先选方案一**：`WeRSS + Miniflux` 组合，Docker Compose 半天就能部署完成，自带数据库，天然满足稳定、每日更新、结构统一的要求，无需重复造轮子。
3. **入库策略**：优先直接复用 Miniflux 的 PostgreSQL 数据库，表结构已经标准化；如果需要对接自有业务系统，再写一个轻量同步脚本即可。

需要我给你一份 WeRSS + Miniflux 的 Docker Compose 一键部署模板吗？