# STEP-58 发布 v1.1.4 读数（执行助手，2026-10-27）

> 卡：`docs/任务规划V0.21.0/steps/STEP-58-发布v1.1.4.md`（依据 D-V21-18，流程与禁止项照 STEP-53）

## 1. 开工前置（现取）

- 队列前置满足：STEP-56 收口批 `52673f2` 与 STEP-57 交付批 `685e3f8`、收口批 `260a3a4` 三条均 attempt 1 全 success；
  逐字行见 `s58_0_preopen_ci_readings.txt`（含 `260a3a4` 上的 `2496 passed, 6 skipped, 4 deselected`、
  skip 门禁 `6=6 / pg_unreachable=0`、`Total coverage: 88.92%`、`✅ 全部模块与全局达标`、
  vitest `425 passed (425)`、e2e `31 passed`、@win `1810 passed, 692 skipped` 与
  `windows 门禁：failed=0 total_skipped=692 baseline=692`）。
- `git fetch` 后 `origin/main...HEAD` = `0 0`；`git rev-list --count v1.1.3..HEAD` = **7** ⇒ 发布批自身 +1
  ⇒ tag 指向的提交上是 8（本文件不抄发布批自己的 sha，自指规避）。
- 远端标签现读 **5 枚**（`git ls-remote --tags origin` 共 10 行 refs = 注释标签 + 其 `^{}` 行）；
  本地另有 2 枚从未推送的 `local-recovery-*` ⇒ 卡面那句「既有七个 tag 逐字不动」要对上的是**本地集合**，
  远端是 5 枚。这条差别按现读记在这里，不照抄卡面措辞，也不因此多动任何标签。

## 2. S58.1 独立复查（两份只读回报）

结论：**STEP-56 PASS-with-nits、STEP-57 PASS-with-nits**，无 FAIL、无 UNKNOWN ⇒ 卡面第 16 格阻塞条件
（"S58.1 出现 FAIL/UNKNOWN"）未触发。逐条判据、复查自己给的依据、以及它留下的 nits 全部记在
`s58_1_independent_review.md`（含我对每条 nit 的处置）。两份回报都被明确要求"不得为和谐而让步"，
且都自报了未验证面（CI 结论取自归档日志摘录、本机不重跑长命令）。

## 3. S58.2 CHANGELOG + AGENTS：本批自己的首轮审计（判 2 处 FAIL + 7 处精度）

发布段草稿先过了一轮对抗性事实核查（不读我的总结，只读仓库字节），**首轮判出两处 FAIL**：

| # | 抓到的 | 复核与处置 |
|---|---|---|
| F1 | 我把 22 条断言的行号写成 `:107` | 成立——`685e3f8` 给那个文件加了 7 行 docstring，现读在 `:114`。这恰好就是我这段 Fixed 里在讲的"行号会漂"，我自己踩了一遍。改成**只点测试名不点行号**，并把这条教训写进 `[Unreleased]` 注记与 AGENTS 的失真教训段 |
| F2 | 我照抄了 `EVD-V21-47/ERRATA.md` 的支撑"该测试文件只有一个提交" | 成立——`685e3f8` 之后现读 2 个提交、`f4f0261..HEAD` 不再为空；结论不受影响（`f4f0261` 那版 `:43` 仍是空行、`assert` 在 `:50`）。处置：CHANGELOG 里改成"当时可复算、本版已失真一处"的过去式，并在 `ERRATA.md` **追加一条带日期的订正**（不回改旧句）——见第 4 节越界申报 |
| N1 | 引用 D-V21-20 时没写"裁决文档正文尚未落档" | 成立——`decision-log.md` 现读止于 D-V21-19。CHANGELOG 与 AGENTS 两处引用都补上代录状态，避免读者去裁决文档找一个不存在的行 |
| N2 | "孤儿 0 与 P-126 登记时判的一致"把 21/34 也算进"登记时判的" | 成立——登记行只判过"shapes 30 个 def 全部可达、孤儿 0"；21 种子 / 34 def 是本卡现读。已分开写 |
| N3 | Changed 那条标题叫"两处**响应形状**判据" | 成立——它管的是 TS 产物导出位与冻结稿↔生成 schema 的名字集，都不直接看 HTTP 响应。改成"契约链上两处判据"并写明各管什么 |
| N4 | "旧判据是交集比对"说满了 | 部分成立——`97cc469` 那版**根本没有**名字集比对，只有"逐对探针"，而探针列表按两侧名字集的交构造 ⇒ 任一侧独有名整条静默。改成这个精确说法（复查自己核过 `git show 97cc469` 里无 `dnames|gnames`） |
| N5 | 覆盖率抖动清单里 88.92/88.94 被笼统写成"作废跑" | 一半反了：88.92 **也来自 STEP-57 收口批 `260a3a4` 的 CI**（本次现取），不是只有本机被取代的那跑。已逐个标出处，并把"计数三处两个 head 逐字相同、只有覆盖率在摆"这层区别写清 |
| N6 | "对外可见的变化只有一处"缺自查依据 | 复查替我核了：区间内不属于 `docs/**` 与 `apps/api/tests/**` 的改动只有 `service.py` 一个文件。把这句核法写进正文（v1.1.3 那次正是因为没写核法，被自己那段演示态改动推翻过） |
| N7 | 基线只写 `685e3f8`，读者会以为 tag 指向的提交上跑过这组数 | 成立——补一句：收口批与发布批都是零代码文档批，计数在它自己的 CI run 上逐字相同、覆盖率另读 88.92% |

