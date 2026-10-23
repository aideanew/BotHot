---
id: ENGINEERING-CONVENTIONS
type: convention
title: BotHot 工程规范
status: active
owner: engineering
created: 2026-09-29
updated: 2026-09-30
version: 1.0
---

# BotHot 工程规范

## 1. 端口分配（强制）

| 端口 | 用途 | 禁止 |
|------|------|------|
| 3000 | 主平台专用 | ❌ BotHot 任何服务不得占用 |
| 3200 | BotHot 前端宿主端口 | — |
| 3300 | BotHot 后端端口 | — |
| 5300 | LangBot | — |
| 5433 | PostgreSQL | — |
| 6380 | Redis | — |

> 容器内部端口：前端 3000、后端 3300（已统一）。

## 2. 命名规范

### 2.1 项目命名
- 项目名：**BotHot**（PascalCase）
- Docker Compose 项目名：**bothot**（lowercase）
- Session Cookie 名：**bothot_session**

### 2.2 后端命名
- 文件：snake_case（`push_provider.py`）
- 类：PascalCase（`PushProvider`）
- 函数/变量：snake_case（`send_message`）
- 常量：UPPER_SNAKE_CASE（`MAX_RETRY_COUNT`）
- 数据库表：snake_case（`bot_channels`）
- 数据库列：snake_case（`channel_type`）

### 2.3 前端命名
- 文件：PascalCase（`SpaceHeaderPanel.tsx`）
- 组件：PascalCase（`SpaceHeaderPanel`）
- 函数/变量：camelCase（`fetchSpaces`）
- 常量：UPPER_SNAKE_CASE（`API_BASE_URL`）
- CSS 类：kebab-case（`space-header`）
- 路由路径：kebab-case（`/hot/daily`）

## 3. Git 规范

### 3.1 分支策略
```
main          ← 生产分支（受保护）
├── develop   ← 集成分支
├── feature/* ← 功能分支
├── fix/*     ← 修复分支
└── docs/*    ← 文档分支
```

### 3.2 提交信息格式
```
<type>(<scope>): <subject>

<body>

<footer>
```

**type**: feat | fix | docs | refactor | test | chore | ci
**scope**: identity | knowledge | subscription | ingest | chat | engine | bot | hot | system | web | infra | docs
**subject**: 简短描述（祈使句，中文或英文均可，同一 PR 内统一语言）

示例：
```
feat(bot): 实现飞书 Webhook Provider 真实推送
fix(hot): 修复聚簇算法时间衰减计算错误
docs(architecture): 更新系统架构设计文档
```

## 4. 测试规范

### 4.1 后端
- 单元测试：`apps/api/tests/test_*.py`（**扁平一层目录**，不按 domain 分子目录）
  - 证据：`ls apps/api/tests` → 76 项全为 `test_*.py` + `conftest.py`，无 `unit/`/`integration/` 子目录。
  - 命名即域标签：`test_be02_engine_routing.py`、`test_w3_push_scheduler.py`、`test_backchannel_logout.py`。
  - 原规范 `tests/unit/modules/<domain>/` 与 `tests/integration/modules/<domain>/`（X-08）**从未落地**，
    按此新建子目录会让 pytest 采集路径与 CI 的 `--junitxml` skip 门禁口径错位。
- 测试文件命名：`test_<module>.py`（沿用）
- 覆盖率目标：core/ 和 application/ 层 > 80%（沿用；实测口径见 `docs/06_validation/`）
- 模块覆盖率门（STEP-06 S6.3，2026-10-22）：全局 `--cov-fail-under` 之外另有一道按模块的门，
  阈值表在 `scripts/check_module_coverage.py`（article_identity 100、manifest/kb/subscription 85、
  四家 provider 80、全局 79）。跑法：`pytest --cov=app --cov-report=json:coverage.json` 之后
  `make coverage-gate`；CI 的 `backend` job 已接同一步。**为什么不让全局分抵掉单模块**：
  总分可以靠别的域涨回来，采集链空了却看不出来。反证常驻
  `apps/api/tests/test_module_coverage_gate.py`（含"人为调高阈值 ⇒ rc≠0"与"缺输入 ⇒ rc=2 ≠ 通过"）。

