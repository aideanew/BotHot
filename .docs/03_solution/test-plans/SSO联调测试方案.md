# SSO 联调测试方案（M0：AideanBot × Aidean 主平台 SSO + 余额共享）

> 版本 v1.0 ｜ 2026-09-18 ｜ 维护：AideanBot 侧（员工A 域协作出品）
> 定位：可直接下发的**剩余任务**测试方案。与主平台 A 方《SSO+余额共享联调测试指引》（下称「A 方指引 §N」）互操作，映射见 §0.4。
> 铁律：任一原子任务 FAIL → 停在当前层，按附录 A 处置或上报；**失败零改动取证**，不擅改 callback/issuer/白名单。

---

## 0. 总纲

### 0.1 本轮两个关键事实（已双重复核）

| # | 事实 | 复核方式与结果 |
|---|---|---|
| ① | AideanBot 后端**无 back-channel logout 接收端点** | 2026-09-18 全仓 grep `backchannel|back_channel|logout_token` → **0 命中**（独立复核通过）；主平台 seed `wechat-rag` 未配 `logoutUri` 属 A 方域声明，列 A 方依赖项 R7 |
| ② | Bot 侧 `/logout` `/me` state/回调链路齐备 | 代码锚定：`backend/app/api/v1/auth.py:93-156`（login/callback/logout/me 四路由）、`backend/app/services/auth/service.py`（state 单次消费→兑换→userinfo→upsert→会话；me 自动 refresh 一次；logout 幂等） |

→ back-channel logout 列为 **L6 可选预研（M1 模块）**，不设验收门槛。

### 0.2 模块注册表（拓展性锚点：新模块只追加，不改既有编号）

| 模块 | 范围 | 状态 | 本方案对应 |
|---|---|---|---|
| M0 | SSO 登录链 + 余额共享读路径 | **本轮执行** | L0~L5 |
| M1 | back-channel logout（bot 接收端点 + A 方 logoutUri seed） | 预研占位 | L6 |
| M2 | AideanWiki 双账号绑定（注册 client→联合登录→绑定映射→余额激活） | **外部输入阻塞**（待 AideanWiki 仓库路径+技术栈：自研 or MediaWiki、后端语言） | 不在本文展开，复用本方案骨架 |
| M3+ | 预留 | — | — |

### 0.3 角色与端口纪律

| 端口 | 归属 | 纪律 |
|---|---|---|
| 3000 | 主平台 IdP（A 方） | **bot 侧禁止 loopback 自拉**（会致容器兑换 503/50002）；只探活、不处置 |
| 3333 | AideanBot 前端容器（3333→3000） | 本轮走查基座；同刻只能容器或本地 dev 二选一 |
| 3334 | 员工C 并行走查备用 | ⚠️ 主平台白名单当前未含 3334 回调——3334 只能做**页面级走查**（无兑换回调）；若需全链，先经 A 方扩白名单（依赖项 R8） |
| 3456 | e2e MOCK 态隔离口 | 与业务口错峰 |
| 8000 / 5433 / 6380 / 5300 | backend / PG / Redis / LangBot | compose 管理，不手工抢占 |

### 0.4 与 A 方指引映射（两文档互操作）

| 本方案 | A 方指引 | 本方案 | A 方指引 |
|---|---|---|---|
| L0 | §1 前置探活 | L4 | §5 余额共享 |
| L1 | §2 单元/集成 | L6 | §6 back-channel logout |
| L2 | §3 容器栈 | 附录 A | §7 坑位表（增补） |
| L3 | §4 九步走查（重排+降级路径修正） | L5/H | §8 报告纪律（强化） |

### 0.5 时间预算与并行泳道（高性能设计）

| 层 | 预算 | 并行性 |
|---|---|---|
| L0 前置探活 | ~3min | 串行先行（fail-fast 总闸） |
| L1 离线测试 | ~6min | ⚡ 与 L2 并行（L1 不依赖容器与主平台） |
| L2 容器栈核对 | ~6min | ⚡ 与 L1 并行 |
| L3 真实链路走查 | ~15min | 串行（Playwright workers=1，会话态依赖；负面用例集中在主链 2 轮绿后用 curl.exe 免浏览器执行，避免限流干扰） |
| L4 余额共享断言 | ~8min | 串行（依赖 L3 会话） |
| L5 收尾报告 | ~5min | 最后 |
| **总墙钟** | **~35min（并行后 ~30min）** | |

