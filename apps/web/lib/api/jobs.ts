/**
 * lib/api/jobs —— 任务域（R0.4，API 契约 v0.13）
 *
 * 契约：GET /api/v1/jobs（清单分页）、GET /api/v1/jobs/{id}（详情轮询）、
 * POST /api/v1/jobs/{id}/retry（失败重试）、POST /api/v1/jobs/{id}/cancel（R0.4.2）。
 *
 * 与 subscriptions.ts 分家：Job 是**用户级**域（跨空间），订阅是**空间级**域。
 * `getJob`/`retryJob` 原落位在 subscriptions.ts（因最初由订阅页调用），随任务中心页
 * （R0.4.3）迁入本域；调用点经 barrel 导入，故零改动。
 * 该域无 mock 分支：Job 进度依赖真实后端链路（与 subscriptions.ts 同口径）。
 */

import { request } from "./http";
import type {
  JobListItem,
  JobView,
  JobsPage,
  ListJobsOptions,
  RetryResult,
} from "./types";

/** Job 类型 → 中文。
 *
 * 取值镜像后端两个硬编码字面量（`services/batch_ingest.py` 的 `JOB_TYPE_BATCH` 与
 * `services/subscription.py` 的 `type="sync_account"`），属**跨语言重复源**——后端新增
 * 类型须同步此处，否则新任务在清单里显示为裸常量（`jobTypeLabel` 已做回落，不会崩）。
 */
export const JOB_TYPE_LABELS: Record<string, string> = {
  batch_ingest: "批量入库",
  sync_account: "整号同步",
};

/** Job 状态 → 中文（对齐 `models/entities.py` Job 状态机，含 R0.4.2 新增终态 CANCELLED）。 */
export const JOB_STATUS_LABELS: Record<string, string> = {
  QUEUED: "排队中",
  RUNNING: "执行中",
  SUCCEEDED: "已完成",
  PARTIAL_SUCCESS: "部分成功",
  FAILED: "失败",
  CANCELLED: "已取消",
};

/** 状态 → 中文；未知取值回落原值，不伪造状态（读路径无校验闸门）。 */
export function jobStatusLabel(status: string): string {
  return JOB_STATUS_LABELS[status] ?? status;
}

/** 用户任务页可重试状态：终态且存在失败篇目（QUEUED 无失败项，RUNNING 在跑）。 */
export const RETRYABLE_STATUSES = new Set(["FAILED", "PARTIAL_SUCCESS"]);

/**
 * 管理台可重试状态 —— 镜像后端 `services/subscription.py:retry_job_any` 的准入集合
 * （`job.status not in ("FAILED", "CANCELLED", "PARTIAL_SUCCESS")` 即 30005）。
 * 比用户侧多出 CANCELLED：运营需要能重新入队被取消的任务。
 */
export const ADMIN_RETRYABLE_STATUSES = new Set(["FAILED", "PARTIAL_SUCCESS", "CANCELLED"]);

/** 类型 → 中文；未知取值回落原值。 */
export function jobTypeLabel(type: string): string {
  return JOB_TYPE_LABELS[type] ?? type;
}

/**
 * Job `error` 字段的可展示文本。
 *
 * 后端统一写成 `reason: 中文说明`（`worker_stale:` / `no_items:` / `all_failed:` /
 * `cancelled:`），前缀是给日志检索用的机器标识，不是给人看的。故取首段冒号之后的部分；
 * 无前缀时原样返回。空串回空串（不渲染占位）。
 */
export function jobErrorText(error: string): string {
  const s = error ?? "";
  const i = s.indexOf(": ");
  return i >= 0 ? s.slice(i + 2) : s;
}

/** GET /api/v1/jobs/{id} —— Job 状态 + JobItem 进度（轮询 5s）。 */
export async function getJob(jobId: string): Promise<JobView> {
  return request<JobView>(`/api/v1/jobs/${encodeURIComponent(jobId)}`);
}

/** POST /api/v1/jobs/{id}/retry —— FAILED JobItem 单篇重试（幂等）。 */
export async function retryJob(jobId: string): Promise<RetryResult> {
  return request<RetryResult>(`/api/v1/jobs/${encodeURIComponent(jobId)}/retry`, {
    method: "POST",
  });
}

/**
 * GET /api/v1/jobs —— 任务清单分页（R0.4.1）。
 *
 * `type`/`status` 是**取值过滤**而非域校验：未知取值后端返**空列表**而非 422。
 * 空串按「不过滤」处理——后端对 `?status=` 空串同样视为不过滤，但那样会把筛选静默
 * 变成「全部」，与用户点选的意图相反，故此处主动不发（与 `listSpaceDocs` 的 `category` 同口径）。
 */
export async function listJobs(opts: ListJobsOptions = {}): Promise<JobsPage> {
  const q = new URLSearchParams();
  q.set("limit", String(opts.limit ?? 50));
  q.set("offset", String(opts.offset ?? 0));
  if (opts.type) q.set("type", opts.type);
  if (opts.status) q.set("status", opts.status);
  return request<JobsPage>(`/api/v1/jobs?${q.toString()}`);
}

/**
 * POST /api/v1/jobs/{id}/cancel —— 取消排队任务（R0.4.2）→ `CANCELLED`。
 *
 * 仅 `QUEUED` 可取消；`RUNNING` → 30005（进度在 message 里）、终态 → 30005、
 * 他人/无效 job → 30004（与 `get_job` 同口径，不泄露存在性）。
 */
export async function cancelJob(jobId: string): Promise<JobListItem> {
  return request<JobListItem>(`/api/v1/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST",
  });
}
