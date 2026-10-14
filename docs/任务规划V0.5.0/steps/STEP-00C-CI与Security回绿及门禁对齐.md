# STEP-00C CI与Security回绿及门禁对齐

| 项 | 值 |
|---|---|
| 里程碑 | M0 |
| 档位 | sonnet |
| 规模 | 小（约 0.5 人日） |
| 依赖 | — |
| 裁决 | D-12（默认 A）、D-11（默认授权） |
| 剩余原子任务 | 现算：`grep -cE '^- \*\*S0C' <本文件>` 是三级总条数，`grep -E '^- \*\*S0C' <本文件> \| grep -c '已交付'` 是本卡里**已交付**的条数，两数之差就是剩余。**口径要说清**（第十五轮 F 组）：本卡 §4 图例里的 ✅ 是**任务类型**（验证/读数），不是完成状态——所以「带 ✅」在本卡**不能**当已交付读，交付与否只认「已交付 `提交号`」这个标记；STEP-02 那张卡的 ✅ 却是交付标记，两张卡口径不同，统一它属 STEP-12 文档对账 |
| 所有权（写） | W：apps/api/tests/test_chat_sse.py、test_env_isolation.py、test_kb_longlink_ingest.py；docs/06_validation/evidence/EVD-V2-00R/prove_net_isolation.py、out_evidence_check.txt；.gitleaksignore（新）；Makefile；scripts/（g24/evidence-check）；.github/workflows/ci.yml（仅 SKIP 相关注释与阈值） |
| 基线 | main@65f508b |

## 1. 目标与可证伪验收
- CI 与 Security 两条 workflow 在推送后均 success（打破 15 连红），run id 入 EVD-V2-00C。
- 本地门禁与 CI 同口径：本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 是 Done 的必要条件，`make evidence-check` 缺工具时打印 SKIP 而非 PASS。
- CI 下游 7 步首次运行即通过，且 skip 留出 ≥1 条余量（当前 6 = 基线 6）。

## 2. 证据链（现状）
- ruff 4 错：test_chat_sse.py:8、test_env_isolation.py:23、test_kb_longlink_ingest.py:28（I001），test_env_isolation.py:68（E501 134>120）——`evidence/65f508b/ruff_65f508b.txt`。
- gitleaks main 历史 6 条（1af68fc×3、1470b77×2、de78125×1），工作树 5 处——`gitleaks_65f508b.txt`。
- CI 失败于 backend `Lint (ruff)`，其后 7 步 skipped；Security 汇总门禁因④失败——`ci_runs_65f508b.txt`。
- 补丁 `STEP-00C_simulated_65f508b.patch` 在 65f508b 实测：ruff 0 错、gitleaks 0、证明脚本 24/0、`git apply --check` rc=0。
  这份副本按 `05` §5 的第 2 批口径**没有进仓库**（它自带 `x:y@` 邻接形，推进 main 会给正红着的 Security
  门禁再加检出项）；执行方按 `gitleaks_65f508b.txt` [C] 重做同一组改动即可，做完后那个提交的 diff 就是第 2 批的存档件。
- skip 构成：LangBot×2、Redis×3、宿主无代理×1（test_env_isolation.py:74）——CI 环境同样无 Redis/LangBot/代理变量 ⇒ 预计 6 条 = `SKIP_BASELINE`（ci.yml:120）。

