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

## 8. windows-dev 终局与 U-20 的定位读数（同日 15:0x，`@win` + `@ci`）

**job 级结论**（`runs/38688133750/jobs` 原始响应）：`windows-dev = completed / cancelled`，
被取消的步是「Backend tests（全量 pytest）」；前 12 步全 **success**：
建环境（pnpm 版本解析 / setup-python 3.12 / setup-node 按 .nvmrc / Tool fingerprint）、
Install backend deps、Install frontend deps、**`entry.py 与 Makefile 目标面一致性`**、`ruff check app tests`、`mypy app`。
后续三步（skip 门禁 / vitest+typecheck / build）因上一步被取消而 **skipped**，末步「取证行」`if: always()` 仍 success。
⇒ **S00X.4.2 未达成**（要的是两个 job 都 success），本卡不写成达成；`@ci` 侧 ubuntu 五个 job 在同一提交全绿，主干不受影响。

**U-20 的定位过程（全部 @win 实测，含被否证的假设）**

| 探针 | 读数 | 结论 |
|---|---|---|
| 前 20 个测试文件逐个 `timeout 40 pytest <file> -q` | `test_alerting_default.py` 0、`test_alerting_drill.py` 0、`test_article_identity.py` 0、`test_asset_fragment_guard.py` 0、**`test_auth.py` 124**、**`test_backchannel_logout.py` 124** | 卡点收敛到 auth 域两个文件 |
| `python -c "import test_auth"` | **2.2s 完成** | 不是模块导入的问题 |
| `pytest tests/test_auth.py --collect-only -q -s`（无缓冲） | **90s 不返回**，输出停在 app.main 的 schema 告警之后 | 卡的是 **pytest 采集期** |
| `socket.create_connection(('127.0.0.1',1), 8)` | `ConnectionRefusedError [WinError 10061]` **2.05s** | 否证「端口 1 拒连慢」；但注意它**不是 0s**——84 个文件各摊 2s 正好是收集 262s 的量级 |
| `env \| grep -i proxy` | **空** | 否证「宿主代理劫持出站」（conftest 的 `_isolate_proxy_env` 在本机无事可做） |
| `create_async_engine(refused).connect()` **不经 conftest** | `psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop'` 0.00s | **这个"发现"是我的探针自己造的假象**：conftest.py:26 已在 import 时设 `WindowsSelectorEventLoopPolicy`，测试进程里没有这个问题。记下以免下一位照着修 |
| `-o asyncio_default_fixture_loop_scope=function` | 仍 **124** | 否证「pytest-asyncio 的 loop scope」 |
| `-p no:asyncio` | 仍 **124** | 否证「pytest-asyncio 插件本身」 |

**还剩下的下一步**（不属本卡，已写进 05 U-20 归属列）：拿栈而不是猜——`py-spy dump` 挂住的 pytest 进程，
或把 `test_auth.py` 的 fixture 树剪到最小可复现段。

## 补记（2026-10-16 14:42 完成）：本机 `pytest -q` **全量跑完了**，82 分钟、0 失败

| 读数 | 值 |
|---|---|
| 命令 | `cd apps/api && .venv/Scripts/python.exe -X utf8 -m pytest -q -p no:cacheprovider`（输出写文件、不经管道） |
| 结果 | `769 passed, 422 skipped, 1 warning in 4904.92s (1:21:44)` `@win` |
| 失败 | **0** |
| 起点时刻对应的树 | 约 `2df0f88`（13:21 启动，故**含** `c966a34` 的第六轮返工，**不含**其后的 `7baded8`/`4427fd1`/`81e1f4f`） |

### 这条读数能证明什么、不能证明什么

**能证明**：
- 本机 Windows 上全量收集与执行**可以跑完**——之前两次尝试分别栽在"管道到 `tail` 取不到中间读数"
  与我在 45 分钟无输出时手动中止（那是取证方式的问题，不是用例的问题）。
- 契约面那批改动（`app/contracts/*` 与比对器）没有把后端整体打红。

**不能证明**：
- **422 条 skip 说明本机没有真库**（PG 不可达时按项目纪律 skip 而不是 fail）。所以这条
  `769 passed` 与 AGENTS.md 里 `@linux` 的 `1058 passed / 6 skipped` **不是同一个覆盖面**，
  两个读数不可互换引用，也不该拿前者去更新后者的基线。
