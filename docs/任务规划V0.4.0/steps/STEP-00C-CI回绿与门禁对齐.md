---
id: STEP-00C
title: CI 回绿与本地门禁对齐（CI 自 5c8552b 起连续 13 次红，d80eeaf 时点复测）
baseline: main@b45777a
tier: sonnect（S0C.2.2 需人裁决 D-12；S0C.3 由 opus review 一次）
size: 小（约 0.5 人日）
priority: P0（阻断：CI 红期间任何 STEP 都无法按完成定义判 Done）
---

# STEP-00C：CI 回绿与本地门禁对齐

## 归属
- 所属切片：S0（测试侧步行骨架）的补丁刀，排在一切 STEP 之前
- 来源需求：REQ-NF（CI 门禁为合并硬门禁，AGENTS.md 完成定义）、本规划 §9.4 自动化守卫
- 来源证据：`evidence/b45777a/ruff_0.12.12_b45777a.txt`、`gitleaks_main_b45777a.txt`、`g24_vs_ruff_E501.txt`、`STEP-00C_proposed.patch`、`e501_calibrate.py`（读数 `e501_width_calibration.txt`）、`g24_vs_ruff_I001.py`（读数 `g24_vs_ruff_I001.txt`）、`precommit_gitleaks_scan.py`（读数 `precommit_gitleaks_scan.txt`）、`STEP-00C_ruff_tests.patch`——后四件是本轮新测：E501 的豁免口径、g24 与 ruff 在 I001 上的**反向互斥**、以及「本包能不能落库」的按行实测（它把 patch 按可入库性切成了两批，见 05 §2.1）

## 目标
`main` 上新 push 的 sha，CI（ruff/mypy/pytest/前端）与 Security（四扫描器汇总门禁）两条 workflow 均 `conclusion=success`，且本地 `make evidence-check` 不再出现“本地绿、CI 红”。

