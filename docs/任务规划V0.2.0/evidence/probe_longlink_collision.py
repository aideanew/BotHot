"""探针 P-3：同号两篇不同长链文章，第二篇是否被第一篇的缓存冒名顶替。

用法（不入库，跑完即删）：
  cp evidence/probe_longlink_collision.py apps/api/tests/test_zz_probe_longlink.py
  DATABASE_URL=$DSN AIDEANBOT_TEST_PG_DSN=$DSN pytest apps/api/tests/test_zz_probe_longlink.py -q -s
  rm apps/api/tests/test_zz_probe_longlink.py
2026-10-12 @61739f0 实测输出：PROBE fetch_count= 1 A.hitCache= False B.hitCache= True same_doc= True
修复后期望：fetch_count= 2 B.hitCache= False same_doc= False
"""
from test_langbot import _client, _lb_transport, _StubResolver  # noqa: F401
from test_p0_asset_cache import _CountingStubResolver, _seeder_space
from app.services.kb import KnowledgeBaseService

A = "https://mp.weixin.qq.com/s?__biz=MjM5MjgwNTQ1MQ==&mid=2650000001&idx=1&sn=aaaa1111"
B = "https://mp.weixin.qq.com/s?__biz=MjM5MjgwNTQ1MQ==&mid=2650000002&idx=1&sn=bbbb2222"


async def test_probe_two_distinct_long_links(db_session):
    _, space = await _seeder_space(db_session, "probe-longlink")
    r = _CountingStubResolver()
    svc = KnowledgeBaseService(_client(), db_session, r)
    a = await svc.ingest_url(space.id, A)
    b = await svc.ingest_url(space.id, B)
    print("\nPROBE fetch_count=", r.fetch_count, "A.hitCache=", a["hitCache"],
          "B.hitCache=", b["hitCache"], "same_doc=", a["docId"] == b["docId"])
