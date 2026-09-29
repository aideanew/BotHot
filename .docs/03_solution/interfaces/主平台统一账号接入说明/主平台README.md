# Aidean · 开发文档中心

> 版本: v2.1 | 更新: 2026-09-03 | 变更: 新增 §8.8 M-SSO 里程碑（主平台 IdP 化：RS256/轮换链/tokenVersion/OIDC 核心子集 7 端点 + 服务间计费查询）；ADR-0002
> 维护口径：本文档中心是 **Aidean 主平台（AI 大模型性能天梯图，代号 AigcLadderDiagram）** 的唯一开发真源。
> 历史详实底稿位于：`.example/history/AigcLadderDiagram/AigcLadderDiagram/.docs/`（含需求/功能设计/目录结构等 v6.5 版本），本文档中心在其基础上做了**结构收敛与精修**，以"总—分"两层组织。

---

## 一、这个仓库是什么

Aidean 是一个 **AI 模型与云服务的「天梯图」评测平台**：用可视化排行榜 + 多维排序，让开发者和企业"扫一眼"完成模型与云服务选型。

- **主平台（本文档范围）**：模型对比天梯图（大模型榜）、大模型云服务天梯图（模型站榜）、模型详情、对比测评、统一计费网关（一次充值通吃所有接入平台）、余额制付费，并以"产品"入口展示平台产品。
- **平台产品（仅入口展示，开发文档不在本仓库）**：
  - **AideanRag**（原 ragwiki）：知识库产品，已部署 `http://36.134.158.50:10001/`。
  - **WeChatRag**（自媒体知识库，开发中）：分享公众号作品链接自动同步为素材；支持 clawbot / 飞书 / 钉钉对话使用；普通用户仅文字版解析（有额度），图文/视频/音频需 Pro 及以上。
  - **SkillsCloud**（规划中）：只需配置一个 skills/mcp 即可享受全自动化。
- **技术主栈（不变）**：Next.js（App Router）全栈 + TypeScript + Tailwind + Prisma + PostgreSQL + Redis，Docker 部署。
- 其余子平台（synapse 中转站 / twin 数据分身）当前**不在本文档范围**，后续如需纳入再扩展为 monorepo。

## 二、文档导航（TOC）

> 完整的三层索引与定位以 **[文档索引.md](./文档索引.md)** 为权威（本文仅作仓库级入口总览）。

