# EVD-V22-60 · S60.0 探针读数（STEP-60 开工前置，2026-10-28）

> 目录名按**卡面第 11 格原字**取 `EVD-V22-60/`（这张卡是 V0.22.0 写的，交付却落在 V0.23.0 队列里，
> 两处版本号不一致——登记在台账 P-149 第三条，本版不自作主张改名）。
> 结论先放这里：**卡面第 5 格验收 ①「八态 8 passed / 0 skipped」在当前供给下不可达**，
> 且八个态里有**两个在 /chat 上没有任何 DOM 出口**，而补出口要动的文件在 V0.23.0 增量里被明令禁止。
> ⇒ 本卡按卡面 13/14 格**停手交回**，不写代码去凑一个"8 passed"。

---

## 1 探针一：`/ask` 的检索根本不在本进程里，而在 LangBot（三条独立读数同向）

| 读数 | 出处 |
|---|---|
| builtin 引擎分支 `retrieve_call = langbot.retrieve(retrieve_kb_id, question, top_k=…, search_type="vector")` | `apps/api/app/api/v1/chat.py:344`（非 builtin 走 `adapter.retrieve`，`:347`） |
| `langbot.retrieve` 的实现是一次 HTTP 调用：`POST /api/v1/knowledge/bases/{kb_uuid}/retrieve`，缺 `data.results` 就抛 `LangbotApiError` | `apps/api/app/providers/langbot/client.py:198-211` |
| 启动器 `scripts/e2e/run_real_backend.sh` 里 `grep -ci langbot` = **0**，全文也没有 export 任何 LangBot 地址（后端 `config.py:63` 默认 `http://localhost:5300`） | 本机现读命令 `grep -nci "langbot" scripts/e2e/run_real_backend.sh` ⇒ `0` |
| CI 的 `e2e-real` job `services:` 只有 `postgres:16` 与 `redis:7` | `.github/workflows/ci.yml` 该 job 段现读 |
| 同 job 的 `Start real stack` 步里 `/system/health` 的实测载荷：`"deps":{"postgres":"ok","redis":"ok","langbot":"unreachable"}` | run 40643109335 / 40648608511 日志（已入 `EVD-V22-59/s59_5_ci_first_run_readings.txt`、`EVD-V22-59/s59_7_round2_ci_forensics.txt`） |

**这条决定 success 态取不到**：`_context_texts(results)` 为空 ⇒ `chat.py:233-235` 直接
`LangbotApiError("知识库无可回答内容")` ⇒ 线上是 `error` 帧 `code=30002`，**流压根到不了 LLM**。
所以假上游 `fake_llm.py` 无论怎么实现，都不可能让 `success` 这条用例真跑出读数。

顺带否证一条我自己的预设（写下来免得下次又这么想）：卡面 S60.2 计划"设 `EMBEDDING_API_BASE` 指向假上游"
——但**本进程在查询时不做向量化**（那是 LangBot 侧的事），`OpenAICompatEmbeddingClient`
（`app/providers/embedding.py:33/123`）在产品链路上没有调用点（`grep` 只命中 `tests/test_embedding.py`）。
⇒ "给假 embeddings 就能让检索命中"是错的；确定性的等值向量即便被用上也不会改变召回排序。
另有一条**副作用**值得规划方知道：`LLM_API_KEY/EMBEDDING_API_KEY=fake` 会让 reranker 落到同一基址
（`providers/reranker.py:144-145` + `config.py:85` 默认 `rerank_enabled=True`），于是它会去 POST `:3290/v1/rerank`；
404 时 `chat.py:120-123` 安全降级为按 score 降序——不炸，但这是"假上游被偷偷复用到第二条链路"，应当显式记账。

## 2 探针二：入库口只吃 URL，没有正文注入路径 ⇒ 种子要外网可达的公开文章

| 读数 | 出处 |
|---|---|
| `class IngestDocRequest(BaseModel): url: str` —— 只有一个字段 | `apps/api/app/api/v1/spaces.py:362-363` |
| 端点 docstring 明写「body 仅 `{url}`（直传 resolved/extracted 形状延后，见交付报告）」，处理函数是 `svc.ingest_url(space_id, payload.url, owner=user_id)` | `apps/api/app/api/v1/spaces.py:377-392` |
| 链路：`ingest_url` → `_ingest_url_inner` → `_resolve_with_retry` / extractor → `upload_document + trigger_ingest` → `_persist_document` → `set_status("INDEXED")`；就绪判定再读 LangBot `list_kb_files`，`completed → READY` | `apps/api/app/services/…:211/226/354/331-332/539`、`spaces.py:419 → get_doc_ingest_status:637`、`_LB_STATUS_MAP:60-66` 应用于 `:668-670` |
| 可检索的硬条件：`KnowledgeDocument.status == "READY"` 且 `langbot_file_id != ""`（默认值分别是 `"FETCHED"` 与 `""`），另要求 `space.langbot_kb_uuid` 非空 | `apps/api/app/repositories/asset.py:249-256`；`apps/api/app/models/entities.py:221/224/225`；`chat.py:440-442` |
| 唯一"复用正文"的分支 `_reuse_cached_asset` 前提是库里已有 asset | `…:511-520` |