### 4.2 前端
- 单元测试：`apps/web/tests/*.spec.ts` / `*.spec.tsx`（**集中在 `tests/`，不与组件同目录**）
  - 证据：`apps/web/vitest.config.ts:25` `include: ["tests/**/*.spec.ts", "tests/**/*.spec.tsx"]`；
    实测 22 个 `*.spec.tsx` 全在 `apps/web/tests/`，组件目录内 `*.spec.tsx` 为 0。
  - 原规范"与组件同目录"（X-08 同族）会导致新写的用例**不被 vitest 采集**而静默不跑。
- e2e 测试：`apps/web/e2e/*.spec.ts`（Playwright，与单测分目录，正确）
- 框架：Vitest（单元，`environment: happy-dom`，见 vitest.config.ts:26） + Playwright（e2e）

### 4.3 验证纪律（STEP-00E S00E.2.2 增，2026-10-17）

三条都是本轮实测踩出来的，不是从别处抄来的通用建议。

1. **`skip ≠ pass`，且判定动作必须是"点名"而不是"看总数"**。
   一条用例出现在 `SKIPPED [...]` 列表里就等于**它没有被执行**；把这种读数写成"通过"是本仓
   最贵的一类错误（本文件 §4.1 那条"采集路径错位导致静默不跑"是同一族的另一面）。
   判定动作固定三步：①`pytest -q -rs`（`-rs` 不是可选项，不加就拿不到原因）；
   ②读 skip 门禁打的 `pg_unreachable` / 各族计数，**不是**读 `N passed`；
   ③对关键用例**单独点名**——它出现在 skip 列表 = 未验收。
   样例判据：`test_be02_engine_routing.py::test_short_link_second_ingest_hits_cache_via_url_fallback`
   （R0 的缓存回归），见 `docs/06_validation/evidence/EVD-V4-00E/s00e_readings.md` §2。
2. **工具/依赖缺失必须打印 `SKIP(tool missing)`，并与"用例自己 skip"用不同退出码区分**。
   原因：同一份 `skipped` 计数里混着两种语义完全不同的东西——
   "这台机器没有 docker"（读数无效，换机重跑）与"这条用例按设计在该环境跳过"（读数有效）。
   二者共用一个计数就是 00E 本机现状的问题：`1570 passed / 6 skipped` 看起来与依赖机同等，
   实际上**这台机器上的连库面一条都没跑**。落地形态见 `ci-windows.yml` 的门禁（按原因族记账 +
   未知族即红）与 `cross-platform.md` §8。
3. **验收环境是共享工作树的一部分，每台机器每轮重取，不得引用上一版的工具链状态**。
   本轮实测：`shutil.which('docker')` 与 `which('docker-compose')` 均为 `None`、
   `wsl.exe --list` rc=1（无发行版）、`netstat` 对 5433/6380 无监听——这与 2026-10-15
   `EVD-V5-00X` §1 记的工具链清单**不是同一份事实**（那份里 gitleaks/node/pnpm 都装齐了，
   docker 从来没有）。引用旧读数的后果是把"判不了"写成"已通过"。
   每轮开工第一步 = 现跑上面三条探测，并把输出贴进当批 EVD。
   **同一句纪律也有"反向"的一半**：引用任何一条现读数字（任务数、目标数、grep 命中数、覆盖率、skip 数）时
   必须带上它**锚在哪个 sha**，并且默认它只在那一批成立——`EVD-V5-00X` 里"`verify-*` 全仓 0 命中"那句
   在 `8e59749` 上是真话，两小时后的 `9983c63`（STEP-00E）就把那四个名字建进了 `entry.py`/`Makefile`。
   两句都仍是对的，各自锚在自己那一批；**错的是把它们当"现在"来读**。案例全文见
   `docs/06_validation/evidence/EVD-V17-12/s12_readings.md` §0.1。

