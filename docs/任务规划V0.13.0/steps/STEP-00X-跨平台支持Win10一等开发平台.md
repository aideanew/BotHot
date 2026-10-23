# STEP-00X 跨平台支持：Windows 10 一等开发平台（V0.11.0 新增）

| 字段 | 值 |
|---|---|
| 归属-切片 | S-M0a 前提固定 |
| 归属-需求 | REQ-C-001（技术栈）、REQ-C-002（端口/部署）、M-6（主干绿）；用户裁定的 D-V4-01 直接派生 |
| 归属-方案 | `decision-log.md` D-V4-01（CI ubuntu-latest 为正式验收面 + windows-latest 为开发平台门）、D-V6-01（标签 `@win/@linux/@ci`）；本卡是其实现面 |
| 里程碑 | **M0a**（与 00E/00G 并列，先于一切功能卡） |
| 档位 | opus　理由：改的是所有人的执行入口（Makefile/脚本/CI/gitattributes），错一处就污染后续所有卡的验收；跨模块且不可逆性高（CI 编排 + 换行约定一旦定错，回滚要重写全库文件）。**升级条件**：若需要推翻"Windows 是一等开发平台"这一范围 ⇒ fable 终裁 |
| 规模 | 中（≈1.5 人日；单原子任务均 <2h） |
| 依赖 | Depends on：无　Blocks：00E、RV、00C 之后的所有卡（它们的 `@win` 烟测依赖本卡） |
| 基线 | main@17c5d28 |
| 剩余原子任务 | 9（👤 0） |

## 目标（可验证的一句话）
一台**干净的** Windows 10 机器，按 README 从零执行安装 → 起依赖服务 → 迁移 → 启动前后端 → 跑 lint/单测/构建 全绿；同时 CI 的 `ubuntu-latest`（正式验收面）与新增 `windows-latest`（开发平台门）都绿，且 `make` 之外的入口在 PowerShell/Git-Bash 下语义一致。

## 输入
- 文档：`docs/任务规划V0.11.0/03-裁决与契约.md` §5（迁移串行）、`04` §2 表；`decision-log.md` D-V4-01/D-V6-01/D-V6-02 签字行
- 契约：`contracts/api.envelope.schema.json`（跨平台不得改变响应契约）、`identity.schema.json`
- 代码/配置锚（**下列数字为 @win 于 17c5d28 实测，非估算**）：`Makefile`（**204 行**）、`scripts/`（**4 个 .sh**：`preflight.sh`/`rotate_keys.sh`/`smoke.sh`/`test-env.sh`，另有 `check_docs_consistency.py`、`gen_contracts.py`）、全仓被跟踪的 `.sh` **20 个 = 6 个自有 + 14 个在 `.project/` vendored 子树**（LangBot/firecrawl/reclip，**不属本卡改造面**）、自有 6 个中另两处是 `apps/web/scripts/ci-repro-frontend.sh` 与 `docs/06_validation/evidence/EVD-V2-00C/collect_ruff_shapes.sh`、`.gitattributes`（**全文只有 1 行：`*.sh text eol=lf`**）、`.github/workflows/ci.yml`（**5 个 job 全是 ubuntu-latest**；`17c5d28` 当时记的 `397 行 / workflow-lint:12 / backend:23 / frontend:174-325 / compose:326 / compose-smoke:361` 已被 STEP-04 的往返步两轮编辑顶偏，**现读**（`d82bfb9` 之后、本批改 ci.yml 停笔时取数）为 431 行、`workflow-lint:12`、`backend:23`、`frontend:208`、`compose:360`、`compose-smoke:395`——前两个未动，故当时那组数对它是真话；今后这类锚按 job 名定位，重取用 `grep -n "^  \(workflow-lint\|backend\|frontend\|compose\|compose-smoke\):" .github/workflows/ci.yml`，别用宽松的 `^  [a-z-]*:`（它会把 `on:` 下的 `push:` 也算成一个 job））、`apps/web/.nvmrc`、`apps/api/pyproject.toml`（ruff 0.12.12/mypy 钉版）、`docker/compose.yml`（端口 3300/5433/6380）、`docs/04_engineering/conventions.md`
- 前置状态：Windows 10；本机现状 `node_modules`/`pnpm`/`.venv`/`gitleaks`/`gh` **全无**（01 F-04/F-05）；用户已授权执行方自行安装，版本对齐 Python 3.12 / Node 按 `.nvmrc` / gitleaks 8.21.2

