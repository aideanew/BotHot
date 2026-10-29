# EVD-V22-63 STEP-63 发布 v1.1.5：读数与判据

卡：[docs/任务规划V0.22.0/steps/STEP-63-发布v1.1.5.md](../../../任务规划V0.22.0/steps/STEP-63-发布v1.1.5.md)
日期：2026-10-29｜允许面：`CHANGELOG.md`、`AGENTS.md` 版本块、卡面、卡表、07、本目录｜**禁止面：一切代码与测试**

## 0 区间对账（发布段的唯一来源）

| 项 | 现读 | 命令 |
|---|---|---|
| 区间提交数 | 63（发布批自身 +1 ⇒ tag 指向的提交上是 64） | `git log --oneline v1.1.4..HEAD \| wc -l` |
| 主语分布 | `feat` 10 / `fix` 12 / `docs(...)` 38（内含 1 条 `docs+fix(...)` 合批）/ `chore` 3 | `git log --format=%s v1.1.4..HEAD \| sed -E 's/^([a-z]+)(\(.*\))?:.*/\1/' \| sort \| uniq -c` |
| `apps/api/app/**` 改动面 | **1 个文件**：`apps/api/app/contracts/shapes.py`（+10/−5） | `git diff --stat v1.1.4..HEAD -- apps/api/app` |
| 数据库迁移 | **0**（该路径区间内无 diff；目录实名是 `apps/api/alembic/versions`，本仓**没有** `apps/api/migrations`） | `git diff --stat v1.1.4..HEAD -- apps/api/alembic` |
| 前端非 e2e 改动面 | 20 个文件（12 个源码 + 8 个测试/配置） | `git diff --stat v1.1.4..HEAD -- apps/web ':!apps/web/e2e'` |
| 契约包改动面 | 5 个路径（`identity/dto.ts` 新增、`ux/states.ts` 新增、`index.ts`、`shapes.schema.json`、`identity/.gitkeep`） | `git diff --stat v1.1.4..HEAD -- packages/contracts` |

10 个 `feat` 主语逐个 `git log -1` 复核过：`a31dc42`、`0e53199`、`31e1977`、`4160b81`、`6da2a0c`、
`c7c0a07`、`5b1a78d`、`e675a26`、`8614365`、`ca9ba70`（`643440b` 是 `fix`，同属 STEP-59 那条链）；
发布段共出现 23 个唯一短 hash——**条目「来源」位 20 个**（`7c15264`、`f536398`、`3115532` 这 3 个在导语与
正文里，不是条目来源），逐个 `git log -1` 全部存在、且 `git rev-list --count <sha> ^v1.1.4` 全 > 0
⇒ 没有一条引用落在区间外。

## 1 判据① 本机全量一次（04 附录 B，本版唯一一次）

环境：隔离 PG16.15 @5547（数据目录 `%USERPROFILE%\pg16-5547\pgdist\data`），
DSN 只经环境变量 `AIDEANBOT_TEST_PG_DSN` 传入、**不入仓也不在本文件复述**（本仓有 gitleaks 的
「带凭据的 URL 形状」判据，写成形即阻断——见本文件 §7），
`PYTHONUTF8=1`（口径见 §1.2），alembic head `ab1006c2a`。

### 1.1 逐门读数（`counts` 与 CI 三绿 head 逐字相同）

