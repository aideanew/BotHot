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