### 4.4 验收环境：一条命令出读数（STEP-00E S00E.1.3 / S00E.2.1 增，2026-10-23）

四个入口，实体只在 `scripts/entry.py` 一份，Makefile 是薄转调，一致性由 `check_entry_parity.py` 常驻判：

| 入口 | 顺序（步骤在 entry.py 里是列表，任一步非 0 立即短路） | 为什么要这个顺序 |
|---|---|---|
| `entry.py testenv-up` / `testenv-down` | 探 `docker`/`podman` → 转调 `scripts/test-env.sh up\|down` | 该脚本是 D-12 的守卫：测试端口命中**部署端口**（5433/5435/6379/6380）即 exit 2 拒绝启动；起完还带 `pg_isready` 60s / `redis-cli ping` 30s 的健康等待 |
| `entry.py verify-backend` | ①探 PG 端口 → ②alembic 单头断言 → ③`upgrade head` → ④`pytest tests/ -q -rs --junitxml=pytest-report.xml --cov=app --cov-report=term-missing` | ①必须在最前：无 PG 时第④步会交出一份**400+ 条 skip 的"0 failed"**，看上去像验收过，实际连库面一条没跑（§4.3 第 2 条就是这个坑）。②在③之前：多头时 `upgrade head` 的报错形状像"环境问题"，而它其实是治理事故 |
| `entry.py verify-frontend` | ①打印 `node_modules` 存在性 → ②`pnpm install --frozen-lockfile` → ③再打印一次 → ④`tsc --noEmit` → ⑤`vitest run`（`pnpm run test:unit`）→ ⑥`NEXT_PUBLIC_API_MOCK=false` 的 `build` | ①③是 **F-10 的要求**：这个仓库历史上出现过"上一版说 node_modules 存在、这一版说没有"——两边都对，差别只在机器。存在性必须**作为读数打出来**，不能假设；⑥是生产守卫（不设这个变量 build 自己会 rc=1） |

三条纪律：

1. **单头断言在本地也判，且它有四发极性读数**：一行 `(head)` 放行、两行拦、零行拦、
   命令自身失败拦（并明写"没跑成"）、`alembic` 没装则 `SKIP` + rc=3。后四发用桩跑出（不连库，
   `EVD-V4-00E/verify_targets_readings.md`）；本机没有可达 PG 时，`verify-backend` 会在①就停下，
   这正是想要的行为——**门没跑与门过了必须一眼可分**。
2. **`SKIP` 不是通过**：这三个入口在非依赖机上都会以 rc=3 收场（`docker-ps` 那类是 3，
   `migrate`/`verify-backend` 无 PG 也是 3）。GNU make 把任何失败折成 2，所以 `make X` 与
   `entry.py X` 的判据是**同为 0 或同为非 0**，不是逐值相等（00X 按实测改正过）。
3. **`docker/compose.yml` 起不到依赖库**：现读它的 services 段只有
   `langbot_plugin_runtime / langbot / backend / migrate / scheduler / worker / frontend`，
   **没有** postgres/redis 服务。所以 `entry.py` 的不可达提示已从"起 compose.yml"更正为
   "`entry.py testenv-up`（隔离栈 5547/6390，需 docker）"；AGENTS.md 端口表里的 5433/6380
   是**部署形态**端口，由平台侧供给，不由本仓 compose.yml 供给（这条差异登记在台账 §4 P-102）。

### 4.5 测试环境的三条隔离纪律（STEP-12 S12.1.3，2026-10-23）

这三条原本散在脚本注释与各卡 EVD 里，从未进本文件；S12.1.3 要求它们成为规范条文。
每条都给出**实体在哪**与**违反时会被什么抓住**，否则写了等于没写。

