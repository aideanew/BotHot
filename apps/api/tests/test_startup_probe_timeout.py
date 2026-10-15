"""STEP-00W S00W.3.2/S00W.3.3 —— 启动探测必须有上界（这条用例本身就是回归线）。

要防的事（生产缺陷，不是测试洁癖）：`app/main.py:281` 在 **import 期** 执行 `create_app()`，
其中 `_assert_schema_current` 同步 `asyncio.run()` 连库探测。改之前这条探测**没有任何超时**，
所以只要"数据库所在网络丢包"（而不是拒连），进程就在 import 期无限挂住：
uvicorn 起不来、`/live` `/ready` 都没机会绑端口，而容器健康检查读不到退出码。
Windows 上它还有一个更隐蔽的形态：psycopg 只在 Selector 事件循环下才真正发起连接，
所以裸 `import app.main` 秒回、而 pytest（conftest.py:27 设了 Selector 策略）一采集就挂——
"裸跑很快、测试很慢"这对矛盾让定位绕了一圈。栈证据：
`docs/06_validation/evidence/EVD-V7-00W/probe_selector_prefix.txt`
（`Timeout (0:00:15)! ... main.py:218 in _assert_schema_current → selectors._select`）。

四条设计约束：
1. **子进程跑**：在测试进程里换事件循环策略或制造挂起会污染整个 session；
2. **父进程带硬 timeout**：挂住时用例要**失败**，而不是把整轮 CI 拖到 35 分钟被 cancelled——
   这正是本版要消灭的形态；
3. **计时量的是子进程自报的 `import app.main` 耗时，不是父进程墙钟**：本机实测父墙钟 6.9–7.1s
   而子自报 4.5s，差的 2.4s 全在解释器/venv 启动上。拿墙钟比 8s 上界，余量只剩 1s，
   换台慢一点的 runner 就会假红（独立验证者也指出了"5.19–5.30s vs 8s"这层脆弱）；
4. **必须看到探测的结论性日志**（`schema 版本探测超时` 或 `版本不一致：DB=`）：只有计时断言的话，
   任何让探测短路的事都会 rc=0 秒过 ⇒ 假通过。这条不是摆设，已用三种反证打过：
   - 非法 DSN → rc=1，红在退出码断言（1.46s）；
   - 缺驱动的 scheme（`+asyncpg`）→ rc=1（`app/db.py:77` 的模块级单例引擎先抛），1.57s；
   - **守卫短路**（在 running loop 内 import，走 `main.py:208` 的 return 分支）→ rc=0、
     子自报 1.33s、**两条结论日志一条都没有** ⇒ 旧版用例会在这里绿，新版红。这条正中靶心。

`FLOOR_SECONDS=3.0` 取自 `connect_timeout=3`：黑洞地址下探测必然至少占用这么久，
短于它又没有超时日志，就说明上界没生效或探测根本没走网络。地址本身也在用例里复检
（`_blackhole_state`）——若它哪天不再无响应，用例 skip 记账而不是冒充"计时已证"。
注意 @win 实测 `127.0.0.1:1` 与 `:5` 都是 unresponsive@2.00s（本机不产生"秒拒"形态），
所以 skip 分支在本地**不可达、未经证明**，只有代码路径为凭。

Windows 下必须换 Selector 策略，否则测的是"psycopg 拒绝在 Proactor 上连接"而不是"连接无上界"。
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[1]
BLACK_HOLE_DSN = os.environ.get("BOTHOT_PROBE_BLACKHOLE", "postgresql+psycopg://probe@10.255.255.1:5432/probe")
LIMIT_SECONDS = 8.0          # 判据：connect_timeout=3 + wait_for(5) 之和，留 CI 抖动余量
FLOOR_SECONDS = 3.0          # 下界 = connect_timeout：真黑洞下探测至少要占用这么久
SOCKET_CHECK_SECONDS = 2.0   # 复检地址性质用，不计入耗时
HARD_TIMEOUT_SECONDS = 40.0  # 父进程兜底：绝不允许本用例把整轮测试拖死

_CHILD = r"""
import asyncio, sys, time
if sys.platform == "win32":
    # 与 tests/conftest.py:27 同条件：不换位时 psycopg 直接拒绝在 Proactor 上连接，
    # 根本不会发起 TCP 连接，于是"无上界"这个缺陷测不出来。
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
t0 = time.monotonic()
import app.main  # noqa: F401  # import 期即 create_app() → _assert_schema_current
sys.stderr.write("PROBE_SECONDS %.2f\n" % (time.monotonic() - t0))
"""


def _blackhole_state() -> str:
    """实测所配置地址的连通形态，用来判断"计时断言"到底有没有测量对象。

    'unresponsive' = 建连在 `SOCKET_CHECK_SECONDS` 内不返回（正是要复现的黑洞）；
    其余（'connected' / 'fast-fail' / 'unresolvable' / 'malformed'）都测不出"无上界"。
    """
    match = re.search(r"@([^:/?#]+):(\d+)", BLACK_HOLE_DSN)
    if match is None:
        return "malformed"
    try:
        with socket.create_connection((match.group(1), int(match.group(2))), timeout=SOCKET_CHECK_SECONDS):
            return "connected"
    except TimeoutError:
        return "unresponsive"
    except socket.gaierror:
        return "unresolvable"
    except OSError:
        return "fast-fail"


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
    wall_seconds = time.monotonic() - started
    combined = (proc.stdout or "") + (proc.stderr or "")

    assert proc.returncode == 0, (
        f"import app.main 退出码 {proc.returncode}（期望 0：探测不可判定应放行，不是崩）\n"
        f"stderr 尾部：{proc.stderr[-600:]}"
    )
    # 这条断言是独立验证逼出来的，比计时更重要：**没有探测结论的计时通过是假通过**。
    # 只要探测真跑了，两条日志必居其一：超时放行（>5s 那支）、或"版本不一致：DB=…"
    # （黑洞下 connect_timeout 先抛、read_current_version_async 归一为 None，本机实测走这支）。
    # 反之若 psycopg 缺失、DSN 解析失败、或已在 loop 内短路，就一条都没有 ⇒ 这里红，而不是悄悄绿。
    markers = ("schema 版本探测超时", "版本不一致：DB=")
    assert any(m in combined for m in markers), (
        "没看到启动探测的任何结论性日志（期望命中 "
        f"{markers} 之一）⇒ 探测被短路，本用例的计时通过不可信。输出尾部：{combined[-600:]}"
    )
    reported = re.search(r"PROBE_SECONDS (\d+\.\d+)", combined)
    assert reported is not None, (
        f"子进程没自报 import 耗时（期望 `PROBE_SECONDS <秒>`）⇒ 它没跑到最后一行。输出尾部：{combined[-600:]}"
    )
    probe_seconds = float(reported.group(1))
    state = _blackhole_state()  # 放在取值之后，这 2s 不吃本用例的计时
    if probe_seconds < FLOOR_SECONDS:
        if state != "unresponsive":
            pytest.skip(
                f"地址 {BLACK_HOLE_DSN} 实测为 {state}（不是无响应黑洞），探测只花 {probe_seconds:.2f}s"
                f"（墙钟 {wall_seconds:.2f}s）⇒ 计时断言没有测量对象，按 skip 记账不冒充已证"
            )
        pytest.fail(
            f"地址实测无响应（真黑洞）而探测只花 {probe_seconds:.2f}s < 下界 {FLOOR_SECONDS}s"
            f"（= connect_timeout）⇒ 超时上界未生效或探测根本没走网络。输出尾部：{combined[-400:]}"
        )
    assert probe_seconds < LIMIT_SECONDS, (
        f"import app.main 的探测耗时 {probe_seconds:.2f}s 超过 {LIMIT_SECONDS}s 上界 —— "
        f"黑洞地址下还这么久说明两级超时（connect_timeout=3 / wait_for=5）都没生效。"
        f"父进程墙钟 {wall_seconds:.2f}s（含解释器启动，不计入判据）"
    )
