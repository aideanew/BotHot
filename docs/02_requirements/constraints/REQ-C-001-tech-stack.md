---
id: REQ-C-001
type: requirement
title: 技术栈
status: active
owner: product
实现度: 已实现（STEP-62 现读 2026-10-29）：门面声明与实值的一致性由常驻门维持——`scripts/check_docs_consistency.py` 的 STACK-001 段（STEP-50 收口，证据 `docs/06_validation/evidence/EVD-V21-50/`，含先红 `s50_1_old_blind.txt`），不一致即红；原「一致性本身无机检」一句作废
验收锚:
  - scripts/check_docs_consistency.py
最后核验 commit: bf141d5（2026-10-23 现读）；实现度于 2026-10-29 STEP-62 按 EVD-V21-50 重判
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

## 替代机制已变成常驻门（STEP-62 现读，原「无锚的替代机制」作废）

原状是「版本一致性靠人读 + 冲突登记史」，已进 backlog **STACK-001** 等做门。**STEP-50 已把它做出来**：
`scripts/check_docs_consistency.py` 的 STACK-001 段把门面里的 `"key": "^x.y.z"` 声明与
`apps/web/package.json` / `apps/api/pyproject.toml` 实值逐键比对，不一致即红；先红读数
`docs/06_validation/evidence/EVD-V21-50/s50_1_old_blind.txt` 记的是门之前「两处旧值无人报警」的样子。
backlog 侧该条已翻 ✅（`docs/04_engineering/backlog.md` 的 STACK-001 段）。

限定读法：这道门只比**声明里的版本号**，不比 `AGENTS.md` / 本文件里所有人读的叙述句——
「门面文本」在判据里的含义就是可被解析的那几个版本字段。
