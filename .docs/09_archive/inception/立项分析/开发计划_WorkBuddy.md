完整版更新，下方有残缺版


逐条回到证据后，**我上一轮有 4 条断言需要撤销或降级**。以下是裁决。

---

## 一、审查方法

我把上一轮自己写的每一条"发现"当作**待证伪命题**，要求每条都有可引用的代码行号或文档行号。结果：11 条断言中 **3 条假阳性、2 条夸大、1 条方向搞反、5 条成立**，并新增 4 条事实。

---

## 二、第二轮：致命追问与双向钢人

### ❌ 撤销 A1 —— 我误判了计划的鉴权模型（假阳性）

我上轮称"计划的 `/api/v1/bots/<uuid>/sync` 路径与鉴权模型错误"。回原文核对：

- 计划 L21/L37/L95/L181 写的全是 **`/bots/<uuid>/sync`**——与我实证出的真实路由 `webhooks.py:10` (`@group_class('webhooks', '/bots')`) + `http_bot.py:254` (`path == 'sync'`) **完全一致**。
- 计划的 `docker/.env.example` 早已把 `LANGBOT_HTTPBOT_SECRET`（注释为"HTTP Bot 适配器的入站签名密钥 inbound_secret"）与 `LANGBOT_API_KEY`（注释为 `lbk_` 前缀）**分成两个变量**。
- 计划 T1.8 明确"建库/ingest/retrieve（lbk_ API Key）"，T1.10 才用 `/bots/<uuid>/sync`。

**双向钢人**：钢人版 A1 会说"计划没写 HMAC 签名头的具体算法"。这成立——`http_bot.py:266-272` 要求 `signature_required` 时用 `signing.verify(secret, body, timestamp, signature)`，而计划未记录 header 名与签名格式。
**幸存结论**：A1 从"架构错误"**降级为文档补全项**（补签名头契约，约半页）。这是我上一轮最严重的一次误判。

### ⬆ 加强 A2/A3 —— 多库隔离证据比我说得更硬

我上轮把 `_knowledge_base_uuids` 定性为"下划线私有变量=隐式契约，风险高"。三条新证据推翻这一定性：

- `localagent.py:373-374` 官方注释逐字写明：`may have been modified by plugins during PromptPreProcessing` —— **LangBot 作者自己把它写成扩展点**。
- `handler.py:627-645` 存在**公开 action** `SET_QUERY_VAR`，实现即 `query.variables[key] = value`；另有 `GET_QUERY_VAR`/`GET_QUERY_VARS`。所以插件**不需要私摸变量**，有正式 API。
- `preproc.py:283`（写变量）→ `preproc.py:286-296`（发 `PromptPreProcessing`）→ `localagent.py:375`（读变量），顺序成立；且仓内已有官方 fixture `skills/.../prompt_probe.py:66` 订阅该事件。

**反向钢人**：公开 action 是公共的，但**被读取的那个 key 名** `_knowledge_base_uuids` 仍是下划线前缀、且没有任何 fixture 示范改它（`prompt_probe.py` 只改 `default_prompt`）。
**幸存结论**：风险从"高"**降为"中低"**；T0.5 可静态定案，但仍需 ADR + 版本 pin + 一条最小集成测试锁住行为。

### ❌ 撤销 A4 —— wandao 确实是纯 HTTP（假阳性）

我上轮称"纯 HTTP 不精确，双路径并列"。回原文：

`export_wechat.py:460` 函数 docstring 逐字写着：
> `"""Fetch only public HTML directly; no cookies, credentials, or proxy are used."""`

实现只用 `urllib.request`（L463-483），带 Chrome UA + `Referer: https://mp.weixin.qq.com/`。CDP 路径（`connect_wechat_browser` L536）**是 fallback，不是并列主路径**。计划的"纯 HTTP，无 Electron 依赖"是对的。

**幸存的真是部分**：`export_wechat.py:357-358` 强制 `__biz` 与 `mid` 同时存在，否则 `raise ExportError`；L352 只接受 HTTPS 单篇链接。**"裸 URL 无法定位公众号"这一失败分支仍然成立**（A5），这是计划真正的遗漏。

### ⬇ 降级 A6 —— LangBot 编排没有我说的那么重（夸大）

我上轮称"多运行时编排，不是单容器，T0.9 低估了复杂度"。读 `docker/docker-compose.yaml` 全文后：

- 必启服务只有 **2 个**：`langbot` + `langbot_plugin_runtime`。
- `langbot_box` 是 **profile 门控**（`profiles: ["box","all"]`），注释明确 `box.enabled: false` / `BOX__ENABLED=false` 即可关闭。

**但换到另一个方向我找到了真实事项**：compose 注释写明"Box off 时 dashboard/skills 列表只读，**sandbox tools、skill 增改、stdio MCP 全部禁用**"——这是一个**静默降级**陷阱，计划完全没提。另外端口事实需修正：compose 发布 `5300`(web+webhook)、`5401`(runtime 控制)、`2280-2285`(平台反向连接)；我上轮引用的 `5400` 来自 AGENTS.md 的容器内默认值。

### ⚠️ 方向搞反 A7 —— 真正矛盾的三方里，计划是异类

我上轮写"以 V2 §三十八 为准，推翻 docx §3.2"。**这个方向错了。**

V2 §三十八 的图里 LangBot 内部三栏是 `Platform Adapters | Pipeline | KnowledgeEngine`，其中 `Platform Adapters → 用户`。docx §3.2 说"接入层（Layer 1）基于 LangBot 适配器对接微信、QQ、Telegram"。**两者一致：LangBot 直接面向用户。**

计划的 D4（"AideanBot 为消息中枢，用户消息全部进 AideanBot"）+ D2（微信走 clawbot）**同时偏离 docx 与 V2**。

**双向钢人**：钢人版会说"AideanBot 只是作为 HTTP Bot 的上游扮演'又一个适配器'，并未否定 LangBot 有适配器能力"。这成立一半——但计划的 M2 明确用 clawbot 取代 LangBot 的微信通道，等于**主动放弃 LangBot 的原生 `wechatpad` 适配器**（`sources/wechatpad.py` 存在，含 `wechatpad.yaml`）。
**幸存结论**：ADR-0000 的题面必须改写成「**IM 适配器归属裁决**」，且必须纳入**第三条选项：LangBot 原生微信适配器**，这条计划从未考虑。

---

## 三、其余断言的裁决

| 断言 | 裁决 | 证据 |
|---|---|---|
| A5 裸 URL 缺 `__biz`/`mid` 不可解析 | ✅ 成立 | `export_wechat.py:357-358` |
| A8 无明文密钥入库 | ✅ 成立，**且比我说得更好** | 22 个 `.env*` 全为 example/template；**无 `.db`/`.log` 被跟踪**（`clawbot.db` 36KB、`.serve.log` 359KB 均未入库） |
| A9 会话→知识空间解析规则缺失 | ✅ 成立 | 计划 §4.3 有 `knowledge_spaces.langbot_kb_uuid`、`knowledge_documents.space_id`，但 T1.10 对话流全文无 session→space 映射规则 |
| A10 计划缺失败设计 | ⚠️ 部分 | 计划 T1.5 已列 `TEMPORARY/PERMANENT/RATE_LIMITED/CONTENT_REMOVED`；我的"升级"准确，但不应表述为"计划没有" |
| A11 `.project/` 4057 文件是仓库卫生问题 | ⚠️ 需修正性质 | `.gitmodules` **不存在** → 是真 vendor 不是 submodule；且 `git ls-files` 显示 `firecrawl/apps/test-suite/load-test-results/` 下 15 张压测 PNG 被提交，证明直接 vendor 上游会把无关产物带进来。**是体积/可追踪性问题，不是泄密问题** |

### 本轮新增 4 条事实

- **N1**：LangBot 原生有 `wechatpad.py` 微信适配器 → IM 适配器归属是**三选一**，不是计划假设的二选一。
- **N2**：建库 API 强制要求 `knowledge_engine_plugin_id`（`knowledge.py:69-70` `raise ValueError('knowledge_engine_plugin_id is required')`），内置引擎 id 形如 `{author}/{name}`（`migration.py:19` `LANGRAG_PLUGIN_ID`）。**计划 T1.8 没有"如何发现合法 engine plugin id"这一步**——不解决则建库必失败。
- **N3**：`GET_QUERY_VAR`/`GET_QUERY_VARS`/`CREATE_NEW_CONVERSATION`（`handler.py:683`，置 `query.session.using_conversation = None`）也是公开 action → 会话重置能力现成。
- **N4**：wandao 微信插件仅 `plugin.json` + `export_wechat.py` + `wechat-export/provider.json`，**无 import、无列表、无历史** → 计划"无历史文章能力"成立，Discovery 职责归 Redfox 正确。

---

## 四、第三轮：修正后的终稿增量

上一版计划主体（M0→M3、四层大纲、回退矩阵）**依然有效**，只需替换以下 8 处。

### 4.1 撤销的"修正"（不要做）
1. ~~修正 D4 的端点路径~~ —— 原计划路径正确。
2. ~~修正 wandao 移植范围（去掉纯 HTTP 说法）~~ —— 原计划正确。
3. ~~重写 ADR-0000 为"推翻 docx"~~ —— 方向错误。

### 4.2 新增/替换的任务
| 编号 | 任务 | 验收断言 |
|---|---|---|
| **T0.0.4'** | ADR-0000 **IM 适配器归属裁决**：LangBot 原生 `wechatpad` / clawbot 独立通道 / AideanBot+HTTP Bot 中枢，三选一并记录与 docx §3.2、V2 §三十八 的偏离理由 | ADR 含三方对照表 |
| **T0.1.2'** | **补 LangBot HTTP Bot 签名契约**：header 名、签名算法、`inbound_secret` 配置项、幂等键头 | curl 样例：合法签名 200 / 篡改 body 40101 |
| **T0.1.5'** | 多库隔离**静态定案 + 最小锁定测试**：走公开 `SET_QUERY_VAR` action 改 `_knowledge_base_uuids`，断言检索范围变化 | 集成测试锁住行为；失败即触发 R2 |
| **T0.1.9 新增** | **发现合法 `knowledge_engine_plugin_id`**：枚举引擎插件清单，确认内置 langrag id 字符串 | 建库 curl 返回 200 而非 ValueError |
| **T0.1.10 新增** | **`BOX__ENABLED=false` 显式关闭 + 验证 sandbox 静默降级未发生** | config 生效证据 |
| **T0.3.3'** | LangBot 编排：2 个必启容器，端口 5300 / 5401 / 2280-2285 | 三端口健康检查 |
| **T1.2.1'** | SourceResolver 增加 `MALFORMED_URL` 分支（缺 `__biz`/`mid`）与用户可感知文案 | 裸 URL 用例断言 |
| **T1.2.11 新增** | 空间解析器：`session_id → knowledge_base_uuids`，经 `SET_QUERY_VAR` 生效 | 单测覆盖多空间切换 |