---

## L0 前置探活（主平台在线性 + 本机工具链，fail-fast 总闸）

| 编号 | 原子动作（PowerShell 口径） | 预期/判据 | 证据 |
|---|---|---|---|
| L0.T1 | `git rev-parse HEAD; docker version --format '{{.Server.Version}}'; pnpm -v` | 三值有输出；记录 commit 作为本轮基线锚 | 原样输出 |
| L0.T2 | `netstat -ano | findstr LISTENING | findstr ":3000 :3333 :3334 :3456"` | 3000 有唯一监听；3333 空闲或仅容器转发；3334/3456 空闲 | 原样输出 |
| L0.T3 | `curl.exe -s http://localhost:3000/api/v1/system/health` → `curl.exe -s http://localhost:3000/.well-known/jwks.json` → `curl.exe -s http://localhost:3000/.well-known/openid-configuration` | ① 200 且 code=0；② `keys` 数组长度 ≥1；③ 含 `issuer` / `authorization_endpoint` / `token_endpoint` | 三段原样输出 |
| L0.T4 | authorize 白名单行为探针（`curl.exe -s -o NUL -w "%{http_code}" --max-redirs 0`，不跟随重定向）：合法 `redirect_uri=http://localhost:3333/auth/aidean/callback`；伪造 `redirect_uri=http://evil.example.com/cb` | 合法值 + 登录态 cookie → **307** 带 code+state；无登录态 → 302/307 至登录页（非 400）；伪造值 → **400**（任何情况下不得重定向） | 状态码 + Location 头 |
| L0.T5 | 双 issuer 环境预备确认：读 `docker/.env`（或 `.env.example`）中 `AIDEAN_ISSUER` / `AIDEAN_PUBLIC_URL` / `OIDC_REDIRECT_URI` / `OIDC_CLIENT_SECRET` | 双变量并存；secret 与 A 方当次下发一致（dev 口径参考 `.docs/00_governance/文档索引.md` §五：`wechat-rag-dev-secret-please-rotate`，以 A 方下发为准） | 键值清单（secret 打码） |

**FAIL 处置**：T3 任一失败或 3000 异常 → 上报 A 方（其承诺 standalone `HOSTNAME=0.0.0.0` 运行），bot 侧不得自行拉起 3000；T4 伪造值未得 400 → 白名单漂移，上报 A 方。

---

## L1 离线测试层（无需主平台在线；⚡ 与 L2 并行）

| 编号 | 原子动作 | 预期/判据 | 证据 |
|---|---|---|---|
| L1.T1 | `cd E:\Code\AideanBot\backend; ./.venv/Scripts/python.exe -m pytest tests/test_auth.py -q` | **12 passed**（与 A 方基线对齐；数量漂移先 `git log --oneline -3 -- tests/test_auth.py` 找原因再继续） | 末行原样输出 |
| L1.T2 | `cd E:\Code\AideanBot\frontend; pnpm vitest run tests/callback.spec.tsx` | 全绿（回调页单测，mock `usePathname=/auth/aidean/callback`） | 末行原样输出 |
| L1.T3（非门槛） | 后端全量 `pytest -q` + 前端全量 `pnpm vitest run` | 回归登记，不阻断本轮 | 汇总行 |
| L1.T4a | MOCK 产物烘焙：`cd frontend; $env:NEXT_PUBLIC_API_MOCK="true"; pnpm build; Remove-Item Env:NEXT_PUBLIC_API_MOCK` | exit 0（`NEXT_PUBLIC_` 只在**构建期**烘焙生效，运行时设无效——双口径铁律） | EXIT=0 |
| L1.T4b | MOCK 态 e2e：`$env:PORT="3456"; pnpm test:e2e; Remove-Item Env:PORT` | **9/9 绿**（`frontend/e2e/trunk.spec.ts`；3456 隔离口）。**严禁把 mock 用例跑在 MOCK=false 的 3333 容器上**（A-T17.1 假红根因） | 9 passed |
| L1.T5 | Playwright 浏览器 revision 对齐（幂等）：`pnpm exec playwright install chromium` | 若项目期望 revision 与运行时环境不一致，用项目自身 CLI 补装；不改代码不改依赖 | 安装日志或 already installed |

---

## L2 容器栈启动与 env 核对（⚡ 与 L1 并行；历史故障点全在此层）

