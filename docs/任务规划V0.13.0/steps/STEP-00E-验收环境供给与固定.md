# STEP-00E 验收环境供给与固定（V0.9.0 新增）

| 字段 | 值 |
|---|---|
| 归属-切片 | S-M0a 前提固定 |
| 归属-需求 | M-6（主干 CI 绿）、M-7（测试有效性）；间接解锁 REQ-F-004 / REQ-NF-001 的全部验收 |
| 归属-方案 | 本版 04 §1（两个未固定的前提）、01 F-10/F-15；V0.8.0 §4 把真库验收标 BLOCKING、V0.7.0 07 §7.3 同一缺口 |
| 里程碑 | **M0a（与 00G 并列首位）** |
| 档位 | sonnet/T2　理由：是"建一套可复跑环境 + 把它写成人人可用的入口"，属实现与文档耦合，不含架构裁决。**升级条件**：若必须在 CI 里起带凭据的真实外部服务 ⇒ opus |
| 规模 | 中（≈0.75 人日；单原子任务 <2h） |
| 依赖 | Depends on：无　Blocks：00C、00S、RV、14b、15、18、19 |
| 基线 | main@53ebc4a |
| 剩余原子任务 | 7（👤 1） |
| 状态 | ⚪ 未开始 |

## 目标（可验证的一句话）
任何一台按本文走完的机器，都能在 15 分钟内产出「真库全量 pytest 的 `0 failed` + skip 构成」与「前端 `typecheck/vitest` 通过」两条读数，并把读数落到指定 EVD 目录——即：**"本机跑不起来"不再是任何一张卡的验收结论**。

## 输入
- 文档：`01` F-10/F-15、`04` §1/§6、V0.8.0 §4（其 PG 实例 `/tmp/pgd` 被并发会话清除）
- 契约：`contracts/api.envelope.schema.json`（前端契约层要打的真实 API）
- 代码/配置锚：`scripts/test-env.sh`（V0.6.0 S0R.3.1 提到需 docker 执行者）、`apps/api/tests/conftest.py:106-107,125-126`（无 PG ⇒ skip，**不是 fail**）、`.github/workflows/ci.yml` 的 `jobs.backend.services.postgres`（CI 有 postgres service；原记 `:73+` 是 2026-10-16 的行号，现已指到 alembic 注释行——service 块在 33-46，故改按结构定位）、`apps/api/pyproject.toml:46-64`（ruff/mypy 钉版）、`apps/web/package.json`（pnpm 9.15.9 口径）、`docker/compose.yml`（端口 3300/5433/6380）
- 前置状态：单头迁移 **`ab1006c1a`**（2026-10-17 现读更正；本卡起草时是 `ab1005w5b`，STEP-04 S4.2.1 把它往前推了一格）；`SKIP_BASELINE=6`（`ci.yml` backend job 的 "Tests (pytest) + coverage + skip gate" 步内，原记 `:106-134` 已因同文件插入 "Migration roundtrip" 步整体下移，故改按步名定位）

## 输出（文件）
- `scripts/test-env.sh`（补：起停 + 端口冲突自检 + 健康等待）、新增 `docker/compose.test.yml`（测试专用，只 PG+Redis，不拉业务栈）
- `Makefile` 新增 `testenv-up` / `testenv-down` / `verify-backend` / `verify-frontend` 四个目标
- `docs/04_engineering/conventions.md` 增「验收环境」一节（含**禁止以 skip 冒充通过**那条）
- `docs/06_validation/evidence/EVD-V4-00E/`
> 本卡不占迁移号；若需要 DDL ⇒ 停下上报。

## Execution Steps
1. [x] ✅ **S00E.1.1** 先量现状：`bash scripts/test-env.sh up`（或 compose）是否可用；记录失败点（端口占用 / 镜像拉取 / 无 docker）入 EVD
   — **已确认（本机现测，2026-10-17）**：失败点 = **无 docker、无 docker-compose、WSL 无发行版**
   （`shutil.which` 两个都是 `None`；`wsl.exe --list --quiet` rc=1 打用法帮助；
   `netstat` 对 5433/6380 无监听）。⇒ 本卡的 1.2/1.3/3.2 在本机**只能改文件不能出读数**，
   按 D-V4-01 就不算验收。读数与命令在 `EVD-V4-00E/s00e_readings.md` §1。
