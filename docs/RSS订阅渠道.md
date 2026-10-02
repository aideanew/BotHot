# RSS 订阅发现渠道

## 概述

BotHot 支持通过 RSS feed 作为文章发现渠道。RSS 渠道可以：
- 解析 RSS 2.0 和 Atom 格式的 feed
- 将 feed item 映射为文章清单（与 RedFox/Dajiala 同形）
- 支持多 feed 聚合
- 零额外依赖（使用 httpx + xml.etree.ElementTree）

## 配置

在 `backend/.env` 中设置：

```bash
# 启用 RSS 渠道，配置 feed URL 列表（逗号分隔）
DISCOVERY_RSS_FEEDS=https://rsshub.app/wechat/ce/CeBaoShi,https://feeds.example.com/tech.xml

# 支持别名格式（alias:url）
DISCOVERY_RSS_FEEDS=tech:https://feeds.example.com/tech.xml,news:https://feeds.example.com/news.xml

# RSS feed 抓取超时（秒，默认 20）
DISCOVERY_RSS_TIMEOUT=20.0

# 将 RSS 加入发现渠道白名单
DISCOVERY_CHANNELS=rss,dajiala

# 设置 RSS 为默认渠道（可选）
DISCOVERY_DEFAULT_CHANNEL=rss
```

## 预置免费 RSS 源

系统预置了 15+ 个免费 RSS 源，涵盖微信公众号、科技博客、新闻、社交等类别：

### 微信公众号类
| 名称 | URL | 说明 |
|------|-----|------|
| RSSHub 官方 | https://rsshub.app/wechat/ce/CeBaoShi | RSSHub 官方实例 |
| RSSHub 1 | https://rsshub.rssforever.com/wechat/ce/CeBaoShi | 公共实例 |
| RSSHub 2 | https://rss.shab.fun/wechat/ce/CeBaoShi | 公共实例 |
| WeRSS | https://werss.app/feed/all | 公众号 RSS 服务 |
| feeddd | https://feeddd.org/feeds/all | 公众号全文 RSS |

### 新闻类
| 名称 | URL | 说明 |
|------|-----|------|
| 新华网-时政 | http://www.xinhuanet.com/politics/news_politics.xml | 新华网时政频道 |
| 人民网-国际 | http://www.people.com.cn/rss/world.xml | 人民网国际频道 |
| 中国新闻网 | https://www.chinanews.com.cn/rss/scroll-news.xml | 滚动新闻 |

### 科技博客
| 名称 | URL | 说明 |
|------|-----|------|
| 阮一峰博客 | https://www.ruanyifeng.com/blog/atom.xml | 阮一峰网络日志 |
| 奇客Solidot | https://www.solidot.org/index.rss | 科技新闻 |
| V2EX | https://www.v2ex.com/index.xml | 最新话题 |

### 社交类
| 名称 | URL | 说明 |
|------|-----|------|
| 知乎日报 | https://rsshub.app/zhihu/daily | 知乎日报 |
| 哔哩哔哩-热门 | https://rsshub.app/bilibili/hot-search | B站热搜 |

### 国际科技
| 名称 | URL | 说明 |
|------|-----|------|
| Hacker News | https://hnrss.org/frontpage | HN 头条 |
| TechCrunch | https://techcrunch.com/feed/ | 科技新闻 |

## 架构

```
RSS Feed → RSSFeedProvider.query_work_list() → _parse_feed() → _map_row() → ArticleManifest
```

- `RSSFeedProvider` 实现 `WorkListProvider` 协议
- `_parse_feed()` 解析 RSS 2.0 / Atom XML
- 字段映射对齐 `manifest._map_row` 的别名（link/url, title, pubDate/publishTime, guid/id）
- RSS 不分页：page=1 返回全部 item，page>1 返回空

## 使用示例

```python
from app.providers.article_sources.rss import RSSFeedConfig, RSSFeedProvider

feeds = [
    RSSFeedConfig(url="https://rsshub.app/wechat/ce/CeBaoShi", alias="tech"),
    RSSFeedConfig(url="https://feeds.example.com/news.xml", alias="news"),
]
provider = RSSFeedProvider(feeds=feeds)

# 按 alias 查询
items, total = await provider.query_work_list("tech", 1)

# 按 URL 直接查询
items, total = await provider.query_work_list("https://other.com/feed.xml", 1)

await provider.aclose()
```

## 测试

```bash
cd backend
python -m pytest tests/test_rss_provider.py -v
```

覆盖：RSS 2.0 解析、Atom 解析、字段映射、分页语义、feed URL 解析、HTTP 错误降级、预置源验证。