## 事实（全部在 b45777a 实测，非推断）
| # | 事实 | 证据 |
|---|---|---|
| C-1 | CI 首红 = 5c8552b（19:23 推送，含 1af68fc），此前 86269a2 两条 workflow 均 success；之后 13 次推送全部红（`d80eeaf` 时点经 GitHub API 复测；本卡初稿的「10 次」是 `de78125` 时点的数，起红 sha 未记错） | GitHub Actions runs 列表（run 38242338715 起）、01 F-29 |
| C-2 | CI `Lint (ruff)`（`ci.yml:67-68`，`ruff check app tests`，ruff 钉死 0.12.12 `pyproject.toml:35`）报 4 条：`test_chat_sse.py:8` I001、`test_env_isolation.py:23` I001、`test_env_isolation.py:68` E501（134>120）、`test_kb_longlink_ingest.py:28` I001 | `ruff_0.12.12_b45777a.txt` |
| C-3 | `mypy app` 绿（107 files）；连库全量 1037 passed / 0 failed ⇒ CI 红仅由 ruff 一步造成（后续步骤因 ruff 失败未执行，可能还有未暴露项，见 S0C.4.1） | `pytest_full_pg_b45777a.txt` |
| C-4 | Security 红的是汇总门禁，阻断来源为 ④ gitleaks：自定义规则 `connection-string-embedded-password` 命中 5 处，全部是证明脚本里的**假 DSN**（scheme `postgresql+psycopg`、账号段 `x`、口令段 `y`、主机 `127.0.0.1:5547`、库名 `z`；口令 `y` 不在占位白名单 `.gitleaks.toml:44`），来源提交 1af68fc（3 处）、1470b77（2 处）。**本行刻意不把五段连成完整 DSN 邻接形**：落库前置扫描（`evidence/b45777a/precommit_gitleaks_scan.py`，读数 `precommit_gitleaks_scan.txt`）实测出「卡面原文照抄完整假 DSN 会给 Security 添 1 条新指纹」，为可写性做的这个取舍要留痕 | `gitleaks_main_b45777a.txt`（gitleaks 8.21.2，`--log-opts=main`，与 CI 同版本同配置） |
| C-5 | pip-audit 2.10.1 对锁定环境 0 漏洞 ⇒ 非依赖漏洞导致 | 本地实跑 |
| C-6 | Security 走 git 历史模式（`security.yml:95-99` fetch-depth 0）⇒ **只改 HEAD 不够**，历史 5 处会持续命中；仓库禁止改写历史（`.gitleaks.toml` 历史登记段） | `.gitleaks.toml:61-72` |
| C-7 | 本地门禁 `g24_static_check.py` 报 0 违规而 ruff 报 4 条：① E501 用 `len()`（`g24_static_check.py:72`）而 ruff 按显示宽度（CJK=2），同一行 112 vs 134；② I001 未建模 ruff isort 的 order-by-type（`_PG_URL_SOURCE` 须排在 `PG_URL` 前）；③ **反向坑**：只把 g24 的 `len()` 换成显示宽度会让本地门禁**假红**——本机实测（`evidence/b45777a/e501_calibrate.py`，读数 `e501_width_calibration.txt`）裸宽度 >120 在 `app tests` 上命中 **27 行**，而 ruff 真报的只有那 **1 行**，其余 26 行全落在 ruff 的三条豁免里（25 行超长尾巴是 `# noqa` / `# type: ignore[...]` pragma、1 行以 URL 结尾、0 行单词） | `g24_vs_ruff_E501.txt`、`ruff --diff` |
| C-8 | 执行端（win32）无 venv/ruff/PG：提交说明多处写明“本机无 pytest 依赖”“本机无 make”，运行时项一律移交（H-1…H-6）。**本轮把缺件程度量到「连收集都过不了」**：本机有 pytest 9.1.1 但没有 app 依赖，`python -m pytest tests --collect-only -q` 0.73s 死在 `tests/conftest.py:33` 的 `ModuleNotFoundError: No module named 'sqlalchemy'`，rc=4、无 `collected` 行（读数 `evidence/win32_pytest_collect_20261013.txt`）⇒ 「本机全绿」在 win32 上无从证伪；本包 b45777a 两份全量读数产在 aarch64 沙箱，分辨线索是路径分隔符（沙箱件 `tests/...`、win32 件 `tests\...`），分工见 00-README §7 | 1af68fc、c10b229、884572d 提交说明、`win32_pytest_collect_20261013.txt` |
| C-9 | 模拟修复（临时克隆，未推送）：ruff `--fix` + 一处手工折行 ⇒ `All checks passed`；HEAD 假 DSN 口令改 `nosuch` + `.gitleaksignore` 登记 5 个历史指纹 ⇒ gitleaks `no leaks found`；`evidence-check` rc=0；相关 3 个测试文件 49 passed / 2 skipped | `STEP-00C_proposed.patch` |

## 输入
- 本卡事实表 C-1…C-9 与 `evidence/b45777a/*`
- 前置：无（本卡是一切 STEP 的前置）
- 裁决：D-12（历史假 DSN 的登记方式）

## 输出（新增/修改的文件）
- `apps/api/tests/test_chat_sse.py`、`tests/test_env_isolation.py`、`tests/test_kb_longlink_ingest.py`（仅 import 段序与一处折行）
- `docs/06_validation/evidence/EVD-V2-00R/prove_net_isolation.py`（仅假 DSN 口令字面量 4 处）
- `.gitleaksignore`（新，5 行指纹，D-12 批准后）
- `docs/06_validation/evidence/EVD-V2-00/g24_static_check.py`（E501 宽度口径、I001 降级声明）
- `Makefile`（`evidence-check` 增真实 ruff 一步，有则跑）
- `docs/06_validation/evidence/EVD-V2-00C/README.md`（新）

## Execution Steps（三级原子任务 → 四级执行步骤）

### S0C.1 ruff 回绿（CI 主因）

