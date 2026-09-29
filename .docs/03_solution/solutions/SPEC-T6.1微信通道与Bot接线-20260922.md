# SPEC-T6.1：微信通道与 LangBot Bot 接线——拓扑偏差裁定与重新立项建议

> 状态：**v0.1 DRAFT，待管理者 APPROVE** | 日期：2026-09-22 | 归属域：A（docs）
> 任务锚：`剩余任务原子化执行大纲` T6.1「LangBot HTTP Bot 接线进 T1.10（HMAC 已活体实测 A-T9）」，证据锚 ADR-0002 附录 A。
> 纪律：**起草 ≠ 实施**。本 SPEC 提交后零代码改动；§四 的 ADR 修订记录**仅为草案块，未写入 ADR-0002**。
> 同级参照：SPEC-T4.3（T4.3）、SPEC-M3（T5.0a）同为 DRAFT 待批。三者共同结论——**任务标题所预设的实现路径，经代码核验后均不成立**。

## 〇、立项前提质疑（本 SPEC 的核心产出）

T6.1 的标题是「LangBot HTTP Bot 接线」，其隐含前提是：**AideanBot 应当调用 LangBot 的 HTTP Bot `/bots/<uuid>/sync`，而目前还没接上**。

**代码核验结论：这条路径从来不存在，且是被主动否决的，不是遗漏。**

当前实现对话流走 ADR-0002 增补一 的**兜底 R2**（「AideanBot 亲调 retrieve + 亲调 LLM，LangBot 退化为 KB 引擎」），且该选择**经 A 批复 2026-09-08**（`chat.py:232` docstring 原文）。ADR-0002 附录 A 的 HMAC 签名契约虽已活体实测（A-T9 四态矩阵），但**从未被接线**——backend 全仓 `hmac`/`X-LB-Timestamp`/`signature` 零命中。

因此 T6.1 的真正工作不是「接线」，而是**裁定并回写一处文档真源冲突**。

## 一、代码实际拓扑（证据锚，全部实读）

```text
用户 → AideanBot POST /api/v1/chat（SSE）
  ├─ retrieve：EngineRouter.available(space.engine) → builtin 走 langbot.retrieve(kb, q, top_k, search_type="vector")
  │            非 builtin 走 adapter.retrieve()（骨架位恒不可用）
  ├─ 可选 rerank：RerankerPort
  ├─ 生成：http.stream("POST", {llm_api_base}/chat/completions, stream=True, Bearer llm_api_key)
  └─ citations：AideanBot 本地组装 {title, spaceName, engine}
```

| 断言 | 证据 |
|---|---|
| retrieve 由 AideanBot 发起 | `chat.py:337-358`：`router.available(engine)` 判 → builtin `langbot.retrieve(...)` / 非 builtin `adapter.retrieve(...)` |
| LLM 由 AideanBot 直连 | `chat.py:247-257`：`http.stream("POST", f"{settings.llm_api_base.rstrip('/')}/chat/completions", json={model, messages, stream:True}, headers={"Authorization": Bearer})` |
| 该选择是被批复的，非临时兜底 | `chat.py:232` docstring 原文：「OpenAI 兼容直连流式生成（**B-T10R 方案 A，A 批复 2026-09-08**）」 |
| AideanBot 自持全部对话增值能力 | `chat.py` 内实现：citations 组装（:184-204，含 `engine` 字段）、rerank（:113）、意图驱动检索宽度（:347）、ping 保活（:362-367）、首 token/流空闲超时判死（:279-286）、断连即收敛（:269） |
| HMAC 签名代码零存在 | backend `app/` 全仓 `grep hmac \| X-LB-Timestamp \| sha256=` → **0 命中** |
| LangBot 客户端无 bot/pipeline 方法 | `providers/langbot/client.py` 方法集：`list_engines / list_embedding_models / register_provider / register_embedding_model / create_kb / upload_document / trigger_ingest / list_kb_files / delete_kb_file / delete_kb / retrieve`——**无 `/bots`、无 `/pipelines`、无 `/sync`** |
| `BotBinding` 是死表 | `entities.py:211-224` 定义；全仓 `grep BotBinding\|bot_bindings` 仅命中 `entities.py`、`models/__init__.py`、初始迁移 `05a5a856c37b`——**零消费者**（无 service、无 repo、无 router） |