- 起点在 13:21，pytest 在收集期就把模块 import 完了 ⇒ 我 14:0x 之后的提交**不在这次跑动的覆盖里**。
  本批全量结论仍以 `@ci` 为准（`4427fd1`：CI run 38860866657 completed/success；
  Security run 38860866667 completed/success；CI-Windows run 38860866656 取数时 in_progress）。

### 与 U-20/U-23 的关系（别把这条读成"卡死已解决"）

这次能跑完，不等于 auth 域那两个文件的**收集期挂起**（124s 超时）已解决——单文件级别的现象还在：
本次是在**没有** `--timeout` 的情况下整批跑完的，说明"挂起"更像是**特定文件 + 超时参数**的组合，
而不是全库普遍卡死。下一步仍然是拿栈不是猜（`py-spy dump` 或把 `test_auth.py` 的 fixture 剪到最小可复现段），
归属没变（05 的 U-20/U-23）。

### 在跑的后续取证

`pytest -q -rs` 的第二次全量已启动（输出 `.staging/full_run_rs.txt`），目的是把 **422 条 skip 的构成**
逐条打出来——S00X.4.1 要求 windows job "在 summary 里打印 skip 构成"，现在我只有条数、没有分类。
它覆盖的是 `81e1f4f` 起的树；跑完前我不再改 `apps/api` 下的文件，免得读数与代码错位。

---

## 4. `pytest -q -rs` 全量跑完：422 条 skip 的构成（S00X.4.1 要的正是这张表）

读数（`@win`，本机 Win10 + `apps/api/.venv`）：**801 passed / 422 skipped / 0 failed，4905.45s（1:21:45）**。
`-rs` 打出 400 行 `SKIPPED` 摘要（部分同源 skip 被 pytest 合并计数），按原因归类：

| 条数 | 原因（逐字取自摘要） | 含义 |
|---|---|---|
| 300 | `AIDEANBOT_TEST_PG_DSN 未设置：连库用例需要独立测试库` | **配置缺**：`conftest.py:49-68` 解析不到 DSN ⇒ `conftest.py:106-107` 在夹具里 skip |
| 93 | `PG 不可达（OperationalError），Docker 引擎恢复后…` | **实例缺**：已配 DSN 但连不上 |
| 2 | `测试 Redis 不可达（ConnectionError）` | 容器缺 |
| 1 | `Redis 不可达（redis://localhost:6379/0，TimeoutError）` | 同上，另一条口径 |
| 1 | `PG:5433 不可达（OperationalError）` | 部署形态端口，本机无实例 |
| 1 | `PG 不可达（OperationalError）`（无"Docker 引擎"后缀） | 第三处独立措辞 |
| 1 | `LangBot :5300 不可达或未注入管理员凭据` | 外部服务缺 |
| 1 | `宿主未设这 6 个待清代理变量，本条对照在此` | **故意 skip**（代理变量对照用例，本机就是没有） |

**结论（这才是 S00X.4.1 要的判断）**：422 条里 **395 条（≈94%）的原因是同一个——本机没有 PostgreSQL**
（300 配置缺 + 95 连不上，含 `:5433` 那条）。另有 3 条 Redis、1 条 LangBot、1 条是设计如此。
所以 `@win` 的全量读数**不能**当作验收面：它与 `@linux` 基线（1058 passed / 5 skipped）差的不是质量，
是**一片从未执行过的代码**。这条把 AGENTS.md 里"skip 构成 = LangBot/Redis 不可达类 4 条、
PG 不可达类 = 0"那句的历史基线彻底更正了——那是**配好隔离 PG 之后**的读数，本机无 PG 时 PG 类就是 395 条。

顺带一条可执行的改进（不必等 S00X.4.2）：上表里 95 条"PG 不可达"分散在 **3 种措辞**、
300 条"DSN 未设置"另有 1 种，`CI-Windows` job 若要"在 summary 打印 skip 构成"，
应打印**归类后的计数表**而不是 400 行原文，否则读数永远靠人手算。

## 5. 这条读数的失效边界（我自己造的，必须写在这张表旁边）

