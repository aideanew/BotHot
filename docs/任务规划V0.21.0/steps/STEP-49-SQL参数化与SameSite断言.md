# STEP-49 SQL 参数化面与 Cookie SameSite 断言（SEC-006）

> 基线 main@9028b89｜状态：🔶 第 1 轮已交付（2026-10-25，读数在 EVD-V21-49/；发现 P-120）｜版本 V0.21.0

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行助手（Agent-Guard，测试侧） |
| 2 切片 | SL-SEC-PROOF（安全需求从"代码成立"到"测试成立"） |
| 3 来源 | REQ-NF-002；backlog `SEC-006`（`docs/04_engineering/backlog.md:226-233`） |
| 4 目标 | ① 登录 Cookie 的 SameSite=Lax 有断言 ② `apps/api/app` 内不存在把运行时值拼进 SQL 文本的入口，且有断言守住 |
| 5 输入 | `apps/api/app/api/v1/auth.py:98`（`samesite="lax"`）；`apps/api/tests/test_auth.py:273`（只断 HttpOnly）；`app` 内 `text(`/`sa_text(` 调用 39 处（规划方 grep 读数，开工复读）；已知一处 f-string：`app/services/process_heartbeat.py:150`（插值是模块常量 `TABLE_NAME`） |
| 6 输出 | 改 `apps/api/tests/test_auth.py`（在 :273 同用例或相邻新用例断 `SameSite=Lax`，大小写不敏感）；新 `apps/api/tests/test_sec006_sql_param_surface.py`：AST 扫 `app/**/*.py`，凡 `text(...)`/`sa_text(...)`/`sqlalchemy.text(...)` 的首参是 JoinedStr（f-string）、BinOp（`+`/`%`）或 `.format()` 调用 ⇒ 记违规；f-string 内只出现**本模块顶层全大写常量名**的，按显式允许表 `{"app/services/process_heartbeat.py": {"TABLE_NAME"}}` 放行；允许表之外任何命中 ⇒ 红；附自测：喂一段含 `text(f"... {user_input}")` 的源码字符串 ⇒ 判违规；`backlog.md` SEC-006 改 ✅ 并写证据路径 |
| 7 验收 | ① 先红：在旧代码上把 auth.py 的 samesite 临时改成 "strict" 跑新断言 ⇒ 红（原文入证后还原）② SQL 门在现代码上绿、自测负例红 ③ 允许表恰 1 条 ④ 全量 + 三绿 |
| 8 命令 | `cd apps/api && pytest -q tests/test_auth.py tests/test_sec006_sql_param_surface.py` |
| 9 证据 | `EVD-V21-49/s49_readings.md` |
| 10 允许修改 | 第 6 格所列 |
| 11 禁止修改 | 任何 `app/**` 业务代码（本卡只加断言）；`process_heartbeat.py` |
| 12 依赖 | 无（与 48、50 文件不相交，可并行；单执行助手仍按队列串行） |
| 13 档位 | sonnet |
| 14 升级条件 | 扫到允许表之外的真实拼接 ⇒ 登记 P-120+ 交回，不修 |
| 15 规模 | 小，≈0.3 人日 |
| 16 熔断 | 同判据 2 次 FAIL ⇒ 停 |

## 三级任务
1. [x] **S49.1 SameSite**：先红（临时改 strict）→ 断言 → 还原
2. [x] **S49.2 SQL 参数化面门**
   1. [ ] S49.2.1 复读 `text(` 调用点清单入证（文件:行，计数）
   2. [ ] S49.2.2 AST 门 + 允许表 + 负例自测
3. [x] **S49.3** backlog 回填 + 全量 + 三绿 + 07 记录
