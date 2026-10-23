# EVD-V18-32 · STEP-32 发布阻断：密钥脱敏与时区依赖

> 基线 `main@73b9fa6`（卡面增量 `f62054b`）｜版本 V0.18.0｜队列第一项
> 归属 Agent-Guard｜来源 P-107 / P-106｜裁决 D-V18-03 / D-V18-04 / D-V18-13
> 本目录按 D-V18-13 只做本版证据；历史卡面与历史台账行一律不追改。

## 0. 本批实际改动面（与卡面 §7/§12 的对照）

| 文件 | 改动 | 授权来源 |
|---|---|---|
| `.github/workflows/ci.yml` | `Generate ephemeral master keys` 步重写（:470-486）+ Governance 步加 4 类新行（:260-261、:263、:269-272） | §7 + 卡面增量 1 第③处 |
| `scripts/guards.py` | 新增守卫（`_workflow_step_bodies` / `ci_mask_violations` / `guard_ci_secret_mask`）+ `GUARDS` 加一键 | §7「仅新增一条守卫函数」 |
| `scripts/entry.py` | 任务表加一项 + `guard` 复合元组加一名 | 卡面增量 1 第①处 |
| `Makefile` | 新增薄转调目标（:176-178）+ 聚合目标前置加一名（:194） | 卡面增量 1 第②处（聚合那一列是 `test_guard_rounds.py:410-416` 的双向断言逼出来的，见 §5.3） |
| `apps/api/pyproject.toml` | 主依赖加 `tzdata`（不带 marker）+ 4 行理由注释 | §7 |
| `apps/api/uv.lock` | uv 重锁，净 +2 行（见 §4.3） | §7 + 卡面增量 2 |
| `apps/api/tests/test_guards_ci_secret_mask.py` | 新增 16 用例 | §7「对应测试」 |
| `apps/api/tests/test_tzdata_dependency.py` | 新增 4 用例 | 同上 |
| `docs/04_engineering/conventions.md` | §4.5 第 3 条补 5 行（掩码纪律 + 执行面点名） | §12 明确允许「§4.5 第 3 条补一句」 |

台账 `docs/任务规划V0.12.0/00-README.md` 追加 2 行（P-109 / P-110，见 §7）。§12 没有列台账，
但卡面「熔断」节写着「前提与现读不符 ⇒ 先登记 P 号」——登记动作的落点就是台账，
所以本批按 V0.17 队列既成惯例**只追加、不改任何历史行**。

未动：`apps/api/Dockerfile`、任何 `app/**`、其他工作流的业务步（§13 禁止面）；
`docs/任务规划V0.18.0/steps/STEP-32-*.md` 卡面本体（不属执行方面）。

## 1. 开工读数（现读锚 = `f62054b`）

| 锚 | 读数 | 与卡面关系 |
|---|---|---|
| `.github/workflows/ci.yml:472-473` | 两行 `echo "<KEY>=$(python3 -c ...)" >> "$GITHUB_ENV"` | 与卡面 §6 输入一致 |
| `grep -rn 'GITHUB_ENV' .github/workflows/` | 全仓**只有**这 2 处 | 守卫的可检面从一开始就已知是 2 行 |
| `grep -c 'add-mask' .github/workflows/ci.yml`（修复前） | **0** | 判据「≥2」的先红侧 |
| `grep -n tzdata apps/api/pyproject.toml` | **0 命中** | P-106 成立 |
| `apps/api/uv.lock:1041` | `{ name = "tzdata", marker = "sys_platform == 'win32'" }`，**挂在 psycopg 的 dependencies 下** | 卡面 §6 只给行号不给归属；此处补正——传递方是 psycopg，不是 dateutil |
| `apps/api/uv.lock:1767` | `[[package]] name = "tzdata"`，version `2026.3` | 包条目本来就在（只是没人无条件要它） |
| 本机 venv `importlib.metadata.distribution("bothot-backend").requires` | 无 tzdata | 声明侧先红可在本机复现 |
| 本机 venv：`zoneinfo.TZPATH` 置空后 `ZoneInfo("Asia/Shanghai")` | **仍可构造**（tzdata 2026.5 作为传递依赖在场，走包兜底） | ⚠ 卡面 S32.3 指定的那条单测在 win32 上**不是先红**，它只能防复发；先红由声明侧承担（§4.1） |
| `python -c "import yaml"`（系统 Python 3.12.10） | pyyaml 6.0.3 在场，但 `pyproject` 未声明 | ⇒ 守卫必须只用 stdlib（现读依据，不是偏好） |
| `which uv` | **未安装** | 卡面增量 2 的处置：装在仓库外 |

