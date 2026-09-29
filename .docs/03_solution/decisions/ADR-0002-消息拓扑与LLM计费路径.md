# ADR-0002：消息拓扑与 LLM 计费路径

> 状态：已采纳 | 日期：2026-09-04 | 依据：M0 能力实证总报告（T0.6/T0.7）
> 决策级：架构核心（对应开发计划 D4/D7，含 T0.6 触发的回退裁定）

## 背景与决策驱动

两个耦合决策：
1. **消息拓扑**：用户消息如何进入系统并得到回答（谁做消息中枢）
2. **LLM 计费路径**：对话生成的模型调用走哪里、如何计费（原计划：LangBot Provider 指向主平台统一计费网关）

## 决策一：消息拓扑 = AideanBot 中枢（方案 B，维持 D4）

```
用户 → [Web / 微信clawbot(M2)] → AideanBot /api/v1/chat
  ├─ 链接消息 → 识别 → 选择卡片 → 采集 Job
  └─ 普通消息 → LangBot HTTP Bot /bots/<uuid>/sync（pipeline+RAG）→ 同步取回复 → 转发用户
```

## 决策二：LLM 计费路径 = LangBot 自有 Key（T0.6 回退生效）

原计划 D7 的"LangBot Provider base_url 指向主平台网关"**当前不可行**，实证依据：

| 阻断点 | 细节 |
|---|---|
| 路径不兼容 | LiteLLM（LangBot 的 OpenAI requester）固定拼 `{base_url}/chat/completions`；主平台网关路径为 `/api/v1/gateway/chat` |
| 鉴权不兼容 | 网关 `requireUserApi` 仅读 HttpOnly cookie 会话；LangBot 发 `Authorization: Bearer`。主平台已存在 `getSessionFromBearer`（双 aud）但网关未启用 |

**裁定**：M1 起 LangBot 配置自有 LLM Key（上游计费路径）；主平台满足以下任一条件后切回统一计费：
- 网关启用 Bearer（getSessionFromBearer）鉴权，**且**
- 提供 OpenAI SDK 兼容路径（`/v1/chat/completions` 形态或可配路径）

切回时无需改 AideanBot 代码（仅改 LangBot Provider 配置）——该路径在防腐层 `providers/langbot` 内收口。

## SSO 实证支撑（T0.7 全链 PASS）

- 主平台（localhost:3000）7 端点与《子平台SSO接入指南》完全一致
- 已验证：注册→cookie→authorize 307（code+state）→RS256 兑换（900s）→userinfo（sub/tier）→code 重放拒绝→wallet 服务间查询（Basic + scope `wallet:read`）
- **dev 凭据**：wechat-rag secret 回退值 `wechat-rag-dev-secret-please-rotate`（env 未注入时）；redirect 白名单 `https://wechat-rag.aidean.local/auth/aidean/callback`
- 生产切换时需管理员正式下发 secret 并更新 redirect 白名单为实际域名

## 采集链裁定（联动 T0.2/T0.3 实证）

```
公众号文章链接
  → 直抓文章页（T0.3 移植 wandao：Markdown + var biz/ct/createTime 提取）
  → 整库：biz(=__biz) → Redfox 广域库 bizInfo 定位 → 清单（Redis 缓存控费）
  → 批量逐篇直抓（单篇成功率 83% → 质量评分 + 失败分类 → 降级链预留）
```
- Redfox 仅承担 Discovery；正文永不依赖 Redfox content（列表恒 null）
- 广域库定位优先级 wxId > bizInfo > account；从链接场景固定走 bizInfo

## 已知限制

1. 对话级 KB 路由（pipeline 按会话选库）未在本轮验证——M1 T1.10 范围；R2 回退已由 retrieve API 层隔离实证支撑
2. clawbot 通道（M2 T2.5）未实证——微信凭据依赖
3. 主平台网关切回条件属主平台路线图（二期 API Key），本系统仅做无感准备

## 影响

- M1 T1.10（对话流）按方案 B 实现；T1.2（SSO）按实证契约实现
- `docker/.env.example` 增加 LangBot 自有 LLM Provider 配置位
- 主平台二期对齐时新增 ADR 修订记录，不推翻本 ADR 骨架

---

## 修订记录 v1.1（2026-09-04，两份开发计划评审后增补）

> 依据：《评审报告-开发计划交叉裁决.md》（W2/W3/W6/O1/O7 裁决采纳）

### 增补一：多 KB 路由路径（M1 对话流默认方案）

LangBot pipeline 的 KB 绑定是静态配置项；多用户多空间需动态路由。三级降级链：

