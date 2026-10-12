---
id: STEP-03
title: 渠道行契约归一（P0-3 零入库 + RFC 822 时间）
baseline: main@4afaedd
tier: sonnect
size: 中（约 1.5 人日）
---

# STEP-03：渠道行契约归一（P0-3 零入库 + RFC 822 时间）

## 归属
- 所属切片：S3 可演示：切换到 dajiala/justoneapi/tikhub/wellbyte/rss 任一渠道，样本清单行全部入库为 DISCOVERED
- 来源需求：M-04、M-07、I-02、I-07
- 来源方案：03 §0 WorkListRow；EVD-V2-00 §6.3；探针 P-1

## 目标
6 份样本经各自 provider `query_work_list` → `_map_row` 全部非 None，`publish_time` 为 aware datetime；4 家付费 provider 覆盖率各 ≥80%。

## 输入
- apps/api/tests/fixtures/provider_payloads/*（7 份样本 + README）
- app/contracts/collection.py（WorkListRow）
- manifest.py:51/96-146
- 4 个 client 文件
- STEP-02.2.2（canonical_article_key，仅 S3.3.3 需要）

## 输出（新增/修改的文件）
- apps/api/app/providers/article_sources/{dajiala,justoneapi,tikhub,wellbyte,rss}.py
- apps/api/app/services/manifest.py（仅 `_parse_time`、`_map_row`、`ManifestSyncReport.id_fallback` 字段）
- apps/api/tests/test_provider_contract.py（新，参数化）
- apps/api/tests/test_rss_provider.py（增 RFC 822 用例）

## Execution Steps（三级原子任务 → 四级执行步骤）

标记：🔴 先红（失败测试/反证）｜🛠 实现｜✅ 验证｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决。每个原子任务单独可验收。

### S3.1 先红：全渠道契约测试

#### S3.1.1 🔴

**交付**：`test_provider_contract.py`：对 `CHANNELS` 中每个 `implemented=True` 的渠道参数化——用 `httpx.MockTransport` 回放对应样本 → `query_work_list` → 每行 `WorkListRow.model_validate` 通过、`_map_row` 非 None、`publish_time` 为 aware；缺样本的渠道直接 FAIL（I-07）

**执行步骤**：
1. [ ] 写参数化测试
2. [ ] 改前期望：dajiala/justoneapi/tikhub/wellbyte 红、redfox 绿、rss 时间断言红

**验收命令**：
```bash
cd apps/api && uv run pytest tests/test_provider_contract.py -q  # 改前 ≥5 failed
```

#### S3.1.2 🔴

**交付**：`test_rss_provider.py` 增：RSS2 `pubDate`=`Mon, 12 Oct 2026 07:00:00 +0000` ⇒ `datetime(2026,10,12,7,0,tzinfo=UTC)`；无时区 RFC 822 ⇒ 按 UTC；非法串 ⇒ None 且不抛

**执行步骤**：
1. [ ] 写 3 条

**验收命令**：
```bash
cd apps/api && uv run pytest tests/test_rss_provider.py -q -k rfc822
```

### S3.2 实现：各 provider 输出 WorkListRow

#### S3.2.1 🛠

**交付**：dajiala：行补 `id`（上游稳定 id 优先，按样本字段；无则 `canonical_article_key(url)`）、`publish_time` 转 aware

**执行步骤**：
1. [ ] 改行构造
2. [ ] S3.1.1[dajiala] 转绿

**验收命令**：
```bash
cd apps/api && uv run pytest tests/test_provider_contract.py -q -k dajiala --cov=app.providers.article_sources.dajiala --cov-fail-under=80
```

#### S3.2.2 🛠

**交付**：justoneapi：同上（`$.data.MsgList.Msg` 层级，样本已固定）

**执行步骤**：
1. [ ] 同上

**验收命令**：
```bash
cd apps/api && uv run pytest tests/test_provider_contract.py -q -k justoneapi --cov=app.providers.article_sources.justoneapi --cov-fail-under=80
```

#### S3.2.3 🛠

**交付**：tikhub：同上（端点核实属 STEP-08.5，本步只按样本）

**执行步骤**：
1. [ ] 同上

**验收命令**：
```bash
cd apps/api && uv run pytest tests/test_provider_contract.py -q -k tikhub --cov=app.providers.article_sources.tikhub --cov-fail-under=80
```

#### S3.2.4 🛠

**交付**：wellbyte：同上

**执行步骤**：
1. [ ] 同上

**验收命令**：
```bash
cd apps/api && uv run pytest tests/test_provider_contract.py -q -k wellbyte --cov=app.providers.article_sources.wellbyte --cov-fail-under=80
```

### S3.3 实现：manifest 侧兼容

#### S3.3.1 🛠

**交付**：`_parse_time`：增 RFC 822 分支（`email.utils.parsedate_to_datetime`），接受 `datetime` 输入；naive 一律按 UTC

**执行步骤**：
1. [ ] 实现
2. [ ] S3.1.2 转绿

**验收命令**：
```bash
cd apps/api && uv run pytest tests/test_rss_provider.py tests/test_manifest_sync.py -q
```

#### S3.3.2 🛠

**交付**：`_map_row` 优先读 `id`（`_ID_KEYS` 保留旧键作兼容）

**执行步骤**：
1. [ ] 实现
2. [ ] S3.1.1 全绿

**验收命令**：
```bash
cd apps/api && uv run pytest tests/test_provider_contract.py -q
```

#### S3.3.3 🛠

**交付**：防御兜底：行缺 id 但有 url ⇒ `external_id = canonical_article_key(url)` 并 `report.id_fallback += 1`（字段名与 ManifestSyncReport 契约一致）

**执行步骤**：
1. [ ] 实现 + 单测（构造缺 id 行）

**验收命令**：
```bash
cd apps/api && uv run pytest tests/test_manifest_sync.py -q -k id_fallback
```

### S3.4 验收

#### S3.4.1 ✅

**交付**：P-1 复跑全部非 None；4 家覆盖率 ≥80%；全量双环境 failed=0；`prove_provider_shapes.py` 仍 FAIL=0

**执行步骤**：
1. [ ] 输出入 EVD-V2-03

**验收命令**：
```bash
python docs/06_validation/evidence/EVD-V2-00/prove_provider_shapes.py && eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests -q --cov=app.providers.article_sources --cov-report=term | grep article_sources
```

## 验收标准（独立验证者逐条判 PASS / FAIL / UNKNOWN）
- [ ] `test_provider_contract.py` 对 6 个渠道全绿，删任一样本即红
- [ ] P-1 五行全部非 None 且 rss 行 publish_time 非 None
- [ ] dajiala/justoneapi/tikhub/wellbyte 覆盖率各 ≥80%
- [ ] `prove_provider_shapes.py` FAIL=0
- [ ] 全量 failed=0

## 验证命令
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_provider_contract.py tests/test_rss_provider.py tests/test_manifest_sync.py -q --cov=app.providers.article_sources --cov-report=term | grep -E 'dajiala|justoneapi|tikhub|wellbyte|passed|failed'
```

## 证据路径
`docs/06_validation/evidence/EVD-V2-03/`（README 记录：sha、命令、原始输出、PASS/FAIL 结论、验证者）

## 允许修改
- `apps/api/app/providers/article_sources/dajiala.py`
- `apps/api/app/providers/article_sources/justoneapi.py`
- `apps/api/app/providers/article_sources/tikhub.py`
- `apps/api/app/providers/article_sources/wellbyte.py`
- `apps/api/app/providers/article_sources/rss.py`
- `apps/api/app/services/manifest.py（仅上述 3 处）`
- `apps/api/tests/test_provider_contract.py`
- `apps/api/tests/test_rss_provider.py`

## 禁止修改
- `manifest.py::sync_source` 循环体与 `_upsert`（STEP-04/05）
- `apps/api/app/services/kb.py`（STEP-02）
- `apps/api/tests/fixtures/provider_payloads/**`（形状锚，改动须先改 prove_provider_shapes 并经 STEP-01 契约审）
- `app/providers/discovery/registry.py`（STEP-08）
- `packages/contracts/**`（STEP-01 除外）
- `apps/api/alembic/versions/**`（STEP-04/08/09 各自唯一迁移号除外）
- `.github/**`（需 D-11 授权）
- `docker/**`、`deploy/**`
- 任务书未列出的一切路径

## 依赖与阻塞
- Depends on：STEP-00R、STEP-01；S3.3.3 另依赖 STEP-02.2.2
- Blocks：STEP-04、STEP-05、STEP-06.2
- 阻塞条件（遇到即停）：样本与真实上游形状不符的证据出现（例如活体返回另一层级）⇒ 停，回报，不得改样本迁就实现

## 建议执行档位
`sonnect`　理由：契约已冻结、样本已入库，属逐 provider 机械实现

## 升级条件
某家上游确无可用 id 且 canonical 兜底与渠道内幂等冲突 ⇒ 升 opus；另：同一原子任务连续 2 次验收失败 ⇒ 停止改代码，重写任务书 / 升档 / 标 blocked（熔断）。

## 预估规模
中（约 1.5 人日）

## 完成定义（全项目唯一口径）
所有权内 diff 符合本卡 ∧ 验收逐条有结果 ∧ 自动测试可复现 ∧ EVD 可让一周后的人复现 ∧ `make evidence-check` 通过 ∧ 未改冻结契约（STEP-01 除外）∧ 无新增同类错误。

## 回滚
`git revert <sha>`；无数据影响。