uv 安装读数（仓库外）：`python -m pip install --user --index-url https://pypi.tuna.tsinghua.edu.cn/simple uv`
⇒ **uv 0.13.5**，落在 `%APPDATA%\Python\Python312\Scripts\uv.exe`（仓库内零字节改动），
解释器 = Python 3.12.10（`sys.prefix` 指向 `AppData\Local\Programs\Python\Python312`）。

## 2. S32.1 密钥掩码

改法严格照 D-V18-03：生成值先赋本步局部变量 → `echo "::add-mask::$变量"` → 再写 `$GITHUB_ENV`。
密钥长度（32 字节）与生成方式（`base64(os.urandom(32))`）**一字未动**。

现读行号（交付提交）：注释 `:479`、`push_master_key` 赋值 `:481` / 掩码 `:482` / 写入 `:483`、
`engine_master_key` 赋值 `:484` / 掩码 `:485` / 写入 `:486`。
**本文件全程不抄任何密钥值**（§4.5 第 3 条）。

判据读数：`grep -c 'add-mask' .github/workflows/ci.yml` = **3**。
其中 1 处是 `:479` 的说明行，真掩码 2 处 ⇒ 卡面「≥2」满足。
这条计数之所以不能当判据用（注释也进数），正是 §3 里「注释行不得登记掩码」那一发的理由。

## 3. S32.2 守卫与反证

### 3.1 判据（三条，全部可复跑）
1. 逐步解析 `.github/workflows/*.yml` 的 `run` 正文（缩进切块，不用 yaml——pyyaml 未声明）。
2. 写入 `$GITHUB_ENV` 的那一行：值来自本步 `$(...)`（直接内联，或经 `x=$(...)` / `y=$x` 两层复制）
   且在该行**之前**没有对同一变量的 `::add-mask::` ⇒ 违规，点名「文件 + 步骤名 + 行号」。
   内联 `$(...)` 直接判违规（这种形状无法先掩码，只能改写成赋值形）。
3. 可检面为零 ⇒ **rc=3，不是通过**（工作流目录空、或整个仓库不再有任何 `$GITHUB_ENV` 写入面）。
   越线 ⇒ rc=1；全绿 ⇒ rc=0。

### 3.2 接线三处（门进了 CI 才算存在）
- `Makefile:176-178` 薄转调 + `Makefile:194` 聚合前置
- `scripts/entry.py:449`（任务表）与 `:455`（`guard` 复合元组）
- `.github/workflows/ci.yml` Governance 步：`:260` 初始化 `rc_ci_mask=0`、`:261` 调用并 `|| rc_ci_mask=$?`、
  `:263` 打印、`:269-272` 非 0 即 `exit 1`（含第三态 3，与既有两门同口径）。
  只做加法：既有 `if [ "$rc_rounds" -ne 0 ] || [ "$rc_evidence" -ne 0 ]` 那一行未改
  （改它会撞 `test_guard_rounds.py` 的 `-ne 0` 计数断言，也撞卡面增量 1「不许改已有行的语义」）。

### 3.3 反证与极性读数（原始输出见 `s32_gate_polarities.txt`）

