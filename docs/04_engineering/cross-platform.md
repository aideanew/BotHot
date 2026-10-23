# 跨平台支持：Windows 10 是一等开发平台，Ubuntu 是生产平台

> 归属：STEP-00X（V0.11.0 第二增量新增），裁决依据 `docs/03_solution/decisions/decision-log.md` 的 **D-V4-01**
> （2026-10-15 12:04 签，性质 = 用户授权代选）。本文是该裁决的执行面。

## 0. 一句话分工

| 平台 | 角色 | 能证明什么 | 不能证明什么 |
|---|---|---|---|
| CI `ubuntu-latest` | **正式验收面** | 连库 pytest 全量、alembic 单头与 upgrade/downgrade 往返、gitleaks 8.21.2、pnpm build/e2e | — |
| CI `windows-latest` | **开发平台门** | "Win10 上装/跑/验这条链有没有平台性断裂" | 不得替代 ubuntu 的出门判据 |
| 本机 `@win` | 开发烟测 | 单测/静态检查/构建/扫描能否跑，以及**跑出来的读数长什么样** | 无 PG/Redis ⇒ 连库结论一律不成立 |
| `@linux`（容器/WSL2） | 本机等价面 | 需要真库时的本地复现 | 需自建服务，端口不得改动 |

> **D-V7-01（2026-10-15 签）：多平台门 = `CI-Windows` 工作流的结论**，与 `CI` 工作流分开读。
> 拆分的理由不是审美：windows job 曾每次卡在全量 pytest 到 35 分钟被 `cancelled`，而同一 run 里
> ubuntu 五个 job 全部 success —— 两者同居一个工作流时，对外那个"CI 徽章"读的是工作流级结论，
> 于是**正式验收面明明是绿的，显示出来是灰的**（V0.12.0 实测最近 10 次 CI 全 cancelled）。
> 否决过的两个替代：`continue-on-error`（红也显示绿＝取消这道门）、只改读法（徽章与分支保护仍读工作流级）。

**规则**：任何读数必须带机器标签 `@win` / `@linux` / `@ci`（D-V6-01）。没有标签的数字不算读数；
CI 的读数还要 run id + head_sha + conclusion（D-V6-02），否则只能记 `采信[REMOTE]`。

## 1. 工具链版本锚（与 CI 完全一致）