**它不是 HEAD 的读数。** 起跑树在 `2df0f88`～`81e1f4f` 区间（`git merge-base --is-ancestor 2df0f88 HEAD` 成立），
而**它跑的这 82 分钟里我正在改 `apps/api`**：`app/services/kb.py`（owner 门的一次临时变异 + 还原）、
`tests/test_idor_matrix.py`（从 10 条扩到 14 条）。因此：

- **成立的部分**：skip 的**原因构成**——原因串来自 `conftest` 与环境探测，与我改的两个文件无关，
  395/422 这个判断不受重叠影响。
- **不成立的部分**：`801 passed` 这个总数与"0 failed"不能归到任何单一提交上。
  特别是 `test_idor_matrix.py` 在这个窗口里被改过，它在全量里的最终状态无法归因。
  要一条干净的 `@win` 全量读数，得在 HEAD 上重跑一次（82 分钟，本批没做，见下）。
- 我为什么不直接把 `801` 写进结论：上一批就是因为"总数与树错位"被你（验收方）抓过一次
  （`6e40a94` 那次我标了"起点树=2df0f88、覆盖面不等于 @linux 基线"）。这次重叠更严重，
  所以我把总数降级为"带窗口的读数"，只把**构成**当结论用。

**待做**：HEAD 上一次干净的 `pytest -q -rs` 全量（约 82 分钟 `@win`），用来支撑 S00X.4.1 的出门判据；
以及 `@ci` 的 `196a808` 之后读数（含 P-11 之外的连库面）。

---

## 补记 3（2026-10-17 20:0x 完成）：`@win` 全量**在 HEAD 上跑干净了**，并把 441 收紧进 CI

上一节留的「待做：HEAD 上一次干净的 `pytest -q -rs` 全量」这条，本批完成了，
而且命令与 CI 的 Windows job 逐字相同（`ci-windows.yml:115-119` 那条 run 块）。

### 1. 读数（本机 Win10 + `apps/api/.venv`，`head_sha=10c1019`，起跑前工作树干净、期间零改动）

```
$ python -m pytest tests/ -q --no-header -o faulthandler_timeout=120 \
      --timeout=300 --timeout-method=thread --junitxml=$TEMP/pr-win-local.xml
1098 passed, 441 skipped, 1 warning in 1038.71s (0:17:18)
junit：tests=1539 skipped=441 failed=0 errors=0
```

**与 `@ci` 的 Windows job 逐项相同**（同一 sha，run 39030366312：`1098 passed, 441 skipped`
`in 987.74s`）。所以这条不是"本地凑数的烟测"，而是同一环境的两台机器互相复现。

### 2. 441 条 skip 的构成（族表按 conftest 原文，不是猜的）

| 原因族 | 条数 | 原文 token |
|---|---|---|
| PG-DSN-未设置 | 332 | `AIDEANBOT_TEST_PG_DSN 未设置` |
| PG-不可达 | 104 | `PG 不可达`(99) + `PG:5433 不可达`(4) + 变体(1) |
| Redis-不可达 | 3 | `Redis 不可达` |
| LangBot-不可达 | 1 | `LangBot :5300 不可达` |
| 代理变量未设 | 1 | `宿主未设这 6 个待清代理变量` |
| **合计** | **441** | 未知族 = **0** |

与 ubuntu 的交叉核对（这一步才是"能不能收紧阈值"的判据，单看总数不算）：

- 两侧总数都是 **1539**：ubuntu `1533 passed + 6 skipped`，Windows `1098 + 441`。
- ubuntu 那 6 条 skip 的族 = LangBot×2 + Redis×3 + 代理×1；Windows 的非 PG 族 = 5 条 + 1 条
  以 DSN 理由 skip 的全链冒烟（`test_chat_sse.py:1192` 在无 DSN 的机器上先撞上 DSN 判定），
  所以 **441 = 436 PG + 5 非 PG**，与 ubuntu 的 6 条只差这一条归类，不缺口。
- **反证**：ubuntu 同一 sha 上那 435 条 PG 用例是**真跑过且通过**的（`pg_unreachable=0`），
  所以 Windows 侧这 436 条不是"永久被 neuter 的用例"，而是同一条纪律（无库则 skip）的另一侧。

### 3. S00X.4.2 要的收紧动作：`SKIP_BASELINE_WIN 320 → 441`

