# SPEC-素材资产化与公共知识库（单篇 / 多号组库 / 公共 AI 库）

> 状态：已采纳为后续实现标准 | 日期：2026-09-13 | 归属：`.docs/`
> 上游：`entities.py`（Source/SourceSubscription/ArticleManifest/ContentAsset/KnowledgeDocument/Job）、`ADR-0001`（LangBot 为当前默认引擎）、`ADR-0004`（引擎可插拔后，本 SPEC 的 LangBot KB 均指“当前空间所选引擎的 KB”，默认=内置引擎）
> 目标：单篇采集、多公众号组库、公共 AI 库同构；素材全局缓存可复用，极大减少重复采集。

## 一、需求与范围

### 1.1 三类用户故事（验收口径）

| 编号 | 故事 | 验收标准 |
|---|---|---|
| F1 单篇 | 用户粘贴一篇公众号文章 URL 入库到当前空间 | `POST /spaces/{id}/docs {url}` → `202 taskId="" status INDEXED` → 轮询 `READY` → `SSE meta→delta→done citations` 含标题 |
| F2 多号组库 | 用户订阅 N 个公众号，素材汇入同一知识库 | `POST /spaces/{id}/subscriptions {source_id}` → `Job(sync_account)` → 进度条 → `PARTIAL_SUCCESS` 可单篇重试 → 空间内可问到多号内容 |
| F3 公共库 | 平台有 AI 领域公共库（采自公众号），用户一键引入 | `GET /spaces/public` 见 `AI前沿库` → `POST /spaces/{id}/links {public_space_id}` → 批量 `copy` 后本空间可问，`citations.spaceName` 标注来源 |

### 1.2 非目标（本 SPEC 不做）

- 微信登录态/付费墙突破；Redfox 以外的清单源接入（预留 `Source.type` 扩展）。
- 引用式多库扇出问答（列 M4，见 §六 P3）。

## 二、核心设计（一句话）

> **抓取解析只做一次进 `ContentAsset` 全局缓存；`KnowledgeSpace` 只存 `KnowledgeDocument(asset_id→space_id)` 映射；公共 AI 库就是 `is_public=1` 的系统空间。**

```
Source(biz) 1:N ArticleManifest(article_key) → ContentAsset(source+external 唯一，hash 版本)
  N:M KnowledgeDocument(asset+space 唯一) → KnowledgeSpace → 引擎 KB（ADR-0004）
Job(sync_account) 1:N JobItem（单篇子任务）
```

## 三、数据模型（复用现表 + 2 字段迁移）

现表零改动复用：`sources(uq_source_type_external)`、`source_subscriptions(uq_sub_user_source_space)`、`article_manifests(uq_manifest_source_external)`、`content_assets(uq_asset_source_external)`、`knowledge_documents(uq_doc_asset_space, FETCHED→INDEXED→READY)`、`jobs(idempotency_key)`、`job_items`。

新增迁移（1 个 Alembic 版本）：

```python
KnowledgeSpace.is_public: bool = False       # 公共库标记；公共库 owner 为 system 用户
KnowledgeSpace.owner_type: str = "user|system"
ContentAsset.hit_count: int = 0              # 复用计数（热点与清理依据）
KnowledgeDocument.source: str = "copy|link"  # 默认 copy；link 预留给 M4 扇出
```

纪律：`users.sub` 锚点不变；幂等键不变；余额/tier 不落库（ADR-0002）。

## 四、缓存与去重键（减少重复采集的关键）

| 层 | 键/函数 | 命中行为 |
|---|---|---|
| URL 归一 | `normalize_article_url()` + `is_short_link` 短链反解 | 非法 → `10006`；短链直抓一次得 `biz` |
| 文章判定 | `has_article_anchors`（`js_content`/`activity-name`） | 缺失 → `20001` 非文章页 |
| 资产 | `(source_id, external_id)` | 命中 `READY` 资产 → 微信 `0` 请求，直接 §五 |
| 内容版本 | `content_hash(正文md)` | 变化 → `version+1`，旧 `doc` 标过期，不静默覆盖 |
| 原文 | `raw_uri + content_markdown` | 引擎上传失败可重传，不重抓微信 |
| 质量 | `score_quality ≥ 30` | 未达 → `20003` 前置拦截，不入库 |

