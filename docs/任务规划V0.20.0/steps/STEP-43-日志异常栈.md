# STEP-43 日志异常栈

> 基线 main@75b212b｜状态：🟡 规划方已交付代码，待 @ci 三绿与独立复查｜版本 V0.20.0

| 字段 | 内容 |
|---|---|
| 1 归属 | **规划方**（D-V20-03） |
| 2 验收者 | 执行助手在 STEP-44 S44.1 做独立复查（PASS / FAIL / UNKNOWN） |
| 3 难度 / 里程碑 | 中高 / M4 |
| 4 来源 | P-114（执行助手登记、规划方复现）、P-115（规划方新发现）；D-V20-01/02 |
| 5 目标 | 两种日志格式下，异常日志都带完整栈；任何环境下都不出现栈帧局部变量 |
| 6 输入 | `apps/api/app/core/logging.py` |
| 7 输出路径 | 改 `apps/api/app/core/logging.py`（渲染器构造 + formatter 处理器链）；`apps/api/tests/test_log_redaction.py` 追加 3 条；证据 `docs/06_validation/evidence/EVD-V20-43/` |
| 10 命令 | `cd apps/api && python -m pytest -q tests/test_log_redaction.py`；rich 在场复现：把 rich 装进临时目录后 `PYTHONPATH=<该目录> python -m pytest -q tests/test_log_redaction.py` |
| 12 允许修改 | 第 7 格所列 |
| 13 禁止修改 | 冻结契约、迁移、`log_redaction.py` 规则本身 |
| 14 依赖 | 无 |
| 15 档位 | opus |
| 16 规模 | ≈0.3 人日（已完成） |

## 三级任务
1. [x] **S43.1** 先红：旧代码 + 无 rich ⇒ JSON 用例红（无栈）；旧代码 + rich ⇒ 4 条红（局部变量进日志、渲染器未固定）
2. [x] **S43.2** console 渲染器固定 `plain_traceback`；JSON 链渲染前加 `format_exc_info`
3. [x] **S43.3** 本机：ruff / mypy / 新用例（有无 rich 各一遍）/ 全量回归
4. [ ] **S43.4** @ci 三绿（规划方回填 `EVD-V20-43/s43_ci.md`）
5. [ ] **S43.5** 独立复查（STEP-44 S44.1）

## 完成判据
- `tests/test_log_redaction.py` 18 条全绿，且在 rich 在场时同样全绿
- 后端全量 0 failed；同一 head 三绿（注意：7e4c10e 上 backend 红属 P-116，由 STEP-45 修复，非本卡引入）
