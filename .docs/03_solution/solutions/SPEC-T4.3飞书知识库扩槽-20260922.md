# SPEC-T4.3：飞书知识库扩槽——路径比选与重新立项建议

> 状态：**v0.1 DRAFT，待管理者 APPROVE** | 日期：2026-09-22 | 归属域：A（docs）
> 任务锚：`剩余任务原子化执行大纲` T4.3「飞书知识库扩槽 SPEC（新引擎位，飞书≠Coze API）」，依赖栏原记「SPEC 立项」。
> 纪律：**起草 ≠ 实施**。本 SPEC 提交后飞书相关代码零开工；含 Alembic 迁移的任何分支须二次签批。
> 同级参照：SPEC-M3（T5.0a）同为 DRAFT 待批；本 SPEC 与 T4.4（ima 调研）共享同一纪律——**外部能力未实证前不排产**。

## 〇、立项前提质疑（本 SPEC 的核心产出）

大纲 T4.3 的标题含两个信号：**「新引擎位」是未经验证的预设**，**「飞书≠Coze API」是已被识别的警示**。两者叠加时，正确动作不是直接写引擎适配器规格书，而是先验证预设能否成立。

**结论先行**：建议**否决「飞书 = 引擎位 E5」**，改按**「采集源 `feishu_wiki`」**重新立项（与公众号 `wechat_oa` 同级，走既有 T2 采集链路）。理由见 §一（引擎位硬门槛）与 §三（路径比选）；§二 的能力对表**全部标记待核**，不下 PASS/FAIL 裁定。

本 SPEC 因此不是引擎实现规格书，而是**路径比选 + 重新立项建议 + 决策点清单（§五）**。

## 一、可插拔引擎位的硬定义（证据锚）

### 1.1 端口六方法（`backend/app/providers/engine_port.py:22-49`）

```text
KnowledgeEnginePort(Protocol)
  name: str
  create_kb(space_name) -> str
  upload_file(kb_id, filename, content) -> str
  ingest_status(kb_id, file_id) -> str
  retrieve(kb_id, question, top_k=5) -> list[dict]
  delete_file(kb_id, file_id) -> None
  delete_kb(kb_id) -> None
```

六方法中五个是写侧（建库/上传/状态/删文档/删库），**只有一个是读侧 `retrieve()`**。而检索是引擎位的存在理由：ADR-0004 §一明确「不部署向量库/Embedding/解析器」，小白路径的终点是契约 ⑧「第一次 API 检索」。

### 1.2 路由三条件（`engine_port.py:219-267`）

```text
EngineRouter.available(engine) = configured() AND allowlisted() AND ENGINE_IMPLEMENTED.get(engine, False)
```

- `ENGINE_ORDER = ["builtin", "main", "coze", "dify", "fastgpt"]`（:184）
- `ENGINE_IMPLEMENTED`（:210）注释原文：**「骨架位（六方法 NotImplementedError）不可路由，杜绝伪 available」**
- 即：**任何六方法无法全实接的引擎位，必然永久不可路由**。

### 1.3 ADR-0004 §四 SaaS 契约 8 项（引擎位验收门禁）

```text
① 注册后能否直接拿 API Key
② API 创建知识库/数据集
③ API 上传 PDF/Word/Markdown/TXT
④ API 上传 URL（无则由我方下载后转文件上传兜底）
⑤ 自动解析完全托管（我方只传文件/文本）
⑥ API 查询/检索（返回 原文+来源+文档ID）
⑦ API 更新/删除
⑧ 小白从注册到第一次 API 检索步数（越少越好，选型权重最高）
```

关键不对称：**缺 ④ 有明文兜底**（§四末：用 `ContentAsset.markdown` 转文件上传，不阻塞）；**缺 ⑤/⑥ 无任何兜底**。⑥ 缺失即意味着该服务根本不是一个「知识库引擎」，而是一个「内容存储」。这是本 SPEC 后续推理的支点。

## 二、飞书能力对表（§四 8 项）

> ⚠️ **本节全部条目状态 = 待核**。起草会话未取得飞书开放平台可验证访问（无应用凭据，Web 检索未返回可用结果），故只列**需核问题 + 核验方法**，不下裁定。此即大纲 T4.4「ima 开放 API 未证实，调研 PASS 前不排产」的同一纪律。
> 表中出现的飞书 API 路径名（如 `wiki/v2`、`docx/v1/.../raw_content`）为**待核假设，非已验证事实**。

| 项 | 需核问题 | 核验方法 | 判读 |
|---|---|---|---|
| ① | 注册后能否直接拿 Key，还是需企业管理员审批链？ | 建测试租户自建应用，实测计时 | 若需审批链，⑧ 步数显著劣化 |
| ② | 是否开放「创建知识库空间」？知识库是 wiki space + node 树 | 查 API 目录 | — |
| ③ | 是否有 PDF/Word/Markdown/TXT 上传入知识库的 API | 查 docx/drive upload 面 | — |
| ④ | 是否有「URL 抓取入知识库」 | 大概率为无 | **不阻塞**（§四末兜底） |
| ⑤ | 是否自动 chunk + embedding 完全托管 | 核验 | **引擎位路径的生死项之一** |
| ⑥ | 是否有向量语义检索 API（返回原文+来源+文档ID） | 核验 | **引擎位路径的生死项之一** |
| ⑦ | 是否开放更新/删除文档 | 查 files delete 面 | — |
| ⑧ | 注册→首次检索的总步数 | 依赖 ①⑥ | 与 ① 审批链风险叠加 |