改完之后 AGENTS 的版本块与 CHANGELOG 的新段是本轮唯一落盘的门面文字；两份都过
`scripts/check_docs_consistency.py`（rc 0）与 `guards.py guard-versions`（rc 0）。

## 4. 越界申报（卡面字段 9 之外的一行）

卡面字段 9 允许改的是「CHANGELOG、AGENTS 版本块、本卡证据」。本批还改了
`docs/06_validation/evidence/EVD-V21-47/ERRATA.md`——**只追加一段带日期的订正，旧句一字未动**。
理由：那段 ERRATA 的全部作用就是"登记读数的适用范围与失真"，而本版恰好让它自己的一条支撑失真了；
把这条留给下一次发现者等于在同一类缺陷上第二次不诚实。改动 2 段、纯文字，不碰任何代码或契约。

## 5. S58.3 tag + Release + 三绿（本批读数）

### 5.1 发布批三绿（这是打 tag 的前置，现取）

CI `40465549229` / CI-Windows `40465549197` / Security `40465549190`，三条都是 **attempt 1 且 success**，
逐字行见 `s58_ci_green_readings.txt`。关键读数：ubuntu 侧 `2496 passed, 6 skipped, 4 deselected`、
skip 门禁 `total_skipped=6 baseline=6 pg_unreachable=0`、`Total coverage: 88.93%`、`✅ 全部模块与全局达标`、
vitest `Test Files 53 passed (53)` 与 `425 passed (425)`、演示态 e2e `31 passed (1.4m)`；
@win 侧 `1810 passed, 692 skipped, 4 deselected`、`windows 门禁：failed=0 total_skipped=692 baseline=692`、
vitest 与 ubuntu 侧同 53/425；Security 侧四个扫描器逐字都是 `判定=ran` 且整条工作流 success（pip-audit 另有
`No known vulnerabilities found`）。

`88.93%` 与「计数不动、只有覆盖率在摆」这件事的关系写清楚：同一条 `2496/6/4` 在 `260a3a4` 上是 88.92%、
在 `685e3f8` 上是 88.91%、本机交付跑也是 88.91% ⇒ 本版三个文档批之间测试数逐字相同，覆盖率在两格里摆。
这正是 §3 的 N5 与台账 P-104 记过的抖动：可以拿它过线，不可以拿它当精确判据。两个 skip 基线都不动
（本版没有新增连库用例）。

### 5.2 tag 与 Release

- `git tag -a v1.1.4 -F <临时消息文件> c682acd` ⇒ **标签对象 `dd71da795b0e08a089d4e79d6e50842b5948f536`**，
  被标提交 `c682acd27284dce30d9b04b1b3631d9b24300259`；`git cat-file -t v1.1.4` = `tag`（注释标签，非轻量）。
  打之前 `git fetch` 后 `origin/main...HEAD` = `0 0`，HEAD 就是 `c682acd`。
- 推送逐字点名：`git push origin v1.1.4`，`push_rc=0`，远端回 `* [new tag] v1.1.4 -> v1.1.4`。**没用 `--tags`**。
- Release：`POST /repos/aideanew/BotHot/releases` → HTTP **201**，**Release id=425152771**；
  `GET /repos/aideanew/BotHot/releases/tags/v1.1.4` → HTTP **200**，`draft=False`，
  `published_at=2026-10-27T07:41:14Z`，`url=https://github.com/aideanew/BotHot/releases/tag/v1.1.4`。
  原文见 `s58_3_release_readings.txt`。

### 5.3 既有标签推前后逐字未动（对账）与一次自曝

对账文件（同目录，行尾都是 LF）：`s58_3_ls_remote_tags_{before,after}.txt`（10→12 行）、
`s58_3_show_ref_{before,after}.txt`（7→8 行）、`s58_3_tags_revlist_{before,after}.txt`（454→462 行）。
归一行尾之后的差异**只有新增行**：远端多 `v1.1.4` 的两行（标签对象 + 其 `^{}`），本地 `show-ref` 多一行，
`rev-list --tags` 删除 0 行、新增 8 行（v1.1.4 的祖先里此前没有任何标签可达的那 8 个提交）；
远端标签枚数 5→6，既有 5 枚的标签对象与被标提交逐字未动；两枚 `local-recovery-*` 仍只在本地、
从未推送 ⇒ 这就是"没有 `--tags` 全推"的实证，不是我的口头主张。

