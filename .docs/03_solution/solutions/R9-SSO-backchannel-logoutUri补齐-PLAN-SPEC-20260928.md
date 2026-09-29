# R9 · SSO back-channel logout（logoutUri）补齐方案（PLAN + SPEC 待批）

> 状态：**A 侧已实施并交付（2026-09-28，管理者「批准开工」后）**；B 侧 E1/E2/E3/E5 仍待管理者/运维
> 生成：2026-09-28 ｜ 范围：仅 AideanBot（子平台侧）+ 待管理者执行的主平台侧 1 项登记
> 触发：主平台 SSO 接入任务模板称「AideanBot 已接入，按 **v1.4** 补齐 logoutUri 验收即可」
> 方法论：AGENTS.md 三轮深推（5W1H 发散 → 苏格拉底拷问 + 双向钢人 → 重构终稿）
> A 侧交付证据：`backend/tests/test_backchannel_logout.py` 38 passed；全量 725 passed / 2 skipped；
> ruff check（改动文件）All checks passed；mypy 6 source files no issues

---

## §0 结论摘要（先读这一段）

### 0.1 任务前提有两处缺陷（必须先纠偏，否则整件事做偏）

| # | 前提 | 实测事实 | 影响 |
|---|---|---|---|
| P1 | 指南存在 **v1.4** | 权威文档 `/e/Code/Aidean/.docs/子平台SSO接入指南.md:17` 自述 **v1.3（2026-09-22）**；仓库内不存在 v1.4（主平台 `git log` 无对应提交，`.docs/` 无同名新版本） | 「按 v1.4」无所依。本报告以 **v1.3 + 主平台代码** 为准（任务模板已授权「以主平台代码为准」） |
| P2 | 「补齐 logoutUri 验收」暗示只剩登记一步 | AideanBot 侧 **完全没有 back-channel 接收能力**：`backend/`、`frontend/` 全量 grep `logout_token\|backchannel\|logoutUri` = **0 命中**。即便主平台今天就把 `logoutUri` 写进 `oidc_clients`，也没人会收到它 | 这是一项**实现任务**（A 侧端点 + 验签），不是纯验收任务 |

### 0.2 权威文档自身矛盾（已按代码裁决，需回写主平台文档）

指南 v1.3 **自相矛盾**：

- §4 撤销语义表第 4 行（`:154`）：back-channel logout **已实现**，「子平台在 client 注册时配置 `logoutUri` 即自动启用（ADR-0003 L4.1）」；
- §10 已知边界（`:277`）：「单点登出（back-channel logout）**为二期**：当前用户在主平台登出**不会**自动通知子平台」。

**以代码裁决：§4 正确，§10 陈旧。** 证据：

| 能力 | 主平台代码 | 结论 |
|---|---|---|
| 签名并发射 logout_token | `apps/web/lib/features/oauth/backchannel.ts:28-65` | 已实现 |
| 登出时触发广播 | `apps/web/app/api/v1/auth/logout/route.ts:36-63`（两条路径） | 已实现并接线 |
| 回归测试 | `apps/web/lib/features/auth/__tests__/backchannel-logout.spec.ts` | 已覆盖 |
| client 字段 | `apps/web/lib/features/oauth/clients.ts:19` `logoutUri: string \| null` | 字段已存在 |

v1.1 在 §4 补记 back-channel 后未同步清理 §10，属文档债。**§10 该行应删除或改为「已实现，见 §4」**——此项归主平台仓库，本方不越权修改，仅登记反馈。

### 0.3 阻塞与不阻塞的切分

| 侧 | 内容 | 阻塞 |
|---|---|---|
| **A 侧（本方，可离线开工）** | 新增 back-channel 接收端点 + JWKS 本地 RS256 验签 + `delete_by_sub` + 单测 + 文档 | **无阻塞**，不依赖凭据 |
| **B 侧（管理者/运维，即 §6.2 的 E1-E5）** | ① 主平台 `oidc_clients` 写 `logoutUri`；② 二级域名确定 | **硬阻塞**，越权且信息未给，**不得猜测** |

> 结论：A 侧设计决策已全部独立裁定完毕（§6.1 D1-D8），批准后即可实施并交付可测代码；端到端「验收」必须等 **E1** 完成后才能做。**在 E1 完成前，不应宣称 logoutUri 已验收。**

---

## §1 取证清单（file:line 证据，全部实测）

### 1.1 主平台侧契约（权威）

