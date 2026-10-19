"""STEP-24：推送任务创建恒 500 与创建者归属服务端化（S24.1 先红 + 修复后防复发）。

缺陷（`docs/任务规划V0.14.0/evidence/fdad6dd/probe_push_write_roles_and_created_by.txt` ②）：
`create_push_task` 写 `created_by=payload.created_by or "system"`，而 `push_tasks.created_by`
是指向 `users.id` 的 NOT NULL 外键——
- 前端口径传 SSO `sub`（`PushTasksTab.tsx` 旧写法）⇒ 外键违例 ⇒ 500/50001；
- 不传 ⇒ 字面量 `"system"` 也不是任何 `users.id` ⇒ 同样 500/50001；
- 传另一个真实 `users.id` ⇒ 落库成功，但归属被调用方任意伪造（写侧越权）。

修复口径（D-V11-02）：归属只取当前登录者的本地 `users.id`，请求体里的 `created_by` 一律忽略。

身份注入按 `test_bots_read_authz.py::_client` 的做法覆写 `get_current_sub`，让
`sub → users 行 → require_role` 的真实授权链跑完，不抄近路覆写 `get_current_user_id`。
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_current_sub, get_db
from app.main import create_app
from app.models.bothot_entities import BotChannel, PushTask
from app.models.entities import User

TASKS = "/api/v1/bots/tasks"


async def _seed_user(db_session: Any, role: str) -> User:
    sub = f"s24-{role}-{uuid.uuid4().hex[:8]}"
    user = User(sub=sub, email=f"{sub}@s24.test", nickname=sub, role=role)
    db_session.add(user)
    await db_session.flush()
    return user


async def _seed_channel(db_session: Any) -> str:
    cid = str(uuid.uuid4())
    db_session.add(
        BotChannel(
            id=cid,
            name=f"s24-{cid[:8]}",
            channel_type="webhook",
            webhook_url="https://example.invalid/s24-hook",
            status="active",
        )
    )
    await db_session.flush()
    return cid


def _client(db_session: Any, user: User) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_sub] = lambda: user.sub
    return TestClient(app, raise_server_exceptions=False)


def _body(cid: str, **extra: Any) -> dict[str, Any]:
    return {"name": f"s24-task-{uuid.uuid4().hex[:6]}", "bot_channel_id": cid, "trigger_type": "manual", **extra}


async def _owner_in_db(db_session: Any, task_id: str) -> str:
    row = (await db_session.execute(select(PushTask.created_by).where(PushTask.id == task_id))).scalar_one()
    return str(row)


async def test_admin_creates_task_and_owner_is_local_user_id(db_session: Any) -> None:
    """S24.1.1：admin 不传 `created_by` 建任务 ⇒ 200/0，响应与落库的归属都等于自己的 `users.id`。

    改前：后端兜字面量 `"system"` ⇒ 外键违例 ⇒ 500/50001。
    """
    admin = await _seed_user(db_session, "admin")
    cid = await _seed_channel(db_session)
    resp = _client(db_session, admin).post(TASKS, json=_body(cid))
    body = resp.json()
    assert resp.status_code == 200 and body.get("code") == 0, f"实得 {resp.status_code}/{body}"
    assert body["data"]["created_by"] == admin.id, body["data"]
    assert await _owner_in_db(db_session, body["data"]["id"]) == admin.id


async def test_forged_created_by_is_ignored(db_session: Any) -> None:
    """S24.1.2：请求体里的 `created_by` 不改变归属。

    两种伪造各打一次：另一个**真实存在**的本地用户 id（改前会落库成功 = 越权），
    以及 SSO `sub`（旧前端口径，改前 500）。改后两次都应 200/0 且归属 = 当前登录者。
    """
    admin = await _seed_user(db_session, "admin")
    victim = await _seed_user(db_session, "user")
    cid = await _seed_channel(db_session)
    client = _client(db_session, admin)

    for forged in (victim.id, admin.sub):
        resp = client.post(TASKS, json=_body(cid, created_by=forged))
        body = resp.json()
        assert resp.status_code == 200 and body.get("code") == 0, (
            f"created_by={forged!r} 实得 {resp.status_code}/{body}"
        )
        assert body["data"]["created_by"] == admin.id, f"created_by={forged!r} 改写了归属：{body['data']}"
        assert await _owner_in_db(db_session, body["data"]["id"]) == admin.id
