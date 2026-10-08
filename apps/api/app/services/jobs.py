"""任务服务（B-T4 骨架）：幂等提交 + 状态机流转 + 心跳。

Celery 接线（worker/beat）在 B-T8；本卡保证任务状态机落库正确与幂等语义，
编排层（B-T10）复用 submit/transition，不重复实现。
"""

from __future__ import annotations

from typing import Any

from app.core.errors import JobStateInvalidError, ResourceNotFoundError
from app.models.entities import Job
from app.repositories.job import JobRepository
from app.services.state_machine import validate_transition

JOB_DOMAIN = "job"


class JobService:
    def __init__(self, repo: JobRepository, session: Any | None = None) -> None:
        # session：生产装配传入（commit 边界在 Service，B-T8R）；内存桩测试传 None
        self._repo = repo
        self._session = session

    async def _commit(self) -> None:
        if self._session is not None:
            await self._session.commit()

    async def submit(
        self,
        *,
        job_type: str,
        user_id: str,
        idempotency_key: str,
        payload_json: str = "{}",
    ) -> tuple[Job, bool]:
        """幂等提交：(job, created)。同 idempotency_key 重复提交返回原 job。"""
        job, created = await self._repo.create_or_get(
            type=job_type,
            user_id=user_id,
            idempotency_key=idempotency_key,
            payload=payload_json,
        )
        if created:
            await self._commit()  # B-T8R：写路径终点持久化
        return job, created

    async def transition(self, job_id: str, new_status: str, error: str = "") -> Job:
        """受控流转：非法流转 → 30005（QUEUED→SUCCEEDED 直跳等）。"""
        job = await self._require(job_id)
        validate_transition(JOB_DOMAIN, job.status, new_status)  # 先校验后写库
        await self._repo.set_status(job_id, new_status, error)
        await self._commit()  # B-T8R：状态机写路径终点持久化
        return await self._require(job_id)

    async def heartbeat(self, job_id: str, progress: int | None = None) -> None:
        """RUNNING 心跳：本卡不强制 RUNNING 才可心跳（worker 重试场景需宽容），
        STALL 判定归可观测层（M3）。"""
        await self._repo.heartbeat(job_id, progress)
        await self._commit()

    async def get_job(self, user_id: str, job_id: str) -> Job | None:
        job = await self._repo.get_by_id(job_id)
        if job is None or job.user_id != user_id:
            return None
        return job

    async def list_jobs(
        self,
        user_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        *,
        job_type: str | None = None,
        offset: int = 0,
    ) -> tuple[list[Job], int]:
        """清单分页（R0.4.1）：返回 (jobs, total)，total 与 jobs 同谓词。

        user_id=None → 无归属约束（/admin 跨用户清单）。授权在路由层，本方法不做角色校验。
        """
        jobs = await self._repo.list_by_user(user_id, status=status, limit=limit, job_type=job_type, offset=offset)
        total = await self._repo.count_by_user(user_id, status=status, job_type=job_type)
        return jobs, total

    async def list_job_views(
        self,
        user_id: str | None = None,
        *,
        status: str | None = None,
        job_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """GET /jobs 列表视图（R0.4.1）。

        列表不聚合 JobItem counts——那要按 Job 逐条查（N+1），单篇钻取走 GET /jobs/{id}。
        带 workerHeartbeatAt / updatedAt：STALL 判定的两个输入（R0.4 可观测性目标）。
        user_id=None → 跨用户（/admin/jobs）。
        """
        jobs, total = await self.list_jobs(user_id, status=status, limit=limit, job_type=job_type, offset=offset)
        return {
            "items": [self._view(job) for job in jobs],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def list_job_views_any(
        self,
        *,
        status: str | None = None,
        job_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """R4.8（A-2 叠加）：admin 跨用户 Job 清单——不做归属校验。

        与 list_job_views 的差异仅在归属谓词；查询、分页、排序、视图组装共用单一实现，
        故 total 与过滤谓词天然一致。角色校验留在路由层（deps.require_roles）。
        """
        return await self.list_job_views(None, status=status, job_type=job_type, limit=limit, offset=offset)

    @staticmethod
    def _view(job: Job) -> dict[str, Any]:
        """Job 视图字典（列表条目与取消回执共用）。"""
        return {
            "jobId": job.id,
            "ownerId": job.user_id,
            "type": job.type,
            "status": job.status,
            "progress": job.progress,
            "error": job.error,
            "workerHeartbeatAt": (job.worker_heartbeat_at.isoformat() if job.worker_heartbeat_at else ""),
            "createdAt": job.created_at.isoformat() if job.created_at else "",
            "updatedAt": job.updated_at.isoformat() if job.updated_at else "",
        }

    async def cancel_job(self, user_id: str, job_id: str) -> dict[str, Any]:
        """POST /jobs/{id}/cancel（R0.4.2）：仅 QUEUED 可取消 → CANCELLED。

        RUNNING 一律拒绝并回当前 progress——已投入执行的作业不半途作废（状态机亦不设
        RUNNING→CANCELLED 出边）；终态同理拒绝。他人/无效 job → 30004，与 get_job 同
        口径（不泄露他人 job 是否存在）。
        """
        job = await self.get_job(user_id, job_id)
        if job is None:
            raise ResourceNotFoundError(job_id)
        if job.status == "RUNNING":
            raise JobStateInvalidError(f"任务执行中，无法取消（当前进度 {job.progress}%）")
        if job.status != "QUEUED":
            raise JobStateInvalidError(f"任务已终结（{job.status}），无法取消")
        validate_transition(JOB_DOMAIN, job.status, "CANCELLED")  # 先校验后写库
        await self._repo.set_status(job_id, "CANCELLED", "cancelled: 用户取消")
        await self._commit()  # B-T8R：状态机写路径终点持久化
        job = await self._repo.refresh(job_id)  # commit 后属性已过期，须显式重取再组视图
        if job is None:
            raise ResourceNotFoundError(job_id)
        return self._view(job)

    async def cancel_job_any(self, job_id: str) -> dict[str, Any]:
        """R7.4.1：admin 跨用户取消 Job——不做归属校验。

        与 cancel_job 的差异仅在归属：本方法直接按 id 取 Job，不检查 user_id。
        状态机语义完全一致：仅 QUEUED → CANCELLED；RUNNING 拒绝；终态拒绝。
        """
        job = await self._repo.get_by_id(job_id)
        if job is None:
            raise ResourceNotFoundError(job_id)
        if job.status == "RUNNING":
            raise JobStateInvalidError(f"任务执行中，无法取消（当前进度 {job.progress}%）")
        if job.status != "QUEUED":
            raise JobStateInvalidError(f"任务已终结（{job.status}），无法取消")
        validate_transition(JOB_DOMAIN, job.status, "CANCELLED")
        await self._repo.set_status(job_id, "CANCELLED", "cancelled: admin 取消")
        await self._commit()
        job = await self._repo.refresh(job_id)
        if job is None:
            raise ResourceNotFoundError(job_id)
        return self._view(job)

    async def _require(self, job_id: str) -> Job:
        job = await self._repo.get_by_id(job_id)
        if job is None:
            raise ResourceNotFoundError(job_id)
        return job