| 契约点 | 位置 | 内容 |
|---|---|---|
| 投递方式 | `backchannel.ts:47-56` | `POST {logoutUri}`，`content-type: application/x-www-form-urlencoded`，body = `logout_token=<RS256 JWT>` |
| 失败语义 | `backchannel.ts:43` 注释 + `:61-64` | fire-and-forget，5s 超时，失败仅日志；**不重试、不阻断登出**；主平台以 `res.ok` 判成功 |
| claims | `backchannel.ts:30-40` | `events={"http://schemas.openid.net/event/backchannel-logout":{}}`、`sub`、`sid`、`aud=clientId`、`iss=AUTH_ISSUER`、`jti`、`iat`；header `alg=RS256` + `kid` |
| **无 `exp`** | `backchannel.ts:30-40` | 签发时**未设 exp/nbf**——RP 无法依赖过期声明，必须自建时间窗 |
| **禁 nonce** | `backchannel.ts:8` | 「**禁止携带 nonce**（规范明确要求，含 nonce 的 logout_token 必须被拒）」 |
| 广播路径 A | `logout/route.ts:36-46` | SSO 产品链登出（`clientId≠null`）→ 仅通知该链属产品，1 条 |
| 广播路径 B | `logout/route.ts:48-63` | 主站自身链登出（`clientId=null`）→ 遍历该用户全部活跃产品链，按 clientId 去重各 1 条 |
| sid 语义 | `backchannel.ts:24` 注释 | `sid` = refresh **chainId**（链级会话标识） |
| JWKS | `apps/web/app/.well-known/jwks.json/route.ts` | `cache-control: public, max-age=300` |
| JWK 形状 | `keys.ts:161-170` | `{keys:[{kty,n,e,kid,alg,use}]}`，**current+previous 可能同时列出** → 必须按 `kid` 选钥 |
| iss 取值 | `constants.ts:82` | `NEXT_PUBLIC_SITE_URL ?? http://localhost:3000` |
| introspect **不支持** logout_token | `apps/web/app/oauth/introspect/route.ts:3` | 「仅支持 refresh 令牌」→ **本地验签是唯一验证路径** |
| logoutUri **无白名单校验** | `backchannel.ts:51` | 直接 `fetch(input.logoutUri)`，无协议/域名限制；该字段是可信 admin 配置 |

### 1.2 AideanBot 侧现状（缺口）

| 项 | 位置 | 现状 |
|---|---|---|
| 路由面 | `backend/app/api/v1/auth.py:93-156` | 仅 `login` / `callback` / `logout` / `me`；**无 back-channel 端点** |
| 全量 grep | `backend/`、`frontend/` | `logout_token\|backchannel\|logoutUri` = **0 命中** |
| 零本地验签 | `service.py:9-13`（R5.1.2 裁定）、`client.py:37-48` | 身份以 `/oauth/userinfo` RPC 为权威，id_token 只解码不验签；裁定理由是「引入 PyJWT 会改变后端供应链」 |
| 依赖现状 | `backend/pyproject.toml:20` | `cryptography>=43.0.0` **已在依赖树** → RS256 验签**无需新增任何依赖** |
| 会话删除能力 | `session_store.py:50-64` | `SessionStore` Protocol 只有 `delete(session_id)`，**无按 sub 删除** |
| sid 本地留存 | `session_store.py:17-47` | `SessionRecord` **无 sid 字段**，refresh JWT 全程不解析 → 本地无法获得 chainId |
| 前端回跳 | `frontend/app/auth/aidean/callback/page.tsx` | 仅 GET 回调承接；与 back-channel 无关（back-channel 是服务器间 POST，不经浏览器） |
| 客户端默认值 | `backend/app/core/config.py:27-30` | `oidc_client_id="wechat-rag"`、redirect `https://wechat-rag.aidean.local/...`（占位默认，靠 env 覆盖） |

---

## §2 第一轮 5W1H 发散拆解

### 2.1 What（客观事实）

1. 主平台 back-channel logout **已实现并已接线**（代码 + 测试 + 路由，见 §1.1）。
2. AideanBot 是**唯一未接**的一方：零代码、零端点、零验签能力。
3. 指南 v1.3 §4 与 §10 矛盾；任务模板引用的 v1.4 不存在。
4. AideanBot 当前降级路径**安全但不即时**：指南 §4 末句「未配置 `logoutUri` 的 client 不受影响，其会话随 refresh 轮换失败自然失效」。

