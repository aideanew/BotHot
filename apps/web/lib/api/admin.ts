/**
 * lib/api/admin —— 后台管理域（SPEC-M3 批次 2 读面 + 批次 4 批量操作，A-2 叠加裁定）
 *
 * 契约：GET /api/v1/admin/spaces、GET /api/v1/admin/spaces/{id}/docs、
 * POST /api/v1/admin/spaces/{id}/docs:delete、POST /api/v1/admin/spaces/{id}/docs:recategorize、
 * DELETE /api/v1/admin/spaces/{id}（R6.6.7）、
 * GET /api/v1/admin/jobs、GET /api/v1/admin/jobs/{id}、
 * POST /api/v1/admin/jobs/{id}:cancel / :retry（R7.4.1~2）、
 * GET /api/v1/admin/subscriptions、DELETE /api/v1/admin/subscriptions/{id}（R7.4.3）、
 * GET /api/v1/admin/sources、DELETE /api/v1/admin/sources/{id}（R7.4.4~5）。
 *
 * 该域无 mock 分支：admin 能力只能来自后端 admin 端点（require_roles("admin")），
 * 演示模式照造跨用户空间数据等于伪造授权面，故承 engines 域纪律直接真实请求。
 * 未登录 → 10001；非 admin → 10004，由调用方按门禁分支处理。
 */

import { request } from "./http";
import type {
  AdminSpace,
  DeleteDocResult,
  DeleteDocsBatchResult,
  ListSpaceDocsOptions,
  PatchAdminSpaceResult,
  RecategorizeDocsBatchResult,
  SpaceDocsPage,
  JobListItem,
  JobsPage,
  ListJobsOptions,
  RetryResult,
  SubscriptionItem,
  SubscriptionView,
} from "./types";

/**
 * GET /api/v1/admin/spaces —— 跨用户空间清单（含归属）。
 * 后端仅在归属行存在时注入 ownerId/ownerSub/ownerNickname（LEFT JOIN 孤儿行不丢空间），
 * 此处统一回填空串，渲染层不处理 undefined。
 */
export async function listAdminSpaces(): Promise<AdminSpace[]> {
  return request<{ items: AdminSpace[] }>("/api/v1/admin/spaces").then((d) =>
    (d.items ?? []).map((s) => ({
      ...s,
      ownerId: s.ownerId ?? "",
      ownerSub: s.ownerSub ?? "",
      ownerNickname: s.ownerNickname ?? "",
    }))
  );
}

/**
 * GET /api/v1/admin/spaces/{id}/docs —— 跨用户文档清单（批量操作面板的目标来源）。
 * 形状、分页与过滤语义与用户端点一致（total 与 items 同谓词）。
 */
export async function listAdminSpaceDocs(
  id: string,
  opts: ListSpaceDocsOptions = {}
): Promise<SpaceDocsPage> {
  const q = new URLSearchParams();
  q.set("limit", String(opts.limit ?? 100));
  q.set("offset", String(opts.offset ?? 0));
  if (opts.category) q.set("category", opts.category);
  return request<SpaceDocsPage>(
    `/api/v1/admin/spaces/${encodeURIComponent(id)}/docs?${q.toString()}`
  );
}

/**
 * PATCH /api/v1/admin/spaces/{spaceId} —— 跨用户改空间简介（R5.4.1）。
 * description 为空串时传 null（后端以 null 清空简介，空串会被视为空值校验失败 10005）。
 * 响应为写回执 {ok, id, description}。
 */
