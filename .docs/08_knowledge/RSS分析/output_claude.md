非常好，信息已经足够。下面我为你整理一份完整、结构清晰的服务器自部署方案。

---

# 📡 服务器自部署 RSS 信息聚合系统方案

> 目标：稳定、每日自动更新、结构统一、全部在服务器上运行并入库。

---

## 🏗️ 总体架构

```
微信公众号来源          其他信息来源（国际/AI/教育）
      ↓                          ↓
  Wewe-RSS / WeRSS           RSSHub（自建）
      ↓                          ↓
         ───── RSS Feed 统一输出 ─────
                      ↓
              FreshRSS（聚合+调度+入库）
                      ↓
              数据库（SQLite / MySQL / PostgreSQL）
                      ↓
              （可选）AI 摘要 / 分类 / 推送
```

---

## 第一层：微信公众号 → RSS 转换

微信公众号本身不支持 RSS，因此诞生了一些专门的开源项目。以下是目前**存活率最高**的两个自建方案：

### ✅ 方案 A：Wewe-RSS（推荐首选）

Wewe-RSS 是免费、开源的微信公众号订阅方式，支持私有化部署、微信公众号 RSS 生成，**原理基于微信读书**，稳定性较高，配置比 RSSHub 简单。

- GitHub：`https://github.com/cooderl/wewe-rss`
- 部署方式：Docker Compose 一键启动
- 通过提交微信公众号分享链接来订阅，**注意：添加频率过高容易被封控**，等 24 小时可解封。

```yaml
# docker-compose.yml 示意
version: '3'
services:
  wewe-rss:
    image: cooderl/wewe-rss
    ports:
      - "4000:4000"
    volumes:
      - ./data:/app/data
```

### ✅ 方案 B：We-MP-RSS（更灵活）

We-MP-RSS 生成的 RSS 订阅源兼容多种常见 RSS 客户端；后端采用 Python + FastAPI，前端用 Vue 3；**数据库默认使用 SQLite，也支持 MySQL**，满足不同需求。同时支持定时任务，按设定间隔自动抓取最新文章（如每 10 分钟一次）。

- GitHub：`https://github.com/rachelos/we-mp-rss`
- 支持微信公众号转 Markdown、转 PDF、Webhook/API 接入，以及高效自动爬取解析正文、图片等核心内容。

---

## 第二层：其他信息来源 → RSS 标准化（RSSHub）

建议**自建 RSSHub 实例**（`docker run -d -p 1200:1200 diygod/rsshub`），公共实例不稳定。

自建后，可以接入以下分类 RSS 源：

| 分类 | 推荐源 |
|------|--------|
| 🌍 国际新闻 | BBC、Reuters、人民网国际、Al Jazeera |
| 🤖 AI 资讯 | Hacker News、ArXiv、MIT Tech Review、机器之心 |
| 📚 教育 | 知乎专栏、少数派、极客时间、Nature |
| 📈 实事/财经 | 虎嗅、界面新闻、经济学人 |

> 上述公众号类来源（经济学人、南方周末、虎嗅等）也可通过 RSSHub 的微信路由获取，与 Wewe-RSS 互补。

---

## 第三层：RSS 聚合器 + 自动入库（FreshRSS）

FreshRSS 是一个开源自托管 RSS 聚合器，提供快速、轻量、可定制的内容订阅方式。

**核心优势：**

- FreshRSS 是自托管 RSS 领域的标杆，功能包括搜索、过滤器、内置阅读器、主题、扩展、WebSub 支持等，与多种桌面/移动客户端 API 兼容。
- 安装简单，支持裸机和 Docker 部署；默认 SQLite 数据库，可切换 PostgreSQL 或 MySQL 以获得更好性能。
- 可流畅管理 10 万条以上文章而不影响速度。
- 支持追踪网站/播客/视频频道、直接在内部阅读文章、搜索与保存查询、抓取外部网站生成 Feed、基于过滤器生成新 Feed、OPML 导入导出。

```bash
# Docker 快速部署
docker run -d \
  --name freshrss \
  -p 8080:80 \
  -v freshrss_data:/var/www/FreshRSS/data \
  freshrss/freshrss
```

---

## 第四层（可选进阶）：AI 分类摘要聚合

