---
id: REQ-C-001
type: requirement
title: 技术栈
status: active
owner: product
实现度: 部分（实值与门面文本今天一致，但一致性本身无机检；本卡就是把一处失效的引用改回来）
验收锚: 无
最后核验 commit: bf141d5（2026-10-23 现读）
---

# REQ-C-001 技术栈

## 需求条目与**现读实值**（版本号一律以实跑代码为准，不沿用文档旧值）

| 项 | 门面声明 | 实值锚（现读） |
|---|---|---|
| 后端语言/框架 | Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic | `apps/api/pyproject.toml:5` `requires-python = ">=3.11,<4.0"`；CI 钉 **3.12**（`.github/workflows/ci.yml` 的 `python-version: "3.12"`）⇒ 声明与 CI 一致，与 `requires-python` 的下界是"允许更宽"关系 |
| 前端框架 | Next.js 15 + React 19 + TypeScript + Tailwind + pnpm | `apps/web/package.json:27` `"next": "^15.5.28"`、`:28` `"react": "^19.0.0"` |
| Node 运行时 | 24 | `apps/web/.nvmrc` = `24.21.0`、`apps/web/package.json:7` `"node": ">=24.0.0"` |
| 数据库 | PostgreSQL 16 | `scripts/test-env.sh` 与 compose 的镜像tag（`postgres:16-alpine` 系） |
| 缓存 | Redis 7 | 同上（`redis:7-alpine` 系） |
| 知识引擎 | LangBot | `AGENTS.md` 后端段 + `apps/api/app/providers/langbot/`（包） |
| 容器 | Docker Compose | `docker/compose.yml` |

## 本卡改掉的一处失效引用（不是可选的润色）

`docs/02_requirements/product-requirements.md` 与 `AGENTS.md` 都写着
`"next": "^15.5.24"`（引 `apps/web/package.json:27`）。该 spec 在 2026-10-23 的 <!-- stack-history -->
依赖安全补丁批里升到 `^15.5.28`（next 公告，见台账 P-99）⇒ **两处引用当场失效**。
REQ-C-001 自己的判据就是「门面文本与实值一致」，所以这两处是本卡必须修的项，
不是顺手润色。历史规划文档（`docs/任务规划V0.1.0/**` 等）里的旧值属禁止改写面，保持原样。

## 无锚的替代机制

版本一致性目前靠**人读 + 冲突登记史**（X-02 就是这类漂移的一次更正），没有机检。
已进 backlog **STACK-001**：给「门面声明 ↔ `package.json`/`pyproject` 实值」做一道
门（形态与 `check_docs_consistency` 同族），未开始。