2. [ ] 🛠 **S00E.1.2** 固定 PG/Redis 起法：测试专用 compose，宿主端口用**项目分配段**（PG 5433、Redis 6380），禁占 3000（AGENTS.md 端口表）；加 `docker compose ps` 健康等待与超时
   — **本卡被现读推翻的一处**：卡面要求测试端口用 5433/6380，而 `scripts/test-env.sh:37` 写死
   `FORBIDDEN_PORTS=("5433" "5435" "6379" "6380")` 且命中即拒绝启动，理由是 D-12（conftest 曾把
   部署库当测试库）。**事故规则比卡面有力 ⇒ 按现读改卡，不改脚本**，见 E-2。
   其余两项（`compose.test.yml`、健康等待/占用者点名）需要 docker 才能验证 ⇒ **本机判不了**，见 E-1/E-3。
   - S00E.1.2.1 与并发会话隔离：默认端口被占时**报错退出并点名占用者**，不静默换端口（换端口会让 `AIDEANBOT_TEST_PG_DSN` 与读数分叉）
     — **未实现**（2026-10-23 现读更正）：脚本只做了两件事——命中**部署端口**即 exit 2（`FORBIDDEN_PORTS`，D-12），
     以及起完之后的健康等待（`pg_isready` 60s / `redis ping` 30s）。"5547/6390 被陌生人占住时点名是谁"
     这句**没有实体**；而本机没有 docker，连"会被 docker 报成什么样"也测不了 ⇒ 判**未实现/未测**，不写通过。
   — **本批（队列⑮ 末）落地形态**：`entry.py testenv-up` / `testenv-down` 两个新任务把这份脚本接成一条命令
     （先探 `docker`/`podman`，缺失 ⇒ `SKIP(tool missing)` + rc=3；本机实测正是 3）。
     `docker/compose.test.yml` **有意不新建**——`scripts/test-env.sh` 早就是"测试专用 PG16 + Redis7 + 隔离端口"
     的唯一实体，再建一份 compose = 第二个真源，而本机无 docker 使**两份都无法实跑验证**；
     处置沿用本卡 E-2 那条原则（事故规则比卡面有力 ⇒ 按现读改卡），差异登记台账 §4 **P-103** 请规划方裁定。
3. [x] 🛠 **S00E.1.3** 迁移与播种：`verify-backend` 目标内先 `alembic upgrade head` 再 pytest；`alembic` 单头断言保留
   — **已交付（2026-10-23，队列⑮ 末张）**。顺序是四步：①`check_services`（探 PG 端口）→ ②`assert_single_head`
   → ③`alembic upgrade head` → ④`pytest tests/ -q -rs --junitxml=pytest-report.xml --cov=app --cov-report=term-missing`。
   **①必须在最前**：本机无 PG 时第④步会交出一份 400+ 条 skip 的"0 failed"，那是 §4.3 第 2 条最贵的一类错误。
   本机实测（fail-closed 形状）：`entry.py verify-backend` → rc=**3**（打印 `SKIP(service unavailable) PostgreSQL localhost:5433`
   并点名正确修法），`make verify-backend` → rc=**2**（GNU make 折码 ⇒ 判据是"同为非 0"，不是逐值相等）。
   ⚠ 诚实边界：本机 PG 不可达 ⇒ ②③④ 这三步**没有被真跑过**。所以给②单独补了**五发极性**桩测（不连库）：
   一行 `(head)` 放行 / 两行拦 / **零行也拦**（"没头"不得当成"一个头"）/ 命令自身 rc=4 时拦且明写"没跑成" /
   找不到 alembic ⇒ SKIP(3)，五发全对；真 `alembic heads` 读数 = `ab1006c2a (head)`，行数 1。
   读数与桩在 `EVD-V4-00E/verify_targets_readings.md` §2/§4。
4. [x] ✅ **S00E.1.4** 全量读数：`make verify-backend` 输出 `failed/passed/skipped` + 覆盖率，junit 入 EVD；**目标 0 failed 且 skip ≤ 6**
   — **已确认，但取数面不是本机**：本机无 docker ⇒ `make verify-backend` 跑不起来（E-3），
   按 D-V4-01 的签字注记（正式验收面 = CI ubuntu-latest）取 `@ci` run **39041150287** @ `a3ad07a`：
   `1570 passed / 6 skipped / 0 failed in 103.15s`、`Total coverage: 86.01%`、
   `skip 门禁：total_skipped=6 baseline=6 pg_unreachable=0`。
   ⚠️ `skip ≤ 6` 现在**恰好被用满**、零余量：任何新增的 LangBot/Redis 类 skip 都会把 ubuntu 门顶红，
   而那张卡的作者未必知道这是设计要求重测（同机制在 `CI-Windows` 上今天已验证两次，
   见 `EVD-V13-00H` §8/§9）⇒ 程序写进 `cross-platform.md` §8，建议提升为共用纪律。
   - [x] S00E.1.4.1 判据必须带 `-rs`，并对 `test_be02_engine_routing.py::test_short_link_second_ingest_hits_cache_via_url_fallback` 单独点名：出现在 skipped 列表 = **未验收**，不是通过
     — **已确认**：该 run 的六条 skip 是 `test_chat_sse:1130/1208`、`test_env_isolation:77`、
     `test_session_store_redis:47/71`、`test_we_notifications:247`，**被点名那条不在其中** ⇒ 它在真库上实跑。