⇒ 卡面 S60.3 那句"种子一条空间 + 一篇文档（走现有 service，不直写表）"要成立，
**必须同时具备**：① 一个能被真实抓取的公开文章 URL，② 运行中的 LangBot（`upload_document` /
`trigger_ingest` / `list_kb_files` 三处调用），③ 已登记的 embedding provider 基址（`services/kb.py:189-210`）。
CI 现在三者都没有，本机更没有 docker。

## 3 探针三：八态里两个态**没有任何 DOM 出口**，而补出口的动作被禁止

现读命令与命中（`grep -rn "forbidden|权限不足|initial" apps/web/components/chat/ apps/web/app/chat/` ⇒ **零命中**）：

| 态 | /chat 上能不能被 Playwright 断言 | 唯一可读文案与出处 |
|---|---|---|
| `loading` | 能 | `正在思考…`（`components/chat/ChatMessageList.tsx:74`） |
| `empty` | 能 | `开始向机器人提问` + `机器人将基于「{空间名}」…`（`:21-33`） |
| `success` | 能（但被探针一挡住） | 正文 `<p>` + `来源文章`（`:63-66/78-93`） |
| `error` | 能 | 错误文案 + `重试`（`:45-62`） |
| `unauthenticated` | 能 | `AUTH REQUIRED` + `尚未登录或会话已过期`（`components/AuthGate.tsx:45-74`） |
| `degraded` | 能（两半） | `引擎暂不可用，请稍后重试或换个空间`（`useSseAsk.ts:125`）/ `响应较慢，仍在生成…`（`ChatMessageList.tsx:67-72`，`role="status"`） |
| `initial` | **不能** | 无专属渲染，只有 Next 路由级 `app/chat/loading.tsx` 的骨架 div（无可读文字） |
| `forbidden` | **不能** | 没有 403/10004 分支——越权空间在 chat 上返的是 **404 + 30004**（`chat.py:431-434`），唯一的 `ForbiddenError`/10004 是"引擎不可用"那一路（`chat.py:438-439`） |

⇒ 命中卡面第 14 格升级条件的原文「八态中某态需后端新错误码才能触发 ⇒ 停，交回」。
而 V0.23.0 增量给 60 的**新增禁止**又写着「不得修改 `apps/web/components/**`、`apps/web/app/**`（UI 归 65）」
⇒ 我既不能给它造一个 DOM，也不能改产品，只能停。

## 4 探针四：一条会被"自证"的判据，先说在前面

增量 5 格新增 ②「枚举取值集合必须等于 8 值，且**与 spec 里原有数组逐值相等**」。
现读 `apps/web/e2e/r19-chat-stream.spec.ts:27-36` 那个 `UX_STATES` 就是手抄数组；
而活体锚 `packages/contracts/src/ux/states.ts` 是 **TS 常量**，`apps/web` 对 `@bothot/contracts`
**全部是 `import type`**（`mock-routes.ts:28`、`mock-contract-map.ts:17`；该包 `exports` 只有类型），
⇒ spec 不能运行时 `import { UX_STATES }`，只能在 Node 侧 `fs` 读那份 `.ts` 再正则抽字面量。
如果 ②' 的"原数组"就是同一个读来的对象，这条永远绿——所以真要开工，交叉基准必须显式落在
**冻结稿 `ux_states.schema.json` 的 `definitions.State.enum`**（只读，且 `_defs_of` 认得 `definitions` 方言），
不能落在 spec 自己身上。

## 5 判定与交回

- 本卡**不写代码**：`fake_llm.py`、种子脚本、8 条用例在任何一条前置没落地的情况下开工，
  交付物只能是"把没测过的态标成通过"——那是队列明令禁止的那类绿。
- 卡面状态保持 `⬜ 未开`（判据「无交付提交」成立），不改成 `⏸`：`⏸` 要求写明 BLOCKING 的 **Q 号**，
  我没有 Q 号可以指（词表禁止自造词，见 `docs/任务规划-索引.md` §3）。
- 交回台账 **P-149**（三条：LangBot/外网文章供给、`initial`+`forbidden` 无 DOM 出口、
  以及卡面第 11 格的 EVD 目录版本号在 V0.22/V0.23 之间不自洽）。
- 队列下一张：**STEP-62**（判词纠真，不依赖 60 的读数）；S62.3 按既有硬约束写
  「保持 `continue-on-error`、`e2e-real` 3 绿计数为 0」，不得写「e2e-real 绿」。
