---
id: TASK-004
type: task
title: gitleaks 规则补『URL 内嵌口令』检测
status: ready
slice: S0
owner: Agent-Guard
created: 2026-10-12
plan: docs/04_planning/current-plan.md
---

# TASK-004：gitleaks 规则补『URL 内嵌口令』检测

**归属**
- 所属切片：S0（WP-0 安全止血）
- 执行 Agent：Agent-Guard
- 来源需求：REQ-NF-002
- 来源方案：DESIGN-001 §9 自动化守卫

**目标**
向 security.yml 的 gitleaks 增加规则，使形如 scheme://<user>:<pass>@host 的连接串被识别；对 commit 01f6892 复跑能报出。

**输入**
- .github/workflows/security.yml:421-515（gitleaks step）
- 证据：01f6892 的口令未被现有 gitleaks 拦截（该 run 结论 success）

**输出**（新增/修改的文件）
- .gitleaks.toml（仓库根）
- `.github/workflows/security.yml`

**Execution Steps**
1. [x] 新建 .gitleaks.toml：extend 默认规则 + 自定义 regex `[a-z+]+://[^:/\s]+:[^@/\s]+@`
2. [x] allowlist 放行占位凭据与历史泄露提交（**原写"仅放行 compose.ci.yml 的 bothot:bothot"，与实做不符**：
   实做放行 `docker/.env.example` 占位形状 1 条路径 + `01f6892` commits 双写；counterfactual 见下）
3. [x] security.yml 的 gitleaks 调用加 --config .gitleaks.toml
4. [x] 本地对 01f6892 复跑验证能报出——**用去除 commits 白名单的临时配置**（见验收项 1 的复述）

**验收标准**
- [ ] **能力证明（反事实）**：在 `/tmp` 复制一份配置并**删掉 commits 白名单**，
      `gitleaks detect --config /tmp/xxx.toml --log-opts '01f6892^..01f6892' -v` 报出 compose.yml:157
      ⇒ rc=1。⚠ 副本必须放仓库外：放 `_workspace/` 且用被 `.gitignore` 忽略的后缀（实测 46 不变），
      放**未被忽略**的命名会 +6（本文件自命中数），污染判据。
- [ ] **共存证明**：同一 range 用**入库配置**复跑 ⇒ 命中被 `commits` 白名单抑制（rc=0）。
      两项一起才说明"规则有效 + 抑制是刻意的"。
      **原验收项 1（用入库配置要求 rc=1）与项 3「Security 工作流绿」互斥**：
      security.yml:95-99 是 `fetch-depth: 0` 的 **git 全历史**扫描，入库配置一旦不抑制 `01f6892`，
      项 3 永红；抑制则项 1 永红。故按意图（能力可证）改写为上面两条。此为 2026-10-12 外部复核第 7 条，已核实。
- [ ] HEAD 全量扫描在 TASK-002 合并后 0 告警（本机近似：tracked 35 命中/白名单 35/告警 0）
- [ ] Security 工作流绿（本机不可证，见大纲 R.14）

**验证命令**
```bash
# 能力证明（副本在仓库外，且不写口令字面量）
mkdir -p /tmp/glcf && cp .gitleaks.toml /tmp/glcf/nolock.toml
python - <<'PY'   # 去掉 commits 白名单（rule 级 + 全局级两处）
PY
gitleaks detect --config /tmp/glcf/nolock.toml --log-opts '01f6892^..01f6892' -v; test $? -eq 1
# 共存证明（入库配置应抑制）
gitleaks detect --config .gitleaks.toml --log-opts '01f6892^..01f6892' -v; test $? -eq 0
# 工作树（TASK-002 合并后）
gitleaks detect --config .gitleaks.toml --no-git -s docker/
```

**证据路径**
`docs/06_validation/evidence/EVD-004/`（PR 描述附命令输出与提交哈希）

**允许修改**
- `.gitleaks.toml`
- `.github/workflows/security.yml`

**禁止修改**
- packages/contracts/**（除 Agent-Contract 任务）
- apps/api/alembic/versions/**（除明确标注迁移版本号的任务）
- apps/api/app/core/errors.py（除 Agent-Contract 任务）
- AideanBot 原项目任何文件（AGENTS.md 关键约束 1）
- docker/**

**依赖与阻塞**
- Depends on：无
- Blocks：无
- 阻塞条件：规则误报 compose.ci.yml 以外的测试夹具 ≥3 处 → 停，回报清单

**建议执行档位**
sonnect　理由：规则编写 + 工作流参数

**升级条件**
Security 工作流连续 2 次红 → opus；任何任务连续 2 次验收失败即熔断（§10）。

**预估规模**
小
