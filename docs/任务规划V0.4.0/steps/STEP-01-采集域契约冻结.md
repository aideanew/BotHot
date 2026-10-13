---
id: STEP-01
title: 采集域契约冻结（ADR + Pydantic 唯一源 + 生成物 + 契约测试）
baseline: main@4afaedd
tier: opus
size: 中（约 1 人日）
---

# STEP-01：采集域契约冻结（ADR + Pydantic 唯一源 + 生成物 + 契约测试）

## 归属
- 所属切片：S1 契约层（不演示行为；为 S2–S6 解耦并行的前置。按 §5.2「<2h 不单独成刀」原则，本步约 1 人日故独立成刀）
- 来源需求：M-01…M-05 的共同前置；I-02、I-07
- 来源方案：03 全篇；ADR-0008（提议）；D-V2-01、D-V2-02、D-09

## 目标
仓库内存在唯一的采集契约源 `app/contracts/collection.py`，其生成的 JSON Schema 与本包冻结稿语义一致并受 `gen_contracts.py --check` 门禁；错误映射与渠道枚举有测试锚。

## 输入
- contracts/collection.schema.json（冻结稿）
- contracts/errors.collection.json
- scripts/gen_contracts.py
- app/providers/discovery/registry.py（CHANNELS）
- app/core/errors.py
- 裁决记录：D-V2-01、D-V2-02（无裁决 ⇒ 只做 S1.2–S1.4 中与键格式无关的部分）

## 输出（新增/修改的文件）
- docs/03_solution/decisions/adr-0011-canonical-article-key.md
- docs/03_solution/decisions/adr-0012-manifest-asset-alignment.md
- docs/03_solution/decisions/adr-index.md（追加两行）
- apps/api/app/contracts/__init__.py、collection.py（新）
- scripts/gen_contracts.py（扩展 schema 生成 + --check）
- packages/contracts/schemas/collection.schema.json（生成物）
- apps/api/tests/test_collection_contract.py（新）
- apps/api/tests/fixtures/contracts/errors.collection.json（冻结稿拷贝）
- docs/00_governance/glossary.md（追加术语）

## Execution Steps（三级原子任务 → 四级执行步骤）

标记：🔴 先红（失败测试/反证）｜🛠 实现｜✅ 验证｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决。每个原子任务单独可验收。

### S1.1 决策落档

#### S1.1.1 👤📄

**交付**：ADR-0011 canonical article key：记录 D-V2-01 裁决（A/B）、键形、降级顺序、存量策略、反例

**执行步骤**：
1. [ ] 按 02 §4.2 填写
2. [ ] 人签字（裁决人+日期）

**验收命令**：
```bash
test -f docs/03_solution/decisions/adr-0011-canonical-article-key.md && grep -n '状态：已接受' docs/03_solution/decisions/adr-0011-canonical-article-key.md
```

#### S1.1.2 👤📄

**交付**：ADR-0012 manifest↔asset 对齐：记录 D-V2-02（新增 article_key 列 + manifest_id + 状态机迁移表）

**执行步骤**：
1. [ ] 按 03 §8.2 填写迁移号 ab1006c1a

**验收命令**：
```bash
grep -n 'ab1006c1a' docs/03_solution/decisions/adr-0012-manifest-asset-alignment.md
```

### S1.2 Pydantic 唯一源

#### S1.2.1 🛠

**交付**：`app/contracts/collection.py`：`ChannelName`(Literal)、`WorkListRow`(id/url/title 必填，extra='allow')、`ManifestStatus`(StrEnum)+`ALLOWED_TRANSITIONS: dict[ManifestStatus, frozenset]`、`ManifestSyncReport`、`CollectionEvent`、`ARTICLE_KEY_PATTERN`

**执行步骤**：
1. [ ] 逐字段对照冻结稿
2. [ ] 不 import services/providers（无反向依赖）

**验收命令**：
```bash
cd apps/api && uv run python -c 'from app.contracts.collection import WorkListRow, ManifestStatus, ALLOWED_TRANSITIONS; print(len(ALLOWED_TRANSITIONS))'
```

### S1.3 生成物与漂移门禁

#### S1.3.1 🛠

**交付**：扩 `gen_contracts.py`：从 `app.contracts.collection` 生成 `packages/contracts/schemas/collection.schema.json`（`TypeAdapter(...).json_schema()` 汇总到 `$defs`），`--check` 同时比对

**执行步骤**：
1. [ ] 实现生成
2. [ ] 生成后 `--check` rc=0
3. [ ] 手改生成物一个字段后 `--check` rc≠0（反证）