### 4.3 计划中"复杂度被低估"的更正
上一轮我说 T0.9 低估 LangBot 复杂度——**收回**。2 个容器是常规量级；真正低估的是 **N2（engine plugin id 发现）** 和 **N3/box 静默降级**这两个隐性前置。

---

## 五、需要你裁决的问题（较上轮收敛为 4 个）

**Q1｜IM 适配器归属（ADR-0000，本轮新增第三选项）**
- A. **LangBot 原生 `wechatpad`**（零自建通道，最省；但受 LangBot 版本与微信协议变更约束）
- B. **clawbot 独立通道**（原计划方案；主动消息能力已实证 `routes.py:569`）
- C. **AideanBot 中枢 + HTTP Bot**（原计划 D4；业务流全在自己手里，但需维护签名与 session 映射）
- 我的建议：M1 用 **C**（免微信凭据、测试最快，与计划 D2 一致），M2 再评估 B；**A 作为 C 失败时的回退**而非并行实现。

**Q2｜一次会话提问检索哪些知识空间**（ADR-0003）
- A. **仅当前选中空间 + 显式"全部空间"开关**（推荐，隐私直觉最顺）
- B. 永远聚合用户全部空间
- C. 按消息来源自动路由

**Q3｜计划文档落盘位置**
- A. **新建 `.docs/开发计划/PLAN.md`**（推荐；`.trae/` 当前 0 文件被跟踪，不宜作真源）
- B. 覆盖 `.trae/documents/AideanBot完整开发计划.md`
- C. 两处同步

**Q4｜M0 中依赖外部凭据的任务现在做吗？**
仓库内无任何 Redfox Key 或主平台 `OIDC_CLIENT_SECRET`（`.env.example` 全是 `change-me`）。
- A. 你下发凭据，全量执行 M0
- B. **先做零凭据子集**：G0.0 全部 + T0.1.3 wandao 移植 + T0.1.5' 静态验证 + T0.1.9 + T0.3.3' + G0.3 脚手架

**（次要）Q5｜`.project/` 是否改 git submodule**——`.gitmodules` 不存在，这是真改动；4057 文件含 119 张 PNG/1 个 mp4 等上游产物。建议 A. 保留现状 / B. submodule 化 / C. 移出仓库。

---

## 前提与局限性

- 本轮全部结论基于 LangBot `4.10.9` 与 wandao 的**静态源码读取**，未启动任何进程；`/bots/<uuid>/sync` 与 `SET_QUERY_VAR` 的**活体行为**仍需 T0.1.2'/T0.1.5' 实测确认。
- 我承认上一轮 4 条断言失准（A1/A4 假阳性、A6 夸大、A7 方向反）。本轮未再发现新的反证，但**静态审计的固有边界**是：无法证伪需要运行时状态才能观察的行为（如微信直连是否被风控、Redfox 真实返回结构）。
- 视频源与会员积分为 M4 占位，本次不实施。

**状态：Plan Mode，零文件改动。等待你确认后再执行。**

-----
残缺版：


# AideanBot（WeChatRag）完整开发计划

> **状态：待确认。本文档只做计划，未落任何业务代码。确认后方可执行。**
> 版本：v2.1（2026-09-04 复审版）｜日期：2026-09-04
> **v2.1 复审变更**：① 修正 E3——知识库入库是**两步式**（`POST /api/v1/files/documents` multipart 上传 ≤10MB → `file_id`；再 `POST /knowledge/bases/<uuid>/files` 传 JSON `{file_id, parser_plugin_id}` → **异步 task_id**，经 `GET /api/v1/system/tasks/<id>` 轮询）；② 修正 T0.5.3 定性——pipeline 的 KB 绑定是配置静态项，但 **PromptPreProcessing 插件可按会话改写 KB 列表**（`localagent.py` 官方注释明确该扩展点），多 KB 路由三条路径并列待决策（Q5）；③ 吸收 `开发计划_OpenCode.md` 复审成果：wandao **双路径**（direct HTTP / CDP 浏览器）且**强制要求 `__biz`+`mid`**（裸 URL 直接失败）、LangBot **多运行时端口**（api 5300 / plugin 5400 / box 5410）、wechat-clawbot 代码实有 `/users/{aid}/{uid}/send`（其 README 过时）、新增"会话→知识空间解析规则"待决策项（Q6）。
> 依据：`.docs/` 全部文档递归精读 + `.project/` 7 个参考项目**源码实证**（非文档转述）+ 两份独立计划（本文档 / OpenCode 版）交叉验证
> 取代：`.trae/documents/AideanBot完整开发计划.md`（v1.0，2026-09-04，Trae Plan Mode 产物）

---

## 〇、原始需求与执行边界

> 依次递归阅读本项目下全部文档，理解项目初衷。设计完整的项目开发流程，创建详细的、最小原子化的、多个大纲层级的计划方案。准备就绪后，等待我确认后才能执行。

**本轮执行边界（严格遵守）**：仅产出计划文档 + 对话内展示。**不新建业务代码、不改 `.project/`、不安装依赖、不启动容器**。唯一写入的文件是本文档。

---

# 一、第一轮 · 5W1H 发散拆解

## 1.1 What — 客观事实是什么

### 1.1.1 仓库实况（2026-09-04 时点，亲自核验）

| 项 | 事实 |
|---|---|
| Git | 唯一 commit `5757a63 Initial commit`；工作区 `M README.md`、`?? .trae/`、`?? docker/` |
| 业务代码 | **0 行** |
| 文档资产 | `.docs/立项分析/{ChatGPT_V1.md(1648行), ChatGPT_V2.md(2000行), 信息源知识库机器人闭环架构设计.docx(118段+5表)}`；`.docs/主平台统一账号接入说明/{主平台README.md(v2.1), 主平台API接口文档.md(v1.8), 子平台SSO接入指南.md(v1.0)}` |
| 参考仓库 | `.project/` 7 个：firecrawl(54M) / **LangBot(21M)** / lux(924K) / reclip(906K) / SHY-downloader(299K) / wandao(28M) / wechat-clawbot(22M) |
| 工程残留 | `docker/.env`（含明文 Redfox Key `ak_153f...`，已被 `.gitignore` 覆盖）+ `docker/.env.example`（5 组配置占位） |
| 旧计划 | `.trae/documents/AideanBot完整开发计划.md`（M0–M4，T0.1–T3.8 共 40 任务） |

### 1.1.2 产品定位（README 一句话 + 主平台交叉印证）

README：「学习其他项目的先进架构和设计，重新设计本项目的个性化功能和界面，实现 **"信息源(核心：公众号)" → "知识库" → "机器人"** 的闭环。」

主平台 README v2.1 §一 交叉印证：本项目 = Aidean 产品矩阵中的 **WeChatRag**（自媒体知识库，开发中；`oidc_clients` 已 seed `wechat-rag` client，与 `aidean-rag`/`skills-cloud` 并列）。主平台已上线的 AideanRag 是它的"兄弟产品"。

### 1.1.3 README 定义的五级目标（原文口径）

| # | 目标 | 归属 | 依赖 |
|---|---|---|---|
| 1 | 发公众号链接 → 自动构建知识库，自动更新即时生效 | MVP 核心 | LangBot |
| 2 | 用户选加入方式：①该公众号全部文章 ②仅链接中这一篇 | MVP 核心 | redfox + wandao |
| 3 | 机器人可后台主动发消息给用户，用户端默认开启 | MVP 核心 | wechat-clawbot |
| 4 | 【未来】抖音/B站/小红书等图文·视频源 | 阶段四 | 视频管线 |
| 5 | 【未来】视频仅 Pro/Max 可用，按时长消耗积分 | 阶段四 | 主平台钱包 |

### 1.1.4 三份立项文档的关系（关键：它们互相矛盾）

- **ChatGPT_V1** = 第一轮架构提案。核心贡献：提出 `Source → ContentAsset → KnowledgeSpace` 领域模型，主张"公众号 ≠ 知识库"，中间必须插内容资产层。
- **ChatGPT_V2** = 对 V1 的**逐条纠错**。核心贡献：6 处架构级修正（见 §1.1.5）。
- **架构设计.docx** = **在 V1 基础上的整理稿，未吸收 V2 的修正**。

> **这不是文档瑕疵，是本计划必须处理的头号事实**：docx 里"wandao 单篇导出/redfox 整库/水位=最新 UUID/热加载器"等表述，已被 V2 明确否证。若照 docx 开发，M2 必然返工。

**V2 否证的 6 条（docx 未吸收）**：
1. wandao 只能**单篇**导出公开文章，**无历史文章能力**（docx §2.2 暗示其可承载整库，错）；
2. firecrawl 是通用抓取，**不能承诺解决微信反爬**（docx §2.3 措辞过度乐观）；
3. 水位**不能只记最新 UUID**，须做 `ArticleManifest` 快照 Diff；
4. 幂等键 = `external_id + content_hash`，**不能只用 publish_time**；
5. 向量库是**检索索引**，不是业务事实源（PG 才是）；
6. "即时生效"**不需要自研热加载器**，向量库在线 upsert 即可见。

### 1.1.5 本轮源码实证结果（本会话亲自核验，非文档转述）

