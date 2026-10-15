"""STEP-00W S00W.3.2/S00W.3.3 —— 启动探测必须有上界（这条用例本身就是回归线）。

要防的事（生产缺陷，不是测试洁癖）：`app/main.py:281` 在 **import 期** 执行 `create_app()`，
其中 `_assert_schema_current` 同步 `asyncio.run()` 连库探测。改之前那条探测**没有任何超时**，
所以只要"数据库所在网络丢包"（而不是拒连），进程就在 import 期无限挂住：
uvicorn 起不来、`/live` `/ready` 都没机会绑端口，而容器健康检查读不到退出码。
Windows 上它还有一个更隐蔽的形态：psycopg 只在 Selector 事件循环下才真正发起连接，
所以裸 `import app.main` 秒回、而 pytest（conftest 设了 Selector 策略）一采集就挂——
"裸跑很快、测试很慢"这对矛盾让定位绕了一圈。栈证据：
`docs/06_validation/evidence/EVD-V7-00W/probe_selector_prefix.txt`
（`Timeout (0:00:15)! ... main.py:218 in _assert_schema_current → selectors._select`）。

三条设计约束：
1. **子进程跑**：在测试进程里换事件循环策略或制造挂起会污染整个 session；
2. **父进程带硬 timeout**：挂住时用例要**失败**，而不是把整轮 CI 拖到 35 分钟被 cancelled——
   这正是本版要消灭的形态；
3. **黑洞地址可覆盖**（`BOTHOT_PROBE_BLACKHOLE`）：换网络时不必改代码，但默认值在本机
   实测是**真黑洞**（`socket.create_connection` 8s 不返回，见 06 会话读数），
   若某天它变成秒拒，本用例会退化成"计时通过"——那种情况下改测例前先重跑 §3 的探测。

Windows 下必须换 Selector 策略，否则测的是"psycopg 拒绝在 Proactor 上连接"而不是"连接无上界"。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[1]
BLACK_HOLE_DSN = os.environ.get("BOTHOT_PROBE_BLACKHOLE", "postgresql+psycopg://probe@10.255.255.1:5432/probe")
LIMIT_SECONDS = 8.0          # 判据：探测有 connect_timeout=3 + wait_for(5) 上界，留 CI 抖动余量
HARD_TIMEOUT_SECONDS = 40.0  # 父进程兜底：绝不允许本用例把整轮测试拖死

_CHILD = r"""
import asyncio, sys, time
if sys.platform == "win32":
    # 与 tests/conftest.py:26 同条件：不换位时 psycopg 直接拒绝在 Proactor 上连接，
    # 根本不会发起 TCP 连接，于是"无上界"这个缺陷测不出来。
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
t0 = time.monotonic()
import app.main  # noqa: F401  # import 期即 create_app() → _assert_schema_current
sys.stderr.write("%.2f\n" % (time.monotonic() - t0))
"""


def test_import_time_schema_probe_is_bounded_against_blackhole_db() -> None:
    env = dict(os.environ)
    env["DATABASE_URL"] = BLACK_HOLE_DSN
    env["APP_ENV"] = "development"   # 生产语义（拒启）由另一条断言管，这里只测"有没有上界"
    env["PYTHONUTF8"] = "1"

    started = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", "-c", _CHILD],
            cwd=str(API_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=HARD_TIMEOUT_SECONDS,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            f"import app.main 在无响应的库前挂住（>{HARD_TIMEOUT_SECONDS}s 被父进程杀掉）：启动期探测没有超时上界。"
            f" 子进程 stderr 尾部：{str(exc.stderr or '')[-400:]}"
        )
    elapsed = time.monotonic() - started

    assert proc.returncode == 0, (
        f"import app.main 退出码 {proc.returncode}（期望 0：探测不可判定应放行，不是崩）\n"
        f"stderr 尾部：{proc.stderr[-600:]}"
    )
    assert elapsed < LIMIT_SECONDS, (
        f"import app.main 花了 {elapsed:.2f}s，超过 {LIMIT_SECONDS}s 上界 —— "
        f"黑洞地址下还这么快说明没走到真连接（测的不是本缺陷，先复核 §3 探针）。"
        f"子进程自报耗时：{proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else '（无）'}"
    )
