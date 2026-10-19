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

---
## 执行记录（Agent-Guard · 2026-10-19 · 基线 main@7d999db，V0.14.0 增量）

卡面文本一律未改（含上面那段 V0.13.0 补充输入）。这一段是追加。

| 增量 | 状态 | 读数 |
|---|---|---|
| **S00T.V14.1** D-14 轮次门 | **已交付** | `python scripts/guards.py rounds-check` ⇒ 范围内无卡越限 rc=0；端到端在一次性仓库里 2 轮⇒绿、3 轮⇒红并点名 `STEP-77`、坏基线⇒1、空范围⇒3 |
| **S00T.V14.2** D-V4-03 耦合门 | **已交付（判据有一处收紧待追认）** | `evidence-check` 现先跑耦合门再复跑脚本；端到端"新增证据脚本 + 零新用例"⇒ rc=1 且打印 `净增 1 / 用例净增 0`，补 1 条用例⇒放行。卡面「= 0 ⇒ 红」实现成 `< 1`（P-33） |
| **S00T.V14.3** F-14 迁移 | **已交付，第 2 轮定点复验判通过** | `apps/api/tests/proofs/test_provider_shapes.py`：15 defs / **33 收集**（复验抓到 2 处判据缺口后 +2）（A16 + B6 + C6 + 极性 3，分组数取自 `pytest --collect-only`）；脚本已从 `EVIDENCE_PROOFS` 移除并 `git rm`，`EVD-V2-00/README.md` 追加 §7 归档说明；**出门判据实测达成**：`python scripts/guards.py evidence-check` ⇒ **rc=0**（准确口径：F-14 自 `314d7f2` 断裂以来第一次回到 0；断裂前 `b45777a` 有过 ✅，故不写「本仓第一次」——该收窄由复验指出并复核） |
| 原 9 项（S0T.1.x 盘点 / S0T.2.x 其余脚本 / S0T.3.x 门禁） | **部分推进**：S0T.3.1（proofs 进 CI）随本批**顺带成立**（CI 命令是 `pytest tests/`，递归收集自动覆盖 `tests/proofs/`）；S0T.1.x 盘点与 S0T.2.x 其余脚本、S0T.3.2 行数上限、S0T.3.3 gitleaks 增量仍**未执行** | 04 §3 表把本卡「本版剩余」记 12 = 原 9 + 增量 3；增量三项已全部交付 |

三条现读纠正（都带命令，不在门文本里静默生效）：

1. 卡面那句「`make evidence-check` 现为红…⇒ `_row_identity` NameError」在 `7d999db` 上**只对了一半**：
   现在第一个炸点是模块级 `MANIFEST_STATUS_DISCOVERED = ManifestStatus.DISCOVERED.value`
   （注入命名空间里没有 `ManifestStatus`），`_row_identity` 被它挡在后面，还有第三处 `_parse_rfc822`。
   复现命令在 `EVD-V14-00T` §2（整段可直接粘贴执行，实测输出已附）。
2. 「`make evidence-check`」这条命令本身**此前也跑不起来**：`$(GUARDS)` 在 Makefile 里从未定义
   ⇒ `make evidence-check` 实测 `Error 2`（旧 Makefile 用 `make -f` 复跑为证）。
   已随本增量补定义并上闸（`EVD-V14-00T` §5）。
3. 卡面 `10 命令` 写的是 `uv run pytest tests/proofs -q`：本机无 `uv`，本增量的验证命令一律用
   `apps/api/.venv/Scripts/python.exe -X utf8 -m pytest …`；`tests/proofs/` 目录尚不存在（属 S0T.2/S0T.3）。

编号归一：本卡原 9 项沿用卡面写法（`S00T.1` 组下三条子项在卡面上是 `S0T.1.1` 形态），
V14 增量按 V0.14.0 增量文件开头的规则写作 `S00T.V14.<n>`。两套前缀并存本身就是 V0.13.0/09 §0-e
登记过的问题，归一动作在 S0T.1.x（未开始），本轮不动。

### 轮次账（D-14：≤2 轮，第 3 轮须升级裁决，不得自行再修）

| 增量 | 第 1 轮 | 第 2 轮 | 结论 |
|---|---|---|---|
| S00T.V14.1 / V14.2 | 判 D 条 FAIL：词界缺失致 `background-3` 假红、`test_` 前缀改名丢用例、基线读不到偏绿、裸 `$VAR` 漏检、2 处过期读数 | 判通过；唯一残留「接线分支没有对应用例」——已用真变异对照（删接线后 rc 仍 1，故第二维断言必须断"真的调用过 `cat-file`"）补齐 | 2/2 用尽 |
| S00T.V14.3 | 判 A、F 两条 FAIL：容器判据丢了「非空」半条；`_URL_KEYS` 顺序从来没有判据（**继承缺陷**，旧脚本那条也只是措辞）；「本仓第一次 rc=0」超售 | 判通过：6 项全 PASS，含它自行复算 `git merge-base --is-ancestor b45777a 314d7f2` 与那条**未跟踪**的反证文件 | 2/2 用尽 |

两条**非阻塞待办**（复验点出，登记而不加轮次修）：

1. `test_upstream_container_levels_…` 对**标量**只要求非 None ⇒ `redfox data.total = 0` 仍算"有内容"。
   这是承旧脚本 `:323` 的口径，docstring 已写明；改成「数值必须 > 0」属判据变更，须新行推翻而非静默收紧。
2. 第 2 轮复验未覆盖：全量 `pytest tests/`（按指令跳过）、`git rm` 与 `EVD-V2-00/README.md` §7
   归档说明的复核（它给 UNKNOWN）。本机侧这两项的证据在 `07-执行过程` §2b 与本节下表。

另记一条本轮反复用到的纪律：**卡面状态行（"⚪ 未开始"）与本执行记录并存是有意的**——
本仓规矩是追加不重写，所以"未开始"不是隐藏矛盾，而是基线快照；真实进度只看本节与 `EVD-V14-00T`。