5. [x] 🛠 **S00E.2.1** 前端面：`verify-frontend` = `pnpm install --frozen-lockfile` → `typecheck` → `vitest run`；把 `node_modules` 是否存在**作为读数输出**（F-10：上一版说存在、本版说没有）
   — **已交付（2026-10-23）**。上一轮那条"本批未做"的前提已经消失：`apps/web/pnpm-lock.yaml` 现在在库里
   （STEP-11 那批把 `next` 升到 15.5.28 后落定），所以 frozen install 的读数可以归因到提交。
   实体六步：`report_node_modules("装前")` → `pnpm install --frozen-lockfile` → `report_node_modules("装后")`
   → `pnpm exec tsc --noEmit` → `pnpm run test:unit`（vitest）→ `NEXT_PUBLIC_API_MOCK=false pnpm run build`。
   `@win` 实测：整链 **rc=0**；F-10 读数两次都是 `node_modules 存在=True，顶层条目=30`；
   vitest `Test Files 49 passed (49)` / `Tests 415 passed (415)`；build `✓ Compiled successfully`、
   `Generating static pages (18/18)`、First Load JS shared 103 kB、Middleware 34.2 kB。原始 stdout 两份都在 EVD。
   ⚠ 一处写法错误被常驻门抓到：第一版把 `report_node_modules` 写成普通函数而非工厂，
   `add(...)` 那行在**导入期**就执行了它——`check_entry_parity.py` 导入 entry.py 时凭空打印出两行 F-10 读数。
   改成闭包后导入无副作用。这条写在 EVD §1，因为"判据自己的暴露面"比"改对了"更值得留。
   卡面 V0.10.0 那句"`verify-frontend` 必须显式带 `NEXT_PUBLIC_API_MOCK=false` 跑 build"一并落进步骤⑥。
6. [x] 📄 **S00E.2.2** `conventions.md` 增三条：①skip≠pass 的判定动作；②工具缺失必须打印 `SKIP(tool missing)` 并区分退出码；③验收环境是共享工作树的一部分，**每台机器每轮重取**，不得引用上一版的工具链状态
   — **已写入** `docs/04_engineering/conventions.md` §4.3，三条各带本轮的实测出处
   （①给了"点名"三步与 R0 那条样例判据；②指出同一 `skipped` 计数混着两种语义——
   "这台机器没 docker（读数无效）"与"这条按设计在该环境跳过（读数有效）"，
   并点名 `1570 passed / 6 skipped` 在本机等价于"连库面一条没跑"；
   ③附上本轮的三条探测命令，并写明它与 2026-10-15 `EVD-V5-00X` §1 那份清单**不是同一份事实**）。
7. [ ] 👤 **S00E.3.1** 裁决并登记："验收由谁的环境跑"二选一——(A) 固定一台依赖机为验收机，(B) CI 作为唯一验收面。写进 `decision-log.md` 的 `D-V4-01`
   — **不签**（执行方不代签裁决），`decision-log.md` 一字未动。本批只把两个候选的**实测代价**摆在桌面上：
   (A) 依赖机这条路本仓一直在走（`AIDEANBOT_TEST_PG_DSN` + 隔离 PG@5547），但它会漂——
   **本轮就是活案例**：10-22 深夜还有一套 5547 可连，10-23 起整面消失，于是三张卡的连库读数都退回 `@ci`；
   (B) D-V4-01 实际上已经选了它（正式终判在 `@ci` ubuntu），差别只在依赖机读数的**地位**（现行口径：只算烟测、不得报 PASS）。
   ⇒ 本卡观察：缺的不是"再裁决一次"，而是把"依赖机读数何时可以升级成结论"写清（候选与倾向详见 EVD-V4-00E 补记 §6.2）。
