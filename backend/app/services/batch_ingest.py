"""T2.6 批量粘贴 Job 化（后端半程）：批量 URL → Job(batch_ingest) + JobItem 簇。

设计口径（大纲 v1.4 §8.1 序6 验收锚「50 篇批量 202 + 刷新进度不丢 + PARTIAL 重试可用」）：
- **提交即返**：同步阶段**零网络抓取**，仅校验 + 建 Job/JobItem 落库即 202 返回；
- **逐篇复用缓存链**：JobItem 交 T2.3 JobWorker 消费，逐篇走 `kb.ingest_url`，
  完整复用 T2.7 锁定的五层幂等（短链映射 / READY 缓存 / uq_doc_asset_space /
  version+1 / 公共库 skipped）——零新增抓取逻辑（大纲 T2.3.2 口径）；
- **幂等提交**：键 `batch_ingest:{空间}:{URL 集指纹}`（指纹与提交顺序无关）——
  同批在途（QUEUED/RUNNING）复用同一 Job（防双击双份排队）；已终态则换新键重建
  （允许重复采集，重复入库由 ingest 幂等链拦截，不产生重复 doc）；
- **进度不丢**：Job/JobItem 持久化，刷新后凭 jobId 经 `GET /jobs/{id}` 轮询恢复
  （复用 T2.3 既有读端点，T5.1 任务中心零额外路由）。

边界取舍（防复议）：提交阶段只校验 URL **形态**（http(s) + 长度 + 非空），
不校验域名白名单——域名合法性由逐篇链路的 resolver 判定，非法篇目落 JobItem
FAILED 并计入 PARTIAL_SUCCESS（T2.3.3 重试端点已覆盖）。此处若再做域名过滤，
会产生与 `providers/source_resolver.py:ALLOWED_HOSTS` 并行的第二套规则（漂移风险）。

事务约定（与 subscription.py 同口径）：Service 显式 commit，repo 只 flush。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import MalformedUrlError, RequestInvalidError, ResourceNotFoundError
from app.repositories.job import JobItemRepository, JobRepository
from app.repositories.space import SpaceRepository

JOB_TYPE_BATCH = "batch_ingest"
DEFAULT_MAX_URLS = 50
_URL_MAX_LEN = 512  # 与 job_items.url 列宽一致
# 终态判定含 CANCELLED：用户取消的批次若不在此列，其幂等键会被永久判为「在途」，
# 同一批次再也无法重新采集（R0.4.2 引入 CANCELLED 后的必要联动）。
_TERMINAL_STATUSES = ("SUCCEEDED", "PARTIAL_SUCCESS", "FAILED", "CANCELLED")


def _article_key(url: str) -> str:
    """URL → 文章幂等键（口径必须与 `kb._article_key` 一致；单源 kb.py 的 `_article_key`）。

    仅用于 `job_items.external_id` 的可追溯标注——无消费方依赖此值做去重
    （worker 只用 `item.url`；`_compute_new_manifests` 仅筛 sync_account 族），
    故不跨模块引私有函数，漂移影响面仅限后台列表面读。
    """
    tail = re.sub(r"[?&#].*$", "", url).rstrip("/").rsplit("/", 1)[-1]
    return tail or url


def _fingerprint(urls: list[str]) -> str:
    """同批 URL 的稳定指纹：排序后 sha1 取前 40 位（与提交顺序无关）。"""
    return hashlib.sha1("|".join(sorted(urls)).encode("utf-8")).hexdigest()[:40]


class BatchIngestService:
    """批量粘贴编排层：空间归属校验 → URL 归一化 → 建 Job + JobItem → commit。"""

    def __init__(self, session: AsyncSession, *, max_urls: int | None = None) -> None:
        self._session = session
        self._job_repo = JobRepository(session)
        self._item_repo = JobItemRepository(session)
        self._space_repo = SpaceRepository(session)
        if max_urls is None:
            max_urls = int(getattr(get_settings(), "batch_ingest_max_urls", DEFAULT_MAX_URLS))
        self._max_urls = max_urls

    async def submit_batch(
        self, user_id: str, space_id: str, raw_urls: list[str]
    ) -> dict[str, Any]:
        """POST /spaces/{id}/docs:batch → {jobId,status,counts,reused,urlCount}。

        越权/无效空间 → 30004；空批或超上限 → 10005；非 http(s)/超长 URL → 10006。
        同批在途 Job 复用（`reused=True`，不重建 JobItem，不重复计数）。
        """
        space = await self._space_repo.get_by_id(space_id)
        if space is None or space.user_id != user_id:
            raise ResourceNotFoundError(space_id)

        urls = self._normalize(raw_urls)
        job, reused = await self._create_batch_job(user_id, space_id, urls)
        await self._session.commit()
        return {
            "jobId": job.id,
            "status": job.status,
            "counts": await self._item_repo.counts(job.id),
            "reused": reused,
            "urlCount": len(urls),
        }

    # ------------------------------------------------------------------ 内部

    def _normalize(self, raw_urls: list[str] | None) -> list[str]:
        """归一化：逐条 strip → 形态校验 → 保序去重（去重提示量由前端 parseBatchUrls 承担）。"""
        urls: list[str] = []
        seen: set[str] = set()
        for raw in raw_urls or []:
            url = str(raw).strip()
            if not url:
                continue  # 空行/纯空白：静默跳过（粘贴尾行常见），不算错误
            if not (url.startswith("http://") or url.startswith("https://")):
                raise MalformedUrlError(f"非 http(s) 链接：{url[:80]}")
            if len(url) > _URL_MAX_LEN:
                raise MalformedUrlError(f"链接超长（>{_URL_MAX_LEN} 字符）：{url[:80]}")
            if url not in seen:
                seen.add(url)
                urls.append(url)
        if not urls:
            raise RequestInvalidError("批量列表为空或全部无效，请至少提交一条有效链接")
        if len(urls) > self._max_urls:
            raise RequestInvalidError(f"批量条数 {len(urls)} 超过单次上限 {self._max_urls}")
        return urls

    async def _create_batch_job(
        self, user_id: str, space_id: str, urls: list[str]
    ) -> tuple[Any, bool]:
        """建 Job(batch_ingest) + 逐篇 JobItem(PENDING)；返回 (job, reused)。

        幂等键 `batch_ingest:{空间}:{指纹}` 的三段语义：
        - 键冲突且 Job 在途（QUEUED/RUNNING）→ **复用**（防双击/重复提交双份排队）；
        - 键冲突且 Job 已终态 → 换新键 `:r{n}` 重建（允许重复采集同一批 URL）；
        - 键不冲突 → 新建并装配 JobItem。
        新建时 status 即 QUEUED（Job model 默认值），无需再 set_status。
        """
        payload = json.dumps(
            {"space_id": space_id, "urlCount": len(urls)}, ensure_ascii=False
        )
        base_key = f"{JOB_TYPE_BATCH}:{space_id}:{_fingerprint(urls)}"
        for seq in range(1, 65):
            key = base_key if seq == 1 else f"{base_key}:r{seq}"
            job, created = await self._job_repo.create_or_get(
                type=JOB_TYPE_BATCH,
                user_id=user_id,
                payload=payload,
                idempotency_key=key,
            )
            if created:
                for url in urls:
                    item = await self._item_repo.create(
                        job_id=job.id, external_id=_article_key(url), url=url
                    )
                    await self._item_repo.set_status(item.id, "PENDING")
                return job, False
            if job.status in _TERMINAL_STATUSES:
                continue  # 终态：允许重复采集，换新键再试
            return job, True  # 在途：复用，零重复入队

        msg = f"幂等键空间耗尽（{base_key} 下已有 64 个同批 Job），请稍后或清理终态 Job"
        raise RequestInvalidError(msg)