| 极性 | 输入 | 违规数 | 结论 |
|---|---|---|---|
| 修复前形状 | `git show HEAD:...ci.yml`（本次交付的 HEAD = 73b9fa6） | **2**（:472 :473） | 门对 P-107 的原形有召回 |
| 修复后 | 交付工作树 | **0** | 不误伤正确写法 |
| 卡面指定反证 | 删掉两行 `::add-mask::` | **2**（:481 :483 点名 push/engine） | 判据确实咬在修复本身上 |
| 顺序颠倒 | 掩码写在之后 | **1** | 顺序敏感，不是"有没有出现过 mask" |
| 注释伪装 | `# echo "::add-mask::$x"` + 真实未掩写入 | **1** | 说明文字不得改变结论（本轮自查踩到，见 §3.4） |
| 跨步安全形 | 上一步生成+掩码，本步写入 | **0** | 掩码在整个 job 内有效 ⇒ 放行是对的 |
| 常量 / `${{ }}` / `$PWD` 写入 | 三条非生成值写入 | **0** | 假阳控制面 |
| 第三态① | `WORKFLOW_DIR` 指向空目录 | rc=**3** + 点名"没有任何 workflow 文件" | 目录空不等于通过 |
| 第三态② | 有工作流、但全仓不再有任何 `$GITHUB_ENV` 写入面 | rc=**3** + 打印 `` `0 行写 $GITHUB_ENV` `` 与「判据未被检验」 | 判据失去可检面时必须自曝，不能顺着"零违规"落绿 |

### 3.4 自查到的一处自洗（当场修）
守卫第一版写成 `if line.startswith("#") or "::add-mask::" in line: masked |= …`，
于是**注释里提到 `::add-mask::$x` 就把 `x` 登记成已掩码**——真实泄漏会被一句说明文字放行。
改为注释先 `continue`、再谈掩码；并把这一发做成常驻用例
`test_comment_lines_do_not_count_as_mask_or_write`（三行形状：注释掩码 + 真实写入 ⇒ 必红）。
触发时机就在本仓的真实文件上：`ci.yml:479` 那句注释含 `::add-mask::` 与 `$GITHUB_ENV` 两个词。

### 3.5 用例与门的实跑读数
- `pytest tests/test_guards_ci_secret_mask.py -q` ⇒ **16 passed**
- `pytest tests/test_tzdata_dependency.py -q` ⇒ 先红 **2 failed / 2 passed** → 改后 **4 passed**（见 §4.1/§4.3）
- `python scripts/guards.py guard-ci-secret-mask` ⇒ rc=0，
  stdout：`扫 <绝对路径>\.github\workflows 下 3 个工作流 / 55 个 run 步，其中 2 行写 $GITHUB_ENV`
- 与既有治理用例同跑：`pytest tests/test_guard_rounds.py tests/test_guards_ci_secret_mask.py tests/test_tzdata_dependency.py -q` ⇒ **69 passed**
- 判据的第三态不是纸面声明：`test_gate_returns_third_state_when_it_has_nothing_to_judge`
  用 `monkeypatch` 把 `WORKFLOW_DIR` 指向空目录、再放一个"没有 GITHUB_ENV 写入面"的工作流，
  两发都断言 rc=3 **且**断言点名原因（只看 rc 会分不清是哪条支路在说话）。
  这条用例反过来逼出一个小修：`rel = str(path.relative_to(ROOT))` 在跨盘临时目录上抛
  `ValueError`（win32 上 C: 的 tmp 对 D: 的仓库就是跨盘）⇒ 改为 `path.name`，
  扫描目录已在表头打印，文件名在同一目录内唯一。

## 4. S32.3 tzdata 显式依赖

### 4.1 先红（改 `pyproject` 之前实跑）
`pytest tests/test_tzdata_dependency.py -q` ⇒ **2 failed / 2 passed**
- FAILED `test_tzdata_is_a_declared_runtime_dependency`（pyproject 主依赖里没有 tzdata）
- FAILED `test_lock_file_agrees_with_the_declaration`（锁里 bothot-backend 的直接依赖没有它）
- PASSED `test_zoneinfo_shanghai_resolves_from_the_tzdata_package`（本机传递依赖在场，见 §1 的 ⚠）
- PASSED `test_the_empty_tzpath_patch_itself_is_effective`（反证：TZPATH 置空可观测——不存在的时区名必须抛 `ZoneInfoNotFoundError`）

