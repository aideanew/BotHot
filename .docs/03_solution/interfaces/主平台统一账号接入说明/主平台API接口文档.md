# API 接口文档

> 版本：v1.8 | 更新日期：2026-09-03 | 变更：§5.2 /api/v1/ladder 响应形态改为快科技式扁平排行（entries[rank]，缓存键 v3，破坏性变更已与前端同步落地）；§7 新增 SSO/OIDC 端点与服务间查询（M-SSO）
> 规范继承旧体系《API架构设计方案》（其错误码/模块编码设计已验证成熟），按新项目范围裁剪。

## 1. URL 规范

- 格式：`/api/v1/{resource}/{action?}/{id?}`，版本号入 URL（Stripe 风格）。
- 资源用复数；查询用扁平参数（`/favorites?userId=123`），不做深层嵌套。
- 公开接口与后台接口分前缀：`/api/v1/*`（公开）与 `/api/v1/admin/*`（后台，需管理员权限）。

## 2. 认证

双模式（继承旧体系 D4）：

| 模式 | 用途 | 方式 |
|---|---|---|
| JWT | Web 会话 | `Authorization: Bearer <token>`，login/refresh/me/logout；登录方式：邮箱 + 密码、微信扫码（OAuth），签发同一 JWT 体系 |
| API Key | 统一计费网关调用（**第二阶段**） | `X-API-Key: <key>`，对应 `user_api_keys`（v2.0 schema 未建表，MVP 网关仅 JWT 会话） |

## 3. 接口分层

Route（Zod 校验 / 鉴权 / 响应归一化）→ Service（业务）→ Repository（数据）。Route 不写业务逻辑。

## 4. 统一响应

```json
{ "code": 0, "message": "ok", "data": { }, "requestId": "..." }
```

错误时 `code` 为模块编码 + 序号（如 `10001` 用户不存在、`30001` 模型站不可用），`message` 为人类可读。错误码段位：1xxxx 用户/认证，2xxxx 模型/天梯，3xxxx 模型站/统一API，4xxxx 财务，5xxxx 系统。

网关段（3xxxx）登记表（先登记后实现，与 `app/api/v1/_lib/errors.ts` 双源对齐）：

| 码位 | 标识 | 语义 |
|---|---|---|
| 30001 | SITE_UNAVAILABLE | 模型站不可用 |
| 30002 | GATEWAY_NO_ROUTE | 网关无可用路由（候选链为空：无配置且无可用 free 兜底） |
| 30003 | GATEWAY_ALL_FAILED | 网关全部候选失败（沿降级链尝试耗尽仍无成功） |
| 30004 | UPSTREAM_ERROR | 上游返回错误（上游非 2xx 或响应不可解析） |

财务段（4xxxx）登记表（先登记后实现，与 `app/api/v1/_lib/errors.ts` 双源对齐）：

| 码位 | 标识 | 语义 |
|---|---|---|
| 40001 | INSUFFICIENT_BALANCE | 余额不足（可用额 = 余额 − 预扣冻结） |
| 40002 | RECHARGE_ORDER_NOT_FOUND | 充值订单不存在或不属于当前用户 |
| 40003 | ORDER_STATE_INVALID | 订单状态不允许该操作（非 PENDING 订单重复受理按幂等成功处理除外） |
| 40004 | HOLD_INVALID | 预扣不存在/已捕获/已作废/已过期，无法继续操作 |
| 40005 | NOTIFY_SIGNATURE_INVALID | 支付渠道回调验签失败（HTTP 401） |

## 5. 接口清单（按模块）

### 5.1 认证 auth
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/v1/auth/register | 注册 |
| POST | /api/v1/auth/login | 登录（返回 JWT） |
| POST | /api/v1/auth/refresh | 刷新 |
| GET | /api/v1/auth/me | 当前用户 |
| POST | /api/v1/auth/logout | 登出 |

### 5.2 天梯 ladder 与模型 models
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/v1/ladder | 天梯榜单（query: type=models/stations，分类、排序；响应为快科技式扁平排行 `data.entries[rank,...]`，一行=一个模型/站点，rank 为综合分同分并列名次；缓存键 `ladder:matrix:v3:*`） |
| GET | /api/v1/models | 模型列表（筛选） |
| GET | /api/v1/models/[id] | 模型详情（Tab1 数据） |
| GET | /api/v1/models/[id]/benchmarks | 基准测试分数 |
| GET | /api/v1/models/[id]/stations | 支持该模型的站点及资费（Tab2，含筛选：格式兼容/国内可达/免费） |

### 5.3 模型站 stations（大模型云服务天梯图）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/v1/stations | 大模型云服务天梯图（模型站榜，默认 API 版排序；端点维度） |
| GET | /api/v1/stations/[id] | 模型站详情（上线时间、可用率、好评率） |
| GET | /api/v1/stations/[id]/reviews | 好评/差评明细 |
| GET | /api/v1/stations/[id]/prices | 价格柱状图数据（输入/输出/缓存命中，按价升序） |

### 5.7 SSO / OIDC（M-SSO，主平台作为 Identity Provider，详见 ADR-0002）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /.well-known/openid-configuration | OIDC 发现（issuer/端点/能力声明） |
| GET | /.well-known/jwks.json | JWKS 公钥集（RS256；产品侧缓存后本地验签，零网络往返） |
| GET | /oauth/authorize | 授权码签发（redirect_uri 精确白名单；state 必填；PKCE S256；未登录跳主站登录页） |
| POST | /oauth/token | code/refresh_token 双 grant 兑换（client Basic/post 认证；code 一次性 60s；refresh 轮换 + 重放检测整链撤销） |
| GET | /oauth/userinfo | Bearer 用户资料（sub/email/nickname/tier/role） |
| POST | /oauth/revoke | 撤销 refresh 链（RFC 7009 子集；恒 200 不泄露存在性） |
| POST | /oauth/introspect | refresh 内省（强实时撤销需求的接入方） |
| GET | /api/v1/internal/billing/wallet?userId= | **服务间**钱包/套餐实时查询（client 认证 + scope `wallet:read`） |