| 编号 | 原子动作 | 预期/判据 | 证据 |
|---|---|---|---|
| L2.T1 | `Copy-Item docker/.env.example docker/.env`（已存在则跳过）后按 L0.T5 清单填值 | `.env` 被 gitignore：`git check-ignore docker/.env` 有输出（密钥不入库铁律） | check-ignore 输出 |
| L2.T2 | 仓库根执行 `docker compose -p aideanbot -f docker/compose.yml --env-file docker/.env up -d` | 七容器 Up；**必须带 `-p aideanbot`**（防 compose 项目劈裂，A-T5 教训） | `docker compose -p aideanbot ps` |
| L2.T3 | 端口映射核对：`docker ps --format "table {{.Names}}\t{{.Ports}}"` | frontend `0.0.0.0:3333->3000`、backend `8000`、postgres `5433`、redis `6380`、langbot `5300` | 原样输出 |
| L2.T4 | backend 实际 Env 核对：`docker inspect aideanbot-backend --format '{{json .Config.Env}}'` | 必含非空 `DATABASE_URL` / `REDIS_URL`（缺失曾致 callback 500 OperationalError）；`AIDEAN_ISSUER=http://host.docker.internal:3000` 且 `AIDEAN_PUBLIC_URL=http://localhost:3000` **双变量并存**（单值冒充修复曾被禁，A-T21）；`OIDC_REDIRECT_URI=http://localhost:3333/auth/aidean/callback`；`OIDC_CLIENT_ID=wechat-rag` | env JSON（secret 打码）。若 compose 已注入而 env 缺失 → **旧配置遗留实例**嫌疑，force-recreate 后复测，勿先判网络 |
| L2.T5 | 容器侧 issuer 可达性预探（兑换 503/50002 的前置排雷）：`docker exec aideanbot-backend python -c "import httpx; r=httpx.get('http://host.docker.internal:3000/api/v1/system/health', timeout=5); print(r.status_code)"` | 200。ConnectError → 兑换必炸，立即上报 A 方（3000 非 standalone），**不进 L3** | 原样输出 |
| L2.T6 | 窗口复验四项（真实态开窗前置）：① 3333 单实例（L2.T3 已证）② `curl.exe -s -o NUL -w "%{http_code}" http://localhost:3333` → 200/307 ③ 3456 无残留监听（与 L1.T4 错峰）④ 3000 监听进程非 Cursor 相对路径伪实例（`Get-CimInstance Win32_Process -Filter "ProcessId=<pid>" | Select CommandLine`，相对路径 + 无 HOSTNAME = 污染信号） | 四项全过才进 L3；③观测到导航 host 变 `0.0.0.0:3000` → **立即停手取证**（netstat→CommandLine→父进程链），不得伪造通过 | 四项各自输出 |

---

## L3 真实链路走查（浏览器 + HTTP 探针；串行，workers=1）

> **主路径修正说明**：compose 已显式注入双 issuer（`compose.yml:104-108`），正常情况 login 302 的 Location host 应为 `AIDEAN_PUBLIC_URL=localhost:3000`（浏览器可直接解析，**无需任何改写**）。仅当实测 Location 为 `host.docker.internal:3000`（`AIDEAN_PUBLIC_URL` 空串回落 issuer，`config.py:26`）或 `wechat-rag.aidean.local`（env 缺失回落代码默认，`config.py:30`）时，才启用降级路径——此时先回查 L2.T4 env，再用 A 方指引 §4 步 3 的分段导航/route 拦截。**降级路径是预案，不是常规操作。**

### L3.A 主链（两轮全绿）