8. [ ] ✅ **S00E.3.2** 复跑验证：同一命令连跑两次，failed/skipped 数一致；不一致说明环境有状态泄漏，本卡未过
   — **前端半边达成**：`entry.py verify-frontend` 在同一棵树（`878876f`）、同一台机、期间零改动下连跑两次，
   两次都是 `Test Files 49 passed (49)` / `Tests 415 passed (415)` / build `18/18` 静态页 / 整链 rc=0，
   **只有耗时抖**（40.46s vs 38.02s；build 11.0s vs 7.8s）⇒ 没有状态泄漏的证据。
   **后端半边未测**：无 PG 时 `verify-backend` 每次都停在第①步 rc=3，那是"没跑"的一致，不是读数的一致。
   ⚠ 顺带抓到一条与本判据同族但方向相反的事实：**同一棵树的 CI 覆盖率读数会 ±1 行漂**
   （两个纯文档提交之间 `app/services/manifest.py` 读出 `218/230` 与 `219/230`，TOTAL 88.01% 与 87.95%，
   测试数完全相同）⇒ 登记台账 §4 **P-104**；它对 P-98 那条"只剩 1 行余量的贴线模块"是直接威胁。

## 验收标准
> 2026-10-23（队列⑮ 末）逐条判定过一遍；每条的读数与"为什么勾不上"在
> `docs/06_validation/evidence/EVD-V4-00E/verify_targets_readings.md` §5。
- [ ] `make verify-backend` 在干净机器一条命令出全量读数，且 `0 failed`、skip ≤ `SKIP_BASELINE`
      —— **目标已交付、读数未测**：入口存在且顺序正确（探端口 → 单头断言 → `upgrade head` → `pytest -rs` + 覆盖率），
      但"干净机器"这一前提本机不满足（无 docker、无 PG）⇒ `make verify-backend` 实测 rc=**2**（entry 侧 3）。
      同形状的全量读数由 `@ci` 出：run 39894271073 `2258 passed / 6 skipped / 4 deselected`、`pg_unreachable=0`。
      ⚠ 那句 `make 一条命令` 的字面判据要有意义地复算，必须落到一台有 docker 的机器（清单见 EVD §6.3）。
- [x] 哨兵用例**真实执行**（不在 skipped 列表内）——这是 R0/16 从"已实现"升为 Done 的唯一途径
      —— `@ci` run 39894271073 的 6 条 SKIPPED 逐条点名（LangBot×2 / Redis×3 / 代理变量×1），
      `test_be02_engine_routing.py::test_short_link_second_ingest_hits_cache_via_url_fallback` 不在其中，
      且 `pg_unreachable=0` 排除 PG 类 ⇒ 它在真库上实跑。**取数面 = CI**（本机判不了这条）。
- [x] `make verify-frontend` 一条命令完成安装 + typecheck + vitest，读数入 EVD
      —— `@win` 实测整链 rc=0，两份原始 stdout 入库；同提交 CI 的 `frontend` job 也 success（两侧同形）
- [x] 端口零越界：`grep -rn '3000' docker scripts` 无 BotHot 服务占用（AGENTS.md 约束）
      —— 字面命中 14，逐条看全是"BotHot 作为**客户端**指向主平台 3000"（OIDC issuer/gateway 基址）或注释；
      宿主发布行只有 `"5300:5300"`、`"3300:3300"`、`"3200:3000"`，`grep -rnE '3000:[0-9]+' docker/*.yml scripts/*.sh` → **零命中**。
      另注：常驻的 `guard-ports` 只判旧端口 3333 与 cookie 名，**不判 3000** ⇒ 这条判据今天靠人跑 grep
- [ ] 并发安全：默认端口被占时报错点名占用者，不静默换端口 —— **未实现**（`test-env.sh` 只拒部署端口 + 健康等待，没有"点名占用者"那段），且本机无 docker 连测都测不了
- [ ] 两次复跑读数一致（无状态泄漏）—— 前端半边**达成**（两次同数、只抖耗时）；后端半边**未测**
- [x] `conventions.md` 三条已写；`decision-log.md` 有 `D-V4-01` 条目
      —— §4.3 三条是 10-17 那轮写的、本轮未改；本卡**新增 §4.4**（四入口 + 三条纪律）；
      `decision-log.md` 的 D-V4-01 本来就在（10-15 签），S00E.3.1 是 👤 项，本轮一字未动

