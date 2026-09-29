# API 接口文档

> 版本：v0.22（v0.21 + **R8 契约纠偏后的入口校验 + 证据状态字段**——①`POST /api/v1/sources` 新增 biz 形态校验与拒绝口径（`10005`/422），并把「缺参数」从 30004 改为 `10005`/422；②`GET /api/v1/admin/discovery/channels` 的 `channels[]` **追加** `contractVerifiedAt` / `verifiedScope` 两字段；③`manifest_sync_max_pages` 语义澄清为**回填硬上限**。见 §十） | 更新：2026-09-28
> ⚠️ **版本登记漏档（v0.22 补记）**：§九（R7.7 常驻进程存活）登记时**未递增版本号**，v0.21 的标题只覆盖了 R7.6。此处补记而不回填改写 v0.21——历史记录应保持原样，只在追加处标注。
>
> 版本：v0.21（v0.20 + **R7.6 发现渠道改为后台可配置**——新增 `GET /api/v1/admin/discovery/channels`
> （`operator`+，返回 `channels[]` 的 `implemented`/`enabled`/`available` 三轴 + `defaultChannel` /
> `selectionReason` / `configuredChannels`）。**零迁移、零错误码新增、既有端点语义一字未改**。
> 渠道选择从代码硬编码改为 `discovery_channels` + `discovery_default_channel` 两个后台配置项；
> 注册表新增 `rss` 为**未实接占位**，使「只有 RedFox 一个通道」这一缺口在运行系统内可见
> （`implemented=false`），不再只能靠翻代码发现。见 §八） | 更新：2026-09-28
>
> 版本：v0.20（v0.19 + **R4 第八/九波收官：admin 域补齐作业与订阅跨用户读面、信息源写面收口、跨用户删空间，及 OpenAPI 安全方案**——①**新增三条 admin 读端点** `GET /api/v1/admin/jobs` / `GET /api/v1/admin/jobs/{job_id}` / `GET /api/v1/admin/subscriptions`，与 §6.2 同源手法（Service 抽出单一实现、`owner=None` 表达「无归属约束」，形状与用户端点一致），admin 面 **10 → 13 个路径（11 → 15 个操作）**；②**新增 `PATCH /api/v1/sources/{source_id}`**（`admin`+，与 `DELETE` 同门禁同口径），`type`/`external_id` 不可写；③**新增 `DELETE /api/v1/admin/spaces/{space_id}`**（T5.8）。**`/api/v1/spaces` 仍 15 个路径（22 个操作），既有端点语义一字未改。** ④**修正 §6.2 一处失实**：此前 `DELETE /api/v1/sources/{id}` 的宽面已在本批收口到 `admin`，「任何登录用户当前可删任何信息源」不再成立（见 §6.2 更正注）。⑤**新增 §6.6 OpenAPI 安全方案**：`components.securitySchemes` 由恒空改为声明 `apiKey`/cookie 方案（名称取自 `session_cookie_name` 配置），**55 个操作中 50 个**标注为需会话、5 个为公开；标注取自**路由声明的依赖树**而非路径白名单，新端点自动纳入。**零迁移（Alembic head 仍 `ab1004m3b`）、零错误码新增**。见 §6.2e、§6.6 与文末条目 ⑱） | 更新：2026-09-23（R4 第八/九波落地，属**契约新增**——三条 admin 读端点 + 两条写端点 + 安全方案声明，故递增为 v0.20；**不改写 v0.19 及之前任何既有端点语义**；§6.2 的更正属**事实回写**，非契约变更）
> 统一响应信封：`{code, message, data, requestId}`（对齐主平台）；错误码段位见 `backend/app/core/errors.py`

## 一、URL 规范

- 格式：`/api/v1/{resource}/{action?}/{id?}`（Stripe 风格，对齐主平台）
- Route 层只做校验/鉴权/响应归一，业务逻辑在 Service

## 二、已实现（M0）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/v1/system/health | 健康检查（信封契约已测试） |

## 三、M1 计划接口（设计定案，实现随任务交付）

### 认证 auth（SSO）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/v1/auth/login | 302 跳主平台 authorize（state 强校验） |
| GET | /api/v1/auth/callback | code 兑换 + 服务端会话建立 |
| POST | /api/v1/auth/logout | 撤销 refresh 链 + 清会话 |
| POST | /api/v1/auth/backchannel-logout | **已实现（R9，2026-09-28）**：主平台 back-channel 登出接收，按用户广播销毁本地会话；**恒 200 同形**，验签 fail-closed（详见下方 §三·认证 补注） |
| GET | /api/v1/auth/me | 聚合 userinfo + 实时 wallet；**v0.19 增补 `user.is_admin: boolean`**——前端 admin 门禁的**唯一依据**（见 §6.1 末注与文末条目 ⑰） |

### 知识空间 spaces
| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | /api/v1/spaces | 列表/创建（创建时同步建 LangBot KB） |
| PATCH | /api/v1/spaces/{id} | **已实现（v0.14，R0.5.2）**：改空间简介（仅 `description`，部分更新） |
| POST | /api/v1/spaces/{space_id}/docs:batch | 批量粘贴入库（**202 提交即返**，Job 化；见文末 v0.7 条目） |

### 任务 jobs
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/v1/jobs | **已实现（v0.13，R0.4.1）**：清单分页，`type`/`status` 取值过滤 + `limit`/`offset` |
| GET | /api/v1/jobs/{id} | 详情（含 job_items 进度） |
| POST | /api/v1/jobs/{id}/retry | 失败重试 |
| POST | /api/v1/jobs/{id}/cancel | **已实现（v0.13，R0.4.2）**：仅 `QUEUED` 可取消 → `CANCELLED` |

### 对话 chat
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/v1/chat | 消息入口：链接→选择卡片；普通消息→LangBot sync 回复 |

## 四、错误码段位

`1xxxx` 用户/认证 | `2xxxx` 采集/信息源 | `3xxxx` 知识库/机器人 | `5xxxx` 系统
（完整登记表：`backend/app/core/errors.py`，先登记后实现）

**裁决记录（2026-09-07，A）**：
1. 新增 `10005 REQUEST_INVALID`（HTTP 422）：用于 `RequestValidationError` 及框架级 `HTTPException`(<500)。业务路由自 M1 起统一抛 `AppError`，禁用 `HTTPException`。
2. 未命中路由 404 暂维持框架默认 `{"detail":"Not Found"}`（M3 对外发布前以路径白名单改写中间件收口，已入 backlog）。
3. 错误码→HTTP 状态映射表 15 条核验通过；返工要求：`http_status_for()` 与各类 `http_status` 属性须收敛为单一来源（DRY）。

## 五、spaces 域字段契约（v0.3，2026-09-07 登记）

> 字段命名**统一 camelCase**（前端 C-T3 已按此实现，后端 B-T4 必须对齐；来源：C-T3 任务卡）：

- `GET /api/v1/spaces` → `data.items: [{id, name, description, docCount, updatedAt}]`
- `GET /api/v1/spaces/{id}` → `data: {id, name, description, docCount, createdAt, updatedAt, stats: {docs, chunks}}`；无效 id → `30004`（404）
- `GET /api/v1/spaces/{id}/docs` → `data.items: [{id, title, source, status, updatedAt}]`；`status ∈ pending|ready|failed`
- 列表/详情为登录保护接口：未登录 → `10001`（401），前端跳回首页引导卡。
- **v0.3a 补登（B-T4 裁决，A 批准）**：空间重名冲突新增 `30006 SPACE_NAME_CONFLICT`（HTTP 409），
  文案"空间名称已存在"；由 POST 建空间的 Service 层捕获 `IntegrityError(uq_space_user_name)` 映射，repo 层不感知契约。
- **v0.3b 补登（C-T4 契约差异裁决，A 批准）**：问答端点统一为 **`POST /api/v1/chat/ask`**，
  body `{spaceId, question}`（原 §三 的 `POST /api/v1/chat` 作废，以本条为准）；
  错误码：10001 未登录 / 30001 空间不存在 / 30002 LangBot 异常 / 50002 依赖不可用。
  流式协议（SSE 事件结构与 delta/citations 字段名）待 B-T5 交付时由 A 出变更单定稿。
- **v0.3c 补登（B-T4R 验收裁决，A 批准）**：
  ① `POST /api/v1/spaces` 响应复用详情形状（201）；
  ② `30004` 登记名由 `JOB_NOT_FOUND` 改为 **`RESOURCE_NOT_FOUND`**（空间/任务/文档通用 404 语义，
  代码类名 ResourceNotFoundError 已对齐）；
  ③ spaces 域 `description` 暂恒空串、`stats.chunks` 暂返 0（数据源在 LangBot 侧，B-T9 接线时定稿，
  非 mock 硬编码）；C 端联调时勿对二者做非空断言。
- **v0.3d 补登（B-T5 验收，A 批准）**：
  ① 新增 `10006 MALFORMED_URL`（HTTP 400，1xxxx 段=用户输入错误，裁决维持 B 的登记）：
  空串/非 http(s)/非白名单域名/超长>512/控制字符；
  ② 新增 `POST /api/v1/resolve`（登录保护 10001）：body `{url}` →
  `data: {title, author, publishTime, content, url, biz}`（camelCase）；
  错误：20001 非文章页 / 20002 网络失败；`content` 为轻量行式文本（完整清洗归 B-T6）。
- **v0.3e 补登（B-T6 验收，A 批准）**：
  ① 新增 `POST /api/v1/extract`（登录保护 10001）：body `{url}`（内部 resolve→extract）→
  `data: {title, author, publishTime, paragraphs: string[], images: [{src, caption}], wordCount, langbotFormat}`；
  ② 质量护栏**裁决复用既有 `20003 EXTRACT_QUALITY_LOW`（422）**：空文章（全噪音剔除后无段落无图片）
  及 html 缺失均 → 20003，不新增码位；
  ③ `ResolvedArticle.html` 为内部字段不进契约视图；`fmt`（wx_fmt）为图片内部字段，B-T7 评分用。
- **v0.3f 补登（B-T7 验收，A 批准）**：`POST /api/v1/extract` 响应 data 追加
  `qualityScore: int`（0-100）/ `qualityPassed: bool` / `qualityReasons: string[]`，
  既有字段不动（向后兼容）；及格阈值 30（后端常量 `QUALITY_PASS_THRESHOLD`，A 可调）；
  `passed=False` → 20003（与空文章护栏同码，reasons 可观测）。
- **v0.3g 预定义（A 主动下发，B-T8 直接照做免报备；①②已被 v0.3h 取代）**：
  ① `POST /api/v1/spaces/{id}/docs`（登录保护 10001；无效空间 30004）：body `{url: string}`
  → 后端内部 resolve→extract→normalize→score→ingest 全链；**202** 接受 →
  `data: {taskId: string}`（ingest 异步，与 M0 实证一致）；护栏失败（10006/20001/20002/20003）→ 同步返回对应错误码；
  ② `GET /api/v1/spaces/{id}/docs/tasks/{taskId}`（登录保护）→
  `data: {status: pending|running|succeeded|failed, progress: int(0-100), docId?: string, error?: string}`；
  ③ 幂等：同 url 同空间重复提交 → 20003 或 30005 由 B 裁定并在交付报告说明。
- **v0.3h 补登（B-T8 验收，A 批准，**取代 v0.3g①② 端点形状**）**：
  ① `POST /api/v1/spaces/{id}/docs`（登录保护 10001；无效空间 30004）202 响应 data 修订为
  `{docId, title, status, langbotFileId, taskId}`——`taskId` **恒为空串**（LangBot v4.10.9 实证
  无 task_id，字段位保留仅为形状稳定，前端勿依赖）；`status` 初始恒 `INDEXED`（已触发异步入库）。
  ② 状态查询端点改为 **`GET /api/v1/spaces/{id}/docs/{docId}/status`**（原
  `/docs/tasks/{taskId}` 形状作废；轮询凭证由 docId 承担）→
  `data: {docId, status, langbotFileId}`，`status ∈ FETCHED|INDEXED|READY`（本地状态机值）；
  LangBot 侧 completed→READY / processing·pending→INDEXED / failed→**30003 INGEST_FAILED（502）**
  抛错而非 200 返回（error 字段方案作废）；无 progress 字段（LangBot 文件清单无可靠进度值）。
  ③ 幂等裁定（v0.3g③ B 裁定补录）：同 url 同空间重复提交 → **覆盖 langbot_file_id 重走
  ingest，返回 202 不报错**（source 按 biz 幂等 / asset 按 hash 幂等 / doc 覆盖更新）。
  ④ 低质护栏维持 **20003（422）** 同步返回（B-T8 交付误抛 30003/502，B-T8R 返工修正中，
  联调前端暂勿依赖 30003 表达低质语义）。
- **v0.4 SSE 定稿（A 下发草案 → B-T9/B-T9R 实现 → 2026-09-08 A 容器级验收后定稿；C 按此更新解析器与测试）**：
  `POST /api/v1/chat/ask`（登录保护）：body `{spaceId, question}` →
  `200 text/event-stream`，每帧 `data: <单行JSON>`，事件以 `type` 判别：
  - 首帧：`{"type":"meta","citations":[{"title","spaceName"}]}`（引用先发，供前端先渲染来源区）
  - 内容帧 ×N：`{"type":"delta","content":"<增量文本>"}`
  - 终帧：`{"type":"done","messageId":"<uuid>"}`
  - 流中错误：`{"type":"error","code":<业务码>,"message":"..."}` 后服务端关闭流
    （已发出的 delta 保留展示，错误以气泡叠加——与 C-T4 既有 UX 一致）
  - 心跳：每 15s `{"type":"ping"}`（前端忽略）
  - 流前错误（鉴权/参数/空间不存在）：不走流，标准 HTTP 4xx + JSON 信封
    （C 既有"非流式回退"路径承接）。
  **对比 C 骨架的差异**：平铺字段（delta/content/citations）改为 type 判别单事件流；
  引用从收尾帧提前到首帧。
  **定稿确认（A，验收证据：容器级真实流级冒烟 meta→delta×N→done PASS）**：
  ① **data-only**：无 `event:` 行，C 解析器按 `data:` + `type` 判别，无需 event 监听；
  ② 流前码位定稿：10001/401（未登录）、10005/422（空问题）、30004/404（无效 id 与
  越权同语义，不泄露存在性）、**30002/502（空间 KB 未初始化——B 报备场景 A 裁决接受，
  M2 复议是否拆专用码）**；
  ③ 流中错误帧覆盖全 AppError 族（B-T9R：`except AppError`——30002/30003/30004/50002
  预包装形态均转 error 帧；裸 httpx 异常兜底 50002 帧）；
  ④ **M1 已知限制（T1.10 摘除，前端勿作验收对象）**：delta 为检索块拼装占位
  （`_compose_answer` 单点）、"触发错误"测试缝、ping 不覆盖 retrieve 阻塞期；
  ⑤ citation `title` 在 LangBot 将上传文件名改写为 hash 时会显示 hash 串
  （行为符合"file_name 尾段"契约，数据源特性非缺陷；本地 doc.title 已落库，
  T1.10 接 LLM 生成时一并用本地 title 替换）。
  ⑥ 错误码表更正：`30004` 登记名 `JOB_NOT_FOUND` → `RESOURCE_NOT_FOUND`
  （v0.3c 已裁决，errors.py 已于 B-T9R 同步落地）。
  ⑦ **v0.4a 集成观察（A-T8，2026-09-09，A 独立探针）**：
  - **打回 B 一项（P3 信息泄露/语义不一致）**：`GET /api/v1/spaces/{id}/docs/{docId}/status`
    对不存在 docId 抛 `30004`（HTTP 404）时，信封 `message` 为原始 docId UUID 串
    （复现：带会话 cookie 请求 `/api/v1/spaces/<sid>/docs/deadbeef/status`
    → `{"code":30004,"message":"9ebd4672-a357-...","data":null,...}`）。影响：message 应为人读
    语义串（对齐 v0.3h 口径），回填查询键无业务价值且轻微泄露检索细节。B 下卡或 B-T11 附带修，
    不单独为此重开工。
  - **OpenAPI 形状缺口（非阻塞，登记 M2）**：`POST /api/v1/spaces/{id}/docs` 在 `/openapi.json`
    的 requestBody schema 显示为空对象 `{}`，未烘焙 `IngestDocRequest{url:string}`；运行期校验正确
    （缺 body→10005/422）。属 FastAPI 模型注解接线问题，前端以本文档为准、勿依赖 OpenAPI。
- **v0.4b P0 资产缓存（AB-P004 阶段1，2026-09-14 登记）**：
  ① `POST /api/v1/spaces/{id}/docs` 202 响应 data 追加两个字段：
  - `hitCache: boolean` —— `true` 表示命中全局资产缓存（0 微信抓取请求，直接用 `content_markdown` 重传引擎）；
  - `hitCount: number` —— 命中次数（0=首抓，≥1=命中）；未命中时 `hitCache=false`、`hitCount=0`。
  ② 命中时前端 toast 文案：`命中缓存，秒入库`；未命中时正常显示 `入库中…`。
  ③ 号主改文（content_hash 变化）：asset `version+1`，旧 `doc` 标 `FAILED/superseded`，不静默覆盖；
     下次命中仍走同一 `(source_id, external_id)` 键，`hit_count` 重置为 0。
  ④ 低质拦截（20003）路径不变；命中复用路径不重新走质量护栏（缓存为已验收的 READY 资产）。
- **v0.5 P1 公共库端点（AB-P004 阶段2，2026-09-14 登记）**：
  ① `GET /api/v1/spaces/public`（登录保护 10001）→ `data.items=[{id,name,description,docCount,engine,isPublic,updatedAt}]`；
  ② `POST /api/v1/spaces/{id}/links {public_space_id}` → 200 `{copied, skipped, total}`；
     幂等：已 copy 的 doc 跳过（skipped+1），重复调用不报错；
     目标空间越权/无效 → 30004；公共空间无效/非公共 → 30004。
  ③ 公共库 SSE citations.spaceName 标注「AI前沿库」（零检索改动，copy 后走既有 SSE 链路）。



## 六、admin 域端点（SPEC-M3 批次 2 / A-2 叠加，2026-09-23 登记）

> **A-2 裁定（管理者，2026-09-23）**：既有用户端点一律不动，`admin` 的**跨用户**能力走本节
> 新增端点——零回归。§五 与 §三 中所有既有端点语义**一字未改**。
> 路由实现：`app/api/v1/admin.py`（新增），注册于 `app/main.py`；授权经
> `app/api/deps.require_roles("admin")` → `app/services/roles.require_role`（**单一来源**）。

### 6.1 角色阶梯（授权主判据）

| `users.role` | 秩 | 可访问 |
|---|---|---|
| `user`（默认） | 0 | 仅 §三/§五 的既有用户端点（本人数据） |
| `operator` | 1 | 全站**只读** + **引擎 Key 登记/撤销（§6.2b，批次 3 已实现）** + **推送触发（§6.2c，批次 5 已落地，诚实占位）** + 公共库审核（T5.5 按裁定不构建） |
| `admin` | 2 | 以上 + **本节跨用户读写（§6.2）** + **批量文档操作（§6.2d，批次 4 已落地）** + **作业/订阅跨用户读面 + 信息源写面（§6.2e，R4.8 已落地）** |

判定语义为**单调秩**：声明 `require_roles("admin")` 的端点，`role=admin` 放行、`operator`/`user`
均拒绝。`role ∈ roles` 的成员语义会拒掉 `admin`（`admin ∉ {operator}`），已否决。

> **秩不是越高越宽**：§6.2b / §6.2c 声明 `require_roles("operator")`，故 `admin` 经秩覆盖可访问；
> 但 §6.2 / §6.2d 声明 `require_roles("admin")`，`operator` 秩**低于** `admin`，**仍被拒**
> （403/10004）。批量删除是不可逆的破坏性操作且跨租户，故取 `admin` 而非 `operator`
> （§6.2d 与 §6.2b/§6.2c 的授权门槛不同，非笔误）。

> **`is_admin` 是本阶梯的读侧回显，不是第二份判定（v0.19）**：`GET /api/v1/auth/me` 返回
> `user.is_admin: boolean`，由**本地 `users.role` 经同一秩谓词** `has_min_rank` /
> `sub_has_min_rank` 派生，与 `require_role` 的裁决**共用单一来源**——故「回显
> `is_admin=true` 但调用 admin 端点 403」（或反之）在结构上不可能发生。`/me` 是**只读回显**、
> **绝不抛错**（任何角色都必须拿到 200 与自己的身份），故谓词返回布尔而非依赖，缺用户时
> 返回 `false` 而非抛错（fail closed 且不破坏登录态）；未知 `role` 取值一律按默认秩
> `user` 处理（`ROLE_RANK.get(role, ROLE_RANK[DEFAULT_ROLE])`），**不**按最高秩兜底。
> ⚠ 前端**不得**从 `user.role` 自行推导 `is_admin`：真实主平台 userinfo 的 `role` 是**大写
> 枚举**（`"USER"`），与本地阶梯**不同源、不同形**，据此门禁会与后端 10004 双向分歧。
> `is_admin` 缺失（旧后端未回显）时前端一律按 `false` 处理（fail closed）。

### 6.2 跨用户端点（`admin`，批次 2 + T5.8；本节 5 个路径 6 个操作，openapi() 实测）

