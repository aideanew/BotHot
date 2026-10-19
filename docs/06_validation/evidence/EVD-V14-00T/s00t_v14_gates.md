# EVD-V14-00T · S00T.V14.1 / V14.2 两道治理闸（main@7a525a0 · 2026-10-19）

卡面：`docs/任务规划V0.14.0/steps/STEP-继承卡增量-00T-00R-15b-10-05-08-17-14a.md` §A
原卡：`docs/任务规划V0.13.0/steps/STEP-00T-证明判据pytest化与脚本归档.md`
来源裁决：D-14（≤2 轮，第 3 轮熔断）、D-V4-03（evidence 净增 ⇒ tests 净增 ≥1）、
D-V11-04（阈值以 D-14 为准）、F-V14-06（两条裁决在 `scripts/`、`Makefile`、`.github/` 里 0 命中）

## 1. 开工前先把规划方的读数自己跑一遍（不采信原文）

| 规划方读数 | 我的复算命令 | 复算结果 | 定性 |
|---|---|---|---|
| F-V14-06：`git grep -n "D-14" scripts/` 0 命中 | `git grep -n "D-14" -- scripts/ Makefile .github/` | 0 命中（`D-V4-03` 同） | 已确认 |
| F-V14-05：`prove_provider_shapes.py` rc=1 | `python scripts/guards.py evidence-check` | **rc=1**，`NameError: name 'ManifestStatus' is not defined`（`manifest.py:50`） | 已确认，但根因比卡面更深（见 §2） |
| 01 §3：本机全量 1 failed（环境泄漏） | `pytest tests/test_security_middleware.py -k production_guard` + 宿主设 `PUSH_SECRET_MASTER_KEY` | `assert 7 == 8` FAILED | 已确认 ⇒ 已由 S00R.V14.1 密封 |
| 04 §8：Done 定义引用 `make guard` | `grep -n "^guard:" Makefile` | **不存在** | 存在缺陷 ⇒ F-V14-09 |

## 2. F-14 的真实形状：不是"一处 NameError"，而是"这个取证形态已经整体失效"

V0.13.0 的 F-14 原文说根因是 STEP-03 给 `_map_row` 加了同文件辅助函数 `_row_identity`。
现跑到 `7a525a0` 上，同一脚本里**三处独立断裂**同时存在，前两处把第三处挡在后面：

1. `exec_functions(manifest.py, {… "MANIFEST_STATUS_DISCOVERED", "UPSTREAM_TZ"})` 把模块级
   赋值一起摘出来 exec，而注入命名空间（`:248-257`）只有 `Any/ET/json/hashlib/datetime/UTC/
   ZoneInfo/logger` ⇒ 第 50 行 `ManifestStatus.DISCOVERED.value` 立刻 NameError。**这是今天真正挡住的那一条。**
2. 手工补上 `ManifestStatus` 后再 exec 成功，但调用 `_map_row` 仍然炸：
   `NameError name '_row_identity' is not defined`——pick 名单里没有它（**这正是 V0.13.0 记的那一处**，
   它还在，只是被 1 挡在后面）。
3. 同一替身里 `_parse_time("Tue, 01 Oct 2026 09:00:00 +0800")` ⇒
   `NameError name '_parse_rfc822' is not defined`——`b84dc53`（STEP-03 S3.1-S3.3）新增的辅助函数
   同样不在名单里。

复现命令（不落 scratch 文件，谁都能直接跑）：

```bash
cd apps/api && ./.venv/Scripts/python.exe -X utf8 -c "
import importlib.util, pathlib, sys
root = pathlib.Path('../..').resolve()
spec = importlib.util.spec_from_file_location('pps', root/'docs/06_validation/evidence/EVD-V2-00/prove_provider_shapes.py')
pps = importlib.util.module_from_spec(spec); spec.loader.exec_module(pps)
sys.path.insert(0, str(root/'apps/api'))
from app.contracts.collection import ManifestStatus
names = {'_map_row','_parse_time','_from_epoch','_first_str','_ID_KEYS','_URL_KEYS','_TITLE_KEYS','_TIME_KEYS','_HASH_KEYS','MANIFEST_STATUS_DISCOVERED','UPSTREAM_TZ'}
ns = pps.exec_functions(root/'apps/api/app/services/manifest.py', names, extra_ns={'ManifestStatus': ManifestStatus})
for v in ('Tue, 01 Oct 2026 09:00:00 +0800',):
    try: print(ns['_parse_time'](v))
    except Exception as e: print('第二处断裂:', type(e).__name__, e)
try: print(ns['_map_row']({'workUuid':'a'*32,'title':'t','publishTime':'2026-09-27 07:42:00'}))
except Exception as e: print('第三处断裂:', type(e).__name__, e)
"
```

