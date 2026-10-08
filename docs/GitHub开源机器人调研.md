# GitHub 开源机器人/推送产品调研报告

> 调研日期：2026-10-02
> 调研范围：飞书/微信/钉钉等渠道推送开源项目，分析与 BotHot 的融合可能性

---

## 一、多渠道推送/通知系统（最相关）

### 1. SmsForwarder — `pppscn/SmsForwarder`
- ⭐ 28,232 | Kotlin | 活跃
- **渠道**：钉钉(群+企业机器人)、企业微信(群机器人+应用消息)、飞书机器人、Bark、Telegram、Server酱、PushPlus、邮件、webhook
- **特点**：监控 Android 短信/通话/应用通知，转发到 15+ 渠道，支持规则过滤
- **融合价值**：可接收 FastAPI webhook → 转发到任意渠道

### 2. push-all-in-one — `CaoMeiYouRen/push-all-in-one`
- ⭐ 211 | TypeScript (npm) | 活跃
- **渠道**：Server酱、邮件、钉钉、企业微信、飞书、PushPlus、WxPusher、iGot、Qmsg、息知、PushDeer、Discord、OneBot、Telegram、ntfy
- **特点**：统一 `send()` API；`runPushAllInOne()` 多渠道同时推送；`runPushAllInCloud()` 云端中继（避免暴露密钥）
- **融合价值**：**理想** — 作为 npm 依赖安装到 Next.js，调用 `send(title, desc, options)`

### 3. all-pusher-api — `HCLonely/all-pusher-api`
- ⭐ 88 | TypeScript | 活跃
- **渠道**：钉钉、Discord、邮件、飞书、PushDeer、PushPlus、QQ频道、Server酱、Telegram、企业微信、息知、WxPusher
- **特点**：统一推送服务 API，支持 Vercel 部署，标准化请求/响应格式
- **融合价值**：部署为 Vercel API，或作为通知微服务

### 4. heimdallr — `LeslieLeung/heimdallr`
- ⭐ 814 | Python | 活跃
- **渠道**：Bark、Server酱、PushDeer、PushPlus、钉钉、飞书/Lark、企业微信、Telegram、ntfy、Discord、Apprise、邮件
- **特点**：轻量通知网关；Serverless 部署；Markdown 支持；**RSS feed 监控**；GitHub star webhook
- **融合价值**：**极佳** — Python 原生，可作为 FastAPI sidecar 集成，支持 RSS 监控+定时触发

### 5. guanguans/notify
- ⭐ 692 | PHP | 活跃
- **渠道**：20+ 通知渠道（钉钉、飞书、企业微信、Telegram、Slack 等）
- **融合价值**：需 PHP 微服务或移植到 Python，不太适合 Python/TS 技术栈

### 6. rsspush — `easychen/rsspush`
- ⭐ 622 | Python (Docker) | 活跃
- **渠道**：微信(via Server酱/PushDeer)、Webhook、Telegram、Discord、Slack、Amazon SNS、Gotify 等
- **特点**：监控 RSS feed 变化并推送到多渠道；Docker Compose 部署；集成 RSSHub；**支持 OpenAI 摘要**
- **融合价值**：**高** — Docker 容器部署，FastAPI 通过 API 管理 RSS 订阅

---

## 二、飞书/Lark 机器人项目

### 7. LangBot — `langbot-app/LangBot`
- ⭐ 17,992 | Python | 活跃
- **渠道**：Discord、Slack、LINE、Telegram、飞书/Lark、钉钉、微信、QQ、KOOK
- **特点**：生产级多平台 IM 机器人平台；Agent/知识库编排；插件系统；LLM 集成(OpenAI/DeepSeek/Ollama/Dify/Coze/n8n)
- **融合价值**：**极高** — Python 原生，可共享 FastAPI 代码库，作为 IM 投递层

### 8. Koishi — `koishijs/koishi`
- ⭐ 6,242 | TypeScript | 活跃
- **渠道**：Discord、飞书/Lark、LINE、Telegram、Matrix、邮件、OneBot(QQ)
- **特点**：跨平台聊天机器人框架；插件生态；Web 控制台；数据库抽象层
- **融合价值**：TypeScript 原生，与 Next.js 自然集成

### 9. larksuite/oapi-sdk-python (飞书官方 SDK)
- ⭐ 560 | Python | 活跃
- **特点**：飞书/Lark 开放平台官方 SDK；全 API 覆盖；事件回调；卡片构建器；WebSocket 长连接
- **融合价值**：**直接集成** — pip 安装到 FastAPI，创建 webhook 端点

### 10. MuseBot — `yincongcyincong/MuseBot`
- ⭐ 1,644 | Go | 活跃
- **渠道**：Telegram、Discord、Slack、飞书、钉钉、企业微信、QQ、微信
- **特点**：多平台 AI 机器人；支持 OpenAI/Gemini/DeepSeek/豆包；流式响应
- **融合价值**：Go 微服务，FastAPI 调用其 API

