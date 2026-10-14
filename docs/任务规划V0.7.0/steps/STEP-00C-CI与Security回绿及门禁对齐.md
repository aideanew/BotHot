# STEP-00C CI与Security回绿及门禁对齐

| 项 | 值 |
|---|---|
| 里程碑 | M0 |
| 档位 | sonnet |
| 规模 | 小（约 0.5 人日） |
| 依赖 | STEP-R0（建议同 PR：只修 ruff 而不修回归，CI 会红在 pytest） |
| 裁决 | D-12（默认 A）、D-11（默认授权） |
| 剩余原子任务 | **17**（👤 1；本版 +1：S0C.1.0 先实跑取当前 lint 集合） |
| 需求锚 | REQ-F-004 / MUST M-6（主干 CI 绿） |
| 所有权（写） | W：apps/api/tests/test_chat_sse.py、test_env_isolation.py、test_kb_longlink_ingest.py、**test_asset_fragment_guard.py（仅折行，禁改断言语义）**；docs/06_validation/evidence/EVD-V2-00R/prove_net_isolation.py、out_evidence_check.txt；.gitleaksignore（新）；Makefile（仅 `lint-backend`/`evidence-check` 目标体）；scripts/（g24/evidence-check）；.github/workflows/ci.yml（仅 SKIP 相关注释与阈值） |
| 禁止修改 | `apps/api/app/**`（归 W-API/W-R0）；`packages/contracts/**`；`apps/api/alembic/**`；`Makefile` 的 `EVIDENCE_LINE_BUDGET` 变量行（归 STEP-00G，见 04 §4.5 重叠处置 2） |
| 基线 | **main@13acacc**（V0.6.0 为 a9b194d） |

## 1. 目标与可证伪验收
- CI 与 Security 两条 workflow 在推送后均 success（打破 15 连红），run id 入 EVD-V2-00C。
- 本地门禁与 CI 同口径：本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 是 Done 的必要条件，`make evidence-check` 缺工具时打印 SKIP 而非 PASS。
- CI 下游 7 步首次运行即通过，且 skip 留出 ≥1 条余量（当前 6 = 基线 6）。

## 2. 证据链（现状）
- **（本版更正）** a9b194d 记录 ruff 5 错（3×I001 + 2×E501）。本轮静态复核（`evidence/13acacc/e501_lint_scan_13acacc.txt`）：
  - E501 **个数仍为 2、行文本逐字未变**（显示宽度 121 / 134），但 `test_asset_fragment_guard.py` 的那一条**行号已从 :104 漂到 :116**（a576bc2 在其上方插入 12 行）。V0.6.0 卡面写 `:104` 是过期定位。
  - I001 三个目标文件（test_chat_sse.py / test_env_isolation.py / test_kb_longlink_ingest.py）自 a9b194d **未被改动**，判据可原样沿用。
  - 本机 `ruff` MISSING ⇒ **13acacc 的真实 lint 集合 NOT_MEASURED**，必须先跑 S0C.1.0 再动手，禁止照抄 5 这个数。
- gitleaks main 历史仍是 6 条（1af68fc×3、1470b77×2、de78125×1），指纹不变。本地 `gitleaks git` 不加 `--log-opts` 会扫到未合并的 `plan/2026-10-12-remaining-tasks` 分支，多出 798f263×3——那 3 条不在 main，CI（只检出 main）看不到——`gitleaks_a9b194d.txt`。**本版复核**：`.gitleaksignore` 所指两文件（`prove_net_isolation.py`=e466e9e、`out_evidence_check.txt`=b7de357）自 a9b194d 未变，6 个指纹可直接沿用（01 F-71）。
- CI/Security 连续失败：15 → **22**（run 38501576733 / 38501576766，失败于 `Lint (ruff)` 与 gitleaks 汇总门禁）——`ci_runs_a9b194d.txt`。**本版未复测**（无 `gh`，`curl api.github.com` 未认证 403），22 为 a9b194d 时点值。
- 合并补丁 `STEP-R0+00C_combined_simulated_a9b194d.patch`（8 个文件，+35/−12）在 a9b194d 实测 ruff 0 错、gitleaks 0、全量 1045/5/0。**本版复核**：该补丁在 13acacc 仍 `git apply --check` rc=0，其中 `test_asset_fragment_guard.py` 的 hunk 以 **+12 offset** 命中（01 F-70）——能套用不等于还对，套用后必须按 S0C.1.0/S0C.1.3 重取读数。
- skip 构成（本沙箱）：LangBot×2、Redis×3；代理类 skip 本轮没有出现（宿主环境差异），CI 侧以首跑为准。

