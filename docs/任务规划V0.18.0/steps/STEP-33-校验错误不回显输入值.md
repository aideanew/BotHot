# STEP-33 校验错误不回显输入值

> 基线 main@f86811e｜状态：⚪ 未开始｜版本 V0.18.0

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行 Agent-API |
| 2 验收者 | 规划方 |
| 3 难度 / 里程碑 | 低 / M4 发布阻断 |
| 4 来源 | P-62；D-V18-05 |
| 5 目标 | 任何 422（10005）响应与日志里都不出现调用方提交的值，只出现字段路径、错误类型与原因 |
| 6 输入 | `apps/api/app/main.py:124-128`；`app/services/system_settings.py` 的 `_readable()`（已是正确形状，可复用） |
| 7 输出路径 | `apps/api/app/main.py`（只改校验处理器）、可选新增 `app/core/validation_message.py`、`apps/api/tests/test_validation_no_echo.py`（新）、`docs/06_validation/evidence/EVD-V18-33/`（D-V18-13） |
| 10 命令 | `cd apps/api && pytest tests/test_validation_no_echo.py -q`；全量 `pytest -q -rs -m "not perf"` |
| 12 允许修改 | 第 7 格所列；现有断言 10005 文案原文的用例只许改期望文案，不许删用例 |
| 13 禁止修改 | 错误码表、信封结构、`packages/contracts/**` |
| 14 依赖 | 32 合入后开工（串行，避免两张阻断卡同批） |
| 15 档位 | sonnet |
| 16 规模 | ≈0.4 人日 |

## 三级任务
1. [ ] **S33.1** 先红：新用例对三个代表端点（`PUT /api/v1/admin/discovery/config`、`PUT /api/v1/admin/categories`、任一用户域 POST）提交带凭据形假值（运行时随机生成，源码里不写凭据形字面量）的非法请求，断言响应体与 `caplog` 全文都不含该值——改前必须红
2. [ ] **S33.2** 校验处理器改为只拼 `loc`（点号连接）+ `type` + `msg`；`msg` 里若含输入值（pydantic 某些类型的 msg 会内插），一律用类型对应的固定原因替换；不读 `input`、不读 `ctx`
3. [ ] **S33.3** 全量回归；把所有因文案变化而改期望的用例逐条列进证据（文件:行、旧期望、新期望）

## 完成判据（全部机器可判）
- S33.1 改前红、改后绿的两次读数
- `grep -n "exc.errors()" apps/api/app/main.py` 里不再把错误字典整体格式化进 message
- 全量 0 failed；三绿

## 熔断
连续 2 轮验收 FAIL ⇒ 停卡交回规划方（rounds-check 机器执行，口径见 D-V18-16）。前提与现读不符 ⇒ 先登记 P 号再停，不自改卡面。