### 2.1 结构性判断（不依赖凭据即可推出）

飞书开放平台的定位是**办公文档协作 + 权限分发**，其知识体系为 `wiki space → node → docx/drive file` 的**内容树**，正文读取需从文档 id 二次取正文。这是**内容源 API 形态**，与 Coze/Dify/FastGPT 的 `dataset + retrieval` 形态在语义层面不同类。即便存在某种「知识问答」能力，也绑定特定应用类型与审批，不构成通用托管向量检索服务。

因此 **⑤/⑥ 双缺的概率极高**，路径 A 的期望值为负。§2.1 是判断而非事实，⑤/⑥ 的最终裁定仍待 D11（见 §五）。

## 三、路径比选

### 路径 A：飞书 = 引擎位 E5（大纲原写法）

- 做法：`ENGINE_ORDER` 加第 6 位 `"feishu"`；`make_engine()` 加分支；`ENGINE_IMPLEMENTED["feishu"]=False`；config 加 `feishu_*`；前端选择器第 6 项。
- 差量文件：`engine_port.py`（3 处）、`config.py`（3 字段）、前端 engines 列表（2 处）。
- **致命缺陷**：`retrieve()` 无宿主 → 六方法无法全实接 → `ENGINE_IMPLEMENTED` 永为 False → `available()` 永假 → **前端置灰，永久不可用**。等于占一个引擎位而不可路由，与其对称的「伪 available」同样违背 `engine_port.py:210` 的立法意图（伪 slot 与伪 available 同恶）。
- **变体 A'（伪引擎壳）**：`retrieve()` 委托 builtin LangBot，飞书只存原文。此时 `available()` 为 True，但语义破产——用户以为在飞书检索，实际检索 LangBot；`citations` 三元 `{title, spaceName, engine}` 中的 `engine` 将指向一个不产生任何检索结果的服务，违反 ADR-0004 §七「多引擎 citations 归属」的语义正确性。
- **结论：否决。**

### 路径 B：飞书 = 采集源 `feishu_wiki`（推荐）

与公众号同级，走既有 T2 链路：`Source(type, external_id) → ArticleManifest → ContentAsset → ingest → builtin 向量库`。

- **零迁移**：`Source.type` 已是 `String(32)`（`entities.py:56`，注释 `wechat_oa | web(M4)`）；`uq_source_type_external = UniqueConstraint("type","external_id")`（:62）**已按 type 分域建键**，新增 type 值不需改约束。
- 施工差量（全部可脱机）：
  1. `source_resolver.py:24` 的 `ALLOWED_HOSTS = {"mp.weixin.qq.com"}` 单常量 → per-source-type 白名单；
  2. 新 `feishu_wiki_resolver`：节点遍历 + 正文抽取（锚点体系与公众号 `#js_content`/`var biz` 完全不同，**HTMLParser 不可复用**）；
  3. 幂等键：飞书 `space_id + node_token`；`uq_manifest_source_external = UniqueConstraint("source_id","external_id")`（:106）天然兼容。
- 检索始终走 builtin → **不需要新引擎位**，检索语义单一可预期。
- 与 SPEC-M3 扩展点③同源：`Source.type=web` 在 M4 预留，飞书是**第二个具体采集源**，正好验证该扩槽协议是否真可走。

### 路径 C：混合（飞书采集 + 引擎位壳）

A' + B 双写，同时付两份成本，价值最低。**否决。**

### 3.1 比选矩阵

| 维度 | 路径 A | 路径 B |
|---|---|---|
| 需新引擎位 | 是（第 6 位） | 否 |
| `retrieve()` 宿主 | 无 / 借 builtin | builtin（明确） |
| `available()` 可达 | 永假 / 语义假 | 不适用 |
| Alembic 迁移 | 无 | **无**（`type` 已 `String(32)`） |
| 对 ADR-0004 §四 契约 | ⑤⑥ 双缺 | 不适用（非 SaaS 引擎） |
| `citations.engine` 语义 | 错误指向 | 始终 builtin，正确 |
| 施工可脱机 | 是 | 是 |
| 外部依赖 | 飞书 Key + 审批链 | 飞书 Key + 审批链 |
| **结论** | 否决 | **采纳** |

## 四、立项建议（需管理者裁定后生效）

**建议 1（主）**：T4.3 更名为**「飞书知识库采集源接入 SPEC」**，从 T4 轨道（引擎实接）移入**采集源轨道**（与 T2 公众号链路同构，M4 定位）；验收门禁改用 §4.2 采集源契约，不再套用 ADR-0004 §四 8 项。

**建议 2（保留）**：若坚持「飞书必须可选为引擎」，先完成 §二 的 ⑤/⑥ 实证核验；**仅当 ⑥ PASS 才建引擎位**。核验成本约 1 天，需新建飞书测试租户应用（新外部锁 D11）。