实测输出（`7d999db`）：
`NameError name '_parse_rfc822' is not defined`、`NameError name '_row_identity' is not defined`。

**更要紧的是两条"在案事实"已经翻了**，而脚本因为先崩在 1，从来没机会报出来：

| 脚本的断言 | `7d999db` 上的真值 | 何时翻的 |
|---|---|---|
| B 组 D-04：「RSS 2.0 的 RFC-2822 pubDate 恒得 `publish_time=None`」判 PASS | `_map_row` 现在给出 `2026-10-02 10:00:00+08:00 → 2026-10-02 02:00:00+00:00`，样本 2/2 行都有值 ⇒ **该 PASS 若迁成用例会直接红** | `b84dc53` 起 `_parse_rfc822` |
| C 组：「4 家付费源归一化行键 ∩ `_ID_KEYS` = ∅ ⇒ 行被 `_map_row` 丢弃」记 WARN | 四家的行键都含 `id` ⇒ **交集非空，行不再被丢弃**；反倒是 RedFox 的 `rowkeys=∅`（它把上游原始行直接交给 `_map_row`，不组装 `row` 变量） | 同上 `b84dc53`「清单行不再因缺 id 被整页静默丢掉」 |

⇒ 结论：这不是"脚本陈旧"，是**取证形态**错了。AST 抽函数 + 手写命名空间的证明，
既不能在实现演进时报红（它只会以 NameError 的形式崩在别处），也不能在结论被推翻时报案。
这正是 S00T.V14.3 要把它迁成 pytest（真 import、真调用）的理由，也是本版把它接进
`evidence-check`/CI 的理由。**V14.3 尚未执行**，本卡只交付两道闸（V14.1/V14.2）。

## 3. 两道闸的判据（`scripts/guards.py`，Makefile 目标 `rounds-check`/`guard`）

两条门都做成**纯函数 + git 薄壳**，判据本体不碰 git：

- `rounds_violations(subjects)` ⇒ 按 `STEP-<id>` 归卡，统计主题含「返工/重做」或「第N轮/round-N」的提交；
  红路两条：同一卡标记数 > `MAX_ROUNDS(=2)`，**或**任一主题直接写出 ≥3 的轮号。
  第二条是必须的：只有计数一条时，跨提交边界的返工（第 1、2 轮在基线之前）永远数不满，
  而"已经第 3 轮"这句话本身就够 D-14 熔断。
- `coupling_counts(rows, read_head, read_base)` + `coupling_violated(net_added, tests_delta)`
  ⇒ 证据脚本净增（A/U 加、D 减，改名 R 不计）> 0 且用例净增 < 1 即红；
  用例数由 `count_test_cases()` 用 AST 数 `def test_`/`async def test_`（含类内方法），
  卡面"不用 grep 行数"这条有专门反证：同一份合成源 AST 数 3、字面 `def test_` 出现 5。

**执行方对判据强度动过的唯一一处**（须规划方追认）：卡面写「用例净增 **= 0** ⇒ 红」，
我实现成 `< 1`（即 ≤0）。理由是"加证据脚本同时删用例"是更坏的情形，按字面 `=0` 会放行。
这是收紧不是放宽，且已有用例 `test_coupling_red_when_cases_net_decrease` 钉住。

**判据顺序也是判据**：耦合门放在 `evidence_check()` 复跑脚本**之前**。放在之后的话，
`prove_provider_shapes.py` 一红就 `return 1` 短路，耦合这一维永远不会被报出来——
这条被写成 AST 用例 `test_evidence_check_calls_the_coupling_gate_before_the_scripts`。

