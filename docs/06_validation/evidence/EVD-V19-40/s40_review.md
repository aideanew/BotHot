# EVD-V19-40 独立复查（STEP-42 S42.1，执行助手）

- 复查者：执行助手（Agent-Doc，非规划方）；对象：`1acd123`（STEP-40 S40.2 第 1 轮）的 diff 与运行结果。
- 平台 @win（Windows 10 x64，本机 `apps/api/.venv`，Python 3.12.10），时间 2026-10-23 23:0x–23:2x（Asia/Shanghai）。
- 本机无 docker CLI、5547 无监听 ⇒ 连库面（`test_audit_log.py` 29 条）本机未复算，以 @ci 为准。

## 结论：**PASS**

理由（对照卡面判据，逐条）：
1. diff 只动卡面允许的四个文件：新增 `app/core/log_redaction.py`、`tests/test_log_redaction.py`（15 条），`logging.py` formatter 处理器链末尾 +1，`audit.py` `_safe_path_params`；未触碰冻结契约、迁移、provider 本体。
2. 先红独立复现：本机临时摘掉处理器链里的遮蔽处理器并还原（改动已用 git restore 还原、`git diff` 为空）⇒ 恰好 8 条红（钉钉、企业微信、飞书三家真推送 provider 与 HTTPStatusError 警告/异常栈，console、json 各一遍），其余 8 条绿；与规划方 s40_readings.md §1 的 8 红/7 过（遮蔽文件内）一致。
3. 改后绿（锁文件等价环境）：`pytest -q tests/test_log_redaction.py tests/test_audit_log.py` ⇒ **16 passed / 29 skipped / 0 failed**（15 条遮蔽用例 + 审计文件 1 条不连库用例全绿；29 条连库用例因本机无测试 PG 跳过，`AIDEANBOT_TEST_PG_DSN 未设置`，非"不可达"异常）。
4. `ruff check app tests` All checks passed；`mypy app` Success: no issues found in 121 source files（本机 @win 复算）。
5. @ci 独立核实（GitHub REST 现读，非抄证据文件）：head `1a622af` 上 Security 39971776622 / CI 39971776546 / CI-Windows 39971776553 三条 completed success，attempt 1 —— 与规划方 s40_ci.md 读数逐项一致。
6. 已知边界核实：绝对 URL 中 UUID 形资源段也会被遮、相对路径只省 query 不遮段、主机名保留——卡面"已知边界"三条与实现一致，未见越界遮蔽排障信息。

## 复查中发现的本机环境红（不属于 STEP-40，登记 P-114，不顺手修）

- 现象：本机 venv **装着 rich 15.0.0** 时（未加隔离直接跑），`test_http_status_error_url_in_warning_is_redacted[console]` 红：console 渲染器把**栈帧局部变量**（测试函数自己的局部令牌值）打进日志，遮蔽函数按设计只管 URL，不管这种路。
- 机制：structlog 26.1.0 的 `RichTracebackFormatter.show_locals` 默认开启；仅当 rich 可导入时生效。`rich` **不在 `uv.lock`、不在 `pyproject.toml`**（本机 venv 里是 pip_audit 的传递依赖）；CI 按锁安装 ⇒ 无 rich ⇒ 用例绿（CI-Windows 也是绿的，佐证与平台无关）。
- 等价环境复算：前置一个"import 即失败"的 rich 替身目录到 `PYTHONPATH`（等价于锁文件环境无 rich，未动 venv 本体，跑完即删）⇒ 16 passed / 0 failed。
- 判定：锁文件约束的部署环境不可达此路径，不构成 STEP-40 的 FAIL 依据；但"开发机 venv 多装了 rich 时凭据形局部变量会进 console 日志"是真实存在的环境敏感面，登记 P-114（见 P 表），建议归属后续硬化（例如 CI 增加依赖面一致性守卫，或遮蔽面覆盖 locals 展示）。

## 反证命令与读数（@win，2026-10-23 Asia/Shanghai）

| 步骤 | 命令（`cd apps/api`） | 读数 |
|---|---|---|
| 基线（rich 在场，未隔离） | `python -m pytest -q tests/test_log_redaction.py tests/test_audit_log.py` | 1 failed / 15 passed / 29 skipped（红的那条见上节） |
| 锁等价（rich 替身隔离） | `PYTHONPATH=<shim> python -m pytest -q …（同上）` | **16 passed / 29 skipped / 0 failed** |
| 反证：摘遮蔽处理器 | 同上（临时删 `redact_rendered` 后） | **8 failed / 8 passed / 29 skipped**，红的 8 条名单与判据一致 |
| 还原 | `git restore app/core/logging.py` | `git diff` 空，工作区干净 |
| 静态 | `python -m ruff check app tests`；`python -m mypy app` | All checks passed；Success: 121 files |