## 3. 执行逻辑穿透
推送 → ci.yml backend：install → ruff(:67) ✗ → [mypy(:71) → alembic(:75/:83) → contracts(:97) → docs(:104) → pytest+cov+skip gate(:118-173)] 全部 skipped。
推送 → security.yml：①pip-audit ②pnpm audit ③trivy ④gitleaks detect(--source . --config .gitleaks.toml，fetch-depth 0) → 汇总(:504) ✗。
gitleaks 默认读取仓库根 `.gitleaksignore`（指纹 = commit:path:rule:line），因此逐指纹登记只豁免这 6 个历史位置，后续任何新增同类串仍会被拦。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红（写失败测试）｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### S0C.1 ruff 回绿
- **S0C.1.1** ✅🛠 已交付（`e6f7de5`）｜`ruff check --fix` 修 3 处 I001（只动 import 块）——本机没有 ruff，落点方式改成
  **照抄实测通过的形状**：`evidence/65f508b/ruff_65f508b.txt` 给出三条 I001 的位置，
  `evidence/65f508b/STEP-00C_simulated_65f508b.patch`（那份副本按 `05` §5 第 2 批口径不入库，是有意未跟踪件）
  是 ruff 0.12.12 实跑 0 错的**目标形状**，逐条搬到当前代码上：
  `test_chat_sse.py:18` 与 `test_env_isolation.py:28` 是 from-import 的**成员序**
  （`_PG_URL_SOURCE` 先于 `PG_URL`：ruff 的 `order-by-type` 把常量归一组、组内按小写名，`_` 排在字母前），
  `test_kb_longlink_ingest.py` 是 `import pytest` 与 `from fixtures.wechat_urls` 之间那句空行。
  - S0C.1.1.1 ✅ 本机不可执行 `ruff check --fix --select I001` ⇒ 改为按上面那份补丁的形状手工落地，
    改前/改后形状由 `EVD-V2-00C/collect_ruff_shapes.sh` 第 4 节现打（不抄进本卡）。
  - S0C.1.1.2 ✅ 仅 import 行变化的核对：`git show --stat e6f7de5` 里三份测试文件各 1–2 行；
    生产代码零改动（现读同一条命令的 `-- apps/api/app` 段为空）。
  - **本条真正的根因不在那三个文件**：本机那张 stdlib 近似表（`EVD-V2-00/g24_static_check.py`）把
    `conftest` 划成第一方、又用一份手抄 stdlib 名单（漏了 `hmac`/`binascii`/`html`/`fnmatch`），
    于是它在 **ruff 全过的文件上**报出 12 条 I001（现读：`bash …/collect_ruff_shapes.sh` 第 1 节），
    而 ruff 真报的那三条（成员序 + 同段空行）它**一条都看不见**。那两条「挂了五轮修不掉」的 I001
    从头到尾是本机门禁自己造的假红——要改的是判据，不是被测文件。已改：段表换成
    `sys.stdlib_module_names` + 「`apps/api/` 下确有其物才算第一方」+ 相对导入算 local-folder，
    并补上成员序与同段空行两判；自证同时加**绿档**（实测通过 CI 的形状不许被咬）。
- **S0C.1.2** 🛠 **上一版把这条标成已交付，是错的**（第十六轮自查）｜`test_env_isolation.py:68` 的 E501
  - 上一版写的是「已完成于本批之前：现读该行 112 列（≤120）」——**那 112 是字符数，而 ruff 的 120 是列宽**：
    East Asian Width 为 `W`/`F` 的字符占 2 列。同一行按列宽是 134，正是 `evidence/65f508b/ruff_65f508b.txt`
    报的那一句 `E501 Line too long (134 > 120)`。锚点核对（现读，两条一起看）：
    `python -X utf8 -c "import subprocess,unicodedata;t=subprocess.run(['git','show','65f508b:apps/api/tests/test_env_isolation.py'],capture_output=True).stdout.decode('utf-8');l=t.splitlines()[67];print(len(l), sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in l))"` （**锚 `65f508b` 才读得到 112/134**：那一行后来被折成三行，今天同一行号读出来是 `38 38`、全文件最大列宽 102——那是修法生效的痕迹，不是锚点错了。第十六轮复核 C4 抓的是「命令指向改后的文件、句子宣称的却是改前的读数」，与 06 条 17「指错的复现命令比没有更糟」同一族）
    ⇒ 那一版给 `112 134`；两个数分别是「字符」与「列宽」，只有后者与 ruff 可比。
  - 根因不在这条用例，在**本机那张近似表**：`EVD-V2-00/g24_static_check.py` 的 E501 按 `len(line)` 计，
    所以它对 CJK 撑爆的行一律假绿。本卡 §4 与 G 段门禁（EVD-V2-02 留档的 G 段）都读它，
    于是「本表 0 违规」这句话当时是**更宽**而不是更严——这一点也写进了该表的 docstring（两处方向性差异，
    ①pragma 侧本表更严、②单位侧本表曾更宽，已修）。
  - S0C.1.2.1 🛠 近似表改成按列宽计（`_width()`：`east_asian_width in "WF"` 记 2 列），自证同时补
    「只有按宽度才报」的正样本与 120/121 的 ASCII 边界对（现读：`python …/g24_static_check.py --self-test`
    末行「N/N 项判据两端都对」的 N）。
  - S0C.1.2.2 🛠 按新单位重测，CI 射程 `apps/api` 内抓到 2 行、本证据包内抓到 7 行，这九行同批折行；
    折完现读：`python docs/06_validation/evidence/EVD-V2-00/g24_static_check.py <那九份文件>` 报
    「合计违规 0 条」。
  - S0C.1.2.3 ⛔ `ruff check app tests` → All checks passed 仍是 **CI 的读数**，本机没有 ruff；
    登记为 S0C.5.1 的一部分，不写成本地通过。