### 4.2 修法
`apps/api/pyproject.toml` 主依赖加 `"tzdata"`，**不带任何平台 marker**，并写清为什么
（导入期构造 `ZoneInfo`、进程起不来而不是功能降级、此前只靠 psycopg 的 win32 传递依赖）。
刻意不钉版本：钉一个下限只会让锁 diff 里多出一条无据的约束。

### 4.3 重锁读数（禁手改，全部由 uv 生成）
```
$ UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple uv lock
Resolved 66 packages in 3.71s          rc=0
$ uv lock --check                       rc=0（Resolved 66 packages in 2ms）
$ git diff --stat apps/api/uv.lock      2 ++（净 +2 行，0 删除）
```
差异逐行（全文两行都是 tzdata，其余 66 个包版本零变化）：
- `:154` bothot-backend 直接依赖表加 `{ name = "tzdata" }`
- `:193` `package.metadata.requires-dist` 加 `{ name = "tzdata" }`
索引保持核验：`grep -c pypi.tuna.tsinghua uv.lock` = **1483**（与改前相同），`grep -c pypi.org` = **0**。
`uv.lock:1041` psycopg 自己那条 win32 marker 原样未动（那是它的声明，不是我们的）。

改后：`pytest tests/test_tzdata_dependency.py -q` ⇒ **4 passed**。

### 4.4 效力来源如实登记（卡面增量 3）
本卡真正生效的是 `pyproject.toml` 那一行——现读 CI（`ci.yml:64`、`ci-windows.yml:174`）、
Security 与 `apps/api/Dockerfile:32` 全部走 `pip install` 读 pyproject，
**没有任何运行面消费 `uv.lock`**。锁文件保持同步只是 D-V18-12 的纪律要求；
"锁文件不被消费"这件事本身属 P-55，由 STEP-38 处理，本卡不越界。

## 5. 门禁与本批其它读数

### 5.1 本批实跑的其它门（push 前）
| 门 | 读数 |
|---|---|
| `python scripts/entry.py guard-structure` | rc=0，4 个目录全 ✅ |
| `python scripts/check_docs_consistency.py` | rc=0，23 个路径引用 0 个不存在 |
| `python scripts/check_entry_parity.py` | ✅（Makefile 38 目标 / entry.py 42 任务） |
| `ruff check scripts/guards.py scripts/entry.py 新测试×2` | All checks passed |
| `python scripts/guards.py evidence-check --base HEAD`（读**索引**，staged 13 个文件） | rc=0：前置敏感形门 + stdlib 证据自测（`prove_dsn_policy` / `g24_static_check` / `prove_net_isolation` 各 SELF-TEST PASS）+ 真实工具两步 |
| 同一步里的 gitleaks | 本机**装有** gitleaks：`374 commits scanned / no leaks found`（14.7s）。这只覆盖历史，本批尚未入库的新文件由上一行的敏感形门读索引，两档合起来才是完整判据 ⇒ 历史侧的"0 新增"以 `@ci` Security job 为终判 |
| `python scripts/guards.py bogus-name` | rc=1（未知子命令不静默放行）；顺带读数：用法行由 `GUARDS` 的键动态拼出，新门自动进提示，无需第二处维护 |

⚠ 一条读法纪律（本批自己差点踩）：`guards.py X | tail -6; echo $?` 打印的是 `tail` 的退出码。
上面所有 rc 一律用"重定向到文件再取 `$?`"复测，不用管道口径。

