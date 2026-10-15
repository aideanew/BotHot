# EVD-V5-00X — Windows 10 一等开发平台：装 / 跑 / 验 读数

采集机：`@win`（Windows 10.0.19045 / x64 / Git Bash / 本机首次自建工具链）
基线：`main@17c5d28`（STEP-00X 的卡与规划面已在 `3efdbb4`/`6764ebe` 入库）
采集时间：2026-10-15 12:30–13:3x（本地 Asia/Shanghai）
依据：D-V4-01（正式验收面 = CI `ubuntu-latest`；`windows-latest` = 开发平台门；本地读数只算烟测）
> 本文件所有数字都是 **@win 现跑**，不是 `采信[REMOTE]`。凡是没有跑出来的，写在 §6"未证"里而不是省略。

## 1. 工具链（与 CI 同版，用户授权自装）

| 工具 | 本机版本 | 装法 | CI 锚点 |
|---|---|---|---|
| Python | **3.12.10**（新装；系统里原有 3.11.9 不用） | `winget install -e --id Python.Python.3.12 --silent` → rc=0，日志记"已成功安装" | `ci.yml:56`、`security.yml:103` = 3.12 |
| Node | **v24.21.0**（已存在） | — | `apps/web/.nvmrc` = 24.21.0 |
| pnpm | **9.15.9** | `npm i -g pnpm@9.15.9` → rc=0（落 `%APPDATA%\npm`，未碰 Program Files） | `apps/web/package.json` `packageManager` |
| gitleaks | **8.21.2** | 官方 `gitleaks_8.21.2_windows_x64.zip` 解到 `%LOCALAPPDATA%\Programs\tools\gitleaks\`，`gitleaks.exe version` → `8.21.2` | `security.yml:53` `GITLEAKS_VERSION: "8.21.2"` |
| GNU make | **4.4.1 (Windows32)** | `winget install -e --id ezwinports.make` → rc=0 | 仅本地快捷方式，CI 不调用 make |
| Docker / WSL 发行版 | **都没有** | 不装（见 §6） | CI ubuntu 有 PG service |
| gh | 没有 | 未装（D-V6-02 的 CI 认定改用 GitHub REST 原始响应） | — |

## 2. S00X.1.1 现状测量（改造前）

```
$ make help                      → RC=127  make: command not found
$ bash scripts/preflight.sh      → RC=1（脚本本身能在 Git Bash 下跑！）
    node=24.21.0 == .nvmrc ✅ / pnpm=9.15.9 == packageManager ✅
    ❌ ruff 版本不符：pyproject 钉 0.12.12，本机 <缺失>
    ❌ mypy 版本不符：pyproject 钉 2.3.1，本机 <缺失>
    ⚠️ python 版本差异：CI=3.12 本机=3.11
    ❌ BACKEND: ruff / mypy 两步都 No module named
    ✅ FRONTEND: lockfile drift frozen 口径 exit=0
    ❌ typecheck: Cannot find module '…apps\web\node_modules\typescript\bin\tsc'（依赖未装）
    ❌ preflight 有红
