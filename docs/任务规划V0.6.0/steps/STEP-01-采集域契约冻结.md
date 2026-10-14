# STEP-01 采集域契约冻结

| 项 | 值 |
|---|---|
| 里程碑 | M1 |
| 档位 | opus |
| 规模 | 中（约 1 人日） |
| 依赖 | STEP-00G（D-V2-01/D-09/D-13/D-V2-02 已生效） |
| 裁决 | D-V2-01、D-09、D-13、D-V2-02 |
| 剩余原子任务 | 7（👤 2） |
| 所有权（写） | W：docs/03_solution/decisions/adr-0011-canonical-article-key.md、adr-0012-manifest-asset-alignment.md（新）；apps/api/app/contracts/collection.py（新）；scripts/gen_contracts.py；packages/contracts/schemas/collection.schema.json（生成）；apps/api/tests/test_collection_contract.py（新）；docs/glossary |
| 基线 | main@a9b194d |

## 1. 目标与可证伪验收
- ADR-0011（键格式）、ADR-0012（对齐）落档并签字/默认生效。
- 采集域契约以 Pydantic 为唯一源，生成 JSON Schema 并纳入 `gen_contracts --check` 漂移门禁。
- 契约测试锚定：键不变量、`WorkListRow` 必填、`ChannelName` 与注册表一致、错误码映射。

## 2. 证据链（现状）
- article_identity.py:13“待 ADR-0011”；docs 下无 ADR-0011。
- 冻结稿 contracts/collection.schema.json（V0.2.1 起未变）。
- registry.py:33-54 渠道表；gen_contracts.py 现只生成 knowledge/subscription/ingest 三个 dto.ts。

## 3. 执行逻辑穿透
Pydantic 模型 → gen_contracts 生成 schema/ts → `--check` 比对工作树；契约测试 import 同一模型做断言 ⇒ 改契约必须同时改模型、生成物、测试，三者在 CI 中互锁。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红（写失败测试）｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### S1.1 决策落档
- **S1.1.1** 👤📄 ADR-0011：键形、host 闸门（D-13）、normalize_url 参数表、短/长链归一、历史兼容、反例（`"s"`）
  - S1.1.1.1 按 03 §2 填写
  - S1.1.1.2 签字或登记默认生效时间
- **S1.1.2** 👤📄 ADR-0012：对齐字段、四态状态机、迁移号 ab1006c1a、回填归属 STEP-07

### S1.2 Pydantic 唯一源
- **S1.2.1** 🛠 app/contracts/collection.py：ArticleKey、ChannelName、WorkListRow、ManifestStatus、DiscoveryReport
  - S1.2.1.1 逐字段对照冻结稿
  - S1.2.1.2 不 import services/providers（无反向依赖）

### S1.3 生成物与漂移门禁
- **S1.3.1** 🛠 扩 gen_contracts.py 生成 collection.schema.json（及需要的 ts 类型）
  - S1.3.1.1 生成后 `--check` rc=0
  - S1.3.1.2 手改生成物一字段 ⇒ `--check` rc≠0（反证）
- **S1.3.2** ✅ 语义比对：生成物 vs 冻结稿（required、enum、pattern、可空性）diff=0，比对输出入 EVD-V2-01

### S1.4 契约测试锚
- **S1.4.1** 🔴✅ test_collection_contract.py：键正则与不变量、WorkListRow 必填、ChannelName == registry.CHANNELS.keys()、错误码映射
  - S1.4.1.1 改错一处确认红（变异反证）
- **S1.4.2** 📄 glossary 增：文章规范键、清单行、发现渠道、信息源标识、全跳过页（每词一行定义 + 代码锚）

## 5. 测试设计
- test_collection_contract.py（约 12 条，纯函数）。

## 6. 停止条件与回滚
- D-V2-01 被推翻为 B：只改 S1.1.1/S1.2.1 的正则与 03 §2，其余不变。

## 7. 交付证据
EVD-V2-01：ADR 签字状态、`--check` 正反读数、语义比对 diff。

## 8. 完成定义（本卡）
所有权内 diff 与任务一致 ∧ 每个 ✅ 有读数 ∧ 本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 通过 ∧ 推送后 CI 与 Security 均 success（run id 入 EVD）∧ 复审 ≤2 轮（D-14）。
