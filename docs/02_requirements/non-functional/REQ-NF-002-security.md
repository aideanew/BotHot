---
id: REQ-NF-002
type: requirement
title: 安全
status: active
owner: product
实现度: 已实现（命题范围：加密 / 生产守卫 / 密钥扫描形 / SQL 参数化面 / Cookie SameSite 五项，STEP-62 现读 2026-10-29）：原缺口两项由 SEC-006 于 STEP-49 收口补上机检——SQL 参数化面 `test_sec006_sql_param_surface.py`、`SameSite=lax` 断言 `test_auth.py`（证据 `docs/06_validation/evidence/EVD-V21-49/`，先红读数 `s49_1_red.txt`）；「CORS 白名单」一条按实况改写为「经 `next.config.mjs` 同源 rewrites 达成，无 CORS 中间件」（C-3：不重新立项）
验收锚:
  - apps/api/tests/test_extra_config_crypto.py
  - apps/api/tests/test_channel_update_extra_config_encrypted.py
  - apps/api/tests/test_r11_engine_keys.py
  - apps/api/tests/test_production_config_guard.py
  - apps/api/tests/test_security_middleware.py
  - apps/api/tests/test_secret_shape_gate.py
  - apps/api/tests/test_r493_openapi_security.py
  - apps/api/tests/test_bots_read_authz.py
  - apps/api/tests/test_sec006_sql_param_surface.py
  - apps/api/tests/test_auth.py
最后核验 commit: bf141d5（2026-10-23 现读）；实现度于 2026-10-29 STEP-62 按 EVD-V21-49 / EVD-V21-50 重判
---

# REQ-NF-002 安全

## 需求条目逐条对表

| 条目 | 实况 | 锚 |
|---|---|---|
| SSO Cookie HttpOnly + SameSite=Lax | 已实现：HttpOnly 与 `samesite=lax` 均有断言（SEC-006 于 STEP-49 补齐后半；断言大小写不敏感，因为 Starlette 按入参原样回写） | `test_auth.py`（HttpOnly；`samesite=lax` 断言见该文件 S49.1 注释的那条 `re.search`） |
| 渠道密钥 AES-256-GCM 加密落库 | 已实现（fail-closed，双主密钥纳入生产守卫） | `test_extra_config_crypto.py`、`test_channel_update_extra_config_encrypted.py`、`test_production_config_guard.py` |
| 生产环境 OIDC iss/aud 校验 | 已实现 | `test_production_config_guard.py`、`test_backchannel_logout.py` |
| ~~CORS 白名单~~ → **经 `next.config.mjs` 同源 rewrites 达成，无 CORS 中间件** | 达成方式与原文本不符，非漏实现 | 见下节 |
| SQL 注入防护（ORM 参数化） | 已实现（结构 + 机检）：结构上是 SQLAlchemy 参数化且无字符串拼 SQL 的入口，机检用例盯住该面的调用点 | `apps/api/tests/test_sec006_sql_param_surface.py`（SEC-006，先红读数 `docs/06_validation/evidence/EVD-V21-49/s49_1_red.txt`，调用点清单 `s49_2_callsites.txt`） |

## CORS 这一条改写的依据（S17.1.2 / 冲突 C-3）

现读 `apps/api/app`：`CORSMiddleware` 与 `allow_origins` 命中数 **0**。
唯一说明在 `apps/api/app/core/security.py` 的 `SecurityHeadersMiddleware` docstring：
「**不含 CORS**——前端经 `next.config.mjs` rewrites 同源代理 `/api/v1/*`，
浏览器从不跨域直连后端；加 `Access-Control-Allow-Origin` 只扩大攻击面。」

⇒ 需求文本按实况改写为"同源 rewrites 达成，无 CORS 中间件"，并且**不排 CORS 开发任务**
（C-3 的裁决就是禁止把这条重新立项）。锚点行号取现读：`apps/api/app/core/security.py` 的该 docstring
（卡面原引 `security.py:440` 已漂移：现读 `apps/api/app/core/security.py:440` 是 `code=PAYLOAD_TOO_LARGE_CODE`）。

## 原「无锚项」的处置结果（STEP-62 现读）

`docs/04_engineering/backlog.md` 里的 SEC-006（SQL 注入面无机检）由 STEP-49 **已实现并收口**——
先红读数 `docs/06_validation/evidence/EVD-V21-49/s49_1_red.txt`，落地后调用点清单 `s49_2_callsites.txt`，
本文件两条表项已随之改成「已实现」。同批的 STACK-001（技术栈版本一致无机检）由 STEP-50 收口
（`docs/06_validation/evidence/EVD-V21-50/`，含先红 `s50_1_old_blind.txt`），见
`../constraints/REQ-C-001-tech-stack.md`。

⇒ 本条**不再有「无锚项」**。原句「两条都标 ⬜ 未开始，不冒充已完成」在写入时是真的，
2026-10-29 现读时两条均已收口，故该句作废。
