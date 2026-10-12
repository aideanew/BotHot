---
id: ADR-0009
type: decision
title: 访客（未登录）访问策略
status: proposed
owner: architecture
created: 2026-10-12
updated: 2026-10-12
related: [CURRENT-PLAN-20261012]
---

# ADR-0009：访客访问策略（待裁决 D-01）

## 背景（证据，互相矛盾）
- `apps/web/middleware.ts:14-15`：真实构建只放行 `/` 与 `/auth*`，其余无 cookie 一律 302 到 `/`。
- `middleware.ts:26`：mock 构建下 middleware 短路；CI e2e 只跑 mock 产物，真实态 302 无自动化覆盖。
- `apps/web/e2e/auth-gate.spec.ts:10`：注释称「/hot 游客可浏览」，但 `2766d17` 已给 hot 与 hot/daily 加 AuthGate；`/public` 在受保护矩阵中。
- CHANGELOG Unreleased：「middleware 裁定不实施」「公共引流位（公共库/热点/空间/问答）保持可见」——与现代码不符。
- 后端：`/api/v1/hot/*` 路由级要求登录（`hot.py:45`）；`/api/v1/spaces/public` 要求登录。

## 选项
| 选项 | /hot、/hot/daily | /public | 真实态未登录行为 | 后端改动 | 风险 |
|---|---|---|---|---|---|
| A | 需登录 | 需登录 | 302 到 `/`（承认现状，写入契约） | 无 | 引流位失效 |
| B | 游客可看 | 需登录 | 受保护页 302；hot 页原地渲染 | hot 读接口开放匿名 + 限流 + 字段裁剪 | 匿名读扩大攻击面 |
| C | 游客可看 | 游客可看 | 同 B | hot 与 public 读接口都开放匿名 | 同上，范围更大 |

无论选哪项，都必须：补真实态 middleware 单测（TASK-010）；修正 CHANGELOG/backlog/e2e 注释（TASK-011）。

## 决定
（待人工裁决后填写。）

## 前提与局限
- middleware 只判 cookie 存在，过期 cookie 会穿透到 AuthGate 由前端兜底，此行为各选项一致。