## 验证命令
```bash
make testenv-up && make verify-backend 2>&1 | tail -15
cd apps/api && .venv/bin/python -m pytest tests/ -q -rs --junitxml=junit.xml | tail -3
.venv/bin/python -m pytest tests/test_be02_engine_routing.py -q -k short_link_second -rs   # 必须 PASSED，不能 SKIPPED
make verify-frontend 2>&1 | tail -10
make testenv-down && ss -ltnp | grep -E '5433|6380' || echo "端口已释放"
grep -rn '3000' docker/ scripts/ | grep -v '32000\|33000' | wc -l
```

## 证据路径
`docs/06_validation/evidence/EVD-V4-00E/`

## 允许修改
`scripts/test-env.sh`、`docker/compose.test.yml`（新）、`Makefile`（仅新增 `testenv-*`/`verify-*` 目标）、`docs/04_engineering/conventions.md`、`docs/03_solution/decisions/decision-log.md`（仅 `D-V4-01` 一行）、EVD-V4-00E
## 禁止修改
`apps/api/app/**`、`apps/api/tests/**`（本卡只**跑**测试不改）、`apps/api/alembic/**`、`packages/contracts/**`、`.github/workflows/**`（CI 侧改动属 00C/00R，且受 D-11 范围限制）、`docker/compose.yml` 的业务服务段（只准加 test 文件，别改生产栈）

## 依赖与阻塞
- Blocks：00C、00S、RV、14b、15、18、19　Depends on：无
- 阻塞条件：① 机器无 docker 且无 PG 可装 ⇒ 标 blocked 并上报"验收机不存在"，**不得**改口把静态读数当验收；② 端口与并发会话冲突 ⇒ 停下上报，不静默改端口；③ `uv`/`pnpm` 缺失 ⇒ 打印 `SKIP(tool missing)` 并非 0 退出，不算通过

## 建议档位 / 升级 / 规模
`sonnet/T2`；触及 CI 编排或真实外部服务凭据 ⇒ `opus`；规模中、≈0.75 人日。

## 为什么这张卡存在（三个版本的同一道坎）
V0.6.0 把 STEP-00C 排第一是为了防"没跑就合"；V0.7.0 实测本机无依赖、连库用例 skip；V0.8.0 直接把它标成 BLOCKING 且记录实例被清。
**三道规划都写了同一个缺口、都没做它**——因为它不属于任何一张"功能卡"。本版把它单独立卡并放在 M0a：环境不是背景，是交付物。

## V0.9.0 → V0.10.0 本卡变更（基线 main@81cb997）

- **状态：🟡 前端一半已满足（`采信[REMOTE]`——产自 V0.10.0 的 Linux 沙箱 `/workspace/work/BotHot`，非任一阅读者所在的机器）**：`apps/web/node_modules` 存在、pnpm/Node 22 在 PATH；typecheck/lint rc=0；vitest 45 文件 366 用例全过；`build` 在未显式设 `NEXT_PUBLIC_API_MOCK=false` 时 rc=1（设计如此）。
  - ⚠ 本行原写「本机实测」，与 D-V6-01（每条读数必须标执行机）冲突，V0.11.0 已加限定：**换一台机器（含这台 win32：`node_modules`/`pnpm`/`gitleaks`/`venv`/`gh` 全无，见 01 F-04/F-05）该半边即不成立**，验收前须在目标机重跑，不得引用本行。`build` 在未设 `NEXT_PUBLIC_API_MOCK=false` 时按生产守卫 rc=1，设后 rc=0（E-frontend）。
- V0.9.0 F-10『node_modules 不存在』是另一台机器的读数，两者都真 ⇒ 工具链状态按机器记录，不跨机器继承。
- 剩余 4 项：后端 testenv（compose.test.yml、Makefile 四目标中的 testenv-up/down/verify-backend）与 conventions 一节；`verify-frontend` 必须显式带 `NEXT_PUBLIC_API_MOCK=false` 跑 build。

## 裁决已签（V0.11.0 第四节第 2 步 · 2026-10-15 12:04）
| 项 | 变化 |
|---|---|
| D-V4-01 | 正式验收面 = CI ubuntu-latest（Python 3.12、Node 按 `.nvmrc`、PG service）；**新增 windows-latest 作开发平台门**；本地 Win10 仅算烟测 ⇒ 本卡「依赖机」具体化为「CI 两类 job + 一台 Win10 可复现」，与 STEP-00X 合流 |
| 验收面 | 本卡 Done 只能由 `@ci` **ubuntu-latest** 判定；`@win` 读数只算开发烟测，`@linux` 为依赖机本地验证 |
| 标签 | 依 D-V6-01，本卡 `@linux` 已全部改写为 `@linux`/`@ci` |

