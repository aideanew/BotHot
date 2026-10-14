---
id: GLOSSARY
type: reference
title: BotHot 术语表
status: active
owner: governance
created: 2026-09-29
updated: 2026-09-29
---

# BotHot 术语表

| 术语 | 英文 | 含义 |
|---|---|---|
| BotHot | — | 本项目名，Bot + Hot，寓意多渠道机器人推送 + 热点聚簇 |
| 知识空间 | Knowledge Space | 隔离的知识库容器，1:1 映射 LangBot KB |
| 内容资产 | Content Asset | 入库后的文章实体，含 Markdown 正文 + 元数据 |
| 知识引擎 | Knowledge Engine | RAG 检索后端，可插拔（LangBot/Aidean/RedFox/builtin） |
| EnginePort | — | 引擎抽象接口，新引擎实现此接口即可接入 |
| 渠道 | Bot Channel | 推送目标配置（飞书/钉钉/企微/ClawBot/Webhook/站内） |
| PushProvider | — | 推送适配器接口，每种渠道一个实现 |
| 推送任务 | Push Task | 定时/事件触发的推送计划，含 Cron 表达式 |
| 推送日志 | Push Log | 每次推送的投递记录（状态/响应/重试） |
| 热点聚簇 | Hot Topic Clustering | 多篇文章按主题聚合为热点事件 |
| 热度评分 | Hot Score | 48h 独立来源数加权 + 24h 时间衰减 |
| Feed 流 | Feed Stream | 信息流，按热度排序，支持类型/分类筛选 |
| 每日日报 | Daily Report | TOP 10 热点 + LLM 摘要，Markdown 格式 |
| SSO | Single Sign-On | 统一认证，通过主平台 OIDC 接入 |
| 身份锚点 | Identity Anchor | users.sub 字段，SSO 用户唯一标识 |
| 订阅 | Subscription | 订阅一个公众号的全部文章 |
| Manifest Diff | — | 文章清单差异比对，实现增量同步 |
| 水位 | Water Level | 已同步的最新文章标记，避免重复拉取 |
| 固定时点锚 | Fixed Anchor | 订阅同步策略：固定时点拉取 |
| 滑动窗口 | Sliding Window | 订阅同步策略：按时间窗口拉取 |
| 空轮询退避 | Empty Poll Backoff | 连续空轮询后增大拉取间隔 |
| Job 队列 | Job Queue | PostgreSQL FOR UPDATE SKIP LOCKED 实现 |
| 短链映射 | Short Link Map | URL → ContentAsset 映射，避免重复入库 |
| 质量评分 | Quality Score | 文章入库后的质量评分，影响检索权重 |
| 分类标签 | Category Tag | 文章自动分类标签 |
| LangBot | — | 华为云知识引擎，BotHot 的 RAG 后端 |
| RedFox | — | 外部文章采集服务 |
| Wandao | — | 外部文章采集服务（备用） |
| SiliconFlow | — | LLM 推理服务，流式直连 |
| ADR | Architecture Decision Record | 架构决策记录 |
| Monorepo | — | 单一仓库管理多个应用/包 |
| 文章规范键 | Canonical Article Key | 一篇文章的全项目唯一身份键，目标形如 `b:{biz}:{mid}:{idx}` / `s:{short_token}` / `h:{sha256[:32]}`；**同一概念全项目只准叫这个名字**。现状实测缺陷：`ContentAsset.external_id` 由 `_article_key(url)`（`apps/api/app/services/kb.py:554-557`，取 URL 末段）生成，长链恒为 `"s"`；而 `ArticleManifest.external_id`（`apps/api/app/models/entities.py:99`）存渠道上游 id ⇒ 两键空间不相交。规范键函数 `canonical_article_key` **尚未实现**，属 STEP-02 S2.2.2；规格见 `docs/任务规划V0.7.0/03` §2 与 `contracts/resources.schema.json#/definitions/ArticleKey` |
| 清单行 | WorkListRow | 发现层各渠道 `query_work_list` 返回的统一行契约：`id`/`url`/`title` 必填，`publishTime`/`digest` 可选，`id_fallback` 标记上游无稳定 id。此前各渠道各自返回 `{url,title,digest,publish_time}` 且无 id，`_map_row` 遇缺 id 直接 `return None` 静默丢整页。契约定义见 `docs/任务规划V0.7.0/03` §9，落地属 STEP-03 |
| 发现渠道 | Discovery Channel | 文章**发现**（取工作列表/搜索）的上游提供方，与「渠道（Bot Channel，推送目标）」是两个不同概念、不得混称。当前实现为 Dajiala/JustOneAPI/TikHub/Wellbyte/RedFox/RSS 共存于发现注册表 `apps/api/app/providers/discovery/registry.py`；注册表条目名与详情兜底协调器的成本排序见该文件，接口面 `query_work_list` 见 `docs/02_requirements` REQ-F-006 |
| 信息源标识 | Source Identifier | 订阅某个公众号时上游 API 真正需要的身份参数（常见为 `__biz`，部分渠道要 `gh_` 开头 id）。现状：路由与清单只传解析出的单一标识，故无法表达"同一源对不同渠道需要不同标识"。落地属 STEP-08（迁移 `ab1006c2a`），契约见 `docs/任务规划V0.7.0/03` §2 D-V2-04 |
| 全跳过页 | All-Skipped Page | 一页发现结果里每一行都因缺 `id` 被丢弃、但对外表现为"本轮无新文章"的页。与正常空轮询不可区分，是采集静默（P0-3）的核心形态；识别与告警属 STEP-03 S3.3.3 + STEP-05 S5.2.2，指标名 `bothot_manifest_rows_total{outcome=dropped}` |
| 幂等键 | Idempotency Key | 去重作业用的唯一键，`Job.idempotency_key`（`apps/api/app/models/entities.py:202`，UNIQUE String(128)）。现存两种口径：`sync_account:{…}` 前缀配 LIKE 匹配（`apps/api/app/services/subscription.py:329/:812`）与 `hot_rescore:yyyyMMddHH`（业务日界 Asia/Shanghai 定宽时间戳）。契约规则见 `docs/任务规划V0.7.0/contracts/events.schema.json#/definitions/IdempotencyKey`：**禁止**用随机 uuid 当幂等键、**禁止**把用户可控字符串原样拼入键内 |
| 收件人可见性 | Notification Visibility | 站内通知"谁能看见"的谓词：定向按 `sub`，广播与定向共用同一可见性 SQL 谓词（`apps/api/app/api/v1/system.py:297` 注释），与 `persist_web_notification` 落库口径互补 |
| 过期回退 | Stale / Superseded 判定 | 同一 `article_key` 正文指纹变化时把旧文档标为过期。现状依赖 `source` 查得到：`apps/api/app/services/kb.py:281-288`，因此短链回归（`docs/任务规划V0.7.0/01` F-72）会让过期判定**一并失效**——这是该回归的第二处伤害，易被漏修 |
