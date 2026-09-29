已完成全量只读审阅与源码实证。以下是三轮推理的产物。

---

## 〇、原始需求（复述）

> 依次递归阅读本项目下全部文档，理解项目初衷。设计完整的项目开发流程，创建详细的、最小原子化的、多个大纲层级的计划方案。准备就绪后，等待我确认后才能执行。

---

## 一、已递归阅读的文档（实证清单）

| 层级 | 文档 | 状态 |
|---|---|---|
| 根 | `README.md`（含未提交修改）、`AGENTS.md`、`.gitignore` | 已读 |
| `.docs/立项分析/` | `ChatGPT_V1.md`、`ChatGPT_V2.md`（50 节）、`信息源知识库机器人闭环架构设计.docx`（212 段，全文提取） | 已读 |
| `.docs/主平台统一账号接入说明/` | `子平台SSO接入指南.md`（全文 263 行）、`主平台README.md`、`主平台API接口文档.md` | 已读 |
| `.trae/documents/` | `AideanBot完整开发计划.md`（247 行，状态"待确认"） | 已读 |
| `docker/` | `.env.example` | 已读 |
| `.project/` | 7 个参考仓库（LangBot / wandao / wechat-clawbot / firecrawl / lux / reclip / SHY-downloader），对 LangBot 与 wandao 做了**源码级实证** | 已实证 |

---

## 二、第一轮（发散）5W1H

**What** — 仓库是**纯绿地**：无任何业务代码，`git log` 仅 1 次初始提交，`.project/` 下 4057 个文件是 7 个只读参考仓库。**且仓库里已存在一份状态为"待确认"的完整计划**（`.trae/documents/AideanBot完整开发计划.md`）。因此本任务不是"从零写计划"，而是**审计既有计划 + 修正其事实错误 + 补齐其产品决策空洞**。

**Why** — 把「看文章—记笔记—问问题」压缩为一次对话：发链接即建库，知识库自动生长、即时生效。立项分析历经 V1→V2 两版自我推翻，V2 的核心结论是：**先建立自己的领域模型（Source→Subscription→ContentAsset→KnowledgeSpace），再把 LangBot/wandao/firecrawl/redfox 当作 Provider 插进去**，而非拼装。

**Where/When** — 实施范围锁定公众号图文闭环（架构 docx 阶段一~三）；视频源/会员积分为阶段四占位。docx 时间轴：阶段一 1-4 周、阶段二 5-8 周、阶段三 9-12 周、阶段四 13-20 周。

**Who** — AideanBot = 知识生产系统；LangBot = 机器人运行时 + RAG 引擎；Aidean 主平台 = IdP + 钱包 + LLM 计费网关（`wechat-rag` client 已 seed）。

**How** — 采集链 SourceResolver → ContentDiscoverer(Redfox) → ContentExtractor(wandao 移植→firecrawl 降级) → ContentNormalizer(质量评分) → ContentAsset → LangBot KB → RAG 回答。

**What if** — 主平台契约变更、Redfox 能力不达预期、公众号反爬、LangBot 版本漂移，均需 ADR + 回退矩阵兜底。

---

## 三、第二轮（苏格拉底拷问）—— 六个被源码反证的论点

我对既有计划逐条向 LangBot v4.10.9 与 wandao 源码发起致命追问，**5 条存活、4 条被推翻**：

**❌ 推翻 1：`POST /bots/<uuid>/sync` 是 LangBot 的 API Key 管理端点**
双向钢人：计划声称调 `/bots/<uuid>/sync` 驱动 pipeline。实证 `webhooks.py:10` 为 `@group_class('webhooks', '/bots')`，`webhooks.py:18` 为 `/<bot_uuid>/<path:path>`，`auth_type=NONE`；`http_bot.py:254` 明确 `path == 'sync'` → `_handle_inbound(sync=True)`。
**幸存结论**：端点路径巧合正确，但**契约性质完全不同**——`/bots/<bot_uuid>/sync` 走 HMAC 签名头（`inbound_secret`），**不需要 `lbk_` API Key**；body 强制 `session_id` + `message`(MessageChain)。`lbk_` Key 只用于 `/api/v1/platform/bots`（`bots.py:9`）与 `/api/v1/knowledge/bases`（`knowledge/base.py:8`）管理面。计划的鉴权模型需整体修正。

