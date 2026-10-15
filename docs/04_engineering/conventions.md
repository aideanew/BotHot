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

### 4.2 前端
- 单元测试：`apps/web/tests/*.spec.ts` / `*.spec.tsx`（**集中在 `tests/`，不与组件同目录**）
  - 证据：`apps/web/vitest.config.ts:25` `include: ["tests/**/*.spec.ts", "tests/**/*.spec.tsx"]`；
    实测 22 个 `*.spec.tsx` 全在 `apps/web/tests/`，组件目录内 `*.spec.tsx` 为 0。
  - 原规范"与组件同目录"（X-08 同族）会导致新写的用例**不被 vitest 采集**而静默不跑。
- e2e 测试：`apps/web/e2e/*.spec.ts`（Playwright，与单测分目录，正确）
- 框架：Vitest（单元，`environment: happy-dom`，见 vitest.config.ts:26） + Playwright（e2e）

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
  CI 的 `windows-dev` job 会跑它。
- **更正 §5.1**：本条原写"包管理：uv（pyproject.toml + uv.lock）"，但 CI 的 backend job 实际执行的是
  `pip install -e ".[dev]" pytest-cov`（`ci.yml:59`），`uv.lock` 只被 security job 的依赖审计读取。
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
