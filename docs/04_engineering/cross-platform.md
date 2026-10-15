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
| Python | `ci.yml:56` = 3.12 | `winget install -e --id Python.Python.3.12` | **3.12.10**（`%LOCALAPPDATA%\Programs\Python\Python312\python.exe`；系统里另存 3.11.9，entry.py 不用它建 venv） |
| Node | `apps/web/.nvmrc` = 24.21.0 | nvm-windows 或官方 msi | **v24.21.0** ✓ |
| pnpm | `apps/web/package.json` `packageManager` = pnpm@9.15.9 | `npm i -g pnpm@9.15.9`（装进 `%APPDATA%\npm`，不碰 Program Files） | **9.15.9** ✓ |
| gitleaks | `security.yml:53` `GITLEAKS_VERSION: "8.21.2"` | 官方 zip 解到 `%LOCALAPPDATA%\Programs\tools\gitleaks\`（**不进 PATH 也可以**，entry.py 会探测该位置） | **8.21.2** ✓ |
| make | 非必需（Linux 快捷方式） | `winget install -e --id ezwinports.make` | **GNU Make 4.4.1 (Windows32)** |
| PostgreSQL 16 / Redis 7 | `docker/compose.yml`（宿主 5433 / 6380） | Docker Desktop 或 WSL2 | **本机两者都不可用**（见 §5） |

## 2. 入口：`python scripts/entry.py <task>` ≈ `make <task>`

命令实体只在 `scripts/entry.py` 一份；Makefile 的 26 个开发类目标改成薄转调，
守卫类（`guard-ports`/`guard-versions`/`guard-structure`/`evidence-check`）与 `help` 的实体仍留在 Makefile，
由 entry.py 反向调用 `make`（没有 make 就 SKIP，不复制一份近似实现）。

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
- 收敛前实测：`git grep -I -c $'\r' HEAD` → **只有 3 个 blob 含 CR**，且全是二进制/vendored
  （`.project/LangBot/src/langbot/pkg/platform/sources/dingtalk.svg`、同目录 `discord.svg`、
  `.project/firecrawl/apps/test-site/public/example-long.pdf`）。
  ⇒ 已跟踪内容本来就是 LF，**不需要也不应该在共享工作树里跑 `git add --renormalize`**
  （那条命令会把并发会话的在途改动一起 stage，属硬规则禁止动作）。
- Windows 控制台/管道默认 cp936：**`PYTHONUTF8=1` 是硬要求**（entry.py 自己注入，也写进 README）。
  本机踩过的两个坑：① `python - <<'PY'` 喂含中文的源码会被 stdin 编码打碎（SyntaxError/非法字符）；
  ② 中文输出在 cp936 码流里变问号。所以本仓库的脚本一律"写成 .py 文件再 `python -X utf8 文件`"。

## 4. 路径与大小写

- 脚本层只允许 `pathlib`，禁止硬编码 `\`、禁止 `os.path.sep` 拼接（`entry.py` 全文如此）。
- 前端 import 的大小写必须与真实文件名一致：Windows 大小写不敏感会**掩盖**断链，
  判据是在 `@ci ubuntu` 上 `pnpm build` 绿，不是本地能跑（这条留在 00X 的 CI 半边）。

## 5. 依赖服务（本机不可达时的正确行为）

本机现状：无 Docker Desktop、无已安装的 WSL 发行版（`wsl -l -o` 只列出"可安装的分发"），
端口 5433/6380/3300/3200 全部无监听（`netstat` 实测）。

**因此连库半边只能在 `@ci` 或 `@linux` 容器里出真实读数**；在 @win 上：

- `entry.py migrate` 先探 PG 端口，不可达直接 `SKIP(service unavailable) PostgreSQL localhost:5433` 且 **rc=3**。
  这条是本卡执行时验出的真实缺陷：**无 PG 时 `alembic upgrade head` 不是快速失败，而是挂住**
  （psycopg 没设 `connect_timeout`，Windows 对未监听端口不立即 RST），150s 被 timeout 打断才停。
  挂住比失败更危险——执行者会以为"在跑"。
- `pytest` 的连库用例在无 PG 时会 skip；**skip 数不等于通过**（AGENTS/D-V6 口径，00R 与 RV 卡盯着这条）。
- 要本机跑真库：Docker Desktop（或 WSL2 里装 PG16/Redis7）起 `docker/compose.test.yml`，
  端口**保持 5433/6380**（AGENTS.md 端口表）。端口被占用时报错并点名占用者，**不得**静默换端口——
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
- Playwright e2e（需 `pnpm exec playwright install --with-deps chromium`；Windows runner 上 `--with-deps` 无 sudo 语义）
- compose 栈（read_only/tmpfs/cap_drop）与 `/ready` 探针
- `rotate_keys.sh` 等**仅上线用**脚本：标「仅 Linux」，不做跨平台改造
