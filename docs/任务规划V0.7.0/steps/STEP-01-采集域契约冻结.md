# STEP-01 采集域契约冻结

| 项 | 值 |
|---|---|
| 里程碑 | M1 |
| 档位 | opus |
| 规模 | 中（约 1 人日） |
| 依赖 | STEP-00G（D-V2-01/D-09/D-13/D-V2-02 已生效） |
| 裁决 | D-V2-01、D-09、D-13、D-V2-02 |
| 剩余原子任务 | **10**（👤 2；V0.6.0 为 7，本版 +3：S1.1.0 stranded ADR 归位、S1.2.2 六契约收编唯一源、S1.4.3 IDOR 用例生成） |
| 所有权（写） | W：docs/03_solution/decisions/adr-0011-canonical-article-key.md、adr-0012-manifest-asset-alignment.md（新）；apps/api/app/contracts/collection.py（新）；scripts/gen_contracts.py；packages/contracts/schemas/collection.schema.json（生成）；apps/api/tests/test_collection_contract.py（新）；docs/glossary |
| 基线 | main@a9b194d |

## 1. 目标与可证伪验收
- ADR-0011（键格式）、ADR-0012（对齐）落档并签字/默认生效。
- 采集域契约以 Pydantic 为唯一源，生成 JSON Schema 并纳入 `gen_contracts --check` 漂移门禁。
- 契约测试锚定：键不变量、`WorkListRow` 必填、`ChannelName` 与注册表一致、错误码映射。

## 2. 证据链（现状）
- article_identity.py:13「待 ADR-0011」；docs 下无 ADR-0011。
- **（V0.7.0 本轮实测补）决策台账是分裂的，执行者照旧卡面写会猜**：
  - 活目录 `docs/03_solution/decisions/` 只有 **adr-0001…adr-0007** 七个文件 + `adr-index.md`（索引亦只列到 0007）。
  - **ADR-0008（契约唯一源=后端 Python 代码）、ADR-0009（访客策略）、ADR-0010（连接串外置）只存在于快照目录 `docs/任务规划V0.1.0/03_solution/decisions/`**，既不在活目录、也不在活索引里 ⇒ 本卡 §3 依据的"契约唯一源"规则，其 ADR 对新执行者**不可发现**；而 `docs/06_validation/evidence/EVD-019/README.md` 已在引用 ADR-0009。
  - 文件名约定是**小写** `adr-NNNN-kebab-slug.md`，而历次规划正文一律写成大写 `ADR-0011` ⇒ 直接照抄会产出 `ADR-0011.md` 这种破坏约定的文件名。
  - 编号缺口 0008-0010 已被占用（虽在快照里），**新 ADR 必须从 0013 起**或先做归位；本卡选定「先归位、再续号」，见 S1.1.0。
- 冻结稿 contracts/collection.schema.json（V0.2.1 起未变）。
- registry.py:33-54 渠道表；gen_contracts.py 现只生成 knowledge/subscription/ingest 三个 dto.ts。

## 3. 执行逻辑穿透
Pydantic 模型 → gen_contracts 生成 schema/ts → `--check` 比对工作树；契约测试 import 同一模型做断言 ⇒ 改契约必须同时改模型、生成物、测试，三者在 CI 中互锁。
决策台账必须先单源化：一个 ADR 只有一个活文件路径 + 一条 `adr-index.md` 行；否则 D-09/D-V2-01 的"依据 ADR-xxxx"是无法验证的引用（`check_docs_consistency` 只校验 backlog 的路径与行号，**不校验 ADR 是否存在**，所以这类断链不会自己变红——`docs/任务规划V0.7.0/05` §4 纪律）。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### S1.1 决策落档
- **S1.1.0** 📄 **（V0.7.0 新增，前置）** 把 stranded 的 ADR-0008/0009/0010 从 `docs/任务规划V0.1.0/03_solution/decisions/` 归位到 `docs/03_solution/decisions/`（`git mv` 保留历史），并在 `adr-index.md` 补三行（含 status：0008/0009/0010 均为 proposed）。
  - S1.1.0.1 归位后 `ls docs/03_solution/decisions/adr-*.md | grep -v index | wc -l` = **10**
  - S1.1.0.2 快照目录内**留一份指针说明**（不改写历史结论，只写「本 ADR 已迁至活目录」），避免 V0.1.0 的证据链断裂
  - S1.1.0.3 反证：`grep -c 'ADR-0008' docs/03_solution/decisions/adr-index.md` 归位前 0、归位后 ≥1
