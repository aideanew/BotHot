---
id: PRODUCT-SCOPE
type: product
title: 产品范围
status: active
owner: product
created: 2026-09-29
updated: 2026-09-29
---

# Product Scope — BotHot

## In Scope（当前包含）

### 知识采集与入库
- 公众号链接解析入库（RedFox + Wandao 采集渠道）
- 整号订阅与增量同步（Manifest Diff 水位机制）
- 短链映射（同文两形态 0 重复请求）
- 内容资产标准化（Markdown + 元数据 + 质量评分 + 分类标签）

### 知识库管理
- 多知识空间隔离（用户级 + 公共库）
- LangBot RAG 知识引擎集成
- 可插拔引擎架构（builtin / langbot / aidean / redfox）
- 公共知识库共享与发布

### 多渠道机器人推送
- 六种渠道：飞书、钉钉、企业微信、微信 ClawBot、通用 Webhook、站内通知
- 定时推送（Cron 表达式驱动）
- 事件触发推送（新文章入库、热点更新、日报生成）
- 推送日志与投递记录
- 管理端一键测试渠道连通性

### 热点聚簇与日报
- 多篇文章按主题聚簇为事件
- 热度评分（48h 独立来源数加权，24h 减半）
- Feed 信息流（支持类型/分类筛选）
- 每日热点日报（TOP 10 + LLM 生成摘要）

### RAG 知识问答
- SSE 流式问答
- 多空间会话路由
- 检索重排（Reranker 可选增强）

### SSO 统一认证
- OIDC 接入主平台
- 会话 Cookie（HttpOnly + SameSite=Lax）
- 角色门禁（admin / operator / user）
- Backchannel Logout

### 管理后台
- 知识空间管理
- 文档生命周期管理
- 订阅管理
- 引擎管理
- Bot 渠道管理
- 推送任务管理
- 热点中心
- 日报管理

## Out of Scope（当前不包含）

- 微信公众号消息回复（非推送场景）
- 用户端 C 端 App（当前仅管理端 Web）
- 多租户隔离（当前单租户，主平台账号体系）
- 付费计费系统（余额/tier 实时查询主平台，不落库）
- 自建采集引擎（依赖外部 RedFox/Wandao API）
- 音视频内容处理（仅文本）
- 跨语言翻译
