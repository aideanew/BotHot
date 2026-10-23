---
id: REQ-NF-002
type: requirement
title: 安全
status: active
owner: product
实现度: 部分（加密/生产守卫/密钥扫描有锚；「CORS 白名单」是达成方式与文本不符，SQL 注入无机检用例）
验收锚:
  - apps/api/tests/test_extra_config_crypto.py
  - apps/api/tests/test_channel_update_extra_config_encrypted.py
  - apps/api/tests/test_r11_engine_keys.py
  - apps/api/tests/test_production_config_guard.py
  - apps/api/tests/test_security_middleware.py
  - apps/api/tests/test_secret_shape_gate.py
  - apps/api/tests/test_r493_openapi_security.py
  - apps/api/tests/test_bots_read_authz.py
最后核验 commit: bf141d5（2026-10-23 现读）
---

# REQ-NF-002 安全

## 需求条目逐条对表

| 条目 | 实况 | 锚 |
|---|---|---|
| SSO Cookie HttpOnly + SameSite=Lax | 部分：HttpOnly 有断言，SameSite 只在代码里设定 | `test_auth.py:273`（HttpOnly）；`apps/api/app/api/v1/auth.py:98` `samesite="lax"` **无测试断言** ⇒ 已进 backlog SEC-006 一并立项 |
| 渠道密钥 AES-256-GCM 加密落库 | 已实现（fail-closed，双主密钥纳入生产守卫） | `test_extra_config_crypto.py`、`test_channel_update_extra_config_encrypted.py`、`test_production_config_guard.py` |
| 生产环境 OIDC iss/aud 校验 | 已实现 | `test_production_config_guard.py`、`test_backchannel_logout.py` |
| ~~CORS 白名单~~ → **经 `next.config.mjs` 同源 rewrites 达成，无 CORS 中间件** | 达成方式与原文本不符，非漏实现 | 见下节 |
| SQL 注入防护（ORM 参数化） | 结构上成立（SQLAlchemy 参数化 + 无字符串拼 SQL 的入口），但**无机检用例** | 无 ⇒ 已进 backlog 立项（见下） |

## CORS 这一条改写的依据（S17.1.2 / 冲突 C-3）

现读 `apps/api/app`：`CORSMiddleware` 与 `allow_origins` 命中数 **0**。
唯一说明在 `apps/api/app/core/security.py` 的 `SecurityHeadersMiddleware` docstring：
「**不含 CORS**——前端经 `next.config.mjs` rewrites 同源代理 `/api/v1/*`，
浏览器从不跨域直连后端；加 `Access-Control-Allow-Origin` 只扩大攻击面。」

⇒ 需求文本按实况改写为"同源 rewrites 达成，无 CORS 中间件"，并且**不排 CORS 开发任务**
（C-3 的裁决就是禁止把这条重新立项）。锚点行号取现读：`apps/api/app/core/security.py` 的该 docstring
（卡面原引 `security.py:440` 已漂移：现读 `apps/api/app/core/security.py:440` 是 `code=PAYLOAD_TOO_LARGE_CODE`）。

## 无锚项的处置（验收标准：回答「无」的必须同步在 backlog 立项）

`docs/04_engineering/backlog.md` 新增 SEC-006（SQL 注入面无机检）与 STACK-001
（技术栈版本一致无机检，见 `../constraints/REQ-C-001-tech-stack.md`），
两条都标 ⬜ 未开始，不冒充已完成。
