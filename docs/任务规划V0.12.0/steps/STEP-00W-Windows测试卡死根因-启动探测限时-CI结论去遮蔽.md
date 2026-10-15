# STEP-00W Windows 测试卡死根因 + 启动探测限时 + CI 结论去遮蔽（V0.12.0 新增）

| 字段 | 值 |
|---|---|
| 归属-切片 | S-M0 前提固定 |
| 归属-需求 | M-9（启动不得因依赖不可达无限挂起，本版新增）、M-10（Win10 一等开发平台，D-V4-01 派生）、M-6（主干绿，口径按 D-V7-01） |
| 归属-方案 | D-V7-01（拆工作流）、D-V7-02（逐用例超时 + faulthandler）、D-V7-04（探测限时 3s/5s）；U-20 根因假设 H1 |
| 里程碑 | M0（阻塞 00X S00X.4.2、00E、RV 的 @ci 读数） |
| 执行者 | 规划方（跨 API + Guard 两列所有权，执行期间两列对其他 Agent 冻结，见 04 §5） |
| 档位 | opus　理由：同时改启动路径、CI 编排和测试夹具，判断错一处会让正式验收面读数失真；不可逆面在 CI 语义 |
| 规模 | 中（≈1.0 人日；8 个三级任务，单个均 < 2h） |
| 依赖 | Depends on：无　Blocks：00X(S00X.4.2)、00E、RV |
| 基线 | main@3a67e96 |

## 目标（可验证的一句话）
`import app.main` 在数据库黑洞地址下 < 5s 返回；`CI` 工作流结论只由 ubuntu 五 job 决定且为 success；`CI-Windows` 工作流里任何卡住的用例以带栈的 failed 结束而不是被取消，并最终 success。

## 输入
- 文档：`docs/任务规划V0.12.0/01-事实基线与进度.md` F-02～F-06、X-3；`02` §5/§6；`03` §1
- 证据：`evidence/3a67e96/win_stall_rootcause_probe.txt`、`ci_run_38707720244_jobs.json`；`docs/06_validation/evidence/EVD-V5-00X/win_dev_platform_readings.md` §2/§5/§8
- 契约：不涉（不改任何响应形状）
- 前置状态：D-V7-01～04 已在 03 §1 代选；本卡 S00W.2.3 负责签入 decision-log

## 输出（文件）
- 改：`apps/api/app/main.py`（`_assert_schema_current` 探测限时）、`apps/api/app/db.py`（新增可选 `connect_args` 参数，默认行为不变）
- 改：`.github/workflows/ci.yml`（移出 windows-dev job）；新：`.github/workflows/ci-windows.yml`
- 改：`apps/api/pyproject.toml`（dev 依赖加 `pytest-timeout`）
- 新：`apps/api/tests/test_startup_probe_timeout.py`
- 改：`docs/03_solution/decisions/decision-log.md`（追加 D-V7-01～04 行，不改历史行）
- 证据：`docs/06_validation/evidence/EVD-V7-00W/`

## Execution Steps

### S00W.1 根因闭合（先证实，再改）
1. [ ] **S00W.1.1** `@ci` 在 windows job 的 pytest 命令加 `-o faulthandler_timeout=120 -x tests/test_auth.py`（临时分支 `diag/00w`，不合入 main），把卡住时的全线程栈写进日志；用 GitHub REST 读 job 结论，日志正文由有权限的会话下载存入 EVD
   - S00W.1.1.1 判据：栈中出现 `_assert_schema_current` / `read_current_version_async` / psycopg connect ⇒ H1 确认；否则进入 S00W.1.3
2. [ ] **S00W.1.2** `@linux` 把 `win_stall_rootcause_probe.txt` §B 的黑洞探针写成回归用例的期望（见 S00W.3.3），先在 3a67e96 上跑出**红**（证明用例能抓到缺陷）
3. [ ] **S00W.1.3**（仅 H1 被否证时）`@ci` 二分：test_auth.py 内按用例 `-k` 二分 + `--collect-only` 与运行分离，定位到单个用例或 fixture；结论写 EVD，本卡后续步骤据此改写后再继续（熔断：二分 2 轮无结论 ⇒ 标 blocked 上报）

### S00W.2 CI 结论去遮蔽
4. [ ] **S00W.2.1** windows-dev 整段移到 `.github/workflows/ci-windows.yml`（name: `CI-Windows`，触发条件与 ci.yml 一致）；`ci.yml` 删除该 job，ubuntu 五 job 一行不改
5. [ ] **S00W.2.2** ci-windows 的 pytest 步改为 `python -m pytest tests/ -q --no-header -o faulthandler_timeout=120 --timeout=300 --timeout-method=thread --junitxml=pytest-report-win.xml`；pyproject dev 依赖加 `pytest-timeout`；job `timeout-minutes` 保留 35 作兜底
6. [ ] **S00W.2.3** decision-log 追加 D-V7-01～04 四行（签字列："用户授权代选 / 2026-10-15 / 所选方案"），同步改 `docs/04_engineering/cross-platform.md` 的"多平台门 = CI-Windows 工作流结论"一句