1. **测试端口只能用隔离段，且不许静默换端口。**
   测试 PG/Redis 的宿主端口 = **5547 / 6390**（`scripts/test-env.sh` 的默认值）；
   命中**部署端口** `5433 / 5435 / 6379 / 6380` 即 `exit 2` 拒绝启动，
   覆盖 `AIDEANBOT_TEST_PG_PORT` / `AIDEANBOT_TEST_REDIS_PORT` 这两个"自己改一个"的入口；
   `<1024` 与 `>65535` 同样拒绝。3000 归主平台（AGENTS.md 端口表），BotHot 任何服务不得占用。
   为什么这么严：D-12 的事故——`conftest` 曾把部署库当连库目标的第三级回退且只告警不拒绝，
   于是"跑测试"等于写部署形态库，而运行中的 scheduler/worker 会把测试订阅当到期任务**真实消费**。
   换端口之所以禁死：`AIDEANBOT_TEST_PG_DSN` 与读数的库会分叉，两份读数就不可比。
2. **用例的出站网络由 `conftest` 密封，不靠机器现状。**
   `apps/api/tests/conftest.py` 的 `_isolate_proxy_env`（autouse）清掉 6 个代理变量
   （`HTTP_PROXY / HTTPS_PROXY / ALL_PROXY` 及小写三个）并把 `NO_PROXY`/`no_proxy` 钉成
   `127.0.0.1,localhost,::1`，所以"连不上"必须意味着**本机真没有那个监听**，而不是被代理劫走。
   配套有一条**故意 skip** 的对照用例 `tests/test_env_isolation.py:77`（宿主根本没设那 6 个变量时
   它在此环境无判定力）⇒ 看到 `@ci` 的 `6 skipped` 时要知道：**其中一条是设计如此**，
   另五条才是 LangBot×2 / Redis×3。按 §4.3 第①条，skip 必须点名读，不许只看总数。
3. **DSN / 口令 / 主密钥一律不得进仓内文本。**
   文档、注释、日志摘录、EVD、提交信息里都不许出现带口令的连接串、口令赋值形或 base64 密钥值；
   引用时用泛化表述（"内嵌 PAT""一次性主密钥"）。执行面：`evidence-check` 读 **索引**判形（它是近似器，
   不是完整扫描器——它的假阳性史记在 §9.1 的 P-36 旁边），CI 的 gitleaks 步读历史。
   文档侧的对应规范条文在 §6.1（AK/SK 只走环境变量）。**一次性生成的凭据同样是凭据**——
   `compose-smoke` 那一步会打印它自己 `os.urandom(32)` 出来的两把临时主密钥，抄进 EVD 就是把
   "它当时能解开那些行"这件事永久写进仓库（这条的完整处置见台账 §4 P-107）。

## 5. 依赖管理

### 5.1 后端
- 包管理：uv（pyproject.toml + uv.lock）
- Python 版本：3.12
- 依赖锁定：uv.lock 必须提交

### 5.2 前端
- 包管理：pnpm
- Node 版本：**24**（`.nvmrc` = `24.21.0`；`apps/web/package.json:7` `engines.node >= 24.0.0`）
  - 原规范写 22（X-03）——按 22 跑 `pnpm install` 会被 engines 判定不满足。
- 锁文件：pnpm-lock.yaml 必须提交

### 5.3 跨平台入口与"文档 ≠ 实现"的一处更正
- **命令实体的唯一源是 `scripts/entry.py`**（STEP-00X / D-V4-01）。`make <task>` 与
  `python scripts/entry.py <task>` 同义：Makefile 的开发类目标只做薄转调，守卫类目标转调
  `scripts/guards.py`。平台分支全仓只允许两处——`entry.py` 的 `dispatch()` 与 Makefile 变量块的
  `ifeq ($(OS),Windows_NT)`。新增第三处要先改本条。
