"""@linux 探针：role=user（默认角色）的已登录用户能否读到别人的推送渠道明文配置。
只读探针，不改业务代码：用 dependency_overrides 注入一个普通用户身份，向测试库播种一条属于另一用户的渠道。"""
import asyncio, json, os, uuid
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.main import create_app
from app.api.deps import get_current_sub, get_db
from app.models.bothot_entities import BotChannel
from app.core.secret_crypto import encrypt_extra_config

DSN = os.environ["AIDEANBOT_TEST_PG_DSN"]
cid = str(uuid.uuid4())

async def seed():
    eng = create_async_engine(DSN); f = async_sessionmaker(eng, expire_on_commit=False)
    async with f() as s:
        s.add(BotChannel(id=cid, name="owner-B-feishu", channel_type="feishu",
                         webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/probe-marker-webhook",
                         extra_config=encrypt_extra_config(cid, json.dumps({"app_secret": "probe-marker-appsecret"})),
                         status="active", user_id=None))
        await s.commit()
    await eng.dispose()

async def cleanup():
    eng = create_async_engine(DSN)
    async with eng.begin() as c:
        await c.exec_driver_sql("DELETE FROM bot_channels WHERE id=%s", (cid,)) if False else await c.execute(__import__("sqlalchemy").text("DELETE FROM bot_channels WHERE id=:i"), {"i": cid})
    await eng.dispose()

asyncio.run(seed())
app = create_app()
eng = create_async_engine(DSN); F = async_sessionmaker(eng, expire_on_commit=False)
async def _db():
    async with F() as s:
        yield s
app.dependency_overrides[get_current_sub] = lambda: "probe-plain-user-sub"   # 普通登录用户（不在 users 表 ⇒ 无任何角色）
app.dependency_overrides[get_db] = _db
c = TestClient(app)
for path in (f"/api/v1/bots/{cid}", "/api/v1/bots?page_size=100", f"/api/v1/bots/{cid}/logs", "/api/v1/bots/tasks"):
    r = c.get(path); body = r.json()
    txt = json.dumps(body, ensure_ascii=False)
    print(path, "->", r.status_code, "code=", body.get("code"),
          "| leaks webhook token:", "probe-marker-webhook" in txt, "| leaks decrypted app_secret:", "probe-marker-appsecret" in txt)
r = c.put(f"/api/v1/bots/{cid}", json={"name": "x"}); print("PUT (对照：有 require_roles) ->", r.status_code, r.json().get("code"))
asyncio.run(cleanup())
