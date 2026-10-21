"""STEP-31：运营与管理写操作的结构化审计日志（D-V17-02）。

S31.1 先红：从路由表**枚举**三个前缀下的 POST/PUT/PATCH/DELETE，逐个以 admin
身份请求一次，断言日志里恰好一条字段齐全的 `event="audit"` 记录。枚举而非手写
清单——新增写端点自动纳入，清单变短也会被下面的计数锚抓住。

S31.3 负面断言：
- 请求体里的标记串绝不进审计记录（本文件连请求体都不读）；
- 匿名请求（401，没有操作者）不产生审计记录；
- 普通用户被拒（403）产生一条，且 status=403、code=10004。

本文件连库（`db_session`），因为它要证明真实的操作者解析链路（sub → users 行 →
role），而不是在测试里自己伪造 `request.state`。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from structlog.testing import capture_logs
from test_idor_matrix import _enumerate_operations

from app.api.deps import get_current_sub, get_db
from app.main import app
from app.models.entities import User

AUDIT_PREFIXES = ("/api/v1/bots", "/api/v1/admin", "/api/v1/sources")
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
AUDIT_FIELDS = frozenset(
    {
        "actor_sub",
        "actor_role",
        "method",
        "route",
        "path_params",
        "status",
        "code",
        "request_id",
        "ts",
    }
)
ADMIN_SUB = "s31-admin"
PLAIN_SUB = "s31-plain"
MARKER = "s31-body-marker"
#: 路径参数统一填同一个不存在的值：端点返回 404/422 都行，审计记录必须在。
MISSING = "s31-missing"
_PARAM_RE = re.compile(r"\{([a-zA-Z_]+)\}")


def _under_audit_prefix(path: str) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in AUDIT_PREFIXES)


AUDITED_OPERATIONS: list[tuple[str, str]] = sorted(
    (path, method)
    for path, method, _ in _enumerate_operations(list(app.routes))
    if method in WRITE_METHODS and _under_audit_prefix(path)
)


def _fill(path: str) -> str:
    return _PARAM_RE.sub(MISSING, path)


def _declared_params(path: str) -> dict[str, str]:
    return {name: MISSING for name in _PARAM_RE.findall(path)}


async def _seed(db_session: Any) -> None:
    db_session.add_all(
        [
            User(sub=ADMIN_SUB, email="s31-admin@test.local", nickname=ADMIN_SUB, role="admin"),
            User(sub=PLAIN_SUB, email="s31-plain@test.local", nickname=PLAIN_SUB, role="user"),
        ]
    )
    await db_session.flush()


def _client(db_session: Any, sub: str | None = None) -> TestClient:
    """真实 `create_app()` + 覆写身份入口与会话，沿用 `test_idor_matrix.py` 的做法。

    `sub=None` 表示匿名：不覆写 `get_current_sub`，让真实认证链路给出 401。
    """
    from app.main import create_app

    application = create_app()
    application.dependency_overrides[get_db] = lambda: db_session
    if sub is not None:
        application.dependency_overrides[get_current_sub] = lambda: sub
    return TestClient(application, raise_server_exceptions=False)


def _audit_entries(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [entry for entry in logs if entry.get("event") == "audit"]


def _json_code(response: Any) -> int | None:
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("code") if isinstance(body, dict) else None


def test_write_operation_enumeration_has_a_measured_anchor() -> None:
    """计数锚（2026-10-21 本机现读，STEP-10 S10.V15.2 之后）：三个前缀下 26 个写操作（admin 15 / bots 8 / sources 3）。

    真加/删写端点时来改这条；不要把断言放宽成 `>= 0`——清单变短就没人发现。
    STEP-28 加了 2 个 admin 写（渠道、分类），STEP-10 V15.2 又加 1 个（付费兜底，仅 admin）。
    三条都是"参数化自动长出来 ⇒ 各自恰好一条审计记录"绿之后才追认的数，不是先改数再期待它绿。
    """
    assert AUDITED_OPERATIONS, "枚举读空了——`app.routes` 的结构又变了"
    assert len(AUDITED_OPERATIONS) == 26, AUDITED_OPERATIONS
    assert {method for _, method in AUDITED_OPERATIONS} <= WRITE_METHODS
    assert {method for _, method in AUDITED_OPERATIONS} == WRITE_METHODS
    assert len([p for p, _ in AUDITED_OPERATIONS if p.startswith("/api/v1/admin")]) == 15
    assert len([p for p, _ in AUDITED_OPERATIONS if p.startswith("/api/v1/bots")]) == 8
    assert len([p for p, _ in AUDITED_OPERATIONS if p.startswith("/api/v1/sources")]) == 3


# ── S31.1：每个写操作恰好一条 ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "method"),
    AUDITED_OPERATIONS,
    ids=[f"{method} {path}" for path, method in AUDITED_OPERATIONS],
)
async def test_each_write_operation_emits_exactly_one_audit_record(
    db_session: Any, path: str, method: str
) -> None:
    """S31.1：admin 请求每个写操作 ⇒ 恰好一条字段齐全、可回查的审计记录。

    不要求端点成功：写操作**被拒的 4xx 也写**，故空请求体造成的 422 同样计一条。
    """
    await _seed(db_session)
    client = _client(db_session, ADMIN_SUB)

    with capture_logs() as logs:
        response = client.request(method, _fill(path))

    entries = _audit_entries(logs)
    assert len(entries) == 1, (
        f"{method} {path}：审计条数 {len(entries)}（status={response.status_code}，"
        f"body={response.text[:120]!r}）"
    )
    entry = entries[0]
    # 审计负载固定 9 个字段；event/log_level 是 structlog 与捕获器的框架元数据。
    payload = {
        key: value for key, value in entry.items() if key not in {"event", "log_level", "level", "timestamp", "logger"}
    }
    assert set(payload) == AUDIT_FIELDS, f"字段集合不符：{sorted(payload)}"
    assert entry["actor_sub"] == ADMIN_SUB
    assert entry["actor_role"] == "admin"
    assert entry["method"] == method
    assert entry["route"] == path, "route 必须是路由模板，不是实际 URL"
    assert entry["path_params"] == _declared_params(path)
    assert entry["status"] == response.status_code
    assert entry["code"] == _json_code(response)
    assert entry["request_id"]
    assert entry["request_id"] == response.headers["X-Request-ID"]
    assert datetime.fromisoformat(entry["ts"]).tzinfo is not None


# ── S31.3：负面断言 ──────────────────────────────────────────────────────────


async def test_request_body_marker_never_reaches_the_audit_log(db_session: Any) -> None:
    """请求体里的标记串绝不出现在审计记录中（拒绝路径与执行路径各一条）。"""
    await _seed(db_session)

    plain = _client(db_session, PLAIN_SUB)
    with capture_logs() as logs:
        denied = plain.post(
            "/api/v1/bots",
            json={"name": MARKER, "channel_type": MARKER, "webhook_url": MARKER},
        )
    assert denied.status_code == 403
    denied_entries = _audit_entries(logs)
    assert len(denied_entries) == 1
    assert MARKER not in json.dumps(denied_entries, ensure_ascii=False)

    admin = _client(db_session, ADMIN_SUB)
    with capture_logs() as logs:
        missing = admin.patch(f"/api/v1/sources/{MISSING}", json={"name": MARKER})
    assert missing.status_code == 404
    executed_entries = _audit_entries(logs)
    assert len(executed_entries) == 1
    assert executed_entries[0]["path_params"] == {"source_id": MISSING}
    assert MARKER not in json.dumps(executed_entries, ensure_ascii=False)


async def test_plain_user_forbidden_is_audited_as_403_10004(db_session: Any) -> None:
    """普通用户被拒也是一次写操作尝试：一条记录，status=403、code=10004。"""
    await _seed(db_session)
    client = _client(db_session, PLAIN_SUB)

    with capture_logs() as logs:
        response = client.post(
            "/api/v1/bots",
            json={"name": "s31-denied", "channel_type": "web", "webhook_url": ""},
        )

    assert response.status_code == 403
    entries = _audit_entries(logs)
    assert len(entries) == 1
    assert entries[0]["actor_sub"] == PLAIN_SUB
    assert entries[0]["actor_role"] == "user"
    assert entries[0]["status"] == 403
    assert entries[0]["code"] == 10004


async def test_anonymous_401_is_not_audited(db_session: Any) -> None:
    """401 没有操作者，不写审计记录。"""
    await _seed(db_session)
    client = _client(db_session)

    with capture_logs() as logs:
        response = client.post(
            "/api/v1/bots",
            json={"name": "s31-anon", "channel_type": "web", "webhook_url": ""},
        )

    assert response.status_code == 401
    assert _audit_entries(logs) == []