---

## 三、微信机器人项目

### 11. wechaty — `wechaty/wechaty`
- ⭐ 23,344 | TypeScript | 活跃
- **特点**：对话式 RPA SDK；puppet 系统抽象多协议；消息监听/发送；联系人/群管理
- **融合价值**：**最成熟的微信机器人 SDK**，TypeScript 原生

### 12. wechat-bot — `wangrongding/wechat-bot`
- ⭐ 11,418 | JavaScript | 活跃
- **渠道**：Telegram、WhatsApp、Lark、微信
- **特点**：多平台 IM AI Agent；连接 ChatGPT/Claude/Kimi/DeepSeek/Ollama；基于 wechaty
- **融合价值**：Node.js 服务，Next.js 可直接集成

### 13. wechatbot-webhook — `danni-cool/wechatbot-webhook`
- ⭐ 2,164 | JavaScript | 活跃
- **特点**：轻量可部署的微信机器人 webhook 服务；HTTP 接口收发消息
- **融合价值**：**完美适配** — FastAPI 直接调用 HTTP API 推送微信消息，Docker 部署

### 14. wecomchan — `easychen/wecomchan`
- ⭐ 1,759 | Go | 活跃
- **特点**：开源 Server酱 替代品；通过企业微信应用消息推送；可自托管
- **融合价值**：Go 微服务，FastAPI 调用其 HTTP 端点

---

## 四、钉钉机器人项目

### 15. CatchZeng/dingtalk
- ⭐ 223 | Go | 活跃
- **特点**：支持 Docker、CLI、模块模式；签名安全；链式消息构建器；text/link/Markdown/ActionCard/FeedCard
- **融合价值**：Go 库/CLI，FastAPI 可 shell 调用或微服务

### 16. open-dingtalk/dingtalk-stream-sdk-python
- ⭐ 174 | Python | 活跃
- **特点**：钉钉官方 Stream Mode SDK；双向通信；事件订阅
- **融合价值**：**直接集成** — pip 安装，Stream Mode 免公网端点

---

## 五、RSS + 通知系统

### 17. rssbot — `iovxw/rssbot`
- ⭐ 1,698 | Rust | 活跃
- **特点**：轻量 Telegram RSS 通知机器人；监控 RSS feed；支持 RSSHub
- **融合价值**：仅 Telegram，但 RSS 监控架构可参考

### 18. ELF_RSS — `Quan666/ELF_RSS`
- ⭐ 609 | Python | 活跃
- **特点**：QQ 机器人 RSS 订阅插件；基于 NoneBot2；支持 RSSHub；过滤规则
- **融合价值**：Python，RSS 监控逻辑可提取适配多渠道

### 19. appstore-discounts — `appstore-discounts/appstore-discounts`
- ⭐ 406 | TypeScript | 活跃
- **渠道**：RSS、Telegram、钉钉
- **特点**：GitHub Actions 定时工作流；RSS feed 输出；多渠道通知
- **融合价值**：TypeScript，钉钉通知逻辑可复用

---

## 六、ClawBot / OpenClaw 生态

### 20. nexu — `nexu-io/nexu`
- ⭐ 3,283 | TypeScript | 活跃
- **渠道**：微信、飞书、Slack、Discord (via OpenClaw)
- **特点**：OpenClaw 桌面客户端；一键桥接 IM 平台
- **融合价值**：桌面应用，非服务端集成

### 21. CountBot — `countbot-ai/CountBot`
- ⭐ 782 | Python | 活跃
- **渠道**：微信 ClawBot、微博龙虾、飞书、钉钉、QQ、小智AI、Telegram、DeepSeek-v4
- **特点**：轻量开源 AI Agent
- **融合价值**：Python，多渠道推送逻辑可参考

---

## 七、融合建议（优先级排序）

### P0 — 立即可集成
| 项目 | 语言 | 融合方式 | 价值 |
|------|------|----------|------|
| larksuite/oapi-sdk-python | Python | pip install → FastAPI | 飞书官方 SDK，直接可用 |
| dingtalk-stream-sdk-python | Python | pip install → FastAPI | 钉钉官方 SDK，Stream Mode |
| wechatbot-webhook | Node.js | Docker → FastAPI HTTP 调用 | 微信推送最简方案 |
| heimdallr | Python | FastAPI sidecar | RSS 监控 + 多渠道通知网关 |

### P1 — 短期可集成
| 项目 | 语言 | 融合方式 | 价值 |
|------|------|----------|------|
| push-all-in-one | TypeScript | npm install → Next.js | 统一推送 API，多渠道 |
| rsspush | Python | Docker 旁路 | RSS 监控 + OpenAI 摘要 + 推送 |
| LangBot | Python | 共享代码库 | 生产级 IM 机器人平台 |