UI 约定：命中缓存时提示“命中缓存，秒入库”；`hit_count+1`。

## 五、三入口流程（与引擎解耦：`ensure_kb/upload/retrieve` 走 ADR-0004 端口）

### F1 单篇（已通，小改 P0）

```text
粘贴 URL → resolve/extract/quality → Asset upsert(hit_count+1)
 → Doc(asset,space) → 引擎 upload → READY → SSE
```

### F2 多号组库（新增 P2）

```text
POST /sources {biz|profile_url} → Source
POST /spaces/{id}/subscriptions {source_id, sync_policy}
 → Job(sync_account)+JobItems(Manifest Diff = DISCOVERED − 已有Asset)
 → worker 逐篇走 F1 → Job SUCCEEDED/PARTIAL_SUCCESS
 → GET /jobs/{id} 进度 + POST /jobs/{id}/retry 单篇重试
```

`ArticleManifest` 为 Diff 基准；`SourceSubscription.next_run_at` 做增量。

### F3 公共库拷贝式（默认，新增 P1）

`system` 建 `AI前沿库(is_public=1)` 定时采 N 个 AI 号；用户“选用” = `POST /links` 批量 `copy`（见 §六）。
引用式（`link`/扇出）列 M4，不默认启用。

## 六、分步落地（每步可对照检查）

### P0 资产缓存（约 1 周）

- 改动：`kb.ingest_url` 先查 `ContentAsset` 再抓；`raw_uri` 落对象存储。
- 完成标准：同一 URL 第二次入库微信 `0` 请求，`hit_count=2`；`ruff/mypy/pytest` 全绿（含新增复用单测 3 个）。
- 产出：`kb.py diff` + 复用率日志 + `evidence/p0_asset_cache_*.txt`。

### P1 公共库拷贝式（约 1 周，前置 P0）

- 改动：迁移 `is_public/owner_type` + `GET /spaces/public` + `POST /spaces/{id}/links` 批量 copy + 前端“公共库”分组。
- 完成标准：新用户一键引入 AI 库 50 篇，`202→READY`，`SSE citations.spaceName=AI前沿库`。
- 产出：公共库页面 + 引入按钮 + `evidence/p1_public_*.txt`。

### P2 整号订阅（约 2 周，前置 P0）

- 改动：`SourceSubscription + Manifest Diff + Job/JobItem worker` + 订阅管理页。
- 完成标准：订阅 1 个号，`Job SUCCEEDED/PARTIAL`，进度条 + 单篇重试可用。
- 产出：订阅页 + `evidence/p2_subscription_*.txt`。

### P3 引用式扇出（可选 M4）

- 改动：`chat.py ask {spaceIds[]}` 多 KB 扇出融合（契约 v0.5）。
- 完成标准：不拷贝也能问出公共库内容，`citations` 标注来源空间。
- 产出：契约升级说明 + 融合单测。

## 七、API 增量（v1 下，7 个，`ingest_doc {url}` 不动）

```text
POST /api/v1/sources
GET  /api/v1/sources?type=wechat_oa
POST /api/v1/spaces/{id}/subscriptions
GET  /api/v1/spaces/{id}/subscriptions
POST /api/v1/jobs/{id}/retry
GET  /api/v1/spaces/public
POST /api/v1/spaces/{id}/links
```

错误码复用 `10006/20001/20002/20003/30003`，整号加 `30005 PARTIAL_SUCCESS`（`Job` 级）。

## 八、验收与证据

- 每阶段：门禁（`ruff/mypy/pytest/tsc/vitest`）+ 运行（`202→READY→SSE` 帧级）+ 端口（3333 唯一）+ 清理（探针空间可删，`DELETE 405` 未关单前登记豁免）。
- 证据落 `.workbuddy/evidence/p{0,1,2}_*.txt`，台账登记，不混业务提交批。
