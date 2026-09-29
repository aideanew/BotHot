/**
 * lib/api/subscriptions —— 整号订阅域（AB-P004 P2，v0.5 契约）
 *
 * 契约：POST /api/v1/sources（注册公众号）、POST/GET /api/v1/spaces/{id}/subscriptions。
 * Job 端点（jobs/{id}、retry、cancel、清单分页）已迁入 lib/api/jobs —— Job 是用户级域，
 * 订阅是空间级域（R0.4.3 分家）。
 * 该域无 mock 分支：整号采集依赖真实后端 Job 链路。
 */

import { request } from "./http";
import type {
  RegisterSourceResult,
  SubscribeResult,
  SubscriptionItem,
  SubscriptionView,
  UpdateSubscriptionPayload,
} from "./types";

/** POST /api/v1/sources —— 注册公众号 Source（biz 或 profile_url 二选一；幂等）。 */
export async function registerSource(payload: {
  biz?: string;
  profile_url?: string;
  name?: string;
}): Promise<RegisterSourceResult> {
  return request<RegisterSourceResult>("/api/v1/sources", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

/** POST /api/v1/spaces/{id}/subscriptions —— 订阅整号（幂等；首次建 Job）。 */
export async function subscribeToSource(
  spaceId: string,
  sourceId: string,
  syncPolicy?: string
): Promise<SubscribeResult> {
  return request<SubscribeResult>(
    `/api/v1/spaces/${encodeURIComponent(spaceId)}/subscriptions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_id: sourceId, sync_policy: syncPolicy ?? "auto" }),
    }
  );
}

/** GET /api/v1/spaces/{id}/subscriptions —— 订阅列表（含 latestJobId）。 */
export async function listSubscriptions(spaceId: string): Promise<SubscriptionItem[]> {
  return request<{ items: SubscriptionItem[] }>(
    `/api/v1/spaces/${encodeURIComponent(spaceId)}/subscriptions`
  ).then((d) => d.items);
}

/**
 * R0.2.3 —— PATCH /api/v1/spaces/{id}/subscriptions/{subId}：改同步策略 / 同步间隔（部分更新）。
 * 间隔只可能把 nextRunAt 往前拉（更频繁），绝不把已逾期的同步往后推；已退订不再重排。
 * 取值越界 → 10005/422；越权或无效 → 30004。
 */
export async function updateSubscription(
  spaceId: string,
  subscriptionId: string,
  payload: UpdateSubscriptionPayload
): Promise<SubscriptionView> {
  return request<SubscriptionView>(
    `/api/v1/spaces/${encodeURIComponent(spaceId)}/subscriptions/${encodeURIComponent(subscriptionId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}

/**
 * R0.2.3 —— DELETE /api/v1/spaces/{id}/subscriptions/{subId}：退订（软取消，幂等）。
 * 只停未来同步，**不删任何文档/资产/清单**；已退订 → 200 且 `cancelled=false`。
 */
export async function cancelSubscription(
  spaceId: string,
  subscriptionId: string
): Promise<SubscriptionView> {
  return request<SubscriptionView>(
    `/api/v1/spaces/${encodeURIComponent(spaceId)}/subscriptions/${encodeURIComponent(subscriptionId)}`,
    { method: "DELETE" }
  );
}
