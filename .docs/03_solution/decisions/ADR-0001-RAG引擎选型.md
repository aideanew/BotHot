# ADR-0001：RAG 引擎选型——LangBot KnowledgeEngine（LangRAG）为主引擎

> 状态：已采纳 | 日期：2026-09-04 | 依据：M0 能力实证总报告（T0.4/T0.5/T0.6）
> 决策级：架构核心（对应开发计划 D3）

## 背景与决策驱动

AideanBot 需要 RAG 引擎承担知识空间的向量化存储与检索。候选：
- **A. LangBot KnowledgeEngine 插件体系**（langbot-team/LangRAG v0.1.9，宿主 Chroma 基础设施）
- **B. 自建 RAG 管道**（PostgreSQL + pgvector + 自主 chunk/embed/rerank）

## 决策

**采用 A：LangBot LangRAG 为主引擎。** AideanBot 通过 LangBot HTTP API（`lbk_` API Key / JWT）驱动建库/入库/检索；不 fork LangBot，不深入其核心。

## 实证依据（2026-09-04）

| 验证点 | 结果 |
|---|---|
| 引擎安装与清单 | PASS（市场插件，caps: doc_ingestion/doc_parsing） |
| 建库→上传→ingest→retrieve 全链 API | PASS（异步 task + status=completed） |
| 多知识库隔离 | PASS（每 KB 独立 Chroma collection，内容归属法零泄漏） |
| OpenAI 兼容嵌入协议替换 | PASS（伪嵌入服务器验证协议面；生产可替换任意兼容端点） |
| 检索模式 | vector / full_text / hybrid + 查询改写（HyDE/Multi-Query/Step-Back）插件自带 |

## 映射模型

```
KnowledgeSpace(AideanBot) ──1:1──> LangBot KB(uuid) ──1:1──> Chroma collection(物理隔离)
ContentAsset ──Markdown文件──> /files/documents 上传 → KB ingest
用户提问 ──按 space 定位 KB uuid──> /retrieve API → 片段
```

## 已知限制与约定

1. **嵌入模型必填**：建库须 `embedding_model_uuid`；ingest 强制嵌入（每批 embed+upsert）。嵌入服务由 AideanBot 侧指定（OpenAI 兼容协议端点）。
2. **检索无阈值**：top_k 恒返回库内最近邻——引用溯源与相似度阈值过滤在 AideanBot 编排层做。
3. **遗留验证（M1 T1.10/T1.8）**：pipeline 按会话路由 KB 的对话级集成；若不满足 → R2 回退（AideanBot 亲调 retrieve + 亲调 LLM），retrieve API 层隔离已实证支撑该回退。
4. **运维耦合**：LangBot 升级可能变更 API——providers/langbot 客户端（防腐层）+ 契约测试覆盖。

## 否决理由（B 自建）

- 重复实现 chunk/embed/upsert/检索（LangRAG 已含 parent-child/QA 索引、hybrid 检索、查询改写）
- 与 D2（LangBot 为机器人运行时）割裂：机器人问答与知识管理需两套检索语义
- 实证成本：A 方案全链一天内跑通；B 方案需自建全部管线

## 影响

- M1 T1.8（LangBot KB 网关）、T1.9（单篇建库编排）按此实现
- 数据模型：`knowledge_spaces.langbot_kb_uuid` 为映射锚点；`knowledge_documents` 记录 asset↔KB 文件映射与状态（FETCHED→INDEXED→READY）
