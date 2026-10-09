"""QA 会话铸造脚本（临时）：直接在 Redis 造服务端会话 + PG 造 users 行。

用途：主平台（localhost:3000，SSO 授权方）不可达时，绕过 code 交换，
直接产出与 AuthService.handle_callback 等价的会话产物，以便对 BotHot
自身的鉴权边界（cookie → sub → users 行 → role）做端到端测试。

边界（A-T024，2026-10-09 补注）：本脚本铸造的 access_token = "qa-fixture-<sub>"
假串，不能送主平台验。get_me 仅在命中 settings.qa_fixture_token_prefix（默认
"qa-fixture-"）时才短路到本地 users 行；主平台在线时本短路为唯一可用途径。
本前缀在生产环境必须显式置空（production_guard_violations 拒启）。
使用本脚本后请优先重新走一次真接 SSO（确保主平台 oidc_clients 已登记本服务 client_id）。

产物：stdout 打印 `sub=<sub> session_id=<id>` 行。
"""

from __future__ import annotations

import asyncio
import sys
import time
import uuid

import redis.asyncio as aioredis
from sqlalchemy import select

from app.core.config import get_settings
from app.db import create_engine_and_session
from app.models.entities import User
from app.services.auth.session_store import RedisSessionStore, SessionRecord

if sys.platform == "win32":
    # psycopg async 不兼容 Windows 默认 ProactorEventLoop，须换 Selector 实现
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ACCOUNTS = (
    # (sub, email, nickname, role)
    ("qa-admin-001", "qa-admin@bothot.local", "QA管理员", "admin"),
    ("qa-operator-001", "qa-operator@bothot.local", "QA运营", "operator"),
    ("qa-user-001", "qa-user@bothot.local", "QA普通用户", "user"),
)


async def main() -> None:
    settings = get_settings()
    engine, factory = create_engine_and_session()
    store = RedisSessionStore(aioredis.from_url(settings.redis_url))

    async with factory() as session:
        for sub, email, nickname, role in ACCOUNTS:
            row = (await session.execute(select(User).where(User.sub == sub))).scalar_one_or_none()
            if row is None:
                row = User(
                    id=str(uuid.uuid4()), sub=sub, email=email, nickname=nickname, role=role
                )
                session.add(row)
            else:
                row.role, row.email, row.nickname, row.status = role, email, nickname, "ACTIVE"
            await session.commit()
            print(f"user {sub}: id={row.id} role={row.role}")

    ttl = settings.session_ttl_seconds
    for sub, email, nickname, _role in ACCOUNTS:
        record = SessionRecord(
            session_id=uuid.uuid4().hex,
            sub=sub,
            email=email,
            nickname=nickname,
            access_token=f"qa-fixture-access-{sub}",
            refresh_token=f"qa-fixture-refresh-{sub}",
            # 远期过期：避免 get_me 触发 refresh 轮换（refresh 会回主平台，主平台不可达）
            access_expires_at=time.time() + ttl,
        )
        await store.create(record, ttl)
        print(f"session {sub}: cookie={settings.session_cookie_name} value={record.session_id}")

    await engine.dispose()


asyncio.run(main())
