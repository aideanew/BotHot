# 子平台 SSO 接入指南

> 版本: v1.0 | 更新: 2026-09-03 | 变更: 首版（随 M-SSO 里程碑落地；端点契约对应 ADR-0002 与《API接口文档》§5.7）
> 受众：AideanRag / WeChatRag / SkillsCloud 及后续接入主平台账号体系的子平台开发者。
> 端点权威清单见《[API接口文档](./API接口文档.md)》§5.7；架构决策背景见《[ADR-0002](./ADR/ADR-0002-SSO选型.md)》。

---

## 1. 概述

主平台作为 **Identity Provider（IdP）**：账号、密码、微信 openid、tier 等级、钱包全部只在主平台；子平台作为 **Relying Party（RP）** 通过标准 OAuth2 授权码流获得用户授权，**本地验签**消费令牌（零网络往返），凭用户身份实时查询权益。

三条铁律（先记住再往下读）：

1. **用户密码只在主平台登录页输入**——子平台任何页面不得出现密码输入框，任何后端不得转发密码；
2. **身份锚点是 `sub`（= 主平台 `User.id`）**——同一用户在所有子平台 sub 一致，以此为本地账号关联键；
3. **余额/套餐是实时数据**——禁止本地持久化副本，一律实时查询（见 §5）。

## 2. 接入前置：注册你的 client

向主平台管理员提供以下信息，注册后获得凭据：

| 项 | 说明 |
|---|---|
| `clientId` | 全局唯一标识（如 `aidean-rag`） |
| `clientSecret` | 仅颁发一次，**只存子平台服务端**（环境变量注入，禁止入库/前端/仓库） |
| `redirectUris` | 授权回调地址**精确匹配白名单**（协议+域名+端口+路径全一致；不支持通配） |
| `scopes` | 声明的资源面：`openid` `profile` `wallet:read`（计费写入 `billing:write` 需单独评审） |
| `pkceRequired` | **公共客户端（SPA/无服务端后端/移动端）必须为 true**；first-party 服务端应用可为 false |

环境口径：`issuer` = 主平台对外地址（生产由 `NEXT_PUBLIC_SITE_URL` 决定），下文以 `<issuer>` 代指。所有端点：

```
<issuer>/.well-known/openid-configuration   # 发现文档（端点与能力自描述）
<issuer>/.well-known/jwks.json              # RS256 公钥集（缓存后本地验签）
<issuer>/oauth/authorize                    # 授权码签发（浏览器跳转）
<issuer>/oauth/token                        # 令牌兑换/刷新（服务端）
<issuer>/oauth/userinfo                     # 用户资料（Bearer）
<issuer>/oauth/revoke                       # 撤销 refresh 链
<issuer>/oauth/introspect                   # refresh 活性内省（可选）
```

## 3. 登录集成：授权码流（五步）

### 第 1 步 · 构造授权跳转

用户点击"使用 Aidean 账号登录"时，子平台（或前端）302 跳转：

```
GET <issuer>/oauth/authorize
  ?response_type=code
  &client_id=<你的 clientId>
  &redirect_uri=<白名单内的回调地址，URL 编码>
  &scope=openid profile wallet:read        # 必须是注册 scopes 的子集
  &state=<随机串，≥16 字符，存入子平台会话>
  &nonce=<随机串（可选，OIDC 防重放）>
  &code_challenge=<BASE64URL(SHA256(code_verifier))>   # 公共客户端必填
  &code_challenge_method=S256
```

**义务**：
- `state` 必填——回调时必须校验一致（防 CSRF）；
- 公共客户端（`pkceRequired=true`）必须携带 `code_challenge`（S256），`plain` 不支持；
- `response_type` 只接受 `code`。

### 第 2 步 · 主平台认证用户

- 用户未登录 → 主平台展示登录页（**邮箱密码 / 微信扫码**双身份源），登录成功后自动回到授权流程——子平台无需关心认证方式；
- 用户已登录主平台 → 直接签发授权码（一次点击完成）。

### 第 3 步 · 接收回调

授权成功，主平台 307 重定向到你的 `redirect_uri`：

```
<redirect_uri>?code=<一次性授权码>&state=<原样回传>
```

子平台回调处理：**先校验 `state` 与会话中保存值一致**，再取 `code`。失败场景主平台会以 `error` / `error_description` 参数回传（如 `invalid_scope` / `unsupported_response_type` / `invalid_request`）。

