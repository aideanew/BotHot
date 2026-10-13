---
id: STEP-05
title: 采集静默告警与可观测（“数据黑洞+静默”不再发生）
baseline: main@4afaedd
tier: sonnect
size: 小（约 0.5–1 人日；面板另 0.5）
---

# STEP-05：采集静默告警与可观测（“数据黑洞+静默”不再发生）

## 归属
- 所属切片：S5 可演示：一页清单全部被跳过时，运维在日志、指标、告警三处同时可见；管理端可看渠道最近成功/错误（COULD）
- 来源需求：M-05；C-03
- 来源方案：03 §5 Events；EVD-V2-00 §6.3（定级依据=静默）

## 目标
`skipped == rows > 0` 的页触发 ERROR 日志 + `bothot_discovery_all_skipped_pages_total` +1 + 告警（同幂等键一天一次）。

## 输入
- app/contracts/collection.py（CollectionEvent、ManifestSyncReport）
- app/core/metrics.py、app/core/alerting.py（现有告警入口，只调用不修改）
- STEP-04 合入（manifest.py 写权释放）

## 输出（新增/修改的文件）
- apps/api/app/services/manifest.py（仅 sync_source 循环内事件发射）
- apps/api/app/core/metrics.py（新增 3 个指标）
- apps/api/tests/test_discovery_silence_alert.py（新）
- （COULD）apps/api/app/providers/discovery/registry.py describe_channels 增 lastSuccessAt/lastError；apps/web 管理端只读面板 + vitest

## Execution Steps（三级原子任务 → 四级执行步骤）

标记：🔴 先红（失败测试/反证）｜🛠 实现｜✅ 验证｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决。每个原子任务单独可验收。

### S5.1 先红

#### S5.1.1 🔴

**交付**：`test_discovery_silence_alert.py`：provider 返回 3 行且全无 id/url ⇒ 断言 caplog 有 1 条 ERROR（含 source_id/channel，不含凭据）、指标 +1、告警桩被调 1 次；同日再跑一次 ⇒ 告警不再调用

**执行步骤**：
1. [ ] 写用例（改前红）

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_discovery_silence_alert.py -q
```

### S5.2 实现

#### S5.2.1 🛠

**交付**：metrics.py 增 `bothot_discovery_calls_total{channel,outcome}`、`bothot_manifest_rows_total{channel,result}`、`bothot_discovery_all_skipped_pages_total{channel}`

**执行步骤**：
1. [ ] 实现
2. [ ] /metrics 输出含新名

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests -q -k metrics
```

#### S5.2.2 🛠

**交付**：sync_source 每页结束判定 all-skipped ⇒ 发 `discovery.page_all_skipped`（日志+指标+告警，幂等键 `{source_id}:{channel}:{yyyymmdd}:{page}`）；`id_fallback>0` ⇒ WARNING

**执行步骤**：
1. [ ] 实现
2. [ ] S5.1.1 转绿

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_discovery_silence_alert.py tests/test_manifest_sync.py -q
```

### S5.3 （COULD）管理端可见

#### S5.3.1 🛠

**交付**：`describe_channels` 增 `lastSuccessAt/lastError`（读心跳/指标，不新建表）；后端用例

**执行步骤**：
1. [ ] 只增字段

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests -q -k discovery_channels
```

#### S5.3.2 🛠

**交付**：前端只读面板，覆盖 03 §6 五态（vitest）

**执行步骤**：
1. [ ] 实现 + vitest

**验收命令**：
```bash
cd apps/web && pnpm vitest run --reporter=dot admin
```

## 验收标准（独立验证者逐条判 PASS / FAIL / UNKNOWN）
- [ ] 全跳过页：ERROR 日志 1 条 + 指标 +1 + 告警 1 次；同日重复不再告警
- [ ] 日志/告警中无凭据（用例断言不含 api_key 值）
- [ ] 全量 failed=0
- [ ] （COULD）面板五态 vitest 绿

## 验证命令
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_discovery_silence_alert.py -q && uv run pytest tests -q | tail -1
```

## 证据路径
`docs/06_validation/evidence/EVD-V2-05/`（README 记录：sha、命令、原始输出、PASS/FAIL 结论、验证者）

## 允许修改
- `apps/api/app/services/manifest.py（仅 sync_source）`
- `apps/api/app/core/metrics.py`
- `apps/api/tests/test_discovery_silence_alert.py`
- `（COULD）apps/api/app/providers/discovery/registry.py（仅 describe_channels）`
- `（COULD）apps/web/app/admin/**/discovery*、apps/web/lib/api/admin*.ts（执行前确认确切文件）`

## 禁止修改
- `subscription.py`、`job_worker.py`、`kb.py`
- 告警文本含凭据或上游原文
- `packages/contracts/**`（STEP-01 除外）
- `apps/api/alembic/versions/**`（STEP-04/08/09 各自唯一迁移号除外）
- `.github/**`（需 D-11 授权）
- `docker/**`、`deploy/**`
- 任务书未列出的一切路径

## 依赖与阻塞
- Depends on：STEP-03（id_fallback 字段）、STEP-04（manifest.py 写权）
- Blocks：STEP-06
- 阻塞条件（遇到即停）：现有告警通道无去重能力且需要新存储 ⇒ 停（新增存储属契约变更）

## 建议执行档位
`sonnect`　理由：指标/日志常规实现

## 升级条件
告警去重需跨进程状态 ⇒ 升 opus 评估（Redis 键空间归 Agent-Data）；另：同一原子任务连续 2 次验收失败 ⇒ 停止改代码，重写任务书 / 升档 / 标 blocked（熔断）。

## 预估规模
小（约 0.5–1 人日；面板另 0.5）

## 完成定义（全项目唯一口径）
所有权内 diff 符合本卡 ∧ 验收逐条有结果 ∧ 自动测试可复现 ∧ EVD 可让一周后的人复现 ∧ `make evidence-check` 通过 ∧ 未改冻结契约（STEP-01 除外）∧ 无新增同类错误。

## 回滚
`git revert <sha>`；无数据影响。