| # | 断言 | 证据 | 结论 |
|---|---|---|---|
| E1 | LangBot 版本 | `LangBot/pyproject.toml` → `version = "4.10.9"` | ✅ 旧计划 T0.4 前提成立 |
| E2 | 知识库 REST API | `controller/groups/knowledge/base.py` → `@group.group_class('knowledge_base', '/api/v1/knowledge/bases')`，子路由：`''`(GET/POST)、`'/<uuid>')`(GET/PUT/DELETE)、`'/<uuid>/files'`(GET/POST)、`'/<uuid>/files/<file_id>')`(DELETE)、`'/<uuid>/retrieve'`(POST) | ✅ 全套可用 |
| E3 | **入库通道是"两步式文件上传"（v2.1 修正）** | ① `POST /api/v1/files/documents`（multipart，`file` 字段，**≤10MB**）→ `file_id`；② `POST /knowledge/bases/<uuid>/files` 传 **JSON** `{file_id, parser_plugin_id?}` → 返回**异步 `task_id`**，经 `GET /api/v1/system/tasks/<task_id>` 轮询状态（`system.py:249` 实证） | ⚠️ **修正 v2.0 的"multipart 直传 /files"说法**：无纯文本直传端点；ingest 是异步任务 → 状态机轮询设计（T1.6.4）被证实必需 |
| E4 | 知识引擎插件化 | `rag/knowledge/kbmgr.py` → `knowledge_engine_plugin_id`，建库必带、缺失则 ValueError；且 `creation_settings` 须满足插件 `creation_schema` 必填校验 | ✅ 必须先在 `/api/v1/knowledge/engines` 确认可用引擎 id |
| E5 | 消息入站通道 | `group_class('webhooks', '/bots')`（**auth_type=NONE，凭 HMAC 签名而非 `lbk_` Key**）；入站 `POST /bots/<bot_uuid>`，`path=='sync'` 时**同步等待并折叠 1→M 回复** | ✅ 成立；**双轨鉴权**：管理面（建库/文件/检索）走 `lbk_` Key，对话面（/bots）走 `inbound_secret` HMAC——两套客户端必须分离 |
| E6 | **LangBot 自带微信适配器** | `platform/sources/openclaw_weixin.yaml` → 对接 `https://ilinkai.weixin.qq.com`，扫码登录，与 wechat-clawbot 同一个 iLink 协议；另有 `wechatpad`、`wecom`、`officialaccount` | ⚠️ **重大新发现**：微信通道出现**两条互斥路径**，必须决策（§1.5 P6） |
| E7 | API Key 形态 | `service/apikey.py:109` → `secret = f'lbk_{secrets.token_urlsafe(32)}'`；仅用于 `/api/v1/*` 管理面 | ✅ 旧计划口径正确 |
| E8 | wandao 解析模块 | `wandao/plugins/wechat/backend/export_wechat.py`，**929 行** Python；**双路径**：`fetch_article_payload_direct`(L459 纯 HTTP) 与 `connect_wechat_browser`(L536 CDP 浏览器)；L357-358 **强制要求 `__biz` 与 `mid` 同时存在**，缺失直接抛 `ExportError` | ⚠️ **移植必须限定 direct 路径**；SourceResolver 必须处理"裸 URL（无查询参数）无法解析"的失败分支（`MALFORMED_URL`） |
| E9 | 主平台网关计费 | 主平台 API §5.4：`POST /api/v1/gateway/chat`，"按 body 形态判别 OpenAI / Anthropic 请求格式" | ⚠️ LangBot 的 OpenAI 兼容 Provider 通常拼 `/chat/completions` 后缀，与 `/gateway/chat` **路径不匹配**，T0.6 必须实测 |
| E10 | 多租户能力 | `controller/groups/workspaces.py` + `invitations.py` + `tenant_scope(request_context.workspace_uuid)` | ⚠️ LangBot 有 workspace 多租户，但 **API Key 是否绑定单一 workspace 未验证** → 多用户隔离方案的关键未知数 |
| E11 | 主平台上线状态 | 主平台 README §8.5「当前待办：生产服务器供给 + 实弹部署」 | ⚠️ **主平台可能尚未生产上线** → SSO/网关实证存在外部阻塞 |
| E12 | **多运行时编排**（v2.1 吸收 OpenCode 实证） | LangBot `AGENTS.md`：API(Hypercorn) `:5300`、Plugin runtime `:5400`、Box runtime `:5410`；依赖由 `uv` 管理 | ⚠️ "compose 起一个 LangBot 容器"的假设不成立 → 编排任务单列（T0.4.1 扩展） |
| E13 | **KB 路由是 pipeline 配置静态项，但插件扩展点存在**（v2.1 修正） | `preproc.py:278-283`：`pipeline_config['ai']['local-agent']['knowledge-bases']` → `query.variables['_knowledge_base_uuids']`（静态）；`localagent.py:373-374` **官方注释**："may have been modified by plugins during PromptPreProcessing" | ⚠️ 请求级 KB 路由**可以不 fork 实现**（插件改写变量），但依赖下划线私有变量（隐式契约）→ 三条路径并列待决策（Q5），T0.5.3 降级为"静态验证 + 最小实测" |
| E14 | **wechat-clawbot 实有通用发送端点**（v2.1 补验） | `api/routes.py:569` → `POST /users/{account_id}/{wechat_user_id}/send`；其 README 的 HTTP API 表**已过时**（仅列 `/notify`） | ✅ 主动推送/定向发送双通道可用，README 需回写 |

## 1.2 Why — 深层原因与动机

**表层**：把「看文章 → 记笔记 → 问问题」三步压缩成「发一条链接」。

**中层**：Aidean 产品矩阵的**基础设施验证场**。主平台 M-SSO（OIDC 7 端点）、统一计费网关、双录账本都已落地但缺少真实消费方。WeChatRag 是第一个完整的"子平台 RP"：验证 **IdP 授权码流 + wallet 实时查询 + 网关自动计费入主站账本** 这条链路。这条路跑通，SkillsCloud 照抄即可。

**深层**：数据资产化与迁移成本。用户沉淀的订阅/文章/标注只存在于本系统，形成锁定。

**反动机（必须承认，否则会自我欺骗）**：
- 纯"公众号问答"不是差异化——ima、知识星球、RagFlow、Coze 都能做；
- 真正的差异化只有三点：**发链接即建库（零配置）**、**订阅式自动生长（活知识）**、**主动推送（不是你问我答）**；
- 这三点的技术含量都不在 RAG，而在**任务系统、增量同步、IM 通道**。这就是为什么本计划把 M0 实证和 M2（订阅/任务/通道）的权重给得比"问答质量调优"更高。

## 1.3 Where / When — 边界条件与时间节点

**范围边界（本计划实施）**：公众号图文闭环（对应 docx 阶段一~三）。
**范围外（仅预留接口）**：抖音/B站/小红书/视频管线/积分计费（docx 阶段四 = M4 占位）。

**外部依赖与就绪度**：

| 依赖 | 就绪度 | 风险 |
|---|---|---|
| LangBot v4.10.9 | 🟢 本地源码在，可 docker 起 | 低 |
| wandao 解析逻辑 | 🟢 本地 929 行源码在 | 低（移植工作量） |
| Redfox API | 🟡 **能力未实测 + Key 已泄露** | 高 |
| 主平台 SSO/网关 | 🔴 **生产待办，可能未上线** | **最高** |
| 微信 iLink | 🟡 需真机扫码，风控不可控 | 中高 |
| Docker Desktop | 🟢 主平台 §8.4 已验证可用 | 低 |

**时间节点**：docx 规划 20 周（阶段一 1–4 周 / 二 5–8 周 / 三 9–12 周 / 四 13–20 周）。本计划沿用该节奏，但把 **M0 实证（docx 中不存在）前置**，因为它是所有后续工作的 go/no-go 闸门。

## 1.4 Who — 涉及的主体与责任边界

| 主体 | 角色 | 责任边界 | 是否可控 |
|---|---|---|---|
| 用户（单人开发者）+ AI | 全栈开发 | 全部自研代码 | ✅ |
| **AideanBot（本仓库）** | **知识生产系统** | 采集 / 内容资产 / 订阅 / 任务 / 知识空间 / 对话编排 | ✅ |
| **LangBot** | **机器人运行时 + RAG 引擎** | pipeline、KnowledgeEngine、IM 适配器；**不 fork、不改核心** | ✅（版本锁定 v4.10.9） |
| **Aidean 主平台** | **IdP + 钱包 + 计费网关** | 账号、tier、余额、LLM 计费 | ❌ 独立仓库/他人维护 |
| Redfox | 公众号 Discovery Provider | 作品清单 API，按次计费 | ❌ 外部商业服务 |
| 微信 iLink | IM 通道 | 官方协议，风控策略 | ❌ |
| `.project/` 其余 5 项目 | 参考/未来依赖 | lux/reclip/firecrawl 等为 M4 备用 | ✅ |

**铁律**：`providers/` 是唯一接触外部系统的防腐层。业务层不得出现 `redfox.xxx`、`langbot.xxx` 的直接调用。

## 1.5 How — 执行手段与实现路径

1. **先实证、后架构**：M0 用真实 API/真实服务跑完「能力实证矩阵」，产出 PASS/FAIL + curl 证据，再冻结 ADR。杜绝"根据 URL 形式猜 API"（V2 §四十 的明确警告）。
2. **六步循环**（对齐主平台《开发流程》）：文档 → spec → 实现 → 测试 → 回写 → 摘要记忆。
3. **领域模型先行**：`Source / Subscription / ArticleManifest / ContentAsset / KnowledgeDocument / Job / KnowledgeSpace` 七张表先定死（V2 §九、§二十五）。
4. **状态机显式化**：Job 与 KnowledgeDocument 都有显式状态机，禁止用"队列成功/失败"代替业务状态。
5. **增量从第一版就有**：不做"全量重建"，只做 Manifest Diff + upsert。
6. **门禁驱动**：每个原子任务自带测试；每个里程碑有硬门禁（§八）。

## 1.6 What if — 前提变化对结论的影响

| 前提 | 若变化 | 结论如何改变 |
|---|---|---|
| 主平台已上线 | 若**未上线** | SSO/网关实证阻塞 → **降级路径 A**：本地 Mock IdP + 自建极简 JWT，M1 先跑业务闭环，M2 切真 SSO（多一次登录改造，可承受） |
| LangBot 可路由多 KB | 若**不可** | 三级路径（D4a）：A 每 space 一组 bot+pipeline → B PromptPreProcessing 插件改写 `_knowledge_base_uuids`（E13：扩展点经官方注释确认存在）→ C R2 全自编排（亲调 retrieve + 网关 LLM）；**R2 从唯一回退降为第三级兜底** |
| LangBot API Key 绑定单 workspace | 若绑定 | 多用户隔离不能靠 Key 分租户 → 改为**单 workspace + `knowledge_space_id` 逻辑隔离字段**，检索时显式过滤 |
| /gateway/chat 与 LangBot Provider 路径匹配 | 若不匹配 | LangBot 暂时配自有 Key（上游计费），或自建一层极薄的 OpenAI→网关反代（10 行 FastAPI） |
| Redfox 能力达标 | 若不达标 | 整库模式降级为「单篇 + 手动批量加链接」；订阅功能推迟到 M3 |
| 微信 iLink 风控 | 若不稳定 | 通道降级为**单向主动通知**，问答留在 Web + LangBot 多平台 |
| wandao 解析成功率 | 若 < 60% | 提前引入 firecrawl 为主路径（`.project/firecrawl` 已在本地，可直接 docker 起） |
| 技术栈选 TS 全栈 | 若改选 | wandao 929 行 Python 解析须 TS 重写 → 解析质量实证升为 M0 第一优先，工期 +1~2 周 |

---

# 二、第二轮 · 苏格拉底拷问与双向钢人论证

> 方法：对每个论点，先构造**最强正方**（如果我错了，对方最可能怎样一举击溃我），再构造**最强反方**（如果我对了，最可能在哪里翻车），然后裁决。裁决结果 = 幸存论点。

## P1 · 「先把架构文档写完整，再写代码」是否正确？

- **正方（支持先文档）**：本项目最大风险不是代码质量，是**领域模型错**（V2 花了 2000 行纠 V1 的 6 处架构误判）。领域模型一旦错，代码越多沉没成本越大。且项目零代码，写文档成本极低、收益极高。
- **反方（支持先代码）**：本项目**真正的未知数全部在外部**（Redfox API 能力、LangBot 多 KB 路由、主平台网关路径、wandao 解析成功率）。文档写得再完美，只要这四项中任意一项 FAIL，文档就作废。**在外部约束未验证前冻结架构，是把最大的不确定性锁死在最贵的层。**
- **裁决（幸存）**：**部分推翻，采纳"先实证，后冻结，再实现"三段式**。具体：M0 阶段**只写实证记录，不冻结架构**；实证全过后再一次性产出 ADR-0001~0004 冻结架构；然后才开 M1。**文档仍然先于代码，但文档的内容来源是实证而非推理。**

