"""W6 A.3：/live + /ready 就绪探针契约，兼带 /health 非回归。

覆盖：
- /live 恒 200（进程在跑即活，不触依赖）；
- /health 仍 200（旧功能探活不回归）；
- /ready 三项（PG/Redis/schema）全 ok → 200；
- **alembic 版本不一致 → 实测 503**（验收 #3）：monkeypatch schema_guard 的
  head 与 current 返回不同值，驱动 `_check_schema` 走真实比对逻辑产出 mismatch，
  而非直接塞一个假结果——留 503 输出与明细。
- PG / Redis 任一不可达也 503。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.v1 import system
from app.core import schema_guard
from app.main import app


def test_live_always_200() -> None:
    resp = TestClient(app).get("/api/v1/system/live")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "alive"


def test_health_non_regression() -> None:
    """旧 /health 仍在、仍 200、仍带 deps——W6 不得回归它。"""
    resp = TestClient(app).get("/api/v1/system/health")
    assert resp.status_code == 200
    assert "deps" in resp.json()["data"]


def _stub_health(monkeypatch, pg: str = "ok", redis: str = "ok") -> None:
    async def _pg() -> str:
        return pg

    async def _redis() -> str:
        return redis

    monkeypatch.setattr(system, "_check_pg", _pg)
    monkeypatch.setattr(system, "_check_redis", _redis)


def test_ready_200_when_all_ok(monkeypatch) -> None:
    _stub_health(monkeypatch)
    monkeypatch.setattr(schema_guard, "get_alembic_head", lambda: "rev_head")

    async def _cur(_engine):  # noqa: ANN001
        return "rev_head"

    monkeypatch.setattr(schema_guard, "read_current_version_async", _cur)
    resp = TestClient(app).get("/api/v1/system/ready")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "ready"


def test_ready_503_on_alembic_version_mismatch(monkeypatch) -> None:
    """验收 #3：版本不一致实测 503 且带 current/head 明细。"""
    _stub_health(monkeypatch)
    monkeypatch.setattr(schema_guard, "get_alembic_head", lambda: "ab_head_latest")

    async def _stale(_engine):  # noqa: ANN001
        return "ab_old_rev"

    monkeypatch.setattr(schema_guard, "read_current_version_async", _stale)
    resp = TestClient(app).get("/api/v1/system/ready")
    assert resp.status_code == 503
    data = resp.json()["data"]
    assert data["status"] == "not_ready"
    schema = data["checks"]["schema"]
    assert schema["ok"] is False
    assert schema["state"] == "mismatch"
    assert schema["current"] == "ab_old_rev"
    assert schema["head"] == "ab_head_latest"


def test_ready_503_when_pg_down(monkeypatch) -> None:
    _stub_health(monkeypatch, pg="unreachable")
    monkeypatch.setattr(schema_guard, "get_alembic_head", lambda: "rev_head")

    async def _cur(_engine):  # noqa: ANN001
        return "rev_head"

    monkeypatch.setattr(schema_guard, "read_current_version_async", _cur)
    resp = TestClient(app).get("/api/v1/system/ready")
    assert resp.status_code == 503
    assert resp.json()["data"]["checks"]["postgres"]["ok"] is False


def test_ready_503_when_redis_down(monkeypatch) -> None:
    _stub_health(monkeypatch, redis="unreachable")
    monkeypatch.setattr(schema_guard, "get_alembic_head", lambda: "rev_head")

    async def _cur(_engine):  # noqa: ANN001
        return "rev_head"

    monkeypatch.setattr(schema_guard, "read_current_version_async", _cur)
    resp = TestClient(app).get("/api/v1/system/ready")
    assert resp.status_code == 503
    assert resp.json()["data"]["checks"]["redis"]["ok"] is False