`ci-windows.yml` 原注释自己写着"保守上界，不是测量值 ⇒ 首跑读数回来后收紧到真实值 ±1"。
首跑读数在 `5e5ab17`（STEP-00H S00H.1.1-1.3）就回来了，但**连续 7 次 run 没人执行这个 TODO**，
于是 Windows 门一直红在同一行——它挡的不只是本卡读数，还挡着 S00H.2.3 与 P-5/U-23 的关闭。

- 取 **441（测量值本身，不留 ±1 余量）**：留余量就是把「同数换因」那个洞的宽度写进阈值。
  阈值现在是硬上界 ⇒ 任何新增连库用例都必须显式重算构成才能过门（变异③已证：440 会红）。
- 同时把门禁脚本从"打前 12 条样本 + 只数总数"改成**按原因族记账 + 未知族即红**，
  也就是 S00X.4.1 原本要求而一直没做的"打印 skip 构成"。收紧阈值如果不配这一步，
  就只是把红灯拧绿。
- 常驻反证：`apps/api/tests/test_ci_windows_skip_gate.py`（6 条，本机全绿，且**跑的是从
  `ci-windows.yml` 抽出来的同一段脚本**）。四发极性读数：基线值放行 / +1 条红 /
  未知族红且点名 / 有 failed 时即使 skip 干净也红。
  其中"族表 token 必须在测试源码里找得到原文"那条**排除本文件**——族表原文就写在这个用例文件里，
  把自己算进语料的话这条恒真，正是本仓反复踩的"用自己的实现喂自己的判据"。

### 4. 一条顺带的量级读数（支持 S00H.1.2，但带混杂因素）

同一条命令、同一台机器：本批 **1039s**，而 2026-10-16 的两条全量都是 **4905s**（§补记/§补记 2）。
skip 数还从 422 涨到 441，所以这不是"用例变少了"。机制方向与 `connect_timeout=3` 一致：
无库时每次建连不再等 Windows 的 TCP  SYN 超时（系统默认量级是十几到二十几秒）。
**混杂因素必须写出来**：其间并入了 STEP-04/22/23 的提交与机器负载差异，
所以这条只算"支持 S00H.1.2 在开发平台上有效"的旁证，不算它的验收读数（验收在 §EVD-V13-00H §7）。

### 5. 本批仍未证的（不静默略过）

1. `@win` 上 **前端**面（vitest/build）未重跑——本批只判后端全量；CI 的 Windows 前端两步
   在这两次 run 里是 `skipped`（因为后端门禁先红），要看它们绿得等下一批 CI。
2. Docker/WSL 仍不存在于本机 ⇒ 连库结论仍只能由 `@ci` 判（D-V4-01 未变）。
3. 门禁的两处盲区原样留着（写在 EVD-V13-00H §7.5 残余风险）：冒充已知族原文的无条件 skip
   仍放行；skip 总数**下降**不设闸（模块级 skip 把 60 条折成 1 条时门反而更绿）。
   后者要抓就得再加一个 collected 常数，而那会让每张新增用例的卡都必须改 CI 文件——本批选择不加。

---

## 补记 4（2026-10-23，V0.17.0 队列⑮ 收口轮 · 判据复算 + 00X 余项两项落地）

执行机标签：除 §2/§7 外全部 `@win`（Win10.0.19045 / Git Bash / `apps/api/.venv` = Python 3.12.10）。
基线 `main@8e59749`。本轮只做 00X 卡面上仍开的两项（S00X.3.1.1、S00X.4.2），外加一件 00X 该做而没做的事：
**把卡面 7 条 Done 判据里那些"落地时跑过一次、此后八张卡再没重取过"的数字重新量一遍**——
这是 `conventions.md` §4.3 第③条（验收环境每台机器每轮重取，不得引用上一版的工具链状态）对本卡自己的要求。

### 0. 环境变更声明（本轮现取，不引用补记 3 那份清单）