$ python -m ruff --version        → RC=1  No module named ruff   （系统 3.11）
$ gitleaks --version             → RC=127  command not found
$ python3 --version              → 无输出、rc=0（Microsoft Store 空壳 stub——假通过）
```
端口占用探测：`netstat` 对 5433/6380/3300/3200 **无任何 LISTENING** ⇒ 本机当时没有依赖服务。

## 3. 改了什么（实体一次落地，Makefile 变薄）

| 文件 | 动作 | 关键判据 |
|---|---|---|
| `scripts/entry.py` | 新建（34 个任务） | 平台差异只出现在 `dispatch()`+`find_tool()`；缺工具 `SKIP(tool missing)` 且 **rc=3** |
| `scripts/guards.py` | 新建 | guard-ports/versions/structure/evidence-check 的**新实体**（原先是 Makefile 里的多行 shell） |
| `scripts/check_entry_parity.py` | 新建 | Makefile 30 个目标全部能解析到实体且 recipe 已转调；`help` 是唯一保留内联的目录页 |
| `Makefile` | 26 个开发目标 → `@$(ENTRY) <task>`；4 个守卫目标 → `@$(GUARDS) <task>`；复合目标（install/test/test-all/lint）改 `@:` 靠前置，避免装两遍；204 → 160 行 | 新增 `ifeq ($(OS),Windows_NT)` 选 `python` vs `python3` |
| `.gitattributes` | 从只有 `*.sh text eol=lf` 扩为 `* text=auto eol=lf` + 关键后缀 + 二进制 + `/.project/** -text` | 影响面预估见 `../../任务规划V0.11.0/evidence/17c5d28/crlf_impact.txt` |
| `.gitignore` | 追加 `.venv/ venv/ env/` | 实测原本**没有任何 venv 规则**，而 `preflight.sh` 的修复提示要求 `apps/api/.venv` |
| `docs/04_engineering/cross-platform.md` | 新建 | 分工表 + 版本锚 + 两个 Windows 专属坑 |
| `README.md`、`conventions.md` §5.3、`project-map.md` | 指向新入口 | `conventions.md` §5.1 的"包管理：uv"与 CI 实际用 pip（`ci.yml:59`）不符，已在 §5.3 更正 |

## 4. @win 运行读数（改造后，全部现跑）

| # | 任务 | 命令 | rc | 读数 |
|---|---|---|---|---|
| 1 | 前端依赖 | `pnpm install --frozen-lockfile` | **0** | Done in 51.1s；`node_modules` 30 个顶层目录 / 528 MB；**未产生任何未跟踪项**（被 `node_modules/` 规则覆盖） |
| 2 | 后端依赖 | `.venv`（3.12）+ `pip install -e ".[dev]" pytest-cov` | **0** / **0** | 两步各自 rc=0；`apps/api/.venv` 已被新规则忽略 |
| 3 | lint-backend | `ruff check app tests` | **0** | `All checks passed!`（ruff 0.12.12，venv 内） |
| 4 | typecheck-backend | `mypy app` | **0** | `Success: no issues found in 107 source files` |
| 5 | test-frontend-unit | `pnpm run test:unit` | **0** | **45 files / 366 tests passed**，27.87s —— 与 V0.10.0 在 Linux 沙箱报的 366 是同一数字，**这条从此不再是 `采信[REMOTE]`** |
| 6 | build-frontend | `pnpm run build`（`NEXT_PUBLIC_API_MOCK=false`） | **0** | 产物：`/subscriptions 5.56 kB`、First Load 103 kB、Middleware 34.1 kB（Linux 侧读数是 5.56/103/34.2 ⇒ 跨机一致） |
| 7 | test-backend | `pytest tests/ -q` | 见 §4.1 | 采集 1063 条用例耗时 **262.65s**（异常慢，已记风险） |
| 8 | guard-ports | `python scripts/guards.py guard-ports` | **0** | ✅ 无旧端口 3333；✅ session cookie = bothot_session |
| 9 | guard-versions | 同上 guard-versions | **0** | .nvmrc 24.21.0 / Dockerfile 24 / engines 24 / compose BASE_IMAGE 24 ⇒ ✅ 一致 |
| 10 | guard-structure | 同上 | **0** | 四个目录全存在 |
| 11 | entry↔make 一致性 | `python scripts/check_entry_parity.py` | **0** | Makefile 30 目标 / entry.py 34 任务，全部有实体且已转调 |
| 12 | scan-secrets | `gitleaks detect --source . --config .gitleaks.toml`（8.21.2，git 模式） | 1（预期：真有命中） | 见 §4.2 |
| 13 | migrate（无 PG） | `entry.py migrate` | **3** | 1s 内 `SKIP(service unavailable) PostgreSQL localhost:5433`，**不再挂起** |
| 14 | docker-ps（无 docker） | `entry.py docker-ps` | **3** | `SKIP(tool missing) docker` |
| 15 | `make help`（改造后的 Makefile） | GNU make 4.4.1 @win | **0** | 列出 30 个目标；说明薄转调没有破坏 `## 描述` 约定，也说明 Windows make 确实找到了 Git 自带的 sh |

### 4.1 后端测试套件（@win，无 PG）
- 收集：`pytest tests/ --collect-only -q` → **1063 tests collected in 262.65s**（异常慢，见下）。
- 定向子集：`pytest tests/test_alerting_default.py tests/test_kb_multisource_anchor.py -q --durations=5`
  → **5 passed, 4 skipped in 0.78s**，rc=0（4 条 skip = 连库类，本机无 PG，符合预期；最慢单项 0.01s）。
- 全量：跑了 **35 分钟**只推进到第 35 个用例（`.....ss…`）后被人为终止。
  ⇒ **判定：@win 全量 pytest 不作为验收读数。** 已知事实只有"收集要 262s、定向子集 0.78s 就过"，
  所以瓶颈在**某些测试模块 itself 在 Windows 上极慢/卡住**（模块级 import 或某个等待网络/子进程的用例），
  具体是哪一个**未定位**——这需要逐个文件跑一轮才能说，属新任务（已登记 05 U-20），
  不许把它写成"Windows 不支持"或"已通过"。连库与全量读数按 D-V4-01 由 `@ci ubuntu` 出。

### 4.2 make 与 entry.py 的退出码对照（6 任务实测）
| 任务 | `make X` | `entry.py X` | 同为 0/非 0 |
|---|---|---|---|
| dev | 0 | 0 | ✅ |
| lint-backend | 0 | 0 | ✅ |
| fmt-check-backend | 2 | 1 | ✅（都非零） |
| docker-ps | 2 | 3 | ✅ |
| guard-ports | 2（改造前） | 3（当时仍依赖 make）→ 0（改实体进 guards.py 后） | ✅ |
| migrate | 2 | 3 | ✅ |
> **为什么不能要求逐值相等**：GNU make 把 recipe 的任何失败折成 2。三态（0/1/3）只在 entry.py 层保留。
> 本卡验收标准里原来写的"退出码一致"因此被按实测改正为"零/非零一致"，改正记录在卡的 §验收标准。

## 5. 执行中验出的缺陷（4 条，都已处置并写进文档）

1. **`python3` 在 Windows 是空壳 stub**：`python3 --version` 无输出但 rc=0。Makefile 原来 `PYTHON := python3`
   意味着 Windows 上"跑了、通过了、其实什么都没发生"。处置：`ifeq ($(OS),Windows_NT)` 选 `python`。
2. **无 PG 时 `alembic upgrade head` 挂住而不是失败**：150s 被 timeout 打断才停（psycopg 无 `connect_timeout`，
   Windows 对未监听端口不立即 RST）。挂住比红更危险——执行者会以为在跑。处置：`entry.py` 的 migrate/migrate-down/
   migrate-new 先 TCP 探测（2s），不可达 `SKIP(service unavailable)` + rc=3。
3. **GNU make 4.4.1 for Windows 跑不了原守卫 recipe**：`make guard-ports` 报
   `printf: -c: line 4: unexpected EOF while looking for matching '"'`（多行 `; \` 续行 + shell 变量），
   改 LF 之后仍错 ⇒ 不是行尾问题，是 Windows make 的 recipe 传递方式问题。处置：守卫实体搬进
   `scripts/guards.py`，Makefile 与 entry.py 都转调它（唯一源，不留第二份实现）。
4. **gitleaks git 模式在 @win 报 `stderr is not empty`**：trace 抓到真凶是 Git for Windows 的系统级
   `/etc/gitattributes` 给 docx/pdf 配的 `textconv=astextplain`，而 `docx2txt.exe` 不存在：
   `C:\Program Files\Git\usr\bin\astextplain: line 18: docx2txt.exe: command not found`
   ⇒ `git log -p` 的 stderr 被污染，gitleaks 判整次扫描失败。处置：扫描时带 `GIT_ATTR_NOSYSTEM=1`
   （**不改任何 git 配置**），实测从"ERR + 未知"变成 **156 commits scanned / 8 leaks found**，
   且与 CI（ubuntu，没有那套系统 attrs）的语义更一致而不是更松。

## 6. 未证 / 不做（不静默略过）

| 项 | 状态 | 原因 |
|---|---|---|
| 连库 pytest（PG 16） | 🛑 @win 不做 | 无 Docker Desktop、无 WSL 发行版。装 Docker Desktop 要管理员+重启+许可，属"影响共享系统且不可逆面大"，按硬规则停手并把这一步交给 `@ci`（D-V4-01 本来就以 ubuntu 为正式面） |
| Redis 7 / compose 全栈 | 🛑 同上 | 同上 |
| CI `windows-latest` 首绿 | ⚪ 待 push 后取 run id + head_sha + conclusion（D-V6-02），本机无 `gh` ⇒ 用 GitHub REST 原始响应存证 | job 已写入 `ci.yml`（`windows-dev`，ubuntu 两个 job 一行未改） |
| `SKIP_BASELINE_WIN=320` | ⚠ 保守上界，**不是测量值** | 首跑读数回来后收紧；写在 job 注释里 |
| Playwright e2e | 🛑 @win 不跑 | `--with-deps` 在 Windows 无 sudo 语义；e2e 的门禁一直在 ubuntu job |
| `scripts/rotate_keys.sh` 等上线脚本 | 标「仅 Linux」，不改造 | 本卡 S00X.1.1.1 明示 |
| `S00X.2.2.1` 的"只降不升"判据 | 0 → 0（**该判据在本仓是空的**） | HEAD 里两个 .py 早已用 `Path.read_text(encoding="utf-8")`；没有可降的对象。如实记空，不谎报改进 |

## 7. `@ci` 的 windows-dev 首跑（写这节时仍在跑）
`https://github.com/aideanew/BotHot/actions/runs/38688133750/job/116267611775`（head_sha `d2462e2b`，取 job steps 原始响应）

| 步 | 结论 |
|---|---|
| 1–7 建环境（checkout / pnpm 版本解析 / pnpm-action / setup-python **3.12** / setup-node **按 .nvmrc** / Tool fingerprint） | **success** |
| 8 Install backend deps（`.[dev]` + pytest-cov） | **success** |
| 9 Install frontend deps（`--frozen-lockfile`） | **success** |
| 10 `entry.py 与 Makefile 目标面一致性`（`scripts/check_entry_parity.py`） | **success** |
| 11 `ruff check app tests`　12 `mypy app` | **success / success** |
| 13 Backend tests（全量 pytest） | **in_progress**（写入本行时） |
| 14 skip 门禁 / 15 vitest+typecheck / 16 build / 17 取证行 | 未开始 |

⇒ **S00X.4.2「两个 job 都 success」尚未达成，不写成达成。**
但 step 13 的卡住已经是这条新门禁抓到的第一个东西：**全量 pytest 在 `windows-latest` 上同样不动**，
与 §4.1 本机 @win 的 stall 同形（本机：收集 1063 条 262s、35 分钟只推进 35 项；定向 5 条 0.78s 全过）
⇒ U-20 不是"我这台机器的毛病"，是 **Windows + 这套测试** 的平台级事实。
按 job 的 `timeout-minutes: 35`，它很可能以超时收场。**不去调判据把它做绿**：windows-dev 的用途正是抓这种断裂，
首跑就抓到，说明门禁有效而不是失败。后续动作（不属本卡，登记在 05 U-20）：用 `--collect-only` 逐文件 +
`--durations` 定位卡住的模块，修完再看这个 job 转绿。