**❌ 推翻 2：T0.5「多知识库隔离」必须靠活体实测才能定案**
实证：`preproc.py:278` 从 `pipeline_config['ai']['local-agent']['knowledge-bases']` 取值 → `preproc.py:283` 写入 `query.variables['_knowledge_base_uuids']` → `preproc.py:286-296` **随后**触发 `PromptPreProcessing` 事件 → `localagent.py:375` 读取该变量执行检索。
**幸存结论**：**变量先写、事件后发**，因此自定义 `PromptPreProcessing` 插件可按 `query.session.launcher_id` 动态改写 KB 列表——多库隔离**不 fork 核心即可实现**，T0.5 可从"实测"降级为"代码验证+最小验证"。
**反向钢人**：依赖下划线私有变量属隐式契约，LangBot 后续版本可无预告移除；且 `localagent.py:419-423` 已向 KB 传入 `session_name`，KnowledgeEngine 插件侧亦有条独立路由路径。故结论需 ADR 锁定 + 版本 pin。

**❌ 推翻 3：wandao 移植是"纯 HTTP，无 Electron 依赖"**
实证 `export_wechat.py`：存在**双路径**——`fetch_article_payload_direct`(L459) 纯 HTTP，与 `connect_wechat_browser`(L536) 经 `wandao_core.browser` 走 CDP。且 L352/L357 强制「仅支持 HTTPS 的 mp.weixin.qq.com 单篇文章链接」并要求 `__biz` 与 `mid` 同时存在。
**幸存结论**：移植范围必须显式限定为 direct 路径；且 **SourceResolver 必须处理"无查询参数的裸 URL 无法定位公众号"这一硬约束**——这是计划完全遗漏的失败分支。

**❌ 推翻 4：T0.9「compose 起一个 LangBot 容器」**
实证 LangBot `AGENTS.md`：Quart/Hypercorn :5300、plugin runtime :5400、box runtime :5410，依赖由 `uv` 管理（Python >=3.11,<4.0）。
**幸存结论**：LangBot 是多运行时编排，不是单容器；`docker compose up` 一次到位的假设不成立，需新增独立任务。

**✅ 存活：无明文密钥入库**
`git ls-files` 中 22 个 `.env*` 全部为 `.env.example`/`.template`；`.project/wechat-clawbot/.env` 与 `docker/.env` 均被 `.gitignore` 覆盖。README 的明文 key 删除已在工作区完成（未提交）。

**✅ 存活：LangBot 事实基线**
`pyproject.toml:3` = `4.10.9`；`knowledge/base.py:8` = `/api/v1/knowledge/bases`；`knowledge/base.py:135` = `/<uuid>/retrieve`；`apikey.py:109` = `lbk_` 前缀；`knowledge_engine_plugin_id` 插件架构全链存在。

**🕳 发现的产品决策空洞（计划最大缺口）**
计划定义了 `KnowledgeSpace` 领域模型，也定义了对话流，**但从未定义"一次会话提问时，从哪个（哪些）KnowledgeSpace 检索"**。多空间产品不解决此规则，T1.10 无法实现。docx §4.4 的"每用户独立命名空间"与 V2 §三十五的"多空间"在此处正面冲突，需裁决。

---

## 四、第三轮（终稿）—— AideanBot 开发计划 v2

> 四层大纲：阶段(L0) → 工作流(L1) → 原子任务(L2) → 验收断言(L3)。每个 L2 任务可独立提交、独立验收。
> 相对既有计划的变更标记：`[新增]` `[修正]` `[升级]`