| 探测项 | 本轮读数 | 与 2026-10-17（补记 3）相比 |
|---|---|---|
| `node --version` | v24.21.0 | 同 |
| `pnpm --version` | 9.15.9 | 同 |
| gitleaks | 8.21.2（`%LOCALAPPDATA%\Programs\tools\gitleaks\gitleaks.exe`） | 同 |
| venv Python / ruff / mypy | 3.12.10 / 0.12.12 / 2.3.1 | 同（与 `pyproject` 钉版一致） |
| `make --version` | GNU Make 4.4.1 (Windows32) | 同 |
| `git --version` | 2.55.0.windows.5 | 同 |
| docker / WSL 发行版 | **都没有** | 同——00X 落地时就没有，这条从未变过 |
| PG 可达性 | `entry.py migrate` → `SKIP(service unavailable) PostgreSQL localhost:5433`（rc=3）；`entry.py docker-ps` → `SKIP(tool missing) docker`（rc=3） | **变了**：10-22 深夜本机还有一个隔离 PG@5547，10-23 起连库面整体消失 |

⇒ 本轮**没有任何连库读数**，连库面一律由 `@ci`（ubuntu-latest）出（D-V4-01）。
凡本轮判不了的判据，写在 §3 的"未测"列里并给出为什么，不写成通过、也不写成本卡已过。

### 1. S00X.3.1.1 前端 import 大小写与真实文件名逐一对齐 —— 两条独立读数

原件：`case_alignment_probe.txt`（同目录）。

**读数 A（`@win`，探针本体）**：语料 = `apps/web` 下 188 个 `.ts/.tsx/.js/.jsx/.mjs/.json/.css` 源文件；
抽出的 import 说明符里 **391 处是仓内解析**（`@/` 别名与 `@bothot/contracts` 共 320 处、相对路径 71 处），
其余 197 处（15 种包名）是外部包，交给 tsc/bundler，本探针不判。
391 处**全部解析到真实文件**：`断链 = 0`、`大小写与磁盘真名不符 = 0`。

**读数 B（`@ci ubuntu`，卡面原判据）**：`frontend` job（含 `pnpm build`）在 `8de3a1a` 与 `8e59749` 上
均 `success` —— 见 §2 的原始面。Linux runner 区分大小写，`build` 绿即"没有任何一处是靠 Windows
大小写不敏感蒙过去的"。

两条各强一半：A 能**点名到路径段**（B 只给一个 job 结论），B 是**真实 Linux 解析**（A 是本机字节比对）。
所以两条都留、不互相替代，这也正是卡面那句"判据是在 `@ci ubuntu` 上 `pnpm build` 绿，而不是本地能跑"的保留原因。

探针有牙齿（四发极性变异自测，`selftest` rc=0）：

| 输入 | 期望 | 实测 |
|---|---|---|
| 磁盘真名 `Mod.ts`，查找 `sub/mod.ts` | 判红并给出真名 | `第 2 段 'mod.ts' 磁盘真名是 'Mod.ts'（大小写不同）` |
| 查找 `sub/nope.ts` | 判红 | `'nope.ts' 在 …\sub 下不存在` |
| 查找 `sub/Mod.ts`（逐字节一致） | 放行 | `ok=True` |
| 查找 `sub`（目录，无 `index.*`） | 拒收 | `ok=True` 但 `is_file=False` ⇒ 解析层不收目录 |

一处**探针差点自洗**的写法必须记下来，因为它是本仓反复踩的那类：
第一版用 `Path.resolve()` 取规范路径再比对，看起来更"严谨"，但 `resolve()` 在 Windows 上会把
路径**规范化成磁盘真实大小写**——错的大小写被探针自己改对，判据于是恒真。改成只用 `os.scandir`
逐段做字节精确匹配后，①那发变异才会红。源码有意不入库（S00T.V14.3 / F-14 裁定证据脚本不再以可执行件
形态进仓库），复建规格写在原件 §4。

### 2. S00X.4.2 双 job 验收读数（D-V6-02：只抄 run 号不算）

原件两份：`ci_runs_8e59749.json`（REST 原始响应，`runs?head_sha=` + 每个 run 的 `/jobs`，
只留身份与结论字段）与 `ci_dual_job_readings_8e59749.txt`（run 级日志原文）。锚定提交
`8e59749181d8822ce060e4ee26330819305077fd`（`main`）。