## P2 · LangBot 应该只做运行时，还是承载全部业务？

- **正方（全部塞进 LangBot 插件）**：只用一套进程、一套配置、一套 WebUI；LangBot 已提供 pipeline/插件/会话/多平台适配器，业务做成插件最省事；省掉一整套后端。
- **反方（分离）**：业务域（订阅、任务状态机、Manifest Diff、积分、用户空间）塞进 LangBot 插件 = **深度耦合第三方项目**。LangBot 一旦升级（v4.10.9 → v4.11），插件 API 变更会直接击穿业务。且 LangBot 是 GPL/商用需授权，业务逻辑绑死它有法务风险。
- **裁决（幸存）**：**LangBot = 运行时 + RAG 引擎，业务域归 AideanBot。** 版本锁定 v4.10.9（docker-compose 固定镜像 tag），升级必须走 ADR。

## P3 · 自建 RAG（pgvector + 自研检索）还是依赖 LangBot KnowledgeEngine？

- **正方（自建）**：完全可控；混合检索（向量+关键词+Rerank）自由实现；不受 LangBot 插件引擎限制；引用溯源数据结构自己定。
- **反方（用 LangBot）**：V2 已论证 LangBot 4.9+ 把 RAG 抽为 KnowledgeEngine 插件，负责 ingestion/retrieval 全生命周期；自研等于重做分块、嵌入、向量管理、文件解析、删除回收，至少 2–3 周且无差异化收益。
- **裁决（幸存）**：**默认用 KnowledgeEngine**，但 M0 必须对 E4（引擎 id）与 E10（多租户）实证。若 FAIL → R2 回退（AideanBot 亲调 retrieve + 自组 LLM 调用），**若 R2 也要自建索引，那才启用 pgvector**。三级递进，逐级加成本。

## P4 · 「单篇 vs 整库」是两个功能，还是同一模型的两种形态？

- **正方（两个功能）**：用户心智上就是两个按钮，交互不同（单篇数秒 vs 整库数分钟+进度条），实现路径不同（wandao 直抓 vs redfox 清单+批量），代码上分开写最直观。
- **反方（同一模型）**：V2 §十论证——两者差异**仅在"是否有 Subscription"**。若写成两个功能，M1 写单篇、M2 写整库，会发现 M1 的代码 80% 无法复用（因为没抽 ContentAsset 与 Job），返工。
- **裁决（幸存）**：**领域模型统一（同一条 `Source → ContentAsset → Job → KnowledgeDocument` 链路），UI 呈现两个选项。** 代码从 M1 起就按"N 篇"写（N=1 是特例），M2 只是把 N 变成 386。

## P5 · 幂等键用 `external_id` 还是 `external_id + content_hash`？

- **正方（只用 external_id）**：简单；Redfox 若提供稳定 uuid 就够；content_hash 需要全文比对，成本高。
- **反方（加 hash）**：V2 §十三明确否证——公众号作者**会修改已发布文章**（发布时间不变、内容变了）。只按 external_id 判重，用户永远不会看到修订后的内容，这是静默的错误数据，比失败更糟。
- **裁决（幸存）**：**`external_id` 定存在，`content_hash` 定变更**（内容规范化后取 sha256）。同理，`publish_time` 只能用于排序与展示，**绝不参与判重**。

## P6 · 微信通道：LangBot 内置 `openclaw-weixin` 适配器 vs 自研 wechat-clawbot 网关？

> 本条是本会话**新发现**（E6），旧计划未覆盖，必须决策。

- **方案 A（用 LangBot 内置适配器）**：零开发，在 LangBot WebUI 里扫码即通，天然打通 pipeline 与 RAG。**最强论据**：省掉一整个子服务的开发运维。
- **方案 B（用 wechat-clawbot 网关）**：README 目标 3 原文标注 `[wechat-clawbot]`；且两者**语义不同**——LangBot 适配器是「**机器人自己的微信账号**」（一个 bot = 一个微信号，用户加它好友），wechat-clawbot 是「**多个用户各自扫码绑定自己的微信**」（多账号，机器人主动推送到用户微信）。README 目标 3「机器人可以由后台控制主动发送消息给用户」= **用户绑定模式**。
- **反方对 A 的致命一击**：若只需"机器人号"，那 README 根本不会把 wechat-clawbot 列为参考项目并标注目标 3。
- **反方对 B 的致命一击**：多账号绑定意味着**每个用户都要扫码**，且 iLink 是官方受限能力，账号数、风控、长期可用性全不可控；而 LangBot 内置适配器是**官方支持路径**。
- **裁决（幸存）**：**两者都要，但顺序与职责不同，且这是待决策项 D9**：
  - **M2 主路径 = 方案 A**（LangBot `openclaw-weixin`），1 个机器人微信账号，服务多用户，成本最低、最快验证闭环；
  - **M2.5 = 方案 B**（wechat-clawbot 作为**主动推送通道**），只在"用户绑定自己微信收通知"场景启用；
  - 二者通过 `NotificationChannel` 抽象统一，业务层不感知。

## P7 · 后端 Python 还是全 TypeScript 对齐主平台？

- **正方（TS 全栈）**：主平台是 Next.js 全栈 + TS + Prisma，SSO 客户端示例是 Node；组件/规范/人力复用；一套语言一套 CI；firecrawl 本地源码是 TS，可直接用。
- **反方（Python 后端）**：wandao 929 行解析逻辑是 Python（要 TS 重写 = 重做全部解析质量实证）；LangBot 是 Python（调试、读源码、排障同一语言）；采集/解析/ASR 生态（httpx/BeautifulSoup/Celery/yt-dlp/faster-whisper）Python 显著更强；firecrawl 是**独立服务**用 HTTP 调，不需要 TS 集成。
- **裁决（幸存）**：**推荐 FastAPI(Python) 后端 + Next.js(TS) 前端**（混合栈）。理由：后端生态收益 >> 语言统一收益，前端对齐主平台保住 UI 铁律与体验一致性。**但因维护成本客观存在，列为待决策项 D1**，若用户更看重单语言，改为 Next.js 全栈 + firecrawl 为主解析器（工期 +1~2 周）。

## P8 · 向量库能否兼作业务事实源？

- **正方（可以）**：少一套存储；检索与数据同处一处，一致性天然好。
- **反方（不行）**：V2 §十四——向量库不能表达"订阅关系、任务状态、用户归属、文章版本、失败原因"；且重建索引时业务数据会随之丢失。
- **裁决（幸存）**：**PostgreSQL 是唯一业务事实源**，向量库只是检索索引，可随时按 PG 数据重建。

## P9 · 积分与计费现在就做，还是留到 M4？

- **正方（现在做）**：架构里没有计费位，以后加要改全链路；主平台网关已经能自动计费（LLM 部分），本系统只需处理"非 LLM 成本"（Redfox 调用、ASR）。
- **反方（M4 再做）**：MVP 阶段唯一外部成本是 Redfox（公众号图文，成本极低），没有任何需要用户付费的能力；V2 §二十九明确警告"过早具体化价格数字"。
- **裁决（幸存）**：**不落真实扣费，但 M1 起预留 `billing_policy` 表与 `Capability` 门禁接口**。tier 门禁（NORMAL/PRO/MAX）M1 就接（来自 SSO claims，零成本），积分数字 M4 再定。

## P10 · 「即时生效」需要自研热加载组件吗？

- **正方（需要）**：docx §4.3.2 专门设计了"热加载索引器"；要保证新向量立刻可检索，需要显式的加载/切换逻辑。
- **反方（不需要）**：V2 §十五——若向量库支持在线 upsert + search，则"写入成功 → 下次查询可见"就是即时生效，自研热加载是**为架构而架构**，且引入一致性 bug 风险。
- **裁决（幸存）**：**不建热加载组件。** 改为**状态口径约束**：`KnowledgeDocument.status` 必须走到 `INDEXED` 才允许提示用户"可以提问"（V2 §十六）。这是产品体验问题，不是架构问题。

---

# 三、第三轮 · 幸存论点与终稿前提

## 3.1 十条幸存论点（本计划的地基）

1. **先实证、后冻结、再实现**：外部未知数未验证前不冻结架构。
2. **LangBot = 运行时 + RAG 引擎**，业务域归 AideanBot，版本锁定 v4.10.9。
3. **RAG 默认用 KnowledgeEngine**，失败才 R2，再失败才 pgvector（三级递进）。
4. **单篇与整库是同一模型**，差异仅在 Subscription 有无。
5. **幂等 = `external_id` + `content_hash`**，`publish_time` 不参与判重。
6. **微信通道双轨**：LangBot 内置适配器为主（机器人号），wechat-clawbot 为主动推送通道（用户绑定号）。
7. **推荐 Python 后端 + Next.js 前端**（待决策 D1）。
8. **PG 是唯一事实源**，向量库是可重建的检索索引。
9. **计费：tier 门禁 M1 接入，积分 M4 落地**，接口 M1 预留。
10. **不建热加载组件**，改用"INDEXED 才可提问"的状态口径。

## 3.2 终稿的前提条件（任一不成立，本计划需重评审）

- A1：LangBot v4.10.9 能以 Docker 独立启动，且其 KnowledgeEngine 插件可用。
- A2：Redfox API 至少能通过「文章 URL → 公众号定位 → 作品清单」中的一条路径工作。
- A3：wandao 的 929 行解析逻辑对当前真实公众号文章仍有 ≥70% 可用成功率。
- A4：主平台 SSO/网关**至少有一个可用环境**（生产/测试/本地均可）。
- A5：开发者接受混合技术栈或明确选择替代方案（D1）。

## 3.3 局限性声明

- 本计划的实证结论基于 **2026-09-04 时点的本地源码核验**（E1–E11）与文档版本（主平台 README v2.1 / API v1.8 / SSO 指南 v1.0）；主平台契约变更需重新评审。
- M0 实证若出现 FAIL，将触发 §九 回退矩阵，届时以 ADR 记录并修订本计划对应章节。
- M4（视频/积分）为占位，不含实施细节。

---

# 四、核心架构决策