## 3. 执行逻辑穿透
推送 → ci.yml backend：install → ruff(:67) ✗ → [mypy(:71) → alembic(:75/:83) → contracts(:97) → docs(:104) → pytest+cov+skip gate(:118-173)] 全部 skipped。
推送 → security.yml：①pip-audit ②pnpm audit ③trivy ④gitleaks detect(--source . --config .gitleaks.toml，fetch-depth 0) → 汇总(:504) ✗。
gitleaks 默认读取仓库根 `.gitleaksignore`（指纹 = commit:path:rule:line），因此逐指纹登记只豁免这 6 个历史位置，后续任何新增同类串仍会被拦。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红（写失败测试）｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### S0C.1 ruff 回绿
- **S0C.1.0** ✅ **（本版新增，先测后改）** 依赖机实跑取当前 lint 集合，读数入 EVD-V3-00C；行号只作提示，不作判据
  - S0C.1.0.1 命令：`cd apps/api && .venv/bin/ruff --version && .venv/bin/ruff check app tests > EVD-V3-00C/ruff_13acacc.txt 2>&1; echo rc=$?`
  - S0C.1.0.2 若版本非 0.12.12 ⇒ **停下**（pyproject 钉版；0.12.x 与 0.16.x 的 I001 规则互斥，见 `ci.yml:60-63` 注释），不得在错版本上判绿
- **S0C.1.1** 🛠 `ruff check --fix` 修 3 处 I001（只动 import 块）
  - S0C.1.1.1 对 test_chat_sse.py、test_env_isolation.py、test_kb_longlink_ingest.py 执行 `ruff check --fix --select I001`
  - S0C.1.1.2 `git diff --stat` 确认仅 import 行变化
- **S0C.1.2** 🛠 两处 E501 折行（括号续行，不改语义）：`test_env_isolation.py:68`、**`test_asset_fragment_guard.py:116`**（V0.6.0 写 :104，已随 a576bc2 下移 12 行）
  - S0C.1.2.1 改写为 `assert ..., (\n f"..."\n)`
  - S0C.1.2.2 `ruff check app tests` → All checks passed
  - S0C.1.2.3 ⚠ 折行只准动**换行**，不准动断言表达式与 f-string 内容（该文件 33 行断言在 00T 里有靶，语义漂移会让证明台与真实用例分叉）
- **S0C.1.3** ✅ 本地 0.12.12 `ruff check app tests` 与 `mypy app` 读数入 EVD-V3-00C

### S0C.2 Security 回绿
- **S0C.2.1** 🛠 工作树占位 DSN 去口令：`x:y@` → `x@`（prove_net_isolation.py:702/705/1214/1219、out_evidence_check.txt:137）
  - S0C.2.1.1 替换后复跑 prove_net_isolation.py，PASS=24 FAIL=0
  - S0C.2.1.2 `gitleaks dir` 对这两个文件 0 命中
- **S0C.2.2** 🛠 新建 `.gitleaksignore`，逐条登记 6 个 main 历史指纹（D-12 默认 A）
  - S0C.2.2.1 指纹取自 `gitleaks git --log-opts=origin/main --report-format json`（必须带 `--log-opts`，否则会混进未合并分支的 798f263×3）
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
- **S0C.4.1** 🛠 `make evidence-check` 增真实 ruff / gitleaks 步；工具缺失打印 `SKIP(tool missing)` 并以非 0 退出码区分
  - S0C.4.1.1 g24 的 E501/I001 近似判定下线（保留文件，入口不再调用）
- **S0C.4.2** 🛠 Makefile:82 `lint-backend` 改为 `ruff check app tests`；`ruff format --check` 拆为非阻断目标 `fmt-check`（13 个待格式化文件另立卡，不在本步批量格式化）
- **S0C.4.3** 👤 执行机（win32）补 venv：`uv sync --extra dev`，能跑 `ruff` 与 `pytest --collect-only`（当前 collect 即 ModuleNotFoundError）
  - S0C.4.3.1 读数入 EVD：`ruff --version`、`pytest --collect-only -q | tail -1`

### S0C.5 收口
- **S0C.5.1** ✅ 推送后 CI、Security 双 success，两个 run id 与 job 结论入 EVD-V2-00C
- **S0C.5.2** 📄 V0.4.0 第 2 批证据件（合并版 patch + evidence-check 读数）在 S0C.2.1 后重采并入库

### S0C.6 防止 ruff 再次漂移
- **S0C.6.1** 🛠 新增 pre-commit 钩子（或 `make precommit`）：对暂存的 `apps/api/**/*.py` 跑 ruff 0.12.12
  - S0C.6.1.1 执行机没装 ruff 时打印 SKIP 并提示，不得静默通过

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

## 9. V0.6.0 → V0.7.0 本卡变更（可核）
| # | 变更 | 依据 |
|---|---|---|
| 1 | 基线 a9b194d → 13acacc；证据目录改 `EVD-V3-00C` | 01 §0 |
| 2 | **新增 S0C.1.0**：先实跑 ruff 取当前集合，禁止照抄「5 错」；并加版本守卫（非 0.12.12 即停） | F-68、`ci.yml:60-63` |
| 3 | E501 定位更正 `:104 → :116`；I001 三文件确认未变 | `e501_lint_scan` |
| 4 | `.gitleaksignore` 6 指纹标注「所指文件未变、可沿用」；补丁标注「可套用但对不对要重测」 | F-70/F-71 |
| 5 | CI 连红 22 次改标 `NOT_MEASURED（a9b194d 时点值）` | 01 §2 |
| 6 | 补 `禁止修改` 字段 + `Makefile` 与 00G 的行域拆分（消所有权重叠） | 04 §4.5、§4.11 |
| 7 | 依赖项补 `test_asset_fragment_guard.py`（原卡漏列，但 S0C.1.2 实际要改它） | 所有权完整性 |
