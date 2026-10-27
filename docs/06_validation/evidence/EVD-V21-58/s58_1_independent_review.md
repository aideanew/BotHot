# S58.1 独立复查（发布门，两份只读回报，2026-10-27）

卡面要求：STEP-58 的独立复查对象是 STEP-56 与 STEP-57，**任一 FAIL 或 UNKNOWN 就不发版、交回**。
两份回报由两个互不知情的只读子智能体各自给出，判据逐条附字节证据；两份结论都是
**PASS-with-nits**，无 FAIL、无 UNKNOWN ⇒ 发版门开。

- 复查方式：只读（`git log/show/diff` 与文件读），不跑套件——本机门链与 CI 都在跑，
  跑长命令会同时污染两侧读数（这条纪律本身是 STEP-55/56 那两次作废读数换来的）。
- 两份回报的完整判断都记在本文件下面，未删任何一条 nit。

## STEP-56（交付 3b462d4，收口 52673f2）：PASS-with-nits

| 判据 | 结论 | 复查给的依据 |
|---|---|---|
| ① 加孤儿 def ⇒ 新守卫红、旧门全绿 | PASS-with-nits | 两种形都在：字面形 ①a 新守卫红（`s56_1a_newguard_red.txt:16` = `1 failed, 10 passed`）**且旧比对器也红**（`s56_1a_oldgate_collection_red.txt:14,32-34`）；①b（同一个 def 也写进冻结稿）才是「只新守卫红、其余全绿」（`s56_1b_oldgate_collection_green.txt:5` = 220 passed、`s56_1b_nameset_gate_green.txt:3` = 82 passed）。账本 P-126 闭合行与 07 第 11 行转述的是这个区分，没有把①a 那次藏掉 |
| ② 删两条引擎反向核 ⇒ 新守卫红 | PASS | `s56_2_engine_live_deleted_newguard_red.txt:50-53` = `3 failed, 8 passed`，三条红分别报四条孤儿、整域失去覆盖、以及锚点随用例消失的那条反证 |
| ③ 判据③触发即不放宽 | PASS | `git diff 97cc469 3b462d4 -- apps/api/tests/test_contract_jsonschema.py` 是**纯新增**（97 增 0 删），旧的交集判据本体没动；P-127 已登记（`00-README.md:215`），裁定行在 `:217` 且明写「decision-log 里 D-V21-20 那一行尚未落档」——复查确认该文件确实止于 D-V21-19，所以这句是自我披露而不是偷偷盖章 |
| ④ 全量 + 三绿 | PASS | `s56_ci_green_readings.txt:3-25` 三条 attempt 1 全 success 且数字与账本/07 引用一致（ubuntu 2488/6/4、skip 6=6、88.91%、vitest 53/425、e2e 31；@win 1802/692、failed=0） |
| 范围 | PASS | 新守卫 11 条（2 正面 + 9 反证）、只 import ast/copy/json/pathlib/typing，`db_session` 只作为 AST 里的字符串出现 ⇒ 零连库；`git diff --stat 97cc469 3b462d4 -- apps/api/app packages/contracts scripts apps/web` 为空；收口批 8 个文件全在 docs/ 下 |

复查留下的三条 nit 与我的处置：

1. **交付批提交信息里说「字段 6 的范围冲突在卡面与 §5 明写」——卡面并没有这段文字**（复查 grep 判定）。
   真实情况是只在 `s56_readings.md` §5 与 §8 披露。按纪律**不回改已归档的提交信息**，
   这条更正记在这里（与 STEP-56 处理 `EVD-V21-47` 行号漂移同一个口径）。
2. **`EVD-V21-47/ERRATA.md` 的第①②条读数已经过期**：那条说「`git log --all -- <测试文件>` 只有 1 个提交」，
   而 STEP-57 的 685e3f8 又碰过这个文件 ⇒ 现读 2 个。承重的第③条（`f4f0261` 的 `:43` 是空行、assert 在 `:50`）
   仍然成立。处置：在 ERRATA 里**追加一条带日期的订正**（不删旧句），并在 STEP-58 发布批里作越界申报
   ——那份文件的作用本来就是登记读数适用范围，留一条已经失效的读数不比加一行更诚实。