- **S0C.1.3** ⛔ **本机的 ruff/mypy 读数至今没有**（上一版这格标 ✅ 且写「本地 0.12.12 …」，那是**错的来源标注**：
  0.12.12 那四条红来自 `evidence/65f508b/ruff_65f508b.txt`，是一份在**有依赖的环境**里采集的入库件，
  本机既没有 ruff 也没有 mypy，把它的读数写成「本地」等于给不可证的东西盖了个可证的章）
  - 现读证明本机没有这两个工具：`python -c "import ruff"` 与 `ruff --version`、`mypy --version` 三条都
    `command not found` / `ModuleNotFoundError`（本机按约定不装依赖，见 `00-README.md` 的环境事实）。
  - 本机有的只是**替代读数**：`EVD-V2-00C/out_ruff_shapes.txt`（近似表改前/改后 + 两端自证 +
    两处方向性差异——①pragma 侧本表更严，②单位侧本表曾按字符数计而更宽，见 S0C.1.2）。
  - 真正的 ruff/mypy 终判仍挂在 S0C.4.3（人工 venv）与 CI；这一格在两者出数之前不许回到 ✅。

### S0C.2 Security 回绿
- **S0C.2.1** 🛠 工作树占位 DSN 去口令：`x:y@` → `x@`（prove_net_isolation.py:702/705/1214/1219、out_evidence_check.txt:137）
  - S0C.2.1.1 替换后复跑 prove_net_isolation.py，PASS=24 FAIL=0
  - S0C.2.1.2 `gitleaks dir` 对这两个文件 0 命中
  - **同案未清的一格（第十六轮复核 C7 抓到）**：那四处 `x:y@` 从在册源码里消掉了，却**原样活在刻意未跟踪的 `evidence/65f508b/STEP-00C_simulated_65f508b.patch`**（84/88/97/103 行）里——`secret_shape_scan.py docs/任务规划V0.5.0` 现读 `HIGH 命中：5（ALLOWED 3）`，其中 4 发就是那份补丁。它按 §5 第 2 批口径故意不入库，所以 gitleaks 的 dir 模式在当前工作树上仍然看得见这些形状：处置与那 6 个历史指纹同案（S0C.2.2 / D-12），本机不猜指纹、也不擅自把那份补丁改名或删除。
- **S0C.2.2** 🛠 新建 `.gitleaksignore`，逐条登记 6 个历史指纹（D-12 默认 A）
  - S0C.2.2.1 指纹取自 `gitleaks git --log-opts=origin/main --report-format json`
  - S0C.2.2.2 去掉该文件复跑必须重新出现 6 条（必要性反证）
- **S0C.2.3** ⛔ **本机没有 gitleaks，这一格的 ✅ 同样是来源标错**（第十六轮自查，与 S0C.1.3 同因）：
  现读 `gitleaks --version` ⇒ `command not found`。手上那份 `evidence/65f508b/gitleaks_65f508b.txt`
  是 gitleaks 8.21.2 在**有依赖的环境**里跑的，而且它给的**不是** rc=0：
  git 模式在 `65f508b` 命中 6 条历史指纹、dir 模式命中 5 条工作树占位 DSN，
  只有打上第 2 批那份模拟补丁之后才 `no leaks found`（且残留一个本地未跟踪的 `.pyc`）。
  上一版把那句写成「本地 … rc=0（仅含已推送分支）」，两处都不实：来源与结果。
  - 本机可证的替代读数只有形状召回器：`python docs/任务规划V0.5.0/evidence/65f508b/secret_shape_scan.py <目录>`
    末行那条 `HIGH 命中：N（ALLOWED M）`（现算，别抄进正文）。它按 `.gitleaks.toml` 规则 1 的同一条正则
    复刻，**不替代** gitleaks 的默认规则集与熵判据。
  - 真终判挂在 S0C.4.3/CI 与 Security workflow；`.gitleaksignore` 那六条指纹（S0C.2.2）只能由真
    gitleaks 产出，本机不猜指纹——猜一个就是把安全门禁静默解除。
