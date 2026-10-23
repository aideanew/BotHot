# EVD-V20-43 STEP-43 日志异常栈 · 规划方读数

- 平台 @linux（沙箱，Python 3.12.15，structlog 26.1.0，PG16@5547 新建库，迁移到头），2026-10-24 00:13–00:25（Asia/Shanghai）
- 基线：main@75b212b

## 1. 复现（修前）
探针：一个函数把随机令牌形值当参数后抛错，分别经 structlog 原生 logger 与标准库第三方 logger 的 `.exception()` 写日志。
| 模式 | rich | 局部值进日志 | 带栈 |
|---|---|---|---|
| console | 无 | 否 | 是 |
| console | 有（装到临时目录经 PYTHONPATH 注入） | **是**（P-114） | 是 |
| json | 无/有 | 否 | **否**：原生行只有 `"exc_info": true`，第三方行是三元组 repr（P-115） |

## 2. 修改
`app/core/logging.py`：console 的 `ConsoleRenderer` 显式 `exception_formatter=structlog.dev.plain_traceback`；json 模式在 formatter 处理器链 `remove_processors_meta` 之后、渲染器之前插入 `structlog.processors.format_exc_info`。遮蔽处理器 `redact_rendered` 仍在最后。
`tests/test_log_redaction.py` 追加：`test_exception_keeps_stack_and_never_shows_frame_locals[console|json]`、`test_console_renderer_pins_plain_traceback`（共 3 条）。

## 3. 先红 / 反证（把 logging.py 临时还原为 75b212b 版本，跑完复原）
| 环境 | 读数 |
|---|---|
| 旧代码、无 rich | 1 failed / 17 passed：`…frame_locals[json]`（无栈） |
| 旧代码、有 rich | 4 failed / 14 passed：`test_http_status_error_url_in_warning_is_redacted[console]`、`…frame_locals[console]`、`…frame_locals[json]`、`test_console_renderer_pins_plain_traceback` |
| 新代码、无 rich | 18 passed |
| 新代码、有 rich | 18 passed |

## 4. 回归
| 项 | 读数 |
|---|---|
| 后端全量（开覆盖率） | **2323 passed / 5 skipped / 4 deselected / 0 failed**，195.31s；覆盖率 TOTAL 88.23%（≥79.0%） |
| `ruff check app tests` | All checks passed |
| `mypy app` | Success（121 files） |

过程失误如实记录：第一次全量开跑时没先确认 PG 在线（沙箱重启丢了 `/tmp` 下的数据目录），跑到 37% 发现异常缓慢，中止；重建 PG 后重跑得上表读数。

## 5. 待回填
- @ci 三绿：`s43_ci.md`（规划方）
- 独立复查：`s43_review.md`（执行助手，STEP-44 S44.1）