**接入约定**：新平台接入 = `oidc_clients` 注册一行（clientId/secret 哈希/redirect 白名单/scopes）+ 标准授权码跳转流；用户身份锚点为 `sub=User.id`，claims 携带 `tier`（NORMAL/PRO/MAX）与 `ver`（tokenVersion）。错误码新增：10006 TOO_MANY_REQUESTS(429)、10007 FORBIDDEN_CLIENT_SCOPE(403)。**分步接入操作手册见《[子平台SSO接入指南](./子平台SSO接入指南.md)》（本节为端点权威清单，参数与响应形态以代码为准）。**

### 5.4 统一计费网关 gateway（implement-gateway-module，MVP）
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/v1/gateway/chat | 统一 API 入口：按 body 形态判别 OpenAI / Anthropic 请求格式（对仅单格式上游自动协议中转）；优先级路由 + 故障自动降级 + free 兜底；平台 Key 路径预扣-按实捕获（余额不足自动降级），自有渠道路径免费中转不扣费；MVP 非流式（stream=true → 40000） |
| GET/POST/PUT/DELETE | /api/v1/user/custom-channels | 自定义平台渠道管理（base_url + Key，兼容 OpenAI / Anthropic 格式；不扣余额、无限制免费中转；apiKey 恒掩码不回显） |
| GET | /api/v1/user/usage | Token 用量与扣费明细分页（model / billingPath 过滤；仅本人） |

控制台路由配置（通用版等级绑定 / 专业版 1~99 优先级，两形态共享底层配置）由 §5.1 认证后的用户域端点承接：`/api/v1/user/tier-mappings` 与 `/api/v1/user/priorities`（A.2.2 已交付）；free 等级由系统自动加载、只读。
> v2.0 schema 口径：/user/station-apis 无表支撑移出 MVP（随第二阶段 user_api_keys 一并设计）；API Key 网关鉴权（§2 第二行）同批第二阶段，MVP 仅 JWT 会话。错误码 30002~30004 见 §4。
>
> 架构约束（路由分层/统一响应/鉴权/分页限流）遵循《[API架构设计方案](API架构设计方案.md)》[§一 路由分层](API架构设计方案.md#一路由分层) 与 [§二 统一响应结构](API架构设计方案.md#二统一响应结构)——本节末尾互引锚点（铁律 2）。

### 5.5 套餐 packages（第二阶段）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/v1/packages | 套餐列表（所属平台、权益内容、价格、有效期） |
| POST | /api/v1/package-orders | 余额兑换套餐（平台内权益；兑换后该平台请求按套餐直连计费） |
| GET | /api/v1/package-orders/[id] | 兑换订单详情与权益状态 |

### 5.6 兑换码 redemption（第二阶段）
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/v1/redemption/redeem | 核销兑换码：余额码得余额；定向套餐码仅兑指定平台的指定套餐 |
| GET | /api/v1/user/redemptions | 用户兑换记录 |

### 5.7 系统 system
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/v1/system/health | 健康检查 |
| GET | /api/v1/system/config | 公开配置（排名权重、功能开关） |
| GET | /api/v1/system/navigation | 导航（一级七项：模型/产品/价格/文档/路线图/合作/关于；Logo 回首页为前端行为） |

### 5.8 后台 admin（第二阶段）
用户、模型、模型站、榜单配置、同步任务、内容、财务、Key 池、计费规则（加价率 / Token 倍率，敏感不出公开接口）、模型等级池、免费额度、套餐、兑换码等管理接口，统一 `/api/v1/admin/*`，结构与旧体系 admin 区一致，实施时展开。

### 5.9 财务 billing（implement-billing-module，MVP）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/v1/billing/wallet | 钱包概览：余额/冻结/可用（available = balance − held，分转元） |
| GET | /api/v1/billing/ledger | 账本流水分页（page/pageSize/entryType 过滤；按自然日分组视图；仅本人） |
| POST | /api/v1/billing/recharge-orders | 创建充值订单（档位五选一 + 微信/支付宝；返回支付参数，MVP 为 dev mock 渠道） |
| GET | /api/v1/billing/recharge-orders | 我的充值订单列表（最近 20 条） |
| POST | /api/v1/billing/recharge-orders/[id]/notify | 支付渠道回调：验签（失败 40005）→ 单事务「PENDING→PAID + TOPUP/GRANT 入账」；重复回调幂等；无会话依赖（签名即凭证） |

> 账本口径：双录不可变流水（`ledger_entries` 只 INSERT）+ 乐观锁（`wallets.lock_version`）+ 幂等键唯一兜底，见《数据库文档》「计费账本（三表分离）」；错误码见 §4 财务段登记表。架构约束（路由分层/统一响应/鉴权/分页限流）遵循《[API架构设计方案](API架构设计方案.md)》[§一 路由分层](API架构设计方案.md#一路由分层) 与 [§二 统一响应结构](API架构设计方案.md#二统一响应结构)——本节末尾互引锚点（铁律 2）。

## 6. 中间件

请求 ID、结构化日志、限流（Redis）、安全头、JWT/API Key 鉴权。继承旧 `lib/api/middleware` 设计。

## 7. 缓存

榜单、模型详情、站点价格等 GET 接口走 Redis 缓存 + ISR；同步管线写库后按 key 失效。
