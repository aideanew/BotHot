# EVD-V18-34 门禁判据精度修正（执行助手）

平台 @win（Windows 10 x64，Git Bash，`apps/api/.venv` Python 3.12.10），开工 head `7e4c10e`（STEP-42 收口批），
时间 2026-10-23 深夜～10-24 凌晨（Asia/Shanghai）。卡面 = `docs/任务规划V0.18.0/steps/STEP-34-*.md` + V0.19.0 增量 S34.7/S34.8。
本机无 docker、5547 无监听 ⇒ 连库面未在本地复算，以 @ci 为准（沿用 AGENTS.md 10-23 口径）。

卡面锚点核对（开工现读）：`scripts/guards.py` 的 `rounds_violations` 实测在 :241 ✅（与卡面 :241 一致，零漂移）。

## S34.1 `open(` 判据锚到调用形（P-100）

- 改前读数（假阳，现测）：裸 grep `grep -rn "open(" scripts | grep -v encoding=` 命中 **7**——P-100 记的 `_enclosing_open(` 定义与调用 2 处 + 本卡自己在 guards.py 里写下的判据说明文字 5 处；P-100 建议的锚定 grep `(^|[^_[:alnum:]])open\(` 命中 **5**（全在注释里，且它挡不住 `f.open(` 形属性访问）。
- 判据实体：`guards.py::open_call_violations`（tokenize 只认调用形：NAME `open` + `(`，前 token 非 `.` 非 `def`/`class`；注释与字符串天然排除；`encoding=` 按行判；tokenize 失败 fail-closed）。
- 常驻面：`tests/test_guards_open_call_form.py` 7 用例全绿（真调用红 / 函数名不红 / 属性不红 / 注释不红 / 带 encoding 绿 / 定义与引用位不算 / 真仓 `scripts/**/*.py` 扫描零违规）。
- 变异读数（P-100 出门判据）：临时加 `scripts/_s341_mutation_tmp.py`（一行不带 encoding 的 open）⇒ 真仓扫描用例 **红**（计数 0→1）；删除 ⇒ 复绿（0）。前后两数在案：0 → 1 → 0。

## S34.2 rounds 按最大轮号 + 持签逃生口（P-56 / P-85 / D-V18-16）

- 改动：`rounds_violations(subjects, max_rounds, decisions)`——按卡归集后取**显式轮号最大值**，>2 才熔断；裸"返工/重做"（无轮号）只归属不计数；任一主题携带**台账里登记过**的裁决号（`registered_decision_ids` 现读 decision-log.md，左右边界与 P-57 同族）⇒ 该卡放行。`decisions=None` 时逃生口关闭（fail-closed）。
- 先红（stash 旧 guards.py 跑新测试）：8 条新/改用例在旧实现上全红——含 P-85 形状（五片"第 1 轮"被判熔断）、跨步泄漏放行、OUTPUT 通道不可见、边界缺失。还原后 73 passed。
- 回放（V0.17.0 真实主题，全文见本目录 `s34_2_replay.txt`）：
  ① STEP-15b 五个真实分片主题 ⇒ **[]（不熔断）**（旧口径 5 > 2 ⇒ 判熔断，CI run 39728297911 的真实红）；
  ② STEP-07 第 3 轮、不带 D 号 ⇒ **熔断**（点名 STEP-07、max_round=3）；
  ③ 同一事实携带 D-V17-04（台账现读在登记，全集 121 号）⇒ **放行**；
  ④ D 号未登记（D-V99-99）⇒ 逃生口关闭，仍熔断。
- 常驻面：`tests/test_guard_rounds.py`——改 2（`test_rounds_gate_counts_rework_token_without_round_number` 改判新语义并更名；end-to-end 第 3 轮改带显式轮号并断言"最高第 3 轮"）、新增 4（分片五片不熔断 / 持签放行+未签不放行 / 中文数字边界照旧 / 台账号左右边界）。

## S34.3 台账门裁决号左右边界（P-57）

- 改动：`test_collection_contract.py` 三处同族模式 `D-V\d+-\d\d` 补 `(?<![A-Za-z0-9-])…(?![0-9])`（`_invisible_decision_ids`、`cites_live_decision`、区间守卫的 ledger_ids）。
- 先红：两发新用例在旧模式上**双红**（`EVD-…/EVD-V8-07/` 目录名被读成裁决号 D-V8-07；目录名引用买通 `cites_live_decision`）。
- 改后：`pytest tests/test_collection_contract.py` ⇒ **185 passed**（含两发极性：目录名形态绿、裸未登记号仍红）。

