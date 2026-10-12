---
id: TASK-INDEX
type: index
title: 任务索引（current-plan 2026-10-12）
status: active
created: 2026-10-12
---

# 任务索引

| 任务 | 名称 | 切片 | Agent | 依赖 | 档位 | 规模 | 状态 |
|---|---|---|---|---|---|---|---|
| [TASK-001](tasks/TASK-001.md) | 轮换已入库的共享底座 PG 账号口令（人工） | S0 | 人工（运维） | — | 人工 | 小 | ready |
| [TASK-002](tasks/TASK-002.md) | compose 连接串外置为必填环境变量 | S0 | Agent-Guard | — | sonnect | 小 | ready |
| [TASK-003](tasks/TASK-003.md) | 端口与底座口径落档（依裁决 D-02） | S0 | Agent-Doc | TASK-002、D-02 | haiku | 小 | blocked（待裁决） |
| [TASK-004](tasks/TASK-004.md) | gitleaks 规则补『URL 内嵌口令』检测 | S0 | Agent-Guard | — | sonnect | 小 | ready |
| [TASK-005](tasks/TASK-005.md) | .project/ 排除出前端镜像构建上下文 | S0 | Agent-Guard | — | haiku | 小 | ready |
| [TASK-006](tasks/TASK-006.md) | 错误码登记表补全 50003 并加注册一致性断言 | S1 | Agent-Contract | D-09 | opus | 小 | blocked（待裁决） |
| [TASK-007](tasks/TASK-007.md) | gen_contracts 生成 errors.ts 并纳入 --check | S1 | Agent-Contract | TASK-006 | sonnect | 中 | waiting |
| [TASK-008](tasks/TASK-008.md) | 前端错误表对齐契约 + 429/413 展示态 | S1 | Agent-App | TASK-007、D-04 | sonnect | 中 | blocked（待裁决） |
| [TASK-009](tasks/TASK-009.md) | ADR-0009 访客访问策略定稿（依裁决 D-01） | S2 | Agent-Doc（opus 起草） | D-01 | opus | 小 | blocked（待裁决） |
| [TASK-010](tasks/TASK-010.md) | middleware 白名单与 AuthGate 按 ADR-0009 对齐 + 真实态单测 | S2 | Agent-App | TASK-009 | sonnect | 中 | waiting |
| [TASK-011](tasks/TASK-011.md) | 访客策略文档对账 | S2 | Agent-Doc | TASK-010 | haiku | 小 | waiting |
| [TASK-012](tasks/TASK-012.md) | bot 域响应模型（Pydantic）声明并接入序列化 | S3 | Agent-API | D-09 | sonnect | 中 | blocked（待裁决） |
| [TASK-013](tasks/TASK-013.md) | hot 域响应模型（Pydantic）声明并接入序列化 | S3 | Agent-API | D-09 | sonnect | 中 | blocked（待裁决） |
| [TASK-014](tasks/TASK-014.md) | gen_contracts 生成响应形状 DTO（*Out） | S3 | Agent-Contract | TASK-012、TASK-013 | sonnect | 中 | waiting |
| [TASK-015](tasks/TASK-015.md) | 前端 bots/hot API 层改用 *Out 契约类型 | S3 | Agent-App | TASK-014 | sonnect | 中 | waiting |
| [TASK-016](tasks/TASK-016.md) | SSE 通知帧携带落库 id（后端） | S4 | Agent-API | — | sonnect | 中 | ready |
| [TASK-017](tasks/TASK-017.md) | NotificationBell 用帧 id 去重（前端） | S4 | Agent-App | — | sonnect | 小 | ready |
| [TASK-018](tasks/TASK-018.md) | check_docs_consistency 入 CI 与 preflight | S5 | Agent-Guard | — | haiku | 小 | ready |
| [TASK-019](tasks/TASK-019.md) | 文档漂移修正批（不含端口） | S5 | Agent-Doc | — | sonnect | 中 | ready |
| [TASK-020](tasks/TASK-020.md) | .docs/ 遗留『待迁移』6 项：迁移或归档 | S5 | Agent-Doc | D-05 | haiku | 中 | blocked（待裁决） |
| [TASK-021](tasks/TASK-021.md) | 性能基线测量脚本与首测 | S6 | Agent-Guard | TASK-002 | sonnect | 中 | waiting |
| [TASK-022](tasks/TASK-022.md) | BotBinding 死表处置（条件：D-03） | S7 | Agent-Data | D-03 | sonnect | 小 | blocked（待裁决） |
| [TASK-023](tasks/TASK-023.md) | embedding.py 处置（条件：D-06） | S7 | Agent-API | D-06 | haiku | 小 | blocked（待裁决） |
| [TASK-024](tasks/TASK-024.md) | .project/ 第三方源码去留（条件：D-07） | S7 | Agent-Guard | D-07 | haiku | 小 | blocked（待裁决） |
| [TASK-025](tasks/TASK-025.md) | real-backend e2e 解阻并转为阻塞门禁（外部依赖） | S8 | Agent-App | D-08 | sonnect | 中 | blocked（待裁决） |