| # | 决策 | 选择 | 理由 | 状态 |
|---|---|---|---|---|
| D1 | 技术栈 | **FastAPI(Python 3.12) + Next.js(TS)** | 后端生态（wandao 移植/LangBot 同构/采集生态）收益 > 语言统一收益；前端对齐主平台 | 🔶 待决策 |
| D2 | 机器人运行时 | LangBot v4.10.9，独立进程，HTTP Bot 起步 | 官方支持、免微信凭据、测试最快 | ✅ |
| D3 | RAG 引擎 | LangBot KnowledgeEngine 为主 | 三级递进（§P3） | ✅ |
| D4 | 消息拓扑 | AideanBot 中枢 + LangBot `POST /bots/<uuid>/sync`（HMAC 签名通道，与 `lbk_` 管理面**双轨鉴权、双客户端分离**） | E5 实证；业务流全在 AideanBot | ✅ |
| D4a | **KB 路由路径** | 三选一（Q5）：A 每 KnowledgeSpace 一组 bot+pipeline（公开契约，运维重）；B 单 bot + PromptPreProcessing 插件按会话改写 `_knowledge_base_uuids`（优雅，依赖私有变量+版本 pin）；C R2 全自编排（亲调 retrieve + 网关 LLM，零耦合） | E13：插件扩展点被官方注释确认存在；推荐 A 或 B，C 为兜底 | 🔶 待决策 |
| D5 | 出站回调 | AideanBot 提供 `POST /api/v1/bot/callback` 端点 | E5：非 sync 模式 LangBot 以 `callback_url` 推送 1→M 回复 | ✅ |
| D6 | 任务系统 | PostgreSQL 持久化状态机 + Celery(worker/beat) + Redis | Job 是状态机，不依赖队列存活 | ✅ |
| D7 | 内容入库形态 | ContentAsset 落**文件** → `POST /api/v1/files/documents`（multipart ≤10MB）→ `POST /knowledge/bases/<uuid>/files`（JSON file_id）→ **异步 task_id 轮询** | E3 v2.1 修正：两步式 + 异步 | 🆕 已修订 |
| D8 | 多用户隔离 | `knowledge_space_id` 逻辑隔离字段（单 workspace 起步）；T0.5 若实证 API Key 可绑 workspace，则改为物理隔离 | E10 未定 → 保守起步 | 🆕 本轮新增 |
| D9 | 微信通道 | 双轨：LangBot `openclaw-weixin`（主，机器人号）+ wechat-clawbot（推送，用户绑定号） | E6 新发现 + README 目标 3 | 🔶 待决策 |
| D10 | 认证计费 | 主平台 SSO（服务端会话）+ tier 实时读 + LLM 走主平台网关 | SSO 铁律：余额不落库、无自建账本 | ✅ |
| D11 | 单体优先 | 单体多模块（FastAPI 一个进程 + worker），不拆微服务 | 单人开发，微服务运维成本不可承受 | ✅ |

---

# 五、目标架构

## 5.1 分层总览

```
┌─ 接入层 ─────────────────────────────────────────────────┐
│  Web(Next.js)   │  LangBot IM(微信/飞书/钉钉/HTTP Bot)   │
└────────┬────────────────────────┬────────────────────────┘
         │                        │ 出站回调 /sync
         ▼                        ▼
┌─ AideanBot · FastAPI ────────────────────────────────────┐
│  api/v1(薄路由) │ services │ repositories │ models       │
│  ├ Source 域   : SourceResolver                          │
│  ├ Discovery 域: ContentDiscoverer (Redfox)              │
│  ├ Content 域  : Extractor(wandao→firecrawl) + Normalizer│
│  │              + 质量评分 → ContentAsset(落文件)        │
│  ├ Knowledge 域: KnowledgeSpace → LangBot KB 网关        │
│  ├ Job 域      : PG 状态机 + Celery(worker/beat)         │
│  ├ Subscription: Manifest Diff 增量同步                  │
│  ├ Bot 域      : 对话流(链接识别/选择卡片/进度/回执)     │
│  └ Auth/Billing: 主平台 SSO + wallet 实时查 + tier 门禁  │
│  providers/(防腐层): redfox · langbot · clawbot · aidean │
└───────────────────────┬──────────────────────────────────┘
                        ▼
┌─ 基础设施 ───────────────────────────────────────────────┐
│ PostgreSQL(事实源) │ Redis(队列/缓存/限流) │ 文件卷 │
│ LangBot(v4.10.9 独立进程: pipeline + KnowledgeEngine)    │
│ Aidean 主平台(IdP + Wallet + 计费网关)                   │
└──────────────────────────────────────────────────────────┘
```

## 5.2 仓库结构（monorepo）

```
aideanbot/
├── backend/                    # Python 3.12 + FastAPI
│   ├── app/
│   │   ├── api/v1/             # 薄路由：校验/鉴权/响应归一
│   │   ├── core/               # 配置/错误码/日志/安全/响应信封
│   │   ├── services/           # source discovery extraction normalization
│   │   │                       # knowledge jobs subscription bot auth billing
│   │   ├── providers/          # 防腐层：redfox / langbot / clawbot / aidean / firecrawl
│   │   ├── repositories/       # SQLAlchemy 数据访问
│   │   ├── models/             # ORM 模型
│   │   ├── schemas/            # Pydantic DTO
│   │   └── workers/            # Celery tasks + beat schedule
│   ├── tests/{unit,integration,e2e}
│   ├── alembic/
│   └── pyproject.toml
├── frontend/                   # Next.js App Router + TS + Tailwind
├── docker/                     # compose.yml / compose.prod.yml / .env.example
└── .docs/                      # 文档体系（文档即真源）
```

## 5.3 核心数据模型（v1，M0.10 细化）

| 表 | 关键字段 | 说明 |
|---|---|---|
| `users` | `sub`(主平台 User.id 锚点, unique)、email/nickname 快照、status | **tier/余额不落库**，实时查 |
| `knowledge_spaces` | user_id、name、`langbot_kb_uuid`、status、doc_count/chunk_count | 一个用户多个空间 |
| `sources` | type(`wechat_oa`/`web`/`video`)、external_id(`__biz`)、name、url、status | 信息源 |
| `source_subscriptions` | source_id、space_id、sync_policy、sync_interval、`next_run_at`、`last_success_at`、status | 订阅 |
| `article_manifests` | source_id、external_id、url、title、publish_time、`content_hash`、status | **发现快照，Diff 基准** |
| `content_assets` | source_id、external_id、url、title、published_at、`content_hash`、`file_uri`、content_markdown、`quality_score`、version、status | **核心资产层（含落文件 URI）** |
| `knowledge_documents` | asset_id、space_id、`langbot_file_id`、status(`FETCHED→NORMALIZED→INDEXING→INDEXED→FAILED`) | 与 LangBot 的映射 |
| `jobs` | type、payload、status、progress、error、`idempotency_key`、result | 持久化状态机 |
| `job_items` | job_id、manifest_id、status、error、retry_count | 支撑 PARTIAL_SUCCESS |
| `billing_policies` | operation、unit、price、tier_required、enabled | M1 建表，M4 启用 |

**Job 状态机**：`QUEUED → RUNNING → (SUCCEEDED | PARTIAL_SUCCESS | FAILED | CANCELLED)`，`RETRYING` 为 RUNNING 子态。
**KnowledgeDocument 状态机**：`FETCHED → NORMALIZED → INDEXING → INDEXED`，任一环节失败 → `FAILED`（保留失败原因）。

## 5.4 API 面（v1）

| 域 | 端点 |
|---|---|
| 认证 | `/api/v1/auth/{login,callback,refresh,me,logout}` |
| 知识空间 | `/api/v1/spaces` CRUD |
| 信息源 | `/api/v1/sources` CRUD、`POST /api/v1/sources/{id}/sync` |
| 内容资产 | `/api/v1/assets`（列表/详情/Markdown 渲染） |
| 任务中心 | `/api/v1/jobs`、`POST /api/v1/jobs/{id}/retry` |
| 对话 | `POST /api/v1/chat`（Web 对话，代理 LangBot sync） |
| 机器人回调 | `POST /api/v1/bot/callback`（LangBot 出站回调，D5） |
| 微信绑定(M2.5) | `/api/v1/bot/wechat/{bind,unbind}`、主动推送接口 |

**统一响应**（对齐主平台）：`{ "code": 0, "message": "ok", "data": {...}, "requestId": "..." }`
**错误码段位**：`1xxxx` 用户/认证 · `2xxxx` 采集/解析 · `3xxxx` 知识库 · `4xxxx` 计费/权限 · `5xxxx` 系统。先登记后实现，与 `core/errors.py` 双源对齐。

---

# 六、开发流程设计

## 6.1 六步循环（对齐主平台《开发流程》）

```
① 文档   → 明确做什么（spec/ADR/接口契约先落 .docs/）
② spec   → 拆到原子任务，写清验收标准
③ 实现   → 只做本任务，禁止顺手改无关代码
④ 测试   → 单测/集成随任务交付（不单独建测试任务）
⑤ 回写   → .docs/ 同步更新（API/数据模型/ADR）
⑥ 摘要   → 关键决策与教训写入 .workbuddy/memory/
```

## 6.2 分支与提交规范

- 分支：`main`（保护）← `feat/M{x}-{slug}` ← 本地提交；每个里程碑一个集成分支。
- 提交：`<type>(<scope>): <subject>`，type ∈ `feat|fix|refactor|docs|test|chore|perf`。
- 每个原子任务 = 1~N 个提交，提交信息带任务号，如 `feat(source): 实现 SourceResolver 域名路由 [T1.4.1]`。

## 6.3 CI 门禁（对齐主平台 G-2 风格）

`verify` job 四段串行，**任一红即阻断**：
1. 文档检查（`.docs/` 与代码冲突检测）
2. `ruff` + `mypy`（后端）、`eslint` + `tsc --noEmit`（前端）
3. 单测 + 集成测试（`pytest` / `vitest`）
4. 构建（`docker build` / `next build`）

## 6.4 安全铁律（不可协商）

1. 密钥只入 `docker/.env`（已被 gitignore），**绝不入代码/文档/前端/Git**。
2. `state` 必填并在 SSO 回调强校验；refresh 链必须可靠持久化（写入失败 = 下次刷新被判重放）。
3. **余额/tier 不落库**，一律实时查主平台。
4. 所有外部调用走 `providers/`，业务层零直接依赖。
5. LangBot 出站回调必须验 HMAC 签名（`outbound_secret`）。

---

# 七、里程碑与路线图

| 里程碑 | 目标 | 对应 docx 阶段 | 硬门禁 |
|---|---|---|---|
| **M0 · 能力实证与工程奠基** | 实证矩阵全 PASS/定案 + 脚手架可跑 | 前置于阶段一 | 11 项实证有结论；`docker compose up` 全家桶可跑 |
| **M1 · 公众号单篇闭环 MVP** | 发链接 → 选单篇 → 入库 → 提问 → 带引用回答 | 阶段一 | 真实链接 → 数秒入库 → 立即提问 → 带引用回答 |
| **M2 · 整库导入 + 订阅增量 + 微信通道** | Redfox 全量 + Manifest Diff + LangBot 微信适配器 | 阶段二 | ≥100 篇整库导入（含制造部分失败）→ 定时增量入库 → 无重启可检索；微信真机全链 |
| **M3 · Web 管理后台 + 体验打磨** | 任务中心/文章浏览/引用溯源/生产部署 | 阶段三 | 全站可演示 + compose.prod 部署 |
| **M4 · 视频源 + 会员积分**（占位） | yt-dlp→ffmpeg→ASR→LLM 管线；BillingPolicy 落地 | 阶段四 | 不在本计划实施范围 |