可结合 AI 聚合工具，将话题按频道自动分类展示（科技 / AI / 财经 / 国际 / 社会 / 生活 / 健康 / 教育 / 其他），分类关键词可自定义，兼容 LM Studio 等本地 LLM 服务。

也可用 Python + `feedparser` + 本地/云端 LLM API 构建自定义管道：

```python
# 伪代码示意
import feedparser
feeds = ["http://your-wewe-rss/feed", "http://your-rsshub/huxiu"]
for f in feeds:
    d = feedparser.parse(f)
    for entry in d.entries:
        # 入库 + AI 摘要
        save_to_db(entry)
        summarize(entry.summary)
```

---

## 📊 方案对比总结

| 维度 | Wewe-RSS | We-MP-RSS | FreshRSS | RSSHub（自建） |
|------|----------|-----------|----------|----------------|
| 微信公众号支持 | ✅ 强 | ✅ 强 | ❌ | 部分路由 |
| 其他来源支持 | ❌ | ❌ | ✅ 统一聚合 | ✅ 生成 Feed |
| 数据库入库 | SQLite | SQLite/MySQL | SQLite/PG/MySQL | 无 |
| 自动定时更新 | ✅ | ✅ | ✅ Cron | ✅ |
| Docker 部署 | ✅ | ✅ | ✅ | ✅ |
| 稳定性 | 较高 | 较高 | 高 | 自建后稳定 |

---

## 🔧 推荐最终部署组合

```
Wewe-RSS（微信）+ RSSHub（其他来源）→ FreshRSS（聚合+入库）
                                         ↓
                                    MySQL / PostgreSQL
                                         ↓
                              （可选）Python 脚本 + AI 摘要
```

所有服务通过 **Docker Compose** 统一管理，Cron 定时触发 FreshRSS 抓取（默认每小时，可设为每天早上固定时间批量更新），数据统一落入你指定的数据库，结构高度统一。


这是一个核心难题，需要系统性地梳理清楚。以下是完整分析：

---

# 🔍 从公众号名字 → 获取文章列表：完整方案

## 🧩 问题本质：为什么"名字"拿不到列表？

微信公众号有三个层级的标识：

```
公众号中文名（不唯一，可重名）
    ↓ 搜索/搜狗
公众号英文 ID / wx_id（唯一）
    ↓ 解析
__biz（base64编码的唯一内部ID，所有接口实际用这个）
    ↓
文章列表 / RSS / 内容
```

**你卡在的是：已有名字 → 还缺 `__biz`（或公众号主页链接）这一步。**

---

## ✅ 方案一：搜狗微信搜索（最常用的非官方途径）

搜狗微信搜索引擎提供了通过公众号名称搜索并获取主页跳转链接的方式，请求地址形如：
`http://weixin.sogou.com/weixin?type=1&query=公众号名&ie=utf8`

通过解析搜索结果，可以根据 `nick_name`（中文名）获取公众号唯一内部 ID `__biz`（base64 编码），搜索结果 HTML 中的 `biz` 字段通常以 `==` 结尾，可通过正则提取。注意微信 URL 调用不能太频繁，否则会触发验证码。

### 完整流程代码（Python）

```python
import requests
import re
from bs4 import BeautifulSoup

def get_biz_from_name(account_name: str) -> str:
    """
    通过公众号名字，经搜狗搜索获取 __biz
    """
    search_url = "https://weixin.sogou.com/weixin"
    params = {
        "type": "1",        # type=1 搜公众号，type=2 搜文章
        "query": account_name,
        "ie": "utf8"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    resp = requests.get(search_url, params=params, headers=headers, timeout=10)
    soup = BeautifulSoup(resp.text, "html.parser")

    # 提取公众号主页链接，属性 uigs 包含 account_name
    a_tag = soup.find("a", attrs={"uigs": re.compile(r"account_name")})
    if not a_tag:
        return None

    profile_url = a_tag["href"]  # 形如 https://mp.weixin.qq.com/profile?...
    print(f"公众号主页 URL: {profile_url}")

    # 从 profile 页面中提取 __biz
    resp2 = requests.get(profile_url, headers=headers, timeout=10)
    biz_match = re.search(r'__biz=([\w=+/]+)', resp2.text)
    if biz_match:
        return biz_match.group(1)
    return None


# 使用示例
biz = get_biz_from_name("人民日报")
print(f"__biz = {biz}")
```