| # | 门 | 命令（CI 原样） | 读数 | rc |
|---|---|---|---|---|
| 1 | ruff | `ruff check app tests ../../scripts` | `All checks passed!` | 0 |
| 2 | mypy | `mypy app ../../scripts` | `Success: no issues found in 137 source files` | 0 |
| 3 | 单头 | `alembic heads` | `ab1006c2a (head)` | 0 |
| 4 | 迁移往返 ①极性 | `alembic downgrade -1` → `alembic current` | `before=[ab1006c2a (head)] after_downgrade=[ab1006c4a]` | 0 |
| 5 | 迁移往返 ②形状 | `migration_roundtrip_probe.py --expect=absent` | `revision=ab1006c2a expect=absent 实得列=[] 索引=[]` | 0 |
| 6 | 迁移往返 ③终态 | `alembic upgrade head` + `--expect=present` | 6 列（`created_at`/`id`/`kind`/`origin`/`source_id`/`value`）+ 3 索引（`ix_source_identifiers_kind`/`ix_source_identifiers_source_id`/`uq_source_identifier_kind_value`），终态等于起点 | 0 |
| 7 | 契约漂移 | `gen_contracts.py --check` | 6 份 schema 全部 `[ok] ... 幂等一致` | 0 |
| 8 | 文档一致性 | `check_docs_consistency.py` | `找到 23 个路径引用`、`语料 15 份，根路径文件锚 139 处`、`含键值引用的行 7 行`、`[ok] 文档一致性检查通过` | 0 |
| 9 | 后端全量 | `pytest tests/ -q -rs --junitxml=pytest-report.xml --cov=app --cov-report=term-missing --cov-report=json:coverage.json --cov-fail-under=75` | `2503 passed, 6 skipped, 4 deselected, 2 warnings in 1179.62s (0:19:39)`、`Required test coverage of 75% reached. Total coverage: 88.90%` | 0 |
| 10 | skip 门 | ci.yml 的内联脚本（本机按行照抄成临时脚本执行，不进证据包） | `total_skipped=6 baseline=6 pg_unreachable=0` + `✅ skip 门禁通过` | 0 |
| 11 | 模块覆盖率门 | `check_module_coverage.py --json coverage.json` | `TOTAL 88.90% ≥ 79.0%` + `✅ 全部模块与全局达标` | 0 |
| 12 | 前端 typecheck | `pnpm run typecheck` | 无输出（tsc 通过） | 0 |
| 13 | 契约 tsc | `pnpm exec tsc --noEmit -p ../../packages/contracts/tsconfig.json` | 无输出 | 0 |
| 14 | 前端 tsc | `pnpm exec tsc --noEmit` | 无输出 | 0 |
| 15 | 前端单测 | `pnpm run test:unit -- --retry=2` | `Test Files 57 passed (57)` / `Tests 452 passed (452)` | 0 |
| 16 | 生产 build | `MOCK=false next build` | 路由表完整（`ƒ Middleware 34.2 kB`），无错误 | 0 |
| 17 | 演示态 build | `NEXT_PUBLIC_API_MOCK=true next build` | 无错误，`grep -c "Failed to proxy"` = **0** | 0 |
| 18 | 演示态 e2e | `PORT=3456 pnpm run test:e2e` | `Running 43 tests using 1 worker` → `12 skipped` / `31 passed (1.6m)` | 0 |

判据①「0 failed 且 skip 数等于基线」：**满足**——`0 failed`，`skipped=6` 与 `SKIP_BASELINE=6` 逐字相等，
`pg_unreachable=0`（连库用例真实执行，不是跳过后假装通过）。

### 1.2 ⚠ 本机口径：默认码页下同一棵树是 3 failed（不是交付缺陷）

第一次全量按默认环境（**未**设 `PYTHONUTF8`）跑，读数 `3 failed, 2500 passed, 6 skipped, 4 deselected
in 1272.21s (0:21:12)`。三条红同一形状：

| 用例 | 失败点 | 根因 |
|---|---|---|
| `test_health_probe_bounded.py::test_health_and_ready_return_within_bound_under_blackhole_dependencies` | `proc.stdout.splitlines()` 上 `AttributeError: 'NoneType'` | 子进程带 `-X utf8` 输出 UTF-8，父进程 `subprocess.run(text=True)` 用本机码页 **gbk** 解码 ⇒ reader 线程 `UnicodeDecodeError` ⇒ `stdout` 回到 `None` |
| `test_health_probe_bounded.py::test_child_wall_clock_is_measured_not_assumed` | 同上 | 同上 |
| `test_security_scan_helper.py::test_helper_is_parseable_and_has_the_two_attempt_contract` | `"--report" in proc.stdout` 上 `TypeError: argument of type 'NoneType' is not iterable` | 同上（子进程 `--help` 输出含 gbk 编不出的字节） |

