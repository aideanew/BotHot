# Task Plan — docs/任务规划V0.1.0 需求拆解与剩余任务执行

> 基线：`main @ 60e57231b1a2fed5ab566290e25f02c16b0e60d3`（2026-10-09）；计划文档自身未纳入版本控制（`git status` → `?? docs/任务规划V0.1.0/`）。
> 约束（用户指令 + 环境实测）：**不启动任何服务**；本机 `docker`/`ruff`/`mypy`/`pnpm`/`node_modules` 均不存在，`python 3.11.9` / `node v24.21.0` 可用。

## Goal

递归读完 `docs/任务规划V0.1.0/` 全部 35 个文件 → 拆解需求 → 对 25 张原子任务卡逐条做代码级证据核验 → 执行当前可执行项（每步交子智能体证明与逻辑验证）→ 输出 ≥3 级、原子化、带序号、可执行的剩余任务大纲体系。

## Phases

| # | 阶段 | 交付物 | 状态 |
|---|---|---|---|
| P0 | 文档全量读取与结构理解 | 本文件 §来源地图；findings §A | complete |
| P1 | 规划事实基线代码级复验（F-01…F-21 / X-01…X-16） | findings §B 证据链表 | in_progress |
| P2 | 需求→切片→任务三级映射与阻塞点定位 | findings §C + 大纲 L1-L3 | pending |
| P3 | 执行 S0 可执行项（TASK-002/004/005） | 代码/配置改动 + 子智能体验证报告 | pending |
| P4 | 执行 S5 治理项（TASK-018/019） | 配置+文档改动 + 子智能体验证报告 | pending |
| P5 | 执行 S4 通知去重（TASK-016/017，静态可验部分） | 后端/前端改动 + 子智能体验证报告 | pending |
| P6 | 汇总剩余任务大纲体系（≥3 级、原子化、序号） | 最终输出 | pending |
| P7 | 上报人工裁决项与人工运维项 | D-01…D-09 + Q-01…Q-04 + TASK-001 | pending |

## 来源地图（35 文件）

| 路径 | 行数/大小 | 作用 | 读取策略 |
|---|---|---|---|
| `04_planning/current-plan.md` | 2453 行 / 108KB | 权威规划全文（16 节） | 全文（§1-6、§8-16 已读；§7 按切片读） |
| `05_execution/tasks/TASK-001…025.md` | 各 1.5-2.8KB | 25 张原子任务卡 | 与 §7 同文（抽样 TASK-016 逐字比对一致），按需读 |
| `03_solution/design/DESIGN-001-*.md` | 20KB | 六份契约冻结包 | 与 §4 同文（§13 自述），按需查 |
| `03_solution/decisions/adr-0008/0009/0010 + adr-index` | 8.8KB | 3 个 proposed ADR | 全文已读 |
| `00_governance/glossary.md` | 3.4KB | 术语 + 规划期新增术语 | 全文已读 |
| `05_execution/task-index.md` / `task-template.md` | 3.8KB / 1KB | 任务索引（25 行状态表）/ 16 字段模板 | 全文已读 |
| `BotHot-current-plan.html` | 189KB | current-plan 的渲染产物 | 不单独读（同源双份，见 findings §A-7） |

## Decisions & Constraints

- **D-a 规划状态是 `proposed`**：§2 头注明「S2/S7/S8 在 §12 裁决前不得开工」；S1/S3 额外受 D-09（ADR-0008）门控。执行范围只能取 S0/S4/S5 中未 blocked 的卡。
- **D-b 不启动服务 = 验收命令大面积不可执行**：连库 pytest、`docker compose config`、`smoke.sh`、e2e 全部不可跑。结论：可交付「改动 + 静态证据 + 待跑命令」，不得标 ✅ 达标（协作纪律 §5：标 ✅ 必须附 `文件:行` 或命令输出）。
- **D-c 串行所有权**：§9 规定 `gen_contracts.py` 由 007→014 串行；`ci.yml` 018 先于 025；`AGENTS/README/conventions` 003 在 019 之后。本轮我只碰不冲突路径。
- **D-d 提交纪律**：单一身份 `CodingHeader`；只 add 自己名下路径；禁 `git rm`；未获指示不 push。

## Errors Encountered

| Error | Attempt | Resolution |
|---|---|---|
| GitHub API 未认证限流（trees 返回 0 文件） | 1 | 改用 `git clone` 走 10808 代理 |
| `docker`/`ruff`/`mypy`/`pnpm` 本机缺失 | 1 | 记录为环境边界（D-b），验证降级为静态 + 子智能体逻辑审查，不虚报测试通过 |

## Escalations（需人）

1. TASK-001：`bothot_rw` 口令轮换（人工运维，public 仓库历史已含明文；本会话无共享底座访问权）。
2. D-01 / D-02 / D-09（BLOCKING）+ D-03/04/05/06/07/08；Q-01…Q-04 需信息。
