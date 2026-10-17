# STEP-00T 证明判据pytest化与脚本归档

> 基线 main@61358c3｜状态：⚪ 未开始

| 字段 | 内容 |
|---|---|
| 1 归属（执行者） | 执行Agent |
| 2 验收者（与执行者分离） | 规划方(Hark)，只输出 PASS/FAIL/UNKNOWN |
| 3 难度 / 里程碑 | 中 / M0.5 |
| 4 来源 | F-18；V0.7.0 docs/任务规划V0.7.0/steps/STEP-00T-证明判据pytest化与脚本归档.md |
| 5 目标 | 把 prove_*.py 中仍有效的判据迁为 pytest 用例，证据目录只留结果；行数单调下降。 |
| 6 输入 | docs/06_validation/evidence/EVD-V2-00R/*.py、EVD-V2-02/*.py |
| 7 输出路径 | apps/api/tests/proofs/**；对应 evidence 脚本删除或标 archived |
| 8 三级任务 | 见下 |
| 9 验收 | proofs 全绿；evidence .py 行数 < 00G 设的上限；CI 双绿 |
| 10 命令 | `cd apps/api && uv run pytest tests/proofs -q` |
| 11 证据 | docs/任务规划V0.8.0/evidence/61358c3-00t/ |
| 12 允许修改 | apps/api/tests/proofs/**、docs/06_validation/evidence/** |
| 13 禁止修改 | apps/api/app/** |
| 14 依赖 / 阻塞 | 00C、00G / 无 |
| 15 档位 | T2 |
| 16 升级条件 / 规模 | 判据依赖真实外网 ⇒ 标 skip 理由并计入 SKIP_BASELINE 讨论，交规划方 / ≈1.5 人日 |

## 三级任务

### S00T.1 盘点
- **S0T.1.1** 列出全部判据函数（AST 扫描），标有效/重复/已失效
- **S0T.1.2** 映射到需求锚与 STEP
- **S0T.1.3** 输出 inventory.md

### S00T.2 迁移
- **S0T.2.1** 有效判据逐个迁为 pytest，参数化
- **S0T.2.2** 迁移后旧脚本删除，保留输出摘要
- **S0T.2.3** 凭据形字面量一律改环境变量（与 00S 规则一致）

### S00T.3 门禁
- **S0T.3.1** proofs 目录纳入 CI pytest
- **S0T.3.2** evidence 行数上限下调到实测值
- **S0T.3.3** gitleaks 0 新增

## V0.9.0 → V0.10.0 本卡变更（基线 main@81cb997）

- 本版无实质变更；执行前现读行号（基线 81cb997，自 53ebc4a 起业务代码零改动）。

---
## V0.13.0 补充输入（基线 main@314d7f2，不增任务数）
- `make evidence-check` 现为红：`docs/06_validation/evidence/EVD-V2-00/prove_provider_shapes.py` 按 AST 抽 `_map_row` 单独 exec，STEP-03 之后 `_map_row` 依赖同文件 `_row_identity`（`apps/api/app/services/manifest.py:165,192`）⇒ `NameError`（证据 `docs/任务规划V0.13.0/evidence/314d7f2/evidence_check.txt`）。这正是本卡"证明判据 pytest 化"要消灭的形态：AST 抽函数的证明会随实现演进静默失效。**本卡第一项任务以它为首个迁移对象**：改为 pytest 直接 import 被测函数，并把 `evidence-check` 接进 CI（或在 `guards.py` 的 `EVIDENCE_PROOFS` 中移除已 pytest 化的条目），出门判据 = `python scripts/guards.py evidence-check` rc=0。