| 端点 | 授权 | 语义 | 响应 data |
|---|---|---|---|
| `GET /api/v1/admin/spaces` | `admin` | **跨用户空间清单**（v0.19 新增），**注入归属三元组** | `{items: [Space + ownerId, ownerSub, ownerNickname]}` |
| `GET /api/v1/admin/spaces/{space_id}/docs` | `admin` | **跨用户文档清单**（v0.19 新增），`limit`/`offset`/`category` | `{items, total, limit, offset}` |
| `PATCH /api/v1/admin/spaces/{space_id}` | `admin` | 跨用户改空间简介（**仅 `description`**） | `{ok, id, description}`（**写回执**） |
| `DELETE /api/v1/admin/spaces/{space_id}/docs/{doc_id}` | `admin` | 跨用户删单篇文档 | `{ok, docId, docs, assets}` |
| `DELETE /api/v1/admin/spaces/{space_id}` | `admin` | 跨用户删整个空间（**T5.8，v0.20 新增**）——引擎删库先行、失败整体回滚、级联删 docs/assets/space 行 | `{ok, docs, assets, spaces}`（返回级联计数，admin 操作应可见影响面） |

- 前缀 `/api/v1/admin`，与 §五 的 `/api/v1/spaces` **无路径重叠**；`/api/v1/spaces` 仍 15 个路径
  （22 个操作，v0.20 实测；此前表述「15 条端点」按路径计数，未含单路径上的多动词）。
- **读面补齐缘由（v0.19）**：批次 2 后端竣工（v0.15）时 `/admin` 只有**写端点**，无读端点——
  A-2 叠加（既有端点零改动）的代价就是 admin 面**没有浏览能力**，前端控制台无从构建。
  本批补齐两条读端点。**Service 层承 `..._any` 手法**（承 v0.15 §6.1 与 v0.18 §6.2d）：
  `list_space_views_any` / `list_space_docs_any` 委托既有 `_space_view` / `_list_space_docs`
  并以 `owner=None` 表达「无归属约束」，**不复制方法体**——服务端分页、分类过滤、条数
  上限口径与用户端点**同源**（测试锁定 admin 面分页与分类过滤结果一致）。
- **归属三元组只在 LEFT JOIN 命中时注入**（非空对象）：`SpaceRepository.list_with_owner`
  用 **LEFT JOIN `users`** 而非 INNER JOIN——归属账号可能已被删除，INNER JOIN 会**静默吞掉**
  这些空间，而「有空间无主」恰恰是 admin 需要看到的异常态。前端据此区分「未归属」与
  「归属信息为空」。**既有用户端点响应不含这三个字段**（A-2 零回归锁，有测试断言）。
- 复用既有 `Space` / `SpaceDoc` 契约视图，**不复制模型**（同 v0.18 请求体复用口径）。
- **`DELETE /api/v1/admin/sources/{source_id}` 刻意不新增**：既有 `DELETE /api/v1/sources/{id}`
  **本就无归属校验**（`sources` 表无 `user_id` 列，全用户共享的全局资源），admin 变体
  **不增加任何跨用户能力**，只会多一道闸。为端点面一致而加一个空能力端点属范围蔓延。
  ⚠ **既有宽面保留是管理者明确接受的代价**——任何登录用户当前可删任何信息源。
  **（v0.20 更正：上一句的后半已失效——`DELETE /api/v1/sources/{id}` 本批已挂
  `require_roles("admin")`，宽面收口，普通用户不再可删源；详见 §6.2e。前半的「不新增
  `/admin/sources` 变体」裁定**在收口后依然成立**：写面已在 `/api/v1/sources` 上，
  再建 `/admin/sources` 只是同能力的第二条路径，与 §6.2b「读侧不在 admin 域重复」同纪律。
  v0.15 ⑬ 原文保留不回写，以便追溯当时「管理者明确接受该代价」的裁定依据。）**
- **`PATCH /admin/spaces/{id}` 同样不含 `name` 字段**：改名触及 `uq_space_user_name` 与
  既有空间链接语义，需单独裁决（与 §五 v0.3d 对既有端点的同一取舍，非遗漏）。

### 6.2b 引擎 Key 登记端点（`operator`+，批次 3 / T5.4，v0.16 新增）

> 目的：operator 自行登记/覆盖/撤销第三方引擎的 API Key，**替代「找管理员改 env 再重启」**。
> 登记值 **AES-256-GCM 加密落库**（12 字节 nonce，**AAD = 引擎名**——密文无法在引擎位间搬移），
> 落库形态 `b64(nonce).b64(ct+tag)`。`main` 的 `base` 是端点不是凭据，**永远只认 env**（登记表无 base 项），
> 故 `main` 仍要求 `MAIN_KB_API_BASE` **且** Key 二者齐备。
> 迁移 `ab1004m3b`：`engine VARCHAR(32)` PK / `secret_ref TEXT` / `key_id VARCHAR(32)` UQ /
> `registered_by VARCHAR(36)` FK→`users.id` ON DELETE CASCADE / `created_at`·`updated_at`。

| 端点 | 授权 | 语义 | 响应 data |
|---|---|---|---|
| `GET /api/v1/admin/engines/keys` | `operator` | 登记状态列表（**不含明文**） | `{masterKeyConfigured, items[]}` |
| `POST /api/v1/admin/engines/keys/{engine}` | `operator` | 登记/覆盖（upsert，一行一引擎位，`key_id` 换新） | `{ok, engine, keyId}` |
| `DELETE /api/v1/admin/engines/keys/{engine}` | `operator` | 撤销（回落 env；env 亦空则该位不再可用） | `{ok, engine, revoked}` |

**`GET` 的 `items[]` 字段**（每个可登记引擎位 `main`/`coze`/`dify`/`fastgpt` 各一项）：

| 字段 | 语义 |
|---|---|
| `registered` | 是否有登记行 |
| `activeSource` | 当前生效来源：`"registered"` / `"env"` / `null` |
| `configured` | 登记表 **合并 env 后**是否已配置 |
| `envConfigured` | **仅凭 env** 是否已配置——与 `configured` 可比，故登记覆盖 env 是**可见**的 |
| `decryptFailed` | 登记行密文不可解（损坏或主密钥已轮换）——**被标注而非静默当「未配置」** |
| `keyEnv` | 应配置的 env 变量名（`MAIN_KB_API_KEY` / `COZE_API_KEY` / `DIFY_API_KEY` / `FASTGPT_API_KEY`） |
| `keyId` / `registeredBy` / `updatedAt` | 登记元数据（`keyId` 是轮换句柄；`registeredBy` 为审计） |

`masterKeyConfigured=false` 表示 `ENGINE_KEY_MASTER_KEY` 未配置：此时列表**仍可用**（只反映 env 侧），
但 `POST` 会 **50002 拒绝**。**绝不回落明文**——UI 显示「已加密登记」而库里其实是明文，
比一开始就写明文更难被发现。

**请求与拒绝口径**：`POST` body `{"key": "..."}`，`min_length=1` / `max_length=1024`；
服务端另拒 strip 后为空与含控制字符（`ord < 0x20` 或 `0x7F`）→ 均 `10005`。
`builtin`（内置回退通道，无需 Key）与未知引擎位 → `10005`。
`DELETE` 无登记行 → `30004`（**不谎报已撤销**）。
`POST` 明文**不落库、不回显**——响应只给 `keyId`。

**读侧不在 admin 域重复**：引擎全景由既有 `GET /api/v1/engines`（登录即可见）承担，
本批不另建一个更窄的只读端点。

### 6.2c 推送通道端点（`operator`+，批次 5 / T6.2，v0.17 新增）

> **诚实占位（管理者裁定 2026-09-23）**：通道接口与注册表落地，两通道 `web` / `clawbot`
> **均不实接**。因此本端点**从不产生真实投递**——未投递即 `50002`/503，
> **绝不返回 200 假成功**（返回 200 会让调用方以为消息已送达，是「显示成功、实际没发生」的推送版）。
> 实现：`app/providers/push_port.py`（`PushProvider` 协议 + `channel → provider` 注册表）
> + `app/services/push.py`（校验 + 分发）。**零迁移、零依赖新增**。
>
> **为何不建通知表**：`web` 是「站内通知占位」，但项目内**无通知表、无站内消息读端点**；
> 为写侧新建一张表而无读侧，`web` 通道即成为第二个 `BotBinding` 死表
> （`BotBinding` 全仓仅 `app/models/__init__.py` 两处导出引用，无任何 service/route/test 使用）。

| 端点 | 授权 | 语义 | 响应 data |
|---|---|---|---|
| `GET /api/v1/admin/push/channels` | `operator` | 通道就绪度全景（**读侧**） | `{channels: [{channel, implemented, reason}]}` |
| `POST /api/v1/admin/push` | `operator` | 推送触发（按 space/doc 或自由正文） | 200 `{ok, channel, delivered}` **或** 503/50002 |

**`POST` 请求体**（snake_case，与 §6.2 同域口径一致）：

| 字段 | 必填 | 约束 |
|---|---|---|
| `channel` | 是 | `web` / `clawbot`（未知 → `10005`，**不臆造通道**） |
| `external_user_id` | 是 | 通道侧目标 id，≤128 字符 |
| `space_id` / `doc_id` / `message` | 三者至少一项 | `space_id` ≤36、`doc_id` ≤36、`message` ≤2000 字符 |

`GET` 的 `channels[]` 每个通道一项：`implemented=false` 即「接口在位、投递未实接」，
`reason` 是拒绝原因（**逐字锁定即契约**，改文案即改契约）：

- `web` → `web 通道无站内投递面（无通知表、无读端点），本批不构建`
- `clawbot` → `clawbot 出站契约项目内不存在（ADR-0002 附录 A 仅入站验签），且微信凭据未注入——活体半程未通`

加这个读侧的动机：通道就绪度**显式回报**，而非只能靠试推撞出 50002 才知道
（同 §6.2b 的 `activeSource` / `masterKeyConfigured` 显式回报纪律）。

**`POST` 的拒绝口径**：

- 校验顺序固定 **通道 → 内容 → 目标**，全部在分发前完成，**失败零副作用**（不落行、不触达 provider）
- 未知通道 / 空目标 / 空内容 / 超长 / 控制字符 → `10005`/422
- 空间不存在 / 文档不存在 / **文档不属于所给空间** → `30004`/404
- 通道未实接 → `50002`/503（message 带通道名与拒绝原因，`data` 为 `null`）

**不做归属校验**（A-2 跨用户口径，operator 以上可代用户操作）；但
**`doc.space_id` 归属是数据事实校验，不随之放宽**——否则跨空间误推不可被发现
（同 §6.4 对 admin 端点的同一判据）。

### 6.2d 批量文档端点（`admin`+，批次 4 / T5.7，v0.18 新增）

| 端点 | 授权 | 语义 | 响应 data |
|---|---|---|---|
| `POST /api/v1/admin/spaces/{space_id}/docs:delete` | `admin` | 跨用户批量删文档（单次上限 50） | `{ok, requested, docs, assets, failed[]}` **或** 502/30002 |
| `POST /api/v1/admin/spaces/{space_id}/docs:recategorize` | `admin` | 跨用户批量改分类（单次上限 50） | `{ok, requested, docs, category}` **或** 404/30004 |

**与既有批量端点的差异仅在授权**：既有 `POST /api/v1/spaces/{id}/docs:delete` 与
`docs:recategorize`（§五，R0.2.5）**强制本人空间**，本端点**绕过归属校验**；**既有端点零改动**
（A-2 承诺面）。请求体模型**直接复用** `app/api/v1/spaces.py` 的
`BatchDocIdsRequest` / `BatchDocCategoryRequest`（不复制模型：pydantic 体量硬闸与字段约束
必须单一来源）。实现：`app/services/spaces.py` 抽出 `_delete_docs` / `_recategorize_docs`
单一实现，以 `owner: str | None` 表达「无归属约束」（见 §6.5）。**零迁移、零错误码新增**。

**双层闸**：请求体 `ids: list[str] = Field(min_length=1, max_length=500)`（pydantic 体量硬闸）；
业务上限 50（`batch_docs_max_ids`）在 Service 内经错误信封报 `10005`。

**批量删除 = 篇级部分成功**（与单篇 DELETE 的 all-or-nothing **相反**）：
`failed: [{docId, code, error}]` 非空即部分成功——引擎侧失败篇的 **PG 行完整保留**，可原样重试。
引擎整体失败时**不上抛 200**：全批失败 → 错误信封（30002/502），避免「200 但一篇都没删」
被误读为成功。顺序与单篇一致：**引擎文件先删 → 成功才删 PG 行**（两阶段切分、逐篇提交）；
`langbot_file_id` 为空的副本行不触发引擎调用。

**批量改分类 = 整批原子**（纯 DB 写）：任一篇缺失 → `30004`，**全批回滚**，无「改了一半」
中间态。`category` 的生效范围是**资产级**——对本资产在**其他空间**的呈现一并生效。

**校验先于取行**：`ids` 与 `category` 的校验在读取任何行之前完成——
对**不存在的空间**提交非法取值也返回 `10005` 而非 `30004`（错误语义不降级）。

**不做归属校验**（A-2 跨用户口径）；但 **`doc.space_id` 归属是数据事实校验，不随之放宽**——
否则可凭任意 `doc_id` 越界批量删除。至此该判据在**三处同口径**：单篇 DELETE（§6.2）、
批量删除（本节）、推送目标校验（§6.2c）。

### 6.2e 作业与订阅跨用户读面 + 信息源写面收口（`admin`+，R4.8 / v0.20 新增）

| 端点 | 授权 | 语义 | 响应 data |
|---|---|---|---|
| `GET /api/v1/admin/jobs` | `admin` | **跨用户 Job 清单**，不按 `user_id` 过滤；`type`/`status` 取值过滤 + `limit`(1~100，默认 50)/`offset` | `{items, total, limit, offset}` |
| `GET /api/v1/admin/jobs/{job_id}` | `admin` | **跨用户 Job 详情**（含 JobItem counts 与 error 文本） | `{jobId, type, status, progress, error, counts{total,succeeded,failed,pending}, createdAt}` |
| `GET /api/v1/admin/subscriptions` | `admin` | **跨用户订阅清单**；`space_id` 省略 → 全系统跨空间视图 | `{items}` |
| `PATCH /api/v1/sources/{source_id}` | `admin` | 改**全局**源的展示名 / 上游地址（部分更新） | `{sourceId, biz, name, url}` |
| `DELETE /api/v1/sources/{source_id}` | **`admin`（v0.20 收口，原为「登录即可」）** | 与 PATCH 同口径——宽面收口，见 §6.2 更正注 | `{sourceId, deleted, references}` |

**缺口与 §6.2 同源**：jobs / subscriptions 的既有读端点**全部带本人归属谓词**（`GET /api/v1/jobs`
按 `user_id` 过滤，`GET /spaces/{id}/subscriptions` 先校验 `space.user_id == 本人`），admin 无法回答
「全系统哪条号卡住了 / 谁在跑同步 / 为什么这条号没人同步」——与批次 2 后端竣工时
「`/admin` 只有写端点、无读端点」是同一类缺陷（**端点存在被当成了能力可用**）。

**`..._any` 手法，抽单一实现不复制**（承 §6.2 / §6.2b / §6.2d，见 §6.5）：
- `JobService.list_job_views(None)` 即跨用户清单——`list_jobs` / `list_job_views` 的 `user_id`
  放开为可选，**查询、分页、排序、`total` 谓词、视图组装共用一份**，故 `total` 不会因
  跨用户口径而虚高。
- `SourceSubscriptionService._job_view(job_id, owner=None)` / `_list_subscriptions(space_id, owner=None)`
  同样以 `owner: str | None` 表达「无归属约束」，角色校验留在路由层。

**两条形状纪律（与 M3 批次 2 不同，须区别对待）**：
- 订阅：归属字段 `spaceId`/`spaceName`/`ownerId`/`ownerNickname` **只在 `owner=None` 时附加**
  （本人清单里这四个值恒等于调用方，纯噪声），故 **`GET /spaces/{id}/subscriptions` 形状零变化**，
  admin 走独立端点。归属名经**两次批量 `IN` 查询**取得，不逐条 get（否则 N+1）。
- Job：`_view` 是列表条目与取消回执共用的一份视图，本次为其追加 `ownerId`——
  **`GET /api/v1/jobs` 的 items 与 `POST /jobs/{id}/cancel` 的 data 因此各多一个键**
  （v0.13 契约的**加法式**变更，前端忽略未知键即零回归，但**不是**「一字未改」）。
  取舍：拆成两份视图会让「列表与详情字段集」漂移成两份拷贝，而 `ownerId` 对本人端点
  不泄露任何跨用户信息（值恒为调用方自己）。此处刻意偏离批次 2 的「独立端点承载增量」口径，
  由 `test_user_job_routes_no_regression` 只锁**跨用户行为**（只列本人、他人 30004）而不锁键集。

**`latestJobId` 的归属取订阅本人（`r.user_id`），不取调用方**：旧实现按调用方 `user_id` 过滤 Job，
admin 路径下调用方并非订阅者，他人订阅的 `latestJobId` 会被**静默过滤成空串**，前端据此误判
「从未同步」。已由 `test_admin_latest_job_id_uses_subscriber_not_caller` 锁（给 admin 自己造一个
不同幂等键的 Job，断言不会误配）。

**`PATCH /api/v1/sources/{id}` 不可写字段**：`type` / `external_id` 是
`uq_source_type_external` 的**全局去重锚**，且被三张子表 CASCADE 引用——改了等于删后重建，
故服务端**忽略**而非报错（部分更新语义：只认已知字段，与 §6.2 对 `PATCH /admin/spaces/{id}`
不含 `name` 的取舍同类：宁可少改，不可错位）。

**信息源清单刻意不在 admin 域重复**（`GET /api/v1/admin/sources` **不建**）：`sources` 表
**无 `user_id` 列**，既有 `GET /api/v1/sources` 本就是**全用户共享清单**（登录即可见），
再加一条 admin 路径只是同一份数据的第二条入口，不增加任何跨用户能力。
F-23 的修正同向：既有实现把 `user_id` 透传给 `list_sources` 却从不过滤——**死参数 + 契约误导**
（让人以为有「我的信息源」概念），参数已移除，登录闸门改挂 `get_current_sub`（纯身份，无需查库）。

**F-24（潜伏缺陷，本批才暴露，P0）**：`JobRepository.count_by_user` 原为
`select(Job).where(Job.user_id == user_id).with_only_columns(func.count())`。
`with_only_columns(func.count())` 把 SELECT 列换成标量函数后，SQLAlchemy 会**剪掉它不引用的
FROM**——零条件时语句退化成 `SELECT count(*)`（**无表**），恒返 `1`。历史实现靠
`Job.user_id == user_id` 这个**恒有**的谓词把 FROM 顶住，所以从未暴露；`user_id` 放开为可选后，
跨用户清单出现「列表 3 条、总数报 1」，分页控件按 1 页渲染，清单完全不可用。
**修**：显式 `.select_from(Job)`；测试同时锁**编译口径**（count 语句必须含 `FROM jobs`）与
**原始 SQL 对账**（`select count(*) from jobs` 与仓库返回值相等）。
**同类跨域陷阱**：任何「全可选谓词」的仓库若复用该惯用法而不补 `select_from`，都会退化成常量 1。
仓内两处该惯用法（`repositories/job.py`、`repositories/space.py`）已逐一核对。

**错误码**：**零新增码位**——复用 10001（未登录）、10004/403（非 admin）、10005/422（参数越界）、
30004/404（无效 id）。`type`/`status` 是**取值过滤而非域校验**：未知取值返回空列表（200），
读路径不设校验闸门（承 v0.13 ⑩ 同一口径）。

**门禁**：后端新增 `tests/test_r48_admin_jobs.py` 共 **16 测**（全走真实 PG），两侧锁——
admin 跨用户放行（清单带 `ownerId` / 过滤与 total 同谓词 / 详情带 counts / 订阅全系统视图 /
`latestJobId` 归属）+ 用户端点**零回归**（只列本人、他人 Job 仍 30004、他人空间订阅仍 30004）
+ 写面门禁（`PATCH`/`DELETE` 非 admin 10004、未登录 10001、**拒绝时零写入**）
+ F-24 回归锁 + F-23 契约锁（`list_sources` 签名无 `user_id`，由 `inspect.signature` 直接断言）。
后端全量 **545 passed / 2 skipped**（基线 514，净增 16~18，**零回归**）、`ruff` 绿、
`mypy` 69 files Success。**前端本批零改动**——三条 admin 读端点无前端调用方，
待 admin 控制台排「作业中心 / 订阅全景」面板（当前控制台范围严格 = 批次 2 浏览 + 批次 4 批量，
见 v0.19 ⑰ 的末段裁定；**新增面板前须先扩该范围裁定**）。



### 6.3 与既有同名语义端点的契约差异（**刻意不一致，勿「统一」**）

| 项 | `PATCH /api/v1/spaces/{id}`（既有） | `PATCH /api/v1/admin/spaces/{id}`（本节新增） |
|---|---|---|
| 归属校验 | `space.user_id == 本人`，否则 30004 | **无**（admin 跨用户） |
| `description` 缺失 | 合法：不写入，返回**详情视图**（PATCH 部分更新） | **10005/422**：本端点唯一可写字段，缺失即客户端 bug |
| 响应形状 | 详情视图 `{id,name,description,docCount,...}` | 写回执 `{ok,id,description}` |
| `description: ""` | 清空（合法） | 清空（同语义） |

理由：写回执端点没有「no-op 也有信息可返回」的语义（详情视图带**本人归属**语义，
跨用户取视图另议）。**测试已双向锁定两侧形状**（`test_user_patch_space_noop_semantics_unchanged`
/ `test_admin_patch_space_requires_description_and_rejects_invalid`），防日后被统一掉。

