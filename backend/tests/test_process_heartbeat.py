"""R7.7 常驻进程心跳验收：写侧 upsert / 读侧全景 / 节流门 / healthcheck 出口 / 门禁。

口径（见 `app/services/process_heartbeat.py` 模块文档）：
- **两种故障必须可区分**：`lastHeartbeatAt=null`（进程从未启动）与「有值但过期」
  （进程启动后卡死）。处置动作不同——前者要 `docker compose up -d`，后者要看进程日志。
  合并成单一布尔就把 2026-09-28 那个 5 天静默失效的盲区原样造了一遍。
- **按期望清单全景回报**：`describe_liveness` 遍历 `EXPECTED_PROCESSES` 而非表内行，
  否则「缺进程」根本查不出来——那正是本次要防的事。
- **心跳不是关键路径**：写失败必须由调用方吞掉，否则一次数据库抖动即让采集全线停摆。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, create_engine
from sqlalchemy import text as sa_text
from sqlalchemy.schema import CreateTable, DropTable

import app.services.process_heartbeat as heartbeat_mod
from app.api.deps import get_current_user_id, get_db
from app.main import create_app
from app.models.entities import ProcessHeartbeat, User
from app.services.process_heartbeat import (
    DEFAULT_MAX_AGE_SECONDS,
    EXPECTED_PROCESSES,
    BeaconGate,
    beacon,
    check_process,
    describe_liveness,
)

PG_DSN = os.environ.get("AIDEANBOT_TEST_PG_DSN", "postgresql+psycopg://bothot:bothot@localhost:5433/bothot")
# 本文件专属的隔离表：与线上 `process_heartbeats` 完全分离。
TEST_TABLE = "process_heartbeats_r77test"


@pytest.fixture(autouse=True)
def _isolated_heartbeat_table(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """全模块用一张**专用表**，绝不读写真实的 `process_heartbeats`。

    为什么必须隔离：`EXPECTED_PROCESSES` 的键就是 `scheduler` / `worker`——与线上两个
    常驻进程正在写入的键**完全相同**。若共用真表会有两个后果，第二个特别坏：

    ① 测不到「缺行」语义——线上容器每 30s 就补回一行新鲜心跳，
      `test_describe_empty_table_*` 一类断言会随机变红；
    ② 为了造「缺行」而删真表行，会让线上 healthcheck 立刻读到 `lastHeartbeatAt=null`
      并报「**从未报到**」——即**用测试把生产可观测性弄坏**，且恢复要等下一个心跳周期。

    这是 R7.7 反过来被 D19（测试与线上库共用）咬到的一口：新特性把旧缺陷显出来了。
    表结构由 ORM 模型拷贝而来（不是手写 DDL），不会与模型漂移；
    teardown 无论成败都删表，不在线上库留痕。
    """
    try:
        engine = create_engine(PG_DSN, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(sa_text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PG 不可达（{type(exc).__name__}），Docker 引擎恢复后复跑本用例")

    target = MetaData()
    table = ProcessHeartbeat.__table__.to_metadata(target)
    # SQLAlchemy 2.0 已移除 `Table.copy()`，改名只能直接改实例属性。
    # 拷到独立 MetaData 上再改名，`ProcessHeartbeat.__table__.name` 不受影响。
    table.name = TEST_TABLE
    with engine.begin() as conn:
        conn.execute(DropTable(table, if_exists=True))
        conn.execute(CreateTable(table))
    monkeypatch.setattr(heartbeat_mod, "TABLE_NAME", TEST_TABLE)
    try:
        yield
    finally:
        with engine.begin() as conn:
            conn.execute(DropTable(table, if_exists=True))
        engine.dispose()


# 锚在**真实当前时刻**而非编造常量：`describe_liveness` 默认用 `datetime.now(UTC)`，
# `check_process` 更不接收时钟注入。编造一个未来的 NOW 会让「NOW - 2h」恰好落在真实现在
# 附近，把「过期」测成「新鲜」。整套用例在秒级跑完，漂移远小于 300s 阈值。
NOW = datetime.now(UTC)


async def _seed_operator(db_session: Any) -> str:  # type: ignore[no-untyped-def]
    op = User(sub="r77-op", email="r77-op@r77.test", nickname="op", role="operator")
    db_session.add(op)
    await db_session.flush()
    return op.id


# ------------------------------------------------------------------ 写侧


async def test_beacon_inserts_then_upserts_to_single_row(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """同键二次报到 → 仍是一行，时间戳前移、detail 覆盖（不是追加）。"""
    await beacon(db_session, "scheduler", "round=1")
    await beacon(db_session, "scheduler", "round=2")

    rows = (await db_session.execute(sa_text(f"SELECT last_detail, last_heartbeat_at FROM {TEST_TABLE}"))).all()
    assert len(rows) == 1
    assert rows[0][0] == "round=2"
    assert rows[0][1] is not None


async def test_beacon_truncates_detail_to_column_width(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """detail 超长 → 截到 VARCHAR(512)。不截会让一次异常详情把整轮心跳写废。"""
    await beacon(db_session, "scheduler", "x" * 600)
    rows = (await db_session.execute(sa_text(f"SELECT length(last_detail) FROM {TEST_TABLE}"))).all()
    assert rows[0][0] == 512


# ------------------------------------------------------------------ 读侧


async def test_describe_empty_table_lists_every_expected_process(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """零行 → 每个期望进程都占位且报 stale。只回报「已有行」就查不出缺进程。"""
    snap = await describe_liveness(db_session, now_fn=lambda: NOW)
    got = {p["processKey"] for p in snap["processes"]}
    assert got == set(EXPECTED_PROCESSES)
    assert all(p["stale"] is True for p in snap["processes"])
    assert snap["allHealthy"] is False
    assert snap["maxAgeSeconds"] == DEFAULT_MAX_AGE_SECONDS


async def test_describe_distinguishes_never_started_from_running(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """scheduler 新鲜 + worker 缺行：前者健康，后者 lastHeartbeatAt=null（从未启动）。"""
    await beacon(db_session, "scheduler", "round=3")

    snap = await describe_liveness(db_session, now_fn=lambda: NOW)
    sched = next(p for p in snap["processes"] if p["processKey"] == "scheduler")
    worker = next(p for p in snap["processes"] if p["processKey"] == "worker")

    assert sched["lastHeartbeatAt"] is not None
    assert sched["stale"] is False
    assert sched["purpose"] == EXPECTED_PROCESSES["scheduler"]

    assert worker["lastHeartbeatAt"] is None
    assert worker["ageSeconds"] is None
    assert worker["stale"] is True
    assert snap["allHealthy"] is False


async def test_describe_reports_stale_row_when_heartbeat_expired(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """有行但过期 = 进程启动后卡死：lastHeartbeatAt 非空，与「从未启动」可区分。"""
    await db_session.execute(
        sa_text(
            f"INSERT INTO {TEST_TABLE} (process_key, last_heartbeat_at, last_detail) "
            "VALUES ('worker', :at, 'stuck mid-ingest')"
        ),
        {"at": NOW - timedelta(hours=2)},
    )
    await db_session.commit()

    snap = await describe_liveness(db_session, max_age_seconds=300, now_fn=lambda: NOW)
    worker = next(p for p in snap["processes"] if p["processKey"] == "worker")

    assert worker["stale"] is True
    assert worker["lastHeartbeatAt"] is not None
    assert worker["ageSeconds"] == 7200
    assert worker["lastDetail"] == "stuck mid-ingest"


async def test_describe_age_equal_to_threshold_is_still_healthy(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """边界口径：age == 阈值不算 stale（严格大于才过期）。阈值本身不能自报故障。"""
    await db_session.execute(
        sa_text(f"INSERT INTO {TEST_TABLE} (process_key, last_heartbeat_at, last_detail) VALUES (:k, :at, '')"),
        {"k": "scheduler", "at": NOW - timedelta(seconds=300)},
    )
    await db_session.commit()

    snap = await describe_liveness(db_session, max_age_seconds=300, now_fn=lambda: NOW)
    sched = next(p for p in snap["processes"] if p["processKey"] == "scheduler")
    assert sched["ageSeconds"] == 300
    assert sched["stale"] is False


async def test_describe_age_uses_absolute_instant_across_zones(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """age 按**绝对时刻**计算，与写入值所处的墙钟时区无关。

    反例（2026-09-28 实测）：往 `timestamptz` 列写 **naive** 值时 PG 按**会话时区**
    解释，naive「11:59」在本机（+08）落库成「03:59+00」，按墙钟算 age 会差整整 8 小时。
    故本模块只写 tz-aware 值（SQL `now()`），age 恒为绝对差。
    """
    shanghai = ZoneInfo("Asia/Shanghai")
    await db_session.execute(
        sa_text(f"INSERT INTO {TEST_TABLE} (process_key, last_heartbeat_at, last_detail) VALUES ('worker', :at, '')"),
        {"at": (NOW - timedelta(seconds=60)).astimezone(shanghai)},
    )
    await db_session.commit()

    snap = await describe_liveness(db_session, now_fn=lambda: NOW)
    worker = next(p for p in snap["processes"] if p["processKey"] == "worker")
    assert worker["ageSeconds"] == 60
    assert worker["stale"] is False


# ------------------------------------------------------------------ 节流门


def test_beacon_gate_blocks_within_interval() -> None:
    """门内不重复放行：空闲循环 10s 一拍时，心跳写入节流到 30s 一次。"""
    t = [0.0]
    gate = BeaconGate(30.0, clock=lambda: t[0])
    assert gate.ready() is True
    t[0] = 29.999
    assert gate.ready() is False


def test_beacon_gate_allows_at_and_after_interval() -> None:
    t = [0.0]
    gate = BeaconGate(30.0, clock=lambda: t[0])
    assert gate.ready() is True
    t[0] = 30.0
    assert gate.ready() is True


# ------------------------------------------------------------------ healthcheck 出口


async def _aim_check_process_at(monkeypatch: pytest.MonkeyPatch, db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """check_process 内部自建引擎；改指向夹具会话以复用外层事务的回滚隔离。"""
    import app.core.config as config_module
    import app.db as db_module

    class _Engine:
        async def dispose(self) -> None:
            return None

    def _fake_create(_url: str) -> tuple[object, object]:
        return _Engine(), lambda: db_session

    monkeypatch.setattr(
        config_module, "get_settings", lambda: SimpleNamespace(database_url="postgresql+psycopg://test")
    )
    monkeypatch.setattr(db_module, "create_engine_and_session", _fake_create)


async def test_check_process_zero_when_fresh(
    db_session: Any,
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[no-untyped-def]
) -> None:
    await _aim_check_process_at(monkeypatch, db_session)
    await beacon(db_session, "scheduler", "ok")
    assert await check_process("scheduler", 300) == 0


async def test_check_process_one_when_stale_or_missing(
    db_session: Any,
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[no-untyped-def]
) -> None:
    """缺行与过期都返回 1（容器 unhealthy），但读侧回报的形态不同。"""
    await _aim_check_process_at(monkeypatch, db_session)
    assert await check_process("worker", 300) == 1

    await beacon(db_session, "worker", "alive")
    assert await check_process("worker", 300) == 0

    await db_session.execute(
        sa_text(f"UPDATE {TEST_TABLE} SET last_heartbeat_at = :at WHERE process_key = 'worker'"),
        {"at": NOW - timedelta(hours=2)},
    )
    await db_session.commit()
    assert await check_process("worker", 300) == 1


async def test_check_process_one_for_unknown_key(
    db_session: Any,
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[no-untyped-def]
) -> None:
    """不在期望清单的键返回 1：误配置的 healthcheck 不能因为「查不到行」而假绿。"""
    await _aim_check_process_at(monkeypatch, db_session)
    assert await check_process("backup", 300) == 1


# ------------------------------------------------------------------ 心跳不是关键路径


async def test_scheduler_beacon_swallows_write_failure() -> None:
    """数据库写不进去时心跳静默失败，不上抛——不能把可观测性故障放大成采集停摆。"""
    from app.services.scheduler import IncrementalScheduler

    def _boom() -> Any:
        raise RuntimeError("db unreachable")

    sched = IncrementalScheduler(_boom)
    await sched._beacon("round=1")  # 不抛即通过


async def test_worker_beacon_swallows_write_failure() -> None:
    from app.services.job_worker import JobWorker

    def _boom() -> Any:
        raise RuntimeError("db unreachable")

    async def _ingest(*_a: object, **_k: object) -> dict[str, object]:
        return {}

    worker = JobWorker(_boom, _ingest)
    await worker._beacon("job=j1")  # 不抛即通过


# ------------------------------------------------------------------ 管理端读侧


async def test_admin_liveness_endpoint(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """operator+ 放行；回报按期望进程全景（缺失也占位）。"""
    await beacon(db_session, "scheduler", "round=7")
    operator_id = await _seed_operator(db_session)

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user_id] = lambda: operator_id

    resp = TestClient(app).get("/api/v1/admin/ops/liveness")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0

    data = body["data"]
    assert [p["processKey"] for p in data["processes"]] == list(EXPECTED_PROCESSES)
    assert data["maxAgeSeconds"] == DEFAULT_MAX_AGE_SECONDS
    sched = next(p for p in data["processes"] if p["processKey"] == "scheduler")
    worker = next(p for p in data["processes"] if p["processKey"] == "worker")
    assert sched["stale"] is False and sched["lastDetail"] == "round=7"
    assert worker["stale"] is True and worker["lastHeartbeatAt"] is None
    assert data["allHealthy"] is False


async def test_admin_liveness_endpoint_accepts_max_age_query(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """Query 参数走 snake_case（项目约定，同 `space_id`/`limit`）；响应体字段才是 camelCase。"""
    await beacon(db_session, "scheduler", "ok")
    operator_id = await _seed_operator(db_session)

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user_id] = lambda: operator_id

    resp = TestClient(app).get("/api/v1/admin/ops/liveness?max_age_seconds=60")
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["maxAgeSeconds"] == 60


async def test_admin_liveness_role_gates(db_session: Any) -> None:  # type: ignore[no-untyped-def]
    """门禁：user 秩 → 10004/403；未登录 → 10001/401（与 discovery/channels 同口径）。"""
    plain = User(sub="r77-plain", email="r77-plain@r77.test", nickname="plain")
    db_session.add(plain)
    await db_session.flush()

    gated = create_app()
    gated.dependency_overrides[get_db] = lambda: db_session
    gated.dependency_overrides[get_current_user_id] = lambda: plain.id
    resp = TestClient(gated).get("/api/v1/admin/ops/liveness")
    assert resp.status_code == 403 and resp.json()["code"] == 10004

    anonymous = create_app()
    anonymous.dependency_overrides[get_db] = lambda: db_session
    resp = TestClient(anonymous).get("/api/v1/admin/ops/liveness")
    assert resp.status_code == 401 and resp.json()["code"] == 10001