| 工作流 | run id | 结论 | 关键读数 |
|---|---|---|---|
| `CI`（ubuntu-latest，正式验收面） | **39891503640** | `completed/success`，5 个 job 逐个 success | `2258 passed, 6 skipped, 4 deselected in 220.46s`；`Total coverage: 88.01%`；`skip 门禁：total_skipped=6 baseline=6 pg_unreachable=0`；`✅ 全部模块与全局达标`；`frontend` job 的 `pnpm run build` → `✓ Compiled successfully in 9.7s` + `✓ Generating static pages (18/18)`（两档构建都过） |
| `CI-Windows`（windows-latest，开发平台门） | **39891503516** | `completed/success` | `1598 passed, 666 skipped, 4 deselected in 1057.83s`；`windows 门禁：failed=0 total_skipped=666 baseline=666`；`Test Files 49 passed (49)` / `Tests 415 passed (415)`；`build` → `✓ Compiled successfully in 9.4s` + `18/18`；取证行原文 `head_sha=8e597491…077fd  conclusion=success  job=windows-dev` |
| `Security` | **39891503530** | `completed/success` | 四道扫描无 BLOCK（`next`→15.5.28 之后 pnpm-audit 与 trivy 清空，见台账 §4 P-99） |

⇒ **卡面 Done 判据第 1 条到此才成立**：补记 3 结束时它仍是"部分确认"，因为当时的 Windows 那一格
红在一条自己标着"保守上界，不是测量值"的 stale 阈值上。现在两格同绿，且绿色是**同一 head_sha** 上的，
不是把两个提交的读数拼起来。

顺带关掉补记 3 §5.1 留的那条未证项：**CI 的 Windows 前端两步**当时因后端门禁先红而被 skip，
本轮真跑了（vitest 49 files/415 tests、build 18/18 静态页）⇒ 不必再等下一批，也不必 `@win` 复跑前端。

### 3. 卡面 7 条 Done 判据逐条判定（本轮现读）

| # | 卡面判据（原文压缩） | 本轮判定 | 依据 |
|---|---|---|---|
| 1 | `@ci` windows 与 ubuntu 两个 job 均 success（run id/conclusion/head_sha 存证） | **达成**（`8e59749`） | §2 + `ci_runs_8e59749.json` |
| 2 | `@win` 干净机按 README 从零：install→起 PG/Redis→migrate→起前后端→lint→单测→build 全绿 | **未测**（不是"不通过"） | 本机不是干净机（工具链是本卡 10-15 那轮自装的），且**现在连 docker 都没有** ⇒ "起依赖服务"那一步在本机不可达。README §6 的顺序本轮只能照抄到 `migrate` 的 `SKIP(rc=3)` 为止，那既不是绿也不是红，是**没跑**。补记 3 §5.2 同一条仍是原样 |
| 3 | `make <task>` 与 `entry.py <task>` **零/非零一致**，至少 6 任务、**两平台各一次** | **半达成**：`@win` 6 任务本轮复算通过；**`@linux` 半边没有执行者** | §4.2 表；ubuntu job 从不调用 `make`（本卡实测并写在卡的执行记录里），而卡面又禁止改 ubuntu job 语义 ⇒ 这条判据在现编排下永远只能半绿 ⇒ 登记 **P-101** 请规划方裁定（要么给 Linux 侧一个执行者，要么把判据改成 `@win` 单侧 + CI 双平台 build 绿） |
| 4 | `@win` 缺工具场景退出码非 0，至少 2 个任务有读数 | **达成** | 本轮复算：`docker-ps`→3、`migrate`→3（两条都打印 `SKIP(...)` 且明写"不是通过"） |
| 5 | `@linux` `.gitattributes` 收敛后 `pnpm build` 仍绿 | **达成** | §2 的 `frontend` job success。**标签纪律**：这条原文写 `@linux`，实际执行者是 CI 的 ubuntu runner（Linux 且区分大小写），按 D-V6-01 必须写明等价关系，否则等于给了一条没有机位的读数 |
| 6 | `@win` "只降不升"判据 `grep -rn "open(" scripts \| grep -v encoding=` 前后两数在案 | **达成，但判据本身是假阳形** | §4.3：落地时记 0→0，本轮复算**字面 2**，两处命中都是函数名 `_enclosing_open(`（`guards.py:731/772`），不是文件打开调用 ⇒ 语义计数仍 0→0 ⇒ 登记 **P-100** |
| 7 | 仅上线脚本在 `cross-platform.md` 明确标「仅 Linux」，且**清单逐条可核** | **达成**（本轮补全） | 原文只有一句「`rotate_keys.sh` 等」——那不是清单。本轮把 `git ls-files '*.sh' \| grep -v '^\.project/'` 实测出的 **6 个自有脚本**逐条列进 `cross-platform.md` §7（3 个仅 Linux + 1 个 Linux/CI 为主（`ci-repro-frontend.sh` 本卡未实跑，故不写「仅」）、`preflight.sh` 跨平台可用、EVD-V2-00C 的采集器标"历史取证件，不再执行"），vendored 14 个不计 |