### 核心文档（先读）
| 文档 | 路径 | 作用 |
|---|---|---|
| **目录结构文档** | `.docs/目录结构文档.md` | **Monorepo 分包蓝图（核心交付，v2.0）**：apps/web + packages/*，分层复用与高性能目录细则 |
| 需求文档 | `.docs/02_requirements/需求文档.md` | 产品目标、用户角色、功能需求、排名算法、MVP 边界 |
| 功能设计文档 | `.docs/功能设计文档.md` | 技术栈、架构分层、核心模块实现逻辑 |
| **开发流程** | `.docs/00_governance/开发流程.md` | 项目工作规范：六步循环 / 四级层级 / 六字段字典与增量展开规则 |

### 研发与运维
| 文档 | 路径 | 作用 |
|---|---|---|
| 技术架构文档 | `.docs/技术架构文档.md` | 技术选型、架构决策（ADR 风格）、关键取舍 |
| 数据库文档 | `.docs/03_solution/interfaces/数据库文档.md` | 数据模型、关键表、初始化与迁移 |
| API 接口文档 | `.docs/03_solution/interfaces/API接口文档.md` | URL 规范、认证、错误码、模块接口清单（**响应/错误码权威**） |
| 子平台SSO接入指南 | `.docs/子平台SSO接入指南.md` | 子平台接入主平台账号体系的分步操作手册（授权码流/权益查询/安全红线，对应 ADR-0002） |
| API 架构设计方案 | `.docs/API架构设计方案.md` | API 架构分层、鉴权中间件、分页/限流/缓存、契约测试（对 API 接口文档的补充） |
| UI 设计文档 | `.docs/UI设计文档.md` | 视觉语言、设计令牌、组件规范 |
| 界面交互文档 | `.docs/界面交互文档.md` | 导航/天梯图/详情页/悬浮 Dock 交互规范 |
| 部署运维文档 | `.docs/部署运维文档.md` | Docker 部署、环境配置、运维手册 |
| 开发环境搭建 | `.docs/开发环境搭建.md` | 本地环境、依赖、数据库、Docker、各脚本启动方式 |
| 测试与验收文档 | `.docs/测试与验收文档.md` | 测试分层、E2E 口径、上线门禁 |

### 辅助
| 文档 | 路径 | 作用 |
|---|---|---|
| 旧资产迁移清单 | `.docs/旧资产迁移清单.md` | `.example/history/` 可复用资产台账（来源→目标→状态） |
| 术语表 | `.docs/术语表.md` | 天梯图/倍率/分组/榜单等统一术语 |
| 架构决策记录 | `.docs/03_solution/decisions/` | 每个重大架构决策的来龙去脉（ADR-0001 见结构重构） |
| 文档索引（权威） | `.docs/00_governance/文档索引.md` | 三层索引总表与定位 |

## 三、强约束（全站通用）

1. **主技术栈不变**：Next.js App Router、Prisma、PostgreSQL、Redis 保持不变，不引入额外重框架。
2. **国内可复现**：Docker / Compose / 依赖示例优先使用国内镜像源。
3. **文档即真源**：实现、测试口径以 `.docs/` 为准；如与代码冲突，以当前可运行代码为准并回写文档。
4. **多套浅色主题**：界面永远浅色（无深色模式）；主题切换为多套浅色主色色相间切换；默认中文。
5. **搜索框唯一位置**：搜索框仅存在于顶部导航栏，筛选栏内不得出现第二个搜索框。

## 四、本次重构说明（2026-08-18）

- 基于 `.example/history/` 下的半成品，重新设计了主平台的项目结构与文档体系。
- 本轮**只重建结构与文档，不搬动历史代码**；历史代码继续保留在 `.example/history/`，待后续按《目录结构文档》蓝图迁移。
- 核心决策见 [ADR-0001 结构重构](./ADR/ADR-0001-结构重构.md)。

## 五、范围收敛说明（2026-08-26）

- **天梯图五类收敛为两类**：保留 **模型对比天梯图**（大模型榜）与 **大模型云服务天梯图**（原 API 站/模型站榜更名）；**取消** Skills / MCP / Agent 三类榜单。
- **资源模块整体取消**：资讯 / Agent / MCP / Skills 定时采集与聚合不再纳入范围（当批导航为五项；同日稍后 UI 批次扩为七项，见下节）。
- **新增平台产品展示口径**：AideanRag（原 ragwiki，已部署）与微信公众号知识库（开发中），仅做入口展示，不改变本仓库文档边界。
- 同步升版文档：需求文档、术语表、功能设计、目录结构、API 接口/架构、数据库、界面交互、Docker 配置、旧资产迁移清单。

## 六、统一计费网关口径（2026-08-26 补充）

- **双模式供给**：优先用户自有平台 API Key，未配置走平台 Key 池（每站多 Key 分流/并发）。
- **控制台双形态**：通用版（用户将具体模型绑定至 Opus/Sonnet/Fable/Haiku 等级档）与专业版（1~99 优先级）共享底层路由配置；等级映射由用户定义，free 等级由后台定义默认免费模型。
- **计费三路径**：本系统计费（上游单价×加价率×Token 数×倍率，默认 1.0 不加价）/ 上游计费（用户自有 Key）/ 套餐直连（该平台规则，倍率不生效）；限时优惠直接影响计费价（折扣或免费）。
- **价格透明铁律**：展示价与官方一致；加价率与 Token 倍率用户不可见。
- **MVP 归属**：统一计费网关 + 微信扫码登录进入 MVP；套餐兑换、兑换码第二阶段。
- **自定义渠道**：用户自填 base_url + Key 接入任意平台，不扣余额（费用自理）、无限制免费中转。

## 七、UI/UX 规格口径（2026-08-26 UI 批次）

- **一级导航（七项）**：模型 / 产品 / 价格 / 文档 / 路线图 / 合作 / 关于；Logo 点击回首页。
- **首页结构**：菜单栏 → banner → 平台介绍 → 模型 → 产品 → 路线图 → 合作 → 关于（关于置底）；滚动动态加载；banner 之下正文左右留白。
- **设计参考**：SiliconFlow（结构与滚动节奏）/ Canva 中国（banner 与长页引导）/ Figma（信息架构与留白）。
- **主题**：多套浅色主题（主色色相切换），永远浅色、无深色模式；默认中文。
- **WeChatRag**（原"微信公众号知识库"）：自媒体知识库，clawbot/飞书/钉钉接入；普通用户仅文字版解析（有额度），图文/视频/音频需 Pro 及以上。**SkillsCloud**（规划中）加入产品矩阵。
- **控制台核心信息**：应用"流动模糊渐变"特效（Web 实现规范见《UI 设计文档》§7）。

## 八、里程碑进度（2026-08-28/29/30）

### 8.1 MVP 四模块全部收官

| 模块 | 里程碑 spec | 验收 |
|---|---|---|
| 天梯图 | implement-ladder-module | 双榜出数、矩阵交互、e2e |
| 用户系统 | implement-auth-module | 邮箱注册登录 + JWT 双令牌 |
| 余额账本 | implement-billing-module | 双录账本 / hold 预扣 / 充值闭环 / 对账，单测 16 |
| 统一计费网关 | implement-gateway-module | 路由链降级 / OpenAI·Anthropic 双协议 / 预扣捕获 / 免费额度 / 自定义渠道，单测 44 + e2e gateway-flow |

测试资产：web 单测 130 + shared 46 + e2e 15，生产 `next build` 通过。

### 8.2 CI 硬门禁（G-2 实装）

`.github/workflows/ci.yml` 双 job 全绿：**verify**（铁律1 文档检查 → prisma generate → 双包 tsc --noEmit → 双包单测 → next build）+ **docker-build**（buildx，生产镜像可构建性持续验证）+ **compose config 校验**。首跑起累计抓出并修复：Dockerfile 漏拷 shared manifest（zod 未装/类型退化）、web 冗余 zod@4 与 shared zod@3 双版本冲突、withApi 丢 ctx、_mock 私有文件夹等。

### 8.3 品牌资产（用户设计稿）

- 素材：`.docs/Aidean文字设计.svg`（2048 描摹矢量）；生成管线去除米色背景与"豆包AI生成"水印残留（33 path）。
- 落位：`public/aidean-logo.png`（header 横版）、`app/favicon.ico`（16/32/48 "A"特写）、`app/icon.png`（512 "A"特写）、`app/apple-icon.png`（180 全字）、`app/opengraph-image.png`（1200×630 宣纸底全字）。
- 口径：favicon 小尺寸用 "A" 特写保辨识度，大尺寸用全字——浏览器按显示尺寸自动选择。

### 8.4 本地 Docker 部署验证（三层根因修复后打通）

引擎启动失败的三层根因与修复：

1. **Windows 功能「虚拟机平台」被禁用** → `dism` 启用（HCS_E_SERVICE_NOT_AVAILABLE 消失）；
2. **docker-desktop WSL 发行版内部状态损坏**（VM init 持续无响应）→ `wsl --unregister docker-desktop` 重建（零损失：此前无成功镜像）；
3. **WSL 2.6.3 引擎僵死 + 镜像源失效** → 升级 WSL 2.7.120；`.wslconfig` 限 8GB/8CPU；daemon.json mirror 更换（docker.1panel.live 首位，移除失效的 docker.aityp.com）。

验证结果：`docker build` 本地成功产出 `aidean-web:latest`（252MB），容器连接宿主 PG/Redis 实跑 `200`（62KB 首页渲染）——**本地 Docker 部署链路全通**。

重启复核（2026-08-30）：重启后引擎 29.4.3 正常应答、`docker-desktop` WSL 发行版 `Running`、镜像持久化完好——三层根因均已修复，故障关闭。排查链完整沉淀至《[部署运维文档](./部署运维文档.md)》§8。

### 8.5 当前待办（发布事务）

- 生产服务器供给 + 环境变量五件套（`docker/.env.example` 模板）→ `docker/docker-compose.prod.yml up -d` 实弹部署
- 真实支付渠道接入（替换 dev mock-pay）、微信扫码凭据下发（qrcode 路由预留）
- 第二阶段候选里程碑：对比测评（¥2/模型/次）、API Key 网关鉴权、流式 SSE、套餐直连/兑换码（均需先立项评审）

### 8.6 M-PERF 性能里程碑（2026-09-03，首次点击延迟专项）

**归因**（代码取证 + prod 实测，非猜测）：首次点击模型延迟 = 无预取（`router.push`）+ 无 loading 边界（导航阻塞等完整 RSC，零反馈）+ 首屏 `opacity-0`（SSR 已回但需 hydration 点亮 + 500ms 动画）+ 详情页 force-dynamic 现算且每请求 2×DB + dev 按需编译放大；另发现独立延迟源 `next.config.mjs` 重定向环（`/models→/aidean→/models`，`/aidean` 404）。

**落地**（感知 → 预取 → 去重 → 缓存，顺序不可换）：
1. `(web)` 组 + `/models/[slug]` 补 loading 骨架（预取前提）；
2. 天梯矩阵 78 单元格 `button+push` → 语义化 `<Link>`（slug 优先 URL，SEO+预取双收益；图表 canvas 保留 push）；
3. `RevealOnScroll` 去 JS 化：纯 CSS 200ms 进场即播，修「超高 section 永久不可见」边界缺陷；
4. 详情页 `React.cache()` 去重（2×→1×）+ `revalidate=3600` ISR 化（**prod 实测二击 11ms，X-Nextjs-Cache: HIT**）；
5. 重定向环整组拆除（3 组 redirects/rewrites）；
6. 配套架构改造：头部登录态迁客户端槽位（`HeaderSession` 探测 `/api/v1/auth/me`）——渲染树禁携 `cookies()`，否则 ISR 路由运行时 500（Next 14 非 PPR 无动态洞机制）。

**实测基线与回归红线**：见《[测试与验收文档](./测试与验收文档.md)》§五；进场动画口径修订：见《[UI设计文档](./UI设计文档.md)》§3。B3（详情页 Redis 读穿）经裁决**弃用**：ISR 页缓存命中最终产物，叠加属过度设计。

### 8.7 M-WIDE / M-LADDER 里程碑（2026-09-03，全宽化 + 天梯排行化）

**M-WIDE 全站全宽化**：正文容器弃 `max-w-6xl~7xl` 居中（13 处），改全宽 + 少量留白（`px-4 md:px-6`）；文本块内部 `max-w-2xl/3xl` 自约束保留。依据：大屏居中容器留白过大、排行表需横向信息密度。口径见《[UI设计文档](./UI设计文档.md)》§2.4。

**M-LADDER 天梯排行化**（参照快科技 CPU 天梯图形态，用户指定参考）：
- 数据形态：5 分档矩阵（行=`90–95` 档位 × 列=厂商，7 行）→ **快科技式扁平排行**（`entries[rank]`，一行=一个模型/站点；实测 78 行/站榜 20 行）；
- rank 语义：恒为综合分降序的同分并列名次（competition ranking 1,2,2,4），与展示排序解耦（按价格排序时 rank 仍呈现分数名次）；
- 契约破坏性变更：`/api/v1/ladder` 响应 `rows` → `entries`，`LadderMatrixData` 类型删除，`LADDER_CACHE_VERSION` v2→v3；见《[API接口文档](./API接口文档.md)》§5.2；
- 组件：`LadderMatrixTable` 删除 → `LadderRankingTable`（排名徽章 Top3 强调 / 厂商徽章行内化 / 双榜列适配）；柱状图改综合分 Top12 模型柱（厂商品牌色着色）；
- 单测重写 15 例全绿（同分并列 / rank 解耦 / 缓存 v3 / stations / 筛选 / 自定义公式 / route 信封）。

**遗留增强（候选）**：性能区段标记（高性能/中/低，排行数据天然支持）；模型量千级时排行表虚拟滚动。

### 8.8 M-SSO 里程碑（2026-09-03，统一认证 / 主平台 IdP 化）

**决策**（详见 [ADR-0002](./ADR/ADR-0002-SSO选型.md)）：主平台作为 Identity Provider，自研精简 OAuth2 授权码流（+PKCE）+ RS256 非对称签名，运行于主站 route handlers；否决共享密钥直发 / 成品 IdP / CAS / 共享 Cookie 四路（记录在案）。

**阶段 0 安全前置（全部落地）**：
1. HS256 → RS256（keys.ts 密钥束：env 私钥 → Redis 持久化 → 内存兜底；kid 轮换位）；
2. claims 补全 `iss`/`aud`（主站=aidean-web，产品=clientId 隔离）/`jti`/`ver`；
3. `refresh_tokens` 表 + 轮换检测：**旧代复用 → 整链撤销**（prod 实测：重放后链上新代同时失效）；
4. `users.token_version`：改密/封号 ver++ 全端失效；
5. 登录 IP 限流（Redis 固定窗口）+ 失败锁定落地（failedLoginAttempts/lockedUntil 强制执行）。

**阶段 1 OIDC 核心子集（7 端点全部 prod build 注册）**：discovery/jwks/authorize/token（code+refresh 双 grant）/userinfo/revoke/introspect；`oidc_clients` 表 + 三个 first-party seed（aidean-rag/wechat-rag/skills-cloud，secret 经 `OIDC_CLIENT_SECRET_*` env 注入）。

**子平台权益接入（P1.7/P1.8）**：`getSessionFromBearer` 双鉴权（主站 aud 或活跃 client）；`GET /api/v1/internal/billing/wallet`（scope `wallet:read`）实时查询余额/tier——子平台余额/套餐**实时读取**而非同步，AI 消费扣费走统一计费网关（§8.3）自动入主站账本。

**prod 实测全链路**：authorize 未登录 307→登录页 → 登录后 307 回 redirect_uri 带 code+state → token 兑换（RS256/Bearer/900s）→ userinfo 标准形态 → **code 重放拒绝**（GETDEL 原子）→ refresh 轮换 200 → 旧值复用拒绝 + 整链撤销生效。单测 133/133 全绿。

**遗留（二期/三期）**：back-channel 单点登出；consent 页；JWKS 轮换自动化；接入方 > 5 或含第三方时以 `oidc-provider` 独立 idp 演进（契约兼容）。