**验收命令**：
```bash
python scripts/gen_contracts.py && python scripts/gen_contracts.py --check
```

#### S1.3.2 ✅

**交付**：语义比对：生成物 vs 冻结稿（required 集合、enum 值、pattern、可空性一致），比对脚本与输出入 EVD-V2-01

**执行步骤**：
1. [ ] 写 stdlib 比对脚本
2. [ ] 输出 diff=0

**验收命令**：
```bash
python docs/06_validation/evidence/EVD-V2-01/compare_schema.py
```

### S1.4 契约测试锚

#### S1.4.1 🔴✅

**交付**：`test_collection_contract.py`：①`set(CHANNELS) == set(get_args(ChannelName))`；②errors.collection.json 每行 code/name/http 与 `ERROR_CODES`/`http_status_for` 一致；③`ALLOWED_TRANSITIONS` 与 ADR-0012 表一致；④`ARTICLE_KEY_PATTERN` 拒绝 `'s'`

**执行步骤**：
1. [ ] 写 4 组断言
2. [ ] 人为改错一处确认红（G-23 变异反证）

**验收命令**：
```bash
cd apps/api && uv run pytest tests/test_collection_contract.py -q
```

#### S1.4.2 📄

**交付**：glossary 追加：文章规范键、清单行、发现渠道、信息源标识、全跳过页

**执行步骤**：
1. [ ] 每词一行定义 + 代码锚

**验收命令**：
```bash
grep -c '文章规范键\|清单行\|全跳过页' docs/00_governance/glossary.md
```

## 验收标准（独立验证者逐条判 PASS / FAIL / UNKNOWN）
- [ ] ADR-0011/0012 状态为已接受且有裁决人签名
- [ ] `gen_contracts.py --check` rc=0，篡改生成物后 rc≠0
- [ ] 生成物与冻结稿语义比对 diff=0
- [ ] `test_collection_contract.py` 全绿且有一次变异反证记录
- [ ] `app/contracts/` 不 import services/providers（`grep -n 'from app.services\|from app.providers' apps/api/app/contracts -r` 为空）

## 验证命令
```bash
python scripts/gen_contracts.py --check && cd apps/api && uv run pytest tests/test_collection_contract.py -q && ! grep -rn 'from app.services\|from app.providers' app/contracts
```

## 证据路径
`docs/06_validation/evidence/EVD-V2-01/`（README 记录：sha、命令、原始输出、PASS/FAIL 结论、验证者）

## 允许修改
- `docs/03_solution/decisions/adr-0011-*.md`
- `docs/03_solution/decisions/adr-0012-*.md`
- `docs/03_solution/decisions/adr-index.md`
- `apps/api/app/contracts/**`
- `scripts/gen_contracts.py`
- `packages/contracts/schemas/**`
- `apps/api/tests/test_collection_contract.py`
- `apps/api/tests/fixtures/contracts/**`
- `docs/00_governance/glossary.md`

## 禁止修改
- `apps/api/app/services/**`、`apps/api/app/providers/**`、`apps/api/app/models/**`（实现归 STEP-02/03/04）
- `packages/contracts/src/**`（实体 DTO 只由 gen_contracts 从 entities.py 生成，本步不动模型）
- `apps/api/alembic/versions/**`（STEP-04/08/09 各自唯一迁移号除外）
- `.github/**`（需 D-11 授权）
- `docker/**`、`deploy/**`
- 任务书未列出的一切路径

## 依赖与阻塞
- Depends on：—（与 STEP-00R 并行）
- Blocks：STEP-02.2、STEP-03、STEP-04
- 阻塞条件（遇到即停）：D-V2-01 未裁 ⇒ `ArticleKey` 只写共同约束（minLength 3、禁止纯 's'），pattern 留 TODO 并标 blocked；不得自选 A/B

## 建议执行档位
`opus`　理由：契约语义与 ADR 属不可逆、跨模块决策

## 升级条件
需要改动已有错误码或实体字段语义 ⇒ 升 fable（推翻冻结契约）并请人批；另：同一原子任务连续 2 次验收失败 ⇒ 停止改代码，重写任务书 / 升档 / 标 blocked（熔断）。

## 预估规模
中（约 1 人日）

## 完成定义（全项目唯一口径）
所有权内 diff 符合本卡 ∧ 验收逐条有结果 ∧ 自动测试可复现 ∧ EVD 可让一周后的人复现 ∧ `make evidence-check` 通过 ∧ 未改冻结契约（STEP-01 除外）∧ 无新增同类错误。

## 回滚
`git revert <sha>`；无数据影响。