## 二、文档真源冲突（本 SPEC 的正式登记项）

《文档索引》口径：「实现与文档冲突时**以可运行代码为准并回写**」。此处冲突成立：

| 位置 | 表述 | 与代码关系 |
|---|---|---|
| **ADR-0002 §决策一** 拓扑图 | 「普通消息 → LangBot HTTP Bot `/bots/<uuid>/sync`（pipeline+RAG）→ 同步取回复 → 转发用户」 | **与实现相反** |
| ADR-0002 增补一 三级降级链 | 方案 A（每空间一组 bot+pipeline）→ 方案 B（插件改写）→ **R2（亲调 retrieve + 亲调 LLM）**，并注明 R2 风险「丢失 pipeline 会话/工具/引用能力」 | 实现即 R2；且 R2 的三项「丢失能力」中，**引用能力已由 AideanBot 本地重建**（`chat.py:184-204` citations 含 engine） |
| ADR-0002 附录 A | 「前置验证①已完成，方案 A 无阻塞」+「对 T1.10 的实现口径（交 B）」 | 前置验证已完成，**但方案 A 从未被采纳为实现**；附录 A 的「交 B」口径未闭环 |

### 2.1 一处命名隐患（须一并消解）

`chat.py:232` 的「**B-T10R 方案 A**」与 ADR-0002 增补一的「**方案 A**」是两个不同概念的同名标签：

- ADR-0002 方案 A = 每 KnowledgeSpace 一组 LangBot bot+pipeline；
- chat.py 方案 A = OpenAI 兼容直连流式生成（A 批复 2026-09-08）。

两个「方案 A」指向相反的实现方向，且后者是当前真实实现。**任何后续读者据此判断都会误读**——这是本 SPEC 要求修正的第二个原因。

## 三、路径比选

### 路径 A：按原标题接线 HTTP Bot（即 ADR-0002 增补一 方案 A）

- 做法：backend 建 HMAC 签名模块（`signing_string = "{ts}.{raw_body_bytes}"`、`sha256=` 前缀、300s 重放窗），实现 `POST /bots/<uuid>/sync` 调用；AideanBot 经 `/api/v1/platform/bots` + `/pipelines` 编程创建并维护 空间↔bot_uuid 映射；`session_id` 承载 ADR-0003 空间解析结果。
- 收益：获得 LangBot pipeline 的**会话记忆 + 工具调用**能力（ADR-0002 已注明 R2 的丢失项）。
- 代价：
  1. **重复建设**——AideanBot 已自持 citations/rerank/意图路由/超时/断连/ping 六项对话能力，切到 pipeline 后这些能力由 LangBot 侧接管，须**逐项对等移植或接受降级**；
  2. **`citations.engine` 语义再变**——检索归属目前由 AideanBot 显式控制（这也是 T4.3 否决「伪引擎壳」的同一条约束）；改由 pipeline 产出后，多引擎归属的控制点转移；
  3. **N 空间 = N pipeline**——ADR-0002 自评为「M1 用户量=1、空间个位数，可承受」，但该判断在 T2 整号闭环（≥100 篇/空间）落地后需重估；
  4. **纯后端返工**，前端零收益（前端只消费 SSE 事件流）。
- 结论：**暂缓**——需管理者明确「是否需要 pipeline 的会话/工具能力」这一产品诉求，非工程判断可裁。

### 路径 B：回写 ADR-0002，把 R2 记为已采纳拓扑（推荐）

- 动作：**纯文档**。新增 ADR-0002 v1.2 修订记录（草案见 §四），并消解 §2.1 命名隐患。
- 效果：文档真源恢复一致；T6.1 从「施工项」转为「已闭环」；HMAC 签名模块不建（避免死代码——`EngineRouter` 的立法先例正是 `engine_port.py:210`「杜绝伪 available」，其对称要求是**不为永不使用的路径保留代码**）。
- 结论：**采纳**。

### 路径 C：两者并行（先接线 A，后回写文档）