- 一致性由 `scripts/check_entry_parity.py` 机检（Makefile 每个目标都能解析到实体、且 recipe 已转调）；
  执行者是 **`CI-Windows` 工作流**里名为 `entry.py 与 Makefile 目标面一致性` 的那一步——原文把它写成
  "CI 的一个 job 会跑它"，而自 D-V7-01 起那半个门已独立成 `ci-windows.yml`（不再属于 `CI` 工作流），
  ⇒ §4 P-1 就地收口；逐字核对方式：`grep -n "entry.py 与 Makefile 目标面一致性" .github/workflows/ci-windows.yml`。
- **更正 §5.1**：本条原写"包管理：uv（pyproject.toml + uv.lock）"，但 CI 的 backend job 实际执行的是
  `pip install -e ".[dev]" pytest-cov`（按步内容定位；原记 `ci.yml:59` 已被后续插步顶偏到 `:64`，
  而 `:59` 现在指的是 `python-version: "3.12"`），`uv.lock` 只被 security job 的依赖审计读取。
  两者并存是现状：装依赖以 **pip + pyproject** 为准，锁文件仍必须提交。跨平台脚本一律按 pip 口径实现。
- Windows 侧两条硬提醒（都实测过，详见 `cross-platform.md`）：`python3` 是 Microsoft Store 空壳（什么都不做还返回 0）；
  无 PG 时 `alembic upgrade head` **挂住不返回**，所以 `entry.py migrate` 先探端口，不可达即 `SKIP` + rc=3。

## 6. 环境变量规范

### 6.1 敏感信息
- AK/SK：**不写入 .tf/.py 文件**，通过环境变量传入
- 渠道密钥：**现状（2026-10-12 代码实证）= AES-256-GCM 已落地并已接线**（X-04 更正）
  - 实现：`apps/api/app/core/secret_crypto.py`（模块首行 docstring 即 "渠道密钥 AES-256-GCM 加解密"），
    密文形态 `b64(nonce).b64(ct+tag)`，AAD 绑定 `bot_channel.id`（`:80` `channel_id.encode()`），
    主密钥 `PUSH_SECRET_MASTER_KEY` = 32 字节密钥的 base64，缺失/畸形 fail-closed（`:30-40`）。
  - 接线证据（非死代码）：写侧 `apps/api/app/api/v1/bots.py:34` import，
    读侧 `apps/api/app/services/push_scheduler.py:181-183` 每渠道投递时调
    `decrypt_channel_secret(ch.id, ch.secret_enc)` / `decrypt_extra_config(...)`。
  - 引擎 Key 是**另一套**同族实现：`apps/api/app/core/engine_keyring.py`
    （AES-256-GCM，AAD 绑引擎名，主密钥 `ENGINE_KEY_MASTER_KEY`），
    由 `apps/api/app/services/engine_keys.py:18` 使用。规范上两者不共用主密钥。
  - **迁移形态 = 数据迁移重加密，不是"双读兼容"**（此处规范原文与实现方式不同，已按实更正）：
    原规范设想"读侧兼容存量 base64（双读），重加密后再删过渡路径"；实际落地的是
    `apps/api/alembic/versions/ab1004w1a_secret_aes.py`——逐行把不含 `.` 的存量 base64
    解出明文后用 AES 重加密（`:46-49` 选行、`:89` 逐行写回），
    并且**主密钥缺失即中止迁移**（docstring `:38-42`：静默跳过会让存量行永久停留在
    fail-closed 不可读状态，比迁移期显式报错更难排查）。
    ⇒ 因此读侧 `decrypt_channel_secret` 是 **AES-only 且正确**的：迁移后不存在 base64 存量行。
    `extra_config` 相反，走的是"`{` 前缀判定"的**兼容读**（`secret_crypto.py:126-142`），
    因其存量形态是明文 JSON 而非 base64，两者口径不同属有意设计，见 `CHANGELOG.md` S2.1 条目。
  - ⚠ 残留**卫生问题**（非功能缺陷）：`secret_crypto.py:93` `decrypt_legacy_base64()` 全仓
    **零调用方**，`is_aes_ciphertext()` 仅出现在 `apps/api/tests/test_w1_push_domain.py`。
    留着的风险不是"漏解密"，而是将来有人把它当"兼容读"接回读侧，等于把已废除的
    base64 伪加密重新变成可用路径 ⇒ 应删除或降级为迁移脚本内部私有实现。
    取证 SQL（需连库，本机无 PG）：
    `select count(*) from bot_channels where secret_enc <> '' and secret_enc not like '%.%';`
    期望 **0**（迁移已收敛）；非 0 才说明存在迁移漏网行。
