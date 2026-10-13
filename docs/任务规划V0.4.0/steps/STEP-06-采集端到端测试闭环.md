---
id: STEP-06
title: 采集端到端测试闭环 + 夹具纠偏 + 模块覆盖率门
baseline: main@4afaedd
tier: sonnect
size: 中（约 1.5 人日）
---

# STEP-06：采集端到端测试闭环 + 夹具纠偏 + 模块覆盖率门

## 归属
- 所属切片：S6 可演示：一条命令跑通「发现 → 清单 → Diff → Job → 入库」全真链路，每个渠道一条
- 来源需求：M-07、M-08、I-03
- 来源方案：V0.2.0 S9；F-12/F-13

## 目标
`test_e2e_collection.py` 对 RedFox + 4 家付费 + RSS 参数化全绿；采集模块覆盖率门进入 `make` 目标（D-11 后进 CI）。

## 输入
- STEP-02…05 合入
- 样本 fixtures
- evidence/pytest_full_pg_4afaedd.txt（覆盖率基线）

## 输出（新增/修改的文件）
- apps/api/tests/test_e2e_collection.py（新）
- apps/api/tests/test_scheduler.py（`_seed_manifests` 与 :530 READY 资产键）
- apps/api/tests/test_p0_asset_cache.py（URL_A 改 `__biz` + 长链用例）
- scripts/check_module_coverage.py（新，stdlib）
- Makefile（新增 coverage-gate 目标）
- docs/06_validation/evidence/EVD-V2-06/**

## Execution Steps（三级原子任务 → 四级执行步骤）

标记：🔴 先红（失败测试/反证）｜🛠 实现｜✅ 验证｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决。每个原子任务单独可验收。

### S6.1 E2E

#### S6.1.1 🛠

**交付**：`test_e2e_collection.py::test_redfox_round_trip`：MockTransport 回放 redfox 样本 → `IncrementalScheduler.run_once` → `JobWorker.run_once`（真实 `KnowledgeBaseService` + LangBot 桩 + 计数 resolver）⇒ 资产数 = 清单数、资产键匹配 `ARTICLE_KEY_PATTERN`、清单全部 INGESTED、第二轮 0 新 Job

**执行步骤**：
1. [ ] 写用例
2. [ ] 连跑 3 次结果一致

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && for i in 1 2 3; do uv run pytest tests/test_e2e_collection.py -q -k redfox || exit 1; done
```

#### S6.1.2 🛠

**交付**：参数化到 dajiala/justoneapi/tikhub/wellbyte/rss（rss 仅 mp.weixin 链接入库，外链按现行 ALLOWED_HOSTS 计 FAILED/10006，断言之）

**执行步骤**：
1. [ ] 参数化
2. [ ] 全绿

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_e2e_collection.py -q
```

### S6.2 纠偏掩盖缺陷的夹具

#### S6.2.1 🛠

**交付**：`test_scheduler.py::_seed_manifests` 改 32 位 hex external_id + 真实形态 URL；`:530` READY 资产改用 `canonical_article_key(url)`

**执行步骤**：
1. [ ] 改夹具
2. [ ] test_scheduler 全绿

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_scheduler.py -q
```

#### S6.2.2 🛠

**交付**：`test_p0_asset_cache.py::URL_A` 的 `?biz=` 改 `__biz`，增长链两篇用例

**执行步骤**：
1. [ ] 改常量 + 增用例

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_p0_asset_cache.py -q
```

### S6.3 模块覆盖率门

#### S6.3.1 🛠

**交付**：`scripts/check_module_coverage.py`：读 coverage.json，阈值表：`providers/article_sources/*` ≥80、`article_identity` =100、`manifest` ≥94、`kb` ≥86、`subscription` ≥79、`scheduler` ≥76、`job_worker` ≥76（取 4afaedd 实测为地板，只升不降）；`make coverage-gate`

**执行步骤**：
1. [ ] 写脚本 + Makefile
2. [ ] 人为降阈值外数据确认 rc≠0

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests -q --cov=app --cov-report=json:/tmp/cov.json && cd ../.. && python scripts/check_module_coverage.py /tmp/cov.json
```

### S6.4 M1 收口验收

#### S6.4.1 ✅

**交付**：双环境全量 + 四探针复跑 + coverage-gate + evidence-check，汇总入 EVD-V2-06（独立验证者判 PASS/FAIL/UNKNOWN）

**执行步骤**：
1. [ ] 执行
2. [ ] 写 EVD README

**验收命令**：
```bash
make evidence-check && eval "$(bash scripts/test-env.sh env)" && cd apps/api && HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 uv run pytest tests -q | tail -1
```

## 验收标准（独立验证者逐条判 PASS / FAIL / UNKNOWN）
- [ ] E2E 6 个渠道全绿且连跑 3 次一致
- [ ] 四探针全部输出修复后期望
- [ ] `check_module_coverage.py` rc=0
- [ ] 双环境全量 failed=0
- [ ] EVD-V2-06 有独立验证者结论

## 验证命令
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests/test_e2e_collection.py -q && uv run pytest tests -q --cov=app --cov-report=json:/tmp/cov.json | tail -1 && cd ../.. && python scripts/check_module_coverage.py /tmp/cov.json
```

## 证据路径
`docs/06_validation/evidence/EVD-V2-06/`（README 记录：sha、命令、原始输出、PASS/FAIL 结论、验证者）

## 允许修改
- `apps/api/tests/test_e2e_collection.py`
- `apps/api/tests/test_scheduler.py`
- `apps/api/tests/test_p0_asset_cache.py（仅 URL_A 与新增长链用例；STEP-02 已改的键断言不回改）`
- `scripts/check_module_coverage.py`
- `Makefile（仅新增目标）`
- `docs/06_validation/evidence/EVD-V2-06/**`
- `.github/workflows/ci.yml（仅 D-11 授权后接入 coverage-gate）`

## 禁止修改
- `apps/api/app/**`（发现缺陷 ⇒ 回报对应 STEP，不在本步修）
- `packages/contracts/**`（STEP-01 除外）
- `apps/api/alembic/versions/**`（STEP-04/08/09 各自唯一迁移号除外）
- `.github/**`（需 D-11 授权）
- `docker/**`、`deploy/**`
- 任务书未列出的一切路径

## 依赖与阻塞
- Depends on：STEP-04、STEP-05
- Blocks：M1 里程碑、STEP-07、STEP-12
- 阻塞条件（遇到即停）：E2E 暴露 app 缺陷 ⇒ 停，开缺陷回对应 STEP，本步标 blocked

## 建议执行档位
`sonnect`　理由：测试编写为主

## 升级条件
E2E 不稳定（同命令两次结果不同）⇒ 升 opus 查并发/事务边界；另：同一原子任务连续 2 次验收失败 ⇒ 停止改代码，重写任务书 / 升档 / 标 blocked（熔断）。

## 预估规模
中（约 1.5 人日）

## 完成定义（全项目唯一口径）
所有权内 diff 符合本卡 ∧ 验收逐条有结果 ∧ 自动测试可复现 ∧ EVD 可让一周后的人复现 ∧ `make evidence-check` 通过 ∧ 未改冻结契约（STEP-01 除外）∧ 无新增同类错误。

## 回滚
`git revert <sha>`；无数据影响。
