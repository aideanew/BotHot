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
1. [ ] ✅ **S00E.1.1** 先量现状：`bash scripts/test-env.sh up`（或 compose）是否可用；记录失败点（端口占用 / 镜像拉取 / 无 docker）入 EVD
2. [ ] 🛠 **S00E.1.2** 固定 PG/Redis 起法：测试专用 compose，宿主端口用**项目分配段**（PG 5433、Redis 6380），禁占 3000（AGENTS.md 端口表）；加 `docker compose ps` 健康等待与超时
   - S00E.1.2.1 与并发会话隔离：默认端口被占时**报错退出并点名占用者**，不静默换端口（换端口会让 `AIDEANBOT_TEST_PG_DSN` 与读数分叉）
3. [ ] 🛠 **S00E.1.3** 迁移与播种：`verify-backend` 目标内先 `alembic upgrade head` 再 pytest；`alembic` 单头断言保留
4. [ ] ✅ **S00E.1.4** 全量读数：`make verify-backend` 输出 `failed/passed/skipped` + 覆盖率，junit 入 EVD；**目标 0 failed 且 skip ≤ 6**
   - S00E.1.4.1 判据必须带 `-rs`，并对 `test_be02_engine_routing.py::test_short_link_second_ingest_hits_cache_via_url_fallback` 单独点名：出现在 skipped 列表 = **未验收**，不是通过
5. [ ] 🛠 **S00E.2.1** 前端面：`verify-frontend` = `pnpm install --frozen-lockfile` → `typecheck` → `vitest run`；把 `node_modules` 是否存在**作为读数输出**（F-10：上一版说存在、本版说没有）
6. [ ] 📄 **S00E.2.2** `conventions.md` 增三条：①skip≠pass 的判定动作；②工具缺失必须打印 `SKIP(tool missing)` 并区分退出码；③验收环境是共享工作树的一部分，**每台机器每轮重取**，不得引用上一版的工具链状态
7. [ ] 👤 **S00E.3.1** 裁决并登记："验收由谁的环境跑"二选一——(A) 固定一台依赖机为验收机，(B) CI 作为唯一验收面。写进 `decision-log.md` 的 `D-V4-01`
8. [ ] ✅ **S00E.3.2** 复跑验证：同一命令连跑两次，failed/skipped 数一致；不一致说明环境有状态泄漏，本卡未过

## 验收标准
- [ ] `make verify-backend` 在干净机器一条命令出全量读数，且 `0 failed`、skip ≤ `SKIP_BASELINE`
- [ ] 哨兵用例**真实执行**（不在 skipped 列表内）——这是 R0/16 从"已实现"升为 Done 的唯一途径
- [ ] `make verify-frontend` 一条命令完成安装 + typecheck + vitest，读数入 EVD
- [ ] 端口零越界：`grep -rn '3000' docker scripts` 无 BotHot 服务占用（AGENTS.md 约束）
- [ ] 并发安全：默认端口被占时报错点名占用者，不静默换端口
- [ ] 两次复跑读数一致（无状态泄漏）
- [ ] `conventions.md` 三条已写；`decision-log.md` 有 `D-V4-01` 条目

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
