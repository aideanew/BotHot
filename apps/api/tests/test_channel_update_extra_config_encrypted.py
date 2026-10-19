"""P-39（STEP-25 执行中发现）：`PUT /api/v1/bots/{id}` 改 `extra_config` 时必须落密文。

改前 `update_channel` 写 `ch.extra_config = payload.extra_config`（明文），而 `create_channel`
与迁移 ab1005w5b 都落 AES-256-GCM 密文。读侧 `decrypt_extra_config` 对 `{` 开头的值原样返回
（存量兼容读），所以 API 回显看起来一切正常——缺陷只在库里看得见，这条用例直接读库判。
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_current_sub, get_db
from app.main import create_app
from app.models.bothot_entities import BotChannel
from app.models.entities import User

MARKER = "p39-marker-app-secret"


async def test_admin_put_extra_config_is_stored_encrypted(db_session: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    key = base64.b64encode(os.urandom(32)).decode()
    fake = type("S", (), {"push_secret_master_key": key})
    monkeypatch.setattr("app.core.secret_crypto.get_settings", lambda: fake())

    sub = f"p39-admin-{uuid.uuid4().hex[:8]}"
    admin = User(sub=sub, email=f"{sub}@p39.test", nickname=sub, role="admin")
    cid = str(uuid.uuid4())
    db_session.add_all(
        [
            admin,
            BotChannel(
                id=cid,
                name=f"p39-{cid[:8]}",
                channel_type="feishu",
                webhook_url="http://127.0.0.1:1/h",
                status="active",
            ),
        ]
    )
    await db_session.flush()

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_sub] = lambda: sub
    client = TestClient(app, raise_server_exceptions=False)

    plaintext = json.dumps({"app_secret": MARKER})
    resp = client.put(f"/api/v1/bots/{cid}", json={"extra_config": plaintext})
    assert resp.status_code == 200 and resp.json()["code"] == 0, resp.json()
    # API 语义不变：回显仍是解密后的明文
    assert resp.json()["data"]["extra_config"] == plaintext

    raw = (await db_session.execute(select(BotChannel.extra_config).where(BotChannel.id == cid))).scalar_one()
    assert MARKER not in raw, f"库里是明文：{raw[:60]}"
    assert not raw.startswith("{"), "库里仍是 JSON 明文形态"
