---
id: STEP-05
title: RSS 作为一等信息源（条件执行）
priority: P1（条件：D-V2-03）
depends: STEP-04
estimate: 1 人日
---

# STEP-05 RSS 一等信息源

## 目标（按推荐的折中裁决）
RSS feed 可以被订阅；只有指向 `mp.weixin.qq.com` 的条目进入清单与入库链，外链在发现层被过滤并计数；外链不再触发无意义的重试。

## 依据（02 §D-07、§D-04、§D-05）
- `source_resolver.py::ALLOWED_HOSTS = {"mp.weixin.qq.com"}`（`:24`）；`MalformedUrlError` 不在永久错误集合（`job_worker.py:100-107`、`kb.py:328-330`）。
- `Source.type` 仅 `wechat_oa`；RSS 标识被当作 URL 静默请求（`rss.py:97`、`:115-117`）。
- `docs/RSS订阅渠道.md` 预置外链源（新华网/阮一峰/V2EX…）。

## 前置裁决
D-V2-03。若裁决为"外链也要入库"，本 STEP 只做 S5.1/S5.2.1，外链入库另立 ADR（出站白名单、SSRF、通用抽取、合规）。

## 允许修改
`apps/api/app/api/v1/subscriptions.py`、`apps/api/app/services/subscription.py`（仅创建订阅分支）、`apps/api/app/providers/article_sources/rss.py`、`apps/api/app/services/manifest.py`（仅过滤计数）、`apps/api/app/services/job_worker.py`（仅 `_is_permanent_error`）、`apps/api/app/services/kb.py`（仅 `_resolve_with_retry` 的不重试集合）、`docs/RSS订阅渠道.md`、新测试；前端 `apps/web/app/subscriptions/**` 与 `apps/web/lib/api/subscriptions*.ts`（仅新增 RSS 订阅入口）
## 禁止修改
`source_resolver.py::ALLOWED_HOSTS`（扩大出站面需 ADR）。

## 原子任务

| 编号 | 类型 | 动作 | 验收命令 |
|---|---|---|---|
| S5.1.1 | 🔴🛠 | `POST /subscriptions` 接受 `{type:"rss", feedUrl}`：建 `Source(type="rss", external_id=sha256(feedUrl)[:32], url=feedUrl)` + `source_identifiers(feed_url)` | API 测试：201 + 源/标识各 1 行；重复订阅幂等 |
| S5.1.2 | 🛠 | RSS provider：identity 无 `feed_url` ⇒ 抛 `DiscoveryFailedError`；HTTP 失败 ⇒ 抛（不再静默返回空） | 单测 2 例 |
| S5.1.3 | 🛠 | 发现层过滤非微信域名，`report.filtered_offsite` 计数（STEP-07 指标消费） | 单测：混合 feed 3 条（1 微信 2 外链）⇒ 清单 1 行、filtered 2 |
| S5.2.1 | 🔴🛠 | `MalformedUrlError` 纳入 worker 永久错误与 kb 不重试集合 | 单测：外链 JobItem 一次即 FAILED、`retry_count==0` |
| S5.2.2 | 📄 | `docs/RSS订阅渠道.md` 外链预置源标"仅发现（V0.2.0 不入库）" | `grep -c "仅发现" docs/RSS订阅渠道.md` ≥ 1 |
| S5.3.1 | 🛠 | 前端订阅页新增"RSS 订阅"表单（feed URL），vitest 2 例（提交成功/后端 400 展示） | `pnpm run test:unit` 绿 |

## 回滚
`git revert`；已建 rss 源可保留（无调度器之外的消费者）。
