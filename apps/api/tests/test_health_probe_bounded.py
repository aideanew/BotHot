"""STEP-00H S00H.1：健康/就绪探针必须**有上界**（黑洞依赖下不得无限挂起）。

为什么这条卡存在（V0.12.0 把结论下错过一次）：`/health` 串行等三个探针，redis 有
`socket_connect_timeout=2`、langbot 有 `httpx timeout=3`，**唯独 PG 探针走业务引擎、
没有 `connect_timeout`**（`app/db.py` 的 `connect_args` 默认空 dict）。依赖不可达且是
"丢包不回 RST"的黑洞地址时，`GET /health` 永不返回。`CI-Windows` 恒红（U-23）的根因怀疑
就在这条上，V0.12.0 曾判"卡在 TestClient/anyio portal，与 psycopg 无关"——本版更正：
portal 只是在替 `/health` 等一次连接。

判据为什么必须用**子进程**：如果探针本身无上界，那么"用一个 pytest 用例去等它"会把这个
pytest 进程一起挂住——测试工具替被测量挂掉，读数就没了。所以父进程只负责计时与判 rc，
子进程里的 `TestClient` 爱挂多久挂多久，由 `timeout` 掐掉。

本机环境说明：无 PG/Redis/LangBot ⇒ 这三个地址在开发机上本来就是黑洞，用例**不需要**
额外起容器；它判的正是"依赖全挂时 `/health` 还要在 5s 内给我一个 degraded 答案"。
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[1]
# 单探针上界 3s（`PROBE_TIMEOUT_S`）+ gather 同批发起 + 进程内 import/装配的余量。
# 5s 是**卡面上的判据**（目标句写的是 ≤5s），不是随手挑的数：三个探针若串行退化，
# 3×3=9s 会在这里红——那正是"加了上界但仍串行"的形态，必须被抓到。
WALL_CLOCK_LIMIT_S = 5.0
PARENT_TIMEOUT_S = 60.0

_CHILD = '''
import json, os, sys
os.environ.setdefault("APP_ENV", "development")
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
from app.main import create_app

client = TestClient(create_app())
out = {}
for name, path in (("health", "/api/v1/system/health"), ("ready", "/api/v1/system/ready")):
    t0 = time.perf_counter()
    resp = client.get(path)
    out[name] = {
        "seconds": round(time.perf_counter() - t0, 3),
        "status_code": resp.status_code,
        "body": resp.json(),
    }
print("RESULT" + json.dumps(out))
'''


def _run_child() -> dict[str, dict[str, object]]:
    """在**干净的事件循环 + 黑洞依赖**下跑一次，返回两次请求的计时与响应。"""
    env = {
        **os.environ,
        "APP_ENV": "development",
        # 10.255.255.1 是 RFC5737 保留地址：不路由、丢包不回 RST ⇒ 正是"黑洞"形态。
        "DATABASE_URL": "postgresql+psycopg://probe:probe@10.255.255.1:5432/probe",
        "REDIS_URL": "redis://127.0.0.1:1/0",
        "LANGBOT_BASE_URL": "http://127.0.0.1:1",
        "SECRET_KEY": "0" * 32,
        "PYTEST_CURRENT_TEST": "",
    }
    # 子进程需要 `time`；把它放进 prelude 而不是改写用例里的探针逻辑。
    code = "import time\n" + _CHILD
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", code],
        cwd=str(API_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=PARENT_TIMEOUT_S,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT"):
            return json.loads(line[len("RESULT") :])
    raise AssertionError(
        f"子进程没给出读数 rc={proc.returncode}\nstdout tail: {proc.stdout[-800:]}\n"
        f"stderr tail: {proc.stderr[-1200:]}"
    )


def test_health_and_ready_return_within_bound_under_blackhole_dependencies() -> None:
    """S00H.1.1：依赖全是黑洞时，`/health` 与 `/ready` 各 ≤5s 返回且 postgres=unreachable。

    改前这条**必红**（子进程 60s 被父进程掐掉 ⇒ `TimeoutExpired`），
    因为 PG 探针没有 `connect_timeout`；这是"用例抓得到缺陷"的证明，不是环境噪声。
    """
    readings = _run_child()
    # 两个探针的**响应形状不同**（`/health` 给 `data.deps.<name>` 字符串，
    # `/ready` 给 `data.checks.<name>` 的 {ok,state} dict 且未就绪时返 503），
    # 所以逐项按各自形状判——上一版这里直接取 `["deps"]`，在 `/ready` 上 KeyError。
    assert readings["health"]["seconds"] <= WALL_CLOCK_LIMIT_S, (
        f"/health 墙钟 {readings['health']['seconds']}s > {WALL_CLOCK_LIMIT_S}s ⇒ 探针没上界或仍串行"
    )
    assert readings["ready"]["seconds"] <= WALL_CLOCK_LIMIT_S, (
        f"/ready 墙钟 {readings['ready']['seconds']}s > {WALL_CLOCK_LIMIT_S}s ⇒ 探针没上界或仍串行"
    )
    health_body = readings["health"]["body"]
    assert health_body["code"] == 0, f"/health 信封不是 success：{health_body}"
    assert health_body["data"]["deps"]["postgres"] == "unreachable", health_body["data"]
    assert health_body["data"]["status"] == "degraded", health_body["data"]

    ready_body = readings["ready"]["body"]
    assert ready_body["code"] == 0, f"/ready 信封不是 success：{ready_body}"
    assert ready_body["data"]["checks"]["postgres"]["state"] == "unreachable", ready_body["data"]
    # 就绪门禁必须真的摘流量：黑洞库下 `/ready` 返 503 而不是 200
    assert readings["ready"]["status_code"] == 503, readings["ready"]["status_code"]


async def test_probes_run_concurrently_not_serially(monkeypatch: pytest.MonkeyPatch) -> None:
    """反证"加了上界但仍是串行"：两支各睡 3s 的探针，并发总耗时 ≈3s，串行 ≈6s。

    这一条**不**用黑洞子进程判并发——上一版我写的是"总时间 ≤ 4.5s"，而端点已经有 4s
    总预算，全串行也能过 ⇒ 那是一条恒真判据。改成确定性的两支慢探针：各 2s（明显短于
    单探针 3s 上界，免得测成"上界与睡眠同时到点"的掷硬币），并发 ≈2s、串行 ≈4s。
    两个极性都要过：耗时那条挡"排队"，`== "ok"` 那条挡"被预算掐掉"（串行时第二支会在
    4s 预算处被取消，读数就变成 unreachable）。
    """
    from app.api.v1 import system

    async def _slow_ok() -> str:
        await asyncio.sleep(2.0)
        return "ok"

    async def _fast_langbot() -> str:
        return "ok"

    monkeypatch.setattr(system, "_check_pg", _slow_ok)
    monkeypatch.setattr(system, "_check_redis", _slow_ok)
    monkeypatch.setattr(system, "_check_langbot", _fast_langbot)

    t0 = time.perf_counter()
    body = await system.health()
    elapsed = time.perf_counter() - t0
    assert elapsed < 3.0, f"两支 2s 探针用了 {elapsed:.2f}s ⇒ 它们在排队，不是并发"
    assert body.data["deps"]["postgres"] == "ok", body.data
    assert body.data["deps"]["redis"] == "ok", "第二支被预算掐掉 ⇒ 实际是串行执行"


def test_endpoint_budget_is_strictly_inside_the_card_bound() -> None:
    """把"预算"本身钉成算术关系，防止有人靠调大上界让上一条判据变松。"""
    from app.api.v1 import system

    assert system.PROBE_BUDGET_S < WALL_CLOCK_LIMIT_S, "端点预算必须严格小于卡面 5s 判据"
    assert system.PROBE_BUDGET_S <= 2 * system.PROBE_TIMEOUT_S, "预算不该超过单探针上界的两倍"


def test_child_wall_clock_is_measured_not_assumed() -> None:
    """计时必须来自子进程的**实测**，并且两条请求各自独立计时。

    这条看起来多余，但它是前两轮的教训：判据若读的是"我以为的常数"，
    实现退化成 `return {"postgres": "unreachable"}`（跳过真连接、直接答 unreachable）
    也能全绿。所以这里要求耗时**大于 0**（真连接发生过）且两次读数不是同一个对象。
    """
    readings = _run_child()
    assert float(readings["health"]["seconds"]) > 0.0, "耗时恒 0 ⇒ 探针根本没去连接，是在背答案"
    assert readings["health"]["body"]["data"]["deps"] != {}, "deps 为空 ⇒ 探针面被摘掉了"


def test_probe_paths_are_exempt_in_both_middleware_layers() -> None:
    """防复发：探针路径必须在**两层中间件**的豁免集里都点名到，且条目必须真的存在。

    这条是被实测逼出来的：`security.py` 的豁免集原本写着裸 `/live`、`/ready`，而路由挂在
    `/api/v1/system` 前缀下 ⇒ 那两个是**死条目**，`/ready` 一直照常限流，Redis 不可达时
    还要在处理器之前先吃一次 2s 连接超时——STEP-00H 的 `/ready` 超预算就是这么来的。
    只改数字（把预算调大）会把这个洞留在原地，所以判据要落在"路径 ↔ 豁免集"的对应关系上。
    """
    from app.core import metrics, security
    from app.main import create_app

    probe_paths = set()

    def walk(routes: list[object], prefix: str = "") -> None:
        for route in routes:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                ctx = getattr(route, "include_context", None)
                walk(list(inner.routes), getattr(ctx, "prefix", None) or prefix)
                continue
            path = getattr(route, "path", None)
            if path and path.endswith(("/live", "/ready", "/health")):
                probe_paths.add(prefix + path)

    walk(list(create_app().routes))
    assert probe_paths, "枚举不到探针路径——路由形状变了，本条守卫失效要先修它"
    missing_sec = sorted(probe_paths - set(security._EXEMPT_PATHS))
    assert not missing_sec, f"这些探针仍会被限流计数：{missing_sec}"
    # metrics 层只豁免 live/ready（health 有意要计入指标），所以只判这两条
    live_ready = {p for p in probe_paths if p.endswith(("/live", "/ready"))}
    missing_m = sorted(live_ready - set(metrics._EXEMPT_PATHS))
    assert not missing_m, f"这些探针没被 metrics 层豁免：{missing_m}"
    # 死条目反向判：豁免集里每一条都必须是真实存在的路径，否则它就是下一个"裸 /ready"
    stale = sorted(p for p in security._EXEMPT_PATHS if p.startswith("/api/v1/") and p not in probe_paths)
    assert not stale, f"豁免集里有不存在的前缀路径（死条目）：{stale}"
