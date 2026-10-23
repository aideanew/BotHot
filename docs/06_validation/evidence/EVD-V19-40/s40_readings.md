# EVD-V19-40 日志出口凭据遮蔽（规划方执行）

平台 @linux（规划方沙箱，Debian aarch64，Python 3.12），基线 main@9c66add，时间 2026-10-23（Asia/Shanghai）。
所有随机值运行时生成；本文件不含任何凭据或令牌原值。

## 1. 先红（问题存在）
- 探针：装配本项目日志后，用 httpx 发一个 query 带随机令牌的请求 ⇒ handler 输出 1 行 `HTTP Request: GET https://…?token=<令牌>`，"令牌在日志里" = True。
- 用例反证：去掉 `app/core/logging.py` 里 formatter 处理器链末尾的 `redact_rendered`，跑 `tests/test_log_redaction.py` ⇒ **8 failed / 7 passed**。红的 8 条 = 钉钉、企业微信、飞书三家真推送 provider 与 HTTPStatusError 警告/异常栈，各 console、json 两遍。还原后 15 passed。

## 2. 改动摘要
- 新增 `apps/api/app/core/log_redaction.py`：`redact_text()`（query/片段整段省略；绝对 URL 中 ≥16 位令牌形或 UUID 形路径段遮蔽；主机保留）+ `redact_rendered()`（挂在渲染器之后，入参为整行字符串）。
- `apps/api/app/core/logging.py`：formatter 处理器链末尾 +1。
- `apps/api/app/core/audit.py`：`path_params` 改走 `_safe_path_params()`（UUID 或 ≤15 位短标识符保留，其余遮蔽）。
- 新增 `apps/api/tests/test_log_redaction.py`（15 条）。

## 3. 改后读数（@linux）
| 项 | 读数 |
|---|---|
| `ruff check app tests` | All checks passed |
| `mypy app` | Success: no issues found in 121 source files |
| `pytest tests/test_log_redaction.py tests/test_audit_log.py` | 全绿 |
| 后端全量（开覆盖率） | **2320 passed / 5 skipped / 4 deselected / 0 failed**，187.11s，覆盖率 88%（基线 2305/5/0，+15 = 本卡新用例） |
| `check_module_coverage.py` | 全部模块与全局达标（TOTAL 88.26% ≥ 79.0%） |
| `log_redaction.py` / `audit.py` / `logging.py` 行覆盖 | 93% / 93% / 89% |
| `gen_contracts.py --check`、`check_docs_consistency.py` | 通过 |
| `guard-ports` / `guard-structure` / `guard-versions` / `guard-ci-secret-mask` | rc=0 |

## 4. 过程中的一次失误（如实记录）
首轮全量 **1 failed**：`test_manifest_asset_alignment.py::test_null_key_manifest_waits_for_backfill_and_is_counted`（`capture_logs` 收不到事件）。
原因：新用例的夹具在还原时调用 `structlog.reset_defaults()`/重新 configure，换掉了 processors 列表对象；更早用例里已缓存的 logger 绑的是旧列表，`capture_logs` 就地改的是新列表 ⇒ 失明（P-63 同族）。
处置：夹具改为保存并原样还回 `structlog.get_config()`（同一列表对象）、root handler 与级别。复跑全量 0 failed。单跑两文件时这个问题不出现，只有全量顺序能暴露。

## 5. @ci（推送后回填）
见本目录 `s40_ci.md`（规划方推送后填写）。

## 6. 独立复查
由执行助手在 STEP-42 S42.1 做，结论写 `s40_review.md`。
