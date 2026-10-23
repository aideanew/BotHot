# EVD-V4-00E 补记（2026-10-23，V0.17.0 队列⑮ 末张）— 验收环境四入口的落地与读数

采集机：`@win`（Windows 10.0.19045 / Git Bash / `apps/api/.venv` = Python 3.12.10 / pnpm 9.15.9 / Node v24.21.0）。
基线：`main@878876f`（STEP-00X 余项收口批）。
上一版本目录只有 `s00e_readings.md`（2026-10-17 那轮：量现状 + 把 `skip ≤ 6` 恰好被用满这件事登记下来）。
本补记覆盖 S00E.1.3 / S00E.2.1 / S00E.3.2 的前端半边，并如实标出仍判不了的部分。

## 0. 本轮环境（按 conventions §4.3 第③条重取，不引用上一版清单）

```
$ python scripts/entry.py docker-ps      → SKIP(tool missing) docker ⇒ rc=3
$ python scripts/entry.py migrate        → SKIP(service unavailable) PostgreSQL localhost:5433 ⇒ rc=3
$ which docker / docker-compose          → 都没有；WSL 无发行版（与 10-17 那轮同形）
$ apps/web/node_modules                  → 存在，顶层条目 30
```

⇒ **后端连库半边本轮仍然判不了**，按 D-V4-01 由 `@ci`（ubuntu + postgres service）承担；
本轮能实跑的是：四个新入口的**接线正确性**（含 fail-closed 形状）、单头断言的**五发极性**（不连库）、
以及 `verify-frontend` 的**完整读数 + 两次复跑**。

## 1. 落地了什么（实体一份在 `scripts/entry.py`，Makefile 薄转调）

| 入口 | entry.py 步骤列表 | Makefile |
|---|---|---|
| `testenv-up` | 探 docker/podman → `bash scripts/test-env.sh up` | `testenv-up: @$(ENTRY) testenv-up` |
| `testenv-down` | 同上 `down` | `testenv-down` |
| `verify-backend` | `check_services` → `assert_single_head` → `alembic upgrade head` → `pytest tests/ -q -rs --junitxml=pytest-report.xml --cov=app --cov-report=term-missing` | `verify-backend` |
| `verify-frontend` | `report_node_modules("装前")` → `pnpm install --frozen-lockfile` → `report_node_modules("装后")` → `pnpm exec tsc --noEmit` → `pnpm run test:unit` → `NEXT_PUBLIC_API_MOCK=false pnpm run build` | `verify-frontend` |

一致性门（常驻）：`python scripts/check_entry_parity.py` → **rc=0**，
读数 `Makefile 目标 37 个；entry.py 任务 41 个；实体文件 entry.py=1 guards.py=1`。
`pyproject`/ruff：`ruff check scripts/entry.py` → All checks passed；`py_compile` 通过。

一处**写错后被发现**的细节必须记下来（否则下一个人还会踩）：第一版把 `report_node_modules`
写成了普通函数而不是工厂，于是 `add(...)` 那一行在**导入期**就把它执行了——
`check_entry_parity.py` 导入 entry.py 时凭空打印出两行 `F-10 读数[装前]/[装后]`，
这就是暴露面。改成工厂 + 闭包后导入无副作用（该读数已复算：parity 步骤不再打印任何东西）。

`verify-backend` 的 `pytest-report.xml` 落在 `apps/api/`，而 `.gitignore:24` 早就忽略了它 ⇒
跑完不会在共享工作树里留下未跟踪文件（本轮跑完 `git status --porcelain` 只有我自己改的两个文件）。

## 2. 单头断言（S00E.1.3 明写"alembic 单头断言保留"）——五发极性读数，不连库

本机 PG 不可达 ⇒ `verify-backend` 在第①步就停，第②步**轮不到跑**。所以用四个 `.bat` 桩
（`D:/tmp/stubhead/`）把 `alembic_cli()` 换掉，直接判 `assert_single_head()` 本身：

