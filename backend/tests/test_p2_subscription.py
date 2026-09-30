"""AB-P004 P2 整号订阅验收测试：sources/subscriptions/jobs 幂等与 PARTIAL_SUCCESS 重试（连库夹具，PG 不可达自动 skip）。

机器门口径（T-018）：
- ① POST /sources biz 幂等（同 biz 二次注册返回同一 sourceId，不报错）；
- ② POST /subscriptions 幂等（同 用户+源+空间 二次订阅 created=False 不建双 Job）；
- ③ GET /jobs/{id} 进度含 counts{total,succeeded,failed,pending}；
- ④ POST /jobs/{id}/retry 对 FAILED JobItem 单篇重试（retried>0 时 Job 回 QUEUED）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from test_repositories import _make_user  # noqa: F401  (复用用户锚夹具)

from app.core.errors import RequestInvalidError
from app.models.entities import ArticleManifest, Job, JobItem, Source, SourceSubscription
from app.repositories.space import SpaceRepository
from app.services.subscription import SourceSubscriptionService

# 通过 register_source 的形态校验（R8 L1-3：须 M 前缀 Base64 __biz），值本身仍是测试专用
BIZ_TEST = "MUDAwNC1URVNULUJJWi0yMDI2"
BIZ_FRESH = "MUFQRUVOVFJTREZSRVNUMjA="

# 固定时点锚的时区口径（须与 app.core.config::scheduler_timezone 一致）
SZ = ZoneInfo("Asia/Shanghai")


async def _seed(db_session):
    """用户+空间+源三件套。"""
    from app.repositories.user import SqlAlchemyUserStore

    user = await SqlAlchemyUserStore(db_session).upsert_by_sub(
        "sub-p2-ab004", "p2ab004@test.local", "P2-AB004"
    )
    space = await SpaceRepository(db_session).create(user_id=user.id, name="P2订阅空间")
    svc = SourceSubscriptionService(db_session)
    src = await svc.register_source(user.id, biz=BIZ_TEST)
    await db_session.commit()
    return user, space, src


async def _seed_manifests(db_session, source_id: str, count: int) -> None:
    """Manifest 前置：count 篇 DISCOVERED 清单行（= 1.2.1 _sync_manifests 的合法 PG 产物）。

    不是伪造 RedFox 响应或假成功——仅铺 PG 状态以驱动 subscribe → JobItem 装配链；
    幂等键 (source_id, external_id) 与真实清单写入同构，RedFox 客户端接入后由真实写入方落盘。
    """
    for i in range(count):
        db_session.add(
            ArticleManifest(
                source_id=source_id,
                external_id=f"{BIZ_TEST}-work-{i}",
                url=f"https://mp.weixin.qq.com/s/{BIZ_TEST}-{i}",
                title=f"清单文章{i}",
                content_hash=f"hash-{BIZ_TEST}-{i}",
                status="DISCOVERED",
            )
        )
    await db_session.flush()


async def test_p2_register_source_idempotent(db_session) -> None:  # type: ignore[no-untyped-def]
    """机器门①：同 biz 二次注册 → 同一 sourceId（uq_source_type_external 幂等，不 409）。"""
    user, space, src1 = await _seed(db_session)
    svc = SourceSubscriptionService(db_session)
    src2 = await svc.register_source(user.id, biz=BIZ_TEST)
    assert src2["sourceId"] == src1["sourceId"]
    rows = (
        await db_session.execute(
            select(Source).where(Source.type == "wechat_oa", Source.external_id == BIZ_TEST)
        )
    ).all()
    assert len(rows) == 1, "同 biz 应只有一条 source 行"
    await db_session.commit()


# ---------------------------------------------------------------- 入口健壮性（R8 L1-3）


async def test_p2_register_source_accepts_mp_query_biz(db_session) -> None:  # type: ignore[no-untyped-def]
    """profile_url 取 `?__biz=` / `?biz=` 参数：公众号文章链接可注册成正确锚点。"""
    user, space, src = await _seed(db_session)
    svc = SourceSubscriptionService(db_session)
    result = await svc.register_source(
        user.id, profile_url=f"https://mp.weixin.qq.com/s?__biz={BIZ_TEST}&mid=1"
    )
    assert result["biz"] == BIZ_TEST
    assert result["sourceId"] == src["sourceId"]


async def test_p2_register_source_rejects_redfox_docs_link(db_session) -> None:  # type: ignore[no-untyped-def]
    """拒绝红狐文档深链：`/apis/gongzhonghao/{interfaceNo}` 的 interfaceNo 不是账号标识。

    此前取路径末段会把 `5Y84NI1D` 落库成 biz，之后整号采集 100% 静默失败且 UI 无异常。
    """
    user, space, _src = await _seed(db_session)
    svc = SourceSubscriptionService(db_session)
    with pytest.raises(RequestInvalidError, match="至少提供"):
        await svc.register_source(user.id, profile_url="https://redfox.hk/apis/gongzhonghao/5Y84NI1D")


async def test_p2_register_source_rejects_bad_biz_shape(db_session) -> None:  # type: ignore[no-untyped-def]
    """拒绝形态非法的 biz：__biz 必须是 M 前缀 Base64，否则必然调不通上游。"""
    user, space, _src = await _seed(db_session)
    svc = SourceSubscriptionService(db_session)
    with pytest.raises(RequestInvalidError, match="形态非法"):
        await svc.register_source(user.id, biz="biz-r48")


async def test_p2_register_source_rejects_mp_short_link(db_session) -> None:  # type: ignore[no-untyped-def]
    """拒绝文章短链：`/s/{随机串}` 的 URL 本身不含 biz，解析不了就明确报错。"""
    user, space, _src = await _seed(db_session)
    svc = SourceSubscriptionService(db_session)
    with pytest.raises(RequestInvalidError, match="至少提供"):
        await svc.register_source(user.id, profile_url="https://mp.weixin.qq.com/s/AbCdEf")


async def test_p2_register_source_no_fake_default_url(db_session) -> None:  # type: ignore[no-untyped-def]
    """无 profile_url 时 url 留空，不再拼 `redfox.hk/apis/gongzhonghao/{biz}` 假地址。

    该路径只接受文档 interfaceNo，填进去是个永不生效的链接，比留空更具误导性。
    """
    user, space, _src = await _seed(db_session)
    svc = SourceSubscriptionService(db_session)
    result = await svc.register_source(user.id, biz=BIZ_FRESH)
    assert result["url"] == ""
    assert result["biz"] == BIZ_FRESH


async def test_p2_subscribe_idempotent_no_double_job(db_session) -> None:  # type: ignore[no-untyped-def]
    """机器门②：同 (用户,源,空间) 二次订阅 → created=False 且不建双 Job。"""
    user, space, src = await _seed(db_session)
    svc = SourceSubscriptionService(db_session)
    r1 = await svc.subscribe(user.id, space.id, src["sourceId"])
    assert r1["created"] is True and len(r1["jobIds"]) == 1
    r2 = await svc.subscribe(user.id, space.id, src["sourceId"])
    assert r2["created"] is False and r2["jobIds"] == []
    subs = (
        await db_session.execute(
            select(SourceSubscription).where(
                SourceSubscription.user_id == user.id,
                SourceSubscription.source_id == src["sourceId"],
                SourceSubscription.space_id == space.id,
            )
        )
    ).all()
    assert len(subs) == 1
    jobs = (
        await db_session.execute(
            select(Job).where(Job.type == "sync_account", Job.user_id == user.id)
        )
    ).all()
    assert len(jobs) == 1, "幂等订阅不得建双 Job"
    await db_session.commit()


async def test_p2_subscribe_with_anchor_lands_on_daily_hour(db_session) -> None:  # type: ignore[no-untyped-def]
    """固定时点锚（建订阅即给）→ 锚值落库，首个 next_run_at 对准调度器时区「下一次整点」。"""
    user, space, src = await _seed(db_session)
    svc = SourceSubscriptionService(db_session)
    r = await svc.subscribe(user.id, space.id, src["sourceId"], sync_anchor_hour=10)
    assert r["created"] is True and len(r["jobIds"]) == 1

    sub = (
        await db_session.execute(select(SourceSubscription).where(SourceSubscription.id == r["subscriptionId"]))
    ).scalar_one()
    assert sub.sync_anchor_hour == 10, "锚值必须落库"

    now_local = datetime.now(UTC).astimezone(SZ)
    due = sub.next_run_at.astimezone(SZ)
    assert (due.hour, due.minute, due.second) == (10, 0, 0), f"锚点须落在整点，实际 {due.isoformat()}"
    assert timedelta(0) < (due - now_local) <= timedelta(days=1), "应是**最近**的一次整点"
    await db_session.commit()


async def test_p2_subscribe_without_anchor_applies_configured_default(db_session) -> None:  # type: ignore[no-untyped-def]
    """未显式传锚 → 套用 `default_sync_anchor_hour`（默认 12），落库且首个触发点对准该整点。

    「每天固定时点采集」需求的关键一环：不套默认则 `sync_anchor_hour=None` = 每 360 分钟
    滑动窗口（一天 4 次），RedFox 清单调用量是每日一次的 3.2 倍。
    """
    user, space, src = await _seed(db_session)
    r = await SourceSubscriptionService(db_session).subscribe(user.id, space.id, src["sourceId"])
    assert r["created"] is True

    sub = await db_session.get(SourceSubscription, r["subscriptionId"])
    assert sub is not None
    assert sub.sync_anchor_hour == 12, f"应套用默认锚 12，实际 {sub.sync_anchor_hour}"

    now_local = datetime.now(UTC).astimezone(SZ)
    due = sub.next_run_at.astimezone(SZ)
    assert (due.hour, due.minute) == (12, 0), f"默认锚须落在 12:00 整点，实际 {due.isoformat()}"
    assert timedelta(0) < (due - now_local) <= timedelta(days=1), "应是最近一次 12:00"
    await db_session.commit()


@pytest.mark.parametrize("configured", [None, -1, 24, 99])
async def test_p2_subscribe_default_disabled_or_invalid_keeps_sliding(  # type: ignore[no-untyped-def]
    db_session, monkeypatch, configured: int | None
) -> None:
    """`default_sync_anchor_hour` 为 None（显式关闭）或越界（env 是外部输入）→ 回落滑动口径。

    越界值不得让建订阅抛错：`replace(hour=99)` 会把整条 POST 打成 500，为一个错误配置值
    牺牲主流程不值得。None 与越界在此表现一致（均为「不锚定」），故合并为参数化一例。
    """
    from types import SimpleNamespace

    from app.services import subscription as sub_mod

    monkeypatch.setattr(sub_mod, "get_settings", lambda: SimpleNamespace(default_sync_anchor_hour=configured))
    user, space, src = await _seed(db_session)
    r = await SourceSubscriptionService(db_session).subscribe(user.id, space.id, src["sourceId"])

    sub = await db_session.get(SourceSubscription, r["subscriptionId"])
    assert sub is not None and sub.sync_anchor_hour is None, f"configured={configured} 应不锚定"
    # next_run_at 在 subscribe 内取 now，本采样点必然略晚于它，故用绝对值容差判定
    assert abs(sub.next_run_at - datetime.now(UTC)) <= timedelta(minutes=5), sub.next_run_at
    await db_session.commit()


async def test_p2_subscribe_idempotent_ignores_new_anchor(db_session) -> None:  # type: ignore[no-untyped-def]
    """幂等再订阅**不改**既有订阅的锚值——POST 是建单，改设置走 PATCH（否则静默忽略会让用户误以为已生效）。"""
    user, space, src = await _seed(db_session)
    svc = SourceSubscriptionService(db_session)
    first = await svc.subscribe(user.id, space.id, src["sourceId"], sync_anchor_hour=8)
    again = await svc.subscribe(user.id, space.id, src["sourceId"], sync_anchor_hour=22)
    assert again["created"] is False and again["subscriptionId"] == first["subscriptionId"]

    sub = await db_session.get(SourceSubscription, first["subscriptionId"])
    assert sub is not None and sub.sync_anchor_hour == 8, "既有订阅的锚值不得被再订阅覆盖"
    await db_session.commit()


@pytest.mark.parametrize("hour", [-1, 24])
async def test_p2_subscribe_anchor_out_of_range_rejected(db_session, hour: int) -> None:  # type: ignore[no-untyped-def]
    """建订阅锚值越界（0..23 之外）→ 10005，且不落订阅/Job 行。"""
    user, space, src = await _seed(db_session)
    svc = SourceSubscriptionService(db_session)
    with pytest.raises(RequestInvalidError):
        await svc.subscribe(user.id, space.id, src["sourceId"], sync_anchor_hour=hour)
    await db_session.rollback()

    rows = (
        await db_session.execute(select(SourceSubscription).where(SourceSubscription.user_id == user.id))
    ).all()
    jobs = (await db_session.execute(select(Job).where(Job.user_id == user.id))).all()
    assert rows == [] and jobs == [], f"校验失败不得落库（hour={hour}）"


async def test_p2_job_progress_counts(db_session) -> None:  # type: ignore[no-untyped-def]
    """机器门③：GET job 进度含 counts（total/succeeded/failed/pending）。"""
    user, space, src = await _seed(db_session)
    svc = SourceSubscriptionService(db_session)
    await _seed_manifests(db_session, src["sourceId"], 3)
    r = await svc.subscribe(user.id, space.id, src["sourceId"])
    job_id = r["jobIds"][0]
    view = await svc.get_job_view(user.id, job_id)
    assert view["status"] in ("QUEUED", "RUNNING")
    assert "counts" in view and "total" in view["counts"]
    # 3 篇 DISCOVERED Manifest（_sync_manifests 合法产物）→ subscribe 装配 3 条 PENDING JobItem
    assert view["counts"]["total"] == 3
    assert view["counts"]["pending"] == 3
    await db_session.commit()


async def test_p2_retry_failed_items(db_session) -> None:  # type: ignore[no-untyped-def]
    """机器门④：POST retry 对 FAILED JobItem 单篇重试（Job 回 QUEUED，retry_count+1）。"""
    user, space, src = await _seed(db_session)
    svc = SourceSubscriptionService(db_session)
    await _seed_manifests(db_session, src["sourceId"], 3)
    r = await svc.subscribe(user.id, space.id, src["sourceId"])
    job_id = r["jobIds"][0]
    item_repo = svc._item_repo
    items = await item_repo.list_by_job(job_id)
    assert len(items) == 3, "3 篇 DISCOVERED Manifest 应装配 3 条 JobItem"
    # 构造 1 篇 FAILED（模拟 20003 低质拦截场景）
    await item_repo.set_status(items[0].id, "FAILED", "20003 EXTRACT_QUALITY_LOW")
    await svc._job_repo.set_status(job_id, "PARTIAL_SUCCESS", "1 failed of 3")
    await db_session.commit()

    result = await svc.retry_job(user.id, job_id)
    assert result["retried"] == 1
    # 重试 = 重新入队：worker 的 claim_next_queued 只认领 QUEUED，置 RUNNING 会让 Job
    # 对 worker 隐形直到 stale 自愈（默认 300s）。故断言落库状态亦为 QUEUED。
    assert result["status"] == "QUEUED"
    assert (await db_session.get(Job, job_id)).status == "QUEUED"
    retried_item = await db_session.get(JobItem, items[0].id)
    assert retried_item.status == "PENDING" and retried_item.retry_count == 1
    await db_session.commit()


async def test_p2_r632_failed_first_sync_requeues(db_session) -> None:  # type: ignore[no-untyped-def]
    """R6.3.2：首同步 Job 失败后，同订阅再次触发 sync 时应复位为 QUEUED（而非永久卡死）。

    旧缺陷：`_create_sync_job` 的 `if not created: return job` 不看 Job 状态，
    导致首次 Job 失败/取消后，同订阅永远无法再自动同步。
    修复：终态 Job（FAILED/CANCELLED）→ 重新 set_status(QUEUED) + 重新填充 JobItem。
    """
    user, space, src = await _seed(db_session)
    svc = SourceSubscriptionService(db_session)
    await _seed_manifests(db_session, src["sourceId"], 2)
    r = await svc.subscribe(user.id, space.id, src["sourceId"])
    assert r["created"] is True
    job_id = r["jobIds"][0]

    # 模拟首次 Job 失败
    await svc._job_repo.set_status(job_id, "FAILED", "test: simulated first-sync failure")
    await db_session.commit()

    # 再次触发同步（模拟 create_subscription 幂等返回后走 _create_sync_job）
    job2 = await svc._create_sync_job(
        user.id, space.id, src["sourceId"], r["subscriptionId"]
    )
    assert job2.id == job_id, "应复用同一 Job 行（幂等键不变）"
    assert job2.status == "QUEUED", "终态 Job 应被复位为 QUEUED"
    # JobItem 应被重新填充
    items = await svc._item_repo.list_by_job(job_id)
    assert len(items) > 0, "终态 Job 复位后应重新填充 JobItem"
    await db_session.commit()


async def test_p2_r632_succeeded_first_sync_no_requeue(db_session) -> None:  # type: ignore[no-untyped-def]
    """R6.3.2 补充：首同步 Job 成功后，同订阅再次触发应直接返回（不复位、不重新填充）。"""
    user, space, src = await _seed(db_session)
    svc = SourceSubscriptionService(db_session)
    await _seed_manifests(db_session, src["sourceId"], 2)
    r = await svc.subscribe(user.id, space.id, src["sourceId"])
    job_id = r["jobIds"][0]

    # 模拟首次 Job 成功
    await svc._job_repo.set_status(job_id, "SUCCEEDED")
    await db_session.commit()

    job2 = await svc._create_sync_job(
        user.id, space.id, src["sourceId"], r["subscriptionId"]
    )
    assert job2.id == job_id
    assert job2.status == "SUCCEEDED", "成功的 Job 不应被复位"
    await db_session.commit()


async def test_p2_subscription_visibility_fields(db_session) -> None:  # type: ignore[no-untyped-def]
    """T1.4.3/T1.4.4（N11）：订阅响应透出 discoveredCount/lastSuccessAt/consecutiveEmptySyncs。

    - discoveredCount = 该源 DISCOVERED 清单计数（U6"预计篇数"权威口径）；
    - lastSuccessAt=""、consecutiveEmptySyncs=0：worker/调度器（大纲 T2.3/T2.4）未建成前
      的诚实缺口呈现，不造假数据。
    """
    user, space, src = await _seed(db_session)
    svc = SourceSubscriptionService(db_session)
    await _seed_manifests(db_session, src["sourceId"], 3)
    await svc.subscribe(user.id, space.id, src["sourceId"])
    subs, subs_total = await svc.list_subscriptions(user.id, space.id)
    assert subs_total == 1
    assert len(subs) == 1
    s = subs[0]
    assert s["discoveredCount"] == 3
    assert s["nextRunAt"] != "", "subscribe 已置 next_run_at，须透出"
    assert s["lastSuccessAt"] == ""
    assert s["consecutiveEmptySyncs"] == 0
    await db_session.commit()