**自曝（记下来而不是抹掉）**：三个 before 文件当时由 `Path.write_text` 写出，行尾被 Windows 默认换行
翻译成 CRLF，而 after 用 shell 重定向是 LF ⇒ 直接 `diff` 报 `1,10c1,12` 这种整片不同，看起来像标签被大改。
处置与核实：对每个 before 做 `tr -d '\r'` 归一，归一前后各算一次 md5（去 CR 后的内容 md5 与整文件 md5 相等：
`78f5ff6ae999e2d48d7ab6eb405b5d41` / `197a40b9805987b0d78886e6f60fdcd6` / `0e639f43bf9785288625ea0ce9a3672d`），
所以归一动到的只是行尾，不是内容。判据没有变松，是我把两种行尾混进了同一个对账；下次同类对账两侧同机制写出。
读数与这段都归档在 `s58_3_push_and_census.txt` §4。

推标签不产生新 run：`ci.yml`、`ci-windows.yml`、`security.yml` 的 `on.push` 现读都只写
`branches: [master, main]`，没有一个带 `tags:` ⇒ 本版唯一的三绿锚点就是发布批那一条。这条不是沿用
STEP-53 发布 v1.1.3 时的结论，是重读这三个文件的触发块之后写的。

### 5.4 凭据口径（照实写，不沿用旧说法）

临时凭据在同一条命令内 创建→使用→删除→核实：`cred_written exists=True requested_mode=0o600
measured_mode=0o666 mode_is_600=False`、`cred_exists_after_rm=NO`、同前缀兄弟文件计数 0；
命令侧用 `-c credential.helper=`（先清空继承来的 helper）再挂本次专用的 `store --file=<临时文件>`，
并带 `GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never`；`git remote -v` 两侧 URL 无凭据残留。
"临时凭据 mode 600"这个历史说法在本机不成立（NTFS 上没有 POSIX 位），兑现的是存在时间压进一条命令 + 删后核实。

### 5.5 裁决落档与文字指向（本批按规划方 2026-10-27 指令新增）

- `docs/03_solution/decisions/decision-log.md` 追加两行：**D-V21-20**（P-127 判据③按等价满足通过 +
  冻结稿盖章权归规划方）与 **D-V21-21**（P-129 选出路③，STEP-57 只发投影，`MeWallet` 与产物维持开放，
  封闭那一半等冻结稿更新后另开卡，并在推翻记录列写明**部分取代 D-V21-17**）。两行的签字列都写明
  "规划方裁定（用户 2026-10-27 指令）/ 执行助手代录"。历史行一字未改，只追加。
- 台账 P-127、P-129 两条**裁定行**里"正文尚未落档"的代录者注记改成指向这两条裁决（按 ID 查，不抄行号——
  本版 Fixed 段刚记过行号会漂这个教训）；P-129 裁定行的归属列从"另开卡 + 把改判行落档"改成只剩"另开卡"；
  另**追加**一条 P-129 状态行写明"落档那一半已做掉、余项只剩①"。
- `docs/任务规划V0.21.0/04-剩余可执行大纲体系.md` 的必读面那句从「到 D-V21-19／到 P-126」改成
  「到 D-V21-21／到 P-129」。P-126 那半句同属这一行、且收口批会让它变成假陈述，所以一起改，改在这里申报。
- CHANGELOG 的 `[v1.1.4]` 段与 AGENTS 的「当前项目状态」版本块各有一处"正文尚未落档"标注，改成指向裁决日志。
- **一处刻意的不回改**：GitHub 上已发布的 Release 正文、以及 tag 指向的那个提交里的 CHANGELOG/AGENTS 文字，
  都停在"裁决尚未落档"的写作时点——落档发生在收口批，比 tag 晚。按规划方指令，**Release 正文不回改**，
  差别就记在本节；main 上后续提交里的门面文字才是指向落档后的状态。台账里 P-121 那行结尾与 STEP-57
  收口批那条 P-129 状态行的"待落档"字样按只追加纪律不回改，以本批新增那条状态行为准。

### 5.6 本批零代码改动的自证

`git diff --numstat` 只应命中：AGENTS 2/2、CHANGELOG 3/2、`decision-log.md` 2/0、04 的 1/1、
台账 3 处改写 + 1 行追加、STEP-58 卡面、卡表第 12 行、07 第 16 行与本证据目录。
`apps/api/app/**`、`packages/contracts/**`、`scripts/**` 与四个测试文件在提交前用同一条 `git status --porcelain`
现核为零命中——读数落在收口批的提交信息与本节，不靠"应该是零"。