- OIDC Client Secret：通过环境变量传入

### 6.2 环境变量命名
- **现状（2026-10-12 实证）= 无前缀**（X-05 更正）。原规范要求的
  `BOTHOT_` 前缀 + `<SECTION>` 分段命名（含 `…_DB_URL` / `…_REDIS_URL` / `…_OIDC_CLIENT_ID` 三个示例）
  **从未生效**，按它起变量名会得到 Settings 读不到的键。
- 机制证据：`apps/api/app/core/config.py:14`
  `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`
  —— pydantic-settings **没有** `env_prefix`，故字段名即大写环境变量名。
- 真实名字（据 config.py 字段 + compose/env 模板）：
  `DATABASE_URL`(`:20`)、`REDIS_URL`(`:23`)、`AIDEAN_ISSUER`(`:30`)、`AIDEAN_PUBLIC_URL`(`:31`)、
  `OIDC_CLIENT_ID`(`:32`)、`OIDC_CLIENT_SECRET`(`:33`)、`OIDC_REDIRECT_URI`(`:35`)、
  `SESSION_STORE_BACKEND`(`:55`)、`LANGBOT_BASE_URL`(`:63`)、`EMBEDDING_API_BASE`(`:74`)，
  以及不经 Settings 的两个主密钥 `PUSH_SECRET_MASTER_KEY`、`ENGINE_KEY_MASTER_KEY`。
- 唯一带前缀者：`BOTHOT_PROCESS_COUNT`，证据 `apps/api/app/db.py:82`
  `int(os.environ.get("BOTHOT_PROCESS_COUNT", "4"))` —— 它绕过 Settings 直接读 `os.environ`，
  前缀是**例外**而非规范。
- **改名代价要算清**：把上述变量统一加前缀需同时改 `config.py` 字段、`docker/compose.yml`、
  `docker/.env.example`、`Makefile`、CI env、`scripts/rotate_keys.sh`，且与已发布部署形态耦合
  ⇒ 本规范条目**按实况改写为"无前缀"**，不改代码；如未来要立前缀规范，另开任务并出迁移方案。
- 格式（沿用，仍然生效的部分）：全大写 + 下划线；秘密类必须经环境注入，禁写入仓库任何文件。

## 7. 文档规范

详见 [PROJECT-DOCUMENTATION-SPEC](../00_governance/doc-spec.md)。

核心规则：
- 每个文档有 frontmatter（id/type/title/status/owner/created/updated）
- 文档放在 docs/ 对应分类目录
- 新需求先入 `02_requirements/inbox/`
- 架构决策记入 `03_solution/decisions/`

## 8. Docker 规范

- Dockerfile 用多阶段构建（`apps/api/Dockerfile:8 builder` / `:35 runtime`；
  `apps/web/Dockerfile:16 builder` / `:61 runner`）