- **S1.1.1** 👤📄 ADR-0011（文件名 `adr-0011-canonical-article-key.md`）：键形、host 闸门（D-13）、normalize_url 参数表、短/长链归一、历史兼容、反例（`"s"`）
  - S1.1.1.1 按 03 §2 填写
  - S1.1.1.2 签字或登记默认生效时间
- **S1.1.2** 👤📄 ADR-0012（文件名 `adr-0012-manifest-asset-alignment.md`）：对齐字段、四态状态机、迁移号 ab1006c1a、回填归属 STEP-07

### S1.2 Pydantic 唯一源
- **S1.2.1** 🛠 app/contracts/collection.py：ArticleKey、ChannelName、WorkListRow、ManifestStatus、DiscoveryReport
  - S1.2.1.1 逐字段对照冻结稿
  - S1.2.1.2 不 import services/providers（无反向依赖）
- **S1.2.2** 🛠 **（V0.7.0 新增）六契约收编进唯一源**：`app/contracts/` 下补 `identity.py` / `events.py` / `resources.py` / `api.py` 四个模块，把本包 `contracts/*.schema.json` 里**能被 Pydantic 表达的部分**（字段、枚举、pattern、可空性、默认值）落进 Pydantic；Pydantic 表达不了的三项**故意留在 JSON Schema**并在此注明理由：①`errors.global` 的 `frontendSurface`（前端呈现面，后端无此概念）②`ux_states` 的八态与界面绑定 ③`api.envelope#/x-pagination` 的目标壳与存量双壳兼容表。
  - S1.2.2.1 契约文件名与类名一一对应，禁止同一字段既在 JSON Schema 手写又在 Pydantic 出现（双源即违规，03 §3 唯一源纪律）
  - S1.2.2.2 ✅ 收编后跑「生成物 vs 冻结稿」逐字段比对，**已收编项** diff=0，**未收编项**必须在 JSON Schema 里带 `x-not-in-single-source` 标记，比对脚本据该标记跳过——否则"跳过"没有凭据，等于静默放行
  - S1.2.2.3 反证：把 `ArticleKey` 的 pattern 在 Pydantic 与 JSON Schema 改成一个不同值 ⇒ 比对必须红

### S1.3 生成物与漂移门禁
- **S1.3.1** 🛠 扩 gen_contracts.py 生成 collection.schema.json（及需要的 ts 类型）
  - S1.3.1.1 生成后 `--check` rc=0
  - S1.3.1.2 手改生成物一字段 ⇒ `--check` rc≠0（反证）
- **S1.3.2** ✅ 语义比对：生成物 vs 冻结稿（required、enum、pattern、可空性）diff=0，比对输出入 EVD-V2-01

### S1.4 契约测试锚
- **S1.4.1** 🔴✅ test_collection_contract.py：键正则与不变量、WorkListRow 必填、ChannelName == registry.CHANNELS.keys()、错误码映射
  - S1.4.1.1 改错一处确认红（变异反证）
- **S1.4.2** 📄 glossary 增：文章规范键、清单行、发现渠道、信息源标识、全跳过页（每词一行定义 + 代码锚）
  - S1.4.2.1 **（V0.7.0 状态）** 五条已由规划会话写入 `docs/00_governance/glossary.md`（见 `07-执行过程记录.md`），执行者只需**核代码锚是否仍对**并补 `幂等键/收件人可见性/stale` 三条，不必重写已有行
- **S1.4.3** 🔴✅ **（V0.7.0 新增）越权（IDOR）用例生成**：对 `identity.schema.json#/x-idor-checklist` 列出的每一类 `{space_id}/{job_id}/{doc_id}` 路径端点，参数化生成「A 用户访问 B 用户同一 id」用例
  - S1.4.3.1 期望：404(30001/30004) 或 403(10004)，**禁止**返回他人数据；返回数据即为缺陷并单独立卡
  - S1.4.3.2 端点清单由脚本从路由表枚举生成，不得手写（手写必漏，漏=「已测」假象）
  - S1.4.3.3 反证：临时移除属主校验 ⇒ 至少一条用例必须红；全绿说明生成器没抓到端点

## 5. 测试设计
- test_collection_contract.py（约 12 条，纯函数）。

## 6. 停止条件与回滚
- D-V2-01 被推翻为 B：只改 S1.1.1/S1.2.1 的正则与 03 §2，其余不变。

## 7. 交付证据
EVD-V2-01：ADR 签字状态、`--check` 正反读数、语义比对 diff。

## 8. 完成定义（本卡）
所有权内 diff 与任务一致 ∧ 每个 ✅ 有读数 ∧ 本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 通过 ∧ 推送后 CI 与 Security 均 success（run id 入 EVD）∧ 复审 ≤2 轮（D-14）。