## S34.4 需求侧验收锚进 check_docs_consistency（P-108）

- 判据：语料 = `docs/02_requirements/**` + `AGENTS.md`（现读 **15 份**）；根路径文件锚（apps/ scripts/ docs/ packages/ .github/ 前缀）按 **HEAD blob**（`git ls-tree -r`）判存在；裸名/半路径写法对语料锚全集、再对 HEAD 全集做基名/后缀兜底解析（两处都不中 ⇒ 写法不齐/编造）；`文件::符号` 在候选文件体里按 `def`/`async def`（py）、`it(`/`test(`/`describe(`（ts）判定义。零锚 fail-closed；git 不可用 fail-closed。
- 现读：**133 处根路径锚全命中、0 断链**（STEP-12 一次性对账的常驻化，`--verbose` 可列非根写法解析）。
- `--self-test`：5 发极性全 OK（真实文件/符号/裸名兜底通过；编造符号点名；编造文件点名；解析不到的裸名点名；零锚语料报"解析器与文档格式脱节"）。
- 变异（卡面判据）：把 REQ-F-001 里的一个真实锚临时改成 `test_no_such_mutation.py` ⇒ 门红且点名；还原 ⇒ 复绿。
- 盲区（如实写明，与探针 §3 同源）：① 用例"今天是否真跑"不判（skip 门管的）；② `test_x[case]` 参数化形态与 ts 引号符号形态不匹配符号正则，不计入符号锚。

## S34.5 make/entry 对等的 Linux 半边（P-101）

- 改动：ci.yml backend job 新增步 `make/entry parity (6 tasks, zero/non-zero)`（在迁移往返步之后 ⇒ `make migrate` 幂等 rc=0），对 @win 复算表的同一组 6 任务（dev / lint-backend / guard-ports / fmt-check-backend / docker-ps / migrate）跑 `make X` 与 `python scripts/entry.py X`，只比**零/非零一致**（make 把工具失败折成 2，entry 的 3=工具缺席，都算非零）。
- 本机 @win 复算（同一循环，修完 entry 接线后）：dev 0/0、lint-backend 0/0、guard-ports 0/0、fmt-check-backend 2/1、docker-ps 2/3、migrate 2/3——六发全一致，循环 rc=0。
- 过程抓到并修正一个真接线 bug：entry 的 scripts 工具步路径写成 `../scripts`（从 apps/api 出发不存在）⇒ lint-backend 1/2；改 `../../scripts` 并注明 cwd 必须留在 apps/api（ruff 的行宽 120 配置在那里，从仓库根跑会退回默认 88 ⇒ 假红）。
- 常驻面：`tests/test_workflow_gate_wiring.py`（步存在、任务表 6 个齐全、零/非零比较逻辑、entry 实跑 rc=0）。

## S34.6 faulthandler 转栈值 < 杀值（P-54）

- 改动：ci-windows.yml Backend tests 步 `-o faulthandler_timeout=120` → **100**（`--timeout=120` 不动），注释更新为"S34.6 已解 P-54 竞态"。
- 为什么必须更小：卡死用例先在 100s 被 faulthandler 把全部线程原始栈写进日志、120s 才被 pytest-timeout 杀掉——"先留栈再被杀"的时序保障成立；同阈值时两把闹钟同秒触发，谁先落地不确定（P-54 原案发现场）。
- 常驻面：`test_workflow_gate_wiring.py::test_faithhandler_stack_dump_value_is_smaller_than_the_kill_timeout`（直接比数值，写反即红）。

## S34.7 掩码守卫 job 级 + GITHUB_OUTPUT（P-109 / D-V19-05）

- 改动：`ci_mask_violations` 的"已生成/已掩码"两个集合从**每步**改为**每 job**（`_workflow_jobs` 新解析器：job id = `jobs:` 段缩进恰 2 的键，状态位排除 `on:` 段同名形态）；sink 正则扩为 `GITHUB_(ENV|OUTPUT)`；`_written_vars` 排除两个目的地；点名格式改为 `job/step`；guard 的零可检面口径同步为 ENV+OUTPUT（两者皆零 ⇒ rc=3）。
- 先红（stash 旧实现跑新测试）：`test_cross_step_generated_value_without_mask_is_red`、`test_github_output_write_of_generated_value_is_red_and_masked_is_green` 等 8 条在旧代码上红（旧口径放行跨步泄漏、看不见 OUTPUT）。
- 改后：`tests/test_guards_ci_secret_mask.py` **73 passed**（连同 rounds 一起数）——含新五发：跨步未掩红、跨步已掩绿、OUTPUT 未掩红/掩过绿、`${{ }}` 与常量写 OUTPUT 仍绿、**job 间隔离**（A job 生成、B job 写 ⇒ 不牵连，这是"job 级"而非"全文件"的极性）。
- 真仓面：`test_real_workflows_pass_the_gate`（现读全部工作流零违规）与 `test_deleting_the_mask_lines_from_ci_yml_turns_the_gate_red`（删掩码行 ⇒ 恰 2 违规）在新实现下复跑均绿。
- 已知边界（docstring 同文）：`${{ }}` 表达式、三层以上复制、`{ 多行; } >> $GITHUB_OUTPUT` 块写法（值行与 sink 行分离）不在判据内——现读全仓零处该写法。