- 基础镜像**版本锚**（三处必须同源，改一处就要改三处）：
  - 后端 `python:3.12-slim` — `apps/api/Dockerfile:5` `ARG BASE_IMAGE=python:3.12-slim`
    与 `docker/compose.yml:132` `${BASE_IMAGE:-python:3.12-slim}`
  - 前端 `node:24-alpine`（X-03 更正：规范原值差两个大版本，详见 §2.3 清单）—
    `apps/web/Dockerfile:13` `ARG BASE_IMAGE=node:24-alpine` 与
    `docker/compose.yml:390` `${BASE_IMAGE:-node:24-alpine}`；
    `compose.yml:388-389` 明确记录了"compose 侧曾用 20 静默覆盖 Dockerfile 的 24 锚"这一事故，
    故**镜像源开关走 build args、锚值只在 Dockerfile 的 ARG 默认里**，不要在 FROM 上写死 tag。
- Docker Compose 配置在 **`docker/compose.yml`**（X-06：原规范 `infra/docker/compose.yml`
  不存在——`ls infra/docker/compose.yml` 无此路径）。v0.7 已**裁定不迁移**，理由见
  `docs/04_engineering/roadmap.md` v1.0 前置项："移动只破坏 CI/alembic.ini，无收益"。
  CI 以 `docker/compose.yml` + `docker/compose.ci.yml` 双文件叠加使用。
- `.env.example` 提供所有环境变量模板（实际路径 `docker/.env.example`；
  compose 以"第一个 config 文件的所在目录"为项目目录自动加载它）

## 9. 安全规范

- Cookie：HttpOnly + SameSite=Lax
- CORS：**不设 CORS**（X-07：原规范"CORS 白名单制，不开放 0.0.0.0/0"与实现相反）
  - 机制：前端 `apps/web/next.config.mjs:9-15` 用 rewrites 把 `/api/v1/:path*`
    代理到 `BACKEND_ORIGIN ?? http://localhost:3300` ⇒ 浏览器**同源**访问，无跨域请求。
  - 实现证据：`grep -rn "CORSMiddleware|allow_origins" apps/api/app --include=*.py` → **零命中**。
  - 裁定依据与后果：`apps/api/app/core/security.py:440-441` 明确写"**不含 CORS**……
    加 `Access-Control-Allow-Origin` 只扩大攻击面"；裁定出处为 TASK-PLAN-v0.9 §0.2。
  - 规范动作：**禁止**在后端引入 `CORSMiddleware`。若未来确有跨域需求（如第三方嵌入），
    必须先出 ADR 裁决来源白名单与凭据策略，再改本条。
- SQL 注入：ORM 参数化查询，禁用字符串拼接 SQL
- XSS：前端输出转义，禁用 dangerouslySetInnerHTML
- 权限：路由层 require_roles 门禁
- 密钥：不硬编码，环境变量传入

### 9.1 入库前敏感形门（STEP-00P S00P.2.1 / 2.2 / 3.1 增，2026-10-19）

机器门位置：`scripts/guards.py` 的 `secret_shape_check()`，作为 `make evidence-check` 的
**前置阻断步**（HIGH>0 ⇒ rc=1；这一维没有可检面 ⇒ rc=3，不伪装成通过）。

- **规矩一：文档与代码注释里不得内联敏感形字面量，也不得内联扫描正则本身。**
  要写判据就指向判据实体（`guards.py` 的 `SECRET_RULES` / `SECRET_ALLOW` / `SECRET_ASSIGN`），
  必要时只描述**邻接关系**（哪几段以什么顺序相接）。
  理由是本仓自伤已三次：V0.7.0/V0.6.0 的规划文档抄过占位连接串、又抄过正则；
  本轮**实现这道门时**第一版 `guards.py` 的注释里带着邻接形状，被自己的门扫出 2 条 HIGH——
  违规者正是要立这条规矩的文件。现跑读数见 `docs/06_validation/evidence/EVD-V4-00P/`。