| 输入 | 期望 | 实测返回 |
|---|---|---|
| 桩打出一行 `xxx (head)` | 放行 | `0` ✅ |
| 桩打出两行 `(head)` | 拦（多头事故真形态） | `1` ✅，并打印"verify-backend 停在这里，不放行 pytest" |
| 桩打出零行 `(head)` | 拦（**没头不能被当成一个头**） | `1` ✅ |
| 桩自身 `exit /b 4` | 拦且明写"没跑成" | `1` ✅，输出含 ``alembic heads` 本身失败（rc=4）⇒ 单头断言**没跑成**，不能当通过 |
| 找不到 alembic | `SKIP` 而非过 | `3` ✅ |

真实读数（同一条判据跑真 alembic）：`apps/api/.venv/Scripts/alembic.exe heads` →
`ab1006c2a (head)`，行数 = 1 ⇒ 当前树是单头，与 CI 的 workflow-lint/backend 那两处断言同判。

## 3. `verify-frontend`：一条命令的完整读数 + 连跑两次一致（S00E.2.1 / S00E.3.2 前端半边）

两次都在同一棵树（`878876f`）、同一台机、期间零改动。判定关键行入库为
`verify_frontend_two_runs_extract.txt`；**完整 stdout 各约 1179 行没有入库**（绝大多数是 vitest 的逐用例行，
44 KB × 2 塞进证据目录只会淹掉别的东西），原文留在本机 `D:/tmp/verify_frontend_run{1,2}.txt`，
复跑一条命令即可再生——这一取舍写在 §3.6，不当"已入库"主张。

| 步 | 读数（run1） | 读数（run2） | 一致 |
|---|---|---|---|
| F-10 装前 | `node_modules 存在=True，顶层条目=30` | 同 | ✅ |
| `pnpm install --frozen-lockfile` | rc=0 | rc=0 | ✅ |
| F-10 装后 | `存在=True，顶层条目=30` | 同 | ✅ |
| `tsc --noEmit` | 无输出（0 错误） | 同 | ✅ |
| vitest | `Test Files 49 passed (49)`、`Tests 415 passed (415)`、Duration 40.46s | 同两项、Duration 38.02s | ✅（**只有耗时不同**） |
| `build`（`NEXT_PUBLIC_API_MOCK=false`） | `✓ Compiled successfully in 11.0s`、`Generating static pages (18/18)`、First Load JS shared 103 kB、Middleware 34.2 kB | `✓ Compiled successfully in 7.8s`、18/18 | ✅ |
| 整链 | `rc=0` | `rc=0` | ✅ |

⇒ S00E.3.2「同一命令连跑两次，failed/skipped 数一致」**在前端半边成立**（用例数、文件数、静态页数全等，
只有耗时抖动）；后端半边要有意义地复算必须先有一台能起 PG 的机器 ⇒ 见 §6。

## 3.5 顺带抓到一条与本卡无关但同族的事实（登记台账 §4 P-105）

`verify-frontend` 的 stdout 里有 **39 个 `AggregateError` 块**，内容全是
`connect ECONNREFUSED ::1:3000` / `127.0.0.1:3000`，出现在 **vitest 阶段**（不是 build）。
它们**不影响 rc**（`Tests 415 passed (415)`、整链 rc=0），也就是说：

- 前端单测里至少有一处走了**真实网络**（happy-dom 的文档基址是 `http://localhost:3000`，
  相对路径的 `fetch()` 就拨到了那里），失败被吞；
- 这些用例在"没有后端"的机器上照样绿 ⇒ 它们的判定力**比看起来弱**（拨没拨通没人判）；
- 端口 3000 是 AGENTS.md 明令 BotHot 禁止碰的主平台端口——这里不是"占用"，是**测试期默认基址落在那儿**，
  语义上仍然踩线（一旦本机真有服务在 3000，这批用例的行为会变）。

两次复跑 39 这个数**完全相同**，`@ci ubuntu` 的 `frontend` 日志里也有同形条目（同一条 pattern 计数 60 与 78，
两个 run 之间会抖）⇒ 不是 Windows 特有，也不是我这次改动带来的。
本卡不修（`apps/web/tests/**` 与 `vitest.config.ts` 都不在允许面，且修法要么钉 `environmentOptions.url`
要么补 `fetch` mock，属前端测试线的题）。

## 3.6 证据取舍（写出来免得被读成"全量已入库"）
完整 stdout 各 44 KB、约 1179 行，其中 vitest 逐用例行占绝大多数；入库的是判定用的 20 来行。
取舍标准：**能被下游引用的数字必须在件里**（F-10 两行、`49/415`、`18/18`、耗时、rc、AggregateError 计数），
逐用例的 ✓ 行不入库。复跑命令写在文件头三行里。

## 4. fail-closed 形状（"没装"绝不能长得像"过了"）

