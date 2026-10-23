---
id: REQ-C-002
type: requirement
title: 端口分配
status: active
owner: product
实现度: 部分（3000 禁占用与宿主映射有常驻用例；判据本身有一条未决：端口表两行与实际不符，已登记 P-78）
验收锚:
  - apps/api/tests/test_r19_ports.py
  - apps/api/tests/test_ci_windows_skip_gate.py
最后核验 commit: c687a33（2026-10-22，STEP-19 收口对 C-002 判「部分确认」）
---

# REQ-C-002 端口分配

## 需求条目（AGENTS.md 端口表同源）

| 端口 | 用途 | 约束 |
|---|---|---|
| 3000 | 主平台专用 | ❌ BotHot 任何服务禁止占用 |
| 3200 | BotHot 前端宿主端口 | 容器内部 3000，宿主映射 3200 |
| 3300 | BotHot 后端端口 | 容器内部 3300 |
| 5300 | LangBot | — |
| 5433 | PostgreSQL | 容器 5432 → 宿主 5433 |
| 6380 | Redis | 容器 6379 → 宿主 6380 |

## 实现度判据

`test_r19_ports.py` 七条，逐条都是**双向**的（正向证明 + 反证），例如：
`test_no_bot_hot_service_publishes_the_main_platform_port`（无服务占 3000）、
`test_the_predicate_fails_on_a_service_that_does_take_3000`（把谓词改成能吃 3000 时它必须红）、
`test_dockerfile_expose_does_not_declare_3000_for_the_backend`、
`test_frontend_host_mapping_is_3200_not_3000`、
`test_every_documented_bot_hot_host_port_is_actually_published`。

## 为什么仍是「部分」

STEP-19 的收口判词是「**部分确认**」：判据本体成立，但同一轮现读发现
**端口表里 5433 / 6380 两行与实际部署形态不符**，已登记为台账 P-78 等规划方裁定。
在 P-78 落定之前，"文档声明的宿主端口"与"实际发布的端口"是否一致这件事没法给 PASS，
所以实现度不写"已实现"。

## 端口变更流程（约束本身）

变更需先经架构裁决，并同步 `AGENTS.md` 与 `docs/04_engineering/conventions.md`——
两处都要改，只改一处就是下一次漂移的种子（与 REQ-C-001 的"门面 vs 实值"是同一类）。