> 注意：若 `client_id` 或 `redirect_uri` 本身不合法，主平台**不会重定向**（直接返回 400 页面）——这是防开放重定向的设计，接入调试时先核对白名单。

### 第 4 步 · 兑换令牌（子平台服务端 → 主平台）

```
POST <issuer>/oauth/token
Content-Type: application/x-www-form-urlencoded
Authorization: Basic base64(clientId:clientSecret)     # 或 form 字段 client_id/client_secret

grant_type=authorization_code
code=<第 3 步拿到的授权码>
redirect_uri=<必须与第 1 步完全一致>
code_verifier=<PKCE 校验器（公共客户端必填）>
```

成功响应（`Cache-Control: no-store`）：

```json
{
  "access_token": "<RS256 JWT，15 分钟>",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_token": "<7 天，轮换链锚点>",
  "id_token": "<RS256 JWT：sub/email/nickname/tier/nonce>",
  "scope": "openid profile wallet:read"
}
```

失败形态：`{"error": "invalid_grant" | "invalid_client" | "unsupported_grant_type", "error_description": "..."}`，HTTP 状态 400/401。

### 第 5 步 · 建立子平台本地会话

- **服务端会话（推荐）**：子平台后端将 `access_token`/`refresh_token` 与自己的会话 Cookie 绑定存储（服务端存储/加密 Cookie）；
- `id_token` 中的 `sub` 即用户唯一身份锚点，据此关联/创建子平台本地用户记录（见 §6 存量迁移）；
- **禁止**把 `refresh_token`/`client_secret` 下发到浏览器。

## 4. 会话维持与登出

### 刷新（refresh_token grant）

access 有效期 15 分钟。过期前用 refresh 换新对（**旧 refresh 立即失效**，轮换链语义）：

```
POST <issuer>/oauth/token
Authorization: Basic base64(clientId:clientSecret)

grant_type=refresh_token
refresh_token=<当前 refresh_token>
```

响应与兑换相同（新的 `access_token` + `refresh_token`）。

### 两级撤销语义（重要）

| 动作 | 语义 | 实现 |
|---|---|---|
| **用户在子平台登出** | 仅断开该用户在该产品的 refresh 链，不影响其主平台及其他产品登录态 | 子平台清除本地会话 + 服务端调 `POST /oauth/revoke`（`token=<refresh_token>`，client 认证；无论令牌状态恒 200） |
| **用户改密 / 被封号（主平台）** | **全端失效**：该用户所有产品的 refresh 链撤销 + 已发 access 最长 15 分钟内自然过期 | 主平台 tokenVersion++ 自动发生，子平台无需处理，只需正确处理刷新失败（§6） |

### 强实时撤销（可选）

若子平台需要逐请求确认 refresh 活性（如涉资金操作），调 `POST /oauth/introspect`。access 的实时性由 15 分钟 TTL + 关键操作二次校验承担。

## 5. 用户资料与权益

### 5.1 用户资料

```
GET <issuer>/oauth/userinfo
Authorization: Bearer <access_token>
```

```json
{ "sub": "<User.id>", "email": "...", "nickname": "...", "tier": "NORMAL|PRO|MAX", "role": "USER|..." }
```

### 5.2 余额与套餐（实时查询，服务端对服务端）

```
GET <issuer>/api/v1/internal/billing/wallet?userId=<sub>
Authorization: Basic base64(clientId:clientSecret)
```

```json
{ "code": 0, "data": {
    "user": { "id": "...", "tier": "PRO", "status": "ACTIVE", "nickname": "..." },
    "wallet": { "balanceYuan": "12.34", "heldYuan": "0.00", "availableYuan": "12.34", "currency": "CNY" }
} }
```

- 需要 client scope `wallet:read`；`userId` 用 userinfo 拿到的 `sub`；
- **实时读取，禁止本地持久化余额副本**（余额随消费变动，副本必然漂移）；
- tier 门禁：子平台按 `tier`/`status` 决定功能开关（如 PRO 专属能力）。

### 5.3 AI 消费计费

子平台内的大模型调用**不自行扣费**：经主平台统一计费网关（`/api/v1/gateway/chat`）调用，费用自动计入主平台钱包账本（预扣-捕获，幂等）。子平台自有消费场景的记账通道（`billing:write` scope）需单独评审后开放。

## 6. 错误处理与排查

