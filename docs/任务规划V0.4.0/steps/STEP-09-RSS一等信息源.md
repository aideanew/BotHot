---
id: STEP-09
title: RSS 一等信息源（条件：D-V2-03）
baseline: main@4afaedd
tier: sonnect
size: 中（约 1 人日）
---

# STEP-09：RSS 一等信息源（条件：D-V2-03）

## 归属
- 所属切片：S9 可演示：用户以 feedUrl 订阅 RSS，公众号镜像源入库、外链只发现不入库且计数可见
- 来源需求：C-01；N-04
- 来源方案：V0.2.0 S5

## 目标
`POST …/subscriptions {type:'rss', feedUrl}` 可用；外链计 `filtered_offsite`；`MalformedUrlError` 为永久失败不重试。

## 输入
- STEP-08 PASS
- D-V2-03 裁决

## 输出（新增/修改的文件）
- apps/api/app/api/v1/subscriptions.py
- apps/api/app/providers/article_sources/rss.py
- apps/api/app/services/job_worker.py（_is_permanent_error）
- apps/api/app/services/kb.py（_resolve_with_retry 不重试 10006）
- （条件）alembic ab1006c3a
- docs/RSS订阅渠道.md
- apps/api/tests/test_rss_subscription.py（新）

## Execution Steps（三级原子任务 → 四级执行步骤）

标记：🔴 先红（失败测试/反证）｜🛠 实现｜✅ 验证｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决。每个原子任务单独可验收。

### S9.1 发现层

#### S9.1.1 🔴🛠

**交付**：订阅 API 支持 `{type:'rss', feedUrl}` → `source_identifiers(kind='feed_url')`；未知标识 ⇒ `DiscoveryFailedError`（不再静默当 URL）

**执行步骤**：
1. [ ] 测试先红
2. [ ] 实现

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_rss_subscription.py -q
```

#### S9.1.2 🛠

**交付**：发现时过滤非 ALLOWED_HOSTS 链接并计 `filtered_offsite`

**执行步骤**：
1. [ ] 实现 + 用例

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_rss_subscription.py -q -k offsite
```

### S9.2 入库层

#### S9.2.1 🔴🛠

**交付**：`_is_permanent_error` 纳入 `MalformedUrlError`；`_resolve_with_retry` 不重试

**执行步骤**：
1. [ ] 测试先红
2. [ ] 实现

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests -q -k permanent
```

#### S9.2.2 📄

**交付**：`docs/RSS订阅渠道.md` 更正：外链预置源标注“仅发现，不入库”

**执行步骤**：
1. [ ] 改文档

**验收命令**：
```bash
grep -n '仅发现' docs/RSS订阅渠道.md
```

## 验收标准（独立验证者逐条判 PASS / FAIL / UNKNOWN）
- [ ] RSS 订阅用例绿
- [ ] 外链不入库且 filtered_offsite 计数正确
- [ ] 10006 不重试
- [ ] 全量 failed=0

## 验证命令
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_rss_subscription.py -q && uv run pytest tests -q | tail -1
```

## 证据路径
`docs/06_validation/evidence/EVD-V2-09/`（README 记录：sha、命令、原始输出、PASS/FAIL 结论、验证者）

## 允许修改
- `apps/api/app/api/v1/subscriptions.py`
- `apps/api/app/providers/article_sources/rss.py`
- `apps/api/app/services/job_worker.py（仅 _is_permanent_error）`
- `apps/api/app/services/kb.py（仅 _resolve_with_retry 异常分类）`
- `apps/api/alembic/versions/ab1006c3a_*.py（仅当需要）`
- `docs/RSS订阅渠道.md`
- `apps/api/tests/test_rss_subscription.py`

## 禁止修改
- 放宽 `ALLOWED_HOSTS`（N-04）
- `packages/contracts/**`（STEP-01 除外）
- `.github/**`（需 D-11 授权）
- `docker/**`、`deploy/**`
- 任务书未列出的一切路径

## 依赖与阻塞
- Depends on：STEP-08；D-V2-03
- Blocks：—
- 阻塞条件（遇到即停）：裁决为“外链入库” ⇒ 停，另立 ADR，不在本步实施

## 建议执行档位
`sonnect`　理由：在已定协议上加一种标识类型

## 升级条件
订阅 API 需破坏性改动 ⇒ 升 opus；另：同一原子任务连续 2 次验收失败 ⇒ 停止改代码，重写任务书 / 升档 / 标 blocked（熔断）。

## 预估规模
中（约 1 人日）

## 完成定义（全项目唯一口径）
所有权内 diff 符合本卡 ∧ 验收逐条有结果 ∧ 自动测试可复现 ∧ EVD 可让一周后的人复现 ∧ `make evidence-check` 通过 ∧ 未改冻结契约（STEP-01 除外）∧ 无新增同类错误。

## 回滚
代码改动 `git revert <sha>`；迁移 `alembic downgrade -1`（仅本卡迁移号）。