#### S0C.1.1 🛠 I001 三处自动修复
**交付**：`ruff check --fix` 只改三处 import 段序，不碰其它行。
1. [ ] `cd apps/api && uv run ruff check tests/test_chat_sse.py tests/test_env_isolation.py tests/test_kb_longlink_ingest.py --fix`
2. [ ] `git diff --stat` 恰为 3 文件、≤4 行变化
3. [ ] 复跑 `prove_net_isolation.py`（其 NR-9-b 用 AST 读 import，改序不得致红）

**验收命令**：
```bash
cd apps/api && uv run ruff check tests --select I001 && cd ../.. && python docs/06_validation/evidence/EVD-V2-00R/prove_net_isolation.py | tail -1
```

**本机（无 uv/ruff）的等价执行与一条必须写在前面的陷阱**：
- 三份文件的 ruff 终序已逐字落在 `evidence/b45777a/STEP-00C_ruff_tests.patch` 里（本轮从合并版按 `diff --git`
  块切出，只含 `apps/api/tests/*` 三个 hunk、4 个 `@@`，不含任何 DSN ⇒ 可入库；`git apply --stat` 与合并版
  逐文件相同，本机 `git apply --check <该 patch>` 复跑 rc=0）。执行端只做一件事：按同一 patch 落盘，
  其余交给有 ruff 的机器复跑上面那条验收命令（登记 J-2）。
- **陷阱（实测，非推测）**：改完之后本地门禁 `g24_static_check.py` 会**反过来**报 2 条 I001
  （它要 `from conftest` 排在 `from fastapi.testclient` 之后）。复现器
  `evidence/b45777a/g24_vs_ruff_I001.py`（读数同目录 `.txt`，rc=0 即互斥成立）。
  ⇒ 谁的判据是「本地门禁绿」谁就会把 import 改回原序，CI 立刻重新红。本步一律以 ruff 为准。

#### S0C.1.2 🛠 E501 一处手工折行
**交付**：`test_env_isolation.py:68` 的断言消息折成括号多行，语义不变。
1. [ ] 按 `STEP-00C_proposed.patch` 对应 hunk 改写
2. [ ] `uv run pytest tests/test_env_isolation.py -q` 仍 3 passed（有代理）/ 2 passed 1 skipped（无代理）
3. [x] 折行后宽度已本机实测：三行分别 38 / 105 / 5（阈值 120），且 `g24_vs_ruff_I001.py` 对三份修复后
    文件报「显示宽度 >120 的行 = 0 行」——这一档不做完，第 1 步就只是「照 patch 抄了一遍」

**验收命令**：
```bash
cd apps/api && uv run ruff check app tests && uv run pytest tests/test_env_isolation.py -q
```

### S0C.2 Security 回绿（gitleaks）

#### S0C.2.1 🛠 HEAD 假 DSN 改占位口令
**交付**：`prove_net_isolation.py` 四处 `x:y@` → `x:nosuch@`（`nosuch` 已在白名单 `.gitleaks.toml:44`，不需改规则）。
1. [ ] 替换 4 处（2 处赋值 + 2 处比较，必须成对）
2. [ ] `prove_net_isolation.py` 与 `--self-test` 均 rc=0（NR-7 仍能红：变异体逻辑不依赖口令值）

**验收命令**：
```bash
! grep -n "://x:y@" docs/06_validation/evidence/EVD-V2-00R/prove_net_isolation.py && python docs/06_validation/evidence/EVD-V2-00R/prove_net_isolation.py --self-test
```