### 4. 复算出的三件事（数字，不是印象）

#### 4.1 行尾收敛至今零文本回退

| 命令（都在 `8e59749` 上现跑） | 读数 |
|---|---|
| `git grep -l $'\r' HEAD`（含二进制） | **205** 个 blob |
| `git grep -I -l $'\r' HEAD`（按属性跳过 binary/`-text`） | **0** |
| `git ls-files --eol` 分布 | `i/lf` 5520、`i/-text` 205、`i/none`（空文件）160、**`i/crlf` 0、`i/mixed` 0** |
| 205 个的构成 | 197 个在 vendored 子树（firecrawl 74 / wandao 46 / MediaCrawler 40 / LangBot 35 / reclip 2）+ 8 个自有二进制（4 张 EVD-V13-14b 的 png、`.docs` 的 2 个 xlsx 与 1 个 docx、`apps/web/app/favicon.ico`） |

卡面与 `cross-platform.md` §3 原写"含 CR 的 blob 只有 3 个"，那是 10-15 在 `17c5d28` 上的读数；
数字当然会随仓库长大而变（新加的 png/xlsx 都带 CR），**结论反而更强了**：文本侧一个都没有。
文档已按本轮读数改写，并把"3 个"降级为历史时点值。这条复算的意义不在于刷新数字，
而在于证明 `* text=auto eol=lf` 撑过了其后八张卡——共享工作树里并发会话多次大批量写文件，
没有任何一次把 CRLF 带回文本 blob。

#### 4.2 `make` 与 `entry.py` 的零/非零一致（本轮 6 任务复算，`@win`）

| 任务 | `make X` | `entry.py X` | 同为 0/非 0 |
|---|---|---|---|
| dev | 0 | 0 | ✅ |
| lint-backend | 0 | 0 | ✅ |
| guard-ports | 0 | 0 | ✅ |
| fmt-check-backend | 2 | 1 | ✅ |
| docker-ps | 2 | 3 | ✅（3 = 工具缺失，经 make 被折成 2） |
| migrate | 2 | 3 | ✅ |

与补记 1 §4.2 那张表的差别：`guard-ports` 那一行当时是"2 / 3→0（搬进 guards.py 后）"，
本轮是 **0 / 0**——守卫实体已在 `scripts/guards.py`，两侧同义。
`python scripts/check_entry_parity.py` 同一轮 rc=0：Makefile 33 个目标全部解析到实体且 recipe 已转调，
entry.py 独有 4 个（`scan-secrets`/`typecheck-backend`/`typecheck-frontend`/`venv-backend`，不算违规）。

#### 4.3 S00X.2.2.1 那条"只降不升"判据被自己的措辞打红（假阳）

判据原文：`grep -rn "open(" scripts | grep -vc encoding=`，落地时记 **0→0**。
本轮复算字面命中 **2**：`scripts/guards.py:731` 的 `def _enclosing_open(text: str, pos: int)` 与
`:772` 的调用点。两处都是**标识符**，不是文件打开。语义计数仍是 **0→0**。

⇒ 这条判据抓不到它想抓的东西，而且会随任何一次把 `open` 写进函数名的重构自红；
本卡不改 `guards.py`（那属后续守卫卡的实体面），只登记 **P-100**：
建议改成"`scripts/**` 里带 `open(` 且**不是**函数定义/调用的行数为 0"，或直接换成
`grep -rnE "^\s*(with )?open\(" scripts --include=*.py | grep -v encoding=` 这类锚定调用形的写法。

### 5. 本卡上一轮的两处 ✅ 被本轮现读更正