### 2.2 Why（深层原因）

1. §10 陈旧是 v1.1 补记 §4 后的**文档债**（v1.1→v1.2→v1.3 变更日志均只记 §4 增补，从未回删 §10）。
2. AideanBot 无本地验签是 **R5.1.2 裁定**，其前提是「验签 = 必须引入 PyJWT 新依赖」。该前提**已失效**：`cryptography>=43.0.0` 早已在依赖里（用于 LangBot/embedding 链路），RS256 = RSA PKCS1v15 + SHA256，可直接用 `cryptography.hazmat` 实现。
3. 「userinfo RPC 为权威」架构（R5.1.3）对登录/资料场景合理，但 **logout_token 没有对应 RPC**（introspect 明确只吃 refresh token）——这是该架构的覆盖盲区，不是疏忽。

### 2.3 Where / When（边界与时间）

- **生效条件**：`oidc_clients.logoutUri` 被写入即生效（主平台侧零改动）。
- **回连方向**：back-channel 是**主平台 → 子平台**的出站 POST。本地栈中主平台在宿主 `:3000`、AideanBot backend 在容器映射 `:8000`，故 `http://localhost:8000/...` 应可达；生产需 `https://<二级域名>/...` 且该路径经前端 rewrite 转发（现有 `/api/v1/*` rewrite 已覆盖 callback，但 callback 是 GET，**POST form 经 rewrite 需实测**）。
- **时限**：主平台 fire-and-forget 5s 超时 → 子平台端点必须快速（不得在此路径上同步调主平台）。

### 2.4 Who（责任方）

| 责任 | 方 |
|---|---|
| A 侧端点 + 验签 + 测试 + 文档 | 本方（员工 A/B） |
| 主平台 `oidc_clients.logoutUri` 登记 | 管理者/主平台管理员（**越权，需授权**） |
| 二级域名 DNS + `*.aidean.com` 证书 | 运维（任务模板已明确运维侧负责） |
| 指南 §10 回写 | 主平台方（本方仅登记反馈） |

### 2.5 How（手段）

- **A 侧**：新增 `POST /api/v1/auth/backchannel-logout`；从 `/.well-known/jwks.json` 取 JWK（带缓存）→ 按 `kid` 选钥 → `RSAPublicNumbers(e,n).public_key()` → `verify(sig, msg, PKCS1v15(), SHA256())`；校验 `iss`/`aud`/`events`/**拒绝 nonce**/`iat` 时间窗；命中后 `delete_by_sub(sub)`。
- **B 侧**：管理者在主平台 `oidc_clients` 写入 `logoutUri`（值取决于二级域名）。

### 2.6 What if（前提变更）

| 前提变了 | 结论如何变 |
|---|---|
| 二级域名长期不落 | 可先用 `http://localhost:8000/api/v1/auth/backchannel-logout` 或容器内网地址临时登记（`logoutUri` 是独立字段，**不受 redirectUris 精确白名单约束**，实测 `backchannel.ts:51` 无校验）→ 本地验收可先行，不阻塞 |
| 主平台改为给 logout_token 加 `exp` | 时窗校验可收紧为 `exp` 校验，但保留 `iat` 窗无害（幂等） |
| 主平台在 token 响应暴露 `chainId` | 可升级为按 `sid` 精确清（见 §3.4），A 侧改动限于 SessionRecord 加字段 |
| 主平台回连子平台不可达（防火墙/容器网） | back-channel 静默失败（仅主平台日志），子平台会话自然失效——**退化为现状**，无新增故障面 |

---

## §3 第二轮 苏格拉底拷问 + 双向钢人

### 3.1 「不接也安全，为什么要接？」

**拷问**：指南 §4 末句明确「未配置 `logoutUri` 的 client 不受影响，其会话随 refresh 轮换失败自然失效」。若降级路径本身安全，这就是**纯便利功能**，为何列为义务？

**钢人 A（不必接）**：真正的安全场景——凭据泄露、账号封禁、改密——由主平台 `tokenVersion++` 全端失效覆盖（§4 表第 2 行），与 logoutUri 无关。主平台自身登出只是「用户主动登出主站」，此时攻击者需要的是浏览器里的会话 Cookie，而 back-channel **并不改变 Cookie 已在浏览器里这一事实**。窗口 = 当前会话到下次 refresh 失败或 TTL 到期。