#### S0C.2.2 👤🛠 历史 5 处登记（D-12）
**交付**：按 D-12 裁决落一种：
- 方案 A（推荐，最窄）：`.gitleaksignore` 逐行登记 5 个指纹（`evidence/b45777a/gitleaks_main_b45777a.txt` 第 4 列）。只豁免“这 5 个提交里的这 5 行”，后续任何新提交里再写 `x:y@` 仍会红。
- 方案 B：`.gitleaks.toml` 两处 `commits = [...]` 追加 1af68fc、1470b77 全长 sha。代价：这两个提交里**任何**未来被规则识别的内容都被豁免，范围更宽。
1. [ ] 人选 A/B
2. [ ] 落文件，并在 `.gitleaks.toml` 历史登记段加一行注释说明来由（假值、非秘密）

**验收命令**（需 gitleaks 8.21.2 二进制）：
```bash
gitleaks detect --source . --config .gitleaks.toml --log-opts=HEAD --no-banner --redact --exit-code 1 && echo OK
```

#### S0C.2.3 ✅ 防再犯：证明脚本内的连接串只用占位口令
**交付**：`EVD-V2-00C/README.md` 写明“证据/测试里构造 DSN 一律用 `bothot_ci`/`nosuch`/`not_a_secret`”，并在 S0C.3.2 的本地门禁里加一步 `gitleaks --no-git` 扫工作树（有二进制才跑，无则打印 SKIP 而非 PASS）。
1. [ ] README 一段
2. [ ] Makefile 一步（见 S0C.3.2）

**验收命令**：
```bash
grep -n "nosuch" docs/06_validation/evidence/EVD-V2-00C/README.md
```

#### S0C.2.4 🛠 第 2 批证据件重采并入库（闭合双端一致）
**交付**：S0C.2.1 落盘后，`evidence/b45777a/STEP-00C_proposed.patch` 与 `evidence_check_b45777a.txt`
里那 5 条假 DSN 邻接形随之消失（前者重生成、后者重跑 `make evidence-check` 重采），本包第 2 批入库，
`git status` 对本包不再有未跟踪项。
**为什么单独列一个原子任务**：落库切分是本轮实测出来的（05 §2.1，跑 1 点名 5 条），
不是「以后再说」的备注——不做完，第 1 批提交后仓库里的规划就少了模拟修复与 evidence-check 两份关键证据，
双端一致只闭合一半，而下一个人照 00-README §6 复现时会发现点名的文件根本不在。
1. [ ] `python docs/任务规划V0.4.0/evidence/b45777a/precommit_gitleaks_scan.py docs/任务规划V0.4.0` → **rc=0**
2. [ ] 重生成 patch（对 S0C.2.1 后的工作树跑 ruff `--fix` + 折行 + DSN 替换，`git diff` 出补丁）并 `git apply --check` rc=0
3. [ ] 两件入库后 `git status --short docs/任务规划V0.4.0` 为空

**验收命令**：
```bash
python docs/任务规划V0.4.0/evidence/b45777a/precommit_gitleaks_scan.py docs/任务规划V0.4.0; echo "rc=$?  # 期望 0"
git status --short docs/任务规划V0.4.0
```

### S0C.3 本地门禁与 CI 口径对齐（防“本地绿、CI 红”）

#### S0C.3.1 🛠 g24 口径缺陷（卡面原判两处，实测后为四处）
**交付**：
- E501 改按显示宽度计数（`unicodedata.east_asian_width in 'WF'` 计 2，combining 计 0），与 ruff 0.12.12 一致；
- **且同时建模 ruff 的三条豁免**（行尾 pragma 注释 `# noqa` / `# type: ignore`、以 URL 结尾、整行单个长词）——只改宽度不改豁免，`app tests` 上会从「0 违规」变成「26 条 ruff 并不报的违规」，把假绿换成更难看的假红。口径以 `evidence/b45777a/e501_calibrate.py` 为准，改完 g24 必须复跑它并核对 `[over] 1 条`；
- I001 不再声称“ruff 子集”：输出改为“段序预检（非 ruff 终判）”，并在 `--self-test` 增一条“`from m import _A, B` 应判违规”的样本，若实现不了就把 I001 从 g24 移除，交真实 ruff。
  **而且必须先解决一条互斥**：`evidence/b45777a/g24_vs_ruff_I001.py` 实测——把 ruff `--fix` 的终序落下去之后，
  g24 反而报 2 条 I001（`test_chat_sse.py:19`、`test_env_isolation.py:29`）。也就是说 g24 现在的 I001 预检
  不只是「弱于 ruff」，是**与 ruff 反向**：留着它，执行端会被诱导把 import 改回 CI 红的那一侧。
