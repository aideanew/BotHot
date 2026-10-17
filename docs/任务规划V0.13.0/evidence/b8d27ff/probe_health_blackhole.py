import time,os
from fastapi.testclient import TestClient
t=time.time()
from app.main import create_app
app=create_app(); print("create_app",round(time.time()-t,1))
t=time.time(); c=TestClient(app); r=c.get("/api/v1/system/health"); print(r.json()["data"]["deps"], round(time.time()-t,1))