### S00W.3 修复与回归
7. [ ] **S00W.3.1** `_assert_schema_current` 的一次性引擎传 `connect_args={"connect_timeout": 3}`，`asyncio.run(asyncio.wait_for(_probe_and_dispose(), 5))`；超时归入现有"不可判定"分支（开发告警、生产维持现有放行语义，U-22 不改）
   - S00W.3.1.1 `create_engine_and_session` 增加可选 `connect_args` 参数，**默认 None 时行为与现在完全一致**（不改业务连接池语义）
8. [ ] **S00W.3.2 + S00W.3.3** 新增 `tests/test_startup_probe_timeout.py`：子进程 `DATABASE_URL=<黑洞地址>` 执行 `import app.main`，断言 rc=0 且耗时 < 8s（留 CI 抖动余量）；若 `@ci` windows 全量仍慢（单文件 > 60s），测试侧在 conftest 为非连库用例设置立即失败的 `DATABASE_URL`（以读数决定，二选一记 EVD）

## 验收标准（全部标机器）
- [ ] `@linux` `DATABASE_URL=postgresql+psycopg://x@10.255.255.1:5432/x timeout 10 python -c "import app.main"` rc=0 且 < 5s（改前 rc=124，见证据 §B）
- [ ] `@linux` 新用例在 3a67e96 上红、在本卡提交上绿（两次读数入 EVD）
- [ ] `@ci` `CI` 工作流（仅 ubuntu 五 job）conclusion = success，run id + head_sha 原始响应存证
- [ ] `@ci` `CI-Windows` 工作流 conclusion = success；若仍失败，结论必须是 failure 且日志含 faulthandler 栈（不得是 cancelled）
- [ ] `@ci` ubuntu backend job 的 passed 数 ≥ 1058、failed = 0（与 F-01 对齐，不得因本卡减少用例）
- [ ] `git diff --stat` 只含"输出"一节列出的文件

## 验证命令
```bash
# @linux
cd apps/api && DATABASE_URL=postgresql+psycopg://x@10.255.255.1:5432/x timeout 10 python -c "import app.main"; echo rc=$?
cd apps/api && python -m pytest tests/test_startup_probe_timeout.py -q
cd apps/api && AIDEANBOT_TEST_PG_DSN=<dsn> python -m pytest tests/ -q
# @ci（D-V6-02：原始响应存证）
curl -s "https://api.github.com/repos/aideanew/BotHot/actions/runs?branch=main&per_page=6" > docs/06_validation/evidence/EVD-V7-00W/runs.json
curl -s "https://api.github.com/repos/aideanew/BotHot/actions/runs/<run_id>/jobs" > docs/06_validation/evidence/EVD-V7-00W/jobs_<run_id>.json
```

## 证据路径
`docs/06_validation/evidence/EVD-V7-00W/`

## 允许修改
`apps/api/app/main.py`（仅 `_assert_schema_current`）、`apps/api/app/db.py`（仅 `create_engine_and_session` 签名）、`.github/workflows/ci.yml`（仅删除 windows-dev job）、`.github/workflows/ci-windows.yml`（新）、`apps/api/pyproject.toml`（仅 dev 依赖）、`apps/api/tests/test_startup_probe_timeout.py`（新）、`apps/api/tests/conftest.py`（仅 S00W.3.3 二选一分支需要时）、`docs/03_solution/decisions/decision-log.md`（仅追加）、`docs/04_engineering/cross-platform.md`（一句）、`docs/06_validation/evidence/EVD-V7-00W/**`

## 禁止修改
`packages/contracts/**`、`docs/任务规划V0.12.0/contracts/**`、`apps/api/alembic/**`（不占迁移号）、`apps/web/**`、ubuntu 五 job 的任何一行、`docs/06_validation/evidence/EVD-V2-02/**`、`docs/任务规划V0.5.0/**`、其他测试文件

## 依赖与阻塞
- Depends on：无　Blocks：00X(S00X.4.2)、00E、RV
- 阻塞条件：① S00W.1.1 拿不到日志正文且 H1 无法闭合 ⇒ 仍可做 S00W.2/S00W.3（它们对 H1 真假都成立），但验收第 4 条只能写 failure+栈；② 修复需要改变生产"不可判定时放行"语义 ⇒ 停，属 U-22，另立 ADR；③ 与并发会话同时改 ci.yml ⇒ 等对方提交后快进再改，不覆盖

## 建议档位 / 升级条件 / 预估规模
opus（理由见表头）；升级：S00W.1.3 二分两轮无结论 ⇒ 升 fable 做一次全局仲裁（每切片 ≤1 券）；规模：中，≈1.0 人日，每个三级任务 < 2h。