**钢人 B（必须接）**：§4 措辞是「子平台收到后**应**销毁对应用户本地会话」，是接入义务而非可选项；用户已登出账号却仍能操作子平台，违反用户预期，是可投诉的体验/合规缺陷。且窗口大小取决于 AideanBot 的 `session_ttl_seconds`，若配置较长则不「极小」。

**裁决**：**接**。但定性为 **P2 契约闭环**，不是 P0 安全漏洞——降级路径安全，故不阻塞其他工作，也不应宣称「存在被利用的安全漏洞」。

### 3.2 「无 exp 的 logout_token + iat 时间窗，是否引入重放风险？」

**拷问**：主平台不发 `exp`（代码事实）。若 RP 不设时间窗，logout_token 可无限重放——但这是否真有风险？

**钢人 A（低风险）**：logout_token 只能**删会话**，无法登录、无法提权。攻击者重放一个 logout_token 对自己毫无收益，唯一效果是帮受害者删会话。

**钢人 B（必须设窗）**：正因为它「只能删」，它构成一个**可用 DoS 向量**：攻击者截获任一 logout_token 后可反复重放，持续摧毁该用户的子平台会话，造成骚扰/可用性损失。且无窗 = 无法区分「新事件」与「1 年前的事件」。

**裁决**：**必须设时间窗**。采用 `|now - iat| ≤ 300s`（与 JWKS `cache-control: max-age=300` 对齐，见 `jwks.json/route.ts`）。**不缓存 jti**：幂等操作（重复删同一 sub 无副作用），无状态校验即可。

### 3.3 「按 sub 全清会不会误杀用户自己的其他会话？」

**拷问**：用户有 2 台设备登录 AideanBot。他在设备 A 登出主平台。按 sub 全清 → 设备 B 会话被杀，用户可能认为「我没让设备 B 登出」。

**钢人 A（按 sub 全清正确）**：主平台广播路径 B 的语义是「**该用户**登出账号」（`clientId=null`，遍历全部活跃产品链，见 `logout/route.ts:48-63`）。用户登出账号后全端下线符合预期；误杀代价 = 重新登录一次点击（主平台已登录态下无需再输密码，指南 §3 第 2 步）。

**钢人 B（应按 sid 精确清）**：`sid` = 链级会话标识，主平台正是**按链粒度**发射的——它已经算好了该清哪条。子平台按 sub 全清是**主动丢弃主平台已提供的精度**，属于实现降级。

**裁决**：**A 侧第一版按 sub 全清**，理由三条：① 主平台登出语义是「用户登出账号」，全清符合用户预期；② AideanBot **拿不到 sid**——`SessionRecord` 无 sid 字段，refresh JWT 全程不解析，而 `TokenPair`（`client.py:26-35`）不含 chainId，要拿 sid 必须解析不验签的 refresh JWT（引入伪造面）或改主平台响应（越界）；③ 全清代价远小于伪造 sid 的攻击面。
**登记后续优化**：主平台若在 token 响应暴露 `chainId`，可升级为按 sid 精确清（见 §2.6）。

### 3.4 「零验签架构是否应被推翻？」

**拷问**：R5.1.2 明确裁定「不引入 PyJWT，改变后端供应链」——现在引入 JWKS 验签，是否违背该裁定？

**钢人 A（一致）**：R5.1.2 是**针对授权码流**的裁定（登录路径继续用 userinfo RPC，不变）。back-channel 是新场景，且 **`/oauth/introspect` 明确不支持 logout_token**（`introspect/route.ts:3`），本地验签是唯一可行路径，无选择空间。

**钢人 B（更一致）**：`cryptography>=43.0.0` 已在依赖树，RS256 验签**不新增任何依赖**，供应链前提已失效。R5.1.2 的反对理由原文是「引入 **PyJWT**」，而本方案不引入 PyJWT。

**裁决**：**不推翻 R5.1.2**（登录/资料路径继续走 userinfo RPC，保持零往返收益不变），仅在 back-channel 这一**唯一无法用 RPC 的场景**新增本地验签，且**零新增依赖**。R5.1.2 的裁定文字应在文档中加注「前提（无可用 crypto 依赖）已于 2026-09-28 复核为不成立，但裁定结论本身仍适用」。

### 3.5 「主平台对 logoutUri 无白名单校验，是否安全缺陷？」

**拷问**：`backchannel.ts:51` 直接 `fetch(input.logoutUri)`，无任何协议/域名限制。

