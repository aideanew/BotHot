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
- 代码/配置锚（**下列数字为 @win 于 17c5d28 实测，非估算**）：`Makefile`（**204 行**）、`scripts/`（**4 个 .sh**：`preflight.sh`/`rotate_keys.sh`/`smoke.sh`/`test-env.sh`，另有 `check_docs_consistency.py`、`gen_contracts.py`）、全仓被跟踪的 `.sh` **20 个 = 6 个自有 + 14 个在 `.project/` vendored 子树**（LangBot/firecrawl/reclip，**不属本卡改造面**）、自有 6 个中另两处是 `apps/web/scripts/ci-repro-frontend.sh` 与 `docs/06_validation/evidence/EVD-V2-00C/collect_ruff_shapes.sh`、`.gitattributes`（**全文只有 1 行：`*.sh text eol=lf`**）、`.github/workflows/ci.yml`（**397 行，5 个 job 全是 ubuntu-latest**：`workflow-lint:12`、`backend:23`、`frontend:174-325`、`compose:326`、`compose-smoke:361`）、`apps/web/.nvmrc`、`apps/api/pyproject.toml`（ruff 0.12.12/mypy 钉版）、`docker/compose.yml`（端口 3300/5433/6380）、`docs/04_engineering/conventions.md`
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
7. [ ] 📄 **S00X.3.2** `cross-platform.md` + README 写死 Win10 依赖服务方案：Docker Desktop 或 WSL2 起 PostgreSQL 16 / Redis 7，**版本与生产、CI 对齐**，端口沿用 5433/6380（AGENTS.md 端口表：3000 禁用、3200 前端宿主、3300 后端）
   - S00X.3.2.1 端口被占用时报错并点名占用者，**不得**静默换端口（换端口会让 `AIDEANBOT_TEST_PG_DSN` 与读分数叉——STEP-00E 同条纪律）

### S00X.4 CI 双平台
8. [ ] 🛠 **S00X.4.1** `.github/workflows/ci.yml` 新增 `windows-latest` job：装 Python 3.12 + Node（按 `apps/web/.nvmrc`）→ 后端 `ruff`/`mypy`/`pytest`（**需真库的用例按标记 skip**，并在 summary 里打印 skip 构成）→ 前端 `typecheck`/`lint`/`vitest`/`build`（`NEXT_PUBLIC_API_MOCK=false`）
   - S00X.4.1.1 `ubuntu-latest` job 一行不改（正式验收面语义必须稳定）；windows job **不**跑 alembic upgrade/downgrade 往返（那是 @ci ubuntu 的出门判据，见 STEP-04）
   - S00X.4.1.2 windows job 的 `SKIP_BASELINE` 与 ubuntu 分开设定，否则"平台差异"会伪装成"回归"
9. [ ] ✅ **S00X.4.2** 验收读数 `@ci`：push 后取 ubuntu-latest 与 windows-latest 两个 job 的 **run id + conclusion + head_sha**，按 D-V6-02 存成证据文件（`gh` 或 GitHub REST 原始响应均可，只抄 run 号不算）

## 验收标准（Done 判据，全部标机器）
- [ ] `@ci` `windows-latest` 与 `ubuntu-latest` 两个 job 均 success（run id/conclusion/head_sha 存证）
- [ ] `@win` 干净机按 README 从零：`install → 起 PG/Redis → migrate → 起前后端 → lint → 单测 → build` 全绿，逐条命令与输出入 EVD（**开发烟测**，不替代 Ubuntu 验收）
- [ ] `@win`+`@linux` `make <task>` 与 `python scripts/entry.py <task>` 退出码一致（至少覆盖 6 个任务，两平台各一次）
- [ ] `@win` 缺工具场景退出码非 0（不得伪装通过）—— 至少 2 个任务有该读数
- [ ] `@linux` `.gitattributes` 收敛后 `pnpm build` 仍绿（证明大小写/换行没有掩盖断链）
- [ ] `@win` 判据"只降不升"：`grep -rn "open(" scripts | grep -vc encoding=` 前后两数记录在案
- [ ] 仅上线用的脚本在 `cross-platform.md` 明确标「仅 Linux」，且其清单逐条可核

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
`scripts/entry.py`（新）、`scripts/dev-env.ps1`（新，可选）、`Makefile`（目标体转薄调用）、`README.md`、`.gitattributes`、`docs/04_engineering/cross-platform.md`（新）、`docs/04_engineering/conventions.md`、`docs/00_governance/project-map.md`、`.github/workflows/ci.yml`（**仅新增** windows job）、`docker/compose.test.yml`（若 00E 未建则可建）、EVD-V5-00X
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

## 本卡的存在理由（不是"再一张治理卡"）
V0.9.0 的 F-10 与 V0.10.0 的 F-08 是**同一件事在两台机器上的两个真读数**，V0.11.0 为此立了 D-V6-01/D-V6-02。
但标签只解决"说清在哪跑的"，不解决"Windows 上跑不了"。Ubuntu 是生产平台、Win10 是一等开发平台——
这个目标此前从未有任何一张卡负责，所以每个版本的执行者都退回到"我这台能跑"的私有定义，
再把它写成"本机"。本卡把这件事变成有 CI 双 job 兜底的公共判据。