### 6.4 错误码

| 场景 | 码 | HTTP |
|---|---|---|
| 未登录（无会话 cookie） | `10001` | 401 |
| 角色不足（`user` 访问本节端点；`user`/非 `operator` 访问 §6.2b；`user`/**`operator`** 访问 §6.2d） | `10004` | 403 |
| `description` 缺失 / >512 / 含控制字符 | `10005` | 422 |
| 无效空间 id；doc 不存在；**doc 存在但不属该空间** | `30004` | 404 |
| §6.2b：`builtin` / 未知引擎位 / Key 为空或含控制字符 | `10005` | 422 |
| §6.2b：`DELETE` 无登记行（**不谎报已撤销**） | `30004` | 404 |
| §6.2b：`ENGINE_KEY_MASTER_KEY` 未配置或畸形（**绝不回落明文**） | `50002` | 503 |
| §6.2c：未知通道 / 空目标 / 空内容 / 超长 / 控制字符 | `10005` | 422 |
| §6.2c：空间/文档不存在、**文档不属于所给空间** | `30004` | 404 |
| §6.2c：通道未实接（**未投递即报，绝不 200 假成功**） | `50002` | 503 |
| §6.2d：空批 / 超业务上限 50 / 全空白 / 缺 `ids` | `10005` | 422 |
| §6.2d：`category` 不在规则版六类或空串（**先校验后取行**） | `10005` | 422 |
| §6.2d：无效空间 id / 任一篇 doc 缺失 / **doc 不属该空间**（零副作用） | `30004` | 404 |
| §6.2d：批量删除**全批失败**（上抛首个异常，不谎报 200） | `30002` | 502 |
| §6.2e：`type`/`status`/`limit`/`offset` 越界；`PATCH` 请求体不合法 | `10005` | 422 |
| §6.2e：无效 job / source / space id（**不校验调用方归属**） | `30004` | 404 |
| 引擎删文件失败（LangBot；§6.2d 篇级失败计入 `failed[]`，不上抛） | `30002` | 502 |

- **`50002` 而非 `10004`/`10005`**：10004「无权限」会误导 operator（他有角色），10005「请求无效」
  会误导一个没有问题的请求；50002「依赖不可用」准确——加密能力未就绪。
- **越权与不存在同码（10004）且发生在任何写入之前**；空间/doc 不存在一律 30004，不泄露存在性。
- `DELETE` 顺序与既有端点完全一致：**引擎文件先删 → 成功才删 PG 行 → 失败整体回滚**
  （PG 零残留，不会出现「PG 删了库没删」的孤儿文件）；`langbot_file_id` 为空的 doc
  （公共库 link 引入的副本）不触发引擎调用。
- **`doc.space_id` 归属判据不随空间归属一起放开**：admin 可跨租户操作空间，但
  「该 doc 属不属于这个空间」仍是硬校验——否则可凭任意 `doc_id` 越界删除。
  该判据在**三处同口径**：单篇 DELETE（§6.2）、批量删除（§6.2d）、推送目标校验（§6.2c）。
- **§6.2d 校验先于取行**：`ids` 与 `category` 的校验在读取任何行之前完成——对**不存在的空间**
  提交非法取值也返回 `10005` 而非 `30004`。若顺序反了，调用方会收到「空间不存在」而误判问题
  在 id 而非在请求体（错误语义降级即误导排查方向）。

### 6.5 实现纪律（防止两处漂移）

`SpaceService.update_space` 与 `delete_doc` 各抽出 `_update_space` / `_delete_doc` **单一实现**，
以 `owner: str | None` 参数表达「无归属约束」——两条入口的**全部差异只在这一处判据**。
若简介校验顺序、commit 纪律、引擎先行顺序在两份拷贝里各写一份，日后修一处忘另一处即漂移
（非法取值对不存在的空间会返回 30004 而非 10005）。服务方法命名为
`update_space_any` / `delete_doc_any`（「无归属约束」）而非 `admin_*`：方法内**不做**角色校验，
`admin_*` 会被误读为方法内做了授权。

**同类纪律适用于 §6.2d（v0.18）**：`delete_docs` / `recategorize_docs` 各抽出
`_delete_docs` / `_recategorize_docs` 单一实现，同样以 `owner: str | None` 表达「无归属约束」，
新增 `delete_docs_any` / `recategorize_docs_any` 走 `owner=None`；`_resolve_owned_docs` 的归属
判据收敛为 `owner is not None and space.user_id != owner`。若篇级部分成功、两阶段切分、
逐篇提交、整批原子这些契约在两份拷贝里各写一份，修一处忘另一处即漂移，且**没有任何调用方会报错**
——已由 `test_admin_batch_both_entries_validate_before_fetch` 直接锁「四条入口都在取行前校验」。

**同类纪律适用于 §6.2b（v0.16）**：「哪个引擎有凭据、凭据来自 env 还是登记表」的判定收敛为
**唯一谓词** `app/core/engine_keyring.resolve_engine_key()`，`GET /api/v1/engines` 的状态上报、
`PATCH /spaces/{id}/engine` 的切换闸、以及 `engine_port.py` 的路由判定与引擎构造**全部走它**。
此前 `engines.py` 对 `main` 只查 `main_kb_api_base`（忽略 Key）、`engine_port.py` 查 base **且** key——
**同一份数据两个结论**（base 已配 Key 空时 `GET /engines` 报「已配置」而入库路径说「未配置」），
既有 R0.3.2 全 5 位不变式测试**从未覆盖 base-only 分支**，故缺陷得以上线。现不变式由构造保证。

**同类纪律适用于 §6.2e（v0.20）**：`JobService.list_job_views` / `list_job_views_any`、
`SourceSubscriptionService._job_view` / `_list_subscriptions` 各以 `user_id=None` / `owner=None`
表达「无归属约束」，`JobRepository.list_by_user` 的三分支谓词（`user_id is not None` 才加列谓词——
传入 `None` 会让 SQLAlchemy 生成 `user_id IS NULL`，语义从「不过滤」静默变成「只取无主行」）。
若 `total` 与列表谓词、JobItem counts 聚合、`latestJobId` 的幂等键前缀匹配这些契约在两份拷贝里
各写一份，同样无任何调用方会报错——F-24 即此类缺陷的真实实例（见 §6.2e）：
**谓词可选化后，`total` 悄悄退化成常量 1**，两条 SQL 都成功，只是数字对不上。




### 6.6 OpenAPI 安全方案（R4.9.3 / v0.20 新增）

此前 `create_app().openapi()` 的 `components.securitySchemes` **恒为空**——Swagger UI 不显示锁形
标识、不出现 Authorize 按钮，「哪些端点要登录」只能靠读代码或撞 10001 才知道。本节由
`app/main.py` 的 `_annotate_session_security` 在 OpenAPI **生成之后**补齐，不改变任何
路由行为，只补文档标注。

**声明的方案**（`components.securitySchemes.AideanBotSessionCookie`）：

| 字段 | 值 |
|---|---|
| `type` | `apiKey` |
| `in` | `cookie` |
| `name` | `get_settings().session_cookie_name`（默认 `aideanbot_session`，**取自配置而非硬编码字面量**） |

**⚠ 本系统没有 Bearer Token，也没有 token 交换端点**：认证是**会话 cookie**——
`GET /api/v1/auth/login` 302 跳主平台、`GET /api/v1/auth/callback` 兑换 code 后由后端下发
cookie（`HttpOnly` + `SameSite=Lax`）。Swagger UI 的 **Authorize** 里填该 cookie 的值
即等价于浏览器自动携带；填 Authorization 头不会生效。方案 `description` 明写这一点，
并有测试断言 `"Bearer"` 出现在描述里（防止日后有人误改回 Bearer 方案让读者去填空头）。

**逐操作标注**：`security: [{AideanBotSessionCookie: []}]`。
**63 个操作中 57 个标注、6 个公开**（openapi() 实测，R9 后复核 2026-09-28）：

| 公开端点 | 无需会话的理由 |
|---|---|
| `GET /api/v1/auth/login` | 浏览器重定向到 IdP |
| `GET /api/v1/auth/callback` | IdP 回跳，尚未建会话 |
| `POST /api/v1/auth/logout` | 幂等：无会话也返回成功 |
| `POST /api/v1/auth/backchannel-logout` | **R9（2026-09-28）**：OIDC Back-Channel Logout 1.0 规定本端点**不携带任何客户端凭据**——JWT 签名本身就是全部鉴权。若挂会话依赖，主平台（无 AideanBot 的 session cookie）必然 10001，整个 back-channel 静默失效。安全性由验签 fail-closed 保证，非「无认证」（见下方 R9 补注） |
| `GET /api/v1/system/health` | 存活探针，容器/编排层轮询 |
| `GET /api/v1/onboarding/steps` | 静态默认值，不含任何用户数据（见 §38 缺陷 F-25） |

**标注取自声明的依赖树，不是路径白名单**：`_uses_session` 递归检查路由的 `Dependant` 树里是否
出现 `get_current_sub`。据此设计的原因——**新增端点自动纳入，无需回改清单**：
- `require_roles(...)` 每次调用都返回**新的函数对象**，按函数身份匹配不可靠；但它的依赖树含
  `get_current_user_id` → `get_current_sub`，故从 `get_current_sub` 这**一个锚点**递归即可同时
  覆盖用户域与全部 admin 域（含 §6.2b / §6.2c 的 `operator`+ 端点）。
- **`require_roles` 不在方案层表达**：OpenAPI 的 `security` 只能声明「需要哪把钥匙」，不能表达
  「这把钥匙属于哪个角色」，故角色门禁只能见各端点描述（§6.1 / §6.2~§6.2e）。

**唯一的例外清单 `MANUAL_SESSION_ROUTES`**：`GET /api/v1/auth/me` 在处理器内自查 cookie 并抛
10001，**不走 `get_current_sub` 依赖**，依赖树推导捕不到它。不登记就会被文档**误标为公开端点**。
新增此类路由必须在此登记，且已有测试逐条断言其确实被标注。

**漂移锁的方向是刻意的**：`tests/test_r493_openapi_security.py::test_public_operations_exact_set`
断言「未标注集合 **精确等于** 6 条清单」。取精确匹配而非子集匹配，因为
**少标比多标危险**——多标只是文档冗字，少标会让读者以为某端点无需登录即可调用。
故新端点若漏挂登录依赖，本测立刻失败；新增真正公开端点时须同时在此清单登记并说明理由。

**R9 补注（2026-09-28）：`POST /api/v1/auth/backchannel-logout` 契约**

```
POST /api/v1/auth/backchannel-logout
Content-Type: application/x-www-form-urlencoded

logout_token=<RS256 JWT>
```

- **调用方**：仅主平台（服务器间 POST，不经浏览器，不读/写本方 cookie）。主平台在用户登出后
  按「该用户全部活跃产品链」广播。
- **鉴权**：无 client 凭证。安全性完全由 JWT 签名保证——从 `/.well-known/jwks.json` 拉
  JWK（TTL 300s 缓存，与主平台 `cache-control: max-age=300` 对齐），按 `kid` 选钥，
  `RSAPublicNumbers(e,n).public_key()` + `verify(sig, signing_input, PKCS1v15(), SHA256())`。
  实现见 `app/services/auth/logout_token.py`；**零新增依赖**（`cryptography>=43.0.0` 已在依赖树）。
- **fail-closed 九步校验**（任一失败即拒绝）：`alg=="RS256"`（拒绝 none/其他 alg）→
  `kid` 存在 → 签名 → `iss == OIDC_ISSUER_EXPECTED` → `aud == OIDC_AUDIENCE_EXPECTED`
  （`aud` 可为 string 或 array）→ `events` 含 backchannel-logout 事件 →
  **`nonce` 声明存在则拒绝**（OIDC Back-Channel Logout 1.0 §2.1 强制）→ `sub` 非空 →
  `|now - iat| ≤ OIDC_LOGOUT_TOKEN_MAX_AGE_SECONDS`。
- **`iss`/`aud` 强制配置，不得 fail-open**：与 userinfo 路径「未配置则跳过」不同。
  本端点无 client 凭证可校验，issuer/audience 是**唯一**的接收方证明；未配置 →
  `misconfigured_expected_claims` 拒绝，绝不降级为「不校验」。
- **时间窗是强制的**：主平台签发的 logout_token **不含 exp/nbf**，RP 必须自建有界窗，
  否则该 token 可无限重放（只能删会话，但足以反复摧毁受害者会话，构成可用 DoS 向量）。
- **响应恒 200 同形**：`{"code":0,"message":"ok","data":{"received":true}}`，无论 token
  缺失、签名无效还是声明不符一律相同——不向主平台泄露校验结果差异（对齐主平台
  `/oauth/revoke` 恒 200 口径）。仅服务端自身故障（如会话存储不可达）返回 5xx。
- **效果**：删除该 `sub` 的**全部**本地服务端会话（`delete_by_sub`），幂等；
  不调用主平台（不 revoke、不 introspect）；不清理本地 users 表（身份锚点保留）。
- **不持久化、不落日志**：不写入任何 token 值；日志只记 `sub` 前缀（8 字符）与原因码。
- **启用条件**：须由主平台管理员在 `oidc_clients` 写入 `logoutUri` 才会投递。
  未登记时本端点静默闲置，会话随 refresh 轮换失败自然失效（降级路径安全，
  指南 v1.3 §4 末句）。故本端点属 **P2 契约闭环，非 P0 安全漏洞**。

**实现约束（三个踩过的坑，勿回退）**：
1. **不遍历 `app.routes` 取路由**：FastAPI 0.141 把 `include_router` 的产物懒收敛成私有
   `_IncludedRouter` 节点，`app.routes` 上取不到 `APIRoute`（实测 `isinstance(APIRoute)` 全 False，
   标注器静默标 0 条），且 `fastapi.routing.get_api_routes` 在本版本不存在。
   故 `APP_ROUTERS` 是一份**模块级路由表**，`create_app` 与标注器共用同一份——
   由 `test_every_included_route_reaches_schema` 双向锁（schema 里的每个操作都能追溯到
   `APP_ROUTERS`，反之亦然），防止「include 进 app 却漏登记」的静默缺席。
2. **`Dependant.dependencies` 的元素是 `Dependant` 本身，不是 `Depends` 包装**（0.141.1），
   递归须直接对子 `Dependant` 调用；`route.methods` 类型为 `set[str] | None`，需先判空。
3. **过滤 `HEAD` / `OPTIONS`**：FastAPI 自动补的这两个动词不进 OpenAPI，不过滤会写出悬空标注。
   另需跳过 `include_in_schema=False` 的路由（框架自带的 `/docs`、`/redoc` 等），
   否则向 `schema["paths"]` 写键会 KeyError。

**实现纪律**：`_openapi_with_security` 调**类方法** `FastAPI.openapi(app)` 而非 `app.openapi()`——
实例属性被 `partial` 遮蔽后调实例方法会自引用递归；原实现的 `openapi_schema` 缓存仍生效，
本包装只在其结果上补标注。`app.openapi = partial(...)` 处需 `# type: ignore[method-assign]`
（与仓内既有 4 处 `type: ignore` 同类）。




## 七、外部依赖 API（AideanBot 消费方）

- LangBot：建库/上传/ingest/retrieve（M0 报告 §四全链已实证）
- 主平台：SSO 七端点 + wallet 查询（M0 报告 §五已实证）
- Redfox：广域库清单（M0 报告 §二契约已实证）

- **v0.5b P2 整号订阅端点（AB-P004 阶段3，2026-09-14 登记）**：
  ① `POST /api/v1/sources {biz|profile_url, name}` → 201 `{sourceId, biz, name, url}`（uq_source_type_external 幂等，已存在 200）；
  ② `GET /api/v1/sources?type=wechat_oa` → `data.items=[{sourceId,biz,name,url,status}]`；
  ③ `POST /api/v1/spaces/{id}/subscriptions {source_id, sync_policy}` → 201 `{subscriptionId, jobIds, created:true}` / 200 已订阅 `{created:false}`；
     越权/无效空间 → 30004；无效 source → 30004。
  ④ `GET /api/v1/spaces/{id}/subscriptions` → `data.items=[{subscriptionId,sourceId,biz,sourceName,syncPolicy,nextRunAt,status,latestJobId}]`；
  ⑤ `GET /api/v1/jobs/{id}` → `{jobId,type,status,progress,error,counts{total,succeeded,failed,pending},createdAt}`（轮询 5s）；
  ⑥ `POST /api/v1/jobs/{id}/retry` → `{jobId,retried,status}`（FAILED JobItem 单篇重试，幂等：全 SUCCEEDED retried=0）。
  整号级错误码 30005 PARTIAL_SUCCESS（Job 终态字符串，非 AppError 码位；Job 状态机已有）。

- **v0.5c P4 引擎可插拔端点（AB-P004 阶段4，2026-09-14 登记，ADR-0004 实现标准）**：
  ① `GET /api/v1/engines`（登录保护 10001）→ `data={items:[{engine,configured,available,allowlisted,keyEnv,description}], defaultEngine}`；
     5 引擎位顺序 builtin→main→coze→dify→fastgpt；builtin 恒 available；SaaS 按 env Key 是否配置返回 configured。
  ② `PATCH /api/v1/spaces/{id}/engine {engine}` → 200 `{engine, engineKbId, spaceId}`（双写）；
     未开放/Key 未配 → 10004/403（提示找管理员）；越权空间 → 30004。
  ③ 空间视图追加：`GET /spaces` items 与 `GET /spaces/{id}` 详情追加 `engine`（默认 builtin）/`engineKbId`/`isPublic`；
  ④ SSE citations 追加 `engine`（三元 {title, spaceName, engine}，跨引擎融合列 M4）。

- **v0.5d BE-02 引擎路由与资产硬化（2026-09-14 登记，同角色内聚交付）**：
  ① 引擎路由全链：`kb.ensure_kb/upload/status`、`chat.ask retrieve`、`spaces/{id} DELETE` 删库
     全走 `KnowledgeEnginePort` 工厂（按 `space.engine` 分发，`EngineRouter` 装配）：
     - builtin 保持 LangBot 原路径零回归（KB 标识取 `langbot_kb_uuid`）；
     - 非 builtin（main/coze/dify/fastgpt）Key 未配/未开放 → ingest/ask/delete 前置拦截 10004/403，
       **不浪费抓取**（ingest 在 resolve 前拦截）；KB 标识取 `engine_kb_id`（实接后回填）。
  ② 缓存兼容存量（D-2/D-3 修复）：无 biz 参数短链二次 ingest 命中缓存——
     `_find_source_by_anchor` 增加「源 URL 含 article_key」兜底；资产查询增加
     `get_by_url_fragment`（biz 锚源 + article_key 资产失配场景），hitCache/hitCount 如实返回。
  ③ raw_uri 存储抽象：`config.raw_store_backend`（url 透传默认 / local 本地卷），
     `POST /docs` 落库资产 `raw_uri` 走存储后端，接口稳定不强上 S3（S3/OSS 留扩展槽位）。
  ④ `GET /engines` 三态语义明确：`configured`（env Key 就绪）/ `allowlisted`（开放名单）/
     `available`（两者交集）；非 builtin 未开放时前端置灰提示找管理员。
  ⑤ **v0.16 增补（SPEC-M3 批次 3 / T5.4）**：`GET /api/v1/engines` 的 item **追加两字段**（字段追加，
     既有字段不变）：`activeSource`（`"registered"` / `"env"` / `null`——当前生效的 Key 来源，
     登录即可见，故登记不只影响 admin 视图，也影响前端引擎切换器的「未配置 Key」判定）与
     `decryptFailed`（登记行密文不可解，被标注而非静默当「未配置」）。
     **`keyEnv` 取值口径变更**：由 settings 字段名（如 `coze_api_key`）改为**真实 env 变量名**
     （`COZE_API_KEY`，大写）——**对齐**前端既有 fixture 的预期，属兼容方向变更；
     前端类型补 `activeSource` / `decryptFailed` 属 C 域分域另提（运行时多余字段无害）
     ——**已兑现**：提交 `a6094ff` 为 `EngineItem` 补两个可选字段并加 1 测锁定「登记但未实接」的
     合法组合（`configured=true` / `available=false` / `activeSource="registered"`），
     纯 C 域契约零改动故**版本不递增**（同 v0.13 ⑪ 口径）。

- **v0.5e 阶段 3.1.1 元数据过滤（2026-09-17 登记，检索质量首个原子任务）**：
  `POST /api/v1/chat/ask` body 追加**可选**字段 `filters`（缺省 / 空对象 = 既有行为零回归）：
  ① `filters.sourceIds: string[]`（最多 20 条）→ 限定信息源（`sources.id`）；
  ② `filters.days: int`（1~365）→ 限定文章时间窗，口径
     `COALESCE(published_at, created_at) >= now - days`（缺发布时间用入库时间兜底）；
  ③ 生效条件：`sourceIds` 非空 或 `days` 非空；二者皆空视为未开启（不查候选集、retrieve 宽度维持 5）；
  ④ 候选集 = 空间内 `status=READY` 且 `langbot_file_id` 非空、且满足 ①② 的 doc；过滤开启时
     retrieve 宽取 `top_k=20` → 按候选集收窄 → 截断 5（`FILTER_CANDIDATE_TOP_K/RESULT_TOP_K`），
     保证 `meta.citations` 与生成上下文全部落在过滤范围内；
  ⑤ 空候选为**合法结果**：`meta.citations=[]` + `error 30002`（知识库无可回答内容），**不做无过滤回退**；
  ⑥ 参数越界（`days` 不在 [1,365] / `sourceIds` 超 20）→ **10005/422** 流前信封。

- **v0.5f 阶段 3.2.1 检索重排（2026-09-19 登记，检索质量第二件，接 v0.5e）**：
  `POST /api/v1/chat/ask` 行为追加**可选**重排增强——无新参数、无新端点，纯配置驱动：
  ① 配置（`backend/app/core/config.py` + compose 透传）：`RERANK_ENABLED`（默认 true）/
     `RERANK_API_BASE` / `RERANK_API_KEY` / `RERANK_MODEL`（默认 `BAAI/bge-reranker-v2-m3`）；
     base/key 留空回落 `EMBEDDING_*`（同供应商硅基流动），二者皆空 → 停用（Noop，显式不可用）；
  ② 生效语义：重排可用时 retrieve 宽取 `top_k=20`（同 3.1.1 候选宽度）→ 相关性分数降序
     （同分保上游原序的稳定 tie-break）取前 5，citations 与生成上下文按重排序输出；
  ③ 失败不致命：上游 4xx/5xx/网络异常/响应缺分 → **保序截断前 5**（不新增错误码、
     不伪造成败——重排属可选增强，绝不变成问答硬依赖）；
  ④ 与 3.1.1 可组合：候选收窄在先，重排只作用于过滤后候选集；
  ⑤ 活体证据（12 题 gold 对比，2026-09-17，`.workbuddy/evidence/rerank_gold_eval_20260917.txt`）：
     top-5 命中率 baseline 100% = +rerank 100%（不劣化）；top-1 100%→91.7%、平均最优排名
     1.00→1.25（小样本，1 题最优位次后移）；结论：top-5 口径零回归，默认开启，
     `RERANK_ENABLED=false` 一键关闭。端口契约单测 `tests/test_reranker.py`（含 PG 用例连栈复跑）。

- **v0.6 第一波执行批（2026-09-22 登记；T1.4.1/T1.4.3/T1.4.4/T1.5.2/T1.5.7/T3.1/T3.2 七项契约增量）**：
  ① **新端点 `PATCH /api/v1/spaces/{space_id}/public`**（T1.4.1，公共库发布/回收写端点，双闸）：
     body `{"isPublic": bool}`（snake 兼容）→ 200 `{spaceId,name,isPublic}`；
     双闸：操作者须在 env `PUBLIC_ADMIN_ALLOWLIST`（逗号分隔 user_id）**且** 目标空间
     `owner_type=system`；任一不过 → **10004/403**；空间不存在 → 30004/404；
     D9=a（M3 role 列）落地后 allowlist 退役为紧急通道；
  ② **`GET /api/v1/spaces/{id}/docs` 分页**（T1.5.7，offset 简版）：query `limit`（1~200，默认 100）/
     `offset`（≥0，默认 0）；data 增量 `total/limit/offset`，`items` 键形状不变（旧调用方零回归）；
  ③ **docs items 增量 `category`**（T3.2）：采集时规则版六类赋值（AI·技术/产品·商业/行业·动态/
     观点·评论/教程·实践/其他），空串=未分类；空间详情页筛选下拉由列表数据派生；
  ④ **`GET /spaces/{id}/subscriptions` 增量三字段**（T1.4.3/T1.4.4，N11 呈现接线）：
     `discoveredCount`（该源 DISCOVERED 清单计数 = U6「预计篇数」权威口径）/
     `lastSuccessAt`（worker 未建成前为空串——诚实缺口呈现）/ `consecutiveEmptySyncs`；
  ⑤ **SSE `meta` 帧增量 `intent`**（T3.1，阶段 3.3.1 意图五分类）：chat/fact/precise/list/summary，
     前端解析器忽略未知键零回归；意图路由检索宽度单调放宽（list/summary → 20，其余 5），
     `max(基线宽度, 意图宽度)` 绝不收窄既有行为；
  ⑥ **405/404 信封收口**（T1.5.2）：未注册路径/未注册动词此前泄漏 FastAPI 默认
     `{"detail": ...}` 裸体（starlette.HTTPException 之父类无处理器），现统一收敛为
     `{code:10005,message,data,requestId}` 信封，HTTP 状态码透传 404/405（回归测试
     `test_envelope.py::test_unmatched_route_returns_404_envelope / test_wrong_method_returns_405_envelope`）。

- **v0.7 第九批第二波（2026-09-22 登记；T2.6.1 批量入库 Job 化契约增量）**：
  **新端点 `POST /api/v1/spaces/{space_id}/docs:batch`**（**202 Accepted 提交即返**）：
  body `{"urls": string[]}`（pydantic 只做**体量硬闸** 1~500；业务上限 `batch_ingest_max_urls` 默认 50）→
  data `{jobId, status:"QUEUED", counts:{total,succeeded,failed,pending}, reused:bool, urlCount}`；
  **同步段零网络抓取**（仅校验 + 建 `Job(type="batch_ingest")` + 逐篇 `JobItem(PENDING)` 落库即返），
  逐篇抓取交 JobWorker 异步消费，**完整复用五层幂等链**（重复 URL 不重复入库）；
  幂等提交键 `batch_ingest:{space_id}:{sha1(排序后 URL 集)[:40]}`（**与提交顺序无关**）——
  同批在途（QUEUED/RUNNING）重复提交 → **复用同一 Job**（`reused:true`，防双击双份排队）；
  已终态（SUCCEEDED/PARTIAL_SUCCESS/FAILED）重复提交 → 换 `:r{n}` 键重建（允许重复采集，
  重复入库由 ingest 幂等链拦截）；
  归一化：strip 空白 + 跳过空行/纯空白 + 保序去重；
  校验：越权/无效空间 → **30004/404**（不泄露存在性，且**不落任何 Job**）；
  空批/全空白/超业务上限 → **10005/422**；非 http(s)/超 512 字符 → **10006/400**；
  收敛：全成 → `SUCCEEDED`；有成有败 → `PARTIAL_SUCCESS`（失败篇 `JobItem.error` 落库）；
  崩溃自愈：Job `RUNNING` 心跳超时 → 回退 QUEUED + item 回退 PENDING（批量进度不因宕机丢失）；
  **进度不丢**：刷新后凭 `jobId` 走既有 `GET /jobs/{id}` 恢复（T5.1 任务中心零额外路由）；
  **PARTIAL 重试**走既有 `POST /jobs/{id}/retry` 单篇重试（T2.3.3）；
  边界注记：**提交阶段只校验 URL 形态（http(s) + ≤512 字符 + 非空），不校验域名白名单**——
  域名合法性由逐篇链路的 resolver 判定，非法篇目落 FAILED 并计入 PARTIAL_SUCCESS；
  此处若再加域名过滤，会与 `providers/source_resolver.py:ALLOWED_HOSTS` 形成**并行的第二套规则**（漂移风险）。

- **v0.8 文档生命周期写端点（2026-09-22 登记；R0.2.1/R0.2.2，销账 F-2）**：
  此前全仓写路径仅 3 条（`PATCH /public`、`DELETE space`、`PATCH engine`），文档**零删除/编辑入口**，
  与 F-1（单页 100 条上限）组合成「删不掉 + 看不全」死锁。本批补两条单篇端点，**批量端点未含**
  （批量删除/改分类另立 R0.2.5，勿在本批私自加）。

  ① **`DELETE /api/v1/spaces/{space_id}/docs/{doc_id}`**（R0.2.1，登录保护 10001）：
     200 → data `{"ok":true, "docId", "docs":1, "assets":0|1}`（`assets`=被连带清理的**孤儿资产数**）；
     - **顺序**：引擎文件先删 → 成功才删 PG 行 → commit（与 AB-T11 删空间同序，防「PG 删了库没删」孤儿文件）；
     - **失败整体回滚**：引擎抛任意异常 → `session.rollback()` 原样上抛，**PG 零残留**
       （LangBot 侧 30002/502、不可达 50002/503）；
     - **引擎分发**：builtin 走 `LangBotClient.delete_kb_file(langbot_kb_uuid, langbot_file_id)`
       **直调不经 EngineRouter**（防 allowlist 误配把 builtin 判为不可用而拦住删除——与删空间的 builtin 分支同口径）；
       非 builtin 走 `EngineRouter.adapter_for(space).delete_file(engine_kb_id, langbot_file_id)`；
     - **跳过副本判定**：`langbot_file_id` 为空的 doc 不触引擎、直接删 PG——
       这是「公共库 link 引入副本」的判定依据（`link_public_space` 只建 PG 行、未上传引擎）；
       **不是 `doc.source`**：所有 doc 的 `source` 默认值都是 `"copy"`，无法区分来源；
     - **资产收敛**：按 `NOT EXISTS` 孤儿判定（与 `delete_space_cascade` 同款惯用法，兼容 PG/SQLite）——
       资产仍被其他空间 doc 引用则不删（`content_assets` 是跨空间共享的唯一真源）；
     - **计数回写**：`space.doc_count` 递减（与 `link_public_space` 递增对称，`max(0, …)` 钳位）；
     - 越权/无效空间 → **30004/404**（不泄露存在性）；doc 不存在或**不属该空间** → **30004**；
       越权路径不触碰引擎。

  ② **`PATCH /api/v1/spaces/{space_id}/docs/{doc_id}`**（R0.2.2，登录保护 10001）：
     body `{"category": string}`（≤32；**只接受 category**，正文字段不在本端点范围——正文属采集事实，
     改写须走新采集；pydantic 忽略未知键）→ 200 data `{"docId", "category"}`；
     - **取值白名单**：规则版六类（`AI·技术`/`产品·商业`/`行业·动态`/`观点·评论`/`教程·实践`/`其他`）
       或**空串**（= 清空人工标签，响应回默认口径 `其他`）；不做大小写/空格归一化掩盖 → 违规 **10005/422**；
     - **语义边界（两处已知，调用方须知）**：
       (a) `category` 是 **ContentAsset 级**属性（跨空间共享），本端点改写对本资产在**其他空间**的呈现
           一并生效——站内分类本就是资产级筛选维度；若需空间级覆盖须加
           `KnowledgeDocument.category_override` 列（迁移，**未立项**，登记为 R0.5 候选）；
       (b) 号主改文使 `content_hash` 变化时 `upsert_content` 会按新内容**重算覆盖** category——
           人工值非永久标签，端点不伪装成永久。
     - 只改 `category`，不动 `hash`/`version`/`status`；越权/无效空间或 doc → 30004/404。

  ③ **邻接缺陷修正（`SpaceValidationError` 映射）**：该异常此前继承裸 `ValueError`（未映射 → 冒泡 500），
     现改继承 `RequestInvalidError`（10005/422）；`create_space` 的三条既有分支同样受益。
     错误码→HTTP 映射表未变（复用既有 10005 码位，未新增码）。


- **v0.9 订阅生命周期端点（2026-09-22 登记；R0.2.3，F-2 续）**：
  此前订阅只有建/列、信息源只有建/列——整号采集管道建成后「订了就订着」：改不了频率、退不掉、删不掉源。
  本批补三条端点。

  ① **`PATCH /api/v1/spaces/{space_id}/subscriptions/{subscription_id}`**（R0.2.3，登录保护 10001）：
     body `{"sync_policy": string?, "sync_interval_minutes": int?}`（**部分更新，省略 = 不改**；
     空 body `{}` → 200 无副作用）→ 200 data `{subscriptionId, syncPolicy, syncIntervalMinutes, nextRunAt, status}`；
     - **取值闸门（建/改共用同一谓词）**：`sync_policy ∈ {"auto"}`（当前唯一有定义语义的值——
       调度器只有 `next_run_at` 驱动一条路径）；`sync_interval_minutes ∈ [5, 4320]` 分钟
       （下限防打爆上游清单接口；上限防退化为「永不同步」，退避最高 8× 生效在间隔之上）；
       越界/非法 → **10005/422**，且**不改库**；
     - **重排语义（两处已知，调用方须守）**：
       `sync_interval_minutes` 只可能把 `next_run_at` **往前**拉（更频繁），
       **绝不**把已逾期的一次同步往后推——否则「想同步得更勤」反而跳过了本该发生的到期同步；
       `status="CANCELLED"` 的订阅允许改值但**不再重排** `nextRunAt`（响应回空串）；
     - 越权/无效空间或订阅（含订阅不属该空间）→ **30004/404**（不泄露存在性）；
     - 校验在**服务层**而非 Pydantic 层，使 create 与 patch 走同一谓词、不可能分叉。

  ② **`DELETE /api/v1/spaces/{space_id}/subscriptions/{subscription_id}`**（R0.2.3 退订，登录保护 10001）：
     200 data `{subscriptionId, syncPolicy, syncIntervalMinutes, nextRunAt, status, cancelled}`；
     - **软取消，只做两件事**：`status=CANCELLED` + `next_run_at=None`；
       `claim_due` 要求 `status=ACTIVE AND next_run_at IS NOT NULL`，双保险后调度器永不再认领；
     - **不删除任何文档/资产/清单**——退订是「停止未来同步」，不是「清空已入库内容」
       （已入库内容的删除走 v0.8 单篇 / R0.2.5 批量，语义不同）；
     - **幂等**：已退订 → 200 且 `cancelled=False`（不报错）；越权/无效 → 30004/404。

  ③ **`DELETE /api/v1/sources/{source_id}`**（R0.2.3，登录保护 10001）：
     200 data `{"sourceId", "deleted":true, "references":{subscriptions, assets, manifests}}`；
     - **闸门 = 三者皆空**（订阅 + 资产 + 清单），**不是**仅「无订阅引用」：
       三张子表（`source_subscriptions` / `article_manifests` / `content_assets`）**全 `ondelete=CASCADE`**，
       而 `content_assets.id` 又被 `knowledge_documents.asset_id` CASCADE 引用——
       只挡订阅会级联删掉资产、进而**级联删掉知识空间的文档行**，
       且 `list_docs` 对 `Source` 是 **inner join**，文档会从清单里**静默消失**；
     - 仍有任一引用 → **10005/422**，message 附三项引用计数与前置动作；无效 id → 30004/404；
     - **无归属校验**（登录即可操作）：`sources` 表**无 user_id 列**——信息源是全用户共享的全局资源
       （`uq_source_type_external` 全局唯一）；零引用闸门保证不伤他人数据，
       但**前端提示文案不应暗示「我的」**。

  ④ **契约补全**：`GET /spaces/{id}/subscriptions` 的 items 补 `syncIntervalMinutes`
     （列此前在库但从不透出；与 PATCH 视图同口径）。

  ⑤ **邻接缺陷修正（`sync_policy` 由写进去没人读的字段变成真契约）**：
     此前建订阅时 `sync_policy` 只受 `max_length=32` 限制（无校验自由文本），
     而 `scheduler.py` **零处读取**该字段——属契约失实（与 F-3「一份数据两个谓词」同类）。
     现建订阅亦校验同一白名单（非法 → 10005/422）。
     **范围克制**：未把 `sync_interval_minutes` 加进 create 请求体（超出 R0.2.3 范围），
     但同一字段的谓词必须两处一致生效。

  ⑥ **错误码语义取舍（上报 A 待裁）**：「信息源仍被引用」语义上是冲突（409），
     但 `errors.py` **无通用 409**（30005/30006 均为域内命名），且明令
     「只使用上表已登记的 code；新增码位属契约变更，须先报 A 登记」。
     故本批**未新增码位**，复用 10005/422（依据 v0.8 确立的
     `SpaceValidationError(RequestInvalidError)` 业务校验先例），message 承载引用计数与前置动作。
     **待 A 裁决**：是否登记 `30007 SOURCE_REFERENCED`（409）以精确化本语义。

- **v0.10 批量文档端点（2026-09-22 登记；R0.2.5，F-2 销账）**：
  单篇端点（v0.8）已具备删除/改分类入口，但数百篇空间要逐篇点删——与 F-1（单页 100 条上限）
  及当时的客户端分类过滤组合仍是「删不掉 + 看不全」死锁。本批补两条批量端点。

  ① **`POST /api/v1/spaces/{space_id}/docs:delete`**（R0.2.5，登录保护 10001）：
     body `{"ids": string[]}` → 200 data `{"ok":true, "requested":n, "docs":n, "assets":n, "failed":[{docId, code, error}]}`；
     - **双层闸（沿用 `docs:batch` 同款）**：pydantic 层只做**体量硬闸** `ids: 1..500`
       （挡掉异常大的请求体，越界由 FastAPI 校验回 422）；业务上限**默认 50**（配置项
       `batch_docs_max_ids`）在 Service 内统一走错误信封 → **10005/422**——避免同一份校验
       规则在路由与服务两层漂移；
     - **ids 归一化**：逐条 `strip` → 丢弃空值 → **保序去重**（去重后条数可能小于请求条数，
       响应 `requested` 是归一化后的数）；归一化后为空批 → 10005（不落到「删了 0 篇却报成功」）；
     - **失败语义 = 篇级部分成功**（与单篇 DELETE 的 all-or-nothing **相反**，调用方须知）：
       引擎文件删除是**外部副作用**，整体回滚会抹掉已成功的 PG 删除、同时留下引擎文件已删的孤儿——
       即「PG 有行但文件没了」，该 doc 此后每次重试都因文件不存在而失败，成为**永久死档**且用户
       无从察觉；逐篇提交保证失败篇的 PG 行**完整保留**（含 `langbot_file_id`），可原样重试；
     - `failed` 非空即部分成功（**200**）；**全批失败 → 上抛首个异常走错误信封**（保持原码位，
       如 30002/502）——避免「200 但一篇都没删」被前端误读为成功；
     - `failed` 明细带 `code`（已登记错误码位）**而非** `str(exception)`：`AppError` 自带
       `[30002]` 前缀，纯字符串形态前端无法可靠解析；前端按 `code` 映射友好文案；
     - 引擎删除失败的篇**不递减** `doc_count`（只按成功篇递减）；跨空间共享资产同样不连带删
       （同 v0.8 ①的 `NOT EXISTS` 孤儿判定）；
     - 请求形态错误仍**整体拒绝且零副作用**（发生在任何引擎调用之前）：空批/超上限 → 10005；
       越权/无效空间 → **30004/404**；任一篇 doc 缺失或**不属该空间** → 30004
       （不回显缺失明细，不泄露存在性，且**合法篇也不删**）；越权路径不触碰引擎；
     - 批量与单篇对同一篇 doc 的删除语义**逐字节一致**（复用同一 `_delete_doc_core`，
       不给批量引入第二套删除语义）：builtin 直调 `LangBotClient.delete_kb_file`
       （不经 EngineRouter）、非 builtin 走 `EngineRouter.adapter_for`、
       `langbot_file_id` 为空跳过引擎（公共库 link 引入的副本）。

  ② **`POST /api/v1/spaces/{space_id}/docs:recategorize`**（R0.2.5，登录保护 10001）：
     body `{"ids": string[], "category": string}`（`category` 省略视为空串；≤32）
     → 200 data `{"ok":true, "requested":n, "docs":n, "category":"…"}`；
     - **双层闸与 ids 归一化同 ①**（同一 `_normalize_doc_ids`）；`category` 取值白名单同 v0.8 ②
       （规则版六类或**空串**；空串 = 清空人工标签，响应回默认口径 `其他`；
       不做大小写/空格归一化掩盖 → 违规 **10005/422**，且**先校验后取行**，零副作用）；
     - **失败语义 = 整批原子**（与 ①的篇级部分成功**相反**）：本路径是纯 DB 写、无外部副作用，
       单事务即可；任一篇缺失或越权 → **30004/404 且全批不生效**，不产生「改了一半」的中间态；
     - **语义边界承袭 v0.8 ②**：`category` 是 **ContentAsset 级**属性（跨空间共享），
       本批改写对本资产在**其他空间**的呈现一并生效；号主改文使 `content_hash` 变化时
       `upsert_content` 会按新内容**重算覆盖**——人工值非永久标签；
     - 只改 `category`，不动 `hash`/`version`/`status`；实现走单条 `IN` 更新（非逐篇 flush），
       避免 50 条的 N+1。

  ③ **失败语义分化的依据**：两条端点走相反语义不是遗漏，是按**副作用性质**裁定——
     有外部副作用（引擎删除）⇒ 篇级部分成功（逐篇提交，失败篇可重试）；
     纯 DB 写（改分类）⇒ 整批原子（单事务，无中间态）。
     **口径来源注记**：v0.8 只写了「沿用双层闸」，**未规定批量失败语义**；
     `batch_ingest` 的先例是 per-item 结果（JobItem 各自状态），故按该先例裁为篇级，
     但改分类路径不适用该先例。详见《剩余任务原子化执行大纲》§19.3。

  ④ **实现约束（非契约）**：批量删除必须拆成「先引擎、后 DB」两阶段——引擎失败时会话
     无 pending DB 写、无需回滚；若连续两篇失败各回滚一次，savepoint 会话
     （`join_transaction_mode="create_savepoint"`）报 **`MissingGreenlet`**，异常信封会退化成
     50001/500（调用方看到「服务内部错误」而非真实的 30002/502，错误诊断完全失真）。
     本批实测踩到并已修；`test_delete_docs_batch_all_failed_raises_envelope` 是回归桩。

  ⑤ **错误码**：**未新增码位**——复用 10005/422（形态校验）、30004/404（缺失/越权）、
     30002/502（LangBot 侧）。v0.9 ⑥上报 A 待裁的 `30007 SOURCE_REFERENCED`（409）问题本批未动。

  ⑥ **测试与调用方现状**：24 测（`tests/test_r02_batch_docs.py`）；门禁 `pytest -q`
     **396 passed / 2 skipped**（基线 372，净增 24）、`ruff` 绿、`mypy` 63 files Success。
     **前端本批零改动**——两条端点当前**无前端调用方**（R0.2.4 只做单篇入口，批量需列表多选 UI）；
     该 UI 建议并入 R0.1.3（服务端分页同页改造），避免同一列表组件连改两次。

- **v0.11 服务端分类过滤与枚举（2026-09-22 登记；R0.1.1/R0.1.2，F-1 + F-9 后端半销账）**：

  ① **`GET /api/v1/spaces/{space_id}/docs?category=`**（R0.1.1，登录保护 10001）：
     在 v0.6 ②的分页参数上**新增** query `category`（≤32）；data 形状不变
     （`{items, total, limit, offset}`，items 含 v0.6 ③的 `category` 字段）。
     - **哨兵口径**：`category=__uncategorized__` = 「未分类」（资产无分类标签）。
       库里存字面空串、**不存哨兵值**；响应保持空串、**不回填哨兵**——哨兵只出现在
       query 入参与 v0.11 ②出参两处契约面。
     - **`total` 与 `items` 同谓词**：分页 + 过滤组合下 `total` 是**过滤后**的数
       （`limit=1, category="AI·技术"` 命中 2 篇时 `total==2`，不是全量 3）——
       否则「第 1/2 页」永远翻不到其余内容。实现上 `list_docs` 与 `count_docs`
       共用仓库 `_docs_stmt` 查询基座（F-3「一份数据两个谓词」类预防；
       该缺陷形态静默，两查询都成功、只是数字不自洽）。
     - **读路径不设分类校验闸门**（与 v0.8 ②写路径 `validate_category` → 10005 相反）：
       未知取值**合法地返回空列表**（`items: []`, `total: 0`），不报错。
       读过滤最坏结果只是「看不到任何东西」；加闸门只会换来假阳性失败——
       `?category=` 带个空格就 422，调用方看到「请求错误」而非「没有匹配」，诊断方向被带偏。
       缓解：v0.11 ②已服务端枚举，UI 不可能产生非法值。
     - 不传 `category` 时行为与 v0.6 ②完全一致（向后兼容，旧调用方零回归）。
     - 越权/无效空间 → 30004/404（不泄露存在性），与不分页时一致。

  ② **新端点 `GET /api/v1/spaces/{space_id}/docs:categories`**（R0.1.2，登录保护 10001）：
     → 200 data `{"items": string[]}`——该空间**实际存在**的分类集合。
     - **服务端枚举，替代前端单页推导**：F-9 的另一半。此前下拉选项由当前页
       `docs.map(...)` 派生，分页后单页推导会漏掉不在本页的分类。
     - **排序 = `CATEGORIES` 声明序**（`categorizer` 约定「声明序即前端筛选项顺序」），
       非入库顺序——否则下拉选项位置随数据抖动。**未登记取值排在已知类之后**
       （只读路径不删值）；**空串以 `__uncategorized__` 置末**。
     - **口径对称（闭环）**：本端点返回值可**直接回传** `?category=`，与 ①入参对称。
       测试显式锁了这条链（取返回值之一作查询参数 → `total == 1` 命中）。
     - **空空间返回 `[]`**，不是 `["__uncategorized__"]`——没有任何 doc 即没有「未分类」，
       不回填哨兵。语义上更诚实，前端空态分支须据此判定。
     - **资产级集合**：join 资产表得出，跨空间共享资产被改分类时，另一空间的集合同步变化
       （承袭 v0.8 ② / v0.10 ②的资产级语义；空间级隔离须加
       `KnowledgeDocument.category_override` 列，**未立项**，登记为 R0.5 候选）。
     - 越权/无效空间 → 30004/404（复用 docs 列表同款判定，不泄露存在性：他人空间与无效 id 同响应）。

  ③ **未加 per-category `count`**（登记，非遗漏）：`GROUP BY` 顺带可得，但会把形状从
     `items: string[]` 改成 `items: {category, count}[]`——**破坏性**形状变更，
     且强迫前端立刻做「下拉显示计数」的 UI 决策（那是设计决策，非实现细节）。
     留给 R0.1.3 一并裁决；若届时需要，同批迁移前端，不存在中间态调用方。

  ④ **承袭的已知不对称（不在本批范围）**：`list_space_docs` 响应里未分类是 `""`，
     而单篇 PATCH（v0.8 ②）响应里是「其他」（`DEFAULT_CATEGORY` 归一化）。
     前端处理法：分类纠偏后**重新拉取当前页**，而非把 PATCH 返回值写回本地状态——
     否则清空分类的行会显示「其他」直到刷新。该修复并入 R0.1.3（顺带修正 `total`）。

  ⑤ **与 v0.6 ③的关系（自我更正，历史条目不回写）**：v0.6 ③曾记「空间详情页筛选下拉
     由列表数据派生」——该方案在分页下**不成立**（漏掉不在本页的分类），本条
     以服务端枚举替代。v0.6 原文保留不改，以便追溯当时的设计依据。

  ⑥ **错误码**：**未新增码位**——复用 10001（未登录）、30004/404（缺失/越权）。

  ⑦ **测试与调用方现状**：新增 5 测（R0.1.1 于 `test_docs_pagination.py`、
     R0.1.2 服务级 + 路由级各 1）；门禁 `pytest -q` **402 passed / 2 skipped**
     （R0.1.1 后基线 400，R0.1.2 净增 2）、`ruff` 绿、`mypy` 63 files Success。
     **前端本批零改动**——两条端点当前**无前端调用方**；接线在 R0.1.3（服务端分页 +
     删除客户端过滤与单页推导 + 空态改判 `total` + 批量入口 UI，见 v0.10 ⑥）。

  ⑧ **R0.1.3 接线竣工回执（2026-09-22；纯 C 域，无契约变更，版本不递增）**：
     ⑦ 的两点状态已过时，在此更正（⑦ 原文保留以便追溯登记时的依据）。
     - **调用方已存在**：`listSpaceDocs` 接 `?category=`（含 `__uncategorized__`
       回传），`listSpaceDocCategories` 接 `GET /docs:categories`。前端新增 10 测
       （`r013-docs-pagination.spec.tsx`）+ 同步改造 `r024-doc-page-wire.spec.tsx`；
       门禁 `vitest` **176 passed / 21 files**、`tsc --noEmit` clean、`next build` 绿。
     - **⑦ 末句「批量入口 UI 并入 R0.1.3」未采纳**：批量入口拆为独立原子 **R0.2.6**，
       理由见执行大纲 §二十一 §21.6。两条 v0.10 批量端点（`docs:delete` /
       `docs:recategorize`）仍**无前端调用方**，待 R0.2.6 接线——此点与 ⑦ 一致。
     - **④ 的处理法已落地且更彻底**：原写「重新拉取当前页」，实施为**重拉第一页**
       （生命周期操作后归位首屏）。原因见 §21.2：服务端分页下本地增删会让
       「本页条数 ≠ `total`」，页码与「加载更多」可用性同步失真。
     - **空态「改判 `total`」的精确口径**：代码判据仍是 `docs.length === 0`，但在
       服务端分页下首屏 `docs.length === 0` 当且仅当 `total === 0`，故语义等价；
       文案按过滤态分三支（见 §21.4）。
     - **两条易踩的口径已在前端固化**：① 空串 `category` **不发送**（空串在服务端
       等于「未分类」，发送 `?category=` 会把「全部」误过滤成「未分类」）；
       ② `:categories` 返回空数组时**不渲染下拉**（空空间无「未分类」，不回填哨兵）。
     - **Next.js 改写实测**：`/docs` 与 `/docs:categories` 两种形态均被 catch-all
       正确转发（含冒号路径未被改写吃掉），见 §21.8。

  ⑨ **R0.2.6 批量入口 UI 竣工回执 + 两条规范性披露（2026-09-22，纯 C 域接线，端点契约零改动）**：
     ⑦ 的两点状态与 ⑧ 的末句均**已过时**，在此更正（⑦/⑧ 原文保留，以便追溯登记时的依据）。

     - **调用方已存在**：`deleteSpaceDocsBatch(spaceId, ids)` → `POST /spaces/{id}/docs:delete`；
       `recategorizeSpaceDocsBatch(spaceId, ids, category)` → `POST /spaces/{id}/docs:recategorize`；
       两者各含 `MOCK_ENABLED` 分支（与其余 client 函数同口径）。前端新增 12 测
       （`r026-chunk-doc-ids.spec.ts` 5 + `r026-doc-batch.spec.tsx` 7）；
       门禁 `vitest` **193 passed / 24 files**、`tsc --noEmit` clean、`next build` 绿
       （`/spaces/[id]` 11.9 kB / 107 kB）。后端**零改动**：402 passed / 2 skipped、
       ruff 绿、mypy 63 不变。

     - **规范性披露 ①（客户端必须在发请求前切片）**：ids 上限 50 是**业务闸**
       （pydantic 层另有 1..500 的体量硬闸，超限走 10005/422 且**零副作用**）。
       客户端若不预切片，用户勾 60 篇只会得到一个「全部没执行」的错误信封——
       比失败更难诊断，因为请求本身语法正确、码位也合规。
       故前端新增 `BATCH_DOCS_MAX_IDS = 50` 并先切片再发（`chunkDocIds`，保序、无空尾批）。
       **已知耦合（登记，非遗漏）**：该常量是后端 `batch_docs_max_ids` 的**客户端镜像**——
       跨语言的重复源，改一处必须改两处。选择镜像而非运行时读取，因为上限在发请求**之前**
       就决定了 UI 文案（按钮标签「批量删除（分 N 批）」与确认弹窗措辞），
       无法延迟到响应之后。

     - **规范性披露 ②（「整批原子」仅在批内成立）**：单次 50 篇内的 `:recategorize` 是整批原子；
       **跨批时每个批次各自独立提交**，后批被整体拒绝时**已生效的前批不回滚**。
       因此 v0.10 ②的「整批原子」不得被理解成「勾选多少篇都整批原子」。
       前端三处如实呈现，而非藏起该细节（藏住的代价是用户以为回滚了而实际没有）：
       按钮标签追加「（分 N 批）」；确认弹窗事前说明；结果面板按批列出被拒批次。
       取舍理由见执行大纲 §二十三 §23.4。

     - **`failed[].error` 不是可展示文案——按 `code` 映射，不要直接展示 `error`**。
       `error` 的取值有两种，取决于异常类型（`services/spaces.py:282` `_failure_entry`）：
       - 异常是 `AppError` → `code = exc.code`，`error = exc.message`，而 `AppError.message`
         回落为 `ERROR_CODES.get(code)`，即 **`LANGBOT_API_ERROR` 这类登记表英文标签**；
       - 异常**不是** `AppError`（未被映射的底层异常）→ `code = 50001`，
         `error = str(exc)`，即**原始 Python 异常字符串，内容不可控**（可能含英文与内部细节）。
       两种情况都不该展示给用户，**`code` 才是承载语义的字段**。前端据此登记
       `BATCH_FAILURE_MESSAGES`（30002 / 30003 / 50001 / 50002）按码映射中文，
       未收录码回落「该篇未能处理（错误码 N）」。

     - **逐篇 `failed[]` 中实际可达的码位，只有引擎调用之后才会出现的失败**。
       30004（任一篇缺失/越权）与 10005（空批/超上限）在任何引擎调用**之前**整体拒绝，
       以错误信封经 `ApiError` 抛出，**永不进入 `failed[]`**（`services/spaces.py:387-388`，
       归一化与归属判定先于循环）。把这两个码收进逐篇映射表是**假完备**——那条分支走不到。
       刻意未做的两件事：未从 barrel 导出 `http.ts` 的内部 `friendlyMessage`
       （barrel 的文档面写明内部设施保持私有，为一条映射把它拉进来是错方向）；
       未整体复制 `ERROR_MESSAGES`（全量错误文案表 ≠ 逐篇可达集合，会把上面的假完备一起复制进来）。

     - **一条对客户端有意义的保证：`failed` 非空 ⇒ `docs >= 1`**。
       全批失败时服务端上抛首个异常（保持原码位，如 30002，`services/spaces.py:418-419`），
       避免「200 但一篇都没删」被误读为成功。故客户端收到 200 时至少有一篇已生效，
       不必处理「200 且 failed 占满」的分支。

     - **两条失败语义的呈现差异**（承袭 v0.10 ② 的裁定，本批只做呈现）：
       - 删除 = 篇级部分成功 → 逐篇列出「篇名：中文原因」+ 成功数/请求数；
         **失败篇的 PG 行完整保留**（逐篇提交，`services/spaces.py:408`），
         故前端把失败篇**留在选中态**——用户再点一次批量删除即**只重试失败篇**，
         把「部分成功」从一句说明变成一个可操作的恢复路径。
       - 改分类 = 整批原子 → 单批恰好一次请求，无中间态；结果面板报出服务端归一化后的
         目标分类（空串归一为「其他」，与 v0.8 ② 的 `DEFAULT_CATEGORY` 口径一致）。

     - **成功篇的回写仍是重拉第一页**（承袭 v0.11 ⑧），不在前端本地摘行。
     - **错误码**：**未新增码位**——复用 10001、10005/422、30002、30003、30004/404、50001、50002。

  ⑩ **R0.4.1/R0.4.2 竣工：两条 Job 端点入册 + 新终态 `CANCELLED`（2026-09-23，B 域，v0.13）**：
     属**契约新增**（两条端点 + 一个新终态），故递增为 v0.13；对比 v0.11 ⑧ 为纯状态更正
     （不递增）、v0.12 ⑨ 含规范性披露（递增）。

     - **`GET /api/v1/jobs`（R0.4.1，原 M1 计划接口「任务中心列表（状态过滤）」已落地）**：
       查询参数 `?type=`、`?status=`、`?limit=`（默认 50）、`?offset=`（默认 0）；
       `data = {items: [...], total, limit, offset}`，条目字段
       `{jobId, type, status, progress, error, workerHeartbeatAt, createdAt, updatedAt}`。
       - **列表不聚合 JobItem counts**——那要按 Job 逐条查（N+1），单篇钻取走 `GET /jobs/{id}`；
         改给 `workerHeartbeatAt` + `updatedAt`，即 STALL 判定的两个输入（R0.4 的可观测性目标）。
       - **`total` 与 `items` 同谓词**：仓库层共用查询基座 `_job_stmt`，且基座**刻意不含
         order_by/limit**——否则 `count(*)` 会套在已被 `LIMIT` 截断的语句上，`total` 悄悄等于
         一页行数。这种漂移**不抛异常**，两条 SQL 都成功，只是数字对不上。
       - **排序 `(created_at desc, id desc)`**：`created_at` 为 `server_default=now()`，
         PostgreSQL 的 `now()` 返回**事务开始时刻**——同一事务内批量建的 Job 时间戳完全相同，
         仅凭 `created_at` 排序属**未定序**，offset 分页会出现重复页/漏行。`id` 是确定性兜底。

     - **`POST /api/v1/jobs/{id}/cancel`（R0.4.2）**：200，`data` 为与列表条目同形的单条视图
       （含最新 `status: "CANCELLED"`）。仅 `QUEUED` 可取消。

     - **新终态 `CANCELLED`**：与 `SUCCEEDED` / `PARTIAL_SUCCESS` / `FAILED` 并列。状态机出边
       `QUEUED → {RUNNING, CANCELLED}`；**刻意不设 `RUNNING → CANCELLED`**——已投入执行的作业
       不半途作废，由 worker 自然收敛（否则半批结果无人对账）。
       服务端幂等键终态集合已补入 `CANCELLED`：漏补则被取消的批次其幂等键永久判为「在途」，
       同一批次**再也无法重新采集且不报错**（静默阻断，比报错更坏）。
       取消的 `error` 字段值 = `"cancelled: 用户取消"`（承袭 `worker_stale:` / `no_items:` /
       `all_failed:` 的 snake_case 原因前缀约定）。

     - **三条规范性披露**：
       - **`type` / `status` 是取值过滤，不是域校验**：未知取值返回**空列表（200）**而非 422。
         读路径不设校验闸门；`limit` ≤ 100 / `offset` ≥ 0 是**资源约束**（防大页 DoS），不是领域规则。
       - **错误信封 `data` 恒为 `null`**（`AppError` 处理器只取 code/message），故**取消被拒时的
         进度只能进 `message`**——如 RUNNING → 30005，message `任务执行中，无法取消（当前进度 42%）`。
         结构化进度仍可由 `GET /jobs/{id}` 取（与 `delete_source` 把计数嵌进 message 的先例同路）。
       - **`?status=` 空串 = 不过滤**：仓库层 `if status:` 是假值判定，与 `list_docs` 的空串
         「未分类」哨兵口径**不同**。前端**不要发送空串参数**（承袭 v0.11 ⑧ 的同类教训）。

     - **取消的拒绝表**：`QUEUED` → 200 `CANCELLED`；`RUNNING` → 30005/409（message 带 progress）；
       终态（含 `CANCELLED` 自身）→ 30005/409（message 带当前 status）；他人或无效 job → 30004/404，
       与 `get_job` 同口径且**不可区分**（不泄露他人 job 是否存在）。

     - **错误码**：**未新增码位**——复用 10005/422（参数越界）、30004/404（缺失/越权）、30005/409（状态非法）。

     - **前端接线提示（R0.4.3 待办）**：`BATCH_JOB_TERMINAL_STATUSES`（`frontend/lib/api/batch.ts`）
       须补 `"CANCELLED"`，否则被取消的作业会被轮询判为「进行中」；且**取消的整库同步作业会报
       `counts: {total: N, succeeded: 0, failed: 0, pending: N}`**，须渲染为「已取消」而非「进行中 0%」。

     - **两处已登记未修邻接缺陷**（判定为预存在，非本批引入，详见执行大纲 §24.8）：
       `_create_sync_job` 在首次同步作业已终结时直接返回该行，导致该订阅**再也无法自动同步**
       （FAILED 今天即同态，增量轮次因每 tick 换新 `run_token` 幂等键而自愈）；
       `_compute_new_manifests` 仅扣减 `QUEUED/RUNNING` 活跃作业，故取消作业的文章**会被重新发现**。

     - **门禁**：`tests/test_r04_jobs.py` 新增 12 测（含 offset 稳定性、幂等键可再投、
       worker 不认领 CANCELLED 三条回归锁）；后端全量 **414 passed / 2 skipped**（净增 12，零回归）、
       `ruff` 绿、`mypy` 63 files Success。**前端本批零改动**，接线在 R0.4.3。

  ⑪ **R0.4.3 任务中心页竣工回执 + 两条规范性披露（2026-09-23，纯 C 域接线，端点契约零改动，版本不递增）**：

     - **两条 Job 端点首次有了前端调用方**（`/jobs` 任务中心页，独立路由）——**更正 ⑩ 的
       「前端本批零改动」**，原文保留不回写。任务中心是**用户级、跨空间**的观测面，故不设空间选择器；
       订阅页（空间内）仍保留它自己的任务进度呈现。

     - **两条规范性披露**：
       - **`error` 字段的原因前缀是日志检索令牌，不是给人看的**：前端 `jobErrorText` 在首个
         `": "`（冒号 + 空格）处截断，只展示中文说明段。按「冒号 + 空格」而非纯冒号截断，
         故 `a:b:c` 不会被误截。**前端不得把 `error` 原文整体展示**
         （`cancelled:` / `worker_stale:` / `no_items:` / `all_failed:` 四个前缀均适用）。
       - **`JOB_TYPE_LABELS` / `JOB_STATUS_LABELS` 是服务端取值集合的客户端镜像、跨语言重复源**
         （与 v0.12 ⑨ 登记的 `BATCH_DOCS_MAX_IDS` 同类）：服务端新增 job 类型或状态时**须同步前端**；
         未同步时前端回落展示原值（不伪造状态、也不静默丢弃）。

     - **前端轮询单元的偏离**：大纲原写「复用 `getJob` 轮询口径」，实施改为**整页 `listJobs` 刷新**。
       理由：列表条目已自带 `progress`，逐条 `getJob` 是 N 倍请求；且列表页刻意不取 JobItem counts
       （⑩ 的 N+1 取舍）。轮询仅在**存在非终态作业**时启动，全终态 / 空列表自动停表。
       刷新单元是整页而非单条，故「加载更多」取到的页外行按 `jobId` 合并保活
       （页外行状态更新延至下次全量刷新——已知局限，登记备查）。

     - **`CANCELLED` 已入 `BATCH_JOB_TERMINAL_STATUSES`**（⑩ 的接线提示已销）；被取消作业按
       「已取消」+ 已完篇数呈现，**不渲染 RUNNING 进度条**——否则
       `progress === 0` 且 `counts.failed === 0` 的已取消批量会被读成「进行中 0%」或「全部成功」。

     - **门禁**：前端新增 2 测文件共 21 测（API 层契约 10 + 页面接线 11），
       `vitest` **215 passed / 26 files**（基线 193 / 24，净增 22）、`tsc --noEmit` clean、
       `next build` 绿（`/jobs` 3.97 kB / First Load 99.3 kB）。**后端本批零改动。**

  ⑫ **R0.5 契约诚实性对齐竣工：`description` 落库 + `PATCH /api/v1/spaces/{id}` + `stats.chunks` 放宽为 `null`（2026-09-23，A+B+C，v0.14）**：

     属**契约新增与字段放宽**（新端点 + 类型放宽），故递增为 v0.14。**本条取代 v0.3c ③**
     （「spaces 域 `description` 暂恒空串、`stats.chunks` 暂返 0」）——该条当时的定性是
     「非 mock 硬编码」的诚实缺口披露，原文明确写「B-T9 接线时定稿」；本批把
     `description` 的缺口真正闭合，而 `stats.chunks` 的缺口由「返回 0」改为「返回 null」，
     两者都属契约语义变更，原文保留不回写。

     - **F-4 销账：`description` 不再被静默丢弃**
       - 根因是三层叠加：`CreateSpaceRequest` 声明了 `description`，`SpaceService.create_space`
         只取 `name`（值在 route→service 边界丢失）；`list_space_views` 与 `get_space_view`
         又各藏一份硬编码 `""`，把实体列的存在性彻底屏蔽。修完写入链后若不删两处硬编码，
         用户会看到「保存成功但列表还是空」——**这是本缺陷最阴的地方：修一半反而更难查**。
       - 新端点 `PATCH /api/v1/spaces/{id}`（大纲 R0.5.2 的「新增 update」）：body
         `{description?: string}`，**缺省即不改**（PATCH 部分更新语义），传 `""` 清空；
         响应复用详情形状；取值非法（>512 / 控制字符）→ `10005`（422）；
         无效 id / 他人空间 → `30004`（404，不泄露存在性）。
         **刻意不含 `name`**：改名触及 `uq_space_user_name` 与既有空间链接语义，需单独裁决。
       - 校验纪律沿用 `update_doc_category`：**先校验后取行，零副作用**
         （非法值不会先读行再失败，越权判定也不发生副作用）。
       - 空串语义：`description` 列可空（迁移 `ab1004m5a`，`String(512) nullable` 且
         **刻意不设 server_default**——PG 下 nullable 且无默认值的 `add_column` 是元数据级操作，
         不重写全表；设 `server_default=""` 则需回填扫描全表，且会把「从未填写」与「显式清空」压成同值）。
         读路径一律下发**空串**（`str(space.description or "")`），**不缺失键**——
         契约稳定比表达「从未填写」更值得；「未填写」由前端空态文案承担。

     - **F-5 销账：`stats.chunks` 由 `number` 放宽为 `number | null`**
       - `0` 会被渲成「已索引 0 块」，把**「指标不可得」谎报成「真的没有分块」**，
         用户会据此以为索引失败而非功能未就绪——这是假数，比空着更坏。
       - **本批未接 LangBot**（大纲原文写「接 LangBot KB 统计查询 + 缓存读取」）。
         实测 LangBot v4.10.9 客户端侧仅有 `list_kb_files`（文件级 `status`），
         **无 KB 级 chunk 统计端点**；用文件数冒充 chunk 数是**换一个假数**，不是修好假数。
         接线需新增 client 方法 + 缓存层（否则每次 `GET /spaces` 都打一次 LangBot，
         正是大纲自己划的红线）。**登记为开放项，待 A 裁定**（需 M0 级活体探测确认
         LangBot 是否暴露 chunk 统计，不在 R0 范围内）。
       - 契约提示：`null` 语义是「无该指标」，**不是**「指标为 0」。展示侧在 `null` 时
         隐藏该指标；`number` 时照常显示。前端 `SpaceDetail.stats.chunks` 已同步放宽。

     - **两条规范性披露**
       - **`stats.chunks === null` 不是缺字段，是明确的「不可得」**：前端不得用
         `?? 0` 兜底，也不得 `toString()` 后拼接——那会把 null 渲成字符串 "null" 或回落到 0，
         两种都把本条的诚实性作废。正确写法是条件渲染。
       - **本批的前端编辑入口缺失**：`PATCH /spaces/{id}` 目前**无前端调用方**
         （前端唯一 `createSpace` 调用方在 onboarding 且只传 `name`），
         故 `description` 现在**可写但不可达**——契约已真，UI 未接。
         大纲 R0.5.4 只要求空态文案，未要求编辑 UI，故本批未加；**登记为开放项**。
         同类先例见 ⑩「前端本批零改动」与 ⑨ 的两条批量端点早期状态。

     - **空态文案的呈现面取舍**（F-4 呈现半）：大纲 R0.5.4 只点名 `spaces/[id]` 详情页，
       故本批只改该一处为「（未填写简介）」——括号式空态表示「字段存在但用户未填写」，
       而「暂无简介」读起来像平台没有这个能力（与 F-5 的「能力未实现」混淆，正是
       R0.5.4 要区分的两件事）。首页空间卡（`app/page.tsx`）与空间列表卡
       （`app/spaces/page.tsx`）**仍为「暂无简介」**：高密度列表面上括号式永久占位
       与卡片主信息（名称 + 篇数）竞争，且超出原子任务边界。已登记为开放项，
       与上面的编辑入口缺失合并处理（有了编辑入口，「（未填写简介）」才有意义）。
       公共库卡的两处（`app/page.tsx`、`app/public/page.tsx`）**不在本条范围**——
       它们渲染的是系统空间字段，数据源与用户空间不同。

     - **门禁**：后端 `tests/test_persistence.py` 新增 1 测走**真实 PG** 验证
       `ab1004m5a` 落列后「建时写入 → 跨 session 回读 → PATCH 改写 → 清空」全链路
       （内存桩证明不了列存在，故必须走真库）；`tests/test_spaces_api.py` 新增 4 测
       （F-4 回归锁：写后读回必须非空；PATCH 部分更新/清空；10005 零副作用；30004 不泄露）。
       前端 `tests/r054-space-detail-honesty.spec.tsx` 新增 4 测（`chunks === null` 不渲指标
       且不显示「0 个」；`chunks` 为数字照常渲——**防止类型放宽后过度隐藏**；
       空串简介渲「（未填写简介）」不渲「暂无简介」；有值原样渲）。
       后端全量 **419 passed / 2 skipped**（基线 414，净增 5，零回归）、`ruff` 绿、
       `mypy` 63 files Success（迁移文件单独 mypy 亦绿）；
       前端 `vitest` **219 passed / 27 files**（基线 215 / 26，净增 4，零回归）、
       `tsc --noEmit` clean、`next build` 绿。
       迁移 `upgrade head` / `downgrade -1` 双向可逆，inspector 实测
       `VARCHAR(512) NULL`、`server_default = None`。

  ⑬ **SPEC-M3 批次 2（A-2 叠加）竣工：新增 admin 域两条跨用户端点（2026-09-23，B+A，v0.15）**：

     管理者裁 **A-2 叠加**：既有三条用户端点（`PATCH /spaces/{id}`、
     `DELETE /spaces/{id}/docs/{doc_id}`、`DELETE /sources/{id}`）**一律不动**，
     `admin` 的跨用户能力走**新增** `/api/v1/admin/*` 端点——**零回归**。
     属**契约新增**（两条新端点 + 一个新路由域），故递增为 v0.15；
     **v0.14 及之前的任何端点语义一字未改**。详见 §六。

     - **新增端点（2 条，openapi() 实测 `/admin` 下仅此 2 条；`/api/v1/spaces` 仍 15 条）**
       - `PATCH /api/v1/admin/spaces/{space_id}`（`admin`）：跨用户改空间简介。
         body `{description: string}`——**必填**（`null`/缺失 → `10005`），
         传 `""` 表示清空；响应 `data: {ok, id, description}`（**写回执**，非详情视图）；
         取值非法（>512 / 控制字符）→ `10005`；无效空间 → `30004`。
       - `DELETE /api/v1/admin/spaces/{space_id}/docs/{doc_id}`（`admin`）：跨用户删单篇文档。
         响应 `data: {ok, docId, docs, assets}`（`assets` = 被连带清理的孤儿资产数，
         跨空间共享则不删）；引擎删除失败 → `30002`/502（PG 无残留）。

     - **刻意不新增 `DELETE /api/v1/admin/sources/{source_id}`**：既有
       `DELETE /api/v1/sources/{id}` **本就无归属校验**（`sources` 表无 `user_id` 列，
       全用户共享的全局资源），admin 变体**不增加任何跨用户能力**，只会多一道闸与一份路由。
       为端点面一致而加一个**空能力端点**属范围蔓延。**既有宽面继续存在**
       （任何登录用户当前可删任何信息源）是管理者**明确接受的代价**，登记备查。

     - **与既有端点的契约分歧是刻意的，勿「统一」**：同一请求体 `{description: null}`
       在 `PATCH /api/v1/spaces/{id}` 返回 **200 详情视图**（PATCH 部分更新语义），
       在 `PATCH /api/v1/admin/spaces/{space_id}` 返回 **10005**。理由：写回执端点没有
       「no-op 也有信息可返回」的语义——详情视图带**本人归属**语义，跨用户取视图另议。
       两端点形状均已有测试双向锁定（`test_user_patch_space_noop_semantics_unchanged` /
       `test_admin_patch_space_requires_description_and_rejects_invalid`）。

     - **`doc.space_id` 归属判据不随空间归属一起放开**：admin 能跨租户操作空间，但
       「该 doc 属不属于这个空间」仍是硬校验（4 种无效目标一律 `30004`）——
       否则可凭任意 `doc_id` 越界删除。这是 A-2 新增面特有的风险面。

     - **授权按 `users.role` 阶梯单调秩判定**（`user`<`operator`<`admin`，取被请求角色的
       **最高秩**），单一来源为 `app/services/roles.require_role`，经
       `app/api/deps.require_roles("admin")` 挂在路由。**未登录 → 10001（先身份后角色）**；
       角色不足 → **10004/403，且失败发生在任何写入之前**（四次拒绝零写入已测）。
       用**空间所有者本人**（`role=user`）当探子仍被拒，正好证明门禁按**角色**而非按
       数据归属生效。

     - **实现纪律——抽 core 而非复制实现**：`update_space` / `delete_doc` 各抽出
       `_update_space` / `_delete_doc` **单一实现**，以 `owner: str | None = None` 表达
       「无归属约束」。两条入口的**全部差异只在这一处判据**；若简介校验顺序、commit 纪律、
       引擎先行顺序在两份拷贝里各写一份，日后修一处忘另一处即漂移
       （非法取值对不存在的空间会返回 `30004` 而非 `10005`）。沿用同文件 `_delete_doc_core`
       的既有手法（自批次 1 起即为「无归属、无事务态」core）。服务方法命名为
       `update_space_any` / `delete_doc_any` 而非 `admin_*`——方法内**不做**角色校验，
       `admin_*` 会被误读为方法内做了授权。

     - **门禁**：后端新增 `tests/test_r11_admin_routes.py` 共 **14 测**，全走**真实 PG**
       （内存桩证明不了跨租户归属与文档行真删除）。分三组——admin 端点 9 测（含引擎先行
       顺序、失败回滚、副本 doc 跳过引擎、4 种无效目标不泄露存在性、单一实现锁）；
       授权门禁 2 测；**零回归锁 3 测**（用户端点跨用户仍 30004、本人 PATCH no-op 仍返回
       详情视图、本人删除路径不变）。
       后端全量 **445 passed / 2 skipped**（基线 431，净增 14，**零回归**）、
       `ruff` All checks passed、`mypy` **65** source files Success（+`app/api/v1/admin.py`）。
       路由面实测：`openapi()` 中 `/admin` 下 2 条、`/api/v1/spaces` 仍 15 条。
       **前端本批零改动**——批次 2 的前端浏览视图待排。

     - **顺手修一处既有编号缺陷**：本文原有两个 `## 五、`（spaces 域字段契约、外部依赖 API）。
       新增 §六 插在两者之间会把序列变成 五→六→五，故将外部依赖 API 改为 `## 七、`，
       章节序号自此单调。文中 4 处 `§五` 引用（均在 §六 内）一律指 spaces 域字段契约，
       无需改动；既无任何引用把外部依赖 API 称作 §五。
  ⑭ **SPEC-M3 批次 3 / T5.4 竣工：admin 域新增三条引擎 Key 端点 + `GET /engines` 两字段追加（2026-09-23，B+A，v0.16）**：

     管理者裁「批次 3 的 GET /admin/engines/keys」**直接做 T5.4 写侧**、「密钥加密」**加依赖，
     AES-GCM 加密落库**；另裁 `POST /admin/public/{space_id}/approve`（T5.5）**不加，登记为双路径风险**。
     属**契约新增**（三条新端点）+ **字段追加**（`GET /engines` +2 字段）+ **字段取值口径变更**
     （`keyEnv` 改报真实 env 变量名），故递增为 v0.16；**v0.15 及之前的端点语义一字未改**，
     `keyEnv` 的变更是**对齐前端既有 fixture 预期**的兼容方向。详见 §6.2b。

     - **新增端点（3 条，均 `operator`+；`GET /api/v1/admin/engines/keys` 与
       `POST`/`DELETE /api/v1/admin/engines/keys/{engine}`）**
       - `GET`：登记状态列表，**不含明文**；返回 `{masterKeyConfigured, items[]}`，
         每个可登记引擎位（`main`/`coze`/`dify`/`fastgpt`）一项，字段见 §6.2b 表。
         `envConfigured`（仅凭 env）与 `configured`（合并登记表后）**并列可比**，
         故「登记覆盖了 env」是**可见的**，不是静默的。
       - `POST`：body `{"key": "..."}`（`min_length=1`/`max_length=1024`；服务端另拒 strip 后
         为空与含控制字符 → 均 `10005`）。upsert，一行一引擎位，`key_id` 换新；
         响应 `{ok, engine, keyId}`——**明文不落库、不回显**，`keyId` 是轮换句柄。
       - `DELETE`：撤销（回落 env；env 亦空则该位不再可用）；**无登记行 → `30004`**
         （不谎报已撤销）；响应 `{ok, engine, revoked}`。
       - `builtin`（内置回退通道，无需 Key）与未知引擎位 → `10005`。

     - **`50002` 而非 `10004`/`10005`**：`ENGINE_KEY_MASTER_KEY` 未配置或畸形时登记/读取拒绝。
       `10004`「无权限」会误导 operator（**他有角色**），`10005`「请求无效」会误导一个
       **没有问题的请求**；`50002`「依赖不可用」准确——加密能力未就绪。
       且 `50002` 已在 `errors.py` 的 `ERROR_CODES` 注册，**不新增码位**
       （`errors.py` 明令新增码位属契约变更须先报 A 登记）。

     - **绝不回落明文**：主密钥缺失时**拒绝**而非降级写明文。理由：UI 显示「已加密登记」
       而库里其实是明文，比一开始就写明文**更难被发现**。畸形 base64 与长度不符同样拒绝
       （静默按截断处理会把「配置错了」伪装成「配置对了」）。

     - **优先级 registered > env，由 `activeSource` 显式回报**（`"registered"`/`"env"`/`null`）。
       登记覆盖 env 必须是可见的——「存了但没生效」是最差的失败形态。
       `GET /api/v1/engines` 亦追加 `activeSource`，故**登记不只影响 admin 视图**，
       也影响前端引擎切换器的「未配置 Key」判定（普通用户可见来源，但不见任何值）。

     - **`keyEnv` 取值口径变更（兼容方向）**：由 settings 字段名（如 `coze_api_key`）
       改为**真实 env 变量名**（`COZE_API_KEY`，大写）。理由：错误提示应指向运维实际要配的东西，
       而非框架内部字段名。后端**无测试断言旧值**；前端 fixture
       （`engine-switcher-states.spec.tsx` / `engines.spec.ts`）**本就期待大写**——
       故此变更是**对齐**既有前端预期，不构成破坏。前端类型补 `activeSource` /
       `decryptFailed` 属 C 域分域另提（运行时多余字段无害，TS 不对运行期值做
       excess-property 检查）——**已兑现**：提交 `a6094ff` 已为 `EngineItem` 补两个可选字段（并加 1 测
       锁定 `configured=true` / `available=false` / `activeSource="registered"` 的合法组合），
       纯 C 域、契约零改动故版本不递增。

     - **实现纪律——凭据解析收敛为唯一谓词 `core.engine_keyring.resolve_engine_key()`**：
       `GET /engines` 的状态上报、`PATCH /spaces/{id}/engine` 的切换闸、`engine_port.py`
       的路由判定与引擎构造**全部走它**。此前 `engines.py` 对 `main` **只查
       `main_kb_api_base`（忽略 Key）**、`engine_port.py` **查 base 且 key**——
       **同一份数据两个结论**（base 已配 Key 空时 `GET /engines` 报「已配置」而入库路径说
       「未配置」）。既有 R0.3.2 全 5 位不变式测试**从未覆盖 base-only 分支**，故缺陷得以上线；
       现不变式**由构造保证**，并补 base-only / key-only 两分支锁。
       这是本仓库第三次出现「同一份数据、两个谓词」缺陷类型（前两次为 F-3 的
       「GET 三条件 / PATCH 两条件」、批次 3 双闸收敛删掉的 allowlist 谓词第二份拷贝），
       故本次以**结构性约束**（唯一函数）而非再补一个不变式测试收口。

     - **迁移 `ab1004m3b`**（承接 `ab1004m3a`）：`engine VARCHAR(32)` PK /
       `secret_ref TEXT` / `key_id VARCHAR(32)` UQ / `registered_by VARCHAR(36)` FK →
       `users.id` ON DELETE CASCADE / `created_at`·`updated_at` 默认 `now()`。
       `secret_ref` 用 **`Text` 而非 `VARCHAR(512)`**——密文长度随明文线性增长（GCM tag +16 字节），
       长度上限会制造**静默截断/写失败**路径；真实边界放请求侧（1024 字符）。
       `downgrade ab1004m3a` + `upgrade head` 往返实测通过；表形状经 `sa.inspect()` **反射核对**。

     - **新增依赖 `cryptography>=43.0.0`**（实装 50.0.1，连带 cffi / pycparser）。

     - **读侧不在 admin 域重复**：引擎全景由既有 `GET /api/v1/engines`（登录即可见）承担，
       本批不另建一个更窄的只读端点。

     - **实修生产缺陷（`InvalidTag` 逃逸）**：`decrypt_secret` 原 except 元组
       `(LookupError, ValueError, binascii.Error, TypeError)` **漏 `cryptography.exceptions.InvalidTag`**，
       实测其 `__mro__ = (InvalidTag, Exception, BaseException, object)` **不经过 `ValueError`**。
       后果：AAD 不匹配（**这正是 AAD 存在要拦的攻击**——把 `coze` 行的密文挪到 `dify` 行解密）
       会以**未处理异常（500）**告终，而非设计要求的 fail-closed（`RequestInvalidError`）。
       已补入并加注释说明为何必须显式列出。

     - **同步惰性路径用进程内快照，不把 async DB 织进同步热路径**：`make_engine` /
       `EngineRouter` 是 sync 且无 DB session，共 5 处构造点（含 `deps.py` 模块级单例）。
       **正确性论证**：所有 async 路由**直读 PG**（权威、永不陈旧），只有同步惰性路径用快照；
       且当前非 builtin 位 `ENGINE_IMPLEMENTED` 全为 `False`，`available()` 恒 `False`，
       `adapter_for` 不会对它们调 `make_engine`——**快照陈旧现在无法造成错误入库判定**，
       最坏回落 env 行为。快照在每次写后刷新，并由 `GET /engines` 预热（覆盖「重启时已有登记行」）。
       `snapshot_age()` 暴露为观测钩子；**多进程部署的跨进程刷新登记未构建**。

     - **门禁**：新增 `tests/test_r11_engine_keys.py` 共 **29 测**，全走**真实 PG**，四层——
       加密 7（往返 / **每次新 nonce**——GCM nonce 复用会泄露，必须防 / **AAD 绑定** /
       空明文拒 / 主密钥缺失·长度错·base64 畸形）；谓词 9（**base-only 历史 bug 锁** /
       登记表优先 coze 与 main / 空登记回落 / builtin 恒真 / 未知位不臆造 /
       **router 与谓词同结论** / 5 位两谓词全等 / `keyEnv` 真实名）；服务 8（**密文落库零明文** /
       拒 builtin 与未知位 / 拒空白与控制字符 / 无主密钥拒且**不落任何行** / upsert 轮换 /
       撤销与缺席撤销 / **解密失败被标注而非丢弃** / 无主密钥全行标注）；
       路由 5（operator+ 门禁 / 登记→列表→撤销全生命周期含 env 并存时 `activeSource`
       翻 env→registered→env / 无主密钥 POST 503·50002 / 拒 builtin 未知位空白 +
       缺席 DELETE 404 + 越权 DELETE 403 / **GET /engines 反映登记**）。
       配套改 `test_p4_engines.py`（`GET /engines` 新增读库依赖，两处端点用例改
       async + `db_session` 夹具 + `dependency_overrides[get_db]`，全套件既有惯例）。
       后端全量 **474 passed / 2 skipped**（基线 445，净增 29，**零回归**）、
       `ruff` All checks passed、`mypy` **67** source files Success
       （+`app/core/engine_keyring.py` +`app/services/engine_keys.py`）。
       路由面实测：`openapi()` 中 `/admin` 下 5 条（批次 2 的 2 条 + 本节 3 条）。
       **前端本批零改动**（类型补充属 C 域分域另提）。

     - **不谎报**：**非 builtin 位 `ENGINE_IMPLEMENTED` 全为 `False`**，登记表当前
       **只影响状态上报与切换前置校验，不影响实际入库链路**（锁 D10）。
       `GET /engines` 刻意**分开回报** `configured=True` 与 `available=False`
       （已配 Key 但骨架位未实接）——两者不可合并，否则会重现 F-3 的伪可用路径。
       多进程快照刷新、密钥轮换工具链（改主密钥后存量密文不可解，须先导出/重录，
       **不静默降级**）均未构建。

     - **T5.5 按裁定不构建，登记为双路径风险**：`PATCH /spaces/{id}/public` 的既有双闸
       已构成一条发布路径；未来若再增 admin 审批路径，两条路径的先后与冲突语义需另行裁定，
       **届时不得静默叠加**。

  ⑮ **SPEC-M3 批次 5 / T6.2 竣工：admin 域新增两条推送通道端点——诚实占位（2026-09-23，B+A，v0.17）**：

     管理者裁「批次 5 的 web 通道怎么落」**诚实占位**——建 `channel → PushProvider` 注册表 +
     `POST /admin/push` + `PushProvider` 协议；`web` provider 显式返回「未投递 + 拒绝原因
     （站内投递面待建）」，`clawbot` 同理返回「未实接（挂微信凭据 + LangBot 出站契约项目内
     不存在）」；**零死表，每通道的拒绝原因都有测试锁定**；**验收口径由「web 通道端到端可发」
     改写为「链路可分发 + 拒绝原因可测」**。属**契约新增**（两条新端点 + 一个新路由子域），
     故递增为 v0.17；**v0.16 及之前的端点语义一字未改**。**零迁移、零依赖新增**。详见 §6.2c。

     - **SPEC-M3 §五 自相矛盾已更正**：同节第 1 条「`web` 内置实现=站内通知占位」与第 3 条
       「验收口径：`web` 通道端到端可发」**不可能同真**——占位不等于端到端可发。四项实测
       依据（全部核自代码，非信 SPEC）：①`BotBinding` 是**死表**（全仓仅
       `app/models/__init__.py` 两处导出引用，无任何 service/route/test 使用，F-8 已标记）；
       ②`backend/app/` **零** HMAC/签名/推送出站代码（仅 `entities.py` 两行**注释**提及）；
       ③`LangBotClient` 是 LangBot **管理面**（KB/ingest/retrieve），**无「给微信用户发消息」
       方法**；④ADR-0002 附录 A 仅记录 clawbot → backend 的**入站验签**契约，
       **backend → 微信用户 的出站发消息 API 项目内无契约可引**。

     - **新增端点（2 条，均 `operator`+）**
       - `GET /api/v1/admin/push/channels`：通道就绪度**读侧**，返回
         `{channels: [{channel, implemented, reason}]}`。加读侧的动机：就绪度**显式回报**，
         而非只能靠试推撞 50002 才知道（同 §6.2b 的 `activeSource` / `masterKeyConfigured` 纪律）。
       - `POST /api/v1/admin/push`：body `{channel, external_user_id, space_id?, doc_id?, message?}`
         （snake_case，与 §6.2 同域口径一致）；`space_id` / `doc_id` / `message` **三者至少一项
         非空**。200 回执 `{ok, channel, delivered}`。

     - **绝不返回 200 假成功**：两通道均未实接，`provider.push()` 返回 `delivered=False`，
       路由据此抛 `DependencyUnavailableError` → **`50002`/503**（`data` 为 `null`），
       message 带通道名与拒绝原因。**返回 200 会让调用方以为消息已送达**——那是
       「显示成功、实际没发生」的推送版。取 `50002` 而非 `10004`/`10005` 的理由与
       ⑭ 完全相同：`10004` 会误导持角色的 operator，`10005` 会误导一个没有问题的请求，
       `50002`「依赖不可用」准确描述能力未就绪，且**已注册、不新增码位**。

     - **拒绝原因逐字锁定即契约**（改文案即改契约，由 `test_web_refusal_reason_verbatim` /
       `test_clawbot_refusal_reason_verbatim` 直接断言字符串）：
       - `web` → `web 通道无站内投递面（无通知表、无读端点），本批不构建`
       - `clawbot` → `clawbot 出站契约项目内不存在（ADR-0002 附录 A 仅入站验签），且微信凭据未注入——活体半程未通`

       **这是「不谎报」的唯一证据**——没有可读拒绝原因，「未实接」与「已通」在外部表现上
       即不可区分。

     - **不新建通知表**：`web` 是「站内通知占位」，但项目内**无通知表、无站内消息读端点**；
       为写侧新建一张表而无读侧，`web` 通道即成为**第二个 `BotBinding` 死表**（F-8 先例，
       已经历标记而未处置）——**同一缺陷不会因第二次实施而变正确**。

     - **校验顺序固定 通道 → 内容 → 目标，全在分发前完成**：未知通道 / 空目标 / 空内容 /
       超长 / 控制字符 → `10005`/422；空间不存在 / 文档不存在 / **文档不属于所给空间** →
       `30004`/404。**失败零副作用**（不落行、不触达 provider，记录型 provider 断言
       `pushed == []`）——**半成功推送是最坏的失败模式**（部分投递不可补偿）。
       **请求问题不得降级成 `50002`**：混淆即误导排查方向。

     - **`implemented` 与 `reason` 成对进入协议**：`PushProvider` 要求三属性
       `name` / `implemented` / `reason`，由 mypy 强制（**首跑报 `attr-defined`**——协议未声明
       `reason`，故**补入协议**而非 `getattr` 绕过；协议声明才是契约）。

     - **不做归属校验，但 `doc.space_id` 不放宽**：A-2 跨用户口径下 operator 以上可代用户
       操作；但「该 doc 属不属于这个空间」是**数据事实**而非授权问题，放宽则跨空间误推
       不可被发现（同 ⑭ 之前 §6.4 对 admin 端点的同一判据）。

     - **分发层回归网**：`test_dispatch_delivers_and_returns_200` 注入一个**会真正投递**的
       记录型 provider，锁定 200 回执形状与 **strip 后透传**语义（`" wx-1 "` → `"wx-1"`），
       并复验目标校验仍先于分发。**真通道落地时该用例即回归基线，无需改写**。

     - **门禁**：新增 `tests/test_r11_push.py` 共 **15 函数 / 16 实例**，全走**真实 PG**，四层——
       provider 5（注册表顺序与全景 / **拒绝原因逐字锁 ×2** / 未知通道不臆造 /
       **占位 provider 在任何输入下永不报 `delivered=True`**，×2 通道参数化）；
       service 5（**校验顺序锁** / 内容校验四类 / 目标存在性三类 / **doc 不属所给 space → 30004** /
       **失败零副作用**）；路由 4（operator+ 门禁与读侧 / **未投递 50002/503 而非 200 假成功** /
       **校验错误仍 10005 不降级** + 目标 30004 / 未登录 10001）；分发 1（200 回执 + strip +
       校验先于分发）。
       后端全量 **490 passed / 2 skipped**（基线 474，净增 16，**零回归**）、
       `ruff` All checks passed、`mypy` **69** source files Success
       （+`app/providers/push_port.py` +`app/services/push.py`）。
       路由面实测：`openapi()` 中 `/admin` 下 **7 条**（批次 2 的 2 条 + §6.2b 的 3 条 + 本节 2 条），
       总 path 数 37。**前端本批零改动**——为**恒返回 503** 的端点建 UI 属范围蔓延；
       admin 控制台浏览视图仍随批次 2 前端一并排。

     - **不谎报**：本批**从不产生真实投递**。落地的是注册表、协议、校验与两条路由；投递面为
       **能力未就绪**（50002/503）。**缺口登记不销账**——SPEC-M3 §五「后台控制主动发送」的
       **落地处已就位**（路由 + 注册表 + 校验），但**投递面不存在**，属能力未就绪而非缺口关闭，
       须与 D10 同类登记；**推送出站契约缺口**（backend → 微信用户 无 API 可引）
       登记为**独立开放项**。`BotBinding` 死表**刻意不动**——其处置属 T6.1（R1.3），本批不越界。

  ⑯ **SPEC-M3 批次 4 / T5.7 竣工：admin 域新增两条批量文档端点（2026-09-23，B+A，v0.18）**：

     新增 `POST /api/v1/admin/spaces/{space_id}/docs:delete` 与 `docs:recategorize`（均
     **`admin`+**）。属**契约新增**（两条新端点），故递增为 v0.18；
     **v0.17 及之前的端点语义一字未改**。**零迁移（Alembic head 仍 `ab1004m3b`）、零错误码新增**
     （`errors.py` `ERROR_CODES` 零改动）。详见 §6.2d。

     - **既有两条用户批量端点（§五，R0.2.5）零改动**（A-2 承诺面）；请求体模型
       `BatchDocIdsRequest` / `BatchDocCategoryRequest` **直接复用不复制**（pydantic 体量硬闸
       1..500 与字段约束必须单一来源）。

     - **授权门槛与 §6.2b / §6.2c 不同，非笔误**：本节端点声明 `require_roles("admin")`，
       而 §6.2b / §6.2c 声明 `require_roles("operator")`。批量删除是**不可逆的破坏性操作**
       且跨租户，取更高秩。角色阶梯单调（`user` 0 < `operator` 1 < `admin` 2），`admin`
       经秩覆盖 `operator`；但**秩不是越高越宽**——`operator` 秩**低于** `admin`，访问本节端点
       **仍被拒**（403/10004）。测试用**空间所有者本人当 `user` 探子**（他对自己空间有完全
       使用权却被拒）证明门禁按**角色**而非按数据归属生效。

     - **两项契约要点**：①**批量删除 = 篇级部分成功**（与单篇 DELETE 的 all-or-nothing 相反）——
       引擎失败篇的 **PG 行完整保留**、可原样重试；**全批失败上抛错误信封**（30002/502），
       不返回「200 但一篇都没删」被误读为成功。②**批量改分类 = 整批原子**——任一篇缺失 → 30004，
       全批回滚，无「改了一半」中间态；`category` 生效范围是**资产级**（对本资产在其他空间的
       呈现一并生效）。③**校验先于取行**——对不存在的空间提交非法取值也返回 10005 而非 30004。

     - **`doc.space_id` 归属判据三处同口径**：单篇 DELETE（§6.2）、批量删除（§6.2d）、
       推送目标校验（§6.2c）——admin 可跨租户，但「该 doc 属不属于这个空间」仍是硬校验，
       否则可凭任意 `doc_id` 越界批量删除。

     - **测试面 14 例，四层，全走真实 PG**：admin 批量删除 6（跨用户引擎先行 + 计数递减 /
       篇级部分成功 / 全批失败走错误信封 / 三类无效目标 30004 / 副本行跳过引擎 /
       请求形态错误在引擎调用前拒绝且零副作用）+ admin 批量改分类 3（跨用户持久化 + 资产级生效 /
       非法取值先校验后取行 / 任一篇缺失整批回滚）+ Service 单一实现锁 1（四条入口都在取行前
       校验）+ 授权门禁 2（所有者当 `user` 探子 + `operator` 秩低于 `admin`；未登录 10001）
       + A-2 零回归锁 2（既有用户批量端点跨用户仍 30004 / 本人行为不变）。
       夹具纪律：`knowledge_documents` 有唯一约束 `uq_doc_asset_space`（`asset_id, space_id`），
       副本行用例须铺独立资产。
       后端全量 **504 passed / 2 skipped**（基线 490，净增 14，**零回归**，35.90s）、
       `ruff` All checks passed、`mypy` **69** source files Success（改的是既有文件，文件数不变）。
       路由面实测：`openapi()` 中 `/admin` 下 **7 → 8 个路径**（9 个操作——
       `engines/keys/{engine}` 有 POST + DELETE），总 path 数 37 → **39**。**前端本批零改动**；批次 5 的「不为恒 503 端点建 UI」论据
       **对批次 4 不适用**——本节端点有真实 200 路径，属可建 UI 的面，批次 2 前端排期时
       应一并纳入批量操作面板。

     - **T5.6 计费预留按裁定不建任何计费面（管理者，2026-09-23）**：两项实测——①仓库根目录
       **仅有 `compose.yml`**，**无 `compose.prod`**，SPEC-M3 §六 与本大纲三处施工面表的
       「计费表预留（`compose.prod` 预留位）」**锚点失实**（据实测更正）；②`billing` / `计费` /
       `charge` / `quota` 全仓（排除 `.venv`）**零命中**——无表、无配置旋钮、无代码、无消费者。
       且 SPEC-M3 §九-3 本就把真实计费结算列入不做清单。三种候选写入面皆引入新缺陷
       （第二个 `BotBinding` 死表 / 无消费者的死旋钮 / 无流程使用的 compose 文件），故**零代码落档**。
       **不谎报**：T5.6 的落地处（SPEC 表格行 + §九-3 扩写 + 缺口登记 + 失实锚点更正）就位，
       但**能力不存在**，属**能力未就绪**而非缺口关闭，须与 D10 同类登记。计费面登记为
       **独立开放项**（与推送出站契约同类），**缺口不销账**。因无契约变更，本文档不为 T5.6
       递增版本号。

     - **至此 T5 八项后端施工面全部收官**；R1.1 剩余施工面收敛为**批次 2 前端浏览视图一项**
       （**v0.19 已销账**：见条目 ⑰）。

  ⑰ **SPEC-M3 批次 2 收官：`/me` 增补 `is_admin` + admin 域补齐两条读端点（2026-09-23，B+C，v0.19）**：

     属**契约新增**（`/me` 新字段 + 两条新端点），故递增为 v0.19；**v0.18 及之前的端点语义
     一字未改**。**零迁移（Alembic `heads` 实测仍 `ab1004m3b`）、零错误码新增**
     （`errors.py` `ERROR_CODES` 零改动）。提交：`22ed6f6`（B，4 文件 +127/−3）、
     `7308cee`（B，4 文件 +269/−19）、`ca973cb`（C，10 文件 +909/−3，前端控制台）。

     - **`GET /api/v1/auth/me` 增补 `user.is_admin: boolean`**——前端 admin 门禁的**唯一依据**。
       由**本地 `users.role` 经同一秩谓词**派生：`roles.py` 新增
       `has_min_rank(role, min_role) -> bool` 与 `sub_has_min_rank(db, sub, min_role) -> bool`，
       `AuthService._is_admin` 调用 `sub_has_min_rank(..., "admin")`，而 `require_role`
       **改为委托** `has_min_rank`。两处共用同一个秩比较，故「回显 `is_admin=true` 但调用
       admin 端点 403」（或反之）在**结构上不可能发生**——若 `/me` 各写一份判定，两次判定
       漂移不会有任何调用方报错。已用 `test_is_admin_flag_and_admin_gate_agree` 直接锁这条
       不变式。

     - **`/me` 只读、绝不抛错，故谓词返回布尔而非依赖**：`require_role` 靠抛
       `PermissionError` → 10001/10004 表达拒绝，那是**写侧门禁**的语义；`/me` 是**读侧回显**，
       任何角色都必须拿到 200 与自己的身份，否则非 admin 用户连登录态都拿不到、前端无从
       渲染。故 `has_min_rank` / `sub_has_min_rank` 一律返回布尔，**缺用户返回 `False` 而非
       抛错**（fail closed 且不破坏登录态）。

     - **未知 `role` 取值 fail closed 到默认秩**：`ROLE_RANK.get(role,
       ROLE_RANK[DEFAULT_ROLE])`——脏值（大小写错、枚举外的历史值）一律按 `user` 处理，
       **不**按最高秩兜底。失败方向必须是收紧而非放宽。

     - **⚠ 前端不得从 `user.role` 自行推导 `is_admin`**：真实主平台 userinfo 的 `role` 是
       **大写枚举**（`"USER"`），与本地授权阶梯（`user`/`operator`/`admin`）**不同源、不同形**，
       拿它门禁会与后端 10004 **双向分歧**（前端认为可进而后端拒，或反之）。
       `normalizeMeData` **不从 `role` 推导** `is_admin`，并由 `me-normalize.spec.ts` 锁定
       ——`role: "ADMIN"` / `role: "admin"` 均得 `false`，任何人「顺手」用 role 推导即刻红灯。
       **`is_admin` 缺失（旧后端未回显）时前端一律按 `false`**（fail closed）；前端门禁在
       **渲染层**解决且**零跨用户请求发出**（不把请求打出去换 10004）。

     - **新增两条 admin 读端点（§6.2）**：`GET /api/v1/admin/spaces` 与
       `GET /api/v1/admin/spaces/{space_id}/docs`（均 `admin`+）。**缘由**：批次 2 后端竣工
       （v0.15）时 `/admin` 只有**写端点**、无读端点——A-2 叠加（既有端点零改动）的代价就是
       admin 面**没有浏览能力**，前端控制台无从构建。本节端点数 **2 → 4**；`/admin` 路由数
       **8 → 10 个路径**（9 → 11 个操作），总 path 数 **39 → 41**，`/api/v1/spaces` 仍 15 条。

     - **`..._any` 手法，抽 core 不复制实现**（承 v0.15 §6.2 与 v0.18 §6.2d）：
       `list_space_views_any` / `list_space_docs_any` 委托既有 `_space_view` /
       `_list_space_docs` 并以 `owner=None` 表达「无归属约束」——服务端分页、分类过滤、条数
       上限口径与用户端点**同源**（测试锁定 admin 面分页与分类过滤结果一致）；复用既有
       `Space` / `SpaceDoc` 契约视图，**不复制模型**。

     - **归属三元组只在 LEFT JOIN 命中时注入（非空对象）**：`SpaceRepository.list_with_owner`
       用 **LEFT JOIN `users`** 而非 INNER JOIN——归属账号可能已被删除，INNER JOIN 会
       **静默吞掉**这些空间，而「有空间无主」恰恰是 admin 需要看到的异常态。前端据此区分
       「未归属」与「归属信息为空」，空归属渲染「（归属账号已不存在）」而非 `undefined`。
       **既有用户端点响应不含这三个字段**（A-2 零回归锁，有测试断言）。

     - **错误码取用（零新增码位）**：读端点无效空间 → **30004 / 404**（不泄露存在性）；
       未登录 → 10001 / 401；非 admin → **10004 / 403**（`user` 与 `operator` 均被拒）。
       前端 `ERROR_MESSAGES` 同步补 **`10004: "权限不足"`**——此前 admin 域拒绝会回落成通用
       「请求失败，请稍后重试」，门禁拒绝必须**指名道姓**，否则排查方向被误导（同类于条目 ⑮
       「10005 不得降级成 50002」的纪律）。

     - **测试面**：后端 **10 例新增**（`is_admin` 4：回显与本地秩一致 / 未知取值 fail closed
       + 非法秩抛错 / 缺用户返回 `False` 而非抛错 / **回显与门禁一致性**；读面 6：跨用户清单
       带归属 / 跨用户文档清单 / **分页与分类过滤口径一致** / 无效空间 30004 /
       **门禁 `user`+`operator` 均 10004、未登录 10001** / **A-2 零回归锁——用户端点响应
       不含归属字段**）。前端 **11 例新增**（`r11-admin-console.spec.tsx` 10 例 +
       `me-normalize.spec.ts` 1 例），其中一例直接 `vi.stubGlobal("fetch", ...)` 打
       `{code:10004}` 走**真实 `request` 管线**，证明 `ERROR_MESSAGES` 条目经友好化链路到达
       用户。
       后端全量 **514 passed / 2 skipped**（基线 504，净增 10，**零回归**，35.09s）、
       `ruff` All checks passed、`mypy` **69** source files Success（改的是既有文件，文件数
       不变）；前端 `tsc --noEmit` clean、`vitest` **31 文件 / 289 用例**（基线 30 文件 /
       278 用例，净增 11，**零回归**）。

     - **`next lint` 未能运行（不谎报）**：仓库**无 ESLint 配置**，`next lint` 首次运行需
       交互式选择「Strict / Base / Cancel」并会改写配置（实测输出
       `? How would you like to configure ESLint?` 即停），属**既有仓库状态、非本批引入**，
       故**不作绿灯声明**。

     - **浏览器活体冒烟**（`next dev -p 3110`，mock 模式）：TopBar 在 mock 模式下**不渲染**
       「管理」入口（`MOCK_ME.is_admin: false`）✅；直访 `/admin` 渲染「权限不足」卡 +
       「返回空间列表」且**无白屏** ✅。**不谎报**：**正向跨用户路径未经浏览器验证**——
       后端 8000 端口未起（实测端口空闲）且需一个真实 `role=admin` 账号才能拿到
       `is_admin=true` 走通 `listAdminSpaces` → 跨用户文档清单 → 批量操作全链；该路径由
       **jsdom 覆盖**（跨用户浏览与批量操作两组共 6 例），非零覆盖但**未经活体**。
       3000 端口当时承载的是另一应用（无 `/admin/login` 路由），故另开 3110。

     - **前端注入缝的回归教训（已修，留档）**：批量操作的端点注入初版把缺省值写成**渲染期
       默认参数**（`deleteBatch = deleteSpaceDocsBatch`），渲染期即解引用被 mock 的模块命名
       空间——Vitest 的 ESM mock 对**未声明的导出是「访问即抛错」**
       （`No "X" export is defined on the "@/lib/api" mock`）而非返回 `undefined`，导入绑定
       的解引用发生在**使用点**故默认参数在渲染期触发，导致 **4 个既有测试文件 / 23 个用例
       失败**；改为在 `runDelete` / `runRecategorize` **调用时**取用
       （`const deleteFn = deleteBatch ?? deleteSpaceDocsBatch`）后恢复全绿，**未改动任何
       既有测试文件**。教训：跨测试替身边界的可选依赖，缺省值必须在**使用点**解析，不得在
       渲染期解析。

     - **R1.1 收官**：批次 2 前端浏览视图 + 批次 4 批量操作面板随本批交付（`ca973cb`），
       条目 ⑯ 末尾登记的「剩余施工面收敛为批次 2 前端浏览视图一项」**已销账**——**R1.1 全部
       施工面收官**（后端八项 T5.0~T5.7 + T6.2 与前端控制台均已交付，无外部锁的施工面已无
       剩余）。admin 台范围**严格** = 批次 2 浏览 + 批次 4 批量：**不纳** §6.2b 引擎 Key
       面板（`operator`+ 与 admin 台不同秩，混页会让门禁语义含糊）、**不纳** §6.2c 推送面板
       （恒 50002/503 的诚实占位，为其建 UI 即把「能力未就绪」渲染成「可点击但失败」）。
       因 §6.2b / §6.2c 本身不变，其语义不受影响。

  ⑱ **R4 第八/九波收官：作业与订阅跨用户读面 + 信息源写面收口 + 跨用户删空间 + OpenAPI 安全方案（2026-09-23，B，v0.20）**：

     属**契约新增**（五条新端点 + 一处既有端点门禁收紧 + OpenAPI 安全方案声明），故递增为
     v0.20；**v0.19 及之前的端点语义一字未改**（例外见下「一处加法式字段变更」）。
     **零迁移（Alembic `heads` 实测仍 `ab1004m3b`）、零错误码新增**（`errors.py` `ERROR_CODES`
     零改动）。提交：`8d2a8fe`（R4.8，8 文件 +812/−47）、`09acfc1`（R4.9.3，2 文件 +249/−18）。
     详见 §6.2 / §6.2e / §6.6。

     - **新增五条端点（§6.2 + §6.2e）**：`GET /api/v1/admin/jobs`、
       `GET /api/v1/admin/jobs/{job_id}`、`GET /api/v1/admin/subscriptions`（均 `admin`+）、
       `PATCH /api/v1/sources/{source_id}`（`admin`+）、`DELETE /api/v1/admin/spaces/{space_id}`
       （`admin`+，T5.8）。缺口与 §6.2 同源——jobs / subscriptions 既有读端点**全带本人归属
       谓词**，admin 无法回答「全系统哪条号卡住了 / 谁在跑同步」。**路由面实测**：`/admin`
       **10 → 13 个路径（11 → 15 个操作）**，总 path 数 **41 → 43**，`/api/v1/spaces` 仍
       15 个路径（22 个操作）。

     - **`DELETE /api/v1/sources/{id}` 宽面收口（更正本文两处失实）**：v0.9 ③ 与 §6.2 曾记
       「**无归属校验（登录即可操作）**」「**任何登录用户当前可删任何信息源**」。本批该端点
       已挂 `require_roles("admin")`，**与新增 `PATCH` 同口径**——普通用户已无法删源或改源。
       §6.2 的原文保留并在其下加更正注（**不静默改写历史裁定**，v0.9 ③ 原文不动，以便追溯
       「管理者明确接受该代价」的当时依据）；**v0.9 ③ 的原文自 v0.20 起失效**，读者以本条与
       §6.2e 为准。

     - **一处加法式字段变更（如实登记，非「一字未改」）**：`JobService._view` 追加 `ownerId`，
       而该视图**同时被用户端点使用**——故 `GET /api/v1/jobs` 的 `items` 与
       `POST /api/v1/jobs/{id}/cancel` 的 `data` 各多一个键。前端忽略未知键即零回归，
       但这是**契约加法**，不是无变更。取舍见 §6.2e：拆两份视图会让「列表/详情字段集」漂移成
       两份拷贝，而 `ownerId` 对本人端点不泄露任何跨用户信息（值恒为调用方自己）。
       订阅侧未偏离：`spaceId`/`spaceName`/`ownerId`/`ownerNickname` **只在 `owner=None` 时附加**
       （M3 批次 2 的「独立端点承载增量」口径），`GET /spaces/{id}/subscriptions` 形状零变化。

     - **`GET /api/v1/admin/subscriptions` 的 `space_id` 语义**：省略 = **全系统跨空间视图**
       （既有端点强制本人空间，无法表达「为什么这条号没人同步」）；给定 = 仅该空间、
       **不做归属校验**；给定**不存在的** id → `30004`（不校验存在性会让「空间不存在」与
       「空间无订阅」无法区分）。

     - **F-24（P0，潜伏缺陷，本批才暴露）**：`with_only_columns(func.count())` 会把 SELECT 列
       换成标量函数，SQLAlchemy 随即**剪掉它不引用的 FROM**——零条件时语句退化成
       `SELECT count(*)`（**无表**），恒返 1。历史实现靠 `Job.user_id == user_id` 这个
       **恒有**谓词把 FROM 顶住故从未暴露；`user_id` 放开为可选（跨用户清单）后，
       「列表 3 条、总数报 1」，分页按 1 页渲染，清单完全不可用。修：显式 `.select_from(Job)`；
       测试锁**编译口径**（count 语句必须含 `FROM jobs`）+ **原始 SQL 对账**。
       **跨域陷阱**：任何「全可选谓词」的仓库复用该惯用法而不补 `select_from` 都会得常量 1——
       仓内两处（`repositories/job.py`、`repositories/space.py`）已逐一核对。

     - **F-23（契约修正）**：`GET /api/v1/sources` 返回**全用户共享**清单，旧实现却把 `user_id`
       透传给 `list_sources` 后被忽略——死参数 + 契约误导（让人以为存在「我的信息源」）。
       `sources` 表**无 `user_id` 列**，该概念无定义。参数已移除，登录闸门改挂 `get_current_sub`
       （纯身份，无需查库）；`inspect.signature` 直接断言签名不含 `user_id`。

     - **新增缺陷登记（不销账）**：F-19（无手动重新采集入口）、F-20（langbot 容器归属旧 compose
       project + 9 处硬编码 `container_name`）、F-21（`test_scheduler.py` 与部署中 scheduler 共库
       竞态，`claim_due` 无归属谓词——**根治需独立测试库**）、F-25（`onboarding/steps` 静态桩）。
       详见《剩余任务原子化执行大纲》§三十八。

     - **R4.9.3 OpenAPI 安全方案（§6.6）**：`components.securitySchemes` 由恒空改为声明
       `apiKey`/`cookie`（名称取自 `session_cookie_name` 配置）；**55 个操作中 50 个标注为需会话、
       5 个公开**。标注取自**路由声明的依赖树**（出现 `get_current_sub` 即需会话）而非路径白名单——
       新端点自动纳入；`require_roles` 每次返回新函数故按身份匹配不可靠，但其依赖树含
       `get_current_user_id` → `get_current_sub`，一个锚点即可覆盖用户域与全部 admin 域。
       **唯一例外清单 `MANUAL_SESSION_ROUTES`** 收录 `GET /api/v1/auth/me`（处理器内自查 cookie，
       不走 `get_current_sub`，不登记会被误标为公开）。**漂移锁方向刻意**：断言「未标注集合
       **精确等于** 5 条」——少标比多标危险（后者只是文档冗字，前者让读者以为无需登录）。
       **三个实现约束**（回退即缺陷）：不遍历 `app.routes`（FastAPI 0.141 把 `include_router`
       产物懒收敛成私有 `_IncludedRouter`，`app.routes` 上取不到 `APIRoute`，标注器会**静默标 0 条**；
       改用模块级 `APP_ROUTERS`，由 `test_every_included_route_reaches_schema` **双向锁**）；
       `Dependant.dependencies` 元素是 `Dependant` 本身而非 `Depends` 包装；过滤 `HEAD`/`OPTIONS`
       与 `include_in_schema=False` 的路由（框架自带 `/docs` 等在 `paths` 里无键，写它会 KeyError）。

     - **门禁**：R4.8 新增 `tests/test_r48_admin_jobs.py` **16 测**（全走真实 PG）；
       R4.9.3 新增 `tests/test_r493_openapi_security.py` **6 测**（含漂移锁、无悬空 `security`
       引用、`require_roles` 旁路防护、路由登记双向核对）。后端全量 **551 passed / 2 skipped**
       （基线 514，净增 37，**零回归**）、`ruff check app tests alembic` All checks passed、
       `mypy app` **69 files** Success。**前端本批零改动**——三条 admin 读端点与 `PATCH /sources`
       均无前端调用方；admin 控制台**当前范围严格 = 批次 2 浏览 + 批次 4 批量**（条目 ⑰ 裁定），
       扩为「作业中心 / 订阅全景」面板前**须先扩该范围裁定**，不得静默叠加。

     - **不谎报**：Swagger UI 的**浏览器活体**未经验证——`docker inspect aideanbot-backend
       --format '{{json .Mounts}}'` 返回 `[]`（后端容器**无 bind mount**），容器跑的是镜像内代码，
       `localhost:8000/docs` 仍呈现未标注的 schema。已验证的是 **OpenAPI JSON 契约**（6 测全绿），
       非浏览器呈现；未重建镜像（属部署动作，未获授权）。

## 八、admin 域新增：发现渠道就绪度（R7.6，2026-09-28 登记）

> 属**契约新增**，故版本递增。既有端点语义一字未改。**零迁移**（Alembic head 仍 `ab1004s1a`）、
> **零错误码新增**。

| 端点 | 授权 | 语义 | 响应 data |
|---|---|---|---|
| `GET /api/v1/admin/discovery/channels` | `operator` | 发现渠道就绪度全景 + 当前默认渠道解析结果 | `{channels, defaultChannel, selectionReason, configuredChannels}` |

**响应结构**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `channels[]` | array | 全部**已注册**渠道（含未启用、未实接的） |
| `channels[].name` | string | 渠道名（如 `redfox` / `rss`） |
| `channels[].description` | string | 渠道语义说明 |
| `channels[].implemented` | bool | 代码是否**已实接**。`false` = 端口在位但未接线 |
| `channels[].enabled` | bool | 是否在 `discovery_channels` 白名单内（白名单为空串 = 全部启用） |
| `channels[].available` | bool | 凭据就位、**现在能否真的用** |
| `channels[].reason` | string | 当前不可用的具体原因：`未实接…` / `未启用（需加入 discovery_channels 白名单）` / `REDFOX_API_KEY 未配置`；可用时为空串 `""`（显式值，非缺字段） |
| `defaultChannel` | string \| null | 本轮调度将使用的发现渠道；`null` = 本轮不做发现、仅按既有清单 Diff |
| `selectionReason` | string | `configured`（白名单命中）/ `registration-order`（空白名单回落注册序）/ `none-available`（无可用渠道） |
| `configuredChannels` | array | 后台配置的白名单（排序后），空数组 = 未配置 |

**设计口径**：`implemented` / `enabled` / `available` 三者**刻意分离**，不合并成单一布尔。
沿用 §6.2e `GET /admin/push/channels` 的显式回报纪律——「代码在位」≠「现在可用」，
合并会把「配置缺失」伪装成「渠道故障」，也无法区分「功能没做」与「功能没配」。
`defaultChannel=null` 与调度器跳过发现的日志同源，**「配了但没生效」永远可见**。

**门禁**：未登录 → `10001`/401；非 `operator`/`admin` → `10004`/403（与 `/admin/push/channels` 同口径）。

**为何不建渠道配置表**：渠道注册表当前只有 1 个实接项，为它开一张 DB 写面而无读侧消费方，
会复刻 `BotBinding` 死表反模式（§6.2e 已两次标记）。当前以 `Settings` 的
`discovery_channels` / `discovery_default_channel` 承载；第二个渠道实接时再评估是否落库
（注册表 `CHANNELS` 的 dict 结构即为该处接缝）。

**已实接 / 未实接现状**：`redfox` 已实接（凭据项 `REDFOX_API_KEY`）；`rss` 已注册但
`implemented=false`（需先把公众号清单暴露为 HTTP 接口再实接 `query_work_list`）。
需求原话「**多种**方式自动化采集」中的「多种」尚未满足，缺口已在运行系统内可见
（`GET /discovery/channels` 返回 `implemented=false` + `未实接` reason），不再只存在于聊天记录里。

## 九、admin 域新增：常驻进程存活（R7.7，2026-09-28 登记）

> **契约新增**：1 条端点 + 1 张表（迁移 `ab1004h1a`，Alembic head 现为 **`ab1004h1a`**）。
> 既有端点语义一字未改，**零错误码新增**。

| 端点 | 授权 | 语义 | 响应 data |
|---|---|---|---|
| `GET /api/v1/admin/ops/liveness` | `operator` | 常驻进程（`scheduler` / `worker`）到底在不在跑 | `{processes[], maxAgeSeconds, allHealthy}` |

**查询参数**：

| 参数 | 默认 | 约束 | 说明 |
|---|---|---|---|
| `max_age_seconds` | `300` | `ge=10, le=3600`（越界 → 422） | stale 判定阈值。**刻意 > 心跳节流 30s**，健康进程不会误报 |

> 命名口径：query 参数走 **snake_case**（与全项目 `space_id` / `type_` / `offset` 一致），
> JSON 响应体走 **camelCase**。两者不统一是既有约定，非本端点引入。

**响应结构**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `processes[]` | array | **按期望进程清单**返回，不是按表里的行——所以「从未报到的进程」也会出现，值为 `null` |
| `processes[].processKey` | string | `scheduler` / `worker` |
| `processes[].purpose` | string | 该进程职责（供运维直接读懂，不必翻代码） |
| `processes[].lastHeartbeatAt` | string \| null | ISO 8601 UTC（`+00:00`）。`null` = **从未报到** |
| `processes[].ageSeconds` | int \| null | 距今秒数，由**服务端时钟**计算。`null` = 无行可算 |
| `processes[].stale` | bool | `true` = 缺行 **或** 超阈值 |
| `processes[].lastDetail` | string | 最近一次报到的现场（如 `job=<id> item=<id> retry=<n>`），最多 512 字符，无内容时为空串 |
| `maxAgeSeconds` | int | 本次判定所用阈值（回显，便于判读） |
| `allHealthy` | bool | 全部进程均新鲜 |

**响应实例（2026-09-28 上线实测）**：

```json
{"code":0,"message":"ok","data":{
  "processes":[
    {"processKey":"scheduler","purpose":"订阅定时调度：认领到期订阅 → Manifest 发现 → Diff 入列 → 推进水位",
     "lastHeartbeatAt":"2026-09-28T03:15:32.154638+00:00","ageSeconds":5,"stale":false,"lastDetail":""},
    {"processKey":"worker","purpose":"Job 执行器：逐篇 ingest → 推 LangBot RAG",
     "lastHeartbeatAt":"2026-09-28T03:15:32.119313+00:00","ageSeconds":5,"stale":false,"lastDetail":""}
  ],
  "maxAgeSeconds":300,"allHealthy":true},"requestId":"81040661-c9bb-45ca-b002-c7c53dac8e33"}
```

**设计口径**：「**从未报到**」（`lastHeartbeatAt: null`，进程从未启动——容器缺失类故障）
与「**曾报到但已过期**」（进程启动过但卡死或已死）**刻意区分**，不合并为一个布尔。
两者的处置动作不同：前者要 `up -d` 创建容器，后者要 `restart` 或查卡死点。
合并后运维会拿到「不健康」而不知道该做什么。

**为何必须有这个端点**：`scheduler` 与 `worker` **不开任何端口**，TCP 探针无从谈起。
此前唯一信号是 `docker ps` 的 `(healthy)`，而那只对 backend 有效——两个常驻进程此前
**没有 healthcheck**，卡死与缺失都不可见。现两者均配 healthcheck，读同一张表。

**同时落地的两条约束**：
- **心跳不是关键路径**：`beacon()` **吞掉一切异常**。心跳写库失败绝不能变成采集中断——
  遥测故障不得升级为业务故障。
- **上报位置在循环开头**：卡在循环体里的进程立刻过期，而不是要等 stale 阈值过后才暴露。
  放在结尾会把「正在挂死」误报成健康直到超时。

**门禁**：未登录 → `10001`/401；非 `operator`/`admin` → `10004`/403（与 §六、§八 同口径）。

**运维查询路径（无需登录，零门槛）**：`docker ps` 的 HEALTH 列。
两个服务的 healthcheck 是 `python -m app.services.process_heartbeat <key> --max-age 300`
（退出码 0 = 新鲜，1 = 过期/缺行/未知键）。
⚠️ **unhealthy 不会自动重启**：`restart: unless-stopped` 只认容器退出码，
「进程活着但循环卡死」时容器并未退出——healthcheck 负责**暴露**，恢复仍需人工 `restart`。
详见《部署运维手册》§3.4d。

## 十、R8 契约纠偏：注册入口校验 + 证据状态字段 + 分页语义澄清（2026-09-28 登记）

> ①② 属**契约变更**（新增拒绝口径 + 字段追加），故版本递增为 v0.22。③ 为**语义澄清**，
> 不涉及任何端点或字段改动。**零迁移**（Alembic head 仍 `ab1004h1a`）、**零新增错误码**
> （复用 `10005`）。

### 10.1 `POST /api/v1/sources` 的注册入口校验（契约变更）

**起因**：用户提供的参考链接 `https://redfox.hk/apis/gongzhonghao/5Y84NI1D` 经活体实测，
其 `5Y84NI1D` 是 RedFox 文档的 `interfaceNo`（对应 `searchUser` 接口），**不是账号标识**。
旧实现取 URL 路径末段当 `biz`，会把 `5Y84NI1D` 落库成一个**永不可采**的源——
之后整号采集 100% 静默失败，而前端列表看起来一切正常。这是「垃圾进、静默败」的典型形态，
比报错更危险。

| 情形 | 旧行为 | 新行为 |
|---|---|---|
| `biz` 与 `profile_url` 都未提供 | `30004`/404（`ResourceNotFoundError`） | **`10005`/422**（`RequestInvalidError`）：缺输入不是「资源找不到」 |
| `biz` 形态非法（非 M 前缀 Base64） | 直接落库 | **`10005`/422**：`biz 形态非法：须为 M 开头的 Base64 公众号 __biz…` |
| `profile_url` 指向红狐文档深链 | 取路径末段当 biz 落库 | **`10005`/422**：明确拒绝，不猜测 |
| `profile_url` 为 MP 文章短链（`/s/xxx`） | 取路径末段当 biz 落库 | **`10005`/422**：该 URL 本身不含 biz |
| `profile_url` 为 MP 文章长链（`?biz=` / `?__biz=`） | 仅认 `?biz=` | **可注册**（`__biz` 亦受理），锚点正确 |
| 无 `profile_url` | `url` = 拼接的 `redfox.hk/apis/gongzhonghao/{biz}` | **`url` = `""`** |

**形态约束**：`^M[A-Za-z0-9+/]{11,25}={0,2}$`（M 前缀 + Base64，含可选 `=` 填充）。

**为何 `url` 改为留空而不拼接**：`redfox.hk/apis/gongzhonghao/{biz}` 这一路径只接受文档的
`interfaceNo`，把 `biz` 填进去得到的是一个**永不生效**的链接。空串是诚实的「无值」，
拼接值是会误导用户的假数据——本项目对后者零容忍。§七 中「`POST /api/v1/sources` →
201 `{sourceId, biz, name, url}`」的字段形状不变，仅 `url` 的取值域扩展为「可为空串」。

### 10.2 `GET /api/v1/admin/discovery/channels` 追加两字段（契约新增）

§八 已登记的 `channels[]` **追加**两个字段（既有字段不变）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `contractVerifiedAt` | string | 该渠道的**上游契约**（请求体键名、响应字段形状、分页语义、错误码）最后一次活体实测日期；`""` = 从未实测 |
| `verifiedScope` | string | 实测覆盖到的层次。当前 `redfox` 为「契约层（请求体/响应字段/分页/错误码）；**端到端未验证**」 |

**为何这两个字段必须与 `implemented` / `available` 正交**：`available=true` 只说明
「凭据就位、能发请求」，**不说明**「字段形状已被真实响应验证过」。而本项目此前
（R8 之前 42 天）的全部 RedFox 契约都是**从文档推导**的，从未被真实响应验证——
正是这个信息从未进入可查询面，才让错误契约潜伏了 42 天。合并两个布尔会让「能启用」
被误读成「字段形状已确认」，重演同一错误。

### 10.3 `manifest_sync_max_pages` 的语义澄清（仅澄清，无代码改动）

**这是有意的成本闸，不是 bug，须在此处显式声明，否则会被误读为缺陷。**

| 语义 | 说明 |
|---|---|
| 性质 | **回填硬上限**，**不是**稳态页数 |
| 取值 | `DEFAULT_MAX_PAGES = 20` / `manifest_sync_max_pages = 20`，保持不变 |
| 覆盖能力 | 20 页 × 20 篇 = **单号回填上限 400 篇** |
| 超出时 | 回填被截断在 400 篇；超出部分**按天追赶**（稳态每日 +1 页新增量），最终收敛但非即时 |

**稳态成本（R8 增量化之后）**：稳态与空日均为 **1 次调用/号/轮**，不再固定翻满 10 页。
依据是一个不变量——上游清单按发布时间倒序，**未见篇恒构成前缀**，故翻页至「本页出现
任何一条既有行 / 末页 / 空页」即止。1 次/天是信息论下界：不调用就无法知道 `total` 变没变。
首次回填为 `⌈篇数/20⌉` 次（173 篇 = 9 次）。

**为何不再按 `⌈缺口/页⌉ + 1` 无条件缓冲一页**：该公式与本节上表的稳态断言**算术冲突**
（`total=173` 时的空日实际需要 2 次而非 1 次）。改用「未见篇前缀收敛」后两条断言同时成立，
且在 `total` 漏报时仍不漏采（漏报会让整页全为新行 → 自动触发继续翻页）。

**成本可审计**：清单同步日志现输出 `calls=N gap_planned=N pages=N local=N total=N`，
每号每轮的实际上游调用次数是**可查询事实**，不再依赖估算。