**裁决**：**不是本方可改的缺陷，但需向管理者反馈确认**。理由：该字段是 `oidc_clients` 表中的 admin 配置项，只有主平台管理员能写入；攻击者要利用它必须先拿到主平台管理权限（此时已无边界可言）。这是「信任 admin 配置」的正当设计。**本方不修改主平台代码**（任务模板明令），仅登记为「建议主平台侧确认/文档化」的观察点。

### 3.6 「A 侧可以现在就全部做完吗？」

**拷问**：A 侧无阻塞，是否可以不问就做完？

**裁决**：**不行**，原因有二：① AGENTS.md 强制六步循环（PLAN→SPEC→**APPROVE**→IMPLEMENT→VERIFY→CLOSE），本项目既有惯例是「PLAN+SPEC 待批」后再实施（见提交 `c01cf6f`）；② 端点路径、时间窗参数、`delete_by_sub` 的 Redis 实现方式均为**设计选择**，批准后实施比先斩后奏更省返工。本文件即为 PLAN+SPEC，等待批准。

---

## §4 PLAN（原子任务，批准后按序执行）

### A 侧（本方实施，不依赖凭据）

| # | 原子任务 | 内容 | 依赖 |
|---|---|---|---|
| A1 | 新增 `JwksVerifier` | 拉取 `/.well-known/jwks.json`（httpx，5s 超时）+ 进程内缓存（TTL 300s，失败回退旧缓存）+ 按 `kid` 选钥 + `RSAPublicNumbers` 重建公钥 | 无 |
| A2 | 新增 `verify_logout_token` | RS256 验签 + claims 校验（`iss`/`aud`/`events`/拒绝 `nonce`/`iat` 窗 300s）→ 返回 `sub` 或抛错 | A1 |
| A3 | `SessionStore.delete_by_sub(sub)` | Protocol 加方法；`InMemorySessionStore` 遍历删除；`RedisSessionStore` 用 `SCAN sso:session:*` 逐个解析按 sub 匹配删除（**已裁定 SCAN，不建索引，理由见 §5.4**） | 无 |
| A4 | 新增端点 `POST /api/v1/auth/backchannel-logout` | 收 form `logout_token` → A2 → A3；恒 200（幂等 + 不向主平台泄露校验结果差异，与 `/oauth/revoke` 恒 200 口径一致） | A1-A3 |
| A5 | 配置项 | `oidc_backchannel_logout_path`（默认 `/api/v1/auth/backchannel-logout`）、`oidc_logout_token_clock_skew_seconds`（默认 300）；issuer/audience 复用现有 `oidc_issuer_expected`/`oidc_audience_expected` | 无 |
| A6 | 单测 | 验签通过/签名错误/未知 kid/`iss` 不符/`aud` 不符/缺 `events`/**含 nonce 被拒**/`iat` 超窗/多会话按 sub 全清/恒 200 语义/端点不依赖主平台可达 | A1-A5 |
| A7 | 文档同步 | 更新 `.docs/03_solution/interfaces/API接口文档.md`（新增端点）、`.docs/03_solution/test-plans/SSO联调测试方案.md`（back-channel 验收步骤）、`.docs/05_execution/任务进度.md`（登记 + 裁决理由）、本文档置为「已实施」 | A4-A6 |

### B 侧（管理者执行，本方不得代办）

| # | 项 | 阻塞原因 |
|---|---|---|
| E1 | 主平台 `oidc_clients` 为 AideanBot 写 `logoutUri` | 主平台 DB 变更，越权；值取决于二级域名（信息未给） |
| E2 | 确认/给出二级域名 | 任务模板说明 DNS+证书归运维，信息后续提供 |
| E3 | 生产 `oidc_issuer_expected` / `oidc_client_id` 现值确认 | D4 强制校验依赖两者已正确配置 |
| E4 | 向主平台方反馈指南 §10 陈旧 + §0.2 矛盾 | 主平台仓库改动，本方不越权 |
| E5 | 端到端验收（主平台登出 → 观察到 AideanBot 会话销毁） | 依赖 E1 |

---

## §5 SPEC

### 5.1 端点契约

```
POST /api/v1/auth/backchannel-logout
Content-Type: application/x-www-form-urlencoded

logout_token=<RS256 JWT>
```

