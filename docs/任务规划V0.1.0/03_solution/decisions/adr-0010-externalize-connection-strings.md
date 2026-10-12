---
id: ADR-0010
type: decision
title: 编排中的数据库/缓存连接串一律来自环境变量
status: proposed
owner: architecture
created: 2026-10-12
updated: 2026-10-12
related: [CURRENT-PLAN-20261012]
---

# ADR-0010：连接串外置

## 背景（证据）
- `docker/compose.yml:157` 含明文 `postgresql+psycopg://bothot_rw:<已轮换·见运维工单>@host.docker.internal:5435/bothot`，由 `01f6892` 引入；仓库为 public。
- 当次 Security 工作流（含 gitleaks）结论 success，现有规则未识别 URL 内嵌口令。
- README「安全铁律：真实密钥禁止入库」。
- 端口口径冲突：AGENTS.md 规定 PG 5433 / Redis 6380；compose 连共享底座 5435 / 6379（D-02）。

## 决定（提议）
1. compose 中 `DATABASE_URL`、`REDIS_URL` 使用 `${VAR:?提示}` 必填展开，值只放 `docker/.env`（已 gitignore）。
2. gitleaks 增加 URL 内嵌口令规则；仅 `docker/compose.ci.yml` 的一次性 CI 库口令进 allowlist。
3. 已泄露口令立即轮换（人工，TASK-001）；不改写 git 历史（与协作纪律「拒绝 rebase 重写」一致）。
4. 端口口径按 D-02 裁决结果统一到 AGENTS/README/conventions 与 compose。

## 前提与局限
- 轮换后旧口令仍可在历史中看到，但已无效。
- 共享底座是否对外可达未知（Q-01）。