```
$ python scripts/entry.py verify-backend
=== verify-backend · 验收面一条命令：探 PG → 单头断言 → upgrade head → pytest 全量（含 -rs 与覆盖率） ===
SKIP(service unavailable) PostgreSQL localhost:5433 不可达 —— 先起依赖服务：`entry.py testenv-up`
（隔离测试栈 PG16@5547 / Redis7@6390，需要 docker；注意 docker/compose.yml 里没有 PG/Redis 服务段，
起它得不到库），端口按 AGENTS.md 固定、不得静默改端口；本步**未执行**，不是通过
→ verify-backend 未通过（rc=3；3 = 工具缺失，不是通过）
entry_rc=3    make verify-backend → make_rc=2      # GNU make 把任何失败折成 2 ⇒ 判据是"同为非 0"

$ python scripts/entry.py testenv-up
SKIP(tool missing) docker —— 这一步**未执行**。…（testenv-up/down 转调 scripts/test-env.sh，
它需要 docker 或 podman；本机两者都无 ⇒ 本步未执行）
entry_rc=3    make testenv-up → make_rc=2
```

顺带更正了一条**会把人引错的既有文案**：`check_services()` 原来让执行者"起 `docker compose -f compose.yml up -d`"，
但现读 `docker/compose.yml` 的 services 段是
`langbot_plugin_runtime / langbot / backend / migrate / scheduler / worker / frontend`——**没有 postgres/redis**，
照那句做仍然连不上库。提示文本改为指向 `entry.py testenv-up`；
"compose.yml 不提供依赖库"这件事本身登记台账 §4 **P-102**（AGENTS.md 端口表里的 5433/6380 由平台侧供给）。

## 5. 卡面三级任务与 Done 判据逐条判定

| 编号 / 判据 | 判定 | 依据 |
|---|---|---|
| S00E.1.2 固定 PG/Redis 起法（compose.test.yml + 健康等待 + 端口冲突自检） | **部分达成 + 一处有意不做**：健康等待与端口拒绝**早就在** `scripts/test-env.sh`（`wait_ready` PG 60s / Redis 30s；`FORBIDDEN_PORTS` 命中即 exit 2），本卡把它的 up/down 接进 `entry.py`/Makefile 成为一条命令；`docker/compose.test.yml` **不新建**（理由见 §6.1，登记 P-103）；"端口被占时点名占用者"这一子句**没有实体**（脚本只拒绝部署端口，不探测 5547/6390 是否被陌生人占住），且本机无 docker ⇒ 连测也测不了 → 判**未实现/未测** | 本文件 §1、§4；`scripts/test-env.sh` 现读 |
| S00E.1.3 `verify-backend` = 先 `alembic upgrade head` 再 pytest，单头断言保留 | **已交付**（顺序与短路形状实跑验证；后端读数本身受环境限制） | §1、§2、§4 |
| S00E.2.1 `verify-frontend` = frozen install → typecheck → vitest，并把 `node_modules` 存在性作为读数输出 | **已交付**（F-10 装前/装后各打一次；两次复跑） | §3 |
| S00E.3.1 👤 裁决"验收由谁的环境跑"并写进 `decision-log.md` 的 D-V4-01 | **不签**：属规划方。本卡只把候选与代价写清楚（§6.2），`decision-log.md` 一字未动 | 卡面字段（👤） |
| S00E.3.2 同一命令连跑两次读数一致 | 前端半边**达成**；后端半边**未测**（无 PG ⇒ `verify-backend` 每次都在第①步 rc=3，那是"没跑"的一致，不是读数的一致） | §3、§4 |
| 验收①：`make verify-backend` 一条命令出全量读数，且 `0 failed`、skip ≤ `SKIP_BASELINE` | **未测（本机）**；同形状的全量读数由 `@ci` 出，run **39894271073** @`878876f`：`2258 passed / 6 skipped / 4 deselected in 211.58s`、`skip 门禁 total_skipped=6 baseline=6 pg_unreachable=0`、`Total coverage: 87.95%`、`✅ 全部模块与全局达标`。⚠ 这条读数**不能**当"`make verify-backend" 的等价证据：CI 那一步直接跑 pytest，没走这四个入口——它证明的是**同一串 flag 的形状**，不是同一条命令 | §0、§7、P-104 |
| 验收②：哨兵用例真实执行 | **达成（取数面 = CI）**：run 39894271073 的 6 条 skip 逐条点名 = `test_chat_sse.py:1130`（LangBot）、`:1208`（LangBot 全链）、`test_env_isolation.py:77`（代理变量对照）、`test_session_store_redis.py:47/71`（Redis）、`test_we_notifications.py:247`（Redis）；哨兵 `test_be02_engine_routing.py::test_short_link_second_ingest_hits_cache_via_url_fallback` **不在其中**，且 `pg_unreachable=0` 同时排除 PG 类 | 该 run 的 backend 日志 SKIPPED 段原文（`-rs` 打的） |
| 验收③：`make verify-frontend` 一条命令完成安装 + typecheck + vitest，读数入 EVD | **达成**（`@win`；CI ubuntu 的 `frontend` job 在同一提交上也绿，两侧同形） | §3、§7 |
| 验收④：端口零越界 `grep -rn '3000' docker scripts` 无 BotHot 服务占用 | **达成**：字面命中 **14**，逐条看全是"BotHot 作为**客户端**指向主平台 3000"（OIDC issuer/gateway 基址）或注释；真正的宿主发布行只有 `"5300:5300"`、`"3300:3300"`、`"3200:3000"`（容器内 3000 是 AGENTS.md 允许的宿主/内部关系），`grep -rnE '3000:[0-9]+' docker/*.yml scripts/*.sh` → **rc=1（零命中）** | 本文件本行命令 |
| 验收⑤：并发安全——默认端口被占时报错点名占用者 | **未实现/未测**（同 S00E.1.2 那一子句） | §0 表第 1 行 |
| 验收⑥：两次复跑读数一致 | 前端达成、后端未测 | §3 |
| 验收⑦：`conventions.md` 三条已写；`decision-log.md` 有 D-V4-01 条目 | **达成**：三条是上一轮 S00E.2.2 写的 §4.3，本卡**新增 §4.4**（四入口 + 三条纪律）；`decision-log.md` 的 D-V4-01 条目本来就在（10-15 签），本卡不改它（S00E.3.1 是👤） | `docs/04_engineering/conventions.md` §4.3/§4.4 |