### 5.2 本地全量后端套件——本机未复算（如实写，不拿部分读数冒充全量）
`pytest tests/ -q` 在本机跑到 20 分钟仍未出汇总（无 PG 监听、无 docker CLI，连库与 e2e 面在等超时），
主动中止。**本机不产全量读数**，连库面按 D-V18-09「CI 是唯一正式验收面」以 `@ci` 为准
（AGENTS.md 现有口径同样是"连库结论以 @ci 为准"）。
本批改的是工作流/守卫/依赖声明三处，未动 `app/**`，所以本地只跑**受影响的文件全集**——
判据是"哪些测试文件读我改的这些面"，用 `grep -rln 'workflows/\|Makefile\|entry\.py' apps/api/tests/*.py` 现读选出：
`pytest tests/test_guard_rounds.py tests/test_guards_ci_secret_mask.py tests/test_tzdata_dependency.py
tests/test_module_coverage_gate.py tests/test_secret_shape_gate.py tests/test_collection_contract.py
tests/test_manifest_asset_alignment.py tests/test_ci_windows_skip_gate.py -q`
⇒ **413 passed / 5 skipped**（三次实跑 41.12s / 33.89s / 20.76s；前两次计数 412，
第三次把第三态那一发补上后是 413）。那 5 条 skip 点名读：
全部在 `apps/api/tests/test_manifest_asset_alignment.py` 的 `:651 :674 :727 :748 :769`，
原因统一是 `AIDEANBOT_TEST_PG_DSN 未设置`（本机无 PG 监听）⇒ 连库面，与 CI-Windows 的 skip 门禁无关。

### 5.3 两个"现读与卡面不同"的落点
1. **聚合目标必须改**：`test_guard_rounds.py:410-416` 判的是 `sorted(guard: 前置) == sorted(GUARDS)`（双向）。
   所以新门进 `GUARDS` 的那一刻，Makefile 的 `guard:` 那一行就必须加名——这不是"改已有行的语义"，
   而是既有断言唯一允许的加法。不改它，本地必红。
2. **Makefile 帮助文本里不能出现 `$GITHUB_ENV`**：`check_entry_parity` 把 `$(…)` 之外的 `$X` 也当变量读，
   实测报 `recipe 用了未定义的变量：G`（`$GITHUB_ENV` → 变量 `G`），并被
   `test_makefile_has_no_undefined_variable_and_the_check_itself_has_polarity` 抓住。
   措辞已改为「写进 GITHUB_ENV 前必须先 add-mask」。GNU make 自己会剥注释，所以这只是本仓工具的口径。

### 5.4 mypy 的覆盖面（本批不修，登记 P-110）
CI 两处都只跑 `mypy app`（`ci.yml:77`、`ci-windows.yml:191`）⇒ `scripts/**` 零机检。
本机对 `scripts/guards.py` 跑 mypy 得 3 条 error（`TextIO.reconfigure` union-attr、
`main()` 里给守卫函数传参的 call-arg、以及一条 not-covered-by-ignore note）；
对 `git show HEAD:scripts/guards.py` 跑同一命令得**同样的 3 条** ⇒ 非本批引入，未新增。

## 6. S32.4 与三绿（push 后回填）
- 交付提交：待回填
- `compose-smoke` 步日志原文里两把密钥所在位置显示为 `***`：只记行号，不抄值
- CI / CI-Windows / Security 三绿（同一 head、attempt 1）：待回填
- gitleaks 全历史新增：待回填

## 7. 台账追加（P-109 / P-110 摘要）
- **P-109**：`guard-ci-secret-mask` 的召回边界按卡面停在"同一步内"。
  代价是"上一步生成、全程未掩码、下一步才写 `$GITHUB_ENV`"这一形状本门看不到。
  要不要扩到 job 级、以及要不要把 `$GITHUB_OUTPUT` 纳进来（同一暴露面），交规划方裁定。
- **P-110**：`scripts/**` 不在任何 mypy/ruff 机检口径内（CI 只 `mypy app`），
  实测 `guards.py` 带 3 条既有 error。守卫本身是判据的执行体，它自己的类型面没人管。
