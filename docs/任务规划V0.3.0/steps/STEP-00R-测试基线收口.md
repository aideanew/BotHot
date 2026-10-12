---
id: STEP-00R
title: 测试基线收口（STEP-00 残项 + 代理根因）
baseline: main@4afaedd
tier: sonnect
size: 中（约 0.5–1 人日；S0R.3.1 需有 docker 的执行者另计）
---

# STEP-00R：测试基线收口（STEP-00 残项 + 代理根因）

## 归属
- 所属切片：S0 步行骨架·测试可信（全量连库 failed=0，且与运行环境的代理设置无关）
- 来源需求：M-06、I-01、I-08；STEP-00 DoD
- 来源方案：01 §3.1（被推翻结论）；EVD-V2-00 §8 #2/#4/#5/#6/#7

## 目标
在「存在环境代理」与「无代理」两种环境下，隔离 PG 全量 pytest 均为 failed=0，且 5 条 skip 只属 LangBot/Redis 类。

## 输入
- evidence/proxy_rootcause_4afaedd.txt
- evidence/pytest_full_pg_4afaedd.txt
- docs/06_validation/evidence/EVD-V2-00/README.md §8
- apps/api/tests/conftest.py（4afaedd）
- 前置状态：main@4afaedd

## 输出（新增/修改的文件）
- apps/api/tests/conftest.py（增 autouse 代理隔离夹具）
- apps/api/tests/fixtures/net.py（新：REFUSED_HTTP_URL 常量）
- apps/api/tests/test_env_isolation.py（新）
- apps/api/tests/test_alerting_drill.py / test_bots_logs_filter.py / test_wb_push_hardening.py / test_w3_push_scheduler.py（仅 webhook_url 常量）
- apps/api/tests/test_chat_sse.py（仅 :1208/:1272 守卫）
- apps/api/tests/test_r48_admin_jobs.py:285、test_scheduler.py:663（仅注释）
- Makefile（新增 evidence-check 目标）
- docs/06_validation/evidence/EVD-V2-00R/**（新）
- docs/任务规划V0.2.0/steps/STEP-00-测试环境与基线.md（追加更正段，不改原文）

## Execution Steps（三级原子任务 → 四级执行步骤）

标记：🔴 先红（失败测试/反证）｜🛠 实现｜✅ 验证｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决。每个原子任务单独可验收。

### S0R.1 代理隔离（根因修复）

#### S0R.1.1 🔴

**交付**：新增 `tests/test_env_isolation.py`：①断言测试进程内 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY`（大小写）均不存在且 `NO_PROXY` 含 `127.0.0.1`；②`WebhookPushProvider().push(PushMessage(message='x', webhook_url=REFUSED_HTTP_URL))` 返回 `delivered=False, retryable=True`

**执行步骤**：
1. [ ] 写两条用例，不改 conftest
2. [ ] 在有代理环境运行，确认两条均 FAIL（改前红）

**验收命令**：
```bash
cd apps/api && HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 uv run pytest tests/test_env_isolation.py -q   # 改前期望 2 failed
```

#### S0R.1.2 🛠

**交付**：`conftest.py` 增 `@pytest.fixture(autouse=True, scope='session')` 级等价实现（session 级用 `pytest.MonkeyPatch.context()`）：删除 6 个代理变量、设置 `NO_PROXY=127.0.0.1,localhost,::1`；不新增 marker（避免改 pyproject）；若将来有用例必须走真实代理，另开卡

**执行步骤**：
1. [ ] 实现夹具；放在 DSN 解析之后、不影响 `_broadcast` 语义
2. [ ] 跑 S0R.1.1 转绿
3. [ ] 跑 prove_dsn_policy.py 确认 20/20 仍 PASS

**验收命令**：
```bash
cd apps/api && HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 uv run pytest tests/test_env_isolation.py -q && python ../../docs/06_validation/evidence/EVD-V2-00/prove_dsn_policy.py
```

#### S0R.1.3 ✅

**交付**：双环境全量复跑：有代理 / 无代理各一次，结果一致且 failed=0

**执行步骤**：
1. [ ] `test-env.sh up`（或等价自起 PG16@5547）
2. [ ] 两次全量，junit 分别入档
3. [ ] diff 两份 junit 的用例结论

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run alembic upgrade head && HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 uv run pytest tests -q -rfs --junitxml=../../docs/06_validation/evidence/EVD-V2-00R/junit_proxy.xml && env -u HTTP_PROXY -u HTTPS_PROXY uv run pytest tests -q -rfs --junitxml=../../docs/06_validation/evidence/EVD-V2-00R/junit_noproxy.xml
```

### S0R.2 同形脆弱点收口

#### S0R.2.1 🛠

**交付**：新建 `tests/fixtures/net.py`：`REFUSED_HTTP_URL = 'http://127.0.0.1:1/bothot-hook-no-listener'`；4 个文件的 webhook_url 改引用此常量（含 test_w3 的 `_REFUSED_WEBHOOK_URL`，统一一处）

**执行步骤**：
1. [ ] 新建常量模块
2. [ ] 替换 4 处
3. [ ] grep 断言仓内 tests 无 `localhost:9999`

**验收命令**：
```bash
! grep -rn --include=*.py 'localhost:9999' apps/api/tests && cd apps/api && uv run pytest tests/test_alerting_drill.py tests/test_bots_logs_filter.py tests/test_wb_push_hardening.py tests/test_w3_push_scheduler.py -q
```

#### S0R.2.2 🔴🛠

**交付**：`test_chat_sse.py:1208/:1272`：在 `create_async_engine(PG_URL)` 前加 `if _PG_URL_SOURCE == 'unset': pytest.skip(SKIP_UNSET_REASON)`（从 conftest 导入），把报错改为体面 skip

**执行步骤**：
1. [ ] 导入 `_PG_URL_SOURCE, SKIP_UNSET_REASON`
2. [ ] 两处加守卫
3. [ ] 用 monkeypatch 伪造 LangBot 可达的单测证明 skip 而非 error

**验收命令**：
```bash
cd apps/api && unset AIDEANBOT_TEST_PG_DSN && uv run pytest tests/test_chat_sse.py -q -rs | grep -c '未设置\|不可达'
```

#### S0R.2.3 📄

**交付**：清陈旧注释：`test_r48_admin_jobs.py:285`、`test_scheduler.py:663` 的「见 conftest 警告」改为「见 conftest SKIP_UNSET_REASON」

**执行步骤**：
1. [ ] 改两行注释

**验收命令**：
```bash
! grep -rn 'conftest 警告' apps/api/tests
```

### S0R.3 环境脚本与基线入档

#### S0R.3.1 👤🗄

**交付**：有 docker 或本地 PG/Redis 二进制的执行者实跑 `test-env.sh up/down`（STEP-00 未跑分支）

**执行步骤**：
1. [ ] `bash scripts/test-env.sh up`
2. [ ] `psql … -c 'select 1'`
3. [ ] `bash scripts/test-env.sh down` 后端口释放

**验收命令**：
```bash
bash scripts/test-env.sh up && eval "$(bash scripts/test-env.sh env)" && psql "${AIDEANBOT_TEST_PG_DSN/+psycopg/}" -c "select 1" && bash scripts/test-env.sh down
```

#### S0R.3.2 ✅

**交付**：连库全量 + 覆盖率 + junit 入档，替换 AGENTS 中旧基线的输入（AGENTS 本身由 STEP-12 改）

**执行步骤**：
1. [ ] 跑全量 `--cov=app --cov-report=json`
2. [ ] 把 coverage.json 与 junit 存 EVD-V2-00R
3. [ ] README 记录命令、sha、数字

**验收命令**：
```bash
eval "$(bash scripts/test-env.sh env)" && cd apps/api && uv run pytest tests -q -rfs --cov=app --cov-report=json:../../docs/06_validation/evidence/EVD-V2-00R/coverage.json
```

#### S0R.3.3 📄

**交付**：（D-11 授权后）`ci.yml:28-32` 注释更正为两级解析 + 拒连广播

**执行步骤**：
1. [ ] 改注释，不改行为

**验收命令**：
```bash
! grep -n 'conftest 默认 DSN' .github/workflows/ci.yml
```

### S0R.4 证据脚本进门禁

#### S0R.4.1 🛠

**交付**：`Makefile` 新增 `evidence-check`：依次运行 `prove_dsn_policy.py`、`prove_dsn_policy.py --self-test`、`prove_provider_shapes.py`、`g24_static_check.py --self-test`，任一非 0 即失败；D-11 授权则 ci.yml 增同名 job（stdlib-only，无需装依赖）

**执行步骤**：
1. [ ] 写 Makefile 目标
2. [ ] 本地 `make evidence-check` rc=0
3. [ ] （授权后）CI job

**验收命令**：
```bash
make evidence-check
```

### S0R.5 回写更正

#### S0R.5.1 📄

**交付**：在 STEP-00 卡末尾追加「2026-10-xx 复核更正」：S0.2.1 根因为环境代理（附 proxy_rootcause 证据），状态由 ✅ 改判 🟡→本步闭合

**执行步骤**：
1. [ ] 只追加，不改历史段落

**验收命令**：
```bash
grep -n '环境代理' 'docs/任务规划V0.2.0/steps/STEP-00-测试环境与基线.md'
```

## 验收标准（独立验证者逐条判 PASS / FAIL / UNKNOWN）
- [ ] `test_env_isolation.py` 在有代理环境改前 2 failed、改后 2 passed
- [ ] 双环境全量 failed=0，两份 junit 用例结论逐条一致
- [ ] tests 内 `localhost:9999` 命中 0
- [ ] 未配置 DSN 时 `test_chat_sse.py` 无 error 只有 skip
- [ ] `make evidence-check` rc=0
- [ ] skip 仅剩 LangBot/Redis 类（-rs 输出逐条列入 EVD）

## 验证命令
```bash
cd apps/api && HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 uv run pytest tests/test_env_isolation.py -q && cd ../.. && make evidence-check && eval "$(bash scripts/test-env.sh env)" && cd apps/api && HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 uv run pytest tests -q -rfs | tail -3
```

## 证据路径
`docs/06_validation/evidence/EVD-V2-00R/`（README 记录：sha、命令、原始输出、PASS/FAIL 结论、验证者）

## 允许修改
- `apps/api/tests/conftest.py`
- `apps/api/tests/fixtures/net.py`
- `apps/api/tests/test_env_isolation.py`
- `apps/api/tests/test_alerting_drill.py`
- `apps/api/tests/test_bots_logs_filter.py`
- `apps/api/tests/test_wb_push_hardening.py`
- `apps/api/tests/test_w3_push_scheduler.py`
- `apps/api/tests/test_chat_sse.py`
- `apps/api/tests/test_r48_admin_jobs.py`
- `apps/api/tests/test_scheduler.py（仅 :663 注释行）`
- `Makefile（仅新增目标）`
- `docs/06_validation/evidence/EVD-V2-00R/**`
- `docs/任务规划V0.2.0/steps/STEP-00-测试环境与基线.md（仅末尾追加）`
- `docs/06_validation/evidence/EVD-V2-00/prove_dsn_policy.py（执行时增补：仅补 stdout UTF-8 保护 2 行，理由见执行记录 D-1）`
- `.github/workflows/ci.yml（仅当 D-11 授权：注释 :28-32 + 新 job）`

## 禁止修改
- `apps/api/app/**`（含 webhook.py，生产 trust_env 不改，N-02）
- `packages/contracts/**`（STEP-01 除外）
- `apps/api/alembic/versions/**`（STEP-04/08/09 各自唯一迁移号除外）
- `.github/**`（需 D-11 授权）
- `docker/**`、`deploy/**`
- 任务书未列出的一切路径

## 依赖与阻塞
- Depends on：—
- Blocks：STEP-02、STEP-03、STEP-04 的验收（它们的验收命令依赖本步的确定性基线）
- 阻塞条件（遇到即停）：改动需要触及 `apps/api/app/**` 才能变绿 ⇒ 停，标 blocked，回报（说明测试依赖了生产行为）

## 建议执行档位
`sonnect`　理由：测试侧机械改动，有现成证据与明确断言

## 升级条件
S0R.1.3 双环境结果不一致且无法用代理/端口解释 ⇒ 升 opus 做根因仲裁；另：同一原子任务连续 2 次验收失败 ⇒ 停止改代码，重写任务书 / 升档 / 标 blocked（熔断）。

## 预估规模
中（约 0.5–1 人日；S0R.3.1 需有 docker 的执行者另计）

## 完成定义（全项目唯一口径）
所有权内 diff 符合本卡 ∧ 验收逐条有结果 ∧ 自动测试可复现 ∧ EVD 可让一周后的人复现 ∧ `make evidence-check` 通过 ∧ 未改冻结契约（STEP-01 除外）∧ 无新增同类错误。

## 回滚
`git revert <sha>`；无数据影响。

---

## 执行记录（2026-10-12，Agent 侧；静态可证项已闭，运行时项移交）

证明与逐原子状态：`docs/06_validation/evidence/EVD-V2-00R/README.md`（§1 逐原子表、§2 20 条断言 +
4 个变异体反证、§3 偏离登记、§4 移交项 H-1…H-6、§5 反自证声明）。

### 与任务书的偏离（全部为「实现形态」偏离，不改本卡目标与验收口径）

| id | 本卡要求 | 实际落点 | 理由 |
|---|---|---|---|
| D-1 | 未授权改 `EVD-V2-00/prove_dsn_policy.py` | 补了 2 行 `sys.stdout.reconfigure(encoding='utf-8')` | 该脚本在 cp936 控制台打印中文证据时抛 `UnicodeEncodeError`，一条断言都出不来 ⇒ `make evidence-check`（本卡 S0R.4.1 验收命令）在 Windows 上永远非 0。其两个兄弟脚本本就有这两行，属漏项。**待复核追认。**（同文件另有 D-6 一处文案修正） |
| D-2 | `@pytest.fixture(autouse=True, scope='session')` 等价实现 | 采用 **function 级** autouse + `monkeypatch` | session 级需在夹具内手工快照/还原 6 个变量，等价但更脆；function 级由 pytest 保证 undo，且证明脚本能真实执行函数体（`prove_net_isolation.py` NR-2…NR-6）。语义差别：单用例内可临时再设代理——本卡未要求禁止。 |
| D-3 | `test_chat_sse.py` 仅 :1208/:1272 两处守卫 | 只在 `test_ask_real_full_chain_smoke` 函数首行加 **1** 处守卫 | 两处 `create_async_engine` 都在该函数体内（第二处是嵌套 `_real_db`），首个守卫之后函数即不再下探 ⇒ 第二处不可达（`prove_net_isolation.py` NR-10-a/b 断言此结构）。 |
| D-4 | ①`NO_PROXY` 含 127.0.0.1 | 除置 `NO_PROXY`/`no_proxy` 外，**先删除 6 个代理变量** | 单靠 `NO_PROXY` 不足以确定性：httpx 的 `trust_env` 对 `ALL_PROXY` 与大小写混用有历史差异，且 socks 代理不吃 `NO_PROXY`。删变量才是「只取决于本机监听状态」的充分条件。 |
| D-5 | S0R.1.1 两条用例 | 写了 **3** 条（新增 `test_host_proxy_state_is_not_inherited`） | 第 3 条把「宿主有代理时用例是否真的经过隔离」做成可观测信号（宿主无代理则 skip），否则前两条在干净机器上是空洞通过。 |
| D-6 | 未在授权范围（同 D-1 文件）| 另改 `prove_dsn_policy.py` 两条 **detail 文案**（S0.1.2-b、S0.1.2-r）| `check()` 无条件打印 detail，原文写成「失败描述」句（如“conftest 仍含口令字面量”“广播值为空串/None”），**断言通过时**输出里也显示 ⇒ 一周后的复核者会误读为缺陷。改为观测值（命中计数 / 三入口实际广播值）。断言逻辑一字未动，仍是 20/20。|

### 未闭合项（阻塞，非本卡可解）

- S0R.1.3 / S0R.2.3 / S0R.3.1 / S0R.3.2：需 venv + 依赖 + 隔离 PG（docker），且受本会话「不实际启动服务、
  不装依赖」约束 ⇒ 全部列为移交项（EVD-V2-00R §4），本卡**不得**据此判 ✅。
- CI 增 `evidence-check` job：与 `.github/**` 同批授权（D-11 类），未动。