| 优先级 | 方案 | 说明 | 风险 |
|---|---|---|---|
| **M1 默认** | **方案 A：每 KnowledgeSpace 一组 bot+pipeline** | AideanBot 经 `/api/v1/platform/bots` + `/api/v1/pipelines` 编程创建，空间↔bot_uuid 映射存库；对话时按 `active_space_id` 路由到对应 bot 的 `/sync` | 全公开契约；N 空间=N pipeline（M1 用户量=1、空间个位数，可承受） |
| 次选 | 方案 B：PromptPreProcessing 插件改写 `_knowledge_base_uuids` | 单 bot；代码链路成立（preproc.py 变量先写、事件后发） | 依赖下划线私有变量（升级即碎）+ 需开发 LangBot 插件 |
| 兜底 | R2：AideanBot 亲调 retrieve + 亲调 LLM | LangBot 退化为 KB 引擎 + IM 通道 | 丢失 pipeline 会话/工具/引用能力 |

**前置验证**：T1.10 首个子任务实测 ①HTTP Bot `/bots/<uuid>/sync` 的 HMAC 签名契约（`inbound_secret`，`signature_required` 默认 true）②pipeline 编程创建 API。失败即沿降级链下移并回写本 ADR 附录。

#### 附录 A：HTTP Bot HMAC 签名契约活体实测（A-T9，2026-09-09，A 独立执行）

**结论：前置验证①已完成，方案 A 无阻塞，降级链 B→R2 不触发。**

- **签名算法**（LangBot `pkg/platform/sources/http_bot_signing.py`，依赖零、双向对称）：
  - `signing_string = "{timestamp}." + raw_body_bytes`（timestamp 为 Unix 秒字符串，`.` 为分隔符）；
  - `signature = "sha256=" + hex(HMAC_SHA256(secret, signing_string))`；
  - 请求头：`X-LB-Timestamp` / `X-LB-Signature` / 可选 `X-LB-Idempotency-Key`；
  - 重放窗口 `DEFAULT_REPLAY_WINDOW = 300s`（超出即拒）。
- **入站路由**：`POST /bots/<bot_uuid>/sync`（同步取回复）与 `POST /bots/<bot_uuid>`（异步回调），
  由统一 webhook 分发器 `groups/webhooks.py` 挂载，**该路由本身不需要 Authorization**（鉴权=签名）。
- **管理面 CRUD 实证**（需 Bearer token）：`GET/POST /api/v1/platform/bots`、
  `DELETE /api/v1/platform/bots/<uuid>` 全部可用；创建体字段为
  `{name, adapter:"http_bot", enable, description, adapter_config:{inbound_secret, signature_required}}`——
  **`pipeline_config` 不是合法列名**（误传 → 500 `Unconsumed column names: pipeline_config`）；
  未显式指定时后端自动绑定**最近更新的一条 pipeline**（`use_pipeline_uuid`）。
  登录端点为 `POST /api/v1/user/auth`，字段名是 **`user`**（非 `username`），错字段 → 500 `KeyError: 'user'`。
- **四态实测矩阵**（临时 bot `a-t9-probe`，测毕删除、LangBot 侧 bots 归零复确认）：
  | 用例 | HTTP | LangBot 响应 |
  |---|---|---|
  | 正确签名 | — | 通过验签进入 pipeline 处理（连接保持、无 40101；本环境无可用 LLM 会话故客户端侧读超时） |
  | 签名值错误 | 401 | `{"code":40101,"msg":"invalid signature: signature_mismatch"}` |
  | 缺失签名头 | 401 | `{"code":40101,"msg":"invalid signature: missing_headers"}` |
  | 时间戳超窗(-600s) | 401 | `{"code":40101,"msg":"invalid signature: expired"}` |
- **对 T1.10 的实现口径（交 B）**：backend 侧出站签名须用**原始 body 字节**参与计算（先序列化再签，
  发送同一份 bytes，勿重新 dumps 改变键序/空格）；`session_id` 为调用方自定义的会话主键，
  ADR-0003 的空间解析结果应落在此字段上；建议同时下发 `X-LB-Idempotency-Key` 以便重试幂等。

### 增补二：IM 适配器已知备选（clawbot 失败回退）

LangBot v4.10.9 自带 `openclaw-weixin` 适配器（`platform/sources/openclaw_weixin.yaml`，对接 `https://ilinkai.weixin.qq.com`，扫码登录）。**语义差异**：openclaw=机器人号模式（用户加机器人为好友）；README 目标 3=用户绑定号模式（clawbot，机器人主动推送到用户自己的微信）——二者不可混同。

**裁定**：M2 主路径维持 clawbot（符合 README 目标 3 语义）；openclaw-weixin 记录为 clawbot 风控不稳时的回退（回退时"主动推送"降级为"机器人号私聊"）。

### 增补三：嵌入服务 API 化（用户约束：本地不部署大模型）

LangRAG 建库强制 `embedding_model_uuid`、ingest 每批强制嵌入（M0 实证）。**约束：嵌入服务必须是 API 形态**（禁本地 Ollama 类部署）。默认推荐硅基流动（国内直连、OpenAI 兼容、bge 系列低价），经 `EMBEDDING_*` env 可配可换。M4 视频占位同理：ASR 只允许 API 形式。