## 5.5 顺带抓到一条新事实：同一棵树的覆盖率读数会 **±1 行**漂（登记台账 §4 P-104）

为了给验收①取数，把相邻两次 CI（都是**只改文档**的批）的模块覆盖率门输出逐行对了一遍：

| 模块 | run 39891503640 @`8e59749` | run 39894271073 @`878876f` | 差 |
|---|---|---|---|
| `app/services/manifest.py` | 94.78% `218/230` | 95.22% `219/230` | **+1 行** |
| `app/services/subscription.py` | 85.19% `351/412` | 85.19% `351/412` | 0 |
| `app/services/kb.py` | 87.61% `304/347` | 87.61% `304/347` | 0 |
| 四家 provider / `article_identity` | 100 / 99.39 / 100 / 99.42 / 100 | 同 | 0 |
| TOTAL | 88.01% | 87.95% | −0.06pp（就是上面那一行） |

两个提交之间**没有任何 `app/**` 改动**，测试数也完全相同（`2258 passed / 6 skipped / 4 deselected`）。
⇒ `manifest.py` 里至少有一行的覆盖与否**取决于运行时序**（最可能是与并发/事件循环/时间相关的一条分支）。

为什么这条要紧：P-98 已经量过 `subscription.py` 在 CI 上只剩 **1 行余量**（351/412，跌破就是 84.95%）。
如果同样的 ±1 行漂移落在一个贴线的模块上，那道门就会在**没人改代码**的情况下变红——
而读起来像"覆盖率退化了"。本卡不修（不在允许面，也没有定位到具体那一行），
把它登记成 P-104 请规划方裁定：要么定位并消除那条非确定性覆盖，要么给模块门允许 ±1 行的抖动带。

## 6. 有意不做 / 判不了（写清楚，不静默略过）

### 6.1 不新建 `docker/compose.test.yml`（登记 P-103）
卡面输出清单写着"新增 `docker/compose.test.yml`（测试专用，只 PG+Redis）"。现读：
`scripts/test-env.sh` **已经是这件事的唯一实体**——它管镜像（`postgres:16-alpine`/`redis:7-alpine`）、
宿主端口（5547/6390）、D-12 端口拒绝、`pg_isready`/`redis ping` 健康等待、以及 `env` 子命令打印 DSN 行。
再造一份 compose 文件 = 两个真源，而**本机没有 docker ⇒ 两份都不可能实跑验证**。
处置按本卡已有的同一原则（卡面 S00E.1.2 那条端口冲突当时就是"事故规则比卡面有力 ⇒ 按现读改卡，不改脚本"）：
本卡把 `testenv-up/down` 接到既有脚本，**不动** compose 文件，并请规划方裁定是否仍要它。