- **新增第 4 条（同一跑里测出）**：g24 收到**仓库外**的绝对路径时在 `g24_static_check.py:275` 的
  `path.relative_to(ROOT)` 上抛 `ValueError`——stdout 空、rc=1、没有任何裁决，正是本项目禁的「崩栈当裁决」。
  处置：显示用给定路径本身（或 `try/except ValueError` 退回绝对路径），并给 `--self-test` 增一条
  「仓库外路径必须下得出裁决」的样本。
1. [ ] 先红：用 `test_env_isolation.py@b45777a:68` 当样本，g24 改前判 0 违规（假绿）
2. [ ] 改宽度口径，转红为“违规 1 条”
3. [ ] **补豁免**：对 `tests/test_kb_orphan_purge.py:91` 等 26 行判 0 违规（这一档不做，第 2 步的红就无从解释）
4. [ ] I001 两选一（建模 order-by-type 或下线并改文案）
5. [ ] 仓库外路径不再崩（`relative_to` 那行），`--self-test` 加一条「给绝对路径 / 仓库外路径也要下裁决」

**验收命令**：
```bash
git show b45777a:apps/api/tests/test_env_isolation.py > /tmp/t.py && python docs/06_validation/evidence/EVD-V2-00/g24_static_check.py /tmp/t.py | grep -q E501 && python docs/06_validation/evidence/EVD-V2-00/g24_static_check.py --self-test
```
（若 g24 当前不接受文件参数，本任务同时加该参数。）

#### S0C.3.2 🛠 `make evidence-check` 增真实 ruff + gitleaks 步
**交付**：recipe 增两步：`command -v uv && (cd apps/api && uv run ruff check app tests)`；`command -v gitleaks && gitleaks detect --no-git ...`。工具缺失时打印 `SKIP（缺 ruff/gitleaks，CI 终判）`，不得打印 PASS。
1. [ ] 改 Makefile（tab 缩进）
2. [ ] 在有 uv 的机器跑一次 rc=0；在无 uv 的机器跑一次，输出含 `SKIP`

**验收命令**：
```bash
make evidence-check 2>&1 | grep -E "ruff|SKIP"
```

### S0C.3.3 👤📄 执行端补齐 venv（消除“本机无依赖”结构性缺口）
**交付**：执行端（win32）按 `apps/api/pyproject.toml` 执行 `uv sync --extra dev`，能跑 `uv run ruff`、`uv run pytest -m "not pg"`；PG 类用例仍可交有 docker/PG 的验证者。结果写 EVD-V2-00C §2。
**为什么这一档现在比上一包更硬**：C-8 实测本机连 `--collect-only` 都过不了（rc=4，无 `collected` 行），
所以「本机全绿」这四个字在 win32 上不是结论而是**无法证伪**；补齐之前，本卡所有 `uv run …` 验收命令都必须由
**装了依赖的那台机器**执行并留档，替身判据（`e501_calibrate.py`、`g24_vs_ruff_I001.py`）只覆盖 E501/I001 两条形状。
**交付**：执行端（win32）按 `apps/api/pyproject.toml` 执行 `uv sync --extra dev`，能跑 `uv run ruff`、`uv run pytest -m "not pg"`；PG 类用例仍可交有 docker/PG 的验证者。结果写 EVD-V2-00C §2。
1. [ ] 人在执行机执行，贴 `uv run ruff --version`（须为 0.12.12）与离线 pytest 末行
2. [ ] 若执行机确实不能装依赖：在 EVD 写明，并把“push 前本地 ruff”改为“push 前在验证机跑 ruff”

