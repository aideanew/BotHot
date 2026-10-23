---
id: REQ-F-007
type: requirement
title: SSO 统一认证
status: active
owner: product
实现度: 已实现（判词限「命题范围」，见正文那条限定）
验收锚:
  - apps/api/tests/test_r19_sso_session.py
  - apps/api/tests/test_auth.py
  - apps/api/tests/test_backchannel_logout.py
  - apps/api/tests/test_session_store_redis.py
  - apps/api/tests/test_r11_roles.py
  - apps/api/tests/test_require_roles_single_arg.py
  - apps/api/tests/test_idor_matrix.py
  - apps/web/tests/auth-gate.spec.tsx
  - apps/web/tests/callback.spec.tsx
  - apps/web/e2e/auth-gate.spec.ts
最后核验 commit: c687a33（2026-10-22，STEP-19 收口判「已确认（命题范围）」）
---

# REQ-F-007 SSO 统一认证

## 需求条目

- OIDC 接入主平台
- 身份锚点 = `users.sub`（余额/等级从不持久化，实时查主平台）
- 会话 Cookie（HttpOnly + SameSite=Lax）
- 角色门禁（admin / operator / user）
- Backchannel Logout
- **验收**：SSO 登录/登出正常，角色门禁生效

## 实现度判据

| 判据 | 出处 |
|---|---|
| 会话 Cookie：HttpOnly 有断言 | `test_auth.py:273` 断 `HttpOnly`；`SameSite=Lax` 在 `apps/api/app/api/v1/auth.py:98` 设定，但**无测试断言**（缺口，另见 REQ-NF-002） |
| 登出后服务端会话真失效 | `test_r19_sso_session.py`、`test_backchannel_logout.py` |
| 角色门禁语义 | `test_require_roles_single_arg.py`（`require_roles` 是 **max()** 不是 min()）、`test_r11_roles.py`；越界面由生成的 `test_idor_matrix.py` 覆盖 |
| 身份锚点 | `AGENTS.md` 关键约束第 2 条 + `users.sub` 唯一约束 |

## 「命题范围」这个限定是什么意思

STEP-19 的判词写的是「已确认（命题范围）」——即**在本仓可验证的命题内**已确认：
与主平台真实的 OIDC 端到端握手（对方白名单、真实回跳）不在本机与 CI 的可达面内，
需要主平台配合的白名单登记（见 `docs/04_engineering/backlog.md` TEST-002 的 real-backend 三项前置）。
所以这一条是"已实现 + 一个外部前置未验"，不是无条件达标。
