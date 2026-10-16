# S1.3.2 第十轮验证返工：判据的**量词**错了（拼块 / 行首 / 斜杠 / 单文件）

批次：`STEP-01` S1.3.2 返工（第十轮独立验证之后）。
基线：`main@5f04695`（我上一轮的九轮返工）。
执行者与验证者都是子智能体；读数标机器位（`@win` = 本机 Win10 + `apps/api/.venv`）。

---

## 0. 一句话

上一轮我补的两条判据（"引用必须说到 def+字段+事实类"、"新增必须真的收窄"）**都成立**，
但它们的量词写错了：`all(… over 拼接后的文本)`、`^` 行首形状、斜杠分隔、单目录扫描。
四个不同的地方都是同一个错误——**把"每条裁决各自成立"实现成"要素在某个大字符串里都出现过"**。

## 1. 验证交了什么 → 我的处置

| 条目 | 验证的实测 | 处置 | 状态 |
|---|---|---|---|
| A1 引用洗白 | 引**两条各自不相干**的号（`D-V8-04` 供 def+`sub`、`D-V8-06` 供事实词 `pattern`）⇒ 拼块后要素齐全，`tightening/strictness/conflict` 三种 kind 全读 **0 条差异** | `_cited_ledger_rows()` 保住行边界，`citation_covers` 的量词改成 **exists 一行**：同一行必须同时说到 def、字段、事实类 | 已修，复跑 1 条差异（三种 kind） |
| B1 `format` 恒真 | `_is_noop_invention("format", "x-unasserted")=False`，而 2020-12 里未识别 `format` 只是注解 ⇒ 接受集不变的"新增"被放行 | `format` 一律算恒真：稿没声明的 `format` 不是约束，任何 kind 都不为它放行 | 已修，复跑 1 条差异 |
| C1 两行空打断 | 连续**两个**空行绕过 `_table_interrupts`（那版要求空行的下一行直接是 `|`） | 改判"空行游程"：向前/向后找最近非空行，中间有任一空行即打断 | 已修，构造反证 `True` |
| C2 编号列失明 | 给台账加一列编号 ⇒ 列数与粘行两条守卫**同时**抓不到，而 `live_decision_ids()` 仍把被吞掉的号算 live | 新增 `_decision_rows()`（第一格必须是裸号）+ `_invisible_decision_ids()`（被提到却没有规范登记行的号）；`live_decision_ids()` 改为只认前者 | 已修，复跑 `['D-V8-05']` |
| D1 旧错数仍活 | 守卫只认斜杠、只扫 `docs/任务规划V0.12.0/**`、不扫 `.py` ⇒ 逗号形式活在证据文件里、`app/contracts/*.py` 植进去两条全绿 | 正则改 `(?<!\d)10[^\d\n]{0,4}13[^\d\n]{0,4}34(?!\d)`，扫描面扩到 `docs/**` 全部 md + `app/contracts/*.py` + 本测试文件自己 | 已修，仓库内该三元组已 0 命中 |
| E 回归 | 未发现；166 条与代码一致 | — | 已确认 |

## 2. 我自己的探针也算错过一次

`.staging/probe_r10.py` 末段打印 5 行 `NEW-RED`（声称若干现网登记会被新判据打红）——那是**探针写错**：
它把 `entry.ref` 整串当 def 名、又把 `path` 传成占位符 `"x"` 塞进 names。
真实判据用逐处 `def_name` 与真实 path，现网 3 个走该档的位置全部仍然通过。
权威读数是永久测试 + `compare_defs` 的四域 0 条，不是我的探针输出。

## 3. 读数（全部 `@win`）

- `pytest tests/test_collection_contract.py -q` → **169 passed in 3.15s**（本批前 166，+3 条反证）
- `pytest tests -q -k "contract or gen_contracts"` → **171 passed, 1 skipped**
- `.staging/probe_r11.py` 复跑第十轮四条注入：
  `A1 kind=tightening/strictness/conflict 差异数=1/1/1`、`B1 format 差异数=1`、
  `C1 两行空打断=True`、`C2 编号列不可见号=['D-V8-05']`、`D 现网四域未解释差异=0/0/0/0`
- `ruff check tests/test_collection_contract.py app/contracts` → `All checks passed!`

## 4. 这条卡的真实状态（不粉饰）

D-14 的熔断对本卡已成立 **10 轮**（机械门 `git log --grep="轮" --format=%s main | grep -c STEP-01`
在 `main@5f04695` 现读 **10**；本轮的提交信息会把它推到 11）。
本轮验证者的结论与我在第八轮的判断同向：**这不是十个 bug，是一类**——
只要语义由我自己实现，判据就只能绑在我的实现上，每轮换个量词就能再穿一次。
`D-V8-05`（BLOCKING，**未签**）提的正是把这件事停掉：校验语义交给标准库 `jsonschema`，
自研比对器退役成"差异登记表 + 覆盖率守卫"。它不自动生效，需要 owner 签字。

我**没有**做：不替 owner 签这条；不在本轮引入 `jsonschema`（那属于 D-V8-05 的 A 案，签了才动）；
没有跑全量后端套件复验（DB 面本机无 PG，连库用例只会 skip）。
域面继续按"每条不等必须有登记、登记必须有责任人"推进——这条判据是可机械核对的，
与"注入必红"不是同一件事。
