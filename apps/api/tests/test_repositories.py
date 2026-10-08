"""B-T4 验收测试：领域仓库落库（真实本地 PG:5433）。

覆盖（任务卡验收项）：
- CRUD 往返（user upsert / space / asset / job）；
- jobs.idempotency_key 重复插入 IntegrityError（唯一约束生效）+ create_or_get 幂等返回原 job；
- KnowledgeSpace(user_id, name) 唯一约束生效；
- 状态机非法流转被拒（QUEUED→SUCCEEDED 直跳 → 30005）。

隔离：conftest 外层事务回滚，零残留。PG 不可达时整组 skip（引擎恢复后 A 复跑）。
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.entities import ContentAsset, Source, User
from app.repositories.asset import AssetRepository, DocumentRepository
from app.repositories.job import JobRepository
from app.repositories.space import SpaceRepository
from app.repositories.user import SqlAlchemyUserStore
from app.services.jobs import JobService
from app.services.spaces import SpaceService, SpaceValidationError
from app.services.state_machine import can_transition, validate_transition


async def _make_user(session) -> User:
    """基础夹具用户（同事务内，随用例回滚）。"""
    user = User(sub="sub-bt4", email="bt4@test.local", nickname="B-T4")
    session.add(user)
    await session.flush()
    return user


async def _make_source(session) -> Source:
    source = Source(type="wechat_oa", external_id="bizBT4", name="测试公众号")
    session.add(source)
    await session.flush()
    return source


# ------------------------------------------------------------------ user


async def test_user_upsert_roundtrip(db_session) -> None:
    """SSO upsert：首登插入、二次登录更新不新建（sub 唯一锚点）。"""
    store = SqlAlchemyUserStore(db_session)
    first = await store.upsert_by_sub("sub-rt", "a@x.local", "旧昵称")
    second = await store.upsert_by_sub("sub-rt", "b@x.local", "新昵称")
    assert first.id == second.id  # 同一本地行
    assert second.email == "b@x.local" and second.nickname == "新昵称"
    got = await store.get_by_sub("sub-rt")
    assert got is not None and got.nickname == "新昵称"


# ------------------------------------------------------------------ space


async def test_space_crud_roundtrip(db_session) -> None:
    user = await _make_user(db_session)
    repo = SpaceRepository(db_session)
    space = await repo.create(user.id, "技术文章")
    assert space.id and space.status == "ACTIVE" and space.doc_count == 0
    fetched = await repo.get_by_name(user.id, "技术文章")
    assert fetched is not None and fetched.id == space.id
    assert [s.id for s in await repo.list_by_user(user.id)] == [space.id]

    # langbot_kb_uuid 回写（ADR-0001 1:1 映射）
    await repo.set_langbot_kb_uuid(space.id, "kb-uuid-123")
    refreshed = await repo.get_by_id(space.id)
    assert refreshed is not None and refreshed.langbot_kb_uuid == "kb-uuid-123"

    # doc_count 增减
    await repo.update_doc_count(space.id, 3)
    await repo.update_doc_count(space.id, -1)
    counted = await repo.get_by_id(space.id)
    assert counted is not None and counted.doc_count == 2


async def test_space_unique_constraint_user_name(db_session) -> None:
    """验收项：KnowledgeSpace(user_id,name) 唯一约束生效。"""
    user = await _make_user(db_session)
    repo = SpaceRepository(db_session)
    await repo.create(user.id, "唯一名")
    with pytest.raises(IntegrityError):
        await repo.create(user.id, "唯一名")


async def test_space_service_rejects_invalid_name(db_session) -> None:
    """Service 层入参校验：空名/控制字符拒绝（超长同理）。"""
    user = await _make_user(db_session)
    service = SpaceService(SpaceRepository(db_session))
    with pytest.raises(SpaceValidationError):
        await service.create_space(user.id, "   ")
    with pytest.raises(SpaceValidationError):
        await service.create_space(user.id, "坏名\x02字")


# ------------------------------------------------------------------ job


async def test_job_idempotency_key_unique_integrity_error(db_session) -> None:
    """验收项：idempotency_key 重复插入抛 IntegrityError（唯一约束生效）。"""
    user = await _make_user(db_session)
    repo = JobRepository(db_session)
    await repo.create(type="SINGLE_FETCH", user_id=user.id, idempotency_key="idem-1")
    with pytest.raises(IntegrityError):
        await repo.create(type="SINGLE_FETCH", user_id=user.id, idempotency_key="idem-1")


async def test_job_create_or_get_returns_original(db_session) -> None:
    """幂等提交：重复提交返回原 job（created=False），而非报错。"""
    user = await _make_user(db_session)
    repo = JobRepository(db_session)
    first, created1 = await repo.create_or_get(
        type="SINGLE_FETCH", user_id=user.id, idempotency_key="idem-2", payload='{"url":"u1"}'
    )
    second, created2 = await repo.create_or_get(
        type="SINGLE_FETCH", user_id=user.id, idempotency_key="idem-2", payload='{"url":"u1"}'
    )
    assert created1 is True and created2 is False
    assert first.id == second.id


async def test_job_state_machine_illegal_transition_rejected(db_session) -> None:
    """验收项：QUEUED→SUCCEEDED 直跳被拒（30005），合法链 QUEUED→RUNNING→终态放行。"""
    user = await _make_user(db_session)
    repo = JobRepository(db_session)
    job = await repo.create(type="SINGLE_FETCH", user_id=user.id, idempotency_key="idem-3")
    assert job.status == "QUEUED"

    service = JobService(repo)
    with pytest.raises(Exception) as exc_info:  # noqa: PT011 - 用码位断言精确定位
        await service.transition(job.id, "SUCCEEDED")
    assert getattr(exc_info.value, "code", None) == 30005
    # 直跳被拒后状态不变
    unchanged = await repo.get_by_id(job.id)
    assert unchanged is not None and unchanged.status == "QUEUED"

    # 合法链：QUEUED → RUNNING → SUCCEEDED，心跳随行
    await service.transition(job.id, "RUNNING")
    await service.heartbeat(job.id, progress=40)
    await service.transition(job.id, "SUCCEEDED")
    final = await repo.get_by_id(job.id)
    assert final is not None and final.status == "SUCCEEDED" and final.progress == 40


def test_state_machine_table_coverage() -> None:
    """流转表边界：未知域拒绝；RUNNING 不可回 QUEUED；FAILED 不可达 SUCCEEDED。"""
    with pytest.raises(Exception) as exc_info:  # noqa: PT011 - 用码位断言精确定位
        validate_transition("unknown_domain", "A", "B")
    assert getattr(exc_info.value, "code", None) == 30005
    assert not can_transition("job", "RUNNING", "QUEUED")
    assert not can_transition("job", "FAILED", "SUCCEEDED")
    assert can_transition("job", "RUNNING", "PARTIAL_SUCCESS")


# ------------------------------------------------------------------ asset / document


async def test_asset_upsert_hash_semantics(db_session) -> None:
    """资产幂等：hash 相同复用(False)；hash 变化 version+1(True)（作者改文）。"""
    source = await _make_source(db_session)
    repo = AssetRepository(db_session)

    asset, created = await repo.upsert_content(
        source_id=source.id,
        external_id="art-1",
        url="https://mp.weixin.qq.com/s/abc",
        title="第一版",
        content_hash="hash-v1",
        content_markdown="# v1",
        quality_score=0.75,
    )
    assert created and asset.version == 1

    same, created2 = await repo.upsert_content(
        source_id=source.id, external_id="art-1", content_hash="hash-v1", content_markdown="# v1"
    )
    assert created2 is False and same.id == asset.id and same.version == 1

    updated, created3 = await repo.upsert_content(
        source_id=source.id,
        external_id="art-1",
        title="第二版",
        content_hash="hash-v2",
        content_markdown="# v2",
        quality_score=0.8,
    )
    assert created3 and updated.version == 2 and updated.title == "第二版"
    fetched = await repo.get_by_source_external(source.id, "art-1")
    assert isinstance(fetched, ContentAsset) and fetched.content_markdown == "# v2"


async def test_document_state_machine_transition(db_session) -> None:
    """文档入库映射：FETCHED → INDEXED → READY 合法链；非法直跳拒绝。"""
    user = await _make_user(db_session)
    source = await _make_source(db_session)
    space = await SpaceRepository(db_session).create(user.id, "文档状态机空间")
    asset = await AssetRepository(db_session).create(
        source_id=source.id,
        external_id="art-doc",
        content_hash="h",
        content_markdown="# m",
    )
    repo = DocumentRepository(db_session)
    doc = await repo.create(asset_id=asset.id, space_id=space.id)
    assert doc.status == "FETCHED"

    with pytest.raises(Exception) as exc_info:  # noqa: PT011
        validate_transition("document", doc.status, "READY")  # FETCHED→READY 直跳
    assert getattr(exc_info.value, "code", None) == 30005

    await repo.set_status(doc.id, "INDEXED")
    await repo.set_langbot_file_id(doc.id, "lb-file-1")
    await repo.set_status(doc.id, "READY")
    final = await repo.get_by_id(doc.id)
    assert final is not None and final.status == "READY" and final.langbot_file_id == "lb-file-1"
