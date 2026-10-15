# STEP-RV R0与16真库验收

> 基线 main@61358c3｜状态：⚪ 未开始

| 字段 | 内容 |
|---|---|
| 1 归属（执行者） | 执行Agent |
| 2 验收者（与执行者分离） | 规划方(Hark)，只输出 PASS/FAIL/UNKNOWN |
| 3 难度 / 里程碑 | 中 / M0 |
| 4 来源 | F-06/F-12/F-13；V0.7.0 STEP-R0、STEP-16 完成定义 |
| 5 目标 | 把 R0/16 从『已实现』升为『已完成』：当前基线真库全量读数 + CI 双绿。 |
| 6 输入 | kb.py 回查路径；core/alerting.py；api/v1/system.py `/ready` |
| 7 输出路径 | docs/任务规划V0.8.0/evidence/61358c3-rv/（读数件） |
| 8 三级任务 | 见下 |
| 9 验收 | 全量 0 failed、skip≤6 且无 PG 类、CI 双绿、三条手测有截图/日志 |
| 10 命令 | `cd apps/api && uv run alembic upgrade head && uv run pytest -q -rs --junitxml=junit.xml` |
| 11 证据 | docs/任务规划V0.8.0/evidence/61358c3-rv/ |
| 12 允许修改 | 仅证据目录；发现缺陷时开新卡，不在本卡改代码 |
| 13 禁止修改 | apps/** |
| 14 依赖 / 阻塞 | 00C / BLOCKING：需 PG+Redis 执行机 |
| 15 档位 | T2 |
| 16 升级条件 / 规模 | 发现回归 ⇒ 记 FAIL，开 STEP-R1，不得就地修 / ≈0.5 人日 |

## 三级任务

### SRV.1 环境
- **SRV.1.1** 起 PG16 + Redis（docker/compose.yml 的 db/redis 服务，端口在 3200-3300 外的内部端口）
- **SRV.1.2** `alembic upgrade head` = ab1005w5b
- **SRV.1.3** 记录 skip 列表，PG 不可达类必须为 0

### SRV.2 R0 验收
- **SRV.2.1** 跑短链二次入库相关用例（kb、asset、collect 端到端），0 failed
- **SRV.2.2** AST 判据：kb.py 无 `Source.url.like` 调用（复用 V0.7.0 AF-S6）
- **SRV.2.3** 真库手测：同一短链入库两次，第二次命中缓存且 asset 数不变

### SRV.3 16 验收
- **SRV.3.1** 默认配置启动，`/ready` 返回告警字段且 enabled=true
- **SRV.3.2** 启动 600s 内不告警；故障持续触发时 1800s 内只告一次
- **SRV.3.3** CI+Security 双绿后在 04 状态表把 R0/16 标 ✅

## V0.9.0 → V0.10.0 本卡变更（基线 main@81cb997）

- **状态：🟡 自动化一半已由 CI 满足**：CI 带 postgres service + skip 门（PG 不可达类 skip 判红、SKIP_BASELINE=6），CI success ⇒「真库全量 0 failed」读数已有（E-ci）。
- 剩余 4 项：SRV.2.3（同一短链二次入库手测）、SRV.3.1（`/ready` 告警字段）、SRV.3.2（600s 宽限 / 1800s 冷却）、SRV.3.3（状态表更新）。它们不再被『依赖机』阻塞，任何能起 compose 的机器即可。
- 由此 D-V5-01：上一轮岔口『先补 0 failed 读数』一支已被 CI 自然满足。

## 裁决已签（V0.11.0 第四节第 2 步 · 2026-10-15 12:04）
| 项 | 变化 |
|---|---|
| D-V6-02 | CI 状态认定放宽到 `gh` CLI **或** GitHub REST 原始响应（run id + conclusion + head_sha 存证）；只抄 run 号不算 ⇒ 本卡 `@ci` 复核项的合格标准由此明确 |
| D-V4-01 | R0/16 的 Done 必须在 ubuntu-latest 上取 run id ⇒ 本版把「CI 半边已满足」从既成事实降格为**待 @ci 复核**，复核前 RV 不得判 Done |
| 验收面 | 本卡 Done 只能由 `@ci` **ubuntu-latest** 判定；`@win` 读数只算开发烟测，`@linux` 为依赖机本地验证 |
| 标签 | 依 D-V6-01，本卡 `@dep` 已全部改写为 `@linux`/`@ci` |
