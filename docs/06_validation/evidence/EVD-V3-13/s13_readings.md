# STEP-13 可插拔引擎能力面收敛（规划方，2026-10-20，基线 25088c4）

- 契约：新冻结稿 `docs/任务规划V0.12.0/contracts/engine.schema.json`（`EngineReason` 四值 + `EngineCapability`），唯一源 `apps/api/app/contracts/engine.py`，产物 `packages/contracts/schemas/engine.schema.json`；两套契约比对（旧比对器 + jsonschema 探针等价）全绿。
- 设计：`reason` 只报首要原因，顺序 = 谁能解决：未开放（管理员）→ 缺 Key（管理员）→ 未实接（开发排期）。builtin 恒 ok。`available ⇔ reason=ok`。
- 实现：`engines.py` 新增 `_engine_reason`，`GET /engines` 的 `reason`、`_engine_available`、切换校验 `assert_engine_switchable` 三处都读它；拒绝仍是 403/10004，文案标记词 `REFUSAL_MARKERS` 与 reason 一一对应。原因判定里不写引擎名，实接与否只认 `ENGINE_IMPLEMENTED`。
- 先红：`01_red.txt` 41 failed / 2 passed（缺 `reason` 字段、缺标记表）。
- 变异反证：`02_mutation.txt`，对调"未开放/缺 Key"两条判断 ⇒ 4 failed；还原 43 passed。
- 骨架基线：`engine_port.py` 里 `NotImplementedError` = 16，测试钉"只降不升"。
- 文档：REQ-F-003 增"实现度"小节（引擎位名单按代码更正：原文写的 langbot / aidean / redfox 不是现有引擎位）；backlog 增 TECH-003b。
- 无迁移、未改 `engine_port.py`、未改前端（前端展示 reason 归 STEP-15/14b，由执行助手做）。
- 本机真库全量 1953 passed / 5 skipped / 0 failed；ruff、mypy、gen_contracts --check 全绿。
