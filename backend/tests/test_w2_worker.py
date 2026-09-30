"""W2 JobWorker 分发集成测试（验收 6）：hot_cluster Job 经 worker 消费执行落库。

真实 PG 真提交路径（与 test_job_worker 同法）：PG 不可达 → skip；用例前后清场
保证套件幂等。验收：trigger 入队的 hot_cluster Job 由 job_worker.run_once 消费 →
SUCCEEDED + HotTopic 落库。

前置：迁移 ab1004w2a 已应用（feed_items 唯一约束）。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.models.bothot_entities import HotTopic
from app.models.entities import ContentAsset, Source, User
from app.repositories.job import JobRepository
from app.services.job_worker import JobWorker
from app.services.jobs import JobService

PG_DSN = os.environ.get(
    "AIDEANBOT_TEST_PG_DSN", "postgresql+psycopg://bothot:bothot@localhost:5433/bothot"
)
_W2_KEY_PREFIX = "w2:"
_W2_SUB = "sub-w2-worker"


def _purge_w2() -> None:
    try:
        engine = create_engine(PG_DSN, connect_args={"connect_timeout": 3})
    except Exception:  # noqa: BLE001
        return
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM jobs WHERE idempotency_key LIKE :p"), {"p": f"{_W2_KEY_PREFIX}%"})
            conn.execute(text("DELETE FROM feed_items WHERE item_type='hot_topic'"))
            conn.execute(text("DELETE FROM hot_topic_articles"))
            conn.execute(text("DELETE FROM hot_topics"))
            conn.execute(text("DELETE FROM content_assets WHERE external_id LIKE 'w2:%'"))
            conn.execute(text("DELETE FROM sources WHERE external_id LIKE 'w2:%'"))
            conn.execute(text("DELETE FROM users WHERE sub = :s"), {"s": _W2_SUB})
    except Exception:  # noqa: BLE001
        return
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def _w2_guard() -> Iterator[None]:
    try:
        engine = create_engine(PG_DSN, connect_args={"connect_timeout": 3})
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PG 不可达（{type(exc).__name__}），Docker 引擎恢复后复跑本用例")
    _purge_w2()
    yield
    _purge_w2()


def _factory():  # noqa: ANN202
    engine = create_async_engine(PG_DSN, pool_pre_ping=True, connect_args={"connect_timeout": 3})
    return engine, async_sessionmaker(engine, expire_on_commit=False)


class _NoopIngest:
    """hot_cluster Job 不走 ingest；占位满足 JobWorker 构造签名。"""

    async def __call__(self, session, space_id: str, url: str) -> dict[str, object]:  # noqa: ANN001
        return {"status": "skipped"}


async def _seed(session_factory) -> str:  # noqa: ANN001
    """建 admin user + 2 source + 4 asset（2 簇）+ 返回 user_id；真提交。"""
    from datetime import datetime, timedelta

    async with session_factory() as session:
        user = User(sub=_W2_SUB, email="w2@bothot.local", nickname="w2", role="admin")
        session.add(user)
        s1 = Source(type="wechat_oa", external_id="w2:biz-a", name="来源A", url="", status="ACTIVE")
        s2 = Source(type="wechat_oa", external_id="w2:biz-b", name="来源B", url="", status="ACTIVE")
        session.add_all([s1, s2])
        await session.flush()
        now = datetime.now(UTC) - timedelta(hours=2)
        assets = [
            ContentAsset(source_id=s1.id, external_id="w2:a1", url="https://x/w2-a1", title="OpenAI发布GPT-5模型",
                         content_hash="w2-h1", content_markdown="OpenAI 发布了 GPT-5。",
                         quality_score=0.5, category="tech", published_at=now),
            ContentAsset(source_id=s2.id, external_id="w2:a2", url="https://x/w2-a2", title="OpenAI推出全新GPT-5大模型",
                         content_hash="w2-h2", content_markdown="OpenAI 推出全新 GPT-5。",
                         quality_score=0.8, category="tech", published_at=now),
            ContentAsset(source_id=s1.id, external_id="w2:b1", url="https://x/w2-b1", title="美联储宣布加息50个基点",
                         content_hash="w2-h3", content_markdown="美联储加息 50 基点。",
                         quality_score=0.6, category="finance", published_at=now),
            ContentAsset(source_id=s2.id, external_id="w2:b2", url="https://x/w2-b2", title="美联储加息50基点应对通胀",
                         content_hash="w2-h4", content_markdown="美联储加息应对通胀。",
                         quality_score=0.9, category="finance", published_at=now),
        ]
        session.add_all(assets)
        await session.commit()
        return user.id


@pytest.mark.asyncio
async def test_hot_cluster_job_consumed_by_worker() -> None:
    """验收 6：hot_cluster Job 经 job_worker.run_once 消费 → SUCCEEDED + 落库。"""
    engine, session_factory = _factory()
    try:
        user_id = await _seed(session_factory)

        # 入队 hot_cluster Job（与 trigger_cluster 端点同口径）
        async with session_factory() as session:
            svc = JobService(JobRepository(session), session)
            job, created = await svc.submit(
                job_type="hot_cluster",
                user_id=user_id,
                idempotency_key=f"{_W2_KEY_PREFIX}hot_cluster:1",
                payload_json='{"date":"2026-09-30","days":1}',
            )
            assert created
            job_id = job.id

        worker = JobWorker(
            session_factory,
            _NoopIngest(),
            settings=Settings(),
            item_interval_seconds=0.0,
            max_item_retries=1,
            stale_job_seconds=1,
            idle_sleep_seconds=0.0,
            heartbeat_enabled=False,
        )
        worked = await worker.run_once()
        assert worked is True

        async with session_factory() as session:
            job = await JobRepository(session).get_by_id(job_id)
            assert job is not None
            assert job.status == "SUCCEEDED", f"actual={job.status} err={job.error}"
            topics = (await session.execute(select(HotTopic))).scalars().all()
            assert len(topics) >= 2, f"expected >=2 topics, got {len(topics)}"
    finally:
        await engine.dispose()