- **鉴权**：无（无 client 凭证可用；安全性完全由 JWT 签名保证——与 OIDC Back-Channel Logout 1.0 一致）。
- **响应**：**恒 200**，body 统一 `{"code":0,"message":"ok","data":{"received":true}}`。
  - 无论 token 缺失、签名无效、校验失败，**一律 200 + 同形响应**（不泄露校验结果差异；与主平台 `/oauth/revoke`「恒 200 不泄露存在性」口径一致，见 `client.py:175` 注释）。
  - 仅当服务端自身故障（如存储不可达）才返回 5xx。
- **Content-Type 严格**：非 `application/x-www-form-urlencoded` → 仍 200（防御性接收），但按缺失处理。
- **不持久化**：不写入任何 token 值，不落日志（日志只记 `sub` 前缀 + 事件类型，见 §5.5）。

### 5.2 验签规则（fail-closed，任一失败即拒绝并返回 200）

| 序 | 校验 | 失败含义 |
|---|---|---|
| 1 | header `alg == "RS256"`（拒绝 `none`、其他 alg、无 alg） | 算法降级攻击 |
| 2 | header `kid` 存在于 JWKS | 未知密钥/未轮换 |
| 3 | `RSAPublicNumbers(e,n).public_key().verify(sig, signing_input, PKCS1v15(), SHA256())` | 签名伪造 |
| 4 | `iss == settings.oidc_issuer_expected`（未配置期望值 → **拒绝**，不跳过） | issuer 冒充 |
| 5 | `aud == settings.oidc_client_id`（`aud` 可为 string 或 array，任一匹配即过） | 非本 client |
| 6 | `events` 含键 `http://schemas.openid.net/event/backchannel-logout` | 非登出事件 |
| 7 | **`nonce` 声明存在 → 拒绝** | 规范强制（`backchannel.ts:8`） |
| 8 | `sub` 非空字符串 | 身份缺失 |
| 9 | `iat` 存在且 `|now - iat| ≤ 300s`（默认值见 A5） | 重放/时钟异常 |

> **注**：`iss`/`aud` 在本路径**强制配置**，与 `service.py:79-100` 的「未配置则跳过」逻辑不同——back-channel 端点无 client 凭证可校验，issuer/audience 是**唯一**的接收方证明，不可 fail-open。此项即 §6.2 的 **E3**（需外部确认现值）。

### 5.3 会话销毁语义

- 命中有效 token → 删除该 `sub` 的**全部**本地服务端会话（`delete_by_sub`）。
- **不调用主平台**（不做 revoke、不做 introspect）——5s 超时约束下保持快速；主平台侧链已在登出时自行撤销（`logout/route.ts:34`）。
- **不清理本地 users 表**（身份锚点保留，下次登录可复用，与 §9 存量迁移一致）。
- 幂等：重复投递同一 token 无害（第二次删 0 条）。

### 5.4 `delete_by_sub` 实现裁定（已独立裁决，记录理由）

**裁定：Redis 侧用 SCAN，不建二级索引。**

| 方案 | 正确性 | 成本 | 风险 |
|---|---|---|---|
| SCAN `sso:session:*` 逐个解析比对 `sub` | **单一事实源，零漂移** | O(全部会话)，实测会话量为百~千级（会话 TTL 7 天，见 `session_store.py:127`），量级可忽略 | 无 |
| 二级索引 `sso:sub_index:<sub>` SET | O(该 sub 会话数) | 需回填历史会话 | **`create` 若 `setex` 成功而 `SADD` 失败 → 该会话对 `delete_by_sub` 不可见 → 登出静默漏杀** |

**理由**：这是一条**登出/安全路径**，「漏杀会话」是可观测性为零的静默失败（用户以为登出了，会话仍在），
比多花几毫秒解析 JSON 严重得多。且索引方案引入两种新故障面（回填缺失 + 索引漂移），
而 SCAN 只有一个事实源。**在千级会话规模下 SCAN 的性能代价不值得用正确性去换。**

- **InMemorySessionStore**：遍历 `_sessions` 按 `record.sub` 删除。
- **RedisSessionStore**：`SCAN 0 MATCH sso:session:* COUNT 200` 迭代 → `SessionRecord.from_json` → 命中即 `DELETE`。
- 返回被删条数供日志（§5.5），不返回会话内容。

### 5.5 可观测性

- 每次接收记结构化日志：`event=auth_backchannel_logout`、`sub_prefix=<sub[:8]>`、`result=<verified|invalid_alg|invalid_kid|invalid_sig|issuer_mismatch|audience_mismatch|no_events|nonce_rejected|no_sub|stale_iat>`、`sessions_deleted=<int>`。
- **绝不记录 logout_token 原文**（凭据）。
- 校验失败计数应可供主平台侧「投递失败」日志关联排查。

