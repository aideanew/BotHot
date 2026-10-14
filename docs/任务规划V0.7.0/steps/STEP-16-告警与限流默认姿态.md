# STEP-16 告警与限流默认姿态（可观测前置）

| 字段 | 值 |
|---|---|
| 归属-切片 | S-M0.5 治理前置 |
| 归属-需求 | REQ-NF-002（安全/可用性）；**STEP-05 的前置** |
| 归属-方案 | 04 §4.13、`01` F-83/F-84；裁决 D-V3-04、D-V3-05 |
| 里程碑 | M0.5（M0 与 M1 之间，必须早于 STEP-05） |
| 档位 | sonnet　理由：配置默认值 + 一个计数器 + 一条警告，改动面小且判据明确。**升级条件**：若改 `security.py` 限流算法本身（非计数）⇒ opus |
| 规模 | 小（≈0.75 人日） |
| 依赖 | Depends on：STEP-00G（D-V3-04 生效）。Blocks：STEP-05、STEP-14 |
| 基线 | main@13acacc |
| 剩余原子任务 | 6（👤 1） |

## 目标
默认部署下「告警探测器真的在跑」，且「限流在 Redis 缺失时 fail-open」这件事对用户/运维可见——使 STEP-05 的「缺陷一天内可发现」成为可验收命题。

## 输入（实测锚）
- `app/core/alerting.py:107` `if not _flag("ALERTING_ENABLED", default=False)`；`:14` docstring 自述默认关闭
- `docker/compose.yml:196` `- ALERTING_ENABLED=${ALERTING_ENABLED:-false}`；`docker/.env.example:107` `ALERTING_ENABLED=false`
- 唯一调用方：`app/services/push_scheduler.py:88-90`（`run_alert_checks` 由推送调度循环触发）⇒ 调度循环不跑则告警完全不跑
- 三类既有告警：心跳缺失、Job 积压、推送连败（`alerting.py:71/81/87`）
- 限流 fail-open：`app/core/security.py:141-153`、`:205`
- `/ready` 探针：`system.py:133`（检 pg/redis/schema）

## 输出（文件）
`docker/compose.yml`、`docker/.env.example`、`apps/api/app/core/alerting.py`（宽限 + 未启用警告）、`apps/api/app/core/metrics.py`（fail-open 计数）、`apps/api/tests/test_alerting_default.py`（新）、`docs/04_engineering/conventions.md`、EVD-V3-16

## Execution Steps
1. [ ] 🔴 **S16.1.1** `test_alerting_default.py`：默认配置下 `run_alert_checks` 必须实际执行探测（改前返回空 ⇒ 红）。判据写法：断言返回的探测列表长度 ≥3 而非「是否非空」（防恒红）
2. [ ] 🛠 **S16.1.2** `compose.yml:196` 与 `.env.example:107` 改 `ALERTING_ENABLED=true`
   - S16.1.2.1 心跳缺失类加**启动宽限 10 分钟**（`alerting.py` 内以进程启动时刻判定），防部署噪声误报
3. [ ] 🛠 **S16.1.3** `ALERTING_ENABLED=false` 时：`/ready` 响应体加 `alerting:"disabled"` 字段，`make evidence-check` 打印显式警告（不阻断）
4. [ ] ✅ **S16.1.4** 起服务实测：制造一次越阈 ⇒ 告警产生且同日幂等；读数入 EVD（依赖 docker 的执行者）
5. [ ] 🛠 **S16.2.1** `metrics.py` 增 `bothot_ratelimit_failopen_total`；Redis 断开路径计数
6. [ ] 📄 **S16.2.2** `conventions.md` + `errors.global.schema.json`（10007 条目）写明「无 10007 ≠ 未被限流」
7. [ ] 📄 **S16.3.1** STEP-05 卡头加「前置：STEP-16 已合」，并把 B-9 的判据从「面板有数据」改为「默认部署能收到一条真实告警」

## 验收标准
- [ ] 默认 `compose up` 后 `/ready` 显示 alerting 启用；关闭时显示 `disabled` 且证据链有警告输出
- [ ] 越阈告警在默认部署产生，同日重复不再发（幂等）
- [ ] 心跳告警在启动 10 分钟内不误报，超宽限后能报
- [ ] Redis 断开时 `bothot_ratelimit_failopen_total` 增长，且 `/ready` 不因 fail-open 变红
- [ ] 全量连库 0 failed；CI 双绿 run id 入 EVD

## 验证命令
```bash
cd apps/api && .venv/bin/python -m pytest tests/test_alerting_default.py -q -rs
grep -n 'ALERTING_ENABLED' ../docker/compose.yml ../docker/.env.example     # 期望 true
docker compose -f docker/compose.yml up -d api && curl -s localhost:3300/ready | jq .alerting
curl -s localhost:3300/metrics | grep -i ratelimit_failopen
```

## 证据路径
`docs/06_validation/evidence/EVD-V3-16/`

## 允许修改
`docker/compose.yml`、`docker/.env.example`、`app/core/{alerting,metrics}.py`、`app/api/v1/system.py`（仅 `/ready` 响应体增字段）、`apps/api/tests/test_alerting_default.py`、`docs/04_engineering/conventions.md`
## 禁止修改
`app/core/security.py` 的限流算法（本卡只加计数，不改 fail-open 语义——改语义需 D-V3-05 被推翻）、`app/services/push_scheduler.py`、`contracts/**`、`alembic/**`（本卡不占迁移号）

## 依赖与阻塞
- Blocks：STEP-05、STEP-14　Depends on：STEP-00G
- 阻塞条件：① 生产环境已有外部告警通道 ⇒ 双通道重复告警，停下上报；② 宽限实现需要新配置项 ⇒ 走 settings 但不得新增迁移；③ 若 `/ready` 语义变化影响既有探针用例 ⇒ 先补用例再改