### P2 — 中期参考
| 项目 | 语言 | 融合方式 | 价值 |
|------|------|----------|------|
| wechaty | TypeScript | 独立服务 | 最成熟微信 SDK，全功能 |
| Koishi | TypeScript | 独立服务 | 跨平台框架，插件生态 |
| CountBot | Python | 逻辑参考 | 多渠道 AI Agent 参考 |


---

## 八、补充项目（第二轮调研）

### 飞书/Lark 补充

| 项目 | ⭐ | 语言 | 说明 |
|------|-----|------|------|
| lark-coding-agent-bridge | 2,589 | TypeScript | 飞书↔Claude Code/Codex CLI 桥接，流式卡片 |
| botmux | 1,561 | TypeScript | 飞书→AI编程CLI桥接，每会话独立流式 |
| chyroc/lark | 477 | Go | 社区Go SDK，全API+事件回调覆盖 |
| iflow-bot | 216 | Python | 零成本多平台AI机器人，内置定时任务 |

### 微信补充

| 项目 | ⭐ | 语言 | 说明 |
|------|-----|------|------|
| wechatferry | 2,099 | TypeScript | Windows微信COM注入框架，RPC接口 |
| wecomchan | 1,759 | Go | 开源Server酱替代，企业微信应用消息推送 |

### wechaty 多语言 SDK

| SDK | ⭐ | 语言 | 说明 |
|-----|-----|------|------|
| python-wechaty | 1,826 | Python | wechaty Python SDK，可直接集成 FastAPI |

---

## 九、完整项目清单（25个）

| # | 项目 | ⭐ | 语言 | 渠道 | RSS | 定时 |
|---|------|-----|------|------|-----|------|
| 1 | SmsForwarder | 28,232 | Kotlin | 钉钉/企微/飞书/Telegram等15+ | ❌ | ❌ |
| 2 | LangBot | 17,992 | Python | 飞书/钉钉/微信/QQ/Telegram等9 | ✅ | ✅ |
| 3 | wechaty | 23,344 | TS | 微信(个人+企业) | ✅ | ✅ |
| 4 | wechat-bot | 11,418 | JS | 微信/Telegram/WhatsApp/Lark | ❌ | ❌ |
| 5 | Koishi | 6,242 | TS | 飞书/Discord/Telegram/QQ等7 | ✅ | ✅ |
| 6 | nexu | 3,283 | TS | 微信/飞书/Slack/Discord | ❌ | ❌ |
| 7 | lark-coding-agent-bridge | 2,589 | TS | 飞书 | ❌ | ❌ |
| 8 | wechatbot-webhook | 2,164 | JS | 微信(个人) | ❌ | ❌ |
| 9 | wechatferry | 2,099 | TS | 微信(Windows) | ❌ | ❌ |
| 10 | wecomchan | 1,759 | Go | 微信(企业微信) | ❌ | ❌ |
| 11 | MuseBot | 1,644 | Go | 飞书/钉钉/企微/QQ/微信等8 | ❌ | ❌ |
| 12 | botmux | 1,561 | TS | 飞书 | ❌ | ❌ |
| 13 | CountBot | 782 | Python | 微信/飞书/钉钉/QQ/Telegram等 | ❌ | ❌ |
| 14 | heimdallr | 814 | Python | 飞书/钉钉/企微/Telegram等15+ | ✅ | ✅ |
| 15 | guanguans/notify | 692 | PHP | 飞书/钉钉/企微/Telegram等20+ | ❌ | ❌ |
| 16 | rsspush | 622 | Python | 微信/Telegram/Discord/Slack等 | ✅ | ✅ |
| 17 | larksuite/oapi-sdk-go | 620 | Go | 飞书(官方) | ❌ | ❌ |
| 18 | ELF_RSS | 609 | Python | QQ(NoneBot2) | ✅ | ✅ |
| 19 | appstore-discounts | 406 | TS | RSS/Telegram/钉钉 | ✅ | ✅ |
| 20 | chyroc/lark | 477 | Go | 飞书(社区) | ❌ | ❌ |
| 21 | larksuite/oapi-sdk-python | 560 | Python | 飞书(官方) | ❌ | ❌ |
| 22 | CatchZeng/dingtalk | 223 | Go | 钉钉 | ❌ | ✅ |
| 23 | iflow-bot | 216 | Python | 飞书/钉钉/QQ/Telegram | ❌ | ✅ |
| 24 | dingtalk-stream-sdk-python | 174 | Python | 钉钉(官方Stream) | ❌ | ❌ |
| 25 | push-all-in-one | 211 | TS | 飞书/钉钉/企微等16+ | ❌ | ❌ |