| 编号 | 原子动作 | 预期/判据 | 证据 |
|---|---|---|---|
| L3.T1 | 浏览器 goto `http://localhost:3333` | 未登录引导卡 | 截图 |
| L3.T2 | 发起登录 `GET /api/v1/auth/login`，提取 302 Location | Location=`<AIDEAN_PUBLIC_URL>/oauth/authorize?...&redirect_uri=http://localhost:3333/auth/aidean/callback&state=<43字符级随机>`；state 每次不同 | Location 原文 |
| L3.T3 | goto Location（主路径直达；不可达时启用降级路径并注明） | 到达主平台 `/login?redirect=...` | 截图 |
| L3.T4 | 主平台登录（A 方测试账号，邮箱密码/验证码） | 登录成功 | 截图 |
| L3.T5 | 主平台 307 回 `redirect_uri?code=..&state=..` | callback 页（`/auth/aidean/callback`）加载 | URL + 截图 |
| L3.T6 | callback 页转发 `GET /api/v1/auth/callback?code=..&state=..`（credentials:include）→ 后端经 AIDEAN_ISSUER 兑换 `/oauth/token` → `/oauth/userinfo` → upsert users（真 PG + 显式 commit）→ 建服务端会话 | 200 信封 `data.session=established`，Set-Cookie httponly | 网络面板/响应体 |
| L3.T7 | **轮询** `GET /api/v1/auth/me` 至 200（退避口径：2s×5 次；命中 3333 约 15s RESET 抖动 → 等 30s 复测**一次**；callback 是页内异步，勿等 URL 跳转） | 200 | 每次轮询状态码 |
| L3.T8 | `/me` 断言 | `data.user.sub/email/nickname/tier` 非空 + `data.wallet.balanceYuan` 实时数值（余额不落库铁律） | 响应 JSON 原样 |
| L3.T9 | `POST /api/v1/auth/logout` | 200 `data.logged_out=true` + cookie 删除（幂等语义，`auth.py:135`） | 响应 + cookie 面板 |
| L3.T10 | 登出后 `GET /api/v1/auth/me` | **10001** 未登录 | 响应 JSON |
| L3.T11 | **第二轮完整复现**（T1→T10 原样重跑） | 两轮全绿（可复现性门） | 第二轮全套证据 |

### L3.B 负面码位（主链 2 轮绿后集中执行；curl.exe 免浏览器，降低限流触发）

| 编号 | 原子动作 | 预期 | 代码锚点 |
|---|---|---|---|
| L3.T12 | `curl.exe "http://localhost:3333/api/v1/auth/callback?code=fake&state=forged"` | **10002**（state 校验先于兑换） | `service.py:61` |
| L3.T13a | **code 重放变体 A**：同一 code+同一 state 二次提交 callback | **10002**（state 单次消费） | `service.py:61` |
| L3.T13b | **code 重放变体 B**：新发起 login 取新 state + 用旧 code 提交 | **10003**（state 合法、兑换被主平台拒：过期/重放/redirect 不一致） | `client.py:99-125` |
| L3.T14 | callback 带错误参数：`?error=access_denied&error_description=x` | **10003** | `auth.py:109-112` |
| L3.T15 | authorize 阶段把 Location 中 `redirect_uri` 替换为未登记值后访问 | 主平台 **400**（不签 code）——A 方域行为对照 | A 方指引 §1 |
| L3.T16 | 无 cookie `GET /me` | **10001** | `auth.py:153-154` |
| L3.T17 | 限流基线纪律：执行前后请 A 方读 `rl:login:*` 基数对比 | 残留 key 须说明来源（如 T12/T13 触发）且 TTL 在预期内过期 | A 方读数 |

**错误码语义对照**：10001 未登录 / 10002 state 不符或重放 / 10003 code 过期、重放（新 state）、redirect_uri 不一致、主平台授权错误回传。

---

## L4 余额共享断言（业务层；依赖 L3 会话）

| 编号 | 原子动作 | 预期/判据 | 门槛 |
|---|---|---|---|
| L4.T1 | 一致性：bot 侧 `/me` 的 `wallet` vs 主平台同 userId 后台余额 | **实时一致**（主平台 internal billing wallet API：Basic client 凭据 + `wallet:read` scope） | ✅ 门 |
| L4.T2 | 变更传播：A 方对测试账号充值/消费 → bot 侧重拉 `/me` | 30s 内见新值，**无需重启任何服务** | ✅ 门 |
| L4.T3 | 刷新轮换（高级，可选）：等 access 自然过期或 A 方短 TTL 签发 → `GET /me` | 自动 refresh 恰好一次后 200（`service.py:121-128` 仅重试一次，禁止循环）；旧 refresh 立即失效 | ❌ 登记 |
| L4.T4 | revoke 链（可选）：logout 后由 A 方观察 revoke 调用与 refresh_token 失效 | 主平台侧 `invalid_grant` | ❌ 登记 |
| L4.T5 | 性能登记（非门槛）：`Measure-Command` 采 login 302 / callback 兑换 / `/me` 三段耗时 | 本地预算各 <3s；超限登记不阻断（本地口径≠生产基线） | ❌ 登记 |
| L4.T6（可选·破坏性·最后做·做完必须还原） | 对照实验：`OIDC_CLIENT_SECRET` 改错值 → `docker compose -p aideanbot up -d backend` → 走一轮登录 | 兑换 **401** → 还原 env → up -d → 复测登录 200 | ❌ 登记 |