### 5.6 安全红线自检（对齐任务模板 §7 + 指南 §7）

| 红线 | 本方案状态 |
|---|---|
| clientSecret 只在服务端环境变量 | 不变（本端点不使用 client 凭证） |
| 无密码输入框 | 不变（前端无改动） |
| 令牌只经 HTTPS；不缓存 token 响应 | back-channel 端点仅生产 HTTPS 可达；JWKS 缓存仅公钥，符合公开语义 |
| 不依赖主平台 Cookie 判登录态 | 满足（JWT 签名验证，不读 Cookie） |
| 刷新失败引导重登录、不循环重试 | 不变 |
| 无本地余额副本 | 不变 |
| **新增：无 alg=none / 未知 kid / 过期窗口外 token 被接受** | 由 §5.2 步骤 1/2/9 覆盖，并有单测（A6） |

---

## §6 已独立裁决项 + 仍需外部输入项

> 按既定授权口径（未决项由本方独立裁决并把理由落文档，不逐条回抛），设计类决策已在下方裁定完毕。
> 剩余仅两项属**本方无能力获取的外部输入**，非选择题。

### 6.1 已裁决（理由附后，可复核）

| # | 决策 | 裁定 | 理由 |
|---|---|---|---|
| D1 | 端点路径 | **`POST /api/v1/auth/backchannel-logout`** | 与 `auth.py:30` 既有 `/api/v1/auth/*` 路由族同域同前缀，路由注册、错误信封、`openapi()` 取证口径全部复用；主平台测试样例的 `/auth/backchannel-logout` 是主平台自己的路径风格，不构成子平台约束。**代价**：需实测 POST form 经 Next.js rewrite 转发（VERIFY 阶段必须做，现有 callback 仅 GET） |
| D2 | Redis `delete_by_sub` | **SCAN，不建二级索引** | 见 §5.4——索引漂移会造成「登出静默漏杀」这一零可观测性失败，正确性优先 |
| D3 | 是否引入 PyJWT | **不引入**，用已有 `cryptography` 手写 RS256 | `pyproject.toml:20` 已有 `cryptography>=43.0.0`；R5.1.2 反对的是「引入 **PyJWT**」，该前提已失效 |
| D4 | `iss`/`aud` 是否沿用「未配置则跳过」 | **本端点强制，不得 fail-open** | 见 §5.2 注——该端点无 client 凭证可校验，issuer/audience 是唯一接收方证明 |
| D5 | 响应语义 | **恒 200 同形** | 不泄露校验结果差异；对齐主平台 `/oauth/revoke` 恒 200 口径（`client.py:175` 注释） |
| D6 | `sid` 精度 | **第一版按 `sub` 全清**，不做 sid 精确匹配 | 见 §3.3——AideanBot 拿不到 sid，伪造 sid 的攻击面大于误杀代价 |
| D7 | 时间窗取值 | **`|now - iat| ≤ 300s`**，不缓存 jti | 与 JWKS `cache-control: max-age=300` 对齐；操作幂等故无需 jti 去重 |
| D8 | 定级 | **P2 契约闭环，非 P0 安全漏洞** | 见 §3.1——降级路径本身安全，不虚报 |

### 6.2 仍需外部输入（非选择题，本方无法自行获取）

| # | 项 | 性质 |
|---|---|---|
| E1 | 主平台 `oidc_clients` 为 AideanBot 写入 `logoutUri` | **需授权**（主平台 DB 变更，越权）；写入值依赖 E2 |
| E2 | 二级域名 | **需信息**（运维侧，任务模板说明信息后续提供） |
| E3 | 生产 `oidc_issuer_expected` / `oidc_client_id` 现值确认 | **需确认**（D4 强制校验依赖两者已正确配置；`config.py:162-164` 已有生产守卫但需确认 back-channel 路径同样强制） |

> **E1 完成前不应宣称 logoutUri 已验收**——主平台不会向任何 logoutUri 投递（见 §0.3）。

---

## §7 局限性与无法在本会话验证的部分

