# STEP-34 门禁判据精度修正

> 基线 main@f86811e｜状态：✅ 已收口（2026-10-24，交付 head 1ae5633 三绿 attempt 1：CI 40004227226 / CI-Windows 40004227288 / Security 40004227468；第 2 轮修 S34.5 的 bash -e 问题）｜版本 V0.18.0

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
1. [x] **S34.1** P-100：`open(` 判据改为只匹配调用形（前面不是标识符字符或 `.`），函数定义名与属性访问不算；反证四发（真调用红 / 函数名不红 / 属性不红 / 注释不红）——tokenize 判据进 `guards.py::open_call_violations` + 常驻 7 用例 + 变异 0→1→0
2. [x] **S34.2** P-56 + P-85（D-V18-16）：`rounds_violations` 改按"第 N 轮"最大 N 计；支持"已升级"标记（主题含 decision-log 中存在的 D 号）越过熔断；V0.17.0 回放四发在 `EVD-V18-34/s34_2_replay.txt`（五分片不熔断 / 裸第 3 轮熔断 / 持 D-V17-04 放行 / 未登记号不放行）
3. [x] **S34.3** P-57：台账门的裁决号匹配加左右边界（前一个字符不能是字母数字或 `-`，序号定长两位），三处同族模式一并修；两发极性反证先红后绿（185 passed）
4. [x] **S34.4** P-108：需求锚对账进 `check_docs_consistency.py`（HEAD blob 存在性 + 裸名/半路径对语料与 HEAD 双层解析 + `::` 符号定义判据 + `--self-test` 五发极性）；现读 133 锚全命中；变异改坏一个锚 ⇒ 门红
5. [x] **S34.5** P-101：ubuntu backend job 加 `make/entry parity` 步（@win 复算表同组 6 任务，零/非零一致；置于迁移往返步后）；本机六发全一致
6. [x] **S34.6** P-54：`faulthandler_timeout` 120→100（小于 `--timeout=120`），常驻断言比数值；理由在证据 §S34.6

## 完成判据（全部机器可判）
- 每条子项都有"改前红/假阳 → 改后正确"的读数
- 三绿；CI 日志里能看到 S34.5 新步与其输出
- rounds-check 回放表入证据

## 熔断
连续 2 轮验收 FAIL ⇒ 停卡交回规划方（rounds-check 机器执行，口径见 D-V18-16）。前提与现读不符 ⇒ 先登记 P 号再停，不自改卡面。