---

# 八、原子任务分解

> **粒度定义**：每个原子任务 = 一次可独立提交、一次可独立验收（有明确测试），工作量 ≤ 半天。
> **编号规则**：`T{里程碑}.{模块}.{序号}`，形成 **里程碑 → 模块 → 原子任务 → 验收标准** 四级大纲。

---

## M0 · 能力实证与工程奠基（11 模块 · 26 任务）

> **性质**：本阶段**只产出实证记录与骨架，不冻结业务架构**。M0.9 之后才由 ADR 冻结。

### S0.1 安全整改

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T0.1.1 | Redfox Key 轮换：在 redfox.hk 后台撤销 `ak_153f...`；新 Key 只写入 `docker/.env` | `.env` 新值生效；Git 历史与文档无明文 Key | — |
| T0.1.2 | 全仓密钥扫描：grep `ak_`/`sk-`/`lbk_`/`secret` 等模式，输出扫描报告 | 报告：命中文件清单 + 处置结论 | — |
| T0.1.3 | `docker/.env.example` 补齐分组注释与占位（DB/Redis/主平台/LangBot/Redfox/App） | 新机器 `cp .env.example .env` 即可启动 | — |

### S0.2 Redfox 能力实证（**最高风险项**）

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T0.2.1 | 鉴权与连通性：两种鉴权方式（Header/Bearer）实测，记录 401/403 形态 | curl 证据 + 结论 | T0.1.1 |
| T0.2.2 | 优质库端点 `/apis/gongzhonghao/XNV30XZ3` 实测：请求/响应字段全量记录 | 原始 JSON 样本入库到 `实证记录.md` | T0.2.1 |
| T0.2.3 | 广域库端点 `/apis/gongzhonghao/8IQD0BJC` 实测 + 与优质库差异对比 | 对比表（字段/覆盖/延迟） | T0.2.2 |
| T0.2.4 | **公众号定位能力**：wxId / bizInfo / 账号名 三种入参实测，记录成功率 | 三路径成功率表 | T0.2.2 |
| T0.2.5 | **URL → 公众号身份**反查实测（能否从一个文章 URL 拿到该号清单） | PASS/FAIL + 证据（决定 M2 交互形态） | T0.2.4 |
| T0.2.6 | 分页/游标/最大返回量/限流/计费口径实测 | 限流阈值与单次成本记录 | T0.2.2 |
| T0.2.7 | 文章 UUID 稳定性 + 修改检测能力实测（同一文章多次拉取 hash 是否稳定） | 结论：能否支撑 content_hash 方案 | T0.2.2 |

### S0.3 wandao 单篇解析实证

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T0.3.1 | 提取 `export_wechat.py` 核心解析函数，剥离 Electron/插件依赖，做成可独立调用的纯函数 | 可 `python -c` 调用并输出 Markdown | — |
| T0.3.2 | 用 **5+ 篇真实公众号文章**（不同号/不同排版）跑解析，记录成功率 | 成功率表 + 失败样本 | T0.3.1 |
| T0.3.3 | 质量缺陷清单：图片处理/标题抽取/发布时间/正文截断/噪声残留逐项记录 | 缺陷清单（带样本） | T0.3.2 |

### S0.4 LangBot 实证（A · 知识库）

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T0.4.1 | **LangBot 多运行时编排**：docker 起 v4.10.9（固定 tag，API :5300 / plugin :5400 / box :5410 三端口健康检查），WebUI 创建 `lbk_` API Key | 三端口全绿 + Key 可用 | — |
| T0.4.2 | 枚举可用知识引擎：`GET /api/v1/knowledge/engines`，记录默认 `knowledge_engine_plugin_id` | 引擎清单 + 默认 id | T0.4.1 |
| T0.4.3 | 创建 KB：`POST /api/v1/knowledge/bases`（带 engine id + 插件 `creation_schema` 必填项） | 返回 kb_uuid | T0.4.2 |
| T0.4.4 | **两步式文件入库实证**：① `POST /api/v1/files/documents`（multipart，≤10MB）→ `file_id`；② `POST /knowledge/bases/{uuid}/files`（JSON `{file_id, parser_plugin_id}`）→ `task_id`；③ `GET /api/v1/system/tasks/{task_id}` 轮询至完成 | 全链 curl 记录 + **写入→可检索延迟实测值** | T0.4.3 |
| T0.4.5 | 检索实证：`POST /api/v1/knowledge/bases/{uuid}/retrieve`，验证能召回刚入库内容 | 命中片段 + 相似度 | T0.4.4 |
| T0.4.6 | 删除实证：`DELETE /.../files/{file_id}` + KB 删除，验证无残留 | 检索不再命中 | T0.4.5 |

### S0.5 LangBot 实证（B · 多租户与路由）

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T0.5.1 | workspace 实证：创建 2 个 workspace，验证 KB 是否 workspace 隔离 | 隔离性结论 | T0.4.3 |
| T0.5.2 | **API Key 与 workspace 绑定关系**实证（一个 Key 能否跨 workspace 操作） | 结论 → 决定 D8 隔离方案 | T0.5.1 |
| T0.5.3 | **多 KB 路由定案**：静态验证已完成（E13：pipeline 配置静态 + PromptPreProcessing 插件扩展点确认）；实测最小验证——按 D4a 选定路径（A 每 space 一组 bot+pipeline / B 插件改写变量 / C R2）跑通一次跨 KB 提问 | 选定路径跑通 → ADR-0002 记录；选 B 则同步记录"私有变量 + 版本 pin"风险 | T0.4.5 |
| T0.5.4 | HTTP Bot 创建 + `POST /bots/{uuid}/sync` 同步通道实测（含 HMAC 签名） | 同步拿到完整回复 | T0.4.1 |
| T0.5.5 | 出站 callback 通道实测（`callback_url` + 1→M 多段回复 + 签名校验） | AideanBot 侧回调端点能收全 | T0.5.4 |

### S0.6 LangBot 实证（C · LLM 经主平台网关）

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T0.6.1 | 主平台网关可用性：`POST /api/v1/gateway/chat` 直连实测（OpenAI 格式 body） | 返回正常 | — |
| T0.6.2 | **路径适配实证**：LangBot OpenAI 兼容 Provider 的 base_url 拼接规则 → 与 `/gateway/chat` 是否匹配 | 结论 → 不匹配则给出反代方案 | T0.6.1 |
| T0.6.3 | 端到端计费实证：LangBot 走网关产生一次对话 → 主平台账本出现扣费流水 | 账本流水截图/curl 证据 | T0.6.2 |

### S0.7 主平台 SSO 实证

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T0.7.1 | 环境确认：主平台是否有可访问环境（生产/测试/本地） | 环境地址 + 可达性结论（**若不可达 → 触发回退路径 A**） | — |
| T0.7.2 | 获取 `wechat-rag` client 凭据（clientId + secret + redirectUris 白名单） | 凭据到手（依赖管理员 = 用户本人） | T0.7.1 |
| T0.7.3 | 五步全链实测：authorize → 登录 → callback(code+state) → token 兑换 → userinfo | 五步 curl 记录 | T0.7.2 |
| T0.7.4 | refresh 轮换 + 旧值复用拒绝 + `wallet:read` 实时查询实测 | 三项结论 + wallet JSON 样本 | T0.7.3 |

### S0.8 微信通道实证（D9 决策输入）

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T0.8.1 | LangBot `openclaw-weixin` 适配器扫码实测：能否成功登录并收发一条消息 | PASS/FAIL + 账号形态说明（机器人号） | T0.4.1 |
| T0.8.2 | wechat-clawbot 冒烟：起服务 + 扫码绑定 + `/notify` 送达实测 | PASS/FAIL + 多账号能力确认 | — |
| T0.8.3 | 产出《微信通道选型结论》：两方案对比 + 推荐 + 风险 | 结论文档 → 用户据此拍板 D9 | T0.8.1, T0.8.2 |

### S0.9 架构定案

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T0.9.1 | 汇总 M0 全部实证 → 《能力实证总报告》（每项 PASS/FAIL + 触发的回退） | 报告入 `.docs/` | S0.2~S0.8 |
| T0.9.2 | 产出 ADR-0001（RAG 引擎选型）、ADR-0002（消息拓扑）、ADR-0003（多租户隔离）、ADR-0004（技术栈 D1 定案） | 4 份 ADR 入 `.docs/ADR/` | T0.9.1 |
| T0.9.3 | 与用户评审 ADR，**冻结架构** | 用户签字确认 | T0.9.2 |

### S0.10 工程脚手架

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T0.10.1 | monorepo 骨架：`backend/`(FastAPI hello + /health) + `frontend/`(Next.js 骨架) + `docker/compose.yml` | `docker compose up` 起 PG+Redis+LangBot+backend+frontend | T0.9.3 |
| T0.10.2 | CI 基线：ruff + mypy + pytest + build 四段 job | CI 全绿 | T0.10.1 |
| T0.10.3 | 日志/配置/错误码底座：`core/` 四件套 | 结构化日志输出 requestId | T0.10.1 |

### S0.11 数据模型与文档体系

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T0.11.1 | SQLAlchemy 模型（§5.3 全表）+ Alembic 首迁移 | 迁移可执行 | T0.10.1 |
| T0.11.2 | 错误码登记表（五段位）落地为 `core/errors.py` | 表与代码双源一致 | T0.10.3 |
| T0.11.3 | `.docs/` 四件套：文档索引 / 需求文档 / API 接口文档 / 开发流程 | 索引可导航 | T0.10.1 |

---

## M1 · 公众号单篇闭环 MVP（8 模块 · 32 任务）

### S1.1 后端骨架分层

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T1.1.1 | 分层目录：`api/v1` `services` `repositories` `models` `schemas` `providers` `workers` | 目录就位，各层职责注释 | T0.10.1 |
| T1.1.2 | 统一响应信封 `{code,message,data,requestId}` 中间件 | 所有路由统一形态 | T1.1.1 |
| T1.1.3 | 全局异常处理 + 错误码映射 | 异常 → 标准错误码 | T1.1.2 |
| T1.1.4 | 请求 ID + 结构化日志中间件 | 每条日志带 requestId | T1.1.2 |