**空范围返回 rc=3，不返回 0**。GitHub 只为多提交推送的末端提交建 run，推送后
`origin/main..HEAD` 必然为空；若空范围给 0，"检查过了"和"什么都没看"在读数上就长得一样。
第三态沿用本仓 `evidence-check` 已有的 rc=3 口径（工具缺席 ⇒ 不是 PASS 也不是 FAIL）。

## 4. 反证：37 个判据定义（收集 38 例）+ 一次性真 git 仓库端到端 10 条读数

> 37/38 是**首轮评审返工之后**的读数（返工前 31 定义/32 收集；§8 记了 +6 条各来自哪条缺陷）。
> 分组数由脚本产生（`ast.parse` + 段横幅切片）。首稿我曾按印象写成"A12+B9+C5+D3+E3"，四个组全错
> ——这是本会话第三次手填数字，所以本版所有计数都必须有产生它的命令。

| 段 | 内容 | 实测 |
|---|---|---|
| A | 轮次判据：2 绿 / 3 红并点名 / 裸「第3轮」即红 / 中英两种轮号写法 / 裸「返工·重做」计数 / 跨卡不误计 / 无标记不计数 / **词界反证（`background-3`、`around 3` 不算轮号）** / **跨卡提及同时计数（卡面口径）** / **L3-only 主题不归属的实测盲区** / 坏基线 fail-closed / 空范围第三态 | 13 |
| B | 耦合判据：红绿两向、净减也红、未跟踪支计入、证据脚本改名不计、**`test_` 前缀被改掉 ⇒ 旧用例计为消失**、`test_` 之间改名两侧各算、**基线 blob 取不到先证伪（不许当 0）**、删除可抵消、AST vs 行数、两个 glob 的负例、`--name-status` 解析 | 13 |
| C | 接线判据：子命令注册、`make guard` 前置覆盖全部门、**未定义变量的多路反证（含裸 `$F` 与 `$$(shell …)`）**、`check_entry_parity` 仍绿、耦合门位置、坏基线 fail-closed、裁决编号出现在门源码里 | 7 |
| D | 端到端（`tmp_path` 里 `git init` 造一次性真仓库）：3 轮熔断、空范围/坏基线、孤儿证据脚本被拦后放行 | 3 |
| E | 主仓交叉核对：门的 git 侧取值 == 独立第二遍重数 | 1 |
| | **合计 defs 37 / 收集 38**（`test_signed_rulings_are_now_named_in_the_gate_sources` 以 `D-14`、`D-V4-03` 两个 token 参数化，1→2） | |

端到端那 10 条读数**已固化成 D 组 pytest 用例**（`test_end_to_end_*`），不再依赖一次性脚本；
复现命令就是 `cd apps/api && python -X utf8 -m pytest tests/test_guard_rounds.py -q -k end_to_end`。
下面是它首次以脚本形式跑出时的原文（同一判据、同一状态）：

```
── A. rounds-check：2 轮 ⇒ 绿
PASS  2 次标记判绿 :: ✅ rounds-check：范围内无卡越过轮次上限
── B. rounds-check：第 3 次标记 ⇒ 红并点名
PASS  3 次标记判红 :: 结论：1 张卡越过 D-14 ⇒ 停手并升级裁决（不得自行开第 4 轮）
PASS  红时点名 STEP-77
── C. 范围空 ⇒ rc=3（不是通过）
PASS  空范围走第三态 :: ⚠️  rounds-check：HEAD..HEAD 为空 ⇒ 无可检提交，**这不是通过**（rc=3）
── D. 基线不可解析 ⇒ rc=1
PASS  坏基线 fail-closed :: ❌ rounds-check：基线 'no-such-ref' 不可解析（先 fetch，或显式传 --base）
── E. 新增证据脚本、无配对用例 ⇒ 耦合门红且短路
PASS  耦合门判红 :: evidence 耦合门（D-V4-03）：范围 10368da…..工作树 ⇒ 证据脚本净增 1，用例净增 0
PASS  红话术点名两个数
PASS  耦合先跑：未走到脚本复跑
── F. 补上一条用例 ⇒ 放行并继续复跑
PASS  耦合门放行 / PASS 放行后进入脚本复跑阶段
── G. 提交后范围空 ⇒ 仍是第三态
PASS  推送后空范围 ⇒ 3
```

