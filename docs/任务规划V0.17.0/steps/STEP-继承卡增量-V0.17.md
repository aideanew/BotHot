# 继承卡增量（V0.17.0，基线 main@81205f1）

原卡面仍然有效，本文件只写变化（D-V11-07）。

## 转给执行助手的卡（D-V17-01）
| 卡 | 原执行者 | 新执行者 | 档位 | 变化 |
|---|---|---|---|---|
| STEP-19 已实现未纳管域验证 | 规划方 | 执行 Agent-API | sonnet | 只换执行者；卡面不变 |
| STEP-15 前端契约层与真实后端对齐 | 规划方 | 执行 Agent-Web | sonnet | **+1 项 S15.V17.1**：`EngineSwitcher`（及调用 `GET /engines` 的地方）按 `reason` 显示原因：`not_allowlisted` → "未开放，请联系管理员"、`key_missing` → "未登记 API Key"、`not_implemented` → "暂未接入"，`ok` 才可选。类型按 `packages/contracts/schemas/engine.schema.json` 写，不手写字符串联合以外的取值。依赖改为 01、13 |
| STEP-15b 前端默认真实后端 + e2e 去手写 mock | 规划方 | 执行 Agent-Web | sonnet | **+1 项 S15b.V17.1（P-47）**：`/admin/ops` 引擎密钥面板对 operator 隐藏"登记 / 撤销"按钮，只读显示状态；admin 照常。判据：vitest 两个角色各一条用例 |
| STEP-14b 管理端四屏 UI | 规划方 | 执行 Agent-Web | sonnet | 只换执行者。余 3 项（告警条、采集配置页等）沿用现有组件与 `LoadingErrorShell`，不新造设计体系 |
| STEP-12 文档对账证据汇总与发布 | 规划方 | 执行 Agent-Doc | sonnet | 只换执行者；依赖加 30、31；**发布与否由用户拍板**，执行助手只出对账与证据汇总 |

## 已完成（规划方，2026-10-20）
| 卡 | 提交 | 读数 | 复查 |
|---|---|---|---|
| STEP-21 | c93a6bc / 1834c4a / bec5225 | @ci 三绿；47 个带参操作全部归类 | STEP-30 S30.1 |
| STEP-01 | 25088c4 | 本机真库 1902 / 5 / 0 | STEP-30 S30.2 |
| STEP-13 | 81205f1 | 本机真库 1953 / 5 / 0 | STEP-30 S30.3 |

## 其他卡需要知道的契约变化
- 冻结稿新增 `engine.schema.json`（STEP-13），`api.envelope.schema.json` 的 `$id` 改为 `bothot://contracts/api.envelope/v1`、三个分页壳提升为 `definitions`（STEP-01）。生成物多了 `api.envelope.schema.json`、`engine.schema.json` 两份。
- 新增 dev 依赖 `jsonschema==4.25.1`：本机老环境要重装 `pip install -e ".[dev]"`，否则 `tests/test_contract_jsonschema.py` 收集期报错。
- 引擎 Key 登记 / 撤销只给 admin（D-V16-06）；`GET /admin/engines/keys` 仍是 operator。
- 新增连库用例的卡，必须同步抬 `ci-windows.yml` 的 `SKIP_BASELINE_WIN`（测量值，不留余量）——规划方在 1834c4a 上漏过一次。

## STEP-26 改卡（D-V17-03，2026-10-20 14:40，执行助手停卡后裁决）
- **S26.2.2 改为**：统一为"先 `db.add(log)` 与计数、后 `persist_web_notification`、再 `commit`"。调度器 `push_scheduler.py::_execute_task` 里的调用整段下移到计数之后；两处直投（run-now、test-push）已是此顺序，不动代码。把这条写进 `persist_web_notification` docstring 作为唯一约定。
- **新增 S26.2.4 失败路径测试**（新建 `apps/api/tests/test_push_persist_order.py`，连库）：三条路径各一条，monkeypatch 让通知落库抛错 ⇒ 断言 PushLog 行存在、`total_push_count`/`success_push_count` 已加、通知行不存在、接口/任务不报错。先在改前跑一次留红/绿读数（调度器那条改前也可能绿，如实记录），改后全绿。
- **允许修改追加**：`push_scheduler.py` 中该调用的位置（只移动这一处调用及其上方注释）；`apps/api/tests/test_push_persist_order.py`（新）；`bots.py` 第 513–518 行那段注释（**只有**当新测试证明"savepoint 回滚会连带撤销未 flush 的 PushLog"与实测不符时，改成实测结论；代码一行不动）；`.github/workflows/ci-windows.yml` 的 `SKIP_BASELINE_WIN`（新增连库用例，按实测值抬）。
- **仍然禁止**：改 `persist_web_notification` 函数体与异常吞没、改计数器语义（属 STEP-05）、改 bots.py 任何代码。
- 其余 S26.1.1 / S26.2.1 / S26.2.3 / S26.3 照原卡执行；S26.3.1 的 `persist_web_notification(` 计数口径不变（仍 4 处）。

## STEP-07 改卡（D-V17-04，2026-10-21 12:45，用户授权后由执行方代录）

背景：`S07.V15.1` 两轮 `@ci` FAIL 后按指令熔断交回（`EVD-V17-07` §6.3），待裁定的只有"演练族把
`--allow-hosts` 写成字面量 host"这一处。用户 2026-10-21 授权重开；因 D-14 的机器门把"主题写出第 ≥3 轮"
本身判红且无"已升级"通道（登记 `§4 P-56`），按 D-14 列出的出路「重写任务书」换号落地。

- **新增 S07.V15.1-R（授权重开，等价于 `S07.V15.1` 的第 3 轮）**：三处 `p39.main` 调用的
  `--allow-hosts` 一律由被测 DSN 推导（`p39.host_of(dsn)`）；`prod-db.internal` 这个**故意不等于任何真实
  host** 的拒绝哨兵保留字面量。
- **新增两条防复发判据**（都不连库，因此 `@win` 与 `@ci` 同形）：① host 形状参数化（`127.0.0.1` /
  `localhost` / `db.internal` / `postgres`）断言"门跟着 DSN 走、对非 DSN host 必须拒绝"；
  ②AST 门钉住本文件所有 `--allow-hosts` 调用点的形态与总数（3 派生 + 1 哨兵 + 总数 4）。
- **允许修改**：`apps/api/tests/test_audit_scripts.py`（只动演练族的白名单实参与新增用例）。
- **仍然禁止**：改 `scripts/audit/**` 的任何判据（只读门、目标门、回读校验、幂等）、放宽 `apply_allowed`、
  改 `SKIP_BASELINE_WIN`（本轮实测不新增 skip，仍 578）。
- 卡面上 `S07.V15.2` / `S07.V15.3` 与其余项照原卡；本增量的轮次账记在 `S07.V15.1-R` 名下，
  但**证据与记录里必须写明它是第 3 轮**——换号是为了让机器门可表达"已升级"，不是为了改写事实。
