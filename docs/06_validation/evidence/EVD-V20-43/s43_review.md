# EVD-V20-43 STEP-43 独立复查（STEP-44 S44.1，执行助手）

- 复查者：执行助手（Agent-Doc，非规划方）；对象：`17c3f13`（STEP-43 日志异常栈）的 diff 与运行结果。
- 平台 @win（本机 `apps/api/.venv`，Python 3.12.10，**venv 里装有 rich 15.0.0**——恰好是 P-114 的触发条件），时间 2026-10-24（Asia/Shanghai）。

## 结论：**PASS**

1. diff 只动 `app/core/logging.py`（json 链渲染前插 `format_exc_info`；console 的 `ConsoleRenderer`
   显式 `exception_formatter=plain_traceback`）与 `tests/test_log_redaction.py`（+3 条）；
   遮蔽处理器 `redact_rendered` 仍在处理器链最后（STEP-40 的语义未被移动）。
2. 改后读数（本机现跑）：`pytest tests/test_log_redaction.py` ⇒ **18 passed**——且本机 rich 在场，
   console 钉了纯文本栈后 P-114 的触发条件被消除（18 绿 = 有无 rich 均绿的 planner 判词在本机复现）。
3. 反证（卡面命令：临时把 `logging.py` 还原到 v1.1.1（`75b212b`）版本跑同一命令）：
   **4 failed / 14 passed**——`test_exception_keeps_stack_and_never_shows_frame_locals[json]`
   （P-115：JSON 无栈）、console locals 两发（P-114）、`test_console_renderer_pins_plain_traceback`
   全部红，与 s43_readings.md §3 的读数同形；还原后 18 passed、`git diff` 空。
4. 先红读数与全量（2323 passed / 0 failed、覆盖率 88.23%）由规划方记录于 `s43_readings.md` §3/§4；
   本机独立复算与之一致（18 passed 子集）。