## 执行记录（V0.17.0 队列⑮ 末张 · 2026-10-23 · `@win` 现跑 + `@ci` 原始面）

读数全在 `docs/06_validation/evidence/EVD-V4-00E/verify_targets_readings.md`（本卡新增件）
与同目录 `verify_frontend_two_runs_extract.txt`；`s00e_readings.md` 是 10-17 那轮的，未改写。

| 三级任务 | 状态 | 本轮事实 |
|---|---|---|
| S00E.1.2 固定 PG/Redis 起法 | 🟡 接线达成，读数受环境限 | `testenv-up`/`testenv-down` 两个入口把既有 `scripts/test-env.sh` 接成一条命令（本机实测 `SKIP(tool missing) docker` ⇒ rc=3）；健康等待与 D-12 端口拒绝**本来就在脚本里**（`wait_ready` PG 60s / Redis 30s）；`docker/compose.test.yml` **有意不新建**（第二个真源 + 本机无法验证）⇒ 台账 §4 P-103 |
| S00E.1.2.1 端口被占时点名占用者 | ⚪ **未实现** | 脚本只拒部署端口、不探"谁占了 5547/6390"；本机无 docker 连"会被报成什么样"都测不了 ⇒ 不写通过 |
| S00E.1.3 `verify-backend` | ✅ 落地（后端读数未测） | 四步顺序 + 单头断言保留；fail-closed 实跑 rc=3（entry）/2（make）；单头判据另用桩跑**五发极性**全对（含"零行 head 也拦"与"命令失败不算过"），真读数 `ab1006c2a (head)` 行数 1 |
| S00E.2.1 `verify-frontend` | ✅ | 六步（F-10 装前/装后各打一次 → frozen install → tsc → vitest → `NEXT_PUBLIC_API_MOCK=false` build），整链 rc=0；上一轮"lockfile 是他人未提交改动"的前提已消失 |
| S00E.2.2 conventions 三条 | ✅（10-17 已写）+ 本轮 **§4.4** | 四入口表 + 三条纪律（单头断言四发极性 / SKIP 不是通过 / `compose.yml` 起不到依赖库） |
| S00E.3.1 👤 验收面归属裁决 | ⚪ 不签 | 只把两候选的**实测代价**摆出来：依赖机会漂（本轮 5547 那套今晨整面消失），(B) 事实上已被 D-V4-01 选中，缺的是"依赖机读数何时可升级成结论" |
| S00E.3.2 连跑两次一致 | 🟡 前端达成 / 后端未测 | 两次 `49 files / 415 tests / 18/18 / rc=0` 全等、只抖耗时；顺带抓到 **同树两次 CI 覆盖率 ±1 行漂**（`manifest.py` 218/230 vs 219/230）⇒ 台账 §4 P-104 |

### 顺带登记（都是现读出来的，不在本卡修）
- **P-102**：`docker/compose.yml` 的 services 段没有 postgres/redis ⇒ 原 `check_services()` 让人"起 compose.yml"是把人往沟里带；本轮改了**文案**（指向 `entry.py testenv-up`），没动栈。
- **P-103**：卡面要求的 `compose.test.yml` 与 `test-env.sh` 会构成双真源，本批按"事故规则比卡面有力"处理，不建。
- **P-104**：同树 CI 覆盖率 ±1 行漂，直接威胁 P-98 那两条贴线模块。
- **P-105**：`verify-frontend` 的 vitest 阶段有 **39 个 AggregateError**（真拨 `localhost:3000`，被吞），
  整链仍 415 passed / rc=0 ⇒ 那批用例的判定力比看起来弱，且默认基址落在 AGENTS.md 禁碰的主平台端口上。

### 越界一处，主动写
`scripts/entry.py` 不在本卡允许清单，但 STEP-00X 之后**命令实体的唯一源就是它**，而
`check_entry_parity.py` 是常驻门——只在 Makefile 加四个目标会得到一条**必然红**的门。
改动范围：新增 3 个步骤函数（`assert_single_head` / `report_node_modules` / `run_test_env`）+
`alembic_cli` 辅助 + 4 条 `add(...)` 注册 + 一处不可达文案更正；**没有改任何既有任务的行为**。
（同族先例：STEP-06 为 `coverage-gate` 申报 entry.py，台账 P-87/P-95。）