- **S0C.2.4** 📄 conventions 增一条：测试/证据中构造 DSN 一律无口令（`scheme://user@host`），禁止 `user:pass@` 字面量

### S0C.3 CI 下游首跑预演
- **S0C.3.1** ⛔ **不是「本地按 ci.yml 顺序跑完」**（第十六轮自查，与 S0C.1.3/S0C.2.3 同因——来源标错）：
  那五步里本机只跑得了第一步，其余四步的读数来自 `evidence/65f508b/gates_65f508b.txt`
  （2026-10-13 在**有依赖的环境**采集，文件内自带时间戳）。逐步的可跑性与现读命令：
  | 步骤 | 本机 | 现读命令 |
  |---|---|---|
  | `check_docs_consistency.py` | ✅ rc=0 | `python scripts/check_docs_consistency.py` |
  | `gen_contracts.py --check` | ⛔ rc=1（`ModuleNotFoundError: No module named 'sqlalchemy'`） | `python scripts/gen_contracts.py --check` |
  | `alembic` 单头 | ⛔ rc=127（`alembic: command not found`，`import alembic` 亦 `ModuleNotFoundError`） | `alembic --version` |
  | `mypy app` | ⛔ rc=127 | `mypy --version` |
  | `pytest + --cov --cov-fail-under` + skip 门禁 | ⛔ 无 venv、无 `pytest-cov` | 见 §5 J-1/J-4 |
  - S0C.3.1.1 ⛔ 同一条更正：那份 `junit`（`evidence/65f508b/junit_65f508b.xml`）也是在有依赖的环境里跑的，
    本机既产不出 junit 也跑不动 ci.yml:120-173 那段内联判定所依赖的读数。
    本机这一半唯一能自证的是「形状召回器」那一条（见 S0C.2.3），不是 CI 判绿。
- **S0C.3.2** 🔴🛠 消除 test_env_isolation.py:74 的环境依赖 skip（判据读的是收集期快照 `_HOST_PROXY_VARS_AT_COLLECT`）：改为用 `subprocess` 以注入了 6 个假代理变量的环境跑一条内嵌用例，断言其内不可见
  - S0C.3.2.1 改前：无代理宿主 skip=1
  - S0C.3.2.2 改后：skip 降为 5，用例在任何宿主都真实执行且绿
  - S0C.3.2.3 变异：临时去掉 conftest:87-97 代理清理夹具 ⇒ 该用例红
- **S0C.3.3** 📄 ci.yml:108-120 注释更正 skip 构成（LangBot×2 + Redis×3），`SKIP_BASELINE` 维持 6 不放宽（D-11 授权范围内）

### S0C.4 本地门禁与 CI 同口径
- **S0C.4.1** ✅🛠 已交付（本批）｜`make evidence-check` 增真实 ruff / gitleaks 步；工具缺失打印 `SKIP(tool missing)` 并以非 0 退出码区分
  - 已加两步，缺失分支的读数：本机 ruff/gitleaks/make 三者皆无 ⇒ 那段 shell 实测打两行 SKIP 并 `exit 3`
    （`EVD-V2-00C/out_ruff_shapes.txt` 第 6 节现打）。**边界要说实话**：`make` 不在这台机器上，
    所以 Makefile 目标本身没被干跑过，验证的是「与目标里逐字同构的那段 shell」——
    真跑 `make evidence-check` 属 S0C.3.1 那批有 make/venv 的环境。
  - **S0C.4.1.1 未按原计划执行，这里写明偏离与理由**：计划是「g24 的 E501/I001 近似判定下线」。
    实测根因之后不改了——那两条挂了五轮的 I001 是 g24 自己的段表造的假红（`conftest` 被划成第一方、
    stdlib 用手抄名单漏了 `hmac`/`binascii`/`html`/`fnmatch`），而 ruff 真报的**成员序**与**同段空行**
    两类它一条都看不见。下线等于把「本机有一条能与 ruff 对齐的 import 判据」这件事扔掉。
    现在的做法是：段表换成 `sys.stdlib_module_names` + 「`apps/api/` 下确有其物才算第一方」+
    相对导入算 local-folder；补上成员序与同段空行两判；自证同时加**绿档**。
    读数：改前该表在同一棵树上报 12 条 I001（ruff 对这些文件是 0 条）、改后报 0 条，
    自证 15/15 两端都对——三条命令都在 `EVD-V2-00C/collect_ruff_shapes.sh` 里。
    自证还顺手暴露一个自己的缺陷：命中判定从前写 `rule in v`，而 `v` 的前缀是**临时文件名**
    （`_selftest_I001_12.py:1 F401 …`），于是文件名里的规则号会让任何违规都被算成「本规则捕获」——
    绿档永远不可能静默。已改成按 ` 规则号 ` 匹配。