同时付 A 的返工成本与文档成本，且 A 的必要性未定。**否决。**

### 3.1 比选矩阵

| 维度 | 路径 A（接线） | 路径 B（回写） |
|---|---|---|
| 代码改动 | HMAC 模块 + bot/pipeline 管理 + 映射存储 | **零** |
| 解决文档冲突 | 否（使实现迁就文档） | **是** |
| 消除命名隐患 | 否 | **是** |
| 获得 pipeline 会话/工具 | 是 | 否 |
| 重复建设风险 | 高（六项能力须对等移植） | 无 |
| 外部依赖 | LangBot 侧 bot/pipeline 编程 API | 无 |
| 依赖未定产品诉求 | **是**（是否要 pipeline 能力） | 否 |
| **结论** | 暂缓（待 Q1） | **采纳** |

## 四、ADR-0002 v1.2 修订记录（**草案块，未写入 ADR**）

> 以下为本 SPEC 建议追加至 ADR-0002 的内容。**须管理者 APPROVE 后方可写入 ADR-0002**——ADR 属已采纳架构决策，本会话不自行改动。

```markdown
## 修订记录 v1.2（2026-09-22，拓扑偏差回写，依据 SPEC-T6.1）

> 触发：SPEC-T6.1 代码核验发现本 ADR §决策一 拓扑图与实现相反。依据《文档索引》
> 「实现与文档冲突时以可运行代码为准并回写」，本节回写；**不推翻 ADR 骨架**。

### 增补四：对话生成路径裁定 = R2 已采纳为正式拓扑

- §决策一 拓扑图中「普通消息 → LangBot HTTP Bot `/bots/<uuid>/sync`」为**决策时设想，
  未采纳为实现**。实际实现为增补一 降级链的 **R2**（AideanBot 亲调 retrieve + 亲调 LLM）。
- 采纳依据：`chat.py` `_llm_stream` docstring「OpenAI 兼容直连流式生成（B-T10R 方案 A，
  **A 批复 2026-09-08**）」——该选择经批复，非临时兜底。
- 增补一 对 R2 标注的风险「丢失 pipeline 会话/工具/引用能力」，**引用能力已失效**：
  AideanBot 已本地重建 citations（`{title, spaceName, engine}` 三元，chat.py:184-204），
  且额外持有 rerank / 意图驱动检索宽度 / ping 保活 / 首 token 与流空闲超时 / 断连即收敛
  共六项对话增值能力，控制点在本系统侧。
- **保留未采纳项**：pipeline 的**会话记忆 + 工具调用**能力。若产品侧确认需要，按增补一
  方案 A 重启（前置验证① HMAC 契约仍有效，见附录 A 四态实测矩阵）。

### 命名消解

- 本 ADR 增补一 的「方案 A」= 每 KnowledgeSpace 一组 LangBot bot+pipeline。
- `chat.py` 的「B-T10R 方案 A」= OpenAI 兼容直连流式生成。**二者无关**。
- 后续文档引用 LangBot pipeline 路径一律写作「增补一 方案 A」，不得简写为「方案 A」。

### 附录 A 状态更新

前置验证①（HMAC 签名契约）实测结论不变、**仍然有效**；但其下游用途由「T1.10 出站接线」
改为「方案 A 重启时的前置资产」。**backend 不保留 HMAC 签名代码**（无消费者；与
engine_port.py:210「杜绝伪 available」的对称要求一致：不为永不使用的路径保留代码）。
```

## 五、通道与推送接口预留登记（T6.2 / T6.3 的真身）

去掉 T6.1 的接线诉求后，T6 轨道剩余两项的真实依赖如下：

| 项 | 真实内容 | 依赖 | 施工半程可否脱机 |
|---|---|---|---|
| **T6.2 主动推送触发入口** | 并入 M3 板块⑤，落 README 目标 3「后台控制主动发送」。需 outbound 推送通道 + 触发端点 | **微信凭据**（推送需已绑定的用户号） | 接口与 `BotBinding` 消费方**可脱机建**，但推送半程必活体 |
| **T6.3 clawbot 通道** | 用户绑定号模式（ADR-0002 增补二：与 openclaw-weixin 机器人号模式**语义不同，不可混同**） | **微信凭据** | `BotBinding` 消费方 + 通道 provider 注册表可脱机建；`channel` 已是 `String(32)`，新增通道值**零迁移** |

