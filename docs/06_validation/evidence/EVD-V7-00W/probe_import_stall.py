"""STEP-00W S00W.1.1 —— 用 @win 栈闭合"import 期卡死"的根因（替代临时诊断分支）。

用法（在 repo 根执行）：
    DATABASE_URL=postgresql+psycopg://x@10.255.255.1:5432/x \\
      apps/api/.venv/Scripts/python.exe docs/06_validation/evidence/EVD-V7-00W/probe_import_stall.py apps/api

为什么要它：卡片原方案是开一个 `diag/00w` 临时分支让 CI 去打栈。但"栈"要的是**在失败的那台机器上、
用失败的那条路径**取到——本机 @win 就是失败面，直接跑更快、更可复核，也不往远端推诊断分支。
`faulthandler.dump_traceback_later(N, exit=True)` 的作用：N 秒内没跑完就把**所有线程的栈**打到 stderr
并以非 0 退出——于是"挂住"第一次变成一份可归档的读数，而不是一个 35 分钟后才被取消的 job。
"""
from __future__ import annotations

import faulthandler
import os
import sys
import time

WATCHDOG_SECONDS = float(os.environ.get("PROBE_WATCHDOG_SECONDS", "20"))

api_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "apps/api")
sys.path.insert(0, api_dir)

# PROBE_SELECTOR=1 复刻 **pytest 的真实条件**：tests/conftest.py:26 在 import 期把 Windows
# 事件循环策略换成 Selector。不换位时 psycopg 直接抛 "cannot use the ProactorEventLoop" 而
# **根本不发起连接**（实测 import 1.67s 就"不可判定"放行），于是黑洞地址也测不出挂死——
# 这正是上一轮"裸 import 很快、pytest 采集很慢"这对矛盾的解。取栈必须带着这个变量跑。
if os.environ.get("PROBE_SELECTOR") == "1" and sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    print("[probe] PROBE_SELECTOR=1 → 已换成 WindowsSelectorEventLoopPolicy（与 conftest 同）")

print(f"[probe] cwd={os.getcwd()} api_dir={api_dir}")
print(f"[probe] DATABASE_URL={os.environ.get('DATABASE_URL', '<unset>')!r}")
print(f"[probe] watchdog={WATCHDOG_SECONDS}s  platform={sys.platform}  py={sys.version.split()[0]}")

faulthandler.enable()
faulthandler.dump_traceback_later(WATCHDOG_SECONDS, exit=True)

t0 = time.monotonic()
try:
    import app.main  # noqa: F401  # 生产形态：import 期即 create_app() → _assert_schema_current
except BaseException as exc:  # noqa: BLE001 - 读数脚本，异常内容就是证据
    faulthandler.cancel_dump_traceback_later()
    print(f"[probe] import raised {type(exc).__name__}: {str(exc)[:200]} after {time.monotonic() - t0:.2f}s")
    raise SystemExit(2)

faulthandler.cancel_dump_traceback_later()
print(f"[probe] import app.main OK in {time.monotonic() - t0:.2f}s")