**我自己的两处判据失效是被反证抓出来的，不是被阅读抓出来的**：
1. 端到端 demo 第一次跑，A 段就报 `rc=3`——我把 `base` 误取了"第一条返工提交"而不是脚手架基线，
   范围因此为空。若只写"真文件 == 绿"那种判据，这个 bug 会让 demo 一直显示"绿"而无人起疑。
2. 主仓上第一次跑耦合门 demo 判成**绿**（`净增 1，用例净增 32`），因为本批自己就带了 32 条新用例——
   也就是说"看到门打印了"不等于"门开过火"。改到一次性仓库里把用例数置零才拿到真红。
   这条写进 §7 局限：**门的红必须在与当前批次无关的状态上证明**。

## 5. 顺带查出的 make 侧断裂（F-V14-09 / F-V14-10，已一并修）

- **F-V14-09**：`docs/任务规划V0.14.0/04 §8` 的完成定义引用 `make guard`，而 Makefile 里
  **没有** `guard` 目标。
- **F-V14-10（更严重）**：`$(GUARDS)` 在 Makefile 里被 5 条 recipe 使用，却**从未定义**。
  实测 HEAD 版 Makefile：
  ```
  $ make -f .staging/old_Makefile guard-ports
  process_begin: CreateProcess(NULL, guard-ports, ...) failed.
  make: *** [.staging/old_Makefile:144: guard-ports] Error 2
  $ make -f .staging/old_Makefile evidence-check   → 同样 Error 2
  ```
  ⇒ `make guard-ports / guard-structure / guard-versions / evidence-check` **四条既有门此前全部不可运行**；
  它们只在 `python scripts/guards.py <子命令>` 这条路上活着。
  而 `scripts/check_entry_parity.py:forwarded()` 的判据是"recipe 文本里含 `$(GUARDS)` 字样"，
  所以"每个目标都已转调实体脚本"这句声明自己也是空头的——**声明与可运行是两个维度**，
  这正是 STEP-00X 那份"跑不了与跑过去读数一样"的原始病灶，只是换了个变量名复发。

修法（三处，都在 Guard 所有权内的文件）：
1. Makefile 在既有 `ifeq ($(OS),Windows_NT)` 平台分支里补 `GUARDS ?= python scripts/guards.py`
   （Windows 分支必须是 `python`：`python3` 在 Windows 解析到 Store 空壳，那是"没装却像通过"的假读数）。
2. Makefile 加 `guard: guard-ports guard-structure guard-versions rounds-check evidence-check`
   （复合目标写法同 `test:`/`lint:`：前置 + `@:`）。
3. `scripts/check_entry_parity.py` 新增 `undefined_variables()`：recipe 用到的每个 `$(VAR)` 必须有定义，
   未定义即 rc=1；调用方变量（`MSG`）只有**每个**出现点都在 `NAME="$(MSG)"` 赋值位时才豁免。
   判据自身有正反四例（见 §4-C 组）。
4. `scripts/entry.py` 注册 `rounds-check` 与复合 `guard`——`check_entry_parity` 要求 Makefile 目标名
   ⊆ `entry.BY_NAME`，不注册就是把新门自己判红。

修后读数：`make rounds-check` ⇒ ✅ rc=0；`make guard-ports` ⇒ ✅ rc=0；
`make -n guard` ⇒ 五行 `python scripts/guards.py …`；`python scripts/check_entry_parity.py` ⇒ rc=0；
`undefined_variables(HEAD 版 Makefile)` = `['GUARDS']`、现行 = `[]`（同一判据能区分修复前后）。
CI-Windows 本来就跑 `python scripts/check_entry_parity.py`（`ci-windows.yml:109`）⇒ 这条新判据自带 CI 面。

## 6. 所有权越界（必须登记，不靠"反正绿了"糊过去）

V0.14.0/04 §5 给 Agent-Guard 的 W 面是 `scripts/guards.py`、`Makefile`、`.github/workflows/**`。
本卡实际另自动了 **两个未列出的文件**：

