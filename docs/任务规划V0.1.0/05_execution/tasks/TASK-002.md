---
id: TASK-002
type: task
title: compose 连接串外置为必填环境变量
status: ready
slice: S0
owner: Agent-Guard
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-002：compose 连接串外置为必填环境变量

**归属**
- 所属切片：S0（WP-0 安全止血）
- 执行 Agent：Agent-Guard
- 来源需求：REQ-NF-002；README『真实密钥禁止入库』
- 来源方案：ADR-0010（提议）

**目标**
docker/compose.yml 不再含任何明文口令；DATABASE_URL/REDIS_URL 缺失时 compose config 直接报错。

**输入**
- docker/compose.yml:150-160（backend_env 锚）
- docker/.env.example
- docker/compose.ci.yml（CI 叠加覆盖，不得被破坏）
- 契约：DESIGN-001 §Resources/配置

**输出**（新增/修改的文件）
- `docker/compose.yml`
- `docker/.env.example`

**Execution Steps**
1. [ ] 把 compose.yml:157-158 改为 ${DATABASE_URL:?DATABASE_URL 未设置} 与 ${REDIS_URL:?REDIS_URL 未设置}
2. [ ] grep 全仓 host.docker.internal:5435 与 bothot_rw 的消费方，逐个改为引用变量（含注释文案）
3. [ ] .env.example 增两条带占位符的条目与注释（共享底座/栈内两种写法）
4. [ ] 确认 compose.ci.yml 覆盖值仍生效

**验收标准**
- [ ] `git grep -nE 'bothot_rw:[^<>@[:space:]]+@' -- docker apps scripts packages .github` 返回空
- [ ] 注：原口径『grep 旧口令字面量』已作废——口令本身已从本规划文档中移除（不该出现在任何入库文件里），改为断言「不存在带 userinfo 口令的 bothot_rw 连接串」这一更强的形状判据
- [ ] 未设置 DATABASE_URL 时 docker compose config 非 0 退出
- [ ] compose.ci.yml 叠加 config --quiet 通过
- [ ] CI compose / compose-smoke 两 job 绿

**验证命令**
```bash
git grep -nE 'bothot_rw:[^<>@[:space:]]+@' -- docker apps scripts packages .github && exit 1 || true
env -u DATABASE_URL docker compose -f docker/compose.yml config --quiet; test $? -ne 0
DATABASE_URL=x REDIS_URL=y docker compose -f docker/compose.yml -f docker/compose.ci.yml config --quiet
```

**证据路径**
`docs/06_validation/evidence/EVD-002/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `docker/compose.yml`
- `docker/.env.example`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- docker/compose.ci.yml

**依赖与阻塞**
- Depends on：无
- Blocks：TASK-003
- 阻塞条件：compose.ci.yml 必须同步修改才能绿 → 停，提交给 Agent-Guard 协调

**建议执行档位**
sonnect　理由：单文件配置改动，规则明确

**升级条件**
CI compose-smoke 连续 2 次红 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小（约 2h）