export async function patchAdminSpaceDescription(
  spaceId: string,
  description: string
): Promise<PatchAdminSpaceResult> {
  return request<PatchAdminSpaceResult>(
    `/api/v1/admin/spaces/${encodeURIComponent(spaceId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: description || null }),
    }
  );
}

/**
 * DELETE /api/v1/admin/spaces/{spaceId} —— 跨用户删空间（R6.6.7）。
 * admin 绕过归属校验，级联删 docs/assets/space 行 + 引擎删库。
 * 200 {ok, docs, assets, spaces}——返回级联删除计数。
 * 未登录 → 10001；非 admin → 10004/403；无效空间 → 30004。
 */
export async function deleteAdminSpace(
  spaceId: string
): Promise<{ ok: boolean; docs: number; assets: number; spaces: number }> {
  return request<{
    ok: boolean;
    docs: number;
    assets: number;
    spaces: number;
  }>(`/api/v1/admin/spaces/${encodeURIComponent(spaceId)}`, {
    method: "DELETE",
  });
}

/**
 * DELETE /api/v1/admin/spaces/{spaceId}/docs/{docId} —— 跨用户删单篇文档（R5.4.2）。
 * 语义与用户端点一致：引擎文件先删 → PG 行，失败整体回滚。
 * 无效空间 / doc 不存在或不属于该空间 → 30004。
 */
export async function deleteAdminSpaceDoc(
  spaceId: string,
  docId: string
): Promise<DeleteDocResult> {
  return request<DeleteDocResult>(
    `/api/v1/admin/spaces/${encodeURIComponent(spaceId)}/docs/${encodeURIComponent(docId)}`,
    { method: "DELETE" }
  );
}

/**
 * POST /api/v1/admin/spaces/{id}/docs:delete —— 跨用户批量删除（单次上限 50，篇级部分成功）。
 * 语义与用户端点一致：failed 为空即全成功；全批失败、无效空间、任一篇 doc 缺失或
 * 不属于该空间 → 错误信封上抛，不返回 200 空结果。
 */
export async function deleteAdminSpaceDocsBatch(
  spaceId: string,
  ids: string[]
): Promise<DeleteDocsBatchResult> {
  return request<DeleteDocsBatchResult>(
    `/api/v1/admin/spaces/${encodeURIComponent(spaceId)}/docs:delete`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    }
  );
}

/**
 * POST /api/v1/admin/spaces/{id}/docs:recategorize —— 跨用户批量改分类（单次上限 50）。
 * **整批原子**：全批成功或全批不生效；category 为资产级属性，对本资产在其他
 * 空间的呈现一并生效（与用户端点同语义）。
 */
export async function recategorizeAdminSpaceDocsBatch(
  spaceId: string,
  ids: string[],
  category: string
): Promise<RecategorizeDocsBatchResult> {
  return request<RecategorizeDocsBatchResult>(
    `/api/v1/admin/spaces/${encodeURIComponent(spaceId)}/docs:recategorize`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, category }),
    }
  );
}

/**
 * GET /api/v1/admin/jobs —— 跨用户 Job 清单（R4.8）。
 * 形状与 GET /api/v1/jobs 一致，不按 user_id 过滤。
 */
export async function listAdminJobs(
  opts: ListJobsOptions = {}
): Promise<JobsPage> {
  const q = new URLSearchParams();
  q.set("limit", String(opts.limit ?? 50));
  q.set("offset", String(opts.offset ?? 0));
  if (opts.type) q.set("type", opts.type);
  if (opts.status) q.set("status", opts.status);
  return request<JobsPage>(`/api/v1/admin/jobs?${q.toString()}`);
}

/**
 * GET /api/v1/admin/subscriptions —— 跨用户订阅清单（R4.8）。
 * space_id 省略 → 全系统；提供 → 该空间。
 */
export async function listAdminSubscriptions(
  spaceId?: string
): Promise<SubscriptionItem[]> {
  const q = new URLSearchParams();
  if (spaceId) q.set("space_id", spaceId);
  const qs = q.toString();
  return request<{ items: SubscriptionItem[] }>(
    `/api/v1/admin/subscriptions${qs ? `?${qs}` : ""}`
  ).then((d) => d.items);
}

/**
 * POST /api/v1/admin/jobs/{id}:cancel —— 跨用户取消 Job（R7.4.1）。
 * admin 绕过归属校验，状态机与用户端 cancel_job 一致。
 * QUEUED → CANCELLED；RUNNING → 30005；终态 → 30005。
 */
export async function cancelAdminJob(jobId: string): Promise<JobListItem> {
  return request<JobListItem>(
    `/api/v1/admin/jobs/${encodeURIComponent(jobId)}:cancel`,
    { method: "POST" }
  );
}

/**
 * POST /api/v1/admin/jobs/{id}:retry —— 跨用户重试 Job（R7.4.2）。
 * admin 绕过归属校验。FAILED JobItem → PENDING + Job → RUNNING（审计保留）。
 */
export async function retryAdminJob(jobId: string): Promise<RetryResult> {
  return request<RetryResult>(
    `/api/v1/admin/jobs/${encodeURIComponent(jobId)}:retry`,
    { method: "POST" }
  );
}

/**
 * DELETE /api/v1/admin/subscriptions/{id} —— 跨用户退订（R7.4.3）。
 * admin 绕过归属校验。只停未来同步，不删文档/资产/清单。
 */
export async function cancelAdminSubscription(
  subscriptionId: string
): Promise<SubscriptionView> {
  return request<SubscriptionView>(
    `/api/v1/admin/subscriptions/${encodeURIComponent(subscriptionId)}`,
    { method: "DELETE" }
  );
}

/**
 * GET /api/v1/admin/sources —— 跨用户来源清单含引用计数（R7.4.4）。
 * 增量字段：subscriptionCount / assetCount / manifestCount（决策删除安全性）。
 */
export async function listAdminSources(): Promise<
  { items: AdminSourceItem[] }
> {
  return request<{ items: AdminSourceItem[] }>("/api/v1/admin/sources");
}

/**
 * DELETE /api/v1/admin/sources/{id} —— 跨用户删来源（R7.4.5）。
 * 复用用户端 delete_source，admin 绕过归属校验。
 */
export async function deleteAdminSource(
  sourceId: string
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(
    `/api/v1/admin/sources/${encodeURIComponent(sourceId)}`,
    { method: "DELETE" }
  );
}

export interface AdminSourceItem {
  id: string;
  biz: string;
  name: string;
  profileUrl: string;
  subscriptionCount: number;
  assetCount: number;
  manifestCount: number;
}
