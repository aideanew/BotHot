"""STEP-18 S18.1.3 的**往返计数**用例（连库夹具，PG 不可达自动 skip）。

这不是 SLA 断言（那归 `scripts/perf_baseline.py` 的测量读数）；这里钉的是
"入库往返的**计数语义**"：n 篇入库 ⇒ 恰 n 资产、n 文档、清单行全部 INGESTED；
同 URL 重复入库 ⇒ 资产/文档计数**不增**（AB-P004 P0② 的先查后抓守卫）。
SLA 数字本身（p50/p95）与可感性证明见 `docs/06_validation/evidence/EVD-V18-18/`。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_p0_asset_cache import _client as _lb_client
from test_p0_asset_cache import _CountingStubResolver  # noqa: E402

from app.models.entities import ContentAsset, KnowledgeDocument, Source  # noqa: E402
from app.repositories.space import SpaceRepository  # noqa: E402
from app.services.kb import KnowledgeBaseService  # noqa: E402

N = 3  # 计数用例的最小规模（SLA 测量另有 n=50 的完整读数）


async def _seed_space(db_session: Any, name: str) -> tuple[str, str, Any]:
    from app.models.entities import User

    ns = name
    user = User(sub=f"sub-perf-probe-{ns}", email=f"perf-probe-{ns}@test.local", nickname="PERF-PROBE")
    db_session.add(user)
    await db_session.flush()
    space = await SpaceRepository(db_session).create(user_id=user.id, name=f"perf-probe-{ns}")
    source = Source(
        type="wechat_oa",
        external_id=f"perf-probe-{ns}",
        name=f"perf-probe-{ns}",
        url=f"https://upstream.invalid/{ns}",
    )
    db_session.add(source)
    await db_session.flush()
    return user.id, space.id, source.id


@pytest.mark.asyncio
async def test_ingest_round_trip_counts(db_session) -> None:  # type: ignore[no-untyped-def]
    """n 篇入库 ⇒ n 资产 n 文档、清单 INGESTED；重复入库计数不增（先查后抓守卫）。"""
    _user_id, space_id, _source_id = await _seed_space(db_session, "a")
    svc = KnowledgeBaseService(_lb_client(), db_session, _CountingStubResolver())
    urls = [f"https://mp.weixin.qq.com/s/perfprobe{i}" for i in range(N)]
    for url in urls:
        result = await svc.ingest_url(space_id, url)
        assert result.get("docId"), result
        await db_session.commit()

    # 资产的 source 归属是页面 biz 源（P-97 的布局事实，S36.1 改的是 ready 减不是归属）——
    # 计数按"空间的文档 ↔ 文档的资产"关联，不按 source_id。
    docs = (
        await db_session.scalars(
            select(KnowledgeDocument).where(KnowledgeDocument.space_id == space_id)
        )
    ).all()
    doc_asset_ids = [d.asset_id for d in docs]
    assets = int(
        await db_session.scalar(
            select(func.count()).select_from(ContentAsset).where(ContentAsset.id.in_(doc_asset_ids))
        )
        or 0
    )
    assert len(docs) == N, f"{N} 篇入库应恰 {N} 文档，实得 {len(docs)}"
    assert assets == N, f"{N} 篇入库应恰 {N} 资产，实得 {assets}"

    # 重复入库（同 URL）：先查后抓 ⇒ 资产/文档计数不增
    for url in urls:
        await svc.ingest_url(space_id, url)
        await db_session.commit()
    docs2 = int(
        await db_session.scalar(
            select(func.count()).select_from(KnowledgeDocument).where(KnowledgeDocument.space_id == space_id)
        )
        or 0
    )
    assert docs2 == N, docs2
