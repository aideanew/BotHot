"""探针 P-2：Manifest(workUuid) 与 ContentAsset(article_key) 键失配 ⇒ 已 READY 的篇仍被 Diff 判为新增。
2026-10-12 @61739f0 实测：已 READY 入库后 Diff 仍判为新增篇数 = 1（修复后期望 0）。
用法：cd apps/api && AIDEANBOT_TEST_PG_DSN=$DSN .venv/bin/python evidence/probe_reenqueue_loop.py
"""
import asyncio, uuid
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.models.entities import Source, ArticleManifest, ContentAsset, SourceSubscription, KnowledgeSpace
from app.services.subscription import SourceSubscriptionService
from app.services.kb import _article_key
from app.repositories.user import SqlAlchemyUserStore
from app.repositories.space import SpaceRepository
import os
DSN=os.environ["AIDEANBOT_TEST_PG_DSN"]  # 隔离测试库，禁止指向 5433/5435
async def main():
    eng=create_async_engine(DSN); f=async_sessionmaker(eng, expire_on_commit=False)
    async with f() as s:
        tag=uuid.uuid4().hex[:8]
        u=await SqlAlchemyUserStore(s).upsert_by_sub("probe-"+tag,f"p{tag}@t.local","P")
        sp=await SpaceRepository(s).create(user_id=u.id,name="probe-"+tag)
        src=Source(type="wechat_oa",external_id="MzProbe"+tag,name="p"); s.add(src); await s.flush()
        sub=SourceSubscription(user_id=u.id,source_id=src.id,space_id=sp.id,sync_policy="auto"); s.add(sub); await s.flush()
        work_uuid="a"*24+tag; url=f"https://mp.weixin.qq.com/s/RealToken{tag}"
        s.add(ArticleManifest(source_id=src.id,external_id=work_uuid,url=url,title="t",content_hash="h",status="DISCOVERED"))
        # 模拟 kb._persist 真实写法：asset.external_id=_article_key(url)
        s.add(ContentAsset(source_id=src.id,external_id=_article_key(url),url=url,title="t",content_hash="h2",content_markdown="x",status="READY"))
        await s.flush()
        svc=SourceSubscriptionService(s)
        new=await svc._compute_new_manifests(src.id, sub.id)
        print("manifest.external_id=",work_uuid,"asset.external_id=",_article_key(url))
        print("已 READY 入库后 Diff 仍判为新增篇数 =",len(new))
        await s.rollback()
    await eng.dispose()
asyncio.run(main())