**建议 3（无论裁向）**：`ENGINE_ORDER` 加第 6 位**暂缓**——现 5 位中仅 builtin 实接，扩位不带来任何可用引擎。

### 4.2 采集源契约（路径 B 的验收门禁，5 项）

```text
① 授权：自建应用 app_id/app_secret + tenant_access_token 刷新；权限集最小化
② 枚举：给定 wiki space_id 能列出全部节点（含文件夹递归 + 更新序）
③ 抽取：单节点 → 规范化 Markdown（标题层级/列表/图片/表格），对齐 ContentAsset.content_markdown 语义
④ 增量：以 node 更新时间为水位，接 SourceSubscription.next_run_at 与 consecutive_empty_syncs 退避
⑤ 幂等：space_id + node_token → uq_manifest_source_external 唯一；正文变更走 ContentAsset.version+1 superseded
     （复用 T2.7 已锁定的五层幂等链，零新增约束）
```

验收证据锚：与 T2.1 同格式的 `evidence/t43_feishu_*.txt`（真实节点枚举 + 抽取 diff）；脱机施工半程可按 `_seed_manifests` 先例先建至「待活体验证」态。

## 五、需管理者裁定项

| # | 待裁 | 选项 | 建议 |
|---|---|---|---|
| Q1 | 飞书归引擎位还是采集源 | A 引擎位 / B 采集源 / 先核 ⑥ 再定 | **先核 ⑥ 再定，默认按 B 立项** |
| Q2 | 是否新建 D11（飞书测试租户应用凭据） | 开 / 不开 | 开（无凭据则 §二 全表永久待核，⑤/⑥ 无法裁定） |
| Q3 | 优先级 vs T6.1 微信 Bot 接线 | 先飞书 / 先 Bot / 并行 | **先 Bot**（微信是产品主线通道；飞书非 MVP 信息源） |
| Q4 | 是否与 T4.4 ima 合并一次调研窗口 | 是 / 否 | 是（同为「外部知识源开放 API 存疑」同类项，合并省一次立项） |

## 六、外部锁与不排产声明

- **D11 飞书凭证（本 SPEC 新登记）**：无应用凭据 → §二 8 项全待核 → 路径 A 可行性无法判定 → **飞书引擎位实接不排产**。
- **飞书审批链风险**：企业级产品，自建应用常需 IT/管理员审批，与 ADR-0004 §四 ⑧「小白步数越少越好」直接冲突。这条冲突本身就不支持「飞书作为小白首选 SaaS」的立项动机。
- **最强先例证据**：ADR-0004 §二 明确将 Notion 排除在引擎位之外，理由原文「**列 CMS（存原文/元数据，不当 RAG 引擎）**」。飞书知识库与 Notion 在「内容树而非向量库」这一点上同类。已有裁决足以支撑本 SPEC 的主张，无需重开选型辩论。

## 七、不做清单

1. 不改 `ENGINE_ORDER` / `ENGINE_IMPLEMENTED`（暂缓，见 §四建议 3）；
2. 不建 `FeishuAdapter` 骨架（六方法 `NotImplementedError` = 死代码 + 伪 slot，与 `engine_port.py:210` 立法意图冲突）；
3. 不加 `feishu_*` config 字段（无消费者）；
4. 不写 Alembic 迁移（路径 B 零迁移需求）；
5. 不动 `source_resolver.py`（`ALLOWED_HOSTS` 改动属施工半程，须 Q1 裁定为 B 后开工）；
6. 不做前端引擎选择器第 6 项。

## 八、自纠：SPEC-M3 两处失实（本批同步修正）

起草本 SPEC 时逐字比对 `engine_port.py`，发现 SPEC-M3 §三（引擎位扩槽协议）两处与代码不符，已回写：

| SPEC-M3 原文（错） | 代码真值 |
|---|---|
| 六方法 `ensure_kb / upload / status / retrieve / delete / describe` | **`create_kb / upload_file / ingest_status / retrieve / delete_file / delete_kb`**（`engine_port.py:22-49`）；无 `ensure_kb`/`describe` |
| 配置形态 `{engine}_api_base / {engine}_api_key / {engine}_kb_id` | **SaaS 位仅 `{engine}_api_key`**（`make_engine` :187-201，`getattr(settings, f"{name}_api_key","")`）；`_api_base` 仅 main 位有（`main_kb_api_base`）；**`_kb_id` 不存在于 config**——KB id 存 PG `knowledge_spaces.engine_kb_id`（`entities.py:45`），由 `EngineRouter.kb_id_for()` 读取，非配置项 |

影响评估：SPEC-M3 的**扩槽协议结论不受影响**（五步清单、`ENGINE_IMPLEMENTED` 单开关点、三条件 `available()` 均正确），失实仅在字段名级细节，属可回写范围，不推翻五批次划分与七项外部锁登记。

对照核验：ADR-0004 §八 的六方法列表与本表「代码真值」列逐字相符，**ADR 无误——错误只在我先前写的 SPEC-M3**，本处如实登记。
