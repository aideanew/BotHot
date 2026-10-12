---
id: STEP-08
title: 信息源标识与按源路由（P1）
baseline: main@4afaedd
tier: opus
size: 大（约 3 人日）
---

# STEP-08：信息源标识与按源路由（P1）

## 归属
- 所属切片：S8 可演示：同一系统内，只有 biz 的源走 RedFox、有 ghid 的源可走付费渠道；首渠道失败且降级开时自动换下一个
- 来源需求：S-01
- 来源方案：V0.2.0 S4；D-V2-04；03 §8.2 迁移 2

## 目标
`select_channels(settings, identity)` 按「启用∩凭据∩源具备所需标识」返回有序渠道列表，scheduler 按订阅路由。

## 输入
- STEP-06 PASS
- D-V2-04 裁决（未裁 ⇒ 只做 S8.1）
- registry.py、scheduler.py:147

## 输出（新增/修改的文件）
- apps/api/alembic/versions/ab1006c2a_source_identifiers.py
- apps/api/app/models/entities.py（SourceIdentifier）
- packages/contracts/src/**（gen_contracts 生成）
- apps/api/app/services/identifier_resolver.py（新）
- apps/api/app/providers/discovery/registry.py
- apps/api/app/services/scheduler.py
- apps/api/app/providers/article_sources/*（协议升级）
- apps/api/app/services/manifest.py（翻页改 next_cursor/page_size）
- apps/api/tests/test_channel_routing.py、test_identifier_resolver.py（新）

## Execution Steps（三级原子任务 → 四级执行步骤）

标记：🔴 先红（失败测试/反证）｜🛠 实现｜✅ 验证｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决。每个原子任务单独可验收。

### S8.1 数据模型

#### S8.1.1 🗄

**交付**：迁移 `ab1006c2a`（down=`ab1006c1a`）建 `source_identifiers` + SQL 回填 biz

**执行步骤**：
1. [ ] 迁移 + 实体 + 生成 dto

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head
```

### S8.2 标识补全

#### S8.2.1 🔴🛠

**交付**：`identifier_resolver.py`：从直抓 HTML 解析 `gh_` 原始 id（以样本为准），入库成功时写 `ghid`（零额外请求）

**执行步骤**：
1. [ ] 测试先红
2. [ ] 实现

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_identifier_resolver.py -q
```

### S8.3 协议升级

#### S8.3.1 🛠

**交付**：`query_work_list(identity, cursor) -> WorkListPage`，保留旧签名适配器一个版本；5 个 provider 迁移

**执行步骤**：
1. [ ] 实现
2. [ ] STEP-03 契约测试仍绿

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_provider_contract.py -q
```

#### S8.3.2 🛠

**交付**：`ManifestSyncService` 以 `page_size` 判末页、`next_cursor` 翻页

**执行步骤**：
1. [ ] 实现

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_manifest_sync.py -q
```

### S8.4 按源路由

#### S8.4.1 🔴🛠

**交付**：`ChannelSpec.required_identifier/cost_rank`；`select_channels`；scheduler 按订阅取首个，`DiscoveryFailedError` 且 `discovery_fallback_enabled`（默认 False）⇒ 试下一个

**执行步骤**：
1. [ ] 测试：只有 biz ⇒ 不选 dajiala；有 ghid ⇒ 可选；降级开 ⇒ 第二渠道被调 1 次

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_channel_routing.py -q
```

### S8.5 TikHub 端点核实

#### S8.5.1 👤

**交付**：核对 `api.tikhub.io/openapi.json`（U-04），结论写 registry `verified_scope`；不符则 `implemented=False` + reason

**执行步骤**：
1. [ ] 人核

**验收命令**：
```bash
grep -n 'verified_scope' apps/api/app/providers/discovery/registry.py | grep -i tikhub
```

## 验收标准（独立验证者逐条判 PASS / FAIL / UNKNOWN）
- [ ] 迁移往返 + 单头
- [ ] 路由三条用例绿
- [ ] STEP-03 契约测试与 STEP-06 E2E 不回退
- [ ] 全量 failed=0

## 验证命令
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_channel_routing.py tests/test_provider_contract.py tests/test_e2e_collection.py -q
```

## 证据路径
`docs/06_validation/evidence/EVD-V2-08/`（README 记录：sha、命令、原始输出、PASS/FAIL 结论、验证者）

## 允许修改
- `apps/api/alembic/versions/ab1006c2a_source_identifiers.py`
- `apps/api/app/models/entities.py（仅新增 SourceIdentifier）`
- `packages/contracts/src/**（仅生成）`
- `apps/api/app/services/identifier_resolver.py`
- `apps/api/app/providers/discovery/registry.py`
- `apps/api/app/services/scheduler.py`
- `apps/api/app/providers/article_sources/**`
- `apps/api/app/services/manifest.py（仅翻页判定）`
- `apps/api/app/services/kb.py（仅 S8.2.1 写 ghid 的一处调用）`
- `apps/api/tests/test_channel_routing.py`
- `apps/api/tests/test_identifier_resolver.py`

## 禁止修改
- `subscription.py`、`job_worker.py`
- `packages/contracts/**`（STEP-01 除外）
- `.github/**`（需 D-11 授权）
- `docker/**`、`deploy/**`
- 任务书未列出的一切路径

## 依赖与阻塞
- Depends on：STEP-06；D-V2-04
- Blocks：STEP-09
- 阻塞条件（遇到即停）：D-V2-04 未裁 ⇒ 完成 S8.1 后停

## 建议执行档位
`opus`　理由：协议升级跨 5 个 provider + scheduler，属架构变更

## 升级条件
协议升级需破坏 WorkListRow 契约 ⇒ 升 fable；另：同一原子任务连续 2 次验收失败 ⇒ 停止改代码，重写任务书 / 升档 / 标 blocked（熔断）。

## 预估规模
大（约 3 人日）

## 完成定义（全项目唯一口径）
所有权内 diff 符合本卡 ∧ 验收逐条有结果 ∧ 自动测试可复现 ∧ EVD 可让一周后的人复现 ∧ `make evidence-check` 通过 ∧ 未改冻结契约（STEP-01 除外）∧ 无新增同类错误。

## 回滚
代码改动 `git revert <sha>`；迁移 `alembic downgrade -1`（仅本卡迁移号）。
