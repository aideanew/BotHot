"""STEP-06 / S6.1 采集端到端闭环：六个发现渠道各跑通一条「发现 → 清单 → 入列 → 入库 → 二轮 Diff=0」。

桩的边界（卡面 §3）——只有**上游 HTTP** 是假的：
- provider 吃 `tests/fixtures/provider_payloads/` 里的样本（复用 `test_provider_contract._BUILDERS`
  的真客户端类 + `httpx.MockTransport`），零真实付费调用；
- LangBot 与文章页抓取用 `test_langbot` 的 MockTransport / `_StubResolver`；
其余全是真的：`ManifestSyncService` / `SourceSubscriptionService.run_incremental_sync` /
`JobWorker` / `KnowledgeBaseService.ingest_url` / 真实 PostgreSQL（`db_session` 外层事务回滚隔离）。

为什么值得六个渠道各跑一遍，而不是「一条通了就算通」：六个渠道在链路上**不是同一条路径**——
`_map_row` 的别名组不同、`external_id` 是上游原样透传还是 S3.2 归一出的字面 `id`、清单键落在
`b:` 支还是 `h:` 兜底支、RSS 还会在发现层就滤掉外链（D-V2-03）。分段用例各自验过自己那一段，
但「发现层的产物能不能一路走到资产行」从来没有一个地方同时验过六次。

本轮实测到的两个非对称（判据位置见 `test_e2e_round_trip` 的最后两条断言）：
1. 五个微信渠道的资产落回**清单同一个 source 行**（`_ensure_source` 按页面 biz 命中预置源），
   所以 Diff 的 ready 键减这一支对它们是真的在减；RSS 的清单挂在 `type=rss` 的源上、资产挂在
   `type=wechat_oa` 的 biz 源上，两支 source 永不相同 ⇒ ready 键减对 RSS 结构性失明（登记 P-97）。
2. 上面那条不是读码推论，是变异实测：把 `_compute_new_manifests` 的 `status == DISCOVERED` 谓词
   摘掉后（`app/services/subscription.py`，EVD 记 run 时点），六个用例里**只有 rss 转红**，
   报 `30005 manifest 非法流转: INGESTED → ENQUEUED`——五个微信渠道被 ready 键减挡住了，
   RSS 没有那道守卫，于是真把已入库的篇重新入列了。正常态下二轮 Diff=0 对六个渠道都成立，
   但 RSS 只由状态门守着：清单一旦被合法回退成 DISCOVERED（批次 6 的失败重试面），
   RSS 会重复排队（入库本身仍走缓存命中，不会重复建资产，代价是一轮白跑）。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from fixtures.wechat_urls import BIZ_A
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from test_job_worker import _worker
from test_langbot import _client
from test_manifest_asset_alignment import _OneSessionCtx
from test_p0_asset_cache import _CountingStubResolver
from test_provider_contract import _BUILDERS
from test_rss_subscription import FEED, MIXED_FEED
from test_rss_subscription import _provider as _rss_provider

from app.models.entities import (
    ArticleManifest,
    ContentAsset,
    Job,
    JobItem,
    KnowledgeDocument,
    Source,
    SourceSubscription,
)
from app.repositories.job import JobItemRepository
from app.repositories.space import SpaceRepository
from app.repositories.user import SqlAlchemyUserStore
from app.services.kb import KnowledgeBaseService
from app.services.manifest import ManifestSyncService
from app.services.subscription import SourceSubscriptionService

# 每渠道期望入库篇数：五家微信样本各 2 行；RSS 混合 feed 5 行里只有 2 条 mp.weixin 可入库。
_EXPECTED_ROWS = 2
_RSS_OFFSITE = 3


@dataclass(frozen=True)
class ChannelCase:
    """一条渠道用例的差异面：用什么 provider、拿什么标识去发现。"""

    channel: str
    identifier: str
    source_type: str
    offsite_filtered: int = 0

    @property
    def is_rss(self) -> bool:
        return self.source_type == "rss"


CHANNELS: tuple[ChannelCase, ...] = (
    ChannelCase("redfox", BIZ_A, "wechat_oa"),
    ChannelCase("dajiala", BIZ_A, "wechat_oa"),
    ChannelCase("justoneapi", BIZ_A, "wechat_oa"),
    ChannelCase("tikhub", BIZ_A, "wechat_oa"),
    ChannelCase("wellbyte", BIZ_A, "wechat_oa"),
    ChannelCase("rss", FEED, "rss", offsite_filtered=_RSS_OFFSITE),
)


def _make_provider(channel: str) -> Any:  # noqa: ANN401
    """按渠道造 provider：五家走真客户端类 + 样本 MockTransport，RSS 走 XML 桩。

    刻意**不**用 `providers/discovery/registry.py` 的 factory：注册表按 `implemented` 与
    配置筛选，`tikhub` 位当前是 `implemented=False`（STEP-08 的按源路由还没放开它），
    经 registry 拿不到 ⇒ 参数化会漏渠道或假绿。这里直接拿契约层同一批客户端类，
    六个渠道都是"真 provider 对象 + 假上游"。
    """
    if channel == "rss":
        return _rss_provider(MIXED_FEED)
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: _sample_response(channel)))
    return _BUILDERS[channel](http)


_SAMPLE_DIR = Path(__file__).parent / "fixtures" / "provider_payloads"


def _sample_response(channel: str) -> httpx.Response:
    """样本原样回吐（与 `test_provider_contract._client` 同法，只是按渠道取文件）。"""
    payload = json.loads((_SAMPLE_DIR / f"{channel}.json").read_text(encoding="utf-8"))
    return httpx.Response(200, json=payload)


async def _seed(db_session: AsyncSession, case: ChannelCase) -> tuple[str, str, str]:
    """一套 user + space + source + 订阅；返回 (user_id, space_id, source_id)。

    source 的 `external_id` 必须是**样本清单里的 biz**（微信渠道）或 feed 地址（RSS）：
    `_ensure_source` 按抓取结果的页面 biz 找源，只有对得上，资产才会落回清单同一个 source 行，
    Diff 的 ready 键减才不是空跑（见模块 docstring 非对称①）。
    """
    ns = uuid.uuid4().hex[:10]
    store = SqlAlchemyUserStore(db_session)
    user = await store.upsert_by_sub(f"sub-e2e-{ns}", f"e2e-{ns}@test.local", "E2E-06")
    space = await SpaceRepository(db_session).create(user_id=user.id, name=f"E2E采集{ns}")
    source = Source(
        type=case.source_type,
        external_id=case.identifier,
        name=f"E2E{case.channel}",
        url=case.identifier if case.is_rss else f"https://upstream.invalid/{case.channel}",
    )
    db_session.add(source)
    await db_session.flush()
    db_session.add(
        SourceSubscription(
            id=f"e2e-{ns}",
            user_id=user.id,
            source_id=source.id,
            space_id=space.id,
            sync_policy="auto",
            sync_interval_minutes=60,
            status="ACTIVE",
        )
    )
    await db_session.commit()
    return user.id, space.id, source.id


async def _manifests(db_session: AsyncSession, source_id: str) -> list[ArticleManifest]:
    return list(
        (
            await db_session.scalars(
                select(ArticleManifest).where(ArticleManifest.source_id == source_id).order_by(ArticleManifest.id)
            )
        ).all()
    )


async def _sub(db_session: AsyncSession, sub_id: str) -> SourceSubscription:
    """每次调用前重新取订阅行：`run_incremental_sync` 要读它的四个字段，
    而跨过一次 commit/savepoint 的旧对象已经过期（见 `_round_trip` 里 job_ids 那条注释）。
    """
    row = await db_session.get(SourceSubscription, sub_id)
    assert row is not None
    return row


async def _jobs(db_session: AsyncSession, sub_id: str) -> list[Job]:
    return list(
        (
            await db_session.scalars(
                select(Job).where(Job.idempotency_key.like(f"sync_account:{sub_id}%")).order_by(Job.created_at, Job.id)
            )
        ).all()
    )


async def _round_trip(db_session: AsyncSession, case: ChannelCase) -> dict[str, Any]:
    """跑完整链路并返回读数字典（六个渠道的判据与 3 次一致性比对共用这一份）。"""
    _user_id, space_id, source_id = await _seed(db_session, case)
    sub_id = (
        await db_session.scalars(select(SourceSubscription.id).where(SourceSubscription.source_id == source_id))
    ).one()

    # ① 发现 + ② 清单
    provider = _make_provider(case.channel)
    first_report = await ManifestSyncService(db_session, provider).sync_source(source_id, case.identifier)
    await db_session.commit()
    offsite = int(getattr(provider, "filtered_offsite", 0))
    await provider.aclose()

    rows = await _manifests(db_session, source_id)
    keys = [m.article_key for m in rows]
    assert len(rows) == first_report.discovered == _EXPECTED_ROWS, (first_report, len(rows))
    assert all(m.status == "DISCOVERED" and m.article_key for m in rows), [(m.status, m.article_key) for m in rows]
    assert len(set(keys)) == len(keys), f"清单键重复（同篇两行会绕过后面的入库去重）：{keys}"

    # ③ 入列：真 Diff → 恰一个 Job + 每篇一个 PENDING 条目
    enqueued = await SourceSubscriptionService(db_session).run_incremental_sync(await _sub(db_session, sub_id), "r1")
    await db_session.commit()
    jobs = await _jobs(db_session, sub_id)
    assert enqueued == _EXPECTED_ROWS and len(jobs) == 1, (enqueued, len(jobs))
    # 标量当场取走，不留 ORM 对象跨过 worker：下面那两次 `commit()` 会经 savepoint 回滚把
    # 早先加载的行整批过期，届时在同步上下文里读 `.id` 就是 MissingGreenlet（实测踩过一次）。
    job_ids = [j.id for j in jobs]
    items = list((await db_session.scalars(select(JobItem).where(JobItem.job_id == job_ids[0]))).all())
    item_view = [(i.status, i.manifest_id is not None) for i in items]
    assert len(item_view) == _EXPECTED_ROWS and all(s == "PENDING" and has_m for s, has_m in item_view), item_view

    # ④ 入库：真 worker + 真 KnowledgeBaseService（LangBot/抓取为桩）
    resolver = _CountingStubResolver()
    lb_client = _client()

    async def _ingest(session: AsyncSession, sid: str, url: str) -> dict[str, Any]:
        return await KnowledgeBaseService(lb_client, session, resolver).ingest_url(sid, url)

    worker = _worker(_OneSessionCtx(db_session), _ingest)
    assert await worker.run_once() is True
    assert await worker.run_once() is False, "worker 应当把队列清空"

    job_after = await db_session.get(Job, job_ids[0])
    assert job_after is not None and job_after.status == "SUCCEEDED", job_after.status
    counts = await JobItemRepository(db_session).counts(job_ids[0])
    rows_after = await _manifests(db_session, source_id)
    assets = list((await db_session.scalars(select(ContentAsset).where(ContentAsset.external_id.in_(keys)))).all())
    docs = list(
        (
            await db_session.scalars(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.space_id == space_id, KnowledgeDocument.asset_id.in_([a.id for a in assets])
                )
            )
        ).all()
    )
    assert counts == {"total": _EXPECTED_ROWS, "succeeded": _EXPECTED_ROWS, "failed": 0, "pending": 0}, counts
    assert all(m.status == "INGESTED" for m in rows_after), [m.status for m in rows_after]
    assert len(assets) == _EXPECTED_ROWS and all(a.status == "READY" for a in assets)
    assert len(docs) == _EXPECTED_ROWS and all(d.status == "INDEXED" for d in docs)
    assert resolver.fetch_count == _EXPECTED_ROWS, f"每篇应当恰好抓一次：{resolver.fetch_count}"
    # 非对称①的实测位置：资产落在哪一行 source 上。
    same_source_as_manifest = all(a.source_id == source_id for a in assets)

    # ⑤ 二轮：重新发现（全部命中既有行）+ 再 Diff ⇒ 0，Job 不增、资产不增
    provider2 = _make_provider(case.channel)
    try:
        second_report = await ManifestSyncService(db_session, provider2).sync_source(source_id, case.identifier)
    finally:
        await provider2.aclose()
    await db_session.commit()
    enqueued2 = await SourceSubscriptionService(db_session).run_incremental_sync(await _sub(db_session, sub_id), "r2")
    await db_session.commit()

    assets_round2 = int(
        await db_session.scalar(
            select(func.count()).select_from(ContentAsset).where(ContentAsset.external_id.in_(keys))
        )
        or 0
    )
    assert second_report.discovered == 0, second_report
    assert second_report.updated + second_report.unchanged == _EXPECTED_ROWS, second_report
    assert enqueued2 == 0, f"二轮 Diff 必须为 0，实得 {enqueued2}"
    assert len(await _jobs(db_session, sub_id)) == 1, "二轮不得再建 Job"
    assert assets_round2 == _EXPECTED_ROWS, "二轮不得新增资产"

    return {
        "channel": case.channel,
        "sub_id": sub_id,
        "source_id": source_id,
        "discovered": first_report.discovered,
        "calls": first_report.calls_made,
        "offsite_filtered": offsite,
        "enqueued": enqueued,
        "ingested": counts["succeeded"],
        "assets": len(assets),
        "docs": len(docs),
        "fetches": resolver.fetch_count,
        "round2_discovered": second_report.discovered,
        "round2_enqueued": enqueued2,
        "asset_source_is_manifest_source": same_source_as_manifest,
    }


@pytest.mark.parametrize("case", CHANNELS, ids=[c.channel for c in CHANNELS])
async def test_e2e_round_trip(db_session, case: ChannelCase) -> None:  # type: ignore[no-untyped-def]
    """S6.1.1 + S6.1.2：六渠道各自的完整往返读数。

    `_round_trip` 已经把五段链路的判据就地断言完（任一段断在第几段就在那里红）；本用例只补
    两条**渠道相关**的判据：
    - RSS 另带 D-V2-03 的要求：`filtered_offsite` 必须是一个**数**（3），不是"看起来少了两条"；
    - 非对称①：RSS 的资产与清单不同源（P-97 的实测锚），五个微信渠道必须同源。
    """
    readings = await _round_trip(db_session, case)

    assert readings["offsite_filtered"] == case.offsite_filtered, readings
    expected_same_source = not case.is_rss
    assert readings["asset_source_is_manifest_source"] is expected_same_source, readings


@pytest.mark.parametrize("case", CHANNELS, ids=[c.channel for c in CHANNELS])
async def test_reopened_manifest_does_not_reenqueue(db_session, case: ChannelCase) -> None:  # type: ignore[no-untyped-def]
    """S36.1（P-97 / D-V18-06 ①）：清单被合法回退成 DISCOVERED 后，重试轮不得重复入列已入库的篇。

    先红口径（STEP-06 变异的常驻化）：修前的 ready 键减按 `ContentAsset.source_id == 清单 source`
    过滤，而 RSS 的资产挂在页面 biz 的 wechat_oa 源上 ⇒ 减除对 RSS 恒不命中 ⇒ 重开行重新入列，
    状态门报 `30005 manifest 非法流转: INGESTED → ENQUEUED`；五个微信渠道靠同源命中挡住
    （P-97 登记的非对称）。修后：ready 减跨 source 按规范文章键减 ⇒ 六渠道 enqueued == 0。"""
    readings = await _round_trip(db_session, case)
    sub_id, source_id = readings["sub_id"], readings["source_id"]

    rows = await _manifests(db_session, source_id)
    assert all(m.status == "INGESTED" for m in rows), [m.status for m in rows]
    for m in rows:
        m.status = "DISCOVERED"  # `_reopen_manifests`/worker stale 回滚之后的合法回退态
    await db_session.commit()

    enqueued3 = await SourceSubscriptionService(db_session).run_incremental_sync(
        await _sub(db_session, sub_id), "r3"
    )
    await db_session.commit()
    assert enqueued3 == 0, f"已入库的篇在清单回退后不得重新入列：{enqueued3}"


async def test_e2e_discovery_is_deterministic_across_three_syncs(db_session) -> None:  # type: ignore[no-untyped-def]
    """S6.1.1.1（进程内那一半）：同一渠道连打三次上游，产物必须逐字相同。

    卡面的「连跑 3 次结果一致」有两半：本条锁**发现层到清单层**的确定性（键集合、条数、
    第二次起零新增），跨进程的读数字面一致性在 EVD 里用三次独立 pytest 调用证明——
    因为整链跑三遍需要一个干净的 source 行，而 `db_session` 只在用例结束时回滚，
    在同一事务里重跑第二遍会先撞 `uq_source_type_external`（这不是不稳定，是夹具边界）。
    """
    case = CHANNELS[0]
    _user_id, _space_id, source_id = await _seed(db_session, case)

    key_sets: list[list[str]] = []
    reports: list[tuple[int, int]] = []
    for _ in range(3):
        provider = _make_provider(case.channel)
        try:
            report = await ManifestSyncService(db_session, provider).sync_source(source_id, case.identifier)
        finally:
            await provider.aclose()
        await db_session.commit()
        rows = await _manifests(db_session, source_id)
        key_sets.append(sorted(str(m.article_key) for m in rows))
        reports.append((report.discovered, report.unchanged))

    assert key_sets[0] == key_sets[1] == key_sets[2], key_sets
    assert len(key_sets[0]) == _EXPECTED_ROWS
    assert reports[0] == (_EXPECTED_ROWS, 0), reports[0]
    assert reports[1] == reports[2] == (0, _EXPECTED_ROWS), reports