### S1.2 认证与权限（主平台 SSO）

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T1.2.1 | `providers/aidean` 客户端：token 端点 + userinfo + wallet 查询封装 | 三个方法单测（mock） | T0.7.4 |
| T1.2.2 | `GET /auth/login`：生成 state 存会话 → 302 主平台 authorize | state 强校验单测 | T1.2.1 |
| T1.2.3 | `GET /auth/callback`：state 校验 → code 兑换 → 建本地 user(sub 锚点) | CSRF 场景单测 | T1.2.2 |
| T1.2.4 | refresh 链持久化（可靠写入，写失败告警）+ 轮换逻辑 | 旧值复用被拒的正确处理单测 | T1.2.3 |
| T1.2.5 | 服务端会话（加密 Cookie）+ `GET /auth/me`（userinfo + **实时 wallet**） | 会话过期/续期单测 | T1.2.4 |
| T1.2.6 | `POST /auth/logout`：清本地会话 + 调 `/oauth/revoke` | 撤销后端到端测试 | T1.2.5 |
| T1.2.7 | tier 门禁中间件：`Capability` 判定（NORMAL/PRO/MAX） | 门禁单测（三档行为） | T1.2.5 |

### S1.3 Source 域

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T1.3.1 | `SourceResolver`：URL → `wechat_oa`/`web` 域名路由表，可扩展 | 多 URL 形态解析单测 | T1.1.1 |
| T1.3.2 | `mp.weixin.qq.com` 链接参数提取（`__biz`/`mid`/`idx`/`sn`/`chksm`）；**裸 URL（无查询参数）→ 显式失败分类 `MALFORMED_URL` + 用户可感知文案**（E8：wandao 强制要求 `__biz`+`mid`） | 参数提取单测 + 裸 URL 失败分支单测 | T1.3.1 |
| T1.3.3 | `sources` 表 repository + service（upsert by external_id） | CRUD 单测 | T0.11.1 |

### S1.4 Content 域（采集与规范化）

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T1.4.1 | `providers/wechat/wandao_extractor`：移植 T0.3.1 的纯函数，httpx 抓取 | 真实文章抽取成功 | T0.3.1 |
| T1.4.2 | 失败分类枚举：`SUCCESS/TEMPORARY_FAILURE/PERMANENT_FAILURE/RATE_LIMITED/AUTH_REQUIRED/CONTENT_REMOVED/NOT_SUPPORTED` | 分类单测 | T1.4.1 |
| T1.4.3 | `ContentNormalizer`：元数据归一（title/author/published_at）+ 正文清洗 | 归一化单测 | T1.4.2 |
| T1.4.4 | 质量评分函数：正文长度/标题存在性/图片比例/导航噪声比/重复文本 → `score` | 评分单测（好/中/差三档样本） | T1.4.3 |
| T1.4.5 | 降级链：`score<0.6` 失败 / `0.6~0.85` 触发备用 Extractor（`firecrawl` 位预留） / `>0.85` 入库 | 三档行为单测 | T1.4.4 |
| T1.4.6 | `content_hash` 计算（规范化后 sha256）+ `external_id` 复合幂等 | 幂等单测 | T1.4.3 |
| T1.4.7 | **ContentAsset 落文件**：Markdown 写本地卷 → 返回 `file_uri` | 文件落盘 + 路径单测 | T1.4.3 |

### S1.5 Job 域

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T1.5.1 | Job 状态机实体 + `idempotency_key` 唯一约束 | 重复提交幂等单测 | T0.11.1 |
| T1.5.2 | Celery worker 接入（队列绑定 + 结果回写 PG） | worker 消费测试 | T0.10.1 |
| T1.5.3 | progress 心跳更新 + 状态流转（QUEUED→RUNNING→SUCCEEDED/FAILED） | 流转单测 | T1.5.1 |
| T1.5.4 | `job_items` 子任务表与聚合逻辑（支撑 PARTIAL_SUCCESS） | 聚合单测（全成/部分成/全败） | T1.5.1 |
| T1.5.5 | 失败重试策略（指数退避 + 最大次数 + 手动重试接口） | 重试单测 | T1.5.3 |

### S1.6 Knowledge 域（LangBot 网关）

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T1.6.1 | `providers/langbot` 客户端：建库/上传文件/检索/删除（含 `lbk_` 鉴权） | 客户端单测（mock）+ 集成（compose） | T0.4.5 |
| T1.6.2 | KnowledgeSpace 创建时同步建 LangBot KB 并回写 `langbot_kb_uuid` | 双写一致性单测 | T1.6.1 |
| T1.6.3 | **两步式文件入库**：ContentAsset `file_uri` → `POST /api/v1/files/documents`（multipart）→ `file_id` → `POST /knowledge/bases/{uuid}/files`（JSON）→ `task_id` 轮询 → `langbot_file_id` 回写 | 端到端集成测试（含 >10MB 拒绝分支） | T1.4.7, T1.6.1 |
| T1.6.4 | `knowledge_documents` 状态流转（含 `INDEXING→INDEXED` 轮询确认） | 状态机单测 | T1.6.3 |
| T1.6.5 | **"INDEXED 才可提问"口径**：检索前置状态校验 | 未索引时不返回内容 | T1.6.4 |

### S1.7 对话流（编排）

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T1.7.1 | 消息分类器：链接消息 / 选择回复（1|2）/ 普通提问 | 分类单测 | T1.3.1 |
| T1.7.2 | 选择卡片生成（仅本篇 / 整库[置灰]） | 卡片数据结构单测 | T1.7.1 |
| T1.7.3 | `SINGLE_FETCH` Job 编排：Extract→Normalize→Asset→Upload→Index | 端到端集成测试（真实链接） | T1.4.7, T1.5.2, T1.6.3 |
| T1.7.4 | 进度回执（入库中 → 完成通知） | 回执时序单测 | T1.7.3 |
| T1.7.5 | 普通提问 → LangBot `/bots/{uuid}/sync` → 回复透传 | 集成测试 | T0.5.4 |
| T1.7.6 | **出站回调端点** `POST /api/v1/bot/callback`（HMAC 验签 + 1→M 合并） | 签名校验单测 + 多段合并单测 | T0.5.5 |
| T1.7.7 | `POST /api/v1/chat`（Web 对话入口，复用同一编排） | 端到端：发链接→选 1→回执→提问 | T1.7.3, T1.7.5 |

### S1.8 前端 + 验收

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T1.8.1 | Next.js 布局（**多套浅色主题**、默认中文、**搜索框仅顶部**——主平台铁律） | `pnpm build` 过 | T0.10.1 |
| T1.8.2 | SSO 登录态接入 + 登录跳转 | 登录后回跳正确 | T1.2.5 |
| T1.8.3 | 首页：粘贴链接建库输入框 + 最近更新列表 | 页面可交互 | T1.8.2 |
| T1.8.4 | 知识空间列表页 + 新建空间 | CRUD 可用 | T1.8.2 |
| T1.8.5 | 聊天页：选择卡片交互 + 消息流 + 引用展示 | 完整对话可跑 | T1.7.7 |
| T1.8.6 | M1 硬门禁演示脚本（真实公众号链接全流程） | **e2e 全绿** | 全部 |
| T1.8.7 | `.docs` 回写：API 文档 / 数据模型 / ADR 补充 | 文档与代码一致 | 全部 |

---

## M2 · 整库导入 + 订阅增量 + 微信通道（7 模块 · 26 任务）

### S2.1 Redfox Discovery

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T2.1.1 | `providers/redfox` 客户端（鉴权 + 两库端点 + 错误分类） | 客户端单测（mock） | T0.2 实证 |
| T2.1.2 | 公众号定位策略：wxId → bizInfo → 账号名（按实证成功率排序） | 定位单测 | T2.1.1 |
| T2.1.3 | 作品清单拉取（优质库→广域库降级 + 分页游标 + 限流 throttle） | 3+ 公众号实测清单完整率 | T2.1.2 |
| T2.1.4 | 清单缓存（Redis，TTL 可配）+ 成本计数 | 缓存命中单测 | T2.1.3 |

### S2.2 Manifest 与 Diff

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T2.2.1 | `article_manifests` 快照写入（全量替换式快照） | 快照单测 | T0.11.1 |
| T2.2.2 | Diff 算法：`external_id` 定存在 + `content_hash` 定变更 → NEW/UPDATED/REMOVED/UNCHANGED | Diff 单测（含修改/删除/补录/乱序） | T2.2.1 |
| T2.2.3 | REMOVED 处置策略（软删除标记 vs 真删向量）→ 默认软删 + 可配 | 策略单测 | T2.2.2 |

### S2.3 整库导入 Job

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T2.3.1 | `FULL_IMPORT` Job：清单 → `job_items` 批量派发 | 派发单测 | T2.1.3, T1.5.4 |
| T2.3.2 | 逐篇入库即索引（不等全量完成） | 进度可观测 | T2.3.1 |
| T2.3.3 | PARTIAL_SUCCESS 聚合 + 失败清单（原因可查） | 模拟 200 篇：部分失败 → 状态正确 | T2.3.2 |
| T2.3.4 | 失败单篇重试 / 断点续传 | 重试后转 SUCCESS | T2.3.3 |
| T2.3.5 | 并发与限流（worker 并发度 + Redfox 全局速率限制） | 限流单测 | T2.3.1 |

### S2.4 订阅与增量调度

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T2.4.1 | `source_subscriptions` 生命周期（创建/暂停/恢复/删除） | CRUD 单测 | T0.11.1 |
| T2.4.2 | Celery beat 定时触发 → Diff → 仅处理 NEW/UPDATED | 时钟伪造单测 | T2.2.2 |
| T2.4.3 | 水位推进 + `next_run_at` 动态计算（长期无更新自动降频） | 降频策略单测 | T2.4.2 |
| T2.4.4 | 增量入库后**立即可检索**（无重启） | 集成测试 | T2.4.2 |

### S2.5 微信通道（按 D9 决策执行）

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T2.5.1 | **路径 A**：LangBot `openclaw-weixin` 适配器接入 + 扫码上线 | 微信收发通 | T0.8.1 |
| T2.5.2 | 路径 A 下的用户身份关联（微信 userId ↔ SSO sub 绑定表） | 绑定表单测 | T2.5.1 |
| T2.5.3 | **路径 B（可选）**：`providers/clawbot` 客户端封装（绑定/解绑/发送） | 客户端单测 | T0.8.2 |
| T2.5.4 | `NotificationChannel` 抽象统一两条推送路径 | 抽象接口单测 | T2.5.1, T2.5.3 |
| T2.5.5 | 主动推送：任务进度 / 完成通知 / 新文章提醒 | 真机收到 | T2.5.4 |

### S2.6 对话流 v2

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T2.6.1 | 整库选项激活（展示预计篇数 = 清单 count） | 卡片数据正确 | T2.1.3 |
| T2.6.2 | 确认/取消交互 + 进度推送（"已采集 12/86 篇"） | 进度推送时序单测 | T2.6.1 |
| T2.6.3 | 命令词：`/同步` `/状态` `/列表` `/帮助` | 命令路由单测 | T2.6.1 |
| T2.6.4 | 引用溯源：回答 → chunk → 文档 → asset → 原文 URL | 全链可点 | T1.6.4 |

### S2.7 M2 验收

