---
id: REQ-C-002
type: requirement
title: 端口分配
status: active
owner: product
实现度: 已实现（按 D-V21-05「文档跟实况」口径，STEP-62 现读 2026-10-29）：端口表拆「本栈发布」/「外部提供」两段（STEP-51 S51.3），常驻用例 `apps/api/tests/test_r19_ports.py` 七条双向（含反证：把谓词改成能吃 3000 时必须红）；原「判据本身有一条未决：端口表两行与实际不符，已登记 P-78」的前提由 D-V21-05 关闭——裁的是文档跟实况，不是改端口
验收锚:
  - apps/api/tests/test_r19_ports.py
  - apps/api/tests/test_ci_windows_skip_gate.py
最后核验 commit: c687a33（2026-10-22，STEP-19 收口判「部分确认」）；实现度于 2026-10-29 STEP-62 按 D-V21-05 重判
---

# REQ-C-002 端口分配

## 需求条目（AGENTS.md 端口表同源；X-4/D-V21-05 起拆两段）

**本栈发布**（`docker/compose.yml` 现读：`:101` "5300:5300"、`:245` "3300:3300"、`:423` "3200:3000"）：

| 端口 | 用途 | 约束 |
|---|---|---|
| 3000 | 主平台专用 | ❌ BotHot 任何服务禁止占用（前端容器内部 3000 不向宿主发布） |
| 3200 | BotHot 前端宿主端口 | 容器内部 3000，宿主映射 3200 |
| 3300 | BotHot 后端端口 | 容器内部 3300 |
| 5300 | LangBot | 容器 5300 → 宿主 5300 |

**外部提供**（本栈 compose 不发布；P-78/P-102 判定前的过渡口径）：

| 端口 | 用途 | 约束 |
|---|---|---|
| 5433 | PostgreSQL（历史规划值） | 本栈 compose 未发布；测试用 5547 隔离库（test-env.sh），CI 用 service 容器 |
| 6380 | Redis（历史规划值） | 本栈 compose 内无 Redis 服务 |

## 实现度判据

`test_r19_ports.py` 七条，逐条都是**双向**的（正向证明 + 反证），例如：
`test_no_bot_hot_service_publishes_the_main_platform_port`（无服务占 3000）、
`test_the_predicate_fails_on_a_service_that_does_take_3000`（把谓词改成能吃 3000 时它必须红）、
`test_dockerfile_expose_does_not_declare_3000_for_the_backend`、
`test_frontend_host_mapping_is_3200_not_3000`、
`test_every_documented_bot_hot_host_port_is_actually_published`。

## 原「部分」的前提是怎么关掉的（STEP-62 重写）

STEP-19 的收口判词是「**部分确认**」，卡点是同一轮现读发现「端口表里 5433 / 6380 两行与实际部署形态不符」，
登记 P-78 等规划方裁定。P-78 的裁定是 **D-V21-05**（`docs/03_solution/decisions/decision-log.md:146`）：
「文档跟实况：分本栈发布 / 外部提供两段，不改端口与 compose」，理由栏写的是「改 compose 回表值：
需架构裁决且无收益」。STEP-51 的 S51.3 按它落了表，台账 P-78 那行也已「状态更新」。

⇒ 判据不再有未决项：文档声明的宿主端口就是实际发布的那些，另外两口明确标成「外部提供、本栈不发布」。
当时那条「在 P-78 落定之前没法给 PASS」的推理随前提消失而失效，实现度改判「已实现」。

**限定读法**：本条只判「文档与 compose 同源 + 3000 不被本栈占用」，不判 PG/Redis 在生产上到底跑在哪台机器——
那是基础设施事实，不属端口分配的文档判据。

## 端口变更流程（约束本身）

变更需先经架构裁决，并同步 `AGENTS.md` 与 `docs/04_engineering/conventions.md`——
两处都要改，只改一处就是下一次漂移的种子（与 REQ-C-001 的"门面 vs 实值"是同一类）。
