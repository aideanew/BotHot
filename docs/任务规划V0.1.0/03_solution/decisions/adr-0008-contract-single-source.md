---
id: ADR-0008
type: decision
title: 契约唯一源 = 后端 Python 代码，TypeScript 契约一律生成
status: proposed
owner: architecture
created: 2026-10-12
updated: 2026-10-12
related: [CURRENT-PLAN-20261012, DESIGN-001]
---

# ADR-0008：契约唯一源 = 后端 Python 代码

## 背景（证据）
- `packages/contracts/src/common/errors.ts` 为手写，已与后端漂移：缺 10007/10008（`apps/api/app/core/errors.py:19-23`）。
- `errors.py` 自身登记表缺 50003，而 `ConfigurationError.code = 50003`（`errors.py:222-225`）。
- 前端 `apps/web/lib/api/http.ts:26-46` 另有一份错误表，缺 8 个后端码、多 5 个后端不存在的码。
- 域 DTO 是实体镜像，不是 API 响应形状（`packages/contracts/src/index.ts` 头注）。
- `scripts/gen_contracts.py --check` 已是 CI 门禁（`ci.yml:97-98`），但不覆盖 errors.ts 与响应形状。

## 决定（提议）
1. 错误码唯一源 = `apps/api/app/core/errors.py`（`ERROR_CODES` + 子类 `http_status`）。
2. 请求/响应形状唯一源 = FastAPI `create_app().openapi()` 的 `components.schemas`（Pydantic 模型）。
3. 实体镜像沿用 SQLAlchemy 内省。
4. `packages/contracts/**` 全部由 `scripts/gen_contracts.py` 生成，带「请勿手动修改」头，`--check` 覆盖全部产物。
5. 前端码表以 `satisfies Record<ApiErrorCode, string>` 约束，新增后端码而前端未补 → 编译失败。

## 备选与否决理由
- 以 OpenAPI YAML 手写为源：与 FastAPI 自动生成形成双源，否决。
- 以 zod 为源：需要在后端引入 TS 运行时或反向生成 Pydantic，改动面过大，否决。
- 维持手写 + 单测比对：可行但只能发现漂移、不能阻止；作为 D-09 否决时的退路。

## 影响
- 新增任务：TASK-006/007/008（错误码）、TASK-012…015（bot/hot 响应形状）。
- 线上 JSON 形状不变（快照测试守护）。

## 前提与局限
- 只覆盖 bot/hot 两域响应形状；其余域后续按同模式扩展。
- 若某端点形状无法用 Pydantic 表达而不改线上值，该端点保持现状并登记。