## 输出（文件）
- 新：`scripts/entry.py`（跨平台任务分发器）、`scripts/dev-env.ps1`（可选 Win 便捷壳）、`docs/04_engineering/cross-platform.md`
- 改：`Makefile`（各目标改为转调 `python scripts/entry.py <task>`，保留为 Linux 快捷方式）、`README.md`（Win10 安装与 `PYTHONUTF8=1`）、`.gitattributes`、`.github/workflows/ci.yml`（新增 `windows-latest` job）、`docs/00_governance/project-map.md`（指向 cross-platform.md）
- `docs/06_validation/evidence/EVD-V5-00X/`

## Execution Steps

### S00X.1 入口跨平台化
1. [ ] ✅ **S00X.1.1** `@win` 先量现状：逐条跑 `make install/dev/test/lint/build/migrate` 与 `scripts/*.sh`，记录哪些在 Win10 直接失败及失败原因（sh 不存在 / `&&` 语义 / 路径分隔符 / 无 CRLF 换行处理），读数入 EVD
   - S00X.1.1.1 只上线用的（`rotate_keys.sh`、deploy 相关）**不改造**，标「仅 Linux」并记入清单
2. [ ] 🛠 **S00X.1.2** 建 `scripts/entry.py`：把 `install / dev / test / lint / build / migrate / verify-backend / verify-frontend` 做成平台无关的任务表；内部用 `pathlib` + `subprocess`，显式 `encoding="utf-8"`，`cwd` 用 `Path(__file__).resolve().parents[1]` 推导（禁止依赖调用方 cwd）
   - S00X.1.2.1 每个任务在 Win/Linux 走**同一份** Python 代码；平台差异只允许出现在一处 `platform_dispatch()` 表里，禁止散落到各任务体
   - S00X.1.2.2 缺工具时打印 `SKIP(tool missing)` 并以**非 0** 退出（沿用 STEP-00C S0C.4.1 与 00P 的口径；"没装"绝不能长得像"通过"）
3. [ ] 🛠 **S00X.1.3** `Makefile` 各目标改为 `python scripts/entry.py <task>` 的薄转调（Linux 快捷方式保留），确保 `make X` 与 `python scripts/entry.py X` 同义
   - S00X.1.3.1 反证：临时让 `entry.py` 某任务返回 1 ⇒ `make` 该目标必须红

### S00X.2 行尾与编码
4. [ ] 🛠 **S00X.2.1** `.gitattributes` 由"仅 `*.sh`"扩为：`* text=auto` + 关键文件显式 `eol=lf`（`*.sh`、`Makefile`、`Dockerfile`、`docker/compose*.yml`、`*.ts`、`*.tsx`、`*.py`、`*.json`、`*.md`）；`*.png/*.ico` 等二进制标 `binary`
   - S00X.2.1.1 改后必须 `git add --renormalize .` 的**影响面预估**先跑出来（`git diff --stat` 预演），若会一次性重写数百文件 ⇒ **拆成独立提交**并在 EVD 记录预估，绝不与功能改动混提
   - S00X.2.1.2 ⚠ 本仓库当前已出现 CRLF 警告（`git status` 大量 "LF will be replaced by CRLF"），说明换行策略本就不一致；本步骤是收敛它，不是制造它
5. [ ] 🛠 **S00X.2.2** 全仓 Python 文本读写与 `subprocess` 输出去掉隐式编码：显式 `encoding="utf-8"`；README/`cross-platform.md` 写明 Win10 需 `PYTHONUTF8=1`（并解释本机踩过的坑：`python -` 喂含中文源码经 cp936 会被打碎）
   - S00X.2.2.1 判据：`grep -rn "open(" scripts | grep -v encoding=` 的命中数必须**只降不升**，且给出前后两个数