**接口预留依据（零迁移）**：`BotBinding.channel` 已为 `String(32)`（`entities.py:220`），`uq_binding_channel_external = UniqueConstraint("channel","external_user_id")`（:224）**已按 channel 分域建键**——新增通道值不需 Alembic 版本，与 SPEC-T4.3 的采集源结论同构。

**但**：`BotBinding` 当前是**死表**（零消费者）。若 M3 批次 1 不打算碰通道，则**连表消费方也不建**——避免制造第二个 `ENGINE_IMPLEMENTED=False` 式伪可用位。

## 六、外部锁与不排产声明

- **微信凭据（既有锁，本 SPEC 收窄其语义）**：同时锁 T6.1 残项、T6.2、T6.3 三者的**活体半程**。
- **D12 pipeline 能力诉求（本 SPEC 新登记的决策锁）**：非技术锁，是**产品诉求未定**——「是否需要 LangBot pipeline 的会话记忆/工具调用」。未裁前**不建 HMAC 签名模块**，§四 的 ADR 回写也不写入。
- 对照锁清单：残锁由 9 项（SPEC-T4.3 §五 的 D11 计入后）增至 **10 项**：D3 / D6 / D10 / RAGFlow Key / R7+PAT 轮换 / LANGBOT_ADMIN_PASSWORD / 微信凭据 / ima 调研 / D11 飞书凭证 / **D12 pipeline 能力诉求**。

## 七、不做清单

1. 不建 HMAC 签名模块（无消费者；`signing_string`/`sha256=`/300s 重放窗等契约仅存于 ADR-0002 附录 A）；
2. 不给 `LangBotClient` 加 `/bots`、`/pipelines`、`/sync` 方法（无消费者）；
3. 不建 `BotBinding` 消费方（service/repo/router）——保持死表原状并如实登记，等 Q1/Q3 裁定；
4. 不写 Alembic 迁移（`channel`/`type` 均已是 `String(32)` 分域建键，零迁移）；
5. **不修改 ADR-0002**——§四 仅为草案块，写入须 APPROVE；
6. 不改 `chat.py` 任何一行（现行 R2 实现是正确的，需被记录的不是被替换）；
7. 不改前端（路径 A/B 均无前端收益）。

## 八、待管理者裁定项（非我方可定）

| # | 待裁 | 建议 |
|---|---|---|
| Q1 | 是否需要 LangBot pipeline 的会话记忆/工具调用能力（D12） | **暂不需要**——AideanBot 已自持六项对话能力，citations 已本地重建；先按路径 B 回写，等真实用户反馈再重启方案 A |
| Q2 | §四 ADR-0002 v1.2 修订记录是否采纳写入 | **采纳**（文档真源必须与代码一致，此为索引口径的强制要求） |
| Q3 | `BotBinding` 死表处置：保留 / 删除 / 本批建消费方 | **保留 + 如实登记**（删除需迁移且有 M2 语义在案；建消费方待微信凭据） |
| Q4 | T6.2 主动推送入口是否并入 M3 批次 3（引擎 Key 之后） | 并入，但**推送半程显式标活体待微信凭据**，不谎报竣工 |

## 九、附带发现：`BotBinding` 死表（自 T1 初始 schema 起）

`05a5a856c37b_v1_initial_schema.py` 已建 `bot_bindings` 表，至今（Alembic head `ab1004t32a`，5 个迁移）**零迁移变更、零代码消费者**。这是本仓第一个「已建表从未接线」的先例，与 `ENGINE_IMPLEMENTED=False` 的骨架位同源——两者共同说明：**本仓存在「先占位后接线」的习惯，而占位本身不产生价值**。

SPEC-T4.3 的结论（不建 `FeishuAdapter` 骨架）与本条先例互相印证。建议把「**占位即价值**」的判断改为：占位仅在**接口形状已被两侧确认**时才有价值，否则应先立项后占位。此条作为流程建议提交，不改任何代码。