| 信号 | 含义 | 处理 |
|---|---|---|
| 回调无 code，`error=invalid_request` | 缺 state / PKCE 缺失或方法不对 | 修正参数重发起 |
| `invalid_scope` | 请求了未注册的 scope | 核对注册 scopes |
| `invalid_client`(401) | secret 错误 / client 停用 | 检查凭据与管理台状态 |
| `invalid_grant`（兑换） | code 过期（60s）/ 已使用 / redirect_uri 不一致 / PKCE 失败 | **重新走授权流程**，不可复用旧 code |
| `invalid_grant`（刷新） | refresh 被撤销 / **旧值复用（重放检测）** / 用户改密封号 | 引导用户重新登录；**禁止无限重试** |
| userinfo 401 `invalid_token` | access 过期或无效 | 用 refresh 轮换后重试 |

**重放检测说明**：refresh 实现轮换链安全——若已轮换的旧 refresh 被复用（疑似泄露），主平台会撤销整条链（新旧令牌同时失效）。因此子平台**必须可靠持久化最新一代 refresh_token**（写入失败会导致下次刷新即被判定重放）。

## 7. 安全红线（接入方必须遵守）

- [ ] clientSecret 只存在于子平台服务端环境变量；
- [ ] `state` 必填并在回调时强校验；
- [ ] 公共客户端必须启用 PKCE（注册时 `pkceRequired=true`），且不得在公共客户端使用 client_secret；
- [ ] 密码输入框只允许出现在主平台登录页；
- [ ] 令牌只经 HTTPS 传输；token 端点响应不缓存；
- [ ] 禁止本地持久化用户余额副本；
- [ ] 处理刷新失败时引导重登录，不循环重试。

## 8. 最小接入示例

### Node（兑换 + 刷新）

```js
// 兑换（服务端）
const token = await fetch(`${ISSUER}/oauth/token`, {
  method: "POST",
  headers: {
    "content-type": "application/x-www-form-urlencoded",
    authorization: `Basic ${Buffer.from(`${CLIENT_ID}:${CLIENT_SECRET}`).toString("base64")}`,
  },
  body: new URLSearchParams({
    grant_type: "authorization_code",
    code, redirect_uri: REDIRECT_URI,
  }),
}).then(r => r.json());

// 刷新（旧 refresh 用后即废，必须保存响应中的新 refresh_token）
const refreshed = await fetch(`${ISSUER}/oauth/token`, {
  method: "POST",
  headers: {
    "content-type": "application/x-www-form-urlencoded",
    authorization: `Basic ${Buffer.from(`${CLIENT_ID}:${CLIENT_SECRET}`).toString("base64")}`,
  },
  body: new URLSearchParams({ grant_type: "refresh_token", refresh_token: savedRefresh }),
}).then(r => r.json());

// 实时权益查询（服务端对服务端）
const wallet = await fetch(`${ISSUER}/api/v1/internal/billing/wallet?userId=${sub}`, {
  headers: { authorization: `Basic ${basicAuth}` },
}).then(r => r.json());
```

### Python（RagFlow 口径，PyJWT 本地验签示意）

```python
import jwt, requests
from jwt import PyJWKClient

jwks = PyJWKClient(f"{ISSUER}/.well-known/jwks.json")   # 缓存公钥，本地验签
key = jwks.get_signing_key_from_jwt(access_token)
claims = jwt.decode(access_token, key.key, algorithms=["RS256"],
                    issuer=ISSUER, audience=CLIENT_ID)  # aud=你的 clientId
# claims["sub"] = 用户唯一锚点；claims["tier"] = 权益等级
```

## 9. 存量用户绑定迁移（RagFlow 场景）

RagFlow 已有自有用户体系。首次联合登录时按以下顺序关联：

1. `sub` 已在绑定表 → 直接登录；
2. 未绑定但 **email 与 RagFlow 本地用户一致** → 提示确认后合并（建议验证 RagFlow 本地密码一次）；
3. 均无匹配 → 以 `sub` 创建新 RagFlow 用户。

绑定关系落在子平台侧（`sub ↔ 本地 userId` 映射表），主平台不感知子平台内部账号。

## 10. 已知边界与演进

- 单点登出（back-channel logout）为二期：当前用户在主平台登出**不会**自动通知子平台，子平台会话按各自 refresh 生命周期自然到期，或经 introspect 主动探测；
- 微信扫码身份源依赖主平台微信凭据下发（待办），协议链路已就绪；
- 接入方超过 5 个或需开放第三方时，主平台将以 `oidc-provider` 独立 idp 服务演进（端点契约兼容，本指南主体不变）。
