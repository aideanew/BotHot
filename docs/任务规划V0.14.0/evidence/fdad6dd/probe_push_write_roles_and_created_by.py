"""@linux 只读探针（main@fdad6dd）：
① 运营(operator)能否调推送域写接口（P-23：require_roles("admin","operator") 经 max() 变 admin-only）；
② 管理员按前端口径建推送任务（created_by=SSO sub / 不传）能否落库（P-26：列是 users.id 外键）。
播种两名本地用户 + 一条渠道，结束时删除。"""
import asyncio, json, os, uuid
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.main import create_app
from app.api.deps import get_current_sub, get_db
from app.models.entities import User
from app.models.bothot_entities import BotChannel

DSN = os.environ["AIDEANBOT_TEST_PG_DSN"]
tag = uuid.uuid4().hex[:8]
op_sub, ad_sub, cid = f"probe-op-{tag}", f"probe-admin-{tag}", str(uuid.uuid4())

async def seed():
    e = create_async_engine(DSN); f = async_sessionmaker(e, expire_on_commit=False)
    async with f() as s:
        s.add_all([User(sub=op_sub, email=f"{op_sub}@x", role="operator"), User(sub=ad_sub, email=f"{ad_sub}@x", role="admin"),
                   BotChannel(id=cid, name=f"probe-{tag}", channel_type="webhook", webhook_url="https://example.invalid/hook", status="active")])
        await s.commit()
    await e.dispose()

async def cleanup():
    e = create_async_engine(DSN)
    async with e.begin() as c:
        await c.execute(text("DELETE FROM push_tasks WHERE bot_channel_id=:c"), {"c": cid})
        await c.execute(text("DELETE FROM bot_channels WHERE id=:c"), {"c": cid})
        await c.execute(text("DELETE FROM users WHERE sub IN (:a,:b)"), {"a": op_sub, "b": ad_sub})
    await e.dispose()

asyncio.run(seed())
app = create_app(); E = create_async_engine(DSN); F = async_sessionmaker(E, expire_on_commit=False)
async def _db():
    async with F() as s:
        yield s
app.dependency_overrides[get_db] = _db
c = TestClient(app, raise_server_exceptions=False)
def as_(sub): app.dependency_overrides[get_current_sub] = lambda: sub
body = {"name": f"probe-{tag}", "bot_channel_id": cid, "trigger_type": "manual"}
try:
    as_(op_sub)
    r = c.get("/api/v1/bots/tasks"); print("① operator GET  /bots/tasks           ->", r.status_code, r.json().get("code"))
    r = c.post("/api/v1/bots/tasks", json=body); print("① operator POST /bots/tasks           ->", r.status_code, r.json().get("code"))
    r = c.put(f"/api/v1/bots/{cid}", json={"name": "x"}); print("① operator PUT  /bots/{id}            ->", r.status_code, r.json().get("code"))
    as_(ad_sub)
    r = c.post("/api/v1/bots/tasks", json={**body, "created_by": ad_sub}); print("② admin POST created_by=<SSO sub>（前端口径）->", r.status_code, (r.json() if r.headers.get("content-type","").startswith("application/json") else {}).get("code"))
    r = c.post("/api/v1/bots/tasks", json=body); print("② admin POST created_by 缺省（后端兜 \"system\"）->", r.status_code, (r.json() if r.headers.get("content-type","").startswith("application/json") else {}).get("code"))
finally:
    asyncio.run(cleanup())
