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
