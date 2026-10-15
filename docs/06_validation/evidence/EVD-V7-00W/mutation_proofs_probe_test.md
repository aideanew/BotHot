# 反证集：`tests/test_startup_probe_timeout.py` 的每条断言都挨过一击

独立验证者判 item 3 "**PASS as run / NOT sound as written**"（只有 `rc==0` + `elapsed<8s`，
任何让探测短路的事都会 rc=0 秒过）。据此重写后的用例有四道断言，逐条给出"打它一下看它红不红"的读数。
全部 `@win`，命令在 `apps/api/` 下用仓库 venv 跑：
`.venv/Scripts/python.exe -X utf8 -m pytest tests/test_startup_probe_timeout.py -q`。

| 反证 | 打的是什么 | 读数 | 红在哪条断言 |
|---|---|---|---|
| 正常（黑洞 `10.255.255.1:5432`） | — | 第一轮重写后 `1 passed in 7.00s`；第二轮把地址复检提前后 `1 passed in 8.09s`。两个数都是 **pytest 总时长**（= 解释器启动 + 子探测 ≈4.5s + 复检 ≈2s），不是判据量；判据量始终是子自报的 `PROBE_SECONDS`。总时长的抖动我不给因果解释 | 全绿 |
| `BOTHOT_PROBE_BLACKHOLE=…@bothot-does-not-exist.invalid:5432/…` | **地址不是黑洞** | `1 skipped in 3.53s`，skip 原因含 `unresolvable` + 子自报 `2.33s` | skip 分支（第二轮新增的提前复检）——证明"没有测量对象"时它不冒充绿 |
| `BOTHOT_PROBE_BLACKHOLE=not-a-valid-dsn` | DSN 解析 | `1 failed in 1.45s` | 退出码断言（rc=1） |
| `BOTHOT_PROBE_BLACKHOLE=postgresql+asyncpg://…@10.255.255.1:5432/…` | 缺驱动（venv 内 `asyncpg_installed=False`） | `1 failed in 1.57s`，子进程 `ModuleNotFoundError: No module named 'asyncpg'` | 退出码断言（rc=1：`app/db.py:77` 的模块级单例引擎先抛，走不到守卫的 `except Exception: pass`） |
| 把 `import app.main` 放进 running loop 内执行 | **探测被短路**（`main.py:208` 的 "已在 async 上下文" return 分支） | `rc=0 / 墙钟 1.77s / 子自报 1.33s / marker_hit=False` | 结论日志断言。**这一条正中靶心**：旧用例在这里会绿（1.33s < 8s 且 rc=0），新版必红 |
| 用系统 python（无 venv）跑同一子进程 | 依赖缺失 | 三个地址全 `rc=1`，`ModuleNotFoundError: No module named 'structlog'` | 退出码断言——顺带说明"环境不对"绝不能表现为计时通过 |

## 计时口径的更正（为什么不再拿墙钟比 8s）

同一黑洞地址，`@win` 实测：子进程自报 `import app.main` = **4.50–4.58s**，父进程墙钟 = **6.91–7.06s**，
差的 2.4s 全在解释器/venv 启动。旧写法用墙钟比 `LIMIT_SECONDS=8.0` ⇒ 本机余量只剩 1s，
验证者那台机器是 5.19–5.30s（余量 2.7s）——同一个判据在不同机器上松紧不一，换台慢 runner 就假红。
新版解析子进程自报的 `PROBE_SECONDS x.xx` 作为判据量，`8.0` 的余量回到 3.4s，且新增
`FLOOR_SECONDS=3.0`（= `connect_timeout`）下界：黑洞实测无响应却短于 3s ⇒ 说明上界没生效或
探测根本没走网络 ⇒ `fail`。

## 记账（第一轮写的"没做到的"，第二轮后状态如何）

1. **skip 分支已证可达**（第一轮写"本地不可达、只有代码路径为凭"；第二轮验证者又指出：复检当时只在
   `probe_seconds<3.0` 时才看，"import 本身就 >3s 的慢机器"会什么都没测就绿）。改法：**地址复检移到
   计时之前**，只要 `_blackhole_state() != "unresponsive"` 就 skip，不看耗时。可跑的反例是**解析不到
   的主机名**：`BOTHOT_PROBE_BLACKHOLE=postgresql+psycopg://probe@bothot-does-not-exist.invalid:5432/probe`
   ⇒ `1 skipped in 3.53s`，原因串自带"实测为 unresolvable / 子自报 2.33s / 结论日志已命中"
   （探测真跑了，只是本机没有黑洞可计时）。
   **"秒拒"那一支仍造不出来**：本机 `127.0.0.1:1`、`127.0.0.1:5` 经 `socket.create_connection(..., 2.0)`
   实测都是 `unresponsive@2.00s`（这台机器的回环不产生 RST），三个地址耗时也几乎一样
   （4.50 / 4.53 / 4.58s）⇒ `fast-fail` 分支仍只有代码路径为凭。
1a. **head 解析不到不再假红**：新增 `_alembic_head()` 前置 skip——守卫在 `head is None` 时两条结论日志
    都不会打，那是环境事实不是缺陷。此分支未造反例（本机 head 解析得到 `ab1005w5b`）。
2. **红/绿两次读数的"红"是用 2940a6f 的分离 worktree 打的**，不是字面上的 3a67e96。
   等价性有机检：`git diff --stat 3a67e96 2940a6f -- apps/api/app/main.py apps/api/app/db.py` 输出为空
   （两提交间只动了 docs），见 `red_prefix_blackhole_selector.txt`。
3. **@linux 手跑面仍缺**，但"新用例在 ubuntu-latest 上是 pass 还是 skip"这一问已改为**有产物可推**：
   `ci_backend_log_2940a6f_excerpt.txt` = `1057 passed, 6 skipped`（用例尚不存在）vs
   `ci_backend_log_e7e9f25_excerpt.txt` = `1058 passed, 6 skipped` 且 6 条 SKIPPED 明细逐字相同
   ⇒ 净增 1 pass、0 skip。这仍不等同于卡面写的 `@linux` 命令读数。
