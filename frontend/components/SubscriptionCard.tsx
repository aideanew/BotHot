import SubscriptionLifecycleActions, { cadenceLabel } from "./SubscriptionLifecycleActions";
import { jobStatusLabel } from "@/lib/api";
import type { JobView, SubscriptionItem, SubscriptionView } from "@/lib/api";

interface SubscriptionCardProps {
  sub: SubscriptionItem;
  job?: JobView;
  spaceId: string;
  onRetry: (jobId: string) => void;
  onSubscriptionChange: (view: SubscriptionView) => void;
}

/** 紧凑时间（下次同步用）：MM/DD HH:mm，避免整行被完整 locale 串撑爆。 */
function shortDateTime(iso: string): string {
  return new Date(iso).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export default function SubscriptionCard({
  sub,
  job,
  spaceId,
  onRetry,
  onSubscriptionChange,
}: SubscriptionCardProps) {
  const total = job?.counts?.total ?? 0;
  const done = (job?.counts?.succeeded ?? 0) + (job?.counts?.failed ?? 0);
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  const partial =
    job?.status === "PARTIAL_SUCCESS" || (job?.counts?.failed ?? 0) > 0;
  // 退订是软取消、订阅行仍会留在清单里（历史痕迹）。若不单独判态，取消的订阅
  // 会一直显示「等待首次同步」——用户会以为它还在排队等采集（2026-09-25 实测）
  const cancelled = sub.status === "CANCELLED";

  return (
    <li className="card p-4">
      <div className="flex items-center justify-between">
        <div className="min-w-0 flex-1">
          <p className="truncate text-base font-medium text-neutral-900">
            {sub.sourceName || sub.biz}
            <span className="ml-2 text-caption text-neutral-400">
              {sub.biz} · {sub.syncPolicy}
            </span>
          </p>
          <p className="mt-1 text-caption text-neutral-400">
            {cancelled
              ? "已退订，不再同步"
              : job?.status
                ? `任务状态：${jobStatusLabel(job.status)}`
                : "等待首次同步"}
          </p>
          <p className="mt-1 text-caption text-neutral-600">
            同步节奏：{cadenceLabel(sub)}
            {!cancelled && sub.nextRunAt ? ` · 下次同步：${shortDateTime(sub.nextRunAt)}` : ""}
          </p>
          <p className="mt-1 text-caption text-neutral-500">
            预计篇数：{sub.discoveredCount ?? 0} 篇
            {sub.lastSuccessAt
              ? ` · 上次成功：${new Date(sub.lastSuccessAt).toLocaleString("zh-CN")}`
              : " · 尚无成功同步"}
            {(sub.consecutiveEmptySyncs ?? 0) > 0 &&
              ` · 连续 ${sub.consecutiveEmptySyncs} 次无新文章`}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          {partial && job && (
            <div className="flex shrink-0 flex-col items-end gap-1">
              <button
                type="button"
                onClick={() => onRetry(job.jobId)}
                className="rounded border border-amber-400 px-3 py-1 text-caption text-amber-700 hover:bg-amber-50"
              >
                重试失败 {job.counts?.failed ?? 0} 篇
              </button>
              <span className="text-caption text-neutral-400">
                将按单篇重走入库流水线（worker 执行循环 M3 接线前仅重置任务状态）
              </span>
            </div>
          )}
          <SubscriptionLifecycleActions
            spaceId={spaceId}
            subscription={sub}
            onChanged={onSubscriptionChange}
            onCancelled={onSubscriptionChange}
          />
        </div>
      </div>
      {total > 0 && (
        <div className="mt-3">
          <div className="mb-1 flex justify-between text-caption text-neutral-500">
            <span>{done}/{total} 篇</span>
            <span>{pct}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded bg-neutral-100">
            <div
              className={`h-full transition-all ${
                partial ? "bg-amber-500" : "bg-brand-500"
              }`}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}
    </li>
  );
}
