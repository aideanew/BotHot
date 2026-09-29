"""任务仓库（B-T4）：持久化状态机 + 幂等提交（idempotency_key 唯一）。

幂等语义：create_or_get 用 SAVEPOINT 包住插入，冲突时回滚 savepoint 并返回
已存在 job——重复提交返回原 job，而非报错（B-T8 编排层沿用）。

AB-P004 P2：JobItem 子任务仓储（Manifest Diff 逐篇子任务，支撑 PARTIAL_SUCCESS 与重试）。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Job, JobItem


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, **fields: object) -> Job:
        job = Job(**fields)  # type: ignore[arg-type]
        self._session.add(job)
        await self._session.flush()
        return job

    async def create_or_get(self, **fields: object) -> tuple[Job, bool]:
        """幂等提交：(job, created)。idempotency_key 冲突 → 返回原 job(created=False)。"""
        key = str(fields["idempotency_key"])
        try:
            async with self._session.begin_nested():  # SAVEPOINT
                job = await self.create(**fields)
            return job, True
        except IntegrityError:
            existing = await self.get_by_idempotency_key(key)
            if existing is None:
                raise
            return existing, False

    async def get_by_id(self, job_id: str) -> Job | None:
        return await self._session.get(Job, job_id)

    async def refresh(self, job_id: str) -> Job | None:
        """commit 后显式重取。

        commit 会过期已加载属性（生产默认 `expire_on_commit=True`；savepoint 测试夹具同理），
        此时直接读属性会触发**同步惰性加载** → `MissingGreenlet`。写路径的调用方（取消回执）
        须走本方法取回后再组装视图。
        """
        job = await self._session.get(Job, job_id)
        if job is None:
            return None
        await self._session.refresh(job)
        return job

    async def get_by_idempotency_key(self, key: str) -> Job | None:
        return await self._session.scalar(select(Job).where(Job.idempotency_key == key))

    async def list_by_user(
        self,
        user_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        *,
        job_type: str | None = None,
        offset: int = 0,
    ) -> list[Job]:
        """清单分页（R0.4.1）。总数由 count_by_user 另取，二者共用 _job_stmt。

        排序稳定性：`created_at` 为 `server_default=now()`，PostgreSQL 的 `now()` 返回
        **事务开始时刻**——同一事务内批量建的 Job 时间戳完全相同，仅凭 `created_at`
        排序属未定序，offset 分页会出现重复页/漏行。故追加 `id` 作确定性兜底。
        """
        stmt = self._job_stmt(user_id, status, job_type).order_by(
            Job.created_at.desc(), Job.id.desc()
        )
        stmt = stmt.limit(limit)
        if offset:
            stmt = stmt.offset(offset)
        result = await self._session.scalars(stmt)
        return list(result)

    async def count_by_user(
        self,
        user_id: str | None = None,
        status: str | None = None,
        *,
        job_type: str | None = None,
    ) -> int:
        """R0.4.1：与 list_by_user 同谓词求总数，避免「过滤后的列表配未过滤的 total」。"""
        # with_only_columns(func.count()) 把 SELECT 列换成标量函数后，SQLAlchemy 会剪掉
        # 它不引用的 FROM——零条件时语句退化成 `SELECT count(*)`（无表），恒返 1。
        # 显式补 select_from 保住 jobs 表；条件谓词仍全部来自 _job_stmt，不另写一份。
        stmt = self._job_stmt(user_id, status, job_type).with_only_columns(
            func.count()
        ).select_from(Job)
        return int((await self._session.scalar(stmt)) or 0)

    def _job_stmt(
        self, user_id: str | None = None, status: str | None = None, job_type: str | None = None
    ) -> Select:
        """Job 清单查询基座（归属 + 状态 + 类型过滤），list/count 共用。

        user_id=None 表示无归属约束（/admin 跨用户清单）：省略该列谓词而非传入 None，
        否则 SQLAlchemy 会生成 `user_id IS NULL`——语义从「不过滤」静默变成「只取无主行」。

        刻意不含 order_by/limit：排序与分页由 list_by_user 追加，count_by_user 才能对
        未被 LIMIT 截断的语句求值（与 repositories/space.py 的 _docs_stmt 同分工）。
        """
        stmt = select(Job)
        if user_id is not None:
            stmt = stmt.where(Job.user_id == user_id)
        if status:
            stmt = stmt.where(Job.status == status)
        if job_type:
            stmt = stmt.where(Job.type == job_type)
        return stmt

    async def claim_next_queued(self) -> Job | None:
        """T2.3 原子取件：QUEUED → RUNNING（`FOR UPDATE SKIP LOCKED` 防双 worker 同抢）。

        并发安全要点：候选行在**本事务内**被锁并置 RUNNING 后立即提交——并行的第二个
        worker 在同一语句上因 `SKIP LOCKED` 跳过该行，转而取下一件；若无可取行则返回
        None（返回前回滚，释放可能已开的空事务）。
        注：QUEUED→RUNNING 是状态机唯一出边（state_machine.py:15），本就合法，故此处
        直写状态而不经 validate_transition，避免取件路径额外往返。
        """
        result = await self._session.execute(
            select(Job)
            .where(Job.status == "QUEUED")
            .order_by(Job.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = result.scalars().first()
        if job is None:
            await self._session.rollback()
            return None
        job.status = "RUNNING"
        job.worker_heartbeat_at = datetime.now(UTC)
        await self._session.commit()
        return job

    async def requeue_stale_running(self, stale_seconds: int) -> list[str]:
        """T2.3 崩溃自愈：RUNNING 且心跳超时的 job → QUEUED（worker 宕机后的可重入）。

        返回被回退的 job id 列表（调用方据此一并复位其 RUNNING item，并供测试断言）。
        """
        cutoff = datetime.now(UTC).timestamp() - stale_seconds
        rows = (
            await self._session.scalars(
                select(Job).where(
                    Job.status == "RUNNING",
                    Job.worker_heartbeat_at.is_not(None),
                )
            )
        ).all()
        stale = [j for j in rows if j.worker_heartbeat_at and j.worker_heartbeat_at.timestamp() < cutoff]
        for j in stale:
            j.status = "QUEUED"
            j.error = "worker_stale: 心跳超时，已回退 QUEUED 待重入"
        if stale:
            await self._session.commit()
        return [j.id for j in stale]

    async def set_status(self, job_id: str, status: str, error: str = "") -> None:
        job = await self.get_by_id(job_id)
        if job is None:
            return
        job.status = status
        if error:
            job.error = error
        await self._session.flush()

    async def heartbeat(self, job_id: str, progress: int | None = None) -> None:
        """worker 心跳：刷新 worker_heartbeat_at（可观测 STALL 判定的依据）。"""
        job = await self.get_by_id(job_id)
        if job is None:
            return
        job.worker_heartbeat_at = datetime.now(UTC)
        if progress is not None:
            job.progress = max(job.progress, progress)
        await self._session.flush()

    async def save_result(self, job_id: str, result_json: str) -> None:
        job = await self.get_by_id(job_id)
        if job is None:
            return
        job.result = result_json
        await self._session.flush()


class JobItemRepository:
    """AB-P004 P2：JobItem 子任务仓储（Manifest Diff 逐篇，PARTIAL_SUCCESS 重试基础）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, job_id: str, external_id: str = "", url: str = "") -> JobItem:
        item = JobItem(job_id=job_id, external_id=external_id, url=url)
        self._session.add(item)
        await self._session.flush()
        return item

    async def list_by_job(self, job_id: str) -> list[JobItem]:
        rows = await self._session.scalars(
            select(JobItem).where(JobItem.job_id == job_id).order_by(JobItem.created_at)
        )
        return list(rows)

    async def list_failed(self, job_id: str) -> list[JobItem]:
        rows = await self._session.scalars(
            select(JobItem).where(JobItem.job_id == job_id, JobItem.status == "FAILED")
        )
        return list(rows)

    async def claim_next_pending(self, job_id: str) -> JobItem | None:
        """T2.3 原子取件：该 job 下 PENDING → RUNNING（`FOR UPDATE SKIP LOCKED`）。

        与 `JobRepository.claim_next_queued` 同口径：锁定+置位+提交一步完成，并行 worker
        取不到同一 item。无可取行 → 回滚并返回 None（终态判定由调用方按 counts 收敛）。
        """
        result = await self._session.execute(
            select(JobItem)
            .where(JobItem.job_id == job_id, JobItem.status == "PENDING")
            .order_by(JobItem.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        item = result.scalars().first()
        if item is None:
            await self._session.rollback()
            return None
        item.status = "RUNNING"
        item.completed = False
        await self._session.commit()
        return item

    async def requeue_running(self, job_id: str) -> int:
        """崩溃自愈：该 job 下遗留 RUNNING 的 item → PENDING（worker 宕机后可重入）。"""
        rows = (
            await self._session.scalars(
                select(JobItem).where(JobItem.job_id == job_id, JobItem.status == "RUNNING")
            )
        ).all()
        for it in rows:
            it.status = "PENDING"
            it.completed = False
        if rows:
            await self._session.commit()
        return len(rows)

    async def set_status(self, item_id: str, status: str, error: str = "") -> None:
        item = await self._session.get(JobItem, item_id)
        if item is None:
            return
        item.status = status
        if error:
            item.error = error
        item.completed = status in ("SUCCEEDED", "FAILED")
        await self._session.flush()

    async def bump_retry(self, item_id: str) -> None:
        item = await self._session.get(JobItem, item_id)
        if item is None:
            return
        item.retry_count += 1
        item.completed = False
        await self._session.flush()

    async def counts(self, job_id: str) -> dict[str, int]:
        items = await self.list_by_job(job_id)
        c = {"total": len(items), "succeeded": 0, "failed": 0, "pending": 0}
        for it in items:
            if it.status == "SUCCEEDED":
                c["succeeded"] += 1
            elif it.status == "FAILED":
                c["failed"] += 1
            else:
                c["pending"] += 1
        return c