| 文件 | 为什么非动不可 | 动的范围 |
|---|---|---|
| `scripts/entry.py` | 既有机器门 `check_entry_parity` 要求 Makefile 每个目标名都在 `entry.BY_NAME`；新增 `rounds-check`/`guard` 两个目标若不注册，就是把这一卡自己判红 | 只在末尾的守卫注册循环里加 1 个名字 + 1 条 `add("guard", composite=…)`；未改任何既有任务体 |
| `scripts/check_entry_parity.py` | 它已经**红了**（F-V14-10），红因正是它自己的 `forwarded()` 判据不检查变量定义；不补这条，同类断裂会第三次复发 | 新增 `undefined_variables()` + `MAKE_BUILTINS`/`CALLER_VARS` 两个常量 + main 里一个红分支 |

两处都是"被既有机器门强制要求"而不是我自作主张扩面，请规划方在追认里判：
是否把 `scripts/entry.py`、`scripts/check_entry_parity.py` 正式并入 Agent-Guard 的 W 面。

## 8. 首轮独立评审的 6 条与本轮返工（第 1 轮，D-14 计 1 次）

评审者（general-purpose 子智能体，15 次调用）判 **D 条 FAIL**、其余 PASS，并给出 6 条缺陷。
**六条我全部自己复算过**（`.staging/verify_review_claims.py` 的思路已内联成下面的命令），
结论是：5 条成立并已修，1 条是卡面原文口径不改。

| # | 评审主张 | 我的复算（返工前） | 定级与处置 |
|---|---|---|---|
| 1 | `_ROUND_RE` 无词界 ⇒ `background-3` 被当成第 3 轮 | `_round_numbers('fix(STEP-01): tune background-3 timeout')` = **`[3]`**，且 `rounds_violations` 直接判红 | **HIGH·假红，已修**：加 `(?<![A-Za-z0-9])`；反证 `test_rounds_gate_round_number_needs_a_word_boundary` 同时钉住"真写法仍计数"（`round-3`/`第 3 轮`/`Round 3` 都得是 `[3]`），防止修成永远空 |
| 2 | `STEP-<id>` 归属对中文卡名失明 | `_STEP_ID_RE.findall('docs(裁决台账): S1.3.2 的第 7 轮熔断')` = **`[]`** | **HIGH·永绿，但按卡面保留**：卡面把归属口径定为 `STEP-<id>`，执行方扩正则=改判据。已写成用例 `test_rounds_gate_cannot_attribute_a_card_named_only_by_l3_id` 钉住现状并登记 P-33 ③ |
| 3 | `test_` 前缀改名时旧用例不计消失 | rows=[R helper_x.py ← test_gone.py(2 条)] ⇒ `{'evidence_added': 1, 'tests_delta': **0**}` | **MED·绕过，已修**：`coupling_counts` 改为两侧各自算（R/M/D 都算旧侧）；反证两条：改名离开 `test_` ⇒ `tests_delta=-2` 红；`test_` 之间改名 ⇒ 旧 2 新 3 记 +1 |
| 4 | `read_base` 读不到时静默当 0，方向偏绿 | M 行喂空基线内容 ⇒ 报成**「用例净增 1」**（旧 2 条被抹成 0） | **MED·已修**：新增纯函数 `missing_base_blobs(rows, blob_exists)`，先证伪再算；反证钉三种情况（判不到⇒点名、判得到⇒空、A/U 行不该被拦） |
| 5 | `undefined_variables` 看不见裸 `$VAR` | `@echo $FROMMK` ⇒ **`[]`** | **LOW·已修**：补 `(?<!\$)\$([A-Za-z])`（make 的单字符引用形式，`$MYVAR` 实际是 `$(M)`+字面量）；同时钉 `$$(shell date)` 不算引用、定义过就不报 |
| 6 | 跨卡提及会同时计入每张被点名的卡 | 一条主题 ⇒ `['20','22','23']` 三卡各红 | **不修，按卡面**："对每个 `STEP-<id>` 统计"就是原文；收窄成"只认第一个 id"是执行方改判据 ⇒ 写成用例 `test_rounds_gate_attributes_every_card_mentioned_in_a_subject` 钉住，交规划方裁（P-33 ③） |
| 附 | include 进别的 mk 文件会误红 | `grep "^include" Makefile` = 0 命中 | 本仓无 include，不加投机性放行分支；若将来引入 include，`$X` 判据会把它抓出来（正是期望行为） |