- **规矩二：必须引用某条凭据形时的替代写法**——
  ① 只描述形状，不写可复制的完整串（连"示意串"也不算例外）；
  ② 测试夹具一律**跨字符串边界拼接**（键名与赋值号之间断开、scheme 与 `://` 之间断开），
     使运行期拼出的串命中、而源码文本里的行不命中；范例 =
     `apps/api/tests/test_secret_shape_gate.py` 的 `_dsn()` / `_kv()`，
     并由该文件末尾的「实现文件自身不带形状」用例把它钉成常设判据；
  ③ 权威终判以 gitleaks 的 git 模式为准（CI：`.github/workflows/security.yml`；
     本机：`evidence-check` 的真实工具步转调）。近似器**不**取代它。
- **边界声明（这道门刻意不做的事）**：
  ① 它是 `.gitleaks.toml` 规则 1 + 已知 token 前缀 + 私钥块 + 口令赋值形的**近似器**，
     不含上游默认规则，也不含熵判据；
  ② 只扫**本批**（索引中的待提交路径；索引为空时退到 `base..HEAD`），不扫全仓——
     全仓口径会被历史遗留件反复挡，结果是门被人关掉；
  ③ 历史提交里的指纹不会因工作树打码而消失，仍需 `.gitleaksignore` 逐指纹登记
     （D-12，归 STEP-00S）；本门**不自建 allowlist**，需要豁免走那条路；
  ④ 命中输出只报打码形状（安全铁律第 1 条），因此不能凭门自己的日志复原值；
     连接串形状的**用户名位也一并打码**（各留 4 字符）——复核实测出「把 token 放在用户名位、
     口令位填一个占位字符」的用法，只隐口令段等于把凭据整条留在输出里。
     另注意**打码 ≠ 脱形**：星号仍满足那两段的字符类，所以门的输出行不能原样抄进待提交文档
     （`EVD-V4-00P` §10 记了这次自伤与钉法）；
  ⑤ 近似器带着**继承来的漏检面**：厂商键名规则要求值不少于 8 个非空白字符。
     ~~赋值形要求键名前后是词边界，所以紧贴在下划线之后的键名不抓~~
     ——S27.3（D-V12-05）起，**源码面**补了 `_TOKEN` 后缀这一族；其余前缀名
     （`DEFAULT_SECRET` 等）仍按 P-41 的登记留在原地，执行面不擅自扩面。
- **两条已测量、待裁决的口子**：
  P-36 口令赋值形启发式对本仓**文档**仍 100% 假阳性（变量引用与布尔读数被判 HIGH）——
  S27.V15.1 只在**源码面**收窄（见 §9.2），文档面读数一字未改；
  P-37 gitleaks 8.21.2 在 Windows 上自报 `failed to scan` 却仍 rc=0（S27.4 起由
  `.gitattributes` 的 `*.docx binary` 消掉触发源）。

### 9.2 验收读数的批面口径（STEP-27 S27.7 / D-V12-04）

- **读数必须取自非空批，并写明批面。** 范围门（`evidence-check` / `rounds-check`）在
  `base..HEAD` 为空时返回 **rc=3**，含义是「这一维没有可检面」，**不是通过**。
  干净工作树上任何平台都会读到 3；把它写成「rc=0 已确认」是假读数（F-V15-01 的原形）。
- 批面写法：`<base 短号>..<HEAD 短号>`，或 `索引面（N 个路径）`。CI 上的批面由事件给出
  （push 用 `github.event.before`，PR 用 base sha，首推 before 全 0 时退回 `HEAD~1`）。
- **源码面与文档面口径不同**（S27.V15.1 / D-V12-21）：源码后缀
  （`.py/.ts/.tsx/.js/.jsx/.mjs/.cjs`）里，键名在代码位且右值无引号、非纯数字 ⇒ 判为表达式、
  不报；键名落在字符串/注释里、右值含值类字面量（≥8 字符、非占位、非全大写环境变量名）、
  或整体就是一个字面量 ⇒ 照报。文档面**一字未改**。改这条口径必须同时给出全仓新旧命中集合
  的包含关系读数（`apps/api/tests/test_secret_shape_gate.py` §H）。