---

## L6 back-channel logout（**R9 已实施**，2026-09-28；本节按实现更正）

> **本节原为「可选预研，本轮不测不验收」（M0 口径）。两处前提已被 R9 实现更正**：
>
> 1. ~~PyJWT RS256 验签~~ → **不引入 PyJWT**（R9 裁决 D3）。`cryptography>=43.0.0`
>    早在依赖树（`backend/pyproject.toml`），RS256 = RSA PKCS1v15 + SHA256，手写即得，
>    **零新增依赖**——R5.1.2「引入 PyJWT 会改变后端供应链」的反对前提已不成立。
>    实现：`backend/app/services/auth/logout_token.py`（`JwksVerifier` + `verify_logout_token`）。
> 2. ~~按 `sid` 清会话~~ → **按 `sub` 全清**（R9 裁决 D6）。AideanBot 拿不到 `sid`
>    （`SessionRecord` 无 sid 字段、refresh JWT 全程不验签不解析、`TokenPair` 不含 chainId），
>    要拿 sid 必须解析未验签的 refresh JWT（引入伪造面）或改主平台响应（越界）。
>    误杀代价 = 用户重新登录一次点击（主平台已登录态下无需再输密码）。
>
> 其余口径不变且已落码：校验 `aud`/`events`、**必须快速 200**（fire-and-forget 5s 超时语义）、
> 恒 200 同形响应、**拒绝含 `nonce` 的 token**、logout_token 无 `exp` 故自建 300s 时间窗。

### L6.1 bot 侧现状（已交付，38 项单测全绿）

| 项 | 落点 |
|---|---|
| 端点 | `POST /api/v1/auth/backchannel-logout`（`backend/app/api/v1/auth.py`） |
| 验签 | `backend/app/services/auth/logout_token.py`（JWKS TTL 300s 缓存 + kid 选钥 + 手写 RS256） |
| 会话销毁 | `SessionStore.delete_by_sub(sub)`（Protocol + memory/Redis 双实现；Redis 走 SCAN，不建二级索引） |
| 配置 | `OIDC_LOGOUT_TOKEN_MAX_AGE_SECONDS`（默认 300）；复用 `OIDC_ISSUER_EXPECTED`/`OIDC_AUDIENCE_EXPECTED` |
| 测试 | `backend/tests/test_backchannel_logout.py`（38 passed）；OpenAPI 公开集合漂移锁已登记新端点 |

### L6.2 A 方增量（**仍未完成，E1**）

seed 补 `wechat-rag.logoutUri = https://<二级域名>/api/v1/auth/backchannel-logout`。
**未登记前主平台不会向任何 logoutUri 投递**——本方端点静默闲置，会话随 refresh 轮换失败
自然失效（降级路径安全，指南 v1.3 §4 末句）。**在此之前任何「logoutUri 已验收」表述都不实。**

---

## L7 back-channel logout 端到端联调（**依赖 L6.2 完成**；A 侧已就绪，可先行）

| 编号 | 原子动作 | 判据 |
|---|---|---|
| L7.T0 | 前置核对：`OIDC_ISSUER_EXPECTED`/`OIDC_AUDIENCE_EXPECTED` 已配置。**二者任一为空 → 全部 token 被 `misconfigured_expected_claims` 拒绝（恒 200 但零删除）**，是本层最易踩的静默失败；取值须为**令牌里的 iss**（主平台 `NEXT_PUBLIC_SITE_URL`），非容器内网基址 `AIDEAN_ISSUER` | 两 env 非空且与 JWKS 端点的 issuer 声明一致 |
| L7.T1 | JWKS 可达性探针：`curl.exe -s "$AIDEAN_ISSUER/.well-known/jwks.json"` 应返回 `keys[]` 且含 `kid`/`n`/`e` | 输出含 `"kid"` |
| L7.T2 | 负向先测（不依赖主平台）：`curl.exe -X POST -d "logout_token=garbage" -H "Content-Type: application/x-www-form-urlencoded" http://localhost:3333/api/v1/auth/backchannel-logout` | HTTP 200 且 `data={"received":true}` |
| L7.T3 | **端到端主断言**：两个 cookie jar（模拟两台设备）各自登录 AideanBot → 主平台登出 → 两 jar 各请求 `GET /api/v1/auth/me` | 两者均返回 `code=10001`（会话全清，非按 sid 精确清） |
| L7.T4 | 幂等：主平台重复广播同一 token 第二次 | 仍 200，日志 `sessions_deleted=0`，无副作用 |
| L7.T5 | 校验差异不泄露：对比 L7.T2（无效）与 L7.T3 触发的（有效）响应体，**剔除 `requestId` 后须逐字节相同** | 两响应同形 |
| L7.T6 | 不外呼核对：L7.T3 期间观察 bot 侧无任何 `/oauth/revoke` 出站（仅 JWKS 取钥允许） | 出站日志仅 JWKS |
| L7.T7 | 日志核对：bot 日志出现 `back-channel logout 已处理`，且**全文检索无 token 原文** | 命中处理日志、零 token 明文 |
| L7.T8 | 主平台侧核对：`sendBackChannelLogout` fire-and-forget 失败仅 `console.error`，须同时看主平台日志确认投递非 200 的原因 | 主平台日志无投递失败 |
| L7.T9 | 报告回写：本文件追加执行记录 + `.docs/05_execution/任务进度.md` 登记（L7.T3 绿方为「已验收」） | 两处 diff |