## S34.8 先清零再扩门（P-110 / D-V19-06）

- 清零前底数：`mypy ../../scripts` **8**（guards 3：attr-defined/union-attr/call-arg；entry 2；security_scan 1；audit/p39_reencrypt 2）、`ruff check ../../scripts` **10**（5 文件）。
- 清零内容：guards（TypedDict `RoundViolation` 消 attr-defined；`GUARDS: dict[str, Callable[..., int]]` 消 call-arg；reconfigure 改 getattr 守卫；E501 折行）、entry（`found: list[Path]`、循环变量改名消 str/Path 重绑、reconfigure getattr、E501）、security_scan（Callable 改 collections.abc 导入、reconfigure getattr、E501）、check_module_coverage（% 格式改 f-string）、check_entry_parity（`l` → `line`）、p39_reencrypt（`fetchone()` None 守卫——count 行缺行记 -1、回读缺行显式 rc=2，语义不变）。类型/格式之外无判据语义改动。
- 清零后：`mypy ../../scripts` = **Success: 11 files**；`ruff check ../../scripts` = **All checks passed!**。
- 扩门（独立一批，本机已绿）：ci.yml 与 ci-windows.yml 的 Lint/Type 步加 `../../scripts`；entry.py `lint-backend` 加 ruff `../../scripts`、`typecheck-backend` 加 mypy `../../scripts`（cwd 留 apps/api 吃 pyproject 配置）。
- 反证：临时放 `scripts/_s348_mutation_tmp.py`（未用 import）⇒ `ruff check ../../scripts` **3 errors（红）**；删除 ⇒ 复绿。另有一次自然反证：本卡自己的 `test_workflow_gate_wiring.py` 初稿留了未用变量，被扩出来的门当场咬红——门的召回是真实的。
- 扩门后读数：`ruff check app tests ../../scripts` All checks passed；`mypy app ../../scripts` = Success: no issues found in **132** source files；`entry.py lint-backend` / `typecheck-backend` rc=0。

## 本机全量（连库面缺位声明）

`pytest tests/ -q -rs`（无 PG）⇒ **1 failed / 1679 passed / 666 skipped / 4 deselected**。skip 666 = @win 基线值，pg_unreachable 形态 0（全部是 `AIDEANBOT_TEST_PG_DSN 未设置` 记账型）。唯一失败 = `test_log_redaction.py::test_http_status_error_url_in_warning_is_redacted[console]`——**P-114 已登记的本机 venv rich 污染**（CI 无 rich ⇒ 绿），非本卡改动所致。连库面与最终判定以 @ci 为准。

## rebase 说明（2026-10-24）

本批开发期间规划方推入了三个提交（STEP-43 修 P-114 + 新登记 P-115「生产 JSON 日志无栈」、STEP-45 冻结时钟修覆盖率门红、V0.20.0 规划）。本批 rebase 到 `e862b3a` 之后全量复验：守卫相关 6 个测试文件 **103 passed**（含规划方新用例共存）、`ruff check app tests ../../scripts` 与 `mypy app ../../scripts`（132 文件）、docs 一致性、rounds-check、guard-ci-secret-mask 全绿。编号收敛：本批文档初稿曾把覆盖率门红登记为 P-115（与规划方撞号），最终以 **P-116** 为准（见 P 表与 07 记录第 7 行）。§本机全量 里那条 console 用例失败读数是 rebase 前的历史读数——规划方 STEP-43 已把 console 栈固定为纯文本不展示局部变量，rebase 后该用例在本机（rich 在场）也绿。

## @ci（推送后回填）

_（占位：交付 head 三条工作流 run id 与结论、attempt 号；CI 日志里 S34.5 parity 步的 6 行输出。）_