**验收命令**：
```bash
cd apps/api && uv run ruff --version && uv run pytest tests -q -p no:cacheprovider | tail -1
```

### S0C.4 收口

#### S0C.4.1 ✅ 推送后两条 workflow 均 success
**交付**：一个提交（或一个 PR）合入 S0C.1–S0C.3；推送后读 Actions：CI 与 Security 的 `conclusion=success`。若 CI 在 ruff 之后的步骤（mypy/pytest/前端）暴露新红，按同卡追加原子任务，不得放宽门禁。
1. [ ] 推送
2. [ ] 记录两条 run id 与结论入 EVD-V2-00C
3. [ ] 关闭 Home 上“CI 转红”提醒（运营侧）

**验收命令**：
```bash
gh run list -R aideanew/BotHot -L 2 --json name,conclusion,headSha
```

## 验收标准（独立验证者逐条判 PASS / FAIL / UNKNOWN）
- [ ] `cd apps/api && uv run ruff check app tests` 输出 `All checks passed!`
- [ ] `gitleaks detect --log-opts=HEAD`（8.21.2，仓库配置）`no leaks found`
- [ ] `grep -rn "://x:y@" docs/06_validation` 为空
- [ ] g24 对 `b45777a:test_env_isolation.py` 报出 E501（不再假绿）
- [ ] 推送后 CI、Security 两条 run 均 success（run id 入档）
- [ ] 连库全量仍 failed=0（不因折行/改序改变任何用例结论）

## 验证命令
```bash
cd apps/api && uv run ruff check app tests && uv run mypy app && cd ../.. && gitleaks detect --source . --config .gitleaks.toml --log-opts=HEAD --no-banner --redact --exit-code 1 && make evidence-check
```

## 证据路径
`docs/06_validation/evidence/EVD-V2-00C/`

## 允许修改
- `apps/api/tests/test_chat_sse.py`、`test_env_isolation.py`、`test_kb_longlink_ingest.py`（仅 S0C.1 所列行）
- `docs/06_validation/evidence/EVD-V2-00R/prove_net_isolation.py`（仅假 DSN 4 处）
- `docs/06_validation/evidence/EVD-V2-00/g24_static_check.py`
- `.gitleaksignore`（新）或 `.gitleaks.toml` 历史登记段（二选一，按 D-12）
- `Makefile`（仅 `evidence-check` recipe）
- `docs/06_validation/evidence/EVD-V2-00C/**`

## 禁止修改
- `apps/api/app/**`（本卡不改业务代码）
- `.github/workflows/**`（D-11 未拍板；本卡不需要改 workflow 就能回绿）
- `.gitleaks.toml` 的规则正则与占位白名单（放宽规则 = 降低门禁，禁止）
- `apps/api/pyproject.toml`（ruff 版本钉死不动）

## 依赖与阻塞
- Depends on：无；S0C.2.2 依赖 D-12
- Blocks：所有 STEP 的“Done”判定（完成定义含 CI 绿）
- 阻塞条件：ruff 之后的 CI 步骤暴露新红且需要改 `app/**` ⇒ 停，另开卡

## 建议执行档位
`sonnect`　理由：改动机械、证据已齐；S0C.3.1 的 I001 取舍请 opus review 一次（是否下线 I001 预检）。

## 升级条件
推送后 CI 仍红且原因不在本卡事实表内 ⇒ 升 opus 诊断；同一原子任务连续 2 次验收失败 ⇒ 熔断。

## 预估规模
小（约 0.5 人日；S0C.3.3 取决于执行机能否装依赖）

## 完成定义
所有权内 diff 符合本卡 ∧ 验收逐条有结果 ∧ 两条 workflow success 的 run id 入档 ∧ 未放宽任何门禁规则。

## 回滚
`git revert <sha>`；`.gitleaksignore` 删除即恢复原行为。