### 6.2 S00E.3.1 的候选（交回规划方，本卡不代签）
- (A) 固定一台依赖机为验收机：本仓历史上就是这条路（`AIDEANBOT_TEST_PG_DSN` + 隔离 PG@5547），
  代价是"验收机"本身会漂——**本轮就漂了**：10-22 深夜还有一套 5547 可连，10-23 起整面消失，
  三张卡的连库读数因此都退回 `@ci`。
- (B) CI 作为唯一验收面：D-V4-01 实际上已经选了它（正式终判在 `@ci` ubuntu），
  差别只在于 `@win`/依赖机读数的**地位**——目前口径是"只算烟测、不得报 PASS"。
  代价是每张卡都要吃一次 CI 往返（~20 分钟），且本机改不了的那半永远改不了。
- 本卡的实测倾向：B 已经把验收这件事做实了，缺的不是裁决而是**把"依赖机读数何时可以升级成结论"写清**。

### 6.3 后端半边仍判不了的清单（换到有 docker/PG 的机器上原地可复跑）
`testenv-up` 起栈、`verify-backend` 出 `failed/passed/skipped` + 覆盖率、junit 入 EVD、
S00E.3.2 的后端复跑、以及"端口被占时点名占用者"那条子句的实现与验证。

## 7. 三绿（本批验收锚）

- **STEP-00X 余项批（`878876f`）三条 attempt 1 全绿**（这同时也是 00X 补记 §7 承诺"推进 00E 之前读取"那一格）：
  `CI` run **39894271073** success（`2258 passed / 6 skipped / 4 deselected in 211.58s`、
  `Total coverage: 87.95%`、`skip 门禁 total_skipped=6 baseline=6 pg_unreachable=0`、`✅ 全部模块与全局达标`）、
  `CI-Windows` run **39894271024** success、`Security` run **39894271026** success。
  取数时刻分别为：本卡开工时 CI/Security 已绿而 Windows in_progress，收口前复读到 Windows success。
- 本批（00E）自己的三条运行在 push 后读取，写在 `docs/任务规划V0.17.0/07-执行过程记录.md` 行 38 末尾；
  推进 STEP-12（队列⑯，发布对账）之前必须三绿（队列纪律）。
- ⚠ 一张本批**不会变红但要看懂**的账：00E 只动 `scripts/entry.py` + `Makefile` + 文档，
  **没有新增连库用例** ⇒ `SKIP_BASELINE_WIN` 不该动（仍 666）。如果 CI-Windows 因为这条变红，
  那说明有别的批把用例带进来了，得按 `cross-platform.md` §8 重测构成再抬，而不是顺手加数。

## 8. 所有权申报（越界一处，主动写）

卡面允许：`scripts/test-env.sh`、`docker/compose.test.yml`（新）、`Makefile`（仅新增 `testenv-*`/`verify-*`）、
`conventions.md`、`decision-log.md`（仅 D-V4-01 一行）、EVD-V4-00E。

| 路径 | 是否允许面内 | 说明 |
|---|---|---|
| `Makefile` | ✅ | 只新增 4 个薄转调目标，未动任何既有目标体 |
| `docs/04_engineering/conventions.md` | ✅ | 新增 §4.4（§4.3 是上一轮写的，本轮未改其内容） |
| `docs/06_validation/evidence/EVD-V4-00E/*` | ✅ | 本补记 + 两份 verify-frontend 原始 stdout |
| **`scripts/entry.py`** | ❌ **越界，主动申报** | 不在 00E 允许清单里。为什么必须动它：STEP-00X 之后**所有命令实体的唯一源就是 entry.py**，`check_entry_parity.py` 是常驻门——只在 Makefile 里加四个目标会得到一个**必然红**的门（Makefile 目标解析不到实体）。这与 STEP-06 那次为 `coverage-gate` 同理由的申报是同一族（台账 P-87/P-95 记过）。动了什么：新增 3 个函数（`assert_single_head` / `report_node_modules` / `run_test_env`）+ `alembic_cli` 辅助 + 4 条 `add(...)` 注册 + 一处不可达提示文案更正；**未改任何既有任务的行为**。 |
| `docker/compose.test.yml` | ✅ 允许但**有意不建** | 理由 §6.1，登记 P-103 |
| `scripts/test-env.sh` | ✅ 允许但**未改** | 它已覆盖 S00E.1.2 的健康等待与端口拒绝；本机无 docker ⇒ 任何改动都无法验证，盲改一个 D-12 守卫脚本的风险高于收益 |
| `docs/03_solution/decisions/decision-log.md` | ✅ 允许（仅 D-V4-01 一行）但**未改** | S00E.3.1 是 👤 项，执行方不代签裁决 |