3. `decision-log.md` 里 D-V21-20 仍未落档（STEP-57 复查也点了同一条，见下）。这条**不由执行侧补**，
   但它有一个发布面上的后果：CHANGELOG 里凡涉及"契约是否封闭"的措辞都必须按 P-129 出路③ 写，
   不能跟着裁决文档的旧正文走。

## STEP-57（交付 685e3f8，收口 260a3a4）：PASS-with-nits

| 判据 | 结论 | 复查给的依据 |
|---|---|---|
| 1 投影本身 | PASS | `service.py:50-82`：白名单恰是卡面五键；返回式 `{k: raw[k] for k in _WALLET_KEYS if k in raw}` ⇒ 没给的可选键保持缺席、不补 0；非字典与「必填缺失或值为 `null`」都回降级形且不抛；`sorted(str(k) …)` 把混合键型那条 `TypeError` 堵掉。三条 `/me` 分支同源（`:252`、`:280`、`:297`）。全仓 grep 只剩 `providers/aidean/client.py:156-171` 造 wallet、且只被 `get_me` 消费，路由层不合并字段 ⇒ **没有第二条透传路径活着** |
| 2 用例 | PASS | 8 条 = 1 集成 + 7 纯函数，全部不连库（`_svc_bundle` 用内存桩、`TestClient` 不进上下文管理器 ⇒ 无 lifespan 建连）；每条都钉一个不同的变异，没有"永不可能红"的那类；"值不许进日志"判的是整批 `events` 而不是单条 |
| 3 范围 | PASS | 交付批只碰 `service.py` 与三个测试文件（第 4 件是第 1 轮那处越界，已随退回消失）；`git diff 52673f2 260a3a4 -- shapes.py / shapes.schema.json / apps/web 那条 spec / 冻结稿` **为空** ⇒ 第 1 轮的两处越界申报确实撤回了；收口批零代码 |
| 4 措辞诚实 | PASS | 账本 P-121 状态列写的是**部分闭合**并明说"不写成本行闭合"；没有任何一处说契约 def 已封闭或 s55 门会判钱包多键；两处残留（可选键显式发 `null` 会原样带出、`data` 是列表时 `AttributeError` = P-128 已复现并登记）都在裁定行、判词与 07 里出现 |
| 5 数字可追 | PASS | `2496/6/4`、skip 6=6 且 `pg_unreachable=0`、CI 覆盖率 88.89%、vitest 53/425、e2e 31、@win `1810/692` 且门禁 692=692 全在 `s57_ci_green_readings.txt`；本机 run4 十五步 rc 全 0、`TOTAL 88.91%`、链首尾字节指纹同值；run3 改名 superseded 并写了字节级理由；`2488+8=2496`、`1802+8=1810` 对账通过 |

复查点出的两条 nits（都归规划方，本卡不自己动）：

1. `decision-log.md:158` 的 D-V21-17 正文仍写「`MeWallet` 改封闭」，而实际按 P-129 出路③ 只发了投影；
   D-V21-20 与这条改判在裁决文档正文里都还没有行 ⇒ **在它们落档之前，权威裁决与已发布事实是矛盾的**。
   执行侧的处理是不去替规划方写裁决正文，而是在 CHANGELOG 与账本里按出路③ 的口径写，并把这件事
   在发布证据里显式记一条（本节）。
2. 冻结稿 `x-invariants` 第 8 行「MeWallet…本仓不控键集合，故开放」现在成了"被代码否证的旧声明"——
   这正是那张被定期的后续卡该处理的东西，本发布不动稿。

## 发版判据

- 两条卡的复查结论均为 PASS-with-nits ⇒ 卡面 S58.1 的「任一 FAIL/UNKNOWN 不发版」条件满足。
- 两份回报都注明"CI 状态取自归档的 run 级日志摘录、本机不重跑长命令"，这属于本轮方法的边界，
  不是未核项；三绿的直接读数在 `s58_0_preopen_ci_readings.txt` 与本目录 readings 里现取。