因果对照（不是猜）：只跑这两个文件、**不加任何编码前缀** ⇒ `3 failed, 15 passed`；
同一条命令加 `PYTHONUTF8=1` ⇒ `18 passed in 29.63s`。父进程 `sys.stdout.encoding` 现读 `gbk`。

为什么 CI 抓不到：Linux job 是 UTF-8；CI-Windows 跑在 cp1252 码页上，UTF-8 字节逐字节都能被 cp1252 解出来
（结果串是乱码，但 `stdout` 非 `None`），所以这条缺陷只在 CJK 码页的 Windows 上现形。
修法是在三处 `subprocess.run(..., text=True)` 补 `encoding="utf-8"`——动的是测试文件、不在本卡允许面，
按熔断纪律**不在发版批里顺手改**，登台账 **P-169**（附上两条对照读数与失败名单）。

### 1.3 与 CI 基线的差

| 项 | CI（`6e78dff`） | 本机（发布批） | 差 |
|---|---|---|---|
| 通过/跳过/摘除 | 2503 / 6 / 4 | 2503 / 6 / 4 | 无 |
| 覆盖率 | 88.93% | 88.90% | 0.03pt，同族抖动（88.89～88.94 都出现过，见 AGENTS.md 的覆盖率口径） |
| 前端单测 | 57 文件 / 452 | 57 文件 / 452 | 无 |
| 演示态 e2e | 43 条 / 31 passed / 12 skipped | 43 条 / 31 passed / 12 skipped | 无 |

## 2 治理门（CI backend job 的末三步，本机照跑）

| 门 | 读数 | rc |
|---|---|---|
| `guards.py rounds-check` | `范围 origin/main..HEAD 共 4 个提交，阈值 ≤2 轮` + `✅ 范围内无卡越过轮次上限` | 0 |
| `guards.py evidence-check` | `gitleaks ... 515 commits scanned` / `no leaks found` + `✅ evidence-check 全部通过（前置两道门 + stdlib 证据 + 真实工具两步）` | 0 |
| `guards.py guard-ci-secret-mask` | `3 个工作流 / 66 个 run 步，其中 8 行写 $GITHUB_ENV/$GITHUB_OUTPUT` + `✅` | 0 |

`evidence-check` 与 `guard-ci-secret-mask` 按 CI 口径跑：`AIDEANBOT_TEST_PG_DSN=""`、`DATABASE_URL=""`、
`GUARD_GITLEAKS_COVERED=1`（gitleaks 权威步在 Security 工作流，但本机装了 gitleaks ⇒ 真扫了 515 个提交）。
本机 `origin/main` 停在 `ca9ba70`（推送走内联 token URL，不改本地远端引用），所以 `rounds-check` 的范围是
`ca9ba70..3115532` 这 4 个提交——与 CI 在同等提交上的范围不同，读数只作「本批没越轮次」的旁证。

## 3 判据② 发版提交三绿（attempt 1）

推送后回填：见 §5。

## 4 判据③ tag / Release / 对账

推送后回填：见 §5。

## 5 推送后回填

_（待推送后按 `git/ref`、`git/tags`、`releases/tags/v1.1.5` 三处独立读数填写。）_

## 6 保留项与残留

| 项 | 状态 | 归属 |
|---|---|---|
| `e2e-real` 的 `continue-on-error` 摘除 | **不在本版做**（允许面不含 `ci.yml`）；前件已在 `d6d67fc`/`f536398`/`6e78dff` 三连绿上成立 | 台账 P-168（STEP-62 已收口，交规划方开卡） |
| 三处 `subprocess.run(text=True)` 缺 `encoding="utf-8"` | 本机 cp936 下三条用例必红；CI 两平台都碰不到 | 台账 P-169（修的是测试文件，不在发版卡允许面） |
| `ci.yml:542` 那句「摘除归 STEP-62」的过期注释 | 与判据② 的决策有偏差 | 并入 P-168 那一卡 |
| 覆盖率读数不可当精确判据 | 本区间已归档 88.93 / 88.94，本机 88.90 | 既有口径（台账 P-104） |