| 工具 | 锚点在哪 | Win10 安装方式 | 实测本机 |
|---|---|---|---|
| Python | `ci.yml` backend job 的 `python-version: "3.12"`（按字段定位，不按行号——该文件自 00X 落地后已被 STEP-04 往返步与 STEP-06 覆盖率门插过两轮） | `winget install -e --id Python.Python.3.12` | **3.12.10**（`%LOCALAPPDATA%\Programs\Python\Python312\python.exe`；系统里另存 3.11.9，entry.py 不用它建 venv） |
| Node | `apps/web/.nvmrc` = 24.21.0 | nvm-windows 或官方 msi | **v24.21.0** ✓ |
| pnpm | `apps/web/package.json` `packageManager` = pnpm@9.15.9 | `npm i -g pnpm@9.15.9`（装进 `%APPDATA%\npm`，不碰 Program Files） | **9.15.9** ✓ |
| gitleaks | `security.yml:53` `GITLEAKS_VERSION: "8.21.2"` | 官方 zip 解到 `%LOCALAPPDATA%\Programs\tools\gitleaks\`（**不进 PATH 也可以**，entry.py 会探测该位置） | **8.21.2** ✓ |
| make | 非必需（Linux 快捷方式） | `winget install -e --id ezwinports.make` | **GNU Make 4.4.1 (Windows32)** |
| PostgreSQL 16 / Redis 7 | `docker/compose.yml`（宿主 5433 / 6380） | Docker Desktop 或 WSL2 | **本机两者都不可用**（见 §5） |

## 2. 入口：`python scripts/entry.py <task>` ≈ `make <task>`

命令实体只有两份：`scripts/entry.py`（开发类任务）与 `scripts/guards.py`（守卫类）。
Makefile 的目标（2026-10-23 实测 **33 个**，entry.py **37 个任务**）全部是薄转调，
`scripts/check_entry_parity.py` 常驻判「每个 Makefile 目标都能解析到 entry/guards 里的实体且 recipe 已转调」，
唯一允许保留内联的是 `help`（目录页）。

> 本节原写「守卫类与 `help` 的实体仍留在 Makefile，由 entry.py 反向调用 make」——**已被实测推翻并改正**：
> GNU make 4.4.1 for Windows 跑不了守卫目标里那些多行 `; \` 续行 recipe（`unexpected EOF while looking
> for matching '"'`），改 LF 也无效；实体因此搬进 `scripts/guards.py`，Makefile 与 entry.py 双双转调它。
> 这是本卡「卡面被实测推翻的两条」之二，读数见 `EVD-V5-00X/win_dev_platform_readings.md`。

**平台分支只有两处**（这是刻意的上限，别再增加）：
1. `entry.py` 的 `dispatch()`：venv 内部布局（`Scripts\python.exe` vs `bin/python`）、`.cmd/.bat` shim 需要 `cmd /c` 包装。
2. `Makefile` 变量块：`ifeq ($(OS),Windows_NT)` 选 `python` 而不是 `python3`。
   原因实测：Windows 上 `python3` 解析到 Microsoft Store 的 **空壳 stub**（`…\WindowsApps\python3`），
   调用它什么都不发生、退出码还是 0 —— 这就是"没装却长得像通过"的假读数。

**退出码三态**（entry.py 层）：`0` 通过 / `1` 失败 / **`3` 工具或服务缺失 = 这一步没跑**。
3 沿用 Makefile `evidence-check` 早就定下的口径："这不是 PASS，也不是 FAIL"。
> **经 make 时不能保持 3**：GNU make 把 recipe 的任何失败折成 **2**。
> 所以验收判据是"两侧同为 0 或同为非 0"，不是"逐值相等"（本卡 §验收标准 已按实测改正）。

## 3. 编码与行尾

- 全仓文本一律 **UTF-8 + LF**。`.gitattributes` 从原来只有 `*.sh text eol=lf` 扩为
  `* text=auto eol=lf` + 关键后缀逐条钉死 + 二进制 `-text/binary`，并把 **vendored 的 `.project/**` 排除在行尾收敛之外**
  （那 14 个 `.sh` 不是 BotHot 的执行面；不排除的话一次跨平台改动会变成上千文件的噪音）。
- 收敛前实测（2026-10-15，`17c5d28`）：`git grep -I -c $'\r' HEAD` → **只有 3 个 blob 含 CR**，且全是二进制/vendored
  （`.project/LangBot/src/langbot/pkg/platform/sources/dingtalk.svg`、同目录 `discord.svg`、
  `.project/firecrawl/apps/test-site/public/example-long.pdf`）。
- **2026-10-23 在 `8e59749` 上复算（同一个判据，八张卡之后）**：
  `git grep -l $'\r' HEAD`（含二进制）= **205 个 blob**；`git grep -I -l $'\r' HEAD`（按属性跳过 binary/`-text`）= **0**；
  `git ls-files --eol` 分布 = `i/lf` 5520 / `i/-text` 205 / `i/none`（空文件）160，**`i/crlf` 与 `i/mixed` 各 0**。
  205 的构成：**197 个在 vendored 子树**（firecrawl 74、wandao 46、MediaCrawler 40、LangBot 35、reclip 2）
  + **8 个自有二进制**（4 张 EVD-V13-14b 的 png、2 个 `.docs/采集渠道` 的 xlsx、1 个 `.docs/09_archive` 的 docx、
  `apps/web/app/favicon.ico`）——
  全是 git 按 `binary`/`-text` 属性跳过的对象。⇒ 结论从「不需要 renormalize」升级成
  **「收敛至今零文本 blob 回退」**（文本侧 0→0，不是只"当初很干净"）。
  ⇒ 已跟踪内容本来就是 LF，**不需要也不应该在共享工作树里跑 `git add --renormalize`**
  （那条命令会把并发会话的在途改动一起 stage，属硬规则禁止动作）。
- Windows 控制台/管道默认 cp936：**`PYTHONUTF8=1` 是硬要求**（entry.py 自己注入，也写进 README）。
  本机踩过的两个坑：① `python - <<'PY'` 喂含中文的源码会被 stdin 编码打碎（SyntaxError/非法字符）；
  ② 中文输出在 cp936 码流里变问号。所以本仓库的脚本一律"写成 .py 文件再 `python -X utf8 文件`"。

## 4. 路径与大小写

- 脚本层只允许 `pathlib`，禁止硬编码 `\`、禁止 `os.path.sep` 拼接（`entry.py` 全文如此）。
- 前端 import 的大小写必须与真实文件名一致：Windows 大小写不敏感会**掩盖**断链，
  判据是在 `@ci ubuntu` 上 `pnpm build` 绿，不是本地能跑（这条留在 00X 的 CI 半边）。
- **S00X.3.1.1 现在有两条独立读数**（2026-10-23，`EVD-V5-00X/case_alignment_probe.txt`）：
  ① `@ci ubuntu` 的 `frontend` job（含 `pnpm build`）在 `8de3a1a` / `8e59749` 上 success；
  ② `@win` 上一支逐段 `os.scandir` 字节比对的探针把 `apps/web` 的 **391 个内部/别名 import 说明符**
  （`@/` 320 + 相对 71，另有 15 种外部包不判）全部解析到真实文件，**大小写不符 = 0、断链 = 0**。
  ②比①强的地方是它点名到段；①强的地方是它是 Linux 真实解析。两侧都留，不互相替代。
  探针自带四发极性变异自测（`mod.ts`→判红并给出磁盘真名 `Mod.ts`、`nope.ts`→判红、`Mod.ts`→放行、
  指向目录→拒收），所以"0"不是恒真的产物。它**刻意不用 `Path.resolve()`**——那个调用在 Windows 上
  会把路径规范化成磁盘真实大小写，判据因此会被探针自己修好。

## 5. 依赖服务（本机不可达时的正确行为）

本机现状：无 Docker Desktop、无已安装的 WSL 发行版（`wsl -l -o` 只列出"可安装的分发"），
端口 5433/6380/3300/3200 全部无监听（`netstat` 实测）。

**因此连库半边只能在 `@ci` 或 `@linux` 容器里出真实读数**；在 @win 上：

- `entry.py migrate` 先探 PG 端口，不可达直接 `SKIP(service unavailable) PostgreSQL localhost:5433` 且 **rc=3**。
  这条是本卡执行时验出的真实缺陷：**无 PG 时 `alembic upgrade head` 不是快速失败，而是挂住**
  （psycopg 没设 `connect_timeout`，Windows 对未监听端口不立即 RST），150s 被 timeout 打断才停。
  挂住比失败更危险——执行者会以为"在跑"。
- `pytest` 的连库用例在无 PG 时会 skip；**skip 数不等于通过**（AGENTS/D-V6 口径，00R 与 RV 卡盯着这条）。
- 要本机跑真库：Docker Desktop（或 WSL2 里装 PG16/Redis7）。**现读更正（2026-10-23）**：
  `docker/compose.test.yml` **至今不存在**（`ls docker/` 只有 `compose.yml` 与 `compose.ci.yml`），
  它是 STEP-00E S00E.1.2 的交付物；本卡原写"起 compose.test.yml"是一句前置引用，不是既成事实。
  今天可用的最小依赖面是 `compose.ci.yml` 里的 `postgres:  image: postgres:16-alpine` 与
  `redis:  image: redis:7-alpine` 两个服务段。端口**保持 5433/6380**（AGENTS.md 端口表）。
  端口被占用时报错并点名占用者，**不得**静默换端口——
  换端口会让 `AIDEANBOT_TEST_PG_DSN` 与读分数叉（STEP-00E 同条纪律）。

## 6. Win10 从零可照抄的顺序

```bat
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent
winget install -e --id ezwinports.make --accept-package-agreements --accept-source-agreements --silent
npm install -g pnpm@9.15.9
set PYTHONUTF8=1
python -m venv apps\api\.venv
python scripts\entry.py install          :: 后端 .[dev]+pytest-cov、前端 --frozen-lockfile
python scripts\entry.py lint-backend     :: ruff check app tests
python scripts\entry.py typecheck-backend:: mypy app
python scripts\entry.py test-frontend-unit
python scripts\entry.py build-frontend   :: NEXT_PUBLIC_API_MOCK=false（生产守卫要求，缺了就 rc=1）
python scripts\entry.py migrate          :: 无 PG ⇒ SKIP(rc=3)，不是失败也不是通过
```
gitleaks（00S 用）：`python scripts\entry.py scan-secrets`。

## 7. 只在 Linux/CI 做的事（明确不伪装成跨平台）

- alembic upgrade→downgrade→upgrade 往返与单头断言（`@ci ubuntu`，STEP-04 的出门判据）
  - 执行者：`.github/workflows/ci.yml` backend job 的两步 "Assert single alembic head" 与
    "Migration roundtrip (upgrade head → downgrade -1 → upgrade head)"。后者分三层判：
    ① 版本极性（降级后 `current` 不得再含 `(head)`、再升级后必须回到起点那一行）；
    ② 形状探针 `scripts/migration_roundtrip_probe.py` 直查 `information_schema` / `pg_indexes`，
    降级后两列两索引必须全不在、升级后必须全回来；③ 终态回到 head，后面的 pytest 才有 schema 可用。
  - 为什么要有第②层：`alembic downgrade -1` 即使 `downgrade()` 里**什么都不做**也会把版本戳重标成父版本
    （先例 `ab1004w1a_secret_aes.py:119-121` 的 downgrade 只打一行 warning 就返回），
    所以"版本变了"根本不等价于"形状被拆掉了"——第一轮那条 `case` 断言因此被批"近似恒真"。
  - 边界：只覆盖**当前 head 那一个版本**（`downgrade base` 会撞 `ab1005w5b` 那类 downgrade 直接 raise 的历史迁移）；
    此步跑在任何测试写入之前、库是空的 ⇒ 判的是 DDL 可逆，不是"降级不丢数据"。
    （2026-10-17 之前这两条口径只有单头断言有执行者，往返步与其三层判据是 S4.2 验证轮补上的。）
- Playwright e2e（需 `pnpm exec playwright install --with-deps chromium`；Windows runner 上 `--with-deps` 无 sudo 语义）
- compose 栈（read_only/tmpfs/cap_drop）与 `/ready` 探针
- **自有 `.sh` 六个的逐条归属**（2026-10-23 `git ls-files '*.sh' | grep -v '^\.project/'` 实测 = 6，
  vendored 另有 14 个、不参与跨平台化）——Done 判据要求"清单逐条可核"，所以这里一条不落：

  | 脚本 | 归属 | 依据（读它自己的头部说明即可核对） |
  |---|---|---|
  | `scripts/rotate_keys.sh` | **仅 Linux/上线** | 密钥轮换，配套 `docs/07_release/key-rotation-sop.md`，要在能连生产库的机器上跑 |
  | `scripts/smoke.sh` | **仅 Linux/上线** | 用法即 `docker compose up -d → 探活 → 心跳`，本机无 docker ⇒ 跑不了 |
  | `scripts/test-env.sh` | **仅 Linux** | 起隔离测试 PG/Redis，内部 `FORBIDDEN_PORTS` 守卫（D-12）；本机无 docker ⇒ 只能读不能跑 |
  | `apps/web/scripts/ci-repro-frontend.sh` | **仅 Linux/CI** | 前端 CI 等价复现，CI 侧执行；本机用 `entry.py` 的对应任务替代 |
  | `scripts/preflight.sh` | **跨平台可用**（经 Git Bash） | 00X §2 实测：Windows 上 `bash scripts/preflight.sh` rc=1 但**脚本本身跑起来了**并逐条报出缺什么，属"能跑、报得准" |
  | `docs/06_validation/evidence/EVD-V2-00C/collect_ruff_shapes.sh` | **历史取证件，不再执行** | 只采集不判定；F-14（S00T.V14.3）已把证据脚本 pytest 化并下线，此件按证据不可改写原则原样保留 |

## 8. 新增连库用例时，`CI-Windows` 的第二步（每张卡都要做，不是"CI 坏了"）

`windows-dev` job 不起 PG/Redis/LangBot 服务 ⇒ 该平台**必然**把所有连库用例 skip 掉。
为了区分"环境使然的 skip"与"用例被无条件标记 skip（静默放行）"，那道门是这么设的：

```
SKIP_BASELINE_WIN = 当次测量的 skip 总数（**零余量**）
判定 = failed 必须 0 ⇒ 未知原因族必须 0 ⇒ 总数不得超过基线
```

于是新增一条连库用例 ⇒ Windows 侧 skip +1 ⇒ **门红**。这不是 CI 坏了，也不是回归：
门在要求"有人显式重测一遍再放行"。**把它调回绿的动作只有两个合法步骤**：

1. 先读那一步打出的**族构成**（不是前 12 条样本，是按原因族记账的计数），确认
   `未知族 = 0`。若未知族 > 0，**停**：那是本门真正要抓的形态，抬阈值是掩盖。
2. `failed = 0` 且未知族 = 0 时，把 `SKIP_BASELINE_WIN` 抬到新的测量值，并在同一段注释里
   重算构成、写上 `head_sha` 与 `run id`（D-V6-02：读数必须可被下游引用）。

为什么不留 ±N 余量：这道门的判定力全在"总数 == 测量值"上。留 4 条余量，就等于允许
4 条用例在被无条件 skip 的同时总数不越线——而 skip 的**原因**与**数量**是可以互相抵的
（加一条合法 PG skip、同时把一条真用例标成 skip，总数纹丝不动）。
所以数闸必须贴死，另配**原因族闸**抓"同数换因"那一半；两道闸合起来才判得住。

已知边界（写在门旁边而不是藏在心里）：
- 冒充已知族原文的无条件 skip 仍会放行（族闸认的是理由文本）；
- skip 总数**下降**不触发门（模块级 `allow_module_level` 把 60 条折成 1 条时门反而更绿）；
  抓它需要再钉一个 collected 总数常数，代价是每张新增用例的卡都得改本文件——目前选择不加。
- 常驻反证：`apps/api/tests/test_ci_windows_skip_gate.py` 跑的是从 `ci-windows.yml` 抽出来的
  **同一段脚本**（合成 junit + 四发极性：基线值放行 / +1 红 / 未知族红且点名 / 有 failed 即红）。
  它不依赖 Windows，所以 `@ci ubuntu` 也在判这道门的逻辑。

2026-10-17 的实际三次收紧：320（猜的上界）→ 441（S00H.2.1 首跑测量）→ 443（STEP-23 返工轮 +2 条连库用例）
→ 444（STEP-23 第二轮 +1 条端到端用例）。三次全是同一形态：`failed=0`、`未知族=0`、DSN 族计数正好增加同样的条数。

**一条配套的取证事实**（同一批实测）：**一次 push 带多个提交时，GitHub 只为最后一个提交建 workflow run**，
中间提交没有任何 CI 读数。`b751564` 就是这样没有 run 的（它与 `f7a3a6b` 同批推送）。
所以按 D-V6-02 引用"某个 run id 证明了某个提交"之前，必须先确认那个 run 的 `head_sha` 就是那个提交——
否则会把"批处理推送的尖端读数"错记成"中间提交的结论"。要每张卡都有自己的门，就一次提交一次 push。

**多平台门已绿**（2026-10-21，S00H.2.3 收口）：`CI-Windows` 连续两个提交 `success`——
run **39500601366**（`b7cdaee`）与 run **39496625738**（`376cfe3`），两条都是
`1489 passed / 578 skipped`、`Failed: Timeout` 与 faulthandler 转栈头双 0、跑完而非被上限砍掉；
据此 pytest 的 `--timeout=300` 收紧为 `--timeout=120`，P-5 / U-23 关闭。
"单用例从未越过 120s"这条是收紧不误伤的依据（`faulthandler_timeout=120` 两次都没转栈），
读数全在 `docs/06_validation/evidence/EVD-V13-00H/s00h_readings.md` §10。

