# STEP-34 门禁判据精度修正

> 基线 main@f86811e｜状态：⚪ 未开始｜版本 V0.18.0

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行 Agent-Guard |
| 2 验收者 | 规划方 |
| 3 难度 / 里程碑 | 中 / M0 |
| 4 来源 | P-54、P-56、P-57、P-85、P-100、P-101、P-108；D-V18-15、D-V18-16 |
| 5 目标 | 每道门只抓它想抓的东西：不把函数名当违规、不把分片提交当多轮、不把目录名当裁决号；需求锚有常驻门；Linux 侧 make 有执行者；卡死时必留栈 |
| 6 输入 | `scripts/guards.py:241` `rounds_violations`；`scripts/check_docs_consistency.py`；`.github/workflows/ci.yml`、`ci-windows.yml`；`apps/api/tests/test_collection_contract.py`（台账门）；`docs/06_validation/evidence/EVD-V17-12/req_anchor_reconciliation.txt`（一次性探针的口径） |
| 7 输出路径 | 上述脚本、两个工作流的相关步、对应测试、`docs/06_validation/evidence/EVD-V18-34/`（D-V18-13） |
| 10 命令 | `python scripts/entry.py guard`（各子门）；`pytest tests/test_guards*.py tests/test_collection_contract.py -q`；`python scripts/check_docs_consistency.py` |
| 12 允许修改 | 第 7 格所列 |
| 13 禁止修改 | `app/**`；门的阈值（只改判据形状） |
| 14 依赖 | 38 |
| 15 档位 | sonnet |
| 16 规模 | ≈1.2 人日 |

## 三级任务
1. [ ] **S34.1** P-100：`open(` 判据改为只匹配调用形（前面不是标识符字符或 `.`），函数定义名与属性访问不算；反证四发（真调用红 / 函数名不红 / 属性不红 / 注释不红）
2. [ ] **S34.2** P-56 + P-85（D-V18-16）：`rounds_violations` 改按"第 N 轮"最大 N 计；支持"已升级"标记（主题含 decision-log 中存在的 D 号）越过熔断；用 V0.17.0 的真实主题列表回放：STEP-15b 分片五提交不再判熔断，STEP-07 第 3 轮仍判熔断除非带 D-V17-04
3. [ ] **S34.3** P-57：台账门的裁决号匹配加左边界（前一个字符不能是字母数字或 `-`），`EVD-V15-27` 这类目录名不再被读成裁决号；反证用例
4. [ ] **S34.4** P-108：把需求锚对账做成 `check_docs_consistency.py` 的一节：扫 `docs/02_requirements/**` 与 `AGENTS.md` 里的仓内文件锚与 `::` 符号锚，按 HEAD 判存在；故意改坏一个锚 ⇒ 门红
5. [ ] **S34.5** P-101：ubuntu 的 backend job 加一步，跑 `check_entry_parity` 已列的 6 个轻量任务的 `make X` 与 `python scripts/entry.py X`，比较零/非零一致
6. [ ] **S34.6** P-54：`faulthandler_timeout` 改为 100（小于 `--timeout=120`），证据里写清为什么要小于

## 完成判据（全部机器可判）
- 每条子项都有"改前红/假阳 → 改后正确"的读数
- 三绿；CI 日志里能看到 S34.5 新步与其输出
- rounds-check 回放表入证据

## 熔断
连续 2 轮验收 FAIL ⇒ 停卡交回规划方（rounds-check 机器执行，口径见 D-V18-16）。前提与现读不符 ⇒ 先登记 P 号再停，不自改卡面。