- **S0C.4.2** ✅🛠 已交付（本批）｜Makefile:82 `lint-backend` 改为 `ruff check app tests`；`ruff format --check` 拆为非阻断目标
  `fmt-check-backend`（13 个待格式化文件另立卡，不在本步批量格式化）——两处已改；
  `ruff format --check` 那份读数取自 `evidence/65f508b/ruff_65f508b.txt`（13 份），本机不重跑。
- **S0C.4.3** 👤 执行机（win32）补 venv：`uv sync --extra dev`，能跑 `ruff` 与 `pytest --collect-only`（当前 collect 即 ModuleNotFoundError）
  - S0C.4.3.1 读数入 EVD：`ruff --version`、`pytest --collect-only -q | tail -1`

### S0C.5 收口
- **S0C.5.1** ⛔ **本机没有 CI 状态的读数**（第十六轮自查）：上一版写「✅ 推送后 CI、Security 双 success，
  两个 run id 与 job 结论入 EVD-V2-00C」，三处不实——①本机没有 `gh`（现读 `gh --version` ⇒
  `command not found`），拿不到 run id；②`EVD-V2-00C/` 里实际只有 ruff 形状那两份件
  （现读 `ls docs/06_validation/evidence/EVD-V2-00C`），没有 CI/Security 的 job 结论；
  ③那份 `evidence/65f508b/ci_runs_65f508b.txt` 记的恰恰是**红**：「最后一次双绿：`86269a2`；
  其后连续失败 CI 15 次、Security 15 次」，而 `65f508b` 那次是 backend 失败在 `Lint (ruff)`、
  Security 汇总门禁失败在 ④ gitleaks——也就是说这句话把「目标状态」写成了「已达成状态」。
  - 交付之后的真实终判要重新采一次：`gh run list --repo aideanew/BotHot --limit 6`（或 Actions 页面），
    并把 run id 与 job 结论落进 `EVD-V2-00C`。这一条登记为 §5 的人工/有依赖项，本机不猜。
  - 本机可证的只有「推送已发生且双端一致」：`git ls-remote origin main` 与 `git rev-parse HEAD` 两条
    （走代理：`git -c http.proxy=http://127.0.0.1:10808 ls-remote origin main`）。
- **S0C.5.2** 📄 V0.4.0 第 2 批证据件（合并版 patch + evidence-check 读数）在 S0C.2.1 后重采并入库

## 5. 测试设计
- 无新增业务测试；S0C.3.2 修改 1 条既有用例使之与环境无关。
- 验收命令：`ruff check app tests`；`gitleaks detect ...`；CI run 结论。

## 6. 停止条件与回滚
- 若 CI 下游 7 步中出现本地未见的失败：**不在本卡修复业务问题**，记录失败步与日志，开新卡（STEP-00C-F*），本卡以 ruff+gitleaks 回绿为止。
- 回滚：本卡改动均为测试/证据/配置，`git revert` 单提交即可。

## 7. 交付证据
EVD-V2-00C：ruff/mypy/gitleaks 本地读数、CI 等价链逐步 rc、两条 run id、skip 从 6→5 的 junit 对比。

## 8. 完成定义（本卡）
所有权内 diff 与任务一致 ∧ 每个 ✅ 有读数 ∧ 本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 通过 ∧ 推送后 CI 与 Security 均 success（run id 入 EVD）∧ 复审 ≤2 轮（D-14）。