返工后的计数（由脚本产生，不再手填）：
**37 个 test 定义 / 收集 38 例**（返工前 31/32，本轮回 +6 定义）；
`pytest tests/test_guard_rounds.py` ⇒ `38 passed in 3.45s`；
`ruff check tests/test_guard_rounds.py` ⇒ 净；`check_entry_parity.py` ⇒ rc=0；
`guards.py rounds-check` ⇒ rc=0（范围 `origin/main..HEAD` 2 个提交）；
`guards.py evidence-check --base HEAD` ⇒ 耦合门打印「证据脚本净增 0，用例净增 37」后放行，
仍在 `prove_provider_shapes.py` 处 rc=1（F-14，归 V14.3，非本批引入）。

评审还确认了两件事，值得留档：
①它用一次性仓库独立复现了"门真的能红"（3 轮⇒rc=1 并点名 STEP-99、2 轮⇒rc=0、
单条「第3轮」⇒rc=1、孤儿证据脚本⇒rc=1 且输出里没有 `──`）；
②它核了我 §2 的内联复现命令是逐字可跑的（`ManifestStatus` / `_parse_rfc822` / `_row_identity`
三处 NameError 全中），并复核了 `undefined_variables(HEAD)=['GUARDS']`、`make -f old_Makefile`
的 `Error 2`、`grep -n "^guard:" HEAD:Makefile` 无命中。

## 9. 追认清单（本轮不自己批自己）

- P-33 ①：耦合门把卡面的「用例净增 = 0 ⇒ 红」实现成 `< 1`。
- P-33 ②：`rounds-check` 空范围返回 **rc=3** 而非 0——卡面未规定第三态，这是我加的防伪装；
  副作用：卡面 §验证命令 用 `&&` 串，CI 上范围空 ⇒ 链条断在 3。要么规划方认可 rc=3 并改验证命令，
  要么我改回 rc=0 并接受"空范围看起来像通过"。
- P-33 ③：轮次门的归属口径（L3-only 主题失明、跨卡提及同时计数、中文数字轮号不计数）。
- P-32：`make guard` 已存在且 `$(GUARDS)` 已定义；是否把它接进 CI 由规划方定。
- 所有权：`scripts/entry.py`、`scripts/check_entry_parity.py` 本批被机器门逼着动了（§6）。

## 10. 前提 / 局限 / 未验证

- 前提：D-14 的归属口径是 `STEP-<id>`。**已实测的盲区**：主题只写 L3 号（如 `S1.3.2`）时不归属，
  仓内真实存在这样一条（`docs(裁决台账): …S1.3.2 的…第 7 轮熔断`），门对它放行。
  扩展归属（由 `S<卡号>.` 反推卡号）会把判据变宽，按「执行方不改判据」我没做，
  已写成用例 `…_measured_blind_spot` 钉住现状，交规划方裁。
- 局限 1：轮次门是**本地/推送前**的门。CI 里 `origin/main..HEAD` 为空 ⇒ rc=3，
  所以它在 CI 上只能证明"接线在"，不能证明"判过"。判的证据只能来自 §4 的一次性仓库端到端。
- 局限 2：`第N轮` 只认阿拉伯数字与 `round-N`；本仓历史里出现过中文数字（`第二轮`…`第十一轮`，
  P-31 记录的 STEP-01 那 10 条）。这类主题**不会**被计数——但同批主题多数也含「返工」，
  且"不回溯历史"（卡面 .c）本来就是本门的前提。若要中文数字也计，需要规划方先定口径。
- 局限 3：`make guard` 的聚合里含 `evidence-check`，而它在缺工具/缺脚本时是 rc=3/rc=1 ⇒
  `make guard` 目前**应当**红（`prove_provider_shapes.py` 还红着，归 V14.3）。我没有为了让聚合绿
  而把它拆成"只跑架构门"——那不是修，那是藏。
- 未验证：CI（Linux/Windows）对本批 32 条新用例与 `check_entry_parity` 新分支的读数；
  本机 `make` 是 GNU Make 4.4.1 for Windows32，Linux 侧 make 行为未在本机复现。
- 未改动：任何 `app/**` 生产代码、任何冻结契约、他人并行会话的脏文件
  （`apps/web/pnpm-lock.yaml`、`packages/contracts/src/**`、`EVD-V2-02/**`、`任务规划V0.5.0/**`、
  `identity.schema.json`、`.q6.json`、`apps/api/.coverage` 等，一律未 stage）。
