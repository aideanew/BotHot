# EVD-V21-49 SQL 参数化面与 SameSite 断言（执行助手）

平台 @win（便携 PG16.15@5547），开工 head `32c2b7d`（STEP-48 收口批），时间 2026-10-24～25（Asia/Shanghai）。

## S49.1 SameSite=Lax 断言（先红 → 绿）

- 断言落在 `test_auth.py:277`（登录全流程用例内，紧邻原 HttpOnly 断言）：
  `re.search(r"samesite=lax", cookie, re.IGNORECASE)`——大小写不敏感。
- **先红**：临时把 `auth.py` 的 `samesite="lax"` 改 `"strict"` ⇒
  `test_full_login_flow_establishes_session_and_me` **FAILED**，原文（含
  `SameSite=strict` 回显与断言位置）存 `s49_1_red.txt`；还原 lax 后该用例 **1 passed**。
- 过程失误如实记：加 `import re` 的脚本把 import 行插进 `from __future__` 语句中间，
  造成两轮 collection error 后修正——与判据无关，最终文件 `ruff` 通过（见下）。

## S49.2 SQL 参数化面 AST 门

- **调用点清单（S49.2.1，AST 现读）**：`app/**` 内 `text()/sa_text()/sqlalchemy.text()`
  共 **12 处**（清单 `s49_2_callsites.txt`：system.py:105、alerting.py×3、metrics.py:278、
  schema_guard.py:43、db.py:124、entities.py×3、process_heartbeat.py:123/150）。
  规划方 grep 读数 39 处含 `richtext(` 一类字面误匹配——AST 口径是 12，护栏按 10 设地板
  （扫描器失明即红）。
- **门本体**：`tests/test_sec006_sql_param_surface.py`——纯函数
  `sql_param_violations({rel: src})`：`text(...)`/`sa_text(...)/<别名>.text(...)` 首参为
  f-string / `+`/`%` 拼接 / `.format()` 调用 ⇒ 违规；f-string 插值**仅**放行
  「本模块顶层全大写常量名 且 (文件, 常量) 在允许表内」。允许表恰 1 条：
  `services/process_heartbeat.py: {TABLE_NAME}`（模块常量表名；同文件 :123/:150 两处真身）。
- **自测六发**：负例①运行时值 f-string（抓）、②`+` 拼接（抓）、③`.format()`（抓）、
  ④允许表外同形常量 f-string（抓，防允许表被当通配）；正例⑤允许表内真身放行、
  ⑥允许表恰 1 条断言（多一条即红，口径变化须先改卡）。
- **现代码面读数**：违规清单 **空**（12 处调用点全部参数化/常量形），门绿。

## 本机全量（@win，PG16@5547）

- 两卡面文件合跑：**28 passed / 2 skipped**。
- 全量三次（如实）：首跑 **2 failed**（w2_worker 时序红 + 一条被 tail 截断）、二跑 **1 failed**
  （固定在 `test_daily_jobs_enqueue_after_0630_with_frozen_clock`）、单跑该用例即红——
  根因是 **S35.6 测试 A 固定 id 直插用户且不清**，持久库上第二次全量必撞唯一约束
  （本卡改动零相关，CI 新库不暴露）⇒ 登记 **P-120**（事实/复现/修法/归属在 P 表）。
  另 w2_worker 首跑红的时序族在二、三跑均绿，待 P-120 修复后观察。
- 重置 `bothot_test` 后第三跑：**2385 passed / 6 skipped / 4 deselected / 0 failed**（1592s；
  基线 2379 + 本卡 6 条）。

## backlog

`SEC-006` 段头 ⬜ → ✅（证据路径写入）。

## @ci（推送后回填，2026-10-25 1:5x @win，Asia/Shanghai）

交付 head `8644bea` 三绿，attempt 1：

| 工作流 | run id | 结论 |
|---|---|---|
| CI | 40115770219 | success |
| CI-Windows | 40115770225 | success |
| Security | 40115770211 | success |

本卡新增用例均非连库 ⇒ Windows skip 基线不动（预测成立：三绿含 skip 门）。
