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
- **S0C.1.1** ✅🛠 已交付（本批，提交号见 `06-执行记录.md` 末行）｜`ruff check --fix` 修 3 处 I001（只动 import 块）——本机没有 ruff，落点方式改成
  **照抄实测通过的形状**：`evidence/65f508b/ruff_65f508b.txt` 给出三条 I001 的位置，
  `evidence/65f508b/STEP-00C_simulated_65f508b.patch`（那份副本按 `05` §5 第 2 批口径不入库，是有意未跟踪件）
  是 ruff 0.12.12 实跑 0 错的**目标形状**，逐条搬到当前代码上：
  `test_chat_sse.py:18` 与 `test_env_isolation.py:28` 是 from-import 的**成员序**
  （`_PG_URL_SOURCE` 先于 `PG_URL`：ruff 的 `order-by-type` 把常量归一组、组内按小写名，`_` 排在字母前），
  `test_kb_longlink_ingest.py` 是 `import pytest` 与 `from fixtures.wechat_urls` 之间那句空行。
  - S0C.1.1.1 ✅ 本机不可执行 `ruff check --fix --select I001` ⇒ 改为按上面那份补丁的形状手工落地，
    改前/改后形状由 `EVD-V2-00C/collect_ruff_shapes.sh` 第 4 节现打（不抄进本卡）。
  - S0C.1.1.2 ✅ 仅 import 行变化的核对：`git show --stat <本批提交>` 里三份测试文件各 1–2 行；
    生产代码零改动。
  - **本条真正的根因不在那三个文件**：本机那张 stdlib 近似表（`EVD-V2-00/g24_static_check.py`）把
    `conftest` 划成第一方、又用一份手抄 stdlib 名单（漏了 `hmac`/`binascii`/`html`/`fnmatch`），
    于是它在 **ruff 全过的文件上**报出 12 条 I001（现读：`bash …/collect_ruff_shapes.sh` 第 1 节），
    而 ruff 真报的那三条（成员序 + 同段空行）它**一条都看不见**。那两条「挂了五轮修不掉」的 I001
    从头到尾是本机门禁自己造的假红——要改的是判据，不是被测文件。已改：段表换成
    `sys.stdlib_module_names` + 「`apps/api/` 下确有其物才算第一方」+ 相对导入算 local-folder，
    并补上成员序与同段空行两判；自证同时加**绿档**（实测通过 CI 的形状不许被咬）。
- **S0C.1.2** ✅🛠 已交付（核实为**本批之前已完成**，见下）｜`test_env_isolation.py:68` 断言消息折行——**已完成于本批之前**：现读该行 112 列
  （≤120），`65f508b` 那次的 134 列已经不存在了；本卡不再重复改它。
  - S0C.1.2.1 ✅ 形状已在（那句 assert 现在自己就在一行内放得下）。
  - S0C.1.2.2 ⛔ `ruff check app tests` → All checks passed 是 **CI 的读数**，本机没有 ruff；
    登记为 S0C.5.1 的一部分，不写成本地通过。
- **S0C.1.3** ✅ 本地 0.12.12 `ruff check app tests` 与 `mypy app` 读数入 EVD-V2-00C
  - ⛔ 本机按约定不装依赖 ⇒ 这一步要 S0C.4.3 的人工 venv 才能出数；本地替代读数在
    `EVD-V2-00C/out_ruff_shapes.txt`（近似表改前/改后 + 两端自证 + E501 的方向性差异）。

### S0C.2 Security 回绿
- **S0C.2.1** 🛠 工作树占位 DSN 去口令：`x:y@` → `x@`（prove_net_isolation.py:702/705/1214/1219、out_evidence_check.txt:137）
  - S0C.2.1.1 替换后复跑 prove_net_isolation.py，PASS=24 FAIL=0
  - S0C.2.1.2 `gitleaks dir` 对这两个文件 0 命中
- **S0C.2.2** 🛠 新建 `.gitleaksignore`，逐条登记 6 个历史指纹（D-12 默认 A）
  - S0C.2.2.1 指纹取自 `gitleaks git --log-opts=origin/main --report-format json`
  - S0C.2.2.2 去掉该文件复跑必须重新出现 6 条（必要性反证）
- **S0C.2.3** ✅ 本地 `gitleaks detect --source . --config .gitleaks.toml` rc=0（仅含已推送分支）读数入 EVD
- **S0C.2.4** 📄 conventions 增一条：测试/证据中构造 DSN 一律无口令（`scheme://user@host`），禁止 `user:pass@` 字面量

### S0C.3 CI 下游首跑预演
- **S0C.3.1** ✅ 本地按 ci.yml 顺序跑 mypy → alembic 单头 → gen_contracts --check → check_docs_consistency → pytest+cov+skip gate，逐步 rc 入 EVD
  - S0C.3.1.1 用 `junit` 喂 ci.yml:120-173 的内联判定脚本，确认判绿
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
- **S0C.5.1** ✅ 推送后 CI、Security 双 success，两个 run id 与 job 结论入 EVD-V2-00C
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