### L0-M0 能力实证与工程奠基

#### L1-G0.0 仓库卫生与决策基线 `[新增]`
- **T0.0.1** 提交 README 安全整改（当前工作区未提交的 key 删除） → A: `git grep -n "ak_"` 零命中
- **T0.0.2** 裁定 `.project/` 4057 文件的版本策略（保留 / git submodule / 移出仓库） → A: 决策入 ADR-0000
- **T0.0.3** LangBot 版本 pin：锁定 `4.10.9`（tag 或 submodule commit） → A: 版本可复现声明入 `.docs`
- **T0.0.4** 输出 **ADR-0000 定位裁决**：以 V2 §三十八为准，推翻 docx §3.2 中"LangBot=接入层/适配器"的定位；确立 LangBot=运行时+RAG 基础设施 → A: ADR 含 docx 冲突点对照
- **T0.0.5** 输出 **docx 六模块 ↔ 计划 monorepo 映射表**（bot/ingestion/knowledge/retrieval/platform/web → backend/app/services/* + frontend） → A: 映射表无未覆盖模块

#### L1-G0.1 外部契约实证
- **T0.1.1** Redfox Key 轮换与注入（现仓库无任何可用凭据） → A: 新 Key 仅入 `docker/.env`
- **T0.1.2** Redfox 能力矩阵 12 项（鉴权/wxId>bizInfo>名称定位/分页游标/UUID 稳定性/修改删除标识/限流/计费） → A: 每项 PASS/FAIL + curl 证据
- **T0.1.3** wandao direct 路径移植验证：5+ 真实文章 HTML→Markdown，**含"缺 `__biz`/`mid`"负样本** → A: 成功率 + 质量缺陷清单 + 裸 URL 失败用例
- **T0.1.4** LangBot 知识库全链路（建库/ingest/retrieve/向量后端/在线可见性延迟） → A: curl 全链路记录 + **写入→可检索延迟实测值**
- **T0.1.5** 多库隔离**静态验证**（替代原实测）：确认 `preproc.py:283→286` 事件顺序与 `localagent.py:375` 读取路径 → A: 代码证据行号记录入 ADR-0001
- **T0.1.6** 主平台 SSO 五步全链 + wallet 实时查询 → A: 五步 curl 记录
- **T0.1.7** LangBot LLM Provider 指向主平台网关计费验证 → A: 网关侧扣费流水
- **T0.1.8** **Redfox 账号定位成功率专项**（3+ 真实公众号） → A: 成功率结论，决定整库模式是否降级

#### L1-G0.2 架构定案
- **T0.2.1** ADR-0001 RAG 主引擎（含 `_knowledge_base_uuids` 隐式契约风险与版本 pin 约束）
- **T0.2.2** ADR-0002 消息拓扑（含 `/bots/<uuid>/sync` HMAC 签名契约 vs `/api/v1/platform/*` API Key 契约的**双轨鉴权表**）`[修正]`
- **T0.2.3** ADR-0003 **会话→知识空间解析规则**（见下方澄清问题 Q2）`[新增]`

#### L1-G0.3 工程脚手架
- **T0.3.1** monorepo 骨架（backend/frontend/docker/.docs）
- **T0.3.2** FastAPI hello + 健康检查 + 统一响应 `{code,message,data,requestId}`
- **T0.3.3** **LangBot 多运行时编排**（api:5300 / plugin-runtime:5400 / box:5410，`uv sync`）`[修正]` → A: 三端口健康检查全绿
- **T0.3.4** PG + Redis 编排
- **T0.3.5** CI 基线（lint → type-check → 单测 → build）
- **T0.3.6** 数据库 v1 全表 + Alembic 首迁移（users/knowledge_spaces/sources/source_subscriptions/article_manifests/content_assets/knowledge_documents/jobs/job_items）
- **T0.3.7** `.docs/` 文档体系（索引/需求/API/开发流程，对齐主平台六步循环）

### L0-M1 公众号单篇闭环 MVP

#### L1-G1.1 认证与领域骨架
- **T1.1.1** 分层契约（api/services/repositories/core，Route 不写业务）
- **T1.1.2** 错误码段位登记（1xxxx 用户/2xxxx 采集/3xxxx 知识库/5xxxx 系统）
- **T1.1.3** **失败分类枚举契约**：`TEMPORARY / PERMANENT / RATE_LIMITED / CONTENT_REMOVED / AUTH_REQUIRED / MALFORMED_URL` + 用户可感知文案映射 → A: 每类至少 1 个用例（V2 §四十二 要求"真正设计失败"）`[升级]`
- **T1.1.4** SSO 接入（authorize→callback→服务端会话；state 强校验；refresh 链轮换 + 旧值复用拒绝）
- **T1.1.5** `/auth/me` 聚合 userinfo + 实时 wallet（**余额不落库**）

#### L1-G1.2 采集链
- **T1.2.1** SourceResolver（域名路由表可扩展；**裸 URL 无 `__biz`/`mid` → `MALFORMED_URL`**）`[修正]`
- **T1.2.2** ContentExtractor(wandao direct 路径移植，httpx)
- **T1.2.3** 图片下载与本地化（`download_image`/`rewrite_images` 逻辑移植）
- **T1.2.4** ContentNormalizer 质量评分（正文长度/标题/图片比/导航噪声 → `<0.6` 失败、`0.6~0.85` 走降级链、`>0.85` 入库）
- **T1.2.5** firecrawl 降级 Provider **接口预留**（不接真实服务）

#### L1-G1.3 任务与知识
- **T1.2.6** Job 持久化状态机（PG + Celery，`QUEUED→RUNNING→SUCCEEDED/PARTIAL_SUCCESS/FAILED`，`idempotency_key` 唯一约束，progress 心跳）
- **T1.2.7** LangBot KB 网关（**建库/ingest/retrieve 走 `lbk_` Key**；**对话走 `/bots/<uuid>/sync` HMAC 签名**——两个客户端分离）`[修正]`
- **T1.2.8** 单篇建库编排 Job(SINGLE_FETCH)：Extractor→Normalizer→Asset→ingest→`KnowledgeDocument: FETCHED→INDEXED→READY`
- **T1.2.9** **索引即时可见性验证**：入库→可检索延迟 < 阈值（依赖 T0.1.4 实测值）`[新增]`

#### L1-G1.4 对话与前端
- **T1.2.10** 对话流 v1（链接识别→选择卡片〔本篇/整库置灰〕；普通消息→LangBot sync→回复）
- **T1.2.11** **空间解析器**：按 ADR-0003 将 `session_id → knowledge_base_uuids`，经 PromptPreProcessing 插件改写 `_knowledge_base_uuids` → A: 单测覆盖多空间切换
- **T1.2.12** Next.js 骨架（顶栏唯一搜索框、中文、多浅色主题、SSO 登录态、空间列表、聊天卡片交互）
- **T1.2.13** M1 验收门禁：真实链接→选本篇→数秒入库→提问→带引用回答 → A: e2e 脚本全绿 + `.docs` 回写

### L0-M2 整库 + 订阅增量 + 微信通道（L2 概要）

- **T2.1** Redfox Discovery Provider（定位/清单/分页/Redis 缓存）
- **T2.2** Manifest Snapshot + Diff（`external_id + content_hash` → NEW/UPDATED/REMOVED/UNCHANGED）
- **T2.3** FULL_IMPORT Job + job_items（限流、逐篇即索引、PARTIAL_SUCCESS 聚合、单篇重试）
- **T2.4** Subscription 生命周期 + Celery beat 增量调度 + 长期无更新自动降频
- **T2.5** clawbot 通道（`/users/{account_id}/{wechat_user_id}/send` 已实证存在于 `routes.py:569`；绑定→SSO sub 关联；回调→对话流；主动消息回执）
- **T2.6** 对话流 v2（整库卡片激活：清单 count 预估、确认/取消；命令词）
- **T2.7** M2 门禁：≥100 篇整库 + 人工制造部分失败 + 增量自动入库 + 微信真机全链

### L0-M3 管理后台与打磨（L2 概要）

- **T3.1** 信息源管理页 / **T3.2** 任务中心页（复用 job_items）/ **T3.3** 文章浏览页（Markdown 渲染 + 原文跳转）
- **T3.4** 引用溯源全链可点（回答→文章→原文 URL）
- **T3.5** BillingPolicy 表 + 积分预估/冻结/结算骨架（**不写死 1/1.5/2 积分每分钟**，V2 §四十八已删除）
- **T3.6** 可观测（结构化日志、缓存失效、慢任务告警）
- **T3.7** 生产部署（compose.prod + 环境变量 + 备份策略）
- **T3.8** M3 门禁 + `.docs` 全量回写

### L0-M4 视频源 + 会员积分（占位，不在本次实施）
yt-dlp 抽象（lux/cobalt fallback）→ ffmpeg 抽音 → ASR 带时间戳 → LLM 三段式摘要 → `ContentAsset(content_type=video)`；tier 门禁 + 冻结-实扣-退款闭环。

---

## 五、澄清问题（需你裁决后才动工）

**Q1：LangBot 多知识库路由的实现路径？**
- A. **每 KnowledgeSpace 建独立 bot_uuid + pipeline**（零插件依赖、全走公开契约，多库时按空间路由到对应 bot）— **推荐 M1 用此方案**
- B. 单 bot + 自定义 PromptPreProcessing 插件改写 `_knowledge_base_uuids`（更优雅，但依赖下划线私有变量）
- C. 走 §八 R2 回退：AideanBot 自调 retrieve + 亲调主平台网关生成回答

**Q2：一次会话提问时检索哪些知识空间？**（ADR-0003 必填）
- A. **仅"当前选中空间" + 显式"全部空间"开关** — 推荐，符合隐私直觉
- B. 永远聚合用户全部空间
- C. 按消息中来源自动路由

**Q3：计划文档落盘位置？**
- A. **新建 `.docs/开发计划/PLAN.md`**（对齐主平台规范；且 `.trae/` 当前未入库，不宜作为真源）— 推荐
- B. 覆盖更新 `.trae/documents/AideanBot完整开发计划.md`
- C. 两处同步

**Q4：M0 中依赖外部凭据的任务（T0.1.1/T0.1.6/T0.1.7/T0.1.8）现在能做吗？**
仓库内无任何 Redfox Key / 主平台 clientSecret。
- A. 你先下发凭据，我全量执行 M0 — 推荐
- B. 先执行不依赖凭据的部分（G0.0 全部 + T0.1.3 wandao 移植 + T0.1.5 静态验证 + G0.3 脚手架）

**Q5：`.project/` 4057 个参考文件留在版本库吗？**
- A. 保留现状（检索方便，仓库体积大）
- B. 改为 git submodule（可追踪上游更新）— 推荐
- C. 移出仓库，改为独立参考区

---

**局限性与前提声明**：本计划基于 2026-09-04 时点的主平台文档与 LangBot `4.10.9` 源码静态实证；`_knowledge_base_uuids` 与 `/bots/<uuid>/sync` 均非官方文档化的稳定契约，任何 LangBot 升级需重跑 T0.1.4/T0.1.5。Redfox 全部能力项未经实测，整库模式可行性以 T0.1.8 结论为准。

**当前状态：Plan Mode，零文件改动，未提交任何变更。等待你确认后再执行。**