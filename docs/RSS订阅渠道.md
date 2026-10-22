# RSS 订阅发现渠道

## 概述

BotHot 支持通过 RSS feed 作为文章发现渠道。RSS 渠道可以：
- 解析 RSS 2.0 和 Atom 格式的 feed
- 将 feed item 映射为文章清单（与 RedFox/Dajiala 同形）
- 支持多 feed 聚合
- 零额外依赖（使用 httpx + xml.etree.ElementTree）

一条与"能不能用"无关但决定"能入库多少"的前提：RSS 是**发现**渠道，条目能否入库由裁决
D-V2-03 决定——只有正文链接落在白名单域名（`ALLOWED_HOSTS`，当前仅 `mp.weixin.qq.com`）的条目
会进入清单，其余在发现层就被滤掉（见下文「外链条目：仅发现，不入库」）。
预置的通用新闻/博客源因此**通常整批不入库**，这是设计后果，不是抓取失败。

## 外链条目：仅发现，不入库（STEP-09 S9.1.2）

| 事项 | 口径 |
|------|------|
| 判据来源 | `app/providers/source_resolver.normalize_article_url`（与入库主路径**同一个**谓词，provider 内不另存域名名单） |
| 滤掉的位置 | `RSSFeedProvider.query_work_list()`（新旧两个端口都经过它，不存在"绕过一条就进清单"的第二条路） |
| 计数出口 | `provider.filtered_offsite`（实例累计，跨多个 feed 相加）+ 一条 `RSS: … 滤掉 N 条不可入库链接` 的 warning 日志 |
| `total` 的含义 | **上游给了几行**（截断后、过滤前），不等于返回的行数——差额只能靠 `filtered_offsite` 或日志看见 |
| 无链接条目 | 只有 guid、没有 link 的 item 同样计入这一格（它没回答"去哪抓正文"） |

**为什么必须有一个数**：没有计数时，"这一轮滤掉 30 条"和"这个 feed 只有 3 条"在库里长得一模一样，
表现是本仓反复登记过的那族静默失败（P0-3、P-9 同族）。计数目前只到 provider 实例，
不在 `WorkListPage` 契约里（那个形状的归属在 STEP-08，本卡无权扩），所以跨进程/跨轮的汇总读不到——
已登记为待办，见 P 项。

**预置源按这条规则的实际后果**（未做活体抓取，下表按"条目链接落在哪个域"推断）：

| 类别 | 条目链接域名 | 是否入库 |
|------|--------------|----------|
| 微信公众号类（RSSHub / WeRSS / feeddd） | 取决于桥本身是否回链到 `mp.weixin.qq.com`——**未测** | 未知，须实测后回填 |
| 新闻类（新华网 / 人民网 / 中新网） | 本站域名 | ❌ 仅发现 |
| 科技博客 / 社交 / 国际科技 | 本站域名 | ❌ 仅发现 |

> 想让某个号的文章经 RSS 入库，要么该桥给出白名单域名的原文链接，要么把它当"热点/发现"用途看待，
> 不要按"订阅后库里会有文章"预期。

## 配置

在 `apps/api/.env` 中设置（容器内部署时走 compose 的 environment 注入，同一批键名）：

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

## 注册一个 RSS 源（STEP-09 S9.1.1）

```
POST /api/v1/sources  { "type": "rss", "feedUrl": "https://rsshub.example.com/wechat/mp/xxx", "name": "…" }
```

落库形状（`type` 省略 = `wechat_oa`，旧客户端形状不变）：

| 位置 | 值 | 为什么在这儿 |
|------|-----|--------------|
| `sources.type` | `rss` | `String(32)`，加一类源零迁移（AGENTS.md 关键约束 3） |
| `sources.url` | feed 地址原文 | 可读、可核对 |
| `sources.external_id` | `rss:` + feed 地址的 sha256 前 32 位 | 该列只有 128 字符且带 `uq_source_type_external`；截断 URL 会让两条 feed 撞成同一个源，留空会被唯一约束挡住第二个 RSS 源 |
| `source_identifiers(kind='feed_url')` | feed 地址原文 | **这才是路由认的那一格**：`select_channels` 按 `CHANNELS["rss"].required_identifier == "feed_url"` 筛源，注册时不补，这个源每轮都派不出渠道 |

标识行由 `IdentifierResolver.ensure_identifiers()` 写入（唯一写入口，撞 `(kind, value)` 唯一约束时告警不覆盖），
服务层不自己插表。重复注册按 `external_id` 落回同一行，幂等。

未知 `type` ⇒ `10005` 报错并点名可用类型（`wechat_oa` / `rss`），不回落到公众号的 biz 通道；
feed 地址形态非法（非 http(s)、无域名、超 512）同样在注册入口就报错——注册一个每轮都同步失败的源，
与当年收下形态非法的 biz 是同一个错误。

`identifier` 传的不是 URL 也不是配置里的别名时，provider 抛 `DiscoveryFailedError`（20004）**且一个请求都不发**：
旧实现末行 `return identifier` 会把 biz 串当地址去打，失败后被 `except HTTPError` 收成空清单，
读起来和"这个 feed 今天没发文"完全同形。

## 架构

```
RSS Feed → query_work_list() → _parse_feed() → _split_offsite() → _map_row() → ArticleManifest
                                 （白名单外的条目在这里被滤掉并计入 filtered_offsite）
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

# 按 URL 直接查询（示例域名不在白名单 ⇒ 返回 0 行、total>0，差额记进 filtered_offsite）
items, total = await provider.query_work_list("https://other.com/feed.xml", 1)

await provider.aclose()
```

## 漏进下游的畸形链接：永久失败，不重试（STEP-09 S9.2.1）

发现层滤一次，不等于后面不会再见到非法链接（清单可能来自别的渠道、旧行可能仍在队列里）。
`MalformedUrlError`（10006：非白名单域名 / 超 512 / 含控制字符）是**解析前**就能判定的静态事实，
重试同一个 URL 必然得到同一个结论，所以两处都按永久失败处理：

| 位置 | 之前的行为 | 现在的行为 |
|------|-----------|-----------|
| `kb._resolve_with_retry` | 退避重试满 `_RESOLVE_MAX_ATTEMPTS` | 立即抛出（与 20001/20003 同列） |
| `job_worker._is_permanent_error` | 不认 10006 ⇒ JobItem 从头再采若干次 | 认 10006 ⇒ 直接判终态 |

反向边界：网络类错误（超时、非 200）**仍然**走满重试预算——把 10006 收紧时顺手把别的也收紧，
会让一次上游抖动变成永久失败。这条边界由 `test_network_errors_are_still_retried` 钉住。

## 测试

```bash
cd apps/api
python -m pytest tests/test_rss_provider.py tests/test_rss_subscription.py -v
```

覆盖：RSS 2.0 解析、Atom 解析、字段映射、分页语义、feed URL 解析、HTTP 错误降级、预置源验证；
`test_rss_subscription.py` 另覆盖 STEP-09 的三条：未知标识不发请求、外链过滤与计数、RSS 源注册落标识。
