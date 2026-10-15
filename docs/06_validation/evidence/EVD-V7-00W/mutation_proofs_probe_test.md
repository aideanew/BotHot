# 反证集：`tests/test_startup_probe_timeout.py` 的每条断言都挨过一击

独立验证者判 item 3 "**PASS as run / NOT sound as written**"（只有 `rc==0` + `elapsed<8s`，
任何让探测短路的事都会 rc=0 秒过）。据此重写后的用例有四道断言，逐条给出"打它一下看它红不红"的读数。
全部 `@win`，命令在 `apps/api/` 下用仓库 venv 跑：
`.venv/Scripts/python.exe -X utf8 -m pytest tests/test_startup_probe_timeout.py -q`。

| 反证 | 打的是什么 | 读数 | 红在哪条断言 |
|---|---|---|---|
| 正常（黑洞 `10.255.255.1:5432`） | — | `1 passed in 7.00s`；子自报 4.58s、墙钟 7.06s、地址复检 `unresponsive@2.02s` | 全绿 |
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

## 三条没做到的（如实记账）

1. **skip 分支在 @win 不可达、未经证明**。本想用"秒拒地址"演练它，但本机
   `127.0.0.1:1`、`127.0.0.1:5` 经 `socket.create_connection(..., 2.0)` 实测**都是
   `unresponsive@2.00s`**（这台机器的回环不产生 RST 形态），三个地址的子进程耗时也几乎一样
   （4.50 / 4.53 / 4.58s）⇒ "地址不再是黑洞"这一前提在本地造不出来，只有代码路径为凭。
2. **红/绿两次读数的"红"是用 2940a6f 的分离 worktree 打的**，不是字面上的 3a67e96。
   等价性有机检：`git diff --stat 3a67e96 2940a6f -- apps/api/app/main.py apps/api/app/db.py` 输出为空
   （两提交间只动了 docs），见 `red_prefix_blackhole_selector.txt`。
3. **@linux 手跑面仍缺**。本机 `docker: command not found`；`@ci` ubuntu runner 上该用例算进
   1058 passed 是同族证据，不等同于卡面写的 `@linux` 命令读数。