## 7 本批自打的两道门禁（发版批自己就是被测对象）

发布批推上去的第一个头 `698b346` 同时打红 **CI** 与 **Security**。根因是同一处：
`docs/06_validation/evidence/EVD-V22-63/s63_readings.md` 的原 §1 把本机隔离库 DSN 写成
「账号 + 掩码口令 + `@` + 主机」的形式。**掩码不等于去形**——本仓 `.gitleaks.toml` 的规则 1
判的是邻接形状而非词表，所以口令段写成 `***` 一样命中。

| 门禁 | 取材面 | 原文读数 | 出路 |
|---|---|---|---|
| CI `backend` → Governance gates | **HEAD 内容**（本批 9 个变更路径） | `敏感形门（STEP-00P S00P.1.1）：待检 9 个路径（取材面=head），实扫 9，跳过 0，HIGH 1，ALLOWED 放行 0` / `HIGH dsn-embedded-password docs/06_validation/evidence/EVD-V22-63/s63_readings.md:25` / `rounds-check rc=0 / evidence-check rc=1` | `ded5089` 改文档：该行只写「DSN 经环境变量传入、不复述形状」⇒ 头扫自愈 |
| Security `汇总门禁` | **git 模式全历史**（`517 commits scanned`） | `gitleaks：🔴 检出 1 处明文密钥` / `🔴 connection-string-embedded-password \| docs/06_validation/evidence/EVD-V22-63/s63_readings.md:25 \| commit=698b346a` / `阻断 1 项 / 告警 3 项` | 工作树去形**不消灭历史 blob**，D-V4-04 禁止重写历史 ⇒ 依 D-12 逐指纹登记 `.gitleaksignore`（用户 2026-10-29 授权；该文件属 STEP-00S 归属面，不在发版卡允许面内） |

指纹由本机真实 gitleaks 8.21.2（与 `security.yml` 的钉版同版）现取，并按 D-12 纪律做了登记前后对照跑：

```
登记前：517 commits scanned / leaks found: 1
        698b346a…:docs/06_validation/evidence/EVD-V22-63/s63_readings.md:connection-string-embedded-password:25
登记后：517 commits scanned / no leaks found（rc=0）
```

对照跑的命令与 §11/§12 的先例一致：`GIT_ATTR_NOSYSTEM=1 gitleaks detect --source . --config .gitleaks.toml`
（不加该变量时 Git for Windows 的 system 级 `docx` textconv 会让整次扫描失败）。
登记条目只放行**那一条指纹**，规则本体一字未改，也没有任何整文件/整目录/整 commit 豁免。

顺带修掉独立复查助手挑出的一处空转证据：§0 的「零迁移」原本写成 `git diff --stat … -- apps/api/migrations`，
而**本仓没有 `apps/api/migrations` 这个目录**（实名 `apps/api/alembic`）⇒ 结论真、取证路径不存在。
现按真实路径复算：`git diff --stat v1.1.4..HEAD -- apps/api/alembic` = 空输出 ⇒ 零迁移成立。

独立复查助手（只读，18 次工具调用）对本批四条判据的结论：**面内性 PASS / 数字可核 PASS / 过度主张 PASS /
markdown 完整性 PASS，必须修的 FAIL 无**；其 nits 共 4 条，本批已修其中 3 条（上面的取证路径、
「发布段 20 个短 hash」改为「条目来源位 20 个 + 导语 3 个 = 23 个唯一 hash」、「唯一一次全量」补成
「唯一一次发版口径，同树两次、差量是码页」），第 4 条是 commit message 措辞、不改历史。