| ID | 任务 | 产出 / 验收标准 | 依赖 |
|---|---|---|---|
| T2.7.1 | 整库导入真实公众号 ≥100 篇演示（含制造部分失败） | **PASS** | T2.3.4 |
| T2.7.2 | 增量同步演示（公众号新发文 → 自动入库 → 立即可检索） | **PASS** | T2.4.4 |
| T2.7.3 | 微信真机全链：发链接 → 选模式 → 收进度 → 提问 | **PASS** | T2.5.5 |
| T2.7.4 | `.docs` 回写 + ADR 补充 | 文档一致 | 全部 |

---

## M3 · Web 管理后台 + 体验打磨（6 模块 · 20 任务）

### S3.1 信息源管理
| ID | 任务 | 验收 |
|---|---|---|
| T3.1.1 | 信息源列表页（类型/状态/文章数/最近同步） | 数据正确渲染 |
| T3.1.2 | 信息源详情页（文章清单 + 同步历史） | 可翻页筛选 |
| T3.1.3 | 立即同步 / 暂停订阅 / 恢复 / 删除 | 操作生效并回写状态 |

### S3.2 任务中心
| ID | 任务 | 验收 |
|---|---|---|
| T3.2.1 | 任务列表（类型/状态/进度/耗时） | 实时刷新 |
| T3.2.2 | 任务详情（`job_items` 逐篇状态 + 失败原因） | 失败可定位 |
| T3.2.3 | 失败重试（单条 + 批量） | 重试后状态更新 |
| T3.2.4 | 任务中心与对话流进度同源 | 两端一致 |

### S3.3 内容与检索体验
| ID | 任务 | 验收 |
|---|---|---|
| T3.3.1 | 文章浏览页（按源/时间筛选、Markdown 渲染、原文跳转） | 渲染正确 |
| T3.3.2 | 全站搜索框（顶部唯一）→ 跨空间检索资产 | 命中正确 |
| T3.3.3 | 引用溯源 UI 打磨（引用气泡 → 原文锚点） | 可点可跳 |
| T3.3.4 | 知识空间管理（新建/重命名/删除/绑定机器人） | 操作生效 |

### S3.4 计费模型预留
| ID | 任务 | 验收 |
|---|---|---|
| T3.4.1 | `billing_policies` 表 + 后台读取（不接真实扣费） | 配置可读写 |
| T3.4.2 | 积分预估/冻结/结算接口骨架（预留，返回 not-implemented） | 接口契约就位 |
| T3.4.3 | tier 门禁可视化（NORMAL/PRO/MAX 能力矩阵） | 前端展示正确 |

### S3.5 性能与可观测
| ID | 任务 | 验收 |
|---|---|---|
| T3.5.1 | 清单/内容缓存失效策略 | 失效及时 |
| T3.5.2 | 结构化日志 + 外部调用耗时埋点 | 埋点可查 |
| T3.5.3 | 慢任务告警 + 失败率告警 | 阈值触发 |
| T3.5.4 | Redfox 调用成本看板 | 成本可见 |

### S3.6 生产部署
| ID | 任务 | 验收 |
|---|---|---|
| T3.6.1 | `compose.prod.yml` + 生产镜像 | 构建通过 |
| T3.6.2 | 环境变量五件套 + 密钥注入流程 | 无明文密钥 |
| T3.6.3 | 数据库备份与恢复演练 | 恢复成功 |
| T3.6.4 | M3 验收门禁 + `.docs` 全量回写 | 全绿 |

---

## M4 · 视频源 + 会员积分（占位 · 不在本计划实施）

- T4.x.1 视频源解析器（抖音/B站/小红书 URL 识别）
- T4.x.2 `VideoDownloader` 抽象（yt-dlp 为主，lux/cobalt 为 fallback）
- T4.x.3 ffmpeg 抽音 + VAD 静音切除
- T4.x.4 ASR 带时间戳转写 → 分段并行
- T4.x.5 LLM 三段式摘要（分段摘要 / 全文要点 / 关键时间码）
- T4.x.6 ContentAsset 扩展 `content_type=video` + 时间码检索
- T4.x.7 BillingPolicy 落地（冻结 → 实扣 → 退款）
- T4.x.8 tier 门禁（视频能力仅 PRO/MAX）

---

# 九、验收门禁与 DoD

## 9.1 每个原子任务的 DoD
1. 代码提交且通过 CI（lint → type-check → 单测 → build）；
2. 有对应测试（新增逻辑必有单测，跨层必有集成测试）；
3. `.docs/` 受影响文档已回写；
4. 无明文密钥、无 TODO 遗留（TODO 必须转为 `job_items` 或任务）。

## 9.2 里程碑硬门禁

| 里程碑 | 硬门禁（不满足禁止进入下一阶段） |
|---|---|
| **M0** | 11 项能力实证全部有 PASS/FAIL 结论 + 触发的回退已定案；4 份 ADR 用户确认；`docker compose up` 全家桶可跑；CI 绿 |
| **M1** | 真实公众号链接 → 选「仅本篇」→ 数秒内入库 → 立即提问 → 得到**基于该文章的带引用回答**（端到端 e2e 脚本 PASS） |
| **M2** | ①整库导入 ≥100 篇（含人工制造部分失败 → PARTIAL_SUCCESS + 可重试）；②定时增量自动入库新文章且无重启即时可检索；③微信真机收发全链 |
| **M3** | 全站可演示 + `compose.prod` 部署成功 + 备份恢复演练通过 |

## 9.3 全局红线
- 未出 ADR 的架构决策不得落代码（§六步循环①）；
- 本计划外功能不实施；
- 每次 M0 实证 FAIL 必须先看回退矩阵，不擅自改方案。

---

# 十、风险与回退矩阵

| # | 风险 | 触发信号 | 回退动作 | 影响 |
|---|---|---|---|---|
| R1 | **主平台未上线/不可达** | T0.7.1 FAIL | **路径 A**：本地 Mock IdP + 自建极简 JWT，M1 跑业务，M2 切真 SSO | 中（多一次登录改造） |
| R2 | `_knowledge_base_uuids` 属隐式契约，LangBot 升级后移除 | 任何 LangBot 版本升级 | 版本 pin v4.10.9；升级前重跑 T0.5.3；D4a-C（R2 全自编排）为兜底路径 | 低（已 pin） |
| R2a | 多 KB 路由三路径均不达标（A 运维爆炸 / B 插件失效 / C 开发量超预期） | T0.5.3 实测 | AideanBot 亲调 `retrieve`（支持 per-request `retrieval_settings`）+ 亲调主平台网关 LLM（对话编排全上收，LangBot 仅保留 IM 通道） | 高（架构调整，出 ADR） |
| R3 | LangBot ingest 不接受 Markdown 文件 | T0.4.4 FAIL | 改 PDF/HTML 形态（parser_plugin_id 可配），或自建 pgvector 管道（ADR 重评审） | 高 |
| R4 | /gateway/chat 与 LangBot Provider 路径不匹配 | T0.6.2 FAIL | LangBot 暂配自有 Key；或加 10 行 FastAPI 反代适配 | 低 |
| R5 | Redfox 定位/清单能力不达标 | T0.2 成功率不达标 | 整库降级为「单篇 + 手动批量」；订阅推迟到 M3 | 中 |
| R6 | wandao 解析成功率 < 60% | T0.3.2 FAIL | 提前引入 firecrawl 为主路径（本地已有源码） | 中 |
| R7 | 微信 iLink 风控/扫码失败 | T0.8.x FAIL 或 M2 真机不稳 | 通道降级为**单向主动通知**；问答留 Web + LangBot 多平台 | 中 |
| R8 | LangBot API Key 绑定单一 workspace | T0.5.2 结论为"绑定" | 单 workspace + `knowledge_space_id` 逻辑隔离（D8 已按此起步） | 低 |
| R9 | docker/.env 中 Key 已泄露 | T0.1.1 执行前 | **必须先轮换再实证**，不得带旧 Key 跑任何测试 | 高（安全） |
| R10 | 混合技术栈维护成本超预期 | M1 中期评估 | 评估迁移到全 TS（wandao 逻辑 TS 重写，+1~2 周） | 中 |

---

# 十一、待决策清单（**请逐项拍板，我据此定稿**）

> 以下 6 项在计划中已给出推荐值与默认假设；确认时请明确「同意推荐」或「改为 X」。

| # | 决策项 | 推荐 | 备选 | 影响面 |
|---|---|---|---|---|
| **D1** | 技术栈 | FastAPI(Python) + Next.js(TS) | 全 TS（Next.js 全栈 + firecrawl 为主解析器，+1~2 周） | 全局 |
| **D9** | 微信通道 | 双轨：LangBot `openclaw-weixin` 为主（机器人号）+ wechat-clawbot 为推送（用户绑定号） | ①只用 LangBot 适配器 ②只用 wechat-clawbot | M2 |
| **Q1** | Redfox Key 轮换时机 | **立即轮换**（当前 Key 已明文落盘，虽被 gitignore） | 延后（不推荐） | M0 前置 |
| **Q2** | 主平台环境 | 请提供可用地址（生产/测试/本地），否则走回退路径 A | Mock IdP | M0/M1 |
| **Q3** | `wechat-rag` client 凭据 | 请提供 clientId/secret/redirectUris | — | M0.7 阻塞 |
| **Q4** | M4（视频+积分）是否纳入本计划 | 不纳入（仅占位） | 纳入详细设计 | 计划范围 |
| **D4a/Q5** | LangBot 多 KB 路由路径 | **B：单 bot + PromptPreProcessing 插件按会话改写 `_knowledge_base_uuids`**（E13 官方注释确认扩展点；代价：依赖私有变量，须版本 pin + ADR 锁定） | A：每 KnowledgeSpace 一组 bot+pipeline（公开契约，运维重）；C：R2 全自编排（零耦合，开发量最大） | M1 对话流 |
| **Q6** | 会话→知识空间解析规则（ADR-0003 必填，OpenCode 复审发现的决策空洞） | 仅"当前选中空间"检索 + 显式"全部空间"开关（符合隐私直觉） | 永远聚合全部空间 / 按消息来源自动路由 | M1 T1.7 |

---

# 十二、执行约定（对齐用户规则与主平台规范）

1. **文档即真源**：实现与文档冲突时以可运行代码为准并回写 `.docs/`。
2. **实证优先于推理**：任何外部依赖的行为，先 curl 拿到证据再写进架构。
3. **单点推进**：同一时刻只做 M{x} 中的一个模块，不做未完成态的并行。
4. **测试脚本与临时报告提交前移除**；关键决策写入 ADR 与 `.workbuddy/memory/`。
5. **SOLID / 高内聚低耦合 / DRY**：`providers/` 是唯一外部防腐层；Route 不写业务逻辑。
6. **未出 ADR 不改架构**；本计划外功能不实施。

---

> **本计划到此为止，等待确认。确认后从 T0.1.1（Redfox Key 轮换）开始执行。**