1. **A 侧已实施**（2026-09-28）：A1-A7 全部交付，§4 各原子任务落点：
   - A1/A2 → `backend/app/services/auth/logout_token.py`（`JwksVerifier` + `verify_logout_token`，九步 fail-closed）
   - A3 → `SessionStore.delete_by_sub`（Protocol + InMemory 遍历 + Redis SCAN）
   - A4 → `backend/app/api/v1/auth/auth.py` 的 `POST /api/v1/auth/backchannel-logout` + `AuthService.handle_backchannel_logout`
   - A5 → `OIDC_LOGOUT_TOKEN_MAX_AGE_SECONDS`（默认 300）。**注：未采纳 `oidc_backchannel_logout_path`**
     ——路径硬编码在路由装饰器，做成可配项会产生一个永远不会被读取的配置项（违反「不加不必要功能」）；
     需要向主平台登记的值在 `docker/.env.example` 与联调方案 L7 中以文档形式给出
   - A6 → `backend/tests/test_backchannel_logout.py`（38 项，含 nonce 拒绝、恒 200 同形、零主平台外呼、
     JWKS 故障 fail-closed、kid 轮换、Redis SCAN 跳过损坏记录）
   - A7 → `.docs/03_solution/interfaces/API接口文档.md`、`.docs/03_solution/test-plans/SSO联调测试方案.md`（L6 更正 + 新增 L7）、
     `.docs/05_execution/任务进度.md`、`docker/.env.example`、本文件
   - 另：`tests/test_r493_openapi_security.py` 的公开端点漂移锁已登记新端点并写明为何无需会话
2. **无法做端到端验收**：E1（`oidc_clients` 写入）未完成前，主平台不会向任何 logoutUri 投递。
   端到端验收必须等 E1 完成——**在此之前任何「已验收」表述都是不实的**。
   验收步骤已写进 `SSO联调测试方案.md` L7 层，E1 完成后可直接执行。
   **本轮实际达成的是：A 侧端点已上线且经单测验证，一旦 E1 完成即自动生效。**
3. **D1 的 rewrite 风险已静态消除**：`frontend/next.config.mjs` 的 rewrite 为
   `source: "/api/v1/:path*" → destination: "…/api/v1/:path*"`，**无方法限定**，
   Next.js rewrite 转发全部方法并保留请求体，故 POST form 可正常穿透。
   **注**：这是静态推理结论，容器栈活体验证仍需 E1 完成后随 L7.T3 一并做。
4. **二级域名未给** → 生产 `logoutUri` 无法确定，E1 写入值待补。
5. **主平台代码为只读参考**：本报告所有主平台结论以 `/e/Code/Aidean`（HEAD `c3faed64`）为准，该仓库 `git status` 有 1 个未跟踪文件 `.tmp_matches.txt`（非本方产物，未触碰）。
6. **指南版本口径**：本报告全部结论基于 **v1.3**（仓库内最新版本）。若主平台方实际另有未落库的 v1.4 草稿，需以其为准重新核对——但按「以代码为准」原则，本报告的代码证据链不受文档版本影响。
7. **`.env.example` 文档债已顺带修复**：`OIDC_ISSUER_EXPECTED`/`OIDC_AUDIENCE_EXPECTED`（R5.1.1 引入）
   此前从未写入 `.env.example`，而 R9 使两者成为 back-channel 校验的强制前提
   （未配置 → 恒 200 但零删除，属零可观测性静默失败）。已补齐并加注「取令牌 iss 值，非容器内网基址」的陷阱说明。

---

## §8 附录：主平台文档偏差反馈（E4，交管理者转达，本方不修改主平台仓库）

1. `子平台SSO接入指南.md` §10 第 1 条「back-channel logout 为二期」**已失效**，与 §4 及代码矛盾 → 建议删除或改为「已实现，见 §4」。
2. §4 未提示「logout_token **不含 exp**」这一事实，而 RP 必须据此自建时间窗 → 建议 §4 补一句「logout_token 无 exp/nbf，RP 应校验 `events`/`iss`/`aud` 并施加有界时间窗，且必须拒绝含 `nonce` 的 logout_token」。
3. §4 未说明 RP 需要 **`/.well-known/jwks.json` 本地验签**能力（且 `introspect` 不支持 logout_token，本地验签是唯一路径）→ 建议 §4 明确写入，避免其他子平台误以为可走 introspect。
4. `sendBackChannelLogout` 对 `logoutUri` 无白名单校验（`backchannel.ts:51`）→ 建议在设计文档中明确「logoutUri 为可信 admin 配置，不设白名单」，避免被误判为缺陷。
5. 任务模板所称「指南 v1.4」在 `/e/Code/Aidean` 中不存在（最新 v1.3 / 2026-09-22）→ 请管理者核对模板来源。
