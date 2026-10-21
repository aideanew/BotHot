"""STEP-25 S25.1.2：推送域 + 热点域写接口的秩矩阵（连库，`@ci` 判）。

判据只看是不是 10004（"无此操作权限"），不要求 200：每个请求都故意构造成在**授权之后**
就停下的形状（不存在的 id ⇒ 404、非法参数 ⇒ 422、已存在的日报 ⇒ 400），
这样矩阵不会真的投递消息、调 LLM 或入队任务，也不和业务前置耦合。

FastAPI 先解依赖（角色门在依赖里）再校验 body/query，所以 user 角色拿到的一定是 10004，
而不是 422——矩阵的 user 列因此有意义。

权限边界按用户裁决 D-V12-12（2026-10-19）：
- 运营(operator)可：建/改/删/立即执行推送任务、测试推送、改渠道的名称与启停、触发热点聚簇、生成日报；
- 只给管理员(admin)：新建推送渠道（新建即写入凭据）、删除推送渠道、修改渠道凭据
  （`webhook_url` / `secret` / `extra_config`）。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_sub, get_db
from app.main import create_app
from app.models.bothot_entities import DailyReport
from app.models.entities import User

B = "/api/v1/bots"
H = "/api/v1/hot"
A = "/api/v1/admin"
NOPE = "00000000-0000-0000-0000-000000000000"
EXISTING_REPORT_DATE = "1999-01-01"

# (标签, 方法, 路径, json body 或 None)
OPERATOR_OK: list[tuple[str, str, str, Any]] = [
    ("建推送任务", "POST", f"{B}/tasks", {"name": "x", "bot_channel_id": NOPE, "trigger_type": "manual"}),
    ("改推送任务", "PUT", f"{B}/tasks/{NOPE}", {"name": "x"}),
    ("删推送任务", "DELETE", f"{B}/tasks/{NOPE}", None),
    ("立即执行任务", "POST", f"{B}/tasks/{NOPE}/run", None),
    ("测试推送", "POST", f"{B}/{NOPE}/test", None),
    ("改渠道名称/启停", "PUT", f"{B}/{NOPE}", {"name": "x", "status": "disabled"}),
    ("触发热点聚簇", "POST", f"{H}/topics/cluster?days=not-an-int", None),
    ("生成日报", "POST", f"{H}/daily/generate?report_date={EXISTING_REPORT_DATE}", None),
    # STEP-28 S28.4.1：采集配置面（D-V12-12 放开给 operator 的两写一读）。
    # body 都故意构造成"过授权门之后才失败"的形状，所以矩阵不会真改配置。
    ("改采集渠道配置", "PUT", f"{A}/discovery/config", {"enabled": ["nope"], "default": "nope"}),
    ("改采集分类配置", "PUT", f"{A}/categories", {"categories": []}),
    ("查采集分类配置", "GET", f"{A}/categories", None),
    # D-V12-20 的读面：运营能看当前生效的兜底形状（看不到任何凭据）。
    ("查付费兜底配置", "GET", f"{A}/article-fallback", None),
]

ADMIN_ONLY: list[tuple[str, str, str, Any]] = [
    ("新建推送渠道", "POST", B, {"name": "x", "channel_type": "not-a-type", "webhook_url": "http://127.0.0.1:1/h"}),
    ("删除推送渠道", "DELETE", f"{B}/{NOPE}", None),
    ("改渠道 webhook_url", "PUT", f"{B}/{NOPE}", {"webhook_url": "http://127.0.0.1:1/h"}),
    ("改渠道 secret", "PUT", f"{B}/{NOPE}", {"secret": "s"}),
    ("改渠道 extra_config", "PUT", f"{B}/{NOPE}", {"extra_config": "{}"}),
    # STEP-10 S10.V15.2（D-V12-20）：付费兜底的写面涉及花钱 ⇒ 与"改渠道凭据"同族，只给 admin。
    # body 给的是"过授权门之后才失败"的形状（无预算 ⇒ 10005），不会真把兜底打开。
    ("改付费兜底配置", "PUT", f"{A}/article-fallback", {"enabled": True, "trigger": [], "providers": []}),
]


async def _seed(db_session: Any) -> dict[str, User]:
    users: dict[str, User] = {}
    for role in ("user", "operator", "admin"):
        sub = f"s25-{role}-{uuid.uuid4().hex[:8]}"
        users[role] = User(sub=sub, email=f"{sub}@s25.test", nickname=sub, role=role)
        db_session.add(users[role])
    db_session.add(DailyReport(report_date=EXISTING_REPORT_DATE, title="s25 已存在", generated_by="manual"))
    await db_session.flush()
    return users


def _call(db_session: Any, user: User, method: str, path: str, body: Any) -> tuple[int, Any]:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_sub] = lambda: user.sub
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.request(method, path, json=body) if body is not None else client.request(method, path)
    try:
        code = resp.json().get("code")
    except ValueError:
        code = None
    return resp.status_code, code


def _matrix(
    db_session: Any, users: dict[str, User], rows: list[tuple[str, str, str, Any]]
) -> dict[tuple[str, str], tuple[int, Any]]:
    return {
        (label, role): _call(db_session, users[role], method, path, body)
        for (label, method, path, body) in rows
        for role in ("user", "operator", "admin")
    }


async def test_operator_write_surface_matches_d_v12_12(db_session: Any) -> None:
    users = await _seed(db_session)
    got = _matrix(db_session, users, OPERATOR_OK)
    wrong: list[str] = []
    for (label, role), (status, code) in got.items():
        denied = code == 10004
        if role == "user" and not denied:
            wrong.append(f"user {label} 应 10004，实得 {status}/{code}")
        if role in ("operator", "admin") and denied:
            wrong.append(f"{role} {label} 不应 10004，实得 {status}/{code}")
    assert not wrong, "\n".join(wrong)


async def test_admin_only_surface_matches_d_v12_12(db_session: Any) -> None:
    users = await _seed(db_session)
    got = _matrix(db_session, users, ADMIN_ONLY)
    wrong: list[str] = []
    for (label, role), (status, code) in got.items():
        denied = code == 10004
        if role in ("user", "operator") and not denied:
            wrong.append(f"{role} {label} 应 10004，实得 {status}/{code}")
        if role == "admin" and denied:
            wrong.append(f"admin {label} 不应 10004，实得 {status}/{code}")
    assert not wrong, "\n".join(wrong)


@pytest.mark.parametrize("field", ["webhook_url", "secret", "extra_config"])
async def test_operator_credential_edit_is_denied_even_mixed_with_allowed_fields(db_session: Any, field: str) -> None:
    """夹带：同一个 PUT 里既改名称（运营可）又改凭据（仅管理员）⇒ 整单 10004，不得部分生效。"""
    users = await _seed(db_session)
    body = {"name": "x", field: "{}" if field == "extra_config" else "v"}
    status, code = _call(db_session, users["operator"], "PUT", f"{B}/{NOPE}", body)
    assert code == 10004, f"operator 夹带 {field} 实得 {status}/{code}"