---

## ✅ 方案二：用 `__biz` 请求文章列表（抓包接口）

拿到 `__biz` 之后，文章列表通过以下接口获取（需要 Cookie/Token，**这是关键限制**）：

```
https://mp.weixin.qq.com/mp/profile_ext
  ?action=getmsg
  &__biz=MjM5MTA1MDU2MA==   ← 公众号唯一ID
  &f=json
  &offset=0                  ← 分页偏移
  &count=10                  ← 每页数量
  &is_ok=1
```

> ⚠️ **此接口需要 `Cookie`（微信登录态）**，直接裸请求会被拒绝。

### 解决 Cookie 的两种方式：

| 方式 | 原理 | 稳定性 |
|------|------|--------|
| 手动抓包获取 Cookie | 用 Charles/Burp 抓微信请求，粘贴到代码 | 2~7天失效，需手动续期 |
| **微信读书接口（推荐）** | wewe-rss 采用此方式，稳定性更高 | 相对更稳定 |

---

## ✅ 方案三：借助 Wewe-RSS 的内部 API（最稳定、推荐）

wewe-rss 通过模拟用户登录微信读书，利用微信读书的接口来获取已关注公众号的文章列表和内容，稳定性主要依赖于微信读书相关接口。

既然你已经自建了 wewe-rss，可以直接**调用它暴露的本地 API**，而不是自己重写采集逻辑：

wewe-rss 要求用户提供该公众号下的**一篇文章的短链接**（形如 `https://mp.weixin.qq.com/s/xxxxxx`），系统会在后台自动解析该公众号的 ID，完成订阅后即可获取 RSS 链接。

```python
# 通过 wewe-rss 本地 API 获取已订阅公众号文章列表
import requests

WEWE_RSS_BASE = "http://localhost:4000"
AUTH_CODE = "your_auth_code"

# 获取所有公众号源
feeds = requests.get(
    f"{WEWE_RSS_BASE}/api/feeds",
    headers={"Authorization": AUTH_CODE}
).json()

# 获取指定公众号文章列表
for feed in feeds["data"]:
    if feed["title"] == "目标公众号名":
        feed_id = feed["id"]  # 形如 MP_WXS_xxxxxxxxxx
        articles = requests.get(
            f"{WEWE_RSS_BASE}/api/feeds/{feed_id}/articles",
            headers={"Authorization": AUTH_CODE}
        ).json()
        print(articles)
```

---

## ✅ 方案四：wechat-download-api（最完整的开源方案）

这是一款完全开源的微信公众号文章获取、RSS 订阅 API 服务，支持整号文章一键导出 7 种格式（Markdown/HTML/Word/PDF/EPUB/Excel/JSON）、IP 代理池反风控、MCP 接入各种 AI Agent 工具。

GitHub：`tmwgsicp/wechat-download-api`，支持**直接传入公众号名称**批量获取文章列表，非常符合你的需求。

---

## 🔁 整体决策流程图

```
输入：公众号中文名
        ↓
   搜狗搜索接口
   type=1&query=名字
        ↓
   解析出 profile URL
        ↓
   提取 __biz
        ↓
   ┌─────────────────────────────────────┐
   │  有微信登录Cookie？                  │
   │  ├─ 是 → 直接调 profile_ext 接口     │
   │  └─ 否 → 走微信读书（wewe-rss方式）  │
   └─────────────────────────────────────┘
        ↓
   获取文章列表（JSON / RSS）
        ↓
   入库（MySQL / PostgreSQL）
```

---

## ⚠️ 关键注意事项

| 问题 | 说明 |
|------|------|
| **中文名不唯一** | 搜索结果可能多个公众号同名，建议用英文 ID 或先人工确认 `__biz` |
| **搜狗验证码** | 请求过频会触发滑块验证码，建议每次请求间隔 3~5s，或接入代理池 |
| **Cookie 时效** | 微信读书的登录状态（session）通常在 2 到 3 天后会过期，需要定期重新扫码 |
| **仅限已关注号** | 微信读书路线只能获取**已在该账号中关注**的公众号文章 |
| **历史文章限制** | 微信接口只返回最近几十篇，历史全量抓取需分页循环+限速 |