> **端口纪律**：L7 走容器栈时 3333 由容器占用，本地 dev 必须已杀净；若需并行则 dev 临时换
> 3334 并在报告中注明。3000 属主平台常驻，不动。

---

## L5 收尾与报告

| 编号 | 原子动作 | 判据 |
|---|---|---|
| L5.T1 | 进程/端口收尾：杀净本轮 dev/测试进程；`netstat` 复核 3333/3334/3456 清零（3000 属主平台**不动**） | 端口清零输出 |
| L5.T2 | 临时文件清理：`frontend/test-results/`、探针 cookie/body 临时文件、`.e2e_err.txt` 等删除并**复核不存在**（含敏感会话信息不得残留） | 删除前后 `ls` 对比 |
| L5.T3 | 报告产出：每层**当次原样输出**（不得复用历史日志）逐条标 PASS/FAIL；e2e 附截图/error-context | 报告文档 |
| L5.T4 | 结论四分类：已实测通过 / mock 测试通过 / 真实态未通过或未覆盖 / 依赖 A 方的阻塞项 | 四分类齐全 |
| L5.T5 | 文档回写：本文件追加「执行记录」节 + `.docs/05_execution/任务进度.md` 登记本轮结果（随任务即时更新口径） | 两处 diff |

---

## H 横切纪律（贯穿全层）

- **H1 取证口径**：PowerShell 每条命令后附 `; "EXIT=$LASTEXITCODE"`，原样粘贴；未逐项取 EXIT 码不得宣称全绿。
- **H2 失败零改动**：失败即截图 + `docker logs aideanbot-backend --tail 200` 取证上报；不擅改 callback/issuer/白名单/compose。
- **H3 职责域边界**：根因落在 A 方域（3000 standalone、白名单、限流键、logoutUri）→ 带「需要谁 + 可复现证据」上报，不越权；用户侧进程（Cursor 污染）不 kill，只取证。
- **H4 限流脏数据**：L3.B 前后各请 A 方读一次 `rl:login:*` 基数，残留须溯源并确认 TTL。

---

## 依赖项 R（A 方承诺/协同清单，转发用）

| # | 项 | 用途 |
|---|---|---|
| R1 | 3000 standalone（`HOSTNAME=0.0.0.0`）持续运行 | L0.T3 / L2.T5 / 兑换链路 |
| R2 | `oidc_clients.wechat-rag` 白名单含 `http://localhost:3333/auth/aidean/callback` | L0.T4 / 全链 |
| R3 | 当次 `OIDC_CLIENT_SECRET` 下发（主平台只存 hash） | L0.T5 / L2.T4 |
| R4 | 测试账号（邮箱密码或验证码可达） | L3.T4 |
| R5 | `rl:login:*` 基数读数 ×2 + 429 时清键 | L3.B / L4 |
| R6 | 余额对照值 + 充值/消费变更操作 | L4.T1/T2 |
| R7 | seed `logoutUri` 增补（待 bot 端点就绪，M1 一并做） | L6 |
| R8 | （可选）3334 白名单扩展——仅当需并行全链走查 | §0.3 |

---

## 附录 A：已知坑位速查表（A 方指引 §7 全量收录 + 本侧增补）

