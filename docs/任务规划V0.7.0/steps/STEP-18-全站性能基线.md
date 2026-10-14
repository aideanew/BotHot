# STEP-18 全站性能基线（四条 SLA 首次测量）

| 字段 | 值 |
|---|---|
| 归属-切片 | S-M4 未纳管域补齐 |
| 归属-需求 | **REQ-NF-001**（`product-requirements.md:132`：API<500ms、首 Token<3s、入库<30s、Feed<100ms） |
| 归属-方案 | 04 §4.13、§4.9 B-15；裁决 **D-V3-08**（默认：先建基线，无基线禁止优化） |
| 里程碑 | M4 |
| 档位 | sonnet　理由：测量脚本 + 读数归档。**升级条件**：若测量结果触发架构级优化立项 ⇒ 由人升 opus/fable 另开卡 |
| 规模 | 中（≈1 人日；每步 <2h） |
| 依赖 | Depends on：STEP-00C（CI 可跑）。Blocks：一切「优化」类任务（本轮不存在，属规则性阻塞） |
| 基线 | main@13acacc |
| 剩余原子任务 | 5（👤 1） |

## 目标
四条 SLA 各拿到**首次可复现测量值**（p50/p95，环境固定），并对每个指标完成「降它是否降用户可感耗时」的证明，证明不了的指标下线。

## 输入（实测缺口）
- 仓内只有 `LLM_FIRST_TOKEN_TIMEOUT` 这类**超时保护**，无延迟/吞吐断言（`coverage §3`）
- backlog `TEST-001` 自述缺口①「无『千篇量级』性能用例」
- V0.6.0 STEP-11 只覆盖采集切片（SQL 往返/EXPLAIN/单篇入库），未覆盖 API/首 Token/Feed
- 相关端点：`api/v1/{spaces,hot,chat,jobs,subscriptions}.py`；`feed_service.py:132/150/168`；`Semaphore(3)` 在 `:40,266-273`

## 输出（文件）
`scripts/perf_baseline.py`（新，stdlib + httpx）、`apps/api/tests/test_perf_probe.py`（往返计数类，非 SLA 断言）、`docs/03_solution/design/PERF-baseline-v1.md`、EVD-V3-18

## Execution Steps
1. [ ] 🛠 **S18.0** 固定测量环境并把环境指纹入 EVD：compose 起 PG/Redis、版本、数据集规模（文章数/资产数）、并发数、客户端位置。**无指纹的读数无效**
2. [ ] ✅ **S18.1.1** API p50/p95：选 3 个用户可感读接口（建议 `/spaces`、`/hot` Feed、`/jobs`），n≥50
3. [ ] ✅ **S18.1.2** 首 Token p50/p95（流式 `/chat/ask`），需真实 LLM 凭据或显式标注「用录制回放」
4. [ ] ✅ **S18.1.3** 单篇入库 p50/p95（短链与长链各测一组，覆盖 R0 修复后的路径）
5. [ ] ✅ **S18.1.4** Feed p95
6. [ ] ✅ **S18.2.1** 指标可感性证明：对每个指标做一次对照（人为变慢/变快），确认它移动时用户可感耗时同向移动；**证明不了的指标直接下线**，不留在目标里
7. [ ] 👤 **S18.3.1** 依数字决定是否开优化卡（候选：批量 upsert、`status` 索引、`jobs.subscription_id` 列）；决定与理由入 decision-log
8. [ ] 📄 **S18.3.2** 基线写入 04 §4.9 B-15，替换「尚无基线」

## 验收标准
- [ ] 四条 SLA 各有 p50/p95 数字 + 环境指纹 + 可复跑命令
- [ ] 每个指标有「可感性证明」结论（通过 / 下线），无第三条模糊态
- [ ] 复跑同命令在同城同环境偏差 ≤15%（否则测量无效，需说明抖动来源）
- [ ] `PERF-baseline-v1.md` 明确写出**前提与局限**（数据集规模、单机、无网络抖动建模）
- [ ] 本卡**未引入任何优化改动**（`git diff` 只命中 scripts/ 与 docs/ 与新增只读用例）

## 验证命令
```bash
cd apps/api
.venv/bin/python ../../scripts/perf_baseline.py --report p50,p95 --n 50 --out ../../docs/06_validation/evidence/EVD-V3-18/
.venv/bin/python -m pytest tests/test_perf_probe.py -q -rs          # 往返计数，非 SLA 断言
curl -s localhost:3300/metrics | grep -E 'http_request_duration|summary' | head
git diff --name-only HEAD | grep -E '^apps/api/app/' | wc -l          # 期望 0
```

## 证据路径
`docs/06_validation/evidence/EVD-V3-18/`

## 允许修改
`scripts/perf_baseline.py`、`apps/api/tests/test_perf_probe.py`、`docs/03_solution/design/PERF-*.md`、EVD-V3-18
## 禁止修改
`app/**`（本卡只测不改）、`alembic/**`（**不得为性能预加索引**，03 §5 索引表里 R0/04 之外的索引一律待 👤 决策）、`docker/compose.yml`（资源规格变更需上报）、`.github/**`

## 依赖与阻塞
- Depends on：STEP-00C　Blocks：所有优化类任务（规则性）
- 阻塞条件：① 拿不到真实 LLM 凭据 ⇒ 首 Token 标 `NOT_MEASURED` 并说明，不得用超时值冒充延迟；② 数据集太小使数字无意义 ⇒ 停下造数方案再测；③ 与 STEP-11 指标重叠 ⇒ 二者共用一套环境指纹，否则数字不可比
