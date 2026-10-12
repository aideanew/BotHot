---
id: TASK-001
type: task
title: 轮换已入库的共享底座 PG 账号口令（人工）
status: ready
slice: S0
owner: 人工（运维）
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-001：轮换已入库的共享底座 PG 账号口令（人工）

**归属**
- 所属切片：S0（WP-0 安全止血）
- 执行 Agent：人工（运维）
- 来源需求：REQ-NF-002（真实密钥禁止入库，README 安全铁律）
- 来源方案：ADR-0010（提议）

**目标**
共享底座 PG 账号 bothot_rw 的口令已更换，旧口令 <已轮换·见运维工单> 无法再连接。

**输入**
- 证据：docker/compose.yml:157（commit 01f6892 引入，仓库为 public）
- 前置任务：无
- 前置状态：无

**输出**（新增/修改的文件）
- 无仓库文件变更（运维操作）
- docs/06_validation/evidence/EVD-001/rotation.md（记录时间、执行人，不记新口令）

**Execution Steps**
1. [ ] 在共享底座 PG（宿主 5435）执行 ALTER ROLE bothot_rw WITH PASSWORD '<新值>'
2. [ ] 把新连接串只写入本机 docker/.env（已 gitignore）
3. [ ] 用旧口令尝试连接，确认被拒绝
4. [ ] 在 EVD-001 写入时间与结论（不含口令）

**验收标准**
- [ ] 旧口令连接返回 password authentication failed
- [ ] 仓库内无新口令（gitleaks 与 grep 均 0 命中）

**验证命令**
```bash
PGPASSWORD=<已轮换·见运维工单> psql -h 127.0.0.1 -p 5435 -U bothot_rw -d bothot -c 'select 1'   # 期望：认证失败
git grep -n "<新口令片段>" || echo OK
```

**证据路径**
`docs/06_validation/evidence/EVD-001/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `docs/06_validation/evidence/EVD-001/**`

**禁止修改**
- 仓库内任何代码与配置

**依赖与阻塞**
- Depends on：无
- Blocks：TASK-002 的上线（不阻塞其开发）
- 阻塞条件：无共享底座 DBA 权限 → 标 blocked 交人

**建议执行档位**
人工　理由：涉及生产凭据，CLI 不得接触口令

**升级条件**
不适用；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小（<2h，按规则并入 S0 演示）