| 症状 | 根因/处置 | 来源 |
|---|---|---|
| 容器兑换 503/50002 ConnectError | 3000 非 `HOSTNAME=0.0.0.0` standalone → 上报 A 方重启，不自行改 | A§7 |
| Location 出现 `0.0.0.0:3000` | 窗口污染信号：**停手**，netstat→CommandLine→父进程链取证，拦截器 fulfill 改写 `localhost:3000` 与 standalone 问题**解耦** | A§7+skill |
| 兑换 401 | 查 backend Env：`AIDEAN_ISSUER` 必为 `host.docker.internal:3000`、secret 与主平台一致 | A§7 |
| `page.route` 改写 Location 不可靠/宿主 curl 000 | 分段导航或 authorize route 拦截（`maxRedirects:0` + 白名单域改 `localhost:3333`、**redirect_uri 原样保留**）；拦截器必须在 `page.goto` **前**注册 | A§7 |
| 429 | `rl:login:*` IP 限流（主平台 Redis）→ A 方清键；负面用例集中执行降低触发 | A§7+H4 |
| 3333 转发约 15s ERR_CONNECTION_RESET | 等 30s 复测一次，非代码问题 | A§7 |
| Playwright health ECONNREFUSED `::1:3000` | 双栈 flaky → `NODE_OPTIONS=--dns-result-order=ipv4first` | A§7 |
| **compose 项目劈裂**（backend 双网丢失、旧容器残留） | 必须 `docker compose -p aideanbot ...`，禁裸 `up`（A-T5 教训） | 本侧增补 |
| **mock 用例误跑 MOCK=false 容器**（SSO 502 假红） | 双口径铁律：mock→3456 烘焙产物；真实→3333 复用容器（A-T17.1） | 本侧增补 |
| Playwright 浏览器 revision 不匹配（门禁全 NaN） | `pnpm exec playwright install chromium` 幂等补装，不改依赖 | 本侧增补 |
| env 缺失 vs 网络不通混淆 | 先 `docker inspect` 实测运行中容器 env 与 compose 逐项比对（旧配置遗留实例嫌疑），再用容器内探针区分根因 | 本侧增补 |
| PowerShell `curl` 是 Invoke-WebRequest 别名 | 一律用 `curl.exe` | 本侧增补 |
| state TTL 600s | 走查中途停留 >10min → state 过期 10002，重新 login 即可，勿误判缺陷 | 本侧增补（`config.py:33`） |
| e2e 必须串行 | `workers=1`/`fullyParallel:false`（会话态 localStorage 依赖），勿改并发求快 | 本侧增补（`playwright.config.ts:23-24`） |

## 附录 B：M0 验收门（通过判据）

**M0 通过 =** L0 全绿 ∧ L1.T1=12 passed ∧ L1.T2 绿 ∧ L1.T4b=9/9 ∧ L2 全绿（含 T5 探针 200、T6 四项）∧ L3.A 两轮全绿 ∧ L3.T12/T13 码位正确 ∧ L4.T1/T2 一致 ∧ L5 清理复核。
**非门槛项**（单独列报告）：L1.T3 全量回归、L4.T3/T4/T5/T6、L6/M1。

## 附录 C：前提与局限（推敲后幸存的边界声明）

1. **A 方声明类事实**（seed 白名单内容、3000 standalone、12 用例基线、token 端点错误语义）无法在本仓代码内证明，全部以 L0 探针独立复核或标 R 依赖项；探针失败即停层上报，不自行补救。
2. **L3 主路径预期基于 compose 双变量注入推得**（Location host=localhost:3000、redirect_uri=localhost:3333）；A 方指引的 host 改写流程降级为预案——两者不矛盾，差异来源是 `AIDEAN_PUBLIC_URL` 是否为空串，以 L2.T4 实测为准。
3. Docker 引擎历史掉线（单日最多 6 次）属环境风险：触发 15s 修复序列或上报，不追溯为用例失败。
4. 时间预算为本地经验口径；L4.T5 性能数据仅登记，不构成生产基线。
5. 本方案不含 M1/M2 执行细则（模块注册表占位）；M2（AideanWiki 绑定）仍阻塞于外部输入：**AideanWiki 仓库路径 + 技术栈（自研 or MediaWiki、后端语言）**。
6. 本文件为 docs-only 产物，未触碰业务代码；后续任何代码增量（如 M1 端点）须走六步开发循环并回写台账。