1. **S00X.1.2 的"任务表"里有 2 个名字从未存在**。卡面列了 8 个任务名
   （`install / dev / test / lint / build / migrate / verify-backend / verify-frontend`），
   上一轮的记录写「✅ 34 个任务」就把这两条一起蒙进了分母。本轮 `entry.py help` 现读 **37 个任务**，
   其中**没有** `verify-backend`/`verify-frontend`；`grep -rn "verify\|testenv" scripts/entry.py Makefile README.md`
   → **0 命中**（本轮实测，**锚在 `8e59749`**）。【失效边界】下一张卡 STEP-00E（`9983c63`）就把这四个名字
   建进了 `entry.py`/`Makefile`——现在复跑同一条 grep 会得到命中，不是这条读数错了，是它只对那一批成立。
   ⇒ 更正为 **6/8 落地 + 2 移交**：这两个名字连同 `testenv-up`/`testenv-down`
   是 STEP-00E 的 S00E.1.3/S00E.2.1 的交付物，本卡不代做（也不假装做了）。00E 就在下一张。
2. **S00X.4.1 卡面写"在 `ci.yml` 新增 windows-latest job"，实体今天不在那里**。
   `windows-dev` job 现居 `.github/workflows/ci-windows.yml`（该文件第 3 行自报"STEP-00W S00W.2.1：
   windows-dev 从 ci.yml 拆成独立工作流"）。拆分依据是 **D-V7-01**：两 job 同居一个工作流时，
   徽章读的是工作流级结论，于是"正式验收面明明绿、显示出来是灰的"。
   ⇒ 这不是漂移而是被裁决追认；本卡的读数因此**按工作流取**（`CI` 与 `CI-Windows` 两条），
   `cross-platform.md` §0 已记着这条分工。

### 6. 所有权声明（本批改动的面）

卡面允许面：`scripts/entry.py`、`scripts/dev-env.ps1`、`Makefile`、`README.md`、`.gitattributes`、
`.gitignore`、`docs/04_engineering/cross-platform.md`、`conventions.md`、`project-map.md`、
`.github/workflows/ci.yml`（仅新增 windows job）、`docker/compose.test.yml`、`EVD-V5-00X`。

本批实际只动了允许面内的四处，**零代码改动**：

| 路径 | 动作 | 为什么在本卡内 |
|---|---|---|
| `docs/04_engineering/cross-platform.md` | §1 版本锚改按字段定位、§2 守卫实体宿主更正、§3 CR 读数刷新、§4 增加大小写双读数、§5 `compose.test.yml` 不存在的现读更正、§7 六个自有 `.sh` 逐条清单 | 全部是本卡 S00X.2/S00X.3/S00X.1.1.1 的执行面文档 |
| `docs/06_validation/evidence/EVD-V5-00X/case_alignment_probe.txt` | 新增（探针原始 stdout + 复建规格） | S00X.3.1.1 的读数 |
| `docs/06_validation/evidence/EVD-V5-00X/ci_runs_8e59749.json` | 新增（REST 原始面） | S00X.4.2 / D-V6-02 |
| 本文件 | 追加补记 4 | S00X 收口 |

未动、且**故意**不动的：`scripts/guards.py`（§4.3 的假阳形不改代码，走 P-100）、
`docker/compose.test.yml`（本卡允许但不属本卡的原子任务，00E S00E.1.2 才要它）、
`README.md`（§3 第 2 条判据未测，不该为它编造"照抄即可"的新话术）。

### 7. 三绿（本批验收锚）

本批是**纯文档批**（零代码、零配置改动，见 §6 的四面清单），所以验收锚取 `8e59749`：
`CI` 39891503640 / `CI-Windows` 39891503516 / `Security` 39891503530 三条 attempt 1 全 `success`（§2）。
这条锚的选取理由与局限都写在这里，不假装它是"本批自己的运行"：

- 理由：文档批不改变任何被检面，而 D-V6-02 要的是"某个 head_sha 上两个 job 都 success"这一**可核对事实**；
  把空提交当验收锚只会多占一次 CI 往返，并把"绿"的来源搞混。
- 局限：本批提交自己的三条运行**在推进 STEP-00E 之前读取**（队列纪律：三绿才许前进）。
  若那一格里出现红（文档批最可能的红源是台账 §4 P-99 那一类上游公告），红点归因与处置写在 00E 的收口行里，
  不在这里预先主张它一定绿。