### S00X.3 路径、大小写与依赖服务
6. [ ] 🛠 **S00X.3.1** 脚本内路径一律 `pathlib`，禁止硬编码 `\` 或裸字符串拼接；`os.path.sep` 拼接同样禁止
   - S00X.3.1.1 前端 import 的大小写与真实文件名逐一对齐（Windows 大小写不敏感会掩盖 Linux CI 上的断链）：判据是在 `@ci ubuntu` 上 `pnpm build` 绿，而不是本地能跑
     — **已交付（2026-10-23，队列⑮ 收口轮）**，而且是**两条独立读数**：
     ① 卡面那条原判据成立——`@ci ubuntu` 的 `frontend` job（含 `pnpm build`）在 `8e59749` 上 success，
     日志原文 `✓ Compiled successfully in 9.7s` + `✓ Generating static pages (18/18)`（两档构建都过）；
     ② 另在 `@win` 补了一支能**点名到路径段**的探针：`apps/web` 的 188 个源文件里 391 处仓内 import 说明符
     （别名 320 + 相对 71）全部逐字节解析到真实文件，**断链 0、大小写不符 0**，
     并带四发极性变异自测（写错的 `sub/mod.ts` 必须红并给出磁盘真名）。
     探针刻意不用 `Path.resolve()`——它会把路径规范化成磁盘真实大小写，判据会被探针自己修好。
     原件 `EVD-V5-00X/case_alignment_probe.txt`（含复建规格，源码有意不入库：F-14 / S00T.V14.3）。
7. [ ] 📄 **S00X.3.2** `cross-platform.md` + README 写死 Win10 依赖服务方案：Docker Desktop 或 WSL2 起 PostgreSQL 16 / Redis 7，**版本与生产、CI 对齐**，端口沿用 5433/6380（AGENTS.md 端口表：3000 禁用、3200 前端宿主、3300 后端）
   - S00X.3.2.1 端口被占用时报错并点名占用者，**不得**静默换端口（换端口会让 `AIDEANBOT_TEST_PG_DSN` 与读分数叉——STEP-00E 同条纪律）

### S00X.4 CI 双平台
8. [ ] 🛠 **S00X.4.1** `.github/workflows/ci.yml` 新增 `windows-latest` job：装 Python 3.12 + Node（按 `apps/web/.nvmrc`）→ 后端 `ruff`/`mypy`/`pytest`（**需真库的用例按标记 skip**，并在 summary 里打印 skip 构成）→ 前端 `typecheck`/`lint`/`vitest`/`build`（`NEXT_PUBLIC_API_MOCK=false`）
   - S00X.4.1.1 `ubuntu-latest` job 一行不改（正式验收面语义必须稳定）；windows job **不**跑 alembic upgrade/downgrade 往返（那是 @ci ubuntu 的出门判据，见 STEP-04）
   - S00X.4.1.2 windows job 的 `SKIP_BASELINE` 与 ubuntu 分开设定，否则"平台差异"会伪装成"回归"
9. [x] ✅ **S00X.4.2** 验收读数 `@ci`：push 后取 ubuntu-latest 与 windows-latest 两个 job 的 **run id + conclusion + head_sha**，按 D-V6-02 存成证据文件（`gh` 或 GitHub REST 原始响应均可，只抄 run 号不算）
   — **已确认（2026-10-23 队列⑮ 收口轮，同一 head_sha `8e59749`）**：
   `CI` run **39891503640** = completed/**success**（5 个 job 逐个 success，含 `pnpm build` 的 `frontend`），
   `CI-Windows` run **39891503516** = completed/**success**（`windows-dev`，`failed=0 total_skipped=666 baseline=666`），
   `Security` run **39891503530** = success。原始面存成 `EVD-V5-00X/ci_runs_8e59749.json`
   （REST `runs?head_sha=` + 每 run 的 `/jobs`，只留身份与结论字段）+ `ci_dual_job_readings_8e59749.txt`（日志原文）。
   — **上一轮（2026-10-17）这段的原话保留如下，不抹平**：当时同 `head_sha=10c1019` 三连
   `CI=success`(39030366256) / `Security=success`(39030366246) / `CI-Windows=failure`(39030366312)，
   而 Windows 那一格红的不是平台性断裂，是 `SKIP_BASELINE_WIN=320` 这条被注释自己标为
   "保守上界，不是测量值"的 stale 阈值；收紧动作（320→441 + 按原因族记账 + 常驻反证用例）在同一批，
   所以当时本卡的 Done 判据「两个 job 均 success」只是**部分确认**。
   现在两格同绿，且是同一提交上的绿——不是把两个提交的读数拼起来。
   ⚠ 一点必须让下游知道的编排事实（不是本卡改的）：`windows-dev` 今天**不在 `ci.yml` 里**，
   STEP-00W S00W.2.1 按 **D-V7-01** 把它拆成独立工作流 `ci-windows.yml`。所以"两个 job 都 success"
   这句在本卡的实体形态是"**两个工作流**都 success"；`cross-platform.md` §0 记着这条分工。

## 验收标准（Done 判据，全部标机器）
> 2026-10-23 队列⑮ 收口轮逐条判定过一遍（读数与"为什么那两条勾不上"全在
> `EVD-V5-00X/win_dev_platform_readings.md` 补记 4 §3），下面的勾就是那一节的结论落在这张卡上的样子。
- [x] `@ci` `windows-latest` 与 `ubuntu-latest` 两个 job 均 success（run id/conclusion/head_sha 存证）
      —— 同一 `head_sha=8e59749`：`CI` 39891503640 / `CI-Windows` 39891503516 双 success（实体是两个工作流，见 S00X.4.2 的 ⚠）
- [ ] `@win` 干净机按 README 从零：`install → 起 PG/Redis → migrate → 起前后端 → lint → 单测 → build` 全绿，逐条命令与输出入 EVD（**开发烟测**，不替代 Ubuntu 验收）
      —— **未测，且本机判不了**：本机不是干净机（工具链是本卡 10-15 那轮自装的），且现在连 docker 都没有
      ⇒ "起 PG/Redis"那一步在本机不可达，照抄 README 只能走到 `migrate` 的 `SKIP(rc=3)`。
      不写成通过，也不写成失败——那是"没跑"。要关这条得有一台带 Docker Desktop/WSL2 的机器（属 00E 的题）。
- [ ] `@win`+`@linux` `make <task>` 与 `python scripts/entry.py <task>` **零/非零一致**（至少 6 个任务，两平台各一次）。
      **判据按实测修正过一次**（S00X.1.3 执行时验出）：GNU make（4.4.1 Windows 实测，Linux 同语义）把 recipe 的任何失败折成 **2**，
      所以 `entry.py docker-ps` 的 rc=3 经 `make docker-ps` 变成 2 —— 要求"退出码逐值相等"是错的判据；
      正确判据是 **同为 0 或同为非 0**，且三态（0 通过 / 1 失败 / 3 没跑）只在 entry.py 层保留。做不到的那一类必须显式记为缺陷，不许把 2 当成 3
      —— **半达成**：`@win` 半边 2026-10-23 复算 6 个任务全零/非零一致（dev 0/0、lint-backend 0/0、guard-ports 0/0、
      fmt-check 2/1、docker-ps 2/3、migrate 2/3）；**`@linux` 半边在现编排里没有执行者**——ubuntu 五个 job 从不调用 `make`
      （本卡落地时实测，正因如此改 Makefile 才零 CI 风险），而卡面与 D-11 又禁止为过判据去动 ubuntu job。
      ⇒ 登记台账 §4 **P-101** 请规划方三选一（降级判据 / 给 Linux 侧加一步对照 / 接受半绿）。
- [x] `@win` 缺工具场景退出码非 0（不得伪装通过）—— 至少 2 个任务有该读数
      —— 本轮复算两条：`docker-ps`→3（`SKIP(tool missing) docker`）、`migrate`→3（`SKIP(service unavailable) PostgreSQL localhost:5433`）
- [x] `@linux` `.gitattributes` 收敛后 `pnpm build` 仍绿（证明大小写/换行没有掩盖断链）
      —— `@ci ubuntu` 的 `frontend` job success（`✓ Compiled successfully in 9.7s`、`18/18` 静态页）。
      标签纪律：这条原文写 `@linux`，实际机位是 CI 的 ubuntu runner（Linux、区分大小写）——等价关系写在补记 4 §3 第 5 行。
      另附一条更强的复算：**行尾收敛至今零文本回退**（`git grep -I -l $'\r' HEAD` = 0；`i/crlf`/`i/mixed` 各 0；
      含 CR 的 205 个 blob 全是 git 按属性跳过的二进制）
- [x] `@win` 判据"只降不升"：`grep -rn "open(" scripts | grep -vc encoding=` 前后两数记录在案
      —— 记的是 0→0；但本轮复算**字面命中 2**，两处都是函数名 `_enclosing_open(`（`guards.py:731/772`），不是文件打开。
      ⇒ 语义计数仍 0→0，判据本身是**字符串形自红**，登记台账 §4 **P-100**（本卡不改 `guards.py`）
- [x] 仅上线用的脚本在 `cross-platform.md` 明确标「仅 Linux」，且其清单逐条可核
      —— 原写一句「`rotate_keys.sh` 等」不算清单。本轮把 `git ls-files '*.sh'` 去掉 vendored 后实测的
      **6 个自有脚本**逐条列进 `cross-platform.md` §7：4 个仅 Linux/CI、`preflight.sh` 标注"经 Git Bash 跨平台可用"、
      `EVD-V2-00C/collect_ruff_shapes.sh` 标注"历史取证件，不再执行"（F-14 / S00T.V14.3）

## 验证命令
```bash
# @win（开发烟测链，README 必须能照抄跑通）
set PYTHONUTF8=1 && python --version && node --version
python scripts/entry.py install
docker compose -f docker/compose.test.yml up -d
python scripts/entry.py migrate && python scripts/entry.py lint && python scripts/entry.py test
python scripts/entry.py verify-frontend        # 内部必须带 NEXT_PUBLIC_API_MOCK=false
# @win 一致性反证
python scripts/entry.py lint ; echo rc=$?      # 与 make lint-backend 退出码相同
# @ci（D-V6-02：原始响应存证，只抄 run 号不算）
gh run list --repo aideanew/BotHot --branch main --limit 6 --json databaseId,conclusion,name,headSha \
  > docs/06_validation/evidence/EVD-V5-00X/ci_runs.json
# @linux 换行/大小写不掩盖断链
cd apps/web && pnpm build
```

## 证据路径
`docs/06_validation/evidence/EVD-V5-00X/`

## 允许修改
`scripts/entry.py`（新）、`scripts/dev-env.ps1`（新，可选）、`Makefile`（目标体转薄调用）、`README.md`、`.gitattributes`、**`.gitignore`（本版追加：S00X.1.1 实测 `git check-ignore -v .venv/x`、`apps/api/.venv/x`、`venv/x` 全部 NO-RULE，而 `scripts/preflight.sh` 的修复提示要求 `apps/api/.venv/Scripts/python.exe` ⇒ 照它做就会在共享工作树里造出未跟踪目录；补 `.venv/` 与 `venv/` 两条是"装依赖不污染共享树"的前提，属本卡范围）**、`docs/04_engineering/cross-platform.md`（新）、`docs/04_engineering/conventions.md`、`docs/00_governance/project-map.md`、`.github/workflows/ci.yml`（**仅新增** windows job）、`docker/compose.test.yml`（若 00E 未建则可建）、EVD-V5-00X
## 禁止修改
`apps/api/app/**`、`apps/api/tests/**`（本卡不改被测行为）、`apps/web/app|components|lib/**`（UI 线归 14b/15）、`apps/api/alembic/**`（**不占迁移号**）、`packages/contracts/**`、`.github/workflows/ci.yml` 的 **ubuntu job 语义**、**`.project/**`**（vendored 子树，实测含 14 个 `.sh`，属 LangBot/firecrawl/reclip，不是 BotHot 的入口，跨平台化不覆盖它）、`docs/06_validation/evidence/EVD-V2-02/**` 与 `docs/任务规划V0.5.0/**`（并发会话在途，硬规则第五节）

## 依赖与阻塞
- Blocks：00E、RV、14b/15 的 `@win` 烟测面　Depends on：无
- 阻塞条件：① 需要改 `ci.yml` 的 ubuntu job 才能过 ⇒ 停，属 D-11 授权范围外，上报；
  ② `.gitattributes` 收敛导致 >50 个文件换行重写 ⇒ 拆独立提交，不与本卡功能改动混提；
  ③ Windows 上无 Docker Desktop/WSL2 且无法安装 ⇒ 标 blocked 并把"依赖服务"退给 `@ci`，**不得**用"本机跑不了"当验收；
  ④ 与并发会话撞同文件（`Makefile`、`ci.yml` 是热点）⇒ 不覆盖对方：改动放新文件，或等对方提交后再 ff 合入，并在汇报写明

## 建议档位 / 升级 / 规模
`opus`（见上）；若仅做 README 与文档面 ⇒ 可降 sonnet，但一旦触碰 `ci.yml`/`.gitattributes`/`Makefile` 三者任一，不得降档。规模中、≈1.5 人日。

## 执行记录（V0.11.0 第二增量 · 2026-10-15 · @win 实跑）
读数全部在 `docs/06_validation/evidence/EVD-V5-00X/win_dev_platform_readings.md`。

| 三级任务 | 状态 | 本轮事实 |
|---|---|---|
| S00X.1.1 现状测量 | ✅ | `make`=command-not-found(127)、`preflight.sh` 能跑且报 ruff/mypy 缺 + tsc 缺依赖、`python3` 是 Store 空壳（rc=0 无输出）、gitleaks/venv/node_modules 全缺 |
| S00X.1.1.1 仅上线脚本 | ✅ | `rotate_keys.sh` 等标「仅 Linux」，见 `cross-platform.md` §7 |
| S00X.1.2 `scripts/entry.py` | ✅ | 34 个任务；平台差异只在 `dispatch()`/`find_tool()`；缺工具 `SKIP(tool missing)` + **rc=3**（沿用 evidence-check 既有口径，不新造） |
| S00X.1.2.2 缺工具非零退出 | ✅ 实测 | `docker-ps`→3、`migrate`（无 PG）→3、`scan-secrets`（工具在、有命中）→1 |
| S00X.1.3 Makefile 薄转调 | ✅ | 26 开发目标 →`$(ENTRY)`、4 守卫目标 →`$(GUARDS)`、复合目标 `@:`；204→160 行 |
| S00X.1.3.1 反证 | ✅ 但**判据改正过一次** | 见下方"卡面被实测推翻的两条" |
| S00X.2.1 `.gitattributes` | ✅ | `* text=auto eol=lf` + 后缀钉死 + `/.project/** -text`；**没跑 renormalize**（共享工作树禁止），改用"含 CR 的 blob=3 且全二进制"作影响面证据 |
| S00X.2.2 编码 | ✅ | `PYTHONUTF8=1` 注入 + README/cross-platform 写明 heredoc 坑；`open(` 无 encoding 判据实测 **0→0**（该判据在本仓是空的，如实记） |
| S00X.3.1 pathlib / 大小写 | ⚠ 半边 | 新脚本全 `pathlib`；前端 import 大小写对齐**只能在 `@ci ubuntu` 上判**，待 run id |
| S00X.3.2 依赖服务文档 | ✅（含一处降格） | `cross-platform.md` §5：本机无 Docker/WSL ⇒ 连库面退回 `@ci`；端口不改 |
| S00X.4.1 windows job | ✅ 写入 | `ci.yml` 新增 `windows-dev`（16 步）；**ubuntu 两个 job 一行未改**（实测 CI 从不调用 make，故 Makefile 改动零 CI 风险） |
| S00X.4.2 @ci 双 job 读数 | ⚪ 待 push 后 | 本机无 `gh` ⇒ 按 D-V6-02 用 REST 原始响应存证 |

### 卡面被实测推翻的两条（改在本卡，不留在原判据里）
1. **原写"make 与 entry.py 退出码一致"** ⇒ 错。GNU make 把 recipe 的任何失败折成 **2**，
   `entry.py` 的 3（工具缺失）经 make 永远是 2。实测 6 个任务：dev 0/0、lint-backend 0/0、
   fmt-check 2/1、docker-ps 2/3、guard-ports 2/3、migrate 2/3 ⇒ 判据改为**零/非零一致**，三态只存在于 entry.py 层。
2. **原以为守卫类目标可以留在 Makefile**（"实体唯一源不复制"）⇒ 实测 GNU make 4.4.1 for Windows
   跑不了那些多行 `; \` 续行 recipe（`unexpected EOF while looking for matching '"'`），改 LF 也没用。
   守卫实体搬进 `scripts/guards.py`，Makefile 与 entry.py 双双转调它——仍是唯一源，只是换了宿主。
   搬完后 `guard-ports`/`guard-versions`/`guard-structure` 在 @win **首次真跑出绿**（此前本机根本跑不了）。

## 本卡的存在理由（不是"再一张治理卡"）

V0.9.0 的 F-10 与 V0.10.0 的 F-08 是**同一件事在两台机器上的两个真读数**，V0.11.0 为此立了 D-V6-01/D-V6-02。
但标签只解决"说清在哪跑的"，不解决"Windows 上跑不了"。Ubuntu 是生产平台、Win10 是一等开发平台——
这个目标此前从未有任何一张卡负责，所以每个版本的执行者都退回到"我这台能跑"的私有定义，
再把它写成"本机"。本卡把这件事变成有 CI 双 job 兜底的公共判据。

## 执行记录（V0.17.0 队列⑮ 收口轮 · 2026-10-23 · @win 现读 + @ci 原始面）

读数全在 `docs/06_validation/evidence/EVD-V5-00X/`（`win_dev_platform_readings.md` 补记 4 +
`case_alignment_probe.txt` + `ci_dual_job_readings_8e59749.txt` + `ci_runs_8e59749.json`）。
本轮**零代码改动**，动的四面全在本卡允许面内。

| 三级任务 | 状态 | 本轮事实 |
|---|---|---|
| S00X.3.1.1 前端 import 大小写 | ✅ | 双读数：`@ci ubuntu` `frontend` job（`pnpm build` 绿，18/18 静态页）+ `@win` 探针 391 处仓内说明符逐字节比对，断链 0、大小写不符 0，四发极性变异自测全对 |
| S00X.4.2 双 job D-V6-02 存证 | ✅ | `8e59749` 上 `CI` 39891503640 / `CI-Windows` 39891503516 / `Security` 39891503530 三条 attempt 1 全 success；原始响应入库 |
| S00X.2.1 行尾收敛（复算） | ✅ 更强 | 文本侧含 CR 的 blob = **0**（`git grep -I -l`），`i/crlf`/`i/mixed` 各 0；205 个含 CR 的全是按属性跳过的二进制 ⇒ 收敛撑过了其后八张卡 |
| S00X.1.3 一致性（复算） | ✅ `@win` 半边 | 6 任务零/非零一致；`check_entry_parity` rc=0（Makefile 33 目标 / entry.py 37 任务）。Linux 半边**无执行者** ⇒ 台账 §4 P-101 |
| S00X.1.2.2 缺工具非零退出（复算） | ✅ | `docker-ps`→3、`migrate`→3，两条都打印 `SKIP(...)` 且明写"不是通过" |
| S00X.2.2.1 "只降不升"（复算） | ✅ 但判据是假阳形 | 字面 0→2，两处都是函数名 `_enclosing_open(`；语义 0→0 ⇒ 台账 §4 P-100 |
| S00X.1.1.1 仅上线清单 | ✅ 补全 | `cross-platform.md` §7 把 6 个自有 `.sh` 逐条列表化（原来只有一句"…等"） |

### 本轮把上一轮的两处 ✅ 更正过来

1. **S00X.1.2 那句「✅ 34 个任务」把两个从未存在的名字蒙进了分母**。卡面列的 8 个任务名里
   `verify-backend` / `verify-frontend` 今天仍然不存在：`entry.py help` 现读 37 个任务，
   且 `grep -rn "verify\|testenv" scripts/entry.py Makefile README.md` **0 命中**。
   【失效边界】该读数锚在 `8e59749`，只对那一批成立：**同一队列的下一张卡 STEP-00E（`9983c63`）就把这四个名字
   建进了 `entry.py`/`Makefile`**，所以现在复跑同一条 grep **会得到命中**。跨批引用数字的锚定规则见
   `docs/06_validation/evidence/EVD-V17-12/s12_readings.md` §0.1。
   ⇒ 按 **6/8 落地 + 2 移交** 记；这两个名字（连同 `testenv-up`/`testenv-down`）是 STEP-00E
   S00E.1.3 / S00E.2.1 的交付物，本卡不代做。00E 就是下一张。
2. **S00X.4.1 卡面写"在 `ci.yml` 新增 windows-latest job"**，实体今天住在 `.github/workflows/ci-windows.yml`
   （STEP-00W S00W.2.1 按 D-V7-01 拆的）。本卡不改写卡面历史，只在 S00X.4.2 下面标了"两个 job"
   在现编排里的实体形态是"两个工作流"。
