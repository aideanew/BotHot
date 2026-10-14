# STEP-00G 执行治理-裁决落地与复审熔断

> 基线 main@61358c3｜状态：⚪ 未开始

| 字段 | 内容 |
|---|---|
| 1 归属（执行者） | 执行Agent |
| 2 验收者（与执行者分离） | 规划方(Hark)，只输出 PASS/FAIL/UNKNOWN |
| 3 难度 / 里程碑 | 中低 / M0 |
| 4 来源 | F-18/F-19；V0.7.0 docs/任务规划V0.7.0/steps/STEP-00G-执行治理-默认裁决复审熔断与文档止血.md |
| 5 目标 | 裁决有签字入口；复审轮次与证据脚本增长被机械约束。 |
| 6 输入 | 03 裁决表；V0.7.0 00G 卡 |
| 7 输出路径 | docs/03_solution/decisions/decision-log.md；Makefile evidence-check 目标的阈值注释 |
| 8 三级任务 | 见下 |
| 9 验收 | decision-log 存在且 24 行；evidence-check 对超限报红（构造一次） |
| 10 命令 | `find docs/06_validation/evidence -name '*.py' | xargs wc -l | tail -1; make evidence-check` |
| 11 证据 | docs/任务规划V0.8.0/evidence/61358c3-00g/ |
| 12 允许修改 | docs/03_solution/**、Makefile 注释与阈值常量 |
| 13 禁止修改 | apps/** |
| 14 依赖 / 阻塞 | 无 / 无 |
| 15 档位 | T1 |
| 16 升级条件 / 规模 | AGENTS.md 已有冲突约定 ⇒ 交规划方裁决 / ≈0.5 人日 |

## 三级任务

### S00G.1 裁决入口
- **S0G.1.1** 建 decision-log.md，24 项裁决逐行：ID/默认值/状态(未签/已签)/签署人/日期
- **S0G.1.2** 4 个 BLOCKING 置顶
- **S0G.1.3** adr-index 加链接

### S00G.2 复审熔断
- **S0G.2.1** 同一子任务复审 >3 轮 ⇒ 判 FAIL 并上报（写入 AGENTS.md 执行约定段，若该段已存在则只加一行）
- **S0G.2.2** 统计 S2.1.4/S2.1.5 当前轮次（≥16）作反证样本
- **S0G.2.3** 熔断规则加入 docs consistency 检查项的待办（由 00T 实现）

### S00G.3 证据增长止血
- **S0G.3.1** 重读 evidence `.py` 行数（勿抄 9,519）
- **S0G.3.2** 设新上限=当前值，超限 evidence-check 报红
- **S0G.3.3** 00T 每迁一个判据，上限同步下调
