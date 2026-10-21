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

---
## 执行记录（执行助手 · 2026-10-21 · 原九项第一次执行）

卡面文本与状态行都未改，本段是追加。读数与判据在 `docs/06_validation/evidence/EVD-V17-00T/`
（`s00t_readings.md` 判定与取数、`inventory.md` 逐支盘点）。

| 项 | 状态 | 读数 |
|---|---|---|
| S0T.1.1 列出全部判据函数（AST） | 已执行 | 20 支 / 11495 行；`EVIDENCE_PROOFS` import 后读常量 ⇒ 被门复跑的只有 **3 支**；自带 `--self-test` 面 9 支 |
| S0T.1.2 映射到需求锚与 STEP | 已执行 | 映射取自每支脚本 `ast.get_docstring` 首行（S27.1/3/5、G-24、S0.1.2、STEP-00R、S2.1.1–2.1.5、S3.4.1、STEP-00W、STEP-00P），见 `inventory.md` §2 |
| S0T.1.3 输出 inventory.md | 已执行 | `EVD-V17-00T/inventory.md` |
| S0T.2.1 有效判据迁为 pytest | **未整批执行**（本轮给出不能整批做的证据） | 真正搬不动的是两类**会动盘**的（临时仓/合成树电池 `replay_s213`/`mutate_replay_r9`/`j_attack_r7`；直接改真实文件再 sha256 还原的 `s27_3_mutation`）加一类**需要特殊环境的一次性读数探针**（`probe_import_stall`）。⚠️ 第一版把 `mutate_s341.py` 也归进"改真实代码"，读实现后否证：它 `write_text` 计数为 0，变异体在内存里造（`_load_mutant`）⇒ 它是**第一顺位迁移对象**。逐支归因与被推翻的归因都写在 `inventory.md` §4/§4.1，需规划方按支签字（节奏同 V14.3 的"逐支 + 两轮复查"） |
| S0T.2.2 迁移后删旧脚本 | 同上未执行 | 本轮零删除。删除只发生过一次且有账：V14.3 的 `prove_provider_shapes.py` |
| S0T.2.3 凭据形字面量改环境变量 | 已核 | 本轮未新增任何内联连接串；`evidence-check` 的敏感形门与 `gitleaks` 均 0 命中 |
| S0T.3.1 proofs 纳入 CI pytest | **已成立并被证明** | `pytest tests/proofs --collect-only` ⇒ 33 条；`testpaths = ["tests"]` + CI 跑 `pytest tests/` ⇒ 每次 `@ci` 都在跑这 33 条 |
| S0T.3.2 行数上限下调到实测值 | **无法执行——上游那道门不存在** | `guards.py` 里没有任何行数上限常量或判定；STEP-00G 的 S0G.3.1–3.3 仍未打勾 ⇒ 没有"当前值"可下调。实测当前值 20 支 / 11495 行，登记 `§4 P-59`（P-31 同族：须机械执行的裁决落地率为 0） |
| S0T.3.3 gitleaks 0 新增 | 成立 | `no leaks found`（311 commits scanned）+ `protect --staged` 0 |

**为什么这张卡的状态行不动、STEP-00R 的动了**：本卡尾上写着"卡面状态行与本执行记录并存是有意的，
本仓规矩是追加不重写"，所以这里只追加；而 STEP-00R 卡面有 `S0R.3.2「状态表更新」`这一条明确指令，
两处不是互相打脸，是**各自卡面的指令不同**。下游若看到 00T 仍写"⚪ 未开始"，真实进度看本节。

本轮最该留下的一条是 §2 那次自我否证：路径存活代理第一次报了 5 个"已消失"，
逐条查回原文发现**全是电池自己造的合成夹具**（`replay_s213.py:1818` 就地 `write_text`）。
如果照那个数下结论，本卡会写出"4 支判据已烂掉"——全是假的。修正后"已失效"是 0 支。